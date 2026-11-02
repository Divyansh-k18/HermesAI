# Hermes AI — Architecture

## Layout
```
hermes/
  backend/        FastAPI service (Python 3.14 locally, 3.11+ supported)
    app/          application package
    migrations/   Alembic migrations
    tests/        pytest suite
```

## Backend components
- `app/config.py`: settings from `HERMES_*` environment variables.
- `app/db.py`: SQLAlchemy engine and session factory. SQLite is enabled with foreign keys for tests and local development. PostgreSQL is the production target.
- `app/models.py`: users, organizations, memberships, auth sessions, invitations, audit events.
- `app/security.py`: Argon2 password hashing, password policy, opaque tokens, SHA-256 token hashing.
- `app/rbac.py`: role ranks, permission table, and rules for who may grant or manage which role.
- `app/deps.py`: request dependencies. `get_current_auth` validates the session cookie. `require_csrf` checks the CSRF header. `org_access` resolves membership and checks permission for one organization.
- `app/audit.py`: append-only audit writer. It redacts metadata keys that look like credentials.
- `app/ratelimit.py`: in-process sliding-window limiter for login and registration.
- `app/routers/`: `auth.py` and `orgs.py`.
- `app/main.py`: application factory with security headers, request IDs, CORS, health, and readiness.

## Request flow for an organization route
1. The session cookie resolves to an active, unexpired, unrevoked session and its user.
2. For state changes, the `X-CSRF-Token` header must match the session's CSRF token.
3. The caller's membership in the path organization is loaded. No membership returns 404.
4. The role must hold the named permission, or the request gets 403.
5. Role-specific rules apply, such as owner protection and assignable roles.
6. The change and its audit event are committed in one transaction.

## Authentication model
- Session token: 32 random bytes, URL-safe encoded, delivered in an HttpOnly, SameSite=Lax cookie.
- Stored server-side as a SHA-256 hash. A database leak does not expose live tokens.
- CSRF token: separate random value bound to the session, returned by login and `/auth/me`.

## Tenant isolation
Every organization-scoped table carries `organization_id`. Every organization route resolves membership first. Cross-tenant identifiers return the same 404 as missing ones.

## Not yet designed in detail
Workflow engine, connectors, AI runtime, approvals, billing. These are tracked in `IMPLEMENTATION_PLAN.md`.
