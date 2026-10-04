# Prompt 15 — Versioned storage technology catalogue and provenance

Continue from accepted Prompt 14. Read scientific Prompt 02, the current storage
technology constants, the thesis-derived storage-cost documentation and all data
roles that describe storage. Act as a storage technology data modeller.

Apply the preservation boundary in `docs/scientific-readiness/README.md`: never
edit retained Scheme C sources, fixtures, the installed data pack or historical
run bundles.

## Objective

Move duration, efficiency, lifetime, cycle life, CAPEX/FOM and related storage
assumptions out of unexplained code constants into a versioned, cited scientific
catalogue consumed consistently by dispatch, dynamic cost recovery and expansion.

## Non-duplication boundary

- Do not reimplement the storage-cost formula or alter its accepted defaults.
- Do not invent missing scientific values or citations.
- Preserve a versioned built-in compatibility catalogue that reproduces the
  current copied modular settings.

## Implement

1. Define one canonical `storage.technology_parameters` data role keyed by stable
   technology ID. Include power MW, energy MWh or duration h, charge/discharge
   efficiency, technical/economic life, battery-only cycle life/degradation rule,
   CAPEX basis, FOM basis, currency/base year and source fields.
2. Specify whether each monetary value is GBP/MW, GBP/MWh, GBP/project or a
   combined power/energy expression. Reject ambiguous unit bases.
3. Resolve fleet, bidding and expansion parameters from one catalogue revision.
   Cross-check `energy_mwh = power_mw × duration_h` and the fixed input/output
   energy ratio implied by efficiencies; reject contradictory overrides.
4. Add provenance down to source document/table/page or dataset record where
   available. Mark owner-supplied or thesis-derived values accurately; never
   present an inference as a quotation.
5. Allow a project to select a compatible catalogue revision or an imported
   canonical adapter output. Snapshot its hash with the run.
6. Keep compatibility defaults under an explicit ID and add a comparison report
   when a new catalogue changes any effective value.

## Tests and acceptance

- Round-trip unit tests for power-based, energy-based and combined cost bases.
- Inconsistent MW/MWh/duration or efficiency fields fail preflight.
- Battery entries require the battery degradation fields; pumped hydro and
  hydrogen cannot acquire battery cycle depreciation by omission/default.
- The compatibility catalogue reproduces all pre-change resolved parameters.
- A small alternative catalogue changes both PSM/storage-cost and expansion inputs
  through the same run snapshot and provenance.

## Stop condition

If the same technology resolves different duration, efficiency or economic basis
in dispatch and expansion, fail the run before execution. Do not select whichever
copy is convenient.

## Deliverable

Provide the catalogue schema, current-value/source table, unit equations,
compatibility comparison and proof of single-source consumption.
