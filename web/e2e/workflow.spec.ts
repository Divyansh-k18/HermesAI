import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "Correct-Horse-42!";
const unique = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

async function signUpWithOrg(page: Page, label: string) {
  const id = unique();
  await page.goto("/register");
  await page.getByLabel("Full name").fill(`${label} Owner`);
  await page.getByLabel("Work email").fill(`${label.toLowerCase()}-${id}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(`${label} ${id}`);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/o\/[0-9a-f-]+$/);
  return page.url().split("/o/")[1];
}

const node = (id: string, type: string, x: number, y: number, config: Record<string, unknown> = {}) => ({
  id,
  type,
  label: "",
  position: { x, y },
  config,
});
const edge = (id: string, source: string, target: string, handle: string | null = null) => ({
  id,
  source,
  target,
  source_handle: handle,
  label: handle ?? "",
});

function salesOrderGraph() {
  return {
    nodes: [
      node("t", "trigger", 0, 120, { event: "hubspot.order.created" }),
      node("ai", "ai_agent", 280, 120, { instructions: "Assess the risk of this order and explain why." }),
      node("c", "condition", 560, 120, { field: "order.total", operator: "gt", value: 50000 }),
      node("a", "approval", 840, 20, { approver_role: "admin", title: "Approve order over ₹50,000" }),
      node("erp", "erp", 1120, 120, { integration: "erpnext", action: "create_sales_order" }),
      node("mail", "email", 1400, 120, { to: "{{customer.email}}", subject: "Order confirmed", body: "Thank you." }),
      node("ok", "end", 1680, 120),
      node("no", "end", 1120, 280),
    ],
    edges: [
      edge("e1", "t", "ai"),
      edge("e2", "ai", "c"),
      edge("e3", "c", "a", "true"),
      edge("e4", "c", "erp", "false"),
      edge("e5", "a", "erp", "approved"),
      edge("e6", "a", "no", "rejected"),
      edge("e7", "erp", "mail"),
      edge("e8", "mail", "ok"),
    ],
  };
}

async function api(page: Page, method: "post" | "put", url: string, data: unknown) {
  const me = await page.request.get("/api/v1/auth/me");
  const { csrf_token } = await me.json();
  const response = await page.request[method](url, { data, headers: { "X-CSRF-Token": csrf_token } });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

test("build, validate, save, publish, and activate a workflow in the editor", async ({ page }) => {
  const orgId = await signUpWithOrg(page, "Builder");

  await page.getByRole("link", { name: "Workflows" }).click();
  await expect(page.getByRole("heading", { name: "Workflow library" })).toBeVisible();
  await expect(page.getByText("No workflows yet")).toBeVisible();

  await page.getByLabel("New workflow").fill("Order intake");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(new RegExp(`/o/${orgId}/workflows/[0-9a-f-]+$`));
  await expect(page.getByText("This canvas is empty")).toBeVisible();

  // The server's checks run live, and an empty graph cannot be published.
  await expect(page.getByText("Add a trigger to start the workflow.")).toBeVisible();

  await page.getByRole("button", { name: /^Trigger/ }).click();
  await page.getByRole("button", { name: /^End/ }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(2);
  // The trigger palette entry is disabled once a trigger exists.
  await expect(page.getByRole("button", { name: /^Trigger/ })).toBeDisabled();

  // Unconnected nodes are reported.
  await page.locator(".react-flow__pane").click({ position: { x: 20, y: 20 } });
  await expect(page.getByText(/issues? to fix before publishing/)).toBeVisible();

  // Connect trigger -> end by dragging between handles.
  const trigger = page.locator(".react-flow__node").filter({ hasText: "Trigger" });
  const end = page.locator(".react-flow__node").filter({ hasText: "End" });
  await trigger.locator(".react-flow__handle.source").dragTo(end.locator(".react-flow__handle.target"));
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
  await expect(page.getByText("No issues. This graph can be published.")).toBeVisible();

  await expect(page.getByText("Unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/Saved draft v1/)).toBeVisible();

  // Undo removes the connection, redo restores it.
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.locator(".react-flow__edge")).toHaveCount(0);
  await page.getByRole("button", { name: "Redo" }).click();
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
  await page.getByRole("button", { name: "Save" }).click();

  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("published · v1")).toBeVisible();

  await page.getByRole("button", { name: "Activate v1" }).click();
  await expect(page.getByText("active · v1").first()).toBeVisible();

  // The state is persisted: a fresh load shows both nodes and the active version.
  await page.reload();
  await expect(page.locator(".react-flow__node")).toHaveCount(2);
  await expect(page.getByText("active · v1").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Publish" })).toBeDisabled();

  // Editing a published workflow starts a new draft; the published version stays frozen.
  await page.getByRole("button", { name: /^Delay/ }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText(/Saved draft v2/)).toBeVisible();
  await page.locator(".react-flow__pane").click({ position: { x: 20, y: 20 } });
  await expect(page.getByText("v1 published")).toBeVisible();
  await expect(page.getByText("v2 draft")).toBeVisible();
});

test("a complete sales-order workflow renders, validates, and publishes", async ({ page }) => {
  const orgId = await signUpWithOrg(page, "Sales");
  const created = await api(page, "post", `/api/v1/orgs/${orgId}/workflows`, { name: "Sales order processing" });
  const wid = created.workflow.id;
  await api(page, "put", `/api/v1/orgs/${orgId}/workflows/${wid}/draft`, {
    definition: salesOrderGraph(),
    base_revision: 1,
  });

  await page.goto(`/o/${orgId}/workflows/${wid}`);
  await expect(page.locator(".react-flow__node")).toHaveCount(8);
  await expect(page.locator(".react-flow__edge")).toHaveCount(8);
  await expect(page.getByText("No issues. This graph can be published.")).toBeVisible();
  await page.waitForTimeout(400);
  // The graph is wide, but the canvas must stay at a readable zoom and start at the trigger.
  const scale = await page
    .locator(".react-flow__viewport")
    .evaluate((el) => new DOMMatrix(getComputedStyle(el).transform).a);
  expect(scale).toBeGreaterThanOrEqual(0.59);
  await expect(page.locator(".react-flow__node").filter({ hasText: "Trigger" })).toBeInViewport();
  await page.screenshot({ path: "e2e/screenshots/builder-sales-order.png" });

  // Selecting a step opens its configuration.
  await page.locator(".react-flow__node").filter({ hasText: "order.total" }).click();
  await expect(page.getByLabel("Field")).toHaveValue("order.total");
  await page.screenshot({ path: "e2e/screenshots/builder-inspector.png" });

  // Breaking a step surfaces an issue that points at it.
  await page.getByLabel("Field").fill("");
  await page.locator(".react-flow__pane").click({ position: { x: 20, y: 20 } });
  await expect(page.getByText("Choose the field this condition checks.")).toBeVisible();
});

test("auto layout arranges steps and the editor is usable at tablet width", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 820, height: 1100 } });
  const page = await context.newPage();
  const orgId = await signUpWithOrg(page, "Tablet");
  const created = await api(page, "post", `/api/v1/orgs/${orgId}/workflows`, { name: "Layout check" });
  const wid = created.workflow.id;
  const graph = salesOrderGraph();
  // Stack everything at one point so auto layout has visible work to do.
  graph.nodes.forEach((n) => (n.position = { x: 0, y: 0 }));
  await api(page, "put", `/api/v1/orgs/${orgId}/workflows/${wid}/draft`, { definition: graph, base_revision: 1 });

  await page.goto(`/o/${orgId}/workflows/${wid}`);
  await expect(page.locator(".react-flow__node")).toHaveCount(8);
  await page.getByRole("button", { name: "Auto layout" }).click();
  await page.waitForTimeout(500);
  // Regression: below the lg breakpoint the canvas once collapsed to zero height and rendered blank.
  const canvasHeight = await page.locator(".react-flow").evaluate((el) => el.getBoundingClientRect().height);
  expect(canvasHeight).toBeGreaterThan(300);
  await expect(page.locator(".react-flow__node").filter({ hasText: "Trigger" })).toBeInViewport();
  await page.screenshot({ path: "e2e/screenshots/builder-tablet.png", fullPage: true });

  const boxes = await page.locator(".react-flow__node").evaluateAll((els) =>
    els.map((el) => {
      const r = el.getBoundingClientRect();
      return `${Math.round(r.x)},${Math.round(r.y)}`;
    }),
  );
  expect(new Set(boxes).size).toBe(8);
  await context.close();
});
