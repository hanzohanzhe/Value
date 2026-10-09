// R4 M-中3: what a Study derivation did beyond creating the new Study. The
// backend appends a code-only revision of the source first (Q13) and starts
// from the current module graph when the stored one is stale; both are said.
// P1 W4b: the sentences come from the dictionaries (English by default).
import { translator, type Translate } from "../../i18n/index.ts";

const ENGLISH = translator("en");

type SourceMigration = { revision_number?: number | null; revision_reason?: string | null };
type GraphDrift = { differences?: { slot?: string | null; module_id?: string | null; field?: string }[] };

export function derivationNotes(response: unknown, t: Translate = ENGLISH): string[] {
  if (!response || typeof response !== "object") return [];
  const record = response as { source_migration?: SourceMigration | null; source_graph_drift?: GraphDrift | null };
  const notes: string[] = [];
  const migration = record.source_migration;
  if (migration && typeof migration === "object") {
    const why = migration.revision_reason === "source-reidentify" ? t("modules.notice.whyEditedInPlace") : t("modules.notice.whyCodeOnly");
    notes.push(t("modules.notice.sourceReidentified", { number: typeof migration.revision_number === "number" ? migration.revision_number : -1, why }));
  }
  const drift = record.source_graph_drift;
  if (drift && typeof drift === "object") {
    const names = [...new Set((drift.differences ?? []).map((row) => row.module_id ? `${row.slot ?? "module"} ${row.module_id}` : row.field ?? t("modules.notice.moduleGraph")))];
    notes.push(t("modules.notice.sourceGraphDrift", { names: names.join(", ") || t("modules.notice.moduleGraph") }));
  }
  return notes;
}
