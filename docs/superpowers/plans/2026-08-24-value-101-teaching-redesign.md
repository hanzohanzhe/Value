# VALUE 101 Teaching Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Castle prototype into VALUE 101: a self-contained Windows teaching product in which a new user can run the real VALUE chain, replace one complete data pack, replace one scientific module, compare the controlled results, and optionally inspect a three-zone network-constraint case within 30 minutes.

**Architecture:** Keep one production execution path: the existing v2 Study contract, module registry, run service, PSM-CEM state transition, SQLite evidence and artifact-backed result APIs. Add a thin teaching orchestration contract around ordinary immutable Studies and Runs. Generate three complete CC0 data packs from one deterministic parent, reuse the accepted staged network/redispatch modules for the optional network exercise, and keep all scientific aggregation on the backend. Hide the experimental AC capability from the ordinary product registry without deleting its developer-only source or direct tests.

**Tech Stack:** Python 3.10, standard-library HTTP service, immutable JSON Study revisions, SQLite result indexes, React/TypeScript, Vite/vinext, PowerShell and C# Windows bootstrapper, `unittest`/`pytest`, npm lint/build/render tests.

**Spec:** `docs/superpowers/specs/2026-08-24-value-101-teaching-redesign.md`

## Global constraints

- Do not edit retained Scheme C source, its archived run logs or accepted hashes.
- Do not add a tutorial solver, a browser-side scientific calculator or precomputed result cards.
- Do not expose the real UK research/1000 TWh packs in the John pilot.
- Do not claim annual GB economics, DC load flow, AC power flow, N-1 security or transmission expansion.
- Use test-driven development: add the named failing test, demonstrate the intended red failure, implement the smallest production change, and rerun the focused test before broader gates.
- Preserve unrelated user changes already present in the worktree. Stage and commit only files named by the current task.
- Stop at a new material architecture decision. Record the original scope, proposed scope and affected contracts; obtain approval before proceeding.
- After each prompt, update `docs/scientific-readiness/PROMPT_INDEX.md` and `docs/scientific-readiness/RELEASE_GAP_MATRIX.md` with evidence links. Prompt numbers begin at 109 because Prompts 85-92 built the first teaching prototype and Prompts 93-108 built the network contracts.
- Use local Git commits as rollback points. Publishing to GitHub is a later, separately authorised operation through the authenticated GitHub connector.

On the current Windows development machine, initialise the verified interpreter
and file-based unittest runner once per PowerShell session:

```powershell
$VALUE_PYTHON = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
if (-not (Test-Path -LiteralPath $VALUE_PYTHON)) {
    throw "The verified CPython 3.10 runtime is missing: $VALUE_PYTHON"
}
function Invoke-ValueTests([string[]]$Patterns) {
    foreach ($pattern in $Patterns) {
        & $VALUE_PYTHON -m unittest discover -s tests -p $pattern -v
        if ($LASTEXITCODE -ne 0) { throw "Test failure: $pattern" }
    }
}
```

`tests/` is not a Python package, so do not invoke tests as
`tests.test_module`. The released Windows installer still uses its private
pinned runtime and does not depend on this developer-machine path.

## Phase map and acceptance coverage

| Phase | Prompts | Exit evidence | Spec gates |
| --- | --- | --- | --- |
| 0. Product boundary | 109 | Git rollback point; VALUE identifiers; public registry without AC; internal AC tests retained | 3, 10, 13 |
| 1. Scientific inputs and lifecycle | 110-111 | Three deterministic complete packs; controlled diffs; explicit teaching origin; safe reset | 1, 2, 4, 11 |
| 2. Guided product | 112-114 | Real module chain; explicit Study then Run; data/module experiments; artifact-backed comparison | 5, 6, 7, 8 |
| 3. Optional network lesson | 115 | Matched copperplate/constrained runs and reconciled redispatch evidence | 9 |
| 4. Pilot packaging and release gate | 116-117 | Offline installer lifecycle; full suite; clean-user timed rehearsal | 12, 13, 14 |

---

## Phase 0 — establish the safe product boundary

### Task 1: Prompt 109 — snapshot, VALUE 101 identity and public capability boundary

**Files:**

- Create: `docs/scientific-readiness/prompts/109-value-101-identity-and-public-boundary.md`
- Create: `tests/test_prompt109_value_101_identity.py`
- Create: `gridform_core/value_101.py`
- Modify: `gridform_core/v2/module_manifest.py`
- Modify: `gridform_core/frontend_contract.py`
- Modify: `gridform_core/application.py`
- Modify: `gridform_core/runtime_capabilities.py`
- Modify: `gridform_core/run_policy.py`
- Modify: `backend/server.py`
- Create: `gridform_core/internal_experimental/manifests/force-reference-ac-feasibility.json`
- Create: `gridform_core/internal_experimental/extension_manifests/force-ac-data-extension.json`
- Delete after moving: `gridform_core/manifests/force-reference-ac-feasibility.json`
- Delete after moving: `gridform_core/extension_manifests/force-ac-data-extension.json`
- Delete after callers move: `gridform_core/tutorials.py`
- Modify: `tests/test_prompt87_tutorial_runtime.py`
- Modify: `tests/test_prompt95_staged_copperplate.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`

- [ ] **Step 1: Turn the approved current prototype into a real Git rollback point before code changes.**

  Run:

  ```powershell
  git status --short
  git diff -- app/features/learn/Castle101Learn.tsx app/features/learn/castle101.ts app/globals.css docs/tutorial/CASTLE_101.md tests/test_prompt91_demo_launcher.py
  git add app/features/learn/Castle101Learn.tsx app/features/learn/castle101.ts app/globals.css docs/tutorial/CASTLE_101.md output/pdf/VALUE_Castle_101_guide.pdf tests/test_prompt91_demo_launcher.py packaging/windows-pilot scripts/build_windows_pilot_installer.py scripts/start-portable-local.ps1 tests/test_windows_pilot_installer.py
  git commit -m "chore: checkpoint pre-VALUE 101 teaching prototype"
  git tag value-101-pre-prompt109-20260824
  git rev-parse HEAD
  ```

  The listed paths are the installer/Lesson 1 prototype that the approved design supersedes. Inspect their diff before staging. If `git status --short` contains any additional path, leave it unstaged and record it as unrelated. Save the snapshot commit, tag and excluded dirty-path list in the Prompt 109 record.

- [ ] **Step 2: Write the failing identity and registry tests.**

  The test must assert:

  ```python
  descriptor = value_101_descriptor(installed_pack_ids={"value-101-baseline-v1"})
  assert descriptor["id"] == "value-101"
  assert descriptor["study"]["id"] == "value-101-baseline"
  assert descriptor["study"]["data_pack_id"] == "value-101-baseline-v1"
  assert descriptor["scientific_boundary"]["country"] == "SYNTHETIC"

  public = workspace_registry(include_internal_experimental=False)
  assert "force-reference-ac-feasibility" not in public.manifests()
  internal = workspace_registry(include_internal_experimental=True)
  assert "force-reference-ac-feasibility" in internal.manifests()
  ```

  Also issue `GET /api/tutorials/value-101` and require 200, issue the old Castle route and require 404, and scan the ordinary workspace payload to prove it contains no AC module/domain/extension.

- [ ] **Step 3: Run the red test and retain the failure.**

  Run:

  ```powershell
  Invoke-ValueTests @("test_prompt109_value_101_identity.py")
  ```

  Expected red reasons: `gridform_core.value_101` and `include_internal_experimental` do not yet exist, and the API still exposes `/api/tutorials/castle-101`.

- [ ] **Step 4: Implement the clean identity.**

  Move the teaching descriptor to `gridform_core/value_101.py` with constants:

  ```python
  VALUE_101_TUTORIAL_ID = "value-101"
  VALUE_101_BASELINE_PACK_ID = "value-101-baseline-v1"
  VALUE_101_BASELINE_STUDY_ID = "value-101-baseline"

  def value_101_study() -> dict[str, object]: ...
  def value_101_descriptor(*, installed_pack_ids: set[str]) -> dict[str, object]: ...
  ```

  Preserve the approved module chain and `planning.defer_spread_years=0`. Set `country=SYNTHETIC`, `timezone=UTC`, 48 periods per year, 2025-2026, teaching-only and nonannual flags. Do not add Castle aliases or migration code.

- [ ] **Step 5: Make experimental AC developer-only.**

  Change the registry signature to:

  ```python
  def workspace_registry(
      modules_path: Path | None = None,
      *,
      include_internal_experimental: bool = False,
  ) -> ModuleRegistryV2:
      ...
  ```

  Move the two built-in AC manifests out of the ordinary manifest directories and into `gridform_core/internal_experimental/`. Load them only when `include_internal_experimental=True`. The backend and normal CLI must use the default. Direct AC tests may request the flag. Remove AC from normal system-domain choices, readiness summaries and public runtime capability claims; do not delete `gridform_core/network_ac.py`.

- [ ] **Step 6: Replace the tutorial route.**

  Serve only `GET /api/tutorials/value-101`. The response must name all three required pack IDs and distinguish installed availability for each pack. The old route returns 404.

- [ ] **Step 7: Run focused and affected tests.**

  Run:

  ```powershell
  Invoke-ValueTests @(
      "test_prompt109_value_101_identity.py",
      "test_contracts_v2.py",
      "test_application_service.py",
      "test_prompt69_ac_feasibility.py",
      "test_prompt87_tutorial_runtime.py",
      "test_prompt95_staged_copperplate.py"
  )
  ```

  Direct AC tests must remain green through explicit internal activation. Ordinary workspace tests must prove AC absence.

- [ ] **Step 8: Commit the bounded change.**

  ```powershell
  git add gridform_core/value_101.py gridform_core/v2/module_manifest.py gridform_core/frontend_contract.py gridform_core/application.py gridform_core/runtime_capabilities.py gridform_core/run_policy.py backend/server.py gridform_core/internal_experimental tests/test_prompt109_value_101_identity.py tests/test_prompt87_tutorial_runtime.py tests/test_prompt95_staged_copperplate.py docs/scientific-readiness/prompts/109-value-101-identity-and-public-boundary.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md
  git add -u gridform_core/tutorials.py gridform_core/manifests/force-reference-ac-feasibility.json gridform_core/extension_manifests/force-ac-data-extension.json
  git commit -m "feat: establish VALUE 101 public boundary"
  ```

---

## Phase 1 — make data replacement scientifically controlled

### Task 2: Prompt 110 — deterministic three-pack family

**Files:**

- Create: `docs/scientific-readiness/prompts/110-value-101-controlled-data-packs.md`
- Create: `scripts/build_value_101_packs.py`
- Create: `tests/test_prompt110_value_101_pack_family.py`
- Create: `data-packs/value-101-baseline-v1/manifest.json`
- Create: `data-packs/value-101-windy-v1/manifest.json`
- Create: `data-packs/value-101-high-demand-v1/manifest.json`
- Create in each pack: `LICENSE`, `derivation.json`, and the 25 bound role files under `files/`
- Modify: `scripts/install_synthetic_pack.py`
- Modify: `scripts/install-force.ps1`
- Create by renaming: `tests/test_prompt86_value_101.py`
- Delete after renaming: `tests/test_prompt86_castle_101.py`
- Delete after replacement: `scripts/build_castle_101_pack.py`
- Delete after replacement: `data-packs/force-castle-101-v1/`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`

- [ ] **Step 1: Add red pack-family tests.**

  Require all three packs to pass the existing 25-role validator and assert the exact controlled role sets:

  ```python
  WIND_CHANGED_ROLES = {
      "weather.wind",
      "profiles.vre_onshore",
      "profiles.vre_offshore",
  }
  DEMAND_CHANGED_ROLES = {"demand.real", "demand.forecast"}
  ```

  Compare normalized manifests separately from scientific payload bytes so IDs, names and provenance are allowed to differ while unchanged scientific role hashes remain identical. Require `windy = clip(baseline * 1.35, 0, 1)` for the CEM per-unit wind profiles. Because `weather.wind` is PSM wind speed rather than availability, require the inverse cubic transform `v' = [3^3 + 1.35 * (v^3 - 3^3)]^(1/3)` with full-output protection. Require `high_demand = baseline * 1.20` for real and forecast demand. Require deterministic pack-tree hashes across two clean temporary builds.

- [ ] **Step 2: Demonstrate the red test.**

  ```powershell
  Invoke-ValueTests @("test_prompt110_value_101_pack_family.py")
  ```

  Expected failure: the new pack IDs and builder do not exist.

- [ ] **Step 3: Refactor the existing generator into one deterministic builder.**

  Expose:

  ```python
  def build_value_101_pack_family(output_root: Path) -> dict[str, object]: ...
  def derive_windy(parent_root: Path, target_root: Path) -> dict[str, object]: ...
  def derive_high_demand(parent_root: Path, target_root: Path) -> dict[str, object]: ...
  ```

  Build baseline first, deep-copy its role payloads, apply only the declared transform, then recompute binding hashes. Each `derivation.json` must contain parent pack ID/hash, transform expression, affected roles, unchanged-role hash result, builder version and CC0 statement. Retain the same synthetic fleet, costs, import envelopes and planning example unless a value is renamed solely to remove Castle branding.

- [ ] **Step 4: Enforce scientific metadata.**

  Each manifest must include `country: SYNTHETIC`, `timezone: UTC`, `teaching_only: true`, `annual_economics_eligible: false`, `scientific_baseline_eligible: false`, `period_hours: 0.5`, `periods_per_year: 48`, sources, units, transformations and SHA-256 values for all 25 roles.

- [ ] **Step 5: Update local installation without replacing user revisions.**

  Install the three pack directories idempotently into the configured state pack root. If an installed ID has different bytes, report the conflict and keep both the existing installation and the bundled source intact; never silently overwrite a scientific identity.

- [ ] **Step 6: Run pack and preflight gates.**

  ```powershell
  & $VALUE_PYTHON scripts/build_value_101_packs.py --check
  Invoke-ValueTests @(
      "test_prompt110_value_101_pack_family.py",
      "test_prompt86_value_101.py",
      "test_data_pack_validation.py",
      "test_executable_data_adapters.py"
  )
  ```

- [ ] **Step 7: Commit the pack family.**

  ```powershell
  git add scripts/build_value_101_packs.py scripts/install_synthetic_pack.py scripts/install-force.ps1 tests/test_prompt110_value_101_pack_family.py tests/test_prompt86_value_101.py data-packs/value-101-baseline-v1 data-packs/value-101-windy-v1 data-packs/value-101-high-demand-v1 docs/scientific-readiness/prompts/110-value-101-controlled-data-packs.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md
  git add -u scripts/build_castle_101_pack.py data-packs/force-castle-101-v1 tests/test_prompt86_castle_101.py
  git commit -m "feat: add controlled VALUE 101 data-pack family"
  ```

### Task 3: Prompt 111 — teaching-origin metadata, guided cloning, completion report and scoped reset

**Files:**

- Create: `docs/scientific-readiness/prompts/111-value-101-lifecycle-contract.md`
- Create: `gridform_core/value_101_lifecycle.py`
- Create: `tests/test_prompt111_value_101_lifecycle.py`
- Modify: `gridform_core/v2/projects.py`
- Modify: `gridform_core/project_revision.py`
- Modify: `backend/server.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`

- [ ] **Step 1: Add red tests for explicit teaching origin.**

  Extend the project contract through the existing `extensions` object, not a substring convention:

  ```json
  {
    "extensions": {
      "value_101": {
        "origin": "guided-course",
        "course_revision": "value-101/v1",
        "variant_kind": "baseline|data|storage|network",
        "parent_project_id": null,
        "changed_dimensions": []
      }
    }
  }
  ```

  Tests must create an ordinary Study whose name contains `value-101` and prove reset leaves it untouched. They must create teaching Studies/Runs with unrelated names and prove reset selects them by metadata. Pack installations, module installations and research records must remain byte-identical.

- [ ] **Step 2: Run the red lifecycle test.**

  ```powershell
  Invoke-ValueTests @("test_prompt111_value_101_lifecycle.py")
  ```

- [ ] **Step 3: Add controlled clone services.**

  Implement:

  ```python
  def clone_value_101_data_variant(
      base: Mapping[str, object], *, target_pack_id: str, new_id: str, new_name: str
  ) -> tuple[dict[str, object], dict[str, object]]: ...

  def clone_value_101_storage_variant(
      base: Mapping[str, object], *, storage_module_id: str, new_id: str, new_name: str
  ) -> tuple[dict[str, object], dict[str, object]]: ...

  def value_101_completion_report(
      projects: Sequence[Mapping[str, object]], runs: Sequence[Mapping[str, object]]
  ) -> dict[str, object]: ...
  ```

  The data clone must preserve every field except ID/name/data pack/origin metadata. The storage clone must preserve every field except ID/name/storage module/origin metadata. Both return a leaf-path identity diff and refuse saving if any extra scientific dimension differs.

- [ ] **Step 4: Add explicit API routes.**

  Add:

  - `POST /api/tutorials/value-101/studies` to create the baseline draft/revision;
  - `POST /api/tutorials/value-101/studies/{id}/clone-data`;
  - `POST /api/tutorials/value-101/studies/{id}/clone-storage`;
  - `GET /api/tutorials/value-101/completion-report`;
  - `POST /api/tutorials/value-101/reset` with `{ "confirm": true }`.

  Creating a Study must not start a Run. Reset must return exact deleted Study/Run/report IDs and refuse without confirmation. Remove teaching use of the generic `/clone-storage-policy` route only after all callers use the scoped route; keep the generic route for ordinary research work.

- [ ] **Step 5: Run lifecycle and revision tests.**

  ```powershell
  Invoke-ValueTests @(
      "test_prompt111_value_101_lifecycle.py",
      "test_project_revision.py",
      "test_prompt109_value_101_identity.py",
      "test_application_service.py"
  )
  ```

- [ ] **Step 6: Commit the lifecycle contract.**

  ```powershell
  git add gridform_core/value_101_lifecycle.py gridform_core/v2/projects.py gridform_core/project_revision.py backend/server.py tests/test_prompt111_value_101_lifecycle.py docs/scientific-readiness/prompts/111-value-101-lifecycle-contract.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md
  git commit -m "feat: add auditable VALUE 101 lifecycle"
  ```

---

## Phase 2 — teach composition in the real frontend

### Task 4: Prompt 112 — Home entry points, guided course and module disclosure

**Files:**

- Create: `docs/scientific-readiness/prompts/112-value-101-guided-workbench.md`
- Create: `app/features/learn/value101.ts`
- Create: `app/features/learn/Value101Learn.tsx`
- Create: `app/features/learn/ModuleChainCard.tsx`
- Create: `tests/test_prompt112_value_101_frontend.py`
- Modify: `app/page.tsx`
- Modify: `app/globals.css`
- Delete after import migration: `app/features/learn/castle101.ts`
- Delete after import migration: `app/features/learn/Castle101Learn.tsx`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`

- [ ] **Step 1: Write red source/render tests.**

  Require four Home actions: `Start VALUE 101`, `Build a Study`, `Open a saved Study`, `Add data or modules`. Require the five-building-block lesson to open inside the application. Require seven baseline module cards in execution order, with a plain-language surface and an expandable technical surface containing ID, version, contract, inputs, outputs and source location. Require no `Castle`, `AC`, `force-reference-ac-feasibility` or `Not evaluated` maturity lead on ordinary user pages.

- [ ] **Step 2: Run the red frontend test.**

  ```powershell
  Invoke-ValueTests @("test_prompt112_value_101_frontend.py")
  npm run build
  ```

- [ ] **Step 3: Build the guided component on live API data.**

  Rename the feature files and replace the progress key with `value.101.progress.v1`. Fetch `/api/tutorials/value-101` and `/api/workspace`; do not encode module version/source metadata in React fallback constants. The locked baseline cards must read the resolved server registry.

  Use this course state model:

  ```ts
  export type Value101StepId =
    | "building-blocks"
    | "baseline"
    | "data-variant"
    | "module-variant"
    | "compare"
    | "build-from"
    | "network";
  ```

  Steps are recommended, not disabled by sequence. Each action explains what it creates or changes before the button.

- [ ] **Step 4: Add compatibility explanations to the ordinary composer.**

  Leave incompatible module choices visible and disabled. Render the backend's missing role/capability/contract and corrective action. Never silently substitute a module. Add **Build from VALUE 101**, which copies the selected teaching Study into the ordinary composer as an unsaved draft and removes guided-course origin until the user explicitly saves it as an ordinary Study.

- [ ] **Step 5: Run frontend gates.**

  ```powershell
  Invoke-ValueTests @(
      "test_prompt112_value_101_frontend.py",
      "test_prompt91_demo_launcher.py"
  )
  npm run lint
  npm run build
  node --test tests/rendered-html.test.mjs
  ```

  Replace obsolete Prompt 91 Castle assertions with the VALUE 101 route; do not weaken launcher ownership or preflight assertions.

- [ ] **Step 6: Commit the guided workbench.**

  ```powershell
  git add app/features/learn/value101.ts app/features/learn/Value101Learn.tsx app/features/learn/ModuleChainCard.tsx app/page.tsx app/globals.css tests/test_prompt112_value_101_frontend.py tests/test_prompt91_demo_launcher.py docs/scientific-readiness/prompts/112-value-101-guided-workbench.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md
  git add -u app/features/learn/castle101.ts app/features/learn/Castle101Learn.tsx
  git commit -m "feat: teach VALUE composition in the workbench"
  ```

### Task 5: Prompt 113 — explicit data and storage-module experiments

**Files:**

- Create: `docs/scientific-readiness/prompts/113-value-101-controlled-experiments.md`
- Create: `app/features/learn/Value101Experiment.tsx`
- Create: `tests/test_prompt113_value_101_experiments.py`
- Modify: `app/features/learn/Value101Learn.tsx`
- Modify: `app/features/learn/value101.ts`
- Modify: `backend/server.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`

- [ ] **Step 1: Add red API and render tests.**

  Test that the learner personally selects either Windy or High demand, sees the exact changed roles/transformation, creates a Study, and must separately start its Run. Test that the storage selector offers Dynamic and Legacy only for the guided experiment, shows the pricing meaning, and creates a Study whose only scientific leaf change is `modules.storage_cost`.

- [ ] **Step 2: Run the red tests.**

  ```powershell
  Invoke-ValueTests @("test_prompt113_value_101_experiments.py")
  ```

- [ ] **Step 3: Implement preview-before-save.**

  Add a dry-run query/body option to both controlled clone APIs. Return:

  ```json
  {
    "changed_dimensions": ["data_pack_id"],
    "changed_roles": ["demand.real", "demand.forecast"],
    "preserved_dimensions": ["years", "modules", "parameters", "runtime_controls"],
    "can_save": true,
    "reason": null
  }
  ```

  The storage preview uses `changed_dimensions: ["modules.storage_cost"]`. The UI renders this response before enabling **Create Study**. Run buttons appear only after the Study revision exists and never fire from the selection event.

- [ ] **Step 4: Run focused and UI gates.**

  ```powershell
  Invoke-ValueTests @(
      "test_prompt113_value_101_experiments.py",
      "test_storage_policy_selection.py"
  )
  npm run lint
  npm run build
  node --test tests/rendered-html.test.mjs
  ```

- [ ] **Step 5: Commit controlled experiments.**

  ```powershell
  git add app/features/learn/Value101Experiment.tsx app/features/learn/Value101Learn.tsx app/features/learn/value101.ts backend/server.py tests/test_prompt113_value_101_experiments.py docs/scientific-readiness/prompts/113-value-101-controlled-experiments.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md
  git commit -m "feat: add guided VALUE 101 experiments"
  ```

### Task 6: Prompt 114 — artifact-backed teaching comparison and local completion evidence

**Files:**

- Create: `docs/scientific-readiness/prompts/114-value-101-comparison-and-evidence.md`
- Create: `gridform_core/value_101_results.py`
- Create: `app/features/learn/Value101Comparison.tsx`
- Create: `tests/test_prompt114_value_101_results.py`
- Modify: `backend/server.py`
- Modify: `app/features/learn/Value101Learn.tsx`
- Modify: `app/features/learn/value101.ts`
- Modify: `gridform_core/results_summary.py`
- Create by renaming: `tests/test_prompt89_value_101_results.py`
- Delete after renaming: `tests/test_prompt89_castle_results.py`
- Modify: `tests/test_prompt92_timing_ledger.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`

- [ ] **Step 1: Add red artifact-backed result tests.**

  Create three fixture Run bundles and require exactly three comparison rows in the approved order. Monkey-patch browser/request inputs with false totals and prove the endpoint ignores them. Require quantities to reconcile to the stored market SQLite, cost ledger, carbon ledger, VRE/curtailment artifacts, storage trace and planning index.

  The response schema is:

  ```python
  def build_value_101_comparison(
      baseline_run: Path, data_run: Path, storage_run: Path
  ) -> dict[str, object]: ...
  ```

  It must label all totals `teaching_window_*`, include `annual_economics_eligible=False`, and refuse the controlled interpretation if the declared identity diff contains extra dimensions.

- [ ] **Step 2: Run the red result test.**

  ```powershell
  Invoke-ValueTests @("test_prompt114_value_101_results.py")
  ```

- [ ] **Step 3: Implement backend aggregation.**

  Return teaching-window system/resource cost, physical operating cost, cost per served MWh, operational/overall/total carbon, VRE available/accepted/unused, storage charge/discharge/terminal SOC, blackout/load shedding, planning admissions/failures/commissioning, and the exact changed dimension. Reuse existing ledger readers rather than reimplementing formulas.

- [ ] **Step 4: Add comparison and detail navigation.**

  Render the three rows and their identity gates. Add links to the existing Market replay, dispatch, SOC, VRE/curtailment, cost, carbon, planning, provenance and raw JSON routes. Do not calculate or annualise any scientific metric in TypeScript.

- [ ] **Step 5: Implement report export and scoped reset UI.**

  Export the backend completion JSON locally. The UI shows the selected Studies, revision hashes, packs/modules, Run IDs/statuses, comparison gate, optional network status and diagnostic paths. Reset requires a confirmation dialog and displays the exact deletion scope before calling the API.

- [ ] **Step 6: Run comparison, ledger and frontend gates.**

  ```powershell
  Invoke-ValueTests @(
      "test_prompt114_value_101_results.py",
      "test_prompt89_value_101_results.py",
      "test_prompt92_timing_ledger.py",
      "test_results_summary.py",
      "test_market_ledger_v6.py",
      "test_carbon_ledger.py",
      "test_planning_index.py"
  )
  npm run lint
  npm run build
  node --test tests/rendered-html.test.mjs
  ```

- [ ] **Step 7: Commit the evidence layer.**

  ```powershell
  git add gridform_core/value_101_results.py gridform_core/results_summary.py backend/server.py app/features/learn/Value101Comparison.tsx app/features/learn/Value101Learn.tsx app/features/learn/value101.ts tests/test_prompt114_value_101_results.py tests/test_prompt89_value_101_results.py tests/test_prompt92_timing_ledger.py docs/scientific-readiness/prompts/114-value-101-comparison-and-evidence.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md
  git add -u tests/test_prompt89_castle_results.py
  git commit -m "feat: add artifact-backed VALUE 101 comparison"
  ```

---

## Phase 3 — add the optional fixed-network lesson without changing the solver design

### Task 7: Prompt 115 — three-zone network constraints and redispatch exercise

**Files:**

- Create: `docs/scientific-readiness/prompts/115-value-101-network-exercise.md`
- Create: `scripts/build_value_101_network_pack.py`
- Create: `data-packs/value-101-network-v1/manifest.json`
- Create in the pack: `LICENSE`, `derivation.json`, 25 ordinary roles and the required zonal-network extension roles
- Create: `app/features/learn/Value101NetworkExercise.tsx`
- Create: `tests/test_prompt115_value_101_network_exercise.py`
- Modify: `app/features/learn/Value101Learn.tsx`
- Modify: `backend/server.py`
- Modify: `scripts/install_synthetic_pack.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Reference without redesign: `gridform_core/staged_psm.py`, `gridform_core/zonal_redispatch.py`, `gridform_core/zonal_results.py`, `app/features/network/NetworkRedispatchView.tsx`

- [ ] **Step 1: Add red network-fixture tests.**

  Require North/Central/South zones, North-Central and Central-South lossless fixed corridors, asymmetric transfer support in the data contract, at least one known congested half-hour, and a matched copperplate/constrained Study pair. Assert identical national demand, fleet, weather, bids and ahead schedule before network redispatch.

- [ ] **Step 2: Run the red network test.**

  ```powershell
  Invoke-ValueTests @("test_prompt115_value_101_network_exercise.py")
  ```

- [ ] **Step 3: Build the deterministic network pack.**

  Derive it from `value-101-baseline-v1`, add explicit zone assignments and network roles, and record every network-only change. Keep the ordinary national demand total fixed. Choose corridor ratings so one period has a hand-calculable transfer deficit and redispatch response. Do not add losses, Kirchhoff voltage-angle equations or a transmission expansion module.

- [ ] **Step 4: Create the matched Study pair through ordinary contracts.**

  Copperplate uses the production bid-at-cost PSM. The constrained case uses the accepted staged national-ahead plus zonal balancing/redispatch modules and the fixed network data extension. Return a pre-run identity report proving the network selection and conditional roles are the only intended changes.

- [ ] **Step 5: Add the optional page.**

  Title it **Network constraints & redispatch**. Show corridor transfer/rating/utilisation, congestion, upward/downward redispatch by resource, network-added and network-avoided curtailment, load shedding, redispatch resource cost, pay-as-bid settlement, system-cost impact and the authoritative ledger. Add the method notice: zonal transport/redispatch representation; not DC load flow, AC power flow or N-1 security.

- [ ] **Step 6: Run scientific network gates.**

  ```powershell
  Invoke-ValueTests @(
      "test_prompt115_value_101_network_exercise.py",
      "test_prompt98_gb_zonal_pack_builder.py",
      "test_prompt99_zonal_redispatch.py",
      "test_prompt100_zonal_ledger.py",
      "test_prompt102_zonal_results_api.py",
      "test_prompt103_zonal_validation.py",
      "test_prompt107_production_gate.py"
  )
  npm run lint
  npm run build
  node --test tests/rendered-html.test.mjs
  ```

  Require energy balance, corridor limits, storage SOC, redispatch settlement, curtailment attribution and authoritative cost ledger reconciliation. Inject one corridor violation and one energy-balance corruption and require the gate to fail.

- [ ] **Step 7: Commit the network lesson.**

  ```powershell
  git add scripts/build_value_101_network_pack.py data-packs/value-101-network-v1 app/features/learn/Value101NetworkExercise.tsx app/features/learn/Value101Learn.tsx backend/server.py scripts/install_synthetic_pack.py tests/test_prompt115_value_101_network_exercise.py docs/scientific-readiness/prompts/115-value-101-network-exercise.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md
  git commit -m "feat: add VALUE 101 network redispatch lesson"
  ```

---

## Phase 4 — package the John pilot and prove the first-use journey

### Task 8: Prompt 116 — clean rename, manuals, PDF and offline Windows installer

**Files:**

- Create: `docs/scientific-readiness/prompts/116-value-101-windows-pilot.md`
- Create: `docs/tutorial/VALUE_101.md`
- Create: `docs/tutorial/VALUE_101_ZH.md`
- Create: `docs/tutorial/VALUE_101_QUICK_CARD.md`
- Create: `docs/tutorial/JOHN_PILOT_RUNBOOK.md`
- Create: `scripts/build_value_101_pdf.py`
- Create output: `output/pdf/VALUE_101_guide.pdf`
- Rename/modify: `packaging/windows-pilot/Value101Installer.cs`
- Modify: `packaging/windows-pilot/product.json`
- Modify: `packaging/windows-pilot/start-portable.ps1`
- Modify: `scripts/build_windows_pilot_installer.py`
- Modify: `scripts/start-portable-local.ps1`
- Create: `scripts/check-value-101.ps1`
- Create: `check-value-101.cmd`
- Modify: `README.md`
- Modify: `tests/test_windows_pilot_installer.py`
- Create: `tests/test_prompt116_value_101_docs.py`
- Modify: `tests/test_prompt90_tutorial_docs.py`
- Delete after replacement: `docs/tutorial/CASTLE_101.md`, `docs/tutorial/CASTLE_101_ZH.md`, `docs/tutorial/CASTLE_101_QUICK_CARD.md`, `docs/tutorial/STUART_DEMO_RUNBOOK.md`, `scripts/build_castle_101_pdf.py`, `scripts/check-castle-demo.ps1`, `check-castle-demo.cmd`, `packaging/windows-pilot/ValueCastleInstaller.cs`
- Delete after replacement: `output/pdf/VALUE_Castle_101_guide.pdf`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`

- [ ] **Step 1: Add red package and public-text scans.**

  Require output name `VALUE-101-Setup.exe`, shortcut/start-menu name `VALUE 101`, install/state root `%LOCALAPPDATA%/VALUE-101`, ports 8800/8766, all four synthetic packs, English guide and no UK pack. Scan release-facing code/docs/assets for `Castle`, `force-castle-101-v1`, public AC claims and old installation roots.

- [ ] **Step 2: Run the red package tests.**

  ```powershell
  Invoke-ValueTests @(
      "test_windows_pilot_installer.py",
      "test_prompt90_tutorial_docs.py",
      "test_prompt116_value_101_docs.py"
  )
  ```

- [ ] **Step 3: Rewrite the human manuals around actual actions.**

  The English manual must take John through baseline, one data replacement, one storage-module replacement, three-row comparison and optional network exercise. Explain every selectable Study/module/data choice, the 25-role data contract, the difference between synthetic teaching and UK research data, and how **Build from VALUE 101** becomes an ordinary Study. The Chinese manual mirrors the same scientific meaning. Do not lead with implementation history.

- [ ] **Step 4: Humanize and render the guide.**

  Run the humanizer skill against the finished English manual, accept only edits that preserve scientific terms and approved caveats, then build `output/pdf/VALUE_101_guide.pdf`. Verify font embedding, page count, internal headings and clickable local/manual links.

- [ ] **Step 5: Rename and complete the installer.**

  Preserve the prototype's transactional staging/rename, current-user install, owned-process stop, state isolation, diagnostic logs, repeat install and safe uninstall. Bundle pinned Python 3.10, locked Node/frontend dependencies, the built app, three ordinary VALUE 101 packs, the network pack and English materials. No administrator rights, terminal, internet, external Python, external Node or Git may be required after download.

- [ ] **Step 6: Test install lifecycle in an isolated user-state root.**

  Build, install, start, health-check, stop, reinstall, restart, uninstall and confirm unrelated local VALUE state is byte-identical. Occupy ports 8800 and 8766 with unrelated processes and require a clear refusal without terminating them.

  ```powershell
  & $VALUE_PYTHON scripts/build_windows_pilot_installer.py --output dist/windows-pilot
  Invoke-ValueTests @(
      "test_windows_pilot_installer.py",
      "test_prompt90_tutorial_docs.py",
      "test_prompt116_value_101_docs.py"
  )
  ```

- [ ] **Step 7: Commit the pilot product.**

  ```powershell
  git add README.md docs/tutorial/VALUE_101.md docs/tutorial/VALUE_101_ZH.md docs/tutorial/VALUE_101_QUICK_CARD.md docs/tutorial/JOHN_PILOT_RUNBOOK.md scripts/build_value_101_pdf.py output/pdf/VALUE_101_guide.pdf packaging/windows-pilot/Value101Installer.cs packaging/windows-pilot/product.json packaging/windows-pilot/start-portable.ps1 scripts/build_windows_pilot_installer.py scripts/start-portable-local.ps1 scripts/check-value-101.ps1 check-value-101.cmd tests/test_windows_pilot_installer.py tests/test_prompt90_tutorial_docs.py tests/test_prompt116_value_101_docs.py docs/scientific-readiness/prompts/116-value-101-windows-pilot.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md
  git add -u docs/tutorial/CASTLE_101.md docs/tutorial/CASTLE_101_ZH.md docs/tutorial/CASTLE_101_QUICK_CARD.md docs/tutorial/STUART_DEMO_RUNBOOK.md scripts/build_castle_101_pdf.py scripts/check-castle-demo.ps1 check-castle-demo.cmd packaging/windows-pilot/ValueCastleInstaller.cs output/pdf/VALUE_Castle_101_guide.pdf
  git commit -m "release: package the VALUE 101 Windows pilot"
  ```

### Task 9: Prompt 117 — clean-user timed release gate and handoff report

**Files:**

- Create: `docs/scientific-readiness/prompts/117-value-101-release-gate.md`
- Create: `scripts/audit_value_101_release.py`
- Create: `tests/test_prompt117_value_101_release_gate.py`
- Create on execution: `publication/prompt117-value-101-release-report.json`
- Create on execution: `publication/prompt117-value-101-release-report.md`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Modify: `docs/scientific-readiness/RELEASE_GAP_MATRIX.md`

- [ ] **Step 1: Add the red release-auditor test.**

  Feed the auditor a deliberately incomplete installer tree, a comparison with an extra changed dimension, an annualised teaching label, a public AC module, a corrupt pack hash and a network ledger imbalance. Require six distinct blocking codes. Feed a valid fixture and require `release_gate_passed=true`.

- [ ] **Step 2: Run the red auditor test.**

  ```powershell
  Invoke-ValueTests @("test_prompt117_value_101_release_gate.py")
  ```

- [ ] **Step 3: Implement the machine-readable gate.**

  Audit source commit, dirty paths, installer hash/size, bundled component versions, pack identities/hashes/licenses, public module catalogue, API routes, scientific labels, controlled diffs, run artifacts, completion/reset scope, network accounting, Scheme C retained hashes and test evidence. The JSON report is authoritative; the Markdown report renders it without independent calculations.

- [ ] **Step 4: Run the full software suite.**

  ```powershell
  & $VALUE_PYTHON -m unittest discover -s tests -p "test_*.py" -v
  npm ci
  npm run lint
  npm run build
  node --test tests/rendered-html.test.mjs
  & $VALUE_PYTHON scripts/audit_value_101_release.py --installer dist/windows-pilot/VALUE-101-Setup.exe --json publication/prompt117-value-101-release-report.json --markdown publication/prompt117-value-101-release-report.md
  ```

- [ ] **Step 5: Run the clean-user scientific journey.**

  In a fresh Windows user-state directory with networking disabled after the installer download:

  1. install and open VALUE with no terminal;
  2. read the five building blocks;
  3. create and run baseline;
  4. select Windy or High demand, preview the change, create and run it;
  5. select Legacy storage pricing, preview the change, create and run it;
  6. compare the three rows and open raw evidence;
  7. open **Build from VALUE 101** and identify the editable data/module/year layers;
  8. optionally run the matched three-zone network exercise;
  9. export the completion report;
  10. reset teaching state and prove unrelated state remains.

  Record wall-clock timestamps. The mandatory steps 1-7 must finish within 30 minutes without developer intervention. Record every confusion or misclick as usability evidence; do not rewrite the result after the fact.

- [ ] **Step 6: Run final integrity checks.**

  ```powershell
  rg -n "Castle|force-castle-101-v1|VALUE-Castle-101|force-reference-ac-feasibility|domain.network.ac" README.md app backend gridform_core/manifests gridform_core/extension_manifests packaging scripts docs/tutorial data-packs/value-101-* publication/prompt117-value-101-release-report.*
  git status --short
  git diff --check
  ```

  The first scan may find AC only in explicitly excluded internal source/test locations; it must find none in the listed public surfaces. Confirm the retained Scheme C hash test separately.

- [ ] **Step 7: Request code review and resolve findings.**

  Use the requesting-code-review skill on Prompts 109-117. Review specifically for a second execution path, browser-side formulas, substring deletion, accidental UK distribution, public AC leakage, uncontrolled scientific diffs and installer state damage. Fix findings with focused red/green tests before regenerating the report.

- [ ] **Step 8: Commit the release evidence.**

  ```powershell
  git add scripts/audit_value_101_release.py tests/test_prompt117_value_101_release_gate.py publication/prompt117-value-101-release-report.json publication/prompt117-value-101-release-report.md docs/scientific-readiness/prompts/117-value-101-release-gate.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md
  git commit -m "test: certify the VALUE 101 pilot journey"
  ```

---

## Phase exit decisions

- **After Prompt 110:** stop if the three-pack diff is not provably one-dimensional. Do not compensate in the comparison UI.
- **After Prompt 114:** stop if any displayed metric cannot be traced to a stored artifact and ledger identity.
- **After Prompt 115:** stop if the constrained result cannot reconcile energy, SOC, corridor capacity, redispatch, curtailment attribution and cost. Do not label the result DC load flow.
- **After Prompt 116:** stop if install/reinstall/uninstall can modify another VALUE workspace or needs a terminal/internet/admin rights.
- **After Prompt 117:** the Windows bundle may be sent to John only if every software, scientific-boundary, isolation and 30-minute gate passes. This is permission for a bounded teaching pilot, not a claim that VALUE 1.1 is a validated UK annual or ten-year scientific release.

## Final deliverables

1. `VALUE-101-Setup.exe` and SHA-256;
2. English PDF guide and Markdown source;
3. three complete ordinary teaching packs and one optional network pack;
4. the VALUE 101 Study/Run/comparison/completion APIs and frontend route;
5. Prompt 109-117 records and updated index/gap matrix;
6. machine-readable and human-readable Prompt 117 test reports;
7. a clean Git commit series with the pre-Prompt-109 rollback tag intact.
