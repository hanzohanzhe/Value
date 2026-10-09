"use client";

// Studies (/studies, /studies/[studyId]), P1 spec 6.2: a one-line page header,
// the "Restore unsaved draft" offer (AF-低2), the composer and the saved
// Studies.  Wording from the dictionaries (studies.*).
import StudyComposer from "../features/studies/StudyComposer";
import { selectedProfileId } from "../features/studies/methodologyChoice.ts";
import AdvancedSettings from "../features/studies/AdvancedSettings";
import { Badge } from "../features/shared/presentation";
import { formatSystemTime } from "../features/shared/format.ts";
import { type TraceProfile } from "../features/market/TraceCoverageNotice";
import { useWorkbench } from "../features/shell/Workbench";
import { useT } from "../i18n/LocaleProvider";
import { Button, Callout } from "../ui";
import { plainClick } from "../features/shell/WorkspaceRail";
import { viewHref } from "../features/shell/routes.ts";

export default function StudiesView() {
  const t = useT();
  const {
    setView, workspace, definitions, selectedPackId, setSelectedPackId, selectedProjectId, setSelectedProjectId, setSelectedRunId, setSelectedRunDetail, methodologyCatalogue, methodologyError, setNotice,
    parameterValues, setParameterValues, runtimeValues, setRuntimeValues, resolvedSources, draftResolution, draftResolving, draftResolutionError, composerInitialStep, setDataContextId,
    editingProjectId, setEditingProjectId, setEditingBaseRevision, projectForm, setProjectForm, selectedPack, selectRunProject, chooseDomain, toggleExtension, chooseMethodology, selectStudyModule,
    loadProjectRevision, moveStudyToTrash, restoreStudyEntry, previewParameters, saveProject, savingStudy, studyDraft, resetStudyDraft, leaveStudyEdit,
  } = useWorkbench();
  const editingName = editingProjectId ? workspace.projects.find((project) => project.id === editingProjectId)?.name ?? editingProjectId : undefined;
  const offer = studyDraft.offer;
  return <div className="page project-page studies-page">
    <header className="v-page-header studies-header">
      <div className="v-page-header__text">
        {/* R-15 (P1-polish): from an edit, a link back to /studies (the browser's Back does the same). */}
        {editingProjectId && <a className="studies-back" href={viewHref("projects")} onClick={(event) => { if (!plainClick(event)) return; event.preventDefault(); leaveStudyEdit(); }}>{t("studies.header.back")}</a>}
        <h2>{editingName ? t("studies.header.edit", { name: editingName }) : t("studies.header.new")}</h2>
        <p>{t("studies.header.lead")}</p>
      </div>
      <div className="v-page-header__actions">
        <Badge tone={draftResolution?.valid ? "good" : "warn"}>{draftResolving ? t("studies.header.resolving") : draftResolution?.valid ? t("studies.header.ready") : t("studies.header.incomplete")}</Badge>
        {studyDraft.dirty && <span className="studies-draft-state" role="status">{t("studies.draft.unsaved")}</span>}
        {editingProjectId && <Button size="sm" onClick={() => { setEditingBaseRevision(undefined); setEditingProjectId(undefined); resetStudyDraft(); }}>{t("studies.header.newStudy")}</Button>}
      </div>
    </header>
    {offer && <Callout tone="info" className="studies-draft-offer" title={studyDraft.offerStale ? t("studies.draft.staleTitle") : t("studies.draft.restoreTitle")}>
      <p>{studyDraft.offerStale ? t("studies.draft.staleBody", { name: offer.snapshot.form.name }) : t("studies.draft.restoreBody", { name: offer.snapshot.form.name, time: formatSystemTime(offer.savedAt) ?? t("studies.draft.unknownTime") })}</p>
      <div className="studies-draft-actions">
        {!studyDraft.offerStale && <Button variant="primary" size="sm" onClick={studyDraft.restore}>{t("studies.draft.restore")}</Button>}
        <Button size="sm" onClick={studyDraft.discard}>{t("studies.draft.discard")}</Button>
      </div>
    </Callout>}
    <StudyComposer initialStep={composerInitialStep} workspace={workspace} form={projectForm} selectedPackId={selectedPack?.id ?? selectedPackId} resolution={draftResolution} resolving={draftResolving} resolutionError={draftResolutionError} savedProjects={workspace.projects} studyTrash={workspace.study_trash} selectedProjectId={selectedProjectId} saving={savingStudy} newStudy={!editingProjectId}
      assumptions={<><AdvancedSettings definitions={definitions} values={{ ...parameterValues, ...runtimeValues }} resolvedSources={resolvedSources} onChange={(id, value, runtime) => runtime ? setRuntimeValues((current) => ({ ...current, [id]: value })) : setParameterValues((current) => ({ ...current, [id]: value }))} /><button type="button" className="text-button full" onClick={() => void previewParameters()}>{t("studies.assumptions.check")}</button></>}
      onForm={(update) => setProjectForm(update)} onPack={setSelectedPackId} onDomain={chooseDomain} onExtension={toggleExtension} onModule={selectStudyModule}
      onExtensionParameter={(name, value) => setProjectForm((current) => ({ ...current, extension_parameters: { ...current.extension_parameters, [name]: value } }))}
      onAcknowledgement={(key, value, checked) => setProjectForm((current) => { const maturity_acknowledgements = { ...current.maturity_acknowledgements }; if (checked) maturity_acknowledgements[key] = value; else delete maturity_acknowledgements[key]; return { ...current, maturity_acknowledgements }; })}
      onSave={() => void saveProject()} onLoad={loadProjectRevision} onOpenRun={(project) => { selectRunProject(project.id); setView("run"); }}
      onTrash={(project, linkedRunCount) => void moveStudyToTrash(project, linkedRunCount)} onRestore={(entry) => void restoreStudyEntry(entry)}
      onOpenTrashRuns={(entry) => { const run = workspace.runs.find((item) => item.project_id === entry.study_id); setSelectedProjectId(entry.study_id); setSelectedRunId(run?.id ?? ""); setSelectedRunDetail(null); setView("run"); if (!run) setNotice(t("studies.trash.noIndexedRun")); }}
      onOpenData={() => { setDataContextId("draft"); setView("data"); }}
      traceLevel={(runtimeValues["runtime.market_trace_level"] as TraceProfile | undefined) ?? "summary"} onTraceLevel={(trace) => setRuntimeValues((current) => ({ ...current, "runtime.market_trace_level": trace }))}
      methodology={{ catalogue: methodologyCatalogue, profileId: selectedProfileId(parameterValues, methodologyCatalogue), error: methodologyError }}
      editingStudyName={editingName} onMethodology={chooseMethodology} />
  </div>;
}
