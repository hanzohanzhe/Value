const DEFAULT_API_ORIGIN = "http://127.0.0.1:8766";

export function value101ApiUrl(path, explicitOrigin) {
  const origin = (
    explicitOrigin
    || process.env.NEXT_PUBLIC_VALUE_API_ORIGIN
    || DEFAULT_API_ORIGIN
  ).replace(/\/+$/, "");
  const route = String(path).replace(/^\/+/, "");
  return `${origin}/api/${route}`;
}
