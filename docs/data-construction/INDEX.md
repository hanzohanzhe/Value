# FORCE data-construction workstream

This index is independent of the numbered model prompts. `DATA-*` prompts build
the reproducible data infrastructure consumed by model Prompt 98; they do not
renumber, replace or reinterpret model Prompts 93–106.

Design authority:
`docs/superpowers/specs/2026-08-21-data-workbench-design.md`.

## Execution order

| Prompt | Gate | Status |
| --- | --- | --- |
| DATA-01 | Lifecycle and service contracts | passed |
| DATA-02 | Official source registry and discovery | passed |
| DATA-03 | Secure fetch and raw-object store | passed |
| DATA-04 | DSO and ETYS compilers | passed |
| DATA-05 | Regional-demand compiler | passed |
| DATA-06 | Interconnector compiler | passed |
| DATA-07 | Zone, corridor and cut review candidate | passed |
| DATA-08 | Validation, reporting and promotion | passed |
| DATA-09 | CLI and local job API | passed |
| DATA-10 | Frontend, official build and Prompt 98 handoff | implementation passed; official candidate stopped on missing/unreviewed inputs |

No prompt starts until its predecessor's acceptance gate passes. The executor
records commits, tests, artifacts, candidate inventory and unresolved blockers
in `docs/data-construction/GAP_MATRIX.md`.

## Global constraints

- Preserve retained Scheme C hashes.
- Preserve copperplate execution without network data.
- Do not change PSM, CEM or redispatch mathematics.
- Runtime reads promoted bundles offline and never downloads scientific inputs.
- Official-source candidates remain isolated until validation and explicit
  promotion.
- Mechanical failures cannot be waived.
- Scientific approximations use named, reviewable waivers.
- Existing Prompt 98 entry points remain import-compatible.
- Large raw objects, candidates and installed bundles remain outside Git.
