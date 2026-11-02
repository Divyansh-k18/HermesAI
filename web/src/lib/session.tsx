"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ApiError, api, type AuthState } from "@/lib/api";

export const SESSION_KEY = ["session"] as const;

/** Current session. `data` is null when signed out, undefined while loading. */
export function useSession() {
  return useQuery<AuthState | null>({
    queryKey: SESSION_KEY,
    queryFn: async () => {
      try {
        return await api.auth.me();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
  });
}

/** Redirects to /login when signed out. Returns the session once available. */
export function useRequireSession() {
  const router = useRouter();
  const session = useSession();
  useEffect(() => {
    if (session.data === null) router.replace("/login");
  }, [session.data, router]);
  return session;
}

export function useSignOut() {
  const router = useRouter();
  const queryClient = useQueryClient();
  return async () => {
    try {
      await api.auth.logout();
    } finally {
      queryClient.clear();
      router.replace("/login");
    }
  };
}
