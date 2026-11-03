"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { memo } from "react";

import { NODE_META, type FlowNode } from "@/lib/workflow-meta";
import { NODE_HEIGHT, NODE_WIDTH } from "@/lib/workflow-layout";

/** One line describing what the node is configured to do, shown under its title. */
function summarize(node: FlowNode["data"]): string {
  const { kind, config } = node;
  const text = (key: string) => (typeof config[key] === "string" ? (config[key] as string) : "");
  switch (kind) {
    case "trigger":
      return text("event");
    case "ai_agent":
      return text("task") === "extract_order"
        ? `read order from ${text("input_path") || "email.body"}`
        : text("instructions");
    case "condition":
      return text("field") ? `${text("field")} ${text("operator")} ${config.value ?? ""}`.trim() : "";
    case "crm":
    case "erp":
    case "database":
      return [text("integration"), text("action")].filter(Boolean).join(" · ");
    case "email":
      return text("subject");
    case "http":
      return text("url") ? `${text("method")} ${text("url")}` : "";
    case "approval":
      return text("approver_role") ? `approver: ${text("approver_role")}` : "";
    case "delay":
      return typeof config.seconds === "number" ? `${config.seconds}s` : "";
    case "transformation":
      return Array.isArray(config.mappings) ? `${config.mappings.length} mapping(s)` : "";
    case "end":
      return "This path finishes here";
    default:
      return "";
  }
}

function NodeCardImpl({ data, selected }: NodeProps<FlowNode>) {
  const meta = NODE_META[data.kind];
  const summary = summarize(data);
  const hasIssues = data.issueCount > 0;
  const branches = meta.handles;

  return (
    <div
      style={{ width: NODE_WIDTH, minHeight: NODE_HEIGHT }}
      className={`relative rounded-md border bg-surface-2 px-3 py-2 transition-colors ${
        selected ? "border-accent" : hasIssues ? "border-danger/60" : "border-line-strong"
      }`}
    >
      {!meta.noInput && (
        <Handle
          type="target"
          position={Position.Left}
          className="!size-2.5 !rounded-[2px] !border !border-line-strong !bg-surface-3"
        />
      )}

      <div className="flex items-center justify-between gap-2">
        <span className="t-label truncate">{meta.label}</span>
        {hasIssues && (
          <span
            title={`${data.issueCount} issue${data.issueCount === 1 ? "" : "s"}`}
            className="rounded-sm border border-danger/50 px-1 font-mono text-[10px] leading-4 text-danger"
          >
            {data.issueCount}
          </span>
        )}
      </div>
      <p className="mt-1.5 truncate text-[13px] font-medium">{data.label || meta.label}</p>
      <p className="mt-0.5 truncate font-mono text-[11px] text-muted">{summary || "Not configured"}</p>

      {!meta.noOutput && branches.length === 0 && (
        <Handle
          type="source"
          position={Position.Right}
          className="!size-2.5 !rounded-[2px] !border !border-accent !bg-surface-3"
        />
      )}
      {branches.map((branch, index) => {
        const top = `${((index + 1) / (branches.length + 1)) * 100}%`;
        return (
          <div key={branch.id}>
            <Handle
              id={branch.id}
              type="source"
              position={Position.Right}
              style={{ top }}
              className="!size-2.5 !rounded-[2px] !border !border-accent !bg-surface-3"
            />
            <span
              style={{ top }}
              className="pointer-events-none absolute right-3 -translate-y-1/2 font-mono text-[10px] text-faint"
            >
              {branch.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export const NodeCard = memo(NodeCardImpl);
