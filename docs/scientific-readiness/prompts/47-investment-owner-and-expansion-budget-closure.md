# Prompt 47 — Investment-owner identity and expansion-budget closure

Continue from accepted Prompt 46. Preserve the retained Scheme C sources,
Prompt 39/46 bundles and the Prompt 47 pre-change snapshot.

## Objective

Stop commissioned assets from becoming accidental new investment agents, make
annual expansion headroom a technology-wide budget, and make every technology's
new-build eligibility explicit.

## Non-duplication boundary

- Prompt 42 already proved project-to-asset-to-next-year clearing and cost
  coupling. Keep that lineage and economics; do not recreate it.
- Prompt 43 already names the public model `force-cem-v1` and declares divergence
  from retained Scheme C. Amend that identity; do not claim parity.
- Do not alter retained Scheme C or historical result bundles.

## Implement

1. Separate an operating asset ID from its investment-owner ID. Initial market
   agents receive stable owner IDs; model investments inherit the owner; external
   projects without an owner do not create a new investor at commissioning.
2. Aggregate annual income, operating cost, capacity and investment tests once per
   owner/technology/region group. Allocate retirement back to its physical assets.
3. Treat expansion-headroom values as one remaining annual MW budget per
   technology. The sum of proposals may not exceed it.
4. Add a versioned eligibility policy: wind, solar and storage require selected
   headroom; thermal technologies are explicitly uncapped under this FORCE-CEM
   version; natural-flow hydro and pumped hydro are site constrained; unknown
   technologies fail closed.
5. Existing pumped hydro remains operable. No model-generated pumped-hydro or
   natural-flow-hydro new build is allowed without a selected site/hydrology
   planning capability.
6. Record compact decision diagnostics: grouped owners, ineligible groups,
   initial and remaining technology budgets, and policy revision.

## Acceptance

- Two physical assets with one owner produce at most one proposal.
- A commissioned child asset cannot recursively multiply proposals.
- Multiple owners sharing one technology cannot exceed its headroom.
- Pumped hydro and natural-flow hydro produce no default model proposal.
- Existing stock still enters PSM clearing and the Prompt 42 lineage tests pass.

## Stop condition

Do not continue if an absent headroom key silently means an undocumented science
assumption or if commissioned asset count changes the number of investment tests.
