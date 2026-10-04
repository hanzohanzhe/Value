# VALUE Ledger Canonicalisation Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the zero-valued Ledger v8 integrity mismatch and resume the bounded output/context gate from new evidence roots.

**Architecture:** Dataclass row contracts remain the single source of field types. One schema-aware helper canonicalises dataclass and SQLite row mappings before sorting and hashing; the model and database values are otherwise untouched. A Prompt 127 wrapper then executes the existing bounded gates in order and writes separate evidence and reports.

**Tech Stack:** Python 3.10, dataclasses, typing, SQLite, unittest.

**Spec:** `docs/scientific-readiness/prompts/126-value-ledger-numeric-canonicalisation.md` and `docs/scientific-readiness/prompts/127-value-output-context-verification-resume.md`

## Global Constraints

- Do not change PSM, staged bidding, zonal LP, SOC, CEM, data packs or scientific values.
- Do not round floats, weaken integrity comparison or migrate retained failure evidence.
- Keep existing schema IDs.
- Use fresh Prompt 127 output roots and stop at the first failed bounded gate.
- Do not run annual or ten-year production studies in this plan.

---

### Task 1: Canonicalise Ledger v8 numeric fields by row contract

**Files:**
- Modify: `gridform_core/market_ledger.py`
- Modify: `tests/test_prompt120_market_ledger_v8.py`

**Interfaces:**
- Consumes: dataclass row types used by `_build_common_projection` and `_database_period_projections`.
- Produces: `_canonical_row_mapping(row_type: type[object], row: Mapping[str, object]) -> dict[str, object]` and identical writer/validator science projections.

- [ ] **Step 1: Write the failing regression test**

Create a `PeriodLedgerRow` whose float-annotated zero-valued fields are passed
as integer `0`, record and close the ledger, then assert:

```python
validation = validate_market_ledger_file(database)
self.assertTrue(validation["valid"], validation)
```

Also assert the stored common projection hash equals a validator reconstruction
and that JSON identity fields remain integers.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m unittest tests.test_prompt120_market_ledger_v8.Prompt120MarketLedgerV8Tests.test_integer_zero_float_fields_round_trip_through_v8_integrity -v
```

Expected: FAIL with `period_integrity_science_projection_mismatch` before the
implementation exists.

- [ ] **Step 3: Implement the minimal shared canonicaliser**

Use resolved dataclass type hints to convert only `float` fields with `float()`
and only `int` fields with `int()`. Reject booleans and non-finite float values.
Call the helper from `_canonical_row_dicts`, the period projection, and
`_database_period_rows` using this exact table mapping:

```python
{
    "period_summary": PeriodLedgerRow,
    "dispatch_summary": DispatchSummaryRow,
    "storage_summary": StorageSummaryRow,
    "redispatch_summary": RedispatchSummaryRow,
    **{table: contract[0] for table, contract in _batch_table_contracts().items()},
}
```

- [ ] **Step 4: Add and run the scientific tamper regression**

After sealing a valid ledger, update one `REAL` field by `0.000001` and assert
that validation fails with a projection-integrity error. This proves the fix
normalises representation rather than adding tolerance.

- [ ] **Step 5: Run focused Prompt 126 regressions**

Run:

```powershell
python -m unittest tests.test_prompt120_market_ledger_v8 -v
python -m unittest tests.test_market_ledger -v
```

Expected: all tests pass with no unexpected skips or warnings.

- [ ] **Step 6: Commit Prompt 126**

```powershell
git add gridform_core/market_ledger.py tests/test_prompt120_market_ledger_v8.py docs/scientific-readiness/prompts/126-value-ledger-numeric-canonicalisation.md docs/superpowers/plans/2026-08-27-value-ledger-canonicalisation-repair.md docs/scientific-readiness/PROMPT_INDEX.md
git commit -m "fix: canonicalise VALUE ledger numeric projections"
```

### Task 2: Resume bounded output/context verification from fresh roots

**Files:**
- Create: `scripts/run_prompt127_output_context_resume.py`
- Create: `tests/test_prompt127_output_context_resume.py`
- Create: `publication/prompt127-output-context-test-report.json`
- Create: `publication/prompt127-output-context-test-report.md`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`

**Interfaces:**
- Consumes: Prompt 125 gate functions and audit semantics.
- Produces: Prompt 127-specific evidence roots, ordered stop-on-failure execution and a literal 48-period physical regression record.

- [ ] **Step 1: Write failing wrapper tests**

Assert that the new runner uses Prompt 127 report/evidence names, never writes
the Prompt 125 report paths, stops after the first failed gate, and records the
literal 48-period physical expectations.

- [ ] **Step 2: Run the wrapper tests and verify RED**

Run:

```powershell
python -m unittest tests.test_prompt127_output_context_resume -v
```

Expected: FAIL because the Prompt 127 runner does not exist.

- [ ] **Step 3: Implement the smallest Prompt 127 wrapper**

Reuse Prompt 125 gate functions rather than copying model logic. Redirect its
fresh-root function to `publication/prompt127-output-context-evidence`, execute
the five gates in locked order, add the literal 48-period result assertions,
and persist Prompt 127 reports after every gate.

- [ ] **Step 4: Run the wrapper tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_prompt127_output_context_resume -v
```

Expected: all tests pass.

- [ ] **Step 5: Execute bounded Prompt 127 gates in order**

Run with single-thread environment variables:

```powershell
python scripts/run_prompt127_output_context_resume.py
```

Expected: 48, 336, two-year coupling, trace equivalence, failure bundle,
preflight and frontend evidence all pass; no production annual/ten-year run is
started.

- [ ] **Step 6: Verify preserved failure history and final report**

Confirm the original Prompt 125 JSON still reports `ten_year_restart_authorised=false`,
the Prompt 127 JSON reports `true`, and every evidence path is under the Prompt
127 root.

- [ ] **Step 7: Commit Prompt 127**

```powershell
git add scripts/run_prompt127_output_context_resume.py tests/test_prompt127_output_context_resume.py docs/scientific-readiness/prompts/127-value-output-context-verification-resume.md docs/scientific-readiness/PROMPT_INDEX.md publication/prompt127-output-context-test-report.json publication/prompt127-output-context-test-report.md
git commit -m "test: resume bounded VALUE output verification"
```

### Task 3: Correct trace-equivalence semantics and finish bounded gates

**Files:**
- Create: `docs/scientific-readiness/prompts/128-value-trace-equivalence-semantics.md`
- Modify: `scripts/run_prompt127_output_context_resume.py`
- Modify: `tests/test_prompt127_output_context_resume.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Regenerate: `publication/prompt127-output-context-test-report.json`
- Regenerate: `publication/prompt127-output-context-test-report.md`

**Interfaces:**
- Consumes: two individually valid summary/full v8 SQLite ledgers from the Prompt 127 trace gate.
- Produces: an exact scientific-table equivalence decision that separates result identity from run-specific provenance identity.

- [x] **Step 1: Write failing trace-comparison tests**

Build two tiny SQLite fixtures with identical scientific tables and solver-link
rows that differ only in `declared_input_sha256`; assert equivalence passes and
retains the distinct roots. In a second test, change one physical numeric value
by `0.000001` and assert equivalence fails.

- [x] **Step 2: Run tests and verify RED**

Run:

```powershell
[LOCAL_PATH_REDACTED]
```

Expected: new tests fail because context-aware trace comparison is absent.

- [x] **Step 3: Implement exact projection comparison in the Prompt 127 runner**

Compare all locked scientific/common tables row-for-row, handle only the
declared-input hash as an allowed provenance difference, require both validator
results to be valid, and make the local Prompt 127 audit use this result instead
of Prompt 125's cross-context root-equality assumption.

- [x] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2. Expected: all Prompt 127 tests pass.

- [x] **Step 5: Rerun bounded Prompt 127 from fresh attempts**

Run the Prompt 127 runner under the locked Python 3.10 scientific environment.
Require all ordered gates, including failure/preflight, to pass. Do not run any
production annual or ten-year study.

Execution stopped fail-closed at trace equivalence because the fresh full
ledger failed its independent validator. The exact science comparison passed
with zero numerical difference; failure/preflight was not run and no model
repair was attempted.

- [ ] **Step 6: Commit Prompt 128**

```powershell
git add docs/scientific-readiness/prompts/128-value-trace-equivalence-semantics.md docs/scientific-readiness/PROMPT_INDEX.md docs/superpowers/plans/2026-08-27-value-ledger-canonicalisation-repair.md scripts/run_prompt127_output_context_resume.py tests/test_prompt127_output_context_resume.py publication/prompt127-output-context-test-report.json publication/prompt127-output-context-test-report.md
git commit -m "fix: compare VALUE trace science independently of provenance"
```

### Task 4: Canonicalise signed floating-point zero and rerun the bounded gate

**Files:**
- Create: `docs/scientific-readiness/prompts/129-value-ledger-signed-zero-canonicalisation.md`
- Modify: `gridform_core/market_ledger.py`
- Modify: `tests/test_prompt120_market_ledger_v8.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Regenerate after repair: `publication/prompt127-output-context-test-report.json`
- Regenerate after repair: `publication/prompt127-output-context-test-report.md`

**Interfaces:**
- Consumes: the existing schema-aware `_canonical_row_mapping` float branch.
- Produces: one canonical JSON representation for both IEEE zero signs while preserving every non-zero float exactly.

- [x] **Step 1: Write failing signed-zero regressions**

Assert a full-trace period containing `-0.0` bid prices validates after SQLite
round-trip, and assert `-0.000001` remains negative and non-zero.

- [x] **Step 2: Run the new tests and verify RED**

Use the locked Python 3.10 environment and expect the round-trip test to fail
with an evidence-projection mismatch.

- [x] **Step 3: Implement exact-zero normalisation**

After finite-float conversion, return `0.0` only when `number == 0.0`; otherwise
return the original finite float. Do not use `abs`, epsilon or rounding.

- [x] **Step 4: Run focused Ledger tests and verify GREEN**

Run `test_prompt120_market_ledger_v8.py` and `test_market_ledger.py` only.

- [x] **Step 5: Rerun Prompt 127 from fresh attempts**

Use the locked Python 3.10 environment. Continue through failure/preflight only
if every earlier gate passes. Do not run production annual or ten-year studies.

- [x] **Step 6: Commit Prompt 129 and refreshed bounded reports**

```powershell
git add docs/scientific-readiness/prompts/129-value-ledger-signed-zero-canonicalisation.md docs/scientific-readiness/PROMPT_INDEX.md docs/superpowers/plans/2026-08-27-value-ledger-canonicalisation-repair.md gridform_core/market_ledger.py tests/test_prompt120_market_ledger_v8.py publication/prompt127-output-context-test-report.json publication/prompt127-output-context-test-report.md
git commit -m "fix: canonicalise VALUE ledger signed zero"
```
