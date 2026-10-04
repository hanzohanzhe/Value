"use client";

import { useMemo, useState } from "react";

import type { Value101NetworkPair, Value101StudyDraft } from "./value101";
import { value101ApiUrl } from "./value101-api.mjs";

type TeachingRun = {
  id: string;
  project_id: string;
  status: string;
};

// This view and its actions identify saved Studies; the complete run configuration
// is resolved by the workbench, not reconstructed from a tutorial display record.
export type Value101NetworkStudy = Pick<Value101StudyDraft, "id" | "name">;

export default function Value101NetworkExercise({
  baselineStudyId,
  installed,
  savedStudies,
  runs,
  launching,
  onStudiesCreated,
  onRunStudy,
  onOpenRun,
}: {
  baselineStudyId: string;
  installed: boolean;
  savedStudies: Value101NetworkStudy[];
  runs: TeachingRun[];
  launching: boolean;
  onStudiesCreated: (studies: Value101StudyDraft[]) => void;
  onRunStudy: (study: Value101NetworkStudy) => void;
  onOpenRun: (runId: string) => void;
}) {
  const [preview, setPreview] = useState<Value101NetworkPair | null>(null);
  const [created, setCreated] = useState<Value101NetworkPair["studies"] | null>(null);
  const [busy, setBusy] = useState<"preview" | "create" | "">("");
  const [error, setError] = useState("");

  const studies = useMemo(() => {
    const byId = Object.fromEntries(savedStudies.map((study) => [study.id, study]));
    return created ?? (
      byId["value-101-network-copperplate"] && byId["value-101-network-constrained"]
        ? {
            copperplate: byId["value-101-network-copperplate"],
            constrained: byId["value-101-network-constrained"],
          }
        : null
    );
  }, [created, savedStudies]);
  const latestRun = (projectId: string) => runs.filter((run) => run.project_id === projectId).at(-1);
  const copperplateRun = studies ? latestRun(studies.copperplate.id) : undefined;
  const constrainedRun = studies ? latestRun(studies.constrained.id) : undefined;

  async function request(dryRun: boolean) {
    setBusy(dryRun ? "preview" : "create");
    setError("");
    try {
      const response = await fetch(value101ApiUrl(`/tutorials/value-101/studies/${baselineStudyId}/network-pair`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dry_run: dryRun }),
      });
      const payload = await response.json() as Value101NetworkPair & { error?: string };
      if (!response.ok) throw new Error(payload.error || "The matched network exercise could not be prepared.");
      if (dryRun) setPreview(payload);
      else {
        setCreated(payload.studies);
        onStudiesCreated([payload.studies.copperplate, payload.studies.constrained]);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy("");
    }
  }

  function runOrOpen(study: Value101NetworkStudy, run: TeachingRun | undefined) {
    if (run) onOpenRun(run.id);
    else onRunStudy(study);
  }

  return <section className="value101-network-exercise" aria-label="VALUE 101 optional network exercise">
    <header><div><span>Optional lesson</span><h3>{"Network constraints & redispatch"}</h3><p>Hold the national demand, fleet, weather, bid-at-cost ahead market and model years fixed. Both cases run all 17,520 half-hours in 2025 and 2026, including the annual investment, planning and transition chain.</p></div><b>North · Central · South</b></header>
    <div className="network-method-boundary"><b>Method boundary</b><p>This is a lossless zonal transport and pay-as-bid redispatch exercise; it is not DC load flow, AC power flow or N-1 security. It contains no transmission expansion implementation.</p></div>
    {!installed && <p className="error-box">The optional VALUE 101 network pack is not installed. Re-run the standard Windows installer; the core course remains available.</p>}
    <div className="network-pair-actions"><button className="secondary" disabled={!installed || !baselineStudyId || Boolean(busy)} onClick={() => void request(true)}>{busy === "preview" ? "Checking…" : "Preview matched pair"}</button><button className="primary" disabled={!preview?.identity.only_network_delivery_changed || Boolean(busy) || Boolean(studies)} onClick={() => void request(false)}>{busy === "create" ? "Creating…" : "Create matched Studies"}</button></div>
    {error && <p className="error-box" role="alert">{error}</p>}
    {preview && <section className="network-pair-preview"><b>{preview.identity.only_network_delivery_changed ? "Controlled pair ready" : "Controlled comparison refused"}</b><dl><div><dt>Ahead inputs</dt><dd>{preview.identity.ahead_inputs_identical ? "Identical" : "Different"}</dd></div><div><dt>National demand authority</dt><dd>{preview.identity.same_national_demand_authority ? "Identical" : "Different"}</dd></div><div><dt>Delivery method</dt><dd>{preview.identity.network_method.replaceAll("_", " ")}</dd></div><div><dt>Changed controls</dt><dd>{preview.identity.controlled_dimensions.join(", ")}</dd></div></dl><small>The ahead schedule is checked from stored results after both Runs; this preview does not claim an outcome.</small></section>}
    {studies && <div className="network-study-pair"><article><span>Control</span><h4>Copperplate delivery</h4><p>National ahead market followed by unconstrained balancing.</p><button className="secondary" disabled={launching} onClick={() => runOrOpen(studies.copperplate, copperplateRun)}>{copperplateRun ? `Open copperplate · ${copperplateRun.status}` : "Run copperplate"}</button></article><article><span>Network case</span><h4>Fixed three-zone delivery</h4><p>The same ahead market followed by constrained zonal redispatch.</p><button className="primary" disabled={launching} onClick={() => runOrOpen(studies.constrained, constrainedRun)}>{constrainedRun ? `Open constrained · ${constrainedRun.status}` : "Run constrained"}</button></article></div>}
    {constrainedRun && ["completed", "archived"].includes(constrainedRun.status) && <button className="audit-link" onClick={() => onOpenRun(constrainedRun.id)}>Open network results</button>}
  </section>;
}
