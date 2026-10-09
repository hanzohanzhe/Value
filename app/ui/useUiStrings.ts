"use client";
// The shared components' default wording in the interface language (P1 spec 3,
// D-W1-8): the dictionaries' "ui.*" keys, which mirror UI_STRINGS (tested).
// Only client components use this hook; server-safe components (Button,
// DataTable, Skeleton, Stepper) keep the English defaults and take the text as a prop.
import { useMemo } from "react";
import { useLocale } from "../i18n/LocaleProvider";
import { DICTIONARIES, type Locale } from "../i18n/index.ts";
import { UI_STRINGS, type UiStringKey } from "./strings.ts";

export type UiStrings = Record<UiStringKey, string>;

/** The raw templates ({min} unfilled; fill() inserts values where they are used). */
export function uiStrings(locale: Locale): UiStrings {
  const dictionary = DICTIONARIES[locale] as Record<string, string>;
  const result = {} as UiStrings;
  for (const key of Object.keys(UI_STRINGS) as UiStringKey[]) result[key] = dictionary[`ui.${key}`] ?? UI_STRINGS[key];
  return result;
}

export function useUiStrings(): UiStrings {
  const { locale } = useLocale();
  return useMemo(() => uiStrings(locale), [locale]);
}
