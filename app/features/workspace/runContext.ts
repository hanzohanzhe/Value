import {
  energyBalanceField, legacyStatusField, profileBadge, rawInvariantsField, runAdvisories, runNotices, stressField,
  type CheckField, type ProfileBadge, type RunAdvisory, type RunNotice, type RunValidationFields,
} from "./runValidation.ts";
import { en } from "../../i18n/en.ts";
import { getActiveLocale, localizedTable, tr, type MessageKey } from "../../i18n/index.ts";

/**
 * S-D13 (four-role report, round R1-5): the Run records the manifest as frozen,
 * which is not the source manifest the Data page shows; say which one it is.
 */
export const FROZEN_MANIFEST_LABEL = en["context.manifestLabel"];
export const FROZEN_MANIFEST_NOTE = en["context.manifestNote"];
/** P1 W5: the label and note in the interface language (the constants keep the English text). */
export function frozenManifestLabel(): string { return tr("context.manifestLabel"); }
export function frozenManifestNote(): string { return tr("context.manifestNote"); }

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
  /** R4 F-低4: extensions of the Run's frozen Study (backend present_run). */
  selected_extensions?: { id: string; version?: string | null; maturity?: string | null }[];
};

export type ExtensionMarker = { key: string; text: string; tone: "caution" | "muted"; title: string };

/**
 * R4 F-低4: a Run that executed extension hooks says so in its header. Any
 * extension that is not declared "ready" is marked experimental.
 */
export function extensionMarkers(run?: Pick<ContextRun, "selected_extensions"> | null): ExtensionMarker[] {
  return (Array.isArray(run?.selected_extensions) ? run.selected_extensions : [])
    .filter((row) => row && typeof row.id === "string" && row.id)
    .map((row) => {
      const ready = row.maturity === "ready";
      const label = `${row.id}${row.version ? ` ${row.version}` : ""}`;
      return {
        key: row.id,
        text: tr(ready ? "context.extension" : "context.experimentalExtension", { label }),
        tone: ready ? "muted" : "caution",
        title: ready ? tr("context.extensionTitle") : tr("context.experimentalTitle", { maturity: row.maturity ? row.maturity.replaceAll("_", " ") : tr("context.noMaturity") }),
      };
    });
}

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
  const labels: Readonly<Record<string, string>> = localizedTable<string>({
    smoke: "context.scope.smoke",
    two_year_smoke: "context.scope.two_year_smoke",
    value_101_day: "context.scope.value_101_day",
    two_year: "context.scope.two_year",
    full: "context.scope.full",
  } as Record<string, MessageKey>);
  const diagnosticYears = run?.diagnostic?.years;
  const years = Array.isArray(diagnosticYears)
    && diagnosticYears.length > 0
    && diagnosticYears.every((year) => positiveInteger(year) !== undefined)
    ? [...diagnosticYears]
    : undefined;
  return {
    mode: recorded(run?.mode),
    // The backend's run_policy label is English; another interface language names a known scope itself.
    label: (getActiveLocale() !== "en" && Object.hasOwn(labels, run?.mode ?? "") ? labels[run?.mode ?? ""] : undefined)
      ?? recorded(run?.run_policy?.label) ?? labels[run?.mode ?? ""] ?? tr("context.scope.notRecorded"),
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
  if (!run) return { ...base, issue: tr("context.issue.select") };
  Object.assign(base, {
    runId: run.id,
    studyId: run.project_id,
    studyName: recorded(run.project_name),
    sourceStudyStatus: recorded(run.source_study_status),
  });
  if (!frozen || frozen.runId !== run.id || frozen.status === "loading") {
    return { ...base, kind: "loading", issue: tr("context.issue.loading") };
  }
  if (frozen.status === "unavailable" || !frozen.project || !recorded(frozen.project.id)) {
    return { ...base, kind: "unavailable", issue: tr("context.issue.unavailable") };
  }
  const project = frozen.project;
  const snapshot = frozen.snapshot;
  const mismatch = (issue: string): RunContext => ({ ...base, kind: "mismatch", issue });
  if (project.id !== run.project_id) return mismatch(tr("context.issue.studyMismatch"));
  if (snapshot?.state !== undefined && snapshot.state !== "ready") {
    return { ...base, kind: "unavailable", issue: tr("context.issue.snapshotNotReady") };
  }
  if (recorded(run.input_snapshot_id) && recorded(snapshot?.snapshot_id)
    && run.input_snapshot_id !== snapshot?.snapshot_id) {
    return mismatch(tr("context.issue.snapshotMismatch"));
  }
  if (recorded(run.input_tree_sha256) && recorded(snapshot?.input_tree_sha256)
    && run.input_tree_sha256 !== snapshot?.input_tree_sha256) {
    return mismatch(tr("context.issue.treeMismatch"));
  }
  const declaredNetwork = recorded(project.market_configuration?.network_pack_id);
  const snapshottedNetwork = recorded(snapshot?.network_pack_id);
  if (declaredNetwork && snapshottedNetwork && declaredNetwork !== snapshottedNetwork) {
    return mismatch(tr("context.issue.networkMismatch"));
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
    issue: complete ? undefined : tr("context.issue.partial"),
  };
}
