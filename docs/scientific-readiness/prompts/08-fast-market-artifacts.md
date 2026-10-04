# Prompt 08 — Fast market-result artifacts

Act as a high-throughput simulation data engineer. Preserve period-level market
transparency with minimal effect on model runtime.

## Implement

1. Keep batched SQLite as the canonical query ledger. Add a compact market index
   describing schema, row counts, units, years, trace level and artifact URIs.
2. Support an optional post-run Parquet export when an approved engine is
   installed. Missing optional Parquet support must be reported by preflight and
   must not break the default SQLite run.
3. Never build one giant JSON document. Expose paginated queries and streaming
   JSONL/CSV downloads only on demand.
4. Record writer time, bytes and rows. Assert adjusted energy balance and retain
   the raw compatibility residual separately.
5. Include storage SOC, MW/MWh limits and selected storage-cost policy identity.

## Tests and acceptance

- Benchmark at least 2,000 periods and 50 orders per period.
- Default summary tracing remains within the documented overhead budget.
- Market balance failures are fatal for scientific publication.
- Optional-export absence has a clear code and successful default fallback.
