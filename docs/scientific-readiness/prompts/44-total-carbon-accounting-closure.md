# Prompt 44 — Total-carbon accounting closure

Continue after Prompt 43. Reuse Prompt 21's catalogue and ledger; do not create a
parallel carbon calculator.

## Objective

Produce an auditable total-emissions ledger for one authoritative current factor
scenario and one clearly labelled Scheme C reproduction scenario.

## Required implementation

- Resolve every generator and interconnector alias to a reviewed factor or stop
  the total with an explicit unresolved status. Add Norway only from a source
  whose licence permits the intended distribution.
- Allocate construction and lifecycle emissions by asset technology, capacity,
  vintage and commissioning event. Treat storage power and energy components
  explicitly and avoid double counting charging electricity.
- Keep operational combustion, imported electricity, renewable construction,
  storage lifecycle and other infrastructure components separate, then sum them
  through one typed ledger.
- Store factor value, unit, boundary, geography, year, source, licence, version
  and transformation provenance. Do not embed restricted third-party tables.
- Preserve the Scheme C factor snapshot for reproduction without presenting it as
  a current authoritative lifecycle assessment.

## Acceptance

- Unit and integration tests cover zero dispatch, imports, storage charging and
  discharge, commissioning, retirement and mixed vintages.
- Component totals reconcile to annual total emissions and both operational and
  overall carbon intensity.
- Every non-zero activity has exactly one factor decision; unresolved factors
  make the total non-publishable rather than silently zero.
- The annual API, SQLite ledger and export contain the same values and provenance.

## Stop condition

Do not claim total carbon emissions until authoritative-scenario coverage is
complete and redistribution-safe.
