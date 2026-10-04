# Prompt 119 — VALUE context runtime wiring

## Scope

Prompt 119 wires Prompt 118's immutable context contracts into the live staged
PSM and zonal redispatch path. It does not change bid construction, the four
zonal LP phases, settlement, SOC updates, curtailment attribution, CEM order or
annual transition semantics.

## Runtime boundary

- The application loads and validates the selected signed network pack once,
  writes `market/context/run-context.json` atomically, binds the exact resolved
  module instances, and calls `psm.configure(run_context, resolver)`.
- The annual orchestrator prepares the exact PSM input, freezes and atomically
  writes `market/context/year-<YYYY>.json`, binds it, and calls `start_year`
  before the PSM executes.
- Each year context is rebuilt from that year's transitioned `YearState` and
  contains the fleet, frozen zones, resource classes, costs, storage technical
  metadata and opening SOC used by that year's market.
- The staged PSM precomputes network period indices once and emits only
  `value.zonal-redispatch-domain/v2` references plus the current-period demand,
  ahead result, directional boundary ratings and interconnector envelopes.
- Zonal clearing resolves static and annual metadata at lifecycle boundaries,
  rejects wrong or unbound references, and never reconstructs or validates a
  network pack in the period loop.

## Output correction

The unconditional staged-market JSONL writer and all calls to it are removed.
Successful periods no longer create one solver-diagnostics JSON file each.
The existing first-failure evidence remains until Prompt 121 replaces it with
the approved atomic bundle. SQLite remains the current staged evidence path;
Prompt 120 owns the v8 transaction and ledger-field migration.

## Focused evidence

The Prompt 119 RED observed the production defect directly:

```text
validate.call_count: 50 != 1
AnnualModelOrchestratorV2.__init__: unexpected run_context
v1 period domain: missing run_context_ref
```

The focused Prompt 119 GREEN covers 48 compact v2 payloads, one validation,
strictly typed current-period ahead results, two-year immutable context
transition and wrong/unbound reference refusal. The Prompt 101 staged/CEM
integration regression passes 18/18. Prompt 99's affected solver and lifecycle
assertions pass; its one pre-existing Prompt 96 `period-bound-noise.json`
source-hash mismatch remains deliberately unchanged.

No full suite, annual execution or ten-year execution is part of this Prompt.
