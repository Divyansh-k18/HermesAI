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

// A real mailbox cannot be reached from the test machine, so this covers everything up to the sign-in:
// the email sample, the setup form, and a clear error for a mail server that does not exist.
test("the email order sample loads and the mailbox form reports connection problems", async ({ page }) => {
  await signUpWithOrg(page, "Mail");
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Workflows", exact: true }).click();
  await page.getByRole("button", { name: "Load email order sample" }).click();
  await expect(page.getByText("active · v1").first()).toBeVisible();
  await expect(page.locator(".react-flow__node").filter({ hasText: "Order email received" })).toBeVisible();

  const panel = page.locator('section[aria-labelledby="email-heading"]');
  await panel.getByRole("button", { name: "Connect mailbox" }).click();
  await expect(panel.getByLabel("Mail server (IMAP)")).toHaveValue("imap.gmail.com");
  await panel.getByLabel("Mail server (IMAP)").fill("mail.hermes-test.invalid");
  await panel.getByLabel("Email address").fill("orders@example.com");
  await panel.getByLabel("App password").fill("not-a-real-password");
  await panel.getByLabel("Only accept orders from (optional)").fill("customer.example.com");
  await panel.getByRole("button", { name: "Save and test" }).click();
  await expect(panel.getByText(/Could not resolve mail\.hermes-test\.invalid/)).toBeVisible({ timeout: 30_000 });
  await panel.screenshot({ path: "e2e/screenshots/email-panel.png" });

  // A manual run with an emailed order shows the parsed fields flowing through the graph.
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const data = page.getByLabel("Run data (JSON)");
  await data.fill(
    JSON.stringify({ email: { from: "asha@customer.example.com", fields: { total: 82000, customer: "Asha Traders" } } }),
  );
  await page.getByRole("dialog").getByRole("button", { name: "Run", exact: true }).click();
  await expect(page).toHaveURL(/\/executions\/[0-9a-f-]+$/);
  await expect(page.getByText("waiting for approval").first()).toBeVisible();
  await expect(page.getByText("Approve emailed order over ₹50,000")).toBeVisible();
});
