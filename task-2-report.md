# Task 2 report — Prompt 127 bounded output/context resume

## Outcome

Prompt 127 stopped at the first failed scientific gate. The bounded 48-period,
literal physical regression, 336-period and two-year coupling checks passed.
Summary/full trace science roots differed, so `failure-and-preflight` was not
run and `ten_year_restart_authorised=false`.

No annual, two-full-year production, or ten-year production study was run.

## TDD record

- RED: `python tests/test_prompt127_output_context_resume.py -v` — 4 expected
  failures in 0.003s because the Prompt 127 runner did not exist.
- First GREEN attempt: 3/4 passed; one Windows temporary-SQLite cleanup error
  exposed a fixture connection that had not been explicitly closed.
- GREEN: `python tests/test_prompt127_output_context_resume.py -v` — 4/4 passed
  in 0.116s after closing the fixture connection.
- Review RED: a new Markdown evidence test failed on eight missing trace
  path/hash/byte fields, proving the reviewer finding.
- Review GREEN: the focused suite passed 5/5 in 0.313s after the Markdown
  renderer retained those fields. Post-commit verification passed 5/5 in
  0.296s.
- The plan's dotted unittest command cannot import either the new test or the
  existing Prompt 125 test in this environment because another installed
  `tests` package shadows this repository's non-package `tests` directory. The
  direct-file invocation above exercised the intended unit file.

## Runtime attempts

1. The default `python` (3.8.2) attempt stopped before producing a scientific
   result with `AttributeError: module 'types' has no attribute 'UnionType'`.
   It took 5.026096s at `zonal-48`; its JSON and Markdown reports are preserved
   as `prompt127-output-context-attempt-1-environment-failure.*`.
2. The scientific attempt used the project runtime
   `[LOCAL_PATH_REDACTED]`
   (Python 3.10.11, numpy 1.24.4, scipy 1.8.1, pandas 2.3.2). It started at
   2026-08-27T10:21:35.8912186Z.

## Scientific gate results

| Runner gate | Result | Elapsed (s) | Evidence |
| --- | --- | ---: | --- |
| `zonal-48` | PASS | 6.353143 | v8 validator passed; literal SQLite regression passed |
| `zonal-336` | PASS | 14.389689 | 336 periods; bounded output estimate and growth checks passed |
| `two-year-coupling` | PASS | 0.031569 | bounded 2025→2026 state-coupling fixture passed |
| `trace-equivalence` | FAIL | 4.858429 | summary/full common result hashes matched, but science roots differed |
| `failure-and-preflight` | NOT RUN | — | stopped after the first failed gate |

Literal 48-period observed totals were: 48 periods, 48 MWh demand, 48 MWh
accepted supply, £480 physical resource cost, £480 market payment, and zero
blackout, curtailment, storage charge, storage discharge and maximum absolute
energy-balance residual.

The trace roots were:

- summary: `c663e8639b2c915a1ed17d779b156f0fbfffd655665954598716fdf02ea10175`
- full: `2324385df31477bb339433b0a17eafefba6841335234ff13f094b84a3819d5c9`

## Preservation and remaining blocker

- Prompt 125 JSON SHA-256 remained
  `2b91983ae56fda5ebe7d5f82583299f2f33ac050225700d52311070031001fd3`.
- Prompt 125 Markdown SHA-256 remained
  `7be0dcb0caedc2ba3c85577e5deffc5a034c347bd777c3b36280a1ca72548884`.
- Every recorded Prompt 127 evidence path is under
  `publication/prompt127-output-context-evidence`.
- Remaining blocker: `trace_science_equivalence` reports
  `trace_science_root_mismatch`; per the stop rule, this task did not diagnose
  or modify the model and did not execute the later gate.
- Independent code review closed its Important Markdown-evidence finding and
  reported no new blocking issue.

Commit message: `test: resume bounded VALUE output verification`.
