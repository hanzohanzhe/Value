# Prompt 26 — Real browser end-to-end, accessibility and failure-path tests

Continue from accepted Prompt 25. Read existing rendered HTML tests and the local
browser workflow. Act as a frontend test architect. Keep all visible copy in
English.

Apply the preservation boundary in `docs/scientific-readiness/README.md`: never
edit retained Scheme C sources, fixtures, the installed data pack or historical
run bundles.

## Objective

Replace string/build-only confidence with deterministic browser tests that exercise
the real API, project/data/module workflow, model launch and recovery states.

## Non-duplication boundary

- Keep current unit/render tests; add browser-level coverage rather than rewriting
  all tests as E2E.
- Use the redistributable synthetic pack for CI. Long UK annual runs are release
  evidence, not per-commit browser tests.
- Do not mock the application service in the primary happy-path test.

## Implement

1. Add a Playwright or equivalent test harness that starts the packaged local
   service on an isolated loopback port, waits for health readiness and always
   cleans up its exact child process and temporary workspace.
2. Cover the non-programmer happy path: open site, import/select synthetic data,
   inspect mappings, create/revise a project, select modules, edit advanced
   settings, run preflight, launch a small two-year run, observe progress, inspect
   annual/pipeline results and download/validate an artifact.
3. Cover failure paths: invalid data mapping, incompatible module, blocking
   preflight, model failure, cancellation, resume, offline/reconnect, stale project
   revision and unavailable optional export.
4. Verify a selected external fixture module is actually executed and visibly
   changes the expected result, closing the UI-to-runtime proof from Prompt 12.
5. Add automated accessibility checks plus manual assertions for labels, focus
   order, keyboard-only use, dialog focus trapping, colour contrast, status not
   conveyed by colour alone, chart text alternatives and readable zoom.
6. Test representative desktop/narrow layouts and loading/empty/large-summary
   states. Prevent the initial online service from flashing a false offline error.
7. Capture screenshots/traces only on failure by default and exclude local paths,
   sensitive data and huge model artifacts from CI uploads.

## Tests and acceptance

- The happy path runs against real backend/application code and validates the run
  bundle.
- Tests run deterministically on the supported clean CI Windows environment.
- No critical automated accessibility violation remains; documented exceptions
  need owner acceptance and expiry.
- Network/API assertions prove initial payloads stay within the declared budget.
- Test cleanup leaves no worker, locked port or mutable shared research directory.

## Stop condition

Do not call a browser workflow covered when it bypasses the production application
service or uses a pre-baked completed result for the primary happy path.

## Deliverable

Provide the E2E matrix, accessibility report, CI command, failure artifacts,
payload measurements and proof of real module execution.
