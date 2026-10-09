import { useT } from "../../i18n/LocaleProvider";

/** The only full-page error of this release (P0 frontend spec section 8):
 * shown when the UI gateway or the API refuses the page (wrong host, no
 * launcher session).  It never shows a token or a path. */
export default function OpenFromLauncher() {
  const t = useT();
  return (
    <main className="launcher-required" role="alert" aria-labelledby="launcher-required-title">
      <section>
        <h1 id="launcher-required-title">{t("launcher.title")}</h1>
        <p>{t("launcher.body")}</p>
      </section>
    </main>
  );
}
