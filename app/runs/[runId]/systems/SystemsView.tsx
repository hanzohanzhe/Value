"use client";

// Optional-domain results (/runs/[runId]/systems). Moved essentially verbatim from app/page.tsx (P1 W3, spec 5.1).
// W4c (R3-16): reached from the Run's network entry; NetworkHubNav switches back to the zonal redispatch results.
// P1-polish R-10 (spec 0.3): the result domain and the model year are in the URL (?tab=&year=).
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import SystemResultsView from "../../../features/network/SystemResultsView";
import NetworkHubNav from "../../../features/network/NetworkHubNav";
import { readSystemsLocation } from "../../../features/network/systemsLocation.ts";
import { replacePageQuery, routePathname } from "../../../features/shell/routes.ts";
import { useWorkbench } from "../../../features/shell/Workbench";

const writeLocation = (values: Record<string, string | number | null>) => replacePageQuery(values);

export default function SystemsView() {
  const { setView, openView, selectedRun } = useWorkbench();
  const runId = selectedRun?.id ?? "";
  const search = useSearchParams()?.toString() ?? "";
  // Read once, when the page opens; later changes are written by the page itself.
  const [linked] = useState(() => readSystemsLocation(search));
  return <>
    {runId && <NetworkHubNav view="systems" hrefFor={(view) => routePathname({ view, runId })} onNavigate={openView} />}
    <SystemResultsView run={selectedRun} onOpenMarket={() => setView("marketReplay")} onOpenNetwork={() => setView("networkRedispatch")} linked={linked} onLocationChange={writeLocation} />
  </>;
}
