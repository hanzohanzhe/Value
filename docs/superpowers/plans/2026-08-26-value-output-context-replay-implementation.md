# VALUE Output, Context and Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long copperplate and fixed-zonal VALUE runs use bounded authoritative SQLite evidence, immutable run/year contexts and current-period module inputs, while preserving solver science and providing honest preflight, replay and failure evidence.

**Architecture:** Freeze one content-addressed run context and one immutable context per model year, then pass only the current-period slice through `value.balancing-input/v1` and `value.zonal-redispatch-domain/v2`. Replace unconditional staged-market JSONL and per-period diagnostic files with a v8 SQLite ledger whose common science projection is trace-invariant; generate exports on demand. Reuse the existing run quota, annual checkpoint and bounded result API infrastructure.

**Tech Stack:** Python 3.10, frozen dataclasses and canonical JSON/SHA-256, SQLite, SciPy/HiGHS, standard-library HTTP backend, React 19/TypeScript, Vite/vinext, `unittest`, ESLint and Node rendered-output tests.

**Spec:** `docs/superpowers/specs/2026-08-26-value-output-context-replay-architecture-design.md`

## Global Constraints

- Do not alter bid-at-cost construction, the four-phase zonal LP, settlement, SOC, curtailment attribution, CEM decisions or annual transition order.
- Do not edit retained Scheme C source, retained-output evidence or protected hashes.
- Do not add a new solver, database server, message queue or runtime dependency.
- New public contracts, artifacts, fields and UI copy use `VALUE`/`value.*`; do not add a FORCE identifier.
- `summary` remains the default trace profile; `full` is labelled **Full market replay**; `off` remains advanced.
- New staged runs write `value.market-ledger/v8` and never write `market/staged-market.jsonl`.
- Prompt 120 must not wire v8 into the simple bid-at-cost, perfect-foresight LP
  or reference DC-OPF paths. This plan fixes the staged plus zonal output
  explosion; it does not unify every PSM implementation.
- Existing v4-v7 ledgers and legacy staged-market JSONL remain read-only; never migrate them in place.
- A network pack is loaded and validated once per run; period records contain no complete pack or annual series.
- Trace choice cannot affect dispatch, SOC, CEM, cost, carbon or curtailment results.
- Use focused red/green tests for the named contract or defect. Do not run the complete Python suite, annual run or ten-year run before Prompt 125 authorises it.
- Preserve unrelated untracked installer/output/publication directories. Stage only files named by the active Prompt.
- After each Prompt, update `docs/scientific-readiness/PROMPT_INDEX.md` and `docs/scientific-readiness/RELEASE_GAP_MATRIX.md` with focused evidence.
- Use local commits as rollback points. GitHub publication is separate and must use the authenticated connector/API.

Initialise the verified interpreter once per PowerShell session:

```powershell
$VALUE_PYTHON = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
if (-not (Test-Path -LiteralPath $VALUE_PYTHON)) {
    throw "Verified CPython 3.10 is missing: $VALUE_PYTHON"
}
function Invoke-ValueTests([string[]]$Patterns) {
    foreach ($pattern in $Patterns) {
        & $VALUE_PYTHON -m unittest discover -s tests -p $pattern -v
        if ($LASTEXITCODE -ne 0) { throw "Test failure: $pattern" }
    }
}
```

## Phase map

| Phase | Prompt | Independently reviewable exit |
| --- | --- | --- |
| Context boundary | 118 | Immutable run/year contexts, refs, resolver and domain v2 contracts |
| Runtime wiring | 119 | One-time pack binding, annual context hand-off and no repeated static payload |
| Evidence store | 120 | Ledger v8, period transactions, summary/full projections and rolling hashes |
| Failure/recovery | 121 | First-failure bundle and safe annual-boundary cancellation/recovery |
| Resource gate | 122 | Selected-graph calibration, honest estimates and hard quota/free-space refusal |
| Read/export | 123 | Bounded SQLite queries and asynchronous range-based exports/replay packages |
| Product UI | 124 | Trace selection, readiness evidence, bounded browsing and export progress |
| Verification | 125 | 48/336-period, two-year and trace-equivalence gates; decision on ten-year restart |

---

## Phase 1 — context boundary and runtime wiring

### Task 1: Prompt 118 — immutable module context contracts

**Files:**

- Create: `docs/scientific-readiness/prompts/118-value-immutable-context-contracts.md`
- Create: `gridform_core/module_context.py`
- Modify: `gridform_core/staged_market_contracts.py`
- Modify: `gridform_core/v2/module_manifest.py`
- Modify: `gridform_core/manifests/value-staged-bid-at-cost-psm.json`
- Modify: `gridform_core/manifests/value-zonal-redispatch-balancing.json`
- Create: `tests/test_prompt118_value_context_contracts.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Modify: `docs/scientific-readiness/RELEASE_GAP_MATRIX.md`

**Interfaces:**

- Produces: `RunContextRef`, `YearContextRef`, `RunStaticContext`, `YearContext`, `ZonalRedispatchPeriodSlice`, `ZonalRedispatchDomainV2`, `ImmutableContextResolver`, `ModuleContextLifecycle`.
- Produces exact lifecycle signatures: `configure(run_context: RunStaticContext, resolver: ImmutableContextResolver) -> None`, `start_year(year_context: YearContext) -> None`, `clear(period_input: BalancingInput) -> BalancingResult`.
- Preserves: outer `BalancingInput.schema_version == "value.balancing-input/v1"`.
- Consumed by: Prompts 119-123.

- [ ] **Step 1: Commit the approved spec/plan and create the rollback tag before code changes.**

  Run:

  ```powershell
  git status --short
  git add docs/superpowers/specs/2026-08-26-value-output-context-replay-architecture-design.md docs/superpowers/plans/2026-08-26-value-output-context-replay-implementation.md
  git commit -m "docs: approve VALUE output and context architecture"
  git tag value-pre-prompt118-output-context-20260826
  git rev-parse HEAD
  ```

  Leave every existing `output/`, `outputs/` and `publication/prompt117-*` path unstaged. Record the commit and tag in the Prompt 118 document.

- [ ] **Step 2: Write the red contract tests.**

  The test builds a run context containing a minimal signed `ZonalNetworkPack`, a 2025 year context and a period slice, then asserts:

  ```python
  self.assertEqual(run_context.schema_version, "value.run-static-context/v1")
  self.assertEqual(year_context.schema_version, "value.year-context/v1")
  self.assertEqual(domain.schema_version, "value.zonal-redispatch-domain/v2")
  self.assertEqual(resolver.resolve_run(domain.run_context_ref), run_context)
  self.assertEqual(resolver.resolve_year(domain.year_context_ref), year_context)
  self.assertNotIn("network_pack", domain.to_dict())
  self.assertNotIn("zonal_demand", domain.to_dict())
  self.assertIn("ahead_result", domain.period_slice.to_dict())
  self.assertEqual(contract_sha256(run_context), domain.run_context_ref.sha256)
  ```

  Mutation of nested mappings and sequences must raise `TypeError`; a wrong hash, wrong year or unsupported schema must raise `ValueError`. Manifest tests require the capabilities `value.module-context-lifecycle/v1` and `value.zonal-redispatch-domain/v2` before a zonal Study is accepted.

- [ ] **Step 3: Run the focused test and retain the expected red failure.**

  ```powershell
  Invoke-ValueTests @("test_prompt118_value_context_contracts.py")
  ```

  Expected failure: `gridform_core.module_context` or the v2 domain class does not exist.

- [ ] **Step 4: Implement canonical frozen contracts and resolver.**

  `gridform_core/module_context.py` must expose these exact public shapes:

  ```python
  @dataclass(frozen=True)
  class RunContextRef(JsonContract):
      sha256: str
      schema_version: str = "value.run-static-context/v1"

  @dataclass(frozen=True)
  class YearContextRef(JsonContract):
      year: int
      sha256: str
      schema_version: str = "value.year-context/v1"

  @dataclass(frozen=True)
  class RunStaticContext(JsonContract):
      run_id: str
      study_revision_sha256: str
      start_year: int
      end_year: int
      period_hours: float
      data_pack: Mapping[str, object]
      module_graph: Mapping[str, object]
      scientific_parameters: Mapping[str, object]
      runtime_controls: Mapping[str, object]
      trace_profile: str
      solver_contract: Mapping[str, object]
      market_configuration: Mapping[str, object]
      network_pack: Mapping[str, object] | None = None
      schema_version: str = "value.run-static-context/v1"

  @dataclass(frozen=True)
  class YearContext(JsonContract):
      run_id: str
      year: int
      run_context_sha256: str
      operating_state: Mapping[str, object]
      frozen_zone_shares: Mapping[str, Mapping[str, float]]
      opening_soc_mwh_by_asset: Mapping[str, float]
      transition_lineage: Mapping[str, object]
      schema_version: str = "value.year-context/v1"

  class ImmutableContextResolver:
      def resolve_run(self, reference: RunContextRef) -> RunStaticContext: ...
      def resolve_year(self, reference: YearContextRef) -> YearContext: ...
      def resolve_module(self, slot: str) -> object: ...
  ```

  Every constructor freezes nested JSON, validates identities and hashes canonical JSON with `allow_nan=False`. `ZonalRedispatchDomainV2` goes in `staged_market_contracts.py`; its period slice contains only the current ahead result, zonal real/forecast demand, directional boundary ratings and interconnector envelopes.

- [ ] **Step 5: Run the focused test, scan names and commit.**

  ```powershell
  Invoke-ValueTests @("test_prompt118_value_context_contracts.py")
  rg -n "FORCE|force\." gridform_core/module_context.py gridform_core/staged_market_contracts.py gridform_core/manifests/value-staged-bid-at-cost-psm.json gridform_core/manifests/value-zonal-redispatch-balancing.json docs/scientific-readiness/prompts/118-value-immutable-context-contracts.md
  git add docs/scientific-readiness/prompts/118-value-immutable-context-contracts.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md gridform_core/module_context.py gridform_core/staged_market_contracts.py gridform_core/v2/module_manifest.py gridform_core/manifests/value-staged-bid-at-cost-psm.json gridform_core/manifests/value-zonal-redispatch-balancing.json tests/test_prompt118_value_context_contracts.py
  git commit -m "feat: add immutable VALUE module contexts"
  ```

  The scan may find explanatory retained-history text only outside the listed new files; any new public FORCE identifier is a failure.

### Task 2: Prompt 119 — bind contexts once and pass only period slices

**Files:**

- Create: `docs/scientific-readiness/prompts/119-value-context-runtime-wiring.md`
- Modify: `gridform_core/application.py`
- Modify: `gridform_core/v2/orchestrator.py`
- Modify: `gridform_core/builtin/value_modules.py`
- Modify: `gridform_core/builtin/scheme_c_1000twh/staged_psm.py`
- Modify: `gridform_core/zonal_redispatch.py`
- Modify: `gridform_core/manifests/value-staged-bid-at-cost-psm.json`
- Modify: `gridform_core/manifests/value-zonal-redispatch-balancing.json`
- Create: `tests/test_prompt119_value_context_runtime.py`
- Modify: `tests/test_prompt101_staged_cem_integration.py`
- Modify: `tests/test_prompt99_zonal_redispatch.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Modify: `docs/scientific-readiness/RELEASE_GAP_MATRIX.md`

**Interfaces:**

- Consumes: Prompt 118 context contracts and resolver.
- Produces: `build_run_static_context(...)`, `build_year_context(...)`, lifecycle calls in `AnnualModelOrchestratorV2`, and v2-only built-in zonal clearing.
- Preserves: current `PSMInput`, `AheadMarketInput`, `AheadMarketResult`, `BalancingInput` and `BalancingResult` scientific fields.

- [ ] **Step 1: Write red runtime tests around the observed failure.**

  Instrument `ZonalNetworkPack.validate` and assert one validation for a 48-period run. Capture all balancing inputs and assert:

  ```python
  self.assertEqual(len(captured), 48)
  for row in captured:
      payload = row.to_dict()["domain_payload"]
      self.assertEqual(payload["schema_version"], "value.zonal-redispatch-domain/v2")
      self.assertNotIn("network_pack", json.dumps(payload))
      self.assertLess(len(json.dumps(payload)), 250_000)
  self.assertEqual(validate_calls, 1)
  ```

  A two-year fixture must assert that the 2025 and 2026 context hashes differ, the 2025 context remains byte-identical after transition, and one commissioned 2025 project appears in the 2026 PSM context.

- [ ] **Step 2: Run the red runtime test.**

  ```powershell
  Invoke-ValueTests @("test_prompt119_value_context_runtime.py")
  ```

  Expected failure: each v1 period payload embeds `network_pack`, validates it again and has no year-context lifecycle.

- [ ] **Step 3: Build and persist the run/year contexts at their proper boundaries.**

  In `application.py`, load and validate the signed network pack once, create `RunStaticContext`, write it atomically to `market/context/run-context.json`, bind it and resolved module instances to `ImmutableContextResolver`, then call:

  ```python
  psm.configure(run_context, resolver)
  ```

  In `AnnualModelOrchestratorV2.run`, after the planning advance and `PSMInput` construction but before `psm.run`, create `YearContext`, persist `market/context/year-<YYYY>.json`, bind it, and call:

  ```python
  start_year = getattr(self.psm, "start_year", None)
  if callable(start_year):
      start_year(year_context)
  ```

  The following year's context must derive from the transitioned `YearState`, not the previous year's mutable Python objects.

- [ ] **Step 4: Replace v1 zonal domain reconstruction with bound v2 resolution.**

  `ValueStagedBidAtCostPSM` builds `ZonalRedispatchDomainV2` from stored context refs and the current period. Precompute `period_index_by_id` once; do not call `period_ids.index` in the loop. Move asset zones, resource classes, resource costs and storage technical metadata into `YearContext`. `ZonalRedispatchBalancing.configure` resolves and validates the pack once, `start_year` resolves annual asset metadata once, and `clear` validates only v2 references and current-period fields.

  Remove `_write_contract` and every call to it. Do not replace it with compressed or split JSONL. Stop writing per-period success JSON diagnostics; record their agreed summary/full fields through the ledger in Prompt 120. Keep first-failure writing temporarily until Prompt 121 replaces it atomically.

- [ ] **Step 5: Run the affected runtime tests and commit.**

  ```powershell
  Invoke-ValueTests @("test_prompt119_value_context_runtime.py", "test_prompt99_zonal_redispatch.py", "test_prompt101_staged_cem_integration.py")
  rg -n "staged-market\.jsonl|zonal-redispatch-domain/v1|network_pack.*to_dict" gridform_core/builtin/scheme_c_1000twh/staged_psm.py gridform_core/zonal_redispatch.py gridform_core/manifests/value-staged-bid-at-cost-psm.json
  git add docs/scientific-readiness/prompts/119-value-context-runtime-wiring.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md gridform_core/application.py gridform_core/v2/orchestrator.py gridform_core/builtin/value_modules.py gridform_core/builtin/scheme_c_1000twh/staged_psm.py gridform_core/zonal_redispatch.py gridform_core/manifests/value-staged-bid-at-cost-psm.json gridform_core/manifests/value-zonal-redispatch-balancing.json tests/test_prompt119_value_context_runtime.py tests/test_prompt99_zonal_redispatch.py tests/test_prompt101_staged_cem_integration.py
  git commit -m "fix: bind zonal contexts once per run and year"
  ```

  The scan must return no live writer or v1 domain construction. A legacy reader reference is allowed only outside the new-run path.

---

## Phase 2 — bounded authoritative evidence

### Task 3: Prompt 120 — market ledger v8, period transactions and trace invariance

**Files:**

- Create: `docs/scientific-readiness/prompts/120-value-market-ledger-v8.md`
- Create: `gridform_core/data/contracts/market-ledger-v8.schema.sql`
- Create: `gridform_core/market_integrity.py`
- Modify: `gridform_core/market_ledger.py`
- Modify: `gridform_core/builtin/scheme_c_1000twh/staged_psm.py`
- Modify: `gridform_core/bundle_validator.py`
- Modify: `gridform_core/run_bundle.py`
- Create: `tests/test_prompt120_market_ledger_v8.py`
- Modify: `tests/test_market_ledger.py`
- Modify: `tests/test_market_replay.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Modify: `docs/scientific-readiness/RELEASE_GAP_MATRIX.md`

**Interfaces:**

- Consumes: Prompt 118 context hashes and Prompt 119 current-period results.
- Produces: `MarketPeriodBatch`, `PeriodIntegrity`, `SQLiteMarketLedger.record_period_batch(batch)`, `science_root_by_year`, `evidence_root_by_year` and `value.market-ledger/v8`.
- Preserves: read-only capability/query support for ledger v4-v7.

- [ ] **Step 1: Write red v8 tests.**

  Construct identical two-period runs in `summary` and `full`, then require:

  ```python
  self.assertEqual(summary_meta["schema_version"], "value.market-ledger/v8")
  self.assertEqual(summary_meta["science_root_by_year"], full_meta["science_root_by_year"])
  self.assertNotEqual(summary_meta["evidence_root_by_year"], full_meta["evidence_root_by_year"])
  self.assertEqual(summary_counts["orders"], 0)
  self.assertGreater(full_counts["orders"], 0)
  self.assertFalse((run_root / "market" / "staged-market.jsonl").exists())
  ```

  Inject an exception after inserting one table in a period and assert that no row for that period remains. Open v4-v7 fixtures read-only and verify queries still work and file hashes do not change.

- [ ] **Step 2: Run the red ledger test.**

  ```powershell
  Invoke-ValueTests @("test_prompt120_market_ledger_v8.py")
  ```

  Expected failure: schema v8 and atomic `record_period_batch` do not exist.

- [ ] **Step 3: Add the v8 schema and atomic writer.**

  `MarketPeriodBatch` contains one `PeriodLedgerRow` plus tuples for common summary rows, full-only detail rows and canonical science/evidence payloads. `record_period_batch` executes `BEGIN IMMEDIATE`, writes all rows, updates both rolling hashes and commits. On any exception it executes `ROLLBACK` and re-raises.

  Add v8 tables from the spec: `dispatch_summary`, `storage_summary`, `redispatch_summary`, `context_registry`, `period_integrity` and `year_integrity`. Populate bid/order, declaration/outcome, asset settlement and full solver phase tables only when `trace_level == "full"`. `off` still writes contexts, annual ledgers, checkpoints, manifests and failure evidence.

- [ ] **Step 4: Stream integrity and remove whole-file sealing from the run path.**

  `gridform_core/market_integrity.py` exposes:

  ```python
  def next_science_hash(previous: str, common_projection: Mapping[str, object]) -> str: ...
  def next_evidence_hash(previous: str, stored_rows: Mapping[str, object]) -> str: ...
  def seal_year(connection: sqlite3.Connection, year: int) -> Mapping[str, object]: ...
  ```

  Use canonical sorted JSON and SHA-256. Artifact manifests retain context hashes, annual roots, row counts and trace coverage. Remove any `read_bytes()` or full JSONL readback from staged finalisation. File SHA-256 may be streamed in chunks after SQLite closes; it must not load the file into memory.

- [ ] **Step 5: Run focused ledger/replay compatibility tests and commit.**

  ```powershell
  Invoke-ValueTests @("test_prompt120_market_ledger_v8.py", "test_market_ledger.py", "test_market_replay.py")
  git add docs/scientific-readiness/prompts/120-value-market-ledger-v8.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md gridform_core/data/contracts/market-ledger-v8.schema.sql gridform_core/market_integrity.py gridform_core/market_ledger.py gridform_core/builtin/scheme_c_1000twh/staged_psm.py gridform_core/bundle_validator.py gridform_core/run_bundle.py tests/test_prompt120_market_ledger_v8.py tests/test_market_ledger.py tests/test_market_replay.py
  git commit -m "feat: make SQLite v8 the authoritative market ledger"
  ```

### Task 4: Prompt 121 — atomic failure evidence and annual-boundary recovery

**Files:**

- Create: `docs/scientific-readiness/prompts/121-value-failure-and-recovery.md`
- Create: `gridform_core/failure_evidence.py`
- Modify: `gridform_core/zonal_redispatch.py`
- Modify: `gridform_core/builtin/scheme_c_1000twh/staged_psm.py`
- Modify: `gridform_core/v2/orchestrator.py`
- Modify: `gridform_core/application.py`
- Modify: `backend/model_runner.py`
- Create: `tests/test_prompt121_failure_and_recovery.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Modify: `docs/scientific-readiness/RELEASE_GAP_MATRIX.md`

**Interfaces:**

- Consumes: immutable contexts and v8 transaction identity.
- Produces: `FailureEvidenceRequest`, `write_first_failure_bundle(request, destination)`, `request_period_boundary_cancel()` behaviour and incomplete-year cleanup.

- [ ] **Step 1: Write red failure and cancellation tests.**

  Break one corridor constraint under each trace profile and require exactly one atomically complete bundle containing run/year contexts, full failing period input, solver settings/identity, completed phases, residuals and hashes. Assert `fallback_used is False` and no alternative copperplate result exists.

  Request cancellation while period 2 is solving. Assert period 1 and 2 are complete transactions, the current year is marked incomplete, the prior annual checkpoint remains resumable, and resume deletes only incomplete-year rows before recomputing from its opening year-context hash.

- [ ] **Step 2: Run the red test.**

  ```powershell
  Invoke-ValueTests @("test_prompt121_failure_and_recovery.py")
  ```

- [ ] **Step 3: Centralise first-failure evidence.**

  Implement:

  ```python
  @dataclass(frozen=True)
  class FailureEvidenceRequest:
      run_context: RunStaticContext
      year_context: YearContext
      period_input: BalancingInput
      stage: str
      error: Exception
      solver: Mapping[str, object]
      residuals: Mapping[str, float]

  def write_first_failure_bundle(
      request: FailureEvidenceRequest,
      destination: Path,
  ) -> ArtifactReference: ...
  ```

  Write to a sibling temporary directory, hash every member, write the manifest last and atomically rename. If a first bundle already exists, preserve it and do not overwrite it with secondary errors.

- [ ] **Step 4: Enforce period-boundary cancellation and annual-only resume.**

  Pass the existing cancellation callback through the resolver. Check it only after `record_period_batch` commits. On resume, verify the frozen opening year-context hash, delete v8 rows for the incomplete year in one scoped transaction, and recompute that year. Do not implement subannual resume.

- [ ] **Step 5: Run focused tests and commit.**

  ```powershell
  Invoke-ValueTests @("test_prompt121_failure_and_recovery.py")
  git add docs/scientific-readiness/prompts/121-value-failure-and-recovery.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md gridform_core/failure_evidence.py gridform_core/zonal_redispatch.py gridform_core/builtin/scheme_c_1000twh/staged_psm.py gridform_core/v2/orchestrator.py gridform_core/application.py backend/model_runner.py tests/test_prompt121_failure_and_recovery.py
  git commit -m "fix: preserve atomic VALUE failure and recovery evidence"
  ```

---

## Phase 3 — honest resource protection and bounded access

### Task 5: Prompt 122 — selected-graph resource estimation and hard disk gate

**Files:**

- Create: `docs/scientific-readiness/prompts/122-value-preflight-resource-gate.md`
- Create: `gridform_core/preflight_resources.py`
- Modify: `gridform_core/preflight.py`
- Modify: `gridform_core/run_quota.py`
- Modify: `gridform_core/run_input_snapshot.py`
- Modify: `backend/server.py`
- Modify: `backend/model_runner.py`
- Create: `tests/test_prompt122_preflight_resource_gate.py`
- Modify: `tests/test_preflight.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Modify: `docs/scientific-readiness/RELEASE_GAP_MATRIX.md`

**Interfaces:**

- Consumes: selected module graph, pack/context cardinalities, trace profile and existing `reserve_run_space`.
- Produces: `ResourceCalibrationKey`, `ResourceEstimate`, `estimate_run_resources(...)` and frozen readiness evidence.

- [ ] **Step 1: Write red estimate and refusal tests.**

  Use a 3-zone and a larger synthetic pack to prove estimates derive from actual zones, boundaries, assets, storage and offers rather than hard-coded 14/20/50 values. Require:

  ```python
  self.assertEqual(report["estimates"]["trace_profile"], "summary")
  self.assertEqual(report["estimates"]["context_copies"], 1)
  self.assertGreaterEqual(report["estimates"]["persisted_safety_multiplier"], 1.5)
  self.assertFalse(insufficient["accepted"])
  self.assertEqual(insufficient["errors"][0]["code"], "VALUE_PREFLIGHT_DISK_SPACE")
  self.assertEqual(project["runtime_options"]["runtime.market_trace_level"], "full")
  ```

  The final assertion proves refusal does not silently change full replay to summary.

- [ ] **Step 2: Run the red tests.**

  ```powershell
  Invoke-ValueTests @("test_prompt122_preflight_resource_gate.py")
  ```

- [ ] **Step 3: Implement exact structural estimates and isolated calibration.**

  Define:

  ```python
  @dataclass(frozen=True)
  class ResourceEstimate:
      persisted_bytes: int
      temporary_bytes: int
      reserve_bytes: int
      runtime_seconds: float
      trace_profile: str
      calibration_basis: Mapping[str, object]
      row_cardinality: Mapping[str, int]

  def estimate_run_resources(
      *, project: Mapping[str, object], policy: Mapping[str, object],
      run_context: RunStaticContext, year_context: YearContext,
      calibration_root: Path, free_bytes: int, quota_policy: RunQuotaPolicy,
  ) -> ResourceEstimate: ...
  ```

  Calculate fixed context bytes exactly. Calculate table cardinality from the selected graph and expansion-headroom upper bounds. When a matching cache key is absent, run 48 periods against a deep-cloned opening state and isolated temporary ledger; do not create a Run, checkpoint, CEM transition or consume the official random stream. Cache bytes/seconds per period by data, module, solver, clock and trace fingerprints.

- [ ] **Step 4: Integrate the hard gate and frozen readiness snapshot.**

  Reuse `RunQuotaPolicy` and `reserve_run_space`. Required space is persisted estimate plus temporary estimate plus `max(10 GiB, 5% of target volume capacity)`. The UI/API error offers exactly: choose Summary, move the output root, or free space. `model_runner` verifies the preflight trace/context identities against the frozen input snapshot before execution.

- [ ] **Step 5: Run focused preflight/quota tests and commit.**

  ```powershell
  Invoke-ValueTests @("test_prompt122_preflight_resource_gate.py", "test_preflight.py")
  git add docs/scientific-readiness/prompts/122-value-preflight-resource-gate.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md gridform_core/preflight_resources.py gridform_core/preflight.py gridform_core/run_quota.py gridform_core/run_input_snapshot.py backend/server.py backend/model_runner.py tests/test_prompt122_preflight_resource_gate.py tests/test_preflight.py
  git commit -m "feat: gate VALUE runs with selected-graph resource estimates"
  ```

### Task 6: Prompt 123 — bounded queries and on-demand replay/export

**Files:**

- Create: `docs/scientific-readiness/prompts/123-value-bounded-replay-export.md`
- Create: `gridform_core/replay_export.py`
- Modify: `gridform_core/market_replay.py`
- Modify: `gridform_core/market_ledger.py`
- Modify: `gridform_core/zonal_results.py`
- Modify: `backend/server.py`
- Create: `tests/test_prompt123_bounded_replay_export.py`
- Modify: `tests/test_market_replay.py`
- Modify: `tests/test_prompt102_zonal_results_api.py`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Modify: `docs/scientific-readiness/RELEASE_GAP_MATRIX.md`

**Interfaces:**

- Consumes: ledger v8 plus legacy v4-v7 read-only adapters.
- Produces: paginated query functions and `create_replay_export(database, request, destination)` for period, 24-hour, 168-hour, year and complete ranges.

- [ ] **Step 1: Write red bounded-query and export tests.**

  Insert more rows than the requested page, call the API with year/start/limit/offset, and require stable ordering, exact totals and no whole-run materialisation. Export a 24-hour full run and assert its ZIP contains contexts, 48 period inputs/outcomes, Study/input manifest, module/solver identities, roots and checksums. Export a restricted-pack fixture and require `reference_only_not_portable` with no restricted source bytes.

- [ ] **Step 2: Run the red tests.**

  ```powershell
  Invoke-ValueTests @("test_prompt123_bounded_replay_export.py")
  ```

- [ ] **Step 3: Implement bounded v8 queries with legacy fallbacks.**

  All public queries accept `year`, `period_from`, `period_to`, `limit` and `offset`; enforce a server maximum of 1,000 rows. Aggregate charts in SQL by requested resolution. For v8, prefer summary tables; for v4-v7, use existing tables without writing to the database. Summary capability responses set `bid_replay_available=False` and name the missing detail honestly.

- [ ] **Step 4: Implement background range exports.**

  Define:

  ```python
  @dataclass(frozen=True)
  class ReplayExportRequest:
      range_kind: str
      year: int | None
      period_from: int | None
      period_to: int | None
      output_format: str

  def create_replay_export(
      database: Path,
      request: ReplayExportRequest,
      destination: Path,
  ) -> Mapping[str, object]: ...
  ```

  The server creates an export job record, writes into a temporary path and atomically publishes the file. JSONL is an explicit bounded export format only. Export jobs never mutate the run database or block the model worker.

- [ ] **Step 5: Run the focused API/replay tests and commit.**

  ```powershell
  Invoke-ValueTests @("test_prompt123_bounded_replay_export.py", "test_market_replay.py", "test_prompt102_zonal_results_api.py")
  git add docs/scientific-readiness/prompts/123-value-bounded-replay-export.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md gridform_core/replay_export.py gridform_core/market_replay.py gridform_core/market_ledger.py gridform_core/zonal_results.py backend/server.py tests/test_prompt123_bounded_replay_export.py tests/test_market_replay.py tests/test_prompt102_zonal_results_api.py
  git commit -m "feat: add bounded VALUE replay and export jobs"
  ```

### Task 7: Prompt 124 — trace/readiness and long-result frontend

**Files:**

- Create: `docs/scientific-readiness/prompts/124-value-trace-and-results-ui.md`
- Modify: `app/page.tsx`
- Modify: `app/globals.css`
- Modify: `app/features/network/networkRedispatch.ts`
- Modify: `app/features/network/NetworkRedispatchView.tsx`
- Create: `app/features/market/ReplayExportPanel.tsx`
- Create: `app/features/market/TraceCoverageNotice.tsx`
- Create: `tests/prompt124-ui-contract.test.mjs`
- Modify: `tests/rendered-html.test.mjs`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Modify: `docs/scientific-readiness/RELEASE_GAP_MATRIX.md`

**Interfaces:**

- Consumes: Prompt 122 readiness payload and Prompt 123 paginated/export APIs.
- Produces: explicit Study trace selector, immutable resolved-trace display, bounded period controls and export job progress.

- [ ] **Step 1: Write the red UI contract test.**

  The rendered source must contain the labels `Summary`, `Full market replay`, `Advanced: Off`, `Estimated persisted output`, `Temporary space`, `Free-space reserve` and `Recorded trace`. It must not contain an anchor that downloads an unbounded whole-run JSONL. A summary fixture must display `Bid-level replay was not recorded` and a link to create a new Study revision rather than mutate/rerun the completed Study.

- [ ] **Step 2: Run the red UI test.**

  ```powershell
  node --test tests/prompt124-ui-contract.test.mjs
  ```

- [ ] **Step 3: Implement trace selection and readiness evidence.**

  The Study composer writes `runtime.market_trace_level` as `summary`, `full` or `off`. Check readiness shows exact pack IDs/hashes, trace, modules/solver, persisted/temporary/reserve bytes, current free space, runtime basis and corrective actions. Once a Run starts, controls are read-only and display the frozen resolved profile.

- [ ] **Step 4: Implement bounded browsing and export jobs.**

  `MarketReplayView` and `NetworkRedispatchView` request only the selected year/window/page. `ReplayExportPanel` requires the user to select period, 24 hours, 168 hours, year or complete before starting a job; it polls only that job and offers the finished artifact. Summary mode never displays empty bid tables as though bids were zero.

- [ ] **Step 5: Run focused frontend gates and commit.**

  ```powershell
  node --test tests/prompt124-ui-contract.test.mjs
  npm run lint
  npm run build
  node --test tests/rendered-html.test.mjs
  git add docs/scientific-readiness/prompts/124-value-trace-and-results-ui.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md app/page.tsx app/globals.css app/features/network/networkRedispatch.ts app/features/network/NetworkRedispatchView.tsx app/features/market/ReplayExportPanel.tsx app/features/market/TraceCoverageNotice.tsx tests/prompt124-ui-contract.test.mjs tests/rendered-html.test.mjs
  git commit -m "feat: expose bounded trace and replay controls"
  ```

---

## Phase 4 — bounded engineering verification

### Task 8: Prompt 125 — storage, coupling and trace-equivalence gate

**Files:**

- Create: `docs/scientific-readiness/prompts/125-value-output-context-verification.md`
- Create: `scripts/run_prompt125_output_context_gate.py`
- Create: `tests/test_prompt125_output_context_gate.py`
- Create on execution: `publication/prompt125-output-context-test-report.json`
- Create on execution: `publication/prompt125-output-context-test-report.md`
- Modify: `docs/scientific-readiness/PROMPT_INDEX.md`
- Modify: `docs/scientific-readiness/RELEASE_GAP_MATRIX.md`

**Interfaces:**

- Consumes: Prompts 118-124.
- Produces: one machine-readable release decision and one concise human report; does not itself alter model code or data.

- [ ] **Step 1: Write the red gate test.**

  The auditor rejects evidence unless it contains all of these named gates:

  ```python
  required = {
      "contracts", "ledger_v8", "zonal_48_period", "zonal_336_period",
      "two_year_state_coupling", "trace_science_equivalence",
      "failure_bundle", "preflight_estimate", "frontend_bounded_access",
  }
  self.assertEqual(set(report["gates"]), required)
  self.assertFalse(report["ten_year_restart_authorised"])
  ```

  A missing context hash, staged-market JSONL, nonlinear byte growth, trace science-root mismatch, incomplete failure bundle or actual disk use above accepted estimate must make the gate fail.

- [ ] **Step 2: Run the auditor red/green fixtures.**

  ```powershell
  Invoke-ValueTests @("test_prompt125_output_context_gate.py")
  ```

- [ ] **Step 3: Execute the focused software checks once.**

  ```powershell
  Invoke-ValueTests @("test_prompt118_value_context_contracts.py", "test_prompt119_value_context_runtime.py", "test_prompt120_market_ledger_v8.py", "test_prompt121_failure_and_recovery.py", "test_prompt122_preflight_resource_gate.py", "test_prompt123_bounded_replay_export.py", "test_prompt125_output_context_gate.py")
  npm run lint
  npm run build
  node --test tests/prompt124-ui-contract.test.mjs tests/rendered-html.test.mjs
  ```

  Do not run the complete Python suite; these are the only affected gates required before live bounded execution.

- [ ] **Step 4: Run 48-period, 336-period and two-year fixtures in order.**

  ```powershell
  & $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --gate zonal-48
  & $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --gate zonal-336
  & $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --gate two-year-coupling
  & $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --gate trace-equivalence
  & $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --gate failure-and-preflight
  ```

  The 336-period run must show linear incremental bytes after fixed context, no annual payload in any period row and actual disk below the accepted estimate. The two-year run must show the commissioned asset in the next-year PSM context. Summary/full must have equal science roots and equal dispatch, SOC, investment, cost, carbon and curtailment results.

- [ ] **Step 5: Generate reports and make the ten-year decision.**

  ```powershell
  & $VALUE_PYTHON scripts/run_prompt125_output_context_gate.py --finalise --json publication/prompt125-output-context-test-report.json --markdown publication/prompt125-output-context-test-report.md
  ```

  Set `ten_year_restart_authorised=true` only when every gate passes. This flag authorises fresh matched ten-year output roots; it does not claim that those runs have completed or that the zonal method is newly scientifically validated.

- [ ] **Step 6: Update indexes and commit the bounded verification.**

  ```powershell
  git add docs/scientific-readiness/prompts/125-value-output-context-verification.md docs/scientific-readiness/PROMPT_INDEX.md docs/scientific-readiness/RELEASE_GAP_MATRIX.md scripts/run_prompt125_output_context_gate.py tests/test_prompt125_output_context_gate.py publication/prompt125-output-context-test-report.json publication/prompt125-output-context-test-report.md
  git commit -m "test: verify bounded VALUE output and context architecture"
  git status --short --branch
  ```

  Leave installer caches, product bundles and unrelated Prompt 117 evidence untracked and unchanged.

## Stop conditions

Stop and return to the user instead of widening the scope when any of these occurs:

1. implementing v2 requires changing a zonal LP coefficient, constraint, objective or settlement equation;
2. trace modes produce different common science roots;
3. a 336-period output projection remains superlinear after fixed context is removed;
4. an external module cannot be made compatible without a new public lifecycle decision;
5. preflight calibration would mutate an official run, random stream or CEM state;
6. a failure path uses automatic solver or copperplate fallback;
7. a requested replay ZIP would redistribute data prohibited by the selected pack ledger;
8. any retained Scheme C hash changes.

## Self-review record

- **Spec coverage:** context lifecycle, trace profiles, ledger v8, rolling integrity, failure evidence, resource protection, cancellation/recovery, bounded APIs, UI and verification are each assigned to Prompts 118-125.
- **Non-duplication:** Prompts 93-108 keep ownership of market/network science; Prompts 109-117 keep ownership of teaching/installer behaviour; Prompt 105 remains the later matched ten-year comparison.
- **Type consistency:** Prompt 118 defines all context/ref/resolver types; Prompt 119 consumes them; Prompts 120-123 use the same context hashes; Prompt 125 audits those exact identities.
- **Placeholder scan:** the plan contains no deferred implementation item; long-run execution is explicitly conditional on the Prompt 125 decision rather than left unspecified.
