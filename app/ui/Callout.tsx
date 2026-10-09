import type { ReactNode } from "react";
import "./Callout.css";

export type CalloutTone = "info" | "attention" | "danger" | "success";

const ICONS: Record<CalloutTone, string> = { info: "i", attention: "!", danger: "×", success: "✓" };

export type CalloutAction = { label: ReactNode; href?: string; onClick?: () => void };

/** Spec 2: info, attention, danger, success; optionally one next step.
 * danger and attention are alerts (announced once); info and success are
 * polite status regions. Colours keep the P0 meanings (amber = attention). */
export function Callout({ tone, title, children, action, className }: {
  tone: CalloutTone;
  title: ReactNode;
  children?: ReactNode;
  action?: CalloutAction;
  className?: string;
}) {
  const role = tone === "danger" || tone === "attention" ? "alert" : "status";
  return <section className={`v-callout v-callout--${tone}${className ? ` ${className}` : ""}`} role={role}>
    <span className="v-callout__icon" aria-hidden="true">{ICONS[tone]}</span>
    <div className="v-callout__content">
      <p className="v-callout__title">{title}</p>
      {children != null && <div className="v-callout__body">{children}</div>}
      {action && (action.href
        ? <a className="v-callout__action" href={action.href}>{action.label}</a>
        : <button type="button" className="v-callout__action" onClick={action.onClick}>{action.label}</button>)}
    </div>
  </section>;
}

/** Spec 2: says why a place is empty and what to do next. */
export function EmptyState({ title, children, action, className }: { title: ReactNode; children?: ReactNode; action?: CalloutAction; className?: string }) {
  return <div className={`v-empty${className ? ` ${className}` : ""}`}>
    <p className="v-empty__title">{title}</p>
    {children != null && <div className="v-empty__body">{children}</div>}
    {action && (action.href
      ? <a className="v-callout__action" href={action.href}>{action.label}</a>
      : <button type="button" className="v-callout__action" onClick={action.onClick}>{action.label}</button>)}
  </div>;
}
