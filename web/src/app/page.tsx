"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useRequireSession } from "@/lib/session";

/** Entry point: routes a signed-in user to their organization, or to onboarding if they have none. */
export default function Home() {
  const router = useRouter();
  const session = useRequireSession();
  const orgs = useQuery({
    queryKey: ["orgs"],
    queryFn: api.orgs.list,
    enabled: Boolean(session.data),
  });

  useEffect(() => {
    if (!orgs.data) return;
    router.replace(orgs.data.length > 0 ? `/o/${orgs.data[0].id}` : "/onboarding");
  }, [orgs.data, router]);

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-3 px-6">
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-4 w-64" />
    </main>
  );
}
