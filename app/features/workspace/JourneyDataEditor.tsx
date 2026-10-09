"use client";

import { apiUrl } from "../../lib/api.ts";
import { useCallback, useId, useState } from "react";
import "./journey-data-editor.css";
import CsvMappingEditor from "../data/CsvMappingEditor";
import type { CsvMappingCommit } from "../data/csvMappingTypes";
import { demandUnitText, type DemandUnitInterpretation } from "./demandUnit.ts";
import { Button, buttonClass } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
import { translator, type Translate } from "../../i18n/index.ts";

// P1 W4b (spec 3): every sentence comes from the dictionaries (journeyData.*);
// the Chinese wording of the R2 swap-data path is the zh entry of each key.
const ENGLISH = translator("en");

export type JourneyBinding = {
  filename: string; sha256: string; validation?: { status?: string }; mapping_provenance?: { source_sha256: string; spec_sha256: string; normalized_sha256: string };
  /** S-D4 timestamp declaration of a mapped binding (shown on the role card, N-6). */
  timestamp_column?: string; timestamp_time_zone?: string; timestamp_check?: { status?: string; rows_checked?: number };
  /** S-中3: the day/month order the timestamp check used (absent for ISO dates). */
  timestamp_date_order?: string;
  /** P0-5a S10 / S-低5: the EUR->GBP declaration of a mapped price binding. */
  source_currency?: string; eur_per_gbp?: number; fx_basis?: string; price_year?: number;
  /** S-F-高1 (R5): the declared unit and, for legacy-labelled demand bytes, the unit they are read in. */
  unit?: string | null; runtime_unit_interpretation?: DemandUnitInterpretation;
};


/** N-6 (round R1-5): the timestamp declaration a mapped binding recorded, in one line. */
export function timestampDeclarationText(binding: JourneyBinding | undefined, t: Translate = ENGLISH): string | null {
  if (!binding?.timestamp_column) return null;
  const check = binding.timestamp_check?.status === "passed"
    ? typeof binding.timestamp_check.rows_checked === "number" ? t("journeyData.timestampCheckedRows", { rows: binding.timestamp_check.rows_checked }) : t("journeyData.timestampChecked")
    : t("journeyData.timestampUnchecked");
  const order = binding.timestamp_date_order === "day_first" ? " · DD/MM/YYYY" : binding.timestamp_date_order === "month_first" ? " · MM/DD/YYYY" : "";
  return t("journeyData.timestamp", { column: binding.timestamp_column, zone: binding.timestamp_time_zone ?? "UTC", order, check });
}

/** S-低5 (R4, A27): the currency conversion a mapped price binding recorded, in one line; null for GBP. */
export function fxDeclarationText(binding: JourneyBinding | undefined, t: Translate = ENGLISH): string | null {
  if (!binding || binding.source_currency !== "EUR" || typeof binding.eur_per_gbp !== "number") return null;
  const missing = t("journeyData.fxNotRecorded");
  return t("journeyData.fx", { rate: binding.eur_per_gbp, basis: binding.fx_basis ?? missing, year: binding.price_year ?? missing });
}

/** S-D8 (round R1-5): the confirmation that survives the editor's reset after a commit changes the manifest. */
export function mappedConfirmationText(role: string, normalizedSha256: string, t: Translate = ENGLISH): string {
  return t("journeyData.mapped", { role, sha: normalizedSha256.slice(0, 12) });
}
export type JourneyDataSlot = { role: string; label: string; required: boolean; formats: string[]; supported_formats?: string[]; unit?: string; time_semantics?: string; template_available?: boolean };
export type JourneyDataEditorProps = {
  sourceName: string;
  sourcePackName: string;
  targetPack?: { id: string; name: string; bindings: Record<string, JourneyBinding>; manifest_sha256?: string };
  sourceBindings: Record<string, JourneyBinding>;
  slots: JourneyDataSlot[];
  networkPackId?: string;
  readOnlyReason?: string;
  /** S-低2: first model year of the baseline Study (the mapping review notes a different data year). */
  modelStartYear?: number;
  busy: boolean;
  onUpload: (role: string, file: File) => Promise<void> | void;
  onPreview: (role: string) => Promise<void> | void;
  onReturn: () => void;
  onMapped?: (result: CsvMappingCommit) => Promise<void> | void;
};

export default function JourneyDataEditor({ sourceName, sourcePackName, targetPack, sourceBindings, slots, networkPackId, readOnlyReason, modelStartYear, busy, onUpload, onPreview, onReturn, onMapped }: JourneyDataEditorProps) {
  const t = useT();
  const id = useId();
  const [selectedRole, setSelectedRole] = useState("");
  // S-D8: the last committed mapping; the editor itself remounts when the manifest changes.
  const [lastMapped, setLastMapped] = useState<{ packId: string; role: string; sha256: string } | null>(null);
  const onCommitted = useCallback(async (result: CsvMappingCommit) => {
    const committed = result.binding as { sha256?: unknown } | null;
    setLastMapped({ packId: result.pack_id, role: result.role, sha256: typeof committed?.sha256 === "string" ? committed.sha256 : "" });
    await onMapped?.(result);
  }, [onMapped]);
  const slot = slots.find((item) => item.role === selectedRole) ?? slots[0];
  const mappingContext = JSON.stringify([targetPack?.id, targetPack?.manifest_sha256, slot?.role, busy, readOnlyReason]);
  const [mappingActivity, setMappingActivity] = useState<{ key: string; busy: boolean } | null>(null);
  const onMappingBusy = useCallback((mappingBusy: boolean) => setMappingActivity({ key: mappingContext, busy: mappingBusy }), [mappingContext]);
  const effectiveBusy = busy || (mappingActivity?.key === mappingContext && mappingActivity.busy);
  const original = slot ? sourceBindings[slot.role] : undefined;
  const binding = slot ? targetPack?.bindings[slot.role] : undefined;
  const formats = slot?.supported_formats?.length ? slot.supported_formats : slot?.formats ?? [];
  const added = slots.filter((item) => targetPack?.bindings[item.role] && !sourceBindings[item.role]).length;
  const changed = slots.filter((item) => targetPack?.bindings[item.role] && sourceBindings[item.role] && targetPack.bindings[item.role].sha256 !== sourceBindings[item.role].sha256).length;
  const missing = slots.filter((item) => item.required && !targetPack?.bindings[item.role]).length;
  const disabled = effectiveBusy || Boolean(readOnlyReason) || !targetPack || !slot;
  const unavailable = t("journeyData.unavailable");
  const originalUnit = demandUnitText(original, t);
  const targetUnit = demandUnitText(binding, t);
  const timestampText = timestampDeclarationText(binding, t);
  const fxText = fxDeclarationText(binding, t);
  return <section className="journey-data-editor panel" aria-labelledby={`${id}-title`} aria-busy={effectiveBusy}>
    <header><span>{t("journeyData.eyebrow")}</span><h3 id={`${id}-title`}>{t("journeyData.title")}</h3><p>{t("journeyData.source", { study: sourceName || unavailable, pack: sourcePackName || unavailable })}</p></header>
    <p>{t("journeyData.target")} <b>{targetPack?.name ?? t("journeyData.notChosen")}</b>{targetPack && <code>{targetPack.id}</code>}</p>
    <p className="journey-data-network">{t("journeyData.network")} <code>{networkPackId || t("journeyData.networkNotConfigured")}</code> {t("journeyData.networkNote")}</p>
    {!targetPack && <p role="status">{t("journeyData.noTarget")}</p>}
    {readOnlyReason && <p role="status">{readOnlyReason}</p>}
    {targetPack && <p className="journey-data-count">{t("journeyData.counts", { added, changed, missing })}{added + changed === 0 && t("journeyData.noChange")}</p>}
    <label className="journey-data-role" htmlFor={`${id}-role`}><span>{t("journeyData.roleStep")}</span><select id={`${id}-role`} value={slot?.role ?? ""} disabled={effectiveBusy || !slots.length} onChange={(event) => setSelectedRole(event.target.value)}>{slots.map((item) => <option key={item.role} value={item.role}>{item.label} · {item.role}{item.required ? t("journeyData.requiredSuffix") : ""}</option>)}</select></label>
    {slot && <><p><code>{slot.role}</code> · {slot.required ? t("journeyData.required") : t("journeyData.optional")} · {t("journeyData.formats", { formats: formats.join(" / ") || t("journeyData.notDeclared") })}{slot.unit && ` · ${slot.unit}`}{slot.time_semantics && ` · ${slot.time_semantics}`}</p>
      <div className="journey-data-files"><div><b>{t("journeyData.original")}</b><span>{original?.filename ?? t("journeyData.notBound")}</span>{original && <code>SHA {original.sha256}</code>}{originalUnit && <span className="journey-data-unit">{originalUnit}</span>}</div><div><b>{t("journeyData.targetFile")}</b><span>{binding?.filename ?? t("journeyData.notBound")}</span>{binding && <><code>SHA {binding.sha256}</code><span>{t("journeyData.validation", { status: binding.validation?.status ?? t("journeyData.notRecorded") })}</span>{binding.mapping_provenance && <><span>{t("journeyData.mappedSource")}</span><code>SHA {binding.mapping_provenance.source_sha256}</code><span>{t("journeyData.canonical")}</span><code>SHA {binding.mapping_provenance.normalized_sha256}</code><span>{t("journeyData.mappingRules")}</span><code>SHA {binding.mapping_provenance.spec_sha256}</code></>}{targetUnit && <span className="journey-data-unit">{targetUnit}</span>}{timestampText && <span className="journey-data-timestamp">{timestampText}</span>}{fxText && <span className="journey-data-fx">{fxText}</span>}</>}</div></div>
      {lastMapped && lastMapped.packId === targetPack?.id && lastMapped.role === slot.role && binding?.sha256 === lastMapped.sha256 && <p className="journey-data-mapped" role="status">{mappedConfirmationText(slot.role, lastMapped.sha256, t)}</p>}
      <p>{t("journeyData.fileStep")}</p>
      {targetPack?.manifest_sha256 && onMapped ? <CsvMappingEditor key={mappingContext} packId={targetPack.id} manifestSha256={targetPack.manifest_sha256} role={slot.role} disabled={busy} readOnlyReason={readOnlyReason} modelStartYear={modelStartYear} currentUnitNote={targetUnit ?? originalUnit} onMapped={onCommitted} onBusyChange={onMappingBusy} /> : <p>{t("journeyData.mappingNeedsRevision")}</p>}
      <div className="journey-data-actions">{slot.template_available && <a className={buttonClass("secondary", "md")} href={apiUrl(`data-contracts/${encodeURIComponent(slot.role)}/template`)}>{t("journeyData.template")}</a>}{binding && <Button disabled={effectiveBusy} onClick={() => void onPreview(slot.role)}>{t("journeyData.previewTarget")}</Button>}<label className="upload">{effectiveBusy ? t("journeyData.processing") : t("journeyData.chooseFile")}<input type="file" accept={formats.map((format) => `.${format}`).join(",")} disabled={disabled} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file && !disabled) void onUpload(slot.role, file); }} /></label></div>
    </>}
    <p>{t("journeyData.separateSteps")}</p>
    <Button className="journey-data-return" onClick={onReturn} disabled={effectiveBusy}>{t("journeyData.return")}</Button>
  </section>;
}
