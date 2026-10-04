# Staged copperplate market modules

FORCE now includes a replaceable two-stage national market path. It is an
optional model choice; the retained Scheme C reproduction path is unchanged.

Select these modules together in a Study:

```json
{
  "psm": "force-staged-bid-at-cost-psm",
  "balancing": "force-copperplate-balancing",
  "storage_cost": "dynamic-annual-storage-cost"
}
```

The PSM freezes a forecast-only `AheadMarketInput`, clears a national
bid-at-cost schedule and writes its hash. Only then does the balancing module
receive realised demand, current-period availability, signed flexibility bids
and opening SOC. The balancing result links both the ahead hash and its own
input hash. Calling the same balancing input twice is rejected.

## Physical and settlement rules

- The national schedule is pay-as-clear.
- Current-period balancing is pay-as-bid.
- Scheduled generation retains its national settlement. Balancing adjustments
  are separate signed cashflows.
- Final dispatch, not scheduled dispatch, changes storage SOC and annual sold
  MWh.
- Positive interconnector profiles are import envelopes. Negative profiles are
  export envelopes and cannot reverse direction in that period.
- Blackout energy is balanced at the Study's VOLL.
- Final physical resource cost uses final dispatch and is not the same ledger
  as market settlement.

The authoritative period stream is `market/staged-market.jsonl`. Each period
contains, in order, `AheadMarketInput`, `AheadMarketResult`, `BalancingInput`
and `BalancingResult`. The annual hash index is
`market/staged-market-year-<year>.json`.

## Compatibility boundary

Scheme-C-derived CSV demand and interconnector rows are legacy power values in
MW. The typed PSM contract uses MWh per period. The canonical adapter performs
the single `MW × period_hours` conversion and records
`force.scheme-c-source-power-to-energy/v1` in chronology evidence. The retained
kernel still reads its unchanged files and performs the same conversion inside
its compatibility boundary.

Prompt 95 verifies exact thermal-only dispatch and operating-cost parity against
the live monolithic module on the same Castle pack, plus hand-calculated VRE,
storage, import/export, forecast-error and 24-hour convex fixtures. This is not
a claim that the new staged module reproduces every legacy Scheme C heuristic.
Full doctoral-result reproduction continues to use `scheme-c-psm`; staged and
future zonal balancing have separate module identities and result provenance.

