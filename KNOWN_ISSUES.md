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
