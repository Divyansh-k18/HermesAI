"""FastAPI dependencies: database session, authenticated user, CSRF, and organization-scoped access.

Tenant isolation rule: every organization-scoped route receives its organization through
`org_access`, which resolves the caller's membership. A caller without membership receives 404,
so organization IDs cannot be probed.
"""

import secrets
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthSession, Membership, Organization, User, utcnow
from app.rbac import can
from app.security import hash_token

SESSION_COOKIE = "hermes_session"
CSRF_HEADER = "X-CSRF-Token"


def get_db(request: Request) -> Iterator[Session]:
    db: Session = request.app.state.session_factory()
    # The engine reads settings from the session, for example to decrypt connection secrets.
    db.info["settings"] = request.app.state.settings
    try:
        yield db
    finally:
        db.close()


@dataclass(frozen=True)
class CurrentAuth:
    user: User
    session: AuthSession


def _unauthenticated() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Cookie"},
    )


def get_current_auth(request: Request, db: Session = Depends(get_db)) -> CurrentAuth:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _unauthenticated()
    session_row = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if session_row is None or session_row.revoked_at is not None or session_row.expires_at <= utcnow():
        raise _unauthenticated()
    user = db.get(User, session_row.user_id)
    if user is None or not user.is_active:
        raise _unauthenticated()
    return CurrentAuth(user=user, session=session_row)


def require_csrf(request: Request, auth: CurrentAuth = Depends(get_current_auth)) -> CurrentAuth:
    """Cookie-authenticated state changes must echo the session's CSRF token in a header."""
    _check_csrf(request, auth)
    return auth


def _check_csrf(request: Request, auth: CurrentAuth) -> None:
    header_value = request.headers.get(CSRF_HEADER, "")
    if not header_value or not secrets.compare_digest(header_value, auth.session.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")


@dataclass(frozen=True)
class OrgAccess:
    organization: Organization
    membership: Membership
    auth: CurrentAuth

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def org_id(self) -> str:
        return self.organization.id


def load_org_access(db: Session, auth: CurrentAuth, org_id: str, permission: str | None) -> OrgAccess:
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == auth.user.id,
            Membership.organization_id == org_id,
        )
    )
    if membership is None:
        # Same response whether the organization is missing or belongs to someone else.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    if permission is not None and not can(membership.role, permission):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have permission for this action.")
    organization = db.get(Organization, org_id)
    if organization is None:  # pragma: no cover - FK guarantees existence
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    return OrgAccess(organization=organization, membership=membership, auth=auth)


def org_access(permission: str | None, *, csrf: bool) -> object:
    """Build a dependency that authenticates the caller and authorizes them for one organization."""

    def dependency(
        org_id: str,
        request: Request,
        db: Session = Depends(get_db),
    ) -> OrgAccess:
        auth = get_current_auth(request, db)
        if csrf:
            _check_csrf(request, auth)
        return load_org_access(db, auth, org_id, permission)

    return dependency


def trace_id_of(request: Request) -> str | None:
    return getattr(request.state, "trace_id", None)
