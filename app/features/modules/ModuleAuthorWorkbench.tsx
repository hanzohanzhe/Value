"use client";

import { apiUrl } from "../shared/api";
import { useEffect, useRef, useState } from "react";
import { isAuthorDraftResolution, isAuthoringDetail, record, type AuthorDraftResolution, type AuthoringDetail, type AuthorModule, type AuthorStudy } from "./module-authoring.types";
import "./ModuleAuthorWorkbench.css";

function failure(body: unknown, fallback: string): string {
  return record(body) && typeof body.error === "string"
    ? `${typeof body.error_code === "string" ? `${body.error_code}: ` : ""}${body.error}` : fallback;
}

function useAuthoring(module?: AuthorModule) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ key: string; detail?: AuthoringDetail; error?: string }>();
  const id = module?.id, version = module?.version, slot = module?.slot;
  const key = JSON.stringify([id, version, slot, attempt]);
  useEffect(() => {
    if (!id) return;
    const abort = new AbortController();
    void (async () => {
      try {
        const response = await fetch(apiUrl(`modules/${encodeURIComponent(id)}/authoring`), { signal: abort.signal, cache: "no-store" });
        const body: unknown = await response.json();
        if (!response.ok) throw new Error(failure(body, `Module detail failed (${response.status})`));
        if (!isAuthoringDetail(body)) throw new Error("Module detail does not match value.module-authoring/v1.");
        if (body.module_id !== id || body.identity.module_version !== version || body.identity.slot !== slot)
          throw new Error("The registry identity changed. Refresh the workspace and review the module again.");
        if (!abort.signal.aborted) setState({ key, detail: body });
      } catch (error) {
        if (!abort.signal.aborted) setState({ key, error: error instanceof Error ? error.message : "Cannot inspect this module." });
      }
    })();
    return () => abort.abort();
  }, [id, version, slot, key]);
  return { detail: state?.key === key ? state.detail : undefined, error: state?.key === key ? state.error : undefined,
    loading: Boolean(id && state?.key !== key), refresh: () => setAttempt(current => current + 1) };
}

function Fields({ title, values }: { title: string; values: string[] }) {
  return <div className="author-fields"><b>{title}</b><div>{values.length ? values.map(value => <code key={value}>{value}</code>) : <span>None declared</span>}</div></div>;
}

function ModuleDetails({ detail }: { detail: AuthoringDetail }) {
  const { identity, manifest, conformance } = detail;
  return <div className="author-detail">
    <div className="author-facts"><span><small>Module identity</small><b>{identity.module_id} · {identity.module_version}</b></span><span><small>Contract / slot</small><code>{identity.contract_version} / {identity.slot}</code></span><span><small>Python entry point</small><code>{identity.entry_point}</code></span><span><small>Source SHA-256</small><code>{identity.source_sha256 ?? "Unavailable"}</code></span><span><small>Scientific version</small><b>{identity.scientific_version ?? "Not declared"}</b></span><span><small>Execution / determinism</small><b>{identity.execution_kind} / {manifest.determinism}</b></span></div>
    <div className="author-contract"><Fields title="Inputs" values={manifest.inputs} /><Fields title="Outputs" values={manifest.outputs} /><Fields title="State reads" values={manifest.state_reads} /><Fields title="State writes · declared responsibility" values={manifest.state_writes} /><Fields title="Parameters" values={manifest.parameters} /><Fields title="Required capabilities" values={manifest.requires_capabilities} /><Fields title="Provided capabilities" values={manifest.provides_capabilities} /><Fields title="Artifacts" values={manifest.artifacts} /><Fields title="Required Python methods" values={detail.methods} /><Fields title="Declared units" values={Object.entries(manifest.units).map(([field, unit]) => `${field}: ${unit}`)} /></div>
    <div className="author-reports"><div><small>Structural contract check</small><b>{conformance.status}</b><span>Origin: {conformance.origin ?? "Not recorded"}</span>{conformance.status === "not_run" && <span>No installation report matches the current manifest and source identity.</span>}</div><div><small>Scientific validation</small><b>{conformance.scientific_validation_status}</b><span>A callable shape or successful installation does not validate a physical method.</span></div></div>
    {conformance.errors.length > 0 && <div className="author-message error"><b>Contract errors</b><ul>{conformance.errors.map((message, index) => <li key={index}>{message}</li>)}</ul></div>}
    {conformance.warnings.length > 0 && <div className="author-message"><b>Contract warnings</b><ul>{conformance.warnings.map((message, index) => <li key={index}>{message}</li>)}</ul></div>}
    <details><summary>Inspect recorded Python source</summary>{detail.source.available ? <><p>{detail.source.filename}{detail.source.truncated ? " · bounded preview, truncated" : ""}</p><pre>{detail.source.content}</pre></> : <p className="author-message">Source unavailable: {detail.source.reason ?? "No readable source is provided."}</p>}</details>
  </div>;
}

export default function ModuleAuthorWorkbench({ modules, projects, onCreated, onInstallRequest }: {
  modules: AuthorModule[]; projects: AuthorStudy[];
  onCreated: (project: { id: string }) => void; onInstallRequest: () => void;
}) {
  const [slotSelection, setSlotSelection] = useState("");
  const [moduleSelection, setModuleSelection] = useState("");
  const [comparisonSelection, setComparisonSelection] = useState("");
  const [sourceSelection, setSourceSelection] = useState("");
  const [studyName, setStudyName] = useState("My module experiment");
  const [newModuleId, setNewModuleId] = useState("");
  const [newVersion, setNewVersion] = useState("0.1.0");
  const [explicitAcks, setExplicitAcks] = useState<{ key: string; values: Record<string, string> }>({ key: "", values: {} });
  const [draft, setDraft] = useState<{ key: string; ackKey: string; resolution?: AuthorDraftResolution; error?: string }>();
  const [saved, setSaved] = useState<{ key: string; id?: string; error?: string }>();
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
        const response = await fetch(apiUrl("projects/resolve-draft"), { method: "POST", headers: { "Content-Type": "application/json" }, body: draftBodyText, signal: abort.signal, cache: "no-store" });
        const body: unknown = await response.json();
        if (!response.ok) throw new Error(failure(body, `Compatibility check failed (${response.status})`));
        if (!isAuthorDraftResolution(body)) throw new Error("Compatibility response does not match value.study-draft-resolution/v1.");
        const resolvedCandidate = body.graph_preview?.modules?.[slot];
        if (body.valid && !resolvedCandidate) throw new Error("The valid response omitted its resolved candidate identity. Saving is unavailable.");
        if (resolvedCandidate && (resolvedCandidate.module_id !== candidateId || resolvedCandidate.module_version !== candidateVersion || resolvedCandidate.contract_version !== candidateContract))
          throw new Error("Compatibility resolved a different candidate identity. Review refreshed details before saving.");
        if (!abort.signal.aborted) setDraft({ key: draftKey, ackKey, resolution: body });
      } catch (error) {
        if (!abort.signal.aborted) setDraft({ key: draftKey, ackKey, error: error instanceof Error ? error.message : "Cannot resolve the candidate." });
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
      const response = await fetch(apiUrl(`projects/${encodeURIComponent(source.id)}/derive`), {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: abort.signal,
        body: JSON.stringify({ intent: "edit_module", name: studyName.trim(), data_pack_id: source.data_pack_id,
          source_revision_sha256: source.revision_sha256, slot, module_id: detail.module_id,
          candidate_identity_sha256: detail.identity_sha256, maturity_acknowledgements: userAcks }),
      });
      const body: unknown = await response.json();
      if (!response.ok) throw new Error(failure(body, `Study derivation failed (${response.status})`));
      if (!record(body) || body.ok !== true || body.run_started !== false || !record(body.project)
        || typeof body.project.id !== "string" || !body.project.id || body.project.id === source.id)
        throw new Error("The response did not confirm a new independent Study with no Run started. Refresh the workspace before retrying.");
      if (!abort.signal.aborted) { setSaved({ key: draftKey, id: body.project.id }); onCreated({ id: body.project.id }); }
    } catch (error) {
      if (!abort.signal.aborted) setSaved({ key: draftKey, error: error instanceof Error ? error.message : "Cannot save the Study." });
    } finally { if (!abort.signal.aborted) setSavingKey(""); }
  }

  const comparison = comparisonInfo.detail;
  const changedFields = detail && comparison ? [...new Set([...Object.keys(detail.manifest), ...Object.keys(comparison.manifest)])].filter(field => JSON.stringify(detail.manifest[field]) !== JSON.stringify(comparison.manifest[field])) : [];
  return <section id="module-author-workbench" className="panel module-author-workbench" aria-label="Module author workbench">
    <header><small>Edit module</small><h3>Inspect a module, then create a controlled method Study</h3><p>Review its contract, prepare and install a separate Python implementation, and replace one selected slot in an independent Study.</p></header>
    <button className="text-button" disabled={saving || !candidate} onClick={candidateInfo.refresh}>Reload reviewed module identity</button>
    <div className="author-controls"><label>Module slot<select aria-label="Author module slot" value={slot} disabled={saving} onChange={event => { setSlotSelection(event.target.value); setModuleSelection(""); setComparisonSelection(""); setNewModuleId(""); }}><option value="" disabled>Select a slot</option>{slots.map(value => <option key={value}>{value}</option>)}</select></label><label>Candidate module<select aria-label="Author candidate module" value={candidate?.id ?? ""} disabled={saving} onChange={event => { setModuleSelection(event.target.value); setNewModuleId(""); }}><option value="" disabled>Select a module</option>{options.map(module => <option key={module.id} value={module.id}>{module.name} · {module.version}</option>)}</select></label></div>
    {!candidate && <p className="author-message">No registered module is available. Install a reviewed local bundle to add one.</p>}
    {candidateInfo.loading && <p role="status" className="author-message">Reading the selected module identity and contract…</p>}
    {candidateInfo.error && <p role="alert" className="author-message error">{candidateInfo.error} <button className="text-button" onClick={candidateInfo.refresh}>Reload module details</button></p>}
    {detail && <><ModuleDetails detail={detail} />{!detail.identity.source_sha256 && <p className="author-message error">Candidate source identity is unavailable. The candidate cannot be saved into a controlled method Study.</p>}
      <section className="author-template"><h4>Prepare a separate implementation</h4><p>Use a new module ID and a new top-level Python package. Existing IDs and packages cannot be overwritten. Downloading a source project does not install or execute it.</p><div className="author-controls"><label>New module ID<input aria-label="Template module ID" value={templateId} onChange={event => setNewModuleId(event.target.value)} /></label><label>New version<input aria-label="Template module version" value={newVersion} onChange={event => setNewVersion(event.target.value)} /></label>{validTemplate ? <a className="text-button" href={apiUrl(`modules/${encodeURIComponent(detail.module_id)}/template?${new URLSearchParams({ module_id: templateId, version: newVersion })}`)}>Download editable source template</a> : <span className="author-message">Choose an unused module ID and a three-part version.</span>}<button className="secondary" onClick={onInstallRequest}>Open reviewed bundle installer</button></div><p>{slot === "storage_cost" ? "The storage-cost template offers a fixed GBP 42/MWh example. It is an experimental packaging example and has no scientific validation." : "This slot template declares the required methods and raises NotImplementedError until you implement them."} Build and review the ZIP locally before installation.</p><p>Formula editing is not available here. This workbench supports source templates and complete Python module development; the browser has no Python editor or execution environment.</p></section>
      <section className="author-comparison"><h4>Compare registered implementations in this slot</h4><label>Reference module<select aria-label="Author reference module" value={compared?.id ?? ""} onChange={event => setComparisonSelection(event.target.value)}><option value="">Choose a reference</option>{options.filter(module => module.id !== detail.module_id).map(module => <option key={module.id} value={module.id}>{module.name} · {module.version}</option>)}</select></label>{comparisonInfo.loading && <p role="status">Reading reference identity…</p>}{comparisonInfo.error && <p role="alert" className="author-message error">{comparisonInfo.error}</p>}{comparison && <><p>Reference {comparison.module_id} {comparison.identity.module_version} → candidate {detail.module_id} {detail.identity.module_version}. Source identities {comparison.identity.source_sha256 == null || detail.identity.source_sha256 == null ? "are unavailable" : comparison.identity.source_sha256 === detail.identity.source_sha256 ? "match" : "differ"}; this is an identity and manifest comparison. Review the Python source separately.</p><div className="author-table"><table><caption>Changed manifest fields</caption><thead><tr><th>Field</th><th>Reference</th><th>Candidate</th></tr></thead><tbody>{changedFields.map(field => <tr key={field}><th>{field}</th><td><code>{JSON.stringify(comparison.manifest[field]) ?? "Not declared"}</code></td><td><code>{JSON.stringify(detail.manifest[field]) ?? "Not declared"}</code></td></tr>)}</tbody></table></div>{!changedFields.length && <p>No manifest fields differ.</p>}</>}</section>
    </>}
    <section className="author-study"><h4>Create an independent Study with one method change</h4><div className="author-controls"><label>Source Study<select aria-label="Module source Study" value={source?.id ?? ""} disabled={saving} onChange={event => setSourceSelection(event.target.value)}><option value="">Choose a saved Study</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><label>New Study name<input aria-label="Module new Study name" value={studyName} disabled={saving} onChange={event => setStudyName(event.target.value)} /></label></div>
      {source && <><div className="author-facts"><span><small>Reviewed source revision</small><code>{source.revision_sha256 ?? "No saved revision identity"}</code></span><span><small>Preserved base data pack</small><code>{source.data_pack_id}</code></span><span><small>One slot change</small><code>{slot}: {sourceModule ?? "Not selected in the source"} → {detail?.module_id ?? "Review candidate details first"}</code></span></div><p>Other methods, data, parameters, years, network and solver settings remain the source configuration. This action saves a Study; it does not start a Run. A replacement requiring further changes must use a separate multi-method setup.</p>{!source.revision_sha256 && <p className="author-message error">Choose a Study with a saved revision before deriving a copy.</p>}{!sourceModule && <p className="author-message error">The source Study does not select this slot. Select a slot it already uses.</p>}{sourceModule === detail?.module_id && <p className="author-message">Choose a different installed implementation for this slot.</p>}</>}
      {resolving && <p role="status" className="author-message">Checking this source revision and candidate configuration…</p>}
      {draftError && <p role="alert" className="author-message error">{draftError}</p>}
      {resolution && <><p className={`author-message ${compatibility?.compatible ? "" : "error"}`}>{compatibility ? compatibility.compatible ? "Candidate is compatible with the declared graph. Review configuration checks below." : `Incompatible candidate: ${compatibility.reason ?? "The contract requirements cannot be resolved."}` : "Candidate compatibility was not returned; saving is unavailable."}</p>{resolution.errors.length > 0 && <ul className="author-message error">{resolution.errors.map((issue, index) => <li key={index}><code>{issue.code}</code> {issue.message}</li>)}</ul>}{resolution.warnings.length > 0 && <ul className="author-message">{resolution.warnings.map((issue, index) => <li key={index}><code>{issue.code}</code> {issue.message}</li>)}</ul>}</>}{requirements.map(item => <label className="author-ack" key={item.key}><input type="checkbox" checked={userAcks[item.key] === item.acknowledgement} disabled={saving} onChange={event => acknowledge(item.key, item.acknowledgement, event.target.checked)} /><span>I acknowledge {item.id} {item.version} is {item.maturity}; I will not present it as a scientifically validated baseline.</span></label>)}{solverAck && <label className="author-ack"><input type="checkbox" checked={userAcks[solverAck.key] === solverAck.acknowledgement} disabled={saving} onChange={event => acknowledge(solverAck.key, solverAck.acknowledgement, event.target.checked)} /><span>I explicitly acknowledge the preserved custom solver contract for this candidate version.</span></label>}
      <button className="primary" disabled={!canSave} onClick={() => void createStudy()}>{saving ? "Saving independent Study…" : "Create Study with this module"}</button>
      {saved?.key === draftKey && saved.error && <p role="alert" className="author-message error">{saved.error}</p>}{saved?.key === draftKey && saved.id && <p role="status" className="author-message">Created independent Study {saved.id}. No Run started. Open its Run page, review preflight, and compare results with the source baseline.</p>}
    </section>
  </section>;
}
