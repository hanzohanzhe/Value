/** Start the pinned Vinext production server with a Windows asset-path fix.
 *
 * Vinext 0.0.50 builds its static-file cache from `path.relative()`. On
 * Windows that returns backslashes, while browser URLs use forward slashes,
 * so otherwise every hashed `/assets/*` request is a 404. The workaround is
 * deliberately local to server startup and can be deleted after the pinned
 * Vinext version includes the upstream fix.
 */
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

function argument(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const host = argument("--host", argument("--hostname", "127.0.0.1"));
const port = Number.parseInt(argument("--port", "8800"), 10);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("--port must be between 1 and 65535");

const root = path.resolve(import.meta.dirname, "..");
const serverModule = path.join(root, "node_modules", "vinext", "dist", "server", "prod-server.js");
const originalRelative = path.relative;
if (process.platform === "win32") {
  path.relative = (...values) => originalRelative(...values).replaceAll(path.sep, "/");
}

try {
  const { startProdServer } = await import(pathToFileURL(serverModule).href);
  await startProdServer({ host, port, outDir: path.join(root, "dist") });
} finally {
  path.relative = originalRelative;
}
