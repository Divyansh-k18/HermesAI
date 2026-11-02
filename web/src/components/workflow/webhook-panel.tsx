"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Badge, Button, FormError } from "@/components/ui";
import { formatTime } from "@/components/status";
import { ApiError, api, type WebhookSecret } from "@/lib/api";

function Copyable({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] text-faint">{label}</span>
      <div className="flex items-start gap-2">
        <code className="min-w-0 flex-1 break-all rounded-md border border-line bg-bg px-2 py-1.5 font-mono text-[11px]">
          {value}
        </code>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className="shrink-0 rounded-md border border-line-strong px-2 py-1 text-[11px] text-muted hover:text-text"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

/** Lets owners and admins give a workflow a signed webhook so outside systems can start runs. */
export function WebhookPanel({ orgId, workflowId }: { orgId: string; workflowId: string }) {
  const queryClient = useQueryClient();
  const [issued, setIssued] = useState<WebhookSecret | null>(null);
  const [errors, setErrors] = useState<string[]>([]);

  const info = useQuery({ queryKey: ["webhook", orgId, workflowId], queryFn: () => api.workflows.webhook(orgId, workflowId) });
  const events = useQuery({
    queryKey: ["webhook-events", orgId, workflowId],
    queryFn: () => api.workflows.webhookEvents(orgId, workflowId),
    enabled: Boolean(info.data?.enabled),
    refetchInterval: 5000,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["webhook", orgId, workflowId] });
    void queryClient.invalidateQueries({ queryKey: ["webhook-events", orgId, workflowId] });
  };
  const onError = (error: unknown) =>
    setErrors(error instanceof ApiError ? error.messages : ["Could not reach the server."]);

  const issue = useMutation({
    mutationFn: () => api.workflows.createOrRotateWebhook(orgId, workflowId),
    onSuccess: (created) => {
      setErrors([]);
      setIssued(created);
      refresh();
    },
    onError,
  });
  const remove = useMutation({
    mutationFn: () => api.workflows.deleteWebhook(orgId, workflowId),
    onSuccess: () => {
      setIssued(null);
      refresh();
    },
    onError,
  });

  const enabled = info.data?.enabled ?? false;
  const url = info.data?.path ? `${window.location.origin}${info.data.path}` : "";

  return (
    <section aria-labelledby="webhook-heading">
      <h2 id="webhook-heading" className="t-label mb-2">
        Webhook trigger
      </h2>
      <FormError messages={errors} />

      {!enabled ? (
        <div className="flex flex-col gap-2">
          <p className="text-[12px] text-muted">
            Let another system start this workflow by sending a signed HTTP request.
          </p>
          <Button variant="secondary" className="self-start" onClick={() => issue.mutate()} loading={issue.isPending}>
            Create webhook
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <Copyable label="URL" value={url} />

          {issued ? (
            <div className="flex flex-col gap-3 border border-accent/40 bg-accent-soft p-3" role="status">
              <p className="text-[12px]">
                Copy this signing secret now. It is stored encrypted and will not be shown again.
              </p>
              <Copyable label="Signing secret" value={issued.secret} />
              <Copyable
                label="Send a test event (from the backend folder)"
                value={`.venv\\Scripts\\python scripts\\send_webhook.py ${url} ${issued.secret}`}
              />
            </div>
          ) : (
            <p className="text-[11px] leading-snug text-faint">
              Requests are signed with HMAC-SHA256 over the timestamp and body. Lost the secret? Rotate it.
            </p>
          )}

          <div className="flex gap-2">
            <Button
              variant="ghost"
              onClick={() => {
                if (window.confirm("Rotate the secret? Senders using the old one will be refused immediately.")) issue.mutate();
              }}
              disabled={issue.isPending}
            >
              Rotate secret
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                if (window.confirm("Delete this webhook? Its URL will stop working.")) remove.mutate();
              }}
              disabled={remove.isPending}
            >
              Delete
            </Button>
          </div>

          <div>
            <p className="mb-1.5 text-[11px] text-faint">
              Recent deliveries{info.data?.last_received_at ? ` · last ${formatTime(info.data.last_received_at)}` : ""}
            </p>
            {events.data && events.data.length > 0 ? (
              <ul className="flex flex-col gap-1">
                {events.data.slice(0, 6).map((event) => (
                  <li key={event.event_id} className="flex items-center justify-between gap-2 text-[11px]">
                    <span className="min-w-0 truncate font-mono text-muted" title={event.error ?? undefined}>
                      {event.event_id}
                    </span>
                    {event.execution_id ? (
                      <Link href={`/o/${orgId}/executions/${event.execution_id}`} className="shrink-0">
                        <Badge tone="success">run</Badge>
                      </Link>
                    ) : (
                      <Badge tone="danger">{event.status}</Badge>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[11px] text-faint">No deliveries yet.</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
