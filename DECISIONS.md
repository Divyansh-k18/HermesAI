# Hermes AI — Decisions

## D-001: Server-side sessions instead of JWT for the web app
Sessions are opaque tokens stored as hashes. Revocation is immediate, and logout and role changes take effect on the next request. JWTs cannot be revoked without extra state, so they were not used for browser sessions.

## D-002: CSRF via session-bound header token
State-changing requests must send `X-CSRF-Token` matching the session. The cookie is SameSite=Lax, and the header check blocks cross-site form posts.

## D-003: 404 for non-members
Organizations a caller cannot see return 404, the same as missing organizations. This prevents tenant enumeration.

## D-004: Role rules enforced server-side
Admins may grant only member and viewer. Owners may grant any role. Admins cannot change or remove owners or other admins. An organization must always keep at least one owner. These rules live in `app/rbac.py` and are tested.

## D-005: Invitation tokens are single-use and hashed
The token is shown once at creation. The invitee must authenticate with the invited email address. If the inviter has been demoted since the invitation, the invitation stops working.

## D-006: Audit events in the same transaction
Each audited action commits with its audit row, so an action cannot succeed without its record. Metadata keys that look like credentials are removed before storage.

## D-007: UUID strings and naive UTC timestamps
UUID strings keep the schema portable between SQLite and PostgreSQL. Timestamps are naive UTC, written only through `utcnow`.

## D-008: SQLite for development and tests, PostgreSQL as the target
No Docker or PostgreSQL is available in the current environment. Models avoid PostgreSQL-only types so the same schema can run on both. PostgreSQL migration testing is pending (see `KNOWN_ISSUES.md`).

## D-009: Argon2 for password hashing
Argon2 via `argon2-cffi`. Unknown-email logins run a dummy verification so response timing does not reveal which emails exist.

## D-010: Frontend deferred until backend slice is tested
The backend auth and tenancy layer was built and tested first, because the frontend depends on its contract.
