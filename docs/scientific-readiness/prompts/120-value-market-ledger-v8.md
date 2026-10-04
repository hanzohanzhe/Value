# Prompt 120 — authoritative VALUE market-ledger v8

## Scope

Prompt 120 makes SQLite `value.market-ledger/v8` the sole authoritative
period-evidence store for the staged bid-at-cost plus balancing/zonal path
that produced the repeated annual network payload. It changes persistence,
trace coverage and integrity sealing only. The simple bid-at-cost,
perfect-foresight LP and reference DC-OPF paths remain on their pre-Prompt-120
behaviour. Bid construction, clearing, zonal redispatch, settlement, storage
SOC, curtailment attribution, CEM and annual transition order are unchanged.

## Period transaction

`MarketPeriodBatch` carries one `PeriodLedgerRow`, the compact common summary
projection, optional full-replay detail and the two canonical integrity
payloads. `SQLiteMarketLedger.record_period_batch` begins with
`BEGIN IMMEDIATE`, writes every row and both rolling roots, and commits once.
Any exception rolls the whole period back; neither a table row nor root state
survives.

Periods append from zero in strict contiguous order. A completed year rejects
further rows, and reopening a v8 database must match its immutable trace and
semantic metadata. The validator reconstructs the fixed projection from the
stored rows and checks every previous/root adjacency rather than trusting only
the last period.

The v8 common projection adds `dispatch_summary`, `storage_summary` and
`redispatch_summary`. `context_registry`, `period_integrity` and
`year_integrity` retain context identities, rolling roots, row counts and
trace coverage. Summary and full write the same common projection. Only full
writes orders, clearing payloads, asset/storage detail, redispatch settlement,
curtailment detail and locked solver-phase rows.

The versioned common/full table sets are disjoint and enforced both when a
batch is constructed and immediately before it is written. Callers cannot add
trace-dependent fields to the science projection. Redispatch summary cost is
the signed accepted physical resource-cost delta, not settlement cashflow; it
reconciles with the ahead and blackout components to the zonal accounting
resource-cost total.

## Integrity and finalisation

`gridform_core.market_integrity` canonicalises sorted JSON with
`allow_nan=False` and advances separate SHA-256 science and evidence chains.
The science seed binds run/year contexts; the evidence seed additionally binds
the resolved trace profile. Consequently identical summary/full science has
the same annual science root while different stored trace coverage has a
different evidence root.

Observed reliability events are inserted and sealed as annual evidence in one
transaction. Changing an event changes the evidence root; a failed annual seal
rolls the event rows and completion state back together.

Annual metadata and bundle manifests retain context hashes, annual roots, row
counts and trace coverage. SQLite and other final artifacts are hashed by
streaming chunks after close; live finalisation does not read a complete
database or JSONL stream into memory. New staged runs do not create
`market/staged-market.jsonl`.

All portable bundle profiles, including `compact_results`, retain the
authoritative v8 SQLite database, metadata, index and referenced run/year
contexts.

## Compatibility and evidence

Ledgers v4 through v7 remain queryable through read-only connections and are
never migrated or rewritten in place. Attempting to open any legacy ledger as
a writer fails closed.

The required focused RED first failed because v8 batch contracts did not
exist. Review counterexamples additionally failed for non-contiguous append,
sealed-year mutation, trace relabelling, chain/projection tampering,
chain-external reliability rows, table-role injection, compact bundle omission
and settlement-cashflow aggregation. The GREEN checks cover those cases plus
paired summary/full roots, transaction rollback, no new staged JSONL and
byte-identical v4-v7 fixtures before and after validation and query.

No full suite, annual run or ten-year run belongs to this Prompt.
