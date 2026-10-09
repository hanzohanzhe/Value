// Focus trap of the navigation drawer below 900 px (P1 spec 5.2 and 7, D-W3-10;
// decided in W6). While the drawer is open its backdrop covers the page, so
// Tab must not move focus to a control under it: from the last control of the
// sidebar Tab wraps to the first (the menu button), and Shift+Tab from the
// first wraps to the last. Pure helper; WorkspaceRail applies it.

/** The controls Tab can reach inside the sidebar. */
export const DRAWER_FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "select:not([disabled])",
  "input:not([disabled]):not([type=\"hidden\"])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex=\"-1\"])",
].join(", ");

/**
 * The element Tab (backwards: Shift+Tab) must move focus to so that it stays
 * in the open drawer, or null when the browser's own next stop is already in
 * the drawer. `items` are the drawer's focusable elements in tab order;
 * `active` is the focused element when it is one of them, else null.
 */
export function drawerWrapTarget<T>(items: readonly T[], active: T | null, backwards: boolean): T | null {
  if (!items.length) return null;
  const index = active === null ? -1 : items.indexOf(active);
  if (index < 0) return backwards ? items[items.length - 1] : items[0];
  if (backwards && index === 0) return items[items.length - 1];
  if (!backwards && index === items.length - 1) return items[0];
  return null;
}
