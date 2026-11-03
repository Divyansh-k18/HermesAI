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
  | "inventory"
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

export type ExecutionStatus =
  | "running"
  | "waiting_approval"
  | "waiting_timer"
  | "succeeded"
  | "failed"
  | "rejected"
  | "cancelled";

export interface ExecutionSummary {
  id: string;
  workflow_id: string;
  workflow_name: string;
  version_number: number;
  status: ExecutionStatus;
  started_at: string;
  finished_at: string | null;
  error: string | null;
}

export interface StepRecord {
  id: string;
  sequence: number;
  node_id: string;
  node_type: NodeKind;
  node_label: string;
  status: "running" | "waiting" | "succeeded" | "failed" | "cancelled";
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface ApprovalItem {
  id: string;
  execution_id: string;
  workflow_id: string;
  workflow_name: string;
  title: string;
  approver_role: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  context: Record<string, unknown>;
  requested_at: string;
  decided_by_name: string | null;
  decided_at: string | null;
  comment: string;
  can_decide: boolean;
}

export interface EmailInboxInfo {
  enabled: boolean;
  imap_host: string | null;
  username: string | null;
  folder: string | null;
  allowed_senders: string | null;
  last_checked_at: string | null;
  last_error: string | null;
  runs_started: number;
  recent_emails: RecentEmail[];
}

/** An email that started a run. */
export interface RecentEmail {
  run_id: string;
  received_at: string;
  sender: string | null;
  subject: string | null;
  status: ExecutionStatus;
}

export interface InventoryItem {
  id: string;
  name: string;
  sku: string | null;
  quantity: number;
  unit: string;
  unit_price: number | null;
  updated_at: string;
}

export interface EmailCheckResult {
  started: number;
  ignored: number;
  duplicates: number;
  error: string | null;
  run_ids: string[];
}

export interface ConnectionItem {
  id: string;
  name: string;
  kind: string;
  header_name: string;
  created_at: string;
}

/** Whether AI steps can run on this server. The key itself never leaves the server. */
export interface AIStatus {
  configured: boolean;
  model: string | null;
  provider: string | null;
}

export interface WebhookInfo {
  enabled: boolean;
  path: string | null;
  created_at: string | null;
  rotated_at: string | null;
  last_received_at: string | null;
}

export interface WebhookSecret extends WebhookInfo {
  secret: string;
}

export interface WebhookEventItem {
  event_id: string;
  status: "accepted" | "failed";
  execution_id: string | null;
  error: string | null;
  received_at: string;
}

export interface ExecutionDetail extends ExecutionSummary {
  trigger_type: string;
  trigger_payload: Record<string, unknown>;
  variables: Record<string, unknown>;
  outcome: string | null;
  trace_id: string | null;
  steps: StepRecord[];
  approvals: ApprovalItem[];
}

export interface Metrics {
  total_runs: number;
  by_status: Record<string, number>;
  pending_approvals: number;
  active_workflows: number;
  total_workflows: number;
  average_duration_seconds: number | null;
  last_7_days: { date: string; succeeded: number; failed: number; rejected: number }[];
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
    if (response.status >= 500 && payload === null) {
      // The proxy answered, not the API: the backend is down or unreachable.
      throw new ApiError(response.status, [SERVER_UNREACHABLE], null);
    }
    const detail = payload && typeof payload === "object" && "detail" in payload ? (payload as { detail: unknown }).detail : null;
    throw new ApiError(response.status, describeDetail(detail), payload);
  }
  return payload as T;
}

export const SERVER_UNREACHABLE = "Cannot reach the Hermes server. Make sure the backend is running, then try again.";

/** True when an error means the API could not be reached or failed, rather than refusing a request. */
export function isServerProblem(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 500;
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
    version: (orgId: string, workflowId: string, versionNumber: number) =>
      request<WorkflowVersion>("GET", `/orgs/${orgId}/workflows/${workflowId}/versions/${versionNumber}`),
    webhook: (orgId: string, workflowId: string) =>
      request<WebhookInfo>("GET", `/orgs/${orgId}/workflows/${workflowId}/webhook`),
    createOrRotateWebhook: (orgId: string, workflowId: string) =>
      request<WebhookSecret>("POST", `/orgs/${orgId}/workflows/${workflowId}/webhook`),
    deleteWebhook: (orgId: string, workflowId: string) =>
      request<void>("DELETE", `/orgs/${orgId}/workflows/${workflowId}/webhook`),
    emailInbox: (orgId: string, workflowId: string) =>
      request<EmailInboxInfo>("GET", `/orgs/${orgId}/workflows/${workflowId}/email-inbox`),
    connectEmailInbox: (
      orgId: string,
      workflowId: string,
      input: { imap_host: string; username: string; password?: string; folder?: string; allowed_senders?: string },
    ) => request<EmailInboxInfo>("PUT", `/orgs/${orgId}/workflows/${workflowId}/email-inbox`, input),
    checkEmailInbox: (orgId: string, workflowId: string) =>
      request<EmailCheckResult>("POST", `/orgs/${orgId}/workflows/${workflowId}/email-inbox/check`),
    disconnectEmailInbox: (orgId: string, workflowId: string) =>
      request<void>("DELETE", `/orgs/${orgId}/workflows/${workflowId}/email-inbox`),
    webhookEvents: (orgId: string, workflowId: string) =>
      request<WebhookEventItem[]>("GET", `/orgs/${orgId}/workflows/${workflowId}/webhook/events`),
    run: (orgId: string, workflowId: string, input: { payload: Record<string, unknown>; idempotency_key?: string }) =>
      request<ExecutionDetail>("POST", `/orgs/${orgId}/workflows/${workflowId}/executions`, input),
  },
  executions: {
    list: (orgId: string, params: { status?: string; workflow_id?: string } = {}) => {
      const query = new URLSearchParams();
      if (params.status) query.set("status", params.status);
      if (params.workflow_id) query.set("workflow_id", params.workflow_id);
      const suffix = query.toString() ? `?${query.toString()}` : "";
      return request<ExecutionSummary[]>("GET", `/orgs/${orgId}/executions${suffix}`);
    },
    get: (orgId: string, executionId: string) =>
      request<ExecutionDetail>("GET", `/orgs/${orgId}/executions/${executionId}`),
    cancel: (orgId: string, executionId: string) =>
      request<ExecutionDetail>("POST", `/orgs/${orgId}/executions/${executionId}/cancel`),
  },
  approvals: {
    list: (orgId: string, status: "pending" | "decided" | "all" = "pending") =>
      request<ApprovalItem[]>("GET", `/orgs/${orgId}/approvals?status=${status}`),
    decide: (orgId: string, approvalId: string, input: { decision: "approve" | "reject"; comment?: string }) =>
      request<ExecutionDetail>("POST", `/orgs/${orgId}/approvals/${approvalId}/decision`, input),
  },
  metrics: {
    get: (orgId: string) => request<Metrics>("GET", `/orgs/${orgId}/metrics`),
  },
  connections: {
    list: (orgId: string) => request<ConnectionItem[]>("GET", `/orgs/${orgId}/connections`),
    create: (orgId: string, input: { name: string; header_name: string; secret: string }) =>
      request<ConnectionItem>("POST", `/orgs/${orgId}/connections`, input),
    remove: (orgId: string, connectionId: string) =>
      request<void>("DELETE", `/orgs/${orgId}/connections/${connectionId}`),
  },
  ai: {
    status: () => request<AIStatus>("GET", "/ai/status"),
  },
  inventory: {
    list: (orgId: string) => request<InventoryItem[]>("GET", `/orgs/${orgId}/inventory`),
    create: (
      orgId: string,
      input: { name: string; quantity: number; unit?: string; unit_price?: number | null; sku?: string | null },
    ) => request<InventoryItem>("POST", `/orgs/${orgId}/inventory`, input),
    update: (orgId: string, itemId: string, input: Partial<Omit<InventoryItem, "id" | "updated_at">>) =>
      request<InventoryItem>("PATCH", `/orgs/${orgId}/inventory/${itemId}`, input),
    remove: (orgId: string, itemId: string) => request<void>("DELETE", `/orgs/${orgId}/inventory/${itemId}`),
    /** Adds the demo office-supply items that are missing. Existing items are left alone. */
    addSamples: (orgId: string) => request<InventoryItem[]>("POST", `/orgs/${orgId}/inventory/sample`),
  },
};
