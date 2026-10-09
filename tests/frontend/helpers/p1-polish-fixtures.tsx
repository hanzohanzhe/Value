// Test-only wrappers for the P1-polish rulings: a component rendered inside
// the interface-language provider (renderTsx bundles one entry, so the
// provider and the component share React).
import type { ComponentProps } from "react";
import { LocaleProvider } from "../../../app/i18n/LocaleProvider";
import type { Locale } from "../../../app/i18n/index.ts";
import WorkspaceRail from "../../../app/features/shell/WorkspaceRail";

export function RailIn({ locale, ...props }: ComponentProps<typeof WorkspaceRail> & { locale: Locale }) {
  return <LocaleProvider initialLocale={locale}><WorkspaceRail {...props} /></LocaleProvider>;
}
