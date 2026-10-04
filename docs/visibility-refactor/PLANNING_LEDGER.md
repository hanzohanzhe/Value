# Planning pipeline lifecycle ledger

Prompt 04 adds evidence around the copied Scheme C planning calculations. It
does not replace or change their success rates, completion-year calculation,
capacity allocation, or commissioning logic.

## Durable artifacts

Each modular run writes:

- `model-output/planning/pipeline.sqlite`: queryable project and event history;
- `model-output/planning/summary.json`: small per-year aggregates for the normal
  Run response.

The SQLite schema version is stored in `metadata` as
`gridform.planning-ledger/v1`. `projects` contains the latest normalized state,
`events` contains append-only lifecycle facts, and `annual_summary` contains
counts and MW grouped by outcome, stage, technology, region, and the next three
expected completion years. The full project table is deliberately excluded from
the normal status payload.

External project IDs use a REPD reference when the source provides one. The
fallback is a deterministic digest that includes source row, technology,
capacity, region and completion year. Model-investment IDs use the scenario,
decision year, target asset/agent fields, technology and original capacity.

## Reconciliation

For year `y`, let `I_y` be every source-imported REPD project and admitted model
investment observed up to the end of `y`. Let `A_y` be IDs remaining in the
active pipeline. Let `T_y` be the last terminal event for each ID: filtered,
failed, commissioned, retired/depleted, excluded existing stock, or explicitly
outside scope. The run requires:

`I_y = A_y union keys(T_y)` and `A_y intersect keys(T_y) = empty` for the
effective latest state.

An introduced ID that is neither active nor terminal stops the run with a
reconciliation error. Projects beyond the selected horizon are classified as
outside-horizon, never as failed planning.

## Captured disappearance paths

The ledger now distinguishes source import, external/model admission,
unsupported technology, uncertain/unknown status exclusion, status-stagnant and
schedule-overdue zombies, minimum-size filtering, existing operating stock,
before/after-horizon filtering, deterministic expected-capacity or seeded
lottery success evaluation, start-year deferment, location assignment,
commissioning, zero/failed capacity, retirement/depletion, and exogenous pumped
hydro treatment.

`gridform_core.planning_ledger.query_projects` and `query_events` expose bounded
pagination and filters without loading the complete ledger into memory.
