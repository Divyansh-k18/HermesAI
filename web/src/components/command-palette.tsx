"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";

interface Command {
  id: string;
  label: string;
  group: "Go to" | "Workflows" | "Actions";
  keywords?: string;
  run: () => void;
}

/** Ctrl+K (or Cmd+K) command palette: jump to pages and workflows, or run an action, from the keyboard. */
export function CommandPalette({
  orgId,
  isAdmin,
  onSignOut,
}: {
  orgId: string;
  isAdmin: boolean;
  onSignOut: () => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  const workflows = useQuery({
    queryKey: ["workflows", orgId],
    queryFn: () => api.workflows.list(orgId),
    enabled: open,
  });

  const show = useCallback(() => {
    returnFocus.current = document.activeElement as HTMLElement | null;
    setQuery("");
    setActive(0);
    setOpen(true);
  }, []);

  const hide = useCallback(() => {
    setOpen(false);
    returnFocus.current?.focus?.();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (open) hide();
        else show();
      }
    };
    const onOpenRequest = () => show();
    window.addEventListener("keydown", onKey);
    window.addEventListener("hermes:open-palette", onOpenRequest);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("hermes:open-palette", onOpenRequest);
    };
  }, [open, show, hide]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const go = (path: string) => () => router.push(`/o/${orgId}${path}`);
    const pages: Command[] = [
      { id: "go-overview", label: "Overview", group: "Go to", keywords: "home dashboard metrics", run: go("") },
      { id: "go-workflows", label: "Workflows", group: "Go to", keywords: "library builder", run: go("/workflows") },
      { id: "go-runs", label: "Runs", group: "Go to", keywords: "executions history trace", run: go("/executions") },
      ...(isAdmin
        ? [{ id: "go-approvals", label: "Approvals", group: "Go to" as const, keywords: "pending decide", run: go("/approvals") }]
        : []),
      { id: "go-integrations", label: "Integrations", group: "Go to", keywords: "connections api keys", run: go("/integrations") },
      { id: "go-team", label: "Team", group: "Go to", keywords: "members invite roles", run: go("/team") },
      { id: "go-audit", label: "Audit log", group: "Go to", keywords: "security events history", run: go("/audit") },
    ];
    const flows: Command[] = (workflows.data ?? []).map((workflow) => ({
      id: `wf-${workflow.id}`,
      label: workflow.name,
      group: "Workflows",
      keywords: "open edit builder",
      run: go(`/workflows/${workflow.id}`),
    }));
    const actions: Command[] = [
      { id: "act-new", label: "Create a workflow", group: "Actions", keywords: "new add sample", run: go("/workflows") },
      { id: "act-failed", label: "Show failed runs", group: "Actions", keywords: "errors problems", run: go("/executions") },
      { id: "act-signout", label: "Sign out", group: "Actions", keywords: "log out logout", run: onSignOut },
    ];
    return [...pages, ...flows, ...actions];
  }, [orgId, isAdmin, workflows.data, router, onSignOut]);

  const results = useMemo(() => {
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (terms.length === 0) return commands;
    return commands.filter((command) => {
      const haystack = `${command.label} ${command.group} ${command.keywords ?? ""}`.toLowerCase();
      return terms.every((term) => haystack.includes(term));
    });
  }, [commands, query]);

  if (!open) return null;

  const current = Math.min(active, Math.max(results.length - 1, 0));
  const runAt = (index: number) => {
    const command = results[index];
    if (!command) return;
    setOpen(false);
    command.run();
  };

  let lastGroup = "";
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/55 px-4 pt-[14vh]" onClick={hide}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(event) => event.stopPropagation()}
        className="rise-in w-full max-w-lg overflow-hidden rounded-lg border border-line-strong bg-surface-1 shadow-2xl shadow-black/50"
      >
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded="true"
          aria-controls="palette-results"
          aria-activedescendant={results[current] ? `palette-${results[current].id}` : undefined}
          aria-label="Search pages, workflows, and actions"
          placeholder="Search pages, workflows, and actions…"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((current + 1) % Math.max(results.length, 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((current - 1 + results.length) % Math.max(results.length, 1));
            } else if (event.key === "Enter") {
              event.preventDefault();
              runAt(current);
            } else if (event.key === "Escape") {
              event.preventDefault();
              hide();
            }
          }}
          className="h-12 w-full border-b border-line bg-transparent px-4 text-[14px] text-text placeholder:text-faint focus-visible:outline-none"
        />
        <ul id="palette-results" role="listbox" aria-label="Results" className="max-h-80 overflow-y-auto py-1.5">
          {results.length === 0 && <li className="px-4 py-6 text-center text-[13px] text-muted">No matches.</li>}
          {results.map((command, index) => {
            const heading = command.group !== lastGroup ? command.group : null;
            lastGroup = command.group;
            return (
              <li key={command.id} role="presentation">
                {heading && <p className="t-label px-4 pb-1 pt-2.5">{heading}</p>}
                <div
                  id={`palette-${command.id}`}
                  role="option"
                  aria-selected={index === current}
                  onMouseMove={() => setActive(index)}
                  onClick={() => runAt(index)}
                  className={`mx-1.5 flex cursor-pointer items-center justify-between rounded-md px-2.5 py-2 text-[13px] ${
                    index === current ? "bg-accent-soft text-text" : "text-muted"
                  }`}
                >
                  <span className="truncate">{command.label}</span>
                  {index === current && <span className="font-mono text-[10px] text-faint">Enter</span>}
                </div>
              </li>
            );
          })}
        </ul>
        <div className="flex justify-between border-t border-line px-4 py-2 font-mono text-[10px] text-faint">
          <span>↑ ↓ to move · Enter to open</span>
          <span>Esc to close</span>
        </div>
      </div>
    </div>
  );
}

/** Opens the palette from a button, for people who do not use the keyboard shortcut. */
export function openCommandPalette() {
  window.dispatchEvent(new Event("hermes:open-palette"));
}
