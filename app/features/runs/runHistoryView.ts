// Run history presentation (four-role report R-D2, S-D12, M2-N1, R-D12;
// round R1-5). Pure view logic: every value comes from the Run record.
import { RUN_SCOPE_LABELS } from "../workspace/runScope.ts";
import { formatNumber } from "../shared/format.ts";
import { statusWord } from "../shared/labels.ts";
import type { ModelRun, ModuleEvidence, RunMode } from "./types";
import { en } from "../../i18n/en.ts";
import { tr, type MessageKey } from "../../i18n/index.ts";

type HistoryRun = Pick<ModelRun, "id" | "mode" | "status"> & { created_at?: string; error_code?: string };

const ACTIVE_STATUSES = new Set(["queued", "snapshotting", "running", "cancel_requested"]);

export function isActiveRunStatus(status: string | undefined): boolean {
  return ACTIVE_STATUSES.has(String(status ?? ""));
}

function scopeLabel(mode: RunMode | string): string {
  return RUN_SCOPE_LABELS[mode as RunMode] ?? String(mode).replaceAll("_", " ");
}

/**
 * When the Run was created, as recorded ("2026-10-06 23:17"); the local clock
 * text of `created_at` is shown as written, never converted. Older records
 * without `created_at` fall back to the timestamp inside the Run ID.
 */
export function runStartedText(run: Pick<HistoryRun, "id" | "created_at">): string | null {
  const recorded = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(run.created_at ?? "");
  if (recorded) return `${recorded[1]} ${recorded[2]}`;
  const fromId = /-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})\d{2}-[0-9a-f]+$/.exec(run.id);
  return fromId ? `${fromId[1]}-${fromId[2]}-${fromId[3]} ${fromId[4]}:${fromId[5]}` : null;
}

/** The short random suffix of a Run ID ("…-c11e26f1" → "c11e26f1"). */
export function runIdSuffix(id: string): string {
  return id.split("-").at(-1) || id;
}

/** R-D2: Runs of one Study are told apart by scope, status, start time and ID suffix. */
export function runOptionLabel(run: HistoryRun): string {
  return [scopeLabel(run.mode), statusWord(run.status), runStartedText(run), runIdSuffix(run.id)].filter(Boolean).join(" · ");
}

/** R-D2: the empty choice of the Run selector; "No runs yet" only when there are none. */
export function runSelectPlaceholder(runCount: number): string {
  return runCount ? tr("history.choose", { count: runCount }) : tr("history.none");
}

/** R-D2 / S-D12: what the results panel says when no Run is selected. */
export function runHistoryEmpty(runCount: number, launching: boolean): { title: string; body: string } {
  if (launching) return { title: tr("history.starting.title"), body: tr("history.starting.body") };
  if (runCount) return { title: tr("history.count.title", { count: runCount }), body: tr("history.count.body") };
  return { title: tr("history.empty.title"), body: tr("history.empty.body") };
}

/**
 * R4 R-低3: `studyId` and `view` bind the notice to the Study and page that
 * started the Run; elsewhere it is not shown (the background-runs button stays).
 * Older callers without them keep the notice everywhere.
 */
export type StartedRunNotice = { runId: string; mode: RunMode; text: string; studyId?: string; view?: string };

/** Whether the "has started" notice belongs on the current page and Study (R4 R-低3). */
export function startedRunNoticeVisible(started: StartedRunNotice | null, current: { view: string; studyId: string }): boolean {
  if (!started) return false;
  if (started.studyId !== undefined && started.studyId !== current.studyId) return false;
  if (started.view !== undefined && started.view !== current.view) return false;
  return true;
}

/**
 * S-D12 / M2-N1: the "has started" notice follows its Run. While the Run is
 * active (or not yet listed) it keeps the start sentence; once the Run ends it
 * says how it ended, and a failure names its error code.
 */
export function startedRunNoticeText(started: StartedRunNotice, run: HistoryRun | undefined): string {
  if (!run || isActiveRunStatus(run.status)) return started.text;
  const which = tr("history.notice.which", { scope: scopeLabel(started.mode), suffix: runIdSuffix(started.runId) });
  if (run.status === "completed") return tr("history.notice.completed", { which });
  if (run.status === "failed") return run.error_code ? tr("history.notice.failedCode", { which, code: run.error_code }) : tr("history.notice.failed", { which });
  if (run.status === "cancelled") return tr("history.notice.cancelled", { which });
  return tr("history.notice.other", { which, status: String(run.status).replaceAll("_", " ") });
}

/**
 * R-D12: the evidence line of one module slot. A finished Run that recorded no
 * call does not say "pending"; the one-day lesson clears the market only, so
 * its other slots were not called in this scope.
 */
export function moduleEvidenceText(run: Pick<ModelRun, "mode" | "status">, slot: string, actions: number | null | undefined, evidence?: ModuleEvidence, moduleId?: string): string {
  if (typeof actions === "number") return tr("history.evidence.calls", { count: actions });
  // R4 M-中1: the PSM calls the storage-cost module internally; the market
  // ledger, not a stage event, shows that it priced the storage offers.
  if (evidence?.source === "market_ledger") {
    const count = formatNumber(evidence.storage_asset_periods, 0);
    const rows = count ? tr("history.evidence.ledgerRows", { count }) : "";
    const named = evidence.ledger_module_id && moduleId && evidence.ledger_module_id !== moduleId ? tr("history.evidence.ledgerId", { id: evidence.ledger_module_id }) : "";
    return `${tr("history.evidence.ledger")}${rows}${named}`;
  }
  if (isActiveRunStatus(run.status)) return tr("history.evidence.pending");
  if (run.mode === "value_101_day" && slot !== "psm") return tr("history.evidence.notCalled");
  return tr("history.evidence.none");
}

/**
 * S-D10 / O-1, A24-5: what happens while a start request is answered. The
 * request only checks readiness and creates the Run; the inputs and the
 * execution environment are frozen afterwards in the background, with their
 * progress on the Run (preparationProgressText).
 */
export const RUN_FREEZE_NOTE = en["history.freezeNote"];
/**
 * L-4 (rounds R2, R3): the same start seen from VALUE 101. Learn opens the Run
 * when it is listed if the reader is still on Learn (startRun in app/page.tsx).
 */
export const LEARN_RUN_FREEZE_NOTE = en["history.learnFreezeNote"];
export const SNAPSHOTTING_NOTE = en["history.snapshottingNote"];
/** P1 W5: the three notes above in the interface language (the constants keep the English text). */
export function runFreezeNote(): string { return tr("history.freezeNote"); }
export function learnRunFreezeNote(): string { return tr("history.learnFreezeNote"); }
export function snapshottingNote(): string { return tr("history.snapshottingNote"); }

/** "42 s", "1 min 05 s", "1 h 02 min" (A24-5 elapsed time). */
export function formatElapsed(seconds: number | null | undefined): string | null {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return null;
  const whole = Math.floor(seconds);
  if (whole < 60) return tr("history.elapsed.seconds", { s: whole });
  if (whole < 3600) return tr("history.elapsed.minutes", { m: Math.floor(whole / 60), s: String(whole % 60).padStart(2, "0") });
  return tr("history.elapsed.hours", { h: Math.floor(whole / 3600), m: String(Math.floor((whole % 3600) / 60)).padStart(2, "0") });
}

/**
 * A24-5: the stage and elapsed time of a Run whose inputs are being frozen
 * ("Preparing · step 2 of 4: Freezing the Study's inputs · 1 min 05 s
 * elapsed"), or null when the Run is not being prepared.
 */
export function preparationProgressText(run: Pick<ModelRun, "status" | "preparation" | "persisted_status">): string | null {
  const preparation = run.preparation;
  const stored = run.status === "cancel_requested" ? run.persisted_status : run.status;
  if (!preparation || preparation.state !== "preparing" || stored !== "snapshotting") return null;
  const step = preparation.stage_index && preparation.stage_count ? tr("history.preparing.step", { index: preparation.stage_index, count: preparation.stage_count }) : "";
  const elapsed = formatElapsed(preparation.elapsed_seconds);
  // The four stages of backend/server.py RUN_PREPARATION_STAGES read in the interface language.
  const known = preparation.stage && Object.hasOwn(PREPARATION_STAGE_KEYS, preparation.stage) ? tr(PREPARATION_STAGE_KEYS[preparation.stage]) : null;
  const parts = [tr("history.preparing", { step, stage: known ?? preparation.stage_label ?? tr("history.preparing.defaultStage") })];
  if (elapsed) parts.push(tr("history.preparing.elapsed", { elapsed }));
  const text = parts.join(" · ");
  return run.status === "cancel_requested" ? tr("history.preparing.cancelled", { text }) : text;
}

const PREPARATION_STAGE_KEYS: Readonly<Record<string, MessageKey>> = {
  execution: "history.stage.execution", snapshot: "history.stage.snapshot", resources: "history.stage.resources", worker: "history.stage.worker",
};

/** A duration estimate in minutes below 90 minutes, otherwise in hours (R4 R-低8). */
function durationText(seconds: number): string {
  if (seconds < 90 * 60) return tr("history.duration.minutes", { count: Math.max(1, Math.round(seconds / 60)) });
  return tr("history.duration.hours", { count: (Math.round(seconds / 360) / 10).toFixed(1) });
}

/**
 * R4 R-低8: the readiness runtime estimate. Measured local runs give one
 * value; without them the backend gives a range (smallest to largest shipped
 * scale) and the page says it is a first estimate.
 */
export function runtimeEstimateText(estimates: { runtime_seconds?: number | null; runtime_range_seconds?: [number, number] | null }): string {
  const range = estimates.runtime_range_seconds;
  if (Array.isArray(range) && range.length === 2 && range.every((value) => typeof value === "number" && Number.isFinite(value))) {
    const [low, high] = range;
    const lowText = durationText(low); const highText = durationText(high);
    return lowText === highText ? tr("history.runtime.aboutFirst", { duration: lowText }) : tr("history.runtime.range", { low: lowText, high: highText });
  }
  if (typeof estimates.runtime_seconds !== "number" || !Number.isFinite(estimates.runtime_seconds)) return tr("history.runtime.none");
  return tr("history.runtime.about", { duration: durationText(estimates.runtime_seconds) });
}
