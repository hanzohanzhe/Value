"use client";

// VRE & curtailment (/runs/[runId]/vre). Moved essentially verbatim from app/page.tsx (P1 W3, spec 5.1); W4 restyles it.
// P1-polish R-10 (spec 0.3): the model year and the timeline resolution are in the URL (?year=&resolution=).
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import CurtailmentView from "../../../features/market/CurtailmentView";
import ResultQueryPanel from "../../../features/results/ResultQueryPanel";
import { readVreLocation } from "../../../features/market/vreLocation.ts";
import { replacePageQuery } from "../../../features/shell/routes.ts";
import { useWorkbench } from "../../../features/shell/Workbench";

const writeLocation = (values: Record<string, string | number | null>) => replacePageQuery(values);

export default function VreView() {
  const { selectedRun } = useWorkbench();
  const search = useSearchParams()?.toString() ?? "";
  // Read once, when the page opens; later changes are written by the page itself.
  const [linked] = useState(() => readVreLocation(search));
  return <><ResultQueryPanel key={`query-${selectedRun?.id ?? "no-run"}`} run={selectedRun} /><CurtailmentView key={`physical-${selectedRun?.id ?? "no-run"}`} run={selectedRun} linked={linked} onLocationChange={writeLocation} /></>;
}
