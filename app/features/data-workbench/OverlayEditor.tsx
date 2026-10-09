"use client";
import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useEffect, useId, useRef, useState } from "react";
import { Button, buttonClass } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
import { errorPrefix } from "../../i18n/index.ts";
import { LocalizedError, messageOf, showMessage, type LocalizedMessage } from "../shared/localizedMessage.ts";
import type { OverlayCandidate, OverlayRecord, OverlayValidation } from "./overlay-editor.types";

// P1 W4b (spec 3, F4-17): wording from the dictionaries (overlay.*); the new
// overlay ID says its rule as you type (aria-describedby), disabled actions
// say why, and every path segment is encoded.
const OVERLAY_ID = /^[a-z][a-z0-9_-]{1,119}$/;
const OVERLAY_ID_EXAMPLE = "my-network-v1";
import "./overlay-editor.css";

export function OverlayEditor({ onWorkspaceChanged }: { onWorkspaceChanged?: () => Promise<void> | void }) {
  const t = useT();
  const fieldId = useId();
  const base = apiUrl("data-workbench/v1");
  const [overlays, setOverlays] = useState<OverlayRecord[]>([]);
  const [saved, setSaved] = useState<{directory_id: string; candidate_id: string}[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [newId, setNewId] = useState("");
  const [name, setName] = useState("");
  const [candidate, setCandidate] = useState<OverlayCandidate | null>(null);
  const [role, setRole] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [reviewer, setReviewer] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<LocalizedMessage | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const generation = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const source = overlays.find((item) => item.pack_id === sourceId);
  const report = candidate?.validation?.candidate_id === candidate?.candidate_id ? candidate?.validation : null;

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const responses = await Promise.all([apiFetch(`${base}/overlays`, { signal: controller.signal, cache: "no-store" }), apiFetch(`${base}/candidates`, { signal: controller.signal, cache: "no-store" })]);
        const [overlayData, candidateData] = await Promise.all(responses.map((response) => response.json()));
        if (!responses.every((response) => response.ok)) throw (overlayData.error ?? candidateData.error) ? new Error(overlayData.error ?? candidateData.error) : new LocalizedError("overlay.serviceUnavailable");
        if (!controller.signal.aborted) { setOverlays(overlayData.overlays); setSaved(candidateData.candidates.filter((item: {directory_id: string}) => item.directory_id.startsWith("overlay-"))); }
      } catch (error) { if (!controller.signal.aborted) setMessage(messageOf(error, "overlay.listUnavailable")); }
    }
    void load();
    return () => controller.abort();
  }, [base, refreshKey]);
  useEffect(() => () => { generation.current++; abort.current?.abort(); }, [base]);

  function resetContext() {
    generation.current++; abort.current?.abort(); setBusy(false); setCandidate(null); setApproved(false); setRole(""); setFile(null); setMessage(null);
  }
  async function request(path: string, init?: RequestInit) {
    abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    const key = ++generation.current; setBusy(true); setMessage(null);
    try {
      const response = await apiFetch(`${base}${path}`, { ...init, signal: controller.signal, cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw payload.error ? new Error(`${errorPrefix(t, payload.error_code)}${payload.error}`) : new LocalizedError("overlay.requestFailed");
      return generation.current === key ? payload : null;
    } catch (error) {
      if (generation.current === key && !controller.signal.aborted) setMessage(messageOf(error, "overlay.requestFailed"));
      return null;
    } finally { if (generation.current === key) setBusy(false); }
  }
  const json = (body: object): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  function adopt(next: OverlayCandidate) { setCandidate(next); setApproved(false); setFile(null); setRefreshKey((value) => value + 1); }
  async function clone() {
    if (!source) return;
    const next = await request(`/overlays/${encodeURIComponent(source.pack_id)}/candidates`, json({ schema_version: "value.network-overlay-clone/v1", source_manifest_sha256: source.source_manifest_sha256, new_pack_id: newId.trim(), name: name.trim() }));
    if (next) adopt(next);
  }
  async function upload() {
    if (!candidate || !file || !role) return;
    if (file.size > 32 * 1024 * 1024 || !file.size) { setMessage({ key: "overlay.fileSize" }); return; }
    const next = await request(`/overlay-candidates/${encodeURIComponent(candidate.directory_id)}/roles/${encodeURIComponent(role)}/file`, { method: "POST", headers: { "Content-Type": file.name.toLowerCase().endsWith(".json") ? "application/json" : "text/csv", "X-Filename": encodeURIComponent(file.name), "X-Expected-Candidate-Id": candidate.candidate_id }, body: file });
    if (next) adopt(next);
  }
  async function validate() {
    if (!candidate) return;
    const current = candidate;
    const next: OverlayValidation | null = await request(`/overlay-candidates/${encodeURIComponent(candidate.directory_id)}/validate`, json({ schema_version: "value.network-overlay-validation-request/v1", candidate_id: candidate.candidate_id }));
    if (next && next.candidate_id === current.candidate_id) { setCandidate({ ...current, validation: next }); setApproved(false); }
  }
  async function promote() {
    if (!candidate || file || !approved || report?.status !== "passed") return;
    const receipt = await request(`/overlay-candidates/${encodeURIComponent(candidate.directory_id)}/promote`, json({ schema_version: "value.data-promotion-request/v1", candidate_id: candidate.candidate_id, version: version.trim(), reviewer: reviewer.trim(), accepted_waivers: [] }));
    if (receipt) { setApproved(false); setMessage({ key: "overlay.installedNotice", values: { id: receipt.network_pack_id } }); setRefreshKey((value) => value + 1); await onWorkspaceChanged?.(); }
  }
  const idValid = OVERLAY_ID.test(newId.trim());
  const roleSpec = candidate?.roles.find((item) => item.role === role);
  const installBlocked = busy || Boolean(file) || report?.status !== "passed" || !approved || !version.trim() || !reviewer.trim();
  return <section className="overlay-editor" aria-labelledby="overlay-editor-title">
    <header><h4 id="overlay-editor-title">{t("overlay.title")}</h4><p>{t("overlay.intro")}</p></header>
    <div className="overlay-editor-grid"><label>{t("overlay.installed")}<select aria-label={t("overlay.installed")} value={sourceId} onChange={(event) => { resetContext(); setSourceId(event.target.value); }}><option value="">{t("overlay.chooseInstalled")}</option>{overlays.map((item) => <option key={item.pack_id} value={item.pack_id} disabled={item.status !== "available"}>{item.name ?? item.pack_id} · {item.pack_id}{item.status === "invalid" ? t("overlay.invalidSuffix") : ""}</option>)}</select></label>
      <label>{t("overlay.preserved")}<select aria-label={t("overlay.preservedAria")} value={candidate?.directory_id ?? ""} onChange={(event) => { resetContext(); const id = event.target.value; if (id) void request(`/overlay-candidates/${encodeURIComponent(id)}`).then((next) => { if (next) adopt(next); }); }}><option value="">{t("overlay.openExisting")}</option>{saved.map((item) => <option key={item.directory_id} value={item.directory_id}>{item.directory_id}</option>)}</select></label></div>
    {source && <><p>{t("overlay.source")} <code>{source.pack_id}</code> · {source.installation_origin.replaceAll("_", " ")} · {t("overlay.sourceYears", { years: source.years.join(", ") || t("overlay.notRecorded") })}</p><details className="overlay-identity"><summary>{t("overlay.frozenIdentity")}</summary><code>{source.source_manifest_sha256}</code><p>{t("overlay.scientificSha")} <code>{source.scientific_sha256}</code></p></details><div className="overlay-editor-grid"><label htmlFor={`${fieldId}-id`}>{t("overlay.newId")}<input id={`${fieldId}-id`} value={newId} onChange={(event) => setNewId(event.target.value)} disabled={busy} placeholder={OVERLAY_ID_EXAMPLE} aria-describedby={`${fieldId}-id-hint`} aria-invalid={newId.trim() !== "" && !idValid} /><small id={`${fieldId}-id-hint`} className={newId.trim() !== "" && !idValid ? "overlay-error" : undefined}>{newId.trim() !== "" && !idValid ? t("overlay.newIdInvalid") : t("overlay.newIdHint")}</small></label><label>{t("overlay.candidateName")}<input value={name} onChange={(event) => setName(event.target.value)} disabled={busy} /></label></div><div className="overlay-actions"><Button variant="primary" disabled={busy || source.status !== "available" || !idValid || !name.trim()} disabledReason={busy ? undefined : t("overlay.copyUnavailable")} onClick={() => void clone()}>{t("overlay.copy")}</Button></div></>}
    {candidate && <section><h4>{candidate.name} · <code>{candidate.pack_id}</code></h4><p>{t("overlay.parent", { id: candidate.parent_pack_id })}</p><details className="overlay-identity"><summary>{t("overlay.currentIdentity")}</summary><code>{candidate.candidate_id}</code></details><div className="overlay-editor-grid"><label>{t("overlay.role")}<select aria-label={t("overlay.roleAria")} value={role} disabled={busy} onChange={(event) => { setRole(event.target.value); setFile(null); }}><option value="">{t("overlay.selectRole")}</option>{candidate.roles.map((item) => <option key={item.role} value={item.role}>{item.role} · {item.format} · {item.unit ?? t("overlay.unitNotDeclared")}</option>)}</select></label><label>{t("overlay.replacement")}<input key={`${candidate.candidate_id}:${role}`} type="file" accept={roleSpec?.format === "json" ? ".json" : ".csv"} disabled={busy || !role} onChange={(event) => { setFile(event.target.files?.[0] ?? null); setApproved(false); }} /></label></div>{file && <p role="status">{t("overlay.pending")} <Button size="sm" variant="ghost" disabled={busy} onClick={() => { setFile(null); setApproved(false); }}>{t("overlay.clearPending")}</Button></p>}<p>{t("overlay.formatNote")}</p><div className="overlay-actions">{role && <a className={buttonClass("secondary", "md", "overlay-download")} href={`${base}/overlay-candidates/${encodeURIComponent(candidate.directory_id)}/roles/${encodeURIComponent(role)}/file?candidate_id=${encodeURIComponent(candidate.candidate_id)}`} download>{t("overlay.download")}</a>}<Button disabled={busy || !role || !file || file.size > 32 * 1024 * 1024} onClick={() => void upload()}>{t("overlay.replace")}</Button><Button variant="primary" disabled={busy} onClick={() => void validate()}>{t("overlay.validate")}</Button></div>
      {report && <div role="status"><h4>{t("overlay.review", { status: report.status })}</h4><p>{t("overlay.mechanical", { status: report.scientific_validation_status.replaceAll("_", " ") })}</p><p>{t("overlay.changedRoles", { roles: report.replaced_roles.join(", ") || t("overlay.none") })}</p>{report.errors.map((item) => <p className="overlay-error" key={item}>{item}</p>)}{report.warnings.map((item) => <p key={item}>{t("overlay.warning", { text: item })}</p>)}<p>{t("overlay.checksNote")}</p></div>}
      <div className="overlay-editor-grid"><label>{t("overlay.version")}<input disabled={busy} value={version} onChange={(event) => setVersion(event.target.value)} /></label><label>{t("overlay.reviewer")}<input disabled={busy} value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label></div><label className="overlay-approval"><input type="checkbox" checked={approved} disabled={busy || Boolean(file) || report?.status !== "passed"} onChange={(event) => setApproved(event.target.checked)} /><span>{t("overlay.approve")}</span></label><div className="overlay-actions"><Button variant="primary" disabled={installBlocked} disabledReason={busy ? undefined : t("overlay.installUnavailable")} onClick={() => void promote()}>{t("overlay.install")}</Button></div></section>}
    {busy && <p role="status">{t("overlay.checking")}</p>}{message && <p role="status">{showMessage(t, message)}</p>}
  </section>;
}
