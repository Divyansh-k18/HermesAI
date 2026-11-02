# Hermes AI — Project State

Last updated: 2026-11-02

## Current milestone
Phase 1 is functionally complete for identity, organizations, and audit. Phase 2 is partly done: workflow definitions, versioning, validation, and the visual builder work end to end. Execution history is not started because nothing executes yet.

## What exists
- `backend/`: FastAPI service. Server-side sessions, CSRF, RBAC, tenant isolation, invitations, audit log, and workflow APIs.
- Workflow model: a workflow has versions. Drafts are editable and published versions are frozen in both the API and the ORM. A version can be marked active.
- Validation: structural rules (one trigger, reachable nodes, no cycles, required branches for conditions and approvals) and per-node configuration rules. HTTP node URLs are checked structurally.
- `backend/migrations/`: two Alembic migrations. Both apply, downgrade, and reapply on SQLite.
- `web/`: Next.js 16 app. Auth, onboarding, invitations, overview, team, audit log, workflow library, and the workflow builder (React Flow).
- Builder features: palette with click and drag to add, drag to connect, branch outputs, node inspector, undo and redo, auto layout, live server validation, save with conflict detection, publish, activate, deactivate, version list, and read-only mode for viewers.
- `.github/workflows/ci.yml`: backend, web, and browser jobs. Not yet run on GitHub.
- Documentation files at the repository root.

## What does not exist yet
- Any execution. No Temporal, workers, triggers, retries, or execution records. "Active" only marks a version.
- Integrations (HubSpot, ERPNext, Gmail, PostgreSQL, REST), the AI runtime, approvals, notifications, analytics, billing and entitlements.
- Natural language workflow creation.
- Account recovery, invitation emails, command palette, 3D, public marketing site, light-theme toggle.
- PostgreSQL verification. Docker and `psql` are not installed on this machine.

## Environment notes
- Windows 11, Python 3.14, Node 24. The backend venv is at `backend/.venv`.
- The repository lives inside OneDrive. If `next build` fails with EPERM on `.next`, delete `web/.next` and rebuild.
- Git history: Phase 1 backend, frontend, e2e tests, CI, workflow backend, then the workflow builder.

## Next milestone
Execution engine foundation. See `NEXT_ACTIONS.md`.
