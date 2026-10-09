// Text the hard-coded-string scan (tests/frontend/unit/i18n-hardcoded-strings.test.mjs)
// does not treat as interface wording (P1 spec 3): product names, technical
// codes, units and symbols.  They read the same in both languages.
export const I18N_ALLOWLIST: readonly string[] = [
  // product and technical names
  "VALUE", "VALUE 101", "VA", "PSM", "CEM", "VRE", "GB", "UK", "API", "Python", "CSV", "JSON", "SHA-256", "ID", "UTC", "DC", "AC", "CfD", "ROC",
  "ERA5", "REPD", "DUKES", "Elexon", "NESO",
  // P1 W4b: currency and hash codes shown beside values, and the TypeScript
  // Promise type (the scan reads "=> Promise<void>" in a props type as text).
  "GBP", "EUR", "SHA", "Promise",
  // language names are written in their own language
  "English", "中文",
  // units
  "MWh", "MW", "GWh", "GW", "TWh", "kWh", "£", "£/MWh", "%", "h", "s", "tCO₂e", "bn", "m", "k",
  // symbols
  "·", "→", "←", "—", "–", "…", "×", "●", "○", "/", "|", ":", "+", "-", "−", "=", "(", ")", "#", "≥", "≤", "<", ">",
];
