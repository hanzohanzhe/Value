// R4 M-中3: what a Study derivation did beyond creating the new Study. The
// backend appends a code-only revision of the source first (Q13) and starts
// from the current module graph when the stored one is stale; both are said.

type SourceMigration = { revision_number?: number | null; revision_reason?: string | null };
type GraphDrift = { differences?: { slot?: string | null; module_id?: string | null; field?: string }[] };

export function derivationNotes(response: unknown): string[] {
  if (!response || typeof response !== "object") return [];
  const record = response as { source_migration?: SourceMigration | null; source_graph_drift?: GraphDrift | null };
  const notes: string[] = [];
  const migration = record.source_migration;
  if (migration && typeof migration === "object") {
    const number = typeof migration.revision_number === "number" ? ` as revision ${migration.revision_number}` : "";
    const why = migration.revision_reason === "source-reidentify"
      ? "installed local code was edited in place"
      : "code-only change, no confirmation needed";
    notes.push(`The source Study was first re-identified${number} (${why}).`);
  }
  const drift = record.source_graph_drift;
  if (drift && typeof drift === "object") {
    const names = [...new Set((drift.differences ?? []).map((row) => row.module_id ? `${row.slot ?? "module"} ${row.module_id}` : row.field ?? "module graph"))];
    notes.push(`The source's module code changed since its revision was saved (${names.join(", ") || "module graph"}). For a one-change comparison, compare with a new Run of the source Study.`);
  }
  return notes;
}
