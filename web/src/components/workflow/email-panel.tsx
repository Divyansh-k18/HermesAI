"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Button, FormError } from "@/components/ui";
import { formatTime } from "@/components/status";
import { ApiError, api, type EmailCheckResult } from "@/lib/api";

const inputClass =
  "h-8 w-full rounded-md border border-line-strong bg-surface-1 px-2.5 text-[12px] text-text placeholder:text-faint " +
  "hover:border-faint focus-visible:border-accent";

function TextInput(props: React.InputHTMLAttributes<HTMLInputElement> & { label: string; id: string }) {
  const { label, id, ...rest } = props;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-[11px] text-muted">
        {label}
      </label>
      <input id={id} className={inputClass} {...rest} />
    </div>
  );
}

/** Connect a mailbox so each new email starts a run. Shown to owners and admins in the builder. */
export function EmailInboxPanel({
  orgId,
  workflowId,
  readsWithAI = false,
}: {
  orgId: string;
  workflowId: string;
  /** The workflow has an AI step, so customers can write orders in their own words. */
  readsWithAI?: boolean;
}) {
  const queryClient = useQueryClient();
  const info = useQuery({
    queryKey: ["email-inbox", orgId, workflowId],
    queryFn: () => api.workflows.emailInbox(orgId, workflowId),
  });
  const [editing, setEditing] = useState(false);
  const [host, setHost] = useState("imap.gmail.com");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [allowed, setAllowed] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [lastCheck, setLastCheck] = useState<EmailCheckResult | null>(null);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["email-inbox", orgId, workflowId] });
    void queryClient.invalidateQueries({ queryKey: ["executions", orgId] });
    void queryClient.invalidateQueries({ queryKey: ["metrics", orgId] });
  };
  const onError = (error: unknown) =>
    setErrors(error instanceof ApiError ? error.messages : ["Could not reach the server."]);

  const save = useMutation({
    mutationFn: () =>
      api.workflows.connectEmailInbox(orgId, workflowId, {
        imap_host: host.trim(),
        username: username.trim(),
        password: password || undefined,
        allowed_senders: allowed.trim(),
      }),
    onSuccess: () => {
      setErrors([]);
      setPassword("");
      setEditing(false);
      refresh();
    },
    onError,
  });
  const checkNow = useMutation({
    mutationFn: () => api.workflows.checkEmailInbox(orgId, workflowId),
    onSuccess: (result) => {
      setErrors(result.error ? [result.error] : []);
      setLastCheck(result);
      refresh();
    },
    onError,
  });
  const disconnect = useMutation({
    mutationFn: () => api.workflows.disconnectEmailInbox(orgId, workflowId),
    onSuccess: () => {
      setLastCheck(null);
      refresh();
    },
    onError,
  });

  const connected = info.data?.enabled ?? false;
  const startEditing = () => {
    if (info.data?.enabled) {
      setHost(info.data.imap_host ?? "imap.gmail.com");
      setUsername(info.data.username ?? "");
      setAllowed(info.data.allowed_senders ?? "");
    }
    setPassword("");
    setErrors([]);
    setEditing(true);
  };

  return (
    <section aria-labelledby="email-heading">
      <h2 id="email-heading" className="t-label mb-2">
        Email orders
      </h2>

      {!connected && !editing && (
        <div className="flex flex-col gap-2">
          {readsWithAI ? (
            <p className="text-[12px] text-muted">
              Connect a mailbox and every new email starts this workflow. The AI step reads each email, written in the
              customer&apos;s own words.
            </p>
          ) : (
            <p className="text-[12px] text-muted">
              Connect a mailbox and every new email starts this workflow. Order details are read from lines like{" "}
              <code className="font-mono text-text">Total: 75,000</code>.
            </p>
          )}
          <Button variant="secondary" className="self-start" onClick={startEditing}>
            Connect mailbox
          </Button>
        </div>
      )}

      {editing && (
        <form
          className="flex flex-col gap-2.5"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <TextInput id="mail-host" label="Mail server (IMAP)" value={host} onChange={(e) => setHost(e.target.value)} />
          <TextInput
            id="mail-user"
            label="Email address"
            type="email"
            autoComplete="off"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="orders@yourcompany.com"
          />
          <TextInput
            id="mail-password"
            label={connected ? "App password (leave empty to keep)" : "App password"}
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <TextInput
            id="mail-allowed"
            label="Only accept orders from (optional)"
            value={allowed}
            onChange={(e) => setAllowed(e.target.value)}
            placeholder="customer.com, buyer@shop.com"
          />
          <p className="text-[11px] leading-snug text-faint">
            For Gmail: turn on IMAP, then create an app password under Google Account, Security, 2-Step Verification.
            Hermes only reads new mail and never marks it as read.
          </p>
          <FormError messages={errors} />
          <div className="flex gap-2">
            <Button type="submit" loading={save.isPending} disabled={!username.trim() || (!connected && !password)}>
              Save and test
            </Button>
            <Button variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {connected && !editing && (
        <div className="flex flex-col gap-2.5">
          <p className="text-[12px]">
            Reading <span className="font-mono">{info.data?.username}</span>
            <span className="text-faint"> · {info.data?.imap_host}</span>
          </p>
          {info.data?.allowed_senders ? (
            <p className="text-[11px] text-muted">Only from: {info.data.allowed_senders}</p>
          ) : (
            <p className="text-[11px] text-warning">Anyone who emails this address can start a run.</p>
          )}
          <p className="text-[11px] text-faint">
            Checked automatically every minute
            {info.data?.last_checked_at ? ` · last ${formatTime(info.data.last_checked_at)}` : ""} ·{" "}
            {info.data?.runs_started ?? 0} order{info.data?.runs_started === 1 ? "" : "s"} started
          </p>
          {info.data?.last_error && !lastCheck && <p className="text-[11px] text-danger">{info.data.last_error}</p>}
          <FormError messages={errors} />
          {lastCheck && !lastCheck.error && (
            <p role="status" className="text-[12px]">
              {lastCheck.started === 0
                ? "No new order emails."
                : `${lastCheck.started} new order${lastCheck.started === 1 ? "" : "s"} started.`}
              {lastCheck.ignored > 0 && ` ${lastCheck.ignored} from unknown senders ignored.`}
              {lastCheck.run_ids[0] && (
                <>
                  {" "}
                  <Link href={`/o/${orgId}/executions/${lastCheck.run_ids[0]}`} className="text-accent-strong hover:underline">
                    Open the run
                  </Link>
                </>
              )}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => checkNow.mutate()} loading={checkNow.isPending}>
              Check now
            </Button>
            <Button variant="ghost" onClick={startEditing}>
              Edit
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                if (window.confirm("Disconnect this mailbox? New emails will no longer start runs.")) disconnect.mutate();
              }}
            >
              Disconnect
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
