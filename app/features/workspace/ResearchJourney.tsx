"use client";

// The research guide (/journey), P1 spec 5.1/6.1: create a reproduction or a
// new-data Study from a saved baseline.  Wording from the dictionaries
// (journey.*).  D-W3-2: the guide is an ordinary route page; what the reader
// has typed (baseline, new name, pack name) is remembered for the session, so
// the trip to Data and back keeps it (the target pack is in the workbench).
import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useId, useRef, useState, type FormEvent } from "react";
import "./research-journey.css";
import { studyNameTaken } from "./studyNames.ts";
import { derivationNotes } from "../modules/derivationNotes.ts";
import { studyMethodologyText, type MethodologyCatalogue } from "../studies/methodologyChoice.ts";
import { useT } from "../../i18n/LocaleProvider";
import { Stepper, type StepItem } from "../../ui";

/** What the reader typed in the guide, kept while the page is away (one browser tab, this session). */
export const journeyMemory = { sourceId: "", newName: "", packName: "" };

export type JourneyStudy = {
  id: string;
  name: string;
  revision_sha256?: string;
  revision_number?: number;
  data_pack_id: string;
  start_year: number;
  end_year: number;
  modules: Record<string, string>;
  parameters?: Record<string, unknown>;
};

export type JourneyPack = {
  id: string;
  name: string;
  complete: boolean;
  valid_required_count: number;
  required_count: number;
  manifest_sha256?: string;
  data_pack_type?: string;
  bindings?: Record<string, { filename: string; sha256: string }>;
};

export type ResearchJourneyProps = {
  intent: "reproduce" | "data";
  studies: JourneyStudy[];
  packs: JourneyPack[];
  initialStudyId: string;
  online: boolean;
  onCreated(studyId: string, notes?: string[]): Promise<void> | void;
  targetPackId: string;
  onTargetPackChange: (id: string) => void;
  onPackCreated(): Promise<void>;
  onOpenData: (context: { sourceStudyId: string; sourceRevisionSha256: string; targetPackId: string }) => void;
  onOpenLearn: () => void;
  onOpenRuns: (studyId: string) => void;
  onReviewSource: (studyId: string) => void;
  /** R5 R-中1: the methodology catalogue, to name the profile the new Study inherits. */
  methodologyCatalogue?: MethodologyCatalogue | null;
};

type DeriveResponse = { project?: { id?: string }; error?: string; detail?: string };

export default function ResearchJourney({
  intent, studies, packs, initialStudyId, online, methodologyCatalogue,
  onCreated, onOpenData, onOpenLearn, onOpenRuns, onReviewSource, targetPackId, onTargetPackChange, onPackCreated,
}: ResearchJourneyProps) {
  const t = useT();
  const fieldId = useId();
  // An explicit selection, including one that later disappears, stays selected.
  const [sourceId, setSourceIdState] = useState(() => journeyMemory.sourceId || initialStudyId || studies[0]?.id || "");
  const [newName, setNewNameState] = useState(() => journeyMemory.newName);
  const [packName, setPackNameState] = useState(() => journeyMemory.packName);
  const setSourceId = (value: string) => { journeyMemory.sourceId = value; setSourceIdState(value); };
  const setNewName = (value: string) => { journeyMemory.newName = value; setNewNameState(value); };
  const setPackName = (value: string) => { journeyMemory.packName = value; setPackNameState(value); };
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submissionLock = useRef(false);
  const selectedSourceId = sourceId || initialStudyId || studies[0]?.id || "";
  const source = studies.find((study) => study.id === selectedSourceId);
  const originalPack = packs.find((pack) => pack.id === source?.data_pack_id);
  const targetPack = packs.find((pack) => pack.id === targetPackId);
  const changingData = intent === "data";
  const availablePacks = packs.filter((pack) => pack.id !== source?.data_pack_id && pack.data_pack_type !== "network_overlay");
  const targetUnavailable = Boolean(targetPackId && !availablePacks.some((pack) => pack.id === targetPackId));
  const hasRevision = Boolean(source?.revision_sha256?.trim());
  const dataSelected = !changingData || Boolean(targetPack && !targetUnavailable && targetPack.id !== source?.data_pack_id);
  const canCreate = Boolean(online && source && hasRevision && dataSelected && newName.trim() && !busy);
  // R3-N4 (round R2): saved Studies may share a name; say so before a second one is created.
  const duplicateName = studyNameTaken(studies, newName);
  const createLabel = changingData ? t("journey.create.data") : t("journey.create.reproduce");
  const reviewStep = changingData ? 3 : 2;
  const methodology = source ? studyMethodologyText(source.parameters, methodologyCatalogue, t) : null;
  // Spec 2 (Stepper): the path's steps, the first unfinished one current.
  const done = [Boolean(source && hasRevision), ...(changingData ? [dataSelected] : []), Boolean(newName.trim()), false];
  const current = done.findIndex((value) => !value);
  const stepLabels = [t("journey.source.title"), ...(changingData ? [t("journey.pack.title")] : []), t("journey.review.title"), t("journey.create.title")];
  const stepItems: StepItem[] = stepLabels.map((label, index) => ({ id: String(index + 1), label, state: done[index] && index < current ? "done" : index === current ? "current" : "todo" }));

  function openData(packId = targetPackId) {
    if (!source) return;
    onOpenData({ sourceStudyId: source.id, sourceRevisionSha256: source.revision_sha256 ?? "", targetPackId: packId });
  }

  async function clonePack() {
    if (!source || !originalPack?.manifest_sha256 || originalPack.data_pack_type === "network_overlay" || !online || !packName.trim() || submissionLock.current) return;
    submissionLock.current = true; setBusy(true); setError("");
    let createdPackId = "";
    try {
      const response = await apiFetch(apiUrl(`data-packs/${encodeURIComponent(originalPack.id)}/clone`), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schema_version: "value.data-pack-clone-request/v1", name: packName.trim(), source_manifest_sha256: originalPack.manifest_sha256 }),
      });
      const payload = await response.json() as { data_pack?: { id?: string }; error?: string; detail?: string };
      if (response.status !== 201) throw new Error(payload.error || payload.detail || t("journey.pack.copyFailed"));
      if (!payload.data_pack?.id || typeof payload.data_pack.id !== "string" || payload.data_pack.id === originalPack.id) throw new Error(t("journey.pack.copyNoIdentity"));
      createdPackId = payload.data_pack.id;
      onTargetPackChange(createdPackId);
      await onPackCreated();
      openData(payload.data_pack.id);
    } catch (cause) { setError(createdPackId ? t("journey.pack.copiedNotListed", { id: createdPackId }) : cause instanceof Error ? cause.message : t("journey.pack.copyError")); }
    finally { submissionLock.current = false; setBusy(false); }
  }

  async function createStudy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreate || !source || submissionLock.current) return;
    submissionLock.current = true;
    setBusy(true);
    setError("");
    try {
      const response = await apiFetch(apiUrl(`projects/${encodeURIComponent(source.id)}/derive`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          intent,
          name: newName.trim(),
          source_revision_sha256: source.revision_sha256,
          data_pack_id: changingData ? targetPackId : source.data_pack_id,
        }),
      });
      let payload: DeriveResponse;
      try {
        payload = await response.json() as DeriveResponse;
      } catch {
        throw new Error(t("journey.create.unreadable"));
      }
      if (!response.ok) {
        throw new Error(typeof payload.error === "string" ? payload.error
          : typeof payload.detail === "string" ? payload.detail : t("journey.create.failed"));
      }
      if (typeof payload.project?.id !== "string" || !payload.project.id) {
        throw new Error(t("journey.create.noStudy"));
      }
      // R3-N4 (round R2): the baseline stays selected and the name is cleared, so a
      // second click does not reproduce the new copy under the same name.
      setSourceId(source.id);
      setNewName("");
      await onCreated(payload.project.id, derivationNotes(payload));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("journey.create.error"));
    } finally {
      submissionLock.current = false;
      setBusy(false);
    }
  }

  return (
    <section className="research-journey" aria-labelledby={`${fieldId}-title`}>
      <header className="research-journey-heading">
        <span>{t("journey.kicker")}</span>
        <h2 id={`${fieldId}-title`} lang="en">{t(changingData ? "home.path.data.label" : "home.path.reproduce.label")}</h2>
        <p>{changingData ? t("journey.lead.data") : t("journey.lead.reproduce")}</p>
      </header>
      <Stepper steps={stepItems} label={t("journey.stepsLabel")} />

      <form onSubmit={createStudy} aria-busy={busy}>
        <ol className="research-journey-steps">
          <li className="research-journey-step">
            <header><span aria-hidden="true">1</span><h3>{t("journey.source.title")}</h3></header>
            {studies.length === 0 ? (
              <div className="research-journey-empty">
                <p>{t("journey.source.empty")}</p>
                <button type="button" onClick={onOpenLearn} disabled={busy}>{t("journey.source.openLearn")}</button>
              </div>
            ) : (
              <label className="research-journey-field" htmlFor={`${fieldId}-source`}>
                <span>{t("journey.source.label")}</span>
                <select id={`${fieldId}-source`} value={selectedSourceId} disabled={busy}
                  onChange={(event) => { setSourceId(event.target.value); setError(""); }}>
                  {selectedSourceId && !source && <option value={selectedSourceId}>{t("journey.source.gone")}</option>}
                  {studies.map((study) => <option key={study.id} value={study.id}>{study.name}</option>)}
                </select>
              </label>
            )}
            {selectedSourceId && !source && <p className="research-journey-warning" role="status">{t("journey.source.goneWarning")}</p>}
            <p className="research-journey-hint">{t("journey.source.hint")}</p>
            {source && <div className="research-journey-baseline-actions">
              <button type="button" onClick={() => onOpenRuns(source.id)} disabled={busy}>{t("journey.source.openRuns")}</button>
              <button type="button" onClick={() => onReviewSource(source.id)} disabled={busy}>{t("journey.source.review")}</button>
            </div>}
          </li>

          {changingData && <li className="research-journey-step">
            <header><span aria-hidden="true">2</span><h3>{t("journey.pack.title")}</h3></header>
            <label className="research-journey-field" htmlFor={`${fieldId}-pack-name`}><span>{t("journey.pack.nameLabel")}</span><input id={`${fieldId}-pack-name`} value={packName} disabled={busy || !source} placeholder={t("journey.pack.namePlaceholder")} onChange={(event) => setPackName(event.target.value)} /></label>
            <button type="button" onClick={() => void clonePack()} disabled={busy || !online || !source || !originalPack?.manifest_sha256 || originalPack.data_pack_type === "network_overlay" || !packName.trim()}>{t("journey.pack.copy")}</button>
            <p className="research-journey-hint">{t("journey.pack.copyHint")}</p>
            {originalPack?.data_pack_type === "network_overlay" && <p className="research-journey-warning">{t("journey.pack.overlayWarning")}</p>}
            {source && !originalPack?.manifest_sha256 && <p className="research-journey-warning">{t("journey.pack.noManifest")}</p>}
            <label className="research-journey-field" htmlFor={`${fieldId}-pack`}>
              <span>{t("journey.pack.installedLabel")}</span>
              <select id={`${fieldId}-pack`} value={targetPackId} disabled={busy || !source}
                onChange={(event) => { onTargetPackChange(event.target.value); setError(""); }}>
                <option value="">{t("journey.pack.choose")}</option>
                {targetUnavailable && <option value={targetPackId}>{t("journey.pack.gone")}</option>}
                {availablePacks.map((pack) => <option key={pack.id} value={pack.id}>{pack.name}</option>)}
              </select>
            </label>
            {targetUnavailable && <p className="research-journey-warning" role="status">{t("journey.pack.goneWarning")}</p>}
            {source && availablePacks.length === 0 && <p className="research-journey-hint">{t("journey.pack.noOther")}</p>}
            {targetPack && !targetUnavailable && <p className="research-journey-pack-status">{t("journey.pack.status", { state: targetPack.complete ? t("journey.pack.complete") : t("journey.pack.incomplete"), valid: targetPack.valid_required_count, required: targetPack.required_count })}</p>}
            <p className="research-journey-hint">{t("journey.pack.readinessHint")}</p>
            <button type="button" onClick={() => openData()} disabled={busy || !source}>{t("journey.pack.openData")}</button>
          </li>}

          <li className="research-journey-step">
            <header><span aria-hidden="true">{reviewStep}</span><h3>{t("journey.review.title")}</h3></header>
            <label className="research-journey-field" htmlFor={`${fieldId}-name`}>
              <span>{t("journey.review.nameLabel")}</span>
              <input id={`${fieldId}-name`} value={newName} required disabled={busy} autoComplete="off"
                placeholder={changingData ? t("journey.review.namePlaceholderData") : t("journey.review.namePlaceholderReproduce")}
                onChange={(event) => { setNewName(event.target.value); setError(""); }} />
            </label>
            {duplicateName && <p className="research-journey-warning" role="status">{t("journey.review.duplicate")}</p>}
            {source ? <>
              <dl className="research-journey-review">
                <div><dt>{t("journey.review.baseline")}</dt><dd>{source.name}</dd></div>
                <div><dt>{t("journey.review.years")}</dt><dd>{source.start_year} – {source.end_year}</dd></div>
                {methodology && <div><dt>{t("journey.review.methodology")}</dt><dd>{methodology.label}{methodology.profileId && <code>{methodology.profileId}</code>}
                  <span className="research-journey-hint">{t("journey.review.methodologyHint")}</span></dd></div>}
                <div><dt>{t("journey.review.revision")}</dt><dd>{source.revision_number !== undefined ? t("journey.review.revisionNumber", { number: source.revision_number }) : t("journey.review.revisionUnknown")}
                  {hasRevision ? <code title={source.revision_sha256}>{source.revision_sha256}</code> : <span className="research-journey-warning">{t("journey.review.revisionMissing")}</span>}</dd></div>
                <div><dt>{t("journey.review.originalPack")}</dt><dd>{originalPack?.name ?? source.data_pack_id}<code>{source.data_pack_id}</code></dd></div>
                <div><dt>{changingData ? t("journey.review.newPack") : t("journey.review.studyPack")}</dt><dd>{changingData ? targetPack?.name ?? t("journey.review.notChosen") : originalPack?.name ?? source.data_pack_id}
                  {changingData && targetPack && <code>{targetPack.id}</code>}</dd></div>
              </dl>
              <details className="research-journey-modules">
                <summary>{t("journey.review.modules")}</summary>
                <div className="research-journey-table-scroll" role="region" aria-label={t("journey.review.modulesRegion")} tabIndex={0}>
                <table>
                  <caption>{t("journey.review.modulesCaption")}</caption>
                  <thead><tr><th scope="col">{t("journey.review.role")}</th><th scope="col">{t("journey.review.module")}</th></tr></thead>
                  <tbody>{Object.entries(source.modules).map(([role, moduleId]) => <tr key={role}><th scope="row">{role}</th><td>{moduleId}</td></tr>)}</tbody>
                </table>
                {Object.keys(source.modules).length === 0 && <p className="research-journey-hint">{t("journey.review.noModules")}</p>}
                </div>
              </details>
            </> : <p className="research-journey-hint">{t("journey.review.noSource")}</p>}
          </li>

          <li className="research-journey-step research-journey-create">
            <header><span aria-hidden="true">{reviewStep + 1}</span><h3>{t("journey.create.title")}</h3></header>
            <p>{t("journey.create.lead")}</p>
            {!online && <p className="research-journey-warning" role="status">{t("journey.create.offline")}</p>}
            {error && <>
              <p className="research-journey-error" role="alert">{error}</p>
              <p className="research-journey-hint">{t("journey.create.retryHint")}</p>
            </>}
            <button className="research-journey-primary" type="submit" disabled={!canCreate} aria-describedby={source && hasRevision && !newName.trim() ? `${fieldId}-name-needed` : undefined}>{busy ? t("journey.create.creating") : createLabel}</button>
            {source && hasRevision && !newName.trim() && <p id={`${fieldId}-name-needed`} className="research-journey-hint" role="status">{t("journey.create.nameNeeded", { step: reviewStep })}</p>}
          </li>
        </ol>
      </form>
    </section>
  );
}
