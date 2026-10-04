import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e", testMatch: "comparison-review.spec.ts", workers: 1, retries: 0, timeout: 30000,
  reporter: [["list"]], outputDir: "test-results/comparison-review",
  use: { ...devices["Desktop Chrome"], baseURL: process.env.BASE_URL ?? "http://127.0.0.1:18800", trace: "retain-on-failure", screenshot: "only-on-failure" },
});
