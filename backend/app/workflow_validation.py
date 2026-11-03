"""Semantic validation of workflow graphs.

`validate_definition` returns a list of issues. Saving a draft stores whatever the user has, and
returns the issues so the editor can show them. Publishing refuses any definition with an error.

Nothing here executes a definition or contacts an external system. Conditions are structured
(field, operator, value), never free-form expressions, so there is nothing to evaluate dynamically.
"""

import ipaddress
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.workflow_schema import Definition, Node

CONDITION_OPERATORS = frozenset({"eq", "neq", "gt", "gte", "lt", "lte", "contains", "exists"})
HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
APPROVER_ROLES = frozenset({"owner", "admin"})
AI_TASKS = frozenset({"extract_order"})
# A dotted data path such as order or response.body.items.
DATA_PATH = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")
MAX_DELAY_SECONDS = 30 * 24 * 3600
MAX_INSTRUCTIONS = 4000

# Connector framework: each integration node type lists the connectors it can use today.
INTEGRATIONS_BY_NODE_TYPE: dict[str, frozenset[str]] = {
    "crm": frozenset({"hubspot"}),
    "erp": frozenset({"erpnext"}),
    "database": frozenset({"postgresql"}),
}

# Nodes that fan out through named handles.
BRANCH_HANDLES: dict[str, frozenset[str]] = {
    "condition": frozenset({"true", "false"}),
    "approval": frozenset({"approved", "rejected"}),
}


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str  # "error" blocks publishing, "warning" does not
    message: str
    node_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "message": self.message, "node_id": self.node_id}


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.severity == "error" for issue in issues)


def validate_definition(definition: Definition) -> list[Issue]:
    issues: list[Issue] = []
    nodes = {node.id: node for node in definition.nodes}

    if len(nodes) != len(definition.nodes):
        issues.append(Issue("duplicate_node_id", "error", "Two nodes share the same id."))
    if not definition.nodes:
        issues.append(Issue("empty_workflow", "error", "Add a trigger to start the workflow."))
        return issues

    issues.extend(_validate_edges(definition, nodes))
    issues.extend(_validate_structure(definition, nodes))
    for node in definition.nodes:
        issues.extend(_validate_node_config(node))
    return issues


def _validate_edges(definition: Definition, nodes: dict[str, Node]) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[tuple[str, str, str | None]] = set()
    edge_ids: set[str] = set()
    for edge in definition.edges:
        if edge.id in edge_ids:
            issues.append(Issue("duplicate_edge_id", "error", "Two connections share the same id."))
        edge_ids.add(edge.id)
        if edge.source not in nodes or edge.target not in nodes:
            issues.append(Issue("dangling_edge", "error", "A connection points to a node that does not exist."))
            continue
        if edge.source == edge.target:
            issues.append(Issue("self_loop", "error", "A node cannot connect to itself.", edge.source))
        key = (edge.source, edge.target, edge.source_handle)
        if key in seen:
            issues.append(Issue("duplicate_edge", "error", "The same connection exists twice.", edge.source))
        seen.add(key)
    return issues


def _validate_structure(definition: Definition, nodes: dict[str, Node]) -> list[Issue]:
    issues: list[Issue] = []
    valid_edges = [e for e in definition.edges if e.source in nodes and e.target in nodes and e.source != e.target]
    outgoing: dict[str, list] = defaultdict(list)
    incoming: dict[str, list] = defaultdict(list)
    for edge in valid_edges:
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)

    triggers = [n for n in definition.nodes if n.type == "trigger"]
    if len(triggers) == 0:
        issues.append(Issue("missing_trigger", "error", "A workflow needs exactly one trigger."))
    elif len(triggers) > 1:
        for trigger in triggers[1:]:
            issues.append(Issue("multiple_triggers", "error", "Only one trigger is allowed.", trigger.id))
    for trigger in triggers:
        if incoming[trigger.id]:
            issues.append(
                Issue("trigger_has_input", "error", "A trigger cannot have incoming connections.", trigger.id)
            )

    if not any(n.type == "end" for n in definition.nodes):
        issues.append(Issue("missing_end", "error", "Add at least one End node so every path finishes."))

    for node in definition.nodes:
        outs = outgoing[node.id]
        if node.type == "end":
            if outs:
                issues.append(
                    Issue("end_has_output", "error", "An End node cannot have outgoing connections.", node.id)
                )
        elif node.type in BRANCH_HANDLES:
            required = BRANCH_HANDLES[node.type]
            handles = [e.source_handle for e in outs]
            for handle in sorted(required):
                if handles.count(handle) == 0:
                    issues.append(
                        Issue("missing_branch", "error", f"Connect the “{handle}” output of this node.", node.id)
                    )
                elif handles.count(handle) > 1:
                    issues.append(
                        Issue(
                            "ambiguous_branch", "error", f"The “{handle}” output has more than one connection.", node.id
                        )
                    )
            if any(h not in required for h in handles):
                issues.append(Issue("unknown_branch", "error", "A connection uses an unknown output name.", node.id))
        else:
            if len(outs) == 0:
                issues.append(
                    Issue("dead_end", "error", "This node leads nowhere. Connect it to the next step.", node.id)
                )
            elif len(outs) > 1:
                issues.append(
                    Issue("multiple_outputs", "error", "Use a Condition node to split the flow into branches.", node.id)
                )
            if any(e.source_handle for e in outs):
                issues.append(Issue("unexpected_handle", "error", "This node has no named outputs.", node.id))

    # Reachability and cycles are only meaningful with a single trigger.
    if len(triggers) == 1:
        reachable = _reachable_from(triggers[0].id, outgoing)
        for node in definition.nodes:
            if node.id not in reachable:
                issues.append(Issue("unreachable", "error", "This node cannot be reached from the trigger.", node.id))
        if _has_cycle(nodes, outgoing):
            issues.append(
                Issue("cycle", "error", "Loops are not supported yet. Remove the connection that loops back.")
            )
    return issues


def _reachable_from(start: str, outgoing: dict[str, list]) -> set[str]:
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for edge in outgoing[current]:
            if edge.target not in seen:
                seen.add(edge.target)
                queue.append(edge.target)
    return seen


def _has_cycle(nodes: dict[str, Node], outgoing: dict[str, list]) -> bool:
    indegree = {node_id: 0 for node_id in nodes}
    for edges in outgoing.values():
        for edge in edges:
            indegree[edge.target] += 1
    queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for edge in outgoing[current]:
            indegree[edge.target] -= 1
            if indegree[edge.target] == 0:
                queue.append(edge.target)
    return visited != len(nodes)


def _text(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    return value.strip() if isinstance(value, str) else ""


def _validate_node_config(node: Node) -> list[Issue]:
    config = node.config
    issues: list[Issue] = []

    def error(code: str, message: str) -> None:
        issues.append(Issue(code, "error", message, node.id))

    kind = node.type
    if kind == "trigger":
        if not _text(config, "event"):
            error("missing_config", "Choose the event that starts this workflow.")
    elif kind == "ai_agent":
        task = config.get("task")
        instructions = _text(config, "instructions")
        if task not in (None, "") and task not in AI_TASKS:
            error("invalid_config", "Choose what the AI should do.")
        # With a task chosen, guidance is optional. Without one, the instructions are the whole job.
        if not task and not instructions:
            error("missing_config", "Choose what the AI should do.")
        if len(instructions) > MAX_INSTRUCTIONS:
            error("invalid_config", f"Instructions must be at most {MAX_INSTRUCTIONS} characters.")
        for key, label in (("input_path", "Read text from"), ("result_path", "Save result as")):
            value = config.get(key)
            if value not in (None, "") and not (isinstance(value, str) and DATA_PATH.match(value.strip())):
                error("invalid_config", f"“{label}” must be a data path such as email.body or order.")
        tools = config.get("allowed_tools", [])
        if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
            error("invalid_config", "Allowed tools must be a list of tool names.")
    elif kind == "condition":
        if not _text(config, "field"):
            error("missing_config", "Choose the field this condition checks.")
        operator = config.get("operator")
        if operator not in CONDITION_OPERATORS:
            error("missing_config", "Choose a comparison operator.")
        elif operator != "exists" and "value" not in config:
            error("missing_config", "Enter the value to compare against.")
    elif kind == "transformation":
        mappings = config.get("mappings")
        valid = (
            isinstance(mappings, list)
            and len(mappings) > 0
            and all(isinstance(m, dict) and _text(m, "target") and _text(m, "source") for m in mappings)
        )
        if not valid:
            error("missing_config", "Add at least one mapping with a source and a target field.")
    elif kind in INTEGRATIONS_BY_NODE_TYPE:
        integration = _text(config, "integration")
        if integration not in INTEGRATIONS_BY_NODE_TYPE[kind]:
            allowed = ", ".join(sorted(INTEGRATIONS_BY_NODE_TYPE[kind]))
            error("missing_config", f"Choose an integration ({allowed}).")
        if not _text(config, "action"):
            error("missing_config", "Choose the action this step performs.")
    elif kind == "email":
        for key, label in (("to", "recipient"), ("subject", "subject"), ("body", "message body")):
            if not _text(config, key):
                error("missing_config", f"Enter the email {label}.")
    elif kind == "http":
        if _text(config, "method").upper() not in HTTP_METHODS:
            error("missing_config", "Choose an HTTP method.")
        url_problem = _url_problem(_text(config, "url"))
        if url_problem:
            error("invalid_config", url_problem)
        for key, label in (("body_path", "Send data from"), ("result_path", "Save response as")):
            value = config.get(key)
            if value not in (None, "") and not (isinstance(value, str) and DATA_PATH.match(value.strip())):
                error("invalid_config", f"“{label}” must be a data path such as order or response.body.")
        connection_id = config.get("connection_id")
        if connection_id not in (None, "") and not isinstance(connection_id, str):
            error("invalid_config", "Choose a connection from the list.")
    elif kind == "inventory":
        for key, label in (("items_path", "Order lines from"), ("result_path", "Save result as")):
            value = config.get(key)
            if value not in (None, "") and not (isinstance(value, str) and DATA_PATH.match(value.strip())):
                error("invalid_config", f"“{label}” must be a data path such as order.items or stock.")
    elif kind == "approval":
        if _text(config, "approver_role") not in APPROVER_ROLES:
            error("missing_config", "Choose which role approves this step (owner or admin).")
    elif kind == "delay":
        seconds = config.get("seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= MAX_DELAY_SECONDS:
            error("invalid_config", "Enter a delay between 1 second and 30 days.")
    return issues


def _url_problem(url: str) -> str | None:
    """Structural URL checks. Runtime SSRF protection (DNS resolution, redirects) belongs to the executor."""
    if not url:
        return "Enter the request URL."
    try:
        parsed = urlparse(url)
    except ValueError:
        return "The URL is not valid."
    if parsed.scheme != "https":
        return "Only https URLs are allowed."
    host = parsed.hostname
    if not host:
        return "The URL needs a host name."
    if parsed.username or parsed.password:
        return "Do not put credentials in the URL. Use a stored connection instead."
    if host.lower() in {"localhost"} or host.lower().endswith((".local", ".internal")):
        return "Requests to internal hosts are not allowed."
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    if not address.is_global:
        return "Requests to private or reserved addresses are not allowed."
    return None
