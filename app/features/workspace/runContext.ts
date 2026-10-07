import {
  energyBalanceField, legacyStatusField, profileBadge, rawInvariantsField, runAdvisories, runNotices, stressField,
  type CheckField, type ProfileBadge, type RunAdvisory, type RunNotice, type RunValidationFields,
} from "./runValidation.ts";

/**
 * S-D13 (four-role report, round R1-5): the Run records the manifest as frozen,
 * which is not the source manifest the Data page shows; say which one it is.
 */
export const FROZEN_MANIFEST_LABEL = "Frozen data pack manifest SHA-256";
export const FROZEN_MANIFEST_NOTE = "Freezing rewrites the manifest's file paths and records the snapshot, so this SHA-256 differs from the source manifest SHA-256 shown on the Data page; compare files by their per-role SHA-256.";

/** Presentation of one Run's recorded identity. No mutable workspace input belongs here. */
export type ContextRun = RunValidationFields & {
  id: string;
  project_id: string;
  project_name?: string;
  mode?: string;
  status?: string;
  input_snapshot_id?: string;
  input_tree_sha256?: string;
  execution_status?: string;
  contract_validation_status?: string | null;
  scientific_validation_status?: string | null;
  source_study_status?: string;
  run_policy?: { label?: string; total_periods?: number; start_year?: number; end_year?: number };
  diagnostic?: { total_periods?: number; years?: number[] };
};

export type FrozenContextProject = {
  id?: string;
  name?: string;
  data_pack_id?: string;
  revision_number?: number;
  revision_sha256?: string;
  market_configuration?: { network_pack_id?: string };
};

export type FrozenContextSnapshot = {
  snapshot_id?: string;
  state?: string;
  input_tree_sha256?: string;
  pack_manifest_sha256?: string;
  network_pack_id?: string;
  network_pack_manifest_sha256?: string;
};

export type FrozenRunContext = {
  /** The Run whose artifacts were requested, not the currently selected Study. */
  runId: string;
  status: "loading" | "ready" | "unavailable";
  project?: FrozenContextProject | null;
  snapshot?: FrozenContextSnapshot | null;
};

export type RunContext = {
  kind: "empty" | "loading" | "ready" | "partial" | "unavailable" | "mismatch";
  runId?: string;
  studyId?: string;
  studyName?: string;
  revisionNumber?: number;
  revisionSha?: string;
  dataPackId?: string;
  dataPackSha?: string;
  networkPackId?: string;
  networkPackSha?: string;
  snapshotId?: string;
  inputTreeSha?: string;
  sourceStudyStatus?: string;
  scope: { mode?: string; label: string; configuredPeriods?: number; years?: number[] };
  executionStatus: string;
  contractStatus: string;
  scientificStatus: string;
  /** Spec 2.2 / 2.3 (X0 S12, P0-9 S11): methodology pill, validation fields and notices. */
  profile: ProfileBadge;
  methodologyProfileId?: string;
  profileCatalogueSha?: string;
  energyBalance: CheckField;
  /** Spec 11.3: doctoral profile only; null otherwise. */
  rawInvariants: CheckField | null;
  stress: CheckField;
  contractField: CheckField | null;
  scientificField: CheckField | null;
  notices: RunNotice[];
  advisories: RunAdvisory[];
  issue?: string;
};

function recorded(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function positiveInteger(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : undefined;
}

function runScope(run?: ContextRun): RunContext["scope"] {
  const labels: Record<string, string> = {
    smoke: "Two-period wiring check",
    two_year_smoke: "Two-year hand-off check",
    value_101_day: "One-day market lesson",
    two_year: "Two-year model scope",
    full: "Full Study scope",
  };
  const diagnosticYears = run?.diagnostic?.years;
  const years = Array.isArray(diagnosticYears)
    && diagnosticYears.length > 0
    && diagnosticYears.every((year) => positiveInteger(year) !== undefined)
    ? [...diagnosticYears]
    : undefined;
  return {
    mode: recorded(run?.mode),
    label: recorded(run?.run_policy?.label) ?? labels[run?.mode ?? ""] ?? "Run scope not recorded",
    configuredPeriods: positiveInteger(run?.diagnostic?.total_periods) ?? positiveInteger(run?.run_policy?.total_periods),
    // Study start/end years are intentionally not accepted: a short Run may cover less.
    years,
  };
}

export function resolveRunContext({ run, frozen }: {
  run?: ContextRun | null;
  frozen?: FrozenRunContext | null;
}): RunContext {
  const contractStatus = recorded(run?.contract_validation_status) ?? "not_evaluated";
  const scientificStatus = recorded(run?.scientific_validation_status) ?? "not_evaluated";
  const base: RunContext = {
    kind: "empty",
    scope: runScope(run ?? undefined),
    // R4 T-低1: while the inputs are frozen the recorded execution status is still "queued".
    executionStatus: run?.status === "snapshotting" ? "preparing" : recorded(run?.execution_status) ?? recorded(run?.status) ?? "not_recorded",
    contractStatus,
    scientificStatus,
    profile: profileBadge(run?.methodology),
    methodologyProfileId: recorded(run?.methodology?.profile_id),
    profileCatalogueSha: recorded(run?.methodology?.catalogue_sha256),
    energyBalance: energyBalanceField(run?.energy_balance_status, run?.energy_balance?.enforcement),
    rawInvariants: rawInvariantsField(run),
    stress: stressField(run?.stress),
    contractField: legacyStatusField(contractStatus, run?.recorded_validation_statuses?.contract_validation_status),
    scientificField: legacyStatusField(scientificStatus, run?.recorded_scientific_validation_status ?? run?.recorded_validation_statuses?.scientific_validation_status),
    notices: runNotices(run),
    advisories: runAdvisories(run),
  };
  if (!run) return { ...base, issue: "Select a Run to view its recorded identity." };
  Object.assign(base, {
    runId: run.id,
    studyId: run.project_id,
    studyName: recorded(run.project_name),
    sourceStudyStatus: recorded(run.source_study_status),
  });
  if (!frozen || frozen.runId !== run.id || frozen.status === "loading") {
    return { ...base, kind: "loading", issue: "Loading this Run’s frozen identity…" };
  }
  if (frozen.status === "unavailable" || !frozen.project || !recorded(frozen.project.id)) {
    return { ...base, kind: "unavailable", issue: "Frozen Study unavailable. The current workspace data is not this Run’s source." };
  }
  const project = frozen.project;
  const snapshot = frozen.snapshot;
  const mismatch = (issue: string): RunContext => ({ ...base, kind: "mismatch", issue });
  if (project.id !== run.project_id) return mismatch("The frozen Study does not match this Run. Source identity is withheld.");
  if (snapshot?.state !== undefined && snapshot.state !== "ready") {
    return { ...base, kind: "unavailable", issue: "The input snapshot is not ready. Source identity is unavailable." };
  }
  if (recorded(run.input_snapshot_id) && recorded(snapshot?.snapshot_id)
    && run.input_snapshot_id !== snapshot?.snapshot_id) {
    return mismatch("The input snapshot ID does not match this Run. Source identity is withheld.");
  }
  if (recorded(run.input_tree_sha256) && recorded(snapshot?.input_tree_sha256)
    && run.input_tree_sha256 !== snapshot?.input_tree_sha256) {
    return mismatch("The input tree identity does not match this Run. Source identity is withheld.");
  }
  const declaredNetwork = recorded(project.market_configuration?.network_pack_id);
  const snapshottedNetwork = recorded(snapshot?.network_pack_id);
  if (declaredNetwork && snapshottedNetwork && declaredNetwork !== snapshottedNetwork) {
    return mismatch("The frozen network-pack identities disagree. Source identity is withheld.");
  }
  const dataPackId = recorded(project.data_pack_id);
  const complete = Boolean(dataPackId && snapshot?.state === "ready"
    && recorded(snapshot.snapshot_id) && recorded(snapshot.pack_manifest_sha256)
    && (!run.input_tree_sha256 || recorded(snapshot.input_tree_sha256)));
  return {
    ...base,
    kind: complete ? "ready" : "partial",
    studyName: recorded(project.name) ?? base.studyName,
    revisionNumber: positiveInteger(project.revision_number),
    revisionSha: recorded(project.revision_sha256),
    dataPackId,
    dataPackSha: recorded(snapshot?.pack_manifest_sha256),
    networkPackId: snapshottedNetwork ?? declaredNetwork,
    networkPackSha: recorded(snapshot?.network_pack_manifest_sha256),
    snapshotId: recorded(snapshot?.snapshot_id),
    inputTreeSha: recorded(snapshot?.input_tree_sha256),
    issue: complete ? undefined : "Some frozen identity fields were not recorded or could not be loaded. Available fields are shown below.",
  };
}
