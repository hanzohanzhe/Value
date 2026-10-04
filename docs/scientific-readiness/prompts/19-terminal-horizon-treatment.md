# Prompt 19 — Terminal-horizon treatment for fleet and planning pipeline

Continue from accepted Prompt 18. Read the ten-year planning summaries and annual
state-transition contracts. Act as a long-horizon capacity-expansion modeller.

Apply the preservation boundary in `docs/scientific-readiness/README.md`: never
edit retained Scheme C sources, fixtures, the installed data pack or historical
run bundles.

## Objective

Make the age, remaining life and model residual value of the operating fleet
explicit, together with end-of-horizon projects, capacity and costs. A 2034 result
must not hide projects that are active, deferred or scheduled to commission after
the last PSM year.

## Non-duplication boundary

- Reuse the existing planning ledger and commissioning logic.
- Do not change success probabilities, project timelines or in-horizon investment
  decisions merely to reduce the terminal pipeline.
- Do not invent a salvage value or terminal-value formula without a documented
  scientific source and a separately versioned policy.

## Implement

1. Define a `TerminalStateReport` reconciling operating stock and every planning
   project at the last simulated year by technology, region, stage, expected
   completion, MW/MWh, sunk/committed cost and outcome status.
2. Add a versioned `FleetVintageLedger` for every currently operating asset with
   asset/source ID, technology, location, MW/MWh, commissioning/vintage year,
   declared technical/economic life, expected retirement year, current age,
   remaining life and the exact source or imputation rule for every field. Unknown
   values are `not_evaluated`; they are never silently replaced by zero or a
   technology median.
3. Distinguish three value concepts instead of publishing one ambiguous residual:

   - historical/accounting book value, only when an asset-specific cost and
     depreciation basis exists;
   - `model_remaining_capital_value`, calculated as the present value of remaining
     annualised model capital charges under the pinned CEM discount-rate/lifetime
     assumptions;
   - market/salvage value, `not_evaluated` unless a separately sourced and selected
     terminal-value policy exists.

   Report GBP base year, valuation year, formula, cost-source revision and data
   quality. Do not feed an informational residual value back into investment,
   retirement or system cost without an explicit versioned policy selection.
4. Add explicit terminal policies:
   - `report_only`, preserving current equations and reporting outstanding state;
   - `pipeline_tail`, advancing planning to a declared final completion year
     without pretending that unrun PSM years have dispatch/economic results;
   - optional `full_extension`, which runs additional PSM/CEM years as a distinct
     project revision.
5. Show terminal active/commissioned/failed/deferred counts and MW in results, with
   detailed project evidence on demand.
6. Add compact fleet aggregates by technology for remaining MW, capacity-weighted
   remaining life, model remaining capital value and capacity reaching retirement
   within 1/5/10 years. Keep asset rows in a bounded audit/download view.
7. Add a warning when comparing scenarios whose final pipeline exposure or
   terminal policy differs materially.

## Tests and acceptance

- Synthetic projects completing before, at and after the horizon reconcile under
  every terminal policy.
- `pipeline_tail` changes no in-horizon PSM output or investment decision.
- A tail year cannot display fabricated generation, system cost or emissions.
- Terminal reports reproduce the outstanding counts/MW in completed ten-year
  bundles without modifying those bundles.
- Scenario comparison blocks an unqualified cost ranking when terminal treatments
  differ.
- Hand-calculated vintage fixtures cover new, mid-life, fully depreciated,
  retired and missing-vintage assets. Remaining capital value reconciles to the
  declared annuity/discount equation and never becomes negative.

## Stop condition

Do not call an end-year expansion trajectory complete while unreconciled projects
remain. Report the residual and fail the terminal-state gate.

## Deliverable

Provide terminal-policy definitions, reconciliation equations, synthetic tests,
completed-run audit and user-facing interpretation guidance.
