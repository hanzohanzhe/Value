"use client";

// React side of the interface language (P1 spec 3).  The root layout reads the
// `value_locale` cookie on the server and passes it here, so the first paint is
// already in the chosen language (no flash).  Choosing a language writes the
// cookie, updates <html lang> and re-renders; nothing follows the browser
// language.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { setFormatLocale } from "../features/shared/format.ts";
import { DEFAULT_LOCALE, htmlLang, intlLocale, localeCookie, setActiveLocale, translate, type Locale, type MessageKey, type MessageValues, type Translate } from "./index.ts";

type LocaleContextValue = { locale: Locale; setLocale: (locale: Locale) => void };

const noop = () => undefined;
const LocaleContext = createContext<LocaleContextValue>({ locale: DEFAULT_LOCALE, setLocale: noop });

export function LocaleProvider({ initialLocale = DEFAULT_LOCALE, children }: { initialLocale?: Locale; children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);
  // Numbers and dates follow the interface language (format.ts). Set before the
  // children render; en-GB and zh-CN group and separate digits identically.
  setFormatLocale(intlLocale(locale));
  // Pure view code (status words, coverage pills, Run notices) reads the same language.
  setActiveLocale(locale);
  const setLocale = useCallback((next: Locale) => {
    try { document.cookie = localeCookie(next); } catch { /* cookies blocked: the choice lasts for this page only */ }
    try { document.documentElement.lang = htmlLang(next); } catch { /* no document (server) */ }
    setLocaleState(next);
  }, []);
  const value = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

/** The interface language and its setter. */
export function useLocale(): LocaleContextValue {
  return useContext(LocaleContext);
}

/** `t("nav.run.label")`, `t("header.backgroundRuns", { count })`. English outside a provider. */
export function useT(): Translate {
  const { locale } = useContext(LocaleContext);
  return useCallback((key: MessageKey, values?: MessageValues) => translate(locale, key, values), [locale]);
}
