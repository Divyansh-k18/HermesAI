"""Send a signed webhook to Hermes, the way an external system such as a CRM would.

Usage:
    python scripts/send_webhook.py URL SECRET [JSON] [--event-id ID]

Example (the JSON defaults to an order of 75,000 when omitted):
    python scripts/send_webhook.py http://127.0.0.1:3000/api/v1/hooks/abc whsec_xyz

Signature: HMAC-SHA256 over "<unix timestamp>.<raw body>" with the secret, sent as
X-Hermes-Signature: sha256=<hex>, with X-Hermes-Timestamp and a unique X-Hermes-Event-Id.
Uses only the Python standard library.
"""

import argparse
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request
import uuid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("secret")
    parser.add_argument("payload", nargs="?", default='{"order": {"id": "SO-1001", "total": 75000}}')
    parser.add_argument("--event-id", default=None, help="Reuse an id to test duplicate delivery.")
    args = parser.parse_args()

    if not args.url.startswith(("http://", "https://")):
        parser.error("URL must start with http:// or https://")

    payload = json.loads(args.payload)
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(args.secret.encode("utf-8"), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    event_id = args.event_id or f"evt-{uuid.uuid4().hex[:12]}"

    request = urllib.request.Request(  # noqa: S310 - scheme restricted to http and https above
        args.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Hermes-Timestamp": timestamp,
            "X-Hermes-Signature": f"sha256={signature}",
            "X-Hermes-Event-Id": event_id,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - URL comes from the operator
            print(response.status, response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        print(error.code, error.read().decode("utf-8"))
        return 1
    print(f"event id: {event_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
