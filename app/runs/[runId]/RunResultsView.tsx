"use client";

// One Run's annual results (/runs/[runId]?year=, P1 spec 5.1 and 6.5; W4c).
// The model year is in the URL: a link or a reload opens the same year.
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import RunResultsPage, { resultYears } from "../../features/runs/RunResultsPage";
import { resultYearFromSearch } from "../../features/runs/resultYear.ts";
import { replacePageQuery } from "../../features/shell/routes.ts";
import { useWorkbench } from "../../features/shell/Workbench";

export default function RunResultsView() {
  const { selectedRun, launching, openView, setView, setInspectTarget, onRecoveredStudyCreated, selectedRunSourceMutable, selectedRunContext, frozenRunSelectionId, frozenRunReadiness, frozenRunProject, frozenInputSnapshot, resumeRun, resubmitRun, rerunAsCopperplate, lifecycleAction, markRunLost } = useWorkbench();
  const linked = useSearchParams()?.get("year");
  const [chosen, setChosen] = useState<{ runId: string; year: number } | null>(null);
  const years = resultYears(selectedRun);
  const year = chosen && chosen.runId === selectedRun?.id && years.includes(chosen.year)
    ? chosen.year
    : resultYearFromSearch(linked ? `?year=${linked}` : "", years);
  return <RunResultsPage run={selectedRun} launching={launching} year={year}
    onYearChange={(value) => { if (selectedRun) setChosen({ runId: selectedRun.id, year: value }); replacePageQuery({ year: value }); }}
    onOpenRunCentre={() => openView("runCentre")}
    onOpenInspect={() => openView("audit")}
    onOpenArtifacts={() => { setInspectTarget({ tab: "artifacts", nonce: Date.now() }); setView("audit"); }}
    onRecoveredStudyCreated={onRecoveredStudyCreated}
    selectedRunSourceMutable={selectedRunSourceMutable}
    frozen={{ contextKind: selectedRunContext.kind, runId: frozenRunSelectionId, readiness: frozenRunReadiness, project: frozenRunProject, snapshot: frozenInputSnapshot }}
    actions={{ resumeRun, resubmitRun, rerunAsCopperplate, lifecycleAction, markLost: markRunLost }} />;
}
