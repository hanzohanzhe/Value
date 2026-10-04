import { defineConfig, devices } from "@playwright/test";

// Runs only the read-only evidence fixture against an already built UI.
export default defineConfig({
  testDir: "./e2e", testMatch: "evidence-isolation.spec.ts", workers: 1, retries: 0,
  timeout: 30_000, expect: { timeout: 10_000 }, reporter: [["list"]],
  outputDir: "test-results/evidence-isolation",
  use: { ...devices["Desktop Chrome"], baseURL: process.env.BASE_URL ?? "http://127.0.0.1:18800",
    trace: "retain-on-failure", screenshot: "only-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {} },
});
