import type { ReactNode } from "react";

export type TabItem = { id: string; label: ReactNode; disabled?: boolean };

/** Index of the tab a key press moves to (WAI-ARIA Tabs: arrows wrap, Home/End
 * jump to the ends, disabled tabs are skipped); null when the key is not ours. */
export function nextTabIndex(tabs: readonly TabItem[], current: number, key: string): number | null {
  const enabled = tabs.map((tab, index) => (tab.disabled ? -1 : index)).filter((index) => index >= 0);
  if (!enabled.length) return null;
  const position = Math.max(0, enabled.indexOf(current));
  if (key === "ArrowRight") return enabled[(position + 1) % enabled.length];
  if (key === "ArrowLeft") return enabled[(position - 1 + enabled.length) % enabled.length];
  if (key === "Home") return enabled[0];
  if (key === "End") return enabled[enabled.length - 1];
  return null;
}
