"""Tenant isolation, role authorization, invitations, and audit visibility."""

from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Invitation, utcnow


def _create_org(owner, name="Acme Corporation"):
    r = owner.post("/api/v1/orgs", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _invite(admin, org_id, email, role="member"):
    r = admin.post(f"/api/v1/orgs/{org_id}/invitations", json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    return r.json()


def _add_member(owner, org_id, make_account, email, role="member"):
    """Invite and accept, returning the Account for the new member."""
    acct = make_account(email, full_name=email.split("@")[0].title())
    invitation = _invite(owner, org_id, email, role)
    r = acct.post("/api/v1/invitations/accept", json={"token": invitation["token"]})
    assert r.status_code == 200, r.text
    return acct


def test_creator_becomes_owner(make_account):
    owner = make_account("owner@acme.example.com")
    org = _create_org(owner)
    assert org["role"] == "owner"
    assert org["slug"].startswith("acme-corporation-")


def test_org_slug_is_unique_for_same_name(make_account):
    owner = make_account("twins@acme.example.com")
    a = _create_org(owner, "Twin Name")
    b = _create_org(owner, "Twin Name")
    assert a["slug"] != b["slug"]


def test_non_member_gets_404_for_org_not_404_for_missing(make_account):
    owner = make_account("owner-iso@acme.example.com")
    outsider = make_account("outsider@other.example.com")
    org = _create_org(owner)
    real = outsider.get(f"/api/v1/orgs/{org['id']}")
    missing = outsider.get("/api/v1/orgs/00000000-0000-0000-0000-000000000000")
    assert real.status_code == missing.status_code == 404
    assert real.json() == missing.json()


def test_org_list_only_shows_own_memberships(make_account):
    alice = make_account("alice@tenant.example.com")
    bob = make_account("bob@tenant.example.com")
    _create_org(alice, "Alice Ltd")
    _create_org(bob, "Bob Ltd")
    alice_orgs = alice.get("/api/v1/orgs").json()
    assert [o["name"] for o in alice_orgs] == ["Alice Ltd"]


def test_cross_tenant_member_change_is_blocked(make_account):
    owner_a = make_account("owner-a@tenant.example.com")
    owner_b = make_account("owner-b@tenant.example.com")
    org_a = _create_org(owner_a, "Tenant A")
    org_b = _create_org(owner_b, "Tenant B")
    victim = _add_member(owner_a, org_a["id"], make_account, "victim@tenant.example.com")
    # Owner B tries to modify a member of Org A through Org B's URL.
    r = owner_b.patch(f"/api/v1/orgs/{org_b['id']}/members/{victim.user_id}", json={"role": "viewer"})
    assert r.status_code == 404
    # Owner B tries to reach Org A directly.
    r = owner_b.patch(f"/api/v1/orgs/{org_a['id']}/members/{victim.user_id}", json={"role": "viewer"})
    assert r.status_code == 404


def test_member_cannot_invite(make_account):
    owner = make_account("owner-inv@acme.example.com")
    org = _create_org(owner)
    member = _add_member(owner, org["id"], make_account, "member-inv@acme.example.com", role="member")
    r = member.post(f"/api/v1/orgs/{org['id']}/invitations", json={"email": "x@acme.example.com", "role": "viewer"})
    assert r.status_code == 403


def test_viewer_can_read_members_but_not_change_settings(make_account):
    owner = make_account("owner-view@acme.example.com")
    org = _create_org(owner)
    viewer = _add_member(owner, org["id"], make_account, "viewer@acme.example.com", role="viewer")
    assert viewer.get(f"/api/v1/orgs/{org['id']}/members").status_code == 200
    r = viewer.patch(f"/api/v1/orgs/{org['id']}", json={"name": "Renamed Co"})
    assert r.status_code == 403


def test_admin_cannot_grant_admin_or_owner(make_account):
    owner = make_account("owner-esc@acme.example.com")
    org = _create_org(owner)
    admin = _add_member(owner, org["id"], make_account, "admin-esc@acme.example.com", role="admin")
    member = _add_member(owner, org["id"], make_account, "member-esc@acme.example.com", role="member")
    assert _invite_status(admin, org["id"], "new-admin@acme.example.com", "admin") == 403
    assert _invite_status(admin, org["id"], "new-owner@acme.example.com", "owner") == 403
    r = admin.patch(f"/api/v1/orgs/{org['id']}/members/{member.user_id}", json={"role": "admin"})
    assert r.status_code == 403
    r = admin.patch(f"/api/v1/orgs/{org['id']}/members/{member.user_id}", json={"role": "owner"})
    assert r.status_code == 403
    r = admin.patch(f"/api/v1/orgs/{org['id']}/members/{member.user_id}", json={"role": "viewer"})
    assert r.status_code == 200  # admins may manage members and grant member or viewer


def test_admin_cannot_demote_or_remove_owner(make_account):
    owner = make_account("owner-protect@acme.example.com")
    org = _create_org(owner)
    admin = _add_member(owner, org["id"], make_account, "admin-protect@acme.example.com", role="admin")
    r = admin.patch(f"/api/v1/orgs/{org['id']}/members/{owner.user_id}", json={"role": "viewer"})
    assert r.status_code == 403
    r = admin.delete(f"/api/v1/orgs/{org['id']}/members/{owner.user_id}")
    assert r.status_code == 403


def test_admin_cannot_modify_another_admin(make_account):
    owner = make_account("owner-peer@acme.example.com")
    org = _create_org(owner)
    admin1 = _add_member(owner, org["id"], make_account, "admin1@acme.example.com", role="admin")
    admin2 = _add_member(owner, org["id"], make_account, "admin2@acme.example.com", role="admin")
    r = admin1.patch(f"/api/v1/orgs/{org['id']}/members/{admin2.user_id}", json={"role": "viewer"})
    assert r.status_code == 403


def test_last_owner_cannot_be_demoted_or_leave(make_account):
    owner = make_account("sole-owner@acme.example.com")
    org = _create_org(owner)
    r = owner.patch(f"/api/v1/orgs/{org['id']}/members/{owner.user_id}", json={"role": "admin"})
    assert r.status_code == 409
    r = owner.delete(f"/api/v1/orgs/{org['id']}/members/{owner.user_id}")
    assert r.status_code == 409


def test_owner_can_promote_then_demote_owner_when_another_exists(make_account):
    owner = make_account("co-owner@acme.example.com")
    org = _create_org(owner)
    second = _add_member(owner, org["id"], make_account, "second@acme.example.com", role="member")
    assert owner.patch(f"/api/v1/orgs/{org['id']}/members/{second.user_id}", json={"role": "owner"}).status_code == 200
    assert owner.patch(f"/api/v1/orgs/{org['id']}/members/{owner.user_id}", json={"role": "admin"}).status_code == 200


def test_removed_member_loses_access_immediately(make_account):
    owner = make_account("owner-rm@acme.example.com")
    org = _create_org(owner)
    member = _add_member(owner, org["id"], make_account, "rm@acme.example.com")
    assert member.get(f"/api/v1/orgs/{org['id']}").status_code == 200
    assert owner.delete(f"/api/v1/orgs/{org['id']}/members/{member.user_id}").status_code == 204
    assert member.get(f"/api/v1/orgs/{org['id']}").status_code == 404
    assert member.get(f"/api/v1/orgs/{org['id']}/members").status_code == 404


def test_member_can_leave_voluntarily(make_account):
    owner = make_account("owner-leave@acme.example.com")
    org = _create_org(owner)
    member = _add_member(owner, org["id"], make_account, "leaver@acme.example.com")
    assert member.delete(f"/api/v1/orgs/{org['id']}/members/{member.user_id}").status_code == 204


def test_invitation_email_mismatch_is_rejected(make_account):
    owner = make_account("owner-mm@acme.example.com")
    org = _create_org(owner)
    invitation = _invite(owner, org["id"], "intended@acme.example.com")
    impostor = make_account("impostor@acme.example.com")
    r = impostor.post("/api/v1/invitations/accept", json={"token": invitation["token"]})
    assert r.status_code == 403
    assert impostor.get(f"/api/v1/orgs/{org['id']}").status_code == 404


def test_invitation_token_is_single_use(make_account):
    owner = make_account("owner-once@acme.example.com")
    org = _create_org(owner)
    invitation = _invite(owner, org["id"], "once@acme.example.com")
    invitee = make_account("once@acme.example.com")
    assert invitee.post("/api/v1/invitations/accept", json={"token": invitation["token"]}).status_code == 200
    assert invitee.post("/api/v1/invitations/accept", json={"token": invitation["token"]}).status_code == 404


def test_expired_invitation_is_rejected(make_account, engine):
    owner = make_account("owner-exp@acme.example.com")
    org = _create_org(owner)
    invitation = _invite(owner, org["id"], "late@acme.example.com")
    with Session(engine) as db:
        db.execute(update(Invitation).values(expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()
    invitee = make_account("late@acme.example.com")
    assert invitee.post("/api/v1/invitations/accept", json={"token": invitation["token"]}).status_code == 404


def test_revoked_invitation_is_rejected(make_account):
    owner = make_account("owner-rv@acme.example.com")
    org = _create_org(owner)
    invitation = _invite(owner, org["id"], "revoked@acme.example.com")
    assert owner.delete(f"/api/v1/orgs/{org['id']}/invitations/{invitation['id']}").status_code == 204
    invitee = make_account("revoked@acme.example.com")
    assert invitee.post("/api/v1/invitations/accept", json={"token": invitation["token"]}).status_code == 404


def test_invitation_from_demoted_inviter_is_no_longer_usable(make_account):
    owner = make_account("owner-dem@acme.example.com")
    org = _create_org(owner)
    admin = _add_member(owner, org["id"], make_account, "admin-dem@acme.example.com", role="admin")
    invitation = _invite(admin, org["id"], "via-admin@acme.example.com", role="member")
    # Owner demotes the admin to viewer before the invitee accepts.
    assert owner.patch(f"/api/v1/orgs/{org['id']}/members/{admin.user_id}", json={"role": "viewer"}).status_code == 200
    invitee = make_account("via-admin@acme.example.com")
    assert invitee.post("/api/v1/invitations/accept", json={"token": invitation["token"]}).status_code == 404


def test_duplicate_pending_invitation_rejected(make_account):
    owner = make_account("owner-dup@acme.example.com")
    org = _create_org(owner)
    _invite(owner, org["id"], "dupe@acme.example.com")
    r = owner.post(f"/api/v1/orgs/{org['id']}/invitations", json={"email": "dupe@acme.example.com", "role": "member"})
    assert r.status_code == 409


def test_invitation_token_not_exposed_in_listing(make_account):
    owner = make_account("owner-list@acme.example.com")
    org = _create_org(owner)
    created = _invite(owner, org["id"], "listed@acme.example.com")
    listed = owner.get(f"/api/v1/orgs/{org['id']}/invitations").json()
    assert len(listed) == 1
    assert "token" not in listed[0]
    assert listed[0]["id"] == created["id"]


def test_invitation_stores_only_token_hash(make_account, engine):
    owner = make_account("owner-hash@acme.example.com")
    org = _create_org(owner)
    created = _invite(owner, org["id"], "hashed@acme.example.com")
    with Session(engine) as db:
        row = db.get(Invitation, created["id"])
        assert row.token_hash != created["token"]
        assert len(row.token_hash) == 64


def test_audit_log_visible_to_admin_not_viewer(make_account):
    owner = make_account("owner-audit@acme.example.com")
    org = _create_org(owner)
    viewer = _add_member(owner, org["id"], make_account, "viewer-audit@acme.example.com", role="viewer")
    assert viewer.get(f"/api/v1/orgs/{org['id']}/audit-events").status_code == 403
    events = owner.get(f"/api/v1/orgs/{org['id']}/audit-events").json()
    actions = {e["action"] for e in events}
    assert {"org.create", "invitation.create", "invitation.accept"} <= actions


def test_audit_metadata_never_contains_tokens(make_account):
    owner = make_account("owner-sec@acme.example.com")
    org = _create_org(owner)
    created = _invite(owner, org["id"], "sec@acme.example.com")
    events = owner.get(f"/api/v1/orgs/{org['id']}/audit-events").json()
    blob = " ".join(str(e) for e in events)
    assert created["token"] not in blob


def test_audit_events_are_tenant_scoped(make_account):
    owner_a = make_account("owner-aa@tenant.example.com")
    owner_b = make_account("owner-bb@tenant.example.com")
    org_a = _create_org(owner_a, "Scope A")
    org_b = _create_org(owner_b, "Scope B")
    assert owner_b.get(f"/api/v1/orgs/{org_a['id']}/audit-events").status_code == 404
    events_b = owner_b.get(f"/api/v1/orgs/{org_b['id']}/audit-events").json()
    assert all(e["action"] for e in events_b)


def test_org_settings_update_is_audited(make_account):
    owner = make_account("owner-upd@acme.example.com")
    org = _create_org(owner)
    r = owner.patch(f"/api/v1/orgs/{org['id']}", json={"name": "Acme Renamed"})
    assert r.status_code == 200
    assert r.json()["name"] == "Acme Renamed"
    actions = [e["action"] for e in owner.get(f"/api/v1/orgs/{org['id']}/audit-events").json()]
    assert "org.update" in actions


def test_invalid_role_value_rejected_by_schema(make_account):
    owner = make_account("owner-schema@acme.example.com")
    org = _create_org(owner)
    r = owner.post(f"/api/v1/orgs/{org['id']}/invitations", json={"email": "s@acme.example.com", "role": "superuser"})
    assert r.status_code == 422


def test_invitation_role_cannot_exceed_inviter(make_account):
    owner = make_account("owner-cap@acme.example.com")
    org = _create_org(owner)
    admin = _add_member(owner, org["id"], make_account, "admin-cap@acme.example.com", role="admin")
    assert _invite_status(admin, org["id"], "cap-owner@acme.example.com", "owner") == 403


def _invite_status(actor, org_id, email, role):
    return actor.post(f"/api/v1/orgs/{org_id}/invitations", json={"email": email, "role": role}).status_code
