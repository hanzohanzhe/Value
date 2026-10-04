# Zonal Redispatch Network Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional fixed, lossless GB zonal redispatch method behind a staged national ahead-market/balancing interface, validate it independently, connect it to the real PSM–CEM chain, and present it honestly in the local FORCE application.

**Architecture:** Preserve the accepted copperplate and Castle 101 paths. Add immutable staged-market contracts, then a thesis-compatible copperplate balancing implementation. Add a separate zonal transport/cut-set contract, offline spatial/network pack builders and a single-period HiGHS balancing solver. Extend the existing SQLite ledger and annual orchestration rather than creating parallel products. Validate the production formulation with an independently assembled PuLP/CBC oracle before annual or ten-year execution.

**Tech Stack:** Python 3.10, dataclasses/JSON contracts, NumPy, SciPy 1.8.1 HiGHS, PuLP/CBC 3.3.2, SQLite, unittest, React 19, TypeScript 5.9, Vinext/Vite, Playwright, PowerShell.

**Spec:** `docs/superpowers/specs/2026-08-21-zonal-redispatch-network-design.md`

## Global Constraints

- Do not edit retained Scheme C or invalidate `docs/visibility-refactor/retained-source-hashes.json`.
- Use copies/adapters in the public modular route.
- Keep old monolithic PSM Studies and Castle 101 behaviour unchanged.
- Keep Prompt 68 DC-OPF and Prompt 69 AC feasibility as separate reference/experimental methods.
- Keep the transmission-expansion public contract, but provide no bundled selectable transmission-CEM implementation on this release line.
- The first zonal method is fixed, lossless and transport/cut-set based. It makes no AC, security, N-1, real-line-flow or endogenous-expansion claim.
- Runtime code must not download data, run GIS or build a network pack.
- Write each behavioural test first and observe the intended failure before implementation.
- Use `apply_patch` for source edits; use format/build tools only for mechanical output.
- Run retained-source checks after every prompt that touches copied Scheme C-derived code.
- Commit each accepted prompt separately on `codex/zonal-redispatch-prompt93-106`.
- Stop at Prompt 98 until Hanzhe Xing explicitly signs the candidate network pack.

---

### Task 1: Prompt 93 — preserve the current product and freeze the workstream

**Files:**
- Existing: `docs/superpowers/specs/2026-08-21-zonal-redispatch-network-design.md`
- Existing: `docs/scientific-readiness/ZONAL_REDISPATCH_PROMPTS_93_106.md`
- Create: `docs/scientific-readiness/ZONAL_REDISPATCH_SUPERSESSION_MATRIX.md`
- Create: `publication/prompt93-pre-change-snapshot.json`
- Modify: `docs/scientific-readiness/README.md`
- Modify: `docs/scientific-readiness/RELEASE_GAP_MATRIX.md`

**Interfaces:**
- Consumes exact Prompt 92 source identity `4915811` / tag `value-castle-101-prompt92-20260820`
- Produces rollback tag `pre-zonal-redispatch-prompt93-20260821`

- [x] **Step 1: Verify the planning commit is clean and create the isolated worktree**

  Use the `using-git-worktrees` skill. Tag commit `4915811`, then create branch
  `codex/zonal-redispatch-prompt93-106` without rewriting Prompt 92 history.

- [x] **Step 2: Run and record the focused baseline**

  Run these existing files with the repository's discover form:

  - `py -3.10 -m unittest discover -s tests -p "test_retained_source_manifest.py" -v`
  - `py -3.10 -m unittest discover -s tests -p "test_prompt86_castle_101.py" -v`
  - `py -3.10 -m unittest discover -s tests -p "test_prompt89_castle_results.py" -v`
  - `py -3.10 -m unittest discover -s tests -p "test_prompt67_network_contracts.py" -v`
  - `py -3.10 -m unittest discover -s tests -p "test_prompt68_reference_dc_network.py" -v`
  - `py -3.10 -m unittest discover -s tests -p "test_prompt70_network_expansion.py" -v`

- [x] **Step 3: Record locks, hashes, commit and baseline results**

  Write `publication/prompt93-pre-change-snapshot.json` with SHA-256 values for
  `pyproject.toml`, `package-lock.json`, the source-release manifest and retained
  hash evidence.

- [x] **Step 4: Write the reuse/supersession matrix and literal ID table**

  Mark Prompt 67 reusable; Prompt 68 separate; Prompt 69 experimental; Prompt 70
  contract-only on this release line; Prompt 83 presentation patterns reusable.

- [x] **Step 5: Verify docs and commit Prompt 93**

  Run `git diff --check`, the focused baseline again, inspect `git status`, then
  commit only Prompt 93 evidence and planning-index changes.

### Task 2: Prompt 94 — staged market contracts and registry negotiation

**Files:**
- Create: `gridform_core/staged_market_contracts.py`
- Create: `gridform_core/balancing.py`
- Create: `gridform_core/data/contracts/staged-market-v1.schema.json`
- Create: `tests/test_prompt94_staged_market_contracts.py`
- Modify: `gridform_core/v2/contracts.py`
- Modify: `gridform_core/v2/interfaces.py`
- Modify: `gridform_core/v2/module_manifest.py`
- Modify: `gridform_core/module_registry.py`
- Modify: `gridform_core/project_revision.py`
- Modify: `gridform_core/run_snapshot.py`

**Interfaces:**
- Produces dataclasses `AheadMarketInput`, `AheadMarketResult`, `FlexibilityBid`,
  `BalancingInput`, `AcceptedAdjustment`, `BalancingResult`, `StagedMarketYearResult`
- Produces protocol `BalancingModule.clear(model_input: BalancingInput) -> BalancingResult`
- Produces optional module slot `balancing` / capability `market.balancing/v1`

- [x] **Step 1: Add failing JSON round-trip and validation tests**

  Cover literal schema IDs, signed prices, duplicate bids, non-finite values,
  units, canonical hashes and ahead-result linkage.

- [x] **Step 2: Run the focused test and observe missing-contract failures**

  Run `py -3.10 -m unittest discover -s tests -p "test_prompt94_staged_market_contracts.py" -v`.

- [x] **Step 3: Implement immutable contracts and the balancing protocol**

  Reuse `JsonContract`; keep realised fields out of `AheadMarketResult`.

- [x] **Step 4: Add failing registry/project identity tests**

  Cover staged PSM with zero/one/two balancing providers, wrong capability,
  monolithic PSM, old project hash, snapshot and checkpoint identity.

- [x] **Step 5: Implement conditional one-registry resolution**

  A balancing module is required only when the selected PSM declares
  `market.ahead-schedule/v1`.

- [x] **Step 6: Run contract, project and registry regressions**

  Run the new focused file, then the existing files
  `test_contracts_v2.py`, `test_project_revision.py` and
  `test_run_input_snapshot.py` with the same `unittest discover` command form.

- [x] **Step 7: Review public contracts and commit Prompt 94**

### Task 3: Prompt 95 — thesis-compatible staged copperplate path

**Files:**
- Create: `gridform_core/builtin/scheme_c_1000twh/staged_psm.py`
- Create: `gridform_core/builtin/scheme_c_1000twh/copperplate_balancing.py`
- Create: `gridform_core/manifests/force-staged-bid-at-cost-psm.json`
- Create: `gridform_core/manifests/force-copperplate-balancing.json`
- Create: `tests/test_prompt95_staged_copperplate.py`
- Modify: `gridform_core/builtin/scheme_c_1000twh/factory.py`
- Modify: `gridform_core/application.py`
- Modify: `gridform_core/frontend_contract.py`

**Interfaces:**
- Produces `StagedBidAtCostPSM.run(model_input: PSMInput) -> MarketYearResult`
- Produces `CopperplateBalancing.clear(model_input: BalancingInput) -> BalancingResult`

- [x] **Step 1: Write failing hand-period and information-scope tests**

  Assert that ahead clearing cannot see realised demand/availability and that
  balancing rejects a mutated ahead hash or a second execution.

- [x] **Step 2: Run and observe the missing-module failures**

  Run `py -3.10 -m unittest discover -s tests -p "test_prompt95_staged_copperplate.py" -v`.

- [x] **Step 3: Copy/adapt the accepted bid-at-cost logic into the staged modules**

  Keep the declared ahead schedule as an immutable input to balancing. Commit
  realised SOC, dispatch and market income once.

- [x] **Step 4: Add parity fixtures**

  Compare one period, two-period smoke, 24 hours, signed imports, charge/idle/
  discharge and forecast surplus/deficit against the accepted monolithic route.

- [x] **Step 5: Run parity, retained-hash and live-invocation tests**

  Run the new focused file, then `test_retained_source_manifest.py` and
  `test_force_market_replay_runtime.py` with `unittest discover`.

- [x] **Step 6: Run code review, resolve findings and commit Prompt 95**

### Task 4: Prompt 96 — zonal transport and cut-set contracts

**Files:**
- Create: `gridform_core/zonal_contracts.py`
- Create: `gridform_core/data/contracts/zonal-network-pack-v1.schema.json`
- Create: `gridform_core/extension_manifests/force-zonal-redispatch-extension.json`
- Create: `examples/zonal-network-pack/**`
- Create: `tests/test_prompt96_zonal_contracts.py`
- Modify: `gridform_core/catalog.py`
- Modify: `gridform_core/data_pack_validation.py`
- Modify: `gridform_core/domain_readiness.py`

**Interfaces:**
- Produces `NetworkZone`, `TransportCorridor`, `CutsetMember`, `ETYSBoundary`,
  `ZonalAssetMapping`, `ZonalNetworkPack`
- Produces `load_zonal_network_pack(pack_root: Path) -> ZonalNetworkPack`

- [x] **Step 1: Write failing valid/invalid topology tests**

  Cover one zone, two zones, overlapping cut sets, asymmetric ratings,
  maintenance multipliers, fallback node, dangling corridors and NI rejection.

- [x] **Step 2: Run and observe missing-schema failures**

  Run `py -3.10 -m unittest discover -s tests -p "test_prompt96_zonal_contracts.py" -v`.

- [x] **Step 3: Implement zonal contracts without DC fields**

  Do not accept voltage, angle, susceptance or reactance. Model corridors as
  computational routing and boundaries as signed cut sets.

- [x] **Step 4: Register only conditional namespaced data roles**

  Activate roles only for `domain.network.zonal_redispatch`; leave the base 25
  and Prompt 67 DC roles unchanged.

- [x] **Step 5: Run data-pack, extension and domain-readiness regressions**

  Run the new focused file, then `test_data_pack_validation.py`,
  `test_prompt65_extension_framework.py` and
  `test_prompt82_domain_readiness.py` with `unittest discover`.

- [x] **Step 6: Review terminology and commit Prompt 96**

### Task 5: Prompt 97 — spatial fleet, weather and CEM allocation

**Files:**
- Create: `gridform_core/spatialization.py`
- Create: `gridform_core/weather_spatialization.py`
- Create: `gridform_core/manifests/force-representative-point-weather.json`
- Create: `gridform_core/manifests/force-repd-era5-aggregated-weather.json`
- Create: `tests/test_prompt97_spatialization.py`
- Modify: `gridform_core/canonical_psm_data.py`
- Modify: `gridform_core/builtin/scheme_c_1000twh/state_transition.py`
- Modify: `gridform_core/builtin/scheme_c_1000twh/planning_pipeline.py`

**Interfaces:**
- Produces `build_agent_zone_allocations(...) -> tuple[AgentZoneAllocation, ...]`
- Produces `rescale_to_national_totals(...)`
- Produces `RepresentativePointWeather.build(...)` and
  `REPDERA5AggregatedWeather.build(...)`

- [x] **Step 1: Write failing allocation and capacity-conservation tests**

  Cover 2/3–1/3 cross-zone shares, 20 MW wind multipliers, fixed shares after
  growth, exact commissioned-project placement and GB/NI separation.

- [x] **Step 2: Write failing coordinate/weather tests**

  Cover BNG conversion provenance, representative profiles, MW-weighted ERA5
  profiles, actual/inferred offshore landing and England fallback flags.

- [x] **Step 3: Run and observe missing-builder failures**

  Run `py -3.10 -m unittest discover -s tests -p "test_prompt97_spatialization.py" -v`.

- [x] **Step 4: Implement offline spatial and weather builders**

  Preserve economic agents; runtime receives only aggregated
  `agent×technology×zone` tranches and profiles.

- [x] **Step 5: Connect frozen shares to planning/state transition**

  New abstract capacity uses signed frozen shares; located REPD projects retain
  their zone and full owner economics.

- [x] **Step 6: Run planning, commissioning and retained-hash regressions**

  Run the new focused file, then `test_planning_index.py`,
  `test_planning_preprocessing_contract.py` and
  `test_retained_source_manifest.py` with `unittest discover`.

- [x] **Step 7: Review scientific identities and commit Prompt 97**

### Task 6: Prompt 98 — build and review the candidate GB zonal pack

**Files:**
- Create: `scripts/inventory_gb_zonal_sources.py`
- Create: `scripts/build_gb_zonal_pack.py`
- Create: `scripts/validate_gb_zonal_pack.py`
- Create: `tests/test_prompt98_gb_zonal_pack_builder.py`
- Create: `publication/prompt98-gb-zonal-pack-candidate.json`
- Create: `docs/scientific-readiness/PROMPT98_GB_ZONAL_PACK_REVIEW.md`
- Create after approval only in the local FORCE data root: immutable signed GB
  network pack; commit only the portable receipt because the accepted rights
  decision forbids bundling the complete real-UK asset in the public source tree

**Interfaces:**
- Produces `build_candidate(source_inventory: Path, output_root: Path) -> dict[str, object]`
- Produces an owner-signed immutable `network_pack_id`

- [x] **Step 1: Write failing source-inventory, determinism, rights and reconciliation tests**

  Assert authoritative URLs/versions/licences, pinned local object hashes, no
  runtime absolute paths, exact demand sums, national capacity totals and
  repeatable scientific files.

- [x] **Step 2: Implement offline discovery/inventory without runtime downloads**

  Inventory NESO, GSP/FES/DFES/DSO, ETYS, REPD, interconnector and ERA5/profile
  sources; transforms may consume only the pinned local inventory.

- [x] **Step 3: Implement the candidate-only offline builder**

  Build DSO-based zones, curated ETYS cuts, corridors, ratings, asset mappings,
  demand, both weather modes and spatial/rights audits.

- [x] **Step 4: Run the builder twice and compare hashes**

  Exclude only declared build timestamps from the deterministic comparison.

- [x] **Step 5: Render and inspect the review package**

  Check maps, zone/cut topology, capacity residuals, demand residuals, offshore
  methods, fallback shares, assumed-symmetric limits and excluded records.

- [x] **Step 6: Stop and request explicit owner sign-off**

  Do not invent the final pack ID, install the pack or continue to Prompt 99.

- [x] **Step 7: After approval, sign, install, revalidate and commit Prompt 98**

### Task 7: Prompt 99 — production single-period zonal solver

**Files:**
- Create: `gridform_core/zonal_redispatch.py`
- Create: `gridform_core/manifests/force-zonal-redispatch-balancing.json`
- Create: `tests/test_prompt99_zonal_redispatch.py`
- Create: `tests/fixtures/zonal_redispatch/**`
- Modify: `gridform_core/module_registry.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces `ZonalRedispatchBalancing.clear(model_input: BalancingInput) -> BalancingResult`
- Internal pure functions: `build_single_period_problem`, `solve_primary`,
  `solve_secondary`, `validate_solution`

- [x] **Step 1: Write failing hand-calculated LP fixtures**

  Cover unconstrained, infinite limit, one binding cut, asymmetric limits,
  signed imports, VRE curtailment, thermal movement, DSR and VOLL.

- [x] **Step 2: Write failing storage/tie/failure fixtures**

  Cover SOC efficiency, power/energy limits, no self-cycle, proportional equal
  bids, deterministic residual ties and preserved infeasible declarations.

- [x] **Step 3: Run and observe missing-solver failures**

  Run `py -3.10 -m unittest discover -s tests -p "test_prompt99_zonal_redispatch.py" -v`.

- [x] **Step 4: Implement primary HiGHS LP and residual validation**

  Minimise signed accepted bids subject to resource, zonal, routing, cut-set,
  storage and interconnector constraints.

- [x] **Step 5: Implement secondary deviation objective and deterministic ties**

  Freeze the primary optimum within tolerance, minimise absolute change from the
  ahead schedule, then apply the declared pro-rata/stable rule.

- [x] **Step 6: Run focused and existing solver tests**

  Run the new focused file, then `test_prompt68_reference_dc_network.py` and
  `test_independent_psm_validation.py` with `unittest discover`.

- [x] **Step 7: Review matrix signs and commit Prompt 99**

### Task 8: Prompt 100 — accounting and SQLite evidence

**Files:**
- Modify: `gridform_core/market_ledger.py`
- Modify: `gridform_core/market_replay.py`
- Modify: `gridform_core/cost_ledger.py`
- Create: `gridform_core/zonal_results.py`
- Create: `gridform_core/data/contracts/market-ledger-v5.schema.sql`
- Create: `tests/test_prompt100_zonal_ledger.py`
- Modify: `gridform_core/bundle_validator.py`

**Interfaces:**
- Upgrades schema to `gridform.market-ledger/v5`
- Adds `ZonalPeriodLedgerRow`, `BoundaryPeriodLedgerRow`,
  `RedispatchSettlementRow`, `ReliabilityEventRow`
- Produces `query_zonal_results(path: Path, query: Mapping[str, object])`

- [x] **Step 1: Write failing migration and six-account reconciliation tests**
- [x] **Step 2: Write failing counterfactual, curtailment and reliability tests**
- [x] **Step 3: Run `py -3.10 -m unittest discover -s tests -p "test_prompt100_zonal_ledger.py" -v` and observe failures**
- [x] **Step 4: Implement v4→v5 migration and batched zonal writers**
- [x] **Step 5: Implement settlement/counterfactual identities and query indexes**
- [x] **Step 6: Prove summary/full decisions are identical and benchmark writes**

  Run the new focused file, then `test_market_ledger.py` and
  `test_market_replay.py` with `unittest discover`.

- [x] **Step 7: Validate bundle migration, review accounting and commit Prompt 100**

### Task 9: Prompt 101 — live PSM–CEM integration and explicit rerun

**Files:**
- Modify: `gridform_core/application.py`
- Modify: `gridform_core/v2/orchestrator.py`
- Modify: `gridform_core/v2/projects.py`
- Modify: `gridform_core/project_revision.py`
- Modify: `gridform_core/cost_ledger.py`
- Modify: `gridform_core/storage_recovery.py`
- Modify: `gridform_core/v2/module_manifest.py`
- Modify: `gridform_core/frontend_contract.py`
- Modify: `gridform_core/runtime_capabilities.py`
- Modify: `backend/model_runner.py`
- Modify: `backend/server.py`
- Create: `tests/test_prompt101_staged_cem_integration.py`

**Interfaces:**
- Produces staged study fields and real annual chain
- Produces `POST /api/runs/{run_id}/rerun-copperplate`

- [x] **Step 1: Write failing two-period cashflow/SOC/CEM tests**
- [x] **Step 2: Write failing commissioned-child next-year placement tests**
- [x] **Step 3: Write failing solver-failure and rerun-lineage tests**
- [x] **Step 4: Run and observe live-path failures**

  Run `py -3.10 -m unittest discover -s tests -p "test_prompt101_staged_cem_integration.py" -v`.

- [x] **Step 5: Connect ahead→balancing→final state exactly once**
- [x] **Step 6: Feed final physical and cashflow values to storage/CEM/ledgers**
- [x] **Step 7: Implement immutable failed-run evidence and new copperplate run**
- [x] **Step 8: Withhold transmission expansion from production selection**

  Keep both historical manifest files, source and results byte-identical. Apply a
  release-profile filter in registry/frontend capability exposure so the bundled
  implementation is not selectable, while the public contract remains available
  to developer-installed modules.

- [x] **Step 9: Run orchestration, project, recovery and retained-hash regressions**

  Run the new focused file, then `test_application_service.py`,
  `test_project_revision.py`, `test_recovery_capability.py` and
  `test_retained_source_manifest.py` with `unittest discover`.

- [x] **Step 10: Review state ownership and commit Prompt 101**

### Task 10: Prompt 102 — Network & redispatch frontend

**Files:**
- Create: `app/features/network/NetworkRedispatchView.tsx`
- Create: `app/features/network/networkRedispatch.ts`
- Create: `app/features/network/NetworkZoneMap.tsx`
- Modify: `app/page.tsx`
- Modify: `app/globals.css`
- Modify: `backend/server.py`
- Create: `tests/test_prompt102_zonal_results_api.py`
- Modify: `tests/rendered-html.test.mjs`
- Create: `e2e/network-redispatch.spec.ts`

**Interfaces:**
- Produces result endpoints under `/api/runs/{run_id}/network-redispatch`
- Consumes the existing run, comparison, export and Market replay identities

- [x] **Step 1: Write failing API pagination/filter/export tests**
- [x] **Step 2: Write failing rendered-label and unsupported-claim tests**
- [x] **Step 3: Run Python and Node tests and observe missing-view failures**
- [x] **Step 4: Add study controls and signed-pack readiness panel**
- [x] **Step 5: Build annual brief, zone/boundary tables and computational map**
- [x] **Step 6: Add period replay, curtailment, storage and reliability drill-down**
- [x] **Step 7: Add failed-run evidence and explicit copperplate rerun UI**
- [x] **Step 8: Test accessibility, laptop width, summary/full/empty/error states**

  Run `npm run lint`, `npm run build`, `node --test tests/rendered-html.test.mjs`
  and `npm run test:e2e` with the focused spec selector supported by the harness.

- [x] **Step 9: Review scientific labels and commit Prompt 102**

### Task 11: Prompt 103 — independent optimisation validation

**Files:**
- Create: `gridform_validation/zonal_oracle.py`
- Create: `gridform_validation/zonal_case_generator.py`
- Create: `tests/test_prompt103_zonal_validation.py`
- Create: `scripts/run_zonal_validation.py`
- Create: `publication/prompt103-zonal-validation-report.json`
- Create: `docs/scientific-readiness/PROMPT103_ZONAL_VALIDATION_REPORT.md`

**Interfaces:**
- Produces `solve_zonal_oracle(declaration: Mapping[str, object]) -> Mapping[str, object]`
- Production matrix/objective imports are forbidden

- [ ] **Step 1: Write a source/import independence gate**
- [ ] **Step 2: Re-formulate analytical cases independently in PuLP/CBC**
- [ ] **Step 3: Add seeded random convex-case comparison**
- [ ] **Step 4: Add deterministic 24-hour and 168-hour sequential-SOC cases**
- [ ] **Step 5: Add one targeted mutation for every declared constraint family**
- [ ] **Step 6: Run the validator and prove all valid cases pass**

  Run `py -3.10 scripts/run_zonal_validation.py --output publication/prompt103-zonal-validation-report.json`.

- [ ] **Step 7: Prove every mutation makes its intended gate fail**
- [ ] **Step 8: Classify degeneracy/differences and write the report**
- [ ] **Step 9: Run requesting-code-review and verification-before-completion**
- [ ] **Step 10: Commit Prompt 103 only if the blocking gate is GO**

### Task 12: Prompt 104 — full-year and causal two-year gate

**Files:**
- Create: `scripts/run_prompt104_zonal_gate.py`
- Create: `publication/prompt104-zonal-annual-two-year-report.json`
- Create: `docs/scientific-readiness/PROMPT104_ZONAL_ANNUAL_TWO_YEAR_REPORT.md`
- Create: `tests/test_prompt104_gate_report.py`

**Interfaces:**
- Produces matched immutable copperplate/zonal one-year and two-year run IDs;
  each complete model year contains all 17,520 half-hour periods

- [ ] **Step 1: Assert Prompt 103 GO, signed pack hash and disk preflight**
- [ ] **Step 2: Run focused smokes and validate their bundles**
- [ ] **Step 3: Launch complete 2025 staged-copperplate run and monitor logs**
- [ ] **Step 4: Validate 2025 copperplate physics, ledgers and exports**
- [ ] **Step 5: Launch matched complete 2025 zonal run and monitor logs**
- [ ] **Step 6: Validate zonal physics, counterfactuals and performance**
- [ ] **Step 7: Stop on any annual NO-GO; otherwise launch both 2025–2026 chains**
- [ ] **Step 8: Audit owner economics, planning, commissioning and 2026 injection**
- [ ] **Step 9: Test checkpoint/interruption, replay and export paths**
- [ ] **Step 10: Write GO/NO-GO Markdown/JSON and commit Prompt 104 evidence**

### Task 13: Prompt 105 — matched four-case ten-year experiment

**Files:**
- Create: `scripts/run_prompt105_ten_year_matrix.py`
- Create: `publication/prompt105-ten-year-zonal-comparison.json`
- Create: `docs/scientific-readiness/PROMPT105_TEN_YEAR_ZONAL_COMPARISON.md`
- Create: `tests/test_prompt105_comparison_identity.py`

**Interfaces:**
- Produces the A/B/C/D immutable run matrix defined in
  `ZONAL_REDISPATCH_PROMPTS_93_106.md`

- [ ] **Step 1: Assert Prompt 104 GO and exact matched-input fingerprints**
- [ ] **Step 2: Launch copperplate/legacy and zonal/legacy runs**
- [ ] **Step 3: Validate both legacy bundles before launching dynamic cases**
- [ ] **Step 4: Launch copperplate/dynamic and zonal/dynamic runs**
- [ ] **Step 5: Validate all 40 annual transitions and bundle identities**
- [ ] **Step 6: Locate the first causal period for every material divergence**
- [ ] **Step 7: Audit costs, settlements, curtailment, storage, reliability, carbon and planning**
- [ ] **Step 8: Compare read-only retained Scheme C under the existing divergence contract**
- [ ] **Step 9: Write classified scientific comparison and commit Prompt 105**

### Task 14: Prompt 106 — documentation, clean-clone and release decision

**Files:**
- Modify: `README.md`
- Modify: `docs/USER_GUIDE.md`
- Modify: `docs/USER_GUIDE_ZH.md`
- Modify: `docs/HOW_TO_BUILD_YOUR_OWN_MODEL_101.md`
- Create: `docs/NETWORK_REDISPATCH_METHOD.md`
- Create: `docs/NETWORK_REDISPATCH_METHOD_ZH.md`
- Create: `publication/prompt106-zonal-release-report.json`
- Create: `docs/scientific-readiness/PROMPT106_ZONAL_RELEASE_REPORT.md`
- Modify: `source-release-manifest.json`
- Modify: `data-release-manifest.json`
- Create: `tests/test_prompt106_zonal_documentation.py`

**Interfaces:**
- Produces separate release decisions for copperplate, optional zonal method,
  signed GB pack redistribution and experimental DC/AC/expansion work

- [ ] **Step 1: Write failing docs/schema/UI consistency tests**
- [ ] **Step 2: Draft bilingual methodology and advanced-user guide from evidence**
- [ ] **Step 3: Apply the humanizer review without changing scientific definitions**
- [ ] **Step 4: Re-run documentation consistency and retained-hash tests**
- [ ] **Step 5: Build source, synthetic fixture and rights-governed data products separately**
- [ ] **Step 6: Run fresh-clone install, Python tests, frontend lint/build and synthetic zonal run**
- [ ] **Step 7: Re-run the Prompt 103 independent validation gate in the clean clone**
- [ ] **Step 8: Scan for absolute paths, secrets, caches, outputs and bundled transmission expansion**
- [ ] **Step 9: Write bounded capability-by-capability decisions**
- [ ] **Step 10: Run full requesting-code-review and verification-before-completion workflows**
- [ ] **Step 11: Commit Prompt 106 and apply finishing-a-development-branch workflow**

## Completion rule

The workstream is complete only when Prompt 106 reports evidence-backed decisions.
Prompt 98 without owner sign-off is a deliberate pause, Prompt 103 NO-GO blocks
production runs, Prompt 104 NO-GO blocks ten-year runs, and a failed Prompt 105
must remain immutable negative evidence rather than being rewritten.
