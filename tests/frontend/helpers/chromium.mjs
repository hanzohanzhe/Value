// Launch options for browser-backed node tests (P0-9 S0). The pinned
// @playwright/test expects a browser revision an offline machine may not have;
// VALUE_E2E_CHROMIUM (shared with the Playwright e2e config) names any Chrome or
// chrome-headless-shell executable instead. CSV_MAPPING_CHROMIUM_EXECUTABLE is
// the older, harness-specific spelling and still works.
export function chromiumLaunchOptions() {
  const executablePath = process.env.VALUE_E2E_CHROMIUM || process.env.CSV_MAPPING_CHROMIUM_EXECUTABLE || "";
  return { headless: true, ...(executablePath ? { executablePath } : {}) };
}
