"use client";

// Market replay (/runs/[runId]/replay). Moved essentially verbatim from app/page.tsx (P1 W3, spec 5.1); W4 restyles it.
import MarketReplayView from "../../../features/market/MarketReplayView";
import { useWorkbench } from "../../../features/shell/Workbench";

export default function ReplayView() {
  const { replayTarget, stressEventsFocus, setStressEventsFocus, selectedRun, createFullReplayRevision } = useWorkbench();
  return <MarketReplayView key={`${selectedRun?.id ?? "no-run"}:${replayTarget?.nonce ?? 0}`} run={selectedRun} onCreateFullReplayRevision={createFullReplayRevision} initialWindow={replayTarget} focusStressEvents={stressEventsFocus > 0} onStressEventsFocused={() => setStressEventsFocus(0)} />;
}
