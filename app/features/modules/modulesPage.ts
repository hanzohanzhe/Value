// Modules and Extensions pages (P1 W4b, spec 6.4, R3-22): the order of their
// sections and the catalogue badge. Pure; the views render what this returns.
import type { MessageKey, Translate } from "../../i18n/index.ts";

/** Spec 5.1 / 6.4: Catalog first, then Disabled & quarantined, author tools last (R3-22). */
export const MODULES_PAGE_SECTIONS = [
  { id: "modules-catalog", label: "modules.nav.catalog" },
  { id: "modules-disabled", label: "modules.nav.disabled" },
  { id: "modules-author", label: "modules.nav.author" },
] as const satisfies readonly { id: string; label: MessageKey }[];

/** The catalogue first, the installer next, the author workbench last. */
export const EXTENSIONS_PAGE_SECTIONS = [
  { id: "extensions-catalogue", label: "extensions.nav.catalogue" },
  { id: "extensions-install", label: "extensions.nav.install" },
  { id: "extensions-author", label: "extensions.nav.author" },
] as const satisfies readonly { id: string; label: MessageKey }[];

/** Spec 6.4: "{n} of {m} ready · {k} experimental" (the experimental part only when k > 0). */
export function catalogBadge(modules: readonly { status?: string }[], t: Translate): string {
  const ready = modules.filter((module) => module.status === "ready").length;
  const experimental = modules.filter((module) => module.status === "experimental").length;
  return t("modules.catalog.badge", { ready, total: modules.length, experimental });
}
