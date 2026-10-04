import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";

const root = path.resolve(import.meta.dirname, "..");
const state = fs.mkdtempSync(path.join(os.tmpdir(), "force-browser-e2e-"));
const packs = path.join(state, "data-packs");
const modules = path.join(state, "modules");
fs.mkdirSync(packs, { recursive: true });
fs.mkdirSync(modules, { recursive: true });
fs.cpSync(path.join(root, "data-packs", "value-synthetic-contract-pack-v1"), path.join(packs, "value-synthetic-contract-pack-v1"), { recursive: true });
fs.cpSync(path.join(root, "data-packs", "force-castle-101-v1"), path.join(packs, "force-castle-101-v1"), { recursive: true });
fs.cpSync(path.join(root, "examples", "external_modules", "manifests"), modules, { recursive: true });
// Repository examples are deliberately marked `fixture` so that they never
// appear as user-selectable scientific modules in a normal installation.
// The isolated browser-test workspace explicitly promotes those copies to
// `ready`, proving the external registry path without altering shipped files.
for (const entry of fs.readdirSync(modules, { withFileTypes: true })) {
  if (!entry.isFile() || !entry.name.endsWith(".json")) continue;
  const manifestPath = path.join(modules, entry.name);
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  if (manifest.status === "fixture") {
    manifest.status = "ready";
    fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  }
}

const environment = { ...process.env, VALUE_DATA_HOME: state, PYTHONUTF8: "1" };
let pythonCommand;
let pythonArgs;
if (process.env.VALUE_PYTHON) {
  pythonCommand = process.env.VALUE_PYTHON;
  pythonArgs = ["-m", "backend.server", "--host", "127.0.0.1", "--port", "18766"];
} else if (process.platform === "win32") {
  const candidates = [
    path.join(root, ".venv", "Scripts", "python.exe"),
    process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, "Programs", "Python", "Python310", "python.exe")
      : "",
  ].filter(Boolean);
  const managed = candidates.find((candidate) => fs.existsSync(candidate));
  if (managed) {
    pythonCommand = managed;
    pythonArgs = ["-m", "backend.server", "--host", "127.0.0.1", "--port", "18766"];
  } else {
    pythonCommand = "py";
    pythonArgs = ["-3.10", "-m", "backend.server", "--host", "127.0.0.1", "--port", "18766"];
  }
} else {
  pythonCommand = "python";
  pythonArgs = ["-m", "backend.server", "--host", "127.0.0.1", "--port", "18766"];
}
const children = [
  ...(process.env.VALUE_E2E_UI_ONLY === "1" ? [] : [
    spawn(pythonCommand, pythonArgs, { cwd: root, env: environment, stdio: ["ignore", "pipe", "pipe"], windowsHide: true }),
  ]),
  spawn(process.execPath, [path.join(root, "scripts", "serve-value-ui.mjs"), "--host", "127.0.0.1", "--port", "18800"], { cwd: root, env: environment, stdio: ["ignore", "pipe", "pipe"], windowsHide: true }),
];
let stopping = false;
for (const child of children) {
  child.stderr.on("data", (chunk) => process.stderr.write(chunk));
  child.on("exit", (code) => { if (!stopping && code !== 0) process.exitCode = code ?? 1; });
}

async function ready(url) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try { if ((await fetch(url)).ok) return; } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for ${url}`);
}
await Promise.all([
  ...(process.env.VALUE_E2E_UI_ONLY === "1" ? [] : [ready("http://127.0.0.1:18766/api/health")]),
  ready("http://127.0.0.1:18800/"),
]);
console.log(`VALUE_E2E_READY state=${state}`);

function cleanup() {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.killed || child.exitCode !== null || child.pid === undefined) continue;
    if (process.platform === "win32") {
      // The venv launcher starts the base Python interpreter as a child. Killing
      // only the launcher can leave the API bound to the prior temporary state.
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
        windowsHide: true,
      });
    } else {
      child.kill();
    }
  }
  setTimeout(() => {
    try { fs.rmSync(state, { recursive: true, force: true }); } catch {}
    process.exit(0);
  }, 500);
}
process.on("SIGINT", cleanup);
process.on("SIGTERM", cleanup);
await new Promise(() => {});
