// The header's data-pack pill (F2-N3, round R1-5; R3M-2, round R2).
// "Inputs not loaded" means the workspace itself could not be read. A degraded
// /api/health (for example one quarantined module) does not hide the pack's
// inputs: the workspace still loaded and its counts are current.

export type PillPack = { complete: boolean; valid_required_count: number; required_count: number };

export function baseInputsPill(workspaceAvailable: boolean, pack: PillPack | null | undefined): { text: string; tone: "good" | "warn" } {
  if (!workspaceAvailable) return { text: "Inputs not loaded", tone: "warn" };
  if (!pack) return { text: "No data pack", tone: "warn" };
  return { text: `${pack.valid_required_count} of ${pack.required_count} base inputs ready`, tone: pack.complete ? "good" : "warn" };
}
