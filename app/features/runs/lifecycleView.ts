// Run lifecycle states the Runs page explains (P0-3 S8; spec 5).
import type { ModelRun } from "./types.ts";

export type LifecycleNotice =
  | { kind: "worker_exited"; title: string; body: string; canResume: boolean; resumeBlockedReason: string | null }
  | { kind: "worker_lost"; title: string; body: string; canMarkLost: boolean };

const ACTIVE = new Set(["queued", "snapshotting", "running", "cancel_requested"]);

/** The notice for a Run whose worker stopped or cannot be reached, or null. */
export function lifecycleNotice(run: Pick<ModelRun, "status" | "error_code" | "worker_liveness" | "recovery" | "source_study_status">): LifecycleNotice | null {
  if (run.status === "failed" && (run.error_code === "GF_WORKER_EXITED" || run.error_code === "GF_WORKER_LOST" || run.error_code === "GF_WORKER_MARKED_LOST")) {
    const checkpoint = run.recovery?.latest_safe_point;
    const sourceBlocked = run.source_study_status === "trash" || run.source_study_status === "missing";
    const resumeBlockedReason = sourceBlocked
      ? "Resume needs the source Study; restore it first."
      : checkpoint && !checkpoint.available ? "No verified annual checkpoint exists yet, so the Run would restart from its first year." : null;
    return {
      kind: "worker_exited",
      title: run.error_code === "GF_WORKER_EXITED" ? "Run stopped unexpectedly (worker exited)" : "Run stopped: VALUE lost its worker",
      body: run.error_code === "GF_WORKER_EXITED"
        ? "Run stopped unexpectedly (worker exited). You can resume from the last annual checkpoint."
        : "The Run's worker is no longer running. You can resume from the last annual checkpoint.",
      canResume: !sourceBlocked,
      resumeBlockedReason,
    };
  }
  if (ACTIVE.has(run.status) && (run.worker_liveness === "lost" || run.worker_liveness === "unverifiable")) {
    return {
      kind: "worker_lost",
      title: "VALUE lost contact with this Run's worker",
      body: run.worker_liveness === "lost"
        ? "VALUE lost contact with this Run's worker (for example after a restart)."
        : "VALUE cannot verify this Run's worker on this platform (for example after a restart).",
      canMarkLost: true,
    };
  }
  return null;
}
