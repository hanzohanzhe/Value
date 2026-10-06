"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import "./data-workbench.css";
import { DataWorkbenchClient } from "./client";
import { BuildBenchmark } from "./BuildBenchmark";
import { CandidateReview } from "./CandidateReview";
import { OverlayEditor } from "./OverlayEditor";
import { InstalledPacks } from "./InstalledPacks";
import { OfficialSources } from "./OfficialSources";
import type {
  CandidateReview as CandidateReviewRecord,
  CandidateSummary,
  DataJob,
  DataSourceDefinition,
  InstalledBundle,
  SourceRevision,
  ValidationReport,
} from "./types";

type Tab = "overlays" | "installed" | "sources" | "build" | "candidates";

const terminal = new Set(["completed", "failed", "cancelled"]);
const acceptedRights = new Set(["redistributable", "pointer_only", "local_use_only"]);

export default function DataWorkbench({ onWorkspaceChanged }: { onWorkspaceChanged?: () => Promise<void> | void }) {
  const client = useMemo(() => new DataWorkbenchClient(), []);
  const [tab, setTab] = useState<Tab>("installed");
  const [sources, setSources] = useState<DataSourceDefinition[]>([]);
  const [revisions, setRevisions] = useState<SourceRevision[]>([]);
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [bundles, setBundles] = useState<InstalledBundle[]>([]);
  const [job, setJob] = useState<DataJob | null>(null);
  const [selected, setSelected] = useState<CandidateSummary | null>(null);
  const [validation, setValidation] = useState<ValidationReport | null>(null);
  const [review, setReview] = useState<CandidateReviewRecord | null>(null);
  const [version, setVersion] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [accepted, setAccepted] = useState<string[]>([]);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [sourceData, revisionData, candidateData, bundleData] = await Promise.all([
        client.sources(), client.revisions(), client.candidates(), client.bundles(),
      ]);
      setSources(sourceData.sources);
      setRevisions(revisionData.revisions);
      setCandidates(candidateData.candidates.filter((item) => !item.directory_id.startsWith("overlay-")));
      setBundles(bundleData.bundles);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The local data service is unavailable.");
    }
  }, [client]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (!job || terminal.has(job.status)) return;
    const timer = window.setTimeout(async () => {
      try {
        const response = await client.job(job.job_id);
        setJob(response.job);
        if (response.job.status === "completed") void refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Job polling failed.");
      }
    }, 650);
    return () => window.clearTimeout(timer);
  }, [client, job, refresh]);

  const currentRevision = (sourceId: string) => revisions
    .filter((item) => item.source_id === sourceId && item.status !== "superseded")
    .sort((left, right) => right.publication_date.localeCompare(left.publication_date))[0];
  const pinnedSources = sources.filter((source) => Boolean(currentRevision(source.source_id)?.object_key));
  const allPinned = sources.length > 0 && sources.every((source) => {
    const revision = currentRevision(source.source_id);
    return Boolean(revision?.object_key && revision.redistribution_decision && acceptedRights.has(revision.redistribution_decision));
  });
  const requiredWaivers = validation?.issues
    .filter((issue) => issue.waivable)
    .map((issue) => String(issue.evidence.waiver_id ?? ""))
    .filter(Boolean) ?? [];
  const mechanicalFailures = validation?.issues.filter(
    (issue) => !issue.waivable && issue.code !== "DW-OWNER-001",
  ) ?? [];
  const canPromote = Boolean(
    selected && validation && mechanicalFailures.length === 0 && version.trim() && reviewer.trim()
    && requiredWaivers.every((item) => accepted.includes(item)),
  );

  async function start(operation: "discover" | "fetch" | "compile", input: Record<string, unknown>) {
    setMessage("");
    try {
      const response = await client.startJob(operation, input);
      setJob(response.job);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The job could not be started.");
    }
  }

  async function inspect(candidate: CandidateSummary) {
    setSelected(candidate); setValidation(null); setReview(null); setAccepted([]); setTab("candidates");
    try {
      const report = await client.validate(candidate.candidate_id);
      setValidation(report);
      setReview(await client.review(candidate.candidate_id));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Candidate review failed.");
    }
  }

  async function promote() {
    if (!selected || !canPromote) return;
    try {
      await client.promote(selected.candidate_id, version.trim(), reviewer.trim(), accepted);
      setMessage("The reviewed bundle was installed locally. The experimental candidate remains preserved as evidence.");
      await refresh();
      await onWorkspaceChanged?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Promotion failed without changing installed packs.");
    }
  }

  return <section className="data-workbench panel" aria-labelledby="data-workbench-title">
    <header className="data-workbench-head">
      <div><span>Official-data construction</span><h3 id="data-workbench-title">Data Workbench</h3><p>Discover, pin, compile and review source evidence. Scientific calculations stay in the Python service.</p></div>
      <span className="data-workbench-status">{job ? `${job.operation} · ${job.status}` : "Local, offline after pinning"}</span>
    </header>
    <nav className="data-workbench-tabs" aria-label="Data Workbench sections">
      {(["installed", "overlays", "sources", "build", "candidates"] as Tab[]).map((item) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item === "installed" ? "Installed packs" : item === "overlays" ? "Network overlay editor" : item === "sources" ? "Official sources" : item === "build" ? "Build benchmark" : "Candidates & review"}</button>)}
    </nav>
    {message && <p className="data-workbench-message" role="status">{message}</p>}
    {job && <div className={`data-job ${job.status}`}><div><b>{job.operation.replaceAll("_", " ")}</b><small>{job.error_code ? `${job.error_code}: ${job.error_message ?? "job failed"}` : job.status.replaceAll("_", " ")}</small></div><progress max={1} value={job.progress} />{!terminal.has(job.status) && <button className="text-button" onClick={() => void client.cancelJob(job.job_id).then((result) => setJob(result.job))}>Cancel</button>}</div>}

    {tab === "overlays" && <OverlayEditor onWorkspaceChanged={onWorkspaceChanged} />}

    {tab === "installed" && <InstalledPacks bundles={bundles} />}

    {tab === "sources" && <OfficialSources sources={sources} currentRevision={currentRevision} busy={Boolean(job && !terminal.has(job.status))} start={start} />}

    {tab === "build" && <BuildBenchmark pinnedCount={pinnedSources.length} sourceCount={sources.length} allPinned={allPinned} busy={Boolean(job && !terminal.has(job.status))} start={start} />}

    {tab === "candidates" && <CandidateReview candidates={candidates} selected={selected} validation={validation} review={review} mechanicalFailures={mechanicalFailures} requiredWaivers={requiredWaivers} accepted={accepted} version={version} reviewer={reviewer} canPromote={canPromote} inspect={inspect} promote={promote} setAccepted={setAccepted} setVersion={setVersion} setReviewer={setReviewer} />}
  </section>;
}
