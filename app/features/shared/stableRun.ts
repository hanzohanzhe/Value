// R5 R-低1: a Run object is replaced on every workspace poll. Pages that load
// evidence for a Run depend on this stable copy instead, so they reload when
// the Run's identity, status or completed years change, not on every poll
// (a preparing Run otherwise re-requested market capabilities every 2 s and
// logged a 404 each time).
import { useState } from "react";

type RunLike = { id: string; status?: string | null; completed_years?: number | null };

/** The fields whose change can change a Run's evidence; "" without a Run. */
export function runEvidenceKey(run: RunLike | null | undefined): string {
  return run ? `${run.id}|${run.status ?? ""}|${run.completed_years ?? ""}` : "";
}

/** True while a Run is still freezing its inputs: it has no market evidence yet. */
export function runPreparing(run: Pick<RunLike, "status"> | null | undefined): boolean {
  return run?.status === "queued" || run?.status === "snapshotting";
}

/** The same Run object for as long as its evidence key is unchanged. */
export function useStableRun<T extends RunLike>(run: T | undefined): T | undefined {
  const key = runEvidenceKey(run);
  const [held, setHeld] = useState<{ key: string; run: T | undefined }>({ key, run });
  if (held.key !== key) {
    setHeld({ key, run });
    return run;
  }
  return held.run;
}
