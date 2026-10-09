// Study drafts in the browser (P1 spec 6.2, four-role report AF-低2).
//
// An unsaved independent Study draft, and an edit of a saved Study, are kept in
// localStorage under a key with the Study ID ("new" for a new Study), so a
// reload or a closed tab no longer loses them.  On return the Studies page
// offers "Restore unsaved draft".  Every storage access is wrapped: a private
// window, blocked storage or a full quota only switches the feature off.
//
// Pure module (no React): the hook in useStudyDraft.ts uses it.
import { copyDefaultZonalSolverContract } from "../network/networkRedispatch.ts";
import type { Project, StudyForm } from "./types";

export const STUDY_DRAFT_PREFIX = "value.study-draft.v1:";
export const STUDY_DRAFT_SCHEMA = "value.study-draft-storage/v1";
/** The draft data pack the workbench starts from (useWorkbenchState). */
export const INITIAL_DRAFT_PACK_ID = "value-uk-1000twh-reproduction";
export const DEFAULT_STUDY_NAME = "VALUE UK transition";
export const DEFAULT_RUNTIME_VALUES: Record<string, unknown> = { "runtime.market_trace_level": "summary" };

export type StudyDraftSnapshot = {
  form: StudyForm;
  parameters: Record<string, unknown>;
  runtime: Record<string, unknown>;
  packId: string;
};

export type StoredStudyDraft = {
  schema: typeof STUDY_DRAFT_SCHEMA;
  /** The saved Study being edited, or null for a new Study. */
  studyId: string | null;
  /** The revision the edit started from (edits only). */
  baseRevision: string | null;
  /** ISO time of the last automatic save. */
  savedAt: string;
  snapshot: StudyDraftSnapshot;
};

/** The composer's starting form for a new Study. */
export function defaultStudyForm(name = DEFAULT_STUDY_NAME): StudyForm {
  return {
    name, purpose: "", start_year: 2025, end_year: 2034,
    modules: { psm: "value-bid-at-cost-psm", investment: "agent-investment", pipeline: "planning-pipeline", vre_cap: "vre-expansion-cap", storage_cap: "value-storage-expansion-policy", transition: "value-annual-state-transition", storage_cost: "dynamic-annual-storage-cost" },
    selected_extensions: [], extension_parameters: {}, maturity_acknowledgements: {},
    market_configuration: {},
  };
}

/** The editable form of a saved Study (Edit as new revision, the extension draft). */
export function studyFormFromProject(project: Project, name = project.name): Omit<StudyDraftSnapshot, "packId"> {
  return {
    form: {
      name,
      purpose: project.purpose ?? "",
      start_year: project.start_year,
      end_year: project.end_year,
      modules: { ...project.modules },
      selected_extensions: [...(project.selected_extensions ?? [])],
      extension_parameters: { ...(project.extension_parameters ?? {}) },
      maturity_acknowledgements: { ...(project.maturity_acknowledgements ?? {}) },
      market_configuration: { ...(project.market_configuration ?? {}) },
      solver_contract: project.solver_contract ? {
        ...project.solver_contract,
        validated_ceilings: { ...project.solver_contract.validated_ceilings },
        absolute_ceilings: { ...project.solver_contract.absolute_ceilings },
      } : project.modules.balancing === "value-zonal-redispatch-balancing"
        ? copyDefaultZonalSolverContract()
        : undefined,
    },
    parameters: { ...(project.parameters ?? {}) },
    runtime: { ...DEFAULT_RUNTIME_VALUES, ...(project.runtime_options ?? {}) },
  };
}

/** The composer snapshot of a saved Study revision, data pack included.  After a
 * save the composer is replaced by this (the backend normalises the Study, e.g.
 * it fills market_configuration), so the form equals its baseline and is not
 * reported as unsaved (W4a review). */
export function savedStudySnapshot(project: Project, name = project.name): StudyDraftSnapshot {
  return { ...studyFormFromProject(project, name), packId: project.data_pack_id };
}

/** localStorage key of the draft of one Study ("new" for a new Study). */
export function studyDraftKey(studyId?: string | null): string {
  return `${STUDY_DRAFT_PREFIX}${studyId || "new"}`;
}

/** JSON with sorted object keys and without undefined members, so two equal drafts compare equal. */
export function stableJson(value: unknown): string {
  const normal = (item: unknown): unknown => {
    if (Array.isArray(item)) return item.map(normal);
    if (item && typeof item === "object") {
      return Object.fromEntries(Object.keys(item as Record<string, unknown>).sort()
        .filter((key) => (item as Record<string, unknown>)[key] !== undefined)
        .map((key) => [key, normal((item as Record<string, unknown>)[key])]));
    }
    return item;
  };
  return JSON.stringify(normal(value)) ?? "null";
}

export function sameDraft(a: StudyDraftSnapshot | null | undefined, b: StudyDraftSnapshot | null | undefined): boolean {
  return Boolean(a && b) && stableJson(a) === stableJson(b);
}

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);

/** A stored draft, or null when the text is not one (old schema, damaged, foreign). */
export function parseStoredDraft(text: string | null | undefined): StoredStudyDraft | null {
  if (!text) return null;
  let value: unknown;
  try { value = JSON.parse(text); } catch { return null; }
  if (!isRecord(value) || value.schema !== STUDY_DRAFT_SCHEMA || !isRecord(value.snapshot)) return null;
  const snapshot = value.snapshot;
  const form = snapshot.form;
  if (!isRecord(form) || typeof form.name !== "string" || typeof form.start_year !== "number" || typeof form.end_year !== "number"
    || !isRecord(form.modules) || !Array.isArray(form.selected_extensions) || !isRecord(snapshot.parameters) || !isRecord(snapshot.runtime)
    || typeof snapshot.packId !== "string") return null;
  return {
    schema: STUDY_DRAFT_SCHEMA,
    studyId: typeof value.studyId === "string" ? value.studyId : null,
    baseRevision: typeof value.baseRevision === "string" ? value.baseRevision : null,
    savedAt: typeof value.savedAt === "string" ? value.savedAt : "",
    snapshot: {
      form: {
        purpose: "", extension_parameters: {}, maturity_acknowledgements: {}, market_configuration: {},
        ...(form as Partial<StudyForm>),
      } as StudyForm,
      parameters: snapshot.parameters,
      runtime: snapshot.runtime,
      packId: snapshot.packId,
    },
  };
}

type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/** window.localStorage, or null where it is unavailable or throws. */
export function browserStorage(): DraftStorage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readStoredDraft(storage: DraftStorage | null, key: string): StoredStudyDraft | null {
  try { return parseStoredDraft(storage?.getItem(key)); } catch { return null; }
}

/** False when the browser refused (quota, blocked storage); the page carries on. */
export function writeStoredDraft(storage: DraftStorage | null, key: string, draft: StoredStudyDraft): boolean {
  try { storage?.setItem(key, JSON.stringify(draft)); return Boolean(storage); } catch { return false; }
}

export function removeStoredDraft(storage: DraftStorage | null, key: string): void {
  try { storage?.removeItem(key); } catch { /* storage unavailable: nothing to remove */ }
}
