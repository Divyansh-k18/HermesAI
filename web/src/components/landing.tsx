import Link from "next/link";

import { Wordmark } from "@/components/auth-shell";
import { HeroVisual } from "@/components/hero-visual";

/**
 * An original diagram of what Hermes does: a trigger, a decision, a person, and a recorded outcome.
 * Dashes on the connections move to suggest flow. They stop for people who prefer reduced motion.
 */
function FlowDiagram() {
  const node = (x: number, y: number, label: string, kind: string, tone: "line" | "accent" | "warning" | "success") => {
    const stroke =
      tone === "accent" ? "var(--accent)" : tone === "warning" ? "var(--warning)" : tone === "success" ? "var(--success)" : "var(--line-strong)";
    return (
      <g transform={`translate(${x} ${y})`}>
        <rect width="156" height="56" rx="6" fill="var(--surface-2)" stroke={stroke} />
        <text x="12" y="21" fontSize="9" letterSpacing="1.2" fill="var(--text-faint)" fontFamily="var(--font-mono)">
          {kind.toUpperCase()}
        </text>
        <text x="12" y="40" fontSize="13" fontWeight="500" fill="var(--text)">
          {label}
        </text>
      </g>
    );
  };
  const edge = (d: string, label?: { x: number; y: number; text: string }) => (
    <>
      <path d={d} fill="none" stroke="var(--text-faint)" strokeWidth="1.25" className="flow-dash" />
      {label && (
        <text x={label.x} y={label.y} fontSize="10" fill="var(--text-muted)" fontFamily="var(--font-mono)">
          {label.text}
        </text>
      )}
    </>
  );

  return (
    <svg viewBox="0 0 860 330" role="img" aria-label="A workflow: an order arrives, a condition checks the amount, a manager approves or rejects, and the outcome is recorded." className="w-full min-w-[720px]">
      {edge("M156 56 H214")}
      {edge("M370 56 H428")}
      {edge("M584 56 C 636 56, 636 28, 688 28", { x: 598, y: 20, text: "approved" })}
      {edge("M584 56 C 636 56, 636 116, 688 116", { x: 598, y: 114, text: "rejected" })}
      {edge("M292 84 V 196 C 292 214, 306 224, 324 224 H 428", { x: 300, y: 160, text: "under limit" })}
      {node(0, 28, "Order received", "trigger", "line")}
      {node(214, 28, "Over ₹50,000?", "condition", "accent")}
      {node(428, 28, "Manager approval", "approval", "warning")}
      {node(688, 0, "Order approved", "end", "success")}
      {node(688, 88, "Order rejected", "end", "line")}
      {node(428, 196, "Auto-approved", "end", "success")}
      <g transform="translate(0 270)">
        <rect width="844" height="44" rx="6" fill="var(--surface-1)" stroke="var(--line)" />
        <text x="14" y="18" fontSize="9" letterSpacing="1.2" fill="var(--text-faint)" fontFamily="var(--font-mono)">
          RECORDED FOR EVERY RUN
        </text>
        <text x="14" y="34" fontSize="12" fill="var(--text-muted)">
          each step · its input and output · who decided · trace ID
        </text>
      </g>
    </svg>
  );
}

const PRINCIPLES = [
  {
    title: "Visible",
    body: "Every run keeps each step with what went in and what came out. Nothing happens in the dark.",
  },
  {
    title: "Accountable",
    body: "When a decision needs a person, the run pauses and asks the right role. It continues only if they approve.",
  },
  {
    title: "Safe by default",
    body: "Published versions are frozen. Rejected work never takes the approved path. Every action is checked on the server and logged.",
  },
];

const LIVE = [
  "Visual workflow builder with versions",
  "Execution engine that survives restarts",
  "Human approvals with role checks",
  "Signed webhooks and HTTP calls to any API",
  "Team roles and organization isolation",
  "Audit log with trace IDs",
];

const NEXT = [
  "HubSpot, ERPNext, and Gmail connectors",
  "AI agent steps with strict tool permissions",
  "Webhook triggers with signature checks",
  "Temporal for distributed execution",
];

export function Landing() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-line">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Wordmark />
          <nav aria-label="Account" className="flex items-center gap-2">
            <Link href="/login" className="rounded-md px-3 py-1.5 text-[13px] text-muted hover:text-text">
              Sign in
            </Link>
            <Link
              href="/register"
              className="rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-on-accent transition-colors hover:bg-accent-strong"
            >
              Create account
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <section className="mx-auto max-w-6xl px-4 pb-16 pt-12 sm:px-6 sm:pt-16">
          <div className="grid items-center gap-6 lg:grid-cols-[1.05fr_1fr]">
            <div>
              <p className="t-label">Workflow automation with human accountability</p>
              <h1 className="t-display mt-5 max-w-3xl">Intelligence in motion.</h1>
              <p className="mt-6 max-w-xl text-[16px] leading-relaxed text-muted">
                Design a workflow, publish it, and run it. When a decision needs a person, Hermes pauses, asks the
                right role, and continues only on approval. Every step is recorded.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link
                  href="/register"
                  className="rounded-md bg-accent px-4 py-2 text-[14px] font-medium text-on-accent transition-colors hover:bg-accent-strong"
                >
                  Create an account
                </Link>
                <Link
                  href="/login"
                  className="rounded-md border border-line-strong px-4 py-2 text-[14px] transition-colors hover:bg-surface-2"
                >
                  Sign in
                </Link>
              </div>
            </div>
            <HeroVisual />
          </div>

          {/* The diagram keeps a readable size and scrolls sideways inside its own box on small screens. */}
          <div className="mt-14 overflow-x-auto border border-line bg-surface-1 p-4 sm:p-6">
            <FlowDiagram />
          </div>
        </section>

        <section aria-label="Principles" className="border-t border-line">
          <div className="mx-auto grid max-w-6xl gap-px bg-line sm:grid-cols-3">
            {PRINCIPLES.map((item) => (
              <div key={item.title} className="bg-bg px-4 py-8 sm:px-6">
                <h2 className="t-title">{item.title}</h2>
                <p className="mt-2 text-[14px] leading-relaxed text-muted">{item.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section aria-label="Status" className="border-t border-line">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:grid-cols-2 sm:px-6">
            <div>
              <h2 className="t-label mb-4">Working today</h2>
              <ul className="flex flex-col gap-2 text-[14px]">
                {LIVE.map((item) => (
                  <li key={item} className="flex gap-3">
                    <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-[2px] bg-success" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h2 className="t-label mb-4">Coming next</h2>
              <ul className="flex flex-col gap-2 text-[14px] text-muted">
                {NEXT.map((item) => (
                  <li key={item} className="flex gap-3">
                    <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-[2px] border border-line-strong" />
                    {item}
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-[12px] text-faint">
                Steps that need these systems are in the builder today and stop with a clear message when run.
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 text-[12px] text-faint sm:px-6">
          <span>Hermes AI</span>
          <span className="font-mono">Intelligence in motion</span>
        </div>
      </footer>
    </div>
  );
}
