"""Execution, approval, and metrics routes.

Starting a run needs an active workflow version. Deciding an approval needs the approver role the
workflow asked for. Rejected approvals never continue down the approved path (see app/engine.py).
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.deps import OrgAccess, get_db, org_access, trace_id_of
from app.engine import (
    CANCELLABLE,
    MAX_PAYLOAD_BYTES,
    EngineError,
    can_decide,
    cancel_execution,
    decide_approval,
    start_execution,
)
from app.models import (
    Approval,
    StepExecution,
    User,
    Workflow,
    WorkflowExecution,
    WorkflowVersion,
    utcnow,
)

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["executions"])


# --------------------------------------------------------------------------- schemas


class StepOut(BaseModel):
    id: str
    sequence: int
    node_id: str
    node_type: str
    node_label: str
    status: str
    input: dict[str, Any]
    output: dict[str, Any]
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class ApprovalOut(BaseModel):
    id: str
    execution_id: str
    workflow_id: str
    workflow_name: str
    title: str
    approver_role: str
    status: str
    context: dict[str, Any]
    requested_at: datetime
    decided_by_name: str | None
    decided_at: datetime | None
    comment: str
    can_decide: bool


class ExecutionSummary(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str
    version_number: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    error: str | None


class ExecutionDetail(ExecutionSummary):
    trigger_payload: dict[str, Any]
    variables: dict[str, Any]
    outcome: str | None
    trace_id: str | None
    steps: list[StepOut]
    approvals: list[ApprovalOut]


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    comment: str = Field(default="", max_length=1000)


class DayCount(BaseModel):
    date: str
    succeeded: int
    failed: int
    rejected: int


class Metrics(BaseModel):
    total_runs: int
    by_status: dict[str, int]
    pending_approvals: int
    active_workflows: int
    total_workflows: int
    average_duration_seconds: float | None
    last_7_days: list[DayCount]


# --------------------------------------------------------------------------- helpers


def _summary(execution: WorkflowExecution, workflow_name: str) -> ExecutionSummary:
    return ExecutionSummary(
        id=execution.id,
        workflow_id=execution.workflow_id,
        workflow_name=workflow_name,
        version_number=execution.version_number,
        status=execution.status,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        error=execution.error,
    )


def _step_out(step: StepExecution) -> StepOut:
    return StepOut(
        id=step.id,
        sequence=step.sequence,
        node_id=step.node_id,
        node_type=step.node_type,
        node_label=step.node_label,
        status=step.status,
        input=step.input,
        output=step.output,
        error=step.error,
        started_at=step.started_at,
        finished_at=step.finished_at,
    )


def _approval_out(db: Session, approval: Approval, role: str, workflow_name: str, workflow_id: str) -> ApprovalOut:
    decider = db.get(User, approval.decided_by_user_id) if approval.decided_by_user_id else None
    return ApprovalOut(
        id=approval.id,
        execution_id=approval.execution_id,
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        title=approval.title,
        approver_role=approval.approver_role,
        status=approval.status,
        context=approval.context,
        requested_at=approval.requested_at,
        decided_by_name=decider.full_name if decider else None,
        decided_at=approval.decided_at,
        comment=approval.comment,
        can_decide=approval.status == "pending" and can_decide(role, approval.approver_role),
    )


def _get_execution(db: Session, org_id: str, execution_id: str) -> WorkflowExecution:
    execution = db.scalar(
        select(WorkflowExecution).where(
            WorkflowExecution.id == execution_id, WorkflowExecution.organization_id == org_id
        )
    )
    if execution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return execution


def _detail(db: Session, execution: WorkflowExecution, role: str) -> ExecutionDetail:
    workflow = db.get(Workflow, execution.workflow_id)
    name = workflow.name if workflow else "Deleted workflow"
    steps = db.scalars(
        select(StepExecution)
        .where(StepExecution.execution_id == execution.id, StepExecution.organization_id == execution.organization_id)
        .order_by(StepExecution.sequence)
    ).all()
    approvals = db.scalars(
        select(Approval)
        .where(Approval.execution_id == execution.id, Approval.organization_id == execution.organization_id)
        .order_by(Approval.requested_at)
    ).all()
    # Members can see that a run is waiting but not the business data inside the approval.
    visible_approvals = (
        [_approval_out(db, a, role, name, execution.workflow_id) for a in approvals]
        if role in {"owner", "admin"}
        else []
    )
    return ExecutionDetail(
        **_summary(execution, name).model_dump(),
        trigger_payload=execution.trigger_payload,
        variables=execution.variables,
        outcome=execution.outcome,
        trace_id=execution.trace_id,
        steps=[_step_out(s) for s in steps],
        approvals=visible_approvals,
    )


# --------------------------------------------------------------------------- runs


@router.post("/workflows/{workflow_id}/executions", status_code=status.HTTP_201_CREATED, response_model=ExecutionDetail)
def run_workflow(
    workflow_id: str,
    payload: RunIn,
    request: Request,
    access: OrgAccess = Depends(org_access("executions:run", csrf=True)),
    db: Session = Depends(get_db),
):
    if len(json.dumps(payload.payload, default=str)) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="The payload is too large.")

    workflow = db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.organization_id == access.org_id,
            Workflow.archived_at.is_(None),
        )
    )
    if workflow is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Workflow not found.")

    if payload.idempotency_key:
        existing = db.scalar(
            select(WorkflowExecution).where(
                WorkflowExecution.organization_id == access.org_id,
                WorkflowExecution.workflow_id == workflow.id,
                WorkflowExecution.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            # Same key, same run. Retrying a request never starts a second run.
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=json.loads(_detail(db, existing, access.role).model_dump_json()),
            )

    if workflow.active_version_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Activate a published version before running this workflow."
        )
    version = db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.id == workflow.active_version_id, WorkflowVersion.organization_id == access.org_id
        )
    )
    if version is None:  # pragma: no cover - foreign key
        raise HTTPException(status.HTTP_409_CONFLICT, detail="The active version could not be found.")

    try:
        execution = start_execution(
            db,
            version=version,
            organization_id=access.org_id,
            workflow_id=workflow.id,
            payload=payload.payload,
            started_by_user_id=access.auth.user.id,
            idempotency_key=payload.idempotency_key,
            trace_id=trace_id_of(request),
        )
        record_audit(
            db,
            action="execution.start",
            organization_id=access.org_id,
            actor_user_id=access.auth.user.id,
            target_type="execution",
            target_id=execution.id,
            metadata={"workflow_id": workflow.id, "version": version.version_number, "status": execution.status},
            trace_id=trace_id_of(request),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A run with this idempotency key already exists."
        ) from None
    except EngineError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from None
    return _detail(db, execution, access.role)


@router.get("/executions", response_model=list[ExecutionSummary])
def list_executions(
    status_filter: str | None = Query(default=None, alias="status"),
    workflow_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    access: OrgAccess = Depends(org_access("executions:read", csrf=False)),
    db: Session = Depends(get_db),
) -> list[ExecutionSummary]:
    query = (
        select(WorkflowExecution, Workflow.name)
        .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
        .where(WorkflowExecution.organization_id == access.org_id)
    )
    if status_filter:
        query = query.where(WorkflowExecution.status == status_filter)
    if workflow_id:
        query = query.where(WorkflowExecution.workflow_id == workflow_id)
    rows = db.execute(query.order_by(WorkflowExecution.started_at.desc()).limit(limit)).all()
    return [_summary(execution, name) for execution, name in rows]


@router.get("/executions/{execution_id}", response_model=ExecutionDetail)
def get_execution(
    execution_id: str,
    access: OrgAccess = Depends(org_access("executions:read", csrf=False)),
    db: Session = Depends(get_db),
) -> ExecutionDetail:
    return _detail(db, _get_execution(db, access.org_id, execution_id), access.role)


@router.post("/executions/{execution_id}/cancel", response_model=ExecutionDetail)
def cancel(
    execution_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access("executions:run", csrf=True)),
    db: Session = Depends(get_db),
) -> ExecutionDetail:
    execution = _get_execution(db, access.org_id, execution_id)
    if execution.status not in CANCELLABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This run has already finished.")
    cancel_execution(db, execution)
    record_audit(
        db,
        action="execution.cancel",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="execution",
        target_id=execution.id,
        trace_id=trace_id_of(request),
    )
    db.commit()
    return _detail(db, execution, access.role)


# --------------------------------------------------------------------------- approvals


@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(
    status_filter: str = Query(default="pending", alias="status", pattern="^(pending|decided|all)$"),
    limit: int = Query(default=100, ge=1, le=200),
    access: OrgAccess = Depends(org_access("approvals:read", csrf=False)),
    db: Session = Depends(get_db),
) -> list[ApprovalOut]:
    query = (
        select(Approval, Workflow.name, WorkflowExecution.workflow_id)
        .join(WorkflowExecution, WorkflowExecution.id == Approval.execution_id)
        .join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
        .where(Approval.organization_id == access.org_id)
    )
    if status_filter == "pending":
        query = query.where(Approval.status == "pending")
    elif status_filter == "decided":
        query = query.where(Approval.status != "pending")
    rows = db.execute(query.order_by(Approval.requested_at.desc()).limit(limit)).all()
    return [_approval_out(db, approval, access.role, name, wid) for approval, name, wid in rows]


@router.post("/approvals/{approval_id}/decision", response_model=ExecutionDetail)
def decide(
    approval_id: str,
    payload: DecisionIn,
    request: Request,
    access: OrgAccess = Depends(org_access("approvals:decide", csrf=True)),
    db: Session = Depends(get_db),
) -> ExecutionDetail:
    approval = db.scalar(select(Approval).where(Approval.id == approval_id, Approval.organization_id == access.org_id))
    if approval is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Approval not found.")
    if not can_decide(access.role, approval.approver_role):
        record_audit(
            db,
            action="approval.decision",
            outcome="rejected",
            organization_id=access.org_id,
            actor_user_id=access.auth.user.id,
            target_type="approval",
            target_id=approval.id,
            metadata={"reason": "role_not_allowed", "required_role": approval.approver_role},
            trace_id=trace_id_of(request),
        )
        db.commit()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=f"This approval needs a {approval.approver_role} to decide it."
        )

    approved = payload.decision == "approve"
    try:
        execution = decide_approval(
            db,
            approval=approval,
            approved=approved,
            decided_by_user_id=access.auth.user.id,
            comment=payload.comment.strip(),
        )
    except EngineError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(error)) from None

    record_audit(
        db,
        action="approval.decision",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="approval",
        target_id=approval.id,
        metadata={"decision": payload.decision, "execution_id": execution.id, "run_status": execution.status},
        trace_id=trace_id_of(request),
    )
    db.commit()
    return _detail(db, execution, access.role)


# --------------------------------------------------------------------------- metrics


@router.get("/metrics", response_model=Metrics)
def metrics(
    access: OrgAccess = Depends(org_access("executions:read", csrf=False)),
    db: Session = Depends(get_db),
) -> Metrics:
    """Real numbers from the database. Nothing here is estimated or sample data."""
    org = access.org_id
    counts = dict(
        db.execute(
            select(WorkflowExecution.status, func.count())
            .where(WorkflowExecution.organization_id == org)
            .group_by(WorkflowExecution.status)
        ).all()
    )
    pending = db.scalar(
        select(func.count()).select_from(Approval).where(Approval.organization_id == org, Approval.status == "pending")
    )
    total_workflows = db.scalar(
        select(func.count())
        .select_from(Workflow)
        .where(Workflow.organization_id == org, Workflow.archived_at.is_(None))
    )
    active = db.scalar(
        select(func.count())
        .select_from(Workflow)
        .where(Workflow.organization_id == org, Workflow.archived_at.is_(None), Workflow.active_version_id.is_not(None))
    )

    finished = db.execute(
        select(WorkflowExecution.started_at, WorkflowExecution.finished_at)
        .where(WorkflowExecution.organization_id == org, WorkflowExecution.finished_at.is_not(None))
        .order_by(WorkflowExecution.finished_at.desc())
        .limit(500)
    ).all()
    durations = [(end - start).total_seconds() for start, end in finished if end and start]
    average = sum(durations) / len(durations) if durations else None

    since = utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)
    recent = db.execute(
        select(WorkflowExecution.finished_at, WorkflowExecution.status).where(
            WorkflowExecution.organization_id == org,
            WorkflowExecution.finished_at.is_not(None),
            WorkflowExecution.finished_at >= since,
        )
    ).all()
    per_day: dict[str, dict[str, int]] = defaultdict(lambda: {"succeeded": 0, "failed": 0, "rejected": 0})
    for finished_at, run_status in recent:
        if run_status in {"succeeded", "failed", "rejected"}:
            per_day[finished_at.date().isoformat()][run_status] += 1
    days = [
        DayCount(
            date=(since + timedelta(days=i)).date().isoformat(),
            **per_day[(since + timedelta(days=i)).date().isoformat()],
        )
        for i in range(7)
    ]

    return Metrics(
        total_runs=sum(counts.values()),
        by_status=counts,
        pending_approvals=pending or 0,
        active_workflows=active or 0,
        total_workflows=total_workflows or 0,
        average_duration_seconds=average,
        last_7_days=days,
    )
