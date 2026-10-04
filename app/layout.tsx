import type { Metadata } from "next";
import "./globals.css";

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

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en-GB"><body>{children}</body></html>;
}
