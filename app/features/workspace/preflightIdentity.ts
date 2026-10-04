type StudyIdentity = { id: string; revision_sha256?: string; data_pack_id: string };
type ReportIdentity = { project_id?: string; project_revision_sha256?: string; data_pack_id?: string; mode?: string };

export function preflightKey(project: StudyIdentity | undefined, mode: string): string {
  return JSON.stringify([project?.id, project?.revision_sha256, project?.data_pack_id, mode]);
}

/** A preflight is evidence for one saved revision and one requested run scope. */
export function preflightMatches(report: ReportIdentity | null | undefined, project: StudyIdentity | undefined, mode: string): boolean {
  return Boolean(report && project?.revision_sha256
    && report.project_id === project.id
    && report.project_revision_sha256 === project.revision_sha256
    && report.data_pack_id === project.data_pack_id
    && report.mode === mode);
}
