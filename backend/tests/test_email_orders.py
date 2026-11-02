"""Email orders: each new email in a connected mailbox starts one run. The mailbox is faked; messages are real."""

from datetime import timedelta
from email.message import EmailMessage

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import email_inbox as mail
from app import http_client
from app.crypto import decrypt_secret
from app.models import EmailInbox, utcnow
from tests.test_executions import make_active_workflow
from tests.test_workflow_validation import edge, node
from tests.test_workflows_api import add_member, base, create_org


def raw_email(sender: str, body: str, subject: str = "New order", message_id: str | None = None, html: bool = False):
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "orders@acme.example.com"
    message["Subject"] = subject
    if message_id:
        message["Message-ID"] = message_id
    if html:
        message.set_content(body, subtype="html")
    else:
        message.set_content(body)
    return message.as_bytes()


def email_order_graph() -> dict:
    return {
        "nodes": [
            node("t", "trigger", {"event": "email.received"}),
            node("c", "condition", {"field": "email.fields.total", "operator": "gt", "value": 50000}),
            node("a", "approval", {"approver_role": "admin", "title": "Approve emailed order"}),
            node("ok", "end"),
            node("no", "end"),
            node("small", "end"),
        ],
        "edges": [
            edge("1", "t", "c"),
            edge("2", "c", "a", "true"),
            edge("3", "c", "small", "false"),
            edge("4", "a", "ok", "approved"),
            edge("5", "a", "no", "rejected"),
        ],
    }


class FakeMailbox:
    def __init__(self, state):
        self.state = state

    def latest_uid(self):
        if self.state["fail"]:
            raise mail.MailboxError(self.state["fail"])
        return self.state["validity"], max((uid for uid, _ in self.state["messages"]), default=0)

    def fetch_after(self, last_uid, limit):
        if self.state["fail"]:
            raise mail.MailboxError(self.state["fail"])
        self.state["fetches"] += 1
        newer = [(uid, raw) for uid, raw in sorted(self.state["messages"]) if uid > last_uid]
        return self.state["validity"], newer[:limit]


@pytest.fixture()
def mailbox(monkeypatch):
    state = {"messages": [], "validity": 1, "fail": None, "fetches": 0, "passwords": []}

    def factory(inbox, password):
        state["passwords"].append(password)
        return FakeMailbox(state)

    monkeypatch.setattr(mail, "open_mailbox", factory)
    monkeypatch.setattr(http_client, "resolve_host", lambda host: ["142.250.4.108"])
    return state


@pytest.fixture()
def owner(make_account):
    return make_account("mail-owner@example.com", "Mail Owner")


@pytest.fixture()
def org(owner):
    return create_org(owner, "Mail Corp")


@pytest.fixture()
def flow(owner, org):
    return make_active_workflow(owner, org["id"], email_order_graph(), name="Email orders")


def inbox_url(org_id, workflow_id):
    return f"{base(org_id)}/{workflow_id}/email-inbox"


def connect(actor, org_id, workflow_id, **overrides):
    body = {"imap_host": "imap.gmail.com", "username": "orders@acme.example.com", "password": "app-pass-1234"}
    body.update(overrides)
    return actor.client.put(inbox_url(org_id, workflow_id), headers=actor.headers(), json=body)


def check(actor, org_id, workflow_id):
    r = actor.post(f"{inbox_url(org_id, workflow_id)}/check")
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- parsing


def test_order_fields_are_read_from_simple_lines():
    fields = mail.parse_order_fields(
        "Hello team,\n\nCustomer Name: Asha Traders\nTotal: ₹75,000\nQty = 5\nUnit price: Rs. 1,200.50\n"
        "SKU: A-17\nThanks!\nTotal: 1"
    )
    assert fields == {
        "customer_name": "Asha Traders",
        "total": 75000,
        "qty": 5,
        "unit_price": 1200.5,
        "sku": "A-17",
    }


def test_html_only_email_is_read():
    payload = mail.message_to_payload(
        raw_email("Buyer <buyer@shop.example.com>", "<p>Total: 9,999</p><p>Customer: Ravi</p>", html=True)
    )
    assert payload["from"] == "buyer@shop.example.com"
    assert payload["from_name"] == "Buyer"
    assert payload["fields"]["total"] == 9999
    assert payload["fields"]["customer"] == "Ravi"


@pytest.mark.parametrize(
    ("sender", "allowed", "ok"),
    [
        ("a@shop.example.com", "", True),
        ("a@shop.example.com", "shop.example.com", True),
        ("a@shop.example.com", "@shop.example.com", True),
        ("a@shop.example.com", "a@shop.example.com", True),
        ("b@shop.example.com", "a@shop.example.com", False),
        ("a@evil.example.com", "shop.example.com, partner.example.com", False),
        ("a@partner.example.com", "shop.example.com, partner.example.com", True),
    ],
)
def test_allowed_senders(sender, allowed, ok):
    assert mail.sender_allowed(sender, allowed) is ok


# --------------------------------------------------------------------------- connecting


def test_connecting_verifies_the_sign_in_and_skips_old_mail(owner, org, flow, mailbox):
    mailbox["messages"] = [
        (1, raw_email("old@shop.example.com", "Total: 99999", message_id="<old-1@shop>")),
        (2, raw_email("old@shop.example.com", "Total: 99999", message_id="<old-2@shop>")),
    ]
    r = connect(owner, org["id"], flow)
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True
    assert "password" not in r.json()
    result = check(owner, org["id"], flow)
    assert result["started"] == 0  # existing mail is never turned into orders


def test_a_new_order_email_starts_a_run(owner, org, flow, mailbox):
    connect(owner, org["id"], flow)
    mailbox["messages"].append(
        (5, raw_email("Asha <asha@shop.example.com>", "Customer: Asha Traders\nTotal: ₹75,000", message_id="<o1@shop>"))
    )
    result = check(owner, org["id"], flow)
    assert result["started"] == 1
    run = owner.get(f"/api/v1/orgs/{org['id']}/executions/{result['run_ids'][0]}").json()
    assert run["trigger_type"] == "email"
    assert run["status"] == "waiting_approval"
    assert run["trigger_payload"]["email"]["fields"] == {"customer": "Asha Traders", "total": 75000}
    assert run["trigger_payload"]["email"]["from"] == "asha@shop.example.com"

    mailbox["messages"].append((6, raw_email("asha@shop.example.com", "Total: 900", message_id="<o2@shop>")))
    small = check(owner, org["id"], flow)
    run2 = owner.get(f"/api/v1/orgs/{org['id']}/executions/{small['run_ids'][0]}").json()
    assert run2["status"] == "succeeded"

    events = owner.get(f"/api/v1/orgs/{org['id']}/audit-events").json()
    assert sum(1 for e in events if e["action"] == "email.received") == 2


def test_the_same_email_never_starts_two_runs(owner, org, flow, mailbox):
    connect(owner, org["id"], flow)
    mailbox["messages"].append((5, raw_email("a@shop.example.com", "Total: 100", message_id="<same@shop>")))
    assert check(owner, org["id"], flow)["started"] == 1
    # Checking again reads nothing new.
    assert check(owner, org["id"], flow)["started"] == 0
    # The same message delivered again under a new UID (for example copied back into the inbox) is a duplicate.
    mailbox["messages"].append((6, raw_email("a@shop.example.com", "Total: 100", message_id="<same@shop>")))
    second = check(owner, org["id"], flow)
    assert second["started"] == 0
    assert second["duplicates"] == 1


def test_unknown_senders_are_ignored_when_restricted(owner, org, flow, mailbox):
    connect(owner, org["id"], flow, allowed_senders="shop.example.com")
    mailbox["messages"] += [
        (5, raw_email("stranger@evil.example.com", "Total: 999999", message_id="<x@evil>")),
        (6, raw_email("buyer@shop.example.com", "Total: 10", message_id="<y@shop>")),
    ]
    result = check(owner, org["id"], flow)
    assert result["started"] == 1
    assert result["ignored"] == 1


def test_mail_waits_while_the_workflow_is_inactive(owner, org, flow, mailbox):
    connect(owner, org["id"], flow)
    owner.post(f"{base(org['id'])}/{flow}/deactivate")
    mailbox["messages"].append((5, raw_email("a@shop.example.com", "Total: 100", message_id="<wait@shop>")))
    paused = check(owner, org["id"], flow)
    assert paused["started"] == 0
    assert "not active" in paused["error"]
    assert mailbox["fetches"] == 0  # the mailbox was not even read

    owner.post(f"{base(org['id'])}/{flow}/versions/1/activate")
    assert check(owner, org["id"], flow)["started"] == 1


def test_a_refused_sign_in_is_reported_and_nothing_is_saved(owner, org, flow, mailbox, engine):
    mailbox["fail"] = "The mail server refused the sign-in."
    r = connect(owner, org["id"], flow, password="wrong")
    assert r.status_code == 400
    assert "refused the sign-in" in r.json()["detail"]
    with Session(engine) as db:
        assert db.scalar(select(EmailInbox)) is None


def test_mailbox_errors_are_shown_on_later_checks(owner, org, flow, mailbox):
    connect(owner, org["id"], flow)
    mailbox["fail"] = "Could not connect to imap.gmail.com: timed out"
    result = check(owner, org["id"], flow)
    assert result["error"] == "Could not connect to imap.gmail.com: timed out"
    shown = owner.get(inbox_url(org["id"], flow)).json()
    assert shown["last_error"] == result["error"]


def test_the_password_is_encrypted_and_kept_on_update(owner, org, flow, mailbox, engine, settings):
    connect(owner, org["id"], flow, password="app-pass-original")
    with Session(engine) as db:
        stored = db.scalar(select(EmailInbox))
        assert "app-pass-original" not in stored.secret_ciphertext
        assert decrypt_secret(settings, stored.secret_ciphertext) == "app-pass-original"
    # Changing only the allowed senders keeps the stored password.
    r = owner.client.put(
        inbox_url(org["id"], flow),
        headers=owner.headers(),
        json={
            "imap_host": "imap.gmail.com",
            "username": "orders@acme.example.com",
            "allowed_senders": "shop.example.com",
        },
    )
    assert r.status_code == 200, r.text
    assert mailbox["passwords"][-1] == "app-pass-original"
    assert r.json()["allowed_senders"] == "shop.example.com"


def test_private_mail_servers_are_refused(owner, org, flow, mailbox, monkeypatch):
    monkeypatch.setattr(http_client, "resolve_host", lambda host: ["10.0.0.9"])
    r = connect(owner, org["id"], flow, imap_host="mail.internal.example.com")
    assert r.status_code == 422
    assert "private or reserved" in r.json()["detail"]


def test_host_and_field_validation(owner, org, flow, mailbox):
    assert connect(owner, org["id"], flow, imap_host="https://imap.gmail.com").status_code == 422
    assert connect(owner, org["id"], flow, folder="INBOX\r\nA1 DELETE").status_code == 422
    first = owner.client.put(
        inbox_url(org["id"], flow),
        headers=owner.headers(),
        json={"imap_host": "imap.gmail.com", "username": "orders@acme.example.com"},
    )
    assert first.status_code == 422  # a password is required the first time


def test_only_owners_and_admins_manage_mailboxes(owner, org, flow, mailbox, make_account):
    member = add_member(owner, org["id"], make_account, "mail-member@example.com", "member")
    assert connect(member, org["id"], flow).status_code == 403
    assert member.get(inbox_url(org["id"], flow)).status_code == 403
    connect(owner, org["id"], flow)
    assert member.post(f"{inbox_url(org['id'], flow)}/check").status_code == 403

    outsider = make_account("mail-outsider@example.com")
    other = create_org(outsider, "Other Mail Corp")
    assert outsider.get(inbox_url(org["id"], flow)).status_code == 404
    assert connect(outsider, other["id"], flow).status_code == 404


def test_disconnecting_stops_reading(owner, org, flow, mailbox):
    connect(owner, org["id"], flow)
    assert owner.delete(inbox_url(org["id"], flow)).status_code == 204
    assert owner.get(inbox_url(org["id"], flow)).json()["enabled"] is False
    assert owner.post(f"{inbox_url(org['id'], flow)}/check").status_code == 404


def test_background_checks_respect_the_interval(owner, org, flow, mailbox, engine, settings):
    connect(owner, org["id"], flow)
    with Session(engine) as db:
        assert mail.process_due_inboxes(db, settings, poll_seconds=60) == 1  # never checked yet
        assert mail.process_due_inboxes(db, settings, poll_seconds=60) == 0  # just checked
        inbox = db.scalar(select(EmailInbox))
        inbox.last_checked_at = utcnow() - timedelta(seconds=61)
        db.commit()
        assert mail.process_due_inboxes(db, settings, poll_seconds=60) == 1


def test_a_renumbered_folder_restarts_from_the_newest_email(owner, org, flow, mailbox):
    connect(owner, org["id"], flow)
    mailbox["messages"].append((5, raw_email("a@shop.example.com", "Total: 100", message_id="<keep@shop>")))
    assert check(owner, org["id"], flow)["started"] == 1
    # The server renumbers the folder: old mail gets new UIDs under a new UIDVALIDITY.
    mailbox["validity"] = 2
    mailbox["messages"] = [
        (1, raw_email("old@shop.example.com", "Total: 99999", message_id="<ancient@shop>")),
        (2, raw_email("a@shop.example.com", "Total: 100", message_id="<keep@shop>")),
    ]
    renumbered = check(owner, org["id"], flow)
    # Neither old mail nor the already-processed order becomes a run.
    assert renumbered["started"] == 0
    assert "renumbered" in renumbered["error"]
    # Mail that arrives afterwards is read normally.
    mailbox["messages"].append((3, raw_email("new@shop.example.com", "Total: 10", message_id="<fresh@shop>")))
    after = check(owner, org["id"], flow)
    assert after["started"] == 1
    assert after["error"] is None
