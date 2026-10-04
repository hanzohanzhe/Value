# Prompt 125 — bounded VALUE output/context verification

## Purpose and boundary

This prompt verifies Prompts 118–124 with bounded engineering fixtures. It does
not change PSM, CEM, SOC, solver, transmission, frontend or data behavior. The
48/336-period runs are storage and contract evidence; the two-year fixture is
state-coupling evidence. None is annual economic validation.

## Required decision gates

The release decision contains exactly `contracts`, `ledger_v8`,
`zonal_48_period`, `zonal_336_period`, `two_year_state_coupling`,
`trace_science_equivalence`, `failure_bundle`, `preflight_estimate` and
`frontend_bounded_access`. Every gate must carry machine-readable evidence and
pass before `ten_year_restart_authorised` can be true.

The auditor fails closed for a missing context hash, new
`market/staged-market.jsonl`, annual/static payload in a period row,
superlinear incremental bytes after fixed context, actual bytes above the
accepted estimate, different summary/full science roots or common results,
incomplete first-failure evidence, fallback, mutable calibration state or an
unbounded frontend path.

## Ordered execution

Use the verified Python 3.10 interpreter. Numerical libraries are constrained
to one thread. Run only Task 8's focused software checks, then these commands
one at a time and in this order:

```powershell
& $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --gate zonal-48
& $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --gate zonal-336
& $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --gate two-year-coupling
& $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --gate trace-equivalence
& $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --gate failure-and-preflight
& $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --finalise --json publication/prompt125-output-context-test-report.json --markdown publication/prompt125-output-context-test-report.md
```

Each gate writes the current JSON and Markdown decision. On a failure, retain
the Prompt125-specific evidence root, report the first blocker and stop without
repairing production code or weakening the gate.

## Decision meaning

`ten_year_restart_authorised=true` authorises only a later creation of fresh
matched copperplate/zonal ten-year output roots. Prompt 125 never starts those
runs and does not claim they completed or newly validate zonal science.

## Execution result

The focused software gate passed. The first `zonal-48` attempt exposed and
preserved a verifier-only schema assumption (`scope` instead of the real v8
`context_scope`). A RED-first auditor regression fixed only that harness issue;
the original evidence root remains unchanged.

The second, separate 48-period attempt completed with one network-pack
validation, 48 compact period payloads (maximum 1,172 bytes), no annual/static
period payload and no `staged-market.jsonl`. The output was 427,454 bytes,
including a 389,120-byte v8 SQLite ledger. The production v8 validator then
reported period science-projection mismatches, broken predecessor-science
links and an annual science-root mismatch. This is the first release blocker.
No 336-period, two-year, trace-equivalence, failure/preflight, annual or
ten-year run was started. `ten_year_restart_authorised` remains false.
