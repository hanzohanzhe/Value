"use client";
import { useEffect, useRef, useState } from "react";
import type { OverlayCandidate, OverlayRecord, OverlayValidation } from "./overlay-editor.types";
import "./overlay-editor.css";

export function OverlayEditor({ apiOrigin, onWorkspaceChanged }: { apiOrigin: string; onWorkspaceChanged?: () => Promise<void> | void }) {
  const base = `${apiOrigin}/api/data-workbench/v1`;
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
  const [message, setMessage] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const generation = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const source = overlays.find((item) => item.pack_id === sourceId);
  const report = candidate?.validation?.candidate_id === candidate?.candidate_id ? candidate?.validation : null;

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const responses = await Promise.all([fetch(`${base}/overlays`, { signal: controller.signal, cache: "no-store" }), fetch(`${base}/candidates`, { signal: controller.signal, cache: "no-store" })]);
        const [overlayData, candidateData] = await Promise.all(responses.map((response) => response.json()));
        if (!responses.every((response) => response.ok)) throw new Error(overlayData.error ?? candidateData.error ?? "Overlay service unavailable");
        if (!controller.signal.aborted) { setOverlays(overlayData.overlays); setSaved(candidateData.candidates.filter((item: {directory_id: string}) => item.directory_id.startsWith("overlay-"))); }
      } catch (error) { if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "Overlay list unavailable"); }
    }
    void load();
    return () => controller.abort();
  }, [base, refreshKey]);
  useEffect(() => () => { generation.current++; abort.current?.abort(); }, [base]);

  function resetContext() {
    generation.current++; abort.current?.abort(); setBusy(false); setCandidate(null); setApproved(false); setRole(""); setFile(null); setMessage("");
  }
  async function request(path: string, init?: RequestInit) {
    abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    const key = ++generation.current; setBusy(true); setMessage("");
    try {
      const response = await fetch(`${base}${path}`, { ...init, signal: controller.signal, cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(`${payload.error_code ?? "Overlay request"}: ${payload.error ?? "failed"}`);
      return generation.current === key ? payload : null;
    } catch (error) {
      if (generation.current === key && !controller.signal.aborted) setMessage(error instanceof Error ? error.message : "Overlay request failed");
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
    if (file.size > 32 * 1024 * 1024 || !file.size) { setMessage("Choose a file containing 1 byte–32 MiB."); return; }
    const next = await request(`/overlay-candidates/${candidate.directory_id}/roles/${encodeURIComponent(role)}/file`, { method: "POST", headers: { "Content-Type": file.name.toLowerCase().endsWith(".json") ? "application/json" : "text/csv", "X-Filename": encodeURIComponent(file.name), "X-Expected-Candidate-Id": candidate.candidate_id }, body: file });
    if (next) adopt(next);
  }
  async function validate() {
    if (!candidate) return;
    const current = candidate;
    const next: OverlayValidation | null = await request(`/overlay-candidates/${candidate.directory_id}/validate`, json({ schema_version: "value.network-overlay-validation-request/v1", candidate_id: candidate.candidate_id }));
    if (next && next.candidate_id === current.candidate_id) { setCandidate({ ...current, validation: next }); setApproved(false); }
  }
  async function promote() {
    if (!candidate || file || !approved || report?.status !== "passed") return;
    const receipt = await request(`/overlay-candidates/${candidate.directory_id}/promote`, json({ schema_version: "value.data-promotion-request/v1", candidate_id: candidate.candidate_id, version: version.trim(), reviewer: reviewer.trim(), accepted_waivers: [] }));
    if (receipt) { setApproved(false); setMessage(`Installed ${receipt.network_pack_id}. Select it for a new Study; the original overlay and existing Studies are unchanged.`); setRefreshKey((value) => value + 1); await onWorkspaceChanged?.(); }
  }
  return <section className="overlay-editor" aria-labelledby="overlay-editor-title">
    <header><h4 id="overlay-editor-title">Independent network overlay</h4><p>Copy an installed overlay, replace declared files, validate the whole pack and approve a new immutable ID. Editing does not run a model.</p></header>
    <div className="overlay-editor-grid"><label>Installed network overlay<select aria-label="Installed network overlay" value={sourceId} onChange={(event) => { resetContext(); setSourceId(event.target.value); }}><option value="">Choose installed overlay</option>{overlays.map((item) => <option key={item.pack_id} value={item.pack_id} disabled={item.status !== "available"}>{item.name ?? item.pack_id} · {item.pack_id}{item.status === "invalid" ? " · invalid" : ""}</option>)}</select></label>
      <label>Preserved candidate<select aria-label="Preserved overlay candidate" value={candidate?.directory_id ?? ""} onChange={(event) => { resetContext(); const id = event.target.value; if (id) void request(`/overlay-candidates/${id}`).then((next) => { if (next) adopt(next); }); }}><option value="">Open existing candidate</option>{saved.map((item) => <option key={item.directory_id} value={item.directory_id}>{item.directory_id}</option>)}</select></label></div>
    {source && <><p>Source: <code>{source.pack_id}</code> · {source.installation_origin.replaceAll("_", " ")} · years {source.years.join(", ") || "not recorded"}</p><details className="overlay-identity"><summary>Frozen source identity</summary><code>{source.source_manifest_sha256}</code><p>Scientific content SHA-256: <code>{source.scientific_sha256}</code></p></details><div className="overlay-editor-grid"><label>New overlay ID<input value={newId} onChange={(event) => setNewId(event.target.value)} disabled={busy} placeholder="my-network-v1" /></label><label>Candidate name<input value={name} onChange={(event) => setName(event.target.value)} disabled={busy} /></label></div><div className="overlay-actions"><button className="primary" disabled={busy || source.status !== "available" || !/^[a-z][a-z0-9_-]{1,119}$/.test(newId.trim()) || !name.trim()} onClick={() => void clone()}>Copy to independent candidate</button></div></>}
    {candidate && <section><h4>{candidate.name} · <code>{candidate.pack_id}</code></h4><p>Parent: {candidate.parent_pack_id}</p><details className="overlay-identity"><summary>Current candidate identity</summary><code>{candidate.candidate_id}</code></details><div className="overlay-editor-grid"><label>Existing role<select aria-label="Overlay role" value={role} disabled={busy} onChange={(event) => { setRole(event.target.value); setFile(null); }}><option value="">Select a declared role</option>{candidate.roles.map((item) => <option key={item.role} value={item.role}>{item.role} · {item.format} · {item.unit ?? "unit not declared"}</option>)}</select></label><label>Replacement file (maximum 32 MiB)<input key={`${candidate.candidate_id}:${role}`} type="file" accept={candidate.roles.find((item) => item.role === role)?.format === "json" ? ".json" : ".csv"} disabled={busy || !role} onChange={(event) => { setFile(event.target.files?.[0] ?? null); setApproved(false); }} /></label></div>{file && <p role="status">Pending replacement not applied. Upload or clear the selected file before approval. <button className="text-button" disabled={busy} onClick={() => { setFile(null); setApproved(false); }}>Clear pending file</button></p>}<p>Keep the declared format, schema, units and clock. Zonal roles use JSON; CSV is accepted only for roles already declared as CSV. The uploaded filename is metadata; the server preserves the existing binding path.</p><div className="overlay-actions">{role && <a className="secondary overlay-download" href={`${base}/overlay-candidates/${candidate.directory_id}/roles/${encodeURIComponent(role)}/file?candidate_id=${encodeURIComponent(candidate.candidate_id)}`} download>Download current role file</a>}<button className="secondary" disabled={busy || !role || !file || file.size > 32 * 1024 * 1024} onClick={() => void upload()}>Replace role file</button><button className="primary" disabled={busy} onClick={() => void validate()}>Validate whole overlay</button></div>
      {report && <div role="status"><h4>Review: {report.status}</h4><p>Mechanical validation · {report.scientific_validation_status.replaceAll("_", " ")}</p><p>Changed roles: {report.replaced_roles.join(", ") || "none"}</p>{report.errors.map((item) => <p className="overlay-error" key={item}>{item}</p>)}{report.warnings.map((item) => <p key={item}>Warning: {item}</p>)}<p>Content hashes, declared interfaces and cross-role zonal topology/clock/reconciliation are checked. This is not a scientific acceptance run.</p></div>}
      <div className="overlay-editor-grid"><label>Approval release version<input disabled={busy} value={version} onChange={(event) => setVersion(event.target.value)} /></label><label>Responsible reviewer<input disabled={busy} value={reviewer} onChange={(event) => setReviewer(event.target.value)} /></label></div><label className="overlay-approval"><input type="checkbox" checked={approved} disabled={busy || Boolean(file) || report?.status !== "passed"} onChange={(event) => setApproved(event.target.checked)} /><span>I reviewed this candidate, including uploaded-file rights and assumptions, and approve its installation under the new ID.</span></label><div className="overlay-actions"><button className="primary" disabled={busy || Boolean(file) || report?.status !== "passed" || !approved || !version.trim() || !reviewer.trim()} onClick={() => void promote()}>Approve and install new overlay</button></div></section>}
    {busy && <p role="status">Checking current overlay context…</p>}{message && <p role="status">{message}</p>}
  </section>;
}
