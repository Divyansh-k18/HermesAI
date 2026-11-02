# Hermes AI

**Intelligence in Motion.** A workflow automation platform where automation is visible, approvals are enforced by the system, and every action is recorded.

Teams design a workflow on a canvas, publish it as a frozen version, and run it. When a run reaches a decision that needs a person, it pauses, asks the right role, and continues only if that person approves. Every step, input, output, and decision is kept and inspectable.

## What works today

- **Accounts and teams.** Sign up, create an organization, invite people, assign roles, revoke access. Sessions are server-side, with CSRF protection, and every organization's data is isolated.
- **Visual workflow builder.** Drag and connect steps, branch on conditions, set approval steps, undo and redo, auto layout, live validation from the server, and conflict detection between editors.
- **Versioning.** Drafts are editable. Published versions are frozen at both the API and the database layer. One version at a time is active.
- **Execution engine.** Runs the active version, records every step with its input and output, and keeps all state in the database, so a restart loses nothing. Supports trigger, condition, transform, delay, approval, and end steps.
- **Human approval.** A run pauses at an approval step. Only the role the workflow names can decide. A decision applies once. A rejected run can never finish as succeeded, and the approved path never runs.
- **Webhook triggers.** Another system can start a workflow with a signed HTTP request. Signatures use HMAC-SHA256, requests older than five minutes are refused, a repeated event returns the original run, and the signing secret is stored encrypted and shown once. `backend/scripts/send_webhook.py` sends a signed test event.
- **Idempotency.** Starting a run with the same key, or delivering the same webhook event twice, returns the same run.
- **Operations view.** Real numbers from the database: runs, outcomes by day, waiting approvals, average run time. Plus an audit log of security-relevant actions with the person who acted and a trace ID.
- **Landing page.** Signed-out visitors see what the product does and an honest split of what works today and what comes next.

## What does not exist yet

Be clear about this when presenting.

- No external integrations. HubSpot, ERPNext, Gmail, PostgreSQL, and REST steps are in the builder, but running them fails with a clear "not available yet" message.
- No AI steps and no natural-language workflow creation.
- The engine is database-backed and in-process. It is not Temporal.
- Webhooks are generic, signed by Hermes's own scheme. There is no HubSpot-specific signature check yet, and no scheduled triggers.
- No billing, usage limits, account recovery, or email delivery.
- Tested on SQLite. PostgreSQL has not been run.
- This is not production-ready. No security review has been done.

## Run it

Two terminals, from the repository root.

```powershell
cd backend
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m uvicorn app.main:create_app --factory --reload
```

```powershell
cd web
npm run dev
```

Open http://localhost:3000, create an account, then follow [DEMO.md](DEMO.md).

If the backend was set up before, run `alembic upgrade head` again. New tables were added.

## Tests

```powershell
cd backend; .venv\Scripts\python -m pytest     # backend
cd web; npm run e2e                            # browser tests, on their own ports
```

Stop `npm run dev` before running browser tests. They build into the same folder.

## How it is built

- **Backend:** Python, FastAPI, SQLAlchemy, Alembic. Argon2 password hashing. SQLite for development, PostgreSQL as the target.
- **Frontend:** Next.js, TypeScript, Tailwind, React Flow, TanStack Query, Zod, React Hook Form.
- **Tests:** pytest for the API and engine, Playwright for the browser.

More detail: [ARCHITECTURE.md](ARCHITECTURE.md), [DECISIONS.md](DECISIONS.md), [KNOWN_ISSUES.md](KNOWN_ISSUES.md), and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
