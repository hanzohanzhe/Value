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

export function CandidateReview({ candidates, selected, validation, review, mechanicalFailures, requiredWaivers, accepted, version, reviewer, canPromote, inspect, promote, setAccepted, setVersion, setReviewer }: Props) {
  return <div className="candidate-layout"><aside>{candidates.length ? candidates.map((candidate) => <button key={candidate.candidate_id} className={selected?.candidate_id === candidate.candidate_id ? "selected" : ""} onClick={() => void inspect(candidate)}><span>Experimental candidate</span><b>{candidate.directory_id}</b><code>{candidate.candidate_id}</code><small>Not installed · review required</small></button>) : <div className="data-workbench-empty"><b>No candidate built</b><p>Complete source pinning and the frozen build recipe first.</p></div>}</aside><div className="candidate-review">{selected && validation ? <><header><div><span>Six-gate review</span><h4>{selected.directory_id}</h4></div><em>{validation.status}</em></header><div className="gate-grid">{Object.entries(validation.gate_results).map(([name, status]) => <div key={name}><span>{name.replaceAll("_", " ")}</span><b>{status.replaceAll("_", " ")}</b></div>)}</div>{mechanicalFailures.length > 0 && <div className="mechanical-stop"><b>Mechanical gate failure</b><p>Promotion is disabled. These errors cannot be waived.</p>{mechanicalFailures.map((issue) => <small key={issue.code}>{issue.code} · {issue.message}</small>)}</div>}{review && <><div className="candidate-purpose"><div><span>Usable now</span>{review.candidate_inventory.flatMap((item) => item.usable_for).map((item) => <b key={`yes-${item}`}>{item}</b>)}</div><div><span>Not usable for</span>{review.candidate_inventory.flatMap((item) => item.not_usable_for).map((item) => <b key={`no-${item}`}>{item}</b>)}</div></div><div className="candidate-next"><span>Required next</span>{review.required_actions.map((item) => <p key={item}>{item}</p>)}</div><div className="audit-map"><span>Audit map</span>{review.audit_map_svg ? <div className="audit-map-image" role="img" aria-label="Candidate audit map supplied by the backend" style={{ backgroundImage: `url("data:image/svg+xml;charset=utf-8,${encodeURIComponent(review.audit_map_svg)}")` }} /> : <p>{review.map_ids?.length ? `${review.map_ids.length} backend map objects` : "Map artifact retained in the candidate review package"}</p>}</div></>}{requiredWaivers.length > 0 && <fieldset><legend>Named scientific waivers</legend>{requiredWaivers.map((waiver) => <label key={waiver}><input type="checkbox" checked={accepted.includes(waiver)} onChange={(event) => setAccepted(event.target.checked ? [...accepted, waiver] : accepted.filter((item) => item !== waiver))} /><span>{waiver}</span></label>)}</fieldset>}<div className="promotion-form"><label><span>Version</span><input value={version} onChange={(event) => setVersion(event.target.value)} placeholder="for example gb-zonal-2026.1" /></label><label><span>Reviewer</span><input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Named scientific owner" /></label><button className="primary" disabled={!canPromote} onClick={() => void promote()}>Approve and install bundle</button><small>This records a local approval attestation. It is not a cryptographic signature.</small></div></> : <div className="data-workbench-empty"><b>Select a candidate</b><p>Review purpose, blockers, map, reconciliation, rights and named assumptions before promotion.</p></div>}</div></div>;
}
