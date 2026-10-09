// Module quarantine panel logic (P0-2 S9; spec 6). Plain JavaScript so that
// node --test reads it directly; the TSX panel renders what this returns.
// P1 W4b (spec 3): the wording comes from the dictionaries (modules.*); every
// text function takes the page's translate function and defaults to English.
import { translator } from "../../i18n/index.ts";

const ENGLISH = translator("en");

export const INSTALL_RECORD_INVALID = "GF_MODULE_INSTALL_RECORD_INVALID";
export const RUNS_PENDING = "GF_MODULE_LIFECYCLE_RUNS_PENDING";

// Absolute paths never reach the page, even if a message slipped past the
// backend's own redaction (spec 6).
const ABSOLUTE_PATH = /(?:[A-Za-z]:\\[^\s"'`]+|\/(?:home|Users|root|tmp|var|opt|mnt|private)\/[^\s"'`]+)/g;

export function sanitizeMessage(text) {
  return String(text ?? "").replace(ABSOLUTE_PATH, "<path>");
}

export function quarantineTitle(count, rows, t = ENGLISH) {
  // R4 M-低4: an extension-only quarantine is not called a module.
  const kinds = new Set((rows ?? []).map((row) => row.kind));
  const key = kinds.size === 1 && kinds.has("extension") ? "modules.quarantine.titleExtensions"
    : kinds.size > 1 ? "modules.quarantine.titleMixed" : "modules.quarantine.titleModules";
  return t(key, { count });
}

/** R4 M-低4: the panel sentence agrees with the number of entries. */
export function quarantineIntro(count, t = ENGLISH) {
  return t("modules.quarantine.intro", { count });
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
      label: [id ?? sanitizeMessage(entry.manifest_file ?? ENGLISH("modules.quarantine.unnamedManifest")), entry.version].filter(Boolean).join(" "),
      errorCode: entry.error_code ?? "GF_MODULE_QUARANTINED",
      firstLine,
      details: rest.join("\n").trim(),
      canDisable,
      correctiveAction: sanitizeMessage(entry.corrective_action ?? ""),
      disablePath: canDisable ? `/api/${kind === "extension" ? "extensions" : "modules"}/${encodeURIComponent(id)}/disable` : null,
    };
  });
}

export function disableConfirmation(id, kind = "module", t = ENGLISH) {
  // R5 F-低1: a Study does not swap an extension for another one; it deselects it.
  return t(kind === "extension" ? "modules.confirm.disableExtension" : "modules.confirm.disableModule", { id });
}

/** A lifecycle change refused because Runs have not finished: ask, then resend with confirmation. */
export function isPendingRunsRefusal(status, code) {
  return status === 409 && code === RUNS_PENDING;
}

export function pendingRunsQuestion(message, noun = "modules", t = ENGLISH) {
  // R4 F-低5: an extension change is not called a module change.
  const question = t(noun === "extensions" ? "modules.confirm.pendingRunsExtensions" : "modules.confirm.pendingRunsModules");
  return `${message || t("modules.confirm.runsNotFinished")}\n\n${question}`;
}

/** R6-1 (EM-中1): the queued Runs a confirmed lifecycle change stopped
 * (GF_RUN_EXECUTION_IDENTITY_CHANGED), appended to the success notice. */
export function stoppedRunsNotice(payload, t = ENGLISH) {
  const runs = Array.isArray(payload?.stopped_unstarted_runs) ? payload.stopped_unstarted_runs.filter((id) => typeof id === "string" && id) : [];
  if (!runs.length) return "";
  const shown = runs.slice(0, 10).join(", ") + (runs.length > 10 ? ", …" : "");
  return ` ${t("modules.notice.stoppedRuns", { count: runs.length, runs: shown })}`;
}
