import { defineConfig, devices } from "@playwright/test";

// One read-only API fixture plus a mocked Study save; never starts a model.
export default defineConfig({
  testDir: "./e2e", testMatch: "module-authoring.spec.ts", workers: 1, retries: 0, timeout: 30000,
  reporter: [["list"]], outputDir: "test-results/module-authoring",
  use: { ...devices["Desktop Chrome"], baseURL: process.env.BASE_URL ?? "http://127.0.0.1:18800",
    trace: "retain-on-failure", screenshot: "only-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {} },
});
