# Hermes AI — Next Actions

Resume here in a new session.

Done so far: Phase 1 backend and frontend, browser tests, CI workflow, workflow definitions and versioning, and the visual builder.

1. Push to GitHub (create a repository, add the remote) and confirm the CI workflow passes. Fix any Windows versus Linux differences.
2. Install Docker Desktop or PostgreSQL. Run `alembic upgrade head` against it and record the result. The workflow migration creates a circular foreign key after both tables exist, which SQLite accepted. PostgreSQL has not confirmed it.
3. Start the execution engine, which is Phase 3. Decide first whether to run Temporal locally (needs Docker) or build the first slice on a database-backed queue with the same activity boundaries. Record the decision in `DECISIONS.md`.
   - Execution and step records tables, with idempotency keys.
   - A manual trigger endpoint that starts an execution of the active version.
   - A step runner for the node types that need no external system: transform, condition, delay, end.
   - An execution list and detail page that reads real records.
4. Build the approval flow (Phase 6) on top of execution: approval records, a pending list, approve and reject actions with role checks, and continuation that skips rejected paths.
5. Connectors (Phase 4), starting with the generic REST connector, because it can be tested without a vendor account. Encrypted credential storage comes with it. Real HubSpot and ERPNext sandboxes need accounts the user must provide.
6. Remaining UI review: register, invite, onboarding, audit, and workflow library pages. Add an accessibility scan and keyboard-only checks for the builder. The builder is usable at tablet width but not designed for phones.
7. Account recovery and invitation email, which need an email provider decision.
8. Move the rate limiter to Redis before any multi-instance deployment.

Run locally:
- Backend: `cd backend; .venv\Scripts\alembic upgrade head; .venv\Scripts\python -m uvicorn app.main:create_app --factory --reload`
- Web: `cd web; npm run dev`
- Tests: `cd backend; .venv\Scripts\python -m pytest` and `cd web; npm run e2e`
