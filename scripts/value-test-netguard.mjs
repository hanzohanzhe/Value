// Node counterpart of scripts/value_test_netguard.py, preloaded by p0_gate
// through NODE_OPTIONS="--import=<this file>" for every node process it starts
// (node --test children inherit it).  Connections to a local host on the live
// VALUE ports 8766/8800 (plus VALUE_TEST_FORBIDDEN_PORTS) fail with
// ECONNREFUSED and listening on them fails with EADDRINUSE, without touching
// the network; each refused attempt is appended to VALUE_TEST_NETGUARD_LOG.
import fs from "node:fs";
import net from "node:net";

const DEFAULT_FORBIDDEN_PORTS = [8766, 8800];
const LOCAL_NAMES = new Set(["", "localhost", "ip6-localhost", "ip6-loopback", "0.0.0.0", "::", "::1", "::ffff:0.0.0.0"]);

function forbiddenPorts() {
  const extra = (process.env.VALUE_TEST_FORBIDDEN_PORTS || "")
    .split(",")
    .map((part) => Number(part.trim()))
    .filter((port) => Number.isInteger(port) && port > 0);
  return new Set([...DEFAULT_FORBIDDEN_PORTS, ...extra]);
}

function isLocalHost(host) {
  const name = String(host ?? "localhost").trim().toLowerCase().replace(/^\[|\]$/g, "");
  return LOCAL_NAMES.has(name) || name.endsWith(".localhost") || name.startsWith("127.") || name.startsWith("::ffff:127.");
}

function record(op, host, port) {
  const entry = { op, host: String(host ?? "localhost"), port, test: `node:${process.argv[1] ?? ""}`, pid: process.pid, argv0: process.argv[1] ?? "" };
  const log = process.env.VALUE_TEST_NETGUARD_LOG;
  if (log) fs.appendFileSync(log, `${JSON.stringify(entry)}\n`);
}

function target(args) {
  let options = args[0];
  if (Array.isArray(options)) options = options[0]; // already-normalised internal arguments
  if (options !== null && typeof options === "object") {
    if (options.path) return null;
    return { host: options.host ?? "localhost", port: Number(options.port) };
  }
  if (typeof options === "number" || (typeof options === "string" && /^\d+$/.test(options))) {
    return { host: typeof args[1] === "string" ? args[1] : "localhost", port: Number(options) };
  }
  return null;
}

function forbidden(args) {
  const found = target(args);
  if (!found || !forbiddenPorts().has(found.port) || !isLocalHost(found.host)) return null;
  return found;
}

const originalConnect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function guardedConnect(...args) {
  const found = forbidden(args);
  if (!found) return originalConnect.apply(this, args);
  record("connect", found.host, found.port);
  const error = Object.assign(
    new Error(`value_test_netguard: tests may not connect to the live VALUE port ${found.port} on ${found.host}`),
    { code: "ECONNREFUSED", errno: -111, syscall: "connect", address: String(found.host), port: found.port },
  );
  process.nextTick(() => this.destroy(error));
  return this;
};

const originalListen = net.Server.prototype.listen;
net.Server.prototype.listen = function guardedListen(...args) {
  const found = forbidden(args);
  if (!found) return originalListen.apply(this, args);
  record("bind", found.host, found.port);
  const error = Object.assign(
    new Error(`value_test_netguard: tests may not listen on the live VALUE port ${found.port}`),
    { code: "EADDRINUSE", errno: -98, syscall: "listen", address: String(found.host), port: found.port },
  );
  process.nextTick(() => this.emit("error", error));
  return this;
};
