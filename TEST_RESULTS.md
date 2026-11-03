# Hermes AI — Test Results

## 2026-11-03: Inventory, stock checks, live email list
- Backend: **251 passed** (full suite), including 16 new inventory tests: admin-only stock changes, member read-only, tenant isolation, word matching ("50 boxes of A4 paper" -> "A4 Paper"), in-stock and short/not-stocked/unknown-quantity paths, missing order lines, path validation, and recent emails on the mailbox endpoint. `ruff check` clean.
- Web: `tsc --noEmit`, `eslint`, and `next build` pass; the build includes `/o/[orgId]/inventory`. All three sample workflows pass backend validation.
- Browser tests were not rerun for this change.
- Live AI: on Groq, `openai/gpt-oss-120b` and `qwen/qwen3.8-27b` read a clear order, a vague order, and an injection attempt correctly.

## 2026-11-03: AI order reading
- Backend: **232 passed** (full suite, including 24 new AI tests against a simulated provider). `ruff check` and `ruff format --check` clean.
- AI tests cover: free-form email to structured order, amounts written as text ("₹1,200"), totals computed by code and mismatches flagged, low confidence and missing totals routed to a person, extra keys from the model dropped and unable to skip approval, the email unable to break out of its fence, invalid and off-schema replies failing the run, JSON-mode fallback, retry on rate limits, rejected key, missing key, missing text, input cap, per-organization hourly limit, mailbox to AI end to end, status endpoint never revealing the key.
- Browser: `e2e/email.spec.ts` **2 passed**, including the new AI sample test (production build). The full browser suite was not rerun for this change.
- **Not tested against a live AI model.**


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

## Phase 3 and 6 update (execution engine and approvals)

Backend: `python -m pytest` from `backend/` runs **146 passed** (111 earlier plus 35 for execution). `ruff check` and `ruff format --check` pass.

Execution tests cover: condition operators and failing closed on bad data; a small order finishing without approval; a large order pausing, then continuing when approved; a rejected order never running the approved path; a graph wired so rejection reaches a normal ending still finishing as rejected; approver role enforcement with denied attempts audited; members and viewers blocked from approvals; an approval deciding only once; idempotency keys returning the same run; runs needing an active version; viewers reading but not running; runs staying on the version they started on after a new version is activated; delays waiting and resuming; a new application instance continuing a waiting run on the same database; steps needing other systems failing with a clear message; bad input failing the run; cancelling a run and its approval; tenant isolation for runs and approvals; CSRF; payload bounds; audit events; metrics from real rows; and organization ids on step and approval rows.

Migrations: three migrations went up, down to base, and up again on a fresh SQLite database. Not run on PostgreSQL.

Browser tests: `npm run e2e` runs **10 passed**. New: the demo story (load the sample, run a large order, see it pause, approve, run a small order, reject a large one, confirm the approved path never ran, check lists, history, and overview) and a roles test (a member runs a workflow but cannot see or decide approvals, the owner decides, the member's run completes).

Defect found by the browser run: a PowerShell find and replace corrupted non-ASCII characters in two test files, so tests searched for garbled text. Fixed by reversing the encoding. The cause and rule are recorded in project notes.

The overview's average run time includes time spent waiting for a person, which can make it large for approval flows.

Still not done: PostgreSQL, security review, accessibility scan, phone layout, and every external integration.

## Final run for this milestone

Backend: **146 passed**. Lint and format checks pass.

Browser tests: **12 tests** (`npm run e2e`). Eleven passed on the first full run and the twelfth failed because it still expected the home page to redirect signed-out visitors to login. The home page now shows a landing page on purpose, so the assertion was updated and the file was rerun. Two new tests cover the landing page at desktop and phone width, including no sideways page scroll.

Reviewed screenshots: landing (desktop and phone), run waiting for approval, run approved, overview with metrics. Fixed from review: the landing diagram hid its branch labels and was unreadable on phones.

The test setup now clears `web/.next` with retries before building, because OneDrive intermittently locks it and fails the build.

## Webhook triggers

Backend: **163 passed** (146 earlier plus 17 webhook tests). Lint and format checks pass, including `backend/scripts`.

Webhook tests cover: the secret shown once; a signed delivery starting a run with trigger type "webhook"; a repeated event returning the same run with one run in the database; bad signatures refused and audited; a tampered body refused; timestamps five minutes old or in the future refused with the same message as a bad secret; missing or malformed headers; unknown endpoints; non-object and oversized bodies; secret rotation invalidating the old secret; deletion; an event refused for an inactive workflow and accepted on retry after activation; the secret stored encrypted; only owners and admins managing webhooks, with tenant isolation; CSRF on management; the per-endpoint rate limit; and production refusing to start without an encryption key.

Migration: the fourth migration went up, down, and up again on SQLite.

Live check against a real uvicorn server with the real `send_webhook.py` script: a large order started a run waiting for approval, resending the same event id returned "duplicate" with the original run, a small order completed on its own, and a wrong secret got 401 with no run.

Browser tests: **13 passed** (12 earlier plus 1 webhook test). The webhook test creates a webhook in the builder, sends signed deliveries through the Next.js proxy, checks the duplicate and forged cases, sees the delivery in the panel, and opens its run.

## HTTP step, connections, and start-up reliability

Backend: **185 passed** (163 earlier plus 22 for the HTTP step and connections). Lint and format checks pass.

HTTP step tests run against a fake network and fake DNS, so nothing leaves the machine. They cover: the response saved for later steps; the connection header sent and absent from the run record; POST bodies taken from the run data with an Idempotency-Key and never retried; GET retried on 5xx with backoff, and giving up after three attempts; private, loopback, link-local, metadata, IPv6 local, and mixed public and private addresses blocked before any request; redirects not followed; 4xx failing the run; responses over 1 MB refused; a missing body field failing before any request; a connection from another organization refused; invalid data paths blocking publish. Connection tests cover encryption at rest, the secret never returned, header validation including header injection, permissions, isolation, CSRF, and audit.

Migration: the fifth migration went up, down, and up again on SQLite.

Browser tests: **16 passed** on the final code. New: the Integrations page stores a connection, masks it, and the HTTP step inspector offers it; an unreachable API shows "Hermes can't reach its server" and recovers on Try again; the login form explains an unreachable API.

The real proxy was checked with the API stopped: it answers 500 with a plain-text body, which is the case the app detects.

One full run had a single `read ECONNRESET` through the proxy during login. After the API was started through `run.py` with a 75 second keep-alive, the sign-in tests passed twice in a row and the full suite passed. A timing race cannot be proven gone from a few runs. The setting removes its known cause.

## Port conflict handling
Browser tests: **17 passed**, including a new test that a 404 from the API address shows the "another program is using the port" explanation. `run.py` was checked against a port held by another process: it exits with code 1 and prints how to use another port.

## UI upgrade and email orders

Backend: **208 passed** (185 earlier plus 23 email-order tests). Lint and format checks pass.

Email-order tests use a fake mailbox with real email messages built by Python's email library. They cover: "Field: value" parsing including ₹, Rs, commas, and decimals; HTML-only emails; allowed senders by address and domain; connecting verifies the sign-in and skips mail already in the box; a new email starting a run with the parsed fields; the same Message-ID never starting two runs; unknown senders ignored; mail left unread while the workflow is inactive and picked up after activation; a refused sign-in saving nothing; mailbox errors shown on later checks; the password encrypted and kept when other settings change; private mail servers refused; header-injection attempts in fields refused; permissions and isolation; disconnecting; the one-minute check interval; and a renumbered folder restarting from the newest email. That last test found a bug, which was fixed.

Migration: the sixth migration went up, down, and up again on SQLite.

Browser tests: **21 passed**. New: the run graph shows the waiting step, the unreached endings, and moves focus to a step's trace entry when clicked; the Ctrl+K command palette filters, navigates, and closes; the 3D hero renders (the test browser ran it in 3D mode) and loads without errors under reduced motion; the email order sample loads and the mailbox form reports a mail server that does not exist.

Found by the full browser run and fixed: the new Search button made the phone-width header wider than the screen.

Not done: a live mailbox. The IMAP code has not been run against Gmail from this machine.
