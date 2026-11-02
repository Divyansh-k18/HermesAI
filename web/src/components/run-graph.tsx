"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { memo, useMemo } from "react";

import type { ExecutionStatus, StepRecord, WorkflowDefinition } from "@/lib/api";
import { NODE_META } from "@/lib/workflow-meta";
import { NODE_HEIGHT, NODE_WIDTH } from "@/lib/workflow-layout";

/** What happened at a step in this run. "unreached" means the run never got there. */
type RunState = "succeeded" | "failed" | "waiting" | "cancelled" | "running" | "unreached";

interface RunNodeData extends Record<string, unknown> {
  kind: keyof typeof NODE_META;
  label: string;
  state: RunState;
  detail: string;
}

type RunNode = Node<RunNodeData, "run">;

const STATE_STYLE: Record<RunState, { border: string; chip: string; text: string }> = {
  succeeded: { border: "border-success/70", chip: "text-success", text: "done" },
  failed: { border: "border-danger", chip: "text-danger", text: "failed" },
  waiting: { border: "border-warning", chip: "text-warning", text: "waiting" },
  running: { border: "border-accent", chip: "text-accent-strong", text: "running" },
  cancelled: { border: "border-line-strong", chip: "text-muted", text: "cancelled" },
  unreached: { border: "border-line", chip: "text-faint", text: "not reached" },
};

const handleClass = "!size-2 !min-w-0 !border-0 !bg-transparent";

function RunNodeCardImpl({ data }: NodeProps<RunNode>) {
  const meta = NODE_META[data.kind];
  const style = STATE_STYLE[data.state];
  const dim = data.state === "unreached";
  return (
    <div
      data-run-status={data.state}
      style={{ width: NODE_WIDTH, minHeight: NODE_HEIGHT }}
      className={`relative cursor-pointer rounded-md border bg-surface-2 px-3 py-2 transition-opacity ${style.border} ${
        dim ? "opacity-45" : ""
      } ${data.state === "waiting" ? "run-pulse" : ""}`}
    >
      {!meta.noInput && <Handle type="target" position={Position.Left} className={handleClass} isConnectable={false} />}
      <div className="flex items-center justify-between gap-2">
        <span className="t-label truncate">{meta.label}</span>
        <span className={`font-mono text-[10px] ${style.chip}`}>{style.text}</span>
      </div>
      <p className="mt-1.5 truncate text-[13px] font-medium">{data.label || meta.label}</p>
      <p className="mt-0.5 truncate font-mono text-[11px] text-muted">{data.detail}</p>
      {!meta.noOutput && meta.handles.length === 0 && (
        <Handle type="source" position={Position.Right} className={handleClass} isConnectable={false} />
      )}
      {meta.handles.map((branch, index) => (
        <Handle
          key={branch.id}
          id={branch.id}
          type="source"
          position={Position.Right}
          style={{ top: `${((index + 1) / (meta.handles.length + 1)) * 100}%` }}
          className={handleClass}
          isConnectable={false}
        />
      ))}
    </div>
  );
}

const nodeTypes = { run: memo(RunNodeCardImpl) };

/** One line about what the step produced, taken from its recorded output. */
function describe(step: StepRecord | undefined): string {
  if (!step) return "";
  if (step.error) return step.error;
  const out = step.output;
  if (typeof out.decision === "string") return `${out.decision}${out.comment ? ` · “${out.comment}”` : ""}`;
  if (typeof out.result === "boolean") return `result: ${out.result}`;
  if (typeof out.status === "number") return `HTTP ${out.status}`;
  if (out.written && typeof out.written === "object") return `wrote ${Object.keys(out.written as object).join(", ")}`;
  if (typeof out.waiting_seconds === "number") return `waits ${out.waiting_seconds}s`;
  if (typeof out.outcome === "string") return out.outcome;
  return "";
}

export function RunGraph({
  definition,
  steps,
  runStatus,
  onSelectStep,
}: {
  definition: WorkflowDefinition;
  steps: StepRecord[];
  runStatus: ExecutionStatus;
  onSelectStep: (nodeId: string) => void;
}) {
  const { nodes, edges } = useMemo(() => {
    const ordered = [...steps].sort((a, b) => a.sequence - b.sequence);
    const lastByNode = new Map<string, StepRecord>();
    for (const step of ordered) lastByNode.set(step.node_id, step);

    // Connections the run actually travelled: each step to the next one in order.
    const taken = new Set<string>();
    for (let i = 0; i + 1 < ordered.length; i += 1) {
      taken.add(`${ordered[i].node_id}->${ordered[i + 1].node_id}`);
    }

    const flowNodes: RunNode[] = definition.nodes.map((node) => {
      const step = lastByNode.get(node.id);
      let state: RunState = "unreached";
      if (step) state = step.status === "waiting" ? "waiting" : (step.status as RunState);
      if (step?.status === "running" && runStatus !== "running") state = "failed";
      return {
        id: node.id,
        type: "run" as const,
        position: node.position,
        draggable: false,
        connectable: false,
        data: { kind: node.type, label: node.label, state, detail: describe(step) },
      };
    });

    const flowEdges: Edge[] = definition.edges.map((edge) => {
      const wasTaken = taken.has(`${edge.source}->${edge.target}`);
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.source_handle ?? undefined,
        label: edge.source_handle ?? undefined,
        type: "smoothstep",
        animated: wasTaken && runStatus === "running",
        style: wasTaken
          ? { stroke: "var(--accent)", strokeWidth: 2 }
          : { stroke: "var(--line-strong)", strokeDasharray: "4 4" },
        markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: wasTaken ? "var(--accent)" : "var(--line-strong)" },
      };
    });
    return { nodes: flowNodes, edges: flowEdges };
  }, [definition, steps, runStatus]);

  return (
    <div className="h-[340px] border border-line bg-bg" aria-label="Path this run took through the workflow">
      <ReactFlow<RunNode, Edge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        onNodeClick={(_, node) => onSelectStep(node.id)}
        colorMode="dark"
        fitView
        fitViewOptions={{ padding: 0.15, minZoom: 0.45, maxZoom: 1 }}
        minZoom={0.3}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
      </ReactFlow>
    </div>
  );
}
