"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ApprovalPanel } from "@/components/approval-panel";
import { EmptyState, Skeleton } from "@/components/ui";
import { formatTime } from "@/components/status";
import { ApiError, api } from "@/lib/api";

export default function ApprovalsPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const queryClient = useQueryClient();
  const [view, setView] = useState<"pending" | "decided">("pending");

  const approvals = useQuery({
    queryKey: ["approvals", orgId, view],
    queryFn: () => api.approvals.list(orgId, view),
    refetchInterval: 5000,
    retry: false,
  });

  const forbidden = approvals.error instanceof ApiError && approvals.error.status === 403;

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["approvals", orgId] });
    void queryClient.invalidateQueries({ queryKey: ["executions", orgId] });
    void queryClient.invalidateQueries({ queryKey: ["metrics", orgId] });
  };

  return (
    <div className="rise-in flex flex-col gap-6">
      <header>
        <p className="t-label">Approvals</p>
        <h1 className="t-title mt-3 text-2xl">Decisions waiting on people</h1>
        <p className="mt-1.5 max-w-xl text-muted">
          A paused run continues only after an authorized person decides. Rejected requests never continue down the
          approved path.
        </p>
      </header>

      {forbidden ? (
        <EmptyState title="Restricted" body="Only owners and admins can see approval requests." />
      ) : (
        <>
          <div role="group" aria-label="Approval view" className="flex gap-1.5">
            {(["pending", "decided"] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={view === value}
                onClick={() => setView(value)}
                className={`rounded-md border px-2.5 py-1 text-[12px] capitalize transition-colors ${
                  view === value
                    ? "border-accent bg-accent-soft text-text"
                    : "border-line text-muted hover:border-line-strong hover:text-text"
                }`}
              >
                {value === "pending" ? "Pending" : "History"}
              </button>
            ))}
          </div>

          {approvals.isLoading ? (
            <Skeleton className="h-40" />
          ) : approvals.data && approvals.data.length > 0 ? (
            <ul className="flex flex-col gap-5">
              {approvals.data.map((approval) => (
                <li key={approval.id}>
                  <p className="mb-2 flex flex-wrap items-center gap-x-3 text-[12px] text-muted">
                    <Link
                      href={`/o/${orgId}/executions/${approval.execution_id}`}
                      className="font-medium text-text hover:text-accent-strong"
                    >
                      {approval.workflow_name}
                    </Link>
                    <span className="font-mono text-faint">requested {formatTime(approval.requested_at)}</span>
                  </p>
                  <ApprovalPanel orgId={orgId} approval={approval} onDecided={refresh} />
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              title={view === "pending" ? "Nothing waiting" : "No decisions yet"}
              body={
                view === "pending"
                  ? "When a run reaches an approval step it appears here."
                  : "Decided approvals appear here with who decided and why."
              }
            />
          )}
        </>
      )}
    </div>
  );
}
