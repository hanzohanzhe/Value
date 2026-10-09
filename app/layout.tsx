import type { Metadata } from "next";
import { cookies } from "next/headers";
import { LocaleProvider } from "./i18n/LocaleProvider";
import { LOCALE_COOKIE, htmlLang, parseLocale } from "./i18n/index.ts";
import Workbench from "./features/shell/Workbench";
// Cascade layers in order (spec 1.1); globals.css declares the order and the tokens.
import "./globals.css";
import "./styles/reset.css";
import "./styles/base.css";
import "./styles/workbench.css";
import "./styles/utilities.css";

export const metadata: Metadata = {
  title: "VALUE · Research workbench",
  description: "Reproduce electricity-system studies, add data, edit modules and develop new model functions with traceable Study and Run evidence.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: {
    title: "VALUE Research workbench",
    description: "Variable renewable electricity Allocation, Load-enabled excess-generation Utilisation, and system Evolution",
    images: [{ url: "/og-value.png", width: 1200, height: 630, alt: "VALUE experimental network research workbench" }],
  },
};

// Every page is rendered per request: the UI gateway's CSP nonce differs per
// response, so no pre-rendered HTML may be served (P0-1, R1-14).
export const dynamic = "force-dynamic";

// P1 spec 3 (A30): English by default; the reader's choice is the cookie
// value_locale, read here so the server already renders the chosen language
// and <html lang> (no flash).  The browser language is never consulted.
// P1 spec 5 (W3): the workbench shell (state, sidebar, top bar) is mounted here
// once, so it survives route changes; each route renders its page inside it.
export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const locale = parseLocale((await cookies()).get(LOCALE_COOKIE)?.value);
  return <html lang={htmlLang(locale)}><body><LocaleProvider initialLocale={locale}><Workbench>{children}</Workbench></LocaleProvider></body></html>;
}
