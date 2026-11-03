# Hermes AI — Known Issues

## Blocking for production
1. **Rate limiting is in-process.** The limiter in `app/ratelimit.py` does not share state across instances. Move it to Redis before running more than one API process.
2. **No email delivery.** Invitation tokens are returned to the inviter through the API. Sending email requires a provider integration, which is not built.
3. **No account recovery.** The account recovery flow in the spec is not implemented.
4. **Cookie secure flag defaults to off.** `HERMES_COOKIE_SECURE` must be set to true in every HTTPS deployment.
5. **Registration reveals whether an email exists.** Registration returns 409 for an existing email. This is a deliberate trade-off for now, and it should be revisited with email verification.
6. **Credential encryption is not wired up.** `HERMES_CREDENTIAL_ENCRYPTION_KEY` is defined but no connector stores credentials yet.
7. **PostgreSQL is untested.** Migrations were applied only to SQLite.
8. **Session cleanup is absent.** Expired and revoked session rows are never deleted.

## Functional gaps
1. No frontend.
2. No workflow, execution, approval, integration, AI, analytics, or billing modules.
3. Organization deletion and ownership transfer are not implemented.
4. Audit events have no retention policy yet.
5. The audit read endpoint has no date filter or export.

## Tooling
0. The CI workflow has never run on GitHub. This repository has no remote. The workflow's YAML parses and each command passed locally on Windows. Linux runner behavior is unverified, including the Python 3.14 setup and the Playwright system dependencies.
1. Starlette warns that `httpx` with its TestClient is deprecated.
2. `HTTP_422_UNPROCESSABLE_ENTITY` is deprecated in the installed Starlette version.
3. Docker and `psql` are not installed, so the Docker and PostgreSQL steps cannot run here.
4. `hermes_dev.db` is a local development database and is git-ignored.

## Phase 2 additions
1. **Nothing executes.** Marking a version active has no effect. The UI says so. Do not describe the product as running workflows.
2. **No entitlements on workflows.** There is no limit on workflow count or size beyond the per-document bounds.
3. **HTTP node safety is structural only.** URLs must be HTTPS and must not point at localhost or private address literals. DNS resolution, redirects, and rebinding need runtime protection in the executor, which does not exist yet.
4. **Old versions cannot be viewed on the canvas.** The versions list shows them and allows activating a published one. Opening an old graph read-only is not built.
5. **Field paths are free text.** Conditions and mappings take typed paths such as `order.total`. There is no picker and no check against real data shapes.
6. **Integration nodes are not tied to connections.** A CRM node names an integration but no connected account exists yet, so no "missing connection" warning is shown.
7. **Last write wins within one revision check.** Two editors get a conflict message and must reload. There is no merge.
8. **Builder is not designed for phones.** It stacks and works at tablet width. Dragging on small touch screens is untested.
9. **OneDrive can lock `web/.next`.** A build failed once with EPERM. Deleting `web/.next` fixed it. Moving the repository out of OneDrive would avoid it.
10. **The first CI run is still pending.** See the earlier note.

## Resolved: dev server build error on fonts
`next dev` failed with "Can't resolve @vercel/turbopack-next/internal/font/google/font" and a 500 on every page. The dev server downloaded Geist from Google Fonts on each request, and that download fails on unreliable networks. Fonts now come from the bundled `geist` package, so nothing is fetched. The Tailwind loader rule in `web/next.config.ts` also now applies only to `globals.css`, not to generated font CSS.

## Test servers use separate ports
Browser tests start their own backend on port 8100 and web app on port 3100, so they no longer collide with a developer's servers on 8000 and 3000. They still build into `web/.next`, so stop `npm run dev` before running them.

## Phase 3 and 6 additions
1. **The engine is in-process, not Temporal.** All state is in the database and a restart loses nothing, but there is no distributed worker fleet, no automatic retry policy, and no activity timeouts. A crash in the middle of a single step could leave a run stuck as running. There is no reconciliation view yet.
2. **Delay timers poll every two seconds** from inside the API process. With several API instances each one polls. Claims are atomic, so a delay resumes once, but this has not been load tested.
3. **Steps needing other systems fail.** CRM, ERP, database, email, HTTP, and AI steps stop the run with "not available yet".
4. **No scheduled triggers.** Runs start manually, by API call, or by signed webhook (see below).
5. **No run retry.** A failed run cannot be restarted from the failed step.
6. **No separation of duties.** The person who starts a run can also approve it if they hold the approver role.
7. **No approval expiry or reminders.** A pending approval waits indefinitely until decided or the run is cancelled.
8. **Run payloads are free-form JSON** up to 50 KB. Payload contents are stored as given and shown to approvers.
9. **Average run time includes waiting for people.**
10. **Existing local databases need `alembic upgrade head`** after pulling these changes.

## Webhook additions
1. **One signing scheme.** Hermes verifies its own HMAC-SHA256 format. Vendor formats, such as HubSpot's v3 signature, need an adapter before a real HubSpot webhook can be pointed at Hermes.
2. **The replay window is five minutes** and relies on the server clock. Within that window, replays are stopped by the event id, which senders must keep unique.
3. **A failed delivery can be retried with the same event id** after the cause is fixed, such as an inactive workflow. An accepted event id can never start a second run.
4. **Rate limiting is in-process.** 120 deliveries per minute per endpoint, per API process. Move it to Redis for multiple instances.
5. **The development encryption key lives in `backend/.dev-encryption-key`.** It is git-ignored and created on first use. Deleting it makes existing webhook secrets unreadable, and those webhooks must be rotated. Production refuses to start without `HERMES_CREDENTIAL_ENCRYPTION_KEY`.
6. **Rejected deliveries are audited, not stored as events.** The audit log records bad signatures and stale timestamps, limited by the rate limiter.
7. **Locally, the webhook URL is on localhost.** An outside system needs a public address, such as a tunnel or a deployment.

## HTTP step and connections
1. **DNS rebinding is not fully closed.** The engine resolves the host and refuses private or reserved addresses, then httpx resolves the name again to connect. A hostile DNS server that changes its answer between the two lookups could reach an internal address. Pinning the connection to the checked address is the fix.
2. **HTTP steps run inside the request that starts or resumes the run.** With retries a slow API can hold that request for about 30 seconds. Moving step execution to background workers removes this.
3. **POST and PATCH are never retried automatically.** They send an `Idempotency-Key` header of the run id and step id, so a receiving API that honors it can deduplicate a manual retry. APIs that ignore the header may see duplicates if a run is retried by hand.
4. **A connection holds one header.** OAuth flows, signed requests, and query-string keys are not supported yet.
5. **Responses are stored in the run's data** (up to 1 MB) and are visible to everyone who can read runs, including viewers. Do not call APIs whose responses contain secrets.
6. **Only JSON request bodies.** The body is taken from one data path. Form encoding and custom templates are not supported.

## Resolved: occasional "connection reset" through the website proxy
One browser test failed with `Failed to proxy ... read ECONNRESET`. The likely cause is a keep-alive race: uvicorn closes idle connections after 5 seconds, and the Next.js proxy reuses idle connections for about as long, so a request can be sent on a connection the server is closing. People would see it as a random "Cannot reach the Hermes server" after a short pause. `backend/run.py` now starts the API with a 75 second keep-alive so the proxy always closes first, and the browser tests start the API through the same script. Start the API with `python run.py`, not plain uvicorn.

## Resolved: endless loading when the API is down
When the API was not running or its database had no tables, the home page and signed-in pages showed a loading placeholder forever. They now show "Hermes can't reach its server" with the usual causes, and forms say "Cannot reach the Hermes server". Confirmed against the real proxy with the API stopped: it answers 500 with a plain-text body, which is what the app detects.

## Resolved: "can't reach its server (HTTP 404)" when port 8000 is taken
On a machine where another program already uses port 8000, the Hermes API cannot start there, and the other program answers the website's requests with 404. `run.py` now checks the port first and stops with instructions for using another port (`HERMES_PORT` for the API, `HERMES_API_URL` for the website). The error page explains the 404 case. Verified by holding a port with another process: `run.py` exits with code 1 and prints the alternative commands.

## Email orders
1. **Not yet tested against a live mailbox.** Tests use a fake mailbox with real email messages. The IMAP code uses Python's standard library and has not been run against Gmail or another provider from this machine. Treat the first live connection as the real test.
2. **Without an AI key, order details must be in "Field: value" lines.** With a key, the AI step reads free-form emails (see below).
3. **Checked once a minute** by the API's background loop, or on demand with Check now. Not instant.
4. **Up to 20 new emails per check.** A burst larger than that is handled over the next checks.
5. **Renumbered folders restart from the newest email.** If the mail server rebuilds a folder's numbering, Hermes starts again from the newest message so old mail never becomes orders. An email that arrived at that exact moment could be skipped. Message-IDs prevent repeats.
6. **Anyone can email the address unless senders are restricted.** The panel warns about this. Approvals still apply to large orders.
7. **Attachments are ignored.** Only the text (or HTML converted to text) is read.
8. **Gmail needs an app password.** OAuth sign-in with Google is not built.

## AI order reading

1. **Not yet tested against a live model.** All tests use a simulated provider that returns scripted replies, including bad ones. The first run with a real key is the real test. Try it before presenting.
2. **Free tiers have rate limits.** If the provider refuses with a rate limit, Hermes retries once, then the run fails with a clear message. Wait a minute and run again.
3. **The AI can misread an email.** That is why the sample sends low-confidence, missing-total, and large orders to a person. Do not remove those checks.
4. **Free tiers may use submitted data for training.** Use made-up orders for demos.
5. **Only the email body is read**, up to 8,000 characters. Attachments are ignored.
