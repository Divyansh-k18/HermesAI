"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthShell } from "@/components/auth-shell";
import { Button, Field, FormError } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { safeNext } from "@/lib/redirect";
import { SESSION_KEY } from "@/lib/session";

const schema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
type Values = z.infer<typeof schema>;

export default function LoginPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [errors, setErrors] = useState<string[]>([]);
  const {
    register,
    handleSubmit,
    formState: { errors: fieldErrors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    setErrors([]);
    try {
      const state = await api.auth.login(values);
      queryClient.setQueryData(SESSION_KEY, state);
      router.replace(safeNext(window.location.search));
    } catch (error) {
      setErrors(error instanceof ApiError ? error.messages : ["Could not reach the server."]);
    }
  });

  return (
    <AuthShell
      title="Sign in"
      subtitle="Welcome back to Hermes."
      footer={
        <>
          New to Hermes?{" "}
          <Link href="/register" className="text-accent-strong hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        <FormError messages={errors} />
        <Field label="Email" type="email" autoComplete="email" error={fieldErrors.email?.message} {...register("email")} />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          error={fieldErrors.password?.message}
          {...register("password")}
        />
        <Button type="submit" loading={isSubmitting} className="mt-2 h-9">
          Sign in
        </Button>
      </form>
    </AuthShell>
  );
}
