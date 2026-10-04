type Props = {
  pinnedCount: number;
  sourceCount: number;
  allPinned: boolean;
  busy: boolean;
  start: (operation: "compile", input: Record<string, unknown>) => Promise<void>;
};

export function BuildBenchmark({ pinnedCount, sourceCount, allPinned, busy, start }: Props) {
  return <div className="build-benchmark"><div><span>Frozen recipe</span><h4>GB DSO-zone candidate</h4><p>Combines pinned DSO boundaries, ETYS capability and geometry, measured demand evidence and interconnector landings. It creates an experimental candidate, never an installed pack.</p></div><dl><div><dt>Official sources pinned</dt><dd>{pinnedCount} / {sourceCount}</dd></div><div><dt>Scientific identity</dt><dd>Unsigned until owner review</dd></div><div><dt>Network claim</dt><dd>Zonal transport simulation, not security analysis</dd></div></dl><button className="primary" disabled={!allPinned || busy} onClick={() => void start("compile", { schema_version: "value.data-compile-request/v1", recipe_id: "prompt98-gb-zonal", inventory_key: "official-uk-network-v1.json", candidate_name: "gb-zonal-official-candidate" })}>Build experimental candidate</button>{!allPinned && <small>Pin each required revision and complete its rights review before building. Missing evidence stays visible and blocks this action.</small>}</div>;
}
