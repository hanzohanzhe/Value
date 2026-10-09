// Automatic saving and restoring of Study drafts (P1 spec 6.2, AF-低2).
//
//   * The draft in the composer is compared with where it started: a saved
//     Study's revision when one is edited, otherwise the empty new-Study form
//     (or the form the last "Build a Study" reset produced).  When they differ
//     the draft is unsaved: it is written to localStorage under its Study ID
//     and leaving the page asks first (beforeunload).
//   * On return (reload, new tab) a stored draft that differs from the form is
//     offered once: "Restore unsaved draft" or discard.  While the offer is
//     open nothing overwrites the stored draft.
//   * A draft of an edit is offered only for the revision it started from; a
//     newer saved revision makes it stale (it can then only be discarded).
//   * Saving the Study, or moving it to trash, removes its stored draft.
// Storage failures switch the feature off without affecting the page.
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { defaultDraftPackId } from "./draftPack.ts";
import { uniqueStudyName } from "./draftName.ts";
import {
  DEFAULT_RUNTIME_VALUES, DEFAULT_STUDY_NAME, INITIAL_DRAFT_PACK_ID, STUDY_DRAFT_SCHEMA, browserStorage, defaultStudyForm, readStoredDraft,
  removeStoredDraft, sameDraft, savedStudySnapshot, studyDraftKey, writeStoredDraft, type StoredStudyDraft, type StudyDraftSnapshot,
} from "./studyDraft.ts";
import type { DataPack, Project, StudyForm } from "./types";

const noSubscription = () => () => undefined;

export type StudyDraftInputs = {
  form: StudyForm;
  parameters: Record<string, unknown>;
  runtime: Record<string, unknown>;
  packId: string;
  editingProjectId?: string;
  editingBaseRevision?: string;
  projects: readonly Project[];
  packs: readonly Pick<DataPack, "id" | "complete" | "data_pack_type" | "frozen_recovery_origin">[];
  workspaceLoaded: boolean;
  /** Puts a snapshot into the composer (form, parameters, runtime options, data pack). */
  apply: (snapshot: StudyDraftSnapshot) => void;
};

export type StudyDraftState = {
  /** The composer differs from where it started. */
  dirty: boolean;
  /** A stored draft to restore, or null. */
  offer: StoredStudyDraft | null;
  /** The offered draft was made from an older revision of the Study; it can only be discarded. */
  offerStale: boolean;
  restore: () => void;
  discard: () => void;
  /** Forget the stored draft of a Study (after saving it or moving it to trash); "new" when no ID. */
  forget: (studyId?: string | null) => void;
  /** "Build a Study": a fresh new-Study form, unless an unsaved new-Study draft is open (it is kept). */
  reset: () => void;
};

export function useStudyDraft(inputs: StudyDraftInputs): StudyDraftState {
  const { form, parameters, runtime, packId, editingProjectId, editingBaseRevision, projects, packs, workspaceLoaded, apply } = inputs;
  // localStorage is read only after hydration, so the server and the first client render agree.
  const hydrated = useSyncExternalStore(noSubscription, () => true, () => false);
  const [storageNonce, setStorageNonce] = useState(0);
  // Where a new-Study draft started: null = the default form on the default pack.
  const [newBaseline, setNewBaseline] = useState<StudyDraftSnapshot | null>(null);
  const key = studyDraftKey(editingProjectId);
  const current: StudyDraftSnapshot = useMemo(() => ({ form, parameters, runtime, packId }), [form, parameters, runtime, packId]);

  const baseline: StudyDraftSnapshot | null = useMemo(() => {
    if (editingProjectId) {
      const project = projects.find((item) => item.id === editingProjectId);
      if (!project || project.revision_sha256 !== editingBaseRevision) return null;
      return savedStudySnapshot(project);
    }
    return newBaseline ?? { form: defaultStudyForm(), parameters: {}, runtime: DEFAULT_RUNTIME_VALUES, packId: defaultDraftPackId(packs, INITIAL_DRAFT_PACK_ID) };
  }, [editingBaseRevision, editingProjectId, newBaseline, packs, projects]);
  const ready = hydrated && workspaceLoaded;
  const dirty = ready && baseline !== null && !sameDraft(current, baseline);

  const stored = useMemo(() => {
    void storageNonce; // re-read after discard / forget
    return ready ? readStoredDraft(browserStorage(), key) : null;
  }, [key, ready, storageNonce]);
  const offerStale = Boolean(stored && editingProjectId && stored.baseRevision !== (editingBaseRevision ?? null));
  const offer = stored && !sameDraft(stored.snapshot, current) ? stored : null;

  // Automatic save (no React state is set here).
  useEffect(() => {
    if (!ready || offer) return;
    const storage = browserStorage();
    if (dirty) {
      writeStoredDraft(storage, key, {
        schema: STUDY_DRAFT_SCHEMA, studyId: editingProjectId ?? null, baseRevision: editingBaseRevision ?? null,
        savedAt: new Date().toISOString(), snapshot: current,
      });
    } else if (baseline) removeStoredDraft(storage, key);
  }, [baseline, current, dirty, editingBaseRevision, editingProjectId, key, offer, ready]);

  // Leaving the page with an unsaved draft asks first (spec 6.2).
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const restore = useCallback(() => {
    if (offer && !offerStale) apply(offer.snapshot);
  }, [apply, offer, offerStale]);
  const discard = useCallback(() => {
    removeStoredDraft(browserStorage(), key);
    setStorageNonce((value) => value + 1);
  }, [key]);
  const forget = useCallback((studyId?: string | null) => {
    removeStoredDraft(browserStorage(), studyDraftKey(studyId));
    setStorageNonce((value) => value + 1);
  }, []);
  const reset = useCallback(() => {
    if (!editingProjectId && dirty) return;
    const fresh: StudyDraftSnapshot = {
      form: defaultStudyForm(uniqueStudyName(DEFAULT_STUDY_NAME, projects)), parameters: {}, runtime: { ...DEFAULT_RUNTIME_VALUES }, packId,
    };
    setNewBaseline(fresh);
    apply(fresh);
    setStorageNonce((value) => value + 1);
  }, [apply, dirty, editingProjectId, packId, projects]);

  return { dirty, offer, offerStale, restore, discard, forget, reset };
}
