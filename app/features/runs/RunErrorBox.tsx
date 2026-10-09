"use client";

// A failed Run's error (P1 spec 6.5): the error code and the first diagnostic
// line, the rest of the recorded diagnostic behind "Full diagnostic". A known
// error code is explained first in the interface language (spec 3, W5); the
// code and the backend's message are shown as sent.
import { useLocale, useT } from "../../i18n/LocaleProvider";
import { errorExplanation } from "../../i18n/index.ts";
import { Disclosure } from "../../ui/Card.tsx";
import { runErrorSummary, type RunErrorFields } from "./runErrorView.ts";

export default function RunErrorBox({ run }: { run: RunErrorFields }) {
  const t = useT();
  const { locale } = useLocale();
  const summary = runErrorSummary(run);
  if (!summary) return null;
  // Not repeated when the backend's own message already says the same (English).
  const explained = errorExplanation(locale, summary.code);
  const explanation = explained && !summary.headline.includes(explained) ? explained : null;
  return <div className="error-box run-error-box">
    {explanation && <p className="run-error-explanation">{explanation}</p>}
    <p className="run-error-headline">{summary.code && <b>{summary.code}: </b>}{summary.headline}</p>
    {summary.rest && <Disclosure summary={t("runs.error.fullDiagnostic")} className="run-error-detail"><pre>{summary.rest}</pre></Disclosure>}
  </div>;
}
