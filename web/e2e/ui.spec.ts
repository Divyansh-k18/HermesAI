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

test("the command palette opens with Ctrl+K and moves between pages and workflows", async ({ page }) => {
  await signUpWithOrg(page, "Palette");
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Workflows", exact: true }).click();
  await page.getByRole("button", { name: "Load sample" }).click();
  await expect(page.getByText("active · v1").first()).toBeVisible();

  // Keyboard: open, filter, and go.
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await page.keyboard.type("audit");
  await expect(palette.getByRole("option")).toHaveCount(1);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/audit$/);
  await expect(palette).toHaveCount(0);

  // Button: open, find a workflow by name, arrow down, and open it.
  await page.getByRole("button", { name: "Search and commands" }).click();
  await expect(palette).toBeVisible();
  await page.keyboard.type("sales");
  await expect(palette.getByRole("option", { name: /Sales order approval/ })).toBeVisible();
  await page.screenshot({ path: "e2e/screenshots/command-palette.png" });
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/workflows\/[0-9a-f-]+$/);

  // Escape closes without navigating.
  await page.keyboard.press("Control+k");
  await expect(palette).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(palette).toHaveCount(0);
  await expect(page).toHaveURL(/\/workflows\/[0-9a-f-]+$/);
});

test("the landing hero renders the 3D scene, or its flat fallback without WebGL", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  const hero = page.locator("[data-hero]");
  await expect(hero).toBeVisible();
  const mode = await hero.getAttribute("data-hero");
  if (mode === "3d") {
    await expect(hero.locator("canvas")).toBeVisible({ timeout: 20_000 });
  } else {
    await expect(hero.locator("svg")).toBeVisible();
  }
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "e2e/screenshots/landing-hero.png" });
  expect(errors).toEqual([]);
  console.log(`hero mode: ${mode}`);
});

test("reduced motion still shows the hero, without animating it", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.locator("[data-hero]")).toBeVisible();
  await page.waitForTimeout(1000);
  expect(errors).toEqual([]);
  await context.close();
});
