# Prompt 94 — Staged national-market and balancing contract family

Execute after Prompt 93. Read `gridform_core/v2/contracts.py`,
`gridform_core/v2/module_manifest.py`, `gridform_core/module_registry.py`,
`gridform_core/clearing_inputs.py`, Prompt 35 declared inputs and Prompt 65
extension rules. Act as a market-contract architect. Add contracts and fixtures
only; do not copy Scheme C logic or implement redispatch.

## Objective

Define a public national ahead-market result and replaceable balancing interface
while leaving every existing monolithic `psm` Study unchanged.

## Contracts

Add immutable JSON contracts with these literal identities:

- `force.ahead-market-input/v1`;
- `force.ahead-market-result/v1`;
- `force.flexibility-bid/v1`;
- `force.balancing-input/v1`;
- `force.balancing-result/v1`;
- `force.staged-market-year-result/v1`.

The ahead result contains run/year/period identity, information scope, national
schedule by asset, clearing price, accepted volume, settlement quantity, storage
scheduled action and source input hash. It contains no realised information.

`FlexibilityBid` contains `bid_id`, `agent_id`, `asset_id`, `technology`,
`zone_id`, `period_id`, `direction`, `available_mw`, `price_gbp_per_mwh`,
`baseline_mw`, `physical_cost_gbp_per_mwh`, `network_effect_id`, provenance and
units. Direction is `up` or `down`; price may be finite positive, zero or
negative. Reject duplicate IDs, non-finite values and unavailable volume.

The balancing input contains the ahead-result hash, realised demand/availability,
initial SOC, signed bids, period hours, VOLL and an optional typed domain payload.
The result contains accepted signed deltas, final physical dispatch, actual
storage state, curtailment classes, blackout, settlement cashflows, resource
costs, residuals and artifact references.

## Registry behaviour

1. Add optional module slot `balancing` with contract
   `force.balancing-module/v1` and capability `market.balancing/v1`.
2. A staged PSM explicitly requires one balancing provider. A monolithic PSM
   neither selects nor silently receives this slot.
3. Project revisions, graph hashes, snapshots, checkpoints, module bundles and
   comparison identities include the balancing module only for staged Studies.
4. An old project with no `balancing` field retains its current graph hash and
   execution path.

## TDD acceptance

Write contract/registry tests first for canonical round trips, signed prices,
hash linkage, missing providers, two providers, wrong capability, old project
migration, snapshot/resume identity and undeclared realised information. Observe
each intended failure before implementation.

## Stop conditions

Stop if this requires editing retained Scheme C, making `balancing` mandatory for
old Studies, adding a second registry or weakening immutable input hashes.

## Deliverables

- staged-market dataclasses/protocols and schema fixtures;
- conditional balancing slot and one-registry negotiation;
- migration/snapshot/conformance tests;
- generated bilingual module-contract reference.
