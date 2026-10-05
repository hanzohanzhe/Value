/** The only full-page error of this release (P0 frontend spec section 8):
 * shown when the UI gateway or the API refuses the page (wrong host, no
 * launcher session).  It never shows a token or a path. */
export default function OpenFromLauncher() {
  return (
    <main className="launcher-required" role="alert" aria-labelledby="launcher-required-title">
      <section>
        <h1 id="launcher-required-title">Open VALUE from its launcher</h1>
        <p>
          This page was not opened through the VALUE launcher, so it cannot talk to the local engine.
          Close it and start VALUE again with start-value (or the desktop shortcut).
        </p>
      </section>
    </main>
  );
}
