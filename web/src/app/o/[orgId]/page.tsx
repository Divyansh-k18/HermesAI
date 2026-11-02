"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { EmptyState } from "@/components/ui";
import { api } from "@/lib/api";

export default function OverviewPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const org = useQuery({ queryKey: ["org", orgId], queryFn: () => api.orgs.get(orgId) });
  const members = useQuery({ queryKey: ["members", orgId], queryFn: () => api.orgs.members(orgId) });

  return (
    <div className="rise-in flex flex-col gap-10">
      <section>
        <p className="t-label">Organization</p>
        <h1 className="t-display mt-3">{org.data?.name}</h1>
        <dl className="mt-6 grid max-w-xl grid-cols-[8rem_1fr] gap-y-2 text-[13px]">
          <dt className="text-faint">Plan</dt>
          <dd className="font-mono">{org.data?.plan_code}</dd>
          <dt className="text-faint">Your role</dt>
          <dd className="font-mono">{org.data?.role}</dd>
          <dt className="text-faint">Members</dt>
          <dd className="font-mono">{members.data?.length ?? "…"}</dd>
        </dl>
      </section>
      <section>
        <p className="t-label mb-3">Workflows</p>
        <EmptyState
          title="Workflows are not available yet"
          body="Identity, teams, and audit are live. The workflow builder and execution engine are the next milestones, so there is nothing to run here yet."
        />
      </section>
    </div>
  );
}
