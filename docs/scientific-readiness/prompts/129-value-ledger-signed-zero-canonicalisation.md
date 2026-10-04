# Prompt 129 — VALUE ledger signed-zero canonicalisation

## Diagnosis

A one-period full-trace capture found exactly two writer/SQLite differences:
`OrderLedgerRow.offer_price_gbp_per_mwh` and
`RedispatchSettlementRow.bid_price_gbp_per_mwh` were `-0.0` before persistence
and `0.0` after SQLite reconstruction. IEEE signed zeroes are numerically equal,
but canonical JSON preserves their spelling and therefore produced different
evidence hashes. No physical, economic or solver result differed.

## Goal

Normalise only signed floating-point zero at the Ledger v8 canonicalisation
boundary so a full-trace ledger validates after SQLite round-trip.

## Locked scope

- Change only shared market-ledger numeric canonicalisation and focused tests.
- Convert a float-contract value equal to zero to canonical positive `0.0`.
- Do not round, clip or apply tolerance to any non-zero value. In particular,
  preserve negative bids such as `-0.000001` exactly.
- Do not change schemas, PSM, bid construction, zonal LP, SOC, CEM, data or
  scientific results.
- Preserve retained failed evidence; generate fresh Prompt 127 attempts after
  the focused repair passes.

## Acceptance checks

1. Writer `-0.0` and SQLite `0.0` produce identical evidence projections.
2. A fresh one-period and 48-period full-trace v8 ledger validates.
3. `-0.000001` remains negative and distinct from zero.
4. Existing strict integer, boolean, nullable-float and tamper regressions pass.
