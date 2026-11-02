"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthShell } from "@/components/auth-shell";
import { Button, FormError } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";

function AcceptInvitation() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = useSearchParams().get("token") ?? "";
  const session = useSession();
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function accept() {
    setBusy(true);
    setErrors([]);
    try {
      const org = await api.invitations.accept(token);
      await queryClient.invalidateQueries({ queryKey: ["orgs"] });
      router.replace(`/o/${org.id}`);
    } catch (error) {
      setErrors(error instanceof ApiError ? error.messages : ["Could not reach the server."]);
      setBusy(false);
    }
  }

  if (!token) {
    return <FormError messages={["This invitation link is missing its token."]} />;
  }

  if (session.data === null) {
    const next = encodeURIComponent(`/invite?token=${token}`);
    return (
      <div className="flex flex-col gap-3">
        <p className="text-muted">Sign in with the email address that was invited, then return to this link.</p>
        <Link href={`/login?next=${next}`} className="text-accent-strong hover:underline">
          Sign in
        </Link>
        <Link href={`/register?next=${next}`} className="text-accent-strong hover:underline">
          Create an account
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <FormError messages={errors} />
      <Button onClick={accept} loading={busy || session.isLoading} className="h-9">
        Accept invitation
      </Button>
    </div>
  );
}

export default function InvitePage() {
  return (
    <AuthShell
      title="Join an organization"
      subtitle="Accepting adds you to the organization with the role you were invited as."
      footer={<>The invitation must match your account email.</>}
    >
      <Suspense>
        <AcceptInvitation />
      </Suspense>
    </AuthShell>
  );
}
