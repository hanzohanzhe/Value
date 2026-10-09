"use client";

// Learn · VALUE 101 (/learn), P1 spec 6.1.  "The latest Run" of a lesson is the
// one created last (F4-07, features/shared/latestRun.ts).
import Value101Learn from "../features/learn/Value101Learn";
import { useWorkbench } from "../features/shell/Workbench";
import { useT } from "../i18n/LocaleProvider";

export default function LearnView() {
  const t = useT();
  const { setView, workspace, setSelectedProjectId, setSelectedRunId, launching, setNotice, value101Tutorial, value101Loading, value101Error, refresh, refreshValue101Tutorial, selectRunProject, value101Project, value101Trash, value101DayRun, value101AnnualRun, value101Preparations, createValue101BaselineStudy, restoreStudyEntry, startRun } = useWorkbench();
  return <Value101Learn
      descriptor={value101Tutorial}
      modules={workspace.modules}
      loading={value101Loading}
      error={value101Error}
      onRetry={() => void refreshValue101Tutorial()}
      onOpenView={setView}
      baselineSaved={Boolean(value101Project)}
      baselineInTrash={Boolean(value101Trash)}
      dayRunStatus={value101DayRun?.status}
      annualRunStatus={value101AnnualRun?.status}
      launching={Boolean(launching)}
      onCreateBaselineStudy={() => void createValue101BaselineStudy()}
      onRestoreBaselineStudy={() => { if (value101Trash) void restoreStudyEntry(value101Trash); }}
      onRunOneDay={() => { if (value101Project) void startRun("value_101_day", value101Project); }}
      onRunFullTwoYear={() => { if (value101Project) void startRun("two_year", value101Project); }}
      onOpenDayRun={() => { if (value101Project && value101DayRun) { setSelectedProjectId(value101Project.id); setSelectedRunId(value101DayRun.id); setView("run"); } }}
      onOpenAnnualRun={() => { if (value101Project && value101AnnualRun) { selectRunProject(value101Project.id); setSelectedRunId(value101AnnualRun.id); setView("run"); } }}
      networkStudies={workspace.projects.filter((project) => project.id === "value-101-network-copperplate" || project.id === "value-101-network-constrained")}
      networkRuns={workspace.runs.filter((run) => run.project_id === "value-101-network-copperplate" || run.project_id === "value-101-network-constrained")}
      preparations={value101Preparations}
      onNetworkStudiesCreated={(studies) => { setSelectedProjectId(studies[0]?.id ?? ""); setSelectedRunId(""); setNotice(t("learn.notice.networkCreated")); void refresh(); }}
      onRunNetworkStudy={(study) => {
        const saved = workspace.projects.find((project) => project.id === study.id);
        if (saved) void startRun("two_year", saved);
        else { setNotice(t("learn.notice.networkLoading")); void refresh(); }
      }}
      onOpenNetworkRun={(runId) => { const run = workspace.runs.find((item) => item.id === runId); if (run) selectRunProject(run.project_id); setSelectedRunId(runId); setView(run?.project_id === "value-101-network-constrained" && ["completed", "archived"].includes(run.status) ? "networkRedispatch" : "run"); }}
    />;
}
