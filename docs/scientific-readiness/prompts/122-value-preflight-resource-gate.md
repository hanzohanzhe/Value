# Prompt 122 — selected-graph resource estimate and hard disk gate

## Scope

Prompt 122 protects only the staged bid-at-cost plus balancing/zonal output
path. It does not alter offers, redispatch optimisation, solver settings,
dispatch, settlement, storage SOC, curtailment, CEM, annual transitions, other
PSMs or frontend structure. The requested trace profile remains immutable: a
Full market replay request is either accepted as full or refused as full.

## Selected-graph estimate

`gridform_core.preflight_resources` derives row maxima from the immutable
selected run/year estimate contexts:

- zones and boundaries/cutsets come from the selected signed network graph;
- assets, storage and resource classes come from the frozen opening state;
- years and periods come from the selected run policy;
- expansion headroom is additive to the observed opening cardinality;
- summary/common and full-only v8 row families are counted separately.

There is no 14-zone, 20-boundary or 50-order pack assumption. The canonical
run context is counted once, each annual context is counted once per model
year, and their JSON byte lengths are measured exactly. Persisted output adds
annual artifacts and calibrated per-period bytes, then applies a 1.5 safety
multiplier. Temporary space is explicit and separate. The reserve is the
larger of 10 GiB or 5% of the target volume capacity.

## Isolated calibration and cache

`ResourceCalibrationKey` binds data/network, selected module graph, solver,
clock and exact trace fingerprints. A matching valid cache stores persisted
bytes, temporary bytes and runtime seconds per period. Invalid, stale or
mismatched entries are ignored and recalibrated under a key-scoped exclusive
publication lock.

A cache miss measures at most 48 periods in a unique temporary root. The
opening YearContext is deep-cloned; the request receives a private RNG and a
temporary ledger path. It explicitly disallows Run publication, checkpoints
and CEM transition. The estimator never reads or advances an official RNG and
never writes to the selected output root. The fallback measures an isolated
v8-shaped SQLite persistence sample; an application executor can use the same
bounded callback contract for selected module/solver timing without widening
the published state boundary.

## Hard gate and reservation

The decision requires the configured per-run/global quota and current free
space to cover persisted output, temporary output and reserve. Refusal uses
`VALUE_PREFLIGHT_DISK_SPACE` and offers exactly:

1. Choose Summary.
2. Move output root.
3. Free space.

The existing `RunQuotaPolicy` and `reserve_run_space` remain authoritative.
Reservation calculation and publication are serialized by an exclusive lock,
so concurrent workers cannot both consume the same quota headroom.

## Frozen readiness identity

Before queue acceptance, the server freezes the estimate, exact trace,
estimate-context hashes, calibration key/basis, free-space observation, actual
quota reservation decision and selected output root beside the immutable
input snapshot. The resource artifact SHA-256 enters the snapshot identity.

Immediately before `run_project_application`, the model worker rereads and
verifies the frozen resource artifact, its hash, trace, selected output root
and both estimate-context identities. Missing or changed staged/zonal evidence
fails closed before model execution.

## Focused evidence

The Prompt122 RED first failed because `gridform_core.preflight_resources` did
not exist. The focused GREEN tests cover a 3-zone and a larger graph, summary
versus full row cardinalities, one context copy, the 1.5 multiplier, the
10-GiB/5% reserve, cache-key mismatch, isolated 48-period calibration, official
state/RNG/output-root non-mutation, exact disk refusal and remedies,
reservation competition, and frozen trace/context/output-root mismatch.

Only these tests belong to this Prompt:

```powershell
python -m unittest discover -s tests -p "test_prompt122_preflight_resource_gate.py" -v
python -m unittest discover -s tests -p "test_preflight.py" -v
```

No full suite, annual run or ten-year run is authorised here.
