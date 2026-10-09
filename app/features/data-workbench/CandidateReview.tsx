"use client";

import { Button, EmptyState } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
import type { CandidateReview as Review, CandidateSummary, ValidationIssue, ValidationReport } from "./types";

type Props = {
  candidates: CandidateSummary[];
  selected: CandidateSummary | null;
  validation: ValidationReport | null;
  review: Review | null;
  mechanicalFailures: ValidationIssue[];
  requiredWaivers: string[];
  accepted: string[];
  version: string;
  reviewer: string;
  canPromote: boolean;
  inspect: (candidate: CandidateSummary) => Promise<void>;
  promote: () => Promise<void>;
  setAccepted: (value: string[]) => void;
  setVersion: (value: string) => void;
  setReviewer: (value: string) => void;
};

// P1 W4b: dictionaries (dataWorkbench.candidate.*, dataWorkbench.review.*); the candidate list and the
// review stack on narrow screens through a container query (F2-01, data-workbench.css).
export function CandidateReview({ candidates, selected, validation, review, mechanicalFailures, requiredWaivers, accepted, version, reviewer, canPromote, inspect, promote, setAccepted, setVersion, setReviewer }: Props) {
  const t = useT();
  return <div className="candidate-layout"><aside aria-label={t("dataWorkbench.candidate.list")}>{candidates.length ? candidates.map((candidate) => <button type="button" key={candidate.candidate_id} className={selected?.candidate_id === candidate.candidate_id ? "selected" : ""} aria-pressed={selected?.candidate_id === candidate.candidate_id} onClick={() => void inspect(candidate)}><span>{t("dataWorkbench.candidate.label")}</span><b>{candidate.directory_id}</b><code>{candidate.candidate_id}</code><small>{t("dataWorkbench.candidate.notInstalled")}</small></button>) : <EmptyState className="data-workbench-empty" title={t("dataWorkbench.candidate.none")}>{t("dataWorkbench.candidate.noneBody")}</EmptyState>}</aside><div className="candidate-review">{selected && validation ? <><header><div><span>{t("dataWorkbench.review.eyebrow")}</span><h4>{selected.directory_id}</h4></div><em>{validation.status}</em></header><div className="gate-grid">{Object.entries(validation.gate_results).map(([name, status]) => <div key={name}><span>{name.replaceAll("_", " ")}</span><b>{status.replaceAll("_", " ")}</b></div>)}</div>{mechanicalFailures.length > 0 && <div className="mechanical-stop" role="alert"><b>{t("dataWorkbench.review.mechanical")}</b><p>{t("dataWorkbench.review.mechanicalBody")}</p>{mechanicalFailures.map((issue) => <small key={issue.code}>{issue.code} · {issue.message}</small>)}</div>}{review && <><div className="candidate-purpose"><div><span>{t("dataWorkbench.review.usable")}</span>{review.candidate_inventory.flatMap((item) => item.usable_for).map((item) => <b key={`yes-${item}`}>{item}</b>)}</div><div><span>{t("dataWorkbench.review.notUsable")}</span>{review.candidate_inventory.flatMap((item) => item.not_usable_for).map((item) => <b key={`no-${item}`}>{item}</b>)}</div></div><div className="candidate-next"><span>{t("dataWorkbench.review.next")}</span>{review.required_actions.map((item) => <p key={item}>{item}</p>)}</div><div className="audit-map"><span>{t("dataWorkbench.review.map")}</span>{review.audit_map_svg ? <div className="audit-map-image" role="img" aria-label={t("dataWorkbench.review.mapAria")} style={{ backgroundImage: `url("data:image/svg+xml;charset=utf-8,${encodeURIComponent(review.audit_map_svg)}")` }} /> : <p>{review.map_ids?.length ? t("dataWorkbench.review.mapObjects", { count: review.map_ids.length }) : t("dataWorkbench.review.mapRetained")}</p>}</div></>}{requiredWaivers.length > 0 && <fieldset><legend>{t("dataWorkbench.review.waivers")}</legend>{requiredWaivers.map((waiver) => <label key={waiver}><input type="checkbox" checked={accepted.includes(waiver)} onChange={(event) => setAccepted(event.target.checked ? [...accepted, waiver] : accepted.filter((item) => item !== waiver))} /><span>{waiver}</span></label>)}</fieldset>}<div className="promotion-form"><label><span>{t("dataWorkbench.review.version")}</span><input value={version} onChange={(event) => setVersion(event.target.value)} placeholder={t("dataWorkbench.review.versionPlaceholder")} /></label><label><span>{t("dataWorkbench.review.reviewer")}</span><input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder={t("dataWorkbench.review.reviewerPlaceholder")} /></label><Button variant="primary" disabled={!canPromote} disabledReason={t("dataWorkbench.review.promoteUnavailable")} onClick={() => void promote()}>{t("dataWorkbench.review.promote")}</Button><small>{t("dataWorkbench.review.attestation")}</small></div></> : <EmptyState className="data-workbench-empty" title={t("dataWorkbench.review.select")}>{t("dataWorkbench.review.selectBody")}</EmptyState>}</div></div>;
}
