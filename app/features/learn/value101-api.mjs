// Same-origin API path (P0-1): the UI gateway forwards /api/* to the local
// engine.  An explicit origin is accepted only for tests and tooling.
export function value101ApiUrl(path, explicitOrigin = "") {
  const origin = String(explicitOrigin || "").replace(/\/+$/, "");
  const route = String(path).replace(/^\/+/, "");
  return `${origin}/api/${route}`;
}
