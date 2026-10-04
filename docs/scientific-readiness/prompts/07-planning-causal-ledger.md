# Prompt 07 — Planning-pipeline causal visibility

Act as a CEM validation engineer. Make annual fleet evolution explainable from
project events without cluttering the main results view.

## Implement

1. Extend the planning annual summary with stage inflow/outflow, admissions,
   success evaluations, failures, deferrals, commissioning and removal reasons.
2. Reconcile project counts and MW by year, technology, region, stage, outcome
   and reason code. Preserve project-level events for on-demand audit.
3. Add a compact pipeline panel and filters for failures and commissioning.
4. Link an operating-capacity change back to commissioned project IDs or an
   explicit exogenous/source reason.
5. Never put all project rows in the normal run status payload.

## Tests and acceptance

- Synthetic projects cover every lifecycle outcome and conservation of counts/MW.
- The two-year smoke proves 2025 pipeline output becomes 2026 pipeline input.
- API pagination remains bounded.
