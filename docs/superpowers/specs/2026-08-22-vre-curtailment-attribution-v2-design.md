# VRE Curtailment Attribution v2 Design

**Date:** 22 August 2026  
**Status:** Approved design; implementation not started  
**Scope:** FORCE optional lossless zonal redispatch path  
**Supersedes:** the non-negative VRE curtailment identity in `force.zonal-period-accounting/v1`  
**Protected boundary:** retained PhD Scheme C source and compatibility runtime remain unchanged

## 1. Purpose

The current zonal accounting assumes that the network can only add VRE
curtailment. A real 2025 period disproved that assumption: realised-demand
copperplate balancing used 4,740.50 MWh of VRE, while the zonal redispatch used
all 6,434.281237573224 MWh available. Redispatch therefore avoided
1,693.7812375732246 MWh of curtailment and final curtailment was zero.

This design replaces the old non-negative identity with a controlled,
counterfactual attribution that allows forecast/scheduling and redispatch to
either add or avoid curtailment. It also makes the result reusable by conforming
third-party PSM and redispatch modules, auditable in SQLite, and understandable
in the Network & redispatch frontend without overloading the main Run screen.

## 2. Approved scientific definition

For each period let:

- `A_r` be realised available wind and solar energy;
- `G_PF` be VRE used by perfect-forecast copperplate clearing;
- `G_CP` be VRE used by the forecast-schedule plus realised copperplate case;
- `G_Z` be VRE used after zonal redispatch.

The authoritative identity is:

```text
A_r - G_Z = (A_r - G_PF) + (G_PF - G_CP) + (G_CP - G_Z)
```

The public decomposition is:

```text
final VRE curtailment
  = economic curtailment
  + forecast-added curtailment
  - forecast-avoided curtailment
  + redispatch-added curtailment
  - redispatch-avoided curtailment
```

`Forecast & scheduling impact` replaces the unsupported label `realised
availability change`. FORCE does not currently have an independent forecast-VRE
availability counterfactual with which to identify weather forecast error on
its own. A later module may add that counterfactual under a separate versioned
contract; this design must not infer it.

`Redispatch impact` is the public name for the difference between matched
realised copperplate balancing and final zonal redispatch. It is not described
as a pure physical-network effect because the transition includes the
participants' redispatch response.

## 3. Physical scope

Formal VRE curtailment covers:

- Solar;
- Onshore wind;
- Offshore wind;
- their sum, Total VRE.

VRE accepted for demand, storage charging, export, cross-zone delivery or
effective demand-side response is used energy and is not curtailment. Run-of-
river hydro spillage, reservoir spillage, unused imports, storage losses,
network losses and load shedding remain separate physical accounts.

Avoided curtailment is subtracted only in the physical curtailment identity.
It is not subtracted again from system resource cost. System cost continues to
use the matched physical-cost comparison between Case 3 and Case 2. No default
GBP value is assigned to avoided curtailment. A future replaceable valuation
module may consume the physical MWh result without changing the authoritative
cost ledger.

## 4. Architecture

### 4.1 Selected approach

Implement an independent attribution component rather than extending the
inline arithmetic in the copied staged PSM. The component has one purpose: turn
matched VRE counterfactual snapshots into validated physical attribution rows.

Suggested module:

```text
gridform_core/vre_curtailment_attribution.py
```

The modular staged PSM remains responsible for running the three existing
counterfactuals. Its integration change is a thin adapter that constructs a
snapshot and calls the attribution component. The attribution component does
not import Scheme C agents, the zonal solver, the CEM, or frontend code.

### 4.2 Data flow

```text
perfect-forecast copperplate clear
realised copperplate clear
zonal redispatch clear
            |
            v
force.vre-counterfactual-snapshot/v1
            |
            v
deterministic copperplate reference allocation
            |
            v
force.vre-curtailment-attribution/v2
            |
            +--> gridform.market-ledger/v6
            +--> annual JSON read model
            +--> failure evidence when invalid
```

The retained PhD Scheme C source and compatibility runtime are outside this
flow and remain protected by the existing hash tests.

## 5. Counterfactual snapshot contract

`force.vre-counterfactual-snapshot/v1` contains one row per VRE dispatch object
and bid tranche:

```text
run_id
year
period
period_id
asset_id
owner_id
canonical_technology
zone_id
bid_tranche_id
realised_available_vre_mwh
perfect_forecast_copperplate_dispatch_mwh
realised_copperplate_dispatch_mwh
zonal_final_dispatch_mwh
realised_input_sha256
```

The object set and stable identifiers must match across all three cases. A
module-provided `bid_tranche_id` is preferred. The built-in bid-at-cost adapter
derives a deterministic tranche identity from the canonical technology and
declared offer basis; it must not use solver row order or a floating-point
display string.

The resolved execution graph declares
`evidence.vre-counterfactual-snapshot/v1` only when all required PSM and
balancing components can produce the contract. The platform must not claim the
capability merely because a final zonal dispatch exists.

## 6. Deterministic reference allocation

Copperplate dispatch can contain economically equivalent allocations between
identical zero-cost VRE objects. Raw asset-level solver allocation is therefore
not a scientifically stable regional counterfactual.

For each period and each group defined by canonical technology and
`bid_tranche_id`, define:

```text
w_i = realised_available_vre_mwh_i / group_realised_available_vre_mwh
```

Allocate the aggregate perfect-forecast and realised-copperplate VRE accepted
within that group in proportion to `w_i`. If group availability and group
dispatch are both zero, every reference allocation is zero. Positive group
dispatch with zero availability is invalid.

The zonal final dispatch is never redistributed. It remains the physical
solver result. The detailed evidence is reconstructed per executable dispatch
object, then aggregated by zone, technology, period, year and national total.

National final curtailment and national net redispatch impact are direct
counterfactual quantities. Zone and technology added/avoided results are
reproducible attributions under this published reference rule and must be
labelled accordingly.

## 7. Attribution algorithm

For each detailed row after reference allocation:

```text
economic = realised_available - perfect_reference_dispatch
forecast_delta = perfect_reference_dispatch - copperplate_reference_dispatch
redispatch_delta = copperplate_reference_dispatch - zonal_final_dispatch

forecast_added = max(forecast_delta, 0)
forecast_avoided = max(-forecast_delta, 0)
redispatch_added = max(redispatch_delta, 0)
redispatch_avoided = max(-redispatch_delta, 0)

total = realised_available - zonal_final_dispatch
redispatch_net = redispatch_added - redispatch_avoided
```

The annual totals separately sum gross added and gross avoided quantities. They
must not be netted by period or zone before aggregation. Annual curtailment rate
is energy weighted:

```text
sum(total_curtailment_mwh) / sum(realised_available_vre_mwh)
```

It is not the simple mean of half-hour curtailment rates.

## 8. Validation and numerical treatment

The period tolerance is:

```text
max(1e-7 MWh, 1e-10 * max(period_realised_available_vre_mwh, 1 MWh))
```

Validation occurs in this order:

1. preserve the raw snapshot and raw residual;
2. reject NaN, infinite values, identifier mismatches and material negative
   quantities;
3. verify the three cases have the same object/tranche set and matched realised
   input identity;
4. verify copperplate group dispatch and zonal object dispatch do not exceed
   realised availability outside tolerance;
5. clamp only tolerance-sized negative or boundary overshoots;
6. calculate detailed and aggregate attribution;
7. verify group, period and annual identities.

The authoritative residual is:

```text
economic
+ forecast_added - forecast_avoided
+ redispatch_added - redispatch_avoided
- total
```

An invariant failure prevents zonal accounting from being published. It does
not invalidate a separately completed copperplate run and does not transform
the failed zonal run into copperplate mode.

Error codes include:

```text
GF_VRE_ATTRIBUTION_IDENTITY_FAILED
GF_VRE_COUNTERFACTUAL_SET_MISMATCH
GF_VRE_DISPATCH_EXCEEDS_AVAILABILITY
GF_VRE_ATTRIBUTION_CAPABILITY_MISSING
```

Invariant failures save
`market/failures/vre-curtailment-attribution-<input-sha256>.json` with the raw
snapshot, reference groups, normalized values, residual, tolerance and module
identity. Capability missing is handled differently: a user-selected
experimental module that never claimed the capability may complete with
attribution unavailable; a built-in module that claims the capability but
fails to provide it violates its contract and fails the run.

## 9. Ledger v6 and compatibility

New runs use `gridform.market-ledger/v6`. Curtailment has two authoritative
tables; zonal cost and reliability accounting remains a separate period table.

### 9.1 `vre_curtailment_period`

Stores period identities, four dispatch totals, economic/forecast/redispatch
components, final curtailment, curtailment rate, residual, tolerance, status,
input hash and attribution method ID.

### 9.2 `vre_curtailment_detail`

Uses `(year, period, asset_id, bid_tranche_id)` as its primary key and stores
object identity, zone, canonical technology, realised availability, the two
copperplate reference dispatches, zonal final dispatch, every attribution
component and evidence level.

### 9.3 Decoupling from the v5 table

The v5 `zonal_period_summary` table combines cost/reliability fields with the
obsolete non-negative curtailment fields. v6 does not write invented values
into those columns. It adds a new cost and reliability period table,
`zonal_period_accounting`, and the two attribution tables above. The v6 read
adapter uses the new tables; the v5 read adapter continues to use
`zonal_period_summary`.

Completed v4/v5 ledgers remain read-only. Reading them must not migrate or
rewrite the SQLite file. Their curtailment capability is `legacy_partial`;
redispatch-avoided fields are `null` with an explicit reason, never zero.
An interrupted pre-v6 run cannot resume writes into the same run ID under v6.
It must create a new run from a portable checkpoint so one evidence database
never mixes scientific definitions.

## 10. Run-level evidence

Each v6 zonal run writes a compact audit artifact at:

```text
model-output/network/vre-curtailment-attribution.json
```

It records contract and method versions, reference allocation rule, data/input
hashes, module versions, capability status, matched-counterfactual proof,
maximum residual and period, tolerance, annual totals, and the SQLite detail
location. Failure evidence remains separate from ordinary frontend payloads.

## 11. API and exports

Keep the existing Network & redispatch API and add version-aware views:

```text
GET /api/runs/{run_id}/network-redispatch/annual
GET /api/runs/{run_id}/network-redispatch/curtailment
GET /api/runs/{run_id}/network-redispatch/curtailment-detail
```

Detailed views are paginated and accept bounded filters for year, period, zone,
technology, asset and bid tranche. Annual JSON is a compact read model and does
not contain detailed rows. CSV exports the current bounded selection. SQLite is
the complete audit store. Existing JSONL export remains a compatibility path,
not the primary novice workflow.

Cross-run curtailment deltas are enabled only when attribution contract/method,
data pack, network pack, period set, realised input identity, initial state and
counterfactual capability match. Otherwise the runs may be shown side by side,
but deltas are `null` with a reason code.

## 12. Frontend

The Run page shows only:

- final VRE curtailment;
- VRE curtailment rate;
- redispatch net impact.

The dedicated Network & redispatch page replaces the obsolete four-card
curtailment block with final, economic, forecast added/avoided and redispatch
added/avoided/net values. An accessible waterfall shows additions upward and
avoidance downward, with signs and text labels as well as color. It supports
Total VRE, Solar, Onshore wind and Offshore wind. A zone-by-technology table
shows the attributed regional detail.

Inspect exposes the three dispatch cases, deterministic reference allocation,
method/evidence status, residual and tolerance. React never reconstructs or
repairs the scientific identity. Legacy and unsupported states are displayed
as unavailable, not converted by a numeric default to zero.

## 13. Third-party modules

A conforming execution graph provides
`evidence.vre-counterfactual-snapshot/v1`; the platform validator then provides
`results.vre-curtailment-attribution/v2`. The manifest, SDK examples and module
developer guide document required identifiers, units, counterfactual matching
and conformance fixtures.

Experimental modules without the snapshot capability may run, but the result
contains:

```json
{
  "attribution_status": "unavailable",
  "reason_code": "module_does_not_provide_counterfactual_snapshot"
}
```

The platform must not guess attribution from partial third-party output.

## 14. Test and rollout gates

Implementation follows test-driven development and proceeds only when the
previous gate passes.

1. Unit and property tests for added, avoided, simultaneous regional effects,
   reference allocation, solver-order invariance, technology totals, absorption
   by storage/export/DSR, tolerance and broken constraints.
2. v6 write/read, v5 read-only compatibility, mixed-schema resume refusal,
   capability and JSON/CSV/SQLite reconciliation tests.
3. Frontend tests for waterfall signs, filters, legacy/unavailable/failed states,
   missing-value handling, lint and production build.
4. Two-period deterministic smoke, including the previously failing period.
5. 24-hour and 168-hour sequences, independent LP comparisons, deterministic
   random convex cases and constraint mutation failures.
6. Complete 17,520-period 2025 copperplate companion verification.
7. Complete 17,520-period 2025 zonal run.
8. 2025-2026 PSM-CEM test proving next-year asset, zone, tranche, SOC and cashflow
   transition.
9. Only after all earlier gates pass, resume the matched ten-year Prompt 105
   comparisons.

Annual acceptance requires all periods, matched input identities, reconciled
cost/settlement/reliability/curtailment ledgers, SQLite integrity, consistent
JSON/CSV/SQL totals, valid comparison eligibility and unchanged retained Scheme
C hashes.

SQLite writes remain batched. The frontend never loads annual detail eagerly.
Writer time, database growth and query time are reported. No GIS, Parquet or
chart dependency is introduced by this change.

## 15. Non-goals

This work does not change:

- network physics, corridors or boundary limits;
- the redispatch objective or bid-at-cost method;
- CEM investment or commissioning;
- storage pricing or SOC semantics;
- settlement and system-cost definitions;
- hydro, interconnector or DSR behavior;
- transmission expansion;
- the retained PhD Scheme C source.

## 16. Completion definition

The change is complete only when the new contract is documented, independently
tested, visible in the frontend, auditable in v6 SQLite, truthful for v5 and
unsupported modules, and the real annual zonal run passes the period that
exposed the original defect. A short smoke result alone is not completion.
