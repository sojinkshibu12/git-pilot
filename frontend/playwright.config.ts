import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E config — targets the full Docker stack.
 *
 * Requires:
 *   docker compose --profile full up --build
 *   and a GitHub OAuth App with redirect URI configured for E2E.
 */
export default defineConfig({
  testDir: "../backend/tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: [
    {
      command: "npm run dev",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      cwd: ".",
    },
    {
      command:
        "cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8000",
      url: "http://localhost:8000/health",
      reuseExistingServer: !process.env.CI,
      cwd: ".",
    },
  ],
});
