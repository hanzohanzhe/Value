"use client";

import { apiUrl } from "../shared/api";
import { useLayoutEffect, useId, useRef, useState } from "react";
import {
  authoringRecords, authoringStrings, isAuthoringRecord, isExtensionAuthoringReport, sameProposal,
  type AuthorExtension, type ExtensionAuthorModule, type ExtensionAuthoringReport,
  type ExtensionAuthoringRequest, type ExtensionProposal, type ValidExtensionAuthoringReport,
} from "./authoring.types";
import "./ExtensionAuthorWorkbench.css";

type Props = {
  onInstallRequest: () => void;
  onOpenStudies: () => void;
  extensions?: AuthorExtension[];
  modules?: ExtensionAuthorModule[];
};
type ReportState = { key: string; requestText: string; report?: ExtensionAuthoringReport; error?: string };

function failure(body: unknown, fallback: string): string {
  return isAuthoringRecord(body) && typeof body.error === "string"
    ? `${typeof body.error_code === "string" ? `${body.error_code}: ` : ""}${body.error}` : fallback;
}
function display(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "Not declared" : JSON.stringify(value);
}
function Declaration({ title, entries, empty }: { title: string; entries: string[]; empty: string }) {
  return <div className="extension-author-declaration"><b>{title}</b>{entries.length
    ? <ul>{entries.map((entry, index) => <li key={index}><code>{entry}</code></li>)}</ul> : <p>{empty}</p>}</div>;
}
function ValidatedDeclaration({ report }: { report: ValidExtensionAuthoringReport }) {
  const manifest = report.manifest;
  return <section className="extension-author-declarations" aria-label="Validated extension declarations">
    <div className="extension-author-facts"><span><small>Template / maturity</small><b>{report.template_kind} · {display(manifest.maturity)}</b></span>
      <span><small>State owner</small><b>{report.state_responsibility.owner}</b></span>
      <span><small>State namespace</small><code>{report.state_responsibility.namespace}</code></span>
      <span><small>State schema</small><code>{report.state_responsibility.schema_version}</code></span></div>
    <p>{report.execution_scope}</p>
    <div className="extension-author-contract-grid">
      <Declaration title="Data roles · declared input contracts" entries={authoringRecords(manifest.data_roles).map(role => `${display(role.role)} · ${role.required === true ? "required" : "optional"} · ${authoringStrings(role.formats).join(", ")} · ${display(role.unit)}`)} empty="No data roles declared." />
      <Declaration title="Provided capabilities" entries={authoringStrings(manifest.provided_capabilities)} empty="None declared." />
      <Declaration title="Required capabilities" entries={authoringStrings(manifest.required_capabilities)} empty="None declared." />
      <Declaration title="Lifecycle hooks" entries={authoringRecords(manifest.hooks).map(hook => `${display(hook.hook)} → ${display(hook.implementation)}`)} empty="No hooks declared." />
      <Declaration title="Composed modules" entries={authoringStrings(manifest.composed_module_ids)} empty="No additional modules composed." />
      <Declaration title="Parameters" entries={authoringRecords(manifest.parameters).map(parameter => `${display(parameter.name)} · ${display(parameter.value_type)} · default ${display(parameter.default)}`)} empty="No parameters declared." />
      <Declaration title="Result schema and summary fields" entries={authoringRecords(manifest.artifacts).map(artifact => `${display(artifact.artifact_type)} · ${display(artifact.schema_version)} · ${authoringStrings(artifact.summary_fields).join(", ")}`)} empty="No result artifact declared." />
      <Declaration title="State migrations" entries={isAuthoringRecord(manifest.state_migrations) ? Object.entries(manifest.state_migrations).map(([schema, method]) => `${schema} → ${display(method)}`) : []} empty="No state migration declared; use a new namespace for this demonstration." />
    </div>
    <details><summary>Complete validated manifest</summary><pre>{JSON.stringify(manifest, null, 2)}</pre></details>
    <dl className="extension-author-identities"><div><dt>Manifest SHA-256</dt><dd><code>{report.manifest_sha256}</code></dd></div><div><dt>Package identity SHA-256</dt><dd><code>{report.package_identity_sha256}</code></dd></div><div><dt>Python source package</dt><dd><code>{report.source_package}</code></dd></div></dl>
  </section>;
}

export default function ExtensionAuthorWorkbench({ onInstallRequest, onOpenStudies, extensions = [], modules = [] }: Props) {
  const fieldId = useId();
  const [proposal, setProposal] = useState<ExtensionProposal>({
    id: "my-audit-extension", name: "My research audit observer", namespace: "local.research-audit", version: "0.1.0",
    question: "", validation_plan: "Check the emitted year and source_inputs_sha256 against the frozen Run input record.",
    migration_notes: "New namespace; no existing state migration.",
  });
  const [advanced, setAdvanced] = useState(false);
  const [manifestText, setManifestText] = useState("");
  const [state, setState] = useState<ReportState>();
  const [reviewRequired, setReviewRequired] = useState(false);
  const [validatingKey, setValidatingKey] = useState("");
  const [download, setDownload] = useState<{ key: string; error?: string; done?: boolean }>();
  const [downloadingKey, setDownloadingKey] = useState("");
  const validationAbort = useRef<AbortController | null>(null);
  const downloadAbort = useRef<AbortController | null>(null);
  const normalized = Object.fromEntries(Object.entries(proposal).map(([key, value]) => [key, value.trim()])) as ExtensionProposal;
  let request: ExtensionAuthoringRequest | undefined;
  let localError = "";
  if (Object.values(normalized).some(value => !value)) localError = "Complete the proposal, research question, validation plan and migration notes.";
  else if (advanced) {
    try {
      const manifest: unknown = JSON.parse(manifestText);
      if (!isAuthoringRecord(manifest)) localError = "The advanced manifest must be a JSON object.";
      else request = { proposal: normalized, manifest };
    } catch { localError = "Enter a complete JSON manifest, or turn off advanced editing to use the server template."; }
  } else request = { proposal: normalized };
  const requestText = request ? JSON.stringify(request) : "";
  // The raw editor state also participates: even a whitespace edit requires
  // another explicit review before a package can be downloaded.
  const requestKey = JSON.stringify([proposal, advanced, manifestText, requestText]);
  const currentKey = useRef(requestKey);
  const report = state?.key === requestKey && state.requestText === requestText ? state.report : undefined;
  const error = state?.key === requestKey ? state.error : undefined;
  const currentDownload = download?.key === requestKey ? download : undefined;
  const validating = validatingKey === requestKey;
  const downloading = downloadingKey === requestKey;
  const canDownload = Boolean(request && report?.valid && !report.errors.length && !validating && !downloading);
  const stale = reviewRequired || Boolean(state && state.key !== requestKey);
  const reusedNamespace = extensions.some(extension => extension.namespace === normalized.namespace || extension.id === normalized.id);

  useLayoutEffect(() => {
    currentKey.current = requestKey;
    return () => { validationAbort.current?.abort(); downloadAbort.current?.abort(); };
  }, [requestKey]);

  function invalidate() {
    validationAbort.current?.abort();
    downloadAbort.current?.abort();
    // Discard approval as well as hiding it: reverting an edit must not revive
    // a report or an in-flight package request from an earlier review.
    setReviewRequired(current => current || Boolean(state));
    setState(undefined);
    setValidatingKey("");
    setDownloadingKey("");
    setDownload(undefined);
  }
  function changeProposal(key: keyof ExtensionProposal, value: string) {
    invalidate();
    setProposal(current => ({ ...current, [key]: value }));
  }
  async function validate() {
    if (!request || localError) return;
    invalidate();
    const abort = new AbortController(); validationAbort.current = abort;
    const key = requestKey, text = requestText, reviewedProposal = request.proposal;
    setReviewRequired(false); setValidatingKey(key); setState({ key, requestText: text }); setDownload(undefined);
    try {
      const response = await fetch(apiUrl("extensions/authoring/validate"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: text, signal: abort.signal, cache: "no-store",
      });
      const body: unknown = await response.json();
      if (!isExtensionAuthoringReport(body)) throw new Error(failure(body, "The validation response does not match value.extension-authoring/v1."));
      if (!sameProposal(body.proposal, reviewedProposal)) throw new Error("Validation returned a different proposal. Review the current request again.");
      if (!response.ok && body.valid) throw new Error(failure(body, `Extension validation failed (${response.status}).`));
      if (!abort.signal.aborted && currentKey.current === key) setState({ key, requestText: text, report: body });
    } catch (reason: unknown) {
      if (!abort.signal.aborted && currentKey.current === key) setState({ key, requestText: text, error: reason instanceof Error ? reason.message : "Extension validation unavailable." });
    } finally {
      if (!abort.signal.aborted && currentKey.current === key) setValidatingKey("");
    }
  }
  async function downloadTemplate() {
    if (!canDownload || !request || !report?.valid) return;
    downloadAbort.current?.abort();
    const abort = new AbortController(); downloadAbort.current = abort;
    const key = requestKey, reviewed = report;
    setDownloadingKey(key); setDownload({ key });
    try {
      const response = await fetch(apiUrl("extensions/authoring/template"), {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: abort.signal, cache: "no-store",
        body: JSON.stringify({ ...request, expected_package_identity_sha256: reviewed.package_identity_sha256 }),
      });
      if (!response.ok) {
        const body: unknown = await response.json();
        throw new Error(failure(body, `Extension package unavailable (${response.status}).`));
      }
      if (!(response.headers.get("content-type") ?? "").toLowerCase().includes("application/zip")) throw new Error("The server did not return an extension ZIP.");
      const blob = await response.blob();
      if (abort.signal.aborted || currentKey.current !== key) return;
      if (!blob.size) throw new Error("The extension ZIP is empty.");
      const url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url; anchor.download = `${reviewed.proposal.id}-${reviewed.proposal.version}.zip`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      setDownload({ key, done: true });
    } catch (reason: unknown) {
      if (!abort.signal.aborted && currentKey.current === key) setDownload({ key, error: reason instanceof Error ? reason.message : "Extension download unavailable." });
    } finally {
      if (!abort.signal.aborted && currentKey.current === key) setDownloadingKey("");
    }
  }
  function editValidatedManifest() {
    if (!report?.valid) return;
    invalidate(); setManifestText(JSON.stringify(report.manifest, null, 2)); setAdvanced(true);
  }

  return <section id="extension-author-workbench" className="extension-author-workbench" aria-label="Extension author workbench">
    <header><span>add new function to VALUE</span><h3>Define a bounded extension</h3><p>Describe the research question, inspect its contracts, then validate and download an installable demonstration package.</p></header>
    <div className="extension-author-boundary"><b>Experimental audit observer</b><p>The generated Python hooks observe the model year and PSM source input hash. The sample CSV role demonstrates declaration and input validation; its values are not consumed by the observer. This template adds no physical algorithm or scientific result.</p><p>Extension Python runs as trusted source in the local VALUE process. Additional lifecycle methods and new scientific logic require local development and their own validation.</p></div>
    <div className="extension-author-form">
      <label htmlFor={`${fieldId}-id`}><span>Extension ID</span><input id={`${fieldId}-id`} value={proposal.id} onChange={event => changeProposal("id", event.target.value)} /></label>
      <label htmlFor={`${fieldId}-name`}><span>Extension name</span><input id={`${fieldId}-name`} value={proposal.name} onChange={event => changeProposal("name", event.target.value)} /></label>
      <label htmlFor={`${fieldId}-namespace`}><span>State namespace</span><input id={`${fieldId}-namespace`} value={proposal.namespace} onChange={event => changeProposal("namespace", event.target.value)} /></label>
      <label htmlFor={`${fieldId}-version`}><span>Extension version</span><input id={`${fieldId}-version`} value={proposal.version} onChange={event => changeProposal("version", event.target.value)} /></label>
      <label className="extension-author-wide" htmlFor={`${fieldId}-question`}><span>Research question</span><textarea id={`${fieldId}-question`} rows={3} value={proposal.question} onChange={event => changeProposal("question", event.target.value)} placeholder="Which recorded input identity do you want this observer to expose?" /></label>
      <label className="extension-author-wide" htmlFor={`${fieldId}-validation`}><span>Validation plan</span><textarea id={`${fieldId}-validation`} rows={3} value={proposal.validation_plan} onChange={event => changeProposal("validation_plan", event.target.value)} /></label>
      <label className="extension-author-wide" htmlFor={`${fieldId}-migration`}><span>Migration notes</span><textarea id={`${fieldId}-migration`} rows={2} value={proposal.migration_notes} onChange={event => changeProposal("migration_notes", event.target.value)} /></label>
    </div>
    {reusedNamespace && <p className="extension-author-message">This ID or namespace is already present in the registry. The server will check whether the proposal requires a new identity.</p>}
    <div className="extension-author-advanced"><label className="extension-author-toggle"><input type="checkbox" checked={advanced} onChange={event => { const enabled = event.target.checked; if (enabled && !manifestText.trim() && report?.valid) setManifestText(JSON.stringify(report.manifest, null, 2)); invalidate(); setAdvanced(enabled); }} /><span>Edit complete extension manifest JSON</span></label><p>The server supplies a complete manifest on validation. Review its roles, capabilities, parameters, module composition, result schema and state responsibility. Advanced editing supports the same observer execution scope: initialize and after_psm, one JSON artifact, and summary fields from year / source_inputs_sha256. A Run records the initialize state and the after_psm artifacts only; see the README for the other hooks.</p>
      {advanced && <label htmlFor={`${fieldId}-manifest`}><span>Advanced extension manifest</span><textarea id={`${fieldId}-manifest`} className="extension-author-json" rows={16} spellCheck={false} value={manifestText} onChange={event => { invalidate(); setManifestText(event.target.value); }} /></label>}
    </div>
    {localError && <p className="extension-author-message">{localError}</p>}
    {stale && <p className="extension-author-message" role="status">The proposal changed. Validate the current request before downloading another package.</p>}
    <div className="extension-author-actions"><button type="button" className="primary" disabled={Boolean(localError) || validating || downloading} onClick={() => void validate()}>{validating ? "Validating…" : "Validate extension proposal"}</button><button type="button" className="secondary" disabled={!canDownload} onClick={() => void downloadTemplate()}>{downloading ? "Preparing ZIP…" : "Download reviewed extension ZIP"}</button>{report?.valid && <button type="button" className="text-button" onClick={editValidatedManifest}>Use validated manifest for advanced editing</button>}</div>
    {error && <p className="extension-author-message error" role="alert">{error}</p>}
    {report && <div className="extension-author-report" aria-label="Extension validation report"><b>{report.valid ? "Structural proposal validation passed" : "Proposal needs attention"}</b><p>Contract validation does not establish scientific validity.</p>{report.errors.length > 0 && <ul className="extension-author-message error">{report.errors.map((message, index) => <li key={index}>{message}</li>)}</ul>}{report.warnings.length > 0 && <ul className="extension-author-message">{report.warnings.map((message, index) => <li key={index}>{message}</li>)}</ul>}{report.valid && <ValidatedDeclaration report={report} />}</div>}
    {currentDownload?.error && <p className="extension-author-message error" role="alert">{currentDownload.error}</p>}
    {currentDownload?.done && <p className="extension-author-message" role="status">The ZIP download is ready. Install the reviewed package, open an independent Study draft and enable the experimental extension in Studies → Advanced → Optional domains, then use that draft as the Data context to bind its required roles before saving the Study.</p>}
    <section className="extension-author-next"><h4>Install, enable in a draft, bind data, then save</h4><ol><li>Install the downloaded ZIP with the existing trusted extension installer.</li><li>Open an independent Study draft. In Studies → Advanced → Optional domains, enable the installed experimental extension. Opening the draft does not save a Study.</li><li>Use that draft as the Data context so its extension roles appear. Bind an independent data pack to the package&apos;s examples/audit-input.csv or compatible files and check the declared contracts.</li><li>Return to the draft, select the bound data pack and save the Study. Check readiness before explicitly running, then open Inspect artifacts to view the recorded summary.</li></ol><div className="extension-author-actions"><button type="button" className="secondary" onClick={onInstallRequest}>Open extension installer</button><button type="button" className="secondary" onClick={onOpenStudies}>Open independent Study draft</button></div><p>The ZIP includes examples/proposal.json, examples/audit-input.csv, schemas/artifact.schema.json and a README. If you modify Python source, rebuild the inventory before installing:</p><code className="extension-author-command">python scripts/build_extension_bundle.py --project-root /path/to/extracted --output /path/to/rebuilt.zip</code></section>
    <details className="extension-author-registry"><summary>Existing registry references · {extensions.length} extensions / {modules.length} modules</summary><p>Use the existing registry identities when declaring dependencies. Installing a package does not automatically enable it in a Study.</p><ul>{extensions.map(extension => <li key={extension.id}><b>{extension.name}</b><code>{extension.id} · {extension.version} · {extension.namespace}</code><span>{extension.maturity ?? "Maturity not exposed"}{extension.enabled === false ? " · disabled" : ""}</span></li>)}</ul>{modules.length > 0 && <details><summary>Available module IDs for composition</summary><ul>{modules.map(module => <li key={module.id}><b>{module.name}</b><code>{module.id} · {module.slot} · {module.version}</code></li>)}</ul></details>}</details>
  </section>;
}
