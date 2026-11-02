/**
 * Typed client for the Hermes backend.
 *
 * Requests go to same-origin `/api/...` paths, which Next.js rewrites to the backend
 * (see next.config.ts). The session lives in an HttpOnly cookie the browser manages.
 * State-changing requests echo the CSRF token the server returned from login or /auth/me.
 */

export type Role = "owner" | "admin" | "member" | "viewer";

export interface User {
  id: string;
  email: string;
  full_name: string;
}

export interface AuthState {
  user: User;
  csrf_token: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan_code: string;
  role: Role;
}

export interface Member {
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  created_at: string;
  expires_at: string;
}

export interface CreatedInvitation extends Invitation {
  token: string;
}

export interface AuditEvent {
  id: number;
  action: string;
  outcome: string;
  actor_user_id: string | null;
  target_type: string | null;
  target_id: string | null;
  metadata: Record<string, unknown>;
  trace_id: string | null;
  created_at: string;
}

export type NodeKind =
  | "trigger"
  | "ai_agent"
  | "condition"
  | "transformation"
  | "crm"
  | "erp"
  | "database"
  | "email"
  | "http"
  | "approval"
  | "delay"
  | "end";

export interface WorkflowNodeDef {
  id: string;
  type: NodeKind;
  label: string;
  position: { x: number; y: number };
  config: Record<string, unknown>;
}

export interface WorkflowEdgeDef {
  id: string;
  source: string;
  target: string;
  source_handle: string | null;
  label: string;
}

export interface WorkflowDefinition {
  nodes: WorkflowNodeDef[];
  edges: WorkflowEdgeDef[];
}

export interface WorkflowIssue {
  code: string;
  severity: "error" | "warning";
  message: string;
  node_id: string | null;
}

export interface VersionMeta {
  id: string;
  version_number: number;
  status: "draft" | "published";
  revision: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
}

export interface WorkflowVersion extends VersionMeta {
  definition: WorkflowDefinition;
}

export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  active_version_number: number | null;
  latest_published_number: number | null;
  has_draft: boolean;
}

export interface WorkflowDetail {
  workflow: WorkflowSummary;
  versions: VersionMeta[];
  draft: WorkflowVersion | null;
  latest_published: WorkflowVersion | null;
  issues: WorkflowIssue[];
}

export interface DraftSaved {
  version: WorkflowVersion;
  issues: WorkflowIssue[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly messages: string[];
  /** Parsed response body, for errors that carry extra data such as publish issues. */
  readonly payload: unknown;

  constructor(status: number, messages: string[], payload: unknown = null) {
    super(messages[0] ?? "Request failed.");
    this.status = status;
    this.messages = messages;
    this.payload = payload;
  }
}

let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

function describeDetail(detail: unknown): string[] {
  if (typeof detail === "string") return [detail];
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object" && "msg" in item) return String((item as { msg: unknown }).msg);
      return "Invalid input.";
    });
  }
  return ["Something went wrong. Please try again."];
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  const response = await fetch(`/api/v1${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });

  if (response.status === 204) return undefined as T;

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload ? (payload as { detail: unknown }).detail : null;
    throw new ApiError(response.status, describeDetail(detail), payload);
  }
  return payload as T;
}

function adoptAuth(state: AuthState): AuthState {
  setCsrfToken(state.csrf_token);
  return state;
}

export const api = {
  auth: {
    register: (input: { email: string; full_name: string; password: string }) =>
      request<AuthState>("POST", "/auth/register", input).then(adoptAuth),
    login: (input: { email: string; password: string }) =>
      request<AuthState>("POST", "/auth/login", input).then(adoptAuth),
    logout: () => request<void>("POST", "/auth/logout").finally(() => setCsrfToken(null)),
    me: () => request<AuthState>("GET", "/auth/me").then(adoptAuth),
  },
  orgs: {
    list: () => request<Organization[]>("GET", "/orgs"),
    create: (name: string) => request<Organization>("POST", "/orgs", { name }),
    get: (orgId: string) => request<Organization>("GET", `/orgs/${orgId}`),
    rename: (orgId: string, name: string) => request<Organization>("PATCH", `/orgs/${orgId}`, { name }),
    members: (orgId: string) => request<Member[]>("GET", `/orgs/${orgId}/members`),
    changeRole: (orgId: string, userId: string, role: Role) =>
      request<Member>("PATCH", `/orgs/${orgId}/members/${userId}`, { role }),
    removeMember: (orgId: string, userId: string) =>
      request<void>("DELETE", `/orgs/${orgId}/members/${userId}`),
    invitations: (orgId: string) => request<Invitation[]>("GET", `/orgs/${orgId}/invitations`),
    invite: (orgId: string, input: { email: string; role: Role }) =>
      request<CreatedInvitation>("POST", `/orgs/${orgId}/invitations`, input),
    revokeInvitation: (orgId: string, invitationId: string) =>
      request<void>("DELETE", `/orgs/${orgId}/invitations/${invitationId}`),
    auditEvents: (orgId: string, limit = 50) =>
      request<AuditEvent[]>("GET", `/orgs/${orgId}/audit-events?limit=${limit}`),
  },
  invitations: {
    accept: (token: string) => request<Organization>("POST", "/invitations/accept", { token }),
  },
  workflows: {
    list: (orgId: string) => request<WorkflowSummary[]>("GET", `/orgs/${orgId}/workflows`),
    create: (orgId: string, input: { name: string; description?: string }) =>
      request<WorkflowDetail>("POST", `/orgs/${orgId}/workflows`, input),
    get: (orgId: string, workflowId: string) =>
      request<WorkflowDetail>("GET", `/orgs/${orgId}/workflows/${workflowId}`),
    update: (orgId: string, workflowId: string, input: { name?: string; description?: string }) =>
      request<WorkflowSummary>("PATCH", `/orgs/${orgId}/workflows/${workflowId}`, input),
    saveDraft: (orgId: string, workflowId: string, input: { definition: WorkflowDefinition; base_revision?: number }) =>
      request<DraftSaved>("PUT", `/orgs/${orgId}/workflows/${workflowId}/draft`, input),
    discardDraft: (orgId: string, workflowId: string) =>
      request<void>("DELETE", `/orgs/${orgId}/workflows/${workflowId}/draft`),
    validate: (orgId: string, workflowId: string, definition: WorkflowDefinition) =>
      request<WorkflowIssue[]>("POST", `/orgs/${orgId}/workflows/${workflowId}/validate`, definition),
    publish: (orgId: string, workflowId: string, baseRevision: number) =>
      request<WorkflowVersion>("POST", `/orgs/${orgId}/workflows/${workflowId}/publish`, {
        base_revision: baseRevision,
      }),
    activate: (orgId: string, workflowId: string, versionNumber: number) =>
      request<WorkflowSummary>("POST", `/orgs/${orgId}/workflows/${workflowId}/versions/${versionNumber}/activate`),
    deactivate: (orgId: string, workflowId: string) =>
      request<WorkflowSummary>("POST", `/orgs/${orgId}/workflows/${workflowId}/deactivate`),
    archive: (orgId: string, workflowId: string) =>
      request<void>("DELETE", `/orgs/${orgId}/workflows/${workflowId}`),
  },
};
