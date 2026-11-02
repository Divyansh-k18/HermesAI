# Hermes AI — Next Actions

Resume here in a new session.

Done so far: backend committed, web app scaffolded with auth, onboarding, invitation, overview, team, and audit screens.

1. Done: Playwright installed, 5 browser tests pass (`npm run e2e` in `web/`).
2. Review the remaining pages visually (register, invite, onboarding, audit) and tablet width. Add a light-theme toggle (tokens exist), an accessibility scan (axe), and keyboard navigation checks.
3. Install Docker Desktop or PostgreSQL, then run `alembic upgrade head` with `HERMES_DATABASE_URL` set to PostgreSQL. Record the result in `TEST_RESULTS.md`.
4. Done, not yet run: GitHub Actions CI in `.github/workflows/ci.yml` (backend lint, format, tests, migration; web types, lint, build; Playwright). Push to GitHub and confirm the first run passes. Fix anything that differs between Windows and Linux.
5. Build account recovery (needs an email provider decision) and email delivery for invitations.
6. Start Phase 2: workflow definition and version tables, validation rules, and the workflow library and builder screens (React Flow).
7. Move the rate limiter to Redis before any multi-instance deployment.

Run locally:
- Backend: `cd backend; .venv\Scripts\alembic upgrade head; .venv\Scripts\python -m uvicorn app.main:create_app --factory --reload`
- Web: `cd web; npm run dev`
