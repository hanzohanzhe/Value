# Scheme C preservation and parity test levels

Use the retained Python 3.10 environment from the repository root.

## Level 0 - source, contracts and storage economics

```powershell
py -3.10 -m unittest discover -s tests -p "test_*.py" -v
```

This protects retained source/data hashes, public contracts, module resolution,
parameter validation, dynamic storage cost recovery, planning/market ledgers,
provenance and run-bundle validation. It is necessary but is not full numerical
parity evidence.

## Level 1 - two-period wiring

```powershell
py -3.10 -m unittest discover -s tests -p "test_application_service.py" -v
```

Every selected module must run once; the v2 contracts, planning ledger, market
ledger, stage parity report and provenance bundle must validate. Annual economic
indicators from this short run are deliberately not published.

## Level 2 - full 2025 application run

```powershell
py -3.10 -m backend.model_runner `
  --project scheme-c-one-year-full-test `
  --run release-one-year `
  --mode full
```

The run must complete 17,520 periods, pass stage parity and planning
reconciliation, preserve the retained 2025 metrics and expose any raw market
compatibility adjustments.

## Level 3 - full 2025-2026 transition

```powershell
py -3.10 -m backend.model_runner `
  --project scheme-c-ten-year-full-test `
  --run release-two-year `
  --mode two_year
```

This is the release gate. It requires two full PSM years, the intervening
investment/planning transition, stage-by-stage parity, next-year fleet and
pipeline reconciliation, retained numerical comparison and a valid provenance
bundle. Historical fixtures and runs are never regenerated.
