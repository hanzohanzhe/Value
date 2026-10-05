import { expect, test, type Page } from "@playwright/test";
import http from "node:http";
import type { AddressInfo } from "node:net";

// P0-1 S7: browser-level regression of the local security boundary.
//
// A real attack server listens on 127.0.0.1:18999 (same site as the UI, other
// port) and is reached both as http://127.0.0.1:18999 and as
// http://localhost:18999 (cross-site).  Its pages fire the review's attacks at
// the UI gateway (18800) and straight at the API (18766): text/plain fetches,
// HTML form posts, cross-origin reads and an iframe.  No request is fulfilled
// by Playwright routing: each attack must reach a VALUE server and be answered
// 403/421 (a `requestfailed` would only prove that the browser itself blocked
// it, which says nothing about VALUE).  A positive control proves that the same
// write made the legitimate way does change state.
//
// Needs the real Python service (skipped when VALUE_E2E_UI_ONLY=1).

const UI = "http://127.0.0.1:18800";
const API = "http://127.0.0.1:18766";
const ATTACK_PORT = 18999;
const VIEWS = [
  "Home", "Research guide", "Learn", "Studies", "Data", "Modules", "Runs",
  "Market replay", "VRE & curtailment", "Network & redispatch", "Network & water", "Inspect", "Add data",
];
const uiOnly = process.env.VALUE_E2E_UI_ONLY === "1";

function attackPage(prefix: string): string {
  const body = (name: string) => JSON.stringify(JSON.stringify({ name }));
  return `<!doctype html><html><body><h1>attacker</h1>
<iframe id="framed" src="${UI}/" width="600" height="400"></iframe>
<iframe name="sink" width="10" height="10"></iframe>
<form id="form-ui" method="POST" action="${UI}/api/data-packs" enctype="text/plain" target="sink"><input name='{"name":"${prefix}-form-ui","x":"' value='"}'></form>
<form id="form-api" method="POST" action="${API}/api/data-packs" enctype="application/x-www-form-urlencoded" target="sink"><input name="name" value="${prefix}-form-api"></form>
<script>
window.attacks = (async () => {
  const results = {};
  const fire = async (name, url, init) => {
    try { const response = await fetch(url, init); results[name] = response.type === "opaque" ? "opaque" : response.status; }
    catch (error) { results[name] = "error:" + error.message; }
  };
  await fire("ui-text-plain", "${UI}/api/data-packs", { method: "POST", mode: "no-cors", headers: { "Content-Type": "text/plain" }, body: ${body(`${prefix}-ui-text-plain`)} });
  await fire("api-text-plain", "${API}/api/data-packs", { method: "POST", mode: "no-cors", headers: { "Content-Type": "text/plain" }, body: ${body(`${prefix}-api-text-plain`)} });
  await fire("ui-read", "${UI}/api/workspace", { mode: "cors" });
  await fire("api-read", "${API}/api/workspace", { mode: "cors" });
  await fire("api-json", "${API}/api/data-packs", { method: "POST", mode: "cors", headers: { "Content-Type": "application/json" }, body: ${body(`${prefix}-api-json`)} });
  document.getElementById("form-ui").submit();
  await new Promise((resolve) => setTimeout(resolve, 600));
  document.getElementById("form-api").submit();
  await new Promise((resolve) => setTimeout(resolve, 600));
  return results;
})();
</script></body></html>`;
}

let attackServer: http.Server;

test.beforeAll(async () => {
  test.skip(uiOnly, "needs the real Python service; VALUE_E2E_UI_ONLY=1 serves the UI only");
  // Playwright's webServer readiness only waits for the UI; the API (and the
  // gateway's session) may still be starting.  An attack on a dead port would
  // prove nothing, so wait until the gateway reaches the API.
  const deadline = Date.now() + 120_000;
  for (;;) {
    try {
      if ((await fetch(`${UI}/api/health`)).status === 200 && (await fetch(`${API}/api/health`)).status === 200) break;
    } catch { /* not up yet */ }
    if (Date.now() > deadline) throw new Error("the VALUE API did not become reachable through the gateway");
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  attackServer = http.createServer((request, response) => {
    const prefix = new URL(request.url ?? "/", "http://attacker").searchParams.get("prefix") ?? "csrf";
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(attackPage(prefix));
  });
  await new Promise<void>((resolve) => attackServer.listen(ATTACK_PORT, "127.0.0.1", () => resolve()));
  expect((attackServer.address() as AddressInfo).port).toBe(ATTACK_PORT);
});

test.afterAll(async () => {
  if (attackServer) await new Promise<void>((resolve) => attackServer.close(() => resolve()));
});

test.beforeEach(() => {
  test.skip(uiOnly, "needs the real Python service; VALUE_E2E_UI_ONLY=1 serves the UI only");
});

async function packNames(page: Page): Promise<string[]> {
  const response = await page.request.get("/api/data-packs");
  expect(response.status()).toBe(200);
  return ((await response.json()).data_packs as { id: string; name: string }[]).map((pack) => `${pack.id} ${pack.name}`);
}

for (const attacker of [`http://127.0.0.1:${ATTACK_PORT}`, `http://localhost:${ATTACK_PORT}`]) {
  test(`attacks from ${attacker} are refused by VALUE itself`, async ({ page }) => {
    const prefix = attacker.includes("localhost") ? "csrf-cross-site" : "csrf-same-site";
    const isValue = (url: string) => url.startsWith(`${UI}/api/`) || url.startsWith(`${API}/api/`);
    // The status VALUE sent is read from the raw response headers (CDP
    // responseReceivedExtraInfo): a refused no-cors response is withheld from
    // the page by Cross-Origin-Resource-Policy and a refused CORS read by the
    // missing CORS grant, so Playwright's own response event may never fire.
    const sent = new Map<string, { url: string; method: string }>();
    const statusById = new Map<string, number>();
    const failed: { url: string; method: string; error: string }[] = [];
    const answered: { url: string; method: string; status: number }[] = [];
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Network.enable");
    cdp.on("Network.requestWillBeSent", (event) => {
      if (isValue(event.request.url)) sent.set(event.requestId, { url: event.request.url, method: event.request.method });
    });
    cdp.on("Network.responseReceivedExtraInfo", (event) => statusById.set(event.requestId, event.statusCode));
    page.on("response", (response) => {
      if (isValue(response.url())) answered.push({ url: response.url(), method: response.request().method(), status: response.status() });
    });
    page.on("requestfailed", (request) => {
      if (isValue(request.url())) failed.push({ url: request.url(), method: request.method(), error: request.failure()?.errorText ?? "" });
    });
    await page.goto(`${attacker}/?prefix=${prefix}`);
    const results = await page.evaluate(() => (window as unknown as { attacks: Promise<Record<string, unknown>> }).attacks);
    const observed = () => {
      const rows = [...answered];
      for (const [id, request] of sent) {
        const status = statusById.get(id);
        if (status !== undefined) rows.push({ ...request, status });
      }
      return rows;
    };
    // Four writes reach VALUE (two no-cors fetches, two HTML forms); the JSON
    // write stops at its refused preflight.
    await expect.poll(() => observed().filter((row) => row.method === "POST").length, { timeout: 15_000 }).toBeGreaterThanOrEqual(4);
    const rows = observed();
    expect(rows.filter((row) => row.method === "POST").length).toBeGreaterThanOrEqual(4);
    expect(rows.filter((row) => row.method === "GET").length).toBeGreaterThanOrEqual(2);
    for (const row of rows) expect([403, 421], `${row.method} ${row.url}`).toContain(row.status);
    // A request the browser failed without VALUE having answered it (for
    // example a local-network-access block) proves nothing about VALUE.
    const unanswered = failed.filter((row) => !rows.some((seen) => seen.url === row.url && seen.method === row.method));
    expect(unanswered, "attacks blocked by the browser prove nothing about VALUE").toEqual([]);
    // Readable responses are refusals too; opaque ones were observed above.
    for (const [name, value] of Object.entries(results)) {
      if (typeof value === "number") expect([403, 421], name).toContain(value);
      else expect(String(value), name).toMatch(/^(opaque|error:)/);
    }
    // No side effect: none of the attack packs exists.
    expect((await packNames(page)).filter((name) => name.includes(prefix))).toEqual([]);

    // The framed UI is refused (X-Frame-Options DENY / frame-ancestors 'none').
    const framed = page.frames().find((frame) => frame !== page.mainFrame() && frame.name() !== "sink");
    expect(framed).toBeTruthy();
    const content = await framed!.content().catch(() => "");
    expect(content).not.toContain("workspace-nav-group");
    expect(content).not.toContain("Power-system evolution");
  });
}

test("positive control: the same write through the VALUE page path changes state", async ({ page }) => {
  const name = `csrf-positive-${Date.now()}`;
  const created = await page.request.post("/api/data-packs", { data: { name }, headers: { origin: UI } });
  expect(created.status()).toBe(201);
  expect((await packNames(page)).some((row) => row.includes(name))).toBeTruthy();
  // ...and the very same request without the page's Origin is refused by the gateway.
  const refused = await page.request.post("/api/data-packs", { data: { name: `${name}-x` } });
  expect(refused.status()).toBe(403);
  // Direct to the API, without the gateway's session: refused.
  const direct = await page.request.post(`${API}/api/data-packs`, { data: { name: `${name}-y` } });
  expect(direct.status()).toBe(403);
});

test("thirteen views render without a single CSP violation", async ({ page }) => {
  const violations: string[] = [];
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (event) => {
      (window as unknown as { __csp: string[] }).__csp ??= [];
      (window as unknown as { __csp: string[] }).__csp.push(`${event.violatedDirective} ${event.blockedURI}`);
    });
  });
  page.on("console", (message) => {
    if (/Content Security Policy/i.test(message.text())) violations.push(message.text());
  });
  const response = await page.goto("/");
  expect(response?.headers()["content-security-policy"]).toMatch(/script-src 'self' 'nonce-/);
  expect(response?.headers()["x-frame-options"]).toBe("DENY");
  await expect(page.locator(".rail-foot")).toContainText("Python");
  const nav = page.getByRole("navigation", { name: "Workspace" });
  for (const label of VIEWS) {
    await nav.getByRole("button", { name: new RegExp(`^${label.replace(/[&]/g, "\\$&")}:`) }).click();
    await expect(page.locator(".topbar h1")).toHaveText(label);
    await page.waitForLoadState("networkidle");
  }
  const recorded = await page.evaluate(() => (window as unknown as { __csp?: string[] }).__csp ?? []);
  expect([...violations, ...recorded]).toEqual([]);
});
