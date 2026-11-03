"""Inventory and the Check stock step."""

import pytest

from app import email_inbox as mail
from app import http_client
from app.inventory import best_match
from app.models import InventoryItem
from tests.test_email_orders import FakeMailbox, raw_email
from tests.test_executions import make_active_workflow, run
from tests.test_workflow_validation import edge, node
from tests.test_workflows_api import add_member, base, create_org


@pytest.fixture()
def owner(make_account):
    return make_account("stock-owner@example.com", "Stock Owner")


@pytest.fixture()
def org(owner):
    return create_org(owner, "Stock Corp")


def inv(org_id: str) -> str:
    return f"/api/v1/orgs/{org_id}/inventory"


def add_item(owner, org_id, name, quantity, **extra):
    r = owner.post(inv(org_id), json={"name": name, "quantity": quantity, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def stock_graph() -> dict:
    return {
        "nodes": [
            node("t", "trigger", {"event": "manual"}),
            node("s", "inventory", {"items_path": "order.items", "result_path": "stock"}),
            node("c", "condition", {"field": "stock.status", "operator": "eq", "value": "in_stock"}),
            node("yes", "end"),
            node("no", "end"),
        ],
        "edges": [
            edge("1", "t", "s"),
            edge("2", "s", "c"),
            edge("3", "c", "yes", "true"),
            edge("4", "c", "no", "false"),
        ],
    }


# --------------------------------------------------------------------------- managing stock


def test_admins_manage_stock_and_members_can_only_read(owner, org, make_account):
    item = add_item(owner, org["id"], "A4 Paper", 200, unit="box", unit_price=1500)
    assert item["quantity"] == 200 and item["unit"] == "box"
    assert owner.post(inv(org["id"]), json={"name": "A4 Paper", "quantity": 1}).status_code == 409

    updated = owner.patch(f"{inv(org['id'])}/{item['id']}", json={"quantity": 150})
    assert updated.status_code == 200 and updated.json()["quantity"] == 150
    assert owner.patch(f"{inv(org['id'])}/{item['id']}", json={"quantity": -1}).status_code == 422

    member = add_member(owner, org["id"], make_account, "stock-member@example.com", "member")
    assert [i["name"] for i in member.get(inv(org["id"])).json()] == ["A4 Paper"]
    assert member.post(inv(org["id"]), json={"name": "Pens", "quantity": 1}).status_code == 403

    assert owner.delete(f"{inv(org['id'])}/{item['id']}").status_code == 204
    assert owner.get(inv(org["id"])).json() == []


def test_stock_is_private_to_each_organization(owner, org, make_account):
    item = add_item(owner, org["id"], "A4 Paper", 10)
    outsider = make_account("stock-outsider@example.com")
    other = create_org(outsider, "Other Corp")
    assert outsider.get(inv(other["id"])).json() == []
    assert outsider.get(inv(org["id"])).status_code == 404
    assert outsider.patch(f"{inv(other['id'])}/{item['id']}", json={"quantity": 0}).status_code == 404


# --------------------------------------------------------------------------- matching


@pytest.mark.parametrize(
    ("wanted", "expected"),
    [
        ("A4 paper (box)", "A4 Paper"),
        ("50 boxes of A4 paper", "A4 Paper"),
        ("blue pens", "Blue Pen"),
        ("Blue Pen", "Blue Pen"),
        ("stapler", None),
        ("", None),
    ],
)
def test_order_lines_match_stock_by_their_words(wanted, expected):
    items = [InventoryItem(name="A4 Paper"), InventoryItem(name="Blue Pen"), InventoryItem(name="Red Marker")]
    match = best_match(wanted, items)
    assert (match.name if match else None) == expected


# --------------------------------------------------------------------------- the Check stock step


def test_an_order_in_stock_takes_the_in_stock_path(owner, org):
    add_item(owner, org["id"], "A4 Paper", 200)
    add_item(owner, org["id"], "Blue Pen", 100)
    wid = make_active_workflow(owner, org["id"], stock_graph())
    order = {"items": [{"name": "A4 paper (box)", "quantity": 50}, {"name": "blue pens", "quantity": 20}]}
    body = run(owner, org["id"], wid, {"order": order}).json()
    assert body["status"] == "succeeded"
    stock = body["variables"]["stock"]
    assert stock["status"] == "in_stock" and stock["all_available"] is True
    assert [(line["matched"], line["available"], line["status"]) for line in stock["lines"]] == [
        ("A4 Paper", 200, "available"),
        ("Blue Pen", 100, "available"),
    ]
    assert body["steps"][-1]["node_id"] == "yes"


@pytest.mark.parametrize(
    ("items", "status", "problem"),
    [
        ([{"name": "A4 paper", "quantity": 500}], "short", "A4 paper: short"),
        ([{"name": "Stapler", "quantity": 1}], "short", "Stapler: not stocked"),
        ([{"name": "A4 paper", "quantity": None}], "needs_check", "A4 paper: quantity unknown"),
        ([], "needs_check", None),
    ],
)
def test_short_unknown_or_unclear_orders_never_count_as_in_stock(owner, org, items, status, problem):
    add_item(owner, org["id"], "A4 Paper", 200)
    wid = make_active_workflow(owner, org["id"], stock_graph())
    body = run(owner, org["id"], wid, {"order": {"items": items}}).json()
    stock = body["variables"]["stock"]
    assert stock["status"] == status and stock["all_available"] is False
    assert body["steps"][-1]["node_id"] == "no"
    if problem:
        assert problem in stock["problems"]


def test_a_missing_order_list_fails_the_step(owner, org):
    wid = make_active_workflow(owner, org["id"], stock_graph())
    body = run(owner, org["id"], wid, {"order": {"total": 5}}).json()
    assert body["status"] == "failed"
    assert "no list of order lines at order.items" in body["error"]


def test_stock_step_paths_are_validated():
    from app.workflow_schema import Definition
    from app.workflow_validation import validate_definition

    graph = stock_graph()
    graph["nodes"][1]["config"] = {"items_path": "../etc", "result_path": "stock"}
    codes = {i.code for i in validate_definition(Definition.model_validate(graph)) if i.node_id == "s"}
    assert codes == {"invalid_config"}


# --------------------------------------------------------------------------- emails show up in the builder


def test_the_mailbox_panel_lists_emails_that_started_runs(owner, org, monkeypatch):
    state = {"messages": [], "validity": 1, "fail": None, "fetches": 0, "passwords": []}
    monkeypatch.setattr(mail, "open_mailbox", lambda inbox, password: FakeMailbox(state))
    monkeypatch.setattr(http_client, "resolve_host", lambda host: ["142.250.4.108"])
    graph = {
        "nodes": [node("t", "trigger", {"event": "email.received"}), node("e", "end")],
        "edges": [edge("1", "t", "e")],
    }
    wid = make_active_workflow(owner, org["id"], graph)
    url = f"{base(org['id'])}/{wid}/email-inbox"
    assert owner.get(url).json()["recent_emails"] == []
    owner.client.put(
        url,
        headers=owner.headers(),
        json={"imap_host": "imap.gmail.com", "username": "orders@acme.example.com", "password": "app-pass"},
    )
    state["messages"].append((5, raw_email("Asha <asha@traders.example.com>", "Order please", message_id="<r1@t>")))
    assert owner.post(f"{url}/check").json()["started"] == 1
    recent = owner.get(url).json()["recent_emails"]
    assert len(recent) == 1
    assert recent[0]["sender"] == "asha@traders.example.com"
    assert recent[0]["status"] == "succeeded"
