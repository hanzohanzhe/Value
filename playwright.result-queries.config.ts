import { defineConfig, devices } from "@playwright/test";

// Read-only fixtures against the built UI. This config never starts a model.
export default defineConfig({
  testDir: "./e2e", testMatch: "result-queries.spec.ts", workers: 1, retries: 0,
  timeout: 30_000, expect: { timeout: 10_000 }, reporter: [["list"]],
  outputDir: "test-results/result-queries",
  use: { ...devices["Desktop Chrome"], baseURL: process.env.BASE_URL ?? "http://127.0.0.1:18800",
    trace: "retain-on-failure", screenshot: "only-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {} },
});
