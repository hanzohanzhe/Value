"use client";
import { useEffect, useRef, type ReactNode } from "react";
import "./PageHeader.css";

/** Spec 2 / 0.1: a one-line page header - title, one sentence, actions on the
 * right. When `focusKey` changes (a route change), focus moves to the h1 so a
 * screen reader announces the new page; the first render leaves focus alone.
 * R-11 (P1-polish, ruling on D-W4c-5): inside the workbench shell the top
 * bar holds the only h1, so the page header is an h2 by default. */
export function PageHeader({ title, description, actions, focusKey, className, headingLevel = 2 }: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  focusKey?: string;
  className?: string;
  /** 1 only outside the workbench shell; inside it the top bar holds the page's h1
   * (P1 W3); the page header then names the page's content (P1 W4b). */
  headingLevel?: 1 | 2;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const Heading = headingLevel === 2 ? "h2" : "h1";
  const previous = useRef(focusKey);
  useEffect(() => {
    if (previous.current !== focusKey) heading.current?.focus();
    previous.current = focusKey;
  }, [focusKey]);
  return <header className={`v-page-header${className ? ` ${className}` : ""}`}>
    <div className="v-page-header__text">
      <Heading ref={heading} tabIndex={-1}>{title}</Heading>
      {description != null && <p>{description}</p>}
    </div>
    {actions != null && <div className="v-page-header__actions">{actions}</div>}
  </header>;
}
