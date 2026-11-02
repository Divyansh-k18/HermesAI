"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Button, FormError } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

interface Props {
  orgId: string;
  workflowId: string;
  workflowName: string;
  versionNumber: number;
  template: Record<string, unknown>;
  onClose: () => void;
}

/** Starts a manual run. The payload is the data the workflow reads, such as an order. */
export function RunDialog({ orgId, workflowId, workflowName, versionNumber, template, onClose }: Props) {
  const router = useRouter();
  const [text, setText] = useState(() => JSON.stringify(template, null, 2));
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const areaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    areaRef.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit() {
    setErrors([]);
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      setErrors(["The data is not valid JSON."]);
      return;
    }
    if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
      setErrors(["The data must be a JSON object, such as {\"order\": {\"total\": 100}}."]);
      return;
    }
    setBusy(true);
    try {
      const run = await api.workflows.run(orgId, workflowId, { payload: payload as Record<string, unknown> });
      router.push(`/o/${orgId}/executions/${run.id}`);
    } catch (error) {
      setErrors(error instanceof ApiError ? error.messages : ["Could not reach the server."]);
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-title"
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-lg border border-line-strong bg-surface-1 p-5"
      >
        <p className="t-label">Run workflow</p>
        <h2 id="run-title" className="t-title mt-2">
          {workflowName} <span className="font-mono text-[12px] text-faint">v{versionNumber}</span>
        </h2>
        <p className="mt-2 text-[13px] text-muted">
          Enter the data this run starts with. It is pre-filled from the fields the workflow reads. Change the values to
          try different paths.
        </p>
        <label htmlFor="run-payload" className="mt-4 block text-[12px] font-medium text-muted">
          Run data (JSON)
        </label>
        <textarea
          id="run-payload"
          ref={areaRef}
          rows={9}
          spellCheck={false}
          value={text}
          onChange={(event) => setText(event.target.value)}
          className="mt-1.5 w-full rounded-md border border-line-strong bg-bg p-3 font-mono text-[12px] hover:border-faint focus-visible:border-accent"
        />
        <div className="mt-3">
          <FormError messages={errors} />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} loading={busy}>
            Run
          </Button>
        </div>
      </div>
    </div>
  );
}
