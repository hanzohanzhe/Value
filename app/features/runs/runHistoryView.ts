// Run history presentation (four-role report R-D2, S-D12, M2-N1, R-D12;
// round R1-5). Pure view logic: every value comes from the Run record.
import { RUN_SCOPE_LABELS } from "../workspace/runScope.ts";
import type { ModelRun, RunMode } from "./types";

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
  return [scopeLabel(run.mode), run.status, runStartedText(run), runIdSuffix(run.id)].filter(Boolean).join(" · ");
}

/** R-D2: the empty choice of the Run selector; "No runs yet" only when there are none. */
export function runSelectPlaceholder(runCount: number): string {
  return runCount ? `Choose a Run (${runCount})` : "No runs yet for this Study";
}

/** R-D2 / S-D12: what the results panel says when no Run is selected. */
export function runHistoryEmpty(runCount: number, launching: boolean): { title: string; body: string } {
  if (launching) return { title: "Starting the Run…", body: "VALUE is checking the Study's readiness. The Run appears in Run history as soon as it is created; its inputs are then frozen in the background." };
  if (runCount) return { title: `${runCount} ${runCount === 1 ? "Run" : "Runs"} for this Study`, body: "Choose one in Run history to see its progress and results." };
  return { title: "No runs yet", body: "Choose a saved study, check its inputs and start with two full years." };
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
  const which = `The ${scopeLabel(started.mode)} Run ${runIdSuffix(started.runId)}`;
  if (run.status === "completed") return `${which} has completed. Its results are under Run history.`;
  if (run.status === "failed") return `${which} failed${run.error_code ? ` (${run.error_code})` : ""}. The reason is shown under Run history.`;
  if (run.status === "cancelled") return `${which} was cancelled.`;
  return `${which} is ${String(run.status).replaceAll("_", " ")}.`;
}

/**
 * R-D12: the evidence line of one module slot. A finished Run that recorded no
 * call does not say "pending"; the one-day lesson clears the market only, so
 * its other slots were not called in this scope.
 */
export function moduleEvidenceText(run: Pick<ModelRun, "mode" | "status">, slot: string, actions: number | undefined): string {
  if (actions !== undefined) return `${actions} recorded calls`;
  if (isActiveRunStatus(run.status)) return "Evidence pending";
  if (run.mode === "value_101_day" && slot !== "psm") return "Not called in this scope";
  return "No calls recorded";
}

/**
 * S-D10 / O-1, A24-5: what happens while a start request is answered. The
 * request only checks readiness and creates the Run; the inputs and the
 * execution environment are frozen afterwards in the background, with their
 * progress on the Run (preparationProgressText).
 */
export const RUN_FREEZE_NOTE = "VALUE is checking the Study's readiness and creating the Run. The Run is listed at once; its inputs and execution environment are then frozen in the background, and other pages stay usable.";
/**
 * L-4 (rounds R2, R3): the same start seen from VALUE 101. Learn opens the Run
 * when it is listed if the reader is still on Learn (startRun in app/page.tsx).
 */
export const LEARN_RUN_FREEZE_NOTE = "Starting the Run: VALUE checks the Study's readiness and lists the Run, then freezes its inputs in the background. If you stay on this page, the Run opens when it is listed; its preparation is also shown here.";
export const SNAPSHOTTING_NOTE = "The first Run in a new data folder archives the Python runtime once (about 3 minutes); later Runs freeze their inputs in under a minute.";

/** "42 s", "1 min 05 s", "1 h 02 min" (A24-5 elapsed time). */
export function formatElapsed(seconds: number | null | undefined): string | null {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return null;
  const whole = Math.floor(seconds);
  if (whole < 60) return `${whole} s`;
  if (whole < 3600) return `${Math.floor(whole / 60)} min ${String(whole % 60).padStart(2, "0")} s`;
  return `${Math.floor(whole / 3600)} h ${String(Math.floor((whole % 3600) / 60)).padStart(2, "0")} min`;
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
  const step = preparation.stage_index && preparation.stage_count ? `step ${preparation.stage_index} of ${preparation.stage_count}: ` : "";
  const elapsed = formatElapsed(preparation.elapsed_seconds);
  const parts = [`Preparing · ${step}${preparation.stage_label ?? "Freezing the Run's inputs"}`];
  if (elapsed) parts.push(`${elapsed} elapsed`);
  const text = parts.join(" · ");
  return run.status === "cancel_requested" ? `${text}. Cancellation requested: the Run stops before its model worker starts.` : text;
}
