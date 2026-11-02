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
  for (const node of definition.nodes) {
    if (node.type === "transformation" && Array.isArray(node.config.mappings)) {
      for (const mapping of node.config.mappings as { target?: string }[]) {
        if (mapping.target) written.add(mapping.target);
      }
    }
  }

  for (const node of definition.nodes) {
    if (node.type === "condition" && typeof node.config.field === "string" && !written.has(node.config.field)) {
      const target = typeof node.config.value === "number" ? node.config.value : Number(node.config.value);
      const operator = node.config.operator;
      if (Number.isFinite(target) && (operator === "gt" || operator === "gte")) put(node.config.field, Math.round(target * 1.5));
      else if (Number.isFinite(target) && (operator === "lt" || operator === "lte")) put(node.config.field, Math.round(target / 2));
      else put(node.config.field, node.config.value ?? "");
    }
  }
  for (const node of definition.nodes) {
    if (node.type === "transformation" && Array.isArray(node.config.mappings)) {
      for (const mapping of node.config.mappings as { source?: string }[]) {
        if (mapping.source && !written.has(mapping.source)) put(mapping.source, "example");
      }
    }
  }
  return result;
}
