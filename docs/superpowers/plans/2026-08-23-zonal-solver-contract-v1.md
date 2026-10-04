# Zonal Solver Contract v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace exact floating-point lexicographic locks in the experimental FORCE zonal redispatch module with a public, solver-aware numerical contract, make every setting and diagnostic reproducible, and then resume the interrupted Task 10 production gate.

**Architecture:** A small pure-Python solver-contract module owns validation, tolerance calculation, classification and annual aggregation. The zonal optimiser consumes that contract but does not relax physical constraints; project revisions, run snapshots, ledger v7, JSON exports and the frontend carry the same canonical contract and status. Existing study files and v5/v6 ledgers remain immutable and readable; execution derives a new v1.2 study copy instead of silently changing old identities.

**Tech Stack:** Python 3.10, dataclasses, NumPy, SciPy 1.8.1 `linprog`/HiGHS, SQLite, JSON Schema, unittest, TypeScript/React, Vite, Playwright, Git.

**Spec:** `docs/superpowers/specs/2026-08-23-zonal-solver-contract-v1-design.md`

## Global Constraints

- Scope is limited to `force-zonal-redispatch-balancing`; the copperplate PSM and CEM equations remain unchanged.
- Built-in validated solver stack is SciPy `1.8.1`, method `highs-ds`, primal tolerance `1e-9`, dual tolerance `1e-9`, presolve enabled, with no automatic solver or copperplate fallback.
- Allowed methods are `highs-ds`, `highs-ipm` and `highs`; primal and dual tolerances are `1e-10` through `1e-7`, and IPM optimality tolerance is `1e-12` through `1e-7`.
- Lexicographic locks are one-sided inequalities. Physical balance, SOC, capacity, transfer and settlement tolerances are not changed.
- Objective floors are `1e-8 GBP` for primary redispatch bid cost and `1e-9 MWh` for secondary deviation and physical throughput.
- Built-in validated ceilings per half-hour are `0.01 GBP`, `0.001 MWh`, `0.001 MWh`; immutable execution ceilings are `0.10 GBP`, `0.01 MWh`, `0.01 MWh`.
- The default warning fraction is `0.10`; values above a validated ceiling continue only while at or below the immutable execution ceiling and make Prompt 107 `NO-GO`.
- The fourth stable-key objective is final and is never locked; its coefficient ordering is fixed for module version `1.2.0`.
- Module `force-zonal-redispatch-balancing` advances from `1.1.0` to `1.2.0` and remains Experimental and non-default.
- New runs write `gridform.market-ledger/v7`; v5 and v6 completed ledgers remain read-only and are never rewritten.
- Old project and Prompt 104 source files remain byte-for-byte unchanged. Execution uses a derived copy with source SHA-256, migration reason and new revision SHA-256.
- Third-party solver contracts may differ, but v7 evidence and the universal physical, SOC, capacity, settlement and ledger validators remain mandatory.
- Task 10 stops at the first failed gate. Prompt 105 and both ten-year studies are outside this plan.

## File Structure

- `gridform_core/zonal_solver_contract.py` — canonical settings, validation, numerical tolerance, classification, runtime stack identity and annual aggregation.
- `gridform_core/data/contracts/network-solver-contract-v1.schema.json` — portable project/export schema for the solver contract.
- `gridform_core/zonal_redispatch.py` — four-phase optimisation, one-sided locks, failure preservation and period diagnostics.
- `gridform_core/v2/module_manifest.py` and `gridform_core/manifests/force-zonal-redispatch-balancing.json` — optional manifest declaration and built-in v1.2 contract metadata.
- `gridform_core/frontend_contract.py`, `gridform_core/project_revision.py`, `gridform_core/run_snapshot.py`, `scripts/run_prompt107_production_gate.py` — project validation, fingerprinting and explicit old-study derivation.
- `gridform_core/data/contracts/market-ledger-v7.schema.sql` and `gridform_core/market_ledger.py` — normalized period/phase solver evidence and read compatibility.
- `gridform_core/application.py` and `gridform_core/zonal_results.py` — status propagation, annual summary, bounded queries and JSON export.
- `app/page.tsx`, `app/features/network/networkRedispatch.ts`, `app/features/network/NetworkRedispatchView.tsx`, `app/globals.css` — advanced settings and compact run evidence.
- `docs/MATHEMATICAL_REFERENCE.md`, `docs/USER_GUIDE.md`, `docs/MODULE_DEVELOPER_101.md`, `docs/BUILD_YOUR_OWN_MODEL_101.md` — public method and usage documentation.
- `scripts/generate_reference_tables.py`, `docs/generated/MODULES.md`, `source-release-manifest.json` — generated references and source product completeness.

---

### Task 1: Canonical Numerical Solver Contract

**Files:**
- Create: `gridform_core/zonal_solver_contract.py`
- Create: `gridform_core/data/contracts/network-solver-contract-v1.schema.json`
- Create: `tests/test_zonal_solver_contract.py`

**Interfaces:**
- Consumes: only Python standard library, NumPy machine precision and declared scalar inputs.
- Produces: `ZonalSolverSettings`, `ObjectiveLockDiagnostic`, `SolverStackIdentity`, `DEFAULT_ZONAL_SOLVER_SETTINGS`, `validate_solver_settings(payload: Mapping[str, object]) -> ZonalSolverSettings`, `compute_lock_tolerance(coefficients: np.ndarray, optimum: np.ndarray, unit_floor: float, solver_tolerance: float) -> LockTolerance`, `classify_lock(degradation: float, computed_tolerance: float, validated_ceiling: float, warning_fraction: float, absolute_ceiling: float) -> LockClassification`, `summarise_solver_diagnostics(rows: Iterable[ObjectiveLockDiagnostic]) -> dict[str, object]` and `solver_stack_identity() -> SolverStackIdentity`.

- [ ] **Step 1: Write failing tests for defaults, bounds and canonical serialization**

```python
import copy
import unittest

from gridform_core.zonal_solver_contract import (
    DEFAULT_ZONAL_SOLVER_SETTINGS,
    validate_solver_settings,
)

class ZonalSolverSettingsTests(unittest.TestCase):
    def test_default_contract_is_the_validated_baseline(self):
        settings = DEFAULT_ZONAL_SOLVER_SETTINGS
        self.assertEqual(settings.schema_version, "force.network-solver-contract/v1")
        self.assertEqual(settings.contract_version, "force.zonal-lexicographic/v1")
        self.assertEqual(settings.method, "highs-ds")
        self.assertEqual(settings.primal_feasibility_tolerance, 1e-9)
        self.assertEqual(settings.dual_feasibility_tolerance, 1e-9)
        self.assertIs(settings.presolve, True)
        self.assertIs(settings.is_builtin_default, True)

    def test_nondefault_settings_are_valid_but_not_builtin_validated(self):
        payload = copy.deepcopy(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        payload["method"] = "highs-ipm"
        payload["ipm_optimality_tolerance"] = 1e-10
        settings = validate_solver_settings(payload)
        self.assertIs(settings.is_builtin_default, False)
        self.assertIs(settings.requires_acknowledgement, True)

    def test_execution_ceiling_cannot_be_overridden(self):
        payload = copy.deepcopy(DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict())
        payload["absolute_ceilings"]["primary_bid_cost_gbp"] = 0.11
        with self.assertRaisesRegex(ValueError, "immutable execution ceiling"):
            validate_solver_settings(payload)
```

- [ ] **Step 2: Run the new test and confirm RED**

Run: `python -m unittest tests.test_zonal_solver_contract -v`

Expected: import failure for `gridform_core.zonal_solver_contract`.

- [ ] **Step 3: Implement immutable settings and schema validation**

Use these public types and constants exactly:

```python
@dataclass(frozen=True)
class ZonalSolverSettings:
    schema_version: str
    contract_version: str
    method: str
    presolve: bool
    primal_feasibility_tolerance: float
    dual_feasibility_tolerance: float
    ipm_optimality_tolerance: float
    warning_fraction: float
    validated_ceilings: Mapping[str, float]
    absolute_ceilings: Mapping[str, float]
    is_builtin_default: bool
    requires_acknowledgement: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "contract_version": self.contract_version,
            "method": self.method,
            "presolve": self.presolve,
            "primal_feasibility_tolerance": self.primal_feasibility_tolerance,
            "dual_feasibility_tolerance": self.dual_feasibility_tolerance,
            "ipm_optimality_tolerance": self.ipm_optimality_tolerance,
            "warning_fraction": self.warning_fraction,
            "validated_ceilings": dict(self.validated_ceilings),
            "absolute_ceilings": dict(self.absolute_ceilings),
            "is_builtin_default": self.is_builtin_default,
            "requires_acknowledgement": self.requires_acknowledgement,
        }

DEFAULT_VALIDATED_CEILINGS = {
    "primary_bid_cost_gbp": 0.01,
    "secondary_schedule_deviation_mwh": 0.001,
    "physical_throughput_mwh": 0.001,
}
ABSOLUTE_EXECUTION_CEILINGS = {
    "primary_bid_cost_gbp": 0.10,
    "secondary_schedule_deviation_mwh": 0.01,
    "physical_throughput_mwh": 0.01,
}
```

The JSON schema must set `additionalProperties: false`, require every public field, enumerate the three methods, and encode the approved numeric ranges. `absolute_ceilings` is exported for audit but validation must reject any value unequal to the immutable constants.

- [ ] **Step 4: Write failing formula and classification tests**

```python
class LockFormulaTests(unittest.TestCase):
    def test_lock_tolerance_uses_largest_declared_term(self):
        result = compute_lock_tolerance(
            coefficients=np.array([2.0, -3.0, 0.0]),
            optimum=np.array([4.0, 5.0, 7.0]),
            unit_floor=1e-8,
            solver_tolerance=1e-9,
        )
        self.assertEqual(result.nonzero_terms, 2)
        self.assertEqual(result.absolute_term_scale, 23.0)
        self.assertAlmostEqual(
            result.tolerance,
            max(1e-8, 23e-9, result.gamma_n * 23.0),
        )

    def test_classification_thresholds_are_one_sided(self):
        self.assertEqual(classify_lock(0.0005, 0.001, 0.01, 0.10, 0.10).status, "GO")
        self.assertEqual(classify_lock(0.002, 0.002, 0.01, 0.10, 0.10).status, "GO_WITH_NUMERICAL_WARNING")
        self.assertEqual(classify_lock(0.011, 0.012, 0.01, 0.10, 0.10).status, "COMPLETED_WITH_NUMERICAL_WARNING")
        with self.assertRaisesRegex(ZonalSolverContractError, "absolute ceiling"):
            classify_lock(0.11, 0.12, 0.01, 0.10, 0.10)
```

- [ ] **Step 5: Implement formula, diagnostics and annual aggregation**

```python
@dataclass(frozen=True)
class ObjectiveLockDiagnostic:
    phase_id: str
    objective_unit: str
    optimum: float
    achieved_final_value: float
    degradation: float
    computed_tolerance: float
    validated_ceiling: float
    absolute_ceiling: float
    nonzero_terms: int
    absolute_term_scale: float
    validation_class: str
    error_code: str | None = None

def compute_lock_tolerance(*, coefficients, optimum, unit_floor, solver_tolerance):
    mask = coefficients != 0.0
    n = int(np.count_nonzero(mask))
    scale = float(np.sum(np.abs(coefficients[mask] * optimum[mask])))
    epsilon = float(np.finfo(float).eps)
    gamma_n = float(n * epsilon / (1.0 - n * epsilon))
    tolerance = max(float(unit_floor), float(solver_tolerance) * max(1.0, scale), gamma_n * scale)
    # Reject n <= 0 and every non-finite intermediate before returning.
```

`summarise_solver_diagnostics` returns each locked phase's `max_tolerance`, `max_degradation`, `periods_above_warning_fraction`, `periods_above_validated_ceiling`, and `cumulative_absolute_degradation`; study status is the worst period status.

`classify_lock` computes `ceiling_use = max(degradation, computed_tolerance) / validated_ceiling`, first rejects `max(degradation, computed_tolerance) > absolute_ceiling`, and then applies the approved 10% and 100% boundaries. It separately rejects `degradation > computed_tolerance` as `GF_ZONAL_OBJECTIVE_LOCK_VIOLATION`.

- [ ] **Step 6: Record the exact embedded solver identity**

`solver_stack_identity()` imports SciPy and `scipy.optimize._highs._highs_wrapper`, records `scipy.__version__`, resolves the extension module's absolute file, hashes its bytes as `highs_binary_sha256`, and emits `highs_identity = "scipy-embedded-highs:<sha256>"`. A missing or unreadable extension binary is a hard `GF_ZONAL_SOLVER_IDENTITY_UNAVAILABLE` failure; do not infer a HiGHS version from a solver status message. Add a test that patches the module path to known bytes and asserts the exact digest.

- [ ] **Step 7: Run contract tests and the schema parser test**

Run: `python -m unittest tests.test_zonal_solver_contract -v`

Expected: all tests pass, including non-finite inputs, invalid term count, range endpoints and JSON round-trip.

- [ ] **Step 8: Commit Task 1**

```bash
git add gridform_core/zonal_solver_contract.py gridform_core/data/contracts/network-solver-contract-v1.schema.json tests/test_zonal_solver_contract.py
git commit -m "feat(network): define zonal solver contract"
```

### Task 2: Numerical Lexicographic Optimiser and Module v1.2

**Files:**
- Modify: `gridform_core/zonal_redispatch.py`
- Modify: `gridform_core/v2/module_manifest.py`
- Modify: `gridform_core/manifests/force-zonal-redispatch-balancing.json`
- Modify: `tests/test_prompt99_zonal_redispatch.py`
- Create: `tests/fixtures/zonal_solver_failures/period-2025-14.json`
- Create: `tests/fixtures/zonal_solver_failures/period-bound-noise.json`

**Interfaces:**
- Consumes: Task 1 settings and diagnostic types.
- Produces: `ZonalRedispatchBalancing(solver_settings: ZonalSolverSettings | None = None, evidence_root: Path | None = None)`, per-period `network_solver_diagnostics`, and manifest field `solver_contract` exposed as a mapping by `ModuleManifest`.

- [ ] **Step 1: Preserve the two failing declared inputs as content-addressed fixtures**

Copy only the declared-input JSON objects from retained Task 10 failure evidence. Add `source_sha256` and assert fixture canonical SHA-256 in tests. Do not edit the original Task 10 output directories.

- [ ] **Step 2: Write failing solver tests for one-sided locks and fixed method settings**

```python
class NumericalLexicographicTests(unittest.TestCase):
    def test_later_phases_use_one_sided_caps(self):
        model_input, _module = _input(
            {"north": 0.0, "south": 10.0},
            {"cheap": 10.0, "local": 0.0},
            {"cheap": "north", "local": "south"},
            (
                _bid("cheap-down", "cheap", "north", "down", 10.0, 0.0, baseline_mw=10.0),
                _bid("local-up", "local", "south", "up", 10.0, 100.0),
            ),
            pack=_pack({"north": 0.0, "south": 10.0}, forward_limit_mw=4.0),
        )
        problem = build_single_period_problem(model_input)
        with patch("scipy.optimize.linprog", wraps=linprog) as wrapped:
            solution = solve_lexicographic(problem, DEFAULT_ZONAL_SOLVER_SETTINGS)
        calls = wrapped.call_args_list
        self.assertEqual(calls[0].kwargs["method"], "highs-ds")
        self.assertEqual(calls[0].kwargs["options"], {
        "presolve": True,
        "primal_feasibility_tolerance": 1e-9,
        "dual_feasibility_tolerance": 1e-9,
        })
        base_rows = len(problem.inequality_matrix)
        self.assertEqual(
            [len(call.kwargs["A_ub"]) for call in calls],
            [base_rows, base_rows + 1, base_rows + 2, base_rows + 3],
        )
        self.assertIs(solution.diagnostics["automatic_copperplate_fallback"], False)

    def test_final_solution_recomputes_all_locked_objectives(self):
        model_input = balancing_input_from_fixture(FIXTURE_ROOT / "period-2025-14.json")
        problem = build_single_period_problem(model_input)
        result = solve_lexicographic(problem, DEFAULT_ZONAL_SOLVER_SETTINGS)
        self.assertEqual(len(result.network_solver_diagnostics), 3)
        self.assertTrue(all(
            row.degradation <= row.computed_tolerance
            for row in result.network_solver_diagnostics
        ))
```

Define `balancing_input_from_fixture(path: Path) -> BalancingInput` in the test module by reading `declared_input`, replacing its `bids` list with `tuple(FlexibilityBid(**dict(item)) for item in payload["bids"])`, and then calling `BalancingInput(**payload)`. This preserves the original domain payload, including `ZonalNetworkPack.from_dict` input, without a production-only fixture parser.

- [ ] **Step 3: Run the targeted tests and confirm RED**

Run: `python -m unittest tests.test_prompt99_zonal_redispatch.ZonalRedispatchSolverContractTests -v`

Expected: exact equality locks or missing solver-contract fields cause failure.

- [ ] **Step 4: Replace exact equality locks with a phase runner**

Implement this sequence without changing the physical matrices:

```python
def solve_lexicographic(
    problem: SinglePeriodProblem,
    settings: ZonalSolverSettings,
) -> SinglePeriodSolution:
    primary = _run_highs(problem, problem.primary_objective, phase="primary_bid_cost", settings=settings)
    primary_lock = _objective_cap(problem.primary_objective, primary.values, settings, "primary_bid_cost_gbp")
    secondary = _run_highs(problem, problem.secondary_objective, phase="secondary_schedule_deviation", settings=settings, locks=(primary_lock,))
    secondary_lock = _objective_cap(problem.secondary_objective, secondary.values, settings, "secondary_schedule_deviation_mwh")
    physical = _run_highs(problem, problem.physical_tie_objective, phase="physical_throughput", settings=settings, locks=(primary_lock, secondary_lock))
    physical_lock = _objective_cap(problem.physical_tie_objective, physical.values, settings, "physical_throughput_mwh")
    final = _run_highs(problem, problem.stable_tie_objective, phase="stable_key", settings=settings, locks=(primary_lock, secondary_lock, physical_lock))
    return _finalise_solution(problem, final, (primary_lock, secondary_lock, physical_lock), settings)
```

Each lock appends one inequality row `c_k` with RHS `f_k(x*) + tau_k`. Preserve bounded solution canonicalisation: a value within the existing physical `TOLERANCE` snaps to its declared bound; a larger violation raises `ZonalRedispatchSolveError`.

- [ ] **Step 5: Preserve failure evidence at every phase**

On solver failure, non-finite diagnostics, lock violation or absolute-ceiling violation, write the declared input SHA-256, settings, stack identity, completed phase optima/tolerances, raw status/message and error code before raising. Never retry with another method.

- [ ] **Step 6: Extend manifest parsing and bump the module**

Add `solver_contract: Mapping[str, object] = field(default_factory=dict)` to `ModuleManifest`, parse it with `values["solver_contract"] = dict(values.get("solver_contract") or {})`, and include it in `to_dict()`. The manifest must declare version `1.2.0`, scientific version `force-lossless-zonal-redispatch-2026.08.23`, output capability `evidence.network-solver-diagnostics/v7`, schema path, defaults, ranges, immutable ceilings and the fixed stable-key rule.

- [ ] **Step 7: Add mutation and deterministic random tests**

Test cancellation, bound noise, analytical three-phase cases, seeded random convex cases and deliberate primary/secondary/physical degradation. A mutation above each absolute ceiling must fail and preserve the declared input. A mutation between validated and absolute ceilings must complete unvalidated.

Use a high-scale but feasible synthetic objective to make the computed `tau_k` exceed the validated ceiling while the observed degradation remains within `tau_k`; do not accept a deliberately injected `degradation > tau_k`. Add one insertion-order test proving that shuffled bid and asset input order produces the same stable-key asset dispatch and result SHA-256.

- [ ] **Step 8: Run Task 2 regressions**

Run:

```text
python -m unittest tests.test_zonal_solver_contract tests.test_prompt99_zonal_redispatch tests.test_force_actual_random_clearing -v
```

Expected: all tests pass; the retained 24-hour failure period completes without changing physical residual tolerances.

- [ ] **Step 9: Commit Task 2**

```bash
git add gridform_core/zonal_redispatch.py gridform_core/v2/module_manifest.py gridform_core/manifests/force-zonal-redispatch-balancing.json tests/test_prompt99_zonal_redispatch.py tests/fixtures/zonal_solver_failures
git commit -m "fix(network): use numerical lexicographic locks"
```

### Task 3: Project Identity, Validation and Explicit Study Derivation

**Files:**
- Modify: `gridform_core/frontend_contract.py`
- Modify: `gridform_core/project_revision.py`
- Modify: `gridform_core/run_snapshot.py`
- Modify: `backend/server.py`
- Modify: `scripts/run_prompt107_production_gate.py`
- Modify: `tests/test_application_service.py`
- Modify: `tests/test_run_input_snapshot.py`
- Modify: `tests/test_prompt107_production_gate.py`
- Create: `tests/test_zonal_solver_project_contract.py`

**Interfaces:**
- Consumes: Task 1 `validate_solver_settings` and Task 2 manifest v1.2.
- Produces: root project field `solver_contract`, acknowledgement key `solver-contract:force-zonal-redispatch-balancing@1.2.0`, and `derive_zonal_execution_project(source_bytes: bytes, registry: ModuleRegistryV2, data_pack_manifest: Mapping[str, object]) -> tuple[dict[str, object], dict[str, object]]` evidence.

- [ ] **Step 1: Write failing project validation and fingerprint tests**

```python
class ZonalSolverProjectContractTests(unittest.TestCase):
    def setUp(self):
        self.registry = builtin_registry()
        self.pack = json.loads((ROOT / "data-packs/force-synthetic-contract-pack-v1/manifest.json").read_text())
        source = (ROOT / "publication/prompt104-zonal-study.json").read_bytes()
        self.baseline, _evidence = derive_zonal_execution_project(
            source,
            registry=self.registry,
            data_pack_manifest=self.pack,
        )

    def resolve(self, project):
        return resolve_study_draft(
            project,
            registry=self.registry,
            module_catalog=[row.to_dict() for row in self.registry.manifests().values()],
            base_dataset_slots=(),
            available_data_roles=tuple((self.pack.get("bindings") or {}).keys()),
        )

    def test_solver_contract_changes_project_fingerprint(self):
        custom = copy.deepcopy(self.baseline)
        custom["solver_contract"]["dual_feasibility_tolerance"] = 1e-8
        self.assertNotEqual(
            project_fingerprint(self.baseline, self.registry, self.pack),
            project_fingerprint(custom, self.registry, self.pack),
        )

    def test_custom_contract_requires_single_save_acknowledgement(self):
        project = copy.deepcopy(self.baseline)
        project["solver_contract"]["dual_feasibility_tolerance"] = 1e-8
        result = self.resolve(project)
        self.assertIn("GF_SOLVER_CONTRACT_ACK_REQUIRED", {row["code"] for row in result["errors"]})

    def test_copperplate_rejects_zonal_solver_contract(self):
        project = copy.deepcopy(self.baseline)
        project["modules"]["balancing"] = "force-copperplate-balancing"
        result = self.resolve(project)
        self.assertIn("GF_SOLVER_CONTRACT_MODULE_MISMATCH", {row["code"] for row in result["errors"]})
```

- [ ] **Step 2: Run project tests and confirm RED**

Run: `python -m unittest tests.test_zonal_solver_project_contract -v`

Expected: `solver_contract` is currently an unknown draft field.

- [ ] **Step 3: Add canonical validation and identity**

Add `solver_contract` to `ALLOWED_DRAFT_FIELDS`. Require it only when the selected balancing module declares a solver contract. Validate exact schema, module identity and settings. Add the canonical validated dictionary to `canonical_project_payload`, so checkpoints and exports inherit it through the existing project revision and run snapshot paths.

- [ ] **Step 4: Implement explicit derivation for old studies**

```python
def derive_zonal_execution_project(
    source_bytes: bytes,
    *,
    registry: ModuleRegistryV2,
    data_pack_manifest: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    candidate = json.loads(source_bytes)
    # Move the experimental acknowledgement from the selected old version to 1.2.0.
    # Add DEFAULT_ZONAL_SOLVER_SETTINGS only to the derived candidate.
    # Recompute revision_sha256 through attach_revision_identity.
    return candidate, {
        "schema_version": "force.study-execution-derivation/v1",
        "source_sha256": source_sha256,
        "reason": "zonal-module-1.2-solver-contract-migration",
        "derived_revision_sha256": candidate["revision_sha256"],
    }
```

The production runner must read and hash original Prompt 104 bytes before derivation, assert they are unchanged afterwards, and write derived files only beneath the new Task 10 output root.

- [ ] **Step 5: Test API save semantics and snapshot round-trip**

POSTing a non-default contract without acknowledgement returns a structured 422 validation response. Saving with acknowledgement creates exactly one new revision; subsequent run launch does not ask again. The run snapshot must reproduce the same solver-contract dictionary and project revision SHA-256.

- [ ] **Step 6: Run Task 3 regressions**

Run:

```text
python -m unittest tests.test_zonal_solver_project_contract tests.test_application_service tests.test_run_input_snapshot tests.test_prompt107_production_gate -v
```

Expected: all pass, including byte-for-byte original study hash assertions.

- [ ] **Step 7: Commit Task 3**

```bash
git add gridform_core/frontend_contract.py gridform_core/project_revision.py gridform_core/run_snapshot.py backend/server.py scripts/run_prompt107_production_gate.py tests/test_zonal_solver_project_contract.py tests/test_application_service.py tests/test_run_input_snapshot.py tests/test_prompt107_production_gate.py
git commit -m "feat(studies): fingerprint zonal solver settings"
```

### Task 4: Market Ledger v7 and Status Propagation

**Files:**
- Create: `gridform_core/data/contracts/market-ledger-v7.schema.sql`
- Modify: `gridform_core/market_ledger.py`
- Modify: `gridform_core/application.py`
- Modify: `gridform_core/zonal_results.py`
- Modify: `tests/test_market_ledger.py`
- Modify: `tests/test_prompt100_zonal_ledger.py`
- Modify: `tests/test_prompt101_staged_cem_integration.py`
- Modify: `tests/test_prompt102_zonal_results_api.py`

**Interfaces:**
- Consumes: Task 2 period diagnostics and Task 1 annual aggregator.
- Produces: `NetworkSolverDiagnosticRow`, `record_network_solver_diagnostics(rows)`, ledger v7 table `network_solver_diagnostics`, annual/study `solver_validation_summary`, and bounded result view `solver-diagnostics`.

- [ ] **Step 1: Write failing v7 schema and round-trip tests**

```python
class MarketLedgerV7Tests(unittest.TestCase):
    def test_v7_round_trips_one_row_per_locked_phase(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="full")
            ledger.record_network_solver_diagnostics(_three_phase_diagnostic_rows())
            ledger.close()
            connection = sqlite3.connect(database)
            phases = [row[0] for row in connection.execute(
                "SELECT phase_id FROM network_solver_diagnostics ORDER BY rowid"
            )]
            connection.close()
        self.assertEqual(phases, [
            "primary_bid_cost", "secondary_schedule_deviation", "physical_throughput"
        ])

    def test_v5_and_v6_are_read_only_but_queryable(self):
        for version in ("v5", "v6"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as folder:
                database = Path(folder) / "market.sqlite"
                _create_legacy_ledger(database, version)
                report = validate_market_ledger_file(database)
                self.assertIs(report["valid"], True)
                self.assertEqual(report["schema_version"], f"gridform.market-ledger/{version}")
                with self.assertRaisesRegex(InvariantError, "read-only"):
                    SQLiteMarketLedger(database, trace_level="full")
```

Implement `_three_phase_diagnostic_rows()` with three concrete `NetworkSolverDiagnosticRow` instances sharing run/year/period and using the approved GBP/MWh units and ceilings. Implement `_create_legacy_ledger(database, version)` by executing the repository's `market-ledger-v5.schema.sql` or `market-ledger-v6.schema.sql` and inserting the matching `metadata.schema_version`; do not commit binary SQLite fixtures.

- [ ] **Step 2: Run ledger tests and confirm RED**

Run: `python -m unittest tests.test_market_ledger tests.test_prompt100_zonal_ledger -v`

Expected: v7 schema and row recorder are missing.

- [ ] **Step 3: Create normalized v7 SQL and row type**

The table primary key is `(run_id, year, period, phase_id)` and contains the spec's required columns with `CHECK` constraints for units and validation classes. Add:

```python
@dataclass(frozen=True)
class NetworkSolverDiagnosticRow:
    run_id: str
    year: int
    period: int
    period_id: str
    phase_id: str
    module_id: str
    module_version: str
    solver_contract_version: str
    scipy_version: str
    highs_identity: str
    highs_binary_sha256: str
    method: str
    presolve: bool
    primal_feasibility_tolerance: float
    dual_feasibility_tolerance: float
    ipm_optimality_tolerance: float | None
    objective_unit: str
    optimum: float
    achieved_final_value: float
    degradation: float
    computed_tolerance: float
    warning_ceiling: float
    validated_ceiling: float
    absolute_ceiling: float
    nonzero_term_count: int
    absolute_term_scale: float
    validation_class: str
    error_code: str | None
    declared_input_sha256: str
```

Set `SCHEMA_VERSION = "gridform.market-ledger/v7"`; legacy versions become v4, v5 and v6. Initialize only v7 for new runs and never upgrade an existing database in place.

- [ ] **Step 4: Wire period evidence and study status through the live chain**

After each zonal result, record its three locked-phase rows. Aggregate at the end of each year and attach `solver_validation_summary` to annual results. If any period exceeds the validated ceiling, continue CEM and mark that year and every later year `solver_validated=false`; preserve the first causal period and class in study state.

- [ ] **Step 5: Add bounded query and JSON export support**

Map public view `solver-diagnostics` to `network_solver_diagnostics`. Permit filters only for run, year, period and phase. Return a compact summary in the main network payload and a bounded paginated table/export for details; do not accept raw SQL or arbitrary column names.

- [ ] **Step 6: Test CEM warning propagation and accounting strictness**

Inject a diagnostic between validated and absolute ceilings, then assert 2025 PSM completes, CEM executes, 2026 is marked inherited-unvalidated, and physical/settlement validators still fail on an independently mutated imbalance.

- [ ] **Step 7: Run Task 4 regressions**

Run:

```text
python -m unittest tests.test_market_ledger tests.test_prompt100_zonal_ledger tests.test_prompt101_staged_cem_integration tests.test_prompt102_zonal_results_api tests.test_prompt103_zonal_validation -v
```

Expected: all pass; SQLite integrity is `ok` and JSON values reconcile exactly with SQL rows.

- [ ] **Step 8: Commit Task 4**

```bash
git add gridform_core/data/contracts/market-ledger-v7.schema.sql gridform_core/market_ledger.py gridform_core/application.py gridform_core/zonal_results.py tests/test_market_ledger.py tests/test_prompt100_zonal_ledger.py tests/test_prompt101_staged_cem_integration.py tests/test_prompt102_zonal_results_api.py tests/test_prompt103_zonal_validation.py
git commit -m "feat(results): record solver evidence in ledger v7"
```

### Task 5: Advanced Solver Settings and Compact Result UI

**Files:**
- Modify: `app/page.tsx`
- Modify: `app/features/network/networkRedispatch.ts`
- Modify: `app/features/network/NetworkRedispatchView.tsx`
- Modify: `app/globals.css`
- Modify: `e2e/network-redispatch.spec.ts`
- Modify: `e2e/expanded-workflows.spec.ts`
- Modify: `tests/rendered-html.test.mjs`

**Interfaces:**
- Consumes: Task 3 `solver_contract` project field and Task 4 compact results/API.
- Produces: accessible advanced settings editor, one save acknowledgement, revision warning and compact solver-evidence summary.

- [ ] **Step 1: Extend the TypeScript contract and write failing component/E2E assertions**

```ts
export type ZonalSolverContract = {
  schema_version: "force.network-solver-contract/v1";
  contract_version: "force.zonal-lexicographic/v1";
  method: "highs-ds" | "highs-ipm" | "highs";
  presolve: true;
  primal_feasibility_tolerance: number;
  dual_feasibility_tolerance: number;
  ipm_optimality_tolerance: number;
  warning_fraction: number;
  validated_ceilings: Record<string, number>;
  absolute_ceilings: Record<string, number>;
  is_builtin_default: boolean;
  requires_acknowledgement: boolean;
};
```

Playwright must assert the section appears only for the zonal module, defaults are read-only until “Use custom solver settings” is selected, invalid ranges block save, and one acknowledgement is required before a custom revision is saved.

- [ ] **Step 2: Run frontend tests and confirm RED**

Run:

```text
npm run lint
npx playwright test e2e/network-redispatch.spec.ts e2e/expanded-workflows.spec.ts
```

Expected: missing labels, controls or result fields fail assertions.

- [ ] **Step 3: Implement the advanced settings section**

Use labels “Solver method”, “Primal feasibility tolerance”, “Dual feasibility tolerance”, “IPM optimality tolerance”, “Numerical warning threshold” and the three validated ceilings. Show immutable absolute ceilings as explanatory text, not editable inputs. The acknowledgement text must state: “Saving custom solver settings creates a new study revision and removes the built-in solver-validated label until the selected stack passes the validation gates.”

- [ ] **Step 4: Implement compact result evidence**

Show method/contract version, stack status, maximum validated-ceiling use, warning count, unvalidated count and one “Export solver diagnostics” link. Do not render the per-period table on the main run screen. `NetworkRedispatchView` may display paginated detailed evidence only after the user opens Inspect.

- [ ] **Step 5: Test accessibility and built-in/custom distinctions**

Assert every numeric input has a visible label and bounds; keyboard navigation reaches the acknowledgement; default studies display “Built-in validated baseline”; custom settings display “Custom contract — not yet solver validated”; completed-with-warning runs are not rendered as ordinary success.

- [ ] **Step 6: Run frontend verification**

Run:

```text
npm run lint
npm run build
node --test tests/rendered-html.test.mjs
npx playwright test e2e/network-redispatch.spec.ts e2e/expanded-workflows.spec.ts
```

Expected: all pass.

- [ ] **Step 7: Commit Task 5**

```bash
git add app/page.tsx app/features/network/networkRedispatch.ts app/features/network/NetworkRedispatchView.tsx app/globals.css e2e/network-redispatch.spec.ts e2e/expanded-workflows.spec.ts tests/rendered-html.test.mjs
git commit -m "feat(frontend): expose zonal solver contract"
```

### Task 6: Public Documentation, Generated References and Release Product

**Files:**
- Modify: `docs/MATHEMATICAL_REFERENCE.md`
- Modify: `docs/USER_GUIDE.md`
- Modify: `docs/MODULE_DEVELOPER_101.md`
- Modify: `docs/BUILD_YOUR_OWN_MODEL_101.md`
- Create: `docs/scientific-readiness/ZONAL_SOLVER_CONTRACT_V1.md`
- Create: `docs/scientific-readiness/prompts/108-zonal-solver-contract-v1.md`
- Modify: `scripts/generate_reference_tables.py`
- Regenerate: `docs/generated/MODULES.md`
- Modify: `source-release-manifest.json`
- Modify: `tests/test_documentation_consistency.py`
- Modify: `tests/test_source_release_tree.py`

**Interfaces:**
- Consumes: Tasks 1–5 public names, values and statuses.
- Produces: auditable handbook explanation, third-party module instructions, generated manifest table and source-release membership.

- [ ] **Step 1: Write failing documentation consistency tests**

Assert documentation contains the exact formula symbols `U_k`, `gamma_n`, `tau_k`, the three objective units and ceilings, SciPy `1.8.1`, `highs-ds`, all allowed ranges, the no-fallback rule, warning propagation, module `1.2.0`, ledger `v7`, and the phrase “numerical tolerance does not relax physical feasibility”. Assert generated module docs match the manifest hash.

- [ ] **Step 2: Run documentation tests and confirm RED**

Run: `python -m unittest tests.test_documentation_consistency tests.test_source_release_tree -v`

Expected: missing v1 contract references and stale generated module version.

- [ ] **Step 3: Document the built-in scientific method and user controls**

`MATHEMATICAL_REFERENCE.md` must define all four objectives, why only the first three are locked, the one-sided formula and classifications. `USER_GUIDE.md` must explain the default solver, advanced ranges, revision acknowledgement, evidence export, failure preservation and how to create an explicit separate copperplate study. It must not present the experimental zonal model as security analysis or transmission expansion.

- [ ] **Step 4: Document third-party contracts**

`MODULE_DEVELOPER_101.md` and `BUILD_YOUR_OWN_MODEL_101.md` must show a complete manifest fragment with `solver_contract`, require v7 diagnostics for every locked phase, list universal validators, and explain that a different optimiser may run but has no validated badge until its declared gates pass.

- [ ] **Step 5: Add Prompt 108 traceability and regenerate references**

Prompt 108 records the approved spec, task list, non-goals and acceptance gates. Run `python scripts/generate_reference_tables.py` and verify only expected generated files change. Add every new source, schema, test and document to the allowlisted source product.

- [ ] **Step 6: Run documentation and release checks**

Run:

```text
python -m unittest tests.test_documentation_consistency tests.test_source_release_tree -v
python scripts/source_release_scan.py
```

Expected: generated references are current; release allowlist contains no run output, real UK pack, cache or local state.

- [ ] **Step 7: Commit Task 6**

```bash
git add docs/MATHEMATICAL_REFERENCE.md docs/USER_GUIDE.md docs/MODULE_DEVELOPER_101.md docs/BUILD_YOUR_OWN_MODEL_101.md docs/scientific-readiness/ZONAL_SOLVER_CONTRACT_V1.md docs/scientific-readiness/prompts/108-zonal-solver-contract-v1.md scripts/generate_reference_tables.py docs/generated/MODULES.md source-release-manifest.json tests/test_documentation_consistency.py tests/test_source_release_tree.py
git commit -m "docs(network): publish zonal solver methodology"
```

### Task 7: Affected-Suite Verification and Preserved Failure Replay

**Files:**
- Modify only if a test exposes a defect in Tasks 1–6; fix in the owning file and add the smallest regression there.
- Create: `publication/prompt108-zonal-solver-contract-test-report.json`
- Create: `publication/PROMPT108_ZONAL_SOLVER_CONTRACT_TEST_REPORT.md`

**Interfaces:**
- Consumes: Tasks 1–6 complete implementation.
- Produces: machine-readable affected-suite report and human-readable decision before production data are run.

- [ ] **Step 1: Record immutable starting evidence**

Capture branch HEAD, working-tree status, Python/SciPy/HiGHS identity, Node/npm versions, original Prompt 104 hashes and retained Scheme C hash gate. If the runtime is not SciPy 1.8.1, record `solver_stack_not_yet_validated`; do not install or substitute a solver inside this task.

- [ ] **Step 2: Run complete affected Python suites**

Run:

```text
python -m unittest tests.test_zonal_solver_contract tests.test_zonal_solver_project_contract tests.test_prompt99_zonal_redispatch tests.test_prompt100_zonal_ledger tests.test_prompt101_staged_cem_integration tests.test_prompt102_zonal_results_api tests.test_prompt103_zonal_validation tests.test_prompt104_network_overlay_resolution tests.test_prompt107_production_gate tests.test_force_actual_random_clearing tests.test_application_service tests.test_run_input_snapshot tests.test_market_ledger -v
```

Expected: zero failures and zero unexpected skips.

- [ ] **Step 3: Replay the two preserved numerical failures**

Run the fixture replay entry point added in Task 2 with exact input SHA assertions. Require all four phases to solve, all three locked objectives to satisfy `d_k <= tau_k`, energy-balance residual within the pre-existing physical tolerance, and deterministic output SHA on two consecutive runs.

- [ ] **Step 4: Run frontend and release suites**

Run:

```text
npm run lint
npm run build
node --test tests/rendered-html.test.mjs
npx playwright test e2e/network-redispatch.spec.ts e2e/expanded-workflows.spec.ts
python -m unittest tests.test_documentation_consistency tests.test_source_release_tree -v
```

Expected: all pass.

- [ ] **Step 5: Write the Prompt 108 reports**

The JSON report must include commands, return codes, counts, environment identity, original hashes, fixture hashes, maximum observed lock degradation/tolerance/ceiling use, validation labels and first blocker. The Markdown report must distinguish code correctness, solver-stack validation and production scientific validation.

- [ ] **Step 6: Commit Task 7**

```bash
git add publication/prompt108-zonal-solver-contract-test-report.json publication/PROMPT108_ZONAL_SOLVER_CONTRACT_TEST_REPORT.md
git commit -m "test(network): verify zonal solver contract"
```

### Task 8: Resume Task 10 Production Gate from a Fresh Output Root

**Files:**
- Modify: `scripts/run_prompt107_production_gate.py`
- Create: `outputs/prompt107-zonal-solver-contract-v1/<run artifacts>`
- Create: `publication/prompt107-zonal-production-gate-v2.json`
- Create: `publication/PROMPT107_ZONAL_PRODUCTION_GATE_V2.md`
- Modify: `.superpowers/sdd/2026-08-22-vre-curtailment-attribution-v2/task-10-report.md`

**Interfaces:**
- Consumes: all prior tasks, installed signed UK data/network packs and derived Prompt 104 execution studies.
- Produces: a truthful sequential Task 10 result ending at the first blocker or at the completed two-year causal comparison.

- [ ] **Step 1: Preflight a clean production root**

Refuse a non-empty destination. Validate both signed pack identities, free disk space, module graph, project revision, solver contract, declared SciPy/HiGHS stack and original source hashes. Record the derived study lineage before launch.

Extend `STAGE_ORDER` to `("smoke", "exact-periods", "24h", "168h", "annual", "two-year")`. `exact-periods` replays only the two preserved declared inputs and writes normal v7 evidence; it is not counted as an annual or matched-scenario result. Update `run_stage_sequence`, CLI-through expansion and `tests/test_prompt107_production_gate.py` so a failed exact-period gate prevents 24-hour and later launches.

- [ ] **Step 2: Run matched two-period smoke cases**

Run one copperplate and one zonal case with identical demand/weather/fleet/scenario inputs. Require completed status, strict balance, valid SOC, valid settlement, ledger v7 integrity and solver evidence for every zonal locked phase.

- [ ] **Step 3: Run the exact failed periods**

Replay period index 14 (`2022-01-01:15`) with declared input SHA ending `068a` and the second retained bound-noise case. Stop on any non-determinism, physical validation error, missing evidence or absolute-ceiling violation.

- [ ] **Step 4: Run matched 24-hour cases**

Run 48 half-hours for copperplate and zonal studies. Compare only matched scenario authority. Require no unexpected fallback, v7/JSON reconciliation, deterministic rerun fingerprint, and Prompt 107 status not `NO-GO`.

- [ ] **Step 5: Run matched 168-hour cases only after 24-hour GO**

Run 336 half-hours. Apply the same checks and report per-phase maximum tolerance, degradation, warning counts and ceiling use. If the solver stack differs from the baseline, the run may complete but remains `solver_stack_not_yet_validated`.

- [ ] **Step 6: Run matched complete 2025 cases only after 168-hour GO**

Run all 17,520 half-hours for copperplate and zonal. Require complete annual PSM/CEM artifacts, strict physical and cost-ledger reconciliation, solver diagnostic completeness, planning/commissioning indices and explicit validation status. This is the first gate that may be interpreted as annual economics.

- [ ] **Step 7: Run causal 2025–2026 cases only after annual GO**

Run 2025 PSM → investment/caps/pipeline → 2026 PSM for both matched studies. Verify commissioned assets inherit economics and reach the next-year clearing object, and propagate any solver warning into downstream years. Do not launch a ten-year study.

- [ ] **Step 8: Audit and write the final Task 10 report**

Report each gate as `GO`, `GO_WITH_NUMERICAL_WARNING`, `NO-GO` or `NOT_STARTED`, with exact command, runtime, artifact root, first blocker and scientific interpretation. Include national cost, redispatch impact, curtailment attribution, reliability, planning changes and solver diagnostics without claiming a network-security result.

- [ ] **Step 9: Run final integrity checks**

Run:

```text
python -m json.tool outputs/prompt107-zonal-solver-contract-v1/prompt107-production-gate.json
python -m unittest tests.test_prompt107_production_gate tests.test_documentation_consistency tests.test_source_release_tree -v
git status --short
```

Expected: the audit matches the furthest completed gate, reports no hidden fallback, and lists every later gate as `NOT_STARTED` if execution stopped.

- [ ] **Step 10: Commit Task 8 evidence without committing bulky run outputs**

```bash
git add scripts/run_prompt107_production_gate.py publication/prompt107-zonal-production-gate-v2.json publication/PROMPT107_ZONAL_PRODUCTION_GATE_V2.md .superpowers/sdd/2026-08-22-vre-curtailment-attribution-v2/task-10-report.md
git commit -m "test(network): resume zonal production gate"
```

## Final Acceptance Review

- [ ] Map every approved design section to Tasks 1–8 and record the mapping in the Prompt 108 report.
- [ ] Confirm no exact floating-point objective equality remains in the zonal lexicographic path.
- [ ] Confirm no physical, SOC, transfer, capacity or settlement validator tolerance changed.
- [ ] Confirm old Prompt 104 study bytes, old market ledgers and retained Scheme C files have unchanged SHA-256 values.
- [ ] Confirm custom solver settings change project revision and require exactly one save acknowledgement.
- [ ] Confirm v7 SQLite, detailed JSON and annual summaries reconcile.
- [ ] Confirm the UI does not hide unvalidated or warning states and does not flood the main run screen with per-period rows.
- [ ] Confirm Task 10 stops at the first failed gate and no Prompt 105 ten-year run is launched.
