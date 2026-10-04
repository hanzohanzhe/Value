# Prompt 11 — Reconciled cost accounting and published cost semantics

Continue from accepted Prompts 01-10. Read
`RELEASE_GAP_MATRIX.md`, the current annual-result calculation in the copied
Scheme C modular implementation, and the storage-cost policy outputs before
editing. Act as a power-system economist and scientific-accounting engineer.

## Objective

Make the headline `system_cost` the annual system resource cost of the selected
CEM scenario and reconcile it through a versioned annual ledger. Preserve the
historical Scheme C value under an explicit legacy name; do not rewrite old runs
or disguise a changed definition as parity.

## Non-duplication boundary

- Reuse the named results from visibility Prompt 03, the market ledger from
  visibility Prompt 07, and storage policies from scientific Prompt 02.
- Do not rebuild storage bids, annual orchestration or period tracing here.
- Do not alter dispatch order, investment decisions or retained Scheme C source.

## Implement

1. Define a versioned `AnnualCostLedger` with explicit units and at least four
   non-overlapping views:
   - physical resource cost;
   - market settlement/payment;
   - policy transfer or subsidy;
   - consumer-facing cost.
2. Define the canonical CEM headline before changing readers:

   `cem_system_cost_gbp = annualised capital cost of commissioned in-service
   fleet + fixed O&M + PSM physical operating resource cost + storage physical
   degradation + reliability/unserved-energy cost + other explicitly classified
   physical terms`.

   Publish `cem_system_cost_gbp_per_mwh_served` using demand actually served as
   the default denominator. A second generated-energy denominator may be exposed
   only with a different metric ID. Market payments, storage bid recovery,
   subsidies/policy transfers, uncommissioned pipeline CAPEX and residual/salvage
   values are separate ledger views and cannot enter this headline silently.
3. Within physical resource cost, name annualised capital, generator fuel and
   variable O&M, fixed O&M, storage fixed O&M, battery cycle degradation,
   unserved-energy penalty and other declared terms. Record `not_applicable` or
   zero with a reason; never infer missing data as zero.
4. Classify a storage bid/payment as a market-recovery mechanism, not automatically
   as an additional physical cost. Include each storage CAPEX/FOM/degradation term
   exactly once and document the treatment of charging energy and losses.
5. Build the headline from the actual annual CEM state. The PSM contributes typed
   dispatch/OPEX components; the CEM/fleet state contributes commissioned asset
   CAPEX/FOM and retirement status. Annualise commissioned CAPEX under the pinned
   technology cost/lifetime/discount-rate revision. Do not expense full investment
   CAPEX in the proposal year unless a separately named cash-flow view requests
   it. Projects still in planning do not enter the in-service system cost.
6. Preserve the current published calculation as
   `scheme_c_legacy_system_cost_gbp_per_mwh_generated`, with formula and source
   fields. Add scientifically named metrics using both:
   - total non-storage generation MWh;
   - demand served MWh, net of unserved energy.
7. Add reconciliation equations from asset-period inputs to annual totals. Report
   absolute and relative residuals and fail the scientific-publication gate when
   a required residual exceeds a declared tolerance.
8. A PSM-only diagnostic without a CEM/fleet cost state must return the canonical
   CEM system cost as `not_evaluated`, not zero. Short runs may exercise equations
   but cannot publish an annual GBP/MWh result.
9. Version the new result schema and migrate readers so historical bundles remain
   readable without mutation. UI labels must state the numerator and denominator.
10. Put detailed rows in a bounded artifact; keep only totals, denominators,
   residuals and definition IDs in normal run results.

## Tests and acceptance

- Hand-calculate fixtures containing thermal generation, VRE, charging losses,
  storage discharge, battery wear, pumped hydro without cycle wear, unserved
  demand and a policy transfer.
- Prove storage physical costs are counted once even when storage bids recover the
  same annual project cost.
- Prove GBP/MWh generated and GBP/MWh served differ when charging/losses exist.
- A two-year fixture proves that a proposed project enters no in-service cost,
  commissioning adds its annualised cost once, and retirement removes future
  in-service charges without rewriting the prior year.
- The displayed headline equals the CEM ledger value exactly; frontend code does
  not recompute or substitute the legacy metric.
- Prove the legacy metric is bitwise or tolerance-equal to the pre-change copied
  modular output for the same fixture.
- Run one full-year modular baseline and reconcile every cost view.
- Retained-source hashes and historical run-directory hashes remain unchanged.

## Stop condition

If any current term cannot be classified as a resource cost, payment or transfer,
mark it `unclassified`, fail publication, and report the originating field. Do not
silently force the ledger to balance.

## Deliverable

Provide the cost dictionary, equations, migration note, fixture calculations,
annual reconciliation result and a before/after table of every public cost label.
