"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";

import { Wordmark } from "@/components/auth-shell";
import { Badge, Button, Skeleton } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useRequireSession, useSignOut } from "@/lib/session";

const NAV = [
  { href: "", label: "Overview" },
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

  const notFound = org.error instanceof ApiError && org.error.status === 404;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-line bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-12 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <Wordmark />
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
        <nav aria-label="Primary" className="mx-auto flex max-w-6xl gap-1 px-4 sm:px-6">
          {NAV.map((item) => {
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
              </Link>
            );
          })}
          {org.data && (
            <span className="ml-auto pb-2">
              <Badge tone="accent">{org.data.role}</Badge>
            </span>
          )}
        </nav>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
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
