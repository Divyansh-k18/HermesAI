"""Connect a mailbox to a workflow so that each new email starts a run.

Saving verifies the sign-in against the real mail server and records the newest existing message as the
starting point, so connecting a busy mailbox never turns old mail into orders. The password is stored
encrypted and is never returned.
"""

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import email_inbox as mail
from app.audit import record_audit
from app.crypto import encrypt_secret
from app.deps import OrgAccess, get_db, org_access, trace_id_of
from app.http_client import OutboundError, ensure_public_host
from app.models import EmailInbox, Workflow, WorkflowExecution

router = APIRouter(prefix="/api/v1/orgs/{org_id}/workflows/{workflow_id}/email-inbox", tags=["email"])

_HOST = re.compile(r"^[A-Za-z0-9.-]{3,255}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class InboxIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    imap_host: str = Field(default="imap.gmail.com", max_length=255)
    username: str = Field(min_length=3, max_length=320)
    # Required when connecting. Leave out when changing other settings to keep the stored password.
    password: str | None = Field(default=None, min_length=1, max_length=1024)
    folder: str = Field(default="INBOX", min_length=1, max_length=100)
    allowed_senders: str = Field(default="", max_length=2000)

    @field_validator("imap_host")
    @classmethod
    def _host(cls, value: str) -> str:
        value = value.strip().lower()
        if not _HOST.match(value):
            raise ValueError("Enter the mail server's host name only, such as imap.gmail.com.")
        return value

    @field_validator("username", "folder", "allowed_senders")
    @classmethod
    def _no_control_characters(cls, value: str) -> str:
        if _CONTROL.search(value):
            raise ValueError("Line breaks and control characters are not allowed.")
        return value.strip()


class RecentEmail(BaseModel):
    run_id: str
    received_at: datetime
    sender: str | None
    subject: str | None
    status: str


class InboxOut(BaseModel):
    enabled: bool
    imap_host: str | None = None
    username: str | None = None
    folder: str | None = None
    allowed_senders: str | None = None
    last_checked_at: datetime | None = None
    last_error: str | None = None
    runs_started: int = 0
    # The latest emails that started runs, so the builder shows mail arriving.
    recent_emails: list[RecentEmail] = []


class CheckOut(BaseModel):
    started: int
    ignored: int
    duplicates: int
    error: str | None
    run_ids: list[str]


def _workflow(db: Session, org_id: str, workflow_id: str) -> Workflow:
    workflow = db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id, Workflow.organization_id == org_id, Workflow.archived_at.is_(None)
        )
    )
    if workflow is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Workflow not found.")
    return workflow


def _inbox(db: Session, org_id: str, workflow_id: str) -> EmailInbox | None:
    return db.scalar(
        select(EmailInbox).where(EmailInbox.workflow_id == workflow_id, EmailInbox.organization_id == org_id)
    )


def _out(inbox: EmailInbox | None) -> InboxOut:
    if inbox is None:
        return InboxOut(enabled=False)
    return InboxOut(
        enabled=True,
        imap_host=inbox.imap_host,
        username=inbox.username,
        folder=inbox.folder,
        allowed_senders=inbox.allowed_senders,
        last_checked_at=inbox.last_checked_at,
        last_error=inbox.last_error,
        runs_started=inbox.runs_started,
    )


@router.get("", response_model=InboxOut)
def get_inbox(
    workflow_id: str,
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=False)),
    db: Session = Depends(get_db),
) -> InboxOut:
    _workflow(db, access.org_id, workflow_id)
    info = _out(_inbox(db, access.org_id, workflow_id))
    runs = db.scalars(
        select(WorkflowExecution)
        .where(
            WorkflowExecution.organization_id == access.org_id,
            WorkflowExecution.workflow_id == workflow_id,
            WorkflowExecution.trigger_type == "email",
        )
        .order_by(WorkflowExecution.started_at.desc())
        .limit(8)
    ).all()
    for run in runs:
        email = (run.trigger_payload or {}).get("email") or {}
        info.recent_emails.append(
            RecentEmail(
                run_id=run.id,
                received_at=run.started_at,
                sender=str(email.get("from") or "")[:320] or None,
                subject=str(email.get("subject") or "")[:200] or None,
                status=run.status,
            )
        )
    return info


@router.put("", response_model=InboxOut)
def connect_inbox(
    workflow_id: str,
    payload: InboxIn,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=True)),
    db: Session = Depends(get_db),
) -> InboxOut:
    workflow = _workflow(db, access.org_id, workflow_id)
    settings = request.app.state.settings
    existing = _inbox(db, access.org_id, workflow.id)

    if payload.password is None and existing is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Enter the mailbox password to connect it.")
    try:
        ensure_public_host(payload.imap_host)
    except OutboundError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from None

    from app.crypto import decrypt_secret

    password = (
        payload.password if payload.password is not None else decrypt_secret(settings, existing.secret_ciphertext)
    )
    candidate = EmailInbox(
        organization_id=access.org_id,
        workflow_id=workflow.id,
        imap_host=payload.imap_host,
        imap_port=mail.IMAP_PORT,
        username=payload.username,
        folder=payload.folder,
        secret_ciphertext="",
    )
    # Verify the sign-in now, and start from the newest message so old mail is never processed.
    try:
        validity, newest = mail.open_mailbox(candidate, password).latest_uid()
    except mail.MailboxError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from None

    mailbox_changed = existing is None or (
        existing.imap_host,
        existing.username,
        existing.folder,
    ) != (payload.imap_host, payload.username, payload.folder)

    inbox = existing or candidate
    inbox.imap_host = payload.imap_host
    inbox.imap_port = mail.IMAP_PORT
    inbox.username = payload.username
    inbox.folder = payload.folder
    inbox.allowed_senders = payload.allowed_senders
    inbox.secret_ciphertext = encrypt_secret(settings, password)
    inbox.last_error = None
    if mailbox_changed:
        inbox.uid_validity = validity or None
        inbox.last_uid = newest
    if existing is None:
        inbox.created_by_user_id = access.auth.user.id
        db.add(inbox)

    record_audit(
        db,
        action="email_inbox.connect" if existing is None else "email_inbox.update",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="workflow",
        target_id=workflow.id,
        metadata={"host": payload.imap_host, "folder": payload.folder, "restricted": bool(payload.allowed_senders)},
        trace_id=trace_id_of(request),
    )
    db.commit()
    return _out(inbox)


@router.post("/check", response_model=CheckOut)
def check_now(
    workflow_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=True)),
    db: Session = Depends(get_db),
) -> CheckOut:
    """Read new mail right away instead of waiting for the next automatic check."""
    _workflow(db, access.org_id, workflow_id)
    inbox = _inbox(db, access.org_id, workflow_id)
    if inbox is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No mailbox is connected to this workflow.")
    result = mail.check_inbox(db, inbox, request.app.state.settings)
    return CheckOut(
        started=result.started,
        ignored=result.ignored,
        duplicates=result.duplicates,
        error=result.error,
        run_ids=result.run_ids,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_inbox(
    workflow_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=True)),
    db: Session = Depends(get_db),
) -> Response:
    _workflow(db, access.org_id, workflow_id)
    inbox = _inbox(db, access.org_id, workflow_id)
    if inbox is not None:
        db.delete(inbox)
        record_audit(
            db,
            action="email_inbox.disconnect",
            organization_id=access.org_id,
            actor_user_id=access.auth.user.id,
            target_type="workflow",
            target_id=workflow_id,
            trace_id=trace_id_of(request),
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
