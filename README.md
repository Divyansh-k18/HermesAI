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
- **HTTP step and connections.** A workflow can call any public HTTPS API and use the response in later steps. API keys are stored as encrypted connections on the Integrations page and never appear in a workflow or run trace. Private and internal addresses are blocked, redirects are not followed, and only safe requests are retried.
- **Idempotency.** Starting a run with the same key, or delivering the same webhook event twice, returns the same run.
- **Operations view.** Real numbers from the database: runs, outcomes by day, waiting approvals, average run time. Plus an audit log of security-relevant actions with the person who acted and a trace ID.
- **Landing page.** Signed-out visitors see what the product does and an honest split of what works today and what comes next.

## What does not exist yet

Be clear about this when presenting.

- No vendor integrations. HubSpot, ERPNext, Gmail, and PostgreSQL steps are in the builder, but running them fails with a clear "not available yet" message. The generic HTTP step works.
- No AI steps and no natural-language workflow creation.
- The engine is database-backed and in-process. It is not Temporal.
- Webhooks are generic, signed by Hermes's own scheme. There is no HubSpot-specific signature check yet, and no scheduled triggers.
- No billing, usage limits, account recovery, or email delivery.
- Tested on SQLite. PostgreSQL has not been run.
- This is not production-ready. No security review has been done.

## Run it

**You need:** Python 3.11 or newer (developed on 3.14), Node.js 20.9 or newer (developed on 24), and Git. Check with `python --version` and `node --version`.

You need **two terminals**, and both must stay open. The website on port 3000 talks to the API on port 8000. If the API terminal is closed or shows an error, the site cannot load.

### First time on a machine

Terminal 1, the API. On Windows:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python run.py
```

On macOS or Linux, the same steps:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m alembic upgrade head
.venv/bin/python run.py
```

`run.py` starts the API with auto-reload and with idle connections kept open long enough to avoid random "connection reset" errors through the website's proxy. Prefer it over calling uvicorn directly.

Wait for `Application startup complete`. Then open http://127.0.0.1:8000/healthz. It should show `{"status":"ok"}`.

Terminal 2, the website:

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000. The first page load compiles for up to a minute. Then create an account and follow [DEMO.md](DEMO.md).

### Every time after that

Run only the last command in each terminal. After pulling new code, run `alembic upgrade head` again first, because new tables may have been added.

### If it does not load

- **"Hermes can't reach its server":** the API terminal is not running or crashed. Read the error in that terminal.
- **`no such table` in the API terminal:** run `alembic upgrade head` in the `backend` folder.
- **`Address already in use` or port 8000 taken:** stop the other program, or start the API on another port and start the website with `HERMES_API_URL=http://127.0.0.1:<port>` set.
- **Opening the site from a different device:** use the laptop's own browser at http://localhost:3000. Other devices on the network are not set up.
- **A build error about `.next`:** stop the website, delete the `web/.next` folder, and start it again.

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
