# Hermes AI — Next Actions

Resume here in a new session.

Done so far: identity and teams, workflow builder and versioning, execution engine, approvals, overview metrics, audit log, README and demo script, browser tests.

1. Push to GitHub and confirm the CI workflow passes. Fix any Windows versus Linux differences.
2. Rehearse `DEMO.md` end to end on a fresh account.
3. Add the generic REST connector, which can be tested without a vendor account. Include encrypted credential storage, runtime SSRF protection (resolve DNS, block private addresses, limit redirects), timeouts, and retries. Add an idempotency key header for writes.
4. Add webhook triggers: an endpoint per workflow with signature verification, replay protection, and event deduplication, so runs start from real events.
5. Add run retry for failed runs and a reconciliation view for uncertain external writes.
6. Connectors that need accounts from the user: HubSpot and ERPNext sandboxes, a Gmail or SMTP provider. Do not call them verified until a real sandbox test passes.
7. AI agent step with structured output, token limits, a tool allowlist, and prompt injection defenses. Needs an API key.
8. Install Docker or PostgreSQL and run the migrations there. The workflow migration creates a circular foreign key after both tables exist, and the execution tables are new.
9. Replace the poller with Temporal if the team wants durable workflow infrastructure at scale. The step boundaries are already separate from the runner.
10. Account recovery, invitation email, entitlements, rate limiting on Redis, accessibility scan, phone layout for the builder.

Run locally:
- Backend: `cd backend; .venv\Scripts\alembic upgrade head; .venv\Scripts\python -m uvicorn app.main:create_app --factory --reload`
- Web: `cd web; npm run dev`
- Tests: `cd backend; .venv\Scripts\python -m pytest` and `cd web; npm run e2e`
