import type { ReactNode } from "react";
import { valueStateText, valueStateTone, type ValueStateKey } from "./valueStates.ts";
import "./callout.css";

export type CalloutTone = "danger" | "caution" | "ok" | "info";
export type PillTone = CalloutTone | "muted";

const ICONS: Record<CalloutTone, string> = { danger: "!", caution: "!", ok: "✓", info: "i" };

/** Spec 1.3: one notice with a 4px tone bar, a title, one or two sentences and the next step. */
export function Callout({ tone, title, children, actions, className }: {
  tone: CalloutTone;
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  // danger/caution are announced once when they appear; ok/info are polite status.
  const role = tone === "danger" || tone === "caution" ? "alert" : "status";
  return <section className={`value-callout ${tone}${className ? ` ${className}` : ""}`} role={role}>
    <span className="value-callout-icon" aria-hidden="true">{ICONS[tone]}</span>
    <h4 className="value-callout-title">{title}</h4>
    {children != null && <div className="value-callout-body">{children}</div>}
    {actions != null && <div className="value-callout-actions">{actions}</div>}
  </section>;
}

/** Spec 1.3: badge for statuses and table cells; lives next to the older `.badge`. */
export function StatusPill({ tone, children, title }: { tone: PillTone; children: ReactNode; title?: string }) {
  return <span className={`value-pill ${tone}`} title={title}>{children}</span>;
}

const STATE_CLASS = { muted: "", amber: " amber", red: " red", blue: " blue" } as const;

/** A state word from valueStates.ts in place of a number; `title` says why. */
export function ValueState({ state, title, coveragePercent }: { state: ValueStateKey; title?: string; coveragePercent?: number | null }) {
  return <span className={`value-state${STATE_CLASS[valueStateTone(state)]}`} title={title}>{valueStateText(state, coveragePercent)}</span>;
}

/** The recorded value when there is one, otherwise the state word. */
export function ValueOr({ value, state = "missing", title }: { value: string | null | undefined; state?: ValueStateKey; title?: string }) {
  return value == null ? <ValueState state={state} title={title} /> : <>{value}</>;
}
