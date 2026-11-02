"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ApprovalPanel, Json } from "@/components/approval-panel";
import { Button, EmptyState, FormError, Skeleton } from "@/components/ui";
import {
  ExecutionStatusBadge,
  StepStatusBadge,
  TERMINAL,
  formatDuration,
  formatTime,
} from "@/components/status";
import { ApiError, api, type StepRecord } from "@/lib/api";
import { NODE_META } from "@/lib/workflow-meta";

function StepItem({ step, last }: { step: StepRecord; last: boolean }) {
  const meta = NODE_META[step.node_type];
  const [open, setOpen] = useState(step.status === "failed");
  const hasOutput = Object.keys(step.output).length > 0;
  return (
    <li className="relative flex gap-4 pb-6">
      {!last && <span aria-hidden className="absolute left-[7px] top-5 h-full w-px bg-line-strong" />}
      <span
        aria-hidden
        className={`relative mt-1.5 size-[15px] shrink-0 rounded-[3px] border ${
          step.status === "succeeded"
            ? "border-success bg-success/20"
            : step.status === "failed"
              ? "border-danger bg-danger/20"
              : step.status === "waiting"
                ? "border-warning bg-warning/20"
                : "border-line-strong bg-surface-2"
        }`}
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="t-label">{meta.label}</span>
          <span className="text-[13px] font-medium">{step.node_label || meta.label}</span>
          <StepStatusBadge status={step.status} />
          <span className="ml-auto font-mono text-[11px] text-faint">
            {formatDuration(step.started_at, step.finished_at)}
          </span>
        </div>
        {step.error && (
          <p role="alert" className="mt-2 rounded-md border border-danger/40 px-3 py-2 text-[13px] text-danger">
            {step.error}
          </p>
        )}
        {hasOutput && (
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="mt-2 text-[12px] text-muted hover:text-text"
          >
            {open ? "Hide details" : "Show details"}
          </button>
        )}
        {open && (
          <div className="mt-2 grid gap-2 lg:grid-cols-2">
            <div>
              <p className="t-label mb-1.5">Output</p>
              <Json value={step.output} />
            </div>
            <div>
              <p className="t-label mb-1.5">Data on arrival</p>
              <Json value={step.input} />
            </div>
          </div>
        )}
      </div>
    </li>
  );
}

export default function ExecutionDetailPage() {
  const { orgId, executionId } = useParams<{ orgId: string; executionId: string }>();
  const queryClient = useQueryClient();
  const [errors, setErrors] = useState<string[]>([]);
  const run = useQuery({
    queryKey: ["execution", orgId, executionId],
    queryFn: () => api.executions.get(orgId, executionId),
    // Keep polling while the run can still change.
    refetchInterval: (query) => (query.state.data && TERMINAL.includes(query.state.data.status) ? false : 3000),
    retry: false,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["execution", orgId, executionId] });
    void queryClient.invalidateQueries({ queryKey: ["executions", orgId] });
    void queryClient.invalidateQueries({ queryKey: ["metrics", orgId] });
    void queryClient.invalidateQueries({ queryKey: ["approvals", orgId] });
  };

  const cancel = useMutation({
    mutationFn: () => api.executions.cancel(orgId, executionId),
    onSuccess: refresh,
    onError: (error) => setErrors(error instanceof ApiError ? error.messages : ["Could not reach the server."]),
  });

  if (run.error instanceof ApiError && run.error.status === 404) {
    return <EmptyState title="Run not found" body="It may belong to another organization." />;
  }
  if (!run.data) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  const data = run.data;
  const canCancel = ["running", "waiting_approval", "waiting_timer"].includes(data.status);

  return (
    <div className="rise-in flex flex-col gap-8">
      <header>
        <Link href={`/o/${orgId}/executions`} className="text-[13px] text-muted hover:text-text">
          Runs
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="t-title text-2xl">{data.workflow_name}</h1>
          <ExecutionStatusBadge status={data.status} />
          <span className="font-mono text-[12px] text-faint">v{data.version_number}</span>
          {canCancel && (
            <Button variant="danger" className="ml-auto" onClick={() => cancel.mutate()} loading={cancel.isPending}>
              Cancel run
            </Button>
          )}
        </div>
        <dl className="mt-4 grid max-w-xl grid-cols-[7rem_1fr] gap-y-1.5 text-[13px]">
          <dt className="text-faint">Started</dt>
          <dd className="font-mono text-[12px]">{formatTime(data.started_at)}</dd>
          <dt className="text-faint">Duration</dt>
          <dd className="font-mono text-[12px]">{formatDuration(data.started_at, data.finished_at)}</dd>
          <dt className="text-faint">Run ID</dt>
          <dd className="break-all font-mono text-[12px] text-muted">{data.id}</dd>
          {data.trace_id && (
            <>
              <dt className="text-faint">Trace ID</dt>
              <dd className="break-all font-mono text-[12px] text-muted">{data.trace_id}</dd>
            </>
          )}
        </dl>
        <div className="mt-4 flex flex-col gap-2">
          <FormError messages={errors} />
          {data.error && (
            <p role="alert" className="max-w-2xl rounded-md border border-danger/40 px-3 py-2 text-[13px] text-danger">
              {data.error}
            </p>
          )}
        </div>
      </header>

      {data.approvals.map((approval) => (
        <ApprovalPanel key={approval.id} orgId={orgId} approval={approval} onDecided={refresh} />
      ))}
      {data.status === "waiting_approval" && data.approvals.length === 0 && (
        <p className="border border-warning/40 px-4 py-3 text-[13px] text-muted">
          This run is waiting for an approval. Only owners and admins can see and decide it.
        </p>
      )}

      <section aria-labelledby="trace-heading" className="grid gap-8 lg:grid-cols-[1fr_20rem]">
        <div>
          <h2 id="trace-heading" className="t-label mb-4">
            Step trace
          </h2>
          <ol>
            {data.steps.map((step, index) => (
              <StepItem key={step.id} step={step} last={index === data.steps.length - 1} />
            ))}
          </ol>
        </div>
        <div className="flex flex-col gap-5">
          <div>
            <h2 className="t-label mb-2">Input</h2>
            <Json value={data.trigger_payload} />
          </div>
          <div>
            <h2 className="t-label mb-2">Current data</h2>
            <Json value={data.variables} />
          </div>
        </div>
      </section>
    </div>
  );
}
