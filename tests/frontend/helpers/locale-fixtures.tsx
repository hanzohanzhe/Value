// Test-only wrappers: render a component inside the interface-language provider
// (renderTsx bundles one entry, so the provider and the component share React).
import { LocaleProvider } from "../../../app/i18n/LocaleProvider";
import type { Locale } from "../../../app/i18n/index.ts";
import WorkspaceRail from "../../../app/features/shell/WorkspaceRail";
import ContractMismatch from "../../../app/features/shell/ContractMismatch";
import { Dialog } from "../../../app/ui/Dialog";

type RailProps = Parameters<typeof WorkspaceRail>[0];

export function RailIn({ locale, ...props }: RailProps & { locale: Locale }) {
  return <LocaleProvider initialLocale={locale}><WorkspaceRail {...props} /></LocaleProvider>;
}

export function ContractMismatchIn({ locale, serviceContract }: { locale: Locale; serviceContract: unknown }) {
  return <LocaleProvider initialLocale={locale}><ContractMismatch serviceContract={serviceContract} /></LocaleProvider>;
}

export function DialogIn({ locale }: { locale: Locale }) {
  return <LocaleProvider initialLocale={locale}><Dialog open onClose={() => undefined} title="T">body</Dialog></LocaleProvider>;
}
