// Test-only wrappers for the W4a pages (P1 spec 6.1, 6.2): a component rendered
// inside the interface-language provider (renderTsx bundles one entry, so the
// provider and the component share React).
import type { ComponentProps } from "react";
import { LocaleProvider } from "../../../app/i18n/LocaleProvider";
import type { Locale } from "../../../app/i18n/index.ts";
import StudyComposer from "../../../app/features/studies/StudyComposer";
import AdvancedSettings from "../../../app/features/studies/AdvancedSettings";
import ResearchJourney from "../../../app/features/workspace/ResearchJourney";
import Value101NetworkExercise from "../../../app/features/learn/Value101NetworkExercise";
import { CommunityHome } from "../../../app/features/workspace/CommunityPaths";

export function ComposerIn({ locale, ...props }: ComponentProps<typeof StudyComposer> & { locale: Locale }) {
  return <LocaleProvider initialLocale={locale}><StudyComposer {...props} /></LocaleProvider>;
}

export function AdvancedIn({ locale, ...props }: ComponentProps<typeof AdvancedSettings> & { locale: Locale }) {
  return <LocaleProvider initialLocale={locale}><AdvancedSettings {...props} /></LocaleProvider>;
}

export function JourneyIn({ locale, ...props }: ComponentProps<typeof ResearchJourney> & { locale: Locale }) {
  return <LocaleProvider initialLocale={locale}><ResearchJourney {...props} /></LocaleProvider>;
}

export function NetworkIn({ locale, ...props }: ComponentProps<typeof Value101NetworkExercise> & { locale: Locale }) {
  return <LocaleProvider initialLocale={locale}><Value101NetworkExercise {...props} /></LocaleProvider>;
}

export function PathsIn({ locale, ...props }: ComponentProps<typeof CommunityHome> & { locale: Locale }) {
  return <LocaleProvider initialLocale={locale}><CommunityHome {...props} /></LocaleProvider>;
}
