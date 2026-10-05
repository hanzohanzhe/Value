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

export function quarantineTitle(count) {
  return count === 1 ? "1 external module quarantined" : `${count} external modules quarantined`;
}

/** Rows of the panel from the backend's value.module-quarantine/v1 report. */
export function quarantineRows(report) {
  const entries = Array.isArray(report?.entries) ? report.entries : [];
  return entries.map((entry, index) => {
    const message = sanitizeMessage(entry.message || entry.error_type || entry.error_code || "Quarantined");
    const [firstLine, ...rest] = message.split(/\r?\n/);
    const kind = entry.kind === "extension" ? "extension" : "module";
    const id = typeof entry.id === "string" && entry.id ? entry.id : null;
    const canDisable = Boolean(id) && entry.error_code !== INSTALL_RECORD_INVALID;
    return {
      key: `${kind}:${id ?? entry.manifest_file ?? index}`,
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

export function pendingRunsQuestion(message) {
  return `${message || "Runs have not finished."}\n\nChange the installed modules anyway?`;
}
