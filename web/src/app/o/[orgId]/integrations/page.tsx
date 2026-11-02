"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Badge, Button, EmptyState, Field, FormError, Skeleton } from "@/components/ui";
import { formatTime } from "@/components/status";
import { ApiError, api } from "@/lib/api";

const CATALOG: { name: string; body: string; status: "available" | "planned" }[] = [
  {
    name: "Generic REST API",
    body: "Call any HTTPS API from an HTTP step. Credentials are stored as encrypted connections below.",
    status: "available",
  },
  {
    name: "Inbound webhooks",
    body: "Any system can start a workflow with a signed request. Set one up in the workflow builder.",
    status: "available",
  },
  { name: "HubSpot CRM", body: "Read customers and update deals from CRM steps.", status: "planned" },
  { name: "ERPNext", body: "Check stock and create sales orders from ERP steps.", status: "planned" },
  { name: "Gmail and Google Workspace", body: "Send email from email steps.", status: "planned" },
  { name: "PostgreSQL", body: "Query and update a database from database steps.", status: "planned" },
];

function messagesOf(error: unknown): string[] {
  return error instanceof ApiError ? error.messages : ["Could not reach the server."];
}

export default function IntegrationsPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const queryClient = useQueryClient();
  const org = useQuery({ queryKey: ["org", orgId], queryFn: () => api.orgs.get(orgId) });
  const connections = useQuery({ queryKey: ["connections", orgId], queryFn: () => api.connections.list(orgId) });
  const canManage = org.data?.role === "owner" || org.data?.role === "admin";

  const [name, setName] = useState("");
  const [header, setHeader] = useState("Authorization");
  const [secret, setSecret] = useState("");
  const [errors, setErrors] = useState<string[]>([]);

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["connections", orgId] });

  const create = useMutation({
    mutationFn: () => api.connections.create(orgId, { name: name.trim(), header_name: header.trim(), secret }),
    onSuccess: () => {
      setErrors([]);
      setName("");
      setSecret("");
      refresh();
    },
    onError: (error) => setErrors(messagesOf(error)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.connections.remove(orgId, id),
    onSuccess: refresh,
    onError: (error) => setErrors(messagesOf(error)),
  });

  return (
    <div className="rise-in flex flex-col gap-10">
      <header>
        <p className="t-label">Integrations</p>
        <h1 className="t-title mt-3 text-2xl">Connected systems</h1>
        <p className="mt-1.5 max-w-xl text-muted">
          What Hermes can talk to today, and what is coming. Nothing here is simulated: planned connectors are not
          available until they are built and tested against a real account.
        </p>
      </header>

      <section aria-label="Connectors" className="border border-line">
        {CATALOG.map((item) => (
          <div
            key={item.name}
            className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3.5 last:border-0"
          >
            <div className="min-w-0 max-w-xl">
              <p className="text-[14px] font-medium">{item.name}</p>
              <p className="mt-0.5 text-[13px] text-muted">{item.body}</p>
            </div>
            {item.status === "available" ? <Badge tone="success">available</Badge> : <Badge>planned</Badge>}
          </div>
        ))}
      </section>

      <section aria-labelledby="connections-heading" className="grid gap-8 lg:grid-cols-2">
        <div>
          <h2 id="connections-heading" className="t-label mb-3">
            Connections
          </h2>
          <p className="mb-4 text-[13px] text-muted">
            A connection adds one header, such as an API key, to an HTTP step&apos;s request. The value is encrypted
            and never shown again, not even to owners.
          </p>
          <FormError messages={errors} />
          {connections.isLoading ? (
            <Skeleton className="h-16" />
          ) : connections.data && connections.data.length > 0 ? (
            <ul className="border border-line">
              {connections.data.map((connection) => (
                <li
                  key={connection.id}
                  className="flex items-center justify-between gap-3 border-b border-line px-3 py-2.5 last:border-0"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium">{connection.name}</p>
                    <p className="font-mono text-[11px] text-faint">
                      {connection.header_name}: •••••• · added {formatTime(connection.created_at)}
                    </p>
                  </div>
                  {canManage && (
                    <Button
                      variant="ghost"
                      onClick={() => {
                        if (window.confirm(`Delete ${connection.name}? HTTP steps using it will fail until changed.`)) {
                          remove.mutate(connection.id);
                        }
                      }}
                    >
                      Delete
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No connections yet" body="HTTP steps can still call public APIs that need no credentials." />
          )}
        </div>

        {canManage ? (
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              setErrors([]);
              create.mutate();
            }}
          >
            <h2 className="t-label">Add a connection</h2>
            <Field label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Inventory API" maxLength={100} />
            <Field
              label="Header"
              value={header}
              onChange={(e) => setHeader(e.target.value)}
              hint="Usually Authorization or X-Api-Key."
              maxLength={100}
            />
            <Field
              label="Value"
              type="password"
              autoComplete="off"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="Bearer sk_live_..."
              hint="Stored encrypted. You will not see it again."
            />
            <Button type="submit" className="self-start" loading={create.isPending} disabled={!name.trim() || !secret}>
              Save connection
            </Button>
          </form>
        ) : (
          <p className="text-[13px] text-muted">Only owners and admins can add or delete connections.</p>
        )}
      </section>
    </div>
  );
}
