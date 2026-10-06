"use client";

import { useState } from "react";
import { StatusPill } from "../shared/Callout";
import { methodologyUse, validationLayers, type CachedValidationStatus, type DataPackValidationReport } from "./dataPackValidation.ts";
import "./data-pack-validation.css";

/**
 * Spec 11.2 (S-D2): the three validation layers of one data pack and whether
 * each methodology profile may use it, with the findings behind a toggle.
 */
export default function DataPackValidationPanel({ packId, report, cached, loading, error, onRetry }: {
  packId: string;
  report?: DataPackValidationReport | null;
  cached?: CachedValidationStatus | null;
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const layers = validationLayers(report, cached);
  const uses = methodologyUse(report, cached);
  const rows = layers.filter((layer) => layer.rows.length);
  const detailsId = `data-pack-validation-${packId}`;
  return <section className="panel data-pack-validation value-new-control" aria-label={`Validation of data pack ${packId}`} aria-busy={Boolean(loading)}>
    <div className="data-pack-validation-row">
      <b>Validation</b>
      {layers.map((layer) => <span key={layer.key}><small>{layer.label}</small><StatusPill tone={layer.pill.tone} title={layer.pill.title}>{layer.pill.tone !== "muted" && <i aria-hidden="true">● </i>}{layer.pill.text}</StatusPill></span>)}
    </div>
    <div className="data-pack-validation-row">
      <b>Methodology use</b>
      {uses.map((use) => <span key={use.profileId}><small>{use.label}</small><StatusPill tone={use.pill.tone} title={use.pill.title}>{use.pill.tone !== "muted" && <i aria-hidden="true">● </i>}{use.pill.text}</StatusPill></span>)}
    </div>
    {loading && <p className="data-pack-validation-note" role="status">Validating the pack…</p>}
    {error && <p className="data-pack-validation-note error" role="alert">Validation could not be loaded: {error}{onRetry && <> <button type="button" className="data-pack-validation-toggle" onClick={onRetry}>Retry</button></>}</p>}
    {rows.length > 0 && <>
      <button type="button" className="data-pack-validation-toggle" aria-expanded={open} aria-controls={detailsId} onClick={() => setOpen(!open)}>{open ? "Hide details ▴" : "Show details ▾"}</button>
      {open && <div id={detailsId} className="data-pack-validation-details">{rows.map((layer) => <section key={layer.key}>
        <h4>{layer.label}</h4>
        <ul>{layer.rows.map((row, index) => <li key={`${row.code}-${index}`} className={row.severity}><code>{row.code}</code>{row.object && <span className="data-pack-validation-object">{row.object}</span>}<span>{row.message}</span></li>)}</ul>
      </section>)}</div>}
    </>}
  </section>;
}
