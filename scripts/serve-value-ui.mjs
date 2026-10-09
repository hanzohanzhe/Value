/** Start the pinned Vinext production server behind the VALUE gateway.
 *
 *   node scripts/serve-value-ui.mjs --host 127.0.0.1 --port 8800 [--api-origin http://127.0.0.1:8766]
 *
 * The browser talks only to this origin.  scripts/value-ui-gateway.mjs checks
 * the Host header, adds the security headers and the per-request CSP nonce,
 * and forwards /api/* to the local API with the session token it reads from
 * <VALUE_DATA_HOME>/runtime/api-session-<api port>.json (P0-1).  The token is
 * never passed on the command line.  `--session-optional` (archived
 * workspaces only) forwards without a token when the archived backend
 * predates API sessions.
 *
 * Windows asset-path fix: Vinext builds its static-file cache from
 * `path.relative()`. On Windows that returns backslashes, while browser URLs
 * use forward slashes, so otherwise every hashed `/assets/*` request is a 404.
 * The workaround is deliberately local to server startup.
 */
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import { createGateway, validateBindHost, wrapServer } from "./value-ui-gateway.mjs";

function argument(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const host = validateBindHost(argument("--host", argument("--hostname", "127.0.0.1")));
const port = Number.parseInt(argument("--port", "8800"), 10);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("--port must be between 1 and 65535");
const upstreamOrigin = argument("--api-origin", "http://127.0.0.1:8766");
const gateway = createGateway({ upstreamOrigin, sessionOptional: process.argv.includes("--session-optional") });

const root = path.resolve(import.meta.dirname, "..");
const serverModule = path.join(root, "node_modules", "vinext", "dist", "server", "prod-server.js");
const originalRelative = path.relative;
if (process.platform === "win32") {
  path.relative = (...values) => originalRelative(...values).replaceAll(path.sep, "/");
}

try {
  const { startProdServer } = await import(pathToFileURL(serverModule).href);
  const started = await startProdServer({ host, port, outDir: path.join(root, "dist") });
  // Same macrotask as vinext's listen callback: no request is accepted before
  // the gateway is in place.  Refuse to run if vinext's listener layout changed.
  wrapServer(started.server, gateway);
  console.log(`VALUE UI gateway: http://${host}:${started.port}/ -> ${gateway.upstreamOrigin} (session file ${gateway.sessionFile})`);
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
} finally {
  path.relative = originalRelative;
}
