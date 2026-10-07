// Module quarantine panel logic (P0-2 S9; spec 6). Plain JavaScript so that
// node --test reads it directly; the TSX panel renders what this returns.

export const INSTALL_RECORD_INVALID = "GF_MODULE_INSTALL_RECORD_INVALID";
export const RUNS_PENDING = "GF_MODULE_LIFECYCLE_RUNS_PENDING";

// Absolute paths never reach the page, even if a message slipped past the
// backend's own redaction (spec 6).
const ABSOLUTE_PATH = /(?:[A-Za-z]:\\[^\s"'`]+|\/(?:home|Users|root|tmp|var|opt|mnt|private)\/[^\s"'`]+)/g;

export function sanitizeMessage(text) {
  return String(text ?? "").replace(ABSOLUTE_PATH, "<path>");
}

export function quarantineTitle(count, rows) {
  // R4 M-低4: an extension-only quarantine is not called a module.
  const kinds = new Set((rows ?? []).map((row) => row.kind));
  const noun = kinds.size === 1 && kinds.has("extension")
    ? (count === 1 ? "extension" : "extensions")
    : kinds.size > 1 ? (count === 1 ? "module or extension" : "modules and extensions")
      : (count === 1 ? "module" : "modules");
  return `${count} external ${noun} quarantined`;
}

/** R4 M-低4: the panel sentence agrees with the number of entries. */
export function quarantineIntro(count) {
  return count === 1
    ? "VALUE started without it. Runs that need it cannot start until it is fixed or disabled."
    : "VALUE started without them. Runs that need them cannot start until they are fixed or disabled.";
}

/** Rows of the panel from the backend's value.module-quarantine/v1 report. */
export function quarantineRows(report) {
  const entries = Array.isArray(report?.entries) ? report.entries : [];
  const seen = new Map();
  for (const entry of entries) {
    const key = `${entry?.kind === "extension" ? "extension" : "module"}:${entry?.id ?? ""}`;
    seen.set(key, (seen.get(key) ?? 0) + 1);
  }
  return entries.map((entry, index) => {
    const message = sanitizeMessage(entry.message || entry.error_type || entry.error_code || "Quarantined");
    const [firstLine, ...rest] = message.split(/\r?\n/);
    const kind = entry.kind === "extension" ? "extension" : "module";
    const id = typeof entry.id === "string" && entry.id ? entry.id : null;
    const canDisable = Boolean(id) && entry.error_code !== INSTALL_RECORD_INVALID;
    const manifestFile = entry.manifest_file ? sanitizeMessage(entry.manifest_file) : null;
    return {
      key: `${kind}:${id ?? entry.manifest_file ?? index}`,
      // R4 M-低4: two manifests with one ID are two rows, told apart by their file.
      rowKey: `${kind}:${id ?? ""}:${entry.manifest_file ?? index}`,
      manifestFile,
      sharedId: Boolean(id) && (seen.get(`${kind}:${id}`) ?? 0) > 1,
      kind,
      id,
      label: [id ?? sanitizeMessage(entry.manifest_file ?? "unnamed manifest"), entry.version].filter(Boolean).join(" "),
      errorCode: entry.error_code ?? "GF_MODULE_QUARANTINED",
      firstLine,
      details: rest.join("\n").trim(),
      canDisable,
      correctiveAction: sanitizeMessage(entry.corrective_action ?? ""),
      disablePath: canDisable ? `/api/${kind === "extension" ? "extensions" : "modules"}/${encodeURIComponent(id)}/disable` : null,
    };
  });
}

export function disableConfirmation(id) {
  return `Disable ${id}? Studies that use it will need another module before they can run.`;
}

/** A lifecycle change refused because Runs have not finished: ask, then resend with confirmation. */
export function isPendingRunsRefusal(status, code) {
  return status === 409 && code === RUNS_PENDING;
}

export function pendingRunsQuestion(message, noun = "modules") {
  // R4 F-低5: an extension change is not called a module change.
  return `${message || "Runs have not finished."}\n\nChange the installed ${noun} anyway?`;
}
