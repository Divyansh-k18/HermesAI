"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { Badge, EmptyState, Skeleton } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

export default function AuditPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const events = useQuery({
    queryKey: ["audit", orgId],
    queryFn: () => api.orgs.auditEvents(orgId, 100),
    retry: false,
  });

  const members = useQuery({ queryKey: ["members", orgId], queryFn: () => api.orgs.members(orgId) });
  // Names for the people who acted. Someone who has since left the organization shows as "former member".
  const nameOf = (userId: string | null): string => {
    if (!userId) return "system";
    return members.data?.find((member) => member.user_id === userId)?.full_name ?? "former member";
  };

  const forbidden = events.error instanceof ApiError && events.error.status === 403;

  return (
    <div className="rise-in flex flex-col gap-6">
      <header>
        <p className="t-label">Audit log</p>
        <h1 className="t-title mt-3 text-2xl">Security and access events</h1>
        <p className="mt-1.5 max-w-xl text-muted">
          Every sign-in, role change, invitation, and organization update is recorded with the person who did it and a trace ID.
        </p>
      </header>

      {forbidden ? (
        <EmptyState title="Restricted" body="Only owners and admins can read the audit log." />
      ) : events.isLoading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
        </div>
      ) : events.isError ? (
        <EmptyState title="Could not load events" body="Try again in a moment." />
      ) : events.data && events.data.length > 0 ? (
        <div className="relative overflow-x-auto border border-line">
          <table className="w-full min-w-[40rem] text-left text-[13px]">
            <thead className="border-b border-line text-faint">
              <tr>
                <th className="px-3 py-2 font-normal">Time</th>
                <th className="px-3 py-2 font-normal">Action</th>
                <th className="px-3 py-2 font-normal">Who</th>
                <th className="px-3 py-2 font-normal">Outcome</th>
                <th className="px-3 py-2 font-normal">Detail</th>
                <th className="px-3 py-2 font-normal">Trace</th>
              </tr>
            </thead>
            <tbody>
              {events.data.map((event) => (
                <tr key={event.id} className="border-b border-line last:border-0 hover:bg-surface-1">
                  <td className="whitespace-nowrap px-3 py-2.5 font-mono text-[12px] text-muted">
                    {new Date(event.created_at + "Z").toLocaleString()}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-[12px]">{event.action}</td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-[12px] text-muted">{nameOf(event.actor_user_id)}</td>
                  <td className="px-3 py-2.5">
                    <Badge tone={event.outcome === "success" ? "success" : "warning"}>{event.outcome}</Badge>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-[12px] text-muted">
                    {Object.keys(event.metadata).length > 0 ? JSON.stringify(event.metadata) : "—"}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-[11px] text-faint">{event.trace_id?.slice(0, 8) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="No events yet" body="Activity in this organization will appear here." />
      )}
    </div>
  );
}
