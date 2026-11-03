"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Badge, Button, EmptyState, Field, FormError, Skeleton } from "@/components/ui";
import { formatTime } from "@/components/status";
import { ApiError, api, type InventoryItem } from "@/lib/api";
import { SAMPLE_STOCK } from "@/lib/sample-workflow";

const LOW_STOCK = 10;

function messagesOf(error: unknown): string[] {
  return error instanceof ApiError ? error.messages : ["Could not reach the server."];
}

function StockBadge({ quantity }: { quantity: number }) {
  if (quantity === 0) return <Badge tone="danger">out of stock</Badge>;
  if (quantity < LOW_STOCK) return <Badge tone="warning">low</Badge>;
  return <Badge tone="success">in stock</Badge>;
}

export default function InventoryPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const queryClient = useQueryClient();
  const org = useQuery({ queryKey: ["org", orgId], queryFn: () => api.orgs.get(orgId) });
  const items = useQuery({ queryKey: ["inventory", orgId], queryFn: () => api.inventory.list(orgId) });
  const canManage = org.data?.role === "owner" || org.data?.role === "admin";

  const [name, setName] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unit, setUnit] = useState("unit");
  const [price, setPrice] = useState("");
  const [errors, setErrors] = useState<string[]>([]);

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["inventory", orgId] });

  const create = useMutation({
    mutationFn: () =>
      api.inventory.create(orgId, {
        name: name.trim(),
        quantity: Number(quantity),
        unit: unit.trim() || "unit",
        unit_price: price.trim() ? Number(price) : null,
      }),
    onSuccess: () => {
      setErrors([]);
      setName("");
      setQuantity("");
      setPrice("");
      refresh();
    },
    onError: (error) => setErrors(messagesOf(error)),
  });
  const update = useMutation({
    mutationFn: ({ id, quantity: next }: { id: string; quantity: number }) =>
      api.inventory.update(orgId, id, { quantity: next }),
    onSuccess: refresh,
    onError: (error) => setErrors(messagesOf(error)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.inventory.remove(orgId, id),
    onSuccess: refresh,
    onError: (error) => setErrors(messagesOf(error)),
  });
  const seed = useMutation({
    mutationFn: async () => {
      for (const item of SAMPLE_STOCK) await api.inventory.create(orgId, item);
    },
    onSettled: refresh,
    onError: (error) => setErrors(messagesOf(error)),
  });

  const setQuantityOf = (item: InventoryItem, raw: string) => {
    const next = Number(raw);
    if (raw.trim() === "" || !Number.isInteger(next) || next < 0 || next === item.quantity) return;
    update.mutate({ id: item.id, quantity: next });
  };

  return (
    <div className="rise-in flex flex-col gap-8">
      <header>
        <p className="t-label">Inventory</p>
        <h1 className="t-title mt-3 text-2xl">Stock on hand</h1>
        <p className="mt-1.5 max-w-xl text-muted">
          The Check stock step compares every ordered item with this list. Items that are short, unknown, or have no
          quantity are never treated as available, so a person checks them.
        </p>
      </header>

      <section aria-labelledby="stock-heading" className="grid gap-8 lg:grid-cols-[3fr_2fr]">
        <div>
          <h2 id="stock-heading" className="t-label mb-3">
            Items
          </h2>
          <FormError messages={errors} />
          {items.isLoading ? (
            <Skeleton className="h-24" />
          ) : items.data && items.data.length > 0 ? (
            <ul className="border border-line">
              {items.data.map((item) => (
                <li
                  key={item.id}
                  className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-3 py-2.5 last:border-0"
                >
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-2 text-[13px] font-medium">
                      <span className="truncate">{item.name}</span>
                      <StockBadge quantity={item.quantity} />
                    </p>
                    <p className="font-mono text-[11px] text-faint">
                      {item.unit_price !== null ? `₹${item.unit_price.toLocaleString("en-IN")} per ${item.unit} · ` : ""}
                      updated {formatTime(item.updated_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {canManage ? (
                      <input
                        key={`${item.id}-${item.quantity}`}
                        aria-label={`Quantity of ${item.name}`}
                        type="number"
                        min={0}
                        defaultValue={item.quantity}
                        onBlur={(event) => setQuantityOf(item, event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") setQuantityOf(item, event.currentTarget.value);
                        }}
                        className="h-8 w-24 rounded-md border border-line-strong bg-surface-1 px-2 text-right font-mono text-[13px] hover:border-faint focus-visible:border-accent"
                      />
                    ) : (
                      <span className="font-mono text-[13px]">{item.quantity}</span>
                    )}
                    <span className="w-12 text-[12px] text-muted">{item.unit}</span>
                    {canManage && (
                      <Button
                        variant="ghost"
                        onClick={() => {
                          if (window.confirm(`Delete ${item.name}?`)) remove.mutate(item.id);
                        }}
                      >
                        Delete
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              title="No stock yet"
              body="Add the items you sell, or load a few sample items to try the Check stock step."
              action={
                canManage ? (
                  <Button variant="secondary" onClick={() => seed.mutate()} loading={seed.isPending}>
                    Add sample stock
                  </Button>
                ) : undefined
              }
            />
          )}
        </div>

        {canManage ? (
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              setErrors([]);
              create.mutate();
            }}
          >
            <h2 className="t-label">Add an item</h2>
            <Field label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="A4 Paper" maxLength={200} />
            <div className="grid grid-cols-2 gap-3">
              <Field
                label="Quantity"
                type="number"
                min={0}
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="200"
              />
              <Field label="Unit" value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="box" maxLength={30} />
            </div>
            <Field
              label="Price per unit in ₹ (optional)"
              type="number"
              min={0}
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="1500"
            />
            <Button
              type="submit"
              className="self-start"
              loading={create.isPending}
              disabled={!name.trim() || quantity.trim() === "" || Number(quantity) < 0}
            >
              Add item
            </Button>
          </form>
        ) : (
          <p className="text-[13px] text-muted">Only owners and admins can change stock.</p>
        )}
      </section>
    </div>
  );
}
