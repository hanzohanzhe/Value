// Wording from the dictionaries (studies.trashConfirm.*); English by default.
import { translator, tr, type Translate } from "../../i18n/index.ts";

export type SourceStudyStatus = "active" | "trash" | "missing";

const english = translator("en");

export function buildStudyTrashConfirmation(
  study: { id: string; name: string },
  linkedRunCount: number,
  t: Translate = english,
) {
  if (linkedRunCount > 0) {
    return {
      requiresExactName: true,
      expected: study.name,
      message: t("studies.trashConfirm.withRuns", { count: linkedRunCount, name: study.name }),
    };
  }
  return {
    requiresExactName: false,
    expected: study.name,
    message: t("studies.trashConfirm.plain", { name: study.name }),
  };
}

export function sourceStudyAllowsDerivedRun(status?: SourceStudyStatus) {
  return status === undefined || status === "active";
}

export function networkPackReadinessLabel(
  readiness?: { status?: string; network_pack_id?: unknown },
) {
  if (!readiness) return tr("readinessLine.networkCheck");
  if (readiness.status === "data_ready" && readiness.network_pack_id) {
    return tr("readinessLine.networkVerified", { pack: String(readiness.network_pack_id) });
  }
  return tr("readinessLine.networkFailed");
}
