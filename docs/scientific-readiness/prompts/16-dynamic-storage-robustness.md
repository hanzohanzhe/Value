# Prompt 16 — Scientific robustness of dynamic annual storage-cost recovery

Continue from accepted Prompt 15. Read the completed ten-year dynamic and legacy
reports and the exact previous-year recovery policy. Act as a storage-market
validation researcher.

Apply the preservation boundary in `docs/scientific-readiness/README.md`: never
edit retained Scheme C sources, fixtures, the installed data pack or historical
run bundles.

## Objective

Characterise, rather than conceal, the zero-sales and low-utilisation behaviour of
the dynamic annual-average recovery rule. Keep the thesis-exact zero-floor scenario
unchanged and compare declared sensitivity scenarios separately.

## Non-duplication boundary

- Do not rewrite the accepted dynamic policy, first-year full-utilisation rule or
  battery-only cycle depreciation.
- Do not add smoothing, caps or floors to the default without creating a new
  versioned policy/parameter scenario.
- Reuse existing storage evidence artifacts; keep detailed rows out of the main
  run card.

## Implement

1. Add a storage cost-recovery adequacy artifact by technology/year containing:
   annual levelised project cost, physical degradation, sold MWh, sales-weighted
   dwell time, bid-recovered revenue, other storage revenue, under/over recovery,
   fallback reason and effective utilisation denominator.
2. Reconcile the bidding denominator to previous-year delivered MWh and the cost
   numerator to the same catalogue/project boundary. Make first-year design-case
   assumptions explicit.
3. Define immutable experiment variants for utilisation floors of 0%, 1%, 5% and
   10% of declared full-utilisation sales. Label 0% `thesis_exact`; label all
   others `sensitivity`, not corrections.
4. Run a bounded multi-year experiment that exposes zero-sales-after-positive-
   basis, fallback frequency, extreme bid/recovery values, storage dispatch,
   investment, curtailment, system resource cost and pipeline outcomes.
5. Add compact comparison summaries and warning codes. An extreme value may be a
   scientific result; do not silently clip it. Permit an explicitly selected and
   versioned guardrail policy only as a separate research scenario.

## Tests and acceptance

- Analytical two-year cases cover full use, partial use, zero previous sales,
  long dwell, battery wear and pumped hydro without wear.
- For positive sales, recovered bid revenue and declared recovery target reconcile
  under the policy equation within tolerance.
- The floor=0 implementation remains numerically unchanged from its accepted
  baseline.
- Sensitivity runs are fingerprint-distinct and never overwrite the thesis-exact
  run.
- Report counts of fallback, zero-sales transitions and declared extreme-value
  thresholds rather than hiding them.

## Stop condition

Do not recommend a new default from one deterministic path. If sensitivity changes
investment or dispatch materially, require the ensemble work in Prompts 18 and 20
before a default-policy decision.

## Deliverable

Provide policy equations, adequacy schema, analytical fixtures, sensitivity table,
warning definitions and a bounded scientific interpretation.
