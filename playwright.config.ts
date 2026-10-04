import { defineConfig, devices } from "@playwright/test";

// Offline hooks (P0-9 S0). The pinned @playwright/test (1.61.1) resolves a
// playwright-core whose expected browser revision is not the one an offline
// machine has cached, so a browser path can be supplied explicitly:
//   VALUE_E2E_CHROMIUM=<path to chrome / chrome-headless-shell>
// (PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH is honoured as a fallback, like the
// per-spec playwright.*.config.ts files). VALUE_E2E_JSON=<file> additionally
// writes a machine-readable report; VALUE_E2E_OUTPUT_DIR relocates artefacts.
const chromiumPath = process.env.VALUE_E2E_CHROMIUM || process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || "";
const jsonReport = process.env.VALUE_E2E_JSON || "";
const outputDir = process.env.VALUE_E2E_OUTPUT_DIR || "test-results";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: jsonReport
    ? [["list"], ["json", { outputFile: jsonReport }]]
    : [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  outputDir,
  use: {
    baseURL: "http://127.0.0.1:18800",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    ...(chromiumPath ? { launchOptions: { executablePath: chromiumPath } } : {}),
  },
  webServer: {
    command: "node e2e/start-e2e-services.mjs",
    url: "http://127.0.0.1:18800",
    timeout: 120_000,
    reuseExistingServer: false,
    // SIGTERM to the process group lets start-e2e-services.mjs stop its
    // children and delete its temporary state (otherwise it leaks per run).
    gracefulShutdown: { signal: "SIGTERM", timeout: 5000 },
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "narrow-chromium", testMatch: /layout-accessibility\.spec\.ts/, use: { ...devices["Pixel 7"] } },
  ],
});
