/** Proposal and report for the bounded server-generated audit observer. */
export type ExtensionProposal = {
  id: string;
  name: string;
  namespace: string;
  version: string;
  question: string;
  validation_plan: string;
  migration_notes: string;
};

export type ExtensionAuthoringRequest = {
  proposal: ExtensionProposal;
  manifest?: Record<string, unknown>;
};

export type AuthorExtension = {
  id: string; name: string; version: string; namespace: string;
  maturity?: string; enabled?: boolean; provided_capabilities?: string[];
};
export type ExtensionAuthorModule = { id: string; name: string; slot: string; version: string };
export type StateResponsibility = { namespace: string; owner: string; schema_version: string };

type ReportBase = {
  schema_version: "value.extension-authoring/v1";
  errors: string[];
  warnings: string[];
  proposal: ExtensionProposal;
};
export type ValidExtensionAuthoringReport = ReportBase & {
  valid: true;
  manifest: Record<string, unknown>;
  state_responsibility: StateResponsibility;
  template_kind: "audit-observer";
  execution_scope: string;
  source_package: string;
  manifest_sha256: string;
  package_identity_sha256: string;
};
export type InvalidExtensionAuthoringReport = ReportBase & {
  valid: false;
  manifest: null;
  state_responsibility: null;
  source_package: null;
  manifest_sha256: null;
  package_identity_sha256: null;
  template_kind?: string;
  execution_scope?: string;
};
export type ExtensionAuthoringReport = ValidExtensionAuthoringReport | InvalidExtensionAuthoringReport;

export function isAuthoringRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
export function authoringStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}
export function authoringRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isAuthoringRecord) : [];
}
function isStringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === "string");
}
export function isExtensionProposal(value: unknown): value is ExtensionProposal {
  return isAuthoringRecord(value) && ["id", "name", "namespace", "version", "question", "validation_plan", "migration_notes"]
    .every(key => typeof value[key] === "string");
}
export function isExtensionAuthoringReport(value: unknown): value is ExtensionAuthoringReport {
  if (!isAuthoringRecord(value) || value.schema_version !== "value.extension-authoring/v1"
    || typeof value.valid !== "boolean" || !isStringList(value.errors) || !isStringList(value.warnings)
    || !isExtensionProposal(value.proposal)) return false;
  if (!value.valid) return value.manifest === null && value.state_responsibility === null
    && value.source_package === null && value.manifest_sha256 === null && value.package_identity_sha256 === null;
  const state = value.state_responsibility;
  return isAuthoringRecord(value.manifest) && isAuthoringRecord(state)
    && typeof state.namespace === "string" && typeof state.owner === "string" && typeof state.schema_version === "string"
    && value.template_kind === "audit-observer" && typeof value.execution_scope === "string"
    && typeof value.source_package === "string" && typeof value.manifest_sha256 === "string"
    && /^[0-9a-f]{64}$/.test(value.manifest_sha256) && typeof value.package_identity_sha256 === "string"
    && /^[0-9a-f]{64}$/.test(value.package_identity_sha256);
}

/** Only identities exposed by the report are compared; object key order is immaterial. */
export function sameProposal(left: ExtensionProposal, right: ExtensionProposal): boolean {
  return (Object.keys(left) as (keyof ExtensionProposal)[]).every(key => left[key] === right[key]);
}
