// P0-1 S3: the UI same-origin gateway (scripts/value-ui-gateway.mjs).
// A fake API upstream and an HTML stub stand in for the backend and vinext;
// the last test drives the real production build when dist/ exists.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  SECURITY_HEADERS,
  createGateway,
  parseApiOrigin,
  resolveDataHome,
  sessionFilePath,
  validateBindHost,
  wrapServer,
} from "../scripts/value-ui-gateway.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TOKEN = "t".repeat(43);

function listen(server, host = "127.0.0.1") {
  return new Promise((resolve) => server.listen(0, host, () => resolve(server.address().port)));
}

function close(server) {
  return new Promise((resolve) => {
    server.closeAllConnections?.();
    server.close(() => resolve());
  });
}

function send({ port, method = "GET", path: target = "/", headers = {}, body = null, host = `127.0.0.1:${port}` }) {
  return new Promise((resolve, reject) => {
    const request = http.request({ host: "127.0.0.1", port, method, path: target, headers: { host, ...headers }, setHost: false });
    request.on("error", reject);
    request.on("response", (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        let json = null;
        try { json = JSON.parse(text); } catch { /* not JSON */ }
        resolve({ status: response.statusCode, headers: response.headers, text, json });
      });
    });
    if (body !== null) request.end(body); else request.end();
  });
}

async function makeUpstream() {
  const seen = [];
  const server = http.createServer((req, res) => {
    const hash = crypto.createHash("sha256");
    let bytes = 0;
    req.on("data", (chunk) => { hash.update(chunk); bytes += chunk.length; });
    req.on("end", () => {
      seen.push({ method: req.method, url: req.url, headers: { ...req.headers }, bytes });
      if (req.url === "/api/session-mismatch") {
        res.writeHead(403, { "Content-Type": "application/json", "X-VALUE-Error-Code": "GF_SESSION_INVALID" });
        res.end(JSON.stringify({ error: "session", error_code: "GF_SESSION_INVALID" }));
        return;
      }
      if (req.url === "/api/forbidden-other") {
        res.writeHead(403, { "Content-Type": "application/json", "X-VALUE-Error-Code": "GF_BROWSER_ORIGIN_REJECTED" });
        res.end(JSON.stringify({ error_code: "GF_BROWSER_ORIGIN_REJECTED" }));
        return;
      }
      res.writeHead(200, {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "X-VALUE-Session",
        "X-Upstream": "yes",
      });
      res.end(JSON.stringify({ headers: req.headers, sha256: hash.digest("hex"), bytes }));
    });
  });
  const port = await listen(server);
  return { server, port, seen };
}

function htmlStub(req, res) {
  const policy = String(req.headers["content-security-policy"] ?? "");
  const nonce = /'nonce-([^']+)'/.exec(policy)?.[1] ?? "";
  res.writeHead(200, { "Content-Type": "text/html" });
  res.end(`<!doctype html><script nonce="${nonce}">1</script><script nonce="${nonce}">2</script><p>VALUE</p>`);
}

async function makeGateway(t, { withSession = true, upstreamPort, apiOrigin, ...options } = {}) {
  const upstream = upstreamPort ? null : await makeUpstream();
  const dataHome = fs.mkdtempSync(path.join(os.tmpdir(), "value-gateway-"));
  const port = upstreamPort ?? upstream.port;
  if (withSession) {
    fs.mkdirSync(path.join(dataHome, "runtime"), { recursive: true });
    fs.writeFileSync(sessionFilePath(dataHome, port), JSON.stringify({ schema_version: "value.api-session/v1", port, token: TOKEN }));
  }
  const gateway = createGateway({ apiOrigin: apiOrigin ?? `http://127.0.0.1:${port}`, dataHome, log: () => {}, ...options });
  const server = wrapServer(http.createServer(htmlStub), gateway);
  const uiPort = await listen(server);
  t.after(async () => {
    await close(server);
    if (upstream) await close(upstream.server);
    fs.rmSync(dataHome, { recursive: true, force: true });
  });
  return { gateway, server, uiPort, upstream, dataHome };
}

function assertSecurityHeaders(headers) {
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) assert.equal(headers[name.toLowerCase()], value, name);
}

test("foreign Host headers are refused with 421 before anything is forwarded", async (t) => {
  const { uiPort, upstream } = await makeGateway(t);
  for (const host of ["attacker.example:" + uiPort, `[::1]:${uiPort}`, "127.0.0.1", "localhost", `127.0.0.1:${uiPort + 1}`, "127.0.0.1.nip.io:" + uiPort, "", `LOCALHOST:${uiPort}x`]) {
    for (const target of ["/", "/api/workspace"]) {
      const response = await send({ port: uiPort, path: target, host });
      assert.equal(response.status, 421, `${host} ${target}`);
      assert.equal(response.json.error_code, "GF_HOST_REJECTED");
      assertSecurityHeaders(response.headers);
    }
  }
  const post = await send({ port: uiPort, method: "POST", path: "/api/modules/install", host: "attacker.example", body: "x".repeat(1000),
    headers: { origin: "http://attacker.example", "content-type": "application/zip", "content-length": "1000" } });
  assert.equal(post.status, 421);
  assert.equal(upstream.seen.length, 0);
  for (const host of [`127.0.0.1:${uiPort}`, `localhost:${uiPort}`, `LocalHost:${uiPort}`]) {
    assert.equal((await send({ port: uiPort, path: "/", host })).status, 200, host);
  }
});

test("pages carry security headers and a fresh CSP nonce that vinext sees", async (t) => {
  const { uiPort } = await makeGateway(t);
  const nonces = [];
  for (let index = 0; index < 2; index += 1) {
    const response = await send({ port: uiPort, path: "/?view=run" });
    assert.equal(response.status, 200);
    assertSecurityHeaders(response.headers);
    const policy = response.headers["content-security-policy"];
    assert.match(policy, /frame-ancestors 'none'/);
    assert.match(policy, /base-uri 'none'/);
    assert.match(policy, /object-src 'none'/);
    assert.match(policy, /connect-src 'self'/);
    assert.doesNotMatch(policy, /unsafe-eval/);
    const nonce = /'nonce-([^']+)'/.exec(policy)[1];
    assert.ok(nonce.length >= 22);
    const inline = [...response.text.matchAll(/<script nonce="([^"]*)"/g)].map((match) => match[1]);
    assert.deepEqual(inline, [nonce, nonce]);
    nonces.push(nonce);
  }
  assert.notEqual(nonces[0], nonces[1]);
});

test("report-only switch keeps the nonce but only reports", async (t) => {
  const { uiPort } = await makeGateway(t, { cspReportOnly: true });
  const response = await send({ port: uiPort, path: "/" });
  assert.equal(response.headers["content-security-policy"], undefined);
  assert.match(response.headers["content-security-policy-report-only"], /'nonce-/);
});

test("API requests are forwarded with the injected token and without browser context", async (t) => {
  const { uiPort, upstream } = await makeGateway(t);
  const response = await send({
    port: uiPort, path: "/api/echo?x=1",
    headers: {
      "sec-fetch-site": "same-origin", "sec-fetch-mode": "cors", referer: `http://127.0.0.1:${uiPort}/`,
      cookie: "a=b", "x-value-session": "forged", "proxy-authorization": "x", connection: "keep-alive, x-drop-me",
      "x-drop-me": "1", "x-value-executable-trust": "acknowledged", "x-filename": "a.zip",
    },
  });
  assert.equal(response.status, 200);
  assertSecurityHeaders(response.headers);
  assert.equal(response.headers["x-upstream"], "yes");
  assert.equal(response.headers["access-control-allow-origin"], undefined);
  assert.equal(response.headers["access-control-allow-headers"], undefined);
  const forwarded = upstream.seen.at(-1);
  assert.equal(forwarded.url, "/api/echo?x=1");
  assert.equal(forwarded.headers["x-value-session"], TOKEN);
  assert.equal(forwarded.headers.host, `127.0.0.1:${upstream.port}`);
  for (const name of ["origin", "referer", "cookie", "sec-fetch-site", "sec-fetch-mode", "proxy-authorization", "x-drop-me"]) {
    assert.equal(forwarded.headers[name], undefined, name);
  }
  // Headers the UI legitimately sends survive (P0-2/P0-3 acknowledgement headers too).
  assert.equal(forwarded.headers["x-value-executable-trust"], "acknowledged");
  assert.equal(forwarded.headers["x-filename"], "a.zip");
  // The gateway adds nothing token-bearing to the response (this fake upstream
  // echoes request headers in its body; the real API never does).
  assert.doesNotMatch(JSON.stringify(response.headers), new RegExp(TOKEN));
});

test("same-origin POST is forwarded; cross-site, same-site, null and missing origins are refused", async (t) => {
  const { uiPort, upstream } = await makeGateway(t);
  const body = JSON.stringify({ confirm: true });
  const base = { "content-type": "application/json", "content-length": String(body.length) };
  const ok = await send({ port: uiPort, method: "POST", path: "/api/tutorials/value-101/reset", body,
    headers: { ...base, origin: `http://127.0.0.1:${uiPort}`, "sec-fetch-site": "same-origin" } });
  assert.equal(ok.status, 200);
  assert.equal(ok.json.headers["x-value-session"], TOKEN);
  const before = upstream.seen.length;
  const cases = [
    [{ origin: "https://evil.example", "sec-fetch-site": "cross-site" }, 403, "GF_GATEWAY_CROSS_SITE"],
    [{ origin: `http://localhost:${uiPort + 1}`, "sec-fetch-site": "same-site" }, 403, "GF_GATEWAY_CROSS_SITE"],
    [{ origin: "null", "sec-fetch-site": "cross-site" }, 403, "GF_GATEWAY_CROSS_SITE"],
    [{ origin: "null" }, 403, "GF_GATEWAY_ORIGIN_REJECTED"],
    [{ origin: "https://evil.example" }, 403, "GF_GATEWAY_ORIGIN_REJECTED"],
    [{ origin: `http://localhost:${uiPort}` }, 403, "GF_GATEWAY_ORIGIN_REJECTED"],
    [{}, 403, "GF_GATEWAY_ORIGIN_REJECTED"],
  ];
  for (const [extra, status, code] of cases) {
    const response = await send({ port: uiPort, method: "POST", path: "/api/tutorials/value-101/reset", body, headers: { ...base, ...extra } });
    assert.equal(response.status, status, JSON.stringify(extra));
    assert.equal(response.json.error_code, code, JSON.stringify(extra));
    assertSecurityHeaders(response.headers);
  }
  const crossSiteGet = await send({ port: uiPort, path: "/api/workspace", headers: { "sec-fetch-site": "cross-site" } });
  assert.equal(crossSiteGet.status, 403);
  const sameSiteGet = await send({ port: uiPort, path: "/api/workspace", headers: { "sec-fetch-site": "same-site" } });
  assert.equal(sameSiteGet.status, 403);
  assert.equal(upstream.seen.length, before);
});

test("methods, Content-Length and preflights are policed at the gateway", async (t) => {
  const { uiPort, upstream } = await makeGateway(t);
  const origin = `http://127.0.0.1:${uiPort}`;
  for (const method of ["PUT", "DELETE", "PATCH", "HEAD"]) {
    const response = await send({ port: uiPort, method, path: "/api/projects", headers: { origin } });
    assert.equal(response.status, 405, method);
  }
  const chunked = await new Promise((resolve, reject) => {
    const request = http.request({ host: "127.0.0.1", port: uiPort, method: "POST", path: "/api/projects",
      headers: { origin, "content-type": "application/json", "transfer-encoding": "chunked" } });
    request.on("error", reject);
    request.on("response", (response) => { response.resume(); response.on("end", () => resolve(response.statusCode)); });
    request.write("{}");
    request.end();
  });
  assert.equal(chunked, 411);
  const badLength = await send({ port: uiPort, method: "POST", path: "/api/projects", headers: { origin, "content-length": "abc" } });
  assert.ok([400, 411].includes(badLength.status) || badLength.status >= 400);
  const preflight = await send({ port: uiPort, method: "OPTIONS", path: "/api/modules/install",
    headers: { origin: "http://localhost:3000", "access-control-request-method": "POST", "sec-fetch-site": "cross-site" } });
  assert.equal(preflight.status, 403);
  const sameOriginPreflight = await send({ port: uiPort, method: "OPTIONS", path: "/api/modules/install" });
  assert.equal(sameOriginPreflight.status, 204);
  assert.equal(sameOriginPreflight.headers["access-control-allow-origin"], undefined);
  assert.equal(upstream.seen.length, 0);
});

test("a 50 MB upload streams through with the same bytes and bounded memory", async (t) => {
  const { uiPort } = await makeGateway(t);
  const chunk = crypto.randomBytes(1024 * 1024);
  const total = 50;
  const expected = crypto.createHash("sha256");
  for (let index = 0; index < total; index += 1) expected.update(chunk);
  global.gc?.();
  const baseline = process.memoryUsage().rss;
  let peak = baseline;
  const sampler = setInterval(() => { peak = Math.max(peak, process.memoryUsage().rss); }, 5);
  const result = await new Promise((resolve, reject) => {
    const request = http.request({ host: "127.0.0.1", port: uiPort, method: "POST", path: "/api/modules/install",
      headers: { origin: `http://127.0.0.1:${uiPort}`, "content-type": "application/zip", "content-length": String(total * chunk.length) } });
    request.on("error", reject);
    request.on("response", (response) => {
      const parts = [];
      response.on("data", (part) => parts.push(part));
      response.on("end", () => resolve(JSON.parse(Buffer.concat(parts).toString("utf8"))));
    });
    let sent = 0;
    const pump = () => {
      while (sent < total) {
        sent += 1;
        if (!request.write(chunk)) { request.once("drain", pump); return; }
      }
      request.end();
    };
    pump();
  });
  clearInterval(sampler);
  assert.equal(result.bytes, total * chunk.length);
  assert.equal(result.sha256, expected.digest("hex"));
  assert.ok(peak - baseline < 64 * 1024 * 1024, `RSS grew by ${(peak - baseline) / 1048576} MiB`);
});

test("session problems become 502 with the session file path", async (t) => {
  const { uiPort, dataHome, upstream } = await makeGateway(t);
  const mismatch = await send({ port: uiPort, path: "/api/session-mismatch" });
  assert.equal(mismatch.status, 502);
  assert.equal(mismatch.json.error_code, "GF_GATEWAY_SESSION_MISMATCH");
  assert.equal(mismatch.json.session_file, sessionFilePath(dataHome, upstream.port));
  assert.match(mismatch.json.error, /runtime[\\/]api-session-\d+\.json/);
  const otherForbidden = await send({ port: uiPort, path: "/api/forbidden-other" });
  assert.equal(otherForbidden.status, 403);

  const missing = await makeGateway(t, { withSession: false });
  const response = await send({ port: missing.uiPort, path: "/api/workspace" });
  assert.equal(response.status, 502);
  assert.equal(response.json.error_code, "GF_GATEWAY_SESSION_UNAVAILABLE");
  assert.equal(response.json.session_file, sessionFilePath(missing.dataHome, missing.upstream.port));
  assert.equal(missing.upstream.seen.length, 0);

  const optional = await makeGateway(t, { withSession: false, sessionOptional: true });
  const forwarded = await send({ port: optional.uiPort, path: "/api/echo" });
  assert.equal(forwarded.status, 200);
  assert.equal(forwarded.json.headers["x-value-session"], undefined);
});

test("a stopped API gives 502 instead of a hanging page", async (t) => {
  const probe = http.createServer();
  const deadPort = await listen(probe);
  await close(probe);
  const { uiPort } = await makeGateway(t, { upstreamPort: deadPort });
  const response = await send({ port: uiPort, path: "/api/health" });
  assert.equal(response.status, 502);
  assert.equal(response.json.error_code, "GF_GATEWAY_UPSTREAM_UNAVAILABLE");
});

test("command-line validation: loopback bind hosts and http loopback API origins only", () => {
  assert.equal(validateBindHost("127.0.0.1"), "127.0.0.1");
  assert.equal(validateBindHost("localhost"), "localhost");
  for (const host of ["0.0.0.0", "::", "::1", "192.168.1.2", ""]) assert.throws(() => validateBindHost(host));
  assert.deepEqual(parseApiOrigin("http://127.0.0.1:8766"), { hostname: "127.0.0.1", port: 8766, origin: "http://127.0.0.1:8766" });
  assert.equal(parseApiOrigin("http://localhost:18766/").port, 18766);
  for (const bad of ["https://127.0.0.1:8766", "http://127.0.0.1", "http://example.com:8766", "http://0.0.0.0:8766",
    "http://user:pw@127.0.0.1:8766", "http://127.0.0.1:8766/api", "127.0.0.1:8766", "http://[::1]:8766"]) {
    assert.throws(() => parseApiOrigin(bad), undefined, bad);
  }
});

test("the gateway refuses to wrap a server unless it has exactly one request listener", () => {
  const gateway = createGateway({ apiOrigin: "http://127.0.0.1:9", dataHome: os.tmpdir(), log: () => {} });
  assert.throws(() => wrapServer(http.createServer(), gateway), /exactly one request listener/);
  const two = http.createServer(() => {});
  two.on("request", () => {});
  assert.throws(() => wrapServer(two, gateway), /exactly one request listener/);
  const one = wrapServer(http.createServer(() => {}), gateway);
  assert.equal(one.listeners("request").length, 1);
});

test("data directory rules follow runtime_paths.user_data_root", () => {
  const home = "/home/someone";
  const cwd = "/work/dir";
  const resolve = (env) => resolveDataHome({ env, cwd, homedir: home });
  assert.equal(resolve({ VALUE_DATA_HOME: "/abs/state" }), "/abs/state");
  assert.equal(resolve({ VALUE_DATA_HOME: "", XDG_DATA_HOME: "/xdg" }), "/xdg/value");
  assert.equal(resolve({ VALUE_DATA_HOME: "~/vh", HOME: home }), "/home/someone/vh");
  const warnings = [];
  assert.equal(resolveDataHome({ env: { VALUE_DATA_HOME: "rel/state" }, cwd, homedir: home, warn: (line) => warnings.push(line) }), "/work/dir/rel/state");
  assert.equal(warnings.length, 1);
  assert.equal(resolve({ LOCALAPPDATA: "/lad" }), "/lad/VALUE");
  assert.equal(resolve({ HOME: home }), "/home/someone/.local/share/value");
  assert.equal(sessionFilePath("/abs/state", 8766), path.join("/abs/state", "runtime", "api-session-8766.json"));
});

test("real production build: two page loads, every inline script carries that response's nonce", async (t) => {
  if (!fs.existsSync(path.join(ROOT, "dist", "server", "index.js"))) {
    t.skip("dist/ not built");
    return;
  }
  const upstream = await makeUpstream();
  const dataHome = fs.mkdtempSync(path.join(os.tmpdir(), "value-gateway-dist-"));
  fs.mkdirSync(path.join(dataHome, "runtime"));
  fs.writeFileSync(sessionFilePath(dataHome, upstream.port), JSON.stringify({ schema_version: "value.api-session/v1", port: upstream.port, token: TOKEN }));
  const probe = http.createServer();
  const uiPort = await listen(probe);
  await close(probe);
  const child = spawn(process.execPath, [path.join(ROOT, "scripts", "serve-value-ui.mjs"), "--host", "127.0.0.1", "--port", String(uiPort),
    "--api-origin", `http://127.0.0.1:${upstream.port}`], { cwd: ROOT, env: { ...process.env, VALUE_DATA_HOME: dataHome }, stdio: ["ignore", "pipe", "pipe"] });
  let output = "";
  child.stdout.on("data", (chunk) => { output += chunk; });
  child.stderr.on("data", (chunk) => { output += chunk; });
  t.after(async () => {
    child.kill("SIGTERM");
    await close(upstream.server);
    fs.rmSync(dataHome, { recursive: true, force: true });
  });
  const deadline = Date.now() + 60_000;
  while (!output.includes("VALUE UI gateway:")) {
    if (child.exitCode !== null) assert.fail(`UI server exited: ${output}`);
    if (Date.now() > deadline) assert.fail(`UI server did not start: ${output}`);
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  const nonces = [];
  for (let index = 0; index < 2; index += 1) {
    const response = await send({ port: uiPort, path: "/" });
    assert.equal(response.status, 200);
    assertSecurityHeaders(response.headers);
    const nonce = /'nonce-([^']+)'/.exec(response.headers["content-security-policy"])[1];
    const scripts = [...response.text.matchAll(/<script\b([^>]*)>/g)].map((match) => match[1]);
    const inline = scripts.filter((attributes) => !/\bsrc=/.test(attributes));
    assert.ok(inline.length > 0);
    for (const attributes of inline) assert.match(attributes, new RegExp(`nonce="${nonce.replace(/[+/=]/g, "\\$&")}"`));
    nonces.push(nonce);
  }
  assert.notEqual(nonces[0], nonces[1]);
  const asset = /<script\b[^>]*\bsrc="([^"]+)"/.exec((await send({ port: uiPort, path: "/" })).text)?.[1];
  if (asset) {
    const response = await send({ port: uiPort, path: asset });
    assert.equal(response.status, 200);
    assertSecurityHeaders(response.headers);
  }
  assert.equal((await send({ port: uiPort, path: "/", host: `attacker.example:${uiPort}` })).status, 421);
  const api = await send({ port: uiPort, path: "/api/echo" });
  assert.equal(api.json.headers["x-value-session"], TOKEN);
  assert.doesNotMatch(output, /Seeded/);
  assert.doesNotMatch(output, new RegExp(TOKEN));
});
