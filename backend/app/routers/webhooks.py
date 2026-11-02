"""Inbound webhooks: a signed HTTP request starts a run of a workflow's active version.

Security model:
- Each workflow has at most one endpoint, addressed by an unguessable public id.
- Every request is signed: HMAC-SHA256 over "<timestamp>.<raw body>" with the endpoint's secret.
  Headers: X-Hermes-Timestamp (unix seconds), X-Hermes-Signature ("sha256=<hex>"), X-Hermes-Event-Id.
- Requests older or newer than five minutes are refused, which limits replay.
- The event id is unique per endpoint. A repeated delivery returns the original run and starts nothing new.
- The signing secret is stored encrypted and is shown once, when it is created or rotated.
"""

import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.crypto import SecretDecryptionError, decrypt_secret, encrypt_secret
from app.deps import OrgAccess, get_db, org_access, trace_id_of
from app.engine import MAX_PAYLOAD_BYTES, EngineError, start_execution
from app.models import WebhookEndpoint, WebhookEvent, Workflow, WorkflowVersion, utcnow

SIGNATURE_HEADER = "X-Hermes-Signature"
TIMESTAMP_HEADER = "X-Hermes-Timestamp"
EVENT_HEADER = "X-Hermes-Event-Id"
TOLERANCE_SECONDS = 300
_EVENT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SIGNATURE = re.compile(r"^sha256=([0-9a-f]{64})$")

public_router = APIRouter(prefix="/api/v1/hooks", tags=["webhooks"])
manage_router = APIRouter(prefix="/api/v1/orgs/{org_id}/workflows/{workflow_id}/webhook", tags=["webhooks"])


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """The signature senders must compute. Shared by the server and by tests and the sample sender script."""
    digest = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def _raw_body(request: Request) -> bytes:
    return await request.body()


def _reject(code: int, message: str) -> HTTPException:
    return HTTPException(code, detail=message)


# --------------------------------------------------------------------------- receiving


@public_router.post("/{public_id}", status_code=status.HTTP_202_ACCEPTED)
def receive(
    public_id: str,
    request: Request,
    body: bytes = Depends(_raw_body),
    db: Session = Depends(get_db),
):
    if not request.app.state.webhook_limiter.allow(public_id):
        raise _reject(status.HTTP_429_TOO_MANY_REQUESTS, "Too many deliveries. Slow down and retry.")
    if len(body) > MAX_PAYLOAD_BYTES:
        raise _reject(status.HTTP_413_CONTENT_TOO_LARGE, "The payload is too large.")

    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.public_id == public_id))
    if endpoint is None:
        raise _reject(status.HTTP_404_NOT_FOUND, "Unknown webhook.")

    timestamp = request.headers.get(TIMESTAMP_HEADER, "")
    signature = request.headers.get(SIGNATURE_HEADER, "")
    event_id = request.headers.get(EVENT_HEADER, "")
    if not timestamp.isdigit() or not _SIGNATURE.match(signature):
        raise _reject(status.HTTP_401_UNAUTHORIZED, "Missing or malformed signature headers.")
    if not _EVENT_ID.match(event_id):
        raise _reject(status.HTTP_400_BAD_REQUEST, f"{EVENT_HEADER} is required (letters, digits, . _ : -).")

    settings = request.app.state.settings
    try:
        secret = decrypt_secret(settings, endpoint.secret_ciphertext)
    except SecretDecryptionError:
        raise _reject(status.HTTP_503_SERVICE_UNAVAILABLE, "This webhook cannot verify requests right now.") from None

    fresh = abs(time.time() - int(timestamp)) <= TOLERANCE_SECONDS
    valid = hmac.compare_digest(sign(secret, timestamp, body), signature)
    if not (fresh and valid):
        record_audit(
            db,
            action="webhook.rejected",
            outcome="rejected",
            organization_id=endpoint.organization_id,
            target_type="workflow",
            target_id=endpoint.workflow_id,
            metadata={"reason": "stale_timestamp" if valid else "bad_signature", "event_id": event_id},
            trace_id=trace_id_of(request),
        )
        db.commit()
        # One message for both cases, so a caller cannot learn whether only the clock was wrong.
        raise _reject(status.HTTP_401_UNAUTHORIZED, "Signature verification failed.")

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise _reject(status.HTTP_400_BAD_REQUEST, "The body must be JSON.") from None
    if not isinstance(payload, dict):
        raise _reject(status.HTTP_400_BAD_REQUEST, "The body must be a JSON object.")

    existing = db.scalar(
        select(WebhookEvent).where(WebhookEvent.endpoint_id == endpoint.id, WebhookEvent.event_id == event_id)
    )
    if existing is not None and existing.status == "accepted":
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "duplicate", "execution_id": existing.execution_id},
        )

    workflow = db.get(Workflow, endpoint.workflow_id)
    version = (
        db.scalar(
            select(WorkflowVersion).where(
                WorkflowVersion.id == workflow.active_version_id,
                WorkflowVersion.organization_id == endpoint.organization_id,
            )
        )
        if workflow is not None and workflow.archived_at is None and workflow.active_version_id
        else None
    )

    event = existing or WebhookEvent(
        organization_id=endpoint.organization_id, endpoint_id=endpoint.id, event_id=event_id, status="failed"
    )
    endpoint.last_received_at = utcnow()

    if version is None:
        # Recorded as failed, so the sender can retry the same event once the workflow is active.
        event.status = "failed"
        event.error = "The workflow has no active version."
        event.received_at = utcnow()
        db.add(event)
        db.commit()
        raise _reject(status.HTTP_409_CONFLICT, "The workflow is not active. The event was not processed.")

    try:
        execution = start_execution(
            db,
            version=version,
            organization_id=endpoint.organization_id,
            workflow_id=endpoint.workflow_id,
            payload=payload,
            started_by_user_id=None,
            idempotency_key=f"webhook:{event_id}",
            trace_id=trace_id_of(request),
            trigger_type="webhook",
        )
        event.status = "accepted"
        event.error = None
        event.execution_id = execution.id
        event.received_at = utcnow()
        db.add(event)
        record_audit(
            db,
            action="webhook.received",
            organization_id=endpoint.organization_id,
            target_type="execution",
            target_id=execution.id,
            metadata={"event_id": event_id, "workflow_id": endpoint.workflow_id, "run_status": execution.status},
            trace_id=trace_id_of(request),
        )
        db.commit()
    except IntegrityError:
        # A concurrent delivery of the same event won the race. Report its run.
        db.rollback()
        winner = db.scalar(
            select(WebhookEvent).where(WebhookEvent.endpoint_id == endpoint.id, WebhookEvent.event_id == event_id)
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "duplicate", "execution_id": winner.execution_id if winner else None},
        )
    except EngineError as error:
        db.rollback()
        raise _reject(status.HTTP_409_CONFLICT, str(error)) from None

    return {"status": "accepted", "execution_id": execution.id, "run_status": execution.status}


# --------------------------------------------------------------------------- managing


class WebhookOut(BaseModel):
    enabled: bool
    path: str | None
    created_at: datetime | None
    rotated_at: datetime | None
    last_received_at: datetime | None


class WebhookSecretOut(WebhookOut):
    # Shown exactly once. Only an encrypted copy is stored.
    secret: str


class WebhookEventOut(BaseModel):
    event_id: str
    status: str
    execution_id: str | None
    error: str | None
    received_at: datetime


def _workflow(db: Session, org_id: str, workflow_id: str) -> Workflow:
    workflow = db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id, Workflow.organization_id == org_id, Workflow.archived_at.is_(None)
        )
    )
    if workflow is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Workflow not found.")
    return workflow


def _endpoint(db: Session, org_id: str, workflow_id: str) -> WebhookEndpoint | None:
    return db.scalar(
        select(WebhookEndpoint).where(
            WebhookEndpoint.workflow_id == workflow_id, WebhookEndpoint.organization_id == org_id
        )
    )


def _out(endpoint: WebhookEndpoint | None) -> WebhookOut:
    if endpoint is None:
        return WebhookOut(enabled=False, path=None, created_at=None, rotated_at=None, last_received_at=None)
    return WebhookOut(
        enabled=True,
        path=f"/api/v1/hooks/{endpoint.public_id}",
        created_at=endpoint.created_at,
        rotated_at=endpoint.rotated_at,
        last_received_at=endpoint.last_received_at,
    )


@manage_router.get("", response_model=WebhookOut)
def get_webhook(
    workflow_id: str,
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=False)),
    db: Session = Depends(get_db),
) -> WebhookOut:
    _workflow(db, access.org_id, workflow_id)
    return _out(_endpoint(db, access.org_id, workflow_id))


@manage_router.post("", response_model=WebhookSecretOut)
def create_or_rotate(
    workflow_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=True)),
    db: Session = Depends(get_db),
) -> WebhookSecretOut:
    """Create the endpoint, or rotate its secret. A rotated secret invalidates the previous one immediately."""
    workflow = _workflow(db, access.org_id, workflow_id)
    secret = "whsec_" + secrets.token_urlsafe(32)
    ciphertext = encrypt_secret(request.app.state.settings, secret)
    endpoint = _endpoint(db, access.org_id, workflow.id)
    action = "webhook.rotate"
    if endpoint is None:
        action = "webhook.create"
        endpoint = WebhookEndpoint(
            organization_id=access.org_id,
            workflow_id=workflow.id,
            public_id=secrets.token_urlsafe(24),
            secret_ciphertext=ciphertext,
            created_by_user_id=access.auth.user.id,
        )
        db.add(endpoint)
    else:
        endpoint.secret_ciphertext = ciphertext
        endpoint.rotated_at = utcnow()
    record_audit(
        db,
        action=action,
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="workflow",
        target_id=workflow.id,
        trace_id=trace_id_of(request),
    )
    db.commit()
    return WebhookSecretOut(**_out(endpoint).model_dump(), secret=secret)


@manage_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    workflow_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=True)),
    db: Session = Depends(get_db),
) -> Response:
    _workflow(db, access.org_id, workflow_id)
    endpoint = _endpoint(db, access.org_id, workflow_id)
    if endpoint is not None:
        db.delete(endpoint)
        record_audit(
            db,
            action="webhook.delete",
            organization_id=access.org_id,
            actor_user_id=access.auth.user.id,
            target_type="workflow",
            target_id=workflow_id,
            trace_id=trace_id_of(request),
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@manage_router.get("/events", response_model=list[WebhookEventOut])
def list_events(
    workflow_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    access: OrgAccess = Depends(org_access("workflows:publish", csrf=False)),
    db: Session = Depends(get_db),
) -> list[WebhookEventOut]:
    _workflow(db, access.org_id, workflow_id)
    endpoint = _endpoint(db, access.org_id, workflow_id)
    if endpoint is None:
        return []
    events = db.scalars(
        select(WebhookEvent)
        .where(WebhookEvent.endpoint_id == endpoint.id, WebhookEvent.organization_id == access.org_id)
        .order_by(WebhookEvent.received_at.desc())
        .limit(limit)
    ).all()
    return [
        WebhookEventOut(
            event_id=e.event_id, status=e.status, execution_id=e.execution_id, error=e.error, received_at=e.received_at
        )
        for e in events
    ]
