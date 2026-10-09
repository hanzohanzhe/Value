"use client";

// Data (/data). P1 W4b (spec 6.3): a one-line page header; the inputs of the
// selected context first (journey editor, input contract, validation, role
// table), then the installers, the Data Workbench (expert tools) and the data
// adapter guide (moved here from /extensions, D-W3-5), reached from a sticky
// in-page navigation; app/ui components and the dictionaries (data.*).
import { useMemo } from "react";
import { Badge, formatBytes, modelDisplayName } from "../features/shared/presentation";
import DataPackValidationPanel from "../features/data/DataPackValidationPanel";
import { inputsPresentSuffix, worstStatus } from "../features/data/dataPackValidation.ts";
import JourneyDataEditor from "../features/workspace/JourneyDataEditor";
import DataWorkbench from "../features/data-workbench/DataWorkbench";
import DataPreviewPanel from "../features/data/DataPreviewPanel";
import AdapterGuide from "../features/data/AdapterGuide";
import SectionNav from "../features/shared/SectionNav";
import { DATA_PAGE_SECTIONS } from "../features/data/dataPage.ts";
import { Button, FileDrop, Hash, PageHeader, TextField, buttonClass } from "../ui";
import "./data-page.css";
import { useT } from "../i18n/LocaleProvider";
import { API_BASE } from "../lib/api.ts";
import { useWorkbench } from "../features/shell/Workbench";

const API = API_BASE;
const DATA_BUNDLE_COMMAND = "py -3.10 scripts\\build_data_bundle.py --pack-root my-pack --output my-pack.zip";

function Progress({ stage, value }: { stage: string; value: string }) {
  return <span><b>{stage}</b><small>{value}</small></span>;
}

export default function DataView() {
  const t = useT();
  const { setView, activePath, workspace, online, selectedPackId, setSelectedPackId, uploading, dataBundle, setDataBundle, dataRights, setDataRights, dataInstalling, dataInstallProgress, dataInstallPhase, researchSuiteBundle, setResearchSuiteBundle, researchSuiteRights, setResearchSuiteRights, researchSuiteInstalling, researchSuiteInstallProgress, researchSuiteInstallPhase, researchSuiteSummary, setPreflight, setDraftResolution, draftResolving, setComposerInitialStep, draftPackCopyName, setDraftPackCopyName, copyingDraftPack, dataContextId, setDataContextId, setSavedDataResolution, setDataPreview, dataPreviewLoading, refresh, journeySource, journeySourcePack, isJourneyData, dataContextProject, dataContextPackId, dataContextPack, journeyNetworkPackId, journeyReadOnlyReason, dataContextResolution, activeDataSlots, dataGroups, dataContextExtensions, dataPreview, setPackValidationNonce, packValidationKey, packValidationCurrent, packValidationLayers, previewDataRole, cancelDataInstall, installDataPack, cancelResearchSuiteInstall, installResearchSuite, openResearchSuiteStudy, copyDraftDataPack, upload } = useWorkbench();
  const sections = useMemo(() => DATA_PAGE_SECTIONS.map((section) => ({ id: section.id, label: t(section.label) })), [t]);
  const packBytes = Object.values(dataContextPack?.bindings ?? {}).reduce((sum, item) => sum + item.bytes, 0);
  const packLocked = workspace.projects.some((project) => project.data_pack_id === dataContextPackId);
  const dataInstallReason = !dataBundle ? t("data.install.needFile") : !dataRights ? t("data.install.needRights") : undefined;
  const suiteInstallReason = !researchSuiteBundle ? t("data.suite.needFile") : !researchSuiteRights ? t("data.suite.needRights") : undefined;
  return <div className="page data-page">
    <PageHeader headingLevel={2} title={dataContextPack ? modelDisplayName(dataContextPack.name) : t("data.page.choosePack")} description={t("data.page.description")}
      actions={dataContextPack ? <div className="pack-id"><span>{t("data.page.packId")}</span><code>{dataContextPack.id}</code><small>{dataContextPack.country} · {dataContextPack.timezone} · {formatBytes(packBytes)}</small></div> : undefined} />
    <SectionNav label={t("data.nav.label")} sections={sections} />

    <section className="page-section" id="data-inputs" aria-label={t("data.nav.inputs")}>
      {activePath === "data" && <section className="panel journey-return"><div><b>{t("data.journeyReturn.title")}</b><p>{t("data.journeyReturn.body")}</p></div><Button onClick={() => setView("journey")}>{t("data.journeyReturn.action")}</Button></section>}
      {isJourneyData && <JourneyDataEditor
        sourceName={journeySource?.name ?? t("data.journey.baselineUnavailable")} sourcePackName={journeySourcePack?.name ?? ""}
        targetPack={dataContextPack} sourceBindings={journeySourcePack?.bindings ?? {}}
        slots={activeDataSlots.filter((slot) => !journeyNetworkPackId || !slot.role.startsWith("value.zonal."))}
        networkPackId={journeyNetworkPackId} modelStartYear={journeySource?.start_year}
        readOnlyReason={journeyReadOnlyReason || (!dataContextResolution ? t("data.journey.resolving") : "")}
        busy={Boolean(uploading)} onUpload={(role, file) => void upload(role, file)}
        onMapped={async () => { setPreflight(null); setSavedDataResolution(null); await refresh(); }}
        onPreview={(role) => void previewDataRole(role)} onReturn={() => setView("journey")} />}
      <section className="panel data-context">
        <div><span>{t("data.context.label")}</span><select aria-label={t("data.context.aria")} value={dataContextId} onChange={(event) => { setDataContextId(event.target.value); setSavedDataResolution(null); setDataPreview(null); }}>
          {isJourneyData && <option value="journey">{t("data.context.journey", { name: dataContextPack?.name ?? t("data.context.notChosen") })}</option>}
          <option value="draft">{t("data.context.draft")}</option>
          {dataContextId !== "draft" && !isJourneyData && !dataContextProject && <option value={dataContextId}>{t("data.context.unavailable", { id: dataContextId })}</option>}
          {workspace.projects.map((project) => <option value={project.id} key={project.id}>{t("data.context.study", { name: project.name, revision: project.revision_number ?? 0 })}</option>)}
        </select></div>
        <div><strong>{dataContextResolution ? `${dataContextResolution.data_readiness.available}/${dataContextResolution.data_readiness.required}` : t("data.context.notEvaluated")}</strong><span>{inputsPresentSuffix(worstStatus(packValidationLayers), t)}</span></div>
        {dataContextPackId && <a className={buttonClass("secondary", "md")} href={`${API}/data-packs/${encodeURIComponent(dataContextPackId)}/missing-checklist?extensions=${encodeURIComponent(dataContextExtensions.join(","))}&format=json`}>{t("data.context.checklist")}</a>}
      </section>
      {dataContextPack && <DataPackValidationPanel key={dataContextPack.id} packId={dataContextPack.id} report={packValidationCurrent?.report} cached={dataContextPack.plausibility_status} loading={Boolean(packValidationKey) && !packValidationCurrent} error={packValidationCurrent?.error} onRetry={() => setPackValidationNonce((value) => value + 1)} />}
      {dataContextId === "draft" && <section className="panel data-draft" aria-labelledby="data-draft-title">
        <div className="data-draft-pack"><b id="data-draft-title" className="data-draft-title">{t("data.draft.title")}</b><select className="v-input v-select" aria-label={t("data.draft.aria")} value={selectedPackId} disabled={copyingDraftPack} onChange={(event) => { setSelectedPackId(event.target.value); setDraftResolution(null); setPreflight(null); setDataPreview(null); }}>
          {workspace.data_packs.filter((pack) => pack.data_pack_type !== "network_overlay").map((pack) => <option key={pack.id} value={pack.id}>{pack.name} · {pack.id}</option>)}
        </select><small>{t("data.draft.hint")}</small></div>
        <div className="data-draft-copy"><TextField label={t("data.draft.copyName")} value={draftPackCopyName} disabled={copyingDraftPack} onChange={setDraftPackCopyName} placeholder={t("data.draft.copyPlaceholder")} />
          <Button disabled={!online || !dataContextPack?.manifest_sha256 || !draftPackCopyName.trim()} disabledReason={t("data.draft.copyUnavailable")} loading={copyingDraftPack} onClick={() => void copyDraftDataPack()}>{copyingDraftPack ? t("data.draft.copying") : t("data.draft.copy")}</Button></div>
        <div className="data-draft-actions"><Button variant="ghost" onClick={() => { setComposerInitialStep(5); setView("projects"); }}>{t("data.draft.returnToReview")}</Button></div>
        {draftResolving && <p role="status">{t("data.draft.rechecking")}</p>}
      </section>}
      {dataContextId !== "draft" && !isJourneyData && !dataContextProject && <p className="info-box" role="status">{t("data.context.linkedUnavailable")}</p>}
      {!isJourneyData && <div className="data-groups">{dataGroups.map((group) => <section className="panel" key={group}>
        <div className="panel-head"><div><span>{t("data.group.inputs", { group })}</span><h3>{group === "PSM" ? t("data.group.psm") : group === "CEM" ? t("data.group.cem") : t("data.group.conditional", { group })}</h3></div><Badge tone="blue">{t("data.group.interfaces", { count: activeDataSlots.filter((slot) => slot.group === group).length })}</Badge></div>
        <div className="dataset-table expanded-dataset-table">{activeDataSlots.filter((slot) => slot.group === group).map((slot) => {
          const binding = dataContextPack?.bindings[slot.role];
          const validation = binding?.validation;
          const supported = slot.supported_formats?.length ? slot.supported_formats : slot.formats;
          const uploadDisabled = Boolean(uploading) || !dataContextPack || packLocked;
          return <div className="dataset-row" key={slot.role}>
            <span className={`slot-state ${binding ? "bound" : ""}`} aria-hidden="true">{binding ? "✓" : "·"}</span>
            <span className="slot-name"><b>{modelDisplayName(slot.label)}</b><code>{slot.role}</code><small>{slot.source === "extension" ? `${slot.owner_extension ?? t("data.role.extensionOwner")} · ${slot.capability ?? t("data.role.declaredCapability")}` : t("data.role.baseContract")}</small></span>
            <span className="slot-format"><small>{t("data.role.parser", { requirement: slot.required ? t("data.role.required") : t("data.role.optional"), formats: supported.join(" / ") })}</small>{supported.join("/") !== slot.formats.join("/") && <em>{t("data.role.manifestAccepts", { formats: slot.formats.join(" / ") })}</em>}<b>{slot.unit || t("data.role.unitBySource")}</b>{slot.time_semantics && <em>{slot.time_semantics}</em>}</span>
            <span className="slot-file">{binding ? <><b>{binding.filename}</b><small>{t("data.role.bindingSize", { size: formatBytes(binding.bytes), sha: binding.sha256.slice(0, 12) })}</small><small>{t("data.role.bindingRevision", { revision: (binding.binding_revision ?? binding.sha256).slice(0, 12), status: validation?.status ?? t("data.role.validatedAtPreflight") })}</small>{binding.licence && <small>{binding.licence}</small>}</> : <><b>{t("data.role.noFile")}</b><small>{slot.template_available ? t("data.role.chooseOrTemplate") : t("data.role.connectSupported")}</small></>}</span>
            <div className="dataset-actions">
              {slot.template_available && <a className="text-button" href={`${API}/data-contracts/${encodeURIComponent(slot.role)}/template`}>{t("data.role.template")}</a>}
              {binding && <Button size="sm" variant="ghost" disabled={dataPreviewLoading === slot.role} loading={dataPreviewLoading === slot.role} onClick={() => void previewDataRole(slot.role)}>{dataPreviewLoading === slot.role ? t("data.role.reading") : t("data.role.preview")}</Button>}
              <label className={`upload ${uploading === slot.role ? "busy" : ""}`} title={packLocked ? t("data.role.uploadLocked") : undefined}><input type="file" accept={supported.map((format) => `.${format}`).join(",")} onChange={(event) => void upload(slot.role, event.target.files?.[0])} disabled={uploadDisabled} />{uploading === slot.role ? t("data.role.importing") : binding ? t("data.role.replace") : t("data.role.chooseFile")}</label>
            </div>
          </div>;
        })}</div>
      </section>)}</div>}
      {dataPreview && <DataPreviewPanel preview={dataPreview} onClose={() => setDataPreview(null)} />}
    </section>

    <section className="page-section" id="data-install" aria-label={t("data.nav.install")}>
      <section className="panel module-installer data-bundle-installer">
        <div className="module-installer-copy"><span>{t("data.install.eyebrow")}</span><h3>{t("data.install.title")}</h3><p>{t("data.install.body", { schema: "value.data-bundle/v1" })}</p><small>{t("data.install.prefixNote")}</small></div>
        <div className="module-installer-form">
          <FileDrop className="module-file" label={t("data.install.file")} accept=".zip,application/zip" disabled={dataInstalling} prompt={t("data.install.choose")} onFiles={(files) => setDataBundle(files[0] ?? null)} hint={dataBundle ? t("data.install.selected", { size: formatBytes(dataBundle.size) }) : undefined} />
          <label className="trust-check"><input type="checkbox" checked={dataRights} onChange={(event) => setDataRights(event.target.checked)} /><span>{t("data.install.rights")}</span></label>
          {dataInstalling && <div className="bundle-progress" role="progressbar" aria-label={t("data.install.progress")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(dataInstallProgress)}><Progress stage={dataInstallPhase === "uploading" ? t("data.install.uploadingStage") : t("data.install.verifyingStage")} value={dataInstallPhase === "uploading" ? `${Math.round(dataInstallProgress)}%` : t("data.install.uploadComplete")} /><i><em style={{ width: `${dataInstallProgress}%` }} /></i></div>}
          <div className="bundle-actions"><Button variant="primary" disabled={!dataBundle || !dataRights} disabledReason={dataInstallReason} loading={dataInstalling} onClick={installDataPack}>{dataInstalling ? dataInstallPhase === "uploading" ? t("data.install.uploading") : t("data.install.verifying") : t("data.install.action")}</Button>{dataInstalling && dataInstallPhase === "uploading" && <Button onClick={cancelDataInstall}>{t("data.install.cancel")}</Button>}</div>
          <details><summary>{t("data.install.builders")}</summary><code>{DATA_BUNDLE_COMMAND}</code></details>
        </div>
      </section>
      <section className="panel module-installer data-bundle-installer research-suite-installer">
        <div className="module-installer-copy"><span>{t("data.suite.eyebrow")}</span><h3>{t("data.suite.title")}</h3><p>{t("data.suite.body")}</p><small>{t("data.suite.caution")}</small></div>
        <div className="module-installer-form">
          <FileDrop className="module-file" label={t("data.suite.file")} accept=".zip,application/zip" disabled={researchSuiteInstalling} prompt={t("data.suite.choose")} onFiles={(files) => setResearchSuiteBundle(files[0] ?? null)} hint={researchSuiteBundle ? t("data.suite.selected", { size: formatBytes(researchSuiteBundle.size) }) : undefined} />
          <label className="trust-check"><input type="checkbox" checked={researchSuiteRights} onChange={(event) => setResearchSuiteRights(event.target.checked)} /><span>{t("data.suite.rights")}</span></label>
          {researchSuiteInstalling && <div className="bundle-progress" role="progressbar" aria-label={t("data.suite.progress")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(researchSuiteInstallProgress)}><Progress stage={researchSuiteInstallPhase === "uploading" ? t("data.install.uploadingStage") : t("data.suite.verifyingStage")} value={researchSuiteInstallPhase === "uploading" ? `${Math.round(researchSuiteInstallProgress)}%` : t("data.install.uploadComplete")} /><i><em style={{ width: `${researchSuiteInstallProgress}%` }} /></i></div>}
          <div className="bundle-actions"><Button variant="primary" disabled={!researchSuiteBundle || !researchSuiteRights} disabledReason={suiteInstallReason} loading={researchSuiteInstalling} onClick={installResearchSuite}>{researchSuiteInstalling ? researchSuiteInstallPhase === "uploading" ? t("data.install.uploading") : t("data.suite.installing") : t("data.suite.action")}</Button>{researchSuiteInstalling && researchSuiteInstallPhase === "uploading" && <Button onClick={cancelResearchSuiteInstall}>{t("data.install.cancel")}</Button>}</div>
        </div>
      </section>
      {researchSuiteSummary && <section className="panel research-suite-result" role="status"><div className="panel-head"><div><span>{t("data.suite.resultEyebrow")}</span><h3>{researchSuiteSummary.suiteId}</h3></div><Badge tone="good">{t("data.suite.verifiedBadge")}</Badge></div>
        <p><b>{t("data.suite.noRun")}</b> {t("data.suite.next")}</p>
        <div className="dataset-table">{researchSuiteSummary.components.map((component) => <div className="dataset-row" key={component.id}><span className="slot-state bound" aria-hidden="true">✓</span><span className="slot-name"><b>{component.id}</b><small>{t("data.suite.component")}</small></span><span className="slot-file"><small>{t("data.suite.bundleSha")}</small><Hash value={component.sha256} /></span></div>)}</div>
        <small>{t("data.suite.suiteSha")}: <Hash value={researchSuiteSummary.suiteSha256} /></small>
        <div className="bundle-actions"><Button onClick={() => openResearchSuiteStudy(researchSuiteSummary.studyIds[0])}>{t("data.suite.openCopperplate")}</Button><Button onClick={() => openResearchSuiteStudy(researchSuiteSummary.studyIds[1])}>{t("data.suite.openZonal")}</Button></div>
      </section>}
      {dataContextPack?.installation && <div className="reference-strip"><div><span>{t("data.installed.label")}</span><b>{t("data.installed.verified")}</b><small>{t("data.installed.detail", { size: formatBytes(dataContextPack.installation.bundle_bytes), at: dataContextPack.installation.installed_at })} · <Hash value={dataContextPack.installation.bundle_sha256} label="SHA-256" /></small></div><div><span>{t("data.installed.boundary")}</span><b>{t("data.installed.noExecutable")}</b><small>{dataContextPack.installation.installation_boundary.replaceAll("_", " ")}</small></div></div>}
      <div className="reference-strip"><div><span>{t("data.reference.carbonLabel")}</span><b>{t("data.reference.carbonTitle")}</b><small>{t("data.reference.carbonBody")}</small></div><div><span>{t("data.reference.networkLabel")}</span><b>{t("data.reference.networkTitle")}</b><small>{t("data.reference.networkBody")}</small></div></div>
      <div className="domain-boundaries"><div><b>{t("data.boundary.hydroTitle")}</b><span>{t("data.boundary.hydroBody")}</span></div><div><b>{t("data.boundary.networkTitle")}</b><span>{t("data.boundary.networkBody")}</span></div></div>
    </section>

    {/* R-11 (P1-polish): an anchor, not a second landmark named like the Data Workbench section inside it. */}
    <div className="page-section" id="data-workbench-section">
      <DataWorkbench onWorkspaceChanged={async () => { setPreflight(null); setSavedDataResolution(null); await refresh(); }} />
    </div>

    <section className="page-section" id="data-adapters" aria-label={t("data.nav.adapters")}>
      <AdapterGuide />
    </section>
  </div>;
}
