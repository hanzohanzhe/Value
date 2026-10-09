// Same-origin API path (P0-1): the UI gateway forwards /api/* to the local
// engine.  An explicit origin is accepted only for tests and tooling.
export function value101ApiUrl(path, explicitOrigin = "") {
  const origin = String(explicitOrigin || "").replace(/\/+$/, "");
  const route = String(path).replace(/^\/+/, "");
  return `${origin}/api/${route}`;
}

// F4-07: the network-pair endpoint of a baseline Study; the ID is one encoded path segment.
export function value101NetworkPairPath(baselineStudyId) {
  return `tutorials/value-101/studies/${encodeURIComponent(String(baselineStudyId))}/network-pair`;
}
