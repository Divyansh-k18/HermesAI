"""SQLAlchemy ORM models for Phase 1: identity, organizations, memberships, sessions, invitations, audit.

Conventions:
- Primary keys are UUID strings (portable across SQLite for tests and PostgreSQL in production).
- Timestamps are naive UTC (`utcnow`). Every writer must use `utcnow` so comparisons stay consistent.
- Tenant-scoped tables carry `organization_id` and are always queried with it (see app/deps.py).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ROLE_CHECK = "role IN ('owner', 'admin', 'member', 'viewer')"


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    plan_code: Mapped[str] = mapped_column(String(40), default="trial", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
        CheckConstraint(ROLE_CHECK, name="ck_membership_role"),
        Index("ix_memberships_org_id", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class AuthSession(Base):
    """Server-side session. Only a SHA-256 hash of the bearer token is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Invitation(Base):
    """Organization invitation. Only a hash of the one-time token is stored."""

    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint(ROLE_CHECK, name="ck_invitation_role"),
        Index("ix_invitations_org_status", "organization_id", "revoked_at", "accepted_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditEvent(Base):
    """Append-only record of security-relevant actions. Application code must not update or delete rows."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_org_created", "organization_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Workflow(Base):
    """A workflow identity. The graph itself lives in immutable-once-published versions."""

    __tablename__ = "workflows"
    __table_args__ = (Index("ix_workflows_org_updated", "organization_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # The published version that receives events. NULL means the workflow is not live.
    active_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workflow_versions.id", ondelete="SET NULL", use_alter=True, name="fk_workflow_active_version"),
        nullable=True,
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkflowVersion(Base):
    """One version of a workflow graph. Draft versions are editable. Published versions never change."""

    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "version_number", name="uq_workflow_version_number"),
        CheckConstraint("status IN ('draft', 'published')", name="ck_workflow_version_status"),
        # At most one draft per workflow.
        Index(
            "uq_workflow_single_draft",
            "workflow_id",
            unique=True,
            sqlite_where=text("status = 'draft'"),
            postgresql_where=text("status = 'draft'"),
        ),
        Index("ix_workflow_versions_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    # Denormalized so every query on this table can be tenant-scoped directly.
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Incremented on every draft save. Clients send it back so concurrent edits are detected.
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PublishedVersionImmutableError(RuntimeError):
    """Raised when code tries to modify or delete a published workflow version."""


def _original_status(version: "WorkflowVersion") -> str | None:
    history = inspect(version).attrs.status.history
    if history.deleted:
        return history.deleted[0]
    if history.unchanged:
        return history.unchanged[0]
    return None


@event.listens_for(WorkflowVersion, "before_update")
def _block_published_update(_mapper, _connection, target: WorkflowVersion) -> None:
    # Defense in depth: the API never updates a published row, and the ORM refuses to as well.
    if _original_status(target) == "published":
        raise PublishedVersionImmutableError("Published workflow versions are immutable.")


@event.listens_for(WorkflowVersion, "before_delete")
def _block_published_delete(_mapper, _connection, target: WorkflowVersion) -> None:
    if _original_status(target) == "published":
        raise PublishedVersionImmutableError("Published workflow versions cannot be deleted.")
