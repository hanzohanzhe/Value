# Prompt 51 — Post-closure targeted verification

Execute only after Prompts 47–50 are implemented.

## Objective

Use short deterministic tests to determine whether the newly identified defects
are closed before spending hours on annual or ten-year reruns.

## Ordered gates

1. Run investment ownership, aggregate headroom, hydro eligibility and planning
   preprocessing unit fixtures.
2. Run planning-index, parameter, cost-ledger, module-manifest, retained-hash,
   path and source-release tests.
3. Run the complete Python suite if the focused gates pass.
4. Run a two-period native website/model smoke test and a causal short two-year
   test. Do not substitute retained replay.
5. Verify output definition IDs, commissioning diagnostics, owner lineage,
   conservation, cost/carbon reconciliation and checkpoint validity.

## Decision rule

Report each Prompt 47–50 defect separately as fixed, failed or not exercised.
Long one-year/ten-year reruns are a later gate unless a short result indicates a
scientific regression that requires them immediately.
