"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Inspector } from "@/components/workflow/inspector";
import { NodeCard } from "@/components/workflow/node-card";
import { RunDialog } from "@/components/workflow/run-dialog";
import { EmailInboxPanel } from "@/components/workflow/email-panel";
import { WebhookPanel } from "@/components/workflow/webhook-panel";
import { payloadTemplate } from "@/lib/sample-workflow";
import { Badge, Button, EmptyState, Skeleton } from "@/components/ui";
import {
  ApiError,
  api,
  type NodeKind,
  type Role,
  type WorkflowDetail,
  type WorkflowIssue,
} from "@/lib/api";
import { autoLayout, NODE_HEIGHT, NODE_WIDTH } from "@/lib/workflow-layout";
import {
  NODE_META,
  PALETTE_ORDER,
  defaultConfig,
  fromFlow,
  newNodeId,
  toFlow,
  type FlowEdge,
  type FlowNode,
} from "@/lib/workflow-meta";

interface Graph {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

const nodeTypes = { hermes: NodeCard };
const MAX_HISTORY = 100;
const MIN_READABLE_ZOOM = 0.6;

// --------------------------------------------------------------------------- loader

export default function WorkflowPage() {
  const { orgId, workflowId } = useParams<{ orgId: string; workflowId: string }>();
  const [generation, setGeneration] = useState(0);
  const org = useQuery({ queryKey: ["org", orgId], queryFn: () => api.orgs.get(orgId) });
  const detail = useQuery({
    queryKey: ["workflow", orgId, workflowId],
    queryFn: () => api.workflows.get(orgId, workflowId),
    // The editor owns local state. Refetching happens only when the editor asks for it.
    staleTime: Infinity,
    retry: false,
  });

  if (detail.error instanceof ApiError && detail.error.status === 404) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
        <EmptyState
          title="Workflow not found"
          body="It may have been archived, or you may not have access."
          action={
            <Link href={`/o/${orgId}/workflows`} className="text-accent-strong hover:underline">
              Back to the library
            </Link>
          }
        />
      </div>
    );
  }
  if (!detail.data || !org.data) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-8 sm:px-6">
        <Skeleton className="h-6 w-56" />
        <Skeleton className="h-[50vh]" />
      </div>
    );
  }

  return (
    <ReactFlowProvider>
      <Builder
        key={generation}
        orgId={orgId}
        workflowId={workflowId}
        role={org.data.role}
        detail={detail.data}
        onReload={async () => {
          const fresh = await detail.refetch();
          if (fresh.data) setGeneration((value) => value + 1);
        }}
        onMetaChanged={() => void detail.refetch()}
      />
    </ReactFlowProvider>
  );
}

// --------------------------------------------------------------------------- builder

interface BuilderProps {
  orgId: string;
  workflowId: string;
  role: Role;
  detail: WorkflowDetail;
  onReload: () => Promise<void>;
  onMetaChanged: () => void;
}

function Builder({ orgId, workflowId, role, detail, onReload, onMetaChanged }: BuilderProps) {
  const queryClient = useQueryClient();
  const flow = useReactFlow<FlowNode, FlowEdge>();
  const canvasRef = useRef<HTMLDivElement>(null);

  const canEdit = role !== "viewer";
  const canPublish = role === "owner" || role === "admin";

  const source = detail.draft ?? detail.latest_published;
  const [graph, setGraphState] = useState<Graph>(() =>
    source ? toFlow(source.definition) : { nodes: [], edges: [] },
  );
  // The ref is the synchronous source of truth for event handlers. Every change goes through applyGraph.
  const graphRef = useRef(graph);
  const applyGraph = useCallback((next: Graph | ((current: Graph) => Graph)) => {
    const resolved = typeof next === "function" ? next(graphRef.current) : next;
    graphRef.current = resolved;
    setGraphState(resolved);
  }, []);

  const [revision, setRevision] = useState<number | null>(detail.draft?.revision ?? null);
  const [dirty, setDirty] = useState(false);
  const [issues, setIssues] = useState<WorkflowIssue[]>(detail.issues);
  const [errors, setErrors] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<"save" | "publish" | "activate" | null>(null);
  const [name, setName] = useState(detail.workflow.name);
  const [conflict, setConflict] = useState(false);
  const [runTemplate, setRunTemplate] = useState<Record<string, unknown> | null>(null);

  // ---- viewport ----
  // Fit the graph, but never zoom out below a readable size. A wide graph is anchored at its first step.
  const fitToGraph = useCallback(
    (animate = true) => {
      const nodes = graphRef.current.nodes;
      const rect = canvasRef.current?.getBoundingClientRect();
      if (nodes.length === 0 || !rect) return;
      const xs = nodes.map((node) => node.position.x);
      const ys = nodes.map((node) => node.position.y);
      const minX = Math.min(...xs);
      const minY = Math.min(...ys);
      const width = Math.max(...xs) + NODE_WIDTH - minX;
      const height = Math.max(...ys) + NODE_HEIGHT - minY;
      const pad = 48;
      const fit = Math.min((rect.width - pad * 2) / width, (rect.height - pad * 2) / height);
      const zoom = Math.min(1, Math.max(MIN_READABLE_ZOOM, fit));
      const x = fit >= MIN_READABLE_ZOOM ? (rect.width - width * zoom) / 2 - minX * zoom : pad - minX * zoom;
      const free = rect.height - height * zoom;
      const y = (free > pad * 2 ? free / 2 : pad) - minY * zoom;
      void flow.setViewport({ x, y, zoom }, { duration: animate ? 200 : 0 });
    },
    [flow],
  );
  // Fit requests run after React has committed the new node positions, never before.
  const [fitRequest, setFitRequest] = useState(0);
  useEffect(() => {
    if (fitRequest > 0) fitToGraph();
  }, [fitRequest, fitToGraph]);

  // ---- history (undo and redo) ----
  const past = useRef<Graph[]>([]);
  const future = useRef<Graph[]>([]);
  const lastKey = useRef<{ key: string; at: number } | null>(null);
  const [history, setHistory] = useState({ canUndo: false, canRedo: false });
  const syncHistory = useCallback(
    () => setHistory({ canUndo: past.current.length > 0, canRedo: future.current.length > 0 }),
    [],
  );

  const record = useCallback(
    (snapshot: Graph, key?: string) => {
      const now = Date.now();
      // Consecutive keystrokes in one field are a single undo step.
      if (key && lastKey.current?.key === key && now - lastKey.current.at < 1000) {
        lastKey.current.at = now;
        return;
      }
      lastKey.current = key ? { key, at: now } : null;
      const stack = past.current;
      if (stack[stack.length - 1] !== snapshot) stack.push(snapshot);
      if (stack.length > MAX_HISTORY) stack.shift();
      future.current = [];
      syncHistory();
    },
    [syncHistory],
  );

  const commit = useCallback(
    (next: Graph, key?: string) => {
      record(graphRef.current, key);
      applyGraph(next);
      setDirty(true);
    },
    [record, applyGraph],
  );

  const undo = useCallback(() => {
    const previous = past.current.pop();
    if (!previous) return;
    future.current.push(graphRef.current);
    lastKey.current = null;
    applyGraph(previous);
    setDirty(true);
    syncHistory();
  }, [applyGraph, syncHistory]);

  const redo = useCallback(() => {
    const next = future.current.pop();
    if (!next) return;
    past.current.push(graphRef.current);
    lastKey.current = null;
    applyGraph(next);
    setDirty(true);
    syncHistory();
  }, [applyGraph, syncHistory]);

  // ---- derived state ----
  const selectedNodes = graph.nodes.filter((node) => node.selected);
  const selected = selectedNodes.length === 1 ? selectedNodes[0] : null;

  const issuesByNode = useMemo(() => {
    const map = new Map<string, WorkflowIssue[]>();
    for (const issue of issues) {
      if (!issue.node_id) continue;
      map.set(issue.node_id, [...(map.get(issue.node_id) ?? []), issue]);
    }
    return map;
  }, [issues]);

  const displayNodes = useMemo(
    () =>
      graph.nodes.map((node) => ({
        ...node,
        data: { ...node.data, issueCount: issuesByNode.get(node.id)?.length ?? 0 },
      })),
    [graph.nodes, issuesByNode],
  );

  const errorCount = issues.filter((issue) => issue.severity === "error").length;

  // ---- live validation against the server's rules (positions excluded) ----
  const definitionKey = useMemo(
    () =>
      JSON.stringify({
        n: graph.nodes.map((n) => [n.id, n.data.kind, n.data.label, n.data.config]),
        e: graph.edges.map((e) => [e.id, e.source, e.target, e.sourceHandle ?? null]),
      }),
    [graph.nodes, graph.edges],
  );
  const firstValidation = useRef(true);
  useEffect(() => {
    if (firstValidation.current) {
      firstValidation.current = false;
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const result = await api.workflows.validate(
          orgId,
          workflowId,
          fromFlow(graphRef.current.nodes, graphRef.current.edges),
        );
        if (!cancelled) setIssues(result);
      } catch {
        // Validation is advisory while editing. Publishing re-validates on the server.
      }
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [definitionKey, orgId, workflowId]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 3000);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // ---- canvas events ----
  const onNodesChange = useCallback(
    (changes: NodeChange<FlowNode>[]) => {
      const allowed = canEdit
        ? changes
        : changes.filter((change) => change.type === "select" || change.type === "dimensions");
      if (allowed.length === 0) return;
      if (allowed.some((change) => change.type === "remove")) record(graphRef.current);
      applyGraph((current) => ({ ...current, nodes: applyNodeChanges(allowed, current.nodes) }));
      if (allowed.some((change) => change.type !== "select" && change.type !== "dimensions")) setDirty(true);
    },
    [canEdit, record, applyGraph],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange<FlowEdge>[]) => {
      const allowed = canEdit ? changes : changes.filter((change) => change.type === "select");
      if (allowed.length === 0) return;
      if (allowed.some((change) => change.type === "remove")) record(graphRef.current);
      applyGraph((current) => ({ ...current, edges: applyEdgeChanges(allowed, current.edges) }));
      if (allowed.some((change) => change.type !== "select")) setDirty(true);
    },
    [canEdit, record, applyGraph],
  );

  const isValidConnection = useCallback((candidate: Edge | Connection) => {
    const { nodes, edges } = graphRef.current;
    const from = nodes.find((node) => node.id === candidate.source);
    const to = nodes.find((node) => node.id === candidate.target);
    if (!from || !to || from.id === to.id) return false;
    if (NODE_META[from.data.kind].noOutput || NODE_META[to.data.kind].noInput) return false;
    const handle = candidate.sourceHandle ?? null;
    // Each output carries one connection. Use a Condition node to branch.
    return !edges.some((edge) => edge.source === from.id && (edge.sourceHandle ?? null) === handle);
  }, []);

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!isValidConnection(connection)) return;
      const handle = connection.sourceHandle ?? null;
      const edge: FlowEdge = {
        id: `e-${connection.source}-${handle ?? "out"}-${connection.target}`,
        source: connection.source,
        target: connection.target,
        sourceHandle: handle ?? undefined,
        label: handle ?? undefined,
      };
      commit({ ...graphRef.current, edges: [...graphRef.current.edges, edge] });
    },
    [commit, isValidConnection],
  );

  const addNode = useCallback(
    (kind: NodeKind, at?: { x: number; y: number }) => {
      const current = graphRef.current;
      if (kind === "trigger" && current.nodes.some((node) => node.data.kind === "trigger")) {
        setNotice("A workflow can only have one trigger.");
        return;
      }
      let position = at;
      const autoPlaced = !position;
      if (!position) {
        // Build left to right: a new step goes beside the selected (or most recent) one.
        const anchor = current.nodes.find((node) => node.selected) ?? current.nodes[current.nodes.length - 1];
        if (anchor) {
          position = { x: anchor.position.x + NODE_WIDTH + 72, y: anchor.position.y };
        } else {
          const rect = canvasRef.current?.getBoundingClientRect();
          const center = flow.screenToFlowPosition({
            x: (rect?.left ?? 0) + (rect?.width ?? 600) / 2,
            y: (rect?.top ?? 0) + (rect?.height ?? 400) / 2,
          });
          position = { x: center.x - NODE_WIDTH / 2, y: center.y - NODE_HEIGHT / 2 };
        }
      }
      const node: FlowNode = {
        id: newNodeId(kind),
        type: "hermes",
        position,
        selected: true,
        data: { kind, label: "", config: defaultConfig(kind), issueCount: 0 },
      };
      commit({
        nodes: [...current.nodes.map((existing) => ({ ...existing, selected: false })), node],
        edges: current.edges,
      });
      if (autoPlaced) setFitRequest((value) => value + 1);
    },
    [commit, flow],
  );

  const patchNode = (id: string, patch: { label?: string; config?: Record<string, unknown> }) => {
    const current = graphRef.current;
    record(current, `edit:${id}`);
    applyGraph({
      ...current,
      nodes: current.nodes.map((node) =>
        node.id === id
          ? {
              ...node,
              data: {
                ...node.data,
                ...(patch.label !== undefined ? { label: patch.label } : {}),
                ...(patch.config ? { config: patch.config } : {}),
              },
            }
          : node,
      ),
    });
    setDirty(true);
  };

  const deleteNode = (id: string) => {
    const current = graphRef.current;
    commit({
      nodes: current.nodes.filter((node) => node.id !== id),
      edges: current.edges.filter((edge) => edge.source !== id && edge.target !== id),
    });
  };

  const selectNode = (id: string) => {
    applyGraph((current) => ({
      ...current,
      nodes: current.nodes.map((node) => ({ ...node, selected: node.id === id })),
    }));
    void flow.fitView({ nodes: [{ id }], duration: 250, maxZoom: 1.1 });
  };

  const runAutoLayout = () => {
    const current = graphRef.current;
    commit({ nodes: autoLayout(current.nodes, current.edges), edges: current.edges });
    setFitRequest((value) => value + 1);
  };

  // ---- persistence ----
  const explain = (error: unknown): string[] => {
    if (error instanceof ApiError) {
      const payload = error.payload as { issues?: WorkflowIssue[] } | null;
      if (payload?.issues) setIssues(payload.issues);
      return error.messages;
    }
    return ["Could not reach the server."];
  };

  const saveDraft = useCallback(async (): Promise<number | null> => {
    setBusy("save");
    setErrors([]);
    try {
      const saved = await api.workflows.saveDraft(orgId, workflowId, {
        definition: fromFlow(graphRef.current.nodes, graphRef.current.edges),
        base_revision: revision ?? undefined,
      });
      setRevision(saved.version.revision);
      setIssues(saved.issues);
      setDirty(false);
      setConflict(false);
      setNotice(`Saved draft v${saved.version.version_number}`);
      onMetaChanged();
      void queryClient.invalidateQueries({ queryKey: ["workflows", orgId] });
      return saved.version.revision;
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) setConflict(true);
      setErrors(explain(error));
      return null;
    } finally {
      setBusy(null);
    }
  }, [orgId, workflowId, revision, onMetaChanged, queryClient]);

  const publish = async () => {
    const draftNumber = detail.draft?.version_number ?? (detail.latest_published?.version_number ?? 0) + 1;
    if (!window.confirm(`Publish version ${draftNumber}? Published versions are frozen and cannot be edited.`)) return;
    setBusy("publish");
    setErrors([]);
    try {
      let target = revision;
      if (dirty || target === null) {
        target = await saveDraft();
        if (target === null) return;
      }
      setBusy("publish");
      await api.workflows.publish(orgId, workflowId, target);
      void queryClient.invalidateQueries({ queryKey: ["workflows", orgId] });
      await onReload();
    } catch (error) {
      setErrors(explain(error));
    } finally {
      setBusy(null);
    }
  };

  const activate = async (versionNumber: number) => {
    setBusy("activate");
    setErrors([]);
    try {
      await api.workflows.activate(orgId, workflowId, versionNumber);
      setNotice(`Version ${versionNumber} is now the active version`);
      onMetaChanged();
      void queryClient.invalidateQueries({ queryKey: ["workflows", orgId] });
    } catch (error) {
      setErrors(explain(error));
    } finally {
      setBusy(null);
    }
  };

  const deactivate = async () => {
    setBusy("activate");
    setErrors([]);
    try {
      await api.workflows.deactivate(orgId, workflowId);
      setNotice("Workflow is no longer active");
      onMetaChanged();
      void queryClient.invalidateQueries({ queryKey: ["workflows", orgId] });
    } catch (error) {
      setErrors(explain(error));
    } finally {
      setBusy(null);
    }
  };

  const discardDraft = async () => {
    if (!window.confirm("Discard this draft and return to the last published version?")) return;
    try {
      await api.workflows.discardDraft(orgId, workflowId);
      await onReload();
    } catch (error) {
      setErrors(explain(error));
    }
  };

  const rename = async () => {
    const next = name.trim();
    if (!next || next === detail.workflow.name) {
      setName(detail.workflow.name);
      return;
    }
    try {
      await api.workflows.update(orgId, workflowId, { name: next });
      onMetaChanged();
      void queryClient.invalidateQueries({ queryKey: ["workflows", orgId] });
    } catch (error) {
      setErrors(explain(error));
    }
  };

  // ---- keyboard shortcuts ----
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const modifier = event.ctrlKey || event.metaKey;
      if (!modifier) return;
      const key = event.key.toLowerCase();
      const target = event.target as HTMLElement | null;
      const typing = target?.matches("input, textarea, select") ?? false;
      if (key === "s" && canEdit) {
        event.preventDefault();
        if (dirty && busy === null) void saveDraft();
      } else if (key === "z" && !typing && canEdit) {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
      } else if (key === "y" && !typing && canEdit) {
        event.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [canEdit, dirty, busy, saveDraft, undo, redo]);

  // ---- render ----
  const live = detail.workflow.active_version_number;
  const latestPublished = detail.workflow.latest_published_number;
  const hasTrigger = graph.nodes.some((node) => node.data.kind === "trigger");
  const publishable = canPublish && (revision !== null || dirty);

  return (
    <div className="flex flex-1 flex-col lg:h-[calc(100dvh-6.5rem)]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line px-4 py-2 sm:px-6">
        <Link href={`/o/${orgId}/workflows`} className="text-[13px] text-muted hover:text-text">
          Workflows
        </Link>
        <span className="text-faint" aria-hidden>
          /
        </span>
        <label className="sr-only" htmlFor="workflow-name">
          Workflow name
        </label>
        <input
          id="workflow-name"
          value={name}
          disabled={!canEdit}
          maxLength={200}
          onChange={(event) => setName(event.target.value)}
          onBlur={rename}
          onKeyDown={(event) => event.key === "Enter" && event.currentTarget.blur()}
          className="h-8 w-48 rounded-md border border-transparent bg-transparent px-1.5 text-[14px] font-medium hover:border-line-strong disabled:hover:border-transparent sm:w-64"
        />
        {live !== null ? (
          <Badge tone="success">active · v{live}</Badge>
        ) : latestPublished !== null ? (
          <Badge>published · v{latestPublished}</Badge>
        ) : (
          <Badge tone="warning">draft</Badge>
        )}
        {!canEdit && <Badge>read only</Badge>}

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <span role="status" className="mr-1 text-[12px] text-muted">
            {notice || (dirty ? "Unsaved changes" : revision !== null ? `Draft saved · rev ${revision}` : "")}
          </span>
          {canEdit && (
            <>
              <Button variant="ghost" onClick={undo} disabled={!history.canUndo} aria-label="Undo" title="Undo (Ctrl+Z)">
                Undo
              </Button>
              <Button variant="ghost" onClick={redo} disabled={!history.canRedo} aria-label="Redo" title="Redo (Ctrl+Shift+Z)">
                Redo
              </Button>
              <Button variant="secondary" onClick={runAutoLayout} disabled={graph.nodes.length === 0}>
                Auto layout
              </Button>
              <Button variant="secondary" onClick={() => void saveDraft()} loading={busy === "save"} disabled={!dirty || busy !== null} title="Save (Ctrl+S)">
                Save
              </Button>
            </>
          )}
          {canEdit && live !== null && (
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  // Runs follow the active published version, so the example data comes from that version.
                  const active = await api.workflows.version(orgId, workflowId, live);
                  setRunTemplate(payloadTemplate(active.definition));
                } catch (error) {
                  setErrors(explain(error));
                }
              }}
              disabled={dirty || busy !== null}
              title={dirty ? "Save your changes first. Runs use the active published version." : "Run the active version"}
            >
              Run
            </Button>
          )}
          {canPublish && (
            <>
              <Button onClick={publish} loading={busy === "publish"} disabled={!publishable || busy !== null}>
                Publish
              </Button>
              {live !== null ? (
                <Button variant="secondary" onClick={deactivate} disabled={busy !== null}>
                  Deactivate
                </Button>
              ) : latestPublished !== null ? (
                <Button variant="secondary" onClick={() => void activate(latestPublished)} disabled={busy !== null || dirty}>
                  Activate v{latestPublished}
                </Button>
              ) : null}
            </>
          )}
        </div>
      </div>

      {runTemplate !== null && live !== null && (
        <RunDialog
          orgId={orgId}
          workflowId={workflowId}
          workflowName={detail.workflow.name}
          versionNumber={live}
          template={runTemplate}
          onClose={() => setRunTemplate(null)}
        />
      )}

      {(errors.length > 0 || conflict) && (
        <div role="alert" className="flex flex-wrap items-center gap-3 border-b border-danger/40 px-4 py-2 text-[13px] text-danger sm:px-6">
          <span>{errors.join(" ")}</span>
          {conflict && (
            <Button variant="secondary" onClick={() => void onReload()}>
              Reload latest (discards your unsaved changes)
            </Button>
          )}
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {canEdit && (
          <aside aria-label="Step palette" className="shrink-0 border-b border-line p-3 lg:w-52 lg:overflow-y-auto lg:border-b-0 lg:border-r">
            <p className="t-label mb-2">Add a step</p>
            <div className="flex gap-1.5 overflow-x-auto lg:flex-col lg:overflow-visible">
              {PALETTE_ORDER.map((kind) => {
                const meta = NODE_META[kind];
                const disabled = kind === "trigger" && hasTrigger;
                return (
                  <button
                    key={kind}
                    type="button"
                    draggable={!disabled}
                    disabled={disabled}
                    onClick={() => addNode(kind)}
                    onDragStart={(event) => {
                      event.dataTransfer.setData("application/hermes-node", kind);
                      event.dataTransfer.effectAllowed = "move";
                    }}
                    title={meta.description}
                    className="flex shrink-0 items-center justify-between gap-3 rounded-md border border-line px-2.5 py-1.5 text-left text-[13px] transition-colors hover:border-line-strong hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <span>{meta.label}</span>
                    <span className="hidden font-mono text-[10px] text-faint lg:inline">{meta.group}</span>
                  </button>
                );
              })}
            </div>
            <p className="mt-3 hidden text-[11px] leading-snug text-faint lg:block">
              Click to add, or drag onto the canvas. Drag from a step&apos;s right handle to connect. Backspace deletes.
            </p>
          </aside>
        )}

        <div
          ref={canvasRef}
          className="relative h-[60vh] min-w-0 flex-none lg:h-auto lg:flex-1"
          onDragOver={(event) => {
            if (canEdit) event.preventDefault();
          }}
          onDrop={(event) => {
            const kind = event.dataTransfer.getData("application/hermes-node") as NodeKind;
            if (!canEdit || !(kind in NODE_META)) return;
            event.preventDefault();
            const point = flow.screenToFlowPosition({ x: event.clientX, y: event.clientY });
            addNode(kind, { x: point.x - NODE_WIDTH / 2, y: point.y - NODE_HEIGHT / 2 });
          }}
        >
          <ReactFlow<FlowNode, FlowEdge>
            nodes={displayNodes}
            edges={graph.edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            isValidConnection={isValidConnection}
            onNodeDragStart={() => record(graphRef.current)}
            nodesDraggable={canEdit}
            nodesConnectable={canEdit}
            deleteKeyCode={canEdit ? ["Backspace", "Delete"] : null}
            defaultEdgeOptions={{
              type: "smoothstep",
              markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
            }}
            colorMode="dark"
            onInit={() => fitToGraph(false)}
            minZoom={0.2}
            maxZoom={1.8}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              ariaLabel="Workflow minimap"
              bgColor="var(--surface-1)"
              maskColor="rgba(11, 12, 14, 0.7)"
              nodeColor="var(--line-strong)"
              nodeStrokeWidth={0}
              style={{ width: 150, height: 96 }}
              className="!hidden sm:!block"
            />
          </ReactFlow>
          {graph.nodes.length === 0 && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
              <p className="max-w-xs text-center text-[13px] text-muted">
                {canEdit
                  ? "This canvas is empty. Add a Trigger from the palette to start building."
                  : "This workflow has no steps yet."}
              </p>
            </div>
          )}
        </div>

        <aside aria-label="Details" className="shrink-0 overflow-y-auto border-t border-line p-4 lg:w-80 lg:border-l lg:border-t-0">
          {selected ? (
            <Inspector
              key={selected.id}
              node={selected}
              readOnly={!canEdit}
              issues={issuesByNode.get(selected.id) ?? []}
              onChange={(patch) => patchNode(selected.id, patch)}
              onDelete={() => deleteNode(selected.id)}
            />
          ) : (
            <div className="flex flex-col gap-6">
              <section aria-labelledby="issues-heading">
                <h2 id="issues-heading" className="t-label mb-2">
                  Checks
                </h2>
                {issues.length === 0 ? (
                  <p className="text-[13px] text-success">No issues. This graph can be published.</p>
                ) : (
                  <>
                    <p className="mb-2 text-[12px] text-muted">
                      {errorCount} issue{errorCount === 1 ? "" : "s"} to fix before publishing.
                    </p>
                    <ul className="flex flex-col gap-1.5">
                      {issues.map((issue, index) => (
                        <li key={`${issue.code}-${issue.node_id ?? "graph"}-${index}`} className="text-[12px]">
                          {issue.node_id ? (
                            <button
                              type="button"
                              onClick={() => selectNode(issue.node_id as string)}
                              className="text-left text-danger hover:underline"
                            >
                              {issue.message}
                            </button>
                          ) : (
                            <span className="text-danger">{issue.message}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </section>

              <section aria-labelledby="versions-heading">
                <h2 id="versions-heading" className="t-label mb-2">
                  Versions
                </h2>
                <ul className="flex flex-col gap-1.5">
                  {detail.versions.map((version) => (
                    <li key={version.id} className="flex items-center justify-between gap-2 text-[12px]">
                      <span className="font-mono">
                        v{version.version_number}{" "}
                        <span className="text-faint">{version.status === "draft" ? "draft" : "published"}</span>
                        {version.version_number === live && <span className="ml-1.5 text-success">active</span>}
                      </span>
                      {canPublish && version.status === "published" && version.version_number !== live && (
                        <Button variant="ghost" onClick={() => void activate(version.version_number)} disabled={busy !== null || dirty}>
                          Activate
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
                {canEdit && detail.draft && latestPublished !== null && (
                  <Button variant="ghost" onClick={discardDraft} className="mt-2">
                    Discard draft
                  </Button>
                )}
                <p className="mt-3 text-[11px] leading-snug text-faint">
                  Published versions are frozen. Editing a published workflow creates a new draft when you save.
                  New runs always use the active version. A run in progress stays on the version it started with.
                </p>
              </section>

              {canPublish && <EmailInboxPanel orgId={orgId} workflowId={workflowId} />}
              {canPublish && <WebhookPanel orgId={orgId} workflowId={workflowId} />}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
