"""Inbound webhooks: signatures, replay protection, duplicate events, secret storage, and permissions."""

import json
import time

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.crypto import decrypt_secret
from app.main import create_app
from app.models import WebhookEndpoint, WorkflowExecution
from app.ratelimit import SlidingWindowLimiter
from app.routers.webhooks import EVENT_HEADER, SIGNATURE_HEADER, TIMESTAMP_HEADER, sign
from tests.test_executions import make_active_workflow
from tests.test_workflows_api import add_member, base, create_org

LARGE_ORDER = {"order": {"id": "SO-900", "total": 82000}}


def deliver(client, path, secret, payload, event_id="evt-1", timestamp=None, raw=None):
    body = raw if raw is not None else json.dumps(payload).encode("utf-8")
    ts = str(timestamp if timestamp is not None else int(time.time()))
    headers = {
        TIMESTAMP_HEADER: ts,
        SIGNATURE_HEADER: sign(secret, ts, body),
        EVENT_HEADER: event_id,
        "Content-Type": "application/json",
    }
    return client.post(path, content=body, headers=headers)


@pytest.fixture()
def owner(make_account):
    return make_account("hook-owner@example.com", "Hook Owner")


@pytest.fixture()
def org(owner):
    return create_org(owner, "Hook Corp")


@pytest.fixture()
def hook(owner, org):
    wid = make_active_workflow(owner, org["id"])
    created = owner.post(f"{base(org['id'])}/{wid}/webhook")
    assert created.status_code == 200, created.text
    body = created.json()
    return {"workflow_id": wid, "path": body["path"], "secret": body["secret"]}


def test_creating_a_webhook_returns_the_secret_once(owner, org, hook):
    assert hook["secret"].startswith("whsec_")
    assert hook["path"].startswith("/api/v1/hooks/")
    shown = owner.get(f"{base(org['id'])}/{hook['workflow_id']}/webhook").json()
    assert shown["enabled"] is True
    assert shown["path"] == hook["path"]
    assert "secret" not in shown


def test_a_signed_delivery_starts_a_run(client, owner, org, hook):
    r = deliver(client, hook["path"], hook["secret"], LARGE_ORDER)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "accepted"
    assert body["run_status"] == "waiting_approval"

    run = owner.get(f"/api/v1/orgs/{org['id']}/executions/{body['execution_id']}").json()
    assert run["trigger_type"] == "webhook"
    assert run["trigger_payload"] == LARGE_ORDER

    events = owner.get(f"{base(org['id'])}/{hook['workflow_id']}/webhook/events").json()
    assert events[0]["event_id"] == "evt-1"
    assert events[0]["status"] == "accepted"
    assert events[0]["execution_id"] == body["execution_id"]


def test_a_repeated_event_returns_the_same_run(client, hook, engine):
    first = deliver(client, hook["path"], hook["secret"], LARGE_ORDER, event_id="evt-dup")
    second = deliver(client, hook["path"], hook["secret"], LARGE_ORDER, event_id="evt-dup")
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate", "execution_id": first.json()["execution_id"]}
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(WorkflowExecution)) == 1


def test_a_bad_signature_is_refused_and_audited(client, owner, org, hook, engine):
    r = deliver(client, hook["path"], "whsec_wrong", LARGE_ORDER)
    assert r.status_code == 401
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(WorkflowExecution)) == 0
    events = owner.get(f"/api/v1/orgs/{org['id']}/audit-events").json()
    rejected = [e for e in events if e["action"] == "webhook.rejected"]
    assert rejected and rejected[0]["metadata"]["reason"] == "bad_signature"


def test_a_tampered_body_is_refused(client, hook):
    body = json.dumps(LARGE_ORDER).encode()
    ts = str(int(time.time()))
    headers = {
        TIMESTAMP_HEADER: ts,
        SIGNATURE_HEADER: sign(hook["secret"], ts, body),
        EVENT_HEADER: "evt-tamper",
    }
    tampered = body.replace(b"82000", b"820")
    assert client.post(hook["path"], content=tampered, headers=headers).status_code == 401


def test_old_or_future_timestamps_are_refused(client, hook):
    stale = deliver(client, hook["path"], hook["secret"], LARGE_ORDER, timestamp=int(time.time()) - 400)
    future = deliver(client, hook["path"], hook["secret"], LARGE_ORDER, timestamp=int(time.time()) + 400)
    assert stale.status_code == 401
    assert future.status_code == 401
    # Same message either way, so a caller cannot tell a clock problem from a bad secret.
    assert stale.json() == deliver(client, hook["path"], "whsec_wrong", LARGE_ORDER).json()


def test_missing_or_malformed_headers(client, hook):
    body = json.dumps(LARGE_ORDER).encode()
    ts = str(int(time.time()))
    no_event = client.post(
        hook["path"], content=body, headers={TIMESTAMP_HEADER: ts, SIGNATURE_HEADER: sign(hook["secret"], ts, body)}
    )
    assert no_event.status_code == 400
    bad_sig = client.post(
        hook["path"], content=body, headers={TIMESTAMP_HEADER: ts, SIGNATURE_HEADER: "md5=abc", EVENT_HEADER: "x"}
    )
    assert bad_sig.status_code == 401
    no_headers = client.post(hook["path"], content=body)
    assert no_headers.status_code == 401


def test_unknown_endpoint_is_404(client, hook):
    assert deliver(client, "/api/v1/hooks/does-not-exist", hook["secret"], LARGE_ORDER).status_code == 404


def test_body_must_be_a_json_object_and_bounded(client, hook):
    assert deliver(client, hook["path"], hook["secret"], None, raw=b"not json", event_id="e-a").status_code == 400
    assert deliver(client, hook["path"], hook["secret"], [1, 2], event_id="e-b").status_code == 400
    huge = {"blob": "x" * 60_000}
    assert deliver(client, hook["path"], hook["secret"], huge, event_id="e-c").status_code == 413


def test_rotating_the_secret_invalidates_the_old_one(client, owner, org, hook):
    rotated = owner.post(f"{base(org['id'])}/{hook['workflow_id']}/webhook").json()
    assert rotated["secret"] != hook["secret"]
    assert rotated["path"] == hook["path"]
    assert deliver(client, hook["path"], hook["secret"], LARGE_ORDER, event_id="old").status_code == 401
    assert deliver(client, hook["path"], rotated["secret"], LARGE_ORDER, event_id="new").status_code == 202
    actions = [e["action"] for e in owner.get(f"/api/v1/orgs/{org['id']}/audit-events").json()]
    assert "webhook.create" in actions and "webhook.rotate" in actions


def test_deleting_the_webhook_disables_it(client, owner, org, hook):
    assert owner.delete(f"{base(org['id'])}/{hook['workflow_id']}/webhook").status_code == 204
    assert deliver(client, hook["path"], hook["secret"], LARGE_ORDER).status_code == 404
    assert owner.get(f"{base(org['id'])}/{hook['workflow_id']}/webhook").json()["enabled"] is False


def test_an_event_for_an_inactive_workflow_can_be_retried_later(client, owner, org, hook):
    owner.post(f"{base(org['id'])}/{hook['workflow_id']}/deactivate")
    refused = deliver(client, hook["path"], hook["secret"], LARGE_ORDER, event_id="evt-retry")
    assert refused.status_code == 409
    events = owner.get(f"{base(org['id'])}/{hook['workflow_id']}/webhook/events").json()
    assert events[0]["status"] == "failed"

    owner.post(f"{base(org['id'])}/{hook['workflow_id']}/versions/1/activate")
    retried = deliver(client, hook["path"], hook["secret"], LARGE_ORDER, event_id="evt-retry")
    assert retried.status_code == 202
    events = owner.get(f"{base(org['id'])}/{hook['workflow_id']}/webhook/events").json()
    assert events[0]["status"] == "accepted"
    assert len(events) == 1


def test_the_secret_is_stored_encrypted(hook, engine, settings):
    with Session(engine) as db:
        endpoint = db.scalar(select(WebhookEndpoint))
        assert hook["secret"] not in endpoint.secret_ciphertext
        assert decrypt_secret(settings, endpoint.secret_ciphertext) == hook["secret"]


def test_only_owners_and_admins_manage_webhooks(owner, org, hook, make_account):
    member = add_member(owner, org["id"], make_account, "hook-member@example.com", "member")
    viewer = add_member(owner, org["id"], make_account, "hook-viewer@example.com", "viewer")
    url = f"{base(org['id'])}/{hook['workflow_id']}/webhook"
    for actor in (member, viewer):
        assert actor.get(url).status_code == 403
        assert actor.post(url).status_code == 403
        assert actor.delete(url).status_code == 403
        assert actor.get(f"{url}/events").status_code == 403

    outsider = make_account("hook-outsider@example.com")
    other = create_org(outsider, "Other Hook Corp")
    assert outsider.get(url).status_code == 404
    assert outsider.post(f"{base(other['id'])}/{hook['workflow_id']}/webhook").status_code == 404


def test_management_requires_csrf(owner, org, hook):
    url = f"{base(org['id'])}/{hook['workflow_id']}/webhook"
    assert owner.client.post(url).status_code == 403
    assert owner.client.delete(url).status_code == 403


def test_deliveries_are_rate_limited_per_endpoint(client, app, hook):
    app.state.webhook_limiter = SlidingWindowLimiter(2, 60)
    codes = [
        deliver(client, hook["path"], hook["secret"], {"order": {"total": 1}}, event_id=f"rl-{i}").status_code
        for i in range(3)
    ]
    assert codes[-1] == 429


def test_production_refuses_to_start_without_an_encryption_key(engine):
    settings = Settings(env="production", database_url="sqlite://", credential_encryption_key="")
    with pytest.raises(RuntimeError):
        create_app(settings=settings, engine=engine)
