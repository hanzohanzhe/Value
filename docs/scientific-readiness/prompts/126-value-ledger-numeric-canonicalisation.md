# Prompt 126 — schema-aware VALUE ledger numeric canonicalisation

## Goal

Repair the `value.market-ledger/v8` integrity mismatch caused solely by Python
integer zeroes being persisted and reconstructed as SQLite `REAL` values. The
repair must make the writer projection and validator reconstruction use the
same row-contract types without changing any scientific value or solver path.

## Locked scope

- Change only ledger projection canonicalisation and its focused tests.
- Keep `year`, `period` and other integer-typed contract fields as integers.
- Canonicalise every float-typed field to a finite Python `float` before
  science/evidence hashing, both from dataclass rows and SQLite rows.
- Do not round values. `0` and `0.0` are equivalent in float fields, while
  `0.0` and `0.000001` remain different.
- Keep `value.market-ledger/v8` and the current science-projection schema IDs.
- Do not modify the PSM, staged bidding, zonal LP, SOC, CEM, data packs or model
  results.
- Do not migrate or rewrite the retained Prompt 125 failure evidence.

## Acceptance checks

1. A fresh v8 ledger whose float-typed source fields contain integer zeroes
   validates without projection, chain or annual-root errors.
2. The stored writer projection hash equals the projection reconstructed from
   SQLite.
3. Integer identity fields remain JSON integers.
4. A post-seal change from `0.0` to `0.000001` still fails integrity validation.
5. Existing focused v8 integrity and market-ledger regressions remain green.
