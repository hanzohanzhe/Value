"use client";

// R3-16 (spec 5.1, W4c): one network entry per Run. The Run section bar has a
// single "Network & redispatch" entry; on its page this bar switches between
// the zonal redispatch results (/runs/[runId]/network) and the DC network,
// transmission expansion and water results (/runs/[runId]/systems). The links
// are real links (a new tab opens the same page); a plain click stays in the
// workbench.
import { useT } from "../../i18n/LocaleProvider";
import { plainClick } from "../shell/WorkspaceRail";
import "./network-coverage.css";

export type NetworkHubView = "networkRedispatch" | "systems";

export default function NetworkHubNav({ view, hrefFor, onNavigate }: { view: NetworkHubView; hrefFor: (view: NetworkHubView) => string; onNavigate: (view: NetworkHubView) => void }) {
  const t = useT();
  const items: { id: NetworkHubView; label: string }[] = [
    { id: "networkRedispatch", label: t("network.hub.zonal") },
    { id: "systems", label: t("network.hub.domains") },
  ];
  return <nav className="network-hub-nav" aria-label={t("network.hub.label")}>
    {items.map((item) => <a key={item.id} href={hrefFor(item.id)} aria-current={view === item.id ? "page" : undefined} onClick={(event) => { if (!plainClick(event)) return; event.preventDefault(); onNavigate(item.id); }}>{item.label}</a>)}
  </nav>;
}
