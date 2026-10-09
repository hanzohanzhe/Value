"use client";

// The language switch in the sidebar footer (P1 spec 3, 5.2): two buttons,
// the current one pressed.  Language names are written in their own language.
import { LOCALES } from "./index.ts";
import { useLocale, useT } from "./LocaleProvider";

export function LocaleSwitch() {
  const { locale, setLocale } = useLocale();
  const t = useT();
  return <div className="locale-switch" role="group" aria-label={t("locale.label")}>
    {LOCALES.map((option) => <button type="button" key={option} lang={option === "zh" ? "zh-Hans" : "en-GB"} aria-pressed={locale === option} className={locale === option ? "active" : ""} onClick={() => setLocale(option)}>
      {t(option === "zh" ? "locale.zh" : "locale.en")}
    </button>)}
  </div>;
}
