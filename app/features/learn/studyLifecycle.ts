export type SourceStudyStatus = "active" | "trash" | "missing";

export function buildStudyTrashConfirmation(
  study: { id: string; name: string },
  linkedRunCount: number,
) {
  if (linkedRunCount > 0) {
    return {
      requiresExactName: true,
      expected: study.name,
      message: `This Study has ${linkedRunCount} historical Runs. Type its exact name to move it to recoverable trash:\n${study.name}`,
    };
  }
  return {
    requiresExactName: false,
    expected: study.name,
    message: `Move ${study.name} and all of its immutable revisions to recoverable trash?`,
  };
}

export function sourceStudyAllowsDerivedRun(status?: SourceStudyStatus) {
  return status === undefined || status === "active";
}

export function networkPackReadinessLabel(
  readiness?: { status?: string; network_pack_id?: unknown },
) {
  if (!readiness) return "Check readiness to confirm";
  if (readiness.status === "data_ready" && readiness.network_pack_id) {
    return `${String(readiness.network_pack_id)} · verified`;
  }
  return "Check readiness failed — review the missing or incompatible role below";
}
