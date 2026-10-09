// Saving a Study (review F4-03 / F1-08, P1 spec 6.2): what the user is told
// when a save is refused or the service cannot be reached, and the
// name-to-ID clash the composer reports while the name is typed.
//
// Pure module: the dictionaries give the wording (spec 3: a translated
// explanation of a known error code, then the service's message as sent).
import type { Translate } from "../../i18n/index.ts";
import { studyIdFromName, uniqueStudyName } from "./draftName.ts";

export type SaveFailure =
  | { kind: "network" }
  | { kind: "refused"; status: number; code?: string; error?: string; studyId?: string };

/** The notice for a failed save; `projects` gives the free name to suggest. */
export function saveFailureNotice(failure: SaveFailure, t: Translate, name: string, projects: readonly { id: string }[]): string {
  if (failure.kind === "network") return t("studies.save.offline");
  const message = failure.error || t("studies.save.httpFailed", { status: failure.status });
  const sent = failure.code ? `${failure.code}: ${message}` : message;
  if (failure.code === "GF_STUDY_ID_EXISTS") {
    return `${t("studies.save.idExists", { id: failure.studyId ?? studyIdFromName(name), suggestion: uniqueStudyName(name, projects) })} ${sent}`;
  }
  if (failure.code === "GF_STUDY_ID_RESERVED_IN_TRASH") {
    return `${t("studies.save.idInTrash", { id: failure.studyId ?? studyIdFromName(name) })} ${sent}`;
  }
  return t("studies.save.failed", { message: sent });
}

export type NameClash = { kind: "saved" | "trash"; id: string; suggestion: string } | null;

/** A new Study's name maps to the ID of a saved Study or of one in trash (the save would be refused). */
export function newStudyNameClash(name: string, projects: readonly { id: string }[], trash: readonly { study_id: string }[]): NameClash {
  if (!name.trim()) return null;
  const id = studyIdFromName(name);
  const taken = [...projects.map((project) => ({ id: project.id })), ...trash.map((entry) => ({ id: entry.study_id }))];
  if (projects.some((project) => project.id === id)) return { kind: "saved", id, suggestion: uniqueStudyName(name, taken) };
  if (trash.some((entry) => entry.study_id === id)) return { kind: "trash", id, suggestion: uniqueStudyName(name, taken) };
  return null;
}

/**
 * R-8 (P1-polish, spec 2 Button): why the save button is disabled, for its
 * title and the line beside it; "" while it can be pressed (or is saving).
 */
export function saveDisabledReason(state: {
  saving: boolean;
  resolving: boolean;
  blockedReason: string;
  resolution: { valid: boolean; errors: readonly { code: string; message?: string }[] } | null | undefined;
  solverContractReady: boolean;
}, t: Translate): string {
  if (state.saving) return "";
  if (state.blockedReason) return state.blockedReason;
  if (state.resolving) return t("studies.review.disabled.resolving");
  if (!state.resolution) return t("studies.review.disabled.notResolved");
  if (!state.resolution.valid) {
    const errors = state.resolution.errors;
    if (errors.some((issue) => issue.code === "GF_EXPERIMENTAL_ACK_REQUIRED")) return t("studies.review.disabled.ack");
    const first = errors[0];
    return first ? t("studies.review.disabled.issues", { count: errors.length, first: first.message ? `${first.code}: ${first.message}` : first.code }) : t("studies.review.disabled.notResolved");
  }
  if (!state.solverContractReady) return t("studies.review.disabled.solver");
  return "";
}
