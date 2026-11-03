"""Workflow execution engine.

Database-backed and restart-safe: every decision about what runs next is derived from rows in
`workflow_executions`, `step_executions`, and `approvals`. Nothing important lives in memory, so a
process restart in the middle of a run loses nothing.

This is an in-process engine, not Temporal. It advances a run synchronously until the run finishes
or reaches a step that must wait for a person (approval) or for time (delay). Waiting steps are
resumed by an approval decision or by the timer poller in `process_due_timers`.

Supported steps: trigger, condition, transformation, delay, approval, end. Steps that need an
external system or an AI model fail with a clear message, never silently.
"""

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import ai, http_client
from app.crypto import SecretDecryptionError, decrypt_secret
from app.inventory import check_stock
from app.models import (
    Approval,
    Connection,
    StepExecution,
    WorkflowExecution,
    WorkflowVersion,
    utcnow,
)

MAX_STEPS = 500
MAX_PAYLOAD_BYTES = 50_000
DEFAULT_RESULT_PATH = "http_response"

SUPPORTED_NODE_TYPES = frozenset(
    {"trigger", "condition", "transformation", "delay", "approval", "http", "ai_agent", "inventory", "end"}
)
AI_TASKS = frozenset({"extract_order"})
UNAVAILABLE_REASON = {
    "crm": "CRM steps are not available yet. No CRM integration is connected.",
    "erp": "ERP steps are not available yet. No ERP integration is connected.",
    "database": "Database steps are not available yet.",
    "email": "Email steps are not available yet. No email provider is connected.",
}


class EngineError(Exception):
    """A step failed for a reason the user can act on. The message is shown in the run trace."""


# --------------------------------------------------------------------------- data access helpers


def lookup(variables: dict[str, Any], path: str) -> tuple[bool, Any]:
    """Resolve a dotted path such as `order.total` or `items.0.sku`. Returns (found, value)."""
    current: Any = variables
    for part in path.strip().split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False, None
    return True, current


def assign(variables: dict[str, Any], path: str, value: Any) -> None:
    parts = path.strip().split(".")
    current = variables
    for part in parts[:-1]:
        nxt = current.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            current[part] = nxt
        current = nxt
    current[parts[-1]] = value


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def evaluate_condition(config: dict[str, Any], variables: dict[str, Any]) -> bool:
    """Evaluate a structured condition. Bad data fails the step instead of quietly choosing a branch."""
    field = str(config.get("field", ""))
    operator = config.get("operator")
    found, actual = lookup(variables, field)

    if operator == "exists":
        return found and actual is not None
    if not found:
        raise EngineError(f"The field “{field}” is missing from the data, so the condition cannot be checked.")

    expected = config.get("value")
    if operator in {"gt", "gte", "lt", "lte"}:
        left, right = _as_number(actual), _as_number(expected)
        if left is None or right is None:
            raise EngineError(f"“{field}” is not a number, so it cannot be compared with {operator}.")
        return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}[operator]
    if operator in {"eq", "neq"}:
        left, right = _as_number(actual), _as_number(expected)
        equal = left == right if left is not None and right is not None else actual == expected
        return equal if operator == "eq" else not equal
    if operator == "contains":
        if isinstance(actual, str):
            return str(expected) in actual
        if isinstance(actual, list):
            return expected in actual
        raise EngineError(f"“{field}” is not text or a list, so it cannot be searched.")
    raise EngineError(f"Unknown operator: {operator}")


# --------------------------------------------------------------------------- graph helpers


def _graph(version: WorkflowVersion) -> tuple[dict[str, dict], dict[tuple[str, str | None], str]]:
    nodes = {node["id"]: node for node in version.definition.get("nodes", [])}
    edges = {
        (edge["source"], edge.get("source_handle")): edge["target"] for edge in version.definition.get("edges", [])
    }
    return nodes, edges


def _version_of(db: Session, execution: WorkflowExecution) -> WorkflowVersion:
    version = db.get(WorkflowVersion, execution.version_id)
    if version is None:  # pragma: no cover - restricted by foreign key
        raise EngineError("The workflow version for this run no longer exists.")
    return version


# --------------------------------------------------------------------------- starting a run


def start_execution(
    db: Session,
    *,
    version: WorkflowVersion,
    organization_id: str,
    workflow_id: str,
    payload: dict[str, Any],
    started_by_user_id: str | None,
    idempotency_key: str | None,
    trace_id: str | None,
    trigger_type: str = "manual",
) -> WorkflowExecution:
    nodes, _ = _graph(version)
    trigger = next((n for n in nodes.values() if n["type"] == "trigger"), None)
    if trigger is None:
        raise EngineError("This workflow version has no trigger.")

    execution = WorkflowExecution(
        organization_id=organization_id,
        workflow_id=workflow_id,
        version_id=version.id,
        version_number=version.version_number,
        status="running",
        trigger_type=trigger_type,
        trigger_payload=payload,
        variables=dict(payload),
        current_node_id=trigger["id"],
        idempotency_key=idempotency_key,
        started_by_user_id=started_by_user_id,
        trace_id=trace_id,
    )
    db.add(execution)
    db.flush()
    advance(db, execution)
    return execution


# --------------------------------------------------------------------------- the run loop


def _next_sequence(db: Session, execution: WorkflowExecution) -> int:
    last = db.scalars(
        select(StepExecution.sequence)
        .where(StepExecution.execution_id == execution.id)
        .order_by(StepExecution.sequence.desc())
        .limit(1)
    ).first()
    return (last or 0) + 1


def _finish(execution: WorkflowExecution, status: str, error: str | None = None) -> None:
    execution.status = status
    execution.error = error
    execution.current_node_id = None
    execution.resume_at = None
    execution.finished_at = utcnow()


def advance(db: Session, execution: WorkflowExecution) -> None:
    """Run steps until the run finishes, fails, or must wait. Safe to call again after a resume."""
    version = _version_of(db, execution)
    nodes, edges = _graph(version)

    for _ in range(MAX_STEPS):
        if execution.status != "running" or execution.current_node_id is None:
            return
        node = nodes.get(execution.current_node_id)
        if node is None:
            _finish(execution, "failed", "The run points at a step that does not exist.")
            return

        step = StepExecution(
            execution_id=execution.id,
            organization_id=execution.organization_id,
            node_id=node["id"],
            node_type=node["type"],
            node_label=node.get("label", ""),
            sequence=_next_sequence(db, execution),
            status="running",
            input=dict(execution.variables),
        )
        db.add(step)
        db.flush()

        try:
            handle, output, wait = _run_node(db, execution, step, node)
        except EngineError as error:
            step.status = "failed"
            step.error = str(error)
            step.finished_at = utcnow()
            _finish(execution, "failed", f"Step “{node.get('label') or node['type']}” failed: {error}")
            return

        step.output = output
        if wait == "approval":
            step.status = "waiting"
            execution.status = "waiting_approval"
            return
        if wait == "timer":
            step.status = "waiting"
            execution.status = "waiting_timer"
            return

        step.status = "succeeded"
        step.finished_at = utcnow()

        if node["type"] == "end":
            _finish(execution, "rejected" if execution.outcome == "rejected" else "succeeded")
            return

        target = edges.get((node["id"], handle))
        if target is None:
            _finish(execution, "failed", f"Step “{node.get('label') or node['type']}” has no next step.")
            return
        execution.current_node_id = target

    _finish(execution, "failed", f"Stopped after {MAX_STEPS} steps to prevent a runaway workflow.")


def _run_node(
    db: Session, execution: WorkflowExecution, step: StepExecution, node: dict
) -> tuple[str | None, dict[str, Any], str | None]:
    """Execute one node. Returns (branch handle to follow, output, wait kind or None)."""
    kind = node["type"]
    config = node.get("config", {})
    variables = execution.variables

    if kind in UNAVAILABLE_REASON:
        raise EngineError(UNAVAILABLE_REASON[kind])
    if kind not in SUPPORTED_NODE_TYPES:  # pragma: no cover - schema restricts node types
        raise EngineError(f"Unknown step type: {kind}")

    if kind == "trigger":
        return None, {"event": config.get("event"), "payload_keys": sorted(variables)}, None
    if kind == "end":
        return None, {"outcome": "rejected" if execution.outcome == "rejected" else "completed"}, None

    if kind == "condition":
        result = evaluate_condition(config, variables)
        return ("true" if result else "false"), {"result": result, "checked": config.get("field")}, None

    if kind == "transformation":
        updated = dict(variables)
        written: dict[str, Any] = {}
        for mapping in config.get("mappings", []):
            found, value = lookup(variables, str(mapping.get("source", "")))
            if not found:
                raise EngineError(f"Mapping source “{mapping.get('source')}” was not found in the data.")
            assign(updated, str(mapping["target"]), value)
            written[str(mapping["target"])] = value
        execution.variables = updated  # reassign so the JSON column change is detected
        return None, {"written": written}, None

    if kind == "delay":
        seconds = int(config.get("seconds", 0))
        resume_at = utcnow() + timedelta(seconds=seconds)
        execution.resume_at = resume_at
        return None, {"waiting_seconds": seconds, "resume_at": resume_at.isoformat()}, "timer"

    if kind == "http":
        return None, _run_http(db, execution, node, config), None

    if kind == "ai_agent":
        return None, _run_ai(db, execution, config), None

    if kind == "inventory":
        return None, _run_stock_check(db, execution, config), None

    if kind == "approval":
        title = str(config.get("title") or node.get("label") or "Approval needed")[:200]
        approval = Approval(
            organization_id=execution.organization_id,
            execution_id=execution.id,
            step_id=step.id,
            node_id=node["id"],
            title=title,
            approver_role=str(config.get("approver_role", "admin")),
            status="pending",
            context=dict(variables),
        )
        db.add(approval)
        db.flush()
        return None, {"approval_id": approval.id, "approver_role": approval.approver_role}, "approval"

    raise EngineError(f"Unknown step type: {kind}")  # pragma: no cover


# --------------------------------------------------------------------------- resuming


def _claim(db: Session, execution_id: str, from_status: str) -> bool:
    """Atomically move a waiting run to running. Only one caller can win, so a decision or timer fires once."""
    result = db.execute(
        update(WorkflowExecution)
        .where(WorkflowExecution.id == execution_id, WorkflowExecution.status == from_status)
        .values(status="running")
    )
    return result.rowcount == 1


def decide_approval(
    db: Session,
    *,
    approval: Approval,
    approved: bool,
    decided_by_user_id: str,
    comment: str,
) -> WorkflowExecution:
    """Record a decision and continue the run down the approved or rejected branch.

    The caller has already checked that this user may decide. Here we make sure it happens only once.
    """
    claimed = db.execute(
        update(Approval)
        .where(Approval.id == approval.id, Approval.status == "pending")
        .values(
            status="approved" if approved else "rejected",
            decided_by_user_id=decided_by_user_id,
            decided_at=utcnow(),
            comment=comment,
        )
    )
    if claimed.rowcount != 1:
        raise EngineError("This approval has already been decided or cancelled.")

    execution = db.get(WorkflowExecution, approval.execution_id)
    if execution is None or not _claim(db, execution.id, "waiting_approval"):
        raise EngineError("This run is no longer waiting for approval.")
    db.refresh(execution)

    step = db.get(StepExecution, approval.step_id)
    if step is not None:
        step.status = "succeeded"
        step.finished_at = utcnow()
        step.output = {
            **(step.output or {}),
            "decision": "approved" if approved else "rejected",
            "decided_by": decided_by_user_id,
            "comment": comment,
        }

    version = _version_of(db, execution)
    _, edges = _graph(version)
    handle = "approved" if approved else "rejected"
    if not approved:
        execution.outcome = "rejected"
    target = edges.get((approval.node_id, handle))
    if target is None:
        _finish(execution, "failed", f"The “{handle}” path of this approval is not connected.")
        return execution
    execution.current_node_id = target
    advance(db, execution)
    return execution


def resume_timer(db: Session, execution_id: str) -> WorkflowExecution | None:
    if not _claim(db, execution_id, "waiting_timer"):
        return None
    execution = db.get(WorkflowExecution, execution_id)
    if execution is None:  # pragma: no cover
        return None
    db.refresh(execution)
    step = db.scalars(
        select(StepExecution)
        .where(StepExecution.execution_id == execution.id, StepExecution.status == "waiting")
        .order_by(StepExecution.sequence.desc())
    ).first()
    node_id = step.node_id if step else execution.current_node_id
    if step is not None:
        step.status = "succeeded"
        step.finished_at = utcnow()
    version = _version_of(db, execution)
    _, edges = _graph(version)
    target = edges.get((node_id, None)) if node_id else None
    execution.resume_at = None
    if target is None:
        _finish(execution, "failed", "The step after the delay is not connected.")
        return execution
    execution.current_node_id = target
    advance(db, execution)
    return execution


def process_due_timers(db: Session, now: datetime | None = None, limit: int = 50) -> int:
    """Resume runs whose delay has elapsed. Called by the scheduler loop. Returns how many resumed."""
    moment = now or utcnow()
    due = db.scalars(
        select(WorkflowExecution.id)
        .where(WorkflowExecution.status == "waiting_timer", WorkflowExecution.resume_at <= moment)
        .limit(limit)
    ).all()
    resumed = 0
    for execution_id in due:
        if resume_timer(db, execution_id) is not None:
            db.commit()
            resumed += 1
        else:
            db.rollback()
    return resumed


def cancel_execution(db: Session, execution: WorkflowExecution) -> None:
    """Cancel a waiting or running run. Pending approvals are cancelled so they can no longer be decided."""
    pending = db.scalars(
        select(Approval).where(Approval.execution_id == execution.id, Approval.status == "pending")
    ).all()
    for approval in pending:
        approval.status = "cancelled"
    waiting = db.scalars(
        select(StepExecution).where(StepExecution.execution_id == execution.id, StepExecution.status == "waiting")
    ).all()
    for step in waiting:
        step.status = "cancelled"
        step.finished_at = utcnow()
    _finish(execution, "cancelled")


# Statuses where a run can still be cancelled.
CANCELLABLE: tuple[str, ...] = ("running", "waiting_approval", "waiting_timer")


def can_decide(user_role: str, approver_role: str) -> bool:
    """Owners can decide any approval. Admins can decide approvals assigned to admins."""
    if user_role == "owner":
        return True
    return user_role == "admin" and approver_role == "admin"


def _run_http(db: Session, execution: WorkflowExecution, node: dict, config: dict[str, Any]) -> dict[str, Any]:
    """Call an outside HTTPS API. Credentials come from an encrypted connection, never from the definition."""
    method = str(config.get("method", "GET")).upper()
    url = str(config.get("url", "")).strip()
    headers = {"User-Agent": "Hermes-Workflow/0.1", "Accept": "application/json"}
    if method != "GET":
        # Lets the receiving API recognize a repeated write from the same run and step.
        headers["Idempotency-Key"] = f"{execution.id}:{node['id']}"

    connection_name = None
    connection_id = config.get("connection_id")
    if connection_id:
        connection = db.scalar(
            select(Connection).where(
                Connection.id == str(connection_id), Connection.organization_id == execution.organization_id
            )
        )
        if connection is None:
            raise EngineError("The connection for this step was not found. It may have been deleted.")
        settings = db.info.get("settings")
        if settings is None:
            raise EngineError("Connection secrets are not available here.")
        try:
            headers[connection.header_name] = decrypt_secret(settings, connection.secret_ciphertext)
        except SecretDecryptionError:
            raise EngineError(
                "The connection secret could not be read. Enter it again on the Integrations page."
            ) from None
        connection_name = connection.name

    body = None
    body_path = str(config.get("body_path") or "").strip()
    if body_path:
        found, body = lookup(execution.variables, body_path)
        if not found:
            raise EngineError(f"The body field “{body_path}” was not found in the data.")

    try:
        response = http_client.send(method, url, headers, body)
    except http_client.OutboundError as error:
        raise EngineError(str(error)) from None

    result_path = str(config.get("result_path") or DEFAULT_RESULT_PATH).strip()
    updated = dict(execution.variables)
    assign(updated, result_path, {"status": response.status, "body": response.body})
    execution.variables = updated
    # The output never includes headers, so a credential cannot leak into the run trace.
    return {
        "method": method,
        "host": urlparse(url).hostname,
        "status": response.status,
        "attempts": response.attempts,
        "bytes": response.size,
        "stored_at": result_path,
        "connection": connection_name,
    }


def _run_ai(db: Session, execution: WorkflowExecution, config: dict[str, Any]) -> dict[str, Any]:
    """Read text from the run's data with the AI model and store a validated, structured result.

    The model only describes the text. It cannot approve or act: later conditions and approvals decide.
    """
    settings = db.info.get("settings")
    if settings is None or not ai.is_configured(settings):
        raise EngineError("The AI step is not set up. Add an AI key to backend/.env (see README, Turn on AI).")
    task = str(config.get("task") or "extract_order")
    if task not in AI_TASKS:
        raise EngineError(f"Unknown AI task: {task}")

    input_path = str(config.get("input_path") or "email.body").strip()
    found, text = lookup(execution.variables, input_path)
    if not found or not isinstance(text, str) or not text.strip():
        raise EngineError(f"There is no text to read at {input_path}.")
    if not ai.allow_call(settings, execution.organization_id):
        raise EngineError("This organization reached its hourly limit for AI steps. Try again later.")

    try:
        result = ai.extract_order(settings, text, str(config.get("instructions") or ""))
    except ai.AIError as error:
        raise EngineError(str(error)) from None

    result_path = str(config.get("result_path") or "order").strip()
    updated = dict(execution.variables)
    assign(updated, result_path, result["order"])
    execution.variables = updated
    order = result["order"]
    return {
        "task": task,
        "model": result["model"],
        "prompt_tokens": result["prompt_tokens"],
        "completion_tokens": result["completion_tokens"],
        "is_order": order["is_order"],
        "confidence": order["confidence"],
        "total": order["total"],
        "total_source": order["total_source"],
        "stored_at": result_path,
    }


def _run_stock_check(db: Session, execution: WorkflowExecution, config: dict[str, Any]) -> dict[str, Any]:
    """Compare the order's lines with the organization's inventory and store the result for later conditions."""
    items_path = str(config.get("items_path") or "order.items").strip()
    found, lines = lookup(execution.variables, items_path)
    if not found or not isinstance(lines, list):
        raise EngineError(f"There is no list of order lines at {items_path}.")
    result = check_stock(db, execution.organization_id, lines)
    result_path = str(config.get("result_path") or "stock").strip()
    updated = dict(execution.variables)
    assign(updated, result_path, result)
    execution.variables = updated
    return {
        "status": result["status"],
        "lines_checked": len(result["lines"]),
        "problems": result["problems"],
        "stored_at": result_path,
    }
