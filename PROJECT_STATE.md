# Hermes AI — Project State

Last updated: 2026-11-02

## Current milestone
Phase 1 (Engineering Foundation): backend and a first frontend slice are implemented. The frontend builds and talks to the backend over HTTP. It has not been viewed in a browser.

## What exists
- `backend/`: FastAPI service with server-side sessions, CSRF protection, RBAC, tenant isolation, invitations, and audit logging.
- `backend/migrations/`: Alembic setup with one initial migration (`phase1 identity tenancy audit`).
- `web/`: Next.js 16 app with Tailwind v4 design tokens, a typed API client, and these screens: login, registration, onboarding, invitation acceptance, organization overview, team (members, roles, invitations), and audit log.
- `/api` requests from the browser are proxied by Next.js to the backend (`HERMES_API_URL`, default `http://127.0.0.1:8000`).
- Documentation files at the repository root (this file and siblings).

## What does not exist yet
- Account recovery screen, command palette, motion polish, 3D, light-theme toggle, public marketing site.
- Browser tests (Playwright) and visual review of rendered pages.
- Workflow engine, Temporal, workers, connectors (HubSpot, ERPNext, Gmail, PostgreSQL, REST), AI runtime, approvals UI, analytics, billing.
- PostgreSQL verification, Docker, CI, Playwright, observability wiring.

## Environment notes
- Windows 11, Python 3.14, Node 24, npm 11, Git 2.53.
- Docker and `psql` are not installed. PostgreSQL has not been exercised.
- The backend venv is at `backend/.venv` and is git-ignored.

## Next milestone
Phase 1 completion: Next.js shell and design tokens, then the auth and organization screens wired to these APIs. See `NEXT_ACTIONS.md`.
