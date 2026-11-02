import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  // The sign-up redirect chain can exceed the 5s default on slow machines.
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  outputDir: "./e2e/results",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node e2e/start-backend.mjs",
      url: "http://127.0.0.1:8000/healthz",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npm run build && npx next start -p 3000",
      url: "http://127.0.0.1:3000/login",
      reuseExistingServer: true,
      timeout: 300_000,
    },
  ],
});
