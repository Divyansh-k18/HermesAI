"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { EmptyState, Skeleton } from "@/components/ui";
import { ExecutionStatusBadge, formatDuration, formatTime } from "@/components/status";
import { api } from "@/lib/api";

const FILTERS = [
  { value: "", label: "All" },
  { value: "waiting_approval", label: "Waiting for approval" },
  { value: "succeeded", label: "Succeeded" },
  { value: "rejected", label: "Rejected" },
  { value: "failed", label: "Failed" },
];

export default function ExecutionsPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const [status, setStatus] = useState("");
  const runs = useQuery({
    queryKey: ["executions", orgId, status],
    queryFn: () => api.executions.list(orgId, { status: status || undefined }),
    // Waiting runs change when someone decides an approval, so keep the list fresh.
    refetchInterval: 5000,
  });

  return (
    <div className="rise-in flex flex-col gap-6">
      <header>
        <p className="t-label">Executions</p>
        <h1 className="t-title mt-3 text-2xl">Runs</h1>
        <p className="mt-1.5 max-w-xl text-muted">
          Every run records each step it took, what went in, and what came out. Open a run to see its trace.
        </p>
      </header>

      <div role="group" aria-label="Filter runs by status" className="flex flex-wrap gap-1.5">
        {FILTERS.map((filter) => (
          <button
            key={filter.value}
            type="button"
            aria-pressed={status === filter.value}
            onClick={() => setStatus(filter.value)}
            className={`rounded-md border px-2.5 py-1 text-[12px] transition-colors ${
              status === filter.value
                ? "border-accent bg-accent-soft text-text"
                : "border-line text-muted hover:border-line-strong hover:text-text"
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {runs.isLoading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-11" />
          <Skeleton className="h-11" />
        </div>
      ) : runs.isError ? (
        <EmptyState title="Could not load runs" body="Try again in a moment." />
      ) : runs.data && runs.data.length > 0 ? (
        <div className="relative overflow-x-auto border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-line text-faint">
              <tr>
                <th className="px-3 py-2 font-normal">Workflow</th>
                <th className="px-3 py-2 font-normal">Status</th>
                <th className="hidden px-3 py-2 font-normal sm:table-cell">Started</th>
                <th className="hidden px-3 py-2 font-normal md:table-cell">Duration</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((run) => (
                <tr key={run.id} className="border-b border-line last:border-0 hover:bg-surface-1">
                  <td className="px-3 py-2.5">
                    <Link href={`/o/${orgId}/executions/${run.id}`} className="font-medium hover:text-accent-strong">
                      {run.workflow_name}
                    </Link>
                    <span className="ml-2 font-mono text-[11px] text-faint">v{run.version_number}</span>
                  </td>
                  <td className="px-3 py-2.5">
                    <ExecutionStatusBadge status={run.status} />
                  </td>
                  <td className="hidden px-3 py-2.5 font-mono text-[12px] text-muted sm:table-cell">
                    {formatTime(run.started_at)}
                  </td>
                  <td className="hidden px-3 py-2.5 font-mono text-[12px] text-muted md:table-cell">
                    {formatDuration(run.started_at, run.finished_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title={status ? "No runs with this status" : "No runs yet"}
          body="Activate a workflow and use Run in the builder to start one."
        />
      )}
    </div>
  );
}
