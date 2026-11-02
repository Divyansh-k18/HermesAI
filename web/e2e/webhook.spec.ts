import { createHmac } from "node:crypto";

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
}

/** Signs exactly like an outside system would: HMAC-SHA256 over "<timestamp>.<raw body>". */
function signedHeaders(secret: string, body: string, eventId: string) {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const digest = createHmac("sha256", secret).update(`${timestamp}.${body}`).digest("hex");
  return {
    "Content-Type": "application/json",
    "X-Hermes-Timestamp": timestamp,
    "X-Hermes-Signature": `sha256=${digest}`,
    "X-Hermes-Event-Id": eventId,
  };
}

test("an owner creates a webhook and a signed delivery starts a run", async ({ page }) => {
  await signUpWithOrg(page, "Hook");
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Workflows", exact: true }).click();
  await page.getByRole("button", { name: "Load sample" }).click();
  await expect(page.getByText("active · v1").first()).toBeVisible();

  const panel = page.locator('section[aria-labelledby="webhook-heading"]');
  await panel.getByRole("button", { name: "Create webhook" }).click();
  await expect(panel.getByText("Copy this signing secret now")).toBeVisible();
  const url = await panel.locator("code").nth(0).innerText();
  const secret = await panel.locator("code").nth(1).innerText();
  expect(url).toMatch(/\/api\/v1\/hooks\/[A-Za-z0-9_-]+$/);
  expect(secret).toMatch(/^whsec_/);
  await page.screenshot({ path: "e2e/screenshots/builder-webhook.png" });

  // A delivery through the app's own address, the way a demo or a tunnel would send it.
  const body = JSON.stringify({ order: { id: "SO-WEB-1", total: 99000 } });
  const accepted = await page.request.post(url, { data: body, headers: signedHeaders(secret, body, "evt-web-1") });
  expect(accepted.status()).toBe(202);
  expect((await accepted.json()).run_status).toBe("waiting_approval");

  // Same event again: no second run.
  const repeated = await page.request.post(url, { data: body, headers: signedHeaders(secret, body, "evt-web-1") });
  expect(repeated.status()).toBe(200);
  expect((await repeated.json()).status).toBe("duplicate");

  // Wrong secret: refused.
  const forged = await page.request.post(url, { data: body, headers: signedHeaders("whsec_wrong", body, "evt-web-2") });
  expect(forged.status()).toBe(401);

  // The delivery shows up in the panel and links to its run.
  await expect(panel.getByText("evt-web-1")).toBeVisible();
  await expect(panel.getByText("evt-web-2")).toHaveCount(0);
  await panel.getByRole("link", { name: "run" }).first().click();
  await expect(page).toHaveURL(/\/executions\/[0-9a-f-]+$/);
  await expect(page.getByText("webhook", { exact: true })).toBeVisible();
  await expect(page.getByText("waiting for approval").first()).toBeVisible();
  await expect(page.getByRole("link", { name: /Approvals/ })).toContainText("1");
});
