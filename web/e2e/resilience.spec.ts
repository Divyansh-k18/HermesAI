import { expect, test } from "@playwright/test";

// When the backend is down, the Next.js proxy answers API calls itself with a plain-text 500.
const proxyFailure = { status: 500, contentType: "text/plain", body: "Internal Server Error" };

test("an unreachable backend shows a clear message instead of loading forever", async ({ page }) => {
  await page.route("**/api/v1/**", (route) => route.fulfill(proxyFailure));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Hermes can't reach its server" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("alembic upgrade head")).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/server-unavailable.png", fullPage: true });

  // Once the backend is back, Try again recovers without a reload.
  await page.unroute("**/api/v1/**");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Intelligence in motion." })).toBeVisible();
});

test("the login form explains an unreachable backend", async ({ page }) => {
  await page.goto("/login");
  await page.route("**/api/v1/**", (route) => route.fulfill(proxyFailure));
  await page.getByLabel("Email").fill("someone@example.com");
  await page.getByLabel("Password").fill("Whatever-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Cannot reach the Hermes server.")).toBeVisible();
});
