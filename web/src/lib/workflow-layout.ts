import { graphlib, layout } from "@dagrejs/dagre";

import type { FlowEdge, FlowNode } from "@/lib/workflow-meta";

export const NODE_WIDTH = 208;
export const NODE_HEIGHT = 68;

/** Arranges nodes left to right by dependency order. Returns new nodes; does not mutate its input. */
export function autoLayout(nodes: FlowNode[], edges: FlowEdge[]): FlowNode[] {
  if (nodes.length === 0) return nodes;
  const graph = new graphlib.Graph();
  graph.setGraph({ rankdir: "LR", nodesep: 36, ranksep: 72, marginx: 24, marginy: 24 });
  graph.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  const known = new Set(nodes.map((node) => node.id));
  for (const edge of edges) {
    if (known.has(edge.source) && known.has(edge.target)) graph.setEdge(edge.source, edge.target);
  }

  layout(graph);

  return nodes.map((node) => {
    const placed = graph.node(node.id);
    return { ...node, position: { x: Math.round(placed.x - NODE_WIDTH / 2), y: Math.round(placed.y - NODE_HEIGHT / 2) } };
  });
}
