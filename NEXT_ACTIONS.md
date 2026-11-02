# Hermes AI — Next Actions

Resume here in a new session.

Done so far: backend committed, web app scaffolded with auth, onboarding, invitation, overview, team, and audit screens.

1. Review the UI in a browser at 1440px and 390px widths. Install Playwright (`npx playwright install chromium`) and add screenshot and critical-flow tests: register, create organization, invite, accept, change role, remove.
2. Fix visual weaknesses found in review. Add a light-theme toggle (tokens already exist) and a mobile navigation check.
3. Install Docker Desktop or PostgreSQL, then run `alembic upgrade head` with `HERMES_DATABASE_URL` set to PostgreSQL. Record the result in `TEST_RESULTS.md`.
4. Add GitHub Actions CI: ruff and pytest for `backend/`, then tsc, eslint, and build for `web/`.
5. Build account recovery (needs an email provider decision) and email delivery for invitations.
6. Start Phase 2: workflow definition and version tables, validation rules, and the workflow library and builder screens (React Flow).
7. Move the rate limiter to Redis before any multi-instance deployment.

Run locally:
- Backend: `cd backend; .venv\Scripts\alembic upgrade head; .venv\Scripts\python -m uvicorn app.main:create_app --factory --reload`
- Web: `cd web; npm run dev`
