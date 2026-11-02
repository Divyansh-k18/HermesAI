"""Audit event recording. Events are written in the same transaction as the action they describe."""

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent

_SENSITIVE_KEY_FRAGMENTS = ("password", "token", "secret", "key", "credential", "authorization")


def redact(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Drop any metadata key that could carry a credential. Values are never logged raw for these keys."""
    if not metadata:
        return {}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = key.lower()
        if any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS):
            continue
        clean[key] = value
    return clean


def record_audit(
    db: Session,
    *,
    action: str,
    outcome: str = "success",
    organization_id: str | None = None,
    actor_user_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        outcome=outcome,
        target_type=target_type,
        target_id=target_id,
        event_metadata=redact(metadata),
        trace_id=trace_id,
    )
    db.add(event)
    return event
