"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";

import { Wordmark } from "@/components/auth-shell";
import { ServerUnavailable } from "@/components/server-unavailable";
import { Badge, Button, Skeleton } from "@/components/ui";
import { ApiError, api, isServerProblem } from "@/lib/api";
import { useRequireSession, useSignOut } from "@/lib/session";

const NAV = [
  { href: "", label: "Overview" },
  { href: "/workflows", label: "Workflows" },
  { href: "/executions", label: "Runs" },
  { href: "/approvals", label: "Approvals", adminOnly: true },
  { href: "/integrations", label: "Integrations" },
  { href: "/team", label: "Team" },
  { href: "/audit", label: "Audit log" },
];

export default function OrgLayout({ children }: { children: React.ReactNode }) {
  const { orgId } = useParams<{ orgId: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const session = useRequireSession();
  const signOut = useSignOut();
  const orgs = useQuery({ queryKey: ["orgs"], queryFn: api.orgs.list, enabled: Boolean(session.data) });
  const org = useQuery({
    queryKey: ["org", orgId],
    queryFn: () => api.orgs.get(orgId),
    enabled: Boolean(session.data),
    retry: false,
  });

  const metrics = useQuery({
    queryKey: ["metrics", orgId],
    queryFn: () => api.metrics.get(orgId),
    enabled: Boolean(org.data),
    refetchInterval: 10_000,
  });
  const isAdmin = org.data?.role === "owner" || org.data?.role === "admin";
  const pending = metrics.data?.pending_approvals ?? 0;

  const notFound = org.error instanceof ApiError && org.error.status === 404;
  // The workflow builder is a full-bleed workspace rather than a centered page.
  const fullBleed = /\/workflows\/[^/]+$/.test(pathname);

  if (session.isError || isServerProblem(org.error)) {
    return (
      <ServerUnavailable
        error={session.error ?? org.error}
        onRetry={() => {
          void session.refetch();
          void org.refetch();
        }}
      />
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-line bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-12 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <Wordmark compact />
          <span className="text-faint" aria-hidden>
            /
          </span>
          <label className="sr-only" htmlFor="org-switcher">
            Organization
          </label>
          <select
            id="org-switcher"
            value={orgId}
            onChange={(event) => {
              if (event.target.value === "__new") router.push("/onboarding");
              else router.push(`/o/${event.target.value}`);
            }}
            className="h-8 max-w-[10rem] truncate rounded-md border border-transparent bg-transparent px-1 text-[13px] hover:border-line-strong sm:max-w-[16rem]"
          >
            {orgs.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
            <option value="__new">New organization…</option>
          </select>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-[12px] text-muted sm:inline">{session.data?.user.email}</span>
            <Button variant="ghost" onClick={signOut}>
              Sign out
            </Button>
          </div>
        </div>
        <nav aria-label="Primary" className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4 sm:px-6">
          {NAV.filter((item) => !item.adminOnly || isAdmin).map((item) => {
            const href = `/o/${orgId}${item.href}`;
            const active = item.href === "" ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={item.label}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`-mb-px border-b-2 px-2.5 pb-2.5 pt-1 text-[13px] transition-colors ${
                  active ? "border-accent text-text" : "border-transparent text-muted hover:text-text"
                }`}
              >
                {item.label}
                {item.adminOnly && pending > 0 && (
                  <span
                    aria-label={`${pending} pending`}
                    className="ml-1.5 rounded-sm border border-warning/50 px-1 font-mono text-[10px] leading-4 text-warning"
                  >
                    {pending}
                  </span>
                )}
              </Link>
            );
          })}
          {org.data && (
            <span className="ml-auto shrink-0 pb-2">
              <Badge tone="accent">{org.data.role}</Badge>
            </span>
          )}
        </nav>
      </header>
      <main className={fullBleed ? "flex w-full flex-1 flex-col" : "mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6"}>
        {notFound ? (
          <p className="text-muted">This organization does not exist or you no longer have access to it.</p>
        ) : org.isLoading || session.isLoading ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-80" />
          </div>
        ) : (
          children
        )}
      </main>
    </div>
  );
}
