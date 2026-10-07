"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import ModuleChainCard from "./ModuleChainCard";
import { LEARN_RUN_FREEZE_NOTE } from "../runs/runHistoryView.ts";
import "../runs/run-history.css";
import Value101NetworkExercise, { type Value101NetworkStudy } from "./Value101NetworkExercise";
import {
  VALUE_101_PROGRESS_KEY,
  type LearnTarget,
  type Value101ModuleIdentity,
  type Value101StepId,
  type Value101StudyDraft,
  type Value101TutorialDescriptor,
} from "./value101";

type RunStatus = "queued" | "snapshotting" | "running" | "cancel_requested" | "cancelled" | "completed" | "failed" | "archived" | "deleting";

type Props = {
  descriptor: Value101TutorialDescriptor;
  modules: Value101ModuleIdentity[];
  loading: boolean;
  error: string;
  onRetry: () => void;
  onOpenView: (view: LearnTarget) => void;
  baselineSaved: boolean;
  baselineInTrash: boolean;
  dayRunStatus?: RunStatus;
  annualRunStatus?: RunStatus;
  launching: boolean;
  onCreateBaselineStudy: () => void;
  onRestoreBaselineStudy: () => void;
  onRunOneDay: () => void;
  onRunFullTwoYear: () => void;
  onOpenDayRun: () => void;
  onOpenAnnualRun: () => void;
  networkStudies: Value101NetworkStudy[];
  networkRuns: { id: string; project_id: string; status: string }[];
  onNetworkStudiesCreated: (studies: Value101StudyDraft[]) => void;
  onRunNetworkStudy: (study: Value101NetworkStudy) => void;
  onOpenNetworkRun: (runId: string) => void;
};

const steps: { id: Value101StepId; number: string; title: string; time: string; copy: string }[] = [
  { id: "building-blocks", number: "01", title: "Meet the five building blocks", time: "5 min", copy: "Learn what Data, Modules, a Study, a Run and Results mean in VALUE." },
  { id: "baseline", number: "02", title: "Create the baseline Study", time: "2 min", copy: "Save the annual synthetic data, selected modules, years and parameters as one versioned Study." },
  { id: "market-day", number: "03", title: "Run one market day", time: "1–3 min", copy: "Clear 48 half-hours with the selected production PSM. No CEM stage is called." },
  { id: "market-evidence", number: "04", title: "Read bids, dispatch and curtailment", time: "5 min", copy: "Inspect submitted offers, accepted energy, storage operation and unused VRE period by period." },
  { id: "annual-run", number: "05", title: "Run the complete two-year model", time: "Long run", copy: "Clear all 17,520 half-hours in 2025, run investment and planning, build the 2026 state, then clear all 17,520 periods in 2026." },
  { id: "annual-evidence", number: "06", title: "Read annual evolution", time: "5 min", copy: "Inspect annual cost, revenue, carbon, capacity, investment, planning and curtailment evidence." },
  { id: "research-model", number: "07", title: "Build a research model", time: "Reference", copy: "Install a real Data Pack, compatible Module bundle, or new optional domain through the ordinary workbench." },
  { id: "network", number: "08", title: "Optional zonal redispatch", time: "Optional", copy: "Compare the copperplate market with the installed fixed-zonal transport and pay-as-bid redispatch method." },
];

function readProgress(): Value101StepId[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(VALUE_101_PROGRESS_KEY) ?? "[]");
    const valid = new Set(steps.map((step) => step.id));
    return Array.isArray(parsed)
      ? parsed.filter((item): item is Value101StepId => typeof item === "string" && valid.has(item as Value101StepId))
      : [];
  } catch {
    return [];
  }
}

function active(status?: RunStatus) {
  return ["queued", "snapshotting", "running", "cancel_requested"].includes(status ?? "");
}

export default function Value101Learn({
  descriptor, modules, loading, error, onRetry, onOpenView, baselineSaved, baselineInTrash,
  dayRunStatus, annualRunStatus, launching, onCreateBaselineStudy, onRunOneDay,
  onRestoreBaselineStudy, onRunFullTwoYear, onOpenDayRun, onOpenAnnualRun, networkStudies, networkRuns,
  onNetworkStudiesCreated, onRunNetworkStudy, onOpenNetworkRun,
}: Props) {
  const [completed, setCompleted] = useState<Value101StepId[]>([]);
  const [lessonOpen, setLessonOpen] = useState(false);
  const completedRef = useRef<Value101StepId[]>([]);
  const lessonRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const stored = readProgress();
      completedRef.current = stored;
      setCompleted(stored);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => {
    if (lessonOpen) lessonRef.current?.focus({ preventScroll: false });
  }, [lessonOpen]);

  const baselineModules = useMemo(() => {
    const selectedIds = new Set(Object.values(descriptor.study.modules));
    return modules.filter((module) => selectedIds.has(module.id)).sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  }, [descriptor.study.modules, modules]);

  function mark(step: Value101StepId) {
    const next = completedRef.current.includes(step) ? completedRef.current : [...completedRef.current, step];
    completedRef.current = next;
    window.localStorage.setItem(VALUE_101_PROGRESS_KEY, JSON.stringify(next));
    setCompleted(next);
  }

  function action(step: Value101StepId) {
    if (step === "building-blocks") return <button className="secondary" onClick={() => { setLessonOpen(true); mark(step); }}>Open lesson</button>;
    if (step === "baseline") return <button className="secondary" disabled={baselineSaved || loading} onClick={() => { if (baselineInTrash) onRestoreBaselineStudy(); else onCreateBaselineStudy(); mark(step); }}>{baselineSaved ? "Study created" : baselineInTrash ? "Restore baseline" : "Create baseline Study"}</button>;
    if (step === "market-day") return <button className="secondary" disabled={!baselineSaved || launching} onClick={() => { mark(step); dayRunStatus ? onOpenDayRun() : onRunOneDay(); }}>{active(dayRunStatus) ? "Open running day" : dayRunStatus ? "Open day result" : "Run one market day"}</button>;
    if (step === "market-evidence") return <button className="secondary" disabled={!dayRunStatus} onClick={() => { mark(step); onOpenView("marketReplay"); }}>Open Market replay</button>;
    if (step === "annual-run") return <button className="secondary" disabled={!baselineSaved || launching} onClick={() => { mark(step); annualRunStatus ? onOpenAnnualRun() : onRunFullTwoYear(); }}>{active(annualRunStatus) ? "Open running model" : annualRunStatus ? "Open annual result" : "Run complete two-year model"}</button>;
    if (step === "annual-evidence") return <button className="secondary" disabled={!annualRunStatus} onClick={() => { mark(step); onOpenAnnualRun(); }}>Open annual results</button>;
    if (step === "research-model") return <button className="secondary" onClick={() => { mark(step); onOpenView("extend"); }}>Open research build routes</button>;
    return <button className="secondary" onClick={() => { mark(step); onOpenView("networkRedispatch"); }}>Open network results</button>;
  }

  return <div className="page learn-page value101-page">
    <section className="learn-hero value101-hero">
      <div><span className="kicker">Start here</span><h2>Build and inspect your first VALUE model</h2><p>VALUE 101 uses one annual CC0 synthetic Data Pack and the same public PSM and CEM contracts as the research workbench.</p>
        <div className="learn-actions"><button className="primary" disabled={loading || !descriptor.availability.all_packs_installed || baselineSaved} onClick={() => { if (baselineInTrash) onRestoreBaselineStudy(); else onCreateBaselineStudy(); mark("baseline"); }}>{baselineSaved ? "Baseline Study created" : baselineInTrash ? "Restore baseline" : "Create baseline Study"}</button><button className="secondary" disabled={!baselineSaved || launching} onClick={() => { dayRunStatus ? onOpenDayRun() : onRunOneDay(); mark("market-day"); }}>{dayRunStatus ? "Open one-day result" : "Run one market day"}</button></div>
        <small>Creating a Study saves a model configuration. A Run is a separate execution of that saved revision.</small></div>
      <aside className="learn-score" aria-label="VALUE 101 progress"><small>Your progress</small><strong>{completed.length}<span> / {steps.length}</span></strong><div><i style={{ width: `${completed.length / steps.length * 100}%` }} /></div><p>Stored only in this browser.</p></aside>
    </section>

    <section className="teaching-boundary" aria-label="Scientific boundary"><div><span>Two clocks, one annual pack</span><b>{descriptor.scientific_boundary.label}</b></div><p>The short lesson reads the first {descriptor.scientific_boundary.one_day_periods} half-hours and runs only the PSM. The complete route runs {descriptor.scientific_boundary.periods_per_year.toLocaleString()} half-hours in each of two years and includes the CEM chain.</p></section>
    {(error || (!loading && !descriptor.availability.all_packs_installed)) && <section className="learn-blocked" role="alert"><div><span>Teaching inputs are not ready</span><h3>VALUE 101 cannot start yet</h3><p>{error || descriptor.availability.corrective_action}</p></div><button className="secondary" onClick={onRetry}>Check again</button></section>}

    {lessonOpen && <section ref={lessonRef} className="learn-first-lesson" role="region" tabIndex={-1} aria-labelledby="value101-first-lesson-title"><header><div><span>VALUE 101 · Lesson 1</span><h3 id="value101-first-lesson-title">The five objects you will use</h3></div><button className="text-button" onClick={() => setLessonOpen(false)}>Close</button></header><p className="learn-first-lesson-intro">VALUE separates supplied evidence from model choices and execution records, so another modeller can see exactly what changed.</p><ol>{descriptor.concepts.map((concept, index) => <li key={concept.id}><i>{String(index + 1).padStart(2, "0")}</i><div><h4>{concept.label}</h4><p>{concept.plain_language}</p></div></li>)}</ol><div className="learn-first-lesson-flow" aria-label="VALUE workflow"><b>Data</b><i>+</i><b>Modules</b><i>→</i><b>Study</b><i>→</i><b>Run</b><i>→</i><b>Results</b></div></section>}

    <div className="learn-layout"><section className="learn-course" aria-labelledby="value101-course-title"><header><div><span>Guided model lesson</span><h3 id="value101-course-title">From one market day to two annual states</h3></div></header>{launching && <p className="run-launch-note value-new-control" role="status">{LEARN_RUN_FREEZE_NOTE}</p>}{steps.map((step) => <article key={step.id} className={completed.includes(step.id) ? "complete" : ""}><i>{step.number}</i><div><h4>{step.title}</h4><small>{step.time}</small><p>{step.copy}</p></div><div className="learn-step-action">{action(step.id)}</div></article>)}</section><aside className="learn-concepts"><span>Annual synthetic system</span><h3>What is actually modelled</h3><ul><li>Solar, wind, CCGT, imports and battery storage</li><li>One unconstrained national market in the baseline</li><li>A planning project and annual PSM–investment–planning state transition</li><li>17,520 half-hours per full model year</li><li>Synthetic economics and evolution, not a GB benchmark</li></ul></aside></div>

    <section className="value101-experiments" aria-label="Build a research model"><header><span>Build a research model</span><h3>Use the real installation contracts</h3><p>These routes install model inputs or executable code. They do not swap a hidden preset.</p></header><div>
      <article><h4>Replace the data</h4><p>Map your files to the 25 roles with declared formats, units and clocks, validate the bundle, then install it as a selectable Data Pack.</p><button className="secondary" onClick={() => onOpenView("data")}>Open Data and mappings</button></article>
      <article><h4>Replace modules</h4><p>Choose a Study slot, implement its entry point and tests, package the bundle, install it, and select it in Advanced Study settings.</p><button className="secondary" onClick={() => onOpenView("models")}>Open Modules</button></article>
      <article><h4>Add a model domain</h4><p>Define conditional data roles, typed contracts, lifecycle hooks, state and result artifacts in an extension bundle.</p><button className="secondary" onClick={() => onOpenView("extend")}>Open Add data and extensions</button></article>
    </div></section>

    <Value101NetworkExercise baselineStudyId={descriptor.study.id} installed={descriptor.availability.optional_network_pack?.installed === true} savedStudies={networkStudies} runs={networkRuns} launching={launching} onStudiesCreated={onNetworkStudiesCreated} onRunStudy={onRunNetworkStudy} onOpenRun={onOpenNetworkRun} />

    <section className="value101-chain" aria-label="VALUE 101 baseline module chain"><header><div><span>Selected executable chain</span><h3>What the complete two-year route calls</h3><p>Module IDs, versions, contracts and implementation locations come from the live VALUE registry.</p></div><strong>{baselineModules.length}<small> / 7 modules resolved</small></strong></header>{baselineModules.length !== 7 && <div className="error-box">The baseline module chain is incomplete. Refresh the local workspace before creating a Study.</div>}<div>{baselineModules.map((module, index) => <ModuleChainCard key={module.id} module={module} sequence={index + 1} />)}</div></section>
  </div>;
}
