"""Email orders: read a mailbox over IMAP and start one run per new email.

How it behaves:
- Connects with IMAP over TLS (port 993) to a public mail server, using an encrypted app password.
- Opens the folder read-only and fetches with BODY.PEEK, so it never marks mail as read or changes it.
- Remembers the highest message UID it has seen. Only newer messages start runs. When a mailbox is first
  connected, the current newest message becomes the starting point, so old mail never floods in.
- Each email starts at most one run: the run's idempotency key comes from the Message-ID.
- An optional allowed-senders list (addresses or domains) ignores everyone else.
- Order details are read from simple "Field: value" lines in the body, for example "Total: 75,000".
  They arrive in the run as email.fields.total and so on. Free-form text needs the AI step, not built yet.
"""

import email
import email.policy
import hashlib
import html
import imaplib
import re
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.config import Settings
from app.crypto import SecretDecryptionError, decrypt_secret
from app.engine import EngineError, start_execution
from app.http_client import OutboundError, ensure_public_host
from app.models import EmailInbox, Workflow, WorkflowVersion, utcnow

IMAP_PORT = 993
MAX_MESSAGES_PER_CHECK = 20
MAX_BODY_CHARS = 20_000
MAX_FIELDS = 50
TIMEOUT_SECONDS = 20

_FIELD_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _-]{0,40}?)\s*[:=]\s*(.+?)\s*$")
_CURRENCY = re.compile(r"^(?:₹|rs\.?|inr|\$|usd|€|eur)\s*", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


class MailboxError(Exception):
    """The mailbox could not be reached or read. The message is safe to show to the user."""


# --------------------------------------------------------------------------- parsing


def _number(value: str) -> int | float | None:
    cleaned = _CURRENCY.sub("", value.strip()).replace(",", "").replace(" ", "")
    if not re.fullmatch(r"-?\d+(\.\d+)?", cleaned):
        return None
    return float(cleaned) if "." in cleaned else int(cleaned)


def parse_order_fields(text: str) -> dict[str, Any]:
    """Read "Field: value" lines. Keys become lower_snake_case, and numbers (with ₹, Rs, commas) become numbers."""
    fields: dict[str, Any] = {}
    for line in text.splitlines():
        match = _FIELD_LINE.match(line)
        if not match:
            continue
        key = re.sub(r"[\s-]+", "_", match.group(1).strip().lower())
        raw = match.group(2).strip()
        if key in fields:
            continue
        number = _number(raw)
        fields[key] = number if number is not None else raw[:500]
        if len(fields) >= MAX_FIELDS:
            break
    return fields


def _plain_text(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    content = part.get_content()
    if part.get_content_type() == "text/html":
        content = html.unescape(_TAGS.sub("\n", content))
    return str(content)[:MAX_BODY_CHARS]


def message_to_payload(raw: bytes) -> dict[str, Any]:
    message = email.message_from_bytes(raw, policy=email.policy.default)
    assert isinstance(message, EmailMessage)
    name, address = parseaddr(str(message.get("From", "")))
    body = _plain_text(message)
    return {
        "from": address.lower(),
        "from_name": name,
        "to": str(message.get("To", "")),
        "subject": str(message.get("Subject", ""))[:500],
        "date": str(message.get("Date", "")),
        "message_id": str(message.get("Message-ID", "")).strip(),
        "body": body,
        "fields": parse_order_fields(body),
    }


def sender_allowed(sender: str, allowed: str) -> bool:
    entries = [entry.strip().lower() for entry in allowed.split(",") if entry.strip()]
    if not entries:
        return True
    sender = sender.lower()
    domain = sender.rsplit("@", 1)[-1] if "@" in sender else ""
    for entry in entries:
        if "@" in entry and not entry.startswith("@"):
            if sender == entry:
                return True
        elif domain and domain == entry.lstrip("@"):
            return True
    return False


# --------------------------------------------------------------------------- reading a mailbox


class Mailbox(Protocol):
    def latest_uid(self) -> tuple[int, int]:
        """Return (uid_validity, highest uid). Used to start from 'now' when a mailbox is connected."""

    def fetch_after(self, last_uid: int, limit: int) -> tuple[int, list[tuple[int, bytes]]]:
        """Return (uid_validity, [(uid, raw message)]) for messages with uid > last_uid, oldest first."""


@dataclass
class ImapMailbox:
    host: str
    port: int
    username: str
    password: str
    folder: str = "INBOX"

    def _connect(self) -> imaplib.IMAP4_SSL:
        try:
            ensure_public_host(self.host)
        except OutboundError as error:
            raise MailboxError(str(error)) from None
        try:
            client = imaplib.IMAP4_SSL(
                self.host, self.port, ssl_context=ssl.create_default_context(), timeout=TIMEOUT_SECONDS
            )
        except (OSError, imaplib.IMAP4.error) as error:
            raise MailboxError(f"Could not connect to {self.host}: {error}") from None
        try:
            client.login(self.username, self.password)
        except imaplib.IMAP4.error:
            client.logout()
            raise MailboxError(
                "The mail server refused the sign-in. For Gmail, use an app password and make sure IMAP is on."
            ) from None
        status, _ = client.select(self._quoted_folder(), readonly=True)
        if status != "OK":
            client.logout()
            raise MailboxError(f"The folder {self.folder} was not found.")
        return client

    def _quoted_folder(self) -> str:
        return '"' + self.folder.replace("\\", "\\\\").replace('"', '\\"') + '"'

    @staticmethod
    def _uid_validity(client: imaplib.IMAP4_SSL) -> int:
        _, data = client.response("UIDVALIDITY")
        try:
            return int(data[0]) if data and data[0] else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _uids(client: imaplib.IMAP4_SSL, criteria: str) -> list[int]:
        status, data = client.uid("search", None, criteria)
        if status != "OK" or not data or not data[0]:
            return []
        return sorted(int(uid) for uid in data[0].split())

    def latest_uid(self) -> tuple[int, int]:
        client = self._connect()
        try:
            uids = self._uids(client, "ALL")
            return self._uid_validity(client), (uids[-1] if uids else 0)
        finally:
            client.logout()

    def fetch_after(self, last_uid: int, limit: int) -> tuple[int, list[tuple[int, bytes]]]:
        client = self._connect()
        try:
            validity = self._uid_validity(client)
            # "N:*" always includes the newest message even when it is older than N, so filter again.
            uids = [uid for uid in self._uids(client, f"UID {last_uid + 1}:*") if uid > last_uid][:limit]
            messages: list[tuple[int, bytes]] = []
            for uid in uids:
                status, data = client.uid("fetch", str(uid), "(BODY.PEEK[])")
                if status != "OK":
                    continue
                raw = next((part[1] for part in data if isinstance(part, tuple)), None)
                if raw:
                    messages.append((uid, raw))
            return validity, messages
        finally:
            client.logout()


def open_mailbox(inbox: EmailInbox, password: str) -> Mailbox:
    """Factory for the mailbox client. Tests replace this to use a fake mailbox."""
    return ImapMailbox(inbox.imap_host, inbox.imap_port, inbox.username, password, inbox.folder)


# --------------------------------------------------------------------------- turning mail into runs


@dataclass
class CheckResult:
    started: int = 0
    ignored: int = 0
    duplicates: int = 0
    error: str | None = None
    run_ids: list[str] = field(default_factory=list)


def _idempotency_key(payload: dict[str, Any], validity: int, uid: int) -> str:
    identity = payload["message_id"] or f"uid:{validity}:{uid}"
    return "email:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def check_inbox(db: Session, inbox: EmailInbox, settings: Settings) -> CheckResult:
    """Read new mail and start runs. Commits as it goes, so one bad message cannot undo the others."""
    result = CheckResult()
    inbox.last_checked_at = utcnow()

    workflow = db.get(Workflow, inbox.workflow_id)
    version = (
        db.scalar(
            select(WorkflowVersion).where(
                WorkflowVersion.id == workflow.active_version_id,
                WorkflowVersion.organization_id == inbox.organization_id,
            )
        )
        if workflow is not None and workflow.archived_at is None and workflow.active_version_id
        else None
    )
    if version is None:
        # Mail is left unread by Hermes and picked up once the workflow is active again.
        result.error = "The workflow is not active, so new email was not read."
        inbox.last_error = result.error
        db.commit()
        return result

    try:
        password = decrypt_secret(settings, inbox.secret_ciphertext)
        mailbox = open_mailbox(inbox, password)
        validity, messages = mailbox.fetch_after(inbox.last_uid, MAX_MESSAGES_PER_CHECK)
        if inbox.uid_validity is not None and validity and validity != inbox.uid_validity:
            # The server renumbered the folder, so old UIDs mean nothing. Starting from zero would turn every
            # old email into an order, so start again from the newest message, as when first connected.
            _, newest = mailbox.latest_uid()
            inbox.uid_validity = validity
            inbox.last_uid = newest
            result.error = "The mail server renumbered this folder. Hermes started again from the newest email."
            inbox.last_error = result.error
            db.commit()
            return result
    except (MailboxError, SecretDecryptionError) as error:
        result.error = str(error) if isinstance(error, MailboxError) else "The mailbox password could not be read."
        inbox.last_error = result.error
        db.commit()
        return result

    if validity:
        inbox.uid_validity = validity

    inbox_id = inbox.id
    for uid, raw in messages:
        payload = message_to_payload(raw)
        if not sender_allowed(payload["from"], inbox.allowed_senders):
            result.ignored += 1
        else:
            try:
                execution = start_execution(
                    db,
                    version=version,
                    organization_id=inbox.organization_id,
                    workflow_id=inbox.workflow_id,
                    payload={"email": payload},
                    started_by_user_id=None,
                    idempotency_key=_idempotency_key(payload, validity, uid),
                    trace_id=None,
                    trigger_type="email",
                )
                record_audit(
                    db,
                    action="email.received",
                    organization_id=inbox.organization_id,
                    target_type="execution",
                    target_id=execution.id,
                    metadata={
                        "from": payload["from"],
                        "subject": payload["subject"][:120],
                        "run_status": execution.status,
                    },
                )
                inbox.runs_started += 1
                db.commit()
                result.started += 1
                result.run_ids.append(execution.id)
            except IntegrityError:
                db.rollback()
                result.duplicates += 1
            except EngineError as error:
                db.rollback()
                result.error = str(error)
            inbox = db.get(EmailInbox, inbox_id)  # reload after a possible rollback
        inbox.last_uid = max(inbox.last_uid, uid)
        db.commit()

    inbox.last_error = result.error
    db.commit()
    return result


def process_due_inboxes(db: Session, settings: Settings, poll_seconds: int) -> int:
    """Check every mailbox not checked in the last poll_seconds. Called from the background loop."""
    from datetime import timedelta

    cutoff = utcnow() - timedelta(seconds=poll_seconds)
    due = db.scalars(
        select(EmailInbox).where((EmailInbox.last_checked_at.is_(None)) | (EmailInbox.last_checked_at <= cutoff))
    ).all()
    for inbox in due:
        check_inbox(db, inbox, settings)
    return len(due)
