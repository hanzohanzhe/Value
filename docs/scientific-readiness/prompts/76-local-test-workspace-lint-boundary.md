# Prompt 76 — Local test-workspace lint boundary

Opened by the Prompt 75 frontend gate. `work/` and `.venv/` are gitignored local
installation and release-test state, but the ESLint global ignore list did not
name them. After clean-clone and wheel-upgrade fixtures were created under
`work/`, `npm run lint` recursively inspected generated `.next` and `dist`
objects in those fixtures and reported generated-code failures unrelated to the
candidate source.

Align the lint input boundary with Git and source-release boundaries by ignoring
root `work/`, `.venv/` and generated Python package metadata. Do not relax any
rule for tracked application source. Prove that a deliberately invalid tracked
source file still fails lint, then rerun lint, production build, rendered tests
and browser E2E.
