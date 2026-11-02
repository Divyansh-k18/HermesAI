# Hermes AI — Implementation Plan

Status key: DONE (implemented and tested), PARTIAL, TODO.

## Phase 1 — Engineering Foundation
| Item | Status | Notes |
|---|---|---|
| Repository structure | DONE | Single `hermes/` root with `backend/`. Not yet a git repository. |
| Database setup (SQLAlchemy + Alembic) | DONE (SQLite) | PostgreSQL not yet exercised. |
| Authentication (sessions, CSRF, lockout-style rate limit) | DONE | Rate limiter is in-process only. |
| Organization management | DONE | Create, read, update, list. |
| Members, roles, revocation | DONE | Owner, admin, member, viewer. |
| Invitations | DONE (API) | No email delivery yet. |
| Audit logging | DONE | Read endpoint for owners and admins. |
| Design tokens and base UI components | TODO | Requires the frontend. |
| Development environment and CI | PARTIAL | Lint and tests run locally. No CI config yet. |

## Phase 2 — Core Product
Application navigation, workflow builder, persistent workflow definitions, validation, versioning, execution history. TODO.

## Phase 3 — Execution Engine
Temporal integration, workers, triggers, retries, persisted execution state, recovery. TODO.

## Phase 4 — External Integrations
HubSpot, ERPNext, Gmail, PostgreSQL, generic REST. TODO. Each requires real sandbox credentials before being called verified.

## Phase 5 — AI Capabilities
Natural-language workflow generation, structured agent output, permissioned tool calls, policy enforcement. TODO.

## Phase 6 — Human Approval
Approval records, notifications, approval UI, durable waiting, continuation and rejection handling. TODO.

## Phase 7 — Visual Polish
Design system refinements, motion, 3D brand asset, optional 3D inspector, accessibility pass. TODO.

## Phase 8 — Operations
Analytics from real data, audit UI, monitoring, usage controls. TODO.

## Phase 9 — Production Hardening
Security review, integration and end-to-end tests, performance measurement, backup testing, deployment configuration. TODO.

## Phase 10 — Release Assessment
Acceptance review and release-readiness report. TODO.
