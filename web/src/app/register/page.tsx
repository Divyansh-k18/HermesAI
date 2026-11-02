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

// Mirrors the server policy so people get feedback before submitting. The server remains the authority.
const schema = z.object({
  full_name: z.string().trim().min(1, "Enter your name.").max(200),
  email: z.string().email("Enter a valid email address."),
  password: z
    .string()
    .min(12, "Use at least 12 characters.")
    .refine((value) => value !== value.toLowerCase() && value !== value.toUpperCase(), "Mix upper and lower case letters.")
    .refine((value) => /\d/.test(value), "Include at least one digit."),
});
type Values = z.infer<typeof schema>;

export default function RegisterPage() {
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
      const state = await api.auth.register(values);
      queryClient.setQueryData(SESSION_KEY, state);
      router.replace(safeNext(window.location.search));
    } catch (error) {
      setErrors(error instanceof ApiError ? error.messages : ["Could not reach the server."]);
    }
  });

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start by creating an account. You will set up your organization next."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="text-accent-strong hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        <FormError messages={errors} />
        <Field label="Full name" autoComplete="name" error={fieldErrors.full_name?.message} {...register("full_name")} />
        <Field label="Work email" type="email" autoComplete="email" error={fieldErrors.email?.message} {...register("email")} />
        <Field
          label="Password"
          type="password"
          autoComplete="new-password"
          hint="At least 12 characters, with mixed case and a digit."
          error={fieldErrors.password?.message}
          {...register("password")}
        />
        <Button type="submit" loading={isSubmitting} className="mt-2 h-9">
          Create account
        </Button>
      </form>
    </AuthShell>
  );
}
