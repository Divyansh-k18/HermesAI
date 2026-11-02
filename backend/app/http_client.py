"""Outbound HTTP for workflow steps, with protection against server-side request forgery (SSRF).

Rules applied to every request:
- HTTPS only, no credentials in the URL.
- The host name is resolved first, and every address it resolves to must be public. Private, loopback,
  link-local (including cloud metadata at 169.254.169.254), multicast, and reserved ranges are refused.
- Redirects are never followed, so a public server cannot bounce the request to an internal one.
- A 10 second timeout and a 1 MB response cap.
- Automatic retries only for methods that are safe to repeat (GET, PUT, DELETE), on connection errors,
  timeouts, and 5xx responses. POST and PATCH are never retried; callers send an Idempotency-Key header
  so the receiving API can deduplicate a manual retry.

Known limit: the address is checked, then httpx resolves the name again to connect. A DNS server that
changes its answer between the two lookups (DNS rebinding) could slip through. See KNOWN_ISSUES.md.
"""

import ipaddress
import json
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 1_000_000
MAX_TEXT_CHARS = 10_000
RETRYABLE_METHODS = frozenset({"GET", "PUT", "DELETE"})
ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (0.5, 1.5)

# Tests replace these two to avoid real DNS and real network traffic.
_transport: httpx.BaseTransport | None = None
_sleep = time.sleep


class OutboundError(Exception):
    """The request was refused or failed. The message is safe to show in a run trace."""


@dataclass(frozen=True)
class OutboundResponse:
    status: int
    body: Any
    attempts: int
    size: int


def resolve_host(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def check_destination(url: str) -> str:
    """Return the host if the URL may be called, otherwise raise OutboundError."""
    try:
        parsed = urlparse(url)
    except ValueError:
        raise OutboundError("The URL is not valid.") from None
    if parsed.scheme != "https":
        raise OutboundError("Only https URLs are allowed.")
    host = parsed.hostname
    if not host:
        raise OutboundError("The URL needs a host name.")
    if parsed.username or parsed.password:
        raise OutboundError("Do not put credentials in the URL. Use a connection instead.")
    ensure_public_host(host)
    return host


def ensure_public_host(host: str) -> None:
    """Refuse a host unless every address it resolves to is public. Shared by HTTP steps and mailboxes."""
    try:
        addresses = resolve_host(host)
    except (OSError, UnicodeError):
        raise OutboundError(f"Could not resolve {host}.") from None
    if not addresses:
        raise OutboundError(f"Could not resolve {host}.")
    for address in addresses:
        if not ipaddress.ip_address(address.split("%")[0]).is_global:
            raise OutboundError(f"{host} resolves to a private or reserved address, so the request was blocked.")


def _decode(raw: bytes, content_type: str) -> Any:
    text = raw.decode("utf-8", errors="replace")
    if "json" in content_type.lower():
        try:
            return json.loads(text)
        except ValueError:
            pass
    return text[:MAX_TEXT_CHARS]


def send(method: str, url: str, headers: dict[str, str], json_body: Any = None) -> OutboundResponse:
    method = method.upper()
    if method not in ALLOWED_METHODS:
        raise OutboundError(f"The HTTP method {method} is not allowed.")
    host = check_destination(url)
    retryable = method in RETRYABLE_METHODS
    last_error = "The request failed."

    with httpx.Client(transport=_transport, timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                with client.stream(method, url, headers=headers, json=json_body) as response:
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise OutboundError(f"The response from {host} was larger than 1 MB.")
                        chunks.append(chunk)
                    status = response.status_code
                    content_type = response.headers.get("content-type", "")
            except httpx.TimeoutException:
                last_error = f"{method} {host} timed out after {TIMEOUT_SECONDS:.0f} seconds."
            except httpx.TransportError:
                last_error = f"Could not connect to {host}."
            else:
                raw = b"".join(chunks)
                if status >= 500 and retryable and attempt < MAX_ATTEMPTS:
                    last_error = f"{method} {host} returned HTTP {status}."
                elif 300 <= status < 400:
                    raise OutboundError(
                        f"{method} {host} returned a redirect (HTTP {status}). Redirects are not followed."
                    )
                elif status >= 400:
                    raise OutboundError(f"{method} {host} returned HTTP {status}.")
                else:
                    return OutboundResponse(
                        status=status, body=_decode(raw, content_type), attempts=attempt, size=len(raw)
                    )

            if not retryable or attempt == MAX_ATTEMPTS:
                break
            _sleep(BACKOFF_SECONDS[attempt - 1])

    raise OutboundError(last_error)
