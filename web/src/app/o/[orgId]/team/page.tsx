"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Badge, Button, EmptyState, Field, FormError, Skeleton } from "@/components/ui";
import { ApiError, api, type CreatedInvitation, type Member, type Role } from "@/lib/api";
import { useSession } from "@/lib/session";

const ALL_ROLES: Role[] = ["owner", "admin", "member", "viewer"];

// UI hints only. The server enforces these rules and is the authority.
function assignableRoles(actor: Role): Role[] {
  if (actor === "owner") return ALL_ROLES;
  if (actor === "admin") return ["member", "viewer"];
  return [];
}

function canManage(actor: Role, target: Role): boolean {
  if (actor === "owner") return true;
  if (actor === "admin") return target === "member" || target === "viewer";
  return false;
}

const inviteSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  role: z.enum(["owner", "admin", "member", "viewer"]),
});
type InviteValues = z.infer<typeof inviteSchema>;

function messagesOf(error: unknown): string[] {
  return error instanceof ApiError ? error.messages : ["Could not reach the server."];
}

export default function TeamPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const queryClient = useQueryClient();
  const session = useSession();
  const org = useQuery({ queryKey: ["org", orgId], queryFn: () => api.orgs.get(orgId) });
  const members = useQuery({ queryKey: ["members", orgId], queryFn: () => api.orgs.members(orgId) });
  const myRole = org.data?.role ?? "viewer";
  const canInvite = myRole === "owner" || myRole === "admin";
  const invitations = useQuery({
    queryKey: ["invitations", orgId],
    queryFn: () => api.orgs.invitations(orgId),
    enabled: canInvite,
  });

  const [errors, setErrors] = useState<string[]>([]);
  const [issued, setIssued] = useState<CreatedInvitation | null>(null);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["members", orgId] });
    void queryClient.invalidateQueries({ queryKey: ["invitations", orgId] });
    void queryClient.invalidateQueries({ queryKey: ["org", orgId] });
  };

  const changeRole = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: Role }) => api.orgs.changeRole(orgId, userId, role),
    onSuccess: () => {
      setErrors([]);
      refresh();
    },
    onError: (error) => setErrors(messagesOf(error)),
  });

  const removeMember = useMutation({
    mutationFn: (userId: string) => api.orgs.removeMember(orgId, userId),
    onSuccess: () => {
      setErrors([]);
      refresh();
    },
    onError: (error) => setErrors(messagesOf(error)),
  });

  const revoke = useMutation({
    mutationFn: (invitationId: string) => api.orgs.revokeInvitation(orgId, invitationId),
    onSuccess: refresh,
    onError: (error) => setErrors(messagesOf(error)),
  });

  const invite = useMutation({
    mutationFn: (values: InviteValues) => api.orgs.invite(orgId, values),
    onSuccess: (created) => {
      setErrors([]);
      setIssued(created);
      refresh();
    },
    onError: (error) => setErrors(messagesOf(error)),
  });

  const form = useForm<InviteValues>({
    resolver: zodResolver(inviteSchema),
    defaultValues: { email: "", role: "member" },
  });

  const inviteRoles = assignableRoles(myRole);
  const inviteLink = issued ? `${window.location.origin}/invite?token=${issued.token}` : "";

  return (
    <div className="rise-in flex flex-col gap-10">
      <header>
        <p className="t-label">Team</p>
        <h1 className="t-title mt-3 text-2xl">Members and access</h1>
      </header>

      <FormError messages={errors} />

      <section aria-labelledby="members-heading">
        <h2 id="members-heading" className="t-label mb-3">
          Members
        </h2>
        {members.isLoading ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
        ) : (
          <div className="overflow-x-auto border border-line">
            <table className="w-full min-w-[34rem] text-left text-[13px]">
              <thead className="border-b border-line text-faint">
                <tr>
                  <th className="px-3 py-2 font-normal">Name</th>
                  <th className="px-3 py-2 font-normal">Email</th>
                  <th className="px-3 py-2 font-normal">Role</th>
                  <th className="px-3 py-2 text-right font-normal">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {members.data?.map((member: Member) => {
                  const isSelf = member.user_id === session.data?.user.id;
                  const editable = canManage(myRole, member.role) && !isSelf;
                  return (
                    <tr key={member.user_id} className="border-b border-line last:border-0 hover:bg-surface-1">
                      <td className="px-3 py-2.5">
                        {member.full_name}
                        {isSelf && <span className="ml-2 text-faint">you</span>}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[12px] text-muted">{member.email}</td>
                      <td className="px-3 py-2.5">
                        {editable ? (
                          <select
                            aria-label={`Role for ${member.full_name}`}
                            value={member.role}
                            onChange={(event) =>
                              changeRole.mutate({ userId: member.user_id, role: event.target.value as Role })
                            }
                            className="h-7 rounded-md border border-line-strong bg-surface-1 px-1.5 text-[12px]"
                          >
                            {Array.from(new Set([member.role, ...assignableRoles(myRole)])).map((role) => (
                              <option key={role} value={role}>
                                {role}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <Badge tone={member.role === "owner" ? "accent" : "neutral"}>{member.role}</Badge>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {(editable || isSelf) && (
                          <Button
                            variant="danger"
                            onClick={() => {
                              const question = isSelf
                                ? "Leave this organization?"
                                : `Remove ${member.full_name} from this organization?`;
                              if (window.confirm(question)) removeMember.mutate(member.user_id);
                            }}
                          >
                            {isSelf ? "Leave" : "Remove"}
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {canInvite && (
        <section aria-labelledby="invite-heading" className="grid gap-8 lg:grid-cols-2">
          <div>
            <h2 id="invite-heading" className="t-label mb-3">
              Invite someone
            </h2>
            <form
              onSubmit={form.handleSubmit((values) => invite.mutate(values))}
              className="flex flex-col gap-4"
              noValidate
            >
              <Field label="Email" type="email" error={form.formState.errors.email?.message} {...form.register("email")} />
              <div className="flex flex-col gap-1.5">
                <label htmlFor="invite-role" className="text-[12px] font-medium text-muted">
                  Role
                </label>
                <select
                  id="invite-role"
                  className="h-9 rounded-md border border-line-strong bg-surface-1 px-2 text-[13px]"
                  {...form.register("role")}
                >
                  {inviteRoles.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" loading={invite.isPending} className="self-start">
                Create invitation
              </Button>
            </form>

            {issued && (
              <div className="mt-6 border border-accent/40 bg-accent-soft p-4" role="status">
                <p className="text-[13px] font-medium">Invitation created for {issued.email}</p>
                <p className="mt-1 text-[12px] text-muted">
                  Email delivery is not set up yet. Copy this link and send it yourself. It is shown only once.
                </p>
                <code className="mt-3 block break-all font-mono text-[11px]">{inviteLink}</code>
                <Button
                  variant="secondary"
                  className="mt-3"
                  onClick={() => void navigator.clipboard.writeText(inviteLink)}
                >
                  Copy link
                </Button>
              </div>
            )}
          </div>

          <div>
            <h2 className="t-label mb-3">Pending invitations</h2>
            {invitations.isLoading ? (
              <Skeleton className="h-10" />
            ) : invitations.data && invitations.data.length > 0 ? (
              <ul className="border border-line">
                {invitations.data.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-center justify-between gap-3 border-b border-line px-3 py-2.5 last:border-0"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-mono text-[12px]">{item.email}</p>
                      <p className="text-[12px] text-faint">
                        {item.role} · expires {new Date(item.expires_at).toLocaleDateString()}
                      </p>
                    </div>
                    <Button variant="ghost" onClick={() => revoke.mutate(item.id)}>
                      Revoke
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No pending invitations" body="Invitations you create appear here until they are accepted or expire." />
            )}
          </div>
        </section>
      )}
    </div>
  );
}
