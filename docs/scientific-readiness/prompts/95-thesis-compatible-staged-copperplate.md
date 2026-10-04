# Prompt 95 — Thesis-compatible staged copperplate implementation

Execute after Prompt 94. Read the copied runtime-compatible Scheme C market
functions, `scheme_c_native_psm.py`, market ledger v4, Prompt 35–37 clearing
evidence and retained hash manifest. Act as PSM refactoring lead. Copy and adapt;
never edit retained Scheme C.

## Objective

Implement the new staged contract with a national bid-at-cost ahead module and a
thesis-compatible copperplate balancing module. Prove that staging alone does not
change accepted copperplate results.

## Required modules

Register:

- `force-staged-bid-at-cost-psm` version `1.0.0`, slot `psm`, providing
  `market.ahead-schedule/v1` and requiring `market.balancing/v1`;
- `force-copperplate-balancing` version `1.0.0`, slot `balancing`, providing
  `market.balancing/v1` and `domain.single_node`.

The ahead module must expose the exact declared offers and schedule before any
realised demand, curtailment or balancing action. The balancing implementation
must consume that artifact, not recompute an unrecorded schedule. Final dispatch,
actual SOC, market income and storage sold MWh must reconcile to the existing
authoritative result boundary.

## Parity evidence

Use the same pack, period selection, storage policy and seed to compare the
monolithic accepted path with the staged copperplate path for:

- one hand-calculated period;
- the two-period smoke chronology;
- a 24-hour deterministic fixture;
- signed interconnector import and export periods;
- charge, idle and discharge storage states;
- forecast surplus and deficit.

Require exact discrete identities and numeric equality within `1e-9` relative or
`1e-8 MWh` absolute for energy. Any allowed retained compatibility adjustment
must be identical and separately visible. Do not broaden parity to the Prompt 68
perfect-foresight PSM.

## Tests and failure cases

Write failing tests before implementation for ahead-stage information leakage,
mutated ahead hash, double balancing, scheduled rather than actual SOC update,
and stale module identity. Invocation evidence must prove both selected modules
executed in the live application path.

## Stop conditions

Stop on unexplained parity difference, retained-source hash change, duplicate
settlement or any need to call a private historical replay as production.

## Deliverables

- registered staged PSM and copperplate balancing modules;
- exact declared stage artifacts;
- parity/mutation report and machine evidence;
- unchanged old Study results.
