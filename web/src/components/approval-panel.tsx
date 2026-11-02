"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { Badge, Button, FormError } from "@/components/ui";
import { formatTime } from "@/components/status";
import { ApiError, api, type ApprovalItem } from "@/lib/api";

export function Json({ value }: { value: unknown }) {
  return (
    <pre className="max-h-64 overflow-auto rounded-md border border-line bg-surface-1 p-2.5 font-mono text-[11px] leading-relaxed text-muted">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

/** Shows what is being approved and, for people allowed to decide, the approve and reject controls. */
export function ApprovalPanel({
  orgId,
  approval,
  onDecided,
}: {
  orgId: string;
  approval: ApprovalItem;
  onDecided: () => void;
}) {
  const [comment, setComment] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const decide = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      api.approvals.decide(orgId, approval.id, { decision, comment: comment.trim() || undefined }),
    onSuccess: onDecided,
    onError: (error) => setErrors(error instanceof ApiError ? error.messages : ["Could not reach the server."]),
  });

  return (
    <section aria-label={`Approval: ${approval.title}`} className="border border-warning/40 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="t-label">Approval</p>
        <Badge tone={approval.status === "pending" ? "warning" : approval.status === "approved" ? "success" : "neutral"}>
          {approval.status}
        </Badge>
        <span className="text-[12px] text-faint">needs: {approval.approver_role}</span>
      </div>
      <p className="mt-2 text-[14px] font-medium">{approval.title}</p>
      <div className="mt-3">
        <p className="t-label mb-1.5">Data to review</p>
        <Json value={approval.context} />
      </div>
      {approval.status === "pending" && approval.can_decide ? (
        <div className="mt-4 flex flex-col gap-3">
          <FormError messages={errors} />
          <label className="text-[12px] font-medium text-muted" htmlFor={`comment-${approval.id}`}>
            Comment (optional)
          </label>
          <textarea
            id={`comment-${approval.id}`}
            rows={2}
            maxLength={1000}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            className="rounded-md border border-line-strong bg-surface-1 px-2.5 py-2 text-[13px] hover:border-faint focus-visible:border-accent"
          />
          <div className="flex gap-2">
            <Button onClick={() => decide.mutate("approve")} loading={decide.isPending} disabled={decide.isPending}>
              Approve
            </Button>
            <Button variant="danger" onClick={() => decide.mutate("reject")} disabled={decide.isPending}>
              Reject
            </Button>
          </div>
        </div>
      ) : approval.status === "pending" ? (
        <p className="mt-3 text-[12px] text-muted">Only a user with the {approval.approver_role} role can decide this.</p>
      ) : (
        <p className="mt-3 text-[12px] text-muted">
          {approval.status} by {approval.decided_by_name ?? "unknown"} · {formatTime(approval.decided_at)}
          {approval.comment ? ` · “${approval.comment}”` : ""}
        </p>
      )}
    </section>
  );
}
