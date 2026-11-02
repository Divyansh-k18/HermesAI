"""HTTP step and connections. The network and DNS are faked, so nothing leaves the machine."""

import json

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import http_client
from app.crypto import decrypt_secret
from app.models import Connection
from tests.test_executions import make_active_workflow, run
from tests.test_workflow_validation import edge, node
from tests.test_workflows_api import add_member, base, create_org

PUBLIC_IP = "93.184.216.34"


@pytest.fixture()
def owner(make_account):
    return make_account("http-owner@example.com", "Http Owner")


@pytest.fixture()
def org(owner):
    return create_org(owner, "Http Corp")


@pytest.fixture()
def network(monkeypatch):
    """Fake DNS and a scripted HTTP server. Tests append responses and read the recorded requests."""
    state = {"responses": [], "requests": [], "addresses": [PUBLIC_IP], "sleeps": []}

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        if not state["responses"]:
            return httpx.Response(200, json={"ok": True})
        return state["responses"].pop(0)

    monkeypatch.setattr(http_client, "resolve_host", lambda host: list(state["addresses"]))
    monkeypatch.setattr(http_client, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(http_client, "_sleep", lambda seconds: state["sleeps"].append(seconds))
    return state


def http_graph(config: dict) -> dict:
    return {
        "nodes": [node("t", "trigger", {"event": "manual"}), node("h", "http", config), node("e", "end")],
        "edges": [edge("1", "t", "h"), edge("2", "h", "e")],
    }


def connections_url(org_id: str) -> str:
    return f"/api/v1/orgs/{org_id}/connections"


def add_connection(actor, org_id, name="Inventory API", header="X-Api-Key", secret="sk_live_123"):
    r = actor.post(connections_url(org_id), json={"name": name, "header_name": header, "secret": secret})
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- the HTTP step


def test_get_stores_the_response_and_sends_the_connection_header(owner, org, network):
    conn = add_connection(owner, org["id"])
    network["responses"].append(httpx.Response(200, json={"sku": "A-1", "in_stock": 12}))
    wid = make_active_workflow(
        owner,
        org["id"],
        http_graph(
            {
                "method": "GET",
                "url": "https://api.example.com/stock?sku=A-1",
                "connection_id": conn["id"],
                "result_path": "stock",
            }
        ),
        name="Stock check",
    )
    body = run(owner, org["id"], wid, {"order": {"sku": "A-1"}}).json()

    assert body["status"] == "succeeded", body
    assert body["variables"]["stock"] == {"status": 200, "body": {"sku": "A-1", "in_stock": 12}}
    sent = network["requests"][0]
    assert sent.headers["x-api-key"] == "sk_live_123"
    assert "idempotency-key" not in sent.headers
    step = body["steps"][1]
    assert step["output"]["connection"] == "Inventory API"
    assert step["output"]["host"] == "api.example.com"
    assert step["output"]["attempts"] == 1
    # The credential never appears anywhere in the run record.
    assert "sk_live_123" not in json.dumps(body)


def test_post_sends_the_body_with_an_idempotency_key_and_is_never_retried(owner, org, network):
    network["responses"].extend([httpx.Response(500), httpx.Response(200)])
    wid = make_active_workflow(
        owner,
        org["id"],
        http_graph({"method": "POST", "url": "https://erp.example.com/orders", "body_path": "order"}),
        name="Create order",
    )
    body = run(owner, org["id"], wid, {"order": {"id": "SO-7", "total": 10}}).json()

    assert body["status"] == "failed"
    assert "returned HTTP 500" in body["error"]
    assert len(network["requests"]) == 1
    sent = network["requests"][0]
    assert json.loads(sent.content) == {"id": "SO-7", "total": 10}
    assert sent.headers["idempotency-key"] == f"{body['id']}:h"


def test_get_is_retried_after_server_errors(owner, org, network):
    network["responses"].extend([httpx.Response(503), httpx.Response(502), httpx.Response(200, json={"n": 1})])
    wid = make_active_workflow(
        owner, org["id"], http_graph({"method": "GET", "url": "https://api.example.com/x"}), name="Flaky"
    )
    body = run(owner, org["id"], wid, {}).json()
    assert body["status"] == "succeeded"
    assert body["steps"][1]["output"]["attempts"] == 3
    assert network["sleeps"] == [0.5, 1.5]
    assert body["variables"]["http_response"]["body"] == {"n": 1}


def test_get_gives_up_after_three_attempts(owner, org, network):
    network["responses"].extend([httpx.Response(503)] * 3)
    wid = make_active_workflow(
        owner, org["id"], http_graph({"method": "GET", "url": "https://api.example.com/x"}), name="Down"
    )
    body = run(owner, org["id"], wid, {}).json()
    assert body["status"] == "failed"
    assert len(network["requests"]) == 3


@pytest.mark.parametrize(
    "address", ["10.0.0.7", "127.0.0.1", "169.254.169.254", "192.168.1.20", "::1", "fd00::1", "0.0.0.0"]
)
def test_private_and_reserved_destinations_are_blocked(owner, org, network, address):
    network["addresses"] = [address]
    wid = make_active_workflow(
        owner, org["id"], http_graph({"method": "GET", "url": "https://looks-public.example.com/"}), name="Sneaky"
    )
    body = run(owner, org["id"], wid, {}).json()
    assert body["status"] == "failed"
    assert "private or reserved" in body["error"]
    assert network["requests"] == []


def test_a_name_with_any_private_address_is_blocked(owner, org, network):
    network["addresses"] = [PUBLIC_IP, "10.1.2.3"]
    wid = make_active_workflow(
        owner, org["id"], http_graph({"method": "GET", "url": "https://mixed.example.com/"}), name="Mixed"
    )
    assert run(owner, org["id"], wid, {}).json()["status"] == "failed"
    assert network["requests"] == []


def test_redirects_are_not_followed(owner, org, network):
    network["responses"].append(httpx.Response(302, headers={"Location": "https://169.254.169.254/latest"}))
    wid = make_active_workflow(
        owner, org["id"], http_graph({"method": "GET", "url": "https://api.example.com/go"}), name="Redirect"
    )
    body = run(owner, org["id"], wid, {}).json()
    assert body["status"] == "failed"
    assert "Redirects are not followed" in body["error"]
    assert len(network["requests"]) == 1


def test_client_errors_fail_the_run(owner, org, network):
    network["responses"].append(httpx.Response(404))
    wid = make_active_workflow(
        owner, org["id"], http_graph({"method": "GET", "url": "https://api.example.com/missing"}), name="404"
    )
    body = run(owner, org["id"], wid, {}).json()
    assert body["status"] == "failed"
    assert "returned HTTP 404" in body["error"]


def test_oversized_responses_are_refused(owner, org, network):
    network["responses"].append(httpx.Response(200, content=b"x" * 1_200_000))
    wid = make_active_workflow(
        owner, org["id"], http_graph({"method": "GET", "url": "https://api.example.com/big"}), name="Big"
    )
    body = run(owner, org["id"], wid, {}).json()
    assert body["status"] == "failed"
    assert "larger than 1 MB" in body["error"]


def test_missing_body_field_fails_before_any_request(owner, org, network):
    wid = make_active_workflow(
        owner,
        org["id"],
        http_graph({"method": "POST", "url": "https://api.example.com/x", "body_path": "order"}),
        name="No body",
    )
    body = run(owner, org["id"], wid, {}).json()
    assert body["status"] == "failed"
    assert network["requests"] == []


def test_a_connection_from_another_organization_cannot_be_used(owner, org, network, make_account):
    outsider = make_account("http-outsider@example.com")
    other = create_org(outsider, "Other Http Corp")
    foreign = add_connection(outsider, other["id"], secret="sk_other_org")
    wid = make_active_workflow(
        owner,
        org["id"],
        http_graph({"method": "GET", "url": "https://api.example.com/x", "connection_id": foreign["id"]}),
        name="Borrowed",
    )
    body = run(owner, org["id"], wid, {}).json()
    assert body["status"] == "failed"
    assert "connection for this step was not found" in body["error"]
    assert network["requests"] == []


def test_invalid_data_paths_block_publishing(owner, org):
    created = owner.post(base(org["id"]), json={"name": "Bad path"}).json()
    wid = created["workflow"]["id"]
    saved = owner.client.put(
        f"{base(org['id'])}/{wid}/draft",
        headers=owner.headers(),
        json={
            "definition": http_graph(
                {"method": "GET", "url": "https://api.example.com/x", "result_path": "not a path!"}
            ),
            "base_revision": 1,
        },
    ).json()
    assert any(i["code"] == "invalid_config" and i["node_id"] == "h" for i in saved["issues"])


# --------------------------------------------------------------------------- connections API


def test_connection_secrets_are_encrypted_and_never_returned(owner, org, engine, settings):
    created = add_connection(owner, org["id"], secret="sk_live_secret_value")
    assert "secret" not in created
    listed = owner.get(connections_url(org["id"])).json()
    assert [c["name"] for c in listed] == ["Inventory API"]
    assert "sk_live_secret_value" not in json.dumps(listed)
    with Session(engine) as db:
        row = db.scalar(select(Connection))
        assert "sk_live_secret_value" not in row.secret_ciphertext
        assert decrypt_secret(settings, row.secret_ciphertext) == "sk_live_secret_value"


def test_connection_validation(owner, org):
    add_connection(owner, org["id"])
    duplicate = owner.post(connections_url(org["id"]), json={"name": "Inventory API", "secret": "x"})
    assert duplicate.status_code == 409
    for header in ("Host", "bad header", "Content-Length", "Idempotency-Key"):
        r = owner.post(connections_url(org["id"]), json={"name": f"n-{header}", "header_name": header, "secret": "x"})
        assert r.status_code == 422, header
    multi = owner.post(connections_url(org["id"]), json={"name": "multi", "secret": "a\nInjected: yes"})
    assert multi.status_code == 422


def test_connection_permissions_and_isolation(owner, org, make_account):
    member = add_member(owner, org["id"], make_account, "http-member@example.com", "member")
    viewer = add_member(owner, org["id"], make_account, "http-viewer@example.com", "viewer")
    conn = add_connection(owner, org["id"])
    # Everyone can see names to pick a connection; only owners and admins can change them.
    assert len(member.get(connections_url(org["id"])).json()) == 1
    assert len(viewer.get(connections_url(org["id"])).json()) == 1
    for actor in (member, viewer):
        assert actor.post(connections_url(org["id"]), json={"name": "x", "secret": "y"}).status_code == 403
        assert actor.delete(f"{connections_url(org['id'])}/{conn['id']}").status_code == 403

    outsider = make_account("http-outsider2@example.com")
    other = create_org(outsider, "Other Http Corp 2")
    assert outsider.get(connections_url(org["id"])).status_code == 404
    assert outsider.delete(f"{connections_url(other['id'])}/{conn['id']}").status_code == 404


def test_deleting_a_connection_is_audited(owner, org):
    conn = add_connection(owner, org["id"])
    assert owner.client.delete(f"{connections_url(org['id'])}/{conn['id']}").status_code == 403  # CSRF
    assert owner.delete(f"{connections_url(org['id'])}/{conn['id']}").status_code == 204
    assert owner.delete(f"{connections_url(org['id'])}/{conn['id']}").status_code == 404
    actions = [e["action"] for e in owner.get(f"/api/v1/orgs/{org['id']}/audit-events").json()]
    assert "connection.create" in actions and "connection.delete" in actions
