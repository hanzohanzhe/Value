"use client";

// Network & redispatch (/runs/[runId]/network). Moved essentially verbatim from app/page.tsx (P1 W3, spec 5.1).
// W4c (R3-16): the Run's one network entry; NetworkHubNav switches to the DC network, expansion and water results.
// W6 (spec 0.3): the model year, tab and period window are in the URL (?year=&tab=&from=&window=).
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import NetworkRedispatchView from "../../../features/network/NetworkRedispatchView";
import NetworkHubNav from "../../../features/network/NetworkHubNav";
import { readNetworkLocation } from "../../../features/network/networkLocation.ts";
import { replacePageQuery, routePathname } from "../../../features/shell/routes.ts";
import { useWorkbench } from "../../../features/shell/Workbench";

const writeLocation = (values: Record<string, string | number | null>) => replacePageQuery(values);

export default function NetworkView() {
  const { setView, setReplayTarget, openView, selectedRun, selectedRunSourceMutable, createFullReplayRevision, rerunAsCopperplate } = useWorkbench();
  const runId = selectedRun?.id ?? "";
  const search = useSearchParams()?.toString() ?? "";
  // Read once, when the page opens; later changes are written by the page itself.
  const [linked] = useState(() => readNetworkLocation(search));
  return <>
    {runId && <NetworkHubNav view="networkRedispatch" hrefFor={(view) => routePathname({ view, runId })} onNavigate={openView} />}
    <NetworkRedispatchView key={selectedRun?.id ?? "no-run"} run={selectedRun} sourceStudyMutable={selectedRunSourceMutable} onReplay={(year, periodFrom) => { if (selectedRun) { setReplayTarget({ runId: selectedRun.id, year, periodFrom, nonce: Date.now() }); setView("marketReplay"); } }} onOpenInspect={() => openView("audit")} onOpenMarket={() => setView("marketReplay")} onCreateFullReplayRevision={createFullReplayRevision} onOpenRun={() => setView("run")} onRerun={() => selectedRun ? rerunAsCopperplate(selectedRun) : Promise.resolve()} linked={linked} onLocationChange={writeLocation} />
  </>;
}
