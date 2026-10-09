"use client";

import { statusWord } from "../shared/labels.ts";
import { useState } from "react";
import { frozenManifestLabel, frozenManifestNote, extensionMarkers, resolveRunContext, type ContextRun, type FrozenRunContext } from "./runContext";
import { GATE_TEXT, NOTICE_ACTION_LABELS, advisorySummaryText, type CheckField, type NoticeAction, type RunAdvisory, type RunNotice } from "./runValidation.ts";
import { Callout, StatusPill } from "../shared/Callout";
import "./run-context.css";
import "./run-context-validation.css";
import { useT } from "../../i18n/LocaleProvider";
import type { MessageKey } from "../../i18n/index.ts";

export type InspectTab = "planning" | "market" | "artifacts";

export type RunContextActions = {
  /** Open the Inspect view, optionally on one of its tabs. */
  onOpenInspect?: (tab?: InspectTab) => void;
  /** Open the view that lists this Run's stress events. */
  onShowStressEvents?: () => void;
};

function CheckValue({ field }: { field: CheckField }) {
  return <b className={`run-context-check ${field.tone}`} title={field.title}>{field.dot && <i aria-hidden="true">● </i>}{field.text}</b>;
}

function AdvisoryList({ advisories, expected }: { advisories: RunAdvisory[]; expected: number }) {
  const t = useT();
  if (!advisories.length) {
    return <p className="run-context-advisory-empty">{t(expected ? "runContext.advisoryLoading" : "runContext.noAdvisory")}</p>;
  }
  return <ul className="run-context-advisories">{advisories.map((advisory) => <li key={advisory.id}>
    <b>{advisory.title ?? advisory.id}{advisory.severity && <small className="run-context-advisory-severity"> · {advisory.severity}</small>}</b>
    {advisory.summary && <span>{advisory.summary}</span>}
    {Boolean(advisory.affected_metrics?.length) && <small>{t("runContext.affected", { metrics: advisory.affected_metrics?.map((metric) => metric.replaceAll("_", " ")).join(", ") })}</small>}
  </li>)}</ul>;
}

function NoticeCallout({ notice, advisories, actions }: { notice: RunNotice; advisories: RunAdvisory[]; actions: RunContextActions }) {
  const [advisoriesOpen, setAdvisoriesOpen] = useState(false);
  const handler = (action: NoticeAction): (() => void) | undefined => {
    switch (action) {
      case "open_residuals": return actions.onOpenInspect && (() => actions.onOpenInspect?.("market"));
      case "open_inspect": return actions.onOpenInspect && (() => actions.onOpenInspect?.());
      case "export_ledger": return actions.onOpenInspect && (() => actions.onOpenInspect?.("artifacts"));
      case "show_stress_events": return actions.onShowStressEvents;
      case "view_advisories": return () => setAdvisoriesOpen((open) => !open);
    }
  };
  const buttons = notice.actions.flatMap((action, index) => {
    const onClick = handler(action);
    if (!onClick) return [];
    const label = action === "view_advisories" ? `${NOTICE_ACTION_LABELS[action]} (${notice.advisoryCount ?? advisories.length})` : NOTICE_ACTION_LABELS[action];
    return [<button key={action} type="button" className={index === 0 ? "value-action-primary" : "value-action-link"}
      aria-expanded={action === "view_advisories" ? advisoriesOpen : undefined} onClick={onClick}>{label}</button>];
  });
  return <Callout tone={notice.tone} title={notice.title} actions={buttons.length ? buttons : undefined}>
    {notice.gates && notice.gates.length > 0 && <ul className="run-context-gates">{notice.gates.map((gate) => <li key={gate}><b>{GATE_TEXT[gate].name}</b> {GATE_TEXT[gate].sentence}</li>)}</ul>}
    <p>{notice.body}</p>
    {notice.id === "pre_fix" && advisoriesOpen && <AdvisoryList advisories={advisories} expected={notice.advisoryCount ?? 0} />}
  </Callout>;
}

export default function RunContextBar({ run, frozen, actions = {} }: {
  run?: ContextRun | null;
  frozen?: FrozenRunContext | null;
  actions?: RunContextActions;
}) {
  const t = useT();
  const context = resolveRunContext({ run, frozen });
  // The expanded list belongs to one Run: selecting another Run collapses it.
  const [moreOpenFor, setMoreOpenFor] = useState<string | null>(null);
  const moreOpen = Boolean(context.runId) && moreOpenFor === context.runId;
  const label = (value: string) => statusWord(value);
  const identityAvailable = context.kind === "ready" || context.kind === "partial";
  const [primaryNotice, ...otherNotices] = context.notices;
  // R-D11: advisories apply to more Runs than the pre-fix notice covers (e.g. a
  // doctoral Run); list them in a disclosure unless that notice already does.
  const advisorySummary = context.notices.some((notice) => notice.id === "pre_fix") ? null : advisorySummaryText(run);
  return <section className={`run-context-bar run-context-${context.kind}`} aria-label={t("runContext.label")} aria-busy={context.kind === "loading"}>
    <div className="run-context-heading">
      <div><span className="run-context-eyebrow">{t("runContext.eyebrow")}</span>
        <strong>{context.studyName ?? context.studyId ?? t("runContext.noRun")}</strong>
        {context.runId && <code>{context.runId}</code>}
        {context.runId && <span className="run-context-profile value-new-control"><StatusPill tone={context.profile.tone} title={context.profile.title}>{context.profile.text}</StatusPill>{extensionMarkers(run).map((marker) => <StatusPill key={marker.key} tone={marker.tone} title={marker.title}>{marker.text}</StatusPill>)}</span>}
      </div>
      {context.runId && <div className="run-context-statuses">
        <span><small>{t("runContext.execution")}</small><b title={context.executionStatus}>{label(context.executionStatus)}</b></span>
        <span><small>{t("runContext.contract")}</small>{context.contractField ? <CheckValue field={context.contractField} /> : <b title={context.contractStatus}>{label(context.contractStatus)}</b>}</span>
        <span><small>{t("runContext.scientific")}</small>{context.scientificField ? <CheckValue field={context.scientificField} /> : <b title={context.scientificStatus}>{label(context.scientificStatus)}</b>}</span>
        <span className="run-context-validation-field"><small>{t("runContext.energyBalance")}</small><CheckValue field={context.energyBalance} /></span>
        {context.rawInvariants && <span className="run-context-validation-field"><small>{t("runContext.rawInvariants")}</small><CheckValue field={context.rawInvariants} /></span>}
        <span className="run-context-validation-field"><small>{t("runContext.stress")}</small><CheckValue field={context.stress} /></span>
      </div>}
    </div>
    {context.runId && primaryNotice && <div className="run-context-notices value-new-control">
      <NoticeCallout key={`${context.runId}:${primaryNotice.id}`} notice={primaryNotice} advisories={context.advisories} actions={actions} />
      {otherNotices.length > 0 && <>
        <button type="button" className="run-context-more" aria-expanded={moreOpen} onClick={() => setMoreOpenFor(moreOpen ? null : context.runId ?? null)}>
          {moreOpen ? t("runContext.hideNotices") : t("runContext.moreNotices", { count: otherNotices.length })}
        </button>
        {moreOpen && otherNotices.map((notice) => <NoticeCallout key={`${context.runId}:${notice.id}`} notice={notice} advisories={context.advisories} actions={actions} />)}
      </>}
    </div>}
    {context.runId && advisorySummary && <details className="run-context-advisory-details value-new-control"><summary>{advisorySummary}</summary><AdvisoryList advisories={context.advisories} expected={1} /></details>}
    {context.issue && <p className="run-context-notice" role="status">{context.issue}</p>}
    {context.runId && <p className="run-context-scope"><b>{t("runContext.scope")}</b> {context.scope.label}
      {context.scope.configuredPeriods !== undefined && t("runContext.periodsConfigured", { count: context.scope.configuredPeriods.toLocaleString("en-GB") })}
      {context.scope.years && <> · {context.scope.years.join(", ")}</>}
      <small>{t("runContext.scopeNote")}</small>
    </p>}
    {identityAvailable && <>
      <div className="run-context-sources">
        <span><small>{t("runContext.revision")}</small><b>{context.revisionNumber === undefined ? t("runContext.notRecorded") : context.revisionNumber}</b></span>
        <span><small>{t("runContext.dataPack")}</small><code>{context.dataPackId ?? t("runContext.notRecorded")}</code></span>
        <span><small>{t("runContext.network")}</small><code>{context.networkPackId ?? t("runContext.notRecorded")}</code></span>
      </div>
      <details className="run-context-details"><summary>{t("runContext.details")}</summary>
        <dl>{([
          ["runContext.studyId", context.studyId],
          ["runContext.revisionSha", context.revisionSha],
          [null, context.dataPackSha],
          ["runContext.networkSha", context.networkPackSha],
          ["runContext.snapshot", context.snapshotId],
          ["runContext.inputTree", context.inputTreeSha],
          ["runContext.profile", context.methodologyProfileId],
          ["runContext.catalogue", context.profileCatalogueSha],
        ] as [MessageKey | null, string | undefined][]).map(([name, value]) => <div key={name ?? "manifest"}><dt>{name ? t(name) : frozenManifestLabel()}</dt><dd><code>{value ?? t("runContext.notRecorded")}</code></dd></div>)}</dl>
        <p>{t("runContext.identityNote")} {frozenManifestNote()}</p>
      </details>
    </>}
    {context.sourceStudyStatus === "trash" && <p className="run-context-notice">{t("runContext.trash")}</p>}
    {context.sourceStudyStatus === "missing" && <p className="run-context-notice">{t("runContext.missing")}</p>}
  </section>;
}
