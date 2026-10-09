// The header's data-pack pill (F2-N3, round R1-5; R3M-2, round R2).
// "Inputs not loaded" means the workspace itself could not be read. A degraded
// /api/health (for example one quarantined module) does not hide the pack's
// inputs: the workspace still loaded and its counts are current.
// The text comes from the dictionaries (P1 spec 3); English by default.
import { translator, type Translate } from "../../i18n/index.ts";

export type PillPack = { complete: boolean; valid_required_count: number; required_count: number };

const english = translator("en");

export function baseInputsPill(workspaceAvailable: boolean, pack: PillPack | null | undefined, t: Translate = english): { text: string; tone: "good" | "warn" } {
  if (!workspaceAvailable) return { text: t("header.pill.notLoaded"), tone: "warn" };
  if (!pack) return { text: t("header.pill.noPack"), tone: "warn" };
  return { text: t("header.pill.ready", { valid: pack.valid_required_count, required: pack.required_count }), tone: pack.complete ? "good" : "warn" };
}
