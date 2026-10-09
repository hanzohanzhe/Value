// Run lifecycle states the Runs page explains (P0-3 S8; spec 5).
import type { ModelRun } from "./types.ts";
import { tr } from "../../i18n/index.ts";

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
      ? tr("lifecycle.resumeNeedsStudy")
      : checkpoint && !checkpoint.available ? tr("lifecycle.noCheckpoint") : null;
    return {
      kind: "worker_exited",
      title: tr(run.error_code === "GF_WORKER_EXITED" ? "lifecycle.exitedTitle" : "lifecycle.lostTitle"),
      body: tr(run.error_code === "GF_WORKER_EXITED" ? "lifecycle.exitedBody" : "lifecycle.lostBody"),
      canResume: !sourceBlocked,
      resumeBlockedReason,
    };
  }
  if (ACTIVE.has(run.status) && (run.worker_liveness === "lost" || run.worker_liveness === "unverifiable")) {
    return {
      kind: "worker_lost",
      title: tr("lifecycle.contactTitle"),
      body: tr(run.worker_liveness === "lost" ? "lifecycle.contactLost" : "lifecycle.contactUnverifiable"),
      canMarkLost: true,
    };
  }
  return null;
}
