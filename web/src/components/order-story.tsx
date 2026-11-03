"use client";

import { Badge } from "@/components/ui";
import type { ExecutionDetail } from "@/lib/api";

type Obj = Record<string, unknown>;

const obj = (value: unknown): Obj | null =>
  typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Obj) : null;
const text = (value: unknown): string | null => (typeof value === "string" && value.trim() ? value : null);
const num = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);
const rupees = (value: number) => `₹${value.toLocaleString("en-IN")}`;

const LINE_TONE: Record<string, "success" | "warning" | "danger"> = {
  available: "success",
  short: "warning",
  quantity_unknown: "warning",
  out_of_stock: "danger",
  not_stocked: "danger",
};

/** What happened to the order, in plain words, from the run's status and the step where it stopped. */
function decisionOf(run: ExecutionDetail): { tone: "success" | "warning" | "danger" | "neutral"; label: string } {
  const pending = run.approvals.find((approval) => approval.status === "pending");
  if (run.status === "waiting_approval") return { tone: "warning", label: pending ? pending.title : "Waiting for approval" };
  if (run.status === "failed") return { tone: "danger", label: run.error ?? "The run failed" };
  if (run.status === "cancelled") return { tone: "neutral", label: "Cancelled" };
  const last = run.steps[run.steps.length - 1];
  if (run.status === "succeeded" && last?.node_type === "end") {
    const rejected = run.outcome === "rejected";
    return { tone: rejected ? "danger" : "success", label: last.node_label || (rejected ? "Rejected" : "Completed") };
  }
  return { tone: "neutral", label: run.status.replace("_", " ") };
}

function Card({ step, title, children }: { step: number; title: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 border border-line p-3">
      <p className="t-label">
        {step}. {title}
      </p>
      {children}
    </div>
  );
}

/** One card that tells the order's story: the email, what the AI read, the stock check, and the decision. */
export function OrderStory({ run }: { run: ExecutionDetail }) {
  const email = obj(run.variables.email);
  const order = obj(run.variables.order);
  const stock = obj(run.variables.stock);
  if (!email && !order) return null;

  const items = Array.isArray(order?.items) ? (order.items as unknown[]).map(obj).filter((i): i is Obj => i !== null) : [];
  const lines = Array.isArray(stock?.lines) ? (stock.lines as unknown[]).map(obj).filter((l): l is Obj => l !== null) : [];
  const missing = Array.isArray(order?.missing_information) ? (order.missing_information as unknown[]).map(String) : [];
  const total = num(order?.total);
  const confidence = num(order?.confidence);
  const decision = decisionOf(run);

  return (
    <section aria-labelledby="story-heading">
      <h2 id="story-heading" className="t-label mb-3">
        Order email
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Card step={1} title={run.trigger_type === "email" ? "Email received" : "Email (test run)"}>
          {email ? (
            <>
              <p className="truncate text-[12px] text-muted">{text(email.from) ?? "unknown sender"}</p>
              {text(email.subject) && <p className="truncate text-[13px] font-medium">{text(email.subject)}</p>}
              <p className="line-clamp-5 whitespace-pre-line text-[12px] text-muted">{text(email.body) ?? "(no text)"}</p>
            </>
          ) : (
            <p className="text-[12px] text-faint">No email in this run.</p>
          )}
        </Card>

        <Card step={2} title="AI read the order">
          {order ? (
            <>
              <p className="text-[13px] font-medium">{text(order.customer_name) ?? "Customer not named"}</p>
              {items.length > 0 ? (
                <ul className="text-[12px] text-muted">
                  {items.map((item, index) => (
                    <li key={index}>
                      {num(item.quantity) ?? "?"} × {text(item.name) ?? "item"}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[12px] text-faint">No items found.</p>
              )}
              <p className="text-[13px]">
                Total <span className="font-mono">{total !== null ? rupees(total) : "not stated"}</span>
              </p>
              {confidence !== null && (
                <p className="text-[12px] text-muted">
                  AI confidence {Math.round(confidence * 100)}%
                  {confidence < 0.6 && <span className="text-warning"> · low</span>}
                </p>
              )}
              {missing.length > 0 && <p className="text-[12px] text-faint">Not in the email: {missing.join(", ")}</p>}
            </>
          ) : (
            <p className="text-[12px] text-faint">Not read yet.</p>
          )}
        </Card>

        <Card step={3} title="Stock check">
          {stock ? (
            <>
              <ul className="flex flex-col gap-1">
                {lines.map((line, index) => (
                  <li key={index} className="flex flex-wrap items-center justify-between gap-1.5 text-[12px]">
                    <span className="min-w-0 truncate">{text(line.matched) ?? text(line.item) ?? "item"}</span>
                    <Badge tone={LINE_TONE[String(line.status)] ?? "neutral"}>
                      {String(line.status).replaceAll("_", " ")}
                      {num(line.available) !== null && line.status !== "not_stocked" ? ` · ${num(line.available)} left` : ""}
                    </Badge>
                  </li>
                ))}
              </ul>
              <p className={`text-[12px] ${stock.status === "in_stock" ? "text-success" : "text-warning"}`}>
                {text(stock.summary) ?? String(stock.status)}
              </p>
            </>
          ) : (
            <p className="text-[12px] text-faint">Stock was not checked in this run.</p>
          )}
        </Card>

        <Card step={4} title="Decision">
          <span className="self-start">
            <Badge tone={decision.tone}>{run.status.replace("_", " ")}</Badge>
          </span>
          <p className="text-[13px] font-medium">{decision.label}</p>
        </Card>
      </div>
    </section>
  );
}
