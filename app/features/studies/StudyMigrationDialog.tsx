"use client";

import { useEffect, useRef, useState } from "react";
import { fetchRevisionMigration, migrationRows, isRevisionMigration, type MigrationProfileChoice, type RevisionMigration } from "./studyMigration.ts";
import { DOCTORAL_OPTION_DESCRIPTION } from "./methodologyChoice.ts";
import "./methodology-selector.css";

function choiceLabel(choice: MigrationProfileChoice): string {
  if (choice.default) return "Corrected (default)";
  if (choice.frozen) return "Doctoral reproduction";
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
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const [migration, setMigration] = useState(initial);
  const [profileId, setProfileId] = useState<string | null>(initial.selected_profile_id ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const choices = migration.profile_choices ?? [];
  const rows = migrationRows(migration);

  async function classify(nextProfile: string) {
    // The choice shows at once; confirming stays disabled until its own diff is loaded,
    // and a failed load returns to the profile whose diff is on screen.
    const shown = migration.selected_profile_id ?? null;
    setProfileId(nextProfile); setBusy(true); setError("");
    try {
      const next = await fetchRevisionMigration(apiBase, projectId, nextProfile);
      setMigration(next);
      setProfileId(next.selected_profile_id ?? nextProfile);
    } catch (reason) {
      setProfileId(shown);
      setError(reason instanceof Error ? reason.message : "The changes for this methodology could not be loaded.");
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
    setBusy(true); setError("");
    try {
      const response = await fetch(`${apiBase}/projects/${encodeURIComponent(projectId)}/revision-migration`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ diff_sha256: migration.diff_sha256, ...(choices.length && profileId ? { profile_id: profileId } : {}) }),
      });
      const payload = await response.json() as ResponsePayload;
      if (!response.ok) {
        if (isRevisionMigration(payload.revision_migration)) setMigration(payload.revision_migration);
        throw new Error(payload.error ?? "The new revision could not be saved.");
      }
      onSaved(payload.project?.revision_number);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The new revision could not be saved.");
    } finally { setBusy(false); }
  }

  return <dialog ref={dialog} className="study-migration-dialog value-new-control" aria-labelledby="study-migration-title"
    onCancel={(event) => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="study-migration-title" ref={title} tabIndex={-1}>This Study needs your confirmation before it runs</h2>
    {studyName && <p className="study-migration-study">{studyName}</p>}
    <p>{version ? `VALUE ${version}` : "The installed VALUE"} changes how this Study is computed:</p>
    <ul className="study-migration-diff">{rows.map((row) => <li key={row.id}>
      <b>{row.dimension}</b> <span>{row.subject}</span>
      <span className="study-migration-change">{row.before} → {row.after}</span>
      {row.effect && <small>{row.effect}</small>}
    </li>)}</ul>
    {choices.length > 0 && <fieldset className="methodology-selector" disabled={busy}><legend>Methodology</legend>{choices.map((choice) => <label key={choice.profile_id}>
      <input type="radio" name="migration-methodology" value={choice.profile_id} checked={profileId === choice.profile_id} disabled={!choice.supported}
        onChange={() => void classify(choice.profile_id)} />
      <span><b>{choiceLabel(choice)}</b>{choice.frozen && <small>{DOCTORAL_OPTION_DESCRIPTION}</small>}
        {!choice.supported && <small className="methodology-note">Not available for this Study: {choice.unsupported_reasons.map((reason) => reason.replaceAll("_", " ")).join(", ") || "unsupported combination"}.</small>}
        {choice.matches_reference_preset && <small>This Study matches its reference settings.</small>}
      </span>
    </label>)}</fieldset>}
    {error && <p className="study-migration-error" role="alert">{error}</p>}
    <div className="study-migration-actions">
      <button type="button" className="primary" disabled={busy} onClick={() => void confirm()}>{busy ? "Saving…" : "Review and save as new revision"}</button>
      <button type="button" className="secondary" disabled={busy} onClick={onCancel}>Cancel</button>
    </div>
  </dialog>;
}
