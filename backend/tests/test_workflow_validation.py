"""Unit tests for workflow graph validation. No database or HTTP involved."""

import pytest

from app.workflow_schema import Definition
from app.workflow_validation import has_errors, validate_definition


def node(node_id, kind, config=None):
    return {"id": node_id, "type": kind, "label": node_id, "position": {"x": 0, "y": 0}, "config": config or {}}


def edge(edge_id, source, target, handle=None):
    return {"id": edge_id, "source": source, "target": target, "source_handle": handle, "label": ""}


def codes(definition: dict) -> set[str]:
    issues = validate_definition(Definition.model_validate(definition))
    return {issue.code for issue in issues if issue.severity == "error"}


def sales_order_graph() -> dict:
    """Trigger, AI risk check, approval above a threshold, ERP write, email, and two endings."""
    return {
        "nodes": [
            node("t", "trigger", {"event": "hubspot.order.created"}),
            node("ai", "ai_agent", {"instructions": "Assess the risk of this order."}),
            node("c", "condition", {"field": "order.total", "operator": "gt", "value": 50000}),
            node("a", "approval", {"approver_role": "admin"}),
            node("erp", "erp", {"integration": "erpnext", "action": "create_sales_order"}),
            node("mail", "email", {"to": "{{customer.email}}", "subject": "Order confirmed", "body": "Thanks."}),
            node("ok", "end"),
            node("no", "end"),
        ],
        "edges": [
            edge("e1", "t", "ai"),
            edge("e2", "ai", "c"),
            edge("e3", "c", "a", "true"),
            edge("e4", "c", "erp", "false"),
            edge("e5", "a", "erp", "approved"),
            edge("e6", "a", "no", "rejected"),
            edge("e7", "erp", "mail"),
            edge("e8", "mail", "ok"),
        ],
    }


def test_complete_sales_order_workflow_is_valid():
    assert codes(sales_order_graph()) == set()


def test_empty_workflow_asks_for_a_trigger():
    assert codes({"nodes": [], "edges": []}) == {"empty_workflow"}


def test_missing_trigger_and_end():
    graph = {"nodes": [node("x", "delay", {"seconds": 5})], "edges": []}
    found = codes(graph)
    assert {"missing_trigger", "missing_end", "dead_end"} <= found


def test_only_one_trigger_allowed():
    graph = sales_order_graph()
    graph["nodes"].append(node("t2", "trigger", {"event": "manual"}))
    graph["edges"].append(edge("e9", "t2", "ok"))
    assert "multiple_triggers" in codes(graph)


def test_trigger_cannot_have_input():
    graph = sales_order_graph()
    graph["edges"].append(edge("e9", "mail", "t"))
    assert "trigger_has_input" in codes(graph)


def test_condition_requires_both_branches():
    graph = sales_order_graph()
    graph["edges"] = [e for e in graph["edges"] if e["id"] != "e4"]
    found = codes(graph)
    assert "missing_branch" in found


def test_approval_requires_rejected_path():
    """Rejected orders must lead somewhere explicit, so they cannot fall through as approved."""
    graph = sales_order_graph()
    graph["edges"] = [e for e in graph["edges"] if e["id"] != "e6"]
    assert "missing_branch" in codes(graph)


def test_ambiguous_branch_is_rejected():
    graph = sales_order_graph()
    graph["edges"].append(edge("e9", "c", "ok", "true"))
    assert "ambiguous_branch" in codes(graph)


def test_unknown_branch_name_is_rejected():
    graph = sales_order_graph()
    graph["edges"].append(edge("e9", "c", "ok", "maybe"))
    assert "unknown_branch" in codes(graph)


def test_plain_node_cannot_fan_out():
    graph = sales_order_graph()
    graph["edges"].append(edge("e9", "ai", "ok"))
    assert "multiple_outputs" in codes(graph)


def test_plain_node_cannot_use_named_outputs():
    graph = sales_order_graph()
    graph["edges"] = [dict(e, source_handle="true") if e["id"] == "e1" else e for e in graph["edges"]]
    assert "unexpected_handle" in codes(graph)


def test_end_node_has_no_outputs():
    graph = sales_order_graph()
    graph["edges"].append(edge("e9", "ok", "no"))
    assert "end_has_output" in codes(graph)


def test_unreachable_node_is_reported():
    graph = sales_order_graph()
    graph["nodes"].append(node("orphan", "end"))
    assert "unreachable" in codes(graph)


def test_cycle_is_rejected():
    graph = {
        "nodes": [
            node("t", "trigger", {"event": "manual"}),
            node("d1", "delay", {"seconds": 5}),
            node("d2", "delay", {"seconds": 5}),
            node("e", "end"),
        ],
        "edges": [edge("1", "t", "d1"), edge("2", "d1", "d2"), edge("3", "d2", "d1")],
    }
    assert "cycle" in codes(graph)


def test_dangling_and_self_edges_and_duplicates():
    graph = sales_order_graph()
    graph["edges"].append(edge("x1", "t", "ghost"))
    graph["edges"].append(edge("x2", "ai", "ai"))
    graph["edges"].append(edge("x3", "t", "ai"))
    found = codes(graph)
    assert {"dangling_edge", "self_loop", "duplicate_edge"} <= found


def test_duplicate_node_ids():
    graph = sales_order_graph()
    graph["nodes"].append(node("t", "end"))
    assert "duplicate_node_id" in codes(graph)


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("https://api.example.com/orders", True),
        ("http://api.example.com/orders", False),
        ("https://localhost/admin", False),
        ("https://intranet.internal/x", False),
        ("https://10.0.0.5/x", False),
        ("https://169.254.169.254/latest/meta-data", False),
        ("https://[::1]/x", False),
        ("https://user:pass@api.example.com/", False),
        ("", False),
        ("not a url", False),
    ],
)
def test_http_node_url_rules(url, ok):
    graph = {
        "nodes": [
            node("t", "trigger", {"event": "manual"}),
            node("h", "http", {"method": "POST", "url": url}),
            node("e", "end"),
        ],
        "edges": [edge("1", "t", "h"), edge("2", "h", "e")],
    }
    assert ("invalid_config" not in codes(graph) and "missing_config" not in codes(graph)) is ok


@pytest.mark.parametrize(
    ("seconds", "ok"),
    [
        (1, True),
        (86400, True),
        (2_592_000, True),
        (0, False),
        (-5, False),
        (2_592_001, False),
        (True, False),
        ("10", False),
        (1.5, False),
    ],
)
def test_delay_bounds(seconds, ok):
    graph = {
        "nodes": [
            node("t", "trigger", {"event": "manual"}),
            node("d", "delay", {"seconds": seconds}),
            node("e", "end"),
        ],
        "edges": [edge("1", "t", "d"), edge("2", "d", "e")],
    }
    assert ("invalid_config" not in codes(graph)) is ok


def test_condition_exists_operator_needs_no_value():
    graph = {
        "nodes": [
            node("t", "trigger", {"event": "manual"}),
            node("c", "condition", {"field": "customer.email", "operator": "exists"}),
            node("a", "end"),
            node("b", "end"),
        ],
        "edges": [edge("1", "t", "c"), edge("2", "c", "a", "true"), edge("3", "c", "b", "false")],
    }
    assert codes(graph) == set()


def test_condition_rejects_free_form_expressions():
    """Conditions are structured. An arbitrary expression string is not an accepted operator."""
    graph = sales_order_graph()
    for n in graph["nodes"]:
        if n["id"] == "c":
            n["config"] = {"field": "order.total", "operator": "__import__('os').system('x')", "value": 1}
    assert "missing_config" in codes(graph)


@pytest.mark.parametrize(
    ("kind", "config"),
    [
        ("trigger", {}),
        ("ai_agent", {}),
        ("transformation", {"mappings": []}),
        ("crm", {"integration": "salesforce", "action": "x"}),
        ("erp", {"integration": "erpnext"}),
        ("database", {"action": "query"}),
        ("email", {"to": "a@b.c", "subject": "s"}),
        ("approval", {"approver_role": "member"}),
    ],
)
def test_required_configuration_is_reported(kind, config):
    graph = {
        "nodes": [
            node("t", "trigger", {"event": "manual"} if kind != "trigger" else {}),
            node("n", kind, config),
            node("e", "end"),
        ],
        "edges": [edge("1", "t", "n"), edge("2", "n", "e")],
    }
    if kind == "trigger":
        graph = {"nodes": [node("t", "trigger", {}), node("e", "end")], "edges": [edge("1", "t", "e")]}
    assert "missing_config" in codes(graph)


def test_ai_agent_instruction_length_is_bounded():
    graph = sales_order_graph()
    for n in graph["nodes"]:
        if n["id"] == "ai":
            n["config"] = {"instructions": "x" * 4001}
    assert "invalid_config" in codes(graph)


def test_has_errors_ignores_warnings():
    from app.workflow_validation import Issue

    assert has_errors([Issue("x", "error", "m")])
    assert not has_errors([Issue("x", "warning", "m")])


def test_schema_rejects_unknown_node_type_and_bad_ids():
    with pytest.raises(ValueError):
        Definition.model_validate({"nodes": [node("a", "shell_command")], "edges": []})
    with pytest.raises(ValueError):
        Definition.model_validate({"nodes": [node("bad id!", "end")], "edges": []})


def test_schema_bounds_node_count_and_config_size():
    many = {"nodes": [node(f"n{i}", "end") for i in range(201)], "edges": []}
    with pytest.raises(ValueError):
        Definition.model_validate(many)
    huge = {"nodes": [node("a", "end", {"blob": "x" * 25_000})], "edges": []}
    with pytest.raises(ValueError):
        Definition.model_validate(huge)
