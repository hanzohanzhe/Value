"use client";

import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useLayoutEffect, useId, useRef, useState } from "react";
import {
  authoringRecords, authoringStrings, isAuthoringRecord, isExtensionAuthoringReport, sameProposal,
  type AuthorExtension, type ExtensionAuthorModule, type ExtensionAuthoringReport,
  type ExtensionAuthoringRequest, type ExtensionProposal, type ValidExtensionAuthoringReport,
} from "./authoring.types";
import { Button } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
import type { Translate } from "../../i18n/index.ts";
import { LocalizedError, messageOf, showMessage, type LocalizedMessage } from "../shared/localizedMessage.ts";
import "./ExtensionAuthorWorkbench.css";

type Props = {
  onInstallRequest: () => void;
  onOpenStudies: () => void;
  extensions?: AuthorExtension[];
  modules?: ExtensionAuthorModule[];
};
type ReportState = { key: string; requestText: string; report?: ExtensionAuthoringReport; error?: LocalizedMessage };

/** The backend's error text (with its code) as sent, or the given dictionary message. */
function failure(body: unknown, fallback: LocalizedError): Error {
  return isAuthoringRecord(body) && typeof body.error === "string"
    ? new Error(`${typeof body.error_code === "string" ? `${body.error_code}: ` : ""}${body.error}`) : fallback;
}
function display(value: unknown, t: Translate): string {
  return typeof value === "string" ? value : value == null ? t("extensionAuthor.notDeclared") : JSON.stringify(value);
}
function Declaration({ title, entries, empty }: { title: string; entries: string[]; empty: string }) {
  return <div className="extension-author-declaration"><b>{title}</b>{entries.length
    ? <ul>{entries.map((entry, index) => <li key={index}><code>{entry}</code></li>)}</ul> : <p>{empty}</p>}</div>;
}
function ValidatedDeclaration({ report, t }: { report: ValidExtensionAuthoringReport; t: Translate }) {
  const manifest = report.manifest;
  const show = (value: unknown) => display(value, t);
  return <section className="extension-author-declarations" aria-label={t("extensionAuthor.declarations")}>
    <div className="extension-author-facts"><span><small>{t("extensionAuthor.templateMaturity")}</small><b>{report.template_kind} · {show(manifest.maturity)}</b></span>
      <span><small>{t("extensionAuthor.stateOwner")}</small><b>{report.state_responsibility.owner}</b></span>
      <span><small>{t("extensionAuthor.stateNamespace")}</small><code>{report.state_responsibility.namespace}</code></span>
      <span><small>{t("extensionAuthor.stateSchema")}</small><code>{report.state_responsibility.schema_version}</code></span></div>
    <p>{report.execution_scope}</p>
    <div className="extension-author-contract-grid">
      <Declaration title={t("extensionAuthor.dataRoles")} entries={authoringRecords(manifest.data_roles).map(role => `${show(role.role)} · ${role.required === true ? t("extensionAuthor.required") : t("extensionAuthor.optional")} · ${authoringStrings(role.formats).join(", ")} · ${show(role.unit)}`)} empty={t("extensionAuthor.noDataRoles")} />
      <Declaration title={t("extensionAuthor.provided")} entries={authoringStrings(manifest.provided_capabilities)} empty={t("extensionAuthor.noneDeclared")} />
      <Declaration title={t("extensionAuthor.requiredCapabilities")} entries={authoringStrings(manifest.required_capabilities)} empty={t("extensionAuthor.noneDeclared")} />
      <Declaration title={t("extensionAuthor.hooks")} entries={authoringRecords(manifest.hooks).map(hook => `${show(hook.hook)} → ${show(hook.implementation)}`)} empty={t("extensionAuthor.noHooks")} />
      <Declaration title={t("extensionAuthor.composed")} entries={authoringStrings(manifest.composed_module_ids)} empty={t("extensionAuthor.noComposed")} />
      <Declaration title={t("extensionAuthor.parameters")} entries={authoringRecords(manifest.parameters).map(parameter => `${show(parameter.name)} · ${show(parameter.value_type)} · ${t("extensionAuthor.parameterDefault", { value: show(parameter.default) })}`)} empty={t("extensionAuthor.noParameters")} />
      <Declaration title={t("extensionAuthor.results")} entries={authoringRecords(manifest.artifacts).map(artifact => `${show(artifact.artifact_type)} · ${show(artifact.schema_version)} · ${authoringStrings(artifact.summary_fields).join(", ")}`)} empty={t("extensionAuthor.noResults")} />
      <Declaration title={t("extensionAuthor.migrations")} entries={isAuthoringRecord(manifest.state_migrations) ? Object.entries(manifest.state_migrations).map(([schema, method]) => `${schema} → ${show(method)}`) : []} empty={t("extensionAuthor.noMigrations")} />
    </div>
    <details><summary>{t("extensionAuthor.completeManifest")}</summary><pre>{JSON.stringify(manifest, null, 2)}</pre></details>
    <dl className="extension-author-identities"><div><dt>{t("extensionAuthor.manifestSha")}</dt><dd><code>{report.manifest_sha256}</code></dd></div><div><dt>{t("extensionAuthor.packageSha")}</dt><dd><code>{report.package_identity_sha256}</code></dd></div><div><dt>{t("extensionAuthor.sourcePackage")}</dt><dd><code>{report.source_package}</code></dd></div></dl>
  </section>;
}

const BUILD_COMMAND = "python scripts/build_extension_bundle.py --project-root /path/to/extracted --output /path/to/rebuilt.zip";

export default function ExtensionAuthorWorkbench({ onInstallRequest, onOpenStudies, extensions = [], modules = [] }: Props) {
  const t = useT();
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
  const [download, setDownload] = useState<{ key: string; error?: LocalizedMessage; done?: boolean }>();
  const [downloadingKey, setDownloadingKey] = useState("");
  const validationAbort = useRef<AbortController | null>(null);
  const downloadAbort = useRef<AbortController | null>(null);
  const normalized = Object.fromEntries(Object.entries(proposal).map(([key, value]) => [key, value.trim()])) as ExtensionProposal;
  let request: ExtensionAuthoringRequest | undefined;
  let localError = "";
  if (Object.values(normalized).some(value => !value)) localError = t("extensionAuthor.incomplete");
  else if (advanced) {
    try {
      const manifest: unknown = JSON.parse(manifestText);
      if (!isAuthoringRecord(manifest)) localError = t("extensionAuthor.notObject");
      else request = { proposal: normalized, manifest };
    } catch { localError = t("extensionAuthor.notJson"); }
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
      const response = await apiFetch(apiUrl("extensions/authoring/validate"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: text, signal: abort.signal, cache: "no-store",
      });
      const body: unknown = await response.json();
      if (!isExtensionAuthoringReport(body)) throw failure(body, new LocalizedError("extensionAuthor.schemaMismatch"));
      if (!sameProposal(body.proposal, reviewedProposal)) throw new LocalizedError("extensionAuthor.differentProposal");
      if (!response.ok && body.valid) throw failure(body, new LocalizedError("extensionAuthor.validationFailed", { status: response.status }));
      if (!abort.signal.aborted && currentKey.current === key) setState({ key, requestText: text, report: body });
    } catch (reason: unknown) {
      if (!abort.signal.aborted && currentKey.current === key) setState({ key, requestText: text, error: messageOf(reason, "extensionAuthor.validationUnavailable") });
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
      const response = await apiFetch(apiUrl("extensions/authoring/template"), {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: abort.signal, cache: "no-store",
        body: JSON.stringify({ ...request, expected_package_identity_sha256: reviewed.package_identity_sha256 }),
      });
      if (!response.ok) {
        const body: unknown = await response.json();
        throw failure(body, new LocalizedError("extensionAuthor.packageUnavailable", { status: response.status }));
      }
      if (!(response.headers.get("content-type") ?? "").toLowerCase().includes("application/zip")) throw new LocalizedError("extensionAuthor.notZip");
      const blob = await response.blob();
      if (abort.signal.aborted || currentKey.current !== key) return;
      if (!blob.size) throw new LocalizedError("extensionAuthor.emptyZip");
      const url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url; anchor.download = `${reviewed.proposal.id}-${reviewed.proposal.version}.zip`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      setDownload({ key, done: true });
    } catch (reason: unknown) {
      if (!abort.signal.aborted && currentKey.current === key) setDownload({ key, error: messageOf(reason, "extensionAuthor.downloadFailed") });
    } finally {
      if (!abort.signal.aborted && currentKey.current === key) setDownloadingKey("");
    }
  }
  function editValidatedManifest() {
    if (!report?.valid) return;
    invalidate(); setManifestText(JSON.stringify(report.manifest, null, 2)); setAdvanced(true);
  }

  return <section id="extension-author-workbench" className="extension-author-workbench" aria-label={t("extensionAuthor.label")}>
    <header><span>{t("extensionAuthor.eyebrow")}</span><h3>{t("extensionAuthor.title")}</h3><p>{t("extensionAuthor.intro")}</p></header>
    <div className="extension-author-boundary"><b>{t("extensionAuthor.boundaryTitle")}</b><p>{t("extensionAuthor.boundary1")}</p><p>{t("extensionAuthor.boundary2")}</p></div>
    <div className="extension-author-form">
      <label htmlFor={`${fieldId}-id`}><span>{t("extensionAuthor.id")}</span><input id={`${fieldId}-id`} value={proposal.id} onChange={event => changeProposal("id", event.target.value)} /></label>
      <label htmlFor={`${fieldId}-name`}><span>{t("extensionAuthor.name")}</span><input id={`${fieldId}-name`} value={proposal.name} onChange={event => changeProposal("name", event.target.value)} /></label>
      <label htmlFor={`${fieldId}-namespace`}><span>{t("extensionAuthor.namespace")}</span><input id={`${fieldId}-namespace`} value={proposal.namespace} onChange={event => changeProposal("namespace", event.target.value)} /></label>
      <label htmlFor={`${fieldId}-version`}><span>{t("extensionAuthor.version")}</span><input id={`${fieldId}-version`} value={proposal.version} onChange={event => changeProposal("version", event.target.value)} /></label>
      <label className="extension-author-wide" htmlFor={`${fieldId}-question`}><span>{t("extensionAuthor.question")}</span><textarea id={`${fieldId}-question`} rows={3} value={proposal.question} onChange={event => changeProposal("question", event.target.value)} placeholder={t("extensionAuthor.questionPlaceholder")} /></label>
      <label className="extension-author-wide" htmlFor={`${fieldId}-validation`}><span>{t("extensionAuthor.validationPlan")}</span><textarea id={`${fieldId}-validation`} rows={3} value={proposal.validation_plan} onChange={event => changeProposal("validation_plan", event.target.value)} /></label>
      <label className="extension-author-wide" htmlFor={`${fieldId}-migration`}><span>{t("extensionAuthor.migrationNotes")}</span><textarea id={`${fieldId}-migration`} rows={2} value={proposal.migration_notes} onChange={event => changeProposal("migration_notes", event.target.value)} /></label>
    </div>
    {reusedNamespace && <p className="extension-author-message">{t("extensionAuthor.reused")}</p>}
    <div className="extension-author-advanced"><label className="extension-author-toggle"><input type="checkbox" checked={advanced} onChange={event => { const enabled = event.target.checked; if (enabled && !manifestText.trim() && report?.valid) setManifestText(JSON.stringify(report.manifest, null, 2)); invalidate(); setAdvanced(enabled); }} /><span>{t("extensionAuthor.advancedToggle")}</span></label><p>{t("extensionAuthor.advancedNote")}</p>
      {advanced && <label htmlFor={`${fieldId}-manifest`}><span>{t("extensionAuthor.advancedManifest")}</span><textarea id={`${fieldId}-manifest`} className="extension-author-json" rows={16} spellCheck={false} value={manifestText} onChange={event => { invalidate(); setManifestText(event.target.value); }} /></label>}
    </div>
    {localError && <p className="extension-author-message">{localError}</p>}
    {stale && <p className="extension-author-message" role="status">{t("extensionAuthor.stale")}</p>}
    <div className="extension-author-actions"><Button variant="primary" disabled={Boolean(localError) || downloading} disabledReason={localError || undefined} loading={validating} onClick={() => void validate()}>{validating ? t("extensionAuthor.validating") : t("extensionAuthor.validate")}</Button><Button disabled={!canDownload} disabledReason={downloading ? undefined : t("extensionAuthor.downloadUnavailable")} loading={downloading} onClick={() => void downloadTemplate()}>{downloading ? t("extensionAuthor.downloading") : t("extensionAuthor.download")}</Button>{report?.valid && <Button variant="ghost" onClick={editValidatedManifest}>{t("extensionAuthor.useValidated")}</Button>}</div>
    {error && <p className="extension-author-message error" role="alert">{showMessage(t, error)}</p>}
    {report && <div className="extension-author-report" aria-label={t("extensionAuthor.reportLabel")}><b>{report.valid ? t("extensionAuthor.passed") : t("extensionAuthor.needsAttention")}</b><p>{t("extensionAuthor.notScientific")}</p>{report.errors.length > 0 && <ul className="extension-author-message error">{report.errors.map((message, index) => <li key={index}>{message}</li>)}</ul>}{report.warnings.length > 0 && <ul className="extension-author-message">{report.warnings.map((message, index) => <li key={index}>{message}</li>)}</ul>}{report.valid && <ValidatedDeclaration report={report} t={t} />}</div>}
    {currentDownload?.error && <p className="extension-author-message error" role="alert">{showMessage(t, currentDownload.error)}</p>}
    {currentDownload?.done && <p className="extension-author-message" role="status">{t("extensionAuthor.ready")}</p>}
    <section className="extension-author-next"><h4>{t("extensionAuthor.nextTitle")}</h4><ol><li>{t("extensionAuthor.next1")}</li><li>{t("extensionAuthor.next2")}</li><li>{t("extensionAuthor.next3")}</li><li>{t("extensionAuthor.next4")}</li></ol><div className="extension-author-actions"><Button onClick={onInstallRequest}>{t("extensionAuthor.openInstaller")}</Button><Button onClick={onOpenStudies}>{t("extensionAuthor.openDraft")}</Button></div><p>{t("extensionAuthor.zipContents")}</p><code className="extension-author-command">{BUILD_COMMAND}</code></section>
    <details className="extension-author-registry"><summary>{t("extensionAuthor.registry", { extensions: extensions.length, modules: modules.length })}</summary><p>{t("extensionAuthor.registryNote")}</p><ul>{extensions.map(extension => <li key={extension.id}><b>{extension.name}</b><code>{extension.id} · {extension.version} · {extension.namespace}</code><span>{extension.maturity ?? t("extensionAuthor.maturityHidden")}{extension.enabled === false ? t("extensionAuthor.disabledSuffix") : ""}</span></li>)}</ul>{modules.length > 0 && <details><summary>{t("extensionAuthor.moduleIds")}</summary><ul>{modules.map(module => <li key={module.id}><b>{module.name}</b><code>{module.id} · {module.slot} · {module.version}</code></li>)}</ul></details>}</details>
  </section>;
}
