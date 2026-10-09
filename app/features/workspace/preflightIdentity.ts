import { tr } from "../../i18n/index.ts";

type StudyIdentity = { id: string; revision_sha256?: string; data_pack_id: string };
type ReportIdentity = { project_id?: string; project_revision_sha256?: string | null; data_pack_id?: string; mode?: string; accepted?: boolean; errors?: unknown[] };

export function preflightKey(project: StudyIdentity | undefined, mode: string): string {
  return JSON.stringify([project?.id, project?.revision_sha256, project?.data_pack_id, mode]);
}

/**
 * A blocked preflight whose revision could not be computed (spec 11.4, M-D3):
 * a quarantined or disabled module stops the backend from fingerprinting the
 * Study, so the report carries no project_revision_sha256 but does carry the
 * errors that explain why. Such a report is never evidence that a Run may start.
 */
export function isUnidentifiedBlockedReport(report: ReportIdentity | null | undefined): boolean {
  return Boolean(report && report.accepted === false && !report.project_revision_sha256
    && Array.isArray(report.errors) && report.errors.length > 0);
}

/** A preflight is evidence for one saved revision and one requested run scope. */
export function preflightMatches(report: ReportIdentity | null | undefined, project: StudyIdentity | undefined, mode: string): boolean {
  return Boolean(report && project?.revision_sha256
    && report.project_id === project.id
    && (report.project_revision_sha256 === project.revision_sha256 || isUnidentifiedBlockedReport(report))
    && report.data_pack_id === project.data_pack_id
    && report.mode === mode);
}

/**
 * R4 M-低2: errors of the installation itself (an unsealed runtime kernel, an
 * unsupported Python, missing scientific packages). While one is reported no
 * Study can run, so the Study's method-upgrade confirmation waits until it is
 * fixed instead of writing a revision first.
 */
export function environmentBlockers(report: { errors?: { scope?: string; code?: string }[] } | null | undefined): string[] {
  return (Array.isArray(report?.errors) ? report.errors : [])
    .filter((issue) => issue?.scope === "environment")
    .map((issue) => String(issue.code ?? "environment"));
}

/** Spec 11.4: why the Run button is disabled after a blocked preflight, or null. */
export function preflightRunBlockedReason(report: { accepted?: boolean; errors?: { message?: string }[] } | null | undefined): string | null {
  if (!report || report.accepted !== false) return null;
  const count = Array.isArray(report.errors) ? report.errors.length : 0;
  return tr("readinessLine.blocked", { count });
}
