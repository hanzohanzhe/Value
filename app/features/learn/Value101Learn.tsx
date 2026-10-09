"use client";

// Learn · VALUE 101 (/learn), P1 spec 6.1: the lesson steps and the optional
// network exercise.  Wording from the dictionaries (learn.*); the tutorial
// descriptor's own text comes from the local service.  Progress is kept in
// localStorage; every access is wrapped, so blocked storage only loses the ticks.
import { useEffect, useMemo, useRef, useState } from "react";
import { useT } from "../../i18n/LocaleProvider";
import type { MessageKey } from "../../i18n/index.ts";

import ModuleChainCard from "./ModuleChainCard";
import { learnRunFreezeNote, snapshottingNote } from "../runs/runHistoryView.ts";
import { formatNumber } from "../shared/format.ts";
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
  /** A24-5: lesson Runs whose inputs are being frozen, with their stage and elapsed time. */
  preparations?: { id: string; label: string; text: string }[];
};

// The lesson steps in order; wording is learn.step.<key>.title|time|copy.
const steps: { id: Value101StepId; number: string; key: string }[] = [
  { id: "building-blocks", number: "01", key: "buildingBlocks" },
  { id: "baseline", number: "02", key: "baseline" },
  { id: "market-day", number: "03", key: "marketDay" },
  { id: "market-evidence", number: "04", key: "marketEvidence" },
  { id: "annual-run", number: "05", key: "annualRun" },
  { id: "annual-evidence", number: "06", key: "annualEvidence" },
  { id: "research-model", number: "07", key: "researchModel" },
  { id: "network", number: "08", key: "network" },
];
const stepText = (key: string, part: "title" | "time" | "copy") => ("learn.step." + key + "." + part) as MessageKey;

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

/** False when the browser refuses storage (private window, blocked site data, full quota). */
function writeProgress(progress: Value101StepId[]): boolean {
  try {
    window.localStorage.setItem(VALUE_101_PROGRESS_KEY, JSON.stringify(progress));
    return true;
  } catch {
    return false;
  }
}

function active(status?: RunStatus) {
  return ["queued", "snapshotting", "running", "cancel_requested"].includes(status ?? "");
}

export default function Value101Learn({
  descriptor, modules, loading, error, onRetry, onOpenView, baselineSaved, baselineInTrash,
  dayRunStatus, annualRunStatus, launching, onCreateBaselineStudy, onRunOneDay,
  onRestoreBaselineStudy, onRunFullTwoYear, onOpenDayRun, onOpenAnnualRun, networkStudies, networkRuns,
  onNetworkStudiesCreated, onRunNetworkStudy, onOpenNetworkRun, preparations = [],
}: Props) {
  const t = useT();
  const [completed, setCompleted] = useState<Value101StepId[]>([]);
  const [progressStored, setProgressStored] = useState(true);
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
    setProgressStored(writeProgress(next));
    setCompleted(next);
  }

  function action(step: Value101StepId) {
    if (step === "building-blocks") return <button className="secondary" onClick={() => { setLessonOpen(true); mark(step); }}>{t("learn.action.openLesson")}</button>;
    if (step === "baseline") return <button className="secondary" disabled={baselineSaved || loading} onClick={() => { if (baselineInTrash) onRestoreBaselineStudy(); else onCreateBaselineStudy(); mark(step); }}>{baselineSaved ? t("learn.action.studyCreated") : baselineInTrash ? t("learn.restoreBaseline") : t("learn.createBaseline")}</button>;
    if (step === "market-day") return <button className="secondary" disabled={!baselineSaved || launching} onClick={() => { mark(step); if (dayRunStatus) onOpenDayRun(); else onRunOneDay(); }}>{active(dayRunStatus) ? t("learn.action.openRunningDay") : dayRunStatus ? t("learn.action.openDayResult") : t("learn.runOneDay")}</button>;
    if (step === "market-evidence") return <button className="secondary" disabled={!dayRunStatus} onClick={() => { mark(step); onOpenView("marketReplay"); }}>{t("learn.action.openReplay")}</button>;
    if (step === "annual-run") return <button className="secondary" disabled={!baselineSaved || launching} onClick={() => { mark(step); if (annualRunStatus) onOpenAnnualRun(); else onRunFullTwoYear(); }}>{active(annualRunStatus) ? t("learn.action.openRunningModel") : annualRunStatus ? t("learn.action.openAnnualResult") : t("learn.action.runTwoYear")}</button>;
    if (step === "annual-evidence") return <button className="secondary" disabled={!annualRunStatus} onClick={() => { mark(step); onOpenAnnualRun(); }}>{t("learn.action.openAnnualResults")}</button>;
    if (step === "research-model") return <button className="secondary" onClick={() => { mark(step); onOpenView("extend"); }}>{t("learn.action.openBuildRoutes")}</button>;
    return <button className="secondary" onClick={() => { mark(step); onOpenView("networkRedispatch"); }}>{t("learn.action.openNetworkResults")}</button>;
  }

  return <div className="page learn-page value101-page">
    <section className="learn-hero value101-hero">
      <div><span className="kicker">{t("learn.kicker")}</span><h2>{t("learn.title")}</h2><p>{t("learn.lead")}</p>
        <div className="learn-actions"><button className="primary" disabled={loading || !descriptor.availability.all_packs_installed || baselineSaved} onClick={() => { if (baselineInTrash) onRestoreBaselineStudy(); else onCreateBaselineStudy(); mark("baseline"); }}>{baselineSaved ? t("learn.baselineCreated") : baselineInTrash ? t("learn.restoreBaseline") : t("learn.createBaseline")}</button><button className="secondary" disabled={!baselineSaved || launching} onClick={() => { if (dayRunStatus) onOpenDayRun(); else onRunOneDay(); mark("market-day"); }}>{dayRunStatus ? t("learn.openOneDay") : t("learn.runOneDay")}</button></div>
        <small>{t("learn.studyVsRun")}</small></div>
      <aside className="learn-score" aria-label={t("learn.progressLabel")}><small>{t("learn.progress")}</small><strong>{completed.length}<span> / {steps.length}</span></strong><div><i style={{ width: `${completed.length / steps.length * 100}%` }} /></div><p>{progressStored ? t("learn.progressStored") : t("learn.progressUnavailable")}</p></aside>
    </section>

    <section className="teaching-boundary" aria-label={t("learn.boundaryLabel")}><div><span>{t("learn.boundaryKicker")}</span><b>{descriptor.scientific_boundary.label}</b></div><p>{t("learn.boundaryText", { dayPeriods: descriptor.scientific_boundary.one_day_periods, yearPeriods: formatNumber(descriptor.scientific_boundary.periods_per_year, 0) })}</p></section>
    {(error || (!loading && !descriptor.availability.all_packs_installed)) && <section className="learn-blocked" role="alert"><div><span>{t("learn.blockedKicker")}</span><h3>{t("learn.blockedTitle")}</h3><p>{error || descriptor.availability.corrective_action}</p></div><button className="secondary" onClick={onRetry}>{t("learn.checkAgain")}</button></section>}

    {lessonOpen && <section ref={lessonRef} className="learn-first-lesson" role="region" tabIndex={-1} aria-labelledby="value101-first-lesson-title"><header><div><span>{t("learn.lessonKicker")}</span><h3 id="value101-first-lesson-title">{t("learn.lessonTitle")}</h3></div><button className="text-button" onClick={() => setLessonOpen(false)}>{t("learn.close")}</button></header><p className="learn-first-lesson-intro">{t("learn.lessonIntro")}</p><ol>{descriptor.concepts.map((concept, index) => <li key={concept.id}><i>{String(index + 1).padStart(2, "0")}</i><div><h4>{concept.label}</h4><p>{concept.plain_language}</p></div></li>)}</ol><div className="learn-first-lesson-flow" aria-label={t("learn.workflowLabel")}><b>{t("learn.flowData")}</b><i>+</i><b>{t("learn.flowModules")}</b><i>→</i><b>{t("learn.flowStudy")}</b><i>→</i><b>{t("learn.flowRun")}</b><i>→</i><b>{t("learn.flowResults")}</b></div></section>}

    <div className="learn-layout"><section className="learn-course" aria-labelledby="value101-course-title"><header><div><span>{t("learn.courseKicker")}</span><h3 id="value101-course-title">{t("learn.courseTitle")}</h3></div></header>{launching && <p className="run-launch-note value-new-control" role="status">{learnRunFreezeNote()}</p>}{preparations.length > 0 && <div className="learn-run-preparation" role="status">{preparations.map((item) => <p key={item.id} className="run-preparation-progress value-new-control">{`${item.label}: ${item.text}`}</p>)}<p className="run-launch-note value-new-control">{snapshottingNote()}</p></div>}{steps.map((step) => <article key={step.id} className={completed.includes(step.id) ? "complete" : ""}><i>{step.number}</i><div><h4>{t(stepText(step.key, "title"))}</h4><small>{t(stepText(step.key, "time"))}</small><p>{t(stepText(step.key, "copy"))}</p></div><div className="learn-step-action">{action(step.id)}</div></article>)}</section><aside className="learn-concepts"><span>{t("learn.conceptsKicker")}</span><h3>{t("learn.conceptsTitle")}</h3><ul><li>{t("learn.concept1")}</li><li>{t("learn.concept2")}</li><li>{t("learn.concept3")}</li><li>{t("learn.concept4")}</li><li>{t("learn.concept5")}</li></ul></aside></div>

    <section className="value101-experiments" aria-label={t("learn.build.label")}><header><span>{t("learn.build.label")}</span><h3>{t("learn.build.title")}</h3><p>{t("learn.build.lead")}</p></header><div>
      <article><h4>{t("learn.build.dataTitle")}</h4><p>{t("learn.build.dataBody")}</p><button className="secondary" onClick={() => onOpenView("data")}>{t("learn.build.dataAction")}</button></article>
      <article><h4>{t("learn.build.modulesTitle")}</h4><p>{t("learn.build.modulesBody")}</p><button className="secondary" onClick={() => onOpenView("models")}>{t("learn.build.modulesAction")}</button></article>
      <article><h4>{t("learn.build.domainTitle")}</h4><p>{t("learn.build.domainBody")}</p><button className="secondary" onClick={() => onOpenView("extend")}>{t("learn.build.domainAction")}</button></article>
    </div></section>

    <Value101NetworkExercise baselineStudyId={descriptor.study.id} installed={descriptor.availability.optional_network_pack?.installed === true} savedStudies={networkStudies} runs={networkRuns} launching={launching} onStudiesCreated={onNetworkStudiesCreated} onRunStudy={onRunNetworkStudy} onOpenRun={onOpenNetworkRun} />

    <section className="value101-chain" aria-label={t("learn.chain.label")}><header><div><span>{t("learn.chain.kicker")}</span><h3>{t("learn.chain.title")}</h3><p>{t("learn.chain.lead")}</p></div><strong>{baselineModules.length}<small> {t("learn.chain.resolved", { total: 7 })}</small></strong></header>{baselineModules.length !== 7 && <div className="error-box">{t("learn.chain.incomplete")}</div>}<div>{baselineModules.map((module, index) => <ModuleChainCard key={module.id} module={module} sequence={index + 1} />)}</div></section>
  </div>;
}
