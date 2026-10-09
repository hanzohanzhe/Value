"use client";

// Inspect (/inspect?tab=&q=). Moved essentially verbatim from app/page.tsx (P1 W3, spec 5.1); W4c restyles it.
// The open tab is in the URL (?tab=): a link or a reload opens the same tab; a
// tab asked for by a Run notice (inspectTarget) still wins once.  The applied
// planning search is in the URL too (?q=, F3-19): it is requested only on Enter
// or Apply, never while typing.
import { useSearchParams } from "next/navigation";
import AuditView, { type AuditTab } from "../features/evidence/AuditView";
import { readInspectSearch } from "../features/evidence/inspectQuery.ts";
import { replacePageQuery } from "../features/shell/routes.ts";
import { useWorkbench } from "../features/shell/Workbench";

const TABS: readonly AuditTab[] = ["planning", "market", "artifacts"];
const writeTab = (tab: AuditTab) => replacePageQuery({ tab });
const writeSearch = (search: string) => replacePageQuery({ q: search || null });

export default function InspectView() {
  const { inspectTarget, selectedRun, createFullReplayRevision } = useWorkbench();
  const params = useSearchParams();
  const linked = params?.get("tab");
  const linkedTab = TABS.includes(linked as AuditTab) ? { tab: linked as AuditTab, nonce: 0 } : null;
  return <AuditView run={selectedRun} onCreateFullReplayRevision={createFullReplayRevision} initialTab={inspectTarget ?? linkedTab} onTabChange={writeTab} initialSearch={readInspectSearch(params?.toString() ?? "")} onSearchChange={writeSearch} />;
}
