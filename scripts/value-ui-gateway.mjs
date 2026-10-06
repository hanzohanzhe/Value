/** VALUE UI same-origin gateway (P0-1, findings F5-01, R1-01, R1-14, R1-15).
 *
 * The browser talks only to the UI origin (http://127.0.0.1:<ui port>).  This
 * module sits in front of the UI server's single request listener:
 *
 * - every request: the Host header must be exactly 127.0.0.1:<port> or
 *   localhost:<port> (421 otherwise, which defeats DNS rebinding), and every
 *   response carries X-Frame-Options DENY, nosniff, Referrer-Policy
 *   no-referrer, COOP/CORP same-origin and a restrictive Permissions-Policy;
 * - pages (anything outside /api): a fresh CSP nonce per request, sent in the
 *   Content-Security-Policy response header and handed to vinext through the
 *   request header it reads the nonce from;
 * - /api/*: only GET, POST and OPTIONS; Sec-Fetch-Site must be same-origin or
 *   none when present; a POST must carry Origin == http://<Host> and a
 *   Content-Length (411 otherwise); hop-by-hop, browser-context
 *   (Origin, Referer, Cookie, Sec-Fetch-*) and any client-supplied
 *   X-VALUE-Session headers are dropped, the session token is injected
 *   server side and the request is streamed to the local API; on the way
 *   back Access-Control-* headers are dropped.  A 403 with a GF_SESSION_*
 *   code from the API becomes 502 GF_GATEWAY_SESSION_MISMATCH naming the
 *   session file it read.
 *
 * The token is read from <VALUE_DATA_HOME>/runtime/api-session-<api port>.json,
 * located with the same rules as gridform_core.runtime_paths.user_data_root().
 * It is never logged, never put on a command line and never sent to the
 * browser.  Node built-in modules only.
 */
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";

export const SESSION_HEADER = "x-value-session";
export const MAX_DRAIN_BYTES = 2 * 1024 * 1024;
export const SECURITY_HEADERS = Object.freeze({
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), serial=(), hid=()",
});
const API_METHODS = new Set(["GET", "POST", "OPTIONS"]);
const ALLOWED_FETCH_SITES = new Set(["same-origin", "none"]);
const HOP_BY_HOP = new Set([
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "proxy-connection",
  "te", "trailer", "trailers", "transfer-encoding", "upgrade", "http2-settings",
]);
// Browser context the API must never see: it rejects any Origin and any
// Sec-Fetch-Site other than none, because only the gateway may vouch for a page.
const BROWSER_CONTEXT = new Set(["origin", "referer", "cookie", "host", "content-security-policy", "content-security-policy-report-only"]);

/** Content-Security-Policy for one page response (the frontend calls only
 * its own origin, so connect-src is 'self'). */
export function contentSecurityPolicy(nonce) {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}'`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

function expandUser(value, homedir) {
  if (value === "~") return homedir;
  if (value.startsWith("~/") || value.startsWith("~\\")) return path.join(homedir, value.slice(2));
  return value;
}

/** Python's Path.resolve(strict=False): resolve symlinks of the existing prefix. */
function resolveLikePython(candidate) {
  const absolute = path.resolve(candidate);
  const missing = [];
  let current = absolute;
  for (;;) {
    try {
      const real = fs.realpathSync.native(current);
      return missing.length ? path.join(real, ...missing.reverse()) : real;
    } catch {
      const parent = path.dirname(current);
      if (parent === current) return absolute;
      missing.push(path.basename(current));
      current = parent;
    }
  }
}

/** The VALUE data directory, by the rules of runtime_paths.user_data_root(). */
export function resolveDataHome({ env = process.env, cwd = process.cwd(), homedir = os.homedir(), warn = () => {} } = {}) {
  const inCwd = (value) => (path.isAbsolute(value) ? value : path.join(cwd, value));
  const configured = env.VALUE_DATA_HOME;
  if (configured) {
    const expanded = expandUser(configured, env.HOME || homedir);
    if (!path.isAbsolute(expanded)) {
      warn(`VALUE_DATA_HOME is relative (${configured}); resolving it against ${cwd}. Launchers should pass an absolute path.`);
    }
    return resolveLikePython(inCwd(expanded));
  }
  if (env.LOCALAPPDATA) return resolveLikePython(inCwd(path.join(env.LOCALAPPDATA, "VALUE")));
  if (env.XDG_DATA_HOME) return resolveLikePython(inCwd(expandUser(path.join(env.XDG_DATA_HOME, "value"), env.HOME || homedir)));
  return resolveLikePython(path.join(env.HOME || homedir, ".local", "share", "value"));
}

export function sessionFilePath(dataHome, apiPort) {
  return path.join(dataHome, "runtime", `api-session-${apiPort}.json`);
}

/** Parse --api-origin: http, loopback host, explicit port. */
export function parseApiOrigin(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`--api-origin must be an http loopback origin such as http://127.0.0.1:8766, not ${value}`);
  }
  const explicitPort = /^http:\/\/[^/]+:(\d+)\/?$/.exec(value);
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(url.hostname) || !explicitPort
      || url.username || url.password || (url.pathname !== "/" && url.pathname !== "") || url.search || url.hash) {
    throw new Error(`--api-origin must be http://127.0.0.1:<port> or http://localhost:<port>, not ${value}`);
  }
  const port = Number.parseInt(explicitPort[1], 10);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("--api-origin port must be between 1 and 65535");
  return { hostname: url.hostname, port, origin: `http://${url.hostname}:${port}` };
}

export function validateBindHost(host) {
  if (host !== "127.0.0.1" && host !== "localhost") {
    throw new Error(`--host must be 127.0.0.1 or localhost (VALUE serves loopback only), not ${host}`);
  }
  return host;
}

function applySecurityHeaders(res) {
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) res.setHeader(name, value);
}

function allowedHosts(port) {
  return new Set([`127.0.0.1:${port}`, `localhost:${port}`]);
}

function requestBodyLength(req) {
  const raw = req.headers["content-length"];
  if (raw === undefined) return null;
  if (!/^\d+$/.test(String(raw))) return NaN;
  return Number(raw);
}

/** Answer without forwarding; a small body is read first so the client sees
 * the answer instead of a connection reset. */
const LAUNCHER_PAGE = `<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Open VALUE from its launcher</title></head>
<body style="font-family:system-ui,sans-serif;margin:0;padding:24px 16px;background:#f6f7fa;color:#172033"><main role="alert" style="max-width:560px;margin:10vh auto;background:#fff;border:1px solid #d9dee8;border-radius:8px;padding:28px 24px">
<h1 style="margin:0 0 12px;font-size:22px">Open VALUE from its launcher</h1>
<p style="margin:0;font-size:15px;line-height:1.55;color:#596273">This page was not opened through the VALUE launcher, so it cannot talk to the local engine. Close it and start VALUE again with start-value (or the desktop shortcut).</p>
</main></body></html>
`;

function reject(req, res, status, code, message, extra = {}, { html = false } = {}) {
  const body = Buffer.from(html ? LAUNCHER_PAGE : JSON.stringify({ error: message, error_code: code, ...extra }));
  const send = () => {
    if (res.headersSent) return;
    applySecurityHeaders(res);
    if (html) res.setHeader("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'");
    res.writeHead(status, {
      "Content-Type": html ? "text/html; charset=utf-8" : "application/json; charset=utf-8",
      "Content-Length": body.length,
      "Cache-Control": "no-store",
      "X-VALUE-Error-Code": code,
      ...(close ? { Connection: "close" } : {}),
    });
    res.end(body);
  };
  const length = requestBodyLength(req);
  const chunked = /chunked/i.test(String(req.headers["transfer-encoding"] ?? ""));
  const close = chunked || Number.isNaN(length) || (length !== null && length > MAX_DRAIN_BYTES);
  if (close || req.readableEnded || req.method === "GET" || req.method === "HEAD" || !length) {
    if (close) req.on("error", () => {});
    send();
    if (close) res.on("finish", () => req.socket?.destroy());
    else req.resume();
    return;
  }
  req.on("error", () => {});
  req.on("end", send);
  req.resume();
}

function hopByHopNames(headers) {
  const names = new Set(HOP_BY_HOP);
  for (const token of String(headers.connection ?? "").split(",")) {
    const name = token.trim().toLowerCase();
    if (name) names.add(name);
  }
  return names;
}

function forwardedRequestHeaders(req, upstream, token) {
  const dropped = hopByHopNames(req.headers);
  const headers = {};
  for (const [name, value] of Object.entries(req.headers)) {
    const lower = name.toLowerCase();
    if (dropped.has(lower) || BROWSER_CONTEXT.has(lower) || lower === SESSION_HEADER || lower.startsWith("sec-fetch-")) continue;
    headers[lower] = value;
  }
  headers.host = `${upstream.hostname}:${upstream.port}`;
  if (token) headers[SESSION_HEADER] = token;
  return headers;
}

function returnedResponseHeaders(upstreamResponse) {
  const dropped = hopByHopNames(upstreamResponse.headers);
  const headers = {};
  for (const [name, value] of Object.entries(upstreamResponse.headers)) {
    const lower = name.toLowerCase();
    if (dropped.has(lower) || lower.startsWith("access-control-")) continue;
    headers[lower] = value;
  }
  return headers;
}

async function readSession(file) {
  let text;
  try {
    text = await fs.promises.readFile(file, "utf8");
  } catch (error) {
    return { problem: error?.code === "ENOENT" ? "missing" : "unreadable" };
  }
  try {
    const payload = JSON.parse(text);
    if (payload && payload.schema_version === "value.api-session/v1" && typeof payload.token === "string" && payload.token) {
      return { token: payload.token };
    }
  } catch {
    // fall through
  }
  return { problem: "invalid" };
}

/** Build the gateway.  ``handle(req, res, next)`` serves one request; ``next``
 * is the UI server's own listener for page and asset requests. */
export function createGateway({
  upstreamOrigin = "http://127.0.0.1:8766",
  dataHome = undefined,
  env = process.env,
  cwd = process.cwd(),
  csp = true,
  cspReportOnly = env.VALUE_UI_CSP_REPORT_ONLY === "1",
  sessionOptional = false,
  log = (line) => process.stderr.write(`${line}\n`),
} = {}) {
  const upstream = parseApiOrigin(upstreamOrigin);
  const home = dataHome ?? resolveDataHome({ env, cwd, warn: (line) => log(`[value-ui-gateway] ${line}`) });
  const sessionFile = sessionFilePath(home, upstream.port);
  const cspHeader = cspReportOnly ? "Content-Security-Policy-Report-Only" : "Content-Security-Policy";
  const counters = { forwarded: 0, rejected: 0 };

  async function proxy(req, res) {
    const session = await readSession(sessionFile);
    if (!session.token && !sessionOptional) {
      reject(req, res, 502, "GF_GATEWAY_SESSION_UNAVAILABLE",
        `The VALUE API session file is ${session.problem}: ${sessionFile}. Start VALUE with its launcher, or check that the UI and the API use the same VALUE_DATA_HOME and API port.`,
        { session_file: sessionFile });
      return;
    }
    counters.forwarded += 1;
    const upstreamRequest = http.request({
      hostname: upstream.hostname,
      port: upstream.port,
      method: req.method,
      path: req.url,
      headers: forwardedRequestHeaders(req, upstream, session.token),
    });
    let settled = false;
    const fail = () => {
      if (settled) return;
      settled = true;
      if (res.headersSent) {
        res.destroy();
        return;
      }
      reject(req, res, 502, "GF_GATEWAY_UPSTREAM_UNAVAILABLE",
        `The VALUE API at ${upstream.origin} did not answer. Is the backend running?`);
    };
    upstreamRequest.on("error", fail);
    res.on("close", () => {
      if (!res.writableFinished) upstreamRequest.destroy();
    });
    upstreamRequest.on("response", (upstreamResponse) => {
      settled = true;
      const code = String(upstreamResponse.headers["x-value-error-code"] ?? "");
      if (upstreamResponse.statusCode === 403 && code.startsWith("GF_SESSION_")) {
        upstreamResponse.resume();
        reject(req, res, 502, "GF_GATEWAY_SESSION_MISMATCH",
          `The VALUE API refused the session read from ${sessionFile} (${code}). The UI and the API probably use different data directories or API ports; restart VALUE with its launcher.`,
          { session_file: sessionFile, upstream_error_code: code });
        return;
      }
      applySecurityHeaders(res);
      res.writeHead(upstreamResponse.statusCode ?? 502, returnedResponseHeaders(upstreamResponse));
      upstreamResponse.on("error", () => res.destroy());
      upstreamResponse.pipe(res);
    });
    req.on("error", () => upstreamRequest.destroy());
    req.pipe(upstreamRequest);
  }

  function handle(req, res, next) {
    const port = req.socket?.localPort;
    const host = String(req.headers.host ?? "").toLowerCase();
    if (!allowedHosts(port).has(host)) {
      counters.rejected += 1;
      const page = !String(req.url ?? "").split("?")[0].startsWith("/api");
      reject(req, res, 421, "GF_HOST_REJECTED", "VALUE only answers requests addressed to 127.0.0.1 or localhost.", {}, { html: page });
      return;
    }
    const target = String(req.url ?? "");
    if (!target.startsWith("/")) {
      counters.rejected += 1;
      reject(req, res, 400, "GF_GATEWAY_BAD_TARGET", "Request target must be a path.");
      return;
    }
    const pathname = target.split("?")[0];
    if (pathname !== "/api" && !pathname.startsWith("/api/")) {
      applySecurityHeaders(res);
      if (csp) {
        const nonce = crypto.randomBytes(16).toString("base64");
        const policy = contentSecurityPolicy(nonce);
        res.setHeader(cspHeader, policy);
        // vinext reads the nonce of its inline scripts from this request header.
        delete req.headers["content-security-policy-report-only"];
        req.headers[cspReportOnly ? "content-security-policy-report-only" : "content-security-policy"] = policy;
        if (cspReportOnly) delete req.headers["content-security-policy"];
      }
      next(req, res);
      return;
    }
    if (!API_METHODS.has(req.method)) {
      counters.rejected += 1;
      res.setHeader("Allow", "GET, POST, OPTIONS");
      reject(req, res, 405, "GF_GATEWAY_METHOD", `${req.method} is not available on the VALUE API.`);
      return;
    }
    const site = req.headers["sec-fetch-site"];
    if (site !== undefined && !ALLOWED_FETCH_SITES.has(String(site).toLowerCase())) {
      counters.rejected += 1;
      reject(req, res, 403, "GF_GATEWAY_CROSS_SITE", "Requests from other web sites cannot reach the VALUE API.");
      return;
    }
    if (req.method === "OPTIONS") {
      // Same-origin pages never send a preflight; answer without any CORS grant.
      applySecurityHeaders(res);
      res.writeHead(204, { "Cache-Control": "no-store", Allow: "GET, POST, OPTIONS" });
      res.end();
      req.resume();
      return;
    }
    if (req.method === "POST") {
      if (req.headers.origin !== `http://${host}`) {
        counters.rejected += 1;
        reject(req, res, 403, "GF_GATEWAY_ORIGIN_REJECTED", "A change to VALUE must come from a VALUE page.");
        return;
      }
      const length = requestBodyLength(req);
      if (length === null || Number.isNaN(length)) {
        counters.rejected += 1;
        reject(req, res, length === null ? 411 : 400, length === null ? "GF_GATEWAY_LENGTH_REQUIRED" : "GF_GATEWAY_BAD_LENGTH",
          "A request body needs a valid Content-Length.");
        return;
      }
    }
    proxy(req, res).catch(() => {
      if (!res.headersSent) reject(req, res, 502, "GF_GATEWAY_UPSTREAM_UNAVAILABLE", "The VALUE API request failed.");
      else res.destroy();
    });
  }

  return { handle, sessionFile, upstreamOrigin: upstream.origin, counters };
}

/** Put the gateway in front of a server's single request listener. */
export function wrapServer(server, gateway) {
  const listeners = server.listeners("request");
  if (listeners.length !== 1) {
    throw new Error(`The UI server must have exactly one request listener, found ${listeners.length}; refusing to start without the VALUE gateway.`);
  }
  const [inner] = listeners;
  server.removeListener("request", inner);
  server.on("request", (req, res) => gateway.handle(req, res, inner));
  return server;
}
