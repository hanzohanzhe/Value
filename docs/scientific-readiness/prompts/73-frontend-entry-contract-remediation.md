# Prompt 73 — Frontend entry-contract test remediation

Opened by the Prompt 71 frontend gate after the production build and lint passed.
The rendered-contract test still required the pre-Prompt-65 literal call
`registry.resolve_selection(selected)`, while the live application correctly calls
the one registry with selected extensions, extension parameters and available data
roles.

Update only the static test assertion so it proves the current fail-closed
resolution contract. Do not simplify the application call or bypass extension
capability negotiation. Re-run frontend lint, build, rendered tests and browser
E2E. Acceptance requires the test to check the selected module map and all
extension/data-role arguments.
