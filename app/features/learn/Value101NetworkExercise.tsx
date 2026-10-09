"use client";

// The optional VALUE 101 network lesson (P1 spec 6.1).  F4-07: the button of a
// case opens that Study's latest Run (newest created; the workspace lists Runs
// by last update), the install hint names no platform, and the request goes
// through the single API client with the Study ID encoded.
import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useMemo, useState } from "react";
import { useT } from "../../i18n/LocaleProvider";
import { latestRunFor } from "../shared/latestRun.ts";
import { value101NetworkPairPath } from "./value101-api.mjs";

import type { Value101NetworkPair, Value101StudyDraft } from "./value101";

type TeachingRun = {
  id: string;
  project_id: string;
  status: string;
  created_at?: string | null;
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
  const t = useT();
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
  const copperplateRun = studies ? latestRunFor(runs, studies.copperplate.id) : undefined;
  const constrainedRun = studies ? latestRunFor(runs, studies.constrained.id) : undefined;

  async function request(dryRun: boolean) {
    setBusy(dryRun ? "preview" : "create");
    setError("");
    try {
      const response = await apiFetch(apiUrl(value101NetworkPairPath(baselineStudyId)), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dry_run: dryRun }),
      });
      const payload = await response.json().catch(() => ({})) as Value101NetworkPair & { error?: string };
      if (!response.ok) throw new Error(payload.error || t("learn.network.prepareFailed"));
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

  return <section className="value101-network-exercise" aria-label={t("learn.network.label")}>
    <header><div><span>{t("learn.network.kicker")}</span><h3>{t("learn.network.title")}</h3><p>{t("learn.network.lead")}</p></div><b>{t("learn.network.zones")}</b></header>
    <div className="network-method-boundary"><b>{t("learn.network.boundaryTitle")}</b><p>{t("learn.network.boundary")}</p></div>
    {!installed && <p className="error-box">{t("learn.network.notInstalled")}</p>}
    <div className="network-pair-actions"><button className="secondary" disabled={!installed || !baselineStudyId || Boolean(busy)} onClick={() => void request(true)}>{busy === "preview" ? t("learn.network.checking") : t("learn.network.preview")}</button><button className="primary" disabled={!preview?.identity.only_network_delivery_changed || Boolean(busy) || Boolean(studies)} onClick={() => void request(false)}>{busy === "create" ? t("learn.network.creating") : t("learn.network.create")}</button></div>
    {error && <p className="error-box" role="alert">{error}</p>}
    {preview && <section className="network-pair-preview"><b>{preview.identity.only_network_delivery_changed ? t("learn.network.ready") : t("learn.network.refused")}</b><dl><div><dt>{t("learn.network.aheadInputs")}</dt><dd>{preview.identity.ahead_inputs_identical ? t("learn.network.identical") : t("learn.network.different")}</dd></div><div><dt>{t("learn.network.demandAuthority")}</dt><dd>{preview.identity.same_national_demand_authority ? t("learn.network.identical") : t("learn.network.different")}</dd></div><div><dt>{t("learn.network.deliveryMethod")}</dt><dd>{preview.identity.network_method.replaceAll("_", " ")}</dd></div><div><dt>{t("learn.network.changedControls")}</dt><dd>{preview.identity.controlled_dimensions.join(", ")}</dd></div></dl><small>{t("learn.network.previewNote")}</small></section>}
    {studies && <div className="network-study-pair"><article><span>{t("learn.network.controlKicker")}</span><h4>{t("learn.network.controlTitle")}</h4><p>{t("learn.network.controlBody")}</p><button className="secondary" disabled={launching} onClick={() => runOrOpen(studies.copperplate, copperplateRun)}>{copperplateRun ? t("learn.network.openCopperplate", { status: copperplateRun.status }) : t("learn.network.runCopperplate")}</button></article><article><span>{t("learn.network.caseKicker")}</span><h4>{t("learn.network.caseTitle")}</h4><p>{t("learn.network.caseBody")}</p><button className="primary" disabled={launching} onClick={() => runOrOpen(studies.constrained, constrainedRun)}>{constrainedRun ? t("learn.network.openConstrained", { status: constrainedRun.status }) : t("learn.network.runConstrained")}</button></article></div>}
    {constrainedRun && ["completed", "archived"].includes(constrainedRun.status) && <button className="audit-link" onClick={() => onOpenRun(constrainedRun.id)}>{t("learn.network.openResults")}</button>}
  </section>;
}
