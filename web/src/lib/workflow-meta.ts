import type { Edge, Node } from "@xyflow/react";

import type { NodeKind, WorkflowDefinition } from "@/lib/api";

export type FieldKind = "text" | "textarea" | "select" | "number" | "scalar" | "list" | "mappings" | "connection";

export interface FieldDef {
  key: string;
  label: string;
  kind: FieldKind;
  options?: { value: string; label: string }[];
  placeholder?: string;
  hint?: string;
}

export interface NodeMeta {
  label: string;
  description: string;
  /** Short group label shown in the palette. */
  group: "Flow" | "Logic" | "Systems" | "Human";
  fields: FieldDef[];
  /** Named outputs. Nodes without any have a single unnamed output. */
  handles: { id: string; label: string }[];
  /** Nodes that cannot receive connections. */
  noInput?: boolean;
  /** Nodes that cannot start connections. */
  noOutput?: boolean;
}

const opt = (...values: string[]) => values.map((value) => ({ value, label: value }));

export const NODE_META: Record<NodeKind, NodeMeta> = {
  trigger: {
    label: "Trigger",
    description: "The event that starts the workflow.",
    group: "Flow",
    noInput: true,
    handles: [],
    fields: [
      {
        key: "event",
        label: "Event",
        kind: "select",
        options: [
          { value: "hubspot.order.created", label: "HubSpot: order created" },
          { value: "hubspot.deal.created", label: "HubSpot: deal created" },
          { value: "email.received", label: "Email: order received" },
          { value: "manual", label: "Manual start" },
        ],
      },
    ],
  },
  ai_agent: {
    label: "AI Agent",
    description: "Reads free-form text, such as an order email, and turns it into structured data.",
    group: "Logic",
    handles: [],
    fields: [
      {
        key: "task",
        label: "Task",
        kind: "select",
        options: [{ value: "extract_order", label: "Read an order from text" }],
        hint: "The AI only reads. Your conditions and approvals decide what happens next.",
      },
      {
        key: "input_path",
        label: "Read text from",
        kind: "text",
        placeholder: "email.body",
        hint: "Where the text is in the run data. Order emails put it in email.body.",
      },
      {
        key: "instructions",
        label: "Guidance (optional)",
        kind: "textarea",
        placeholder: "We sell paper and stationery. Prices are in rupees.",
        hint: "Background that helps the AI read your customers' emails. Up to 4,000 characters.",
      },
      {
        key: "result_path",
        label: "Save result as",
        kind: "text",
        placeholder: "order",
        hint: "Later steps read order.total, order.confidence, order.customer_name and order.items.",
      },
    ],
  },
  condition: {
    label: "Condition",
    description: "Sends the flow down a true or false branch.",
    group: "Logic",
    handles: [
      { id: "true", label: "true" },
      { id: "false", label: "false" },
    ],
    fields: [
      { key: "field", label: "Field", kind: "text", placeholder: "order.total" },
      {
        key: "operator",
        label: "Operator",
        kind: "select",
        options: [
          { value: "eq", label: "equals" },
          { value: "neq", label: "does not equal" },
          { value: "gt", label: "is greater than" },
          { value: "gte", label: "is at least" },
          { value: "lt", label: "is less than" },
          { value: "lte", label: "is at most" },
          { value: "contains", label: "contains" },
          { value: "exists", label: "exists" },
        ],
      },
      { key: "value", label: "Value", kind: "scalar", placeholder: "50000" },
    ],
  },
  transformation: {
    label: "Transform",
    description: "Maps fields from earlier steps into new names.",
    group: "Logic",
    handles: [],
    fields: [{ key: "mappings", label: "Field mappings", kind: "mappings" }],
  },
  crm: {
    label: "CRM",
    description: "Reads or updates records in your CRM.",
    group: "Systems",
    handles: [],
    fields: [
      { key: "integration", label: "Integration", kind: "select", options: opt("hubspot") },
      { key: "action", label: "Action", kind: "select", options: opt("get_customer", "update_deal", "add_note") },
    ],
  },
  erp: {
    label: "ERP",
    description: "Reads or writes business records in your ERP.",
    group: "Systems",
    handles: [],
    fields: [
      { key: "integration", label: "Integration", kind: "select", options: opt("erpnext") },
      { key: "action", label: "Action", kind: "select", options: opt("check_stock", "create_sales_order") },
    ],
  },
  database: {
    label: "Database",
    description: "Runs a read or write against a connected database.",
    group: "Systems",
    handles: [],
    fields: [
      { key: "integration", label: "Integration", kind: "select", options: opt("postgresql") },
      { key: "action", label: "Action", kind: "select", options: opt("query", "insert", "update") },
    ],
  },
  email: {
    label: "Email",
    description: "Sends an email through a connected provider.",
    group: "Systems",
    handles: [],
    fields: [
      { key: "to", label: "To", kind: "text", placeholder: "{{customer.email}}" },
      { key: "subject", label: "Subject", kind: "text" },
      { key: "body", label: "Message", kind: "textarea" },
    ],
  },
  http: {
    label: "HTTP request",
    description: "Calls an outside HTTPS API and saves the response for later steps.",
    group: "Systems",
    handles: [],
    fields: [
      { key: "method", label: "Method", kind: "select", options: opt("GET", "POST", "PUT", "PATCH", "DELETE") },
      {
        key: "url",
        label: "URL",
        kind: "text",
        placeholder: "https://api.example.com/orders",
        hint: "HTTPS only. Private and internal addresses are blocked, and redirects are not followed.",
      },
      {
        key: "connection_id",
        label: "Connection",
        kind: "connection",
        hint: "Adds a stored credential header. Manage connections on the Integrations page.",
      },
      {
        key: "body_path",
        label: "Send data from",
        kind: "text",
        placeholder: "order",
        hint: "Optional. Sends this part of the run data as the JSON body.",
      },
      {
        key: "result_path",
        label: "Save response as",
        kind: "text",
        placeholder: "http_response",
        hint: "Later steps can read the status and body from here.",
      },
    ],
  },
  inventory: {
    label: "Check stock",
    description: "Compares each ordered item with your inventory and marks it available, short, or not stocked.",
    group: "Systems",
    handles: [],
    fields: [
      {
        key: "items_path",
        label: "Order lines from",
        kind: "text",
        placeholder: "order.items",
        hint: "A list of items with a name and quantity. The AI step saves them in order.items.",
      },
      {
        key: "result_path",
        label: "Save result as",
        kind: "text",
        placeholder: "stock",
        hint: "Later steps can check stock.status: in_stock, short, or needs_check.",
      },
    ],
  },
  approval: {
    label: "Approval",
    description: "Pauses until a person approves or rejects.",
    group: "Human",
    handles: [
      { id: "approved", label: "approved" },
      { id: "rejected", label: "rejected" },
    ],
    fields: [
      { key: "approver_role", label: "Approver", kind: "select", options: opt("admin", "owner") },
      { key: "title", label: "Request title", kind: "text", placeholder: "Approve order over ₹50,000" },
    ],
  },
  delay: {
    label: "Delay",
    description: "Waits before continuing.",
    group: "Flow",
    handles: [],
    fields: [{ key: "seconds", label: "Seconds", kind: "number", hint: "1 second to 30 days (2,592,000)." }],
  },
  end: {
    label: "End",
    description: "Finishes this path of the workflow.",
    group: "Flow",
    noOutput: true,
    handles: [],
    fields: [],
  },
};

export const PALETTE_ORDER: NodeKind[] = [
  "trigger",
  "ai_agent",
  "condition",
  "transformation",
  "crm",
  "erp",
  "database",
  "email",
  "http",
  "inventory",
  "approval",
  "delay",
  "end",
];

export function defaultConfig(kind: NodeKind): Record<string, unknown> {
  switch (kind) {
    case "trigger":
      return { event: "manual" };
    case "ai_agent":
      return { task: "extract_order", input_path: "email.body", result_path: "order" };
    case "condition":
      return { operator: "eq" };
    case "crm":
      return { integration: "hubspot" };
    case "erp":
      return { integration: "erpnext" };
    case "database":
      return { integration: "postgresql" };
    case "http":
      return { method: "GET" };
    case "inventory":
      return { items_path: "order.items", result_path: "stock" };
    case "approval":
      return { approver_role: "admin" };
    case "delay":
      return { seconds: 60 };
    default:
      return {};
  }
}

export function newNodeId(kind: NodeKind): string {
  const random = Math.random().toString(36).slice(2, 8);
  return `${kind}-${random}`;
}

// --------------------------------------------------------------------------- React Flow conversion

export interface FlowNodeData extends Record<string, unknown> {
  kind: NodeKind;
  label: string;
  config: Record<string, unknown>;
  issueCount: number;
}

export type FlowNode = Node<FlowNodeData, "hermes">;
export type FlowEdge = Edge;

export function toFlow(definition: WorkflowDefinition): { nodes: FlowNode[]; edges: FlowEdge[] } {
  return {
    nodes: definition.nodes.map((node) => ({
      id: node.id,
      type: "hermes" as const,
      position: node.position,
      data: { kind: node.type, label: node.label, config: node.config, issueCount: 0 },
    })),
    edges: definition.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.source_handle ?? undefined,
      label: edge.label || undefined,
    })),
  };
}

export function fromFlow(nodes: FlowNode[], edges: FlowEdge[]): WorkflowDefinition {
  return {
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.data.kind,
      label: node.data.label,
      position: { x: Math.round(node.position.x), y: Math.round(node.position.y) },
      config: node.data.config,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_handle: edge.sourceHandle ?? null,
      label: typeof edge.label === "string" ? edge.label : "",
    })),
  };
}
