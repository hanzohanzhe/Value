"use client";

// Home (/), P1 spec 6.1: the four research-task paths with one sentence and an
// entry each; below them the service status (with the data pack of the
// selected Study, R3-04) and the three most recent Runs (newest created first,
// F4-07).  Every visible string comes from the dictionaries (home.*).
import type { MouseEvent } from "react";
import { useT } from "./i18n/LocaleProvider";
import type { MessageKey } from "./i18n/index.ts";
import { Button, Card, EmptyState } from "./ui";
import { Badge, modelDisplayName } from "./features/shared/presentation";
import { newestRuns } from "./features/shared/latestRun.ts";
import { runStartedText } from "./features/runs/runHistoryView.ts";
import { CommunityHome } from "./features/workspace/CommunityPaths";
import { plainClick } from "./features/shell/WorkspaceRail";
import { routePathname, viewHref } from "./features/shell/routes.ts";
import { useWorkbench } from "./features/shell/Workbench";
import "./features/home/home.css";

type RunLink = { id: string; project_id: string };
const RUN_STATUSES = ["queued", "snapshotting", "running", "cancel_requested", "cancelled", "completed", "failed", "archived", "deleting"];

export default function HomeView() {
  const t = useT();
  const {
    setView, activePath, setActivePath, workspace, connectionState, online, setSelectedProjectId, setSelectedRunId, setEditingBaseRevision, setEditingProjectId,
    selectedPack, selectedProject, selectedProjectPack, chooseCommunityPath, readyModules, experimentalModules, resetStudyDraft,
  } = useWorkbench();
  // R3-04: next to a selected saved Study, Home names that Study's data pack; the draft pack only when no Study is selected.
  const pack = selectedProject ? selectedProjectPack : selectedPack;
  const packLabel = selectedProject ? t("home.status.studyData") : t("home.status.draftData");
  const packName = pack ? modelDisplayName(pack.name) : selectedProject?.data_pack_id ?? t("home.status.noPack");
  const recentRuns = newestRuns(workspace.runs, 3);
  const runtimeReady = online && workspace.runtime.compatible;
  const reference = workspace.runtime.capabilities?.["doctoral-reproduction"]?.available;
  const openRun = (event: MouseEvent<HTMLAnchorElement>, run: RunLink) => {
    if (!plainClick(event)) return;
    event.preventDefault();
    setSelectedProjectId(run.project_id); setSelectedRunId(run.id); setView("run");
  };
  const statusText = (status: string) => RUN_STATUSES.includes(status) ? t(`home.run.status.${status}` as MessageKey) : status;
  const steps: { label: MessageKey; note: MessageKey }[] = [
    { label: "home.about.step1", note: "home.about.step1Note" }, { label: "home.about.step2", note: "home.about.step2Note" },
    { label: "home.about.step3", note: "home.about.stepNote" }, { label: "home.about.step4", note: "home.about.stepNote" },
    { label: "home.about.step5", note: "home.about.step5Note" }, { label: "home.about.step6", note: "home.about.stepNote" },
  ];
  const scope: { yes: boolean; title: MessageKey; note: MessageKey }[] = [
    { yes: true, title: "home.about.scope1", note: "home.about.scope1Note" }, { yes: true, title: "home.about.scope2", note: "home.about.scope2Note" },
    { yes: false, title: "home.about.scope3", note: "home.about.scope3Note" }, { yes: true, title: "home.about.scope4", note: "home.about.scope4Note" },
  ];
  return <div className="page overview home-page">
    <header className="home-hero">
      <span className="home-kicker">{t("home.kicker")}</span>
      <h2>{t("home.title")}</h2>
      <p>{t("home.lead")}</p>
      <div className="home-quick-start" role="group" aria-label={t("home.quickStart")}>
        <Button variant="primary" onClick={() => { setActivePath("reproduce"); setView("learn"); }}>{t("home.startLearn")}</Button>
        <Button onClick={() => { setSelectedProjectId(""); setSelectedRunId(""); setEditingBaseRevision(undefined); setEditingProjectId(undefined); resetStudyDraft(); setView("projects"); }}>{t("home.buildStudy")}</Button>
        <Button onClick={() => setView(workspace.projects.length ? "projects" : "learn")}>{t("home.openStudy")}</Button>
      </div>
      <small className="home-scope">{t("home.scope")}</small>
    </header>

    <CommunityHome activePath={activePath} onSelect={chooseCommunityPath} />

    <div className="home-status-grid">
      <Card className="home-status" title={t("home.status.title")} headingLevel={3}>
        <dl className="home-facts">
          <div><dt>{t("home.status.service")}</dt><dd>
            <b>{connectionState === "loading" ? t("home.status.loading") : runtimeReady ? t("home.status.online", { python: workspace.runtime.python }) : t("home.status.notReady")}</b>
            <small>{runtimeReady ? t("home.status.reference", { state: reference ? t("home.status.referenceAvailable") : t("home.status.referenceMissing") }) : connectionState === "loading" ? "" : t("home.status.startService")}</small>
          </dd></div>
          <div><dt>{t("home.status.modules")}</dt><dd>
            <b>{t("home.status.modulesValue", { ready: readyModules, total: workspace.modules.length, experimental: experimentalModules })}</b>
            <small>{t("home.status.modulesNote")}</small>
          </dd></div>
          <div><dt>{packLabel}</dt><dd>
            <b>{packName}</b>
            <small>{pack?.complete ? t("home.status.packReady") : t("home.status.packIncomplete")}</small>
          </dd></div>
        </dl>
        <Button size="sm" onClick={() => setView("data")}>{t("home.status.reviewData")}</Button>
      </Card>

      <Card className="home-runs" title={t("home.runs.title")} headingLevel={3} actions={workspace.runs.length > 0 ? <a href={viewHref("runCentre")} onClick={(event) => { if (plainClick(event)) { event.preventDefault(); setView("runCentre"); } }}>{t("home.runs.all")}</a> : undefined}>
        {recentRuns.length ? <ol className="home-run-list">{recentRuns.map((run) => {
          const started = runStartedText(run);
          return <li key={run.id}>
            <a href={routePathname({ view: "run", runId: run.id })} onClick={(event) => openRun(event, run)} aria-label={t("home.runs.open", { id: run.id })}>
              <b>{modelDisplayName(run.project_name) || run.project_id}</b>
              <small>{started ? t("home.runs.started", { time: started }) : run.mode}</small>
              <code className="home-run-id">{run.id}</code>
            </a>
            <Badge tone={run.status === "completed" ? "good" : run.status === "failed" ? "warn" : "neutral"}>{statusText(run.status)}</Badge>
          </li>;
        })}</ol> : <EmptyState title={t("home.runs.empty")}>{t("home.runs.emptyHint")}</EmptyState>}
      </Card>
    </div>

    <details className="workspace-about"><summary>{t("home.about.summary")}</summary><p><b lang="en">{t("home.about.name")}</b></p><p>{t("home.about.lead")}</p>
      <section className="annual-cycle"><header><span className="kicker">{t("home.about.cycleKicker")}</span><h3>{t("home.about.cycleTitle")}</h3></header><div className="annual-flow lifecycle-flow">{steps.map((step, index) => <div className={index === 1 ? "model-node psm" : "model-node cem"} key={step.label}><span>{String(index + 1).padStart(2, "0")}</span><b>{t(step.label)}</b><small>{t(step.note)}</small></div>)}</div></section>
      <div className="overview-grid"><section className="panel scope-panel"><div className="panel-head"><div><span>{t("home.about.scopeKicker")}</span><h3>{t("home.about.scopeTitle")}</h3></div></div><ul className="scope-list">{scope.map((item) => <li key={item.title}><i className={item.yes ? "yes" : "limit"} /><span><b>{t(item.title)}</b><small>{t(item.note)}</small></span></li>)}</ul></section>
        <section className="panel pack-panel"><div className="panel-head"><div><span>{t("home.about.inputsKicker")}</span><h3>{packName}</h3></div><Badge tone={pack?.complete ? "good" : "warn"}>{pack?.complete ? t("home.about.inputsReady") : t("home.about.inputsIncomplete")}</Badge></div><div className="pack-score"><strong>{pack?.valid_required_count ?? 0}</strong><span> / {pack?.required_count ?? 0}</span></div><p>{t("home.about.inputsNote")}</p></section></div>
    </details>
  </div>;
}
