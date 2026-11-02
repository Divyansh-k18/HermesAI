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

const nav = (page: Page, name: string) =>
  page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name, exact: true });

test("an owner stores a connection and picks it in an HTTP step", async ({ page }) => {
  await signUpWithOrg(page, "Integrate");
  await nav(page, "Integrations").click();

  // The catalog is honest about what exists.
  const catalog = page.getByRole("region", { name: "Connectors" });
  await expect(catalog.getByText("Generic REST API")).toBeVisible();
  await expect(catalog.getByText("HubSpot CRM")).toBeVisible();
  await expect(catalog.getByText("planned")).toHaveCount(4);

  await page.getByLabel("Name").fill("Inventory API");
  await page.getByLabel("Value").fill("Bearer sk_test_should_not_render");
  await page.getByRole("button", { name: "Save connection" }).click();
  await expect(page.getByText("Inventory API")).toBeVisible();
  await expect(page.getByText(/Authorization: ••••••/)).toBeVisible();
  // The secret is gone from the page once saved.
  await expect(page.getByLabel("Value")).toHaveValue("");
  expect(await page.content()).not.toContain("sk_test_should_not_render");
  await page.screenshot({ path: "e2e/screenshots/integrations.png", fullPage: true });

  // The connection is offered in an HTTP step's inspector.
  await nav(page, "Workflows").click();
  await page.getByLabel("New workflow").fill("Call an API");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByText("This canvas is empty")).toBeVisible();
  await page.getByRole("button", { name: /^Trigger/ }).click();
  await page.getByRole("button", { name: /^HTTP request/ }).click();
  const connection = page.getByLabel("Connection");
  await expect(connection).toBeVisible();
  await connection.selectOption({ label: "Inventory API (Authorization)" });
  await page.getByLabel("URL").fill("https://api.example.com/stock");
  await page.getByLabel("Save response as").fill("stock");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText(/Saved draft v1/)).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/builder-http-step.png" });

  // A fresh load keeps the choice, and only the connection id is stored in the workflow.
  await page.reload();
  await page.locator(".react-flow__node").filter({ hasText: "HTTP request" }).click();
  await expect(page.getByLabel("Connection")).toHaveValue(/[0-9a-f-]{36}/);
});
