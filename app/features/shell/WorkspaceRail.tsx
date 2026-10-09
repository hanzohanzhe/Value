"use client";

// The workspace sidebar (P1 spec 3, 5.2): three groups of page links, service
// status with Retry, the language switch and the version.  240 px wide; an
// icon rail below 1200 px; below 900 px a drawer opened from its menu button
// (R-6, P1-polish: the service status then sits at the drawer's foot and a
// reduced or lost service marks the menu button).  Every visible string comes from the dictionaries (strict in
// the hard-coded-string scan).
import { useEffect, useId, useRef, useState, type MouseEvent } from "react";
import { LocaleSwitch } from "../../i18n/LocaleSwitch";
import { useT } from "../../i18n/LocaleProvider";
import { OFFLINE_AFTER_FAILURES, pollDelay, type ServiceState } from "../../lib/poll.ts";
import type { HealthPayload } from "../../lib/workspaceStore.ts";
import { NAV_GROUPS, findNavView, railView, type View } from "../shared/navigation.ts";
import { viewHref } from "./routes.ts";
import { DRAWER_FOCUSABLE, drawerWrapTarget } from "./drawerFocus.ts";
import "./shell.css";

export type RailService = {
  state: ServiceState;
  failures: number;
  health: HealthPayload | null;
  runtime: { python: string; compatible: boolean; selected_capability?: string };
  architectureVersion: string;
};

function serviceClass(service: RailService): string {
  if (service.state === "online" && service.runtime.compatible) return "online";
  if (service.state === "degraded" || service.state === "offline") return service.state;
  return "";
}

export function ServiceStatus({ service, onRetry }: { service: RailService; onRetry: () => void }) {
  const t = useT();
  const { state, failures, health, runtime } = service;
  const title = state === "loading" ? t("service.loading.title")
    : state === "online" ? t("service.online.title", { version: runtime.python })
      : state === "degraded" ? t("service.degraded.title") : t("service.offline.title");
  const detail = state === "loading" ? t("service.loading.detail")
    : state === "online" ? (runtime.compatible ? t("service.online.ready", { capability: runtime.selected_capability ?? "value-native" }) : t("service.online.runtimeUnavailable"))
      : state === "degraded" ? (failures
        ? t("service.degraded.failed", { count: failures, seconds: Math.round(pollDelay(failures) / 1000) })
        : t("service.degraded.reduced", { reasons: (health?.degraded_reasons ?? []).map((reason) => reason.code).join(", ") || t("service.degraded.seeModules") }))
        : t("service.offline.detail", { attempts: OFFLINE_AFTER_FAILURES });
  const canRetry = state === "offline" || (state === "degraded" && failures > 0);
  return <div className={`service ${serviceClass(service)}`} role="status" title={`${title} · ${detail}`}><i /><span><b>{title}</b><small>{detail}</small></span>{canRetry && <button type="button" onClick={onRetry}>{t("service.retry")}</button>}</div>;
}

/** A plain click opens the page in the workbench (keeping the draft and the
 * selection); a modified click (new tab or window) follows the link. */
export function plainClick(event: MouseEvent<HTMLAnchorElement>): boolean {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

export default function WorkspaceRail({ view, onNavigate, service, onRetry }: {
  view: View;
  onNavigate: (view: View) => void;
  service: RailService;
  onRetry: () => void;
}) {
  const t = useT();
  const version = service.health?.version;
  const current = railView(view);
  // R-6 (P1-polish): below 900 px the service status is only in the drawer; a
  // reduced or lost service marks the menu button (dot and accessible name).
  const alert = (service.state === "degraded" ? t("service.degraded.title") : service.state === "offline" ? t("service.offline.title") : "").replace(/^●\s*/u, "");
  const [open, setOpen] = useState(false);
  const drawerId = useId();
  const toggle = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const rail = useRef<HTMLElement>(null);
  const wasOpen = useRef(false);
  // The drawer (< 900 px): Esc closes it; opening moves focus into it, closing returns it to the menu button.
  // W6 (spec 7, D-W3-10): while it is open, Tab and Shift+Tab stay in the sidebar; the backdrop covers the page.
  useEffect(() => {
    if (open) panel.current?.querySelector<HTMLElement>("nav a")?.focus();
    else if (wasOpen.current) toggle.current?.focus();
    wasOpen.current = open;
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); return; }
      const root = rail.current;
      if (event.key !== "Tab" || !root) return;
      const items = [...root.querySelectorAll<HTMLElement>(DRAWER_FOCUSABLE)].filter((item) => item.getClientRects().length > 0);
      const focused = document.activeElement instanceof HTMLElement && items.includes(document.activeElement) ? document.activeElement : null;
      const target = drawerWrapTarget(items, focused, event.shiftKey);
      if (target) { event.preventDefault(); target.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  // R-11 (P1-polish): the whole sidebar (brand, navigation, status, language, version) is one labelled landmark.
  return <aside ref={rail} className={`rail${open ? " rail-open" : ""}`} aria-label={t("shell.sidebar")}>
    <div className="rail-head"><div className="logo"><span>{t("shell.brand.mark")}</span><div><b>{t("shell.brand.name")}</b><small>{t("shell.brand.tagline")}</small></div></div>
      <button ref={toggle} type="button" className="rail-toggle" aria-expanded={open} aria-controls={drawerId} aria-label={alert ? `${t(open ? "nav.closeMenu" : "nav.openMenu")} · ${alert}` : t(open ? "nav.closeMenu" : "nav.openMenu")} onClick={() => setOpen(!open)}><i aria-hidden="true" />{alert && <b className={`rail-toggle-alert ${service.state}`} aria-hidden="true" />}</button></div>
    {open && <div className="rail-backdrop" onClick={() => setOpen(false)} />}
    <div className="rail-panel" id={drawerId} ref={panel}>
      <nav aria-label={t("nav.label")}>{NAV_GROUPS.map((group) => <div className="workspace-nav-group" key={group.label}><p>{t(group.label)}</p>{group.ids.map(findNavView).map((item) => <a href={viewHref(item.id)} aria-label={t("nav.item", { label: t(item.label), note: t(item.note) })} title={t(item.label)} aria-current={current === item.id ? "page" : undefined} key={item.id} className={current === item.id ? "active" : ""} onClick={(event) => { if (!plainClick(event)) return; event.preventDefault(); setOpen(false); onNavigate(item.id); }}><i>{item.index}</i><span><b>{t(item.label)}</b><small>{t(item.note)}</small></span></a>)}</div>)}</nav>
      <div className="rail-foot"><ServiceStatus service={service} onRetry={onRetry} /><LocaleSwitch /><small className="rail-version">{t("shell.contract", { version: service.architectureVersion.replace("value.contracts/", "") })}{version ? <> · {t("shell.version", { version })}</> : null}</small></div>
    </div>
  </aside>;
}
