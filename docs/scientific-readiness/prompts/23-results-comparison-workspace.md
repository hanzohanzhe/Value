# Prompt 23 — Decision-oriented results and scenario comparison workspace

Continue from accepted Prompt 22. Read visibility Prompt 08 and the current Run
centre/result APIs. Act as a senior frontend engineer and power-system results
analyst. Keep the product UI in English.

## Objective

Turn completed run cards into a scientifically labelled comparison workspace while
keeping period/project evidence on demand and payloads bounded.

## Non-duplication boundary

- Reuse existing annual result, planning, market, provenance and artifact APIs.
- Do not duplicate the audit table or load full ledgers into the browser.
- Do not recompute scientific metrics in JavaScript; consume versioned backend
  summaries with definition IDs.

## Implement

1. Add a comparison selection model keyed by run ID, project revision, data
   revision, module set, storage policy and execution/scientific status. Give runs
   human-readable names plus immutable IDs/timestamps so duplicate smoke runs are
   distinguishable.
2. Add compact annual views for:
   - reconciled cost decomposition and explicit GBP/MWh denominator;
   - installed MW and storage MWh;
   - generation, imports, charging/discharging and curtailment;
   - adequacy/unserved energy;
   - operational/lifecycle carbon;
   - storage utilisation/cost-recovery warnings;
   - planning pipeline, commissioning, failure/deferral and terminal stock.
3. Allow absolute, delta and percentage-delta comparison only for compatible metric
   definitions. Warn or block when cost/carbon definitions, terminal policies,
   periods, currencies/base years or scientific statuses differ.
4. Link every chart/card to provenance and bounded audit evidence. Detailed storage
   pricing fields remain in an audit drawer/download, not the main result card.
5. Replace the initial false `offline` flash with distinct loading, online, offline
   and retry states. Explain scientific gate failures and `not_evaluated` results
   in plain English.
6. Add server-side summary endpoints/caching with pagination and payload budgets.
   Avoid embedding full run arrays in the initial workspace response.
7. Ensure keyboard navigation, accessible chart alternatives, responsive layout,
   readable typography, stable colour semantics and exportable CSV/PNG summaries.
8. Add a storage-policy experiment workflow that clones one immutable base project
   while changing only the storage participation/cost module. It must compare the
   published dynamic recovery policy, Scheme C legacy tariff and any conformant
   user module directly in the frontend. If perfect-foresight co-optimization is
   selected, label storage offer pricing `not applicable` and compare it as a
   different PSM formulation, not as a fourth tariff.
9. Show a module-difference strip before charts. A clean storage-policy comparison
   requires identical data snapshot, non-storage modules, years, CEM parameters,
   carbon/cost definitions and terminal treatment. Otherwise show every changed
   dimension and block an unlabeled causal claim.
10. Export the current comparison as bounded CSV and JSON with metric IDs,
   denominators, run IDs and provenance; export charts as accessible PNG/SVG where
   supported. Never export only rendered labels without the machine-readable
   values behind them.

## Tests and acceptance

- Compare dynamic, legacy, a synthetic conformant user storage module and the
  retained-reference run with correct compatibility warnings and metric labels.
- One-click storage-policy cloning changes only the selected storage module and
  project fingerprint; all controlled dimensions remain byte-identical.
- A smoke run cannot appear as annual scientific evidence.
- A cost-definition mismatch cannot produce an unlabeled delta.
- Initial, loading, empty, failed, partial and completed states render correctly.
- Growing market/planning ledgers does not materially grow the initial payload.
- All chart values match backend fixture summaries exactly.

## Stop condition

If a displayed metric lacks a schema version, unit, denominator or provenance
reference, remove it from the comparison view until the backend contract supplies
those fields.

## Deliverable

Provide user flows, route/component/API changes, compatibility rules, payload
measurements, screenshots and a metric-to-source mapping.
