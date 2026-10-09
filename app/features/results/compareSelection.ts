// Compare: the selected Runs and the reference Run (P1 spec 6.6, EM-低1).
//
// The backend measures every annual delta against the first Run of the
// request (gridform_core/results_summary.compare_run_summaries), so the
// reference Run is sent first. The page keeps the selection in its URL:
// /compare?runs=a,b,c&ref=a. Pure functions only.

export type CompareRun = { id: string; project_id?: string; created_at?: string | null };
export type CompareStudy = { id: string; derivation?: { source_study_id?: string } | null };

/** At most this many Runs are compared at once (the picker's limit). */
export const MAX_COMPARED_RUNS = 6;

const ID = /^[^\s,/\u0000-\u001f]{1,256}$/;

/** The Run IDs and the reference a /compare URL names (unknown text dropped, duplicates removed). */
export function readCompareQuery(search: string): { runs: string[]; ref: string } {
  const params = new URLSearchParams(search);
  const runs: string[] = [];
  for (const id of (params.get("runs") ?? "").split(",")) {
    const value = id.trim();
    if (value && ID.test(value) && !runs.includes(value)) runs.push(value);
  }
  const ref = (params.get("ref") ?? "").trim();
  return { runs: runs.slice(0, MAX_COMPARED_RUNS), ref: ID.test(ref) && runs.includes(ref) ? ref : "" };
}

/** The page's own query values for a selection (null removes the key). */
export function compareQueryValues(runs: readonly string[], ref: string): { runs: string | null; ref: string | null } {
  return { runs: runs.length ? runs.join(",") : null, ref: ref && runs.includes(ref) ? ref : null };
}

/** Milliseconds of a Run's creation: `created_at`, else the timestamp in its ID ("…-20261008-135051-b5a998bb"), else null. */
export function runCreatedMs(run: CompareRun): number | null {
  if (run.created_at) {
    const parsed = Date.parse(run.created_at);
    if (Number.isFinite(parsed)) return parsed;
  }
  const match = /-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-[0-9a-f]+$/.exec(run.id);
  if (!match) return null;
  const [, year, month, day, hour, minute, second] = match.map(Number);
  return Date.UTC(year, month - 1, day, hour, minute, second);
}

/**
 * The default reference among the selected Runs: the earliest-created Run of a
 * baseline Study (a Study another selected Run's Study was derived from), else
 * the earliest-created selected Run. Runs without any creation time keep the
 * order in which they were ticked (the first ticked wins), as before.
 */
export function defaultReferenceRun(selected: readonly string[], runs: readonly CompareRun[], studies: readonly CompareStudy[] = []): string {
  const chosen = selected.map((id) => runs.find((run) => run.id === id)).filter((run): run is CompareRun => Boolean(run));
  if (!chosen.length) return selected[0] ?? "";
  const studyOf = new Map(studies.map((study) => [study.id, study]));
  const sources = new Set(chosen.map((run) => studyOf.get(run.project_id ?? "")?.derivation?.source_study_id).filter((id): id is string => Boolean(id)));
  const baseline = chosen.filter((run) => run.project_id && sources.has(run.project_id));
  const pool = baseline.length ? baseline : chosen;
  const order = new Map(selected.map((id, index) => [id, index]));
  const sorted = [...pool].sort((a, b) => {
    const ta = runCreatedMs(a); const tb = runCreatedMs(b);
    if (ta != null && tb != null && ta !== tb) return ta - tb;
    if (ta != null && tb == null) return -1;
    if (ta == null && tb != null) return 1;
    return (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0);
  });
  return sorted[0].id;
}

/** The reference: the one asked for while it is selected, else the default. */
export function effectiveReference(requested: string, selected: readonly string[], runs: readonly CompareRun[], studies: readonly CompareStudy[] = []): string {
  return requested && selected.includes(requested) ? requested : defaultReferenceRun(selected, runs, studies);
}

/** The Run IDs in request order: the reference first, then the others as ticked. */
export function referenceFirst(selected: readonly string[], reference: string): string[] {
  if (!reference || !selected.includes(reference)) return [...selected];
  return [reference, ...selected.filter((id) => id !== reference)];
}

/**
 * The backend comparison CSV with the reference Run named in its header block
 * (a `reference_run_id,<id>` row after `schema_version`). The CSV's rows are
 * values per Run; the reference says which Run the page's deltas are measured
 * against.
 */
export function csvWithReference(csv: string, reference: string): string {
  const text = csv.replace(/^﻿/, "");
  const newline = text.includes("\r\n") ? "\r\n" : "\n";
  const row = `reference_run_id,${/[",\r\n]/.test(reference) ? `"${reference.replaceAll("\"", "\"\"")}"` : reference}`;
  const lines = text.split(newline);
  const at = lines.findIndex((line) => line.startsWith("schema_version,"));
  lines.splice(at >= 0 ? at + 1 : 0, 0, row);
  return lines.join(newline);
}
