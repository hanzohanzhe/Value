"use client";

// Compare (/compare?runs=a,b&ref=a, spec 5.1 and 6.6; W4c).  The ticked Runs
// and the reference Run are in the URL: a link or a reload opens the same
// comparison; every delta is measured against the reference Run (EM-低1).
import { useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useT } from "../i18n/LocaleProvider";
import ComparisonWorkspace from "../features/results/ComparisonWorkspace";
import { compareQueryValues, readCompareQuery } from "../features/results/compareSelection.ts";
import { replacePageQuery } from "../features/shell/routes.ts";
import { useWorkbench } from "../features/shell/Workbench";

export default function CompareView() {
  const t = useT();
  const { workspace } = useWorkbench();
  const params = useSearchParams();
  const query = params?.toString() ?? "";
  // The URL is read once, when the page opens; afterwards the page writes it.
  const [initial] = useState(() => readCompareQuery(query));
  const onSelectionChange = useCallback((runs: string[], reference: string) => replacePageQuery(compareQueryValues(runs, reference)), []);
  return <div className="page compare-page">
    <ComparisonWorkspace title={t("compare.page.title")} description={t("compare.page.description")} runs={workspace.runs} studies={workspace.projects} initialRuns={initial.runs} initialReference={initial.ref} onSelectionChange={onSelectionChange} />
  </div>;
}
