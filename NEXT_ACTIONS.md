# Hermes AI — Next Actions

Resume here in a new session.

1. Initialize git in `hermes/` and commit the Phase 1 backend. Do this only when the user asks for a commit.
2. Install Docker Desktop or PostgreSQL locally, then run `alembic upgrade head` with `HERMES_DATABASE_URL` pointing to PostgreSQL. Record the result in `TEST_RESULTS.md`.
3. Start the API with `uvicorn app.main:create_app --factory --reload` from `backend/` and run a live smoke test of register, login, create organization, and invite.
4. Scaffold the Next.js frontend under `hermes/web/` with TypeScript, Tailwind, and the design tokens. Define the typography and color system first.
5. Build the auth screens (login, registration, account recovery) and the organization switcher against the existing endpoints.
6. Build the team and invitations screens, and the audit log view for admins.
7. Add CI (GitHub Actions) running ruff, pytest, and the frontend type check.
8. Move the rate limiter to Redis before any multi-instance deployment.
