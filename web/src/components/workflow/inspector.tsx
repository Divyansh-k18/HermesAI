"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Button, Badge } from "@/components/ui";
import { api, type WorkflowIssue } from "@/lib/api";
import { NODE_META, type FieldDef, type FlowNode } from "@/lib/workflow-meta";

const inputClass =
  "w-full rounded-md border border-line-strong bg-surface-1 px-2.5 text-[13px] text-text placeholder:text-faint " +
  "hover:border-faint focus-visible:border-accent disabled:opacity-60";

interface Props {
  node: FlowNode;
  readOnly: boolean;
  issues: WorkflowIssue[];
  onChange: (patch: { label?: string; config?: Record<string, unknown> }) => void;
  onDelete: () => void;
}

export function Inspector({ node, readOnly, issues, onChange, onDelete }: Props) {
  const meta = NODE_META[node.data.kind];
  const config = node.data.config;

  const setConfig = (key: string, value: unknown) => {
    const next = { ...config };
    if (value === "" || value === undefined) delete next[key];
    else next[key] = value;
    onChange({ config: next });
  };

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="t-label">{meta.label}</p>
        <p className="mt-2 text-[12px] text-muted">{meta.description}</p>
      </div>

      {node.data.kind === "ai_agent" && <AIStatusNote />}

      {issues.length > 0 && (
        <ul className="flex flex-col gap-1.5" aria-label="Issues for this step">
          {issues.map((issue, index) => (
            <li key={`${issue.code}-${index}`} className="text-[12px] text-danger">
              {issue.message}
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-col gap-1.5">
        <label htmlFor="node-label" className="text-[12px] font-medium text-muted">
          Name
        </label>
        <input
          id="node-label"
          value={node.data.label}
          disabled={readOnly}
          maxLength={120}
          placeholder={meta.label}
          onChange={(event) => onChange({ label: event.target.value })}
          className={`${inputClass} h-8`}
        />
      </div>

      {meta.fields.map((field) => (
        <FieldEditor
          key={field.key}
          field={field}
          config={config}
          readOnly={readOnly}
          onChange={(value) => setConfig(field.key, value)}
        />
      ))}

      {!readOnly && (
        <Button variant="danger" onClick={onDelete} className="self-start">
          Delete step
        </Button>
      )}
    </div>
  );
}

function FieldEditor({
  field,
  config,
  readOnly,
  onChange,
}: {
  field: FieldDef;
  config: Record<string, unknown>;
  readOnly: boolean;
  onChange: (value: unknown) => void;
}) {
  const id = `field-${field.key}`;
  const raw = config[field.key];

  // The "value" of a condition is irrelevant for the exists operator.
  if (field.key === "value" && config.operator === "exists") return null;

  let control: React.ReactNode;
  switch (field.kind) {
    case "textarea":
      control = (
        <textarea
          id={id}
          rows={5}
          disabled={readOnly}
          value={typeof raw === "string" ? raw : ""}
          placeholder={field.placeholder}
          onChange={(event) => onChange(event.target.value)}
          className={`${inputClass} py-2 leading-snug`}
        />
      );
      break;
    case "select":
      control = (
        <select
          id={id}
          disabled={readOnly}
          value={typeof raw === "string" ? raw : ""}
          onChange={(event) => onChange(event.target.value)}
          className={`${inputClass} h-8`}
        >
          <option value="">Choose…</option>
          {field.options?.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
      break;
    case "number":
      control = (
        <input
          id={id}
          type="number"
          min={1}
          disabled={readOnly}
          value={typeof raw === "number" ? raw : ""}
          onChange={(event) => onChange(event.target.value === "" ? undefined : Number(event.target.value))}
          className={`${inputClass} h-8 font-mono`}
        />
      );
      break;
    case "scalar":
      control = (
        <input
          id={id}
          disabled={readOnly}
          value={raw === undefined || raw === null ? "" : String(raw)}
          placeholder={field.placeholder}
          onChange={(event) => {
            const text = event.target.value;
            onChange(text.trim() !== "" && !Number.isNaN(Number(text)) ? Number(text) : text);
          }}
          className={`${inputClass} h-8 font-mono`}
        />
      );
      break;
    case "list":
      control = (
        <input
          id={id}
          disabled={readOnly}
          value={Array.isArray(raw) ? raw.join(", ") : ""}
          placeholder={field.placeholder}
          onChange={(event) =>
            onChange(
              event.target.value
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
            )
          }
          className={`${inputClass} h-8 font-mono`}
        />
      );
      break;
    case "mappings":
      control = <MappingsEditor value={raw} readOnly={readOnly} onChange={onChange} />;
      break;
    case "connection":
      control = <ConnectionSelect id={id} value={raw} readOnly={readOnly} onChange={onChange} />;
      break;
    default:
      control = (
        <input
          id={id}
          disabled={readOnly}
          value={typeof raw === "string" ? raw : ""}
          placeholder={field.placeholder}
          onChange={(event) => onChange(event.target.value)}
          className={`${inputClass} h-8`}
        />
      );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[12px] font-medium text-muted">
        {field.label}
      </label>
      {control}
      {field.hint && <p className="text-[11px] text-faint">{field.hint}</p>}
    </div>
  );
}

/** Says whether the server has an AI key, so a missing key shows up here instead of as a failed run. */
function AIStatusNote() {
  const status = useQuery({ queryKey: ["ai-status"], queryFn: () => api.ai.status(), staleTime: 60_000 });
  if (!status.data) return null;
  return status.data.configured ? (
    <p className="text-[12px] text-muted">
      <Badge tone="success">AI on</Badge> <span className="ml-1">{status.data.model}</span>
      <span className="text-faint"> · {status.data.provider}</span>
    </p>
  ) : (
    <div className="border border-warning/40 px-3 py-2 text-[12px] text-muted">
      <p className="font-medium text-text">AI is not set up on this server</p>
      <p className="mt-1">
        Runs will stop at this step. Add a free AI key to <code className="font-mono">backend/.env</code> and restart
        the backend. The README section “Turn on AI” shows how.
      </p>
    </div>
  );
}

/** Picks a stored connection by name. Only the id is saved in the workflow, never the secret. */
function ConnectionSelect({
  id,
  value,
  readOnly,
  onChange,
}: {
  id: string;
  value: unknown;
  readOnly: boolean;
  onChange: (value: unknown) => void;
}) {
  const { orgId } = useParams<{ orgId: string }>();
  const connections = useQuery({ queryKey: ["connections", orgId], queryFn: () => api.connections.list(orgId) });
  const selected = typeof value === "string" ? value : "";
  const missing = selected !== "" && connections.data !== undefined && !connections.data.some((c) => c.id === selected);

  return (
    <div className="flex flex-col gap-1.5">
      <select
        id={id}
        disabled={readOnly}
        value={selected}
        onChange={(event) => onChange(event.target.value || undefined)}
        className={`${inputClass} h-8`}
      >
        <option value="">No connection</option>
        {connections.data?.map((connection) => (
          <option key={connection.id} value={connection.id}>
            {connection.name} ({connection.header_name})
          </option>
        ))}
        {missing && <option value={selected}>Deleted connection</option>}
      </select>
      {missing && <p className="text-[11px] text-danger">This connection no longer exists. Runs will fail at this step.</p>}
      {connections.data?.length === 0 && (
        <Link href={`/o/${orgId}/integrations`} className="text-[11px] text-accent-strong hover:underline">
          Add a connection
        </Link>
      )}
    </div>
  );
}

interface Mapping {
  source: string;
  target: string;
}

function MappingsEditor({
  value,
  readOnly,
  onChange,
}: {
  value: unknown;
  readOnly: boolean;
  onChange: (value: unknown) => void;
}) {
  const rows: Mapping[] = Array.isArray(value) ? (value as Mapping[]) : [];
  const update = (next: Mapping[]) => onChange(next.length > 0 ? next : undefined);

  return (
    <div className="flex flex-col gap-2" id="field-mappings">
      {rows.length === 0 && <Badge>none yet</Badge>}
      {rows.map((row, index) => (
        <div key={index} className="grid grid-cols-[1fr_1fr_auto] items-center gap-1.5">
          <input
            aria-label={`Mapping ${index + 1} source`}
            disabled={readOnly}
            placeholder="source.path"
            value={row.source ?? ""}
            onChange={(event) => update(rows.map((r, i) => (i === index ? { ...r, source: event.target.value } : r)))}
            className={`${inputClass} h-8 font-mono text-[12px]`}
          />
          <input
            aria-label={`Mapping ${index + 1} target`}
            disabled={readOnly}
            placeholder="target_field"
            value={row.target ?? ""}
            onChange={(event) => update(rows.map((r, i) => (i === index ? { ...r, target: event.target.value } : r)))}
            className={`${inputClass} h-8 font-mono text-[12px]`}
          />
          {!readOnly && (
            <button
              type="button"
              aria-label={`Remove mapping ${index + 1}`}
              onClick={() => update(rows.filter((_, i) => i !== index))}
              className="h-8 rounded-md px-2 text-muted hover:bg-surface-3 hover:text-text"
            >
              ×
            </button>
          )}
        </div>
      ))}
      {!readOnly && (
        <Button variant="secondary" onClick={() => update([...rows, { source: "", target: "" }])} className="self-start">
          Add mapping
        </Button>
      )}
    </div>
  );
}
