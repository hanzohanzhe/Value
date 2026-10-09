"use client";
import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { nextTabIndex, type TabItem } from "./tabKeys.ts";
export type { TabItem } from "./tabKeys.ts";
export { nextTabIndex } from "./tabKeys.ts";
import "./Tabs.css";

/** Spec 2: tablist/tab/tabpanel linked by id; arrows switch, Home/End jump.
 * Controlled: the page keeps `value` in the URL (useSearchParamState). */
export function Tabs({ tabs, value, onChange, label, children, className, idBase }: {
  tabs: readonly TabItem[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  /** The panel of the selected tab. */
  children?: ReactNode;
  className?: string;
  idBase?: string;
}) {
  const generated = useId();
  const base = idBase ?? `v-tabs${generated.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const selected = Math.max(0, tabs.findIndex((tab) => tab.id === value));
  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next = nextTabIndex(tabs, index, event.key);
    if (next == null) return;
    event.preventDefault();
    onChange(tabs[next].id);
    buttons.current[next]?.focus();
  }
  const current = tabs[selected];
  return <div className={`v-tabs${className ? ` ${className}` : ""}`}>
    <div className="v-tabs__list" role="tablist" aria-label={label}>
      {tabs.map((tab, index) => {
        const active = index === selected;
        return <button
          key={tab.id}
          ref={(node) => { buttons.current[index] = node; }}
          type="button"
          role="tab"
          id={`${base}-tab-${tab.id}`}
          aria-selected={active}
          aria-controls={`${base}-panel-${tab.id}`}
          tabIndex={active ? 0 : -1}
          disabled={tab.disabled}
          className={`v-tabs__tab${active ? " is-active" : ""}`}
          onClick={() => onChange(tab.id)}
          onKeyDown={(event) => onKeyDown(event, index)}
        >{tab.label}</button>;
      })}
    </div>
    {current && <div className="v-tabs__panel" role="tabpanel" id={`${base}-panel-${current.id}`} aria-labelledby={`${base}-tab-${current.id}`} tabIndex={0}>{children}</div>}
  </div>;
}
