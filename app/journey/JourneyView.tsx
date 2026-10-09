"use client";

// The research guide (/journey), P1 spec 5.1/6.1 and D-W3-2: an ordinary route
// page.  The task switch belongs here only, with the current task selected
// (R3-07).  The guide's typed progress is remembered for the session
// (ResearchJourney's journeyMemory) and its target pack lives in the workbench,
// so the trip to Data and back keeps both.
import ResearchJourney from "../features/workspace/ResearchJourney";
import { CommunityPathPicker } from "../features/workspace/CommunityPaths";
import { useWorkbench } from "../features/shell/Workbench";
import { useT } from "../i18n/LocaleProvider";

export default function JourneyView() {
  const t = useT();
  const {
    activePath, chooseCommunityPath, workspace, methodologyCatalogue, selectedProjectId, online, journeyTargetPackId, setJourneyTargetPackId, refresh,
    setSelectedProjectId, setSelectedRunId, setPreflight, setView, setNotice, setJourneyData, setDataContextId, setSavedDataResolution, setDataPreview,
    loadProjectRevision, selectRunProject,
  } = useWorkbench();
  const intent = activePath === "data" ? "data" : "reproduce";
  return <div className="page journey-page">
    <CommunityPathPicker activePath={intent} onSelect={chooseCommunityPath} />
    <ResearchJourney intent={intent} studies={workspace.projects} packs={workspace.data_packs} methodologyCatalogue={methodologyCatalogue}
      initialStudyId={selectedProjectId} online={online}
      targetPackId={journeyTargetPackId} onTargetPackChange={setJourneyTargetPackId}
      onPackCreated={async () => { if (!await refresh()) throw new Error(t("journey.pack.refreshFailed")); }}
      onCreated={async (studyId, notes) => {
        await refresh(); setSelectedProjectId(studyId); setSelectedRunId(""); setPreflight(null); setView("runCentre");
        setNotice(t("journey.notice.created") + (notes?.length ? ` ${notes.join(" ")}` : ""));
      }}
      onOpenData={(context) => {
        setJourneyData(context); setJourneyTargetPackId(context.targetPackId);
        setSelectedProjectId(context.sourceStudyId); setSelectedRunId(""); setDataContextId("journey");
        setSavedDataResolution(null); setDataPreview(null); setView("data");
      }}
      onOpenLearn={() => setView("learn")}
      onReviewSource={(studyId) => {
        const source = workspace.projects.find((project) => project.id === studyId);
        if (source) { loadProjectRevision(source); setView("projects"); }
      }}
      onOpenRuns={(studyId) => { selectRunProject(studyId); setView("runCentre"); }} />
  </div>;
}
