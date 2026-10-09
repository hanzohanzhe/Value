// Test-only wrappers for the Data, Modules and Extensions pages (P1 W4b): a
// component rendered inside the interface-language provider, so render tests
// can assert the English default and the Chinese dictionary entries.
import { LocaleProvider } from "../../../app/i18n/LocaleProvider";
import type { Locale } from "../../../app/i18n/index.ts";
import JourneyDataEditor from "../../../app/features/workspace/JourneyDataEditor";
import ModuleQuarantinePanel from "../../../app/features/modules/ModuleQuarantinePanel";
import DisabledEntriesPanel from "../../../app/features/modules/DisabledEntriesPanel";
import DataPackValidationPanel from "../../../app/features/data/DataPackValidationPanel";
import DataPreviewPanel from "../../../app/features/data/DataPreviewPanel";
import AdapterGuide from "../../../app/features/data/AdapterGuide";
import { InstalledPacks } from "../../../app/features/data-workbench/InstalledPacks";
import SectionNav from "../../../app/features/shared/SectionNav";

type Localized<P> = P & { locale: Locale };

export function JourneyDataEditorIn({ locale, ...props }: Localized<Parameters<typeof JourneyDataEditor>[0]>) {
  return <LocaleProvider initialLocale={locale}><JourneyDataEditor {...props} /></LocaleProvider>;
}
export function ModuleQuarantinePanelIn({ locale, ...props }: Localized<Parameters<typeof ModuleQuarantinePanel>[0]>) {
  return <LocaleProvider initialLocale={locale}><ModuleQuarantinePanel {...props} /></LocaleProvider>;
}
export function DisabledEntriesPanelIn({ locale, ...props }: Localized<Parameters<typeof DisabledEntriesPanel>[0]>) {
  return <LocaleProvider initialLocale={locale}><DisabledEntriesPanel {...props} /></LocaleProvider>;
}
export function DataPackValidationPanelIn({ locale, ...props }: Localized<Parameters<typeof DataPackValidationPanel>[0]>) {
  return <LocaleProvider initialLocale={locale}><DataPackValidationPanel {...props} /></LocaleProvider>;
}
export function DataPreviewPanelIn({ locale, ...props }: Localized<Parameters<typeof DataPreviewPanel>[0]>) {
  return <LocaleProvider initialLocale={locale}><DataPreviewPanel {...props} /></LocaleProvider>;
}
export function AdapterGuideIn({ locale }: { locale: Locale }) {
  return <LocaleProvider initialLocale={locale}><AdapterGuide /></LocaleProvider>;
}
export function InstalledPacksIn({ locale, ...props }: Localized<Parameters<typeof InstalledPacks>[0]>) {
  return <LocaleProvider initialLocale={locale}><InstalledPacks {...props} /></LocaleProvider>;
}
export function SectionNavIn({ locale, ...props }: Localized<Parameters<typeof SectionNav>[0]>) {
  return <LocaleProvider initialLocale={locale}><SectionNav {...props} /></LocaleProvider>;
}
