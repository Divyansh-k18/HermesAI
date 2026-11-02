"""Execution engine and approvals, exercised through the API with real database rows."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engine import EngineError, assign, evaluate_condition, lookup, process_due_timers
from app.models import Approval, StepExecution, WorkflowExecution, utcnow
from tests.test_workflow_validation import edge, node
from tests.test_workflows_api import add_member, base, create_org


def order_graph(with_done_step: bool = True) -> dict:
    """Orders above 50,000 need an admin's approval. Rejected orders end on their own branch."""
    nodes = [
        node("t", "trigger", {"event": "manual"}),
        node("x", "transformation", {"mappings": [{"source": "order.total", "target": "summary.total"}]}),
        node("c", "condition", {"field": "order.total", "operator": "gt", "value": 50000}),
        node("a", "approval", {"approver_role": "admin", "title": "Approve large order"}),
        node("ok", "end"),
        node("ok2", "end"),
        node("no", "end"),
    ]
    edges = [
        edge("e1", "t", "x"),
        edge("e2", "x", "c"),
        edge("e3", "c", "a", "true"),
        edge("e4", "c", "ok", "false"),
        edge("e6", "a", "no", "rejected"),
    ]
    if with_done_step:
        nodes.append(node("done", "transformation", {"mappings": [{"source": "order.id", "target": "approved_order"}]}))
        edges += [edge("e5", "a", "done", "approved"), edge("e7", "done", "ok2")]
    else:
        edges.append(edge("e5", "a", "ok2", "approved"))
    return {"nodes": nodes, "edges": edges}


def publish_and_activate(actor, org_id, workflow_id, definition, base_revision):
    saved = actor.client.put(
        f"{base(org_id)}/{workflow_id}/draft",
        headers=actor.headers(),
        json={"definition": definition, **({"base_revision": base_revision} if base_revision else {})},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["issues"] == [], saved.json()["issues"]
    revision = saved.json()["version"]["revision"]
    published = actor.post(f"{base(org_id)}/{workflow_id}/publish", json={"base_revision": revision})
    assert published.status_code == 200, published.text
    number = published.json()["version_number"]
    assert actor.post(f"{base(org_id)}/{workflow_id}/versions/{number}/activate").status_code == 200
    return number


def make_active_workflow(owner, org_id, definition=None, name="Order approval"):
    created = owner.post(base(org_id), json={"name": name}).json()
    wid = created["workflow"]["id"]
    publish_and_activate(owner, org_id, wid, definition or order_graph(), base_revision=1)
    return wid


def run(actor, org_id, workflow_id, payload=None, key=None):
    body = {"payload": payload if payload is not None else {}}
    if key:
        body["idempotency_key"] = key
    return actor.post(f"{base(org_id)}/{workflow_id}/executions", json=body)


def decide(actor, org_id, approval_id, decision, comment=""):
    return actor.post(
        f"/api/v1/orgs/{org_id}/approvals/{approval_id}/decision", json={"decision": decision, "comment": comment}
    )


@pytest.fixture()
def owner(make_account):
    return make_account("exec-owner@example.com", "Exec Owner")


@pytest.fixture()
def org(owner):
    return create_org(owner, "Exec Corp")


@pytest.fixture()
def team(owner, org, make_account):
    return {
        "admin": add_member(owner, org["id"], make_account, "exec-admin@example.com", "admin"),
        "member": add_member(owner, org["id"], make_account, "exec-member@example.com", "member"),
        "viewer": add_member(owner, org["id"], make_account, "exec-viewer@example.com", "viewer"),
    }


# --------------------------------------------------------------------------- pure helpers


def test_lookup_and_assign_paths():
    data = {"order": {"total": 10, "items": [{"sku": "A"}]}}
    assert lookup(data, "order.total") == (True, 10)
    assert lookup(data, "order.items.0.sku") == (True, "A")
    assert lookup(data, "order.missing") == (False, None)
    assert lookup(data, "order.items.5") == (False, None)
    assign(data, "summary.total", 5)
    assert data["summary"] == {"total": 5}


@pytest.mark.parametrize(
    ("operator", "actual", "expected", "result"),
    [
        ("gt", 100, 50, True),
        ("gt", "100", 50, True),
        ("gte", 50, 50, True),
        ("lt", 1, 2, True),
        ("lte", 3, 2, False),
        ("eq", "5", 5, True),
        ("eq", "gold", "gold", True),
        ("neq", "gold", "silver", True),
        ("contains", "hello world", "world", True),
        ("contains", ["a", "b"], "b", True),
    ],
)
def test_condition_operators(operator, actual, expected, result):
    config = {"field": "x", "operator": operator, "value": expected}
    assert evaluate_condition(config, {"x": actual}) is result


def test_condition_fails_closed_on_bad_data():
    with pytest.raises(EngineError):
        evaluate_condition({"field": "x", "operator": "gt", "value": 1}, {"x": "abc"})
    with pytest.raises(EngineError):
        evaluate_condition({"field": "x", "operator": "gt", "value": 1}, {})
    assert evaluate_condition({"field": "x", "operator": "exists"}, {}) is False


# --------------------------------------------------------------------------- running


def test_small_order_finishes_without_approval(owner, org):
    wid = make_active_workflow(owner, org["id"])
    r = run(owner, org["id"], wid, {"order": {"id": "SO-1", "total": 900}})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "succeeded"
    assert [s["node_id"] for s in body["steps"]] == ["t", "x", "c", "ok"]
    assert all(s["status"] == "succeeded" for s in body["steps"])
    assert body["steps"][2]["output"]["result"] is False
    assert body["variables"]["summary"] == {"total": 900}
    assert body["approvals"] == []


def test_large_order_waits_for_approval_then_continues_when_approved(owner, org, team):
    wid = make_active_workflow(owner, org["id"])
    r = run(team["member"], org["id"], wid, {"order": {"id": "SO-2", "total": 75000}})
    body = r.json()
    assert body["status"] == "waiting_approval"
    assert body["steps"][-1]["status"] == "waiting"
    # A member can see that the run is waiting but not the approval's business data.
    assert body["approvals"] == []

    pending = team["admin"].get(f"/api/v1/orgs/{org['id']}/approvals").json()
    assert len(pending) == 1
    assert pending[0]["title"] == "Approve large order"
    assert pending[0]["context"]["order"]["total"] == 75000
    assert pending[0]["can_decide"] is True

    done = decide(team["admin"], org["id"], pending[0]["id"], "approve", "Looks fine")
    assert done.status_code == 200, done.text
    final = done.json()
    assert final["status"] == "succeeded"
    assert [s["node_id"] for s in final["steps"]] == ["t", "x", "c", "a", "done", "ok2"]
    assert final["variables"]["approved_order"] == "SO-2"
    assert final["steps"][3]["output"]["decision"] == "approved"
    assert final["approvals"][0]["comment"] == "Looks fine"
    assert final["approvals"][0]["decided_by_name"]


def test_rejected_order_never_runs_the_approved_path(owner, org):
    wid = make_active_workflow(owner, org["id"])
    started = run(owner, org["id"], wid, {"order": {"id": "SO-3", "total": 90000}}).json()
    approval_id = started["approvals"][0]["id"]
    final = decide(owner, org["id"], approval_id, "reject", "Over budget").json()
    assert final["status"] == "rejected"
    assert final["outcome"] == "rejected"
    visited = [s["node_id"] for s in final["steps"]]
    assert visited == ["t", "x", "c", "a", "no"]
    assert "done" not in visited
    assert "approved_order" not in final["variables"]


def test_rejected_run_stays_rejected_even_if_wired_to_a_normal_ending(owner, org):
    """Safety net: a graph that wires rejection into the normal ending still cannot finish as succeeded."""
    graph = order_graph()
    graph["edges"] = [e for e in graph["edges"] if e["id"] != "e6"] + [edge("e6", "a", "ok2", "rejected")]
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] != "no"]  # nothing leads to it any more
    wid = make_active_workflow(owner, org["id"], graph, name="Miswired")
    started = run(owner, org["id"], wid, {"order": {"id": "SO-X", "total": 90000}}).json()
    final = decide(owner, org["id"], started["approvals"][0]["id"], "reject").json()
    assert final["status"] == "rejected"


def test_approval_authorization(owner, org, team):
    graph = order_graph()
    for n in graph["nodes"]:
        if n["id"] == "a":
            n["config"] = {"approver_role": "owner", "title": "Owner only"}
    wid = make_active_workflow(owner, org["id"], graph, name="Owner approval")
    started = run(owner, org["id"], wid, {"order": {"id": "SO-4", "total": 80000}}).json()
    approval_id = started["approvals"][0]["id"]

    assert decide(team["admin"], org["id"], approval_id, "approve").status_code == 403
    assert decide(team["member"], org["id"], approval_id, "approve").status_code == 403
    assert decide(team["viewer"], org["id"], approval_id, "approve").status_code == 403
    # Nothing moved: the run is still waiting and the approval is still pending.
    still = owner.get(f"/api/v1/orgs/{org['id']}/executions/{started['id']}").json()
    assert still["status"] == "waiting_approval"
    assert still["approvals"][0]["status"] == "pending"
    # A denied attempt is audited.
    events = owner.get(f"/api/v1/orgs/{org['id']}/audit-events?limit=200").json()
    assert any(e["action"] == "approval.decision" and e["outcome"] == "rejected" for e in events)

    assert decide(owner, org["id"], approval_id, "approve").status_code == 200


def test_members_and_viewers_cannot_list_approvals(owner, org, team):
    wid = make_active_workflow(owner, org["id"])
    run(owner, org["id"], wid, {"order": {"id": "SO-5", "total": 99999}})
    assert team["member"].get(f"/api/v1/orgs/{org['id']}/approvals").status_code == 403
    assert team["viewer"].get(f"/api/v1/orgs/{org['id']}/approvals").status_code == 403
    assert len(team["admin"].get(f"/api/v1/orgs/{org['id']}/approvals").json()) == 1


def test_an_approval_can_only_be_decided_once(owner, org):
    wid = make_active_workflow(owner, org["id"])
    started = run(owner, org["id"], wid, {"order": {"id": "SO-6", "total": 70000}}).json()
    approval_id = started["approvals"][0]["id"]
    assert decide(owner, org["id"], approval_id, "approve").status_code == 200
    again = decide(owner, org["id"], approval_id, "reject")
    assert again.status_code == 409
    final = owner.get(f"/api/v1/orgs/{org['id']}/executions/{started['id']}").json()
    assert final["status"] == "succeeded"


def test_idempotency_key_returns_the_same_run(owner, org, engine):
    wid = make_active_workflow(owner, org["id"])
    first = run(owner, org["id"], wid, {"order": {"id": "SO-7", "total": 10}}, key="evt-123")
    second = run(owner, org["id"], wid, {"order": {"id": "SO-7", "total": 10}}, key="evt-123")
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(WorkflowExecution)) == 1


def test_a_workflow_must_be_active_to_run(owner, org):
    created = owner.post(base(org["id"]), json={"name": "Never activated"}).json()
    wid = created["workflow"]["id"]
    assert run(owner, org["id"], wid).status_code == 409
    wid2 = make_active_workflow(owner, org["id"])
    owner.post(f"{base(org['id'])}/{wid2}/deactivate")
    assert run(owner, org["id"], wid2, {"order": {"total": 1}}).status_code == 409


def test_viewers_cannot_run_but_can_read_runs(owner, org, team):
    wid = make_active_workflow(owner, org["id"])
    assert run(team["viewer"], org["id"], wid, {"order": {"total": 1}}).status_code == 403
    started = run(owner, org["id"], wid, {"order": {"id": "SO-8", "total": 1}}).json()
    assert team["viewer"].get(f"/api/v1/orgs/{org['id']}/executions/{started['id']}").status_code == 200
    assert len(team["viewer"].get(f"/api/v1/orgs/{org['id']}/executions").json()) == 1


def test_run_follows_the_version_it_started_on(owner, org):
    wid = make_active_workflow(owner, org["id"])
    started = run(owner, org["id"], wid, {"order": {"id": "SO-9", "total": 60000}}).json()
    assert started["version_number"] == 1
    # A new version removes the post-approval step and becomes active while the first run waits.
    publish_and_activate(owner, org["id"], wid, order_graph(with_done_step=False), base_revision=None)
    final = decide(owner, org["id"], started["approvals"][0]["id"], "approve").json()
    assert final["version_number"] == 1
    assert "done" in [s["node_id"] for s in final["steps"]]
    # New runs use version 2.
    fresh = run(owner, org["id"], wid, {"order": {"id": "SO-10", "total": 60000}}).json()
    assert fresh["version_number"] == 2


def test_delay_waits_and_resumes_after_the_time_passes(owner, org, engine):
    graph = {
        "nodes": [node("t", "trigger", {"event": "manual"}), node("d", "delay", {"seconds": 60}), node("e", "end")],
        "edges": [edge("1", "t", "d"), edge("2", "d", "e")],
    }
    wid = make_active_workflow(owner, org["id"], graph, name="Delayed")
    started = run(owner, org["id"], wid).json()
    assert started["status"] == "waiting_timer"

    with Session(engine) as db:
        assert process_due_timers(db, now=utcnow() + timedelta(seconds=30)) == 0
    still = owner.get(f"/api/v1/orgs/{org['id']}/executions/{started['id']}").json()
    assert still["status"] == "waiting_timer"

    with Session(engine) as db:
        assert process_due_timers(db, now=utcnow() + timedelta(seconds=61)) == 1
    done = owner.get(f"/api/v1/orgs/{org['id']}/executions/{started['id']}").json()
    assert done["status"] == "succeeded"
    assert [s["node_id"] for s in done["steps"]] == ["t", "d", "e"]
    assert done["steps"][1]["status"] == "succeeded"

    with Session(engine) as db:
        assert process_due_timers(db, now=utcnow() + timedelta(days=1)) == 0


def test_state_survives_a_restart(owner, org, engine, settings):
    """A new application instance on the same database continues a waiting run."""
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.conftest import PASSWORD

    wid = make_active_workflow(owner, org["id"])
    started = run(owner, org["id"], wid, {"order": {"id": "SO-11", "total": 88000}}).json()

    restarted = TestClient(create_app(settings=settings, engine=engine))
    login = restarted.post("/api/v1/auth/login", json={"email": "exec-owner@example.com", "password": PASSWORD})
    csrf = login.json()["csrf_token"]
    approvals = restarted.get(f"/api/v1/orgs/{org['id']}/approvals").json()
    assert approvals[0]["execution_id"] == started["id"]
    done = restarted.post(
        f"/api/v1/orgs/{org['id']}/approvals/{approvals[0]['id']}/decision",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "approve"},
    )
    assert done.json()["status"] == "succeeded"


def test_steps_that_need_other_systems_fail_with_a_clear_message(owner, org):
    graph = {
        "nodes": [
            node("t", "trigger", {"event": "manual"}),
            node("m", "email", {"to": "a@b.co", "subject": "Hi", "body": "Hello"}),
            node("e", "end"),
        ],
        "edges": [edge("1", "t", "m"), edge("2", "m", "e")],
    }
    wid = make_active_workflow(owner, org["id"], graph, name="Needs email")
    body = run(owner, org["id"], wid).json()
    assert body["status"] == "failed"
    assert "not available yet" in body["error"]
    assert body["steps"][-1]["status"] == "failed"
    assert [s["node_id"] for s in body["steps"]] == ["t", "m"]


def test_bad_input_data_fails_the_run_instead_of_guessing(owner, org):
    wid = make_active_workflow(owner, org["id"])
    not_a_number = run(owner, org["id"], wid, {"order": {"id": "SO-12", "total": "lots"}}).json()
    assert not_a_number["status"] == "failed"
    assert "not a number" in not_a_number["steps"][-1]["error"]
    missing = run(owner, org["id"], wid, {}).json()
    assert missing["status"] == "failed"


def test_cancel_stops_the_run_and_its_approval(owner, org):
    wid = make_active_workflow(owner, org["id"])
    started = run(owner, org["id"], wid, {"order": {"id": "SO-13", "total": 95000}}).json()
    cancelled = owner.post(f"/api/v1/orgs/{org['id']}/executions/{started['id']}/cancel")
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert body["approvals"][0]["status"] == "cancelled"
    assert decide(owner, org["id"], body["approvals"][0]["id"], "approve").status_code == 409
    assert owner.post(f"/api/v1/orgs/{org['id']}/executions/{started['id']}/cancel").status_code == 409


def test_other_organizations_cannot_see_or_decide(owner, org, make_account):
    wid = make_active_workflow(owner, org["id"])
    started = run(owner, org["id"], wid, {"order": {"id": "SO-14", "total": 77000}}).json()
    approval_id = started["approvals"][0]["id"]

    outsider = make_account("exec-outsider@example.com")
    other_org = create_org(outsider, "Other Exec Corp")
    assert outsider.get(f"/api/v1/orgs/{org['id']}/executions/{started['id']}").status_code == 404
    assert outsider.get(f"/api/v1/orgs/{org['id']}/approvals").status_code == 404
    assert decide(outsider, org["id"], approval_id, "approve").status_code == 404
    # The same ids through the outsider's own organization do not resolve either.
    assert outsider.get(f"/api/v1/orgs/{other_org['id']}/executions/{started['id']}").status_code == 404
    assert decide(outsider, other_org["id"], approval_id, "approve").status_code == 404
    assert outsider.get(f"/api/v1/orgs/{other_org['id']}/executions").json() == []
    assert run(outsider, other_org["id"], wid).status_code == 404


def test_run_and_decision_require_csrf(owner, org):
    wid = make_active_workflow(owner, org["id"])
    assert owner.client.post(f"{base(org['id'])}/{wid}/executions", json={"payload": {}}).status_code == 403
    started = run(owner, org["id"], wid, {"order": {"id": "SO-15", "total": 99000}}).json()
    r = owner.client.post(
        f"/api/v1/orgs/{org['id']}/approvals/{started['approvals'][0]['id']}/decision",
        json={"decision": "approve"},
    )
    assert r.status_code == 403


def test_payload_must_be_an_object_and_bounded(owner, org):
    wid = make_active_workflow(owner, org["id"])
    assert owner.post(f"{base(org['id'])}/{wid}/executions", json={"payload": [1, 2]}).status_code == 422
    huge = {"blob": "x" * 60_000}
    assert run(owner, org["id"], wid, huge).status_code == 413


def test_audit_trail_records_runs_and_decisions(owner, org):
    wid = make_active_workflow(owner, org["id"])
    started = run(owner, org["id"], wid, {"order": {"id": "SO-16", "total": 66000}}).json()
    decide(owner, org["id"], started["approvals"][0]["id"], "approve")
    events = owner.get(f"/api/v1/orgs/{org['id']}/audit-events?limit=200").json()
    actions = {e["action"] for e in events}
    assert {"execution.start", "approval.decision"} <= actions
    decision = next(e for e in events if e["action"] == "approval.decision")
    assert decision["metadata"]["decision"] == "approve"
    assert decision["trace_id"]


def test_metrics_come_from_real_runs(owner, org):
    wid = make_active_workflow(owner, org["id"])
    run(owner, org["id"], wid, {"order": {"id": "a", "total": 5}})
    run(owner, org["id"], wid, {"order": {"id": "b", "total": 6}})
    waiting = run(owner, org["id"], wid, {"order": {"id": "c", "total": 90000}}).json()
    rejected = run(owner, org["id"], wid, {"order": {"id": "d", "total": 91000}}).json()
    decide(owner, org["id"], rejected["approvals"][0]["id"], "reject")
    run(owner, org["id"], wid, {})  # fails: missing data

    m = owner.get(f"/api/v1/orgs/{org['id']}/metrics").json()
    assert m["total_runs"] == 5
    assert m["by_status"]["succeeded"] == 2
    assert m["by_status"]["waiting_approval"] == 1
    assert m["by_status"]["rejected"] == 1
    assert m["by_status"]["failed"] == 1
    assert m["pending_approvals"] == 1
    assert m["active_workflows"] == 1
    assert m["total_workflows"] == 1
    assert m["average_duration_seconds"] is not None
    today = m["last_7_days"][-1]
    assert (today["succeeded"], today["rejected"], today["failed"]) == (2, 1, 1)
    assert len(m["last_7_days"]) == 7
    assert waiting["status"] == "waiting_approval"


def test_executions_list_filters_by_status(owner, org):
    wid = make_active_workflow(owner, org["id"])
    run(owner, org["id"], wid, {"order": {"id": "a", "total": 5}})
    run(owner, org["id"], wid, {"order": {"id": "b", "total": 90000}})
    waiting = owner.get(f"/api/v1/orgs/{org['id']}/executions?status=waiting_approval").json()
    assert len(waiting) == 1
    assert len(owner.get(f"/api/v1/orgs/{org['id']}/executions").json()) == 2


def test_step_rows_and_approval_rows_carry_the_organization(owner, org, engine):
    wid = make_active_workflow(owner, org["id"])
    run(owner, org["id"], wid, {"order": {"id": "z", "total": 99000}})
    with Session(engine) as db:
        steps = db.scalars(select(StepExecution)).all()
        approvals = db.scalars(select(Approval)).all()
        assert steps and all(s.organization_id == org["id"] for s in steps)
        assert approvals and all(a.organization_id == org["id"] for a in approvals)
