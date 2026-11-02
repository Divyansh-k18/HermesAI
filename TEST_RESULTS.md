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

## Phase 2 update (workflows)

Backend: `python -m pytest` from `backend/` now runs **111 passed** (43 identity and organization, 49 workflow validation, 19 workflow API). `ruff check` and `ruff format --check` pass.

Workflow API tests cover role permissions, tenant isolation, CSRF, stale revision conflicts, malformed definitions, publish blocking on invalid graphs, immutability of published versions at the API and ORM level, the one-draft-per-workflow database index, activation rules, archive rules, and audit events.

Migrations: upgrade, downgrade to base, and upgrade again succeeded on a fresh SQLite database. The partial unique index and the named foreign key were present afterwards. Not run on PostgreSQL. The first generated migration created a table with a foreign key to a table that did not exist yet, which SQLite accepts and PostgreSQL rejects. It was restructured by hand, but that fix is unverified on PostgreSQL.

Browser tests: `npm run e2e` runs **8 passed** (5 earlier plus 3 for the builder). The builder tests drive real mouse interaction: add steps from the palette, drag between handles to connect, undo and redo, save, publish, activate, reload to confirm persistence, then edit a published workflow and confirm a new draft appears while version 1 stays frozen. A seeded eight-step sales-order graph is checked for rendering, validation, and the inspector. Auto layout is checked at 820px width.

Defects found by reviewing screenshots and fixed:
- The canvas collapsed to zero height below the large breakpoint, so the editor was blank on tablets.
- Fit-to-view shrank wide graphs to about a third of normal size. It now keeps a readable zoom and starts at the trigger.
- Branch labels sat on bright patches and the minimap was a light grey block. Both now follow the dark theme.
- End steps said "Not configured".

Regression assertions were added for the zero-height canvas and the readable zoom.

One run had a single failure in the sign-up redirect step. It passed on three reruns. The assertion timeout was raised from 5 to 10 seconds. The cause was not proven.

Still not done: keyboard-only and accessibility scans of the builder, phone-width layout of the builder, Firefox and Safari, and visual review of the register, invite, onboarding, audit, and library pages.
