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
- **Orders by email.** Connect a mailbox (for example Gmail with an app password) to a workflow, and each new email starts a run. Order details come from lines such as `Total: 75,000` and `Customer: Asha Traders`, which arrive as `email.fields.total` and `email.fields.customer`. Hermes only reads new mail, never marks it as read, never processes old mail, starts at most one run per email, and can be limited to known senders. The password is stored encrypted.
- **AI reads free-form order emails.** The AI step turns an email written in any style ("please send 50 boxes of A4 paper to Pune by Friday, total Rs 75,000") into a structured order: customer, items, total, delivery, a confidence score, and what is missing. The AI only reads. Plain rules decide what happens next, so unclear or large orders still go to a person. Works with any OpenAI-compatible provider, including free tiers from Groq and Google AI Studio. See **Turn on AI** below.
- **HTTP step and connections.** A workflow can call any public HTTPS API and use the response in later steps. API keys are stored as encrypted connections on the Integrations page and never appear in a workflow or run trace. Private and internal addresses are blocked, redirects are not followed, and only safe requests are retried.
- **Idempotency.** Starting a run with the same key, or delivering the same webhook event twice, returns the same run.
- **Operations view.** Real numbers from the database: runs, outcomes by day, waiting approvals, average run time. Plus an audit log of security-relevant actions with the person who acted and a trace ID.
- **Landing page.** Signed-out visitors see what the product does and an honest split of what works today and what comes next.

## What does not exist yet

Be clear about this when presenting.

- No vendor integrations. HubSpot, ERPNext, Gmail, and PostgreSQL steps are in the builder, but running them fails with a clear "not available yet" message. The generic HTTP step works.
- AI does one job: reading orders from text. There is no natural-language workflow creation, and the AI cannot call tools or take actions.
- The AI step has been tested against a simulated provider, not yet against a live model. Try it with your key before presenting.
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

- **"Hermes can't reach its server" with HTTP 404:** another program is using port 8000, so a different app answers instead of Hermes. `python run.py` detects this and prints how to use another port. To see what holds the port on Windows, run `netstat -ano | findstr :8000`, then `tasklist /FI "PID eq <number>"`.
- **"Hermes can't reach its server" with HTTP 500:** the API terminal is not running or crashed. Read the error in that terminal.
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

## Taking orders by email (Gmail)

1. In Gmail settings, under "Forwarding and POP/IMAP", turn on IMAP.
2. In your Google Account, under Security, turn on 2-Step Verification, then create an **app password**. Your normal Gmail password will not work.
3. In Hermes, open **Workflows** and click **Load email order sample**.
4. In the builder's right panel (click empty canvas first), under **Email orders**, click **Connect mailbox**. Enter the Gmail address and the app password. Optionally limit orders to your customers' domains. Click **Save and test**.
5. Send an email to that address from another account, with lines like:

   ```
   Customer: Asha Traders
   Total: 75,000
   ```

6. Click **Check now**, or wait up to a minute. Open the run: an order over ₹50,000 waits for approval.

Hermes only reads emails that arrive after the mailbox is connected.

## Turn on AI (free key)

The AI step needs a key from an AI provider. Both options below have a free tier. **Never paste the key into chat, code, or a workflow. It goes only in `backend/.env`, which git ignores.**

**Option A: Groq (recommended for demos, very fast)**

1. Go to https://console.groq.com/keys, sign in, and click **Create API Key**. Copy it.
2. Open `backend/.env` (create it if it does not exist) and add:

   ```
   HERMES_AI_BASE_URL=https://api.groq.com/openai/v1
   HERMES_AI_API_KEY=paste-your-key-here
   HERMES_AI_MODEL=openai/gpt-oss-120b
   ```

**Option B: Google AI Studio (Gemini)**

1. Go to https://aistudio.google.com/apikey and click **Create API key**. Copy it.
2. Add to `backend/.env`:

   ```
   HERMES_AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
   HERMES_AI_API_KEY=paste-your-key-here
   HERMES_AI_MODEL=gemini-2.5-flash
   ```

Model names change over time (Groq retired `llama-3.3-70b-versatile` in 2026). On 2026-11-03, `openai/gpt-oss-120b` and `qwen/qwen3.8-27b` read the test orders correctly. If a run fails with "model or URL not found", check the provider's model list and update `HERMES_AI_MODEL`. Free tiers may use your data to improve their models, so use made-up orders for demos, not real customer data.

**Then:**

1. Stop the backend (Ctrl+C) and start it again with `python run.py`. Settings are read at start-up.
2. In Hermes, open **Workflows** and click **Load AI email order sample**. Click the AI step: the right panel should say **AI on**.
3. Click **Run**. The payload is pre-filled with an order written in plain English. Edit the text however you like, then run it.
4. Open the run. The AI step's output shows the order it read; a large, clear order waits for a manager, and a vague one waits for a person to check it.

To take real emails, connect a mailbox to this workflow as described in **Taking orders by email** above. The AI reads each email body.

Limits: each organization can make 200 AI calls an hour (`HERMES_AI_CALLS_PER_HOUR`), and only the first 8,000 characters of an email are read (`HERMES_AI_MAX_INPUT_CHARS`).
