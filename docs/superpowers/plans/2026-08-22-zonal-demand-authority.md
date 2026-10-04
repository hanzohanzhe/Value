# Zonal Demand Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the Prompt 104 national-demand authority conflict without mutating the signed network pack, and make controlled copperplate/zonal comparison eligibility machine-verifiable.

**Architecture:** A pure alignment component validates the two clocks and derives zonal demand before clearing. Study resolution passes an explicit demand mode into the staged PSM; the PSM writes alignment rows to the existing market SQLite ledger. A separate comparison-eligibility builder fingerprints scientific inputs and prevents unsupported network-cost attribution.

**Tech Stack:** Python 3.10, frozen dataclasses, SQLite, unittest/pytest, TypeScript/React, Vite.

**Spec:** `docs/superpowers/specs/2026-08-22-zonal-demand-authority-design.md`

## Global Constraints

- Do not edit retained Scheme C source or the installed signed network overlay.
- New zonal Studies must declare `scenario_scaled_zonal_shares` or `network_pack_absolute_demand`; old missing declarations fail rather than migrate silently.
- Controlled comparison requires identical period-by-period realised and forecast demand plus the other identities named in the spec.
- SQLite is the default detailed audit path; the frontend shows bounded summaries.
- Apply strict red-green-refactor for every production behavior.

---

### Task 1: Pure demand-alignment contract

**Files:**
- Create: `gridform_core/zonal_demand_alignment.py`
- Create: `tests/test_prompt104_zonal_demand_alignment.py`

**Interfaces:**
- Produces: `align_zonal_demand(mode, period_ids, research_real_mwh, research_forecast_mwh, network_demand) -> ZonalDemandAlignment`
- Produces: immutable per-period rows and annual scaling summary consumed by the staged PSM and ledger.

- [ ] Write literal-fixture tests for scenario-scaled shares, residual closure and absolute-demand forecast scaling.
- [ ] Run the new test module and confirm imports or expected outputs fail because the contract does not exist.
- [ ] Implement the smallest immutable alignment types and calculation needed to pass.
- [ ] Add one failing test at a time for missing/duplicate/misaligned periods, zero network totals, zero base-real ratios, negative/non-finite data and conservation.
- [ ] Implement each validation branch and keep the focused test module green.
- [ ] Commit the completed pure contract.

### Task 2: Explicit Study declaration and runtime wiring

**Files:**
- Modify: `gridform_core/study_market_config.py`
- Modify: `gridform_core/frontend_contract.py`
- Modify: `gridform_core/application.py`
- Modify: `gridform_core/builtin/scheme_c_1000twh/staged_psm.py`
- Modify: `gridform_core/run_lineage.py`
- Modify: `publication/prompt104-zonal-study.json`
- Test: `tests/test_prompt101_staged_cem_integration.py`
- Test: `tests/test_prompt104_network_overlay_resolution.py`
- Test: `tests/test_prompt104_zonal_demand_alignment.py`

**Interfaces:**
- Consumes: Task 1 `ZonalDemandAlignment`.
- Produces: resolved `market_configuration.zonal_demand_mode` and one precomputed alignment supplied to `StagedBidAtCostPSM.configure_run`.

- [ ] Write failing resolution tests proving a zonal Study without a mode is rejected, both supported values are accepted, and copperplate does not require a mode.
- [ ] Run the focused tests and observe the missing-validation failures.
- [ ] Add mode validation without silently changing migrated or saved zonal Studies.
- [ ] Write a failing staged-PSM integration test using unequal network and research national demand.
- [ ] Pass the mode through application configuration, compute alignment after chronology construction, and consume aligned zonal demand during redispatch.
- [ ] Preserve the source Study when creating an explicit copperplate rerun and remove only zonal-only configuration from the new copy.
- [ ] Recompute Prompt 104 Study revision identities with the explicit scaled mode.
- [ ] Run the focused integration tests and commit.

### Task 3: SQLite demand audit and comparison eligibility

**Files:**
- Modify: `gridform_core/market_ledger.py`
- Modify: `gridform_core/data/contracts/market-ledger-v5.schema.sql`
- Create: `gridform_core/comparison_eligibility.py`
- Modify: `gridform_core/results_summary.py`
- Modify: `backend/server.py`
- Test: `tests/test_prompt100_zonal_ledger.py`
- Create: `tests/test_prompt104_comparison_eligibility.py`

**Interfaces:**
- Consumes: Task 1 alignment rows and annual summary.
- Produces: SQLite `zonal_demand_alignment` rows, market metadata summary and run-level `comparison-eligibility.json`.
- Produces: comparison response fields `network_cost_attribution_allowed` and `comparison_eligibility_mismatches`.

- [ ] Write a failing ledger test that queries the exact per-period alignment evidence from SQLite.
- [ ] Add the schema row type, batch writer, counts and field dictionary entry; run the test green.
- [ ] Write failing literal-hash tests for eligible matched runs, non-eligible demand mismatch and absolute-demand labelling.
- [ ] Implement deterministic scientific-input fingerprints and comparison evaluation.
- [ ] Integrate the run artifact into summaries/API so side-by-side viewing remains possible while causal attribution is blocked.
- [ ] Run focused ledger, bundle and comparison tests and commit.

### Task 4: Frontend declaration, evidence and methods

**Files:**
- Modify: `app/page.tsx`
- Modify: `app/features/network/NetworkRedispatchView.tsx`
- Modify: `app/features/network/networkRedispatch.ts`
- Modify: `README.md`
- Modify: `README_BILINGUAL.md`
- Modify: `docs/generated/ZONAL_NETWORK_DATA_CONTRACT.md`
- Modify: `docs/generated/ZONAL_NETWORK_DATA_CONTRACT_ZH.md`
- Test: existing frontend lint/build and relevant API contract tests.

**Interfaces:**
- Consumes: resolved market configuration and bounded demand-alignment metadata.
- Produces: explicit Study selection and truthful results interpretation.

- [ ] Add `zonal_demand_mode` to `StudyForm` and load/save it as part of immutable Study JSON.
- [ ] Default newly selected zonal balancing to `scenario_scaled_zonal_shares`; do not populate old saved zonal revisions silently.
- [ ] Expose the absolute mode only in Advanced and display the required attribution warning.
- [ ] Show mode/source/scaling summary in Network & redispatch evidence without rendering period rows.
- [ ] Update English and bilingual methodology text with the fixed-2024-weight limitation and replacement contract.
- [ ] Run frontend lint and production build; commit.

### Task 5: Prompt 104 verification gate

**Files:**
- Modify: `publication/prompt104-copperplate-preflight.json`
- Modify: `publication/prompt104-zonal-preflight.json`
- Create or update: `publication/prompt104-annual-and-two-year-zonal-gate-report.json`
- Create or update: `docs/scientific-readiness/PROMPT104_ANNUAL_AND_TWO_YEAR_ZONAL_GATE_REPORT.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: auditable GO/NO-GO evidence for annual and, conditionally, two-year execution.

- [ ] Run affected Python regression tests, ledger validation, frontend lint and frontend production build.
- [ ] Regenerate both preflights and confirm the signed overlay identity is unchanged.
- [ ] Run deterministic real copperplate and zonal smokes and validate their bundles and comparison eligibility.
- [ ] If either smoke fails, stop the production gate, record the root cause and do not start annual execution.
- [ ] If both pass, run the matched 17,520-period 2025 copperplate and zonal cases and execute every Prompt 104 mandatory audit.
- [ ] If either annual audit fails, issue NO-GO and do not start two-year execution.
- [ ] If both annual gates pass, run the matched 2025–2026 chains, validate next-year state inheritance, checkpoint/replay/export and publish the final Markdown/JSON decision.
