"use client";

import { apiFetch } from "../../lib/api.ts";
import { useEffect, useRef, useState } from "react";
import { fetchRevisionMigration, migrationRows, isRevisionMigration, type MigrationProfileChoice, type RevisionMigration } from "./studyMigration.ts";
import "./methodology-selector.css";
import { useT } from "../../i18n/LocaleProvider";
import type { Translate } from "../../i18n/index.ts";
import { LocalizedError, messageOf, showMessage, type LocalizedMessage } from "../shared/localizedMessage.ts";

function choiceLabel(t: Translate, choice: MigrationProfileChoice): string {
  if (choice.default) return t("migration.corrected");
  if (choice.frozen) return t("migration.doctoral");
  return choice.label;
}

type ResponsePayload = { error?: string; error_code?: string; revision_migration?: unknown; project?: { revision_number?: number } };

/**
 * Spec 7 (X0 S11, Q13): a method or data change of a saved Study is shown as a
 * diff and saved as a new revision only after the user confirms it. Native
 * <dialog>: focus starts on the title, Esc cancels, and no Run starts here.
 */
export default function StudyMigrationDialog({ projectId, studyName, migration: initial, version, apiBase = "/api", onCancel, onSaved }: {
  projectId: string;
  studyName?: string;
  migration: RevisionMigration;
  version?: string | null;
  apiBase?: string;
  onCancel: () => void;
  onSaved: (revisionNumber: number | undefined) => void;
}) {
  const t = useT();
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const [migration, setMigration] = useState(initial);
  const [profileId, setProfileId] = useState<string | null>(initial.selected_profile_id ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<LocalizedMessage | null>(null);
  const choices = migration.profile_choices ?? [];
  const rows = migrationRows(migration);

  async function classify(nextProfile: string) {
    // The choice shows at once; confirming stays disabled until its own diff is loaded,
    // and a failed load returns to the profile whose diff is on screen.
    const shown = migration.selected_profile_id ?? null;
    setProfileId(nextProfile); setBusy(true); setError(null);
    try {
      const next = await fetchRevisionMigration(apiBase, projectId, nextProfile);
      setMigration(next);
      setProfileId(next.selected_profile_id ?? nextProfile);
    } catch (reason) {
      setProfileId(shown);
      setError(messageOf(reason, "migration.loadFailed"));
    } finally { setBusy(false); }
  }

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) {
      if (typeof element.showModal === "function") element.showModal(); else element.setAttribute("open", "");
    }
    title.current?.focus();
    return () => { if (element?.open) element.close(); };
  }, []);

  async function confirm() {
    setBusy(true); setError(null);
    try {
      const response = await apiFetch(`${apiBase}/projects/${encodeURIComponent(projectId)}/revision-migration`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ diff_sha256: migration.diff_sha256, ...(choices.length && profileId ? { profile_id: profileId } : {}) }),
      });
      const payload = await response.json() as ResponsePayload;
      if (!response.ok) {
        if (isRevisionMigration(payload.revision_migration)) setMigration(payload.revision_migration);
        throw payload.error ? new Error(payload.error) : new LocalizedError("migration.saveFailed");
      }
      onSaved(payload.project?.revision_number);
    } catch (reason) {
      setError(messageOf(reason, "migration.saveFailed"));
    } finally { setBusy(false); }
  }

  return <dialog ref={dialog} className="study-migration-dialog value-new-control" aria-labelledby="study-migration-title"
    onCancel={(event) => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="study-migration-title" ref={title} tabIndex={-1}>{t("migration.title")}</h2>
    {studyName && <p className="study-migration-study">{studyName}</p>}
    <p>{t("migration.changes", { version: version ? t("migration.version", { version }) : t("migration.installed") })}</p>
    <ul className="study-migration-diff">{rows.map((row) => <li key={row.id}>
      <b>{row.dimension}</b> <span>{row.subject}</span>
      <span className="study-migration-change">{row.before} → {row.after}</span>
      {row.effect && <small>{row.effect}</small>}
    </li>)}</ul>
    {choices.length > 0 && <fieldset className="methodology-selector" disabled={busy}><legend>{t("migration.methodology")}</legend>{choices.map((choice) => <label key={choice.profile_id}>
      <input type="radio" name="migration-methodology" value={choice.profile_id} checked={profileId === choice.profile_id} disabled={!choice.supported}
        onChange={() => void classify(choice.profile_id)} />
      <span><b>{choiceLabel(t, choice)}</b>{choice.frozen && <small>{t("studies.method.doctoralDescription")}</small>}
        {!choice.supported && <small className="methodology-note">{t("migration.unsupported", { reasons: choice.unsupported_reasons.map((reason) => reason.replaceAll("_", " ")).join(", ") || t("migration.unsupportedDefault") })}</small>}
        {choice.matches_reference_preset && <small>{t("migration.matchesPreset")}</small>}
      </span>
    </label>)}</fieldset>}
    {error && <p className="study-migration-error" role="alert">{showMessage(t, error)}</p>}
    <div className="study-migration-actions">
      <button type="button" className="primary" disabled={busy} onClick={() => void confirm()}>{t(busy ? "migration.saving" : "migration.save")}</button>
      <button type="button" className="secondary" disabled={busy} onClick={onCancel}>{t("migration.cancel")}</button>
    </div>
  </dialog>;
}
