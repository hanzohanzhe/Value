"use client";
import { useCallback, useEffect, useState } from "react";

/** Read one query parameter, falling back when absent or not allowed. */
export function readSearchParam(search: string, name: string, fallback: string, allowed?: readonly string[]): string {
  const value = new URLSearchParams(search).get(name);
  if (value == null || value === "") return fallback;
  return allowed && !allowed.includes(value) ? fallback : value;
}

/** The query string with `name` set (or removed when equal to the fallback). */
export function writeSearchParam(search: string, name: string, value: string, fallback: string): string {
  const params = new URLSearchParams(search);
  if (value === fallback) params.delete(name);
  else params.set(name, value);
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** Spec 0.3: state that lives in the URL (current tab, year, period). Uses
 * history.replaceState so Back is not flooded; follows Back/Forward. W3's
 * router may replace this with its own search-param hook. */
export function useSearchParamState(name: string, fallback: string, allowed?: readonly string[]): [string, (value: string) => void] {
  const [value, setValue] = useState(fallback);
  const allowedKey = allowed?.join("\u0000");
  useEffect(() => {
    const list = allowedKey ? allowedKey.split("\u0000") : undefined;
    const sync = () => setValue(readSearchParam(window.location.search, name, fallback, list));
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [name, fallback, allowedKey]);
  const update = useCallback((next: string) => {
    setValue(next);
    const search = writeSearchParam(window.location.search, name, next, fallback);
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${search}${window.location.hash}`);
  }, [name, fallback]);
  return [value, update];
}
