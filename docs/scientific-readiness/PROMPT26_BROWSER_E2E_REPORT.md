# Prompt 26 browser E2E and accessibility report

Status: **core browser acceptance passed; extended failure matrix remains partial**.

Command: `npm run test:e2e`. The harness starts the real Python application service
and built frontend on isolated loopback ports 18766/18800 using a temporary
`FORCE_DATA_HOME`, waits for health, and terminates its exact child processes.
Screenshots and traces are retained only on failure.

Four Playwright tests passed with Chromium:

1. create a real synthetic project, choose an installed external PSM, revise
   settings, execute a two-year smoke, observe completion, verify the external
   marker/module event, inspect results, and validate the exported bundle;
2. reject an incompatible module selection and exercise offline/reconnect state;
3. verify desktop and narrow layouts plus initial payload below 512 KiB;
4. verify labels, keyboard focus, 200% zoom and no serious/critical axe violation.

The happy path does not mock the application service or load a pre-baked completed
run. Manual production-browser inspection also confirmed the English interface,
25/25 required data roles, 10/17 executable modules, visible transition selection,
three PSM choices, Python 3.10.11 status and no console warning/error.

Defects found and fixed during E2E included Windows production assets returning
404, a missing transition module in project composition, queued runs being hidden
before execution identity was attached, connection-abort noise during polling,
missing navigation labels and insufficient secondary-text contrast.

Cancellation, native checkpoint resume, stale revisions, quota and unavailable
optional capabilities have real Python integration tests, but not every one has a
dedicated browser scenario yet. Dialog focus trapping and chart text alternatives
are not applicable to the current pages because no modal/chart component is used.
The public release report keeps the unautomated browser rows explicit rather than
calling the entire failure matrix complete.
