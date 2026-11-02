"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthShell } from "@/components/auth-shell";
import { Button, Field, FormError } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { useRequireSession } from "@/lib/session";

const schema = z.object({ name: z.string().trim().min(2, "Use at least 2 characters.").max(200) });
type Values = z.infer<typeof schema>;

export default function OnboardingPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const session = useRequireSession();
  const [errors, setErrors] = useState<string[]>([]);
  const {
    register,
    handleSubmit,
    formState: { errors: fieldErrors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async ({ name }) => {
    setErrors([]);
    try {
      const org = await api.orgs.create(name);
      await queryClient.invalidateQueries({ queryKey: ["orgs"] });
      router.replace(`/o/${org.id}`);
    } catch (error) {
      setErrors(error instanceof ApiError ? error.messages : ["Could not reach the server."]);
    }
  });

  return (
    <AuthShell
      title="Name your organization"
      subtitle={session.data ? `Signed in as ${session.data.user.email}. You will be its owner.` : "One moment."}
      footer={<>You can invite teammates once it exists.</>}
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        <FormError messages={errors} />
        <Field label="Organization name" error={fieldErrors.name?.message} {...register("name")} />
        <Button type="submit" loading={isSubmitting} className="mt-2 h-9">
          Create organization
        </Button>
      </form>
    </AuthShell>
  );
}
