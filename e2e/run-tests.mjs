import { spawnSync } from "node:child_process";
import path from "node:path";
import process from "node:process";

const root = path.resolve(import.meta.dirname, "..");
const environment = {
  ...process.env,
  NEXT_PUBLIC_VALUE_API_ORIGIN: "http://127.0.0.1:18766",
};
const vinext = path.join(root, "node_modules", "vinext", "dist", "cli.js");
let result = spawnSync(process.execPath, [vinext, "build"], { cwd: root, env: environment, stdio: "inherit" });
if (result.status !== 0) process.exit(result.status ?? 1);
result = spawnSync(process.execPath, [path.join(root, "node_modules", "@playwright", "test", "cli.js"), "test"], { cwd: root, env: environment, stdio: "inherit" });
process.exit(result.status ?? 1);
