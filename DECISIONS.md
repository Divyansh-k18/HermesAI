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

## D-011: Drafts and published versions
A workflow has one editable draft at most and any number of frozen published versions. Immutability is enforced twice: the API never updates a published row, and the ORM refuses to. A partial unique index allows one draft per workflow. Editing a published workflow creates the next draft on the first save.

## D-012: Structured conditions, no expression language
Conditions are a field, an operator from a fixed list, and a value. There is no free-form expression, so there is nothing to evaluate dynamically and no injection surface. More power can be added later through explicit operators.

## D-013: Save accepts incomplete graphs, publish does not
Saving stores whatever the user has so work is never lost, and returns the issues. Publishing re-validates on the server and refuses any error. Publishing also requires the revision the user reviewed, so a stale view cannot publish unseen changes.

## D-014: "Active", not "live"
Activation marks which published version receives new runs. The word "active" was chosen when no execution engine existed, so the interface would not overstate. The engine now exists (D-016), and "active" still describes it accurately: new runs and webhook deliveries use that version.

## D-015: Builder views fit to a readable zoom
Wide graphs keep at least 60 percent zoom and anchor at the trigger, so text stays legible. The Controls fit button still fits everything.

## D-016: Database-backed engine now, Temporal later
Docker is not available here and the time budget is short, so the first engine keeps every piece of run state in PostgreSQL-compatible tables and advances runs in process. Step execution is separate from the loop that picks the next step, so the runner can later be replaced by Temporal activities without changing the data model. This is a deliberate trade-off and is not a claim of Temporal-grade durability.

## D-017: Runs are pinned to the version they started on
A run stores the version id and always follows that frozen graph, even if another version is activated while it waits. Approving an old run cannot change which steps run.

## D-018: Rejection is sticky
A rejection sets the run outcome to rejected. If a graph is wired so the rejected branch reaches a normal ending, the run still finishes as rejected. The approved branch only runs after an approval is recorded as approved.

## D-019: One-shot decisions and timers by atomic claim
Approval decisions and delay resumes are claimed with a conditional update. Only one caller can win, so a double click, a retry, or two processes cannot run a step twice.

## D-020: Members can run workflows but not see approval data
Approval context can contain business data. Only owners and admins see and decide approvals. A member who started a run sees that it is waiting, nothing more.

## D-021: Conditions fail closed
A condition that cannot be evaluated because a field is missing or not a number fails the run with a visible error. It never silently picks a branch.

## D-022: Signed webhooks with encrypted secrets
Webhook requests are signed with HMAC-SHA256 over the timestamp and raw body, so the body cannot be changed in transit and old requests cannot be replayed outside a five-minute window. The event id is unique per endpoint, which makes delivery idempotent: a sender may retry freely. The server must read the secret back to verify signatures, so it cannot be hashed. It is encrypted with Fernet instead, and the key comes from configuration. Production refuses to start without a key. Bad signatures and stale timestamps get the same response, so a caller learns nothing about which check failed.

## D-023: Credentials live in connections, not in workflows
An HTTP step refers to a connection by id. The connection holds an encrypted header value that no endpoint returns. Workflow definitions, versions, run traces, and exports therefore never contain a credential, and rotating a key does not require a new workflow version.

## D-024: Outbound requests are deny-by-default
Steps may call only HTTPS URLs whose every resolved address is public. Redirects are not followed, responses are capped at 1 MB, and requests time out after 10 seconds. Only methods that are safe to repeat are retried. Writes carry an Idempotency-Key so the receiving system can recognize a repeat.
