"""Workflow routes: definitions, drafts, validation, publishing, and activation.

Rules enforced here:
- Every query is scoped by the caller's organization.
- Drafts are editable. Publishing freezes a version permanently.
- Only a published version can be activated. Activation and publishing need workflows:publish.
- Saves use optimistic concurrency (`base_revision`) so two editors cannot silently overwrite each other.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.deps import OrgAccess, get_db, org_access, trace_id_of
from app.models import Workflow, WorkflowVersion, utcnow
from app.workflow_schema import EMPTY_DEFINITION, Definition
from app.workflow_validation import Issue, has_errors, validate_definition

router = APIRouter(prefix="/api/v1/orgs/{org_id}/workflows", tags=["workflows"])


# --------------------------------------------------------------------------- schemas


class IssueOut(BaseModel):
    code: str
    severity: str
    message: str
    node_id: str | None


class VersionMeta(BaseModel):
    id: str
    version_number: int
    status: str
    revision: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None


class VersionOut(VersionMeta):
    definition: dict[str, Any]


class WorkflowSummary(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    active_version_number: int | None
    latest_published_number: int | None
    has_draft: bool


class WorkflowDetail(BaseModel):
    workflow: WorkflowSummary
    versions: list[VersionMeta]
    draft: VersionOut | None
    latest_published: VersionOut | None
    # Issues for the draft when there is one, otherwise for the latest published version.
    issues: list[IssueOut]


class DraftSaved(BaseModel):
    version: VersionOut
    issues: list[IssueOut]


class WorkflowCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    definition: Definition | None = None


class WorkflowUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class DraftSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: Definition
    # Revision of the draft the editor loaded. Omit only when no draft exists yet.
    base_revision: int | None = Field(default=None, ge=1)


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision: int = Field(ge=1)


# --------------------------------------------------------------------------- helpers


def _issues_out(issues: list[Issue]) -> list[IssueOut]:
    return [IssueOut(**issue.as_dict()) for issue in issues]


def _version_meta(version: WorkflowVersion) -> VersionMeta:
    return VersionMeta(
        id=version.id,
        version_number=version.version_number,
        status=version.status,
        revision=version.revision,
        created_at=version.created_at,
        updated_at=version.updated_at,
        published_at=version.published_at,
    )


def _version_out(version: WorkflowVersion) -> VersionOut:
    return VersionOut(**_version_meta(version).model_dump(), definition=version.definition)


def _get_workflow(db: Session, org_id: str, workflow_id: str) -> Workflow:
    workflow = db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.organization_id == org_id,
            Workflow.archived_at.is_(None),
        )
    )
    if workflow is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Workflow not found.")
    return workflow


def _versions_of(db: Session, workflow: Workflow) -> list[WorkflowVersion]:
    return list(
        db.scalars(
            select(WorkflowVersion)
            .where(
                WorkflowVersion.workflow_id == workflow.id, WorkflowVersion.organization_id == workflow.organization_id
            )
            .order_by(WorkflowVersion.version_number.desc())
        )
    )


def _summary(workflow: Workflow, versions: list[WorkflowVersion]) -> WorkflowSummary:
    published = [v for v in versions if v.status == "published"]
    active = next((v for v in versions if v.id == workflow.active_version_id), None)
    return WorkflowSummary(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        active_version_number=active.version_number if active else None,
        latest_published_number=max((v.version_number for v in published), default=None),
        has_draft=any(v.status == "draft" for v in versions),
    )


def _detail(db: Session, workflow: Workflow) -> WorkflowDetail:
    versions = _versions_of(db, workflow)
    draft = next((v for v in versions if v.status == "draft"), None)
    published = [v for v in versions if v.status == "published"]
    latest = published[0] if published else None
    focus = draft or latest
    issues = validate_definition(Definition.model_validate(focus.definition)) if focus else []
    return WorkflowDetail(
        workflow=_summary(workflow, versions),
        versions=[_version_meta(v) for v in versions],
        draft=_version_out(draft) if draft else None,
        latest_published=_version_out(latest) if latest else None,
        issues=_issues_out(issues),
    )


def _next_version_number(db: Session, workflow: Workflow) -> int:
    current = db.scalar(
        select(func.max(WorkflowVersion.version_number)).where(WorkflowVersion.workflow_id == workflow.id)
    )
    return (current or 0) + 1


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This workflow was changed by someone else. Reload and try again."
        ) from None


# --------------------------------------------------------------------------- routes


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WorkflowDetail)
def create_workflow(
    payload: WorkflowCreateIn,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:write", csrf=True)),
    db: Session = Depends(get_db),
) -> WorkflowDetail:
    workflow = Workflow(
        organization_id=access.org_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        created_by_user_id=access.auth.user.id,
    )
    db.add(workflow)
    db.flush()
    definition = payload.definition.model_dump(mode="json") if payload.definition else dict(EMPTY_DEFINITION)
    db.add(
        WorkflowVersion(
            workflow_id=workflow.id,
            organization_id=access.org_id,
            version_number=1,
            status="draft",
            definition=definition,
            created_by_user_id=access.auth.user.id,
        )
    )
    record_audit(
        db,
        action="workflow.create",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="workflow",
        target_id=workflow.id,
        trace_id=trace_id_of(request),
    )
    db.commit()
    return _detail(db, workflow)


@router.get("", response_model=list[WorkflowSummary])
def list_workflows(
    access: OrgAccess = Depends(org_access("workflows:read", csrf=False)),
    db: Session = Depends(get_db),
) -> list[WorkflowSummary]:
    workflows = list(
        db.scalars(
            select(Workflow)
            .where(Workflow.organization_id == access.org_id, Workflow.archived_at.is_(None))
            .order_by(Workflow.updated_at.desc())
        )
    )
    if not workflows:
        return []
    versions = db.scalars(
        select(WorkflowVersion).where(
            WorkflowVersion.organization_id == access.org_id,
            WorkflowVersion.workflow_id.in_([w.id for w in workflows]),
        )
    )
    by_workflow: dict[str, list[WorkflowVersion]] = {w.id: [] for w in workflows}
    for version in versions:
        by_workflow[version.workflow_id].append(version)
    return [_summary(w, by_workflow[w.id]) for w in workflows]


@router.get("/{workflow_id}", response_model=WorkflowDetail)
def get_workflow(
    workflow_id: str,
    access: OrgAccess = Depends(org_access("workflows:read", csrf=False)),
    db: Session = Depends(get_db),
) -> WorkflowDetail:
    return _detail(db, _get_workflow(db, access.org_id, workflow_id))


@router.patch("/{workflow_id}", response_model=WorkflowSummary)
def update_workflow(
    workflow_id: str,
    payload: WorkflowUpdateIn,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:write", csrf=True)),
    db: Session = Depends(get_db),
) -> WorkflowSummary:
    workflow = _get_workflow(db, access.org_id, workflow_id)
    changed: list[str] = []
    if payload.name is not None and payload.name.strip() != workflow.name:
        workflow.name = payload.name.strip()
        changed.append("name")
    if payload.description is not None and payload.description.strip() != workflow.description:
        workflow.description = payload.description.strip()
        changed.append("description")
    if changed:
        record_audit(
            db,
            action="workflow.update",
            organization_id=access.org_id,
            actor_user_id=access.auth.user.id,
            target_type="workflow",
            target_id=workflow.id,
            metadata={"fields": changed},
            trace_id=trace_id_of(request),
        )
        db.commit()
    return _summary(workflow, _versions_of(db, workflow))


@router.put("/{workflow_id}/draft", response_model=DraftSaved)
def save_draft(
    workflow_id: str,
    payload: DraftSaveIn,
    access: OrgAccess = Depends(org_access("workflows:write", csrf=True)),
    db: Session = Depends(get_db),
) -> DraftSaved:
    """Save the editor's graph. Incomplete graphs are accepted and reported back as issues."""
    workflow = _get_workflow(db, access.org_id, workflow_id)
    draft = db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.organization_id == access.org_id,
            WorkflowVersion.status == "draft",
        )
    )
    definition = payload.definition.model_dump(mode="json")
    if draft is None:
        draft = WorkflowVersion(
            workflow_id=workflow.id,
            organization_id=access.org_id,
            version_number=_next_version_number(db, workflow),
            status="draft",
            definition=definition,
            created_by_user_id=access.auth.user.id,
        )
        db.add(draft)
    else:
        if payload.base_revision != draft.revision:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="This draft changed since you opened it. Reload to see the latest version.",
            )
        draft.definition = definition
        draft.revision = draft.revision + 1
    workflow.updated_at = utcnow()
    _commit_or_conflict(db)
    return DraftSaved(
        version=_version_out(draft),
        issues=_issues_out(validate_definition(payload.definition)),
    )


@router.post("/{workflow_id}/validate", response_model=list[IssueOut])
def validate_only(
    workflow_id: str,
    payload: Definition,
    access: OrgAccess = Depends(org_access("workflows:read", csrf=True)),
    db: Session = Depends(get_db),
) -> list[IssueOut]:
    """Validate a graph without saving it, for live feedback while editing."""
    _get_workflow(db, access.org_id, workflow_id)
    return _issues_out(validate_definition(payload))


@router.delete("/{workflow_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
def discard_draft(
    workflow_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:write", csrf=True)),
    db: Session = Depends(get_db),
) -> Response:
    workflow = _get_workflow(db, access.org_id, workflow_id)
    versions = _versions_of(db, workflow)
    draft = next((v for v in versions if v.status == "draft"), None)
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="There is no draft to discard.")
    if not any(v.status == "published" for v in versions):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="A workflow needs at least one version. Archive it instead."
        )
    db.delete(draft)
    record_audit(
        db,
        action="workflow.draft_discard",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="workflow",
        target_id=workflow.id,
        metadata={"version": draft.version_number},
        trace_id=trace_id_of(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{workflow_id}/publish", response_model=VersionOut)
def publish(
    workflow_id: str,
    payload: PublishIn,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=True)),
    db: Session = Depends(get_db),
):
    workflow = _get_workflow(db, access.org_id, workflow_id)
    draft = db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.organization_id == access.org_id,
            WorkflowVersion.status == "draft",
        )
    )
    if draft is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="There is no draft to publish.")
    if payload.base_revision != draft.revision:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This draft changed since you reviewed it. Reload and review it again before publishing.",
        )

    issues = validate_definition(Definition.model_validate(draft.definition))
    if has_errors(issues):
        count = sum(1 for issue in issues if issue.severity == "error")
        record_audit(
            db,
            action="workflow.publish",
            outcome="rejected",
            organization_id=access.org_id,
            actor_user_id=access.auth.user.id,
            target_type="workflow",
            target_id=workflow.id,
            metadata={"version": draft.version_number, "errors": count},
            trace_id=trace_id_of(request),
        )
        db.commit()
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": [f"Fix {count} issue{'s' if count != 1 else ''} before publishing."],
                "issues": [issue.as_dict() for issue in issues],
            },
        )

    draft.status = "published"
    draft.published_at = utcnow()
    draft.published_by_user_id = access.auth.user.id
    workflow.updated_at = utcnow()
    record_audit(
        db,
        action="workflow.publish",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="workflow",
        target_id=workflow.id,
        metadata={"version": draft.version_number},
        trace_id=trace_id_of(request),
    )
    db.commit()
    return _version_out(draft)


@router.get("/{workflow_id}/versions/{version_number}", response_model=VersionOut)
def get_version(
    workflow_id: str,
    version_number: int,
    access: OrgAccess = Depends(org_access("workflows:read", csrf=False)),
    db: Session = Depends(get_db),
) -> VersionOut:
    workflow = _get_workflow(db, access.org_id, workflow_id)
    version = db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.organization_id == access.org_id,
            WorkflowVersion.version_number == version_number,
        )
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return _version_out(version)


@router.post("/{workflow_id}/versions/{version_number}/activate", response_model=WorkflowSummary)
def activate(
    workflow_id: str,
    version_number: int,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=True)),
    db: Session = Depends(get_db),
) -> WorkflowSummary:
    workflow = _get_workflow(db, access.org_id, workflow_id)
    version = db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.organization_id == access.org_id,
            WorkflowVersion.version_number == version_number,
        )
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Version not found.")
    if version.status != "published":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Publish this version before activating it.")

    previous = workflow.active_version_id
    workflow.active_version_id = version.id
    workflow.updated_at = utcnow()
    record_audit(
        db,
        action="workflow.activate",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="workflow",
        target_id=workflow.id,
        metadata={"version": version.version_number, "replaced_active": previous is not None},
        trace_id=trace_id_of(request),
    )
    db.commit()
    return _summary(workflow, _versions_of(db, workflow))


@router.post("/{workflow_id}/deactivate", response_model=WorkflowSummary)
def deactivate(
    workflow_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=True)),
    db: Session = Depends(get_db),
) -> WorkflowSummary:
    workflow = _get_workflow(db, access.org_id, workflow_id)
    if workflow.active_version_id is not None:
        workflow.active_version_id = None
        workflow.updated_at = utcnow()
        record_audit(
            db,
            action="workflow.deactivate",
            organization_id=access.org_id,
            actor_user_id=access.auth.user.id,
            target_type="workflow",
            target_id=workflow.id,
            trace_id=trace_id_of(request),
        )
        db.commit()
    return _summary(workflow, _versions_of(db, workflow))


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_workflow(
    workflow_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=True)),
    db: Session = Depends(get_db),
) -> Response:
    workflow = _get_workflow(db, access.org_id, workflow_id)
    if workflow.active_version_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Deactivate this workflow before archiving it.")
    workflow.archived_at = utcnow()
    record_audit(
        db,
        action="workflow.archive",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="workflow",
        target_id=workflow.id,
        trace_id=trace_id_of(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
