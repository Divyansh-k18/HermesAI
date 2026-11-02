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
1. Starlette warns that `httpx` with its TestClient is deprecated.
2. `HTTP_422_UNPROCESSABLE_ENTITY` is deprecated in the installed Starlette version.
3. Docker and `psql` are not installed, so the Docker and PostgreSQL steps cannot run here.
4. `hermes_dev.db` is a local development database and is git-ignored.
