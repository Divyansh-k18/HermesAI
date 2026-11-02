"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Badge, Button, EmptyState, Field, FormError, Skeleton } from "@/components/ui";
import { ApiError, api, type WorkflowSummary } from "@/lib/api";
import { SAMPLE_WORKFLOW, SAMPLE_WORKFLOW_NAME } from "@/lib/sample-workflow";

function StatusBadge({ workflow }: { workflow: WorkflowSummary }) {
  if (workflow.active_version_number !== null) {
    return <Badge tone="success">active · v{workflow.active_version_number}</Badge>;
  }
  if (workflow.latest_published_number !== null) {
    return <Badge>published · v{workflow.latest_published_number}</Badge>;
  }
  return <Badge tone="warning">draft</Badge>;
}

export default function WorkflowLibraryPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const org = useQuery({ queryKey: ["org", orgId], queryFn: () => api.orgs.get(orgId) });
  const workflows = useQuery({ queryKey: ["workflows", orgId], queryFn: () => api.workflows.list(orgId) });
  const canWrite = org.data ? org.data.role !== "viewer" : false;
  const canPublish = org.data?.role === "owner" || org.data?.role === "admin";

  const [name, setName] = useState("");
  const [errors, setErrors] = useState<string[]>([]);

  const create = useMutation({
    mutationFn: (workflowName: string) => api.workflows.create(orgId, { name: workflowName }),
    onSuccess: async (detail) => {
      await queryClient.invalidateQueries({ queryKey: ["workflows", orgId] });
      router.push(`/o/${orgId}/workflows/${detail.workflow.id}`);
    },
    onError: (error) => setErrors(error instanceof ApiError ? error.messages : ["Could not reach the server."]),
  });

  // Creates, publishes, and activates the sample so a run and an approval can be tried right away.
  const loadSample = useMutation({
    mutationFn: async () => {
      const created = await api.workflows.create(orgId, {
        name: SAMPLE_WORKFLOW_NAME,
        description: "Orders above ₹50,000 wait for a manager's approval.",
      });
      const id = created.workflow.id;
      const saved = await api.workflows.saveDraft(orgId, id, { definition: SAMPLE_WORKFLOW, base_revision: 1 });
      if (canPublish) {
        await api.workflows.publish(orgId, id, saved.version.revision);
        await api.workflows.activate(orgId, id, saved.version.version_number);
      }
      return id;
    },
    onSuccess: async (id) => {
      await queryClient.invalidateQueries({ queryKey: ["workflows", orgId] });
      router.push(`/o/${orgId}/workflows/${id}`);
    },
    onError: (error) => setErrors(error instanceof ApiError ? error.messages : ["Could not reach the server."]),
  });

  return (
    <div className="rise-in flex flex-col gap-8">
      <header>
        <p className="t-label">Workflows</p>
        <h1 className="t-title mt-3 text-2xl">Workflow library</h1>
        <p className="mt-1.5 max-w-xl text-muted">
          Each workflow is a graph of steps. Drafts are editable. Published versions are frozen, and one version at a
          time can be marked active. Running workflows on real events is not built yet.
        </p>
      </header>

      {canWrite && (
        <form
          className="flex max-w-xl items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            setErrors([]);
            if (name.trim()) create.mutate(name.trim());
          }}
        >
          <div className="flex-1">
            <Field label="New workflow" value={name} onChange={(event) => setName(event.target.value)} placeholder="Sales order processing" maxLength={200} />
          </div>
          <Button type="submit" loading={create.isPending} disabled={!name.trim()} className="h-9">
            Create
          </Button>
        </form>
      )}
      {canWrite && (
        <div className="flex flex-wrap items-center gap-3 border border-line px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-medium">Try the sample sales-order workflow</p>
            <p className="text-[12px] text-muted">
              Orders above ₹50,000 pause for a manager&apos;s approval.
              {canPublish ? " It is published and activated for you." : " It is saved as a draft for an admin to publish."}
            </p>
          </div>
          <Button variant="secondary" onClick={() => loadSample.mutate()} loading={loadSample.isPending}>
            Load sample
          </Button>
        </div>
      )}
      <FormError messages={errors} />

      {workflows.isLoading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-11" />
          <Skeleton className="h-11" />
        </div>
      ) : workflows.isError ? (
        <EmptyState title="Could not load workflows" body="Try again in a moment." />
      ) : workflows.data && workflows.data.length > 0 ? (
        <div className="relative overflow-x-auto border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="border-b border-line text-faint">
              <tr>
                <th className="px-3 py-2 font-normal">Name</th>
                <th className="px-3 py-2 font-normal">Status</th>
                <th className="hidden px-3 py-2 font-normal sm:table-cell">Updated</th>
              </tr>
            </thead>
            <tbody>
              {workflows.data.map((workflow) => (
                <tr key={workflow.id} className="border-b border-line last:border-0 hover:bg-surface-1">
                  <td className="px-3 py-2.5">
                    <Link href={`/o/${orgId}/workflows/${workflow.id}`} className="font-medium hover:text-accent-strong">
                      {workflow.name}
                    </Link>
                    {workflow.description && <p className="text-[12px] text-faint">{workflow.description}</p>}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="inline-flex items-center gap-2">
                      <StatusBadge workflow={workflow} />
                      {workflow.has_draft && workflow.latest_published_number !== null && (
                        <span className="text-[12px] text-faint">unpublished changes</span>
                      )}
                    </span>
                  </td>
                  <td className="hidden px-3 py-2.5 font-mono text-[12px] text-muted sm:table-cell">
                    {new Date(workflow.updated_at + "Z").toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No workflows yet"
          body={
            canWrite
              ? "Name your first workflow above. You will land in the builder with an empty canvas."
              : "Workflows created by your team will appear here."
          }
        />
      )}
    </div>
  );
}
