"use client";
import type { ReactNode } from "react";
import "./Card.css";

type Sections = {
  title?: ReactNode;
  /** Small line above the title (kicker), e.g. the object type. */
  eyebrow?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
  className?: string;
};

function Head({ title, eyebrow, actions, level = 2 }: Pick<Sections, "title" | "eyebrow" | "actions"> & { level?: 2 | 3 | 4 }) {
  if (title == null && eyebrow == null && actions == null) return null;
  const Heading = `h${level}` as "h2" | "h3" | "h4";
  return <>
    <div className="v-card__titles">
      {eyebrow != null && <span className="v-card__eyebrow">{eyebrow}</span>}
      {title != null && <Heading className="v-card__title">{title}</Heading>}
    </div>
    {actions != null && <div className="v-card__actions">{actions}</div>}
  </>;
}

/** Spec 2: header, body and footer areas. */
export function Card({ title, eyebrow, actions, footer, children, className, headingLevel = 2, as = "section", label }: Sections & { headingLevel?: 2 | 3 | 4; as?: "section" | "article" | "div"; label?: string }) {
  const Tag = as;
  const hasHead = title != null || eyebrow != null || actions != null;
  return <Tag className={`v-card${className ? ` ${className}` : ""}`} aria-label={label}>
    {hasHead && <header className="v-card__head"><Head title={title} eyebrow={eyebrow} actions={actions} level={headingLevel} /></header>}
    {children != null && <div className="v-card__body">{children}</div>}
    {footer != null && <footer className="v-card__foot">{footer}</footer>}
  </Tag>;
}

/** Spec 2: a Card that can collapse (native details/summary, keyboard and
 * screen-reader support built in). Not collapsible = a plain Card. */
export function Panel({ title, eyebrow, actions, footer, children, className, collapsible = false, defaultOpen = true, onToggle }: Sections & { collapsible?: boolean; defaultOpen?: boolean; onToggle?: (open: boolean) => void }) {
  if (!collapsible) return <Card title={title} eyebrow={eyebrow} actions={actions} footer={footer} className={`v-panel${className ? ` ${className}` : ""}`}>{children}</Card>;
  return <details className={`v-card v-panel v-panel--collapsible${className ? ` ${className}` : ""}`} open={defaultOpen} onToggle={(event) => onToggle?.(event.currentTarget.open)}>
    <summary className="v-card__head">
      <span className="v-panel__chevron" aria-hidden="true" />
      <span className="v-card__titles">
        {eyebrow != null && <span className="v-card__eyebrow">{eyebrow}</span>}
        <span className="v-card__title">{title}</span>
      </span>
    </summary>
    {actions != null && <div className="v-card__actions v-panel__actions">{actions}</div>}
    {children != null && <div className="v-card__body">{children}</div>}
    {footer != null && <footer className="v-card__foot">{footer}</footer>}
  </details>;
}

/** Spec 2: native details/summary with the shared look. */
export function Disclosure({ summary, children, defaultOpen = false, className, onToggle }: { summary: ReactNode; children: ReactNode; defaultOpen?: boolean; className?: string; onToggle?: (open: boolean) => void }) {
  return <details className={`v-disclosure${className ? ` ${className}` : ""}`} open={defaultOpen} onToggle={(event) => onToggle?.(event.currentTarget.open)}>
    <summary><span className="v-panel__chevron" aria-hidden="true" />{summary}</summary>
    <div className="v-disclosure__body">{children}</div>
  </details>;
}
