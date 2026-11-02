"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Landing } from "@/components/landing";
import { ServerUnavailable } from "@/components/server-unavailable";
import { Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

/** Signed-out visitors see the landing page. Signed-in users go to their organization, or to onboarding. */
export default function Home() {
  const router = useRouter();
  const session = useSession();
  const orgs = useQuery({
    queryKey: ["orgs"],
    queryFn: api.orgs.list,
    enabled: Boolean(session.data),
  });

  useEffect(() => {
    if (!orgs.data) return;
    router.replace(orgs.data.length > 0 ? `/o/${orgs.data[0].id}` : "/onboarding");
  }, [orgs.data, router]);

  if (session.data === null) return <Landing />;
  // Without this, an unreachable backend would leave the loading placeholder on screen forever.
  if (session.isError || orgs.isError) {
    return (
      <ServerUnavailable
        error={session.error ?? orgs.error}
        onRetry={() => {
          void session.refetch();
          if (session.data) void orgs.refetch();
        }}
      />
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-3 px-6">
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-4 w-64" />
    </main>
  );
}
