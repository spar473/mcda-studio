import { defineConfig } from "@playwright/test";

const port = Number(process.env.MCDA_E2E_PORT ?? 8799);
// In a sandbox with a pre-installed browser of another revision, point at it explicitly;
// otherwise Playwright uses the browser from `npx playwright install chromium`.
const executablePath = process.env.MCDA_CHROMIUM || undefined;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45_000,
  expect: { timeout: 7_000 },
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${String(port)}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1360, height: 860 },
    launchOptions: executablePath ? { executablePath } : {},
  },
  webServer: {
    command: "node scripts/e2e-server.mjs",
    url: `http://127.0.0.1:${String(port)}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
