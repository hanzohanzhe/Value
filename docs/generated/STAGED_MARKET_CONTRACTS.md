# Staged market module contracts

Contract family: `force.staged-market-contracts/v1`

This reference describes the public boundary between a national ahead-market
PSM and a replaceable current-period balancing module. The machine-readable
authority is `gridform_core/data/contracts/staged-market-v1.schema.json`.

## Composition rule

A PSM that provides `market.ahead-schedule/v1` must be paired with exactly one
module in slot `balancing`. That module must use contract
`force.balancing-module/v1`, provide `market.balancing/v1`, and implement:

```python
def clear(model_input: BalancingInput) -> BalancingResult:
    ...
```

Existing monolithic PSMs do not select a balancing module. Their saved project
payloads, graph hashes and execution path remain unchanged.

## Public contracts

| Type | Schema identity | Purpose |
| --- | --- | --- |
| `AheadMarketInput` | `force.ahead-market-input/v1` | Forecast-only demand, offers and opening storage state for one period |
| `AheadMarketResult` | `force.ahead-market-result/v1` | Immutable national schedule, clearing price, settlement quantity and scheduled storage action |
| `FlexibilityBid` | `force.flexibility-bid/v1` | Signed up/down balancing offer with price, volume, physical cost and provenance |
| `BalancingInput` | `force.balancing-input/v1` | Ahead-result hash plus realised demand, availability, SOC, bids, period length and VOLL |
| `BalancingResult` | `force.balancing-result/v1` | Balancing-input hash, accepted adjustments, final dispatch/SOC, curtailment, blackout, cashflows, resource costs and residual |
| `StagedMarketYearResult` | `force.staged-market-year-result/v1` | Per-period ahead and balancing hashes plus selected module identities |

`AcceptedAdjustment` is a typed record nested inside `BalancingResult`; it is
not a separately versioned top-level contract.

## Information boundary

Ahead inputs and results must use `information_scope="forecast_only"`. Realised
demand, realised availability and final dispatch are rejected at this stage.
Balancing receives those realised fields only after the ahead result is frozen
and linked by `ahead_result_sha256`.
Each balancing result also records `source_input_sha256`, so realised inputs and
bids are part of replay identity.

## Bid and settlement signs

- `direction` is `up` or `down`.
- `available_mw` is strictly positive.
- Bid prices may be finite positive, zero or negative.
- Each `bid_id` is unique within a balancing input and belongs to its period.
- An accepted adjustment records a signed MWh delta.
- `cashflow_to_agent_gbp = accepted_delta_mwh × bid_price_gbp_per_mwh`.

## Replay identity

Contract hashes use UTF-8 canonical JSON with sorted keys and no non-finite
numbers. Staged project snapshots and annual checkpoints contain both the PSM
and balancing identities. Changing either module therefore creates a different
scientific run identity; a monolithic run contains no synthetic balancing slot.

## External module manifest

```json
{
  "slot": "balancing",
  "contract_version": "force.balancing-module/v1",
  "provides_capabilities": ["market.balancing/v1"],
  "implementation": "your_package.module:YourBalancingModule"
}
```

The normal FORCE `module.zip` installer checks that the implementation exposes
a callable `clear` method. Network-specific inputs belong in the typed
`domain_payload`; the generic balancing contract remains unchanged.
