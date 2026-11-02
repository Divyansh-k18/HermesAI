"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";

import { EmptyState, Skeleton } from "@/components/ui";
import { ExecutionStatusBadge, formatSeconds, formatTime } from "@/components/status";
import { api, type Metrics } from "@/lib/api";

function Stat({ label, value, href, hint }: { label: string; value: string | number; href: string; hint?: string }) {
  return (
    <Link
      href={href}
      className="group flex flex-col gap-2 border-b border-line px-4 py-4 transition-colors hover:bg-surface-1 sm:border-b-0 sm:border-r sm:last:border-r-0"
    >
      <span className="t-label">{label}</span>
      <span className="font-mono text-3xl tracking-tight">{value}</span>
      <span className="text-[12px] text-faint group-hover:text-muted">{hint ?? " "}</span>
    </Link>
  );
}

/** Seven days of finished runs, stacked by outcome. Colors carry meaning: green succeeded, amber rejected, red failed. */
function DailyChart({ days }: { days: Metrics["last_7_days"] }) {
  const max = Math.max(1, ...days.map((d) => d.succeeded + d.failed + d.rejected));
  const height = 120;
  const barWidth = 44;
  const gap = 28;
  const width = days.length * (barWidth + gap) - gap;
  const empty = days.every((d) => d.succeeded + d.failed + d.rejected === 0);

  return (
    <figure>
      <svg
        viewBox={`0 0 ${width} ${height + 22}`}
        role="img"
        aria-label="Finished runs per day for the last seven days"
        className="h-44 w-full max-w-2xl"
      >
        <line x1="0" x2={width} y1={height} y2={height} stroke="var(--line-strong)" />
        {days.map((day, index) => {
          const x = index * (barWidth + gap);
          let y = height;
          const segments: [number, string][] = [
            [day.succeeded, "var(--success)"],
            [day.rejected, "var(--warning)"],
            [day.failed, "var(--danger)"],
          ];
          return (
            <g key={day.date}>
              {segments.map(([count, color]) => {
                if (count === 0) return null;
                const h = (count / max) * (height - 8);
                y -= h;
                return <rect key={color} x={x} y={y} width={barWidth} height={h} fill={color} rx="2" />;
              })}
              <text x={x + barWidth / 2} y={height + 15} textAnchor="middle" fontSize="10" fill="var(--text-faint)" fontFamily="var(--font-mono)">
                {day.date.slice(5)}
              </text>
            </g>
          );
        })}
      </svg>
      {empty && <p className="text-[12px] text-faint">No finished runs in the last seven days.</p>}
      <figcaption className="mt-2 flex flex-wrap gap-4 text-[12px] text-muted">
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-[2px] bg-success" /> succeeded
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-[2px] bg-warning" /> rejected
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-[2px] bg-danger" /> failed
        </span>
      </figcaption>
      <table className="sr-only">
        <caption>Finished runs per day</caption>
        <thead>
          <tr>
            <th>Date</th>
            <th>Succeeded</th>
            <th>Rejected</th>
            <th>Failed</th>
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day.date}>
              <td>{day.date}</td>
              <td>{day.succeeded}</td>
              <td>{day.rejected}</td>
              <td>{day.failed}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

export default function OverviewPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const org = useQuery({ queryKey: ["org", orgId], queryFn: () => api.orgs.get(orgId) });
  const metrics = useQuery({
    queryKey: ["metrics", orgId],
    queryFn: () => api.metrics.get(orgId),
    refetchInterval: 10_000,
  });
  const recent = useQuery({
    queryKey: ["executions", orgId, "recent"],
    queryFn: () => api.executions.list(orgId),
    refetchInterval: 10_000,
  });

  const m = metrics.data;
  const isAdmin = org.data?.role === "owner" || org.data?.role === "admin";

  return (
    <div className="rise-in flex flex-col gap-10">
      <section>
        <p className="t-label">Organization</p>
        <h1 className="t-display mt-3">{org.data?.name}</h1>
        <p className="mt-3 font-mono text-[12px] text-faint">
          plan {org.data?.plan_code} · your role {org.data?.role}
        </p>
      </section>

      <section aria-label="Key numbers" className="grid border border-line sm:grid-cols-4">
        {m ? (
          <>
            <Stat
              label="Active workflows"
              value={m.active_workflows}
              href={`/o/${orgId}/workflows`}
              hint={`of ${m.total_workflows} total`}
            />
            <Stat label="Runs" value={m.total_runs} href={`/o/${orgId}/executions`} hint="all time" />
            <Stat
              label="Waiting on people"
              value={m.pending_approvals}
              href={isAdmin ? `/o/${orgId}/approvals` : `/o/${orgId}/executions`}
              hint={m.pending_approvals > 0 ? "needs a decision" : "nothing pending"}
            />
            <Stat label="Average run time" value={formatSeconds(m.average_duration_seconds)} href={`/o/${orgId}/executions`} hint="finished runs" />
          </>
        ) : (
          <div className="col-span-4 p-4">
            <Skeleton className="h-16" />
          </div>
        )}
      </section>

      {m && m.total_workflows === 0 ? (
        <EmptyState
          title="Start with a workflow"
          body="Create one in the library, or load the sample sales-order workflow to see runs and approvals working."
          action={
            <Link href={`/o/${orgId}/workflows`} className="text-accent-strong hover:underline">
              Open the workflow library
            </Link>
          }
        />
      ) : (
        <div className="grid gap-10 lg:grid-cols-2">
          <section aria-labelledby="chart-heading">
            <h2 id="chart-heading" className="t-label mb-4">
              Finished runs, last 7 days
            </h2>
            {m ? <DailyChart days={m.last_7_days} /> : <Skeleton className="h-44" />}
          </section>

          <section aria-labelledby="recent-heading">
            <h2 id="recent-heading" className="t-label mb-4">
              Latest runs
            </h2>
            {recent.data && recent.data.length > 0 ? (
              <ul className="border border-line">
                {recent.data.slice(0, 6).map((run) => (
                  <li key={run.id} className="border-b border-line last:border-0">
                    <Link
                      href={`/o/${orgId}/executions/${run.id}`}
                      className="flex items-center justify-between gap-3 px-3 py-2.5 hover:bg-surface-1"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-[13px] font-medium">{run.workflow_name}</span>
                        <span className="font-mono text-[11px] text-faint">{formatTime(run.started_at)}</span>
                      </span>
                      <ExecutionStatusBadge status={run.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No runs yet" body="Runs you start appear here with their status." />
            )}
          </section>
        </div>
      )}
    </div>
  );
}
