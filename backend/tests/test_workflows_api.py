"""Workflow API: permissions, tenant isolation, concurrency, immutability, and activation."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import PublishedVersionImmutableError, Workflow, WorkflowVersion
from tests.test_workflow_validation import node, sales_order_graph


def create_org(owner, name="Flow Corp"):
    r = owner.post("/api/v1/orgs", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def add_member(owner, org_id, make_account, email, role):
    acct = make_account(email, full_name=email.split("@")[0].title())
    invitation = owner.post(f"/api/v1/orgs/{org_id}/invitations", json={"email": email, "role": role}).json()
    r = acct.post("/api/v1/invitations/accept", json={"token": invitation["token"]})
    assert r.status_code == 200, r.text
    return acct


def base(org_id):
    return f"/api/v1/orgs/{org_id}/workflows"


def new_workflow(actor, org_id, name="Order processing", definition=None):
    body = {"name": name}
    if definition is not None:
        body["definition"] = definition
    r = actor.post(base(org_id), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def publish_valid(actor, org_id, workflow_id):
    saved = actor.client.put(
        f"{base(org_id)}/{workflow_id}/draft",
        headers=actor.headers(),
        json={"definition": sales_order_graph(), "base_revision": 1},
    )
    assert saved.status_code == 200, saved.text
    revision = saved.json()["version"]["revision"]
    return actor.post(f"{base(org_id)}/{workflow_id}/publish", json={"base_revision": revision})


@pytest.fixture()
def owner(make_account):
    return make_account("flow-owner@example.com", "Flow Owner")


@pytest.fixture()
def org(owner):
    return create_org(owner)


def test_create_starts_with_an_empty_draft(owner, org):
    detail = new_workflow(owner, org["id"])
    assert detail["workflow"]["has_draft"] is True
    assert detail["workflow"]["active_version_number"] is None
    assert detail["draft"]["version_number"] == 1
    assert detail["draft"]["definition"] == {"nodes": [], "edges": []}
    assert any(issue["code"] == "empty_workflow" for issue in detail["issues"])


def test_list_returns_only_this_orgs_workflows(owner, org, make_account):
    new_workflow(owner, org["id"], "Mine")
    other = make_account("other-owner@example.com")
    other_org = create_org(other, "Other Corp")
    new_workflow(other, other_org["id"], "Theirs")
    names = [w["name"] for w in owner.get(base(org["id"])).json()]
    assert names == ["Mine"]


def test_other_tenants_cannot_see_or_touch_a_workflow(owner, org, make_account):
    detail = new_workflow(owner, org["id"])
    wid = detail["workflow"]["id"]
    outsider = make_account("outsider-flow@example.com")
    other_org = create_org(outsider, "Outsider Corp")
    # Direct access to the owning organization is hidden.
    assert outsider.get(f"{base(org['id'])}/{wid}").status_code == 404
    # The same id through the outsider's own organization does not resolve either.
    assert outsider.get(f"{base(other_org['id'])}/{wid}").status_code == 404
    r = outsider.client.put(
        f"{base(other_org['id'])}/{wid}/draft",
        headers=outsider.headers(),
        json={"definition": {"nodes": [], "edges": []}, "base_revision": 1},
    )
    assert r.status_code == 404
    assert outsider.post(f"{base(other_org['id'])}/{wid}/publish", json={"base_revision": 1}).status_code == 404


def test_role_permissions(owner, org, make_account):
    member = add_member(owner, org["id"], make_account, "wf-member@example.com", "member")
    viewer = add_member(owner, org["id"], make_account, "wf-viewer@example.com", "viewer")
    admin = add_member(owner, org["id"], make_account, "wf-admin@example.com", "admin")

    assert viewer.post(base(org["id"]), json={"name": "Nope"}).status_code == 403
    detail = new_workflow(member, org["id"], "Member made")
    wid = detail["workflow"]["id"]
    assert viewer.get(f"{base(org['id'])}/{wid}").status_code == 200

    saved = viewer.client.put(
        f"{base(org['id'])}/{wid}/draft",
        headers=viewer.headers(),
        json={"definition": sales_order_graph(), "base_revision": 1},
    )
    assert saved.status_code == 403

    member.client.put(
        f"{base(org['id'])}/{wid}/draft",
        headers=member.headers(),
        json={"definition": sales_order_graph(), "base_revision": 1},
    )
    # Members edit drafts but cannot publish or activate.
    assert member.post(f"{base(org['id'])}/{wid}/publish", json={"base_revision": 2}).status_code == 403
    assert admin.post(f"{base(org['id'])}/{wid}/publish", json={"base_revision": 2}).status_code == 200
    assert member.post(f"{base(org['id'])}/{wid}/versions/1/activate").status_code == 403
    assert admin.post(f"{base(org['id'])}/{wid}/versions/1/activate").status_code == 200
    assert member.post(f"{base(org['id'])}/{wid}/deactivate").status_code == 403
    assert member.delete(f"{base(org['id'])}/{wid}").status_code == 403


def test_state_changes_require_csrf(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    r = owner.client.put(
        f"{base(org['id'])}/{wid}/draft",
        json={"definition": {"nodes": [], "edges": []}, "base_revision": 1},
    )
    assert r.status_code == 403


def test_save_draft_increments_revision_and_returns_issues(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    r = owner.client.put(
        f"{base(org['id'])}/{wid}/draft",
        headers=owner.headers(),
        json={"definition": {"nodes": [node("t", "trigger", {})], "edges": []}, "base_revision": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["version"]["revision"] == 2
    assert {i["code"] for i in body["issues"]} >= {"missing_config", "missing_end", "dead_end"}


def test_stale_revision_is_a_conflict(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    url = f"{base(org['id'])}/{wid}/draft"
    empty = {"nodes": [], "edges": []}
    assert (
        owner.client.put(url, headers=owner.headers(), json={"definition": empty, "base_revision": 1}).status_code
        == 200
    )
    stale = owner.client.put(url, headers=owner.headers(), json={"definition": empty, "base_revision": 1})
    assert stale.status_code == 409
    missing = owner.client.put(url, headers=owner.headers(), json={"definition": empty})
    assert missing.status_code == 409


def test_malformed_definition_is_rejected(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    bad = {"nodes": [node("a", "shell_command")], "edges": []}
    r = owner.client.put(
        f"{base(org['id'])}/{wid}/draft", headers=owner.headers(), json={"definition": bad, "base_revision": 1}
    )
    assert r.status_code == 422


def test_publish_blocks_invalid_graph_and_leaves_draft_editable(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    r = owner.post(f"{base(org['id'])}/{wid}/publish", json={"base_revision": 1})
    assert r.status_code == 422
    body = r.json()
    assert body["issues"]
    assert "Fix" in body["detail"][0]
    detail = owner.get(f"{base(org['id'])}/{wid}").json()
    assert detail["draft"]["status"] == "draft"
    assert detail["latest_published"] is None
    events = owner.get(f"/api/v1/orgs/{org['id']}/audit-events").json()
    assert any(e["action"] == "workflow.publish" and e["outcome"] == "rejected" for e in events)


def test_publish_requires_the_reviewed_revision(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    owner.client.put(
        f"{base(org['id'])}/{wid}/draft",
        headers=owner.headers(),
        json={"definition": sales_order_graph(), "base_revision": 1},
    )
    stale = owner.post(f"{base(org['id'])}/{wid}/publish", json={"base_revision": 1})
    assert stale.status_code == 409


def test_published_version_is_frozen_and_edits_create_a_new_draft(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    published = publish_valid(owner, org["id"], wid)
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    original = published.json()["definition"]

    edited = sales_order_graph()
    edited["nodes"].append(node("extra", "end"))
    saved = owner.client.put(f"{base(org['id'])}/{wid}/draft", headers=owner.headers(), json={"definition": edited})
    assert saved.status_code == 200
    assert saved.json()["version"]["version_number"] == 2
    assert saved.json()["version"]["revision"] == 1

    v1 = owner.get(f"{base(org['id'])}/{wid}/versions/1").json()
    assert v1["status"] == "published"
    assert v1["definition"] == original
    assert len(owner.get(f"{base(org['id'])}/{wid}").json()["versions"]) == 2


def test_orm_refuses_to_modify_or_delete_a_published_version(owner, org, engine):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    assert publish_valid(owner, org["id"], wid).status_code == 200
    with Session(engine) as db:
        version = db.scalar(select(WorkflowVersion).where(WorkflowVersion.workflow_id == wid))
        version.definition = {"nodes": [], "edges": []}
        with pytest.raises(PublishedVersionImmutableError):
            db.flush()
        db.rollback()
        version = db.scalar(select(WorkflowVersion).where(WorkflowVersion.workflow_id == wid))
        db.delete(version)
        with pytest.raises(PublishedVersionImmutableError):
            db.flush()


def test_database_allows_only_one_draft_per_workflow(owner, org, engine):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    with Session(engine) as db:
        db.add(
            WorkflowVersion(
                workflow_id=wid,
                organization_id=org["id"],
                version_number=2,
                status="draft",
                definition={"nodes": [], "edges": []},
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_activation_rules(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    # A draft cannot be activated.
    assert owner.post(f"{base(org['id'])}/{wid}/versions/1/activate").status_code == 409
    assert publish_valid(owner, org["id"], wid).status_code == 200
    assert owner.post(f"{base(org['id'])}/{wid}/versions/99/activate").status_code == 404
    activated = owner.post(f"{base(org['id'])}/{wid}/versions/1/activate")
    assert activated.status_code == 200
    assert activated.json()["active_version_number"] == 1
    deactivated = owner.post(f"{base(org['id'])}/{wid}/deactivate")
    assert deactivated.json()["active_version_number"] is None


def test_archive_requires_deactivation_and_hides_the_workflow(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    publish_valid(owner, org["id"], wid)
    owner.post(f"{base(org['id'])}/{wid}/versions/1/activate")
    assert owner.delete(f"{base(org['id'])}/{wid}").status_code == 409
    owner.post(f"{base(org['id'])}/{wid}/deactivate")
    assert owner.delete(f"{base(org['id'])}/{wid}").status_code == 204
    assert owner.get(f"{base(org['id'])}/{wid}").status_code == 404
    assert owner.get(base(org["id"])).json() == []


def test_discard_draft_rules(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    # The only version is a draft, so it cannot be discarded.
    assert owner.delete(f"{base(org['id'])}/{wid}/draft").status_code == 409
    publish_valid(owner, org["id"], wid)
    assert owner.delete(f"{base(org['id'])}/{wid}/draft").status_code == 404
    owner.client.put(
        f"{base(org['id'])}/{wid}/draft", headers=owner.headers(), json={"definition": {"nodes": [], "edges": []}}
    )
    assert owner.delete(f"{base(org['id'])}/{wid}/draft").status_code == 204
    detail = owner.get(f"{base(org['id'])}/{wid}").json()
    assert detail["draft"] is None
    assert detail["latest_published"]["version_number"] == 1


def test_validate_endpoint_reports_without_saving(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    r = owner.post(f"{base(org['id'])}/{wid}/validate", json={"nodes": [node("t", "trigger", {})], "edges": []})
    assert r.status_code == 200
    assert any(i["code"] == "missing_config" for i in r.json())
    draft = owner.get(f"{base(org['id'])}/{wid}").json()["draft"]
    assert draft["definition"] == {"nodes": [], "edges": []}
    assert draft["revision"] == 1


def test_rename_and_audit_trail(owner, org):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    r = owner.patch(f"{base(org['id'])}/{wid}", json={"name": "Renamed flow"})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed flow"
    publish_valid(owner, org["id"], wid)
    owner.post(f"{base(org['id'])}/{wid}/versions/1/activate")
    actions = [e["action"] for e in owner.get(f"/api/v1/orgs/{org['id']}/audit-events").json()]
    assert {"workflow.create", "workflow.update", "workflow.publish", "workflow.activate"} <= set(actions)


def test_every_workflow_row_carries_its_organization(owner, org, engine):
    wid = new_workflow(owner, org["id"])["workflow"]["id"]
    publish_valid(owner, org["id"], wid)
    with Session(engine) as db:
        workflow = db.get(Workflow, wid)
        versions = db.scalars(select(WorkflowVersion).where(WorkflowVersion.workflow_id == wid)).all()
        assert workflow.organization_id == org["id"]
        assert versions and all(v.organization_id == org["id"] for v in versions)
