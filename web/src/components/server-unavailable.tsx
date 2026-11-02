"use client";

import { Wordmark } from "@/components/auth-shell";
import { Button } from "@/components/ui";
import { ApiError } from "@/lib/api";

/**
 * Shown instead of an endless loading state when the browser cannot reach the Hermes API.
 * The usual causes on a new machine are listed so the person can fix it without reading logs.
 */
export function ServerUnavailable({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const status = error instanceof ApiError ? error.status : null;
  const missingTables = error instanceof ApiError && error.status === 500 && error.payload !== null;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-xl flex-col justify-center gap-6 px-6 py-12">
      <Wordmark />
      <div role="alert">
        <p className="t-label">Connection problem</p>
        <h1 className="t-title mt-3 text-2xl">Hermes can&apos;t reach its server</h1>
        <p className="mt-2 text-muted">
          The web app is running, but the API did not answer{status ? ` (HTTP ${status})` : ""}. Check these on the
          machine running Hermes:
        </p>
      </div>
      {status === 404 && (
        <div className="border border-warning/40 px-4 py-3 text-[14px]">
          <p className="font-medium">Another program is probably using the API&apos;s port.</p>
          <p className="mt-1.5 text-muted">
            Something answered at the API address, but it is not Hermes. This usually means another project is
            already running on port 8000, so the Hermes API could not start there. Start the API with{" "}
            <code className="font-mono text-text">python run.py</code>: it checks the port and explains how to use a
            different one.
          </p>
        </div>
      )}
      <ol className="flex list-decimal flex-col gap-3 pl-5 text-[14px] text-muted">
        <li>
          The backend is running. In the <code className="font-mono text-text">backend</code> folder, start it and
          leave that terminal open. Opening{" "}
          <a href="http://127.0.0.1:8000/healthz" className="text-accent-strong hover:underline">
            127.0.0.1:8000/healthz
          </a>{" "}
          should show <code className="font-mono text-text">{'{"status":"ok"}'}</code>.
        </li>
        <li className={missingTables ? "text-text" : undefined}>
          The database is set up. Run <code className="font-mono text-text">alembic upgrade head</code> in the backend
          folder before the first start, and again after pulling new code.
        </li>
        <li>
          The backend uses port 8000. If something else is on that port, stop it, or set{" "}
          <code className="font-mono text-text">HERMES_API_URL</code> before starting the web app.
        </li>
      </ol>
      <Button onClick={onRetry} className="self-start">
        Try again
      </Button>
    </main>
  );
}
