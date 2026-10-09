// Browser harness for the Study draft hook (W4a review, AF-低2): it drives
// useStudyDraft with the same state transitions as the workbench's saveProject
// and "leave the edit" paths.  The save goes through a mocked POST /api/projects
// whose answer is the backend's normalised Study (filled market_configuration and
// extension parameters), then a mocked workspace refresh.
import React, { useCallback, useState } from "react";
import { createRoot } from "react-dom/client";
import { useStudyDraft } from "../../../app/features/studies/useStudyDraft";
import { DEFAULT_RUNTIME_VALUES, INITIAL_DRAFT_PACK_ID, defaultStudyForm, savedStudySnapshot, type StudyDraftSnapshot } from "../../../app/features/studies/studyDraft";
import type { Project, StudyForm } from "../../../app/features/studies/types";

const packs = [{ id: INITIAL_DRAFT_PACK_ID, complete: true, data_pack_type: "reproduction" }];

function Harness() {
  const [form, setForm] = useState<StudyForm>(() => defaultStudyForm());
  const [parameters, setParameters] = useState<Record<string, unknown>>({});
  const [runtime, setRuntime] = useState<Record<string, unknown>>({ ...DEFAULT_RUNTIME_VALUES });
  const [packId, setPackId] = useState(INITIAL_DRAFT_PACK_ID);
  const [editingProjectId, setEditingProjectId] = useState<string | undefined>();
  const [editingBaseRevision, setEditingBaseRevision] = useState<string | undefined>();
  const [projects, setProjects] = useState<Project[]>([]);
  const apply = useCallback((snapshot: StudyDraftSnapshot) => {
    setPackId(snapshot.packId); setForm(snapshot.form); setParameters({ ...snapshot.parameters }); setRuntime({ ...snapshot.runtime });
  }, []);
  const draft = useStudyDraft({ form, parameters, runtime, packId, editingProjectId, editingBaseRevision, projects, packs, workspaceLoaded: true, apply });

  // Mirrors useWorkbenchState.saveProject after a successful POST; `fixed` = false is the pre-fix flow.
  async function save(fixed: boolean) {
    const response = await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...form, id: editingProjectId, data_pack_id: packId }) });
    const payload = await response.json() as { project: Project };
    draft.forget(editingProjectId);
    if (fixed) apply(savedStudySnapshot(payload.project));
    setEditingBaseRevision(payload.project.revision_sha256); setEditingProjectId(payload.project.id);
    const workspace = await (await fetch("/api/workspace")).json() as { projects: Project[] };
    setProjects(workspace.projects);
  }
  // Mirrors leaveStudyEdit (openResearchSuiteStudy, trash of the edited Study); `fixed` = false is the pre-fix flow.
  function leave(fixed: boolean) {
    if (fixed && editingProjectId) draft.reset();
    setEditingBaseRevision(undefined); setEditingProjectId(undefined);
  }
  return <>
    <label>Study name <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
    <button onClick={() => void save(true)}>Save</button>
    <button onClick={() => void save(false)}>Save (pre-fix)</button>
    <button onClick={() => leave(true)}>Leave edit</button>
    <button onClick={() => leave(false)}>Leave edit (pre-fix)</button>
    <output aria-label="editing">{editingProjectId ?? "new"}:{projects.length}</output>
    <output aria-label="dirty">{draft.dirty ? "unsaved" : "clean"}</output>
    <output aria-label="offer">{draft.offer ? "offer" : "none"}</output>
  </>;
}

createRoot(document.getElementById("root")!).render(<Harness />);
