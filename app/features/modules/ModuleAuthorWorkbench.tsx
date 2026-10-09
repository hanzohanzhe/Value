"use client";

import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useEffect, useRef, useState } from "react";
import { Button } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
import type { Translate } from "../../i18n/index.ts";
import { LocalizedError, messageOf, showMessage, type LocalizedMessage } from "../shared/localizedMessage.ts";
import { isAuthorDraftResolution, isAuthoringDetail, record, type AuthorDraftResolution, type AuthoringDetail, type AuthorModule, type AuthorStudy } from "./module-authoring.types";
import { derivationNotes } from "./derivationNotes.ts";
import "./ModuleAuthorWorkbench.css";

/** The backend's error text (with its code) as sent, or the given dictionary message. */
function failure(body: unknown, fallback: LocalizedError): Error {
  return record(body) && typeof body.error === "string"
    ? new Error(`${typeof body.error_code === "string" ? `${body.error_code}: ` : ""}${body.error}`) : fallback;
}

function useAuthoring(module?: AuthorModule) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ key: string; detail?: AuthoringDetail; error?: LocalizedMessage }>();
  const id = module?.id, version = module?.version, slot = module?.slot;
  const key = JSON.stringify([id, version, slot, attempt]);
  useEffect(() => {
    if (!id) return;
    const abort = new AbortController();
    void (async () => {
      try {
        const response = await apiFetch(apiUrl(`modules/${encodeURIComponent(id)}/authoring`), { signal: abort.signal, cache: "no-store" });
        const body: unknown = await response.json();
        if (!response.ok) throw failure(body, new LocalizedError("moduleAuthor.detailFailed", { status: response.status }));
        if (!isAuthoringDetail(body)) throw new LocalizedError("moduleAuthor.detailSchema");
        if (body.module_id !== id || body.identity.module_version !== version || body.identity.slot !== slot)
          throw new LocalizedError("moduleAuthor.identityChanged");
        if (!abort.signal.aborted) setState({ key, detail: body });
      } catch (error) {
        if (!abort.signal.aborted) setState({ key, error: messageOf(error, "moduleAuthor.cannotInspect") });
      }
    })();
    return () => abort.abort();
  }, [id, version, slot, key]);
  return { detail: state?.key === key ? state.detail : undefined, error: state?.key === key ? state.error : undefined,
    loading: Boolean(id && state?.key !== key), refresh: () => setAttempt(current => current + 1) };
}

function Fields({ title, values, t }: { title: string; values: string[]; t: Translate }) {
  return <div className="author-fields"><b>{title}</b><div>{values.length ? values.map(value => <code key={value}>{value}</code>) : <span>{t("moduleAuthor.noneDeclared")}</span>}</div></div>;
}

function ModuleDetails({ detail, t }: { detail: AuthoringDetail; t: Translate }) {
  const { identity, manifest, conformance } = detail;
  return <div className="author-detail">
    <div className="author-facts"><span><small>{t("moduleAuthor.identity")}</small><b>{identity.module_id} · {identity.module_version}</b></span><span><small>{t("moduleAuthor.contractSlot")}</small><code>{identity.contract_version} / {identity.slot}</code></span><span><small>{t("moduleAuthor.entryPoint")}</small><code>{identity.entry_point}</code></span><span><small>{t("moduleAuthor.sourceSha")}</small><code>{identity.source_sha256 ?? t("moduleAuthor.unavailable")}</code></span><span><small>{t("moduleAuthor.scientificVersion")}</small><b>{identity.scientific_version ?? t("moduleAuthor.notDeclared")}</b></span><span><small>{t("moduleAuthor.execution")}</small><b>{identity.execution_kind} / {manifest.determinism}</b></span></div>
    <div className="author-contract"><Fields t={t} title={t("moduleAuthor.inputs")} values={manifest.inputs} /><Fields t={t} title={t("moduleAuthor.outputs")} values={manifest.outputs} /><Fields t={t} title={t("moduleAuthor.stateReads")} values={manifest.state_reads} /><Fields t={t} title={t("moduleAuthor.stateWrites")} values={manifest.state_writes} /><Fields t={t} title={t("moduleAuthor.parameters")} values={manifest.parameters} /><Fields t={t} title={t("moduleAuthor.requiredCapabilities")} values={manifest.requires_capabilities} /><Fields t={t} title={t("moduleAuthor.providedCapabilities")} values={manifest.provides_capabilities} /><Fields t={t} title={t("moduleAuthor.artifacts")} values={manifest.artifacts} /><Fields t={t} title={t("moduleAuthor.methods")} values={detail.methods} /><Fields t={t} title={t("moduleAuthor.units")} values={Object.entries(manifest.units).map(([field, unit]) => `${field}: ${unit}`)} /></div>
    <div className="author-reports"><div><small>{t("moduleAuthor.structuralCheck")}</small><b>{conformance.status}</b><span>{t("moduleAuthor.origin", { origin: conformance.origin ?? t("moduleAuthor.notRecorded") })}</span>{conformance.status === "not_run" && <span>{t("moduleAuthor.noReport")}</span>}</div><div><small>{t("moduleAuthor.scientificValidation")}</small><b>{conformance.scientific_validation_status}</b><span>{t("moduleAuthor.scientificNote")}</span></div></div>
    {conformance.errors.length > 0 && <div className="author-message error"><b>{t("moduleAuthor.contractErrors")}</b><ul>{conformance.errors.map((message, index) => <li key={index}>{message}</li>)}</ul></div>}
    {conformance.warnings.length > 0 && <div className="author-message"><b>{t("moduleAuthor.contractWarnings")}</b><ul>{conformance.warnings.map((message, index) => <li key={index}>{message}</li>)}</ul></div>}
    <details><summary>{t("moduleAuthor.inspectSource")}</summary>{detail.source.available ? <><p>{detail.source.filename}{detail.source.truncated ? ` · ${t("moduleAuthor.truncated")}` : ""}</p><pre>{detail.source.content}</pre></> : <p className="author-message">{t("moduleAuthor.sourceUnavailable", { reason: detail.source.reason ?? t("moduleAuthor.noReadableSource") })}</p>}</details>
  </div>;
}

export default function ModuleAuthorWorkbench({ modules, projects, onCreated, onInstallRequest }: {
  modules: AuthorModule[]; projects: AuthorStudy[];
  onCreated: (project: { id: string; notes?: string[] }) => void; onInstallRequest: () => void;
}) {
  const t = useT();
  const [slotSelection, setSlotSelection] = useState("");
  const [moduleSelection, setModuleSelection] = useState("");
  const [comparisonSelection, setComparisonSelection] = useState("");
  const [sourceSelection, setSourceSelection] = useState("");
  const [studyName, setStudyName] = useState("My module experiment");
  const [newModuleId, setNewModuleId] = useState("");
  const [newVersion, setNewVersion] = useState("0.1.0");
  const [explicitAcks, setExplicitAcks] = useState<{ key: string; values: Record<string, string> }>({ key: "", values: {} });
  const [draft, setDraft] = useState<{ key: string; ackKey: string; resolution?: AuthorDraftResolution; error?: LocalizedMessage }>();
  const [saved, setSaved] = useState<{ key: string; id?: string; error?: LocalizedMessage }>();
  const [savingKey, setSavingKey] = useState("");
  const saveAbort = useRef<AbortController | null>(null);
  const slots = [...new Set(modules.map(module => module.slot))].sort();
  const slot = slots.includes(slotSelection) ? slotSelection : slots[0] ?? "";
  const options = modules.filter(module => module.slot === slot);
  const candidate = options.find(module => module.id === moduleSelection) ?? options[0];
  const compared = options.find(module => module.id === comparisonSelection && module.id !== candidate?.id);
  const source = projects.find(project => project.id === sourceSelection);
  const candidateInfo = useAuthoring(candidate);
  const comparisonInfo = useAuthoring(compared);
  const detail = candidateInfo.detail;
  const candidateId = detail?.module_id;
  const candidateVersion = detail?.identity.module_version;
  const candidateContract = detail?.identity.contract_version;
  const sourceModule = source?.modules[slot];
  const ackKey = JSON.stringify([source?.id, source?.revision_sha256, slot, detail?.identity_sha256]);
  const userAcks = explicitAcks.key === ackKey ? explicitAcks.values : {};
  const sourceAcks = { ...source?.maturity_acknowledgements };
  if (detail) {
    delete sourceAcks[`module:${detail.module_id}@${detail.identity.module_version}`];
    delete sourceAcks[`solver-contract:${detail.module_id}@${detail.identity.module_version}`];
  }
  const mergedAcks = { ...sourceAcks, ...userAcks };
  const draftBody = source && detail ? {
    schema_version: "value.study-draft/v1", name: studyName.trim(), purpose: source.purpose ?? "",
    data_pack_id: source.data_pack_id, start_year: source.start_year, end_year: source.end_year,
    modules: { ...source.modules, [slot]: detail.module_id }, parameters: source.parameters ?? {},
    runtime_options: source.runtime_options ?? {}, selected_extensions: source.selected_extensions ?? [],
    extension_parameters: source.extension_parameters ?? {}, maturity_acknowledgements: mergedAcks,
    market_configuration: source.market_configuration ?? {}, ...(source.solver_contract ? { solver_contract: source.solver_contract } : {}),
  } : undefined;
  const draftBodyText = draftBody ? JSON.stringify(draftBody) : "";
  const draftKey = JSON.stringify([source?.id, source?.revision_sha256, detail?.identity_sha256, draftBodyText]);
  const canResolve = Boolean(detail && source?.revision_sha256 && sourceModule && sourceModule !== detail.module_id);
  const resolution = draft?.key === draftKey ? draft.resolution : undefined;
  const draftError = draft?.key === draftKey ? draft.error : undefined;
  const resolving = canResolve && draft?.key !== draftKey;
  const compatibility = resolution?.compatible_modules[slot]?.find(module => module.id === detail?.module_id);
  const saving = savingKey === draftKey;
  const requirements = draft?.ackKey === ackKey ? draft.resolution?.maturity.acknowledgements_required.filter(item => item.id === detail?.module_id && item.version === candidateVersion) ?? [] : [];
  const solverAck = source && detail && slot === "balancing" && record(source.solver_contract) && source.solver_contract.requires_acknowledgement === true
    && record(detail.manifest.solver_contract) && Object.keys(detail.manifest.solver_contract).length > 0
    ? { key: `solver-contract:${detail.module_id}@${detail.identity.module_version}`, acknowledgement: "value.solver-contract-ack/v1" } : undefined;
  const acknowledged = requirements.every(item => userAcks[item.key] === item.acknowledgement)
    && (!solverAck || userAcks[solverAck.key] === solverAck.acknowledgement);
  const canSave = Boolean(canResolve && detail?.conformance.status !== "failed" && detail?.identity.source_sha256 && resolution?.valid && compatibility?.compatible && acknowledged && studyName.trim() && !saving);
  const templateId = newModuleId || (detail ? `draft-${detail.module_id.slice(0, 58)}` : "");
  const validTemplate = /^[a-z][a-z0-9-]{2,63}$/.test(templateId) && /^\d+\.\d+\.\d+$/.test(newVersion) && !modules.some(module => module.id === templateId);

  useEffect(() => {
    if (!canResolve || !draftBodyText) return;
    const abort = new AbortController();
    void (async () => {
      try {
        const response = await apiFetch(apiUrl("projects/resolve-draft"), { method: "POST", headers: { "Content-Type": "application/json" }, body: draftBodyText, signal: abort.signal, cache: "no-store" });
        const body: unknown = await response.json();
        if (!response.ok) throw failure(body, new LocalizedError("moduleAuthor.compatibilityFailed", { status: response.status }));
        if (!isAuthorDraftResolution(body)) throw new LocalizedError("moduleAuthor.compatibilitySchema");
        const resolvedCandidate = body.graph_preview?.modules?.[slot];
        if (body.valid && !resolvedCandidate) throw new LocalizedError("moduleAuthor.omittedIdentity");
        if (resolvedCandidate && (resolvedCandidate.module_id !== candidateId || resolvedCandidate.module_version !== candidateVersion || resolvedCandidate.contract_version !== candidateContract))
          throw new LocalizedError("moduleAuthor.differentIdentity");
        if (!abort.signal.aborted) setDraft({ key: draftKey, ackKey, resolution: body });
      } catch (error) {
        if (!abort.signal.aborted) setDraft({ key: draftKey, ackKey, error: messageOf(error, "moduleAuthor.cannotResolve") });
      }
    })();
    return () => abort.abort();
  }, [canResolve, draftBodyText, draftKey, candidateId, candidateVersion, candidateContract, slot, ackKey]);

  useEffect(() => () => { saveAbort.current?.abort(); }, [draftKey]);

  function acknowledge(key: string, value: string, checked: boolean) {
    const values = { ...userAcks };
    if (checked) values[key] = value; else delete values[key];
    setExplicitAcks({ key: ackKey, values });
  }
  async function createStudy() {
    if (!canSave || !source?.revision_sha256 || !detail) return;
    saveAbort.current?.abort();
    const abort = new AbortController(); saveAbort.current = abort;
    setSavingKey(draftKey); setSaved(undefined);
    try {
      const response = await apiFetch(apiUrl(`projects/${encodeURIComponent(source.id)}/derive`), {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: abort.signal,
        body: JSON.stringify({ intent: "edit_module", name: studyName.trim(), data_pack_id: source.data_pack_id,
          source_revision_sha256: source.revision_sha256, slot, module_id: detail.module_id,
          candidate_identity_sha256: detail.identity_sha256, maturity_acknowledgements: userAcks }),
      });
      const body: unknown = await response.json();
      if (!response.ok) throw failure(body, new LocalizedError("moduleAuthor.deriveFailed", { status: response.status }));
      if (!record(body) || body.ok !== true || body.run_started !== false || !record(body.project)
        || typeof body.project.id !== "string" || !body.project.id || body.project.id === source.id)
        throw new LocalizedError("moduleAuthor.deriveUnconfirmed");
      if (!abort.signal.aborted) { setSaved({ key: draftKey, id: body.project.id }); onCreated({ id: body.project.id, notes: derivationNotes(body, t) }); }
    } catch (error) {
      if (!abort.signal.aborted) setSaved({ key: draftKey, error: messageOf(error, "moduleAuthor.cannotSave") });
    } finally { if (!abort.signal.aborted) setSavingKey(""); }
  }

  const comparison = comparisonInfo.detail;
  const changedFields = detail && comparison ? [...new Set([...Object.keys(detail.manifest), ...Object.keys(comparison.manifest)])].filter(field => JSON.stringify(detail.manifest[field]) !== JSON.stringify(comparison.manifest[field])) : [];
  const sourcesText = !comparison ? "" : comparison.identity.source_sha256 == null || detail?.identity.source_sha256 == null ? t("moduleAuthor.sourcesUnavailable") : comparison.identity.source_sha256 === detail.identity.source_sha256 ? t("moduleAuthor.sourcesMatch") : t("moduleAuthor.sourcesDiffer");
  return <section id="module-author-workbench" className="panel module-author-workbench" aria-label={t("moduleAuthor.label")}>
    <header><small>{t("moduleAuthor.eyebrow")}</small><h3>{t("moduleAuthor.title")}</h3><p>{t("moduleAuthor.intro")}</p></header>
    <Button size="sm" variant="ghost" className="author-reload" disabled={saving || !candidate} onClick={candidateInfo.refresh}>{t("moduleAuthor.reload")}</Button>
    <div className="author-controls"><label>{t("moduleAuthor.slot")}<select aria-label={t("moduleAuthor.slotAria")} value={slot} disabled={saving} onChange={event => { setSlotSelection(event.target.value); setModuleSelection(""); setComparisonSelection(""); setNewModuleId(""); }}><option value="" disabled>{t("moduleAuthor.selectSlot")}</option>{slots.map(value => <option key={value}>{value}</option>)}</select></label><label>{t("moduleAuthor.candidate")}<select aria-label={t("moduleAuthor.candidateAria")} value={candidate?.id ?? ""} disabled={saving} onChange={event => { setModuleSelection(event.target.value); setNewModuleId(""); }}><option value="" disabled>{t("moduleAuthor.selectModule")}</option>{options.map(module => <option key={module.id} value={module.id}>{module.name} · {module.version}</option>)}</select></label></div>
    {!candidate && <p className="author-message">{t("moduleAuthor.noModule")}</p>}
    {candidateInfo.loading && <p role="status" className="author-message">{t("moduleAuthor.reading")}</p>}
    {candidateInfo.error && <p role="alert" className="author-message error">{showMessage(t, candidateInfo.error)} <Button size="sm" variant="ghost" onClick={candidateInfo.refresh}>{t("moduleAuthor.reloadDetails")}</Button></p>}
    {detail && <><ModuleDetails detail={detail} t={t} />{!detail.identity.source_sha256 && <p className="author-message error">{t("moduleAuthor.noSourceIdentity")}</p>}
      <section className="author-template"><h4>{t("moduleAuthor.templateTitle")}</h4><p>{t("moduleAuthor.templateIntro")}</p><div className="author-controls"><label>{t("moduleAuthor.newId")}<input aria-label={t("moduleAuthor.newIdAria")} value={templateId} onChange={event => setNewModuleId(event.target.value)} /></label><label>{t("moduleAuthor.newVersion")}<input aria-label={t("moduleAuthor.newVersionAria")} value={newVersion} onChange={event => setNewVersion(event.target.value)} /></label>{validTemplate ? <a className="text-button" href={apiUrl(`modules/${encodeURIComponent(detail.module_id)}/template?${new URLSearchParams({ module_id: templateId, version: newVersion })}`)}>{t("moduleAuthor.downloadTemplate")}</a> : <span className="author-message">{t("moduleAuthor.templateInvalid")}</span>}<Button onClick={onInstallRequest}>{t("moduleAuthor.openInstaller")}</Button></div><p>{slot === "storage_cost" ? t("moduleAuthor.storageTemplate") : t("moduleAuthor.slotTemplate")} {t("moduleAuthor.buildLocally")}</p><p>{t("moduleAuthor.noFormula")}</p></section>
      <section className="author-comparison"><h4>{t("moduleAuthor.compareTitle")}</h4><label>{t("moduleAuthor.reference")}<select aria-label={t("moduleAuthor.referenceAria")} value={compared?.id ?? ""} onChange={event => setComparisonSelection(event.target.value)}><option value="">{t("moduleAuthor.chooseReference")}</option>{options.filter(module => module.id !== detail.module_id).map(module => <option key={module.id} value={module.id}>{module.name} · {module.version}</option>)}</select></label>{comparisonInfo.loading && <p role="status">{t("moduleAuthor.readingReference")}</p>}{comparisonInfo.error && <p role="alert" className="author-message error">{showMessage(t, comparisonInfo.error)}</p>}{comparison && <><p>{t("moduleAuthor.comparison", { reference: comparison.module_id, referenceVersion: comparison.identity.module_version, candidate: detail.module_id, candidateVersion: detail.identity.module_version, sources: sourcesText })}</p><div className="author-table"><table><caption>{t("moduleAuthor.changedFields")}</caption><thead><tr><th scope="col">{t("moduleAuthor.field")}</th><th scope="col">{t("moduleAuthor.referenceColumn")}</th><th scope="col">{t("moduleAuthor.candidateColumn")}</th></tr></thead><tbody>{changedFields.map(field => <tr key={field}><th scope="row">{field}</th><td><code>{JSON.stringify(comparison.manifest[field]) ?? t("moduleAuthor.notDeclared")}</code></td><td><code>{JSON.stringify(detail.manifest[field]) ?? t("moduleAuthor.notDeclared")}</code></td></tr>)}</tbody></table></div>{!changedFields.length && <p>{t("moduleAuthor.noFieldsDiffer")}</p>}</>}</section>
    </>}
    <section className="author-study"><h4>{t("moduleAuthor.studyTitle")}</h4><div className="author-controls"><label>{t("moduleAuthor.sourceStudy")}<select aria-label={t("moduleAuthor.sourceStudyAria")} value={source?.id ?? ""} disabled={saving} onChange={event => setSourceSelection(event.target.value)}><option value="">{t("moduleAuthor.chooseStudy")}</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><label>{t("moduleAuthor.studyName")}<input aria-label={t("moduleAuthor.studyNameAria")} value={studyName} disabled={saving} onChange={event => setStudyName(event.target.value)} /></label></div>
      {source && <><div className="author-facts"><span><small>{t("moduleAuthor.sourceRevision")}</small><code>{source.revision_sha256 ?? t("moduleAuthor.noRevisionIdentity")}</code></span><span><small>{t("moduleAuthor.preservedPack")}</small><code>{source.data_pack_id}</code></span><span><small>{t("moduleAuthor.oneSlotChange")}</small><code>{slot}: {sourceModule ?? t("moduleAuthor.notInSource")} → {detail?.module_id ?? t("moduleAuthor.reviewFirst")}</code></span></div><p>{t("moduleAuthor.otherSettingsKept")}</p>{!source.revision_sha256 && <p className="author-message error">{t("moduleAuthor.needRevision")}</p>}{!sourceModule && <p className="author-message error">{t("moduleAuthor.slotNotUsed")}</p>}{sourceModule === detail?.module_id && <p className="author-message">{t("moduleAuthor.chooseDifferent")}</p>}</>}
      {resolving && <p role="status" className="author-message">{t("moduleAuthor.checking")}</p>}
      {draftError && <p role="alert" className="author-message error">{showMessage(t, draftError)}</p>}
      {resolution && <><p className={`author-message ${compatibility?.compatible ? "" : "error"}`}>{compatibility ? compatibility.compatible ? t("moduleAuthor.compatible") : t("moduleAuthor.incompatible", { reason: compatibility.reason ?? t("moduleAuthor.incompatibleDefault") }) : t("moduleAuthor.noCompatibility")}</p>{resolution.errors.length > 0 && <ul className="author-message error">{resolution.errors.map((issue, index) => <li key={index}><code>{issue.code}</code> {issue.message}</li>)}</ul>}{resolution.warnings.length > 0 && <ul className="author-message">{resolution.warnings.map((issue, index) => <li key={index}><code>{issue.code}</code> {issue.message}</li>)}</ul>}</>}{requirements.map(item => <label className="author-ack" key={item.key}><input type="checkbox" checked={userAcks[item.key] === item.acknowledgement} disabled={saving} onChange={event => acknowledge(item.key, item.acknowledgement, event.target.checked)} /><span>{t("moduleAuthor.acknowledge", { id: item.id, version: item.version, maturity: item.maturity })}</span></label>)}{solverAck && <label className="author-ack"><input type="checkbox" checked={userAcks[solverAck.key] === solverAck.acknowledgement} disabled={saving} onChange={event => acknowledge(solverAck.key, solverAck.acknowledgement, event.target.checked)} /><span>{t("moduleAuthor.acknowledgeSolver")}</span></label>}
      <Button variant="primary" className="author-create" disabled={!canSave} disabledReason={saving ? undefined : t("moduleAuthor.createUnavailable")} loading={saving} onClick={() => void createStudy()}>{saving ? t("moduleAuthor.creating") : t("moduleAuthor.create")}</Button>
      {saved?.key === draftKey && saved.error && <p role="alert" className="author-message error">{showMessage(t, saved.error)}</p>}{saved?.key === draftKey && saved.id && <p role="status" className="author-message">{t("moduleAuthor.created", { id: saved.id })}</p>}
    </section>
  </section>;
}
