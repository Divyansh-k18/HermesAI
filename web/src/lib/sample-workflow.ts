import type { WorkflowDefinition } from "@/lib/api";

export const SAMPLE_WORKFLOW_NAME = "Sales order approval (sample)";

/**
 * A sales-order flow built only from steps the engine can run today. Orders above ₹50,000 pause for a
 * manager. Approved orders continue, and rejected orders end on their own branch.
 */
export const SAMPLE_WORKFLOW: WorkflowDefinition = {
  nodes: [
    { id: "trigger", type: "trigger", label: "Order received", position: { x: 0, y: 140 }, config: { event: "manual" } },
    {
      id: "capture",
      type: "transformation",
      label: "Capture order total",
      position: { x: 280, y: 140 },
      config: { mappings: [{ source: "order.total", target: "summary.total" }] },
    },
    {
      id: "check",
      type: "condition",
      label: "Order over ₹50,000?",
      position: { x: 560, y: 140 },
      config: { field: "order.total", operator: "gt", value: 50000 },
    },
    {
      id: "approval",
      type: "approval",
      label: "Manager approval",
      position: { x: 840, y: 40 },
      config: { approver_role: "admin", title: "Approve order over ₹50,000" },
    },
    {
      id: "mark",
      type: "transformation",
      label: "Mark order approved",
      position: { x: 1120, y: 0 },
      config: { mappings: [{ source: "order.id", target: "approved_order_id" }] },
    },
    { id: "done", type: "end", label: "Approved", position: { x: 1400, y: 0 }, config: {} },
    { id: "rejected", type: "end", label: "Rejected", position: { x: 1120, y: 150 }, config: {} },
    { id: "auto", type: "end", label: "Auto-approved (small order)", position: { x: 840, y: 280 }, config: {} },
  ],
  edges: [
    { id: "e1", source: "trigger", target: "capture", source_handle: null, label: "" },
    { id: "e2", source: "capture", target: "check", source_handle: null, label: "" },
    { id: "e3", source: "check", target: "approval", source_handle: "true", label: "true" },
    { id: "e4", source: "check", target: "auto", source_handle: "false", label: "false" },
    { id: "e5", source: "approval", target: "mark", source_handle: "approved", label: "approved" },
    { id: "e6", source: "approval", target: "rejected", source_handle: "rejected", label: "rejected" },
    { id: "e7", source: "mark", target: "done", source_handle: null, label: "" },
  ],
};

export const SAMPLE_EMAIL_WORKFLOW_NAME = "Email order approval (sample)";

/**
 * Orders that arrive by email. A customer writes lines such as "Total: 75,000" and "Customer: Asha Traders";
 * Hermes reads them as email.fields.total and email.fields.customer. Orders above ₹50,000 wait for a manager.
 */
export const SAMPLE_EMAIL_WORKFLOW: WorkflowDefinition = {
  nodes: [
    { id: "trigger", type: "trigger", label: "Order email received", position: { x: 0, y: 140 }, config: { event: "email.received" } },
    {
      id: "capture",
      type: "transformation",
      label: "Read order from email",
      position: { x: 280, y: 140 },
      config: {
        mappings: [
          { source: "email.fields.total", target: "order.total" },
          { source: "email.from", target: "order.customer_email" },
        ],
      },
    },
    {
      id: "check",
      type: "condition",
      label: "Order over ₹50,000?",
      position: { x: 560, y: 140 },
      config: { field: "order.total", operator: "gt", value: 50000 },
    },
    {
      id: "approval",
      type: "approval",
      label: "Manager approval",
      position: { x: 840, y: 40 },
      config: { approver_role: "admin", title: "Approve emailed order over ₹50,000" },
    },
    { id: "done", type: "end", label: "Approved", position: { x: 1120, y: 0 }, config: {} },
    { id: "rejected", type: "end", label: "Rejected", position: { x: 1120, y: 150 }, config: {} },
    { id: "auto", type: "end", label: "Auto-approved (small order)", position: { x: 840, y: 280 }, config: {} },
  ],
  edges: [
    { id: "e1", source: "trigger", target: "capture", source_handle: null, label: "" },
    { id: "e2", source: "capture", target: "check", source_handle: null, label: "" },
    { id: "e3", source: "check", target: "approval", source_handle: "true", label: "true" },
    { id: "e4", source: "check", target: "auto", source_handle: "false", label: "false" },
    { id: "e5", source: "approval", target: "done", source_handle: "approved", label: "approved" },
    { id: "e6", source: "approval", target: "rejected", source_handle: "rejected", label: "rejected" },
  ],
};

export const SAMPLE_AI_EMAIL_WORKFLOW_NAME = "AI email order approval (sample)";

/**
 * Customers write orders in their own words. The AI step reads the email into a structured order; plain rules
 * then decide. Unclear emails and stock problems go to a person, orders under ₹1,000 are approved automatically,
 * and everything else waits for a manager.
 */
export const SAMPLE_AI_EMAIL_WORKFLOW: WorkflowDefinition = {
  nodes: [
    { id: "trigger", type: "trigger", label: "Order email received", position: { x: 0, y: 160 }, config: { event: "email.received" } },
    {
      id: "ai",
      type: "ai_agent",
      label: "AI reads the order",
      position: { x: 280, y: 160 },
      config: { task: "extract_order", input_path: "email.body", result_path: "order" },
    },
    {
      id: "found",
      type: "condition",
      label: "Total found?",
      position: { x: 560, y: 160 },
      config: { field: "order.total", operator: "exists" },
    },
    {
      id: "sure",
      type: "condition",
      label: "AI confident?",
      position: { x: 840, y: 60 },
      config: { field: "order.confidence", operator: "gte", value: 0.6 },
    },
    {
      id: "stock",
      type: "inventory",
      label: "Check stock",
      position: { x: 1120, y: -20 },
      config: { items_path: "order.items", result_path: "stock" },
    },
    {
      id: "available",
      type: "condition",
      label: "All items in stock?",
      position: { x: 1400, y: -20 },
      config: { field: "stock.status", operator: "eq", value: "in_stock" },
    },
    {
      id: "small",
      type: "condition",
      label: "Order under ₹1,000?",
      position: { x: 1680, y: -100 },
      config: { field: "order.total", operator: "lt", value: 1000 },
    },
    {
      id: "manager",
      type: "approval",
      label: "Manager approval",
      position: { x: 1960, y: -200 },
      config: { approver_role: "admin", title: "Approve ₹{{order.total}} order from {{order.customer_name}}" },
    },
    {
      id: "shortage",
      type: "approval",
      label: "Stock problem",
      position: { x: 1680, y: 120 },
      config: { approver_role: "admin", title: "Stock problem: {{stock.summary}}. Accept as backorder?" },
    },
    {
      id: "review",
      type: "approval",
      label: "Person checks the email",
      position: { x: 1120, y: 320 },
      config: { approver_role: "admin", title: "Check unclear order email" },
    },
    { id: "approved", type: "end", label: "Approved", position: { x: 2240, y: -260 }, config: {} },
    { id: "rejected", type: "end", label: "Rejected", position: { x: 2240, y: -130 }, config: {} },
    { id: "auto", type: "end", label: "Auto-approved (under ₹1,000)", position: { x: 1960, y: 0 }, config: {} },
    { id: "backorder", type: "end", label: "Accepted as backorder", position: { x: 1960, y: 120 }, config: {} },
    { id: "nostock", type: "end", label: "Declined: no stock", position: { x: 1960, y: 240 }, config: {} },
    { id: "confirmed", type: "end", label: "Confirmed after review", position: { x: 1400, y: 280 }, config: {} },
    { id: "declined", type: "end", label: "Not an order", position: { x: 1400, y: 400 }, config: {} },
  ],
  edges: [
    { id: "e1", source: "trigger", target: "ai", source_handle: null, label: "" },
    { id: "e2", source: "ai", target: "found", source_handle: null, label: "" },
    { id: "e3", source: "found", target: "sure", source_handle: "true", label: "true" },
    { id: "e4", source: "found", target: "review", source_handle: "false", label: "false" },
    { id: "e5", source: "sure", target: "stock", source_handle: "true", label: "true" },
    { id: "e6", source: "sure", target: "review", source_handle: "false", label: "false" },
    { id: "e7", source: "stock", target: "available", source_handle: null, label: "" },
    { id: "e8", source: "available", target: "small", source_handle: "true", label: "true" },
    { id: "e9", source: "available", target: "shortage", source_handle: "false", label: "false" },
    { id: "e10", source: "small", target: "auto", source_handle: "true", label: "true" },
    { id: "e11", source: "small", target: "manager", source_handle: "false", label: "false" },
    { id: "e12", source: "manager", target: "approved", source_handle: "approved", label: "approved" },
    { id: "e13", source: "manager", target: "rejected", source_handle: "rejected", label: "rejected" },
    { id: "e14", source: "shortage", target: "backorder", source_handle: "approved", label: "approved" },
    { id: "e15", source: "shortage", target: "nostock", source_handle: "rejected", label: "rejected" },
    { id: "e16", source: "review", target: "confirmed", source_handle: "approved", label: "approved" },
    { id: "e17", source: "review", target: "declined", source_handle: "rejected", label: "rejected" },
  ],
};

/** A realistic order written in a customer's own words, used to prefill runs of workflows with an AI step. */
export const SAMPLE_ORDER_EMAIL =
  "Hi team,\n\nThis is Asha from Asha Traders. Please send 50 boxes of A4 paper and 20 packs of blue pens to our " +
  "Pune warehouse by Friday. As per your quote the total comes to Rs 78,000.\n\nThanks,\nAsha";

/** Builds an example run payload from the fields a workflow reads, so people start from something valid. */
export function payloadTemplate(definition: WorkflowDefinition): Record<string, unknown> {
  const result: Record<string, unknown> = {};

  const put = (path: string, value: unknown) => {
    const parts = path.split(".").filter(Boolean);
    if (parts.length === 0) return;
    let current = result;
    for (const part of parts.slice(0, -1)) {
      if (typeof current[part] !== "object" || current[part] === null) current[part] = {};
      current = current[part] as Record<string, unknown>;
    }
    const last = parts[parts.length - 1];
    if (!(last in current)) current[last] = value;
  };

  const written = new Set<string>();
  // Paths an AI step fills in, such as order. Everything under them comes from the AI, not the payload.
  const aiResults: string[] = [];
  for (const node of definition.nodes) {
    if (node.type === "transformation" && Array.isArray(node.config.mappings)) {
      for (const mapping of node.config.mappings as { target?: string }[]) {
        if (mapping.target) written.add(mapping.target);
      }
    }
    if (node.type === "ai_agent") {
      const input = typeof node.config.input_path === "string" && node.config.input_path ? node.config.input_path : "email.body";
      const output = typeof node.config.result_path === "string" && node.config.result_path ? node.config.result_path : "order";
      put(input, SAMPLE_ORDER_EMAIL);
      aiResults.push(output);
    }
  }
  const fromAI = (field: string) => aiResults.some((path) => field === path || field.startsWith(`${path}.`));

  // A value each condition accepts, so the example run takes a meaningful path instead of failing a comparison.
  const examples = new Map<string, unknown>();
  for (const node of definition.nodes) {
    if (node.type !== "condition" || typeof node.config.field !== "string") continue;
    const target = typeof node.config.value === "number" ? node.config.value : Number(node.config.value);
    const operator = node.config.operator;
    let example: unknown = node.config.value ?? "";
    if (Number.isFinite(target) && (operator === "gt" || operator === "gte")) example = Math.round(target * 1.5);
    else if (Number.isFinite(target) && (operator === "lt" || operator === "lte")) example = Math.round(target / 2);
    if (!examples.has(node.config.field)) examples.set(node.config.field, example);
    if (!written.has(node.config.field) && !fromAI(node.config.field)) put(node.config.field, example);
  }
  for (const node of definition.nodes) {
    if (node.type === "transformation" && Array.isArray(node.config.mappings)) {
      for (const mapping of node.config.mappings as { source?: string; target?: string }[]) {
        if (!mapping.source || written.has(mapping.source)) continue;
        // A copied field gets the value its condition checks, e.g. email.fields.total -> order.total > 50000.
        const checked = mapping.target ? examples.get(mapping.target) : undefined;
        const looksLikeEmail = /(^|\.)(from|email)$/.test(mapping.source) || /email$/.test(mapping.target ?? "");
        put(mapping.source, checked !== undefined ? checked : looksLikeEmail ? "customer@example.com" : "example");
      }
    }
  }
  return result;
}
