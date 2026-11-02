# Hermes AI — Test Results

Date: 2026-11-02. Environment: Windows 11, Python 3.14 venv at `backend/.venv`.

## Automated tests
Command: `python -m pytest -o addopts="" -W ignore::DeprecationWarning -q` from `backend/`

Result: **43 passed**.

Coverage areas:
- Registration, login, logout, session expiry and revocation, session token storage, cookie flags.
- Password policy and login rate limiting.
- CSRF rejection on state changes.
- Tenant isolation: non-member and missing organizations return identical 404s. Cross-tenant member changes are blocked. Audit visibility is tenant-scoped.
- RBAC: member and viewer restrictions, admin escalation limits, owner protection, last-owner protection.
- Invitations: email matching, single use, expiry, revocation, demoted-inviter invalidation, duplicate prevention, token hashing, token absence from listings.
- Audit: events created for key actions, credential-like metadata redacted, security headers, readiness check.

## Lint
Command: `ruff check app tests migrations`

Result: **All checks passed** after formatting.

## Database migration
- `alembic revision --autogenerate` produced an initial migration covering seven tables.
- `alembic upgrade head` applied it to a local SQLite file. The tables `users`, `organizations`, `memberships`, `auth_sessions`, `invitations`, and `audit_events` were confirmed, along with `alembic_version`.
- Not run against PostgreSQL.

## Live server smoke test
Command: `uvicorn app.main:create_app --factory --port 8765` against the migrated SQLite file.

Results: `/healthz` returned ok, `/readyz` returned ready, and `POST /api/v1/auth/register` returned 201. The smoke user `smoke.owner@example.com` remains in the local development database.

## Frontend checks
- `tsc --noEmit`: no errors. `eslint src`: no findings. `next build`: succeeded.
- Production server (`next start`) plus uvicorn, checked over HTTP: `/login`, `/register`, `/onboarding`, and `/invite` returned 200. Registration through the `/api` proxy returned 201. Creating an organization returned role owner. Listing members returned one member.

## Browser tests (Playwright, Chromium)
Command: `npm run e2e` from `web/`. It starts the backend on a fresh SQLite database, builds and starts the web app, then runs 5 tests.

Result: **5 passed**.
- Signed-out visitors are redirected to login.
- Registration shows password policy feedback before submitting.
- A wrong password shows a generic error.
- Full flow across two users: register, create organization, invite, accept as a second user, member sees no invite form and no audit access, owner changes role, owner removes member, removed member loses access immediately, audit log shows the events.
- Mobile (390px): login and team pages render, no horizontal page scroll, sign out returns to login.

Defects found by this run and fixed:
- Hidden table header cells escaped the scroll container and widened the page by 159px on mobile.
- The mobile members table hid the role column and actions. Email now stacks under the name on small screens.
- "Sign out" wrapped onto two lines in the header.

Screenshots were reviewed at 1280px and 390px for overview, team, and login.

## Not performed
- Visual review of register, invite, onboarding, and audit pages. Only overview, team, and login were inspected.
- Tablet widths, light theme, keyboard-only navigation checks, and automated accessibility scans.
- Frontend unit tests.
- Firefox and Safari.
- PostgreSQL migration, backup, or restore.
- Security scanning beyond ruff's bandit-style rules.
- Any provider integration. No HubSpot, ERPNext, Gmail, or other sandbox was connected.
