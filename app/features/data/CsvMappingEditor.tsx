"use client";

import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useEffect, useId, useRef, useState } from "react";
import type { CsvMappingCatalog, CsvMappingColumn, CsvMappingCommit, CsvMappingReview, CsvMappingStage } from "./csvMappingTypes";
import { DATE_ORDERS, EMPTY_FX, EMPTY_TIMESTAMP, FX_BASES, PRICE_YEAR_RANGE, TIME_ZONES, acceptsEur, reviewExpiryText, columnSuggestsEur, fxCaption, fxErrors, fxRequest, sourceUnits, timestampCoverageText, timestampRequest, type Currency, type FxDraft, type TimestampDraft } from "./csvMappingFx.ts";
import { suggestSourceColumns } from "./csvMappingSuggest.ts";
import { Button, DataTable, Disclosure } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
import type { Translate } from "../../i18n/index.ts";
import { LocalizedError, messageOf, showMessage, type LocalizedMessage } from "../shared/localizedMessage.ts";
import "./csv-mapping-editor.css";

// P1 W4b (spec 3, 6.3, F4-13): every sentence comes from the dictionaries
// (mapping.*; the R2 Chinese wording is the zh entry). A staged file's
// same-name columns are suggested (and marked until changed); the review shows
// tables and lists, with the raw report behind "Technical details".

export type CsvMappingEditorProps = {
  packId: string; manifestSha256: string; role: string;
  disabled?: boolean; readOnlyReason?: string;
  /** S-低2: the first model year of the Study the data is for; the review notes a different data year. */
  modelStartYear?: number;
  /** S-F-高1 (R5): how the role's current file is read when its label is a known mislabel. */
  currentUnitNote?: string | null;
  onMapped: (result: CsvMappingCommit) => Promise<void> | void;
  onBusyChange?: (busy: boolean) => void;
};
type Scoped<T> = { key: string; value: T };
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const hash = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
const count = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const expiry = (value: unknown): value is string => typeof value === "string" && Number.isFinite(Date.parse(value));
const token = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f]{32}$/.test(value);
const listOfStrings = (value: unknown): value is string[] => Array.isArray(value) && value.every((item) => typeof item === "string");
const columnIdentity = (columns: CsvMappingColumn[]) => JSON.stringify(columns.map(({ source, target, source_unit, target_unit }) => ({ source, target, source_unit, target_unit })));
const validColumns = (value: unknown): value is CsvMappingColumn[] => Array.isArray(value) && value.every((item) => record(item) && typeof item.source === "string" && typeof item.target === "string" && (item.source_unit === null || typeof item.source_unit === "string") && (item.target_unit === null || typeof item.target_unit === "string"));
async function responseJson(response: Response): Promise<Record<string, unknown>> {
  const value: unknown = await response.json();
  if (!record(value)) throw new LocalizedError("mapping.error.unreadable");
  if (!response.ok) throw typeof value.error === "string" ? new Error(value.error) : new LocalizedError("mapping.error.request");
  return value;
}
const cell = (value: unknown): string => value == null ? "—" : typeof value === "object" ? JSON.stringify(value) : String(value);
/** Scalar fields of the whole-file report other than its lists (status, rows, …), for the summary list. */
function reportFacts(report: Record<string, unknown>): [string, string][] {
  return Object.entries(report).filter(([key, value]) => !["status", "errors", "warnings"].includes(key) && (value === null || typeof value !== "object")).map(([key, value]) => [key.replaceAll("_", " "), cell(value)]);
}
function MessageList({ title, items, className }: { title: string; items: readonly string[]; className: string }) {
  if (!items.length) return null;
  return <div className={className}><b>{title}</b><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></div>;
}
function SampleTable({ review, t }: { review: CsvMappingReview; t: Translate }) {
  const rows = review.sample_rows.map((row, index) => ({ id: String(index + 1), row }));
  const columns = review.columns.map((column) => ({
    key: column.target, numeric: true,
    header: column.target_unit ? `${column.target} (${column.target_unit})` : column.target,
    render: ({ row }: { row: Record<string, unknown> }) => cell(row[column.target]),
  }));
  return <DataTable caption={t("mapping.sampleCaption", { shown: rows.length, rows: review.rows })} rowKey={(item) => item.id} rows={rows} maxHeight="320px"
    columns={[{ key: "row", header: t("mapping.dataRow"), numeric: true, render: (item) => item.id }, ...columns]} />;
}

export default function CsvMappingEditor({ packId, manifestSha256, role, disabled = false, readOnlyReason, modelStartYear, currentUnitNote, onMapped, onBusyChange }: CsvMappingEditorProps) {
  const id = useId();
  const contextKey = JSON.stringify([packId, manifestSha256, role]);
  const [catalogState, setCatalog] = useState<Scoped<CsvMappingCatalog> | null>(null);
  const [stageState, setStage] = useState<Scoped<CsvMappingStage> | null>(null);
  const [mappingState, setMapping] = useState<Scoped<CsvMappingColumn[]> | null>(null);
  const [reviewState, setReview] = useState<(Scoped<CsvMappingReview> & { mappingKey: string }) | null>(null);
  const [messageState, setMessage] = useState<Scoped<LocalizedMessage> | null>(null);
  // F4-13: columns pre-selected by name; the hint stays until the user changes the column.
  const [suggestedState, setSuggested] = useState<Scoped<readonly string[]> | null>(null);
  const t = useT();
  const [activity, setActivity] = useState<Scoped<"upload" | "review" | "commit"> | null>(null);
  const [confirmed, setConfirmed] = useState<string | null>(null);
  // S-低2: a series shorter than a model year needs its own confirmation (review id it was given for).
  const [acknowledged, setAcknowledged] = useState<string | null>(null);
  const [fxState, setFx] = useState<Scoped<FxDraft> | null>(null);
  const [timestampState, setTimestamp] = useState<Scoped<TimestampDraft> | null>(null);
  const operation = useRef<AbortController | null>(null);
  const requestSequence = useRef(0);
  const currentContext = useRef(contextKey);
  const catalog = catalogState?.key === contextKey ? catalogState.value : null;
  const specification = catalog?.roles.find((item) => item.role === role);
  const stage = stageState?.key === contextKey ? stageState.value : null;
  const columns = mappingState?.key === contextKey ? mappingState.value : [];
  const columnsKey = columnIdentity(columns);
  // F-P05A-1: the declared currency and rate are part of the reviewed identity.
  const fx = fxState?.key === contextKey ? fxState.value : EMPTY_FX;
  const eur = acceptsEur(specification);
  const fxIssues = eur ? fxErrors(fx, t) : {};
  const fxBody = eur ? fxRequest(fx) : null;
  const fxInvalid = Object.keys(fxIssues).length > 0;
  // Spec 11.6 (S-D4): the declared timestamp column is part of the reviewed identity too.
  const timestamp = timestampState?.key === contextKey ? timestampState.value : EMPTY_TIMESTAMP;
  const timestampBody = specification?.timestamp_supported ? timestampRequest(timestamp) : null;
  const mappingKey = JSON.stringify([columnsKey, fx.currency === "EUR" ? fxBody : null, timestampBody]);
  const review = reviewState?.key === contextKey && reviewState.mappingKey === mappingKey && reviewState.value.stage_id === stage?.stage_id ? reviewState.value : null;
  const busy = activity?.key === contextKey;
  const locked = disabled || Boolean(readOnlyReason) || busy;
  const message = messageState?.key === contextKey ? showMessage(t, messageState.value) : "";
  const suggested = suggestedState?.key === contextKey ? suggestedState.value : [];
  const acknowledgements = review?.acknowledgements_required ?? [];
  const acknowledgementsGiven = acknowledgements.length === 0 || (review !== null && acknowledged === review.review_id);

  useEffect(() => {
    currentContext.current = contextKey;
    requestSequence.current += 1;
    operation.current?.abort();
    const controller = new AbortController();
    if (disabled || readOnlyReason) return () => controller.abort();
    void apiFetch(apiUrl(`data-packs/${encodeURIComponent(packId)}/csv-mapping/catalog`), { signal: controller.signal }).then(responseJson).then((value) => {
      if (controller.signal.aborted || currentContext.current !== contextKey) return;
      if (value.schema_version !== "value.data-mapping-catalog/v1" || value.pack_id !== packId || value.target_manifest_sha256 !== manifestSha256 || !Array.isArray(value.roles) || !value.roles.every((item) => record(item) && typeof item.role === "string" && Array.isArray(item.columns) && item.columns.every((column) => record(column) && typeof column.target === "string" && (column.target_unit === null || typeof column.target_unit === "string")) && Array.isArray(item.conversion_pairs) && item.conversion_pairs.every((pair) => record(pair) && typeof pair.source_unit === "string" && typeof pair.target_unit === "string") && typeof item.single_value === "boolean") || typeof value.max_upload_bytes !== "number" || value.max_upload_bytes <= 0) throw new LocalizedError("mapping.error.catalog");
      setCatalog({ key: contextKey, value: value as CsvMappingCatalog });
    }).catch((reason: unknown) => { if (!controller.signal.aborted && currentContext.current === contextKey) setMessage({ key: contextKey, value: messageOf(reason, "mapping.error.request") }); });
    return () => { controller.abort(); operation.current?.abort(); requestSequence.current += 1; onBusyChange?.(false); };
  }, [packId, manifestSha256, role, contextKey, disabled, readOnlyReason, onBusyChange]);

  function invalidateReview() {
    operation.current?.abort(); requestSequence.current += 1;
    setReview(null); setConfirmed(null); setAcknowledged(null); setMessage(null);
  }
  function begin(kind: "upload" | "review" | "commit") {
    operation.current?.abort();
    const controller = new AbortController(); operation.current = controller;
    const sequence = ++requestSequence.current;
    setActivity({ key: contextKey, value: kind }); setMessage(null); onBusyChange?.(true);
    return { controller, sequence };
  }
  function live(sequence: number, controller: AbortController) { return !controller.signal.aborted && requestSequence.current === sequence && currentContext.current === contextKey; }
  function finish(sequence: number, controller: AbortController) { if (live(sequence, controller)) { setActivity(null); onBusyChange?.(false); } }

  function changeFx(patch: Partial<FxDraft>) {
    invalidateReview();
    const next = { ...fx, ...patch };
    setFx({ key: contextKey, value: next });
    if (patch.currency && specification) {
      // Switching currency picks the first source unit of that currency for each priced column.
      setMapping({ key: contextKey, value: columns.map((column) => column.target_unit === null ? column : { ...column, source_unit: sourceUnits(specification, column.target_unit, patch.currency as Currency)[0] ?? column.target_unit }) });
    }
  }
  async function upload(file: File) {
    invalidateReview(); setStage(null); setMapping(null); setFx(null); setTimestamp(null); setSuggested(null);
    if (!specification || !catalog || locked) return;
    if (!file.name.toLowerCase().endsWith(".csv") || file.size === 0 || file.size > catalog.max_upload_bytes) { setMessage({ key: contextKey, value: { key: "mapping.error.file", values: { mib: Math.floor(catalog.max_upload_bytes / 1024 / 1024) } } }); return; }
    const { controller, sequence } = begin("upload");
    try {
      const value = await responseJson(await apiFetch(apiUrl(`data-packs/${encodeURIComponent(packId)}/csv-mapping/stages?role=${encodeURIComponent(role)}`), { method: "POST", headers: { "Content-Type": "text/csv", "X-Filename": encodeURIComponent(file.name), "X-Expected-Pack-Revision": manifestSha256 }, body: file, signal: controller.signal }));
      if (!live(sequence, controller)) return;
      if (value.schema_version !== "value.data-mapping-stage/v1" || value.pack_id !== packId || value.role !== role || value.target_manifest_sha256 !== manifestSha256 || !token(value.stage_id) || !hash(value.source_sha256) || !listOfStrings(value.source_columns) || !expiry(value.expires_at) || !count(value.rows) || !count(value.source_bytes) || value.source_bytes !== file.size) throw new LocalizedError("mapping.error.stageIdentity");
      const payload = value as CsvMappingStage;
      const suggestions = suggestSourceColumns(specification.columns.map((column) => column.target), payload.source_columns, specification.columns.map((column) => column.target_unit));
      setStage({ key: contextKey, value: payload });
      setSuggested({ key: contextKey, value: suggestions });
      setMapping({ key: contextKey, value: specification.columns.map((column, index) => ({ source: suggestions[index] ?? "", target: column.target, source_unit: column.target_unit, target_unit: column.target_unit })) });
    } catch (reason) { if (live(sequence, controller)) setMessage({ key: contextKey, value: messageOf(reason, "mapping.error.stageFailed") }); }
    finally { finish(sequence, controller); }
  }
  function changeTimestamp(patch: Partial<TimestampDraft>) {
    invalidateReview();
    setTimestamp({ key: contextKey, value: { ...timestamp, ...patch } });
  }
  function changeColumn(index: number, patch: Partial<CsvMappingColumn>) {
    invalidateReview();
    if (patch.source !== undefined && suggested[index]) setSuggested({ key: contextKey, value: suggested.map((value, item) => item === index ? "" : value) });
    setMapping({ key: contextKey, value: columns.map((column, item) => item === index ? { ...column, ...patch } : column) });
  }
  async function preview(requestedAt: number) {
    invalidateReview();
    if (!stage || locked || columns.some((column) => !column.source) || fxInvalid) return;
    if (!Number.isFinite(Date.parse(stage.expires_at)) || Date.parse(stage.expires_at) <= requestedAt) { setStage(null); setMapping(null); setMessage({ key: contextKey, value: { key: "mapping.error.stageExpired" } }); return; }
    const { controller, sequence } = begin("review");
    try {
      const value = await responseJson(await apiFetch(apiUrl(`data-mapping/stages/${encodeURIComponent(stage.stage_id)}/preview`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ schema_version: "value.data-mapping-preview-request/v1", source_sha256: stage.source_sha256, target_manifest_sha256: manifestSha256, columns, ...(fx.currency === "EUR" && fxBody ? { fx: fxBody } : {}), ...(timestampBody ? { timestamp: timestampBody } : {}), ...(modelStartYear ? { model_start_year: modelStartYear } : {}) }), signal: controller.signal }));
      if (!live(sequence, controller)) return;
      if (value.schema_version !== "value.data-mapping-review/v1" || value.pack_id !== packId || value.role !== role || value.stage_id !== stage.stage_id || value.source_sha256 !== stage.source_sha256 || value.target_manifest_sha256 !== manifestSha256 || !validColumns(value.columns) || columnIdentity(value.columns) !== columnsKey || !token(value.review_id) || typeof value.valid !== "boolean" || !listOfStrings(value.errors) || !listOfStrings(value.warnings) || (!Array.isArray(value.sample_rows) || value.sample_rows.length > 20 || !value.sample_rows.every(record)) || value.source_bytes !== stage.source_bytes || value.rows !== stage.rows || !count(value.normalized_bytes) || !hash(value.spec_sha256) || !(value.normalized_sha256 === null || hash(value.normalized_sha256)) || (value.valid && (!hash(value.normalized_sha256) || !record(value.validation))) || !expiry(value.expires_at)) throw new LocalizedError("mapping.error.reviewIdentity");
      setReview({ key: contextKey, mappingKey, value: value as CsvMappingReview });
    } catch (reason) { if (live(sequence, controller)) setMessage({ key: contextKey, value: messageOf(reason, "mapping.error.reviewFailed") }); }
    finally { finish(sequence, controller); }
  }
  async function commit(requestedAt: number) {
    if (!review?.valid || confirmed !== review.review_id || !acknowledgementsGiven || locked) return;
    if (!Number.isFinite(Date.parse(review.expires_at)) || Date.parse(review.expires_at) <= requestedAt) { setReview(null); setConfirmed(null); setMessage({ key: contextKey, value: { key: "mapping.error.reviewExpired" } }); return; }
    const { controller, sequence } = begin("commit");
    try {
      const value = await responseJson(await apiFetch(apiUrl(`data-mapping/reviews/${encodeURIComponent(review.review_id)}/commit`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ schema_version: "value.data-mapping-commit-request/v1", source_sha256: review.source_sha256, spec_sha256: review.spec_sha256, normalized_sha256: review.normalized_sha256, target_manifest_sha256: manifestSha256, ...(acknowledgements.length ? { acknowledged: acknowledgements.map((item) => item.code) } : {}) }), signal: controller.signal }));
      if (!live(sequence, controller)) return;
      if (value.schema_version !== "value.data-mapping-commit/v1" || value.ok !== true || value.pack_id !== packId || value.role !== role || value.run_started !== false || !hash(value.manifest_sha256) || !record(value.binding) || value.binding.sha256 !== review.normalized_sha256 || !record(value.binding.mapping_provenance) || value.binding.mapping_provenance.source_sha256 !== review.source_sha256 || value.binding.mapping_provenance.spec_sha256 !== review.spec_sha256 || value.binding.mapping_provenance.normalized_sha256 !== review.normalized_sha256) throw new LocalizedError("mapping.error.commitIdentity");
      setReview(null); setConfirmed(null); setAcknowledged(null); setStage(null); setMapping(null); setSuggested(null);
      setMessage({ key: contextKey, value: { key: "mapping.committed" } });
      await onMapped(value as CsvMappingCommit);
    } catch (reason) { if (live(sequence, controller)) setMessage({ key: contextKey, value: messageOf(reason, "mapping.error.commitFailed") }); }
    finally { finish(sequence, controller); }
  }

  const previewBlocked = locked || columns.some((column) => !column.source) || fxInvalid;
  const validation = review && record(review.validation) ? review.validation : null;
  return <section className="csv-mapping-editor" aria-labelledby={`${id}-title`} aria-busy={busy}>
    <h4 id={`${id}-title`}>{t("mapping.title")}</h4>
    {!specification ? <p>{catalog ? t("mapping.noMapping") : readOnlyReason ? t("mapping.readOnly") : t("mapping.loadingCatalog")}</p> : <>
      <p>{t("mapping.intro")}{specification.single_value && t("mapping.singleValue")}</p>
      {specification.unit_contract === "value.demand-mw-half-hour/v1" && <p>{t("mapping.demandUnit")}</p>}
      {specification.unit_contract === "value.demand-mw-half-hour/v1" && currentUnitNote && <p className="csv-mapping-hint">{currentUnitNote}</p>}
      <label className="upload">{activity?.key === contextKey && activity.value === "upload" ? t("mapping.staging") : t("mapping.chooseCsv")}<input type="file" accept=".csv,text/csv" disabled={locked} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file && !locked) void upload(file); }} /></label>
      {stage && <><p className="csv-mapping-identity">{t("mapping.originalSha")} <code>{stage.source_sha256}</code> · {t("mapping.rowsBytes", { rows: stage.rows, bytes: stage.source_bytes })}<br />{t("mapping.targetSha")} <code>{stage.target_manifest_sha256}</code></p>
        <div className="csv-mapping-columns">{columns.map((column, index) => <fieldset key={column.target} disabled={locked}><legend>{column.target}</legend><label><span>{t("mapping.sourceColumn")}</span><select value={column.source} onChange={(event) => changeColumn(index, { source: event.target.value })}><option value="">{t("mapping.chooseSource")}</option>{stage.source_columns.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>{suggested[index] && column.source === suggested[index] && <p className="csv-mapping-hint csv-mapping-suggested" role="status">{column.target_unit === null ? t("mapping.autoMatched") : t("mapping.autoMatchedUnit", { unit: column.target_unit })}</p>}{column.target_unit === null ? <p>{t("mapping.noUnitContract")}</p> : <>{eur && <label><span>{t("mapping.currency")}</span><select value={fx.currency} onChange={(event) => changeFx({ currency: event.target.value as Currency })}><option value="GBP">GBP</option><option value="EUR">EUR</option></select></label>}{eur && columnSuggestsEur(column.source, fx.currency) && <p className="csv-mapping-hint" role="status">{t("mapping.eurHint")}</p>}<label><span>{t("mapping.sourceUnit")}</span><select value={column.source_unit ?? ""} onChange={(event) => changeColumn(index, { source_unit: event.target.value || null })}>{sourceUnits(specification, column.target_unit, eur ? fx.currency : "GBP").map((unit) => <option key={unit} value={unit}>{unit}</option>)}</select></label>
          {eur && fx.currency === "EUR" && <div className="csv-mapping-fx">
            <label><span>{t("mapping.eurPerGbp")}</span><input type="number" inputMode="decimal" min="0" step="0.0001" value={fx.eurPerGbp} aria-invalid={Boolean(fxIssues.eurPerGbp)} onChange={(event) => changeFx({ eurPerGbp: event.target.value })} />{fxIssues.eurPerGbp && <small className="csv-mapping-fx-error">{fxIssues.eurPerGbp}</small>}</label>
            <label><span>{t("mapping.fxBasis")}</span><select value={fx.fxBasis} aria-invalid={Boolean(fxIssues.fxBasis)} onChange={(event) => changeFx({ fxBasis: event.target.value })}><option value="">{t("mapping.chooseFxBasis")}</option>{FX_BASES.map((basis) => <option key={basis} value={basis}>{basis}</option>)}</select>{fxIssues.fxBasis && <small className="csv-mapping-fx-error">{fxIssues.fxBasis}</small>}</label>
            <label><span>{t("mapping.priceYear")}</span><input type="number" inputMode="numeric" min={PRICE_YEAR_RANGE[0]} max={PRICE_YEAR_RANGE[1]} step="1" value={fx.priceYear} aria-invalid={Boolean(fxIssues.priceYear)} onChange={(event) => changeFx({ priceYear: event.target.value })} />{fxIssues.priceYear && <small className="csv-mapping-fx-error">{fxIssues.priceYear}</small>}</label>
          </div>}</>}<p>{t("mapping.canonicalUnit", { unit: column.target_unit ?? t("mapping.notApplicable") })}</p></fieldset>)}</div>
        {specification.timestamp_supported && <fieldset className="csv-mapping-timestamp" disabled={locked}><legend>{t("mapping.timestampLegend")}</legend>
          <label><span>{t("mapping.timestampColumn")}</span><select value={timestamp.column} onChange={(event) => changeTimestamp({ column: event.target.value })}><option value="">{t("mapping.noTimestamp")}</option>{stage.source_columns.filter((name) => !columns.some((column) => column.source === name)).map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
          <label><span>{t("mapping.timeZone")}</span><select value={timestamp.timeZone} disabled={!timestamp.column} onChange={(event) => changeTimestamp({ timeZone: event.target.value })}>{(specification.time_zones?.length ? specification.time_zones : [...TIME_ZONES]).map((zone) => <option key={zone} value={zone}>{zone}</option>)}</select></label>
          <label><span>{t("mapping.dateOrder")}</span><select value={timestamp.dateOrder ?? "auto"} disabled={!timestamp.column} onChange={(event) => changeTimestamp({ dateOrder: event.target.value })}>{DATE_ORDERS.map((order) => <option key={order.value} value={order.value}>{t(order.label)}</option>)}</select></label>
          <p>{t("mapping.timestampNote")}</p>
        </fieldset>}
        <Button className="csv-mapping-preview" disabled={previewBlocked} disabledReason={busy ? undefined : t("mapping.previewUnavailable")} onClick={() => void preview(Date.now())}>{t("mapping.preview")}</Button></>}
      {review && <section className="csv-mapping-review" aria-label={t("mapping.reviewLabel")}><h5>{review.valid ? t("mapping.reviewPassed") : t("mapping.reviewFailed")}</h5>
        <p>{t("mapping.originalSha")} <code>{review.source_sha256}</code><br />{t("mapping.canonicalSha")} <code>{review.normalized_sha256 ?? t("mapping.notYet")}</code><br />{t("mapping.specSha")} <code>{review.spec_sha256}</code><br /><small>{t("mapping.specShaNote")}</small></p>
        <MessageList className="csv-mapping-errors" title={t("mapping.errors")} items={review.errors} />
        <MessageList className="csv-mapping-warnings" title={t("mapping.warnings")} items={review.warnings} />
        {review.timestamp && <div className="csv-mapping-timestamp-report"><p><b>{t("mapping.timestamps")}</b> · {t("mapping.timestampSummary", { column: review.timestamp.column, zone: review.timestamp.time_zone, rows: review.timestamp.rows_checked, interval: review.timestamp.interval_minutes, problems: review.timestamp.problem_count ? t("mapping.problems", { count: review.timestamp.problem_count }) : t("mapping.noProblems") })}{review.timestamp.first_utc ? <> · {t("mapping.first")} <code>{review.timestamp.first_utc}</code></> : null}{review.timestamp.last_utc ? <> · {t("mapping.last")} <code>{review.timestamp.last_utc}</code></> : null}</p>{timestampCoverageText(review.timestamp, t) && <p className="csv-mapping-timestamp-coverage">{timestampCoverageText(review.timestamp, t)}</p>}{(review.timestamp.hints ?? []).length > 0 && <ul className="csv-mapping-timestamp-hints">{(review.timestamp.hints ?? []).map((hint, index) => <li key={index}>{hint}</li>)}</ul>}{review.timestamp.problems.length > 0 && <table><caption className="v-visually-hidden">{t("mapping.problemTable")}</caption><thead><tr><th scope="col">{t("mapping.dataRow")}</th><th scope="col">{t("mapping.csvLine")}</th><th scope="col">{t("mapping.timestampUtc")}</th><th scope="col">{t("mapping.problem")}</th></tr></thead><tbody>{review.timestamp.problems.map((row) => <tr key={row.row}><td>{row.data_row ?? row.row - 1}</td><td>{row.csv_line ?? row.row}</td><td>{row.timestamp ?? "—"}</td><td>{row.problem}</td></tr>)}</tbody></table>}{review.timestamp.problem_count > review.timestamp.problems.length && <small>{t("mapping.showingFirst", { shown: review.timestamp.problems.length, total: review.timestamp.problem_count })}</small>}</div>}
        {review.fx && review.source_sample_rows && review.source_sample_rows.length > 0 && <div className="csv-mapping-fx-table"><table><caption className="v-visually-hidden">{t("mapping.fxTable")}</caption><thead><tr><th scope="col">{t("mapping.fxOriginal", { column: review.columns[0]?.source })}</th><th scope="col">{t("mapping.fxConverted", { caption: fxCaption(review.fx, t) })}</th></tr></thead><tbody>{review.source_sample_rows.map((row, index) => <tr key={index}><td>{String(row[review.columns[0]?.source] ?? "—")}</td><td>{String(review.sample_rows[index]?.[review.columns[0]?.target] ?? "—")}</td></tr>)}</tbody></table></div>}
        <section className="csv-mapping-sample" aria-label={t("mapping.sampleTitle")}><b>{t("mapping.sampleTitle")}</b>
          <ul className="csv-mapping-map">{review.columns.map((column) => <li key={column.target}><code>{t("mapping.columnMap", { source: column.source, target: column.target })}</code>{column.target_unit && <> · {t("mapping.unitMap", { from: column.source_unit ?? column.target_unit, to: column.target_unit })}</>}</li>)}</ul>
          {review.sample_rows.length > 0 && <SampleTable review={review} t={t} />}
        </section>
        <section className="csv-mapping-validation" aria-label={t("mapping.validationTitle")}><b>{t("mapping.validationTitle")}</b>{review.validation == null ? <p className="csv-mapping-validation-pending">{t("mapping.validationPending")}</p> : validation && <>
          <p>{t("mapping.validationStatus", { status: cell(validation.status) })}</p>
          <MessageList className="csv-mapping-errors" title={t("mapping.errors")} items={Array.isArray(validation.errors) ? validation.errors.map(cell) : []} />
          <MessageList className="csv-mapping-warnings" title={t("mapping.warnings")} items={Array.isArray(validation.warnings) ? validation.warnings.map(cell) : []} />
          {reportFacts(validation).length > 0 && <dl className="csv-mapping-facts">{reportFacts(validation).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>}
        </>}</section>
        <Disclosure summary={t("mapping.technical")}><pre>{JSON.stringify({ columns: review.columns, rows: review.rows, sample_rows: review.sample_rows, validation: review.validation }, null, 2)}</pre></Disclosure>
        <p>{t("mapping.expiry", { time: reviewExpiryText(review.expires_at, t) })}</p>{review.valid && <><label className="csv-mapping-confirm"><input type="checkbox" disabled={locked} checked={confirmed === review.review_id} onChange={(event) => setConfirmed(event.target.checked ? review.review_id : null)} /><span>{t("mapping.confirm")}</span></label>{acknowledgements.map((item) => <label key={item.code} className="csv-mapping-confirm csv-mapping-acknowledge"><input type="checkbox" disabled={locked} checked={acknowledged === review.review_id} onChange={(event) => setAcknowledged(event.target.checked ? review.review_id : null)} /><span>{t("mapping.acknowledge", { text: item.text })}</span></label>)}<Button variant="primary" disabled={locked || confirmed !== review.review_id || !acknowledgementsGiven} disabledReason={busy ? undefined : t("mapping.commitUnavailable")} onClick={() => void commit(Date.now())}>{t("mapping.commit")}</Button></>}</section>}
    </>}{readOnlyReason && <p role="status">{readOnlyReason}</p>}{message && <p role="status">{message}</p>}
  </section>;
}
