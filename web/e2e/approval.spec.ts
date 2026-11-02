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

async function startRun(page: Page, total: number | null) {
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  if (total !== null) {
    await dialog.getByLabel("Run data (JSON)").fill(JSON.stringify({ order: { id: `SO-${total}`, total }}));
  }
  await dialog.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page).toHaveURL(/\/executions\/[0-9a-f-]+$/);
}

test("load the sample, run it, pause for approval, approve, then reject another run", async ({ page }) => {
  const orgId = await signUpWithOrg(page, "Demo");

  // The overview starts empty and points at the library.
  await expect(page.getByText("Start with a workflow")).toBeVisible();
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Workflows", exact: true }).click();
  await page.getByRole("button", { name: "Load sample" }).click();
  await expect(page).toHaveURL(new RegExp(`/o/${orgId}/workflows/[0-9a-f-]+$`));
  await expect(page.locator(".react-flow__node")).toHaveCount(8);
  await expect(page.getByText("active · v1").first()).toBeVisible();

  // 1. A large order pauses for approval. The dialog is pre-filled from the fields the workflow reads.
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByLabel("Run data (JSON)")).toHaveValue(/"total": 75000/);
  await page.getByRole("dialog").getByRole("button", { name: "Run", exact: true }).click();
  await expect(page).toHaveURL(/\/executions\/[0-9a-f-]+$/);
  await expect(page.getByText("waiting for approval").first()).toBeVisible();
  await expect(page.getByText("Approve order over ₹50,000")).toBeVisible();
  await expect(page.getByText("Mark order approved")).toHaveCount(0);
  await page.screenshot({ path: "e2e/screenshots/run-waiting.png", fullPage: true });

  // The pending badge appears on the Approvals tab.
  await expect(page.getByRole("link", { name: /Approvals/ })).toContainText("1");

  await page.getByLabel("Comment (optional)").fill("Within budget");
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("succeeded").first()).toBeVisible();
  await expect(page.getByText("Mark order approved")).toBeVisible();
  await expect(page.getByText(/approved by .*Within budget/)).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/run-approved.png", fullPage: true });

  // 2. A small order needs no approval.
  await page.goBack();
  await page.goto(`/o/${orgId}/workflows`);
  await page.getByRole("link", { name: "Sales order approval (sample)" }).click();
  await startRun(page, 900);
  await expect(page.getByText("succeeded").first()).toBeVisible();
  await expect(page.getByText("Auto-approved (small order)")).toBeVisible();
  await expect(page.getByText("Manager approval")).toHaveCount(0);

  // 3. A rejected order never takes the approved path.
  await page.goto(`/o/${orgId}/workflows`);
  await page.getByRole("link", { name: "Sales order approval (sample)" }).click();
  await startRun(page, 120000);
  await expect(page.getByText("waiting for approval").first()).toBeVisible();
  await page.getByLabel("Comment (optional)").fill("Over budget");
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.locator("header").getByText("rejected", { exact: true })).toBeVisible();
  await expect(page.getByText("Mark order approved")).toHaveCount(0);
  await expect(page.getByText("Rejected", { exact: true }).first()).toBeVisible();

  // 4. Lists and the overview reflect the real records.
  await page.getByRole("link", { name: "Runs", exact: true }).first().click();
  await expect(page.getByRole("link", { name: "Sales order approval (sample)" })).toHaveCount(3);
  await page.getByRole("button", { name: "Rejected" }).click();
  await expect(page.getByRole("link", { name: "Sales order approval (sample)" })).toHaveCount(1);

  await page.getByRole("link", { name: "Approvals" }).click();
  await page.getByRole("button", { name: "History" }).click();
  await expect(page.getByText(/approved by/)).toBeVisible();
  await expect(page.getByText(/rejected by/)).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/approvals-history.png", fullPage: true });

  await page.getByRole("link", { name: "Overview" }).click();
  await expect(page.getByText("Finished runs, last 7 days")).toBeVisible();
  await expect(page.getByText("Latest runs")).toBeVisible();
  await page.waitForTimeout(400);
  await page.screenshot({ path: "e2e/screenshots/overview-metrics.png", fullPage: true });
});

test("members can run workflows but cannot see or decide approvals", async ({ page, browser }) => {
  const id = unique();
  const orgId = await signUpWithOrg(page, "Roles");
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Workflows", exact: true }).click();
  await page.getByRole("button", { name: "Load sample" }).click();
  await expect(page.getByText("active · v1").first()).toBeVisible();

  // Invite a member and sign them in on a separate context.
  await page.getByRole("link", { name: "Team" }).click();
  await page.getByLabel("Email", { exact: true }).fill(`member-${id}@example.com`);
  await page.getByRole("button", { name: "Create invitation" }).click();
  const link = await page.locator("code").innerText();

  const context = await browser.newContext();
  const member = await context.newPage();
  await member.goto("/register");
  await member.getByLabel("Full name").fill("Mia Member");
  await member.getByLabel("Work email").fill(`member-${id}@example.com`);
  await member.getByLabel("Password").fill(PASSWORD);
  await member.getByRole("button", { name: "Create account" }).click();
  await expect(member).toHaveURL(/\/onboarding/);
  await member.goto(link);
  await member.getByRole("button", { name: "Accept invitation" }).click();
  await expect(member).toHaveURL(/\/o\/[0-9a-f-]+$/);

  await member.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Workflows", exact: true }).click();
  await member.getByRole("link", { name: "Sales order approval (sample)" }).click();
  await startRun(member, 80000);
  await expect(member.getByText("waiting for approval").first()).toBeVisible();
  // The member sees that the run is waiting, but not the approval data or any decision controls.
  await expect(member.getByText("Only owners and admins can see and decide it.")).toBeVisible();
  await expect(member.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
  await expect(member.getByRole("link", { name: "Approvals" })).toHaveCount(0);

  // The owner sees it and can decide.
  await page.getByRole("link", { name: /Approvals/ }).click();
  await expect(page.getByText("Approve order over ₹50,000")).toBeVisible();
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("Nothing waiting")).toBeVisible();

  await member.reload();
  await expect(member.getByText("succeeded").first()).toBeVisible();
  await context.close();
  expect(orgId).toBeTruthy();
});
