"""Organization, membership, invitation, and audit routes.

Every route here resolves the caller's membership before touching data. Role checks use the
server-side permission table in app/rbac.py. Responses for organizations the caller cannot see are 404.
"""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.deps import CurrentAuth, OrgAccess, get_current_auth, get_db, org_access, require_csrf, trace_id_of
from app.models import AuditEvent, Invitation, Membership, Organization, User, utcnow
from app.rbac import assignable_roles, can, can_manage_target
from app.schemas import (
    AuditEventOut,
    InvitationAcceptIn,
    InvitationCreatedOut,
    InvitationCreateIn,
    InvitationOut,
    MemberOut,
    MemberRoleIn,
    OrgCreateIn,
    OrgOut,
    OrgUpdateIn,
)
from app.security import hash_token, new_token
from app.utils import slugify

router = APIRouter(prefix="/api/v1", tags=["organizations"])


def _owner_count(db: Session, org_id: str) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.organization_id == org_id, Membership.role == "owner")
        )
        or 0
    )


def _org_out(org: Organization, role: str) -> OrgOut:
    return OrgOut(id=org.id, name=org.name, slug=org.slug, plan_code=org.plan_code, role=role)


def _invitation_out(inv: Invitation) -> InvitationOut:
    return InvitationOut(
        id=inv.id,
        email=inv.email,
        role=inv.role,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
    )


# --------------------------------------------------------------------------- organizations


@router.post("/orgs", status_code=status.HTTP_201_CREATED, response_model=OrgOut)
def create_org(
    payload: OrgCreateIn,
    request: Request,
    auth: CurrentAuth = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> OrgOut:
    name = payload.name.strip()
    org = Organization(name=name, slug=f"{slugify(name)}-{secrets.token_hex(3)}")
    db.add(org)
    db.flush()
    db.add(Membership(user_id=auth.user.id, organization_id=org.id, role="owner"))
    record_audit(
        db,
        action="org.create",
        organization_id=org.id,
        actor_user_id=auth.user.id,
        target_type="organization",
        target_id=org.id,
        trace_id=trace_id_of(request),
    )
    db.commit()
    return _org_out(org, "owner")


@router.get("/orgs", response_model=list[OrgOut])
def list_my_orgs(
    auth: CurrentAuth = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> list[OrgOut]:
    rows = db.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == auth.user.id)
        .order_by(Organization.name)
    ).all()
    return [_org_out(org, role) for org, role in rows]


@router.get("/orgs/{org_id}", response_model=OrgOut)
def get_org(access: OrgAccess = Depends(org_access("org:read", csrf=False))) -> OrgOut:
    return _org_out(access.organization, access.role)


@router.patch("/orgs/{org_id}", response_model=OrgOut)
def update_org(
    payload: OrgUpdateIn,
    request: Request,
    access: OrgAccess = Depends(org_access("org:settings:write", csrf=True)),
    db: Session = Depends(get_db),
) -> OrgOut:
    org = db.get(Organization, access.org_id)
    changed: list[str] = []
    if payload.name is not None and payload.name.strip() != org.name:
        org.name = payload.name.strip()
        changed.append("name")
    if changed:
        record_audit(
            db,
            action="org.update",
            organization_id=org.id,
            actor_user_id=access.auth.user.id,
            target_type="organization",
            target_id=org.id,
            metadata={"fields": changed},
            trace_id=trace_id_of(request),
        )
        db.commit()
    return _org_out(org, access.role)


# --------------------------------------------------------------------------- members


@router.get("/orgs/{org_id}/members", response_model=list[MemberOut])
def list_members(
    access: OrgAccess = Depends(org_access("members:read", csrf=False)),
    db: Session = Depends(get_db),
) -> list[MemberOut]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == access.org_id)
        .order_by(User.full_name)
    ).all()
    return [
        MemberOut(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=membership.role,
            joined_at=membership.created_at,
        )
        for membership, user in rows
    ]


def _get_membership(db: Session, org_id: str, user_id: str) -> Membership:
    membership = db.scalar(
        select(Membership).where(Membership.organization_id == org_id, Membership.user_id == user_id)
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Member not found.")
    return membership


@router.patch("/orgs/{org_id}/members/{user_id}", response_model=MemberOut)
def change_member_role(
    user_id: str,
    payload: MemberRoleIn,
    request: Request,
    access: OrgAccess = Depends(org_access("members:manage", csrf=True)),
    db: Session = Depends(get_db),
) -> MemberOut:
    target = _get_membership(db, access.org_id, user_id)
    if not can_manage_target(access.role, target.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You cannot change this member's role.")
    if payload.role not in assignable_roles(access.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You cannot grant this role.")
    if target.role == "owner" and payload.role != "owner" and _owner_count(db, access.org_id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An organization must keep at least one owner.")

    previous = target.role
    target.role = payload.role
    user = db.get(User, user_id)
    record_audit(
        db,
        action="member.role_change",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="user",
        target_id=user_id,
        metadata={"from": previous, "to": payload.role},
        trace_id=trace_id_of(request),
    )
    db.commit()
    return MemberOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=target.role,
        joined_at=target.created_at,
    )


@router.delete("/orgs/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access(None, csrf=True)),
    db: Session = Depends(get_db),
) -> Response:
    """Revoke a member's access. Any member may leave; removing others requires members:manage."""
    target = _get_membership(db, access.org_id, user_id)
    is_self = user_id == access.auth.user.id
    if not is_self:
        if not can(access.role, "members:manage") or not can_manage_target(access.role, target.role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You cannot remove this member.")
    if target.role == "owner" and _owner_count(db, access.org_id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An organization must keep at least one owner.")

    removed_role = target.role
    db.delete(target)
    record_audit(
        db,
        action="member.remove",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="user",
        target_id=user_id,
        metadata={"role": removed_role, "self_leave": is_self},
        trace_id=trace_id_of(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- invitations


def _pending_invitations_query(org_id: str):
    now = utcnow()
    return select(Invitation).where(
        Invitation.organization_id == org_id,
        Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None),
        Invitation.expires_at > now,
    )


@router.post(
    "/orgs/{org_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=InvitationCreatedOut,
)
def create_invitation(
    payload: InvitationCreateIn,
    request: Request,
    access: OrgAccess = Depends(org_access("members:invite", csrf=True)),
    db: Session = Depends(get_db),
) -> InvitationCreatedOut:
    settings = request.app.state.settings
    if payload.role not in assignable_roles(access.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You cannot invite someone with this role.")

    existing_user = db.scalar(select(User).where(User.email == payload.email))
    if existing_user is not None:
        already_member = db.scalar(
            select(Membership.id).where(
                Membership.organization_id == access.org_id, Membership.user_id == existing_user.id
            )
        )
        if already_member is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This person is already a member.")

    duplicate = db.scalar(_pending_invitations_query(access.org_id).where(Invitation.email == payload.email))
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A pending invitation already exists for this email.")

    token = new_token()
    invitation = Invitation(
        organization_id=access.org_id,
        email=payload.email,
        role=payload.role,
        token_hash=hash_token(token),
        invited_by_user_id=access.auth.user.id,
        expires_at=utcnow() + timedelta(days=settings.invitation_ttl_days),
    )
    db.add(invitation)
    db.flush()
    record_audit(
        db,
        action="invitation.create",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="invitation",
        target_id=invitation.id,
        metadata={"role": payload.role},
        trace_id=trace_id_of(request),
    )
    db.commit()
    return InvitationCreatedOut(**_invitation_out(invitation).model_dump(), token=token)


@router.get("/orgs/{org_id}/invitations", response_model=list[InvitationOut])
def list_invitations(
    access: OrgAccess = Depends(org_access("members:invite", csrf=False)),
    db: Session = Depends(get_db),
) -> list[InvitationOut]:
    rows = db.scalars(_pending_invitations_query(access.org_id).order_by(Invitation.created_at.desc())).all()
    return [_invitation_out(inv) for inv in rows]


@router.delete("/orgs/{org_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access("members:invite", csrf=True)),
    db: Session = Depends(get_db),
) -> Response:
    invitation = db.scalar(
        select(Invitation).where(Invitation.id == invitation_id, Invitation.organization_id == access.org_id)
    )
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invitation not found.")
    if invitation.revoked_at is None and invitation.accepted_at is None:
        invitation.revoked_at = utcnow()
        record_audit(
            db,
            action="invitation.revoke",
            organization_id=access.org_id,
            actor_user_id=access.auth.user.id,
            target_type="invitation",
            target_id=invitation.id,
            trace_id=trace_id_of(request),
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_INVALID_INVITATION = "Invitation is invalid or has expired."


@router.post("/invitations/accept", response_model=OrgOut)
def accept_invitation(
    payload: InvitationAcceptIn,
    request: Request,
    auth: CurrentAuth = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> OrgOut:
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(payload.token)))
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= utcnow()
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_INVALID_INVITATION)

    if invitation.email != auth.user.email:
        record_audit(
            db,
            action="invitation.accept",
            outcome="rejected",
            organization_id=invitation.organization_id,
            actor_user_id=auth.user.id,
            target_type="invitation",
            target_id=invitation.id,
            metadata={"reason": "email_mismatch"},
            trace_id=trace_id_of(request),
        )
        db.commit()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="This invitation was issued to a different email address."
        )

    # The inviter must still be able to grant this role. Otherwise an invitation issued before a demotion stays usable.
    inviter = None
    if invitation.invited_by_user_id is not None:
        inviter = db.scalar(
            select(Membership.role).where(
                Membership.organization_id == invitation.organization_id,
                Membership.user_id == invitation.invited_by_user_id,
            )
        )
    if inviter is None or invitation.role not in assignable_roles(inviter):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_INVALID_INVITATION)

    already = db.scalar(
        select(Membership.id).where(
            Membership.organization_id == invitation.organization_id, Membership.user_id == auth.user.id
        )
    )
    if already is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="You are already a member of this organization.")

    db.add(Membership(user_id=auth.user.id, organization_id=invitation.organization_id, role=invitation.role))
    invitation.accepted_at = utcnow()
    org = db.get(Organization, invitation.organization_id)
    record_audit(
        db,
        action="invitation.accept",
        organization_id=org.id,
        actor_user_id=auth.user.id,
        target_type="invitation",
        target_id=invitation.id,
        metadata={"role": invitation.role},
        trace_id=trace_id_of(request),
    )
    db.commit()
    return _org_out(org, invitation.role)


# --------------------------------------------------------------------------- audit


@router.get("/orgs/{org_id}/audit-events", response_model=list[AuditEventOut])
def list_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, ge=1),
    access: OrgAccess = Depends(org_access("audit:read", csrf=False)),
    db: Session = Depends(get_db),
) -> list[AuditEventOut]:
    query = select(AuditEvent).where(AuditEvent.organization_id == access.org_id)
    if before_id is not None:
        query = query.where(AuditEvent.id < before_id)
    events = db.scalars(query.order_by(AuditEvent.id.desc()).limit(limit)).all()
    return [
        AuditEventOut(
            id=e.id,
            action=e.action,
            outcome=e.outcome,
            actor_user_id=e.actor_user_id,
            target_type=e.target_type,
            target_id=e.target_id,
            metadata=e.event_metadata,
            trace_id=e.trace_id,
            created_at=e.created_at,
        )
        for e in events
    ]
