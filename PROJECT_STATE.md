# Hermes AI — Project State

Last updated: 2026-11-02

## Current milestone
A working vertical slice: accounts and teams, a visual workflow builder with versioning, an execution engine, human approvals with durable waiting, an operations overview, and an audit log. The slice is demo-ready for a hackathon presentation. It is not a finished product.

## What exists
- `backend/`: FastAPI service. Server-side sessions, CSRF, RBAC, tenant isolation, invitations, audit log, workflow APIs, execution engine, approvals, and metrics.
- Execution engine (`backend/app/engine.py`): database-backed and restart-safe. Runs trigger, condition, transform, delay, approval, and end steps. Records every step with input, output, and error. Idempotency keys. Runs are pinned to the version they started on.
- Approvals: a run pauses at an approval step. Only the role the workflow names can decide. A decision applies once. A rejected run can never finish as succeeded. Members can run workflows but cannot see or decide approvals.
- Delays resume through a poller that reads the database, so a restart loses nothing.
- Webhook triggers (`backend/app/routers/webhooks.py`): HMAC-SHA256 signed requests, a five-minute replay window, idempotent event ids, encrypted signing secrets (`backend/app/crypto.py`), rotation, delivery history, and a per-endpoint rate limit. `backend/scripts/send_webhook.py` sends signed test events.
- HTTP step (`backend/app/http_client.py`) and connections (`backend/app/routers/connections.py`): outbound HTTPS calls with SSRF checks, encrypted credential headers, safe retries, and an Integrations page.
- `backend/migrations/`: five Alembic migrations. They apply, downgrade, and reapply on SQLite.
- `web/`: Next.js 16 app. Auth, onboarding, invitations, overview with real metrics and a seven-day chart, workflow library with a one-click sample, the builder, a runs list, a run detail page with a step trace, an approvals page, team, and an audit log with actor names.
- `README.md` and `DEMO.md`: honest scope and a four-minute demo script.
- `.github/workflows/ci.yml`: backend, web, and browser jobs. Never run on GitHub.

## What does not exist
- External integrations. HubSpot, ERPNext, Gmail, PostgreSQL, and HTTP steps fail with "not available yet".
- AI steps and natural-language workflow creation.
- Temporal. The engine is in-process.
- Vendor-specific webhook verification (for example HubSpot's signature format) and scheduled triggers.
- Billing, usage limits, account recovery, invitation email, command palette, 3D, marketing site.
- PostgreSQL verification and any security review.

## Environment notes
- Windows 11, Python 3.14, Node 24. Backend venv at `backend/.venv`.
- Browser tests use ports 8100 and 3100. Dev servers use 8000 and 3000.
- The repository lives in OneDrive. If `next build` fails with EPERM on `.next`, delete `web/.next`.
- Do not rewrite source files with PowerShell Get-Content and Set-Content. It corrupts non-ASCII characters.

## Next milestone
A real integration. See `NEXT_ACTIONS.md`.
