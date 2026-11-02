# Hermes AI — Project State

Last updated: 2026-11-02

## Current milestone
Phase 1 (Engineering Foundation), backend slice only. Identity, organizations, memberships, invitations, and audit are implemented and tested.

## What exists
- `backend/`: FastAPI service with server-side sessions, CSRF protection, RBAC, tenant isolation, invitations, and audit logging.
- `backend/migrations/`: Alembic setup with one initial migration (`phase1 identity tenancy audit`).
- Documentation files at the repository root (this file and siblings).

## What does not exist yet
- Frontend (Next.js, design system, any page). Not started.
- Workflow engine, Temporal, workers, connectors (HubSpot, ERPNext, Gmail, PostgreSQL, REST), AI runtime, approvals UI, analytics, billing.
- PostgreSQL verification, Docker, CI, Playwright, observability wiring.

## Environment notes
- Windows 11, Python 3.14, Node 24, npm 11, Git 2.53.
- Docker and `psql` are not installed. PostgreSQL has not been exercised.
- The backend venv is at `backend/.venv` and is git-ignored.

## Next milestone
Phase 1 completion: Next.js shell and design tokens, then the auth and organization screens wired to these APIs. See `NEXT_ACTIONS.md`.
