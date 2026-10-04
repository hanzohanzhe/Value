# Zonal Monthly Runtime Checkpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit, identity-verified, end-of-calendar-month resume support to future VALUE zonal PSM runs without changing any PSM, CEM, settlement, cost, carbon or transmission result.

**Architecture:** Complete the existing optional `value.subannual-checkpoint/v1` contract. The maintained zonal PSM owns a pure-JSON year-to-date runtime state; the VALUE runtime owns month-boundary recognition, atomic checkpoint publication, identity validation, retention, one-use authorization and SQLite prefix recovery. Annual orchestration remains unchanged: monthly boundaries never invoke expansion, investment, planning, admission or transition.

**Tech Stack:** Python 3.10, standard-library dataclasses/JSON/hashlib/os/sqlite3, VALUE v2 JSON contracts, SQLite v8 authoritative market ledger, React/TypeScript Runs UI, Python `unittest`, Node test runner and Playwright.

**Spec:** `docs/superpowers/specs/2026-08-29-zonal-monthly-runtime-checkpoints-design.md`

## Global Constraints

- Do not modify, stop, convert or resume the active v2 runs under `outputs/value-uk-*-2025-2034-20260828-v2`.
- Apply this capability only to subsequently launched zonal runs using `value-staged-bid-at-cost-psm` with `value-zonal-redispatch-balancing@2.0.0` and solver contract `value.zonal-lexicographic/v2`.
- Copperplate and third-party PSMs without the optional capability retain annual recovery.
- Complete the existing `value.subannual-checkpoint/v1`; do not introduce another checkpoint schema or compatibility alias.
- Set the schema `$id` exactly to `urn:value:contract:subannual-checkpoint:v1` and remove the unsupported-future wording.
- Month boundaries come from the frozen chronology's real dates; do not divide period counts by twelve and do not synthesize leap-day periods.
- Publish only after the month's last period transaction commits and the complete in-memory period outcome is applied.
- Keep two verified monthly checkpoints for the active model year; a verified annual checkpoint removes that year's monthly checkpoints.
- Resume only after an explicit checkpoint ID is supplied through the UI or CLI; the presence of files never implies resume intent.
- Preserve unconfirmed SQLite suffix rows in an immutable diagnostic copy, then publish the verified prefix in one SQLite-native transaction while holding exclusive recovery ownership. Never replace the live database file or manually manipulate its WAL/SHM files.
- Fail closed on any identity, chronology, ledger, storage, balance, authorization or atomic-publication mismatch; never change solver, parameters or network mode and never fall back to copperplate.
- Serialize no PuLP, CBC, open SQLite connection, compatibility-session object or other solver-native object.
- Add no runtime dependency and do not run annual, two-year or ten-year production studies for this feature.

---

## File Structure

- `gridform_core/subannual_checkpoint.py` — the one public v1 checkpoint model, chronology boundary parser, canonical hashing, atomic store, discovery, retention and recovery-candidate types.
- `gridform_core/market_ledger.py` — v8 ledger-prefix identity, prefix validation and transactional tail recovery because this file owns every authoritative table and hash-chain rule.
- `gridform_core/market_ownership.py` — the shared cross-process ownership domain automatically held by every product ledger writer and exclusively claimed by recovery.
- `gridform_core/builtin/scheme_c_1000twh/psm_runtime_state.py` — focused, solver-neutral staged-PSM period outcome and resumable year-to-date state.
- `gridform_core/builtin/scheme_c_1000twh/staged_psm.py` — optional checkpoint hooks, exact resume index and period-loop ordering.
- `gridform_core/zonal_redispatch.py` — JSON export/restore for the balancing module's consumed-input identity guard.
- `gridform_core/application.py` — explicit selected-checkpoint validation, one-use claim, ledger recovery, PSM restore and annual supersession cleanup.
- `backend/model_runner.py` — explicit `--resume-from-checkpoint` propagation and non-zero failures.
- `backend/server.py` — safe recovery presentation and exact-checkpoint resume API.
- `app/page.tsx` — recovery status, explicit resume, run-again separation and corrective-action UI.
- `gridform_core/data/contracts/subannual-checkpoint-v1.schema.json` and `gridform_core/manifests/value-staged-bid-at-cost-psm.json` — completed public contract and capability declaration.
- `tests/test_subannual_checkpoint.py`, `tests/test_zonal_subannual_resume.py`, `tests/test_checkpoint_resume_api.py`, `tests/test_model_runner_resume_cli.py` — new bounded tests; existing ledger, recovery and UI tests receive narrowly scoped additions.

---

### Task 1: Complete the v1 contract and real-calendar boundary parser

**Files:**
- Create: `gridform_core/subannual_checkpoint.py`
- Modify: `gridform_core/data/contracts/subannual-checkpoint-v1.schema.json:1-29`
- Modify: `gridform_core/manifests/value-staged-bid-at-cost-psm.json`
- Modify: `gridform_core/recovery_capability.py:10-66`
- Test: `tests/test_subannual_checkpoint.py`
- Test: `tests/test_recovery_capability.py:17-44`

**Interfaces:**
- Produces:
  - `RuntimeCheckpointBoundary(JsonContract)`
  - `SubannualCheckpointIdentity(JsonContract)`
  - `LedgerPrefixIdentity(JsonContract)`
  - `SubannualCheckpoint(JsonContract)`
  - `RecoveryMismatch(JsonContract)`
  - `RecoveryCandidate(JsonContract)`
  - `calendar_month_boundaries(period_ids: Sequence[str], *, model_year: int, period_hours: float, run_id: str) -> tuple[RuntimeCheckpointBoundary, ...]`
  - `checkpoint_content_sha256(checkpoint: SubannualCheckpoint | Mapping[str, object]) -> str`
  - `validate_subannual_checkpoint(checkpoint: SubannualCheckpoint, expected: SubannualCheckpointIdentity) -> None`
- Consumes: `JsonContract` and `contract_sha256` from the existing VALUE v2 contract layer.

- [ ] **Step 1: Write failing contract and chronology tests**

```python
class SubannualCheckpointContractTests(unittest.TestCase):
    def test_month_boundary_comes_from_frozen_reference_clock(self) -> None:
        boundaries = calendar_month_boundaries(
            (
                "2022-01-31:47",
                "2022-01-31:48",
                "2022-02-01:01",
                "2022-02-01:02",
            ),
            model_year=2028,
            period_hours=0.5,
            run_id="zonal-run",
        )
        self.assertEqual(len(boundaries), 1)
        self.assertEqual(boundaries[0].calendar_month, 1)
        self.assertEqual(boundaries[0].last_period_index, 1)
        self.assertEqual(boundaries[0].next_period_index, 2)
        self.assertEqual(boundaries[0].boundary_timestamp, "2028-02-01T00:00:00")
        self.assertEqual(boundaries[0].next_period_id, "2022-02-01:01")

    def test_unparseable_or_non_monotonic_clock_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "frozen chronology"):
            calendar_month_boundaries(
                ("2022-01-31:48", "bad-period-id"),
                model_year=2028,
                period_hours=0.5,
                run_id="zonal-run",
            )
```

Also assert that the JSON Schema has `$id == "urn:value:contract:subannual-checkpoint:v1"`, `additionalProperties == false`, and requires every exact field listed below.

- [ ] **Step 2: Run the focused tests and confirm the missing API failure**

Run:

```powershell
py -3.10 -m unittest tests.test_subannual_checkpoint tests.test_recovery_capability -v
```

Expected: FAIL because `gridform_core.subannual_checkpoint` and the completed schema do not exist.

- [ ] **Step 3: Define the exact v1 JSON envelope**

The schema must require these top-level fields and no others:

```json
{
  "schema_version": "value.subannual-checkpoint/v1",
  "checkpoint_id": "<run-id>:<model-year>:month-<01-12>:period-<index>",
  "run_id": "<run-id>",
  "model_year": 2028,
  "calendar_month": 3,
  "boundary_timestamp": "2028-04-01T00:00:00",
  "last_committed_period": 4319,
  "last_committed_period_id": "2022-03-31:48",
  "next_period": 4320,
  "next_period_id": "2022-04-01:01",
  "period_hours": 0.5,
  "chronology_sha256": "<64 lowercase hex>",
  "chronological_storage_state": [],
  "agent_observations": {},
  "writer_offsets": {},
  "random_generator_states": {},
  "year_to_date": {},
  "frozen_input_hashes": {},
  "frozen_module_hashes": {},
  "parent_annual_checkpoint_identity": {},
  "ledger_boundary": {},
  "publication_state": "verified",
  "content_sha256": "<64 lowercase hex>"
}
```

`checkpoint_content_sha256()` must canonicalize the payload after removing `content_sha256`; the manifest later hashes the complete file bytes separately. Validate required identity-map keys in Python so the schema remains implementation-neutral:

```python
REQUIRED_INPUT_IDENTITIES = frozenset({
    "study_revision_sha256",
    "resolved_run_sha256",
    "run_context_sha256",
    "year_context_sha256",
    "data_pack_id",
    "data_pack_manifest_sha256",
    "network_pack_id",
    "network_pack_manifest_sha256",
    "scientific_parameters_sha256",
    "runtime_controls_sha256",
})

REQUIRED_MODULE_IDENTITIES = frozenset({
    "module_graph_sha256",
    "psm_module_id",
    "psm_module_version",
    "balancing_module_id",
    "balancing_module_version",
    "solver_contract_id",
    "solver_contract_version",
})
```

- [ ] **Step 4: Implement strict half-hour settlement-period parsing**

Parse `YYYY-MM-DD:SS`, require `SS` from 1 to `round(24 / period_hours)`, derive interval starts and detect a boundary only when the next frozen period belongs to a new month. Keep the source `period_id` unchanged in the contract, but map only the human-readable `boundary_timestamp` to the model year. Hash the complete raw `period_ids`, `period_hours` and model year to form `chronology_sha256`.

- [ ] **Step 5: Declare capability only for the maintained zonal chain**

Update `recovery_capability()` to accept the selected module IDs and return `subannual_resume_supported=True` only when both maintained IDs are selected. The public manifest declares `value.subannual-checkpoint/v1`; a copperplate selection remains annual.

```python
supports_monthly = {
    "value-staged-bid-at-cost-psm",
    "value-zonal-redispatch-balancing",
}.issubset(set(modules))
```

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
py -3.10 -m unittest tests.test_subannual_checkpoint tests.test_recovery_capability -v
```

Expected: PASS.

Commit:

```powershell
git add gridform_core/subannual_checkpoint.py gridform_core/data/contracts/subannual-checkpoint-v1.schema.json gridform_core/manifests/value-staged-bid-at-cost-psm.json gridform_core/recovery_capability.py tests/test_subannual_checkpoint.py tests/test_recovery_capability.py
git commit -m "feat: complete zonal subannual checkpoint contract"
```

---

### Task 2: Add authoritative SQLite prefix verification and tail recovery

**Files:**
- Modify: `gridform_core/market_ledger.py:215-234,1664-1870,2125-2179,2448-2460`
- Modify: `gridform_core/failure_evidence.py:371-552`
- Modify: `tests/test_prompt120_market_ledger_v8.py`
- Modify: `tests/test_prompt121_failure_and_recovery.py`

**Interfaces:**
- Produces:
  - `MarketLedgerBoundary(JsonContract)`
  - `market_ledger_boundary(database: Path, *, year: int, committed_period: int) -> MarketLedgerBoundary`
  - `verify_v8_market_prefix(database: Path, *, boundary: MarketLedgerBoundary) -> Mapping[str, object]`
  - `recover_v8_market_prefix(database: Path, *, boundary: MarketLedgerBoundary, diagnostic_directory: Path, lease: MarketLedgerOwnershipLease) -> Mapping[str, object]`
- Consumes: `LedgerPrefixIdentity` from Task 1 and existing `PeriodIntegrity`, hash-chain projections and v8 schema metadata.

- [ ] **Step 1: Write failing all-table prefix tests**

Build a three-period full-trace v8 ledger, recover it to period 0, and assert:

```python
with sqlite3.connect(database) as connection:
    for table in PERIOD_INDEXED_V8_TABLES:
        self.assertEqual(
            connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE year=2025 AND period>0"
            ).fetchone()[0],
            0,
            table,
        )
    orphaned = connection.execute(
        "SELECT COUNT(*) FROM clearing_outcomes AS o "
        "LEFT JOIN clearing_inputs AS i ON i.input_sha256=o.input_sha256 "
        "WHERE i.input_sha256 IS NULL"
    ).fetchone()[0]
    self.assertEqual(orphaned, 0)
    row = connection.execute(
        "SELECT period_count, complete FROM year_integrity WHERE year=2025"
    ).fetchone()
    self.assertEqual(tuple(row), (1, 0))
```

Add cases for a missing middle period, tampered root, uncommitted WAL, injected deletion failure, unexpected `reliability_event` row, recovery followed by writing periods 1 and 2, and final annual seal.

- [ ] **Step 2: Run the ledger tests and confirm the missing prefix API failure**

Run:

```powershell
py -3.10 -m unittest tests.test_prompt120_market_ledger_v8 tests.test_prompt121_failure_and_recovery -v
```

Expected: FAIL because prefix verification and recovery functions are absent.

- [ ] **Step 3: Define the one authoritative list of period-indexed v8 tables**

The list must contain exactly:

```python
PERIOD_INDEXED_V8_TABLES = (
    "period_summary", "orders", "storage_state", "physical_dispatch",
    "clearing_inputs", "zonal_period_summary", "zonal_period_accounting",
    "vre_curtailment_period", "vre_curtailment_detail",
    "zonal_demand_alignment", "zone_period_summary",
    "boundary_period_summary", "zonal_resource_dispatch",
    "redispatch_settlement", "solver_declaration_link",
    "network_solver_diagnostics", "dispatch_summary", "storage_summary",
    "redispatch_summary", "period_integrity",
)
```

Add a schema-coverage assertion that fails whenever a future period-indexed table is created without entering this registry. `clearing_outcomes` is handled through the tail `clearing_inputs.input_sha256` set. `context_registry` remains. Any `reliability_event` for the incomplete year fails closed because those rows are annual products.

- [ ] **Step 4: Implement prefix identity and validation**

`MarketLedgerBoundary` must contain year, last committed period, period count, run/year context hashes, science/evidence roots, common/stored projection hashes, trace level, row-count JSON and trace-coverage JSON. `verify_v8_market_prefix()` replays the existing projection hash chain through the boundary and requires a continuous `0..N` prefix, matching contexts, roots and row counts.

- [ ] **Step 5: Implement diagnostic-first atomic tail recovery**

Follow the existing annual recovery publication pattern:

1. Open the live ledger read-only and verify the selected boundary.
2. Create a SQLite backup containing the untouched live database and WAL state.
3. Flush and hash the diagnostic copy, then publish it under `recovery-diagnostics/<sha256>/market.sqlite` with an immutable JSON manifest.
4. Require the actual product writer to have exited and acquire the same ledger ownership domain in the exclusive recovery role. Every `SQLiteMarketLedger` writer acquires the writer role before its first SQLite open and holds it until the connection closes.
5. On a second working copy, start `BEGIN IMMEDIATE`, delete tail `clearing_outcomes`, then every registered period table row with `period > N`, rewrite `year_integrity`, and exactly re-verify the prefix. Close, flush and hash this dry-run copy before touching live state.
6. Open the live ledger under the still-held recovery lease, set `synchronous=FULL`, start `BEGIN IMMEDIATE`, apply the identical deletion/rewrite, and exactly re-verify it inside the transaction. Commit through SQLite; this transaction/WAL protocol is the crash-consistent publication primitive. Do not use `os.replace` on the live database and do not manually delete or replace WAL/SHM.
7. If a pre-commit step fails, roll back the live transaction. The selected checkpoint and published diagnostic remain byte-for-byte unchanged. SQLite rollback preserves logical live-ledger contents, while WAL/SHM coordination bytes are implementation-managed and need not remain byte-identical. Directory-entry durability is best-effort on Windows because Python 3.10 exposes no enforceable directory-fsync operation.

- [ ] **Step 6: Run the ledger and annual-regression tests**

Run:

```powershell
py -3.10 -m unittest tests.test_prompt120_market_ledger_v8 tests.test_prompt121_failure_and_recovery tests.test_market_ledger_v6 -v
```

Expected: PASS, including all pre-existing annual recovery cases.

- [ ] **Step 7: Commit**

```powershell
git add gridform_core/market_ledger.py gridform_core/failure_evidence.py tests/test_prompt120_market_ledger_v8.py tests/test_prompt121_failure_and_recovery.py
git commit -m "feat: recover verified market ledger prefixes"
```

---

### Task 3: Make staged PSM year-to-date state solver-neutral and resumable

**Files:**
- Create: `gridform_core/builtin/scheme_c_1000twh/psm_runtime_state.py`
- Modify: `gridform_core/builtin/scheme_c_1000twh/runtime_compat/storage_cost.py:67-250,347-424`
- Modify: `gridform_core/zonal_redispatch.py:1344-1365,1536-1538,1744`
- Test: `tests/test_staged_psm_runtime_state.py`
- Test: `tests/test_dynamic_storage_cost.py`
- Test: `tests/test_prompt99_zonal_redispatch.py`

**Interfaces:**
- Produces:
  - `StagedPeriodOutcome(JsonContract)`
  - `StagedPSMRuntimeState(JsonContract)` with `initial()`, `apply_period()` and strict `from_dict()`
  - `snapshot_storage_cost_runtime(model: object) -> Mapping[str, object]`
  - `restore_storage_cost_runtime(model: object, payload: Mapping[str, object]) -> None`
  - `ZonalRedispatchBalancing.export_runtime_state() -> Mapping[str, object]`
  - `ZonalRedispatchBalancing.restore_runtime_state(state: Mapping[str, object]) -> None`
- Consumes: `PeriodSummary` and `NetworkSolverDiagnosticRow` as JSON mappings, never live class instances.

- [ ] **Step 1: Write a failing runtime-state round-trip test**

Create a two-period state, serialize it through JSON, restore it, apply the second outcome and compare it with an uninterrupted state. Assert every annual-result input exactly matches, including storage observations and balancing consumed-input hashes.

```python
restored = StagedPSMRuntimeState.from_dict(
    json.loads(json.dumps(after_first.to_dict(), sort_keys=True))
)
self.assertEqual(
    restored.apply_period(second).to_dict(),
    uninterrupted.to_dict(),
)
```

- [ ] **Step 2: Run focused tests and confirm the state type is absent**

Run:

```powershell
py -3.10 -m unittest tests.test_staged_psm_runtime_state tests.test_dynamic_storage_cost tests.test_prompt99_zonal_redispatch -v
```

Expected: FAIL on the missing runtime-state module.

- [ ] **Step 3: Define all state fields explicitly**

`StagedPSMRuntimeState` must contain:

```python
@dataclass(frozen=True)
class StagedPSMRuntimeState(JsonContract):
    run_id: str
    year: int
    next_period_index: int
    soc_mwh_by_asset: Mapping[str, float]
    storage_cost_state_by_asset: Mapping[str, Mapping[str, object]]
    balancing_state: Mapping[str, object]
    summaries: Sequence[Mapping[str, object]]
    ahead_hashes: Mapping[str, str]
    balancing_hashes: Mapping[str, str]
    generation_mwh_by_asset: Mapping[str, float]
    income_gbp_by_owner: Mapping[str, float]
    operating_cost_gbp: float
    operating_cost_gbp_by_class: Mapping[str, float]
    total_blackout_mwh: float
    total_excess_mwh: float
    total_export_mwh: float
    national_settlement_gbp_by_owner: Mapping[str, float]
    redispatch_settlement_gbp_by_owner: Mapping[str, float]
    actual_storage_discharge_mwh_by_asset: Mapping[str, float]
    final_dispatch_mwh_by_physical_asset: Mapping[str, float]
    last_soc_mwh_by_base_asset: Mapping[str, float]
    zonal_account_totals_gbp: Mapping[str, float]
    reliability_period_rows: Sequence[Mapping[str, object]]
    solver_diagnostic_rows: Sequence[Mapping[str, object]]
    schema_version: str = "value.staged-psm-runtime-state/v1"
```

`StagedPeriodOutcome` contains the one-period increments for the same accumulators plus the completed `PeriodSummary`, hashes, post-period SOC, storage-cost state and balancing state. Reject non-finite numeric values, a repeated/skipped period, changed run/year and duplicate period IDs.

- [ ] **Step 4: Add pure JSON storage-cost snapshot and restore**

Snapshot and restore `previous` and `current` annual observations, prepared year, pricing basis and all numeric pricing coefficients. Rebuild the pricing object from the frozen module and inputs first; then overwrite only these declared runtime fields. The user-formula compiled AST is reconstructed from the frozen formula and is never serialized.

- [ ] **Step 5: Add pure JSON zonal-balancing snapshot and restore**

Expose the consumed input SHA-256 sequence/set through public methods. Restore must require lowercase 64-hex hashes and reject any hash whose period is not strictly before `next_period_index`. Do not serialize solver models or results.

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
py -3.10 -m unittest tests.test_staged_psm_runtime_state tests.test_dynamic_storage_cost tests.test_prompt99_zonal_redispatch -v
```

Expected: PASS.

Commit:

```powershell
git add gridform_core/builtin/scheme_c_1000twh/psm_runtime_state.py gridform_core/builtin/scheme_c_1000twh/runtime_compat/storage_cost.py gridform_core/zonal_redispatch.py tests/test_staged_psm_runtime_state.py tests/test_dynamic_storage_cost.py tests/test_prompt99_zonal_redispatch.py
git commit -m "refactor: expose staged PSM runtime state"
```

---

### Task 4: Implement atomic checkpoint publication, discovery and retention

**Files:**
- Modify: `gridform_core/subannual_checkpoint.py`
- Modify: `tests/test_subannual_checkpoint.py`

**Interfaces:**
- Produces:
  - `SubannualCheckpointStore(root: Path)`
  - `SubannualCheckpointStore.publish(checkpoint: SubannualCheckpoint) -> RecoveryCandidate`
  - `SubannualCheckpointStore.discover(expected: SubannualCheckpointIdentity) -> tuple[RecoveryCandidate, ...]`
  - `SubannualCheckpointStore.load(checkpoint_id: str, expected: SubannualCheckpointIdentity) -> SubannualCheckpoint`
  - `SubannualCheckpointStore.prune_verified(*, year: int, keep: int = 2) -> None`
  - `SubannualCheckpointStore.supersede_with_annual(*, year: int, annual_checkpoint_sha256: str) -> None`
  - `SubannualCheckpointStore.claim(authorization: Mapping[str, object]) -> Path`
- Consumes: Task 1 contract and hashes; Task 2 ledger identity; Task 3 PSM state mapping.

- [ ] **Step 1: Add failing publication, corruption and retention tests**

Cover:

- temporary write failure leaves the previous verified manifest usable;
- file and canonical-content hashes are re-read and checked after atomic rename;
- three verified months retain February and March, not January;
- annual supersession removes only the completed year's monthly files;
- latest corrupt candidate is reported with its mismatch while the previous candidate is offered only as a separately selectable ID;
- two simultaneous claims of the same authorization produce exactly one winner.

- [ ] **Step 2: Run the test and confirm the store API is absent**

```powershell
py -3.10 -m unittest tests.test_subannual_checkpoint -v
```

Expected: FAIL on `SubannualCheckpointStore`.

- [ ] **Step 3: Implement the on-disk layout and atomic protocol**

Use:

```text
model-output/
  checkpoints-subannual-v1/
    manifest.json
    2028/
      month-02-period-2831.json
      month-03-period-4319.json
    claims/
      <authorization-id>.claim
```

Write JSON with sorted keys and a trailing newline to a sibling temporary file, flush and `os.fsync()`, `os.replace()`, re-read and validate, then atomically publish `manifest.json`. Manifest entries contain checkpoint ID, relative path, model year, calendar month, last/next period, boundary label, canonical content SHA-256 and complete-file SHA-256.

- [ ] **Step 4: Implement exact discovery semantics**

Return candidates newest first. Each candidate has `compatible`, `selectable`, `boundary_label`, `next_period_label`, `checkpoint_id` and optional `RecoveryMismatch(code, message, corrective_action)`. Do not skip a corrupt latest artifact silently and do not select the prior candidate automatically.

- [ ] **Step 5: Run tests and commit**

```powershell
py -3.10 -m unittest tests.test_subannual_checkpoint -v
git add gridform_core/subannual_checkpoint.py tests/test_subannual_checkpoint.py
git commit -m "feat: publish verified monthly checkpoints"
```

Expected: PASS and one commit.

---

### Task 5: Integrate monthly boundaries into the maintained zonal PSM

**Files:**
- Modify: `gridform_core/builtin/scheme_c_1000twh/staged_psm.py:499-627,1143-2435`
- Modify: `gridform_core/v2/interfaces.py:23-27`
- Modify: `tests/test_prompt101_staged_cem_integration.py`
- Create: `tests/test_zonal_subannual_resume.py`

**Interfaces:**
- Produces optional protocol:

```python
@runtime_checkable
class PSMSubannualCheckpointEngine(Protocol):
    def configure_subannual_checkpoint_sink(
        self,
        sink: Callable[[RuntimeCheckpointBoundary, Mapping[str, object], MarketLedgerBoundary], None] | None,
    ) -> None: ...

    def export_runtime_checkpoint(
        self, boundary: RuntimeCheckpointBoundary
    ) -> Mapping[str, object]: ...

    def restore_runtime_checkpoint(
        self, checkpoint: Mapping[str, object]
    ) -> None: ...
```

- Consumes: Task 1 boundaries, Task 2 committed ledger boundary, Task 3 state and Task 4 sink.

- [ ] **Step 1: Write failing three-month zonal parity tests**

Use a small dated Jan–Mar network fixture. Run continuously, then stop after January and restore into a fresh PSM instance. Compare complete `MarketYearResult.to_dict()` after deleting only operational checkpoint metadata. Separately compare period dispatch, SOC, boundary flows, redispatch, owner cash flow, costs, operational/overall carbon accumulators, VRE curtailment and SQLite science/evidence roots.

- [ ] **Step 2: Run the tests and observe non-resumable whole-year behavior**

```powershell
py -3.10 -m unittest tests.test_zonal_subannual_resume tests.test_prompt101_staged_cem_integration -v
```

Expected: FAIL because the staged PSM always starts at period 0 and exposes no checkpoint hooks.

- [ ] **Step 3: Refactor one period into compute, commit and apply phases**

The required order is:

```python
outcome = self._solve_period(...)
integrity = _record_period_batch_at_boundary(ledger, outcome.market_batch)
state = state.apply_period(outcome)
if outcome.period_index in month_boundary_by_period:
    boundary = month_boundary_by_period[outcome.period_index]
    ledger_boundary = market_ledger_boundary(
        ledger.path, year=model_input.year, committed_period=outcome.period_index
    )
    self._subannual_checkpoint_sink(
        boundary, self.export_runtime_checkpoint(boundary), ledger_boundary
    )
if self._period_boundary_cancellation is not None:
    self._period_boundary_cancellation(model_input.year, outcome.period_index)
```

Remove cancellation from `_record_period_batch_at_boundary()`. This ensures the state includes the just-committed period before either checkpointing or cancellation.

- [ ] **Step 4: Start or restore the runtime state explicitly**

For a new year use `StagedPSMRuntimeState.initial(...)`. For an explicitly supplied checkpoint, validate run, year, chronology and contexts; recreate storage-cost models from frozen inputs; restore their observations and balancing state; then iterate with:

```python
for period in range(state.next_period_index, len(chronology.period_ids)):
    ...
```

Do not renumber sliced periods. A checkpoint for another year or a `next_period_index` outside the chronology raises before a solver call.

- [ ] **Step 5: Gate monthly emission to the maintained zonal chain**

Emit only when a network pack is bound, balancing identity/version is exactly maintained v2, solver contract is `value.zonal-lexicographic/v2`, output ledger is active and a sink was explicitly configured. Copperplate and third-party paths execute the existing whole-year loop without monthly files.

- [ ] **Step 6: Preserve annual output construction**

Build `MarketYearResult`, storage reports, staged-year contract, reliability events, solver summary and ledger seal from `StagedPSMRuntimeState`. No formula or ledger definition changes. At end of year assert `state.next_period_index == len(chronology.period_ids)`.

- [ ] **Step 7: Run bounded parity tests and annual integration regressions**

```powershell
py -3.10 -m unittest tests.test_zonal_subannual_resume tests.test_prompt101_staged_cem_integration tests.test_native_checkpoint_resume -v
```

Expected: PASS. The copperplate annual-resume test remains unchanged.

- [ ] **Step 8: Commit**

```powershell
git add gridform_core/builtin/scheme_c_1000twh/staged_psm.py gridform_core/v2/interfaces.py tests/test_zonal_subannual_resume.py tests/test_prompt101_staged_cem_integration.py
git commit -m "feat: checkpoint zonal PSM at calendar months"
```

---

### Task 6: Wire explicit authorization, recovery and annual supersession

**Files:**
- Modify: `gridform_core/subannual_checkpoint.py`
- Modify: `gridform_core/application.py:113-225,999-1083,1281-1283,1689-1818`
- Modify: `gridform_core/v2/orchestrator.py:340-403,556-571`
- Modify: `tests/test_prompt121_failure_and_recovery.py`
- Modify: `tests/test_native_checkpoint_resume.py`
- Modify: `tests/test_zonal_subannual_resume.py`

**Interfaces:**
- Produces:
  - `subannual_recovery_authorization_id(value: Mapping[str, object]) -> str`
  - `issue_subannual_recovery_authorization(...) -> Mapping[str, object]`
  - `claim_subannual_recovery_authorization(...) -> Mapping[str, object]`
  - `run_project_application(..., resume_checkpoint_id: str | None = None) -> dict[str, object]`
- Consumes: exact Task 4 candidate ID and Task 2 recovery result.

- [ ] **Step 1: Write failing explicit-authorization tests**

Assert that:

- no `resume_checkpoint_id` means no monthly discovery, claim, cleanup or restore;
- an exact ID is bound to run ID, checkpoint hash, year, last/next period, RunContext, YearContext, source and nonce;
- states progress `issued -> presented -> consumed` once;
- a second process cannot consume the same claim;
- a mismatch is rejected before SQLite modification;
- cleanup failure leaves the authorization claimed, checkpoint immutable and live database unchanged;
- the annual v1 authorization path still recomputes an incomplete year for unsupported modules.

- [ ] **Step 2: Run recovery tests and confirm the new parameter is absent**

```powershell
py -3.10 -m unittest tests.test_prompt121_failure_and_recovery tests.test_native_checkpoint_resume tests.test_zonal_subannual_resume -v
```

Expected: FAIL on the missing explicit monthly authorization path.

- [ ] **Step 3: Implement a distinct authorization, not a second checkpoint contract**

Use `schema_version="value.subannual-recovery-authorization/v1"`. Its canonical ID binds:

```python
SUBANNUAL_AUTH_FIELDS = (
    "schema_version", "run_id", "checkpoint_id", "checkpoint_content_sha256",
    "model_year", "last_committed_period", "next_period",
    "run_context_sha256", "year_context_sha256", "source", "nonce",
)
```

Keep the existing annual authorization reader unchanged for old runs.

- [ ] **Step 4: Claim before diagnostics or cleanup**

When `resume_checkpoint_id` is supplied, load that exact artifact, validate all identities, atomically claim the authorization, run `recover_v8_market_prefix()`, and only then call `psm.restore_runtime_checkpoint()`. Record `resumed_from_checkpoint_id`, diagnostic URI/SHA and cleaned prefix in status evidence. Missing, corrupt, incompatible or claimed checkpoints raise before orchestration.

- [ ] **Step 5: Configure the sink without changing annual CEM sequencing**

Application code configures the optional PSM sink before `AnnualModelOrchestratorV2.run()`. The sink assembles the full `SubannualCheckpoint` from frozen run identities, PSM state and ledger boundary, then calls `SubannualCheckpointStore.publish()`. The orchestrator still sees one complete `MarketYearResult`; it never observes a monthly pseudo-year.

- [ ] **Step 6: Remove monthly files only after a verified annual checkpoint**

Wrap the existing annual JSON checkpoint writer so `supersede_with_annual(year=completed_year, annual_checkpoint_sha256=...)` runs only after the annual state file has been written, replaced and successfully reloaded. A failed annual write leaves the monthly files intact.

- [ ] **Step 7: Run recovery tests and commit**

```powershell
py -3.10 -m unittest tests.test_prompt121_failure_and_recovery tests.test_native_checkpoint_resume tests.test_zonal_subannual_resume -v
git add gridform_core/subannual_checkpoint.py gridform_core/application.py gridform_core/v2/orchestrator.py tests/test_prompt121_failure_and_recovery.py tests/test_native_checkpoint_resume.py tests/test_zonal_subannual_resume.py
git commit -m "feat: resume zonal runs from explicit checkpoints"
```

Expected: PASS.

---

### Task 7: Expose exact checkpoint selection through worker, CLI and local API

**Files:**
- Modify: `backend/model_runner.py:77-143,221-269,399-560,625-655`
- Modify: `backend/server.py:792-916,2250-2348,2814-2817`
- Create: `tests/test_model_runner_resume_cli.py`
- Create: `tests/test_checkpoint_resume_api.py`
- Modify: `tests/test_study_lifecycle_api.py`

**Interfaces:**
- Produces CLI: `--resume-from-checkpoint CHECKPOINT_ID`
- Produces API: `POST /api/runs/{run_id}/resume` with body `{"checkpoint_id": "..."}`
- Produces safe Run recovery summary; raw nonce and internal authorization hashes are never returned.
- Consumes: Task 6 `run_project_application(..., resume_checkpoint_id=...)`.

- [ ] **Step 1: Write failing CLI and API tests**

Test exact propagation, an empty body rejection for monthly recovery, exact candidate validation, Popen argv, source Study trash/missing gates, one-use claim, and stable 409 responses:

```json
{
  "error_code": "GF_RECOVERY_CHECKPOINT_INCOMPATIBLE",
  "error": "The selected checkpoint does not match the frozen Run inputs",
  "corrective_action": "Choose a compatible checkpoint or start a new Run."
}
```

Use these exact codes: `GF_RECOVERY_CHECKPOINT_MISSING`, `GF_RECOVERY_CHECKPOINT_CORRUPT`, `GF_RECOVERY_CHECKPOINT_INCOMPATIBLE`, `GF_RECOVERY_AUTHORIZATION_CLAIMED`.

- [ ] **Step 2: Run focused tests and confirm failure**

```powershell
py -3.10 -m unittest tests.test_model_runner_resume_cli tests.test_checkpoint_resume_api tests.test_study_lifecycle_api -v
```

Expected: FAIL because the CLI and endpoint ignore a checkpoint ID.

- [ ] **Step 3: Add explicit CLI propagation**

Change the worker signature to:

```python
def run(
    project_id: str,
    run_id: str,
    mode: str,
    *,
    resume_checkpoint_id: str | None = None,
) -> None:
    ...
```

`argparse` requires a string value after `--resume-from-checkpoint`. Without it, start/restart behavior is unchanged. Missing, claimed, corrupt and incompatible artifacts propagate to a non-zero process exit before a solver call.

- [ ] **Step 4: Make the API select and authorize one exact artifact**

Change `_resume_run()` and `_resume_run_locked()` to accept the parsed request body. Re-discover and validate the exact ID under the lifecycle lock, issue the authorization, mark the same immutable Run queued and append:

```python
["--resume-from-checkpoint", checkpoint_id]
```

to the worker command. Do not authorize automatically when a cancellation is recorded.

- [ ] **Step 5: Return a safe recovery summary**

`present_run()` returns status, boundary/next-period labels, checkpoint ID, candidate compatibility and the first mismatch/corrective action. Strip nonce, claim path and full frozen hashes. Detailed hashes remain in Inspect/audit artifacts.

- [ ] **Step 6: Run focused tests and commit**

```powershell
py -3.10 -m unittest tests.test_model_runner_resume_cli tests.test_checkpoint_resume_api tests.test_study_lifecycle_api -v
git add backend/model_runner.py backend/server.py tests/test_model_runner_resume_cli.py tests/test_checkpoint_resume_api.py tests/test_study_lifecycle_api.py
git commit -m "feat: select monthly checkpoints in local API"
```

Expected: PASS.

---

### Task 8: Make recovery choices truthful and distinct in the Runs UI

**Files:**
- Modify: `app/page.tsx:146-166,1696-1704,1884-1914`
- Modify: `tests/rendered-html.test.mjs`
- Create: `e2e/checkpoint-resume.spec.ts`

**Interfaces:**
- Consumes Task 7 recovery summary and POST body.
- Produces these exact primary labels:
  - `Resume from checkpoint`
  - `Run again`
  - `No compatible checkpoint`
  - `Create a separate copperplate comparison run`

- [ ] **Step 1: Write failing rendered and interaction tests**

Mock a failed zonal Run with a verified March candidate and assert the UI displays:

```text
Recoverable from 31 March 2028; next period 1 April 00:00
```

Clicking Resume must POST the exact checkpoint ID. Add separate cases for an unsupported annual-only module, no compatible checkpoint, a corrupt latest with a separately selectable prior checkpoint, and Run again creating a new Run ID.

- [ ] **Step 2: Run UI tests and confirm annual-only wording failure**

```powershell
node --test tests/rendered-html.test.mjs
npx playwright test e2e/checkpoint-resume.spec.ts --project=desktop-chromium
```

Expected: FAIL because `page.tsx` still hard-codes annual recovery and POSTs `{}`.

- [ ] **Step 3: Extend the frontend recovery types**

Model `candidate`, `previous_candidates`, `first_mismatch`, `subannual_resume_supported`, `annual_resume_supported` and safe authorization status. Do not put internal hashes or nonce in the TypeScript type.

- [ ] **Step 4: Render four explicit states**

1. Compatible monthly candidate: named boundary and `Resume from checkpoint`.
2. Annual-only module: `Recovery is annual for this module. An interrupted model year is recomputed from its verified opening checkpoint.`
3. Incompatible/corrupt: `No compatible checkpoint` plus exact corrective action; a previous checkpoint requires another explicit click.
4. No checkpoint: offer only `Run again`.

Keep a copperplate comparison action visually and semantically separate from recovery; remove the word `fallback` from that action.

- [ ] **Step 5: Run UI tests, lint and commit**

```powershell
node --test tests/rendered-html.test.mjs
npx playwright test e2e/checkpoint-resume.spec.ts --project=desktop-chromium
npm run lint
git add app/page.tsx tests/rendered-html.test.mjs e2e/checkpoint-resume.spec.ts
git commit -m "feat: show explicit checkpoint recovery choices"
```

Expected: all commands PASS.

---

### Task 9: Document recovery semantics and run the bounded acceptance gate

**Files:**
- Modify: `docs/USER_GUIDE.md`
- Modify: `docs/methodology/VALUE_METHODOLOGY.md`
- Modify: `docs/MODULE_BUILDER_101.md`
- Modify: `tests/test_documentation_consistency.py`
- Modify: `tests/test_zonal_subannual_resume.py`

**Interfaces:**
- Documents Task 1 optional module contract, Task 2 diagnostic recovery, Task 7 CLI/API behavior and Task 8 UI wording.
- Produces no scientific-model behavior.

- [ ] **Step 1: Write failing documentation assertions**

Assert that maintained docs contain all of:

```python
required = (
    "value.subannual-checkpoint/v1",
    "end of each calendar month",
    "Resume from checkpoint",
    "--resume-from-checkpoint",
    "latest two verified monthly checkpoints",
    "does not run the CEM",
    "does not fall back to copperplate",
)
```

- [ ] **Step 2: Run documentation and real-structure tests before editing**

```powershell
py -3.10 -m unittest tests.test_documentation_consistency tests.test_zonal_subannual_resume -v
```

Expected: documentation assertions FAIL while the earlier synthetic parity cases PASS.

- [ ] **Step 3: Document user, method and module-author behavior**

The user guide explains how to inspect the named boundary, resume the same immutable Run and start a different Run. The methodology states that monthly recovery is computational only and changes no clearing/CEM equations. The module guide gives the exact optional three-method protocol and states that a module without it remains annual-recovery compatible.

- [ ] **Step 4: Add the installed representative two-month gate**

Use the installed structurally representative zonal network fixture with a bounded chronology spanning two calendar boundaries. Run uninterrupted and one stop/resume path. Compare complete scientific output and authoritative ledger roots; exclude only timestamps, process IDs, checkpoint paths and recovery audit metadata. Do not invoke a production year.

- [ ] **Step 5: Run the complete bounded acceptance set**

```powershell
py -3.10 -m unittest tests.test_subannual_checkpoint tests.test_recovery_capability tests.test_prompt120_market_ledger_v8 tests.test_prompt121_failure_and_recovery tests.test_staged_psm_runtime_state tests.test_zonal_subannual_resume tests.test_native_checkpoint_resume tests.test_model_runner_resume_cli tests.test_checkpoint_resume_api tests.test_documentation_consistency -v
node --test tests/rendered-html.test.mjs
npx playwright test e2e/checkpoint-resume.spec.ts --project=desktop-chromium
npm run lint
```

Expected: PASS. No annual, two-year or ten-year production run starts.

- [ ] **Step 6: Verify spec coverage and source hygiene**

Run:

```powershell
$forbidden = @(("TO" + "DO"), ("T" + "BD"), ("implement" + " later"), "force-model\.org/contracts/subannual-checkpoint", "value\.psm-runtime-checkpoint")
rg -n ($forbidden -join "|") gridform_core/subannual_checkpoint.py gridform_core/data/contracts/subannual-checkpoint-v1.schema.json docs/USER_GUIDE.md docs/methodology/VALUE_METHODOLOGY.md docs/MODULE_BUILDER_101.md
git status --short
```

Expected: the search returns no matches; `git status` shows only pre-existing unrelated worktree changes, if any.

- [ ] **Step 7: Commit documentation and bounded gate**

```powershell
git add docs/USER_GUIDE.md docs/methodology/VALUE_METHODOLOGY.md docs/MODULE_BUILDER_101.md tests/test_documentation_consistency.py tests/test_zonal_subannual_resume.py
git commit -m "docs: explain zonal monthly recovery"
```

---

## Acceptance Traceability

| Approved requirement | Implementing task |
| --- | --- |
| Existing v1 contract, no duplicate | 1 |
| Real frozen-calendar month boundaries | 1, 5 |
| SQLite committed-prefix identity | 2 |
| Immutable diagnostic suffix and atomic cleanup | 2, 6 |
| Complete storage/PSM/accounting runtime state | 3, 5 |
| Solver-neutral export/restore | 3, 5 |
| Atomic publication and two-checkpoint retention | 4 |
| Explicit one-use authorization | 4, 6, 7 |
| CEM remains annual | 5, 6 |
| Annual checkpoint supersedes monthly files | 4, 6 |
| No silent downgrade or copperplate fallback | 4, 6, 7, 8 |
| CLI and frontend selection | 7, 8 |
| Three-month deterministic parity | 5, 9 |
| Mid-month diagnostic/truncate/recompute | 2, 6, 9 |
| Identity/corruption/atomicity gates | 1, 2, 4, 6 |
| Bounded real-structure validation | 9 |

## Plan Self-Review Result

- Spec coverage: every requirement in Sections 1–12 of the approved design maps to at least one task above.
- Placeholder scan: the plan contains no deferred implementation marker or unspecified error-handling step.
- Type consistency: `RuntimeCheckpointBoundary`, `SubannualCheckpointIdentity`, `MarketLedgerBoundary`, `StagedPSMRuntimeState`, `RecoveryCandidate` and `resume_checkpoint_id` keep the same names and roles across all dependent tasks.
- Scope check: output tracing, market science, CEM science, network expansion, copperplate checkpointing and current v2 run mutation remain outside this plan.
