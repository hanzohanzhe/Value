"use client";

// The Run centre's history (P1 spec 6.5, W4c): every Run of the selected Study
// with its status, progress, start time and - for a failed Run - the error code
// and the first diagnostic line; each row opens that Run's results page.
import { statusWord } from "../shared/labels.ts";
import { useLocale, useT } from "../../i18n/LocaleProvider";
import { errorExplanation } from "../../i18n/index.ts";
import { DataTable, type DataColumn } from "../../ui/DataTable.tsx";
import { Badge } from "../shared/presentation";
import { RUN_SCOPE_LABELS } from "../workspace/runScope";
import { runErrorSummary } from "./runErrorView.ts";
import { runIdSuffix, runStartedText } from "./runHistoryView.ts";
import type { ModelRun, RunMode } from "./types";

type HistoryRow = Pick<ModelRun, "id" | "mode" | "status" | "completed_years" | "total_years" | "error" | "error_code" | "error_detail"> & { created_at?: string };

export default function RunHistoryTable({ runs, selectedRunId, onOpen }: { runs: readonly HistoryRow[]; selectedRunId: string; onOpen: (runId: string) => void }) {
  const t = useT();
  const { locale } = useLocale();
  if (!runs.length) return null;
  const columns: DataColumn<HistoryRow>[] = [
    { key: "run", header: t("runs.history.col.run"), rowHeader: true, render: (run) => <span className="run-history-label"><b>{RUN_SCOPE_LABELS[run.mode as RunMode] ?? String(run.mode).replaceAll("_", " ")}</b><code title={run.id}>{runIdSuffix(run.id)}</code></span> },
    { key: "status", header: t("runs.history.col.status"), render: (run) => <Badge tone={run.status === "completed" ? "good" : run.status === "failed" ? "warn" : "blue"} title={run.status}>{statusWord(run.status)}</Badge> },
    { key: "progress", header: t("runs.history.col.progress"), numeric: true, render: (run) => t("runs.history.years", { done: run.completed_years, total: run.total_years }) },
    { key: "started", header: t("runs.history.col.started"), render: (run) => runStartedText(run) ?? "—" },
    { key: "diagnostic", header: t("runs.history.col.diagnostic"), render: (run) => { const error = runErrorSummary(run); return error ? <span title={error.rest || undefined}>{error.code && <code title={errorExplanation(locale, error.code) ?? undefined}>{error.code}</code>} {error.headline}</span> : "—"; } },
    { key: "open", header: t("runs.history.col.results"), render: (run) => <button type="button" className="text-button" aria-label={t("runs.history.openLabel", { run: runIdSuffix(run.id) })} aria-current={run.id === selectedRunId ? "true" : undefined} onClick={() => onOpen(run.id)}>{t("runs.history.open")}</button> },
  ];
  return <DataTable className="run-history-table" caption={t("runs.history.caption")} columns={columns} rows={runs} rowKey={(run) => run.id} maxHeight="360px" />;
}
