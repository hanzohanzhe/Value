# Prompt 03 — Run classification and publication gates

Act as a scientific-computing product engineer. Make run purpose and evidence
unambiguous in API, CLI and UI.

## Implement

1. Centralise run modes and their years, periods, purpose and publication policy.
2. Distinguish `execution_status`, `contract_validation_status` and
   `scientific_validation_status`.
3. Two-period verification and two-year smoke runs may show diagnostics only.
   Full-year modes may show economics only after required invariants pass.
4. Labels must distinguish Completed, Contract validated, Scientific baseline
   matched, Not evaluated and Failed.
5. Write the policy decision into status and provenance so the frontend cannot
   infer scientific validity from a green process exit.

## Tests and acceptance

- All entry points resolve the same mode policy.
- Short runs contain no public annual result rows.
- Full-year results are withheld if a required invariant fails.
- Rendered UI tests verify the three independent statuses.
