import type { InstalledBundle } from "./types";

export function InstalledPacks({ bundles }: { bundles: InstalledBundle[] }) {
  return <div className="data-workbench-grid">{bundles.length ? bundles.map((bundle) => <article key={bundle.pack_id}>
    <span>Installed</span><h4>{bundle.name ?? bundle.pack_id}</h4><code>{bundle.pack_id}</code>
    <p>{bundle.validation.passed}/{bundle.validation.total} interfaces passed</p>
    <small>{bundle.installation_boundary.replaceAll("_", " ")}</small>
  </article>) : <div className="data-workbench-empty"><b>No promoted Workbench bundle</b><p>Existing Study data packs remain available above. A Workbench candidate appears here only after validation and named owner approval.</p></div>}</div>;
}
