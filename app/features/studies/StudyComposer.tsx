"use client";

// The five-step Study composer (P1 spec 6.2).  Wording from the dictionaries
// (studies.*); numbers through NumberField (F4-02: clearing a box is "no value",
// never 0; out-of-range values are flagged at once and block saving); a new
// Study's name that maps to an existing ID is flagged while it is typed
// (F4-03); saved Studies show the revision hash, which covers the data pack
// (F4-04), and the module-graph hash only in their details.
import { useRef, useState, type ReactNode } from "react";
import type { Workspace } from "../shared/workspaceTypes";
import type { StudyForm, DraftResolution, Project, StudyTrashEntry, DomainPreset, Extension, MarketConfiguration } from "./types";
import type { TraceProfile } from "../market/TraceCoverageNotice";
import { copyDefaultZonalSolverContract, isBuiltinZonalSolverContract, withZonalSolverContractFlags, type ZonalSolverContract } from "../network/networkRedispatch";
import { Badge, labelFor } from "../shared/presentation";
import { useLocale, useT } from "../../i18n/LocaleProvider";
import { translator, type MessageKey } from "../../i18n/index.ts";
import { Hash, NumberField } from "../../ui";
import { ZONAL_SOLVER_ACK_KEY, ZONAL_SOLVER_ACK, validateZonalSolverContract, upgradeZonalSolverContract, withoutZonalSolverAcknowledgements } from "./solverContract";
import SolverSettingsEditor from "./SolverSettingsEditor";
import NetworkOverlaySelector from "./NetworkOverlaySelector";
import { dataPackAvailability, domainBadgeText, extensionAvailability, findProfile, moduleAvailability, profileOptionDescription, profileOptionLabel, type MethodologyCatalogue } from "./methodologyChoice.ts";
import { codeIdentityUpdate } from "./studyMigration.ts";
import { newStudyNameClash, saveDisabledReason } from "./studySave.ts";
import "./methodology-selector.css";
import "./studies.css";

/** Model years a Study may name (F4-02; the service checks the data pack's coverage). */
export const STUDY_YEAR_MIN = 2000;
export const STUDY_YEAR_MAX = 2100;

const STEP_KEYS: MessageKey[] = ["studies.step.identity", "studies.step.domain", "studies.step.optional", "studies.step.chain", "studies.step.review"];

export default function StudyComposer({
  initialStep = 1, workspace, form, selectedPackId, resolution, resolving, resolutionError,
  savedProjects, studyTrash, selectedProjectId, assumptions, onForm, onPack, onDomain,
  onExtension, onModule, onExtensionParameter, onAcknowledgement, onSave,
  onLoad, onOpenRun, onTrash, onRestore, onOpenTrashRuns, onOpenData, traceLevel, onTraceLevel,
  methodology, onMethodology, editingStudyName, saving = false, newStudy,
}: {
  initialStep?: number; workspace: Workspace; form: StudyForm; selectedPackId: string;
  resolution: DraftResolution | null; resolving: boolean; resolutionError: string;
  savedProjects: Project[]; studyTrash: StudyTrashEntry[]; selectedProjectId: string; assumptions: ReactNode;
  onForm: (update: (current: StudyForm) => StudyForm) => void;
  onPack: (id: string) => void; onDomain: (preset: DomainPreset) => void;
  onExtension: (extension: Extension, enabled: boolean) => void;
  onModule: (slot: string, moduleId: string) => void;
  onExtensionParameter: (name: string, value: unknown) => void;
  onAcknowledgement: (key: string, value: string, checked: boolean) => void;
  onSave: () => void; onLoad: (project: Project) => void; onOpenRun: (project: Project) => void;
  onTrash: (project: Project, linkedRunCount: number) => void;
  onRestore: (entry: StudyTrashEntry) => void;
  onOpenTrashRuns: (entry: StudyTrashEntry) => void;
  onOpenData: () => void;
  traceLevel: TraceProfile;
  onTraceLevel: (trace: TraceProfile) => void;
  /** Spec 7 / X0 S12: the methodology catalogue and the draft's profile; null while unavailable. */
  methodology?: { catalogue: MethodologyCatalogue | null; profileId: string | null; error?: string };
  onMethodology?: (profileId: string) => void;
  /** R-D11 / F-D6 (round R1-5): the saved Study being edited; the heading says so. */
  editingStudyName?: string;
  /** F4-03: a save is in progress (one request at a time). */
  saving?: boolean;
  /** True for a new Study (its name becomes its ID); defaults to "not editing a saved Study". */
  newStudy?: boolean;
}) {
  const t = useT();
  const { locale } = useLocale();
  const [step, setStep] = useState(initialStep);
  const [advanced, setAdvanced] = useState(false);
  const [saveBlock, setSaveBlock] = useState("");
  const panel = useRef<HTMLElement>(null);
  const domains = resolution?.system_domains ?? [];
  const visibleDomains = advanced ? domains : domains.filter((domain) =>
    domain.psm_module_id === "value-bid-at-cost-psm"
    || domain.psm_module_id === "value-staged-bid-at-cost-psm"
  );
  const selectedDomain = domains.find((item) => item.psm_module_id === form.modules.psm);
  const activeExtensions = workspace.extensions.filter((item) => form.selected_extensions.includes(item.id));
  const visibleExtensions = advanced ? workspace.extensions : workspace.extensions.filter((extension) =>
    selectedDomain?.required_extensions.includes(extension.id)
    || extension.provided_capabilities.some((capability) => capability.startsWith("domain.hydrology"))
  );
  const requirements = resolution?.maturity.acknowledgements_required ?? [];
  const extensionParameters = activeExtensions.flatMap((extension) => extension.parameters.map((parameter) => ({ extension, parameter })));
  const stagedMarket = Boolean(form.modules.balancing);
  const zonalBalancing = form.modules.balancing === "value-zonal-redispatch-balancing";
  const [customSolverEditorContract, setCustomSolverEditorContract] = useState<ZonalSolverContract | null>(
    form.solver_contract && !isBuiltinZonalSolverContract(form.solver_contract) ? form.solver_contract : null,
  );
  const solverContract = form.solver_contract ?? copyDefaultZonalSolverContract();
  const customSolverEditorEnabled = customSolverEditorContract === form.solver_contract
    || !isBuiltinZonalSolverContract(solverContract);
  const solverContractError = zonalBalancing ? validateZonalSolverContract(form.solver_contract) : "";
  const solverAcknowledged = form.maturity_acknowledgements[ZONAL_SOLVER_ACK_KEY] === ZONAL_SOLVER_ACK;
  const solverContractReady = !zonalBalancing || (
    !solverContractError
    && (!solverContract.requires_acknowledgement || solverAcknowledged)
  );
  const toggleCustomSolverSettings = (enabled: boolean) => {
    setCustomSolverEditorContract(enabled ? solverContract : null);
    if (!enabled) {
      onForm((current) => ({
        ...current,
        solver_contract: copyDefaultZonalSolverContract(),
        maturity_acknowledgements: withoutZonalSolverAcknowledgements(current.maturity_acknowledgements),
      }));
    }
  };
  const changeSolverContract = (candidate: ZonalSolverContract) => {
    const solver_contract = withZonalSolverContractFlags(candidate);
    setCustomSolverEditorContract(solver_contract);
    onForm((current) => ({
      ...current,
      solver_contract,
      maturity_acknowledgements: withoutZonalSolverAcknowledgements(current.maturity_acknowledgements),
    }));
  };
  const catalogue = methodology?.catalogue ?? null;
  const profile = findProfile(catalogue, methodology?.profileId);
  const unavailablePacks = workspace.data_packs.flatMap((pack) => { const verdict = dataPackAvailability(profile, pack.id, t); return verdict.available ? [] : [{ pack, reason: verdict.reason }]; });
  const selectedPackUnavailable = unavailablePacks.find((item) => item.pack.id === selectedPackId);
  const selectedPack = workspace.data_packs.find((pack) => pack.id === selectedPackId);
  const psmOptions = resolution?.compatible_modules.psm ?? [];
  // F4-03: a new Study takes its ID from its name; say so while the name is typed.
  const isNew = newStudy ?? !editingStudyName;
  const clash = isNew ? newStudyNameClash(form.name, savedProjects, studyTrash) : null;
  const yearsError = form.end_year < form.start_year ? t("studies.identity.yearsOrder") : "";
  const blockedReason = clash ? t("studies.review.blockedName") : yearsError ? t("studies.review.blockedYears") : "";
  // R-8 (P1-polish): a disabled save button says why (title and a line beside it).
  const saveReason = saveDisabledReason({ saving, resolving, blockedReason, resolution, solverContractReady }, t);
  const maturityLabel = (value: string) => value.replaceAll("_", " ");
  const save = () => {
    // F4-02: a box that holds an invalid number (flagged next to it) blocks saving.
    const invalid = panel.current?.querySelector<HTMLElement>('[aria-invalid="true"]');
    if (invalid) {
      setSaveBlock(t("studies.review.fixInvalid"));
      if (invalid.closest("[hidden]")) setAdvanced(true);
      window.setTimeout(() => invalid.focus(), 0);
      return;
    }
    setSaveBlock("");
    onSave();
  };
  return <div className="project-grid expanded-composer">
    <section ref={panel} className="panel form-panel composer-panel">
      <div className="panel-head"><div><span>{editingStudyName ? t("studies.composer.editing", { name: editingStudyName }) : t("studies.composer.new")}</span><h3>{t("studies.composer.title")}</h3></div><div className="view-toggle" role="group" aria-label={t("studies.composer.detail")}><button type="button" className={!advanced ? "active" : ""} aria-pressed={!advanced} onClick={() => setAdvanced(false)}>{t("studies.composer.basic")}</button><button type="button" className={advanced ? "active" : ""} aria-pressed={advanced} onClick={() => setAdvanced(true)}>{t("studies.composer.advanced")}</button></div></div>
      <ol className="composer-steps" aria-label={t("studies.composer.progress")}>{STEP_KEYS.map((label, index) => <li key={label} className={step === index + 1 ? "active" : step > index + 1 ? "complete" : ""}><button type="button" onClick={() => setStep(index + 1)} aria-current={step === index + 1 ? "step" : undefined}><i>{index + 1}</i><span>{t(label)}</span></button></li>)}</ol>
      {step === 1 && <div className="form-section composer-stage"><b>{t("studies.identity.heading")}</b><p>{t("studies.identity.lead")}</p>
        <label><span>{t("studies.identity.name")}</span><input value={form.name} aria-invalid={clash ? true : undefined} aria-describedby={clash ? "study-name-clash" : undefined} onChange={(event) => onForm((current) => ({ ...current, name: event.target.value }))} /></label>
        {clash && <p id="study-name-clash" className="study-name-clash" role="status">{t(clash.kind === "saved" ? "studies.identity.nameTaken" : "studies.identity.nameInTrash", { id: clash.id, suggestion: clash.suggestion })} <button type="button" className="text-button" onClick={() => onForm((current) => ({ ...current, name: clash.suggestion }))}>{t("studies.identity.useSuggestion", { suggestion: clash.suggestion })}</button></p>}
        <label><span>{t("studies.identity.purpose")}</span><textarea rows={3} value={form.purpose} placeholder={t("studies.identity.purposePlaceholder")} onChange={(event) => onForm((current) => ({ ...current, purpose: event.target.value }))} /></label>
        <div className="two-fields">
          <NumberField label={t("studies.identity.firstYear")} value={form.start_year} min={STUDY_YEAR_MIN} max={STUDY_YEAR_MAX} step={1} required onChange={(value, check) => { if (check.valid && value !== null) onForm((current) => ({ ...current, start_year: value })); }} />
          <NumberField label={t("studies.identity.finalYear")} value={form.end_year} min={STUDY_YEAR_MIN} max={STUDY_YEAR_MAX} step={1} required error={yearsError || undefined} onChange={(value, check) => { if (check.valid && value !== null) onForm((current) => ({ ...current, end_year: value })); }} />
        </div>
        <fieldset className="methodology-selector value-new-control"><legend>{t("studies.identity.methodology")}</legend>{catalogue ? catalogue.profiles.map((item) => { const description = profileOptionDescription(item, t); return <label key={item.id}><input type="radio" name="study-methodology" value={item.id} checked={methodology?.profileId === item.id} disabled={!onMethodology} onChange={() => onMethodology?.(item.id)} /><span><b>{profileOptionLabel(item, t)}</b>{/* R-17 (P1-polish): outside English, the English name and the profile id in small type. */}{locale !== "en" && <small className="methodology-profile-id" lang="en">{profileOptionLabel(item, translator("en"))} · <code>{item.id}</code></small>}{description && <small>{description}</small>}</span></label>; }) : <p className="methodology-note">{methodology?.error ? t("studies.identity.methodologyFailed", { error: methodology.error }) : t("studies.identity.methodologyLoading")} {t("studies.identity.methodologyDefault")}</p>}</fieldset>
        <label><span>{t("studies.identity.dataPack")}</span><select value={selectedPackId} onChange={(event) => onPack(event.target.value)}>{workspace.data_packs.map((pack) => { const blocked = unavailablePacks.some((item) => item.pack.id === pack.id); return <option value={pack.id} key={pack.id} disabled={blocked && pack.id !== selectedPackId}>{`${pack.name}${blocked ? ` · ${t("studies.method.notAvailable")}` : ""}`}</option>; })}</select></label>
        {unavailablePacks.length > 0 && <p className="methodology-note value-new-control">{selectedPackUnavailable ? <><b>{t("studies.identity.packUnavailable", { profile: profile ? profileOptionLabel(profile, t) : t("studies.method.thisProfile") })}</b> </> : null}{unavailablePacks[0].reason} {t("studies.identity.unavailableList", { packs: unavailablePacks.map((item) => item.pack.name).join(", ") })}</p>}</div>}
      {step === 2 && <div className="form-section composer-stage"><b>{t("studies.domain.heading")}</b><p>{advanced ? t("studies.domain.leadAdvanced") : t("studies.domain.leadBasic")}</p><div className="domain-options">{visibleDomains.map((domain) => { const psmOption = psmOptions.find((option) => option.id === domain.psm_module_id); const methodVerdict = psmOption ? moduleAvailability(psmOption, profile, t) : { available: true as const }; return <button type="button" key={`${domain.id}-${domain.psm_module_id}`} className={selectedDomain?.psm_module_id === domain.psm_module_id ? "selected" : ""} aria-pressed={selectedDomain?.psm_module_id === domain.psm_module_id} disabled={!domain.available || (!methodVerdict.available && selectedDomain?.psm_module_id !== domain.psm_module_id)} onClick={() => onDomain(domain)}><span><b>{domain.psm_module_id === "value-bid-at-cost-psm" ? t("studies.domain.singleNode") : domain.psm_module_id === "value-staged-bid-at-cost-psm" ? t("studies.domain.zonal") : domain.title}</b><Badge tone={methodVerdict.available && domain.maturity === "ready" ? "good" : "warn"}>{domainBadgeText(domain.maturity, methodVerdict.available, t)}</Badge></span><strong>{domain.psm_name}</strong><p>{domain.psm_module_id === "value-bid-at-cost-psm" ? t("studies.domain.singleNodeClaim") : domain.psm_module_id === "value-staged-bid-at-cost-psm" ? t("studies.domain.zonalClaim") : domain.claim}</p><small>{domain.available ? t("studies.domain.requiredExtensions", { count: domain.required_extensions.length }) : domain.unavailable_reason}</small>{!methodVerdict.available && <small className="methodology-note value-new-control">{methodVerdict.reason}</small>}</button>; })}</div></div>}
      {step === 3 && <div className="form-section composer-stage"><b>{t("studies.optional.heading")}</b><p>{advanced ? t("studies.optional.leadAdvanced") : t("studies.optional.leadBasic")}</p><div className="extension-options">{visibleExtensions.map((extension) => { const selected = form.selected_extensions.includes(extension.id); const required = Boolean(selectedDomain?.required_extensions.includes(extension.id)); const methodVerdict = extensionAvailability(profile, extension.id, t); return <label key={extension.id} className={selected ? "selected" : ""}><input type="checkbox" checked={selected} disabled={required || !extension.enabled || (!methodVerdict.available && !selected)} onChange={(event) => onExtension(extension, event.target.checked)} /><span><b>{extension.name}</b>{!methodVerdict.available && <small className="methodology-note value-new-control">{methodVerdict.reason}</small>}{advanced && <small>{extension.id} · {extension.version}</small>}<p>{required ? t("studies.optional.providesDomain") : extension.provided_capabilities.join(" · ")}</p><em>{required ? t("studies.optional.requiredByDomain") : t("studies.optional.conditionalInputs", { count: extension.data_roles.filter((role) => role.required).length })} · {maturityLabel(extension.maturity)}</em></span></label>; })}{!visibleExtensions.length && <div className="empty-copy"><b>{t("studies.optional.emptyTitle")}</b><p>{t("studies.optional.emptyBody")}</p></div>}</div></div>}
      {step === 4 && <div className="form-section composer-stage"><b>{t("studies.chain.heading")}</b><p>{advanced ? t("studies.chain.leadAdvanced") : t("studies.chain.leadBasic")}</p><div className="chain-editor">{(resolution?.module_slots ?? workspace.module_slots).map((slot) => { const options = resolution?.compatible_modules[slot.slot] ?? slot.options.map((item) => ({ ...item, compatible: true })); const selected = options.find((item) => item.id === form.modules[slot.slot]); if (!slot.required && !selected && !advanced) return null; return <div key={slot.slot} className="chain-slot"><span><b>{labelFor(slot.slot)}</b><small>{slot.required ? t("studies.chain.required") : t("studies.chain.optional")} · {slot.contract_version}</small></span>{advanced ? <select aria-label={labelFor(slot.slot)} value={form.modules[slot.slot] ?? ""} onChange={(event) => onModule(slot.slot, event.target.value)}><option value="">{slot.required ? t("studies.chain.selectCompatible") : t("studies.chain.notSelected")}</option>{options.map((option) => { const methodBlocked = !moduleAvailability(option, profile, t).available; return <option value={option.id} key={option.id} disabled={!option.compatible || (methodBlocked && option.id !== form.modules[slot.slot])}>{`${option.name} · ${option.version}${option.compatible ? "" : ` · ${t("studies.chain.incompatible")}`}${methodBlocked ? ` · ${t("studies.method.notAvailable")}` : ""}`}</option>; })}</select> : <div><strong>{selected?.name ?? t("studies.chain.notSelected")}</strong><small>{selected?.id ?? t("studies.chain.noOptional")}</small></div>}{(() => { const blocked = options.filter((option) => !moduleAvailability(option, profile, t).available && (advanced || option.id === selected?.id)); return blocked.length > 0 && <div className="methodology-note value-new-control">{blocked.map((option) => { const verdict = moduleAvailability(option, profile, t); return <p key={option.id}><b>{option.name}</b> {verdict.available ? "" : verdict.reason}</p>; })}</div>; })()}{selected && <Badge tone={selected.status === "ready" ? "good" : "warn"}>{maturityLabel(selected.status)}</Badge>}{advanced && options.some((option) => !option.compatible) && <div className="compatibility-reasons">{options.filter((option) => !option.compatible).map((option) => <p key={option.id}><b>{option.name}</b><span>{option.reason ?? t("studies.chain.incompatibleReason")}</span><small>{t("studies.chain.correctiveAction")}</small></p>)}</div>}</div>; })}</div>{stagedMarket && <section className="study-market-method"><div><span>01</span><b>{t("studies.chain.aheadMarket")}</b><small>{form.modules.psm}</small></div><i>→</i><div><span>02</span><b>{zonalBalancing ? t("studies.chain.zonalBalancing") : t("studies.chain.copperplateBalancing")}</b><small>{form.modules.balancing}</small></div>{zonalBalancing && <><p><strong>{t("studies.chain.networkPackRequired")}</strong> {t("studies.chain.networkPackNote")}</p><NetworkOverlaySelector value={form.market_configuration.network_pack_id ?? ""} onChange={(network_pack_id) => onForm((current) => ({ ...current, market_configuration: { ...current.market_configuration, network_pack_id } }))} onOpenData={onOpenData} /><label><span>{t("studies.chain.demandAuthority")}</span><select value={form.market_configuration.zonal_demand_mode ?? ""} onChange={(event) => onForm((current) => ({ ...current, market_configuration: { ...current.market_configuration, zonal_demand_mode: event.target.value as MarketConfiguration["zonal_demand_mode"] } }))}><option value="">{t("studies.chain.demandSelect")}</option><option value="scenario_scaled_zonal_shares">{t("studies.chain.demandScaled")}</option><option value="network_pack_absolute_demand">{t("studies.chain.demandAbsolute")}</option></select><small>{form.market_configuration.zonal_demand_mode === "network_pack_absolute_demand" ? t("studies.chain.demandAbsoluteNote") : t("studies.chain.demandScaledNote")}</small></label></>}</section>}{!form.modules.storage_cost && <div className="info-box">{t("studies.chain.storageCoOptimised")}</div>}</div>}
      {step === 5 && <div className="form-section composer-stage review-stage"><b>{t("studies.review.heading")}</b><div className={`resolution-state ${resolution?.valid ? "ready" : "blocked"}`}><span><strong>{resolving ? t("studies.review.resolving") : resolution?.valid ? t("studies.review.ready") : t("studies.review.attention")}</strong><small>{resolutionError || t("studies.review.rolesReady", { available: resolution?.data_readiness.available ?? 0, required: resolution?.data_readiness.required ?? 0 })}</small></span><Badge tone={resolution?.valid ? "good" : "warn"}>{resolution?.valid ? t("studies.review.badgeReady") : t("studies.review.issues", { count: resolution?.errors.length ?? 0 })}</Badge></div>{Boolean(resolution?.data_readiness.missing_roles.length) && <div className="missing-inputs"><header><b>{t("studies.review.missingInputs")}</b><button type="button" className="text-button" onClick={onOpenData}>{t("studies.review.openData")}</button></header>{resolution?.data_readiness.missing_roles.map((role) => <code key={role}>{role}</code>)}</div>}
        <fieldset className="trace-profile-selector"><legend>{t("studies.trace.legend")}</legend><p>{t("studies.trace.leadBefore")} <code>{"runtime.market_trace_level"}</code> {t("studies.trace.leadAfter")}</p><label><input type="radio" name="market-trace-level" value="summary" checked={traceLevel === "summary"} onChange={() => onTraceLevel("summary")} /><span><b>{t("studies.trace.summary")}</b><small>{t("studies.trace.summaryNote")}</small></span></label><label><input type="radio" name="market-trace-level" value="full" checked={traceLevel === "full"} onChange={() => onTraceLevel("full")} /><span><b>{t("studies.trace.full")}</b><small>{t("studies.trace.fullNote")}</small></span></label><label><input type="radio" name="market-trace-level" value="off" checked={traceLevel === "off"} onChange={() => onTraceLevel("off")} /><span><b>{t("studies.trace.off")}</b><small>{t("studies.trace.offNote")}</small></span></label></fieldset>
        {extensionParameters.length > 0 && <details className="advanced-settings" open={advanced}><summary>{t("studies.review.extensionParameters")}</summary><div className="parameter-grid">{extensionParameters.map(({ extension, parameter }) => { const value = form.extension_parameters[parameter.name] ?? resolution?.effective_extension_parameters[parameter.name] ?? parameter.default; const footer = <><small>{parameter.description}</small><em>{t("studies.review.parameterDefault", { extension: extension.name, value: String(parameter.default), unit: parameter.unit ?? "" })}</em></>; if (parameter.value_type === "integer" || parameter.value_type === "number") return <div className="parameter-field" key={parameter.name}><NumberField label={<><b>{parameter.title}</b> <code>{parameter.name}</code></>} value={typeof value === "number" ? value : null} min={parameter.minimum ?? undefined} max={parameter.maximum ?? undefined} step={parameter.value_type === "integer" ? 1 : undefined} unit={parameter.unit ?? undefined} required onChange={(next, check) => { if (check.valid && next !== null) onExtensionParameter(parameter.name, next); }} />{footer}</div>; return <label className="parameter-field" key={parameter.name}><span><b>{parameter.title}</b><code>{parameter.name}</code></span>{parameter.enum?.length ? <select value={String(value)} onChange={(event) => onExtensionParameter(parameter.name, event.target.value)}>{parameter.enum.map((item) => <option key={String(item)}>{String(item)}</option>)}</select> : parameter.value_type === "boolean" ? <input type="checkbox" checked={Boolean(value)} onChange={(event) => onExtensionParameter(parameter.name, event.target.checked)} /> : <input type="text" value={String(value ?? "")} onChange={(event) => onExtensionParameter(parameter.name, event.target.value)} />}{footer}</label>; })}</div></details>}
        {zonalBalancing && <SolverSettingsEditor contract={solverContract} useCustom={customSolverEditorEnabled} acknowledgement={solverAcknowledged} error={solverContractError} onUpgrade={() => { setCustomSolverEditorContract(null); onForm(upgradeZonalSolverContract); }} onUseCustom={toggleCustomSolverSettings} onChange={changeSolverContract} onAcknowledgement={(checked) => onAcknowledgement(ZONAL_SOLVER_ACK_KEY, ZONAL_SOLVER_ACK, checked)} />}
        {requirements.length > 0 && <div className="maturity-acks"><b>{t("studies.review.experimentalAck")}</b>{requirements.map((item) => <label key={item.key}><input type="checkbox" checked={form.maturity_acknowledgements[item.key] === item.acknowledgement} onChange={(event) => onAcknowledgement(item.key, item.acknowledgement, event.target.checked)} /><span>{t("studies.review.ackBefore")} <strong>{item.id} {item.version}</strong> {t("studies.review.ackAfter", { maturity: maturityLabel(item.maturity) })}</span></label>)}</div>}
        {/* Mounted while hidden, so a value it flags as invalid still blocks saving (F4-02). */}
        <div hidden={!advanced}>{assumptions}</div>
        <div className="graph-review">
          <div><span>{t("studies.review.methodology")}</span><b>{profile ? profileOptionLabel(profile, t) : resolution?.methodology?.label ?? t("studies.review.notResolved")}</b></div>
          <div><span>{t("studies.review.years")}</span><b>{form.start_year}–{form.end_year}</b></div>
          <div><span>{t("studies.review.dataPack")}</span><b>{selectedPackId}</b></div>
          <div><span>{t("studies.review.modules")}</span><b>{Object.keys(form.modules).length}</b></div>
          <div><span>{t("studies.review.extensions")}</span><b>{form.selected_extensions.length}</b></div>
          <div><span>{t("studies.review.packHash")}</span>{selectedPack?.manifest_sha256 ? <Hash value={selectedPack.manifest_sha256} label={t("studies.review.packHash")} /> : <code>{t("studies.review.notRecorded")}</code>}</div>
          <div><span>{t("studies.review.graphHash")}</span>{resolution?.graph_sha256 ? <Hash value={resolution.graph_sha256} label={t("studies.review.graphHash")} /> : <code>{t("studies.review.notResolved")}</code>}</div>
        </div>
        <p className="form-note">{t("studies.review.identityNote")}</p>
        {Boolean(resolution?.errors.length) && <div className="issue-list">{resolution?.errors.slice(0, 8).map((issue) => <article key={`${issue.code}-${issue.message}`}><code>{issue.code}</code><span>{issue.message}</span></article>)}</div>}
        {(blockedReason || saveBlock) && <p className="study-save-blocked" role="alert">{blockedReason || saveBlock}</p>}
        <button type="button" className="primary full" disabled={!resolution?.valid || resolving || !solverContractReady || saving || Boolean(blockedReason)} aria-busy={saving || undefined} title={saveReason || undefined} aria-describedby={saveReason && !blockedReason ? "study-save-reason" : undefined} onClick={save}>{saving ? t("studies.review.saving") : t("studies.review.save")}</button>{saveReason && !blockedReason && <p id="study-save-reason" className="study-save-reason" role="status">{saveReason}</p>}<small className="form-note">{t("studies.review.saveNote")}</small></div>}
      <div className="composer-actions"><button type="button" className="secondary" disabled={step === 1} onClick={() => setStep((current) => Math.max(1, current - 1))}>{t("studies.composer.back")}</button><span>{t("studies.composer.stepOf", { step, total: STEP_KEYS.length })}</span><button type="button" className="secondary" disabled={step === STEP_KEYS.length} onClick={() => setStep((current) => Math.min(STEP_KEYS.length, current + 1))}>{t("studies.composer.continue")}</button></div>
    </section>
    <aside className="study-records-column">
      <section className="panel saved-panel"><div className="panel-head"><div><span>{t("studies.saved.kicker")}</span><h3>{t("studies.saved.title")}</h3></div><Badge>{savedProjects.length}</Badge></div><div className="saved-projects">{savedProjects.length ? savedProjects.map((project) => { const linkedRunCount = project.linked_run_count ?? workspace.runs.filter((run) => run.project_id === project.id).length; const graph = project.module_resolution_graph?.graph_sha256; return <article className={selectedProjectId === project.id ? "selected" : ""} key={project.id}><div><b>{project.name}</b><small>{project.id}</small><em>{project.start_year}–{project.end_year} · {t("studies.saved.revision", { number: project.revision_number ?? 0 })} · {t("studies.saved.data", { pack: project.data_pack_id })}</em>
        {/* F4-04: the revision hash covers the data pack, years, parameters and modules. */}
        <small className="saved-study-hash-label">{t("studies.saved.revisionHash")}</small>{project.revision_sha256 ? <Hash value={project.revision_sha256} label={t("studies.saved.revisionHash")} /> : <code>{t("studies.saved.unversioned")}</code>}
        {graph && <details className="saved-study-graph"><summary>{t("studies.saved.graphHash")}</summary><Hash value={graph} label={t("studies.saved.graphHash")} /></details>}
        {codeIdentityUpdate(project) && <small className="study-code-identity value-new-control" role="note">{codeIdentityUpdate(project)}</small>}</div><span><button type="button" className="text-button" onClick={() => onLoad(project)}>{t("studies.saved.edit")}</button><button type="button" className="secondary" onClick={() => onOpenRun(project)}>{t("studies.saved.openRuns")}</button><details className="study-card-menu"><summary aria-label={t("studies.saved.moreActions", { name: project.name })}>•••</summary><button type="button" className="danger" onClick={() => onTrash(project, linkedRunCount)}>{t("studies.saved.trash")}</button></details></span></article>; }) : <div className="empty-copy"><b>{t("studies.saved.emptyTitle")}</b><p>{t("studies.saved.emptyBody")}</p></div>}</div></section>
      <details className="panel study-trash-panel"><summary><span><small>{t("studies.trash.kicker")}</small><b>{t("studies.trash.title")}</b></span><Badge>{studyTrash.length}</Badge></summary>{studyTrash.length ? <div className="study-trash-list">{studyTrash.map((entry) => <article key={entry.trash_id}><div><b>{entry.study_name}</b><small>{entry.study_id}</small><em>{t("studies.trash.counts", { revisions: entry.revision_count, runs: entry.linked_run_count })}</em><small>{entry.deleted_at} · {entry.reason}</small></div><span>{entry.linked_run_count > 0 && <button type="button" className="text-button" onClick={() => onOpenTrashRuns(entry)}>{t("studies.trash.openRuns")}</button>}<button type="button" className="secondary" onClick={() => onRestore(entry)}>{t("studies.trash.restore")}</button></span></article>)}</div> : <p className="empty-copy">{t("studies.trash.empty")}</p>}</details>
    </aside>
  </div>;
}
