# Prompt 04 — Durable planning pipeline lifecycle and ledger

Continue from accepted Prompts 01-03. Act as a domain modeller and event-ledger
designer. Preserve the existing Scheme C success and timeline calculations unless
the task only wraps them with evidence.

## Objective

Make every planning project and transition visible. A filtered or failed project
must produce a durable event before leaving the active pipeline.

## Mandatory constraints

- Do not change current effective filtering, success, timing, allocation or
  commissioning results.
- Do not display a project as failed merely because it is outside the selected
  simulation horizon; use distinct reason codes.
- Expected-capacity mode and stochastic success mode must remain distinguishable.
- Do not put the complete project table in `status.json`.

## Work

1. Implement the v2 `PlanningProject` and `PlanningEvent` contracts with stable
   project IDs, normalized stage/status values and reason-code enums.
2. Wrap all current pipeline entry, filtering, success evaluation, deferment,
   allocation, completion and retirement points with events.
3. Record source REPD identity when available; generate deterministic IDs for
   model investments from project/scenario/year/agent without relying only on name.
4. Separate:
   - source import;
   - model eligibility/filtering;
   - planning success evaluation;
   - active pipeline state;
   - commissioning into operating stock.
5. Persist `model-output/planning/pipeline.sqlite` with `projects`, `events` and
   `annual_summary` tables. Use batch inserts and stable schema/version metadata.
6. Persist a small `planning/summary.json` suitable for the normal Run response.
7. Include counts and MW by year, outcome, stage, technology and region, plus the
   next three expected completion years.
8. Add reconciliation checks so imported/admitted projects can be accounted for as
   active, commissioned, failed/filtered, retired or explicitly outside scope.
9. Provide read/query functions with pagination and filters; do not add the UI in
   this prompt.

## Tests

- Unit tests for every event/reason code.
- Expected-mode and seeded-stochastic determinism tests.
- Pipeline reconciliation/property tests.
- Location/region preservation tests, including missing coordinates.
- Two-period run proves ledger wiring without claiming annual economics.
- Full fixture-level annual transition comparison proves no capacity-path change.
- Retained-source hash test.

## Deliverable

Report project/event schemas, reconciliation equations, existing disappearance
paths now captured, database size on the test fixture and numerical parity.
