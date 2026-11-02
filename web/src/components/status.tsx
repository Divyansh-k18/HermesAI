import { Badge } from "@/components/ui";
import type { ExecutionStatus, StepRecord } from "@/lib/api";

const LABELS: Record<ExecutionStatus, string> = {
  running: "running",
  waiting_approval: "waiting for approval",
  waiting_timer: "waiting (delay)",
  succeeded: "succeeded",
  failed: "failed",
  rejected: "rejected",
  cancelled: "cancelled",
};

const TONES: Record<ExecutionStatus, "neutral" | "accent" | "success" | "warning" | "danger"> = {
  running: "accent",
  waiting_approval: "warning",
  waiting_timer: "warning",
  succeeded: "success",
  failed: "danger",
  rejected: "danger",
  cancelled: "neutral",
};

export function ExecutionStatusBadge({ status }: { status: ExecutionStatus }) {
  return <Badge tone={TONES[status]}>{LABELS[status]}</Badge>;
}

export function StepStatusBadge({ status }: { status: StepRecord["status"] }) {
  const tone = status === "succeeded" ? "success" : status === "failed" ? "danger" : status === "waiting" ? "warning" : "neutral";
  return <Badge tone={tone}>{status}</Badge>;
}

export const TERMINAL: ExecutionStatus[] = ["succeeded", "failed", "rejected", "cancelled"];

/** The API returns naive UTC timestamps. Append Z so the browser converts them to local time. */
export function parseTime(value: string): Date {
  return new Date(value.endsWith("Z") ? value : `${value}Z`);
}

export function formatTime(value: string | null): string {
  return value ? parseTime(value).toLocaleString() : "—";
}

export function formatDuration(start: string, end: string | null): string {
  if (!end) return "—";
  const ms = parseTime(end).getTime() - parseTime(start).getTime();
  if (ms < 1000) return `${Math.max(ms, 0)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  return `${Math.floor(seconds / 60)} m ${Math.round(seconds % 60)} s`;
}

export function formatSeconds(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  return `${(seconds / 60).toFixed(1)} min`;
}
