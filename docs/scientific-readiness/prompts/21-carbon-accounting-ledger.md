# Prompt 21 — Reconciled operational, lifecycle, import and storage carbon ledger

Continue from accepted Prompt 20. Read the current operational/overall carbon
outputs, market ledger and storage chronology. Act as a power-system carbon-
accounting specialist.

Apply the preservation boundary in `docs/scientific-readiness/README.md`: never
edit retained Scheme C sources, fixtures, the installed data pack or historical
run bundles.

## Objective

Connect the existing carbon-factor database to the actual PSM/CEM calculation so
users can calculate total annual carbon emissions as well as intensity. Make every
result traceable to a declared numerator, denominator and factor scenario,
including carbon carried into and out of storage. Prevent double counting of
storage losses, fixed storage factors and imported electricity.

## Non-duplication boundary

- Do not change dispatch or storage bidding in this task.
- Reuse period-level charge/discharge/SOC evidence and canonical technology data.
- Preserve historical carbon values under explicit legacy names rather than
  rewriting old run bundles.

## Implement

1. Define a versioned `CarbonLedger` separating direct operational emissions,
   upstream/lifecycle emissions, imported-electricity emissions, storage-carried
   emissions and any policy accounting adjustment.
2. Add immutable `CarbonFactorScenario` manifests and expose exactly two built-in
   starting selections:

   - `force_current_authoritative_v1`, which pins reviewed records and explicit
     technology variants from `uk_authority_reference_2026_08_06` plus declared
     operational/import sources. It may publish physical `tCO2e` only when every
     active technology has a compatible factor/boundary or an explicit
     `not_applicable` reason;
   - `scheme_c_reproduction_2026_07_18`, which pins
     `scheme_c_2026_07_18` and reproduces the retained carbon calculation without
     correcting it.

   The selected scenario, record IDs, variants, boundaries and database hash must
   enter the project revision, run snapshot and result provenance. Never choose an
   ambiguous catalogue row silently.
3. Publish `total_carbon_emissions_tco2e` and named component masses before
   deriving any intensity. Name the denominator for every intensity: gross
   generation, delivered demand, or another declared basis. Publish kgCO2e/MWh
   with numerator tonnes and denominator MWh.
4. Track storage carbon through chronological charging inventory. Allocate charge
   source carbon using the declared market accounting rule, apply charge/discharge
   losses once, and carry remaining carbon with SOC. Discharge transfers carried
   carbon; it does not create it.
5. Keep embodied storage lifecycle factors separate from energy-carried carbon.
   Battery cycle degradation, if assigned a lifecycle factor, must be a named term
   and cannot also appear as fixed discharge carbon.
6. Treat interconnector imports as exogenous supply with a selected, sourced carbon
   profile. Do not model an external network that is outside the declared system
   boundary.
7. Reconcile period and annual carbon mass, including ending stored inventory,
   curtailment treatment and losses. Gate publication on required residuals.
8. Handle the legacy boundary honestly. Scheme C storage scalars 40/50 currently
   have no declared physical unit. Preserve and reproduce their exact legacy
   formula under `scheme_c_legacy_carbon_metric`, but do not label that result
   `tCO2e` or combine it into a physically reconciled total until a source and unit
   are established. Return a reason-coded `not_physically_interpretable` total
   while still reporting the exact reproduction value.
9. Add a frontend factor-scenario selector and carbon result panel showing total
   mass, direct, lifecycle/embodied, imports, storage-carried transfer, ending
   inventory, intensity definitions and reconciliation status. Detailed factor
   rows remain in the audit/download view.

## Tests and acceptance

- Analytical fixtures cover zero-carbon charge, fossil charge, mixed charge,
  multi-period dwell, losses, ending SOC and imported supply.
- Storage discharge never has less/more carried carbon than inventory equations
  allow; ending inventory closes the mass balance.
- Operational and lifecycle metrics differ only by named terms.
- Legacy overall/operational values remain readable under explicit formulas.
- One full-year run produces a reconciled ledger and bounded UI summary.
- Switching only the factor scenario changes the project fingerprint and carbon
  ledger but not dispatch, investment or planning state.
- The authoritative scenario produces a hand-reconciled physical total. The
  reproduction scenario matches the retained fixture exactly and surfaces the
  unresolved storage-unit limitation rather than relabelling it.

## Stop condition

If source-specific generation cannot be assigned to charging under the declared
single-node clearing evidence, mark storage-carried carbon `not_evaluated` or use a
clearly documented average-pool rule. Do not fabricate plant-level tracing.

## Deliverable

Provide system boundaries, equations, factor provenance, analytical fixtures,
annual reconciliation and corrected result labels.
