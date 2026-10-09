"use client";

// The pages of one Run (spec 5.1: /runs/[runId], /replay, /vre, /network,
// /systems).  Shown above the Run context bar on those routes; the links are
// real links (a new tab opens the same page), a plain click stays in the
// workbench.
import { useT } from "../../i18n/LocaleProvider";
import { RUN_SECTION_NAV, findNavView, runSectionEntry, type View } from "../shared/navigation.ts";
import { plainClick } from "./WorkspaceRail";

export default function RunSectionNav({ view, hrefFor, onNavigate }: { view: View; hrefFor: (view: View) => string; onNavigate: (view: View) => void }) {
  const t = useT();
  // R3-16 (W4c): the optional-domain results page belongs to the network entry.
  const current = runSectionEntry(view);
  return <nav className="run-section-nav" aria-label={t("nav.runSection")}>
    {RUN_SECTION_NAV.map(findNavView).map((item) => <a key={item.id} href={hrefFor(item.id)} aria-current={current === item.id ? "page" : undefined} className={current === item.id ? "active" : ""} onClick={(event) => { if (!plainClick(event)) return; event.preventDefault(); onNavigate(item.id); }}>{item.id === "run" ? t("nav.runResults") : t(item.label)}</a>)}
  </nav>;
}
