import { expect, test, type Browser, type Page } from "@playwright/test";

const PASSWORD = "Correct-Horse-42!";
const unique = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

async function register(page: Page, name: string, email: string) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
}

async function createOrg(page: Page, name: string) {
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(name);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/o\/[0-9a-f-]+$/);
}

async function newUserPage(browser: Browser) {
  const context = await browser.newContext();
  return { context, page: await context.newPage() };
}

test("signed-out visitors are sent to login", async ({ page }) => {
  await page.goto("/o/00000000-0000-0000-0000-000000000000");
  await expect(page).toHaveURL(/\/login/);
});

test("registration validates the password before submitting", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Weak Pass");
  await page.getByLabel("Work email").fill(`weak-${unique()}@example.com`);
  await page.getByLabel("Password").fill("short");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "at least 12" })).toBeVisible();
});

test("wrong password shows a generic error", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(`nobody-${unique()}@example.com`);
  await page.getByLabel("Password").fill("Wrong-Pass-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Invalid email or password.")).toBeVisible();
});

test("owner onboarding, invitation, acceptance, role change, and removal", async ({ page, browser }) => {
  const id = unique();
  const ownerEmail = `owner-${id}@example.com`;
  const inviteeEmail = `invitee-${id}@example.com`;

  await register(page, "Olive Owner", ownerEmail);
  await createOrg(page, `Acme ${id}`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(`Acme ${id}`);

  await page.screenshot({ path: "e2e/screenshots/overview-desktop.png" });

  await page.getByRole("link", { name: "Team" }).click();
  await expect(page.getByRole("heading", { name: "Members and access" })).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill(inviteeEmail);
  await page.getByRole("button", { name: "Create invitation" }).click();
  const link = await page.locator("code").innerText();
  expect(link).toContain("/invite?token=");
  await expect(page.getByText(inviteeEmail).first()).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/team-desktop.png", fullPage: true });

  // The invitee registers in a separate browser context and accepts.
  const invitee = await newUserPage(browser);
  await register(invitee.page, "Ira Invitee", inviteeEmail);
  await expect(invitee.page).toHaveURL(/\/onboarding/);
  await invitee.page.goto(link);
  await invitee.page.getByRole("button", { name: "Accept invitation" }).click();
  await expect(invitee.page).toHaveURL(/\/o\/[0-9a-f-]+$/);
  await invitee.page.getByRole("link", { name: "Team" }).click();
  // A member can read the team but gets no invite form and no role controls.
  await expect(invitee.page.getByRole("heading", { name: "Members and access" })).toBeVisible();
  await expect(invitee.page.getByRole("button", { name: "Create invitation" })).toHaveCount(0);
  await invitee.page.getByRole("link", { name: "Audit log" }).click();
  await expect(invitee.page.getByText("Only owners and admins can read the audit log.")).toBeVisible();

  // The owner now sees two members, demotes the invitee, then removes them.
  await page.reload();
  const row = page.getByRole("row", { name: /Ira Invitee/ });
  await expect(row).toBeVisible();
  await page.getByLabel("Role for Ira Invitee").selectOption("viewer");
  await expect(page.getByLabel("Role for Ira Invitee")).toHaveValue("viewer");

  page.once("dialog", (dialog) => void dialog.accept());
  await row.getByRole("button", { name: "Remove" }).click();
  await expect(page.getByRole("row", { name: /Ira Invitee/ })).toHaveCount(0);

  // Access is revoked immediately.
  await invitee.page.reload();
  await expect(invitee.page.getByText("does not exist or you no longer have access")).toBeVisible();
  await invitee.context.close();

  await page.getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByText("member.remove")).toBeVisible();
  await expect(page.getByText("invitation.accept").first()).toBeVisible();
});

test("login, mobile layout, and sign out", async ({ browser }) => {
  const id = unique();
  const email = `mobile-${id}@example.com`;
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();

  await page.goto("/login");
  await page.screenshot({ path: "e2e/screenshots/login-mobile.png" });

  await register(page, "Mia Mobile", email);
  await createOrg(page, `Mobile ${id}`);
  await page.getByRole("link", { name: "Team" }).click();
  await expect(page.getByRole("heading", { name: "Members and access" })).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/team-mobile.png", fullPage: true });

  // No horizontal page scroll at phone width.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await context.close();
});
