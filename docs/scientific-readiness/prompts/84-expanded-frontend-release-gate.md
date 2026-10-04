# Prompt 84 — Expanded-frontend release gate

Execute after Prompts 77–83. Implement no new product feature here. Act as an
independent test engineer, accessibility reviewer, power-system modeller and
release auditor. Start from a clean clone and retain the Prompt 77 rollback
identity.

## Objective

Decide, capability by capability, whether a non-programmer can install data and
extensions, compose, preflight, run, inspect, compare, export and reproduce the
expanded platform without manual JSON or source editing.

## Required end-to-end journeys

1. **Unchanged single-node:** load an old v2 Study and prove graph and results do
   not migrate.
2. **Reference DC:** install/select the network contract and synthetic pack,
   compose a Study, run 24 and 168 hours, inspect nodal/branch results and export.
3. **Hydrology:** enable the extension, complete conditional roles, run
   run-of-river and reservoir fixtures and prove pumped hydro is not duplicated.
4. **Experimental AC feasibility:** acknowledge maturity, satisfy AC roles, run
   converged and infeasible fixtures, and verify the UI never says AC OPF.
5. **Transmission expansion:** select DC plus the expansion lifecycle, run the
   causal two-year fixture and trace commissioned capacity into next-year actual
   clearing and cost/carbon ledgers.
6. **Third-party extension:** install the Prompt 65 toy bundle, use its role and
   parameter, preserve it through snapshot/export/import, then enforce in-use
   disable protection.
7. **Negative journeys:** missing solver, role, licence acknowledgement,
   capability, endpoint, hydrology mapping, extension version and disk headroom.

## Verification matrix

Run the complete Python suite; frontend lint/build/rendered tests; browser E2E;
accessibility and responsive checks; generated-document consistency; source,
rights, dependency and archive scans; wheel/sdist clean installation; and
retained Scheme C hash checks. Verify preview/save/preflight/snapshot/run/result
graph identity equality for every journey.

Use 24/168-hour and causal two-year fixtures for frontend/integration claims. Do
not run or publish a new annual/ten-year network or hydrology baseline unless
scientific code changed or such a pathway is explicitly being claimed. Reuse
Prompt 64 evidence only for the unchanged single-node baseline.

## Documentation truth closure

Update README, bilingual README, user guides, installation, Build Your Own Model
101, generated module/parameter references and frontend scope copy. Remove stale
claims that Prompts 65–71 are merely drafted or that the entire 0.6 candidate has
no network capability. State instead:

- the default UK baseline remains single-node;
- DC is ready only for its declared reference scope;
- hydrology, AC feasibility and transmission expansion retain their Prompt 71
  maturity;
- no real-UK hydrology/network or national expansion baseline has been accepted.

## Decisions and stop conditions

Issue separate `GO`, `EXPERIMENTAL`, `NO_GO` or `NOT_EVALUATED` decisions for
single-node UI compatibility, extension installation, Study composition,
conditional data, DC workflow, hydrology workflow, AC feasibility workflow,
transmission expansion workflow, results exploration and real-data packs.

Return `NO_GO` only for the affected workflow if it requires manual state edits,
displays a different graph from execution, hides required data, permits an
unacknowledged experimental choice, fabricates a result or loses provenance.
Do not weaken a gate or alter model science inside this release prompt.

## Deliverables

- human-readable expanded-frontend test report;
- machine-readable decision and claim-to-evidence matrix;
- clean-clone logs and browser screenshots for the five principal workflows;
- final data/module/extension/results field map;
- explicit list of any workflow still requiring developer intervention.

