# Castle 101 teaching implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a real, local Castle 101 teaching model and guided course that takes an installed user from startup to a controlled comparison in 30 minutes.

**Architecture:** Keep the existing application service and module graph. Add one CC0 data pack, one explicitly non-annual run policy and a Learn component that prepares the ordinary Study composer. Existing artifact-backed result views and storage-policy clone comparison remain the only calculation and comparison paths.

**Tech Stack:** Python 3.10, unittest, React 19, TypeScript, Vinext/Vite, Playwright, PowerShell, ReportLab, Poppler.

**Spec:** `docs/superpowers/specs/2026-08-20-castle-101-teaching-design.md`

## Global constraints

- Do not modify retained Scheme C source or its hashes.
- Keep `force-synthetic-contract-pack-v1` unchanged.
- Castle data is synthetic CC0-1.0 and contains no UK or network source object.
- Tutorial results are never annual-economics or scientific-baseline eligible.
- The required route uses the real local backend and works offline.
- Write each behavioural test first and observe the intended failure.
- Use `apply_patch` for source edits.
- Commit each prompt separately on `codex/castle-101-prompt85-92`.

---

### Task 1: Prompt 85 contract and rollback evidence

**Files:**
- Existing: `docs/superpowers/specs/2026-08-20-castle-101-teaching-design.md`
- Existing: `docs/scientific-readiness/prompts/85-castle-101-teaching-contract.md`
- Existing: `publication/prompt85-pre-change-snapshot.json`

**Interfaces:**
- Consumes: Prompt 84 commit `dd0e8ca`
- Produces: rollback tag `expanded-ui-pre-prompt85-20260820` and branch contract

- [x] **Step 1: Record the clean source identity and test counts**
- [x] **Step 2: Run Python, frontend build/render and lint baselines**
- [x] **Step 3: Commit the approved design and Prompt 85 to 92 definitions**

### Task 2: Prompt 86 deterministic Castle pack

**Files:**
- Create: `scripts/build_castle_101_pack.py`
- Create: `data-packs/force-castle-101-v1/**`
- Create: `tests/test_prompt86_castle_101.py`
- Modify: `source-release-manifest.json`

**Interfaces:**
- Produces: `build_pack(destination: Path) -> dict[str, object]`
- Produces: `gridform.data-pack/v1` with all 25 base roles

- [x] **Step 1: Write a failing pack contract test**

  Assert the literal pack ID, 25 validated bindings, 48-row demand/profile clocks,
  CC0 rights, no network roles, no absolute path and deterministic hashes.

- [x] **Step 2: Run `py -3.10 -m unittest tests.test_prompt86_castle_101 -v`**

  Expected failure: `scripts.build_castle_101_pack` or the checked-in pack is missing.

- [x] **Step 3: Implement the deterministic builder and generate the pack**

  The builder emits readable CSV/JSON files for demand, VRE profiles, generators,
  imports, one battery, planning records, costs and configuration. Use existing
  `DATASET_SLOTS` and `validate_data_pack`; do not create a Castle-only adapter.

- [x] **Step 4: Run the focused test and existing data-pack tests**

  Run: `py -3.10 -m unittest tests.test_prompt86_castle_101 tests.test_data_pack_validation tests.test_synthetic_public_pack -v`

- [x] **Step 5: Run a real 48-period year through the selected native modules**

  Assert energy residual below `1e-8 MWh`, non-zero cost/carbon, positive VRE
  curtailment, battery charge/discharge and planning rows.

- [x] **Step 6: Commit Prompt 86**

### Task 3: Prompt 87 tutorial policy and canonical Study

**Files:**
- Create: `gridform_core/tutorials.py`
- Create: `tests/test_prompt87_tutorial_runtime.py`
- Modify: `gridform_core/run_policy.py`
- Modify: `gridform_core/application.py`
- Modify: `backend/server.py`
- Modify: `scripts/install_synthetic_pack.py`
- Modify: `scripts/install-force.ps1`

**Interfaces:**
- Produces: `castle_101_study() -> dict[str, object]`
- Produces: `RUN_POLICIES["tutorial"]`
- Produces: `GET /api/tutorials/castle-101`

- [x] **Step 1: Write failing tests for policy, Study and installation**

  Hand-check that tutorial resolves to 2025 to 2026, 48 periods per year,
  `annual_economics_candidate=false`, the expected module IDs and no extensions.

- [x] **Step 2: Run the tests and observe missing policy/endpoint failures**
- [x] **Step 3: Add the policy and canonical Study factory**
- [x] **Step 4: Expose the read-only tutorial descriptor in the backend workspace**
- [x] **Step 5: Install Castle idempotently without replacing an existing pack**
- [x] **Step 6: Run focused policy, preflight, snapshot and API tests**
- [x] **Step 7: Commit Prompt 87**

### Task 4: Prompt 88 Learn interface

**Files:**
- Create: `app/features/learn/Castle101Learn.tsx`
- Create: `app/features/learn/castle101.ts`
- Modify: `app/page.tsx`
- Modify: `app/globals.css`
- Modify: `tests/rendered-html.test.mjs`
- Create: `e2e/castle-101.spec.ts`

**Interfaces:**
- Consumes: tutorial descriptor from `/api/tutorials/castle-101`
- Produces: `Castle101Learn` callbacks `onLoadStudy`, `onOpenView`

- [x] **Step 1: Add failing rendered assertions for Learn and teaching boundary**
- [x] **Step 2: Run `node --test tests/rendered-html.test.mjs` and observe failure**
- [x] **Step 3: Build the Learn component and add navigation item 00**
- [x] **Step 4: Load the canonical values into the existing Study composer**
- [x] **Step 5: Persist only presentation progress in local storage**
- [x] **Step 6: Add keyboard, missing-pack and laptop-width E2E assertions**
- [x] **Step 7: Run lint, build/render tests and focused E2E**
- [x] **Step 8: Commit Prompt 88**

### Task 5: Prompt 89 artifact-backed results and controlled experiment

**Files:**
- Create: `tests/test_prompt89_castle_results.py`
- Modify: `app/features/learn/Castle101Learn.tsx`
- Modify: `app/page.tsx`
- Modify: `e2e/castle-101.spec.ts`

**Interfaces:**
- Consumes: existing market, VRE, planning, ledger and comparison APIs
- Consumes: `POST /api/projects/{id}/clone-storage-policy`
- Produces: guided links and controlled comparison, no new result formula

- [x] **Step 1: Add a failing real-run test for required Castle evidence**
- [x] **Step 2: Run and observe the missing tutorial run/presentation behaviour**
- [x] **Step 3: Add a tutorial run button using mode `tutorial`**
- [x] **Step 4: Guide the user to existing artifact views after completion**
- [x] **Step 5: Wire the existing storage-policy clone and comparison paths**
- [x] **Step 6: Validate the exported bundle and changed-dimension identity**
- [x] **Step 7: Run focused Python and browser journeys**
- [x] **Step 8: Commit Prompt 89**

### Task 6: Prompt 90 manuals, humanizer and PDF

**Files:**
- Create: `docs/tutorial/CASTLE_101.md`
- Create: `docs/tutorial/CASTLE_101_ZH.md`
- Create: `docs/tutorial/CASTLE_101_QUICK_CARD.md`
- Create: `docs/tutorial/STUART_DEMO_RUNBOOK.md`
- Create: `scripts/build_castle_101_pdf.py`
- Create: `tests/test_prompt90_tutorial_docs.py`
- Create: `output/pdf/VALUE_Castle_101_guide.pdf`

**Interfaces:**
- Produces: technically checked Markdown sources and stable PDF path

- [x] **Step 1: Write a failing documentation consistency test**

  Check real labels, `127.0.0.1:8800`, tutorial boundary, expected module IDs,
  required files and absence of port 3000 instructions.

- [x] **Step 2: Draft manuals from verified UI and result evidence**
- [x] **Step 3: Run the humanizer draft-audit-final loop in file mode**
- [x] **Step 4: Re-run documentation consistency tests**
- [x] **Step 5: Mark one PDF create operation, then generate the PDF**
- [x] **Step 6: Inspect PDF metadata/text, render every page to PNG and inspect**
- [x] **Step 7: Correct layout defects and repeat rendering until clean**
- [x] **Step 8: Commit Prompt 90**

### Task 7: Prompt 91 local demo reliability

**Files:**
- Create: `scripts/check-castle-demo.ps1`
- Create: `check-castle-demo.cmd`
- Create: `tests/test_prompt91_demo_launcher.py`
- Modify: `scripts/start-local.ps1`
- Modify: `docs/tutorial/STUART_DEMO_RUNBOOK.md`

**Interfaces:**
- Produces: read-only pre-demo report with runtime, pack, build, port and disk status

- [x] **Step 1: Write failing launcher behaviour tests**
- [x] **Step 2: Observe missing check command and missing-pack diagnosis failures**
- [x] **Step 3: Implement the pre-demo check and safe startup repair**
- [x] **Step 4: Test repeated start/stop ownership and occupied-port refusal**
- [x] **Step 5: Disable network access and execute the local happy path**
- [x] **Step 6: Commit Prompt 91**

### Task 8: Prompt 92 final teaching gate

**Files:**
- Create: `publication/prompt92-castle-101-release-report.json`
- Create: `docs/scientific-readiness/PROMPT92_CASTLE_101_RELEASE_REPORT.md`
- Create: `publication/prompt92-castle-101-timing.json`
- Modify: `README.md`
- Modify: `docs/USER_GUIDE.md`
- Modify: `docs/USER_GUIDE_ZH.md`

**Interfaces:**
- Produces: capability-by-capability GO/NO-GO decisions and timed learner ledger

- [x] **Step 1: Execute the live Castle baseline and controlled variant**
- [x] **Step 2: Run complete Python suite**
- [x] **Step 3: Run frontend lint, production build, rendered and browser tests**
- [x] **Step 4: Run accessibility, responsive, source/rights and retained-hash gates**
- [x] **Step 5: Run the timed course and record observed seconds per step**
- [x] **Step 6: Reconcile evidence with every design acceptance gate**
- [x] **Step 7: Write human and machine reports without expanding claims**
- [x] **Step 8: Run `git diff --check`, inspect status and commit Prompt 92**
- [x] **Step 9: Apply the finishing-development-branch verification workflow**
