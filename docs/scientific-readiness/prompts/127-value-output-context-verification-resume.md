# Prompt 127 — resume bounded VALUE output/context verification

## Goal

Resume the interrupted Prompt 125 verification from fresh output roots after
Prompt 126 passes. Preserve the original failed Prompt 125 report and evidence
as the historical diagnosis.

## Execution order

1. Run a fresh 48-period zonal summary fixture and require a valid v8 ledger.
2. Confirm its literal physical regression: 48 MWh demand, 48 MWh accepted
   supply, £480 physical resource cost, £480 market payment, zero blackout,
   zero curtailment, zero storage charge/discharge and zero maximum absolute
   energy-balance residual.
3. Run the 336-period bounded-growth fixture only after step 1 passes.
4. Run two-year state coupling only after step 3 passes.
5. Run summary/full trace science-equivalence only after step 4 passes.
6. Run first-failure and preflight-refusal checks only after step 5 passes.
7. Generate new Prompt 127 Markdown and JSON reports. Do not overwrite Prompt
   125 reports.

## Locked scope

- Use one numerical thread and fresh Prompt 127 evidence roots.
- Do not start a one-year, two-full-year or ten-year production study.
- Do not restart the stopped VALUE-UK runs.
- Do not accept a percentage tolerance for hashes or integrity chains.
- Set `ten_year_restart_authorised=true` only if every bounded gate passes.

## Acceptance checks

- All nine Prompt 125 evidence gates pass from fresh evidence.
- The 48-period literal physical regression passes exactly within the existing
  energy-balance numerical tolerance.
- The retained Prompt 125 report still records its original failure.
- Prompt 127 reports contain exact evidence paths, hashes, byte counts and
  elapsed times.
