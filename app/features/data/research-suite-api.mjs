// Same-origin only (P0-1): the UI gateway forwards /api/* to the engine.
export function researchSuiteApiUrl() {
  return "/api/research-suites/install";
}

export function describeResearchSuiteInstallation(installation) {
  const componentIds = Array.isArray(installation?.component_pack_ids)
    ? installation.component_pack_ids
    : [];
  const componentHashes = Array.isArray(installation?.component_bundle_sha256)
    ? installation.component_bundle_sha256
    : [];
  const studyIds = Array.isArray(installation?.study_ids) ? installation.study_ids : [];

  return {
    suiteId: installation?.suite_id ?? "unknown suite",
    suiteSha256: installation?.suite_sha256 ?? "",
    components: componentIds.map((id, index) => ({
      id,
      sha256: componentHashes[index] ?? "",
    })),
    studyIds,
    idempotent: installation?.idempotent === true,
    runStarted: false,
  };
}
