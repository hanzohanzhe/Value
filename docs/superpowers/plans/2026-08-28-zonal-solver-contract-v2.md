# VALUE Zonal Solver Contract v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the v1 scale-blind zonal objective-lock allowance with the approved coefficient-aware v2 contract, verify the original failure, and restart clean matched ten-year runs.

**Architecture:** Keep the four-phase HiGHS solve and physical model unchanged. Extend only the objective-lock allowance and status classification, then propagate the v2 identities through the existing manifest, schema, ledger, Study acknowledgements, frontend and release evidence.

**Tech Stack:** Python 3.10, NumPy, SciPy/HiGHS, SQLite, JSON Schema, TypeScript/React, unittest.

**Spec:** `docs/superpowers/specs/2026-08-28-zonal-solver-contract-v2-design.md`

## Global Constraints

- `epsilon_effective = max(epsilon_solver, epsilon_canonicalisation)`.
- `tau_v2 = max(tau_v1, ||c||_1 * epsilon_effective)`.
- Physical feasibility and degradation above computed tolerance remain fail-closed.
- Above the validated ceiling completes only as `COMPLETED_WITH_NUMERICAL_WARNING`.
- Contract identity is `value.zonal-lexicographic/v2`; module version is `2.0.0`.
- Do not alter PSM/CEM economics, network data, topology, bids or settlement.
- Do not fall back to copperplate or silently loosen settings.
- Preserve existing unrelated dirty-worktree changes.

---

### Task 1: Lock-tolerance and classification regression

**Files:**
- Modify: `tests/test_zonal_solver_contract.py`
- Modify: `tests/test_prompt99_zonal_redispatch.py`

**Interfaces:**
- Consumes: `compute_lock_tolerance(...)`, `classify_lock(...)`.
- Produces: failing behavioral regressions for the approved v2 rules.

- [ ] Add a test whose zero optimum, VOLL-sized coefficient vector and `1e-8` effective tolerance require `||c||_1 * 1e-8`, not the unit floor.
- [ ] Add a test proving degradation within computed tolerance completes with `COMPLETED_WITH_NUMERICAL_WARNING` even when the computed tolerance exceeds the former absolute threshold.
- [ ] Run only those tests and confirm the first underestimates tolerance and the second raises `GF_ZONAL_ABSOLUTE_CEILING_VIOLATION`.

### Task 2: Implement the v2 numerical behavior

**Files:**
- Modify: `gridform_core/zonal_solver_contract.py`
- Modify: `gridform_core/zonal_redispatch.py`
- Modify: `gridform_core/data/contracts/market-ledger-v7.schema.sql`
- Modify: `gridform_core/market_ledger.py`

**Interfaces:**
- Consumes: the existing four-phase objective caps and bound canonicaliser.
- Produces: coefficient-aware `LockTolerance`; non-fatal over-reference classification; SQLite rows that accept the same classification.

- [ ] Add the coefficient one-norm allowance to `compute_lock_tolerance`.
- [ ] Pass `max(active_solver_tolerance, TOLERANCE)` from `_objective_cap`.
- [ ] Remove the former absolute-threshold hard failure from `classify_lock` while keeping `degradation > computed_tolerance` fatal.
- [ ] Change the SQLite class constraint so every value above the validated ceiling maps to `COMPLETED_WITH_NUMERICAL_WARNING`.
- [ ] Run focused solver-contract, zonal-redispatch and market-ledger tests.

### Task 3: Publish coherent v2 identities

**Files:**
- Create: `gridform_core/data/contracts/network-solver-contract-v2.schema.json`
- Modify: `gridform_core/zonal_solver_contract.py`
- Modify: `gridform_core/zonal_redispatch.py`
- Modify: `gridform_core/manifests/value-zonal-redispatch-balancing.json`
- Modify: `gridform_core/data/contracts/solver-validation-registry-v1.json`
- Modify: current Study/acknowledgement builders under `gridform_core/`
- Modify: current frontend contract types under `app/`
- Modify: focused tests and current user/developer documentation.

**Interfaces:**
- Produces: `value.network-solver-contract/v2`, `value.zonal-lexicographic/v2`, and `value-zonal-redispatch-balancing@2.0.0` end to end.

- [ ] Add the v2 JSON schema with recorded reference thresholds.
- [ ] Update the built-in module manifest and validation-registry candidate entry.
- [ ] Update active Study acknowledgements, frontend parsers and current documentation.
- [ ] Update focused contract tests and run them.
- [ ] Run frontend lint/build only if TypeScript production files changed.

### Task 4: Reproduce and verify the original failure boundary

**Files:**
- Use: `output/verification-diagnostics/diagnose_period_2431.py`
- Use: preserved `outputs/value-uk-zonal-2025-2034-20260827-matched/market/failures/first-failure`.
- Create: a compact machine-readable verification record under `publication/`.

**Interfaces:**
- Produces: exact evidence that the period-2431 canonicalised solution passes v2 without changing physical inputs or using fallback.

- [ ] Replay the exact declared input with v2.
- [ ] Verify all physical residuals remain within contract tolerances.
- [ ] Verify every objective degradation is at or below its computed tolerance.
- [ ] Verify `automatic_copperplate_fallback` remains false.

### Task 5: Bounded temporal gates

**Files:**
- Use: existing VALUE zonal gate scripts and VALUE-UK data pack.
- Create: 48-period and 336-period evidence directories under `publication/`.

**Interfaces:**
- Produces: short-horizon integration evidence before any destructive cleanup or long run.

- [ ] Run the 48-period matched zonal gate at one numerical thread.
- [ ] Run the 336-period matched zonal gate at one numerical thread.
- [ ] Validate period counts, physical balance, diagnostic rows and no fallback.

### Task 6: Remove obsolete v1 run evidence safely

**Files:**
- Delete only: exact obsolete run/output and run-specific report paths enumerated under `VALUE-1.1/outputs`, `VALUE-1.1/output/verification-diagnostics`, and `VALUE-1.1/publication`.

**Interfaces:**
- Produces: a clean run namespace without deleting source, Studies, data packs or Scheme C references.

- [ ] Resolve and print every candidate absolute path.
- [ ] Verify every deletion target remains beneath an intended VALUE output/report root.
- [ ] Delete only the approved v1 run evidence and report what was removed.

### Task 7: Fresh matched ten-year launch

**Files:**
- Create: fresh copperplate and zonal run directories under `outputs/`.
- Create: launch evidence under `publication/`.

**Interfaces:**
- Produces: matched 2025-2034 background runs using the same base inputs, one numerical thread and BelowNormal priority.

- [ ] Resolve current v2 Study/module identities through readiness.
- [ ] Launch copperplate and zonal workers with six numerical thread limits set to one.
- [ ] Set surviving workers to BelowNormal and record PIDs, commands, hashes and directories.
- [ ] Update the monitoring automation to report completion or the first exact blocker without auto-restart.

### Task 8: Review and handoff

**Files:**
- Review: `git diff` for every v2 source/config/test/document change.

**Interfaces:**
- Produces: reviewed bounded implementation and truthful long-run status.

- [ ] Self-review for scope drift, version mismatches, permissive physical failures and accidental FORCE identities.
- [ ] Run fresh focused verification commands and record exact counts.
- [ ] Report completed bounded gates, deleted evidence, long-run launch status and any remaining blocker.
