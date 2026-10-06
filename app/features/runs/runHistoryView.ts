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
  if (launching) return { title: "Starting the Run…", body: "VALUE is freezing the Study's inputs and execution environment. The Run appears in Run history as soon as they are frozen." };
  if (runCount) return { title: `${runCount} ${runCount === 1 ? "Run" : "Runs"} for this Study`, body: "Choose one in Run history to see its progress and results." };
  return { title: "No runs yet", body: "Choose a saved study, check its inputs and start with two full years." };
}

export type StartedRunNotice = { runId: string; mode: RunMode; text: string };

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
 * S-D10 / O-1: why starting a Run can take minutes. Starting freezes the
 * Study's inputs and archives the execution environment before the Run is
 * listed; the first Run in a new data folder archives the Python runtime.
 */
export const RUN_FREEZE_NOTE = "VALUE is freezing the Study's inputs and execution environment before the Run is listed. The first Run in a new data folder also archives the Python runtime once (about 3 minutes); later Runs take under a minute. Other pages stay usable; you are not taken back here when it finishes.";
export const SNAPSHOTTING_NOTE = "The first Run in a new data folder archives the Python runtime once (about 3 minutes); later Runs freeze their inputs in under a minute.";
