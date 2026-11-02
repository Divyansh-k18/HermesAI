import Link from "next/link";
import type { ReactNode } from "react";

/** Wordmark: a node-and-edge glyph beside the name. Drawn in SVG so it inherits text color. */
export function Wordmark() {
  return (
    <Link href="/" className="inline-flex items-center gap-2.5" aria-label="Hermes AI home">
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden>
        <circle cx="11" cy="11" r="3" fill="var(--accent)" />
        <circle cx="3.5" cy="5" r="1.6" stroke="currentColor" strokeWidth="1.2" />
        <circle cx="18.5" cy="5" r="1.6" stroke="currentColor" strokeWidth="1.2" />
        <circle cx="11" cy="19" r="1.6" stroke="currentColor" strokeWidth="1.2" />
        <path d="M5 6l4.4 3.4M17 6l-4.4 3.4M11 14v3.4" stroke="currentColor" strokeWidth="1.2" />
      </svg>
      <span className="text-[15px] font-semibold tracking-tight">Hermes</span>
    </Link>
  );
}

export function AuthShell({ title, subtitle, children, footer }: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <main className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <section className="flex flex-col justify-between px-6 py-8 sm:px-12">
        <Wordmark />
        <div className="rise-in mx-auto w-full max-w-sm py-12">
          <h1 className="t-title text-2xl">{title}</h1>
          <p className="mt-1.5 text-muted">{subtitle}</p>
          <div className="mt-8">{children}</div>
          <div className="mt-6 text-[13px] text-muted">{footer}</div>
        </div>
        <p className="t-label">Intelligence in motion</p>
      </section>
      <aside
        aria-hidden
        className="relative hidden overflow-hidden border-l border-line bg-surface-1 lg:block"
      >
        <svg className="absolute inset-0 size-full" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M32 0H0V32" fill="none" stroke="var(--line)" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
        <div className="absolute inset-x-12 bottom-12">
          <p className="t-label">Principle</p>
          <p className="mt-3 max-w-md text-xl leading-snug tracking-tight">
            Automation you can read, inspect, and stop. Every action is authorized, approved when it should be, and recorded.
          </p>
        </div>
      </aside>
    </main>
  );
}
