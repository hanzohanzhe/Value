"use client";

// R-6 (P1-polish): below 900 px (the drawer layout of spec 5.2) the top bar
// keeps only the page title and the Read me icon; the Study context folds into
// one disclosure.  The server and the first client render assume the wide
// layout; the narrow one follows right after hydration.
import { useSyncExternalStore } from "react";

export const NARROW_QUERY = "(max-width: 899px)";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const query = window.matchMedia(NARROW_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

const snapshot = () => typeof window !== "undefined" && Boolean(window.matchMedia?.(NARROW_QUERY).matches);

export function useNarrowViewport(): boolean {
  return useSyncExternalStore(subscribe, snapshot, () => false);
}
