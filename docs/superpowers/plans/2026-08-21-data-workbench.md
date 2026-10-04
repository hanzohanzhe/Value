# FORCE Data Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build a reproducible local Data Workbench that discovers, pins, compiles, validates, reviews and promotes official-source GB zonal-network data without changing FORCE model mathematics or retained Scheme C.

**Architecture:** A transport-independent Python service owns the strict SourceDefinition -> SourceRevision -> RawObjectReceipt -> BuildManifest -> CandidatePack -> PromotedBundle lifecycle. Dataset-specific compilers emit the existing Prompt 96 zonal roles, independent validators gate an existing force.data-bundle/v1 archive, and thin CLI/API/frontend adapters call the same service. Stable service DTOs and storage ports permit later migration to a hosted data service.

**Tech Stack:** Python 3.10.11, dataclasses/typing/json/hashlib/pathlib/urllib, pandas 2.3.2, optional Shapely 2.1.1, PyProj 3.7.1 and OpenPyXL 3.1.0, local SQLite, existing Python HTTP backend, React/TypeScript/Vite, pytest/unittest and Playwright.

**Spec:** docs/superpowers/specs/2026-08-21-data-workbench-design.md

## Global Constraints

- Do not edit retained Scheme C or change its accepted hashes.
- Do not change PSM, CEM, redispatch or transmission-expansion mathematics.
- Do not make zonal-network roles mandatory for copperplate Studies.
- Do not download or rebuild scientific inputs during model execution.
- Do not silently adopt the latest online data revision.
- Do not silently combine official, academic, community or inferred data.
- Do not call an ETYS electrical cut a physical line or force it into a single pairwise DSO connection.
- Do not allow a candidate pack to masquerade as a promoted benchmark.
- Do not allow an incomplete network run to continue silently as copperplate.
- Do not place large raw-source objects or local cache paths in the Git source release.
- Do not expose local absolute paths through public service responses or bundle metadata.
- Ordinary CI uses frozen fixtures; live portal access is restricted to the explicit freshness and official-build gates.
- Prompt 98 public entry points remain compatible while their implementation becomes a facade.

---

### Task 0: Preserve the interrupted Prompt 98 baseline and isolate execution

**Files:**
- Preserve: gridform_core/gb_zonal_pack_builder.py
- Preserve: scripts/inventory_gb_zonal_sources.py
- Preserve: scripts/build_gb_zonal_pack.py
- Preserve: scripts/validate_gb_zonal_pack.py
- Preserve: tests/test_prompt98_gb_zonal_pack_builder.py
- Preserve: docs/scientific-readiness/PROMPT98_GB_ZONAL_PACK_REVIEW.md
- Preserve: publication/prompt98-gb-zonal-pack-candidate.json
- Preserve: publication/prompt98-gb-zonal-source-inventory.json
- Preserve: publication/prompt98-gb-zonal-source-plan.json
- Preserve: docs/generated/MODULES.md

**Interfaces:**
- Consumes: the current dirty Prompt 98 worktree whose HEAD contains design commit 924a3a3.
- Produces: a named WIP Git checkpoint and clean codex/data-workbench branch in the existing linked worktree.

- [ ] **Step 1: Record baseline state**

    git status --short --branch
    git merge-base --is-ancestor 924a3a3 HEAD
    git diff --check

Expected: the ancestry check exits 0 and the dirty set contains only the known Prompt 98 work plus no uncommitted planning documents.

- [ ] **Step 2: Run focused baseline tests**

    py -3.10 -m pytest tests/test_prompt96_zonal_contracts.py tests/test_prompt97_spatialization.py tests/test_prompt98_gb_zonal_pack_builder.py -q

Record the observed result. A failing WIP can be preserved but cannot be called complete.

- [ ] **Step 3: Commit the exact WIP set**

    git add docs/generated/MODULES.md docs/scientific-readiness/PROMPT98_GB_ZONAL_PACK_REVIEW.md gridform_core/gb_zonal_pack_builder.py publication/prompt98-gb-zonal-pack-candidate.json publication/prompt98-gb-zonal-source-inventory.json publication/prompt98-gb-zonal-source-plan.json scripts/build_gb_zonal_pack.py scripts/inventory_gb_zonal_sources.py scripts/validate_gb_zonal_pack.py tests/test_prompt98_gb_zonal_pack_builder.py
    git commit -m "wip: preserve prompt 98 zonal pack builder"

- [ ] **Step 4: Reuse the existing isolated worktree**

The using-git-worktrees check confirms that `.worktrees/zonal-redispatch` is already a linked worktree. Do not nest another worktree. Create branch codex/data-workbench from the WIP checkpoint in place and verify git status --short is empty before DATA-01.

---

### Task 1: DATA-01 lifecycle and service contracts

**Files:**
- Create: gridform_core/data_workbench/__init__.py
- Create: gridform_core/data_workbench/contracts.py
- Create: gridform_core/data_workbench/ports.py
- Create: gridform_core/data_workbench/service.py
- Create: gridform_core/data_workbench/state.py
- Create: tests/data_workbench/test_contracts.py
- Create: tests/data_workbench/test_state.py
- Create: docs/generated/DATA_WORKBENCH_CONTRACT.md
- Modify: docs/data-construction/GAP_MATRIX.md

**Interfaces:**
- Consumes: force.data-bundle/v1, Prompt 96 zonal contracts and application-state root.
- Produces: immutable lifecycle dataclasses, DATA_WORKBENCH_API_SCHEMA, five protocols and canonical scientific hashing.

- [ ] **Step 1: Write failing lifecycle tests**

Add tests equivalent to:

    def test_candidate_identity_excludes_observation_timestamps():
        first = make_candidate(observed_at="2026-08-21T10:00:00Z")
        later = replace(first, observed_at="2026-08-21T11:00:00Z")
        assert candidate_id(first) == candidate_id(later)

    def test_public_contract_rejects_absolute_paths():
        with pytest.raises(ValueError, match="absolute path"):
            make_source_revision(object_key=r"C:\private\source.csv")

    def test_unknown_schema_is_rejected():
        with pytest.raises(ValueError, match="schema_version"):
            SourceDefinition.from_dict({"schema_version": "force.unknown/v9"})

- [ ] **Step 2: Verify tests fail**

    py -3.10 -m pytest tests/data_workbench/test_contracts.py -q

Expected: import failure because the package is absent.

- [ ] **Step 3: Implement immutable contracts and hashing**

Define:

    DATA_WORKBENCH_API_SCHEMA = "force.data-workbench-api/v1"

    def canonical_payload(value: object, *, scientific: bool = False) -> str: ...
    def scientific_hash(value: object) -> str: ...
    def candidate_id(candidate: CandidatePack) -> str: ...

Use frozen dataclasses with to_dict and from_dict. Scientific hashing excludes only declared observation, retrieval and approval timestamps.

- [ ] **Step 4: Implement protocols**

Define SourceRegistry.list_sources/get_source, ObjectStore.put_stream/verify, JobStore, ApprovalStore and DataWorkbenchService.discover/fetch/compile/validate/promote with the exact return types from the spec.

- [ ] **Step 5: Implement state-root isolation**

resolve_data_workbench_root(application_state_root) returns application_state_root / "data-workbench", does not inspect Path.cwd(), and does not expose the resolved path in DTOs.

- [ ] **Step 6: Run DATA-01 gates**

    py -3.10 -m pytest tests/data_workbench/test_contracts.py tests/data_workbench/test_state.py tests/test_prompt96_zonal_contracts.py tests/test_prompt97_spatialization.py tests/test_prompt98_gb_zonal_pack_builder.py tests/test_retained_source_manifest.py -q

- [ ] **Step 7: Generate docs, update gap matrix and commit**

    git add gridform_core/data_workbench tests/data_workbench docs/generated/DATA_WORKBENCH_CONTRACT.md docs/data-construction/GAP_MATRIX.md
    git commit -m "feat(data): add workbench lifecycle contracts"

---

### Task 2: DATA-02 official source registry and discovery

**Files:**
- Create: gridform_core/data_workbench/registry.py
- Create: gridform_core/data_workbench/discovery.py
- Create: gridform_core/data_workbench/reporting.py
- Create: gridform_core/data_workbench/sources/uk-network/*.source.json
- Create: tests/data_workbench/fixtures/discovery/*.json
- Create: tests/data_workbench/test_registry.py
- Create: tests/data_workbench/test_discovery.py
- Create: scripts/audit_data_freshness.py
- Modify: pyproject.toml
- Modify: MANIFEST.in
- Modify: source-release-manifest.json
- Modify: docs/data-construction/GAP_MATRIX.md

**Interfaces:**
- Consumes: SourceDefinition and SourceRevision.
- Produces: JsonSourceRegistry, DiscoveryTransport, discover_source and deterministic freshness/candidate reports.

- [ ] **Step 1: Write failing registry tests**

Assert seven source IDs load and duplicate IDs, HTTP URLs, non-allowlisted domains, absent licence expectations and missing candidate uses fail.

- [ ] **Step 2: Add exact source definitions**

Create definitions for neso.dno-license-areas, neso.etys-capabilities, neso.etys-boundary-gis, desnz.postcode-electricity-consumption, ons.postcode-directory, neso.fes-gsp-regional-demand and neso.interconnector-register.

- [ ] **Step 3: Write frozen discovery tests**

Fixture transport returns checked-in NESO/DESNZ/ONS catalogue responses. Assert revision ID, publication date, URL, media type and new/unchanged/superseded/unavailable status.

- [ ] **Step 4: Implement discovery adapters**

    class DiscoveryTransport(Protocol):
        def get_json(self, url: str, *, allowed_domains: tuple[str, ...]) -> Mapping[str, object]: ...
        def get_text(self, url: str, *, allowed_domains: tuple[str, ...]) -> str: ...

    def discover_source(
        source: SourceDefinition,
        transport: DiscoveryTransport,
        installed_revision_id: str | None,
    ) -> tuple[SourceRevision, ...]: ...

Discovery never downloads scientific resource bytes.

- [ ] **Step 5: Implement reports**

render_discovery_reports writes stable JSON and Markdown. Every candidate states usable_for, not_usable_for, blocking_reasons and required_actions.

- [ ] **Step 6: Package sources and test**

    py -3.10 -m pytest tests/data_workbench/test_registry.py tests/data_workbench/test_discovery.py tests/test_reproducible_python_release.py tests/test_source_release_tree.py -q

- [ ] **Step 7: Update gap matrix and commit**

    git add gridform_core/data_workbench pyproject.toml MANIFEST.in source-release-manifest.json scripts/audit_data_freshness.py tests/data_workbench docs/data-construction/GAP_MATRIX.md
    git commit -m "feat(data): add official source discovery"

---

### Task 3: DATA-03 secure fetch and raw-object store

**Files:**
- Create: gridform_core/data_workbench/object_store.py
- Create: gridform_core/data_workbench/fetch.py
- Create: gridform_core/data_workbench/rights.py
- Create: tests/data_workbench/test_object_store.py
- Create: tests/data_workbench/test_fetch.py
- Create: tests/data_workbench/test_rights.py
- Modify: gridform_core/data_workbench/service.py
- Modify: docs/data-construction/GAP_MATRIX.md

**Interfaces:**
- Consumes: SourceRevision, SourceDefinition, FetchTransport and ObjectStore.
- Produces: StoredObject, RawObjectReceipt and RightsDecision.

- [ ] **Step 1: Write failing object-store tests**

For blocks abc and def, assert SHA-256 bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1c5c6d5cd93c4721, duplicate reuse and corruption detection.

- [ ] **Step 2: Implement LocalObjectStore**

Stream to a unique .partial file, hash during write, flush, and atomically move to raw/sha256/hash. Public objects expose key and hash rather than absolute path.

- [ ] **Step 3: Write failing bounded-fetch tests**

Cover HTTPS enforcement, redirect allowlist, media type, byte limit, cancellation, truncated body and transport error. None may emit a receipt.

- [ ] **Step 4: Implement fetch_revision**

    def fetch_revision(
        revision: SourceRevision,
        *,
        source: SourceDefinition,
        transport: FetchTransport,
        object_store: ObjectStore,
        cancel: CancellationToken,
        max_bytes: int,
    ) -> RawObjectReceipt: ...

- [ ] **Step 5: Implement rights decisions**

Allow only redistributable, pointer_only, local_use_only and needs_rights_review. Unknown rights block promotion.

- [ ] **Step 6: Run gates**

    py -3.10 -m pytest tests/data_workbench/test_object_store.py tests/data_workbench/test_fetch.py tests/data_workbench/test_rights.py tests/test_data_bundle.py tests/test_data_bundle_api.py -q

- [ ] **Step 7: Commit**

    git add gridform_core/data_workbench tests/data_workbench docs/data-construction/GAP_MATRIX.md
    git commit -m "feat(data): pin official raw objects safely"

---

### Task 4: DATA-04 DSO and ETYS compilers

**Files:**
- Create: gridform_core/data_workbench/compilers/__init__.py
- Create: gridform_core/data_workbench/compilers/dso_zones.py
- Create: gridform_core/data_workbench/compilers/etys_geometry.py
- Create: gridform_core/data_workbench/compilers/etys_capabilities.py
- Create: gridform_core/data_workbench/compilers/version_reconciliation.py
- Create: tests/data_workbench/fixtures/dso/*.geojson
- Create: tests/data_workbench/fixtures/etys/*.xlsx
- Create: tests/data_workbench/fixtures/etys/*.geojson
- Create: tests/data_workbench/test_dso_compiler.py
- Create: tests/data_workbench/test_etys_compiler.py
- Modify: pyproject.toml
- Modify: requirements/force-all-py310.lock
- Modify: requirements/force-ci-tools-py310.lock
- Modify: docs/data-construction/GAP_MATRIX.md

**Interfaces:**
- Consumes: internally resolved pinned objects.
- Produces: CompiledDsoZones, CompiledEtysEvidence, VersionDecision records and requested waivers.

- [ ] **Step 1: Write DSO tests**

Cover MultiPolygon, EPSG:27700-to-4326 conversion, stable ordering, duplicate IDs and invalid-geometry repair evidence.

- [ ] **Step 2: Add build-only dependency extra**

    data-workbench = [
      "openpyxl==3.1.0",
      "pyproj==3.7.1",
      "shapely==2.1.1",
    ]

Regenerate affected locks only. Ordinary runtime dependencies remain unchanged.

- [ ] **Step 3: Implement compile_dso_zones**

Return source/display FeatureCollections, stable resource-zone records and geometry-repair evidence. Reject undocumented feature loss.

- [ ] **Step 4: Write ETYS tests**

Fixture rows distinguish Capability, Capability (Reverse) and FES percentiles. Assert 2025 Capability selection, reverse fallback, negative-rating rejection and field-level conflict evidence.

- [ ] **Step 5: Implement compile_etys_evidence**

    def compile_etys_evidence(
        workbook: Path,
        geometry: Path,
        *,
        model_year: int = 2025,
        report_extracts: Sequence[OfficialReportExtract] = (),
    ) -> CompiledEtysEvidence: ...

Newer same-semantic values win; geometry and capacity remain separate claims.

- [ ] **Step 6: Run gates**

    py -3.10 -m pytest tests/data_workbench/test_dso_compiler.py tests/data_workbench/test_etys_compiler.py tests/test_dependency_audit_policy.py tests/test_reproducible_python_release.py -q

- [ ] **Step 7: Commit**

    git add gridform_core/data_workbench pyproject.toml requirements tests/data_workbench docs/data-construction/GAP_MATRIX.md
    git commit -m "feat(data): compile DSO and ETYS evidence"

---

### Task 5: DATA-05 regional-demand compiler

**Files:**
- Create: gridform_core/data_workbench/compilers/regional_demand.py
- Create: tests/data_workbench/fixtures/demand/desnz-postcodes.csv
- Create: tests/data_workbench/fixtures/demand/ons-postcodes.csv
- Create: tests/data_workbench/fixtures/demand/fes-gsp.csv
- Create: tests/data_workbench/test_regional_demand.py
- Modify: docs/data-construction/GAP_MATRIX.md

**Interfaces:**
- Consumes: zones, DESNZ consumption, ONS coordinates, FES GSP evidence and unchanged FORCE national demand.
- Produces: region_zone_weights.csv, zonal_demand.csv and DemandReconciliation.

- [ ] **Step 1: Write postcode tests**

Fixture domestic energy is 30 MWh and non-domestic energy is 70 MWh. Assert exact 100 MWh mapping, non-GB exclusion and deterministic boundary-point handling.

- [ ] **Step 2: Implement chunked joins**

Use pandas.read_csv with chunksize 100000 and a Shapely spatial index. Normalize postcodes to uppercase without spaces while preserving original keys in audit rows.

- [ ] **Step 3: Write FES evolution tests**

With base weights 0.4 and 0.6 and growth factors 2.0 and 1.0, assert future weights 4/7 and 3/7.

- [ ] **Step 4: Implement compile_zonal_demand**

    def compile_zonal_demand(
        national_demand_mwh: Sequence[float],
        period_years: Sequence[int],
        base_energy_by_zone: Mapping[str, float],
        fes_by_zone_year: Mapping[tuple[str, int], float],
    ) -> CompiledZonalDemand: ...

Apply floating residual deterministically to the largest positive-demand zone and record pre/post residual.

- [ ] **Step 5: Emit coverage and method reports**

Record measured, calibrated or static_share_fallback per zone/year and energy totals for unmatched, terminated, duplicate and non-GB postcodes.

- [ ] **Step 6: Run gates**

    py -3.10 -m pytest tests/data_workbench/test_regional_demand.py tests/test_prompt96_zonal_contracts.py tests/test_prompt97_spatialization.py -q

Expected maximum demand residual is at most 1e-8 MWh.

- [ ] **Step 7: Commit**

    git add gridform_core/data_workbench tests/data_workbench docs/data-construction/GAP_MATRIX.md
    git commit -m "feat(data): compile regional demand weights"

---

### Task 6: DATA-06 interconnector compiler

**Files:**
- Create: gridform_core/data_workbench/compilers/interconnectors.py
- Create: tests/data_workbench/fixtures/interconnectors/register.csv
- Create: tests/data_workbench/fixtures/interconnectors/sites.csv
- Create: tests/data_workbench/test_interconnectors.py
- Modify: docs/data-construction/GAP_MATRIX.md

**Interfaces:**
- Consumes: register, official site evidence, network zones and asset/country profiles.
- Produces: interconnector_assets.csv, interconnector_profile_allocation.csv, evidence and waivers.

- [ ] **Step 1: Write register and landing tests**

Include IFA/Sellindge, BritNed/Grain, North Sea Link/Blyth and Moyle/Auchencrosh. Assert one GB landing per asset and no internal NI zone.

- [ ] **Step 2: Implement evidence ranking**

Use official_coordinate, official_named_site, operator_supported, inferred_nearest_coast_dso. Preserve rejected conflicting evidence.

- [ ] **Step 3: Write conservation tests**

For equal 1000 MW links and a 1500 MW profile, assert 750/750. For 1000/500 MW links, assert 1000/500. Repeat with signed export.

- [ ] **Step 4: Implement allocation**

    def allocate_country_profile(
        profile_mw: Sequence[float],
        assets: Sequence[InterconnectorAsset],
        period_times: Sequence[str],
    ) -> InterconnectorProfileAllocation: ...

Reject any period that cannot conserve the profile inside directional envelopes.

- [ ] **Step 5: Add nearest-coast tests and implementation**

Assert stable geometry, distance and tie-break. Every inferred result requests inferred_nearest_coast_dso.

- [ ] **Step 6: Run gates**

    py -3.10 -m pytest tests/data_workbench/test_interconnectors.py tests/test_prompt96_zonal_contracts.py -q

- [ ] **Step 7: Commit**

    git add gridform_core/data_workbench tests/data_workbench docs/data-construction/GAP_MATRIX.md
    git commit -m "feat(data): compile interconnector landings"

---

### Task 7: DATA-07 zonal candidate and Prompt 98 facade

**Files:**
- Create: gridform_core/data_workbench/compilers/cut_membership.py
- Create: gridform_core/data_workbench/compilers/gb_zonal_pack.py
- Create: gridform_core/data_workbench/maps.py
- Create: gridform_core/data_workbench/schemas/cut-review.schema.json
- Create: tests/data_workbench/fixtures/cuts/review.json
- Create: tests/data_workbench/test_cut_membership.py
- Create: tests/data_workbench/test_gb_candidate.py
- Modify: gridform_core/gb_zonal_pack_builder.py
- Modify: scripts/build_gb_zonal_pack.py
- Modify: docs/data-construction/GAP_MATRIX.md

**Interfaces:**
- Consumes: DATA-04/05/06 outputs, Prompt 97 mappings and versioned human cut review.
- Produces: unsigned GB candidate, audit map and stable build_candidate facade.

- [ ] **Step 1: Write hand-calculated cut tests**

Assert exact signed corridor tuples and zone sides for one-cut and overlapping-cut fixtures.

- [ ] **Step 2: Implement adjacency and corridor candidates**

Build stable connected transport corridors with endpoints and orientation only. Reject reactance and voltage fields.

- [ ] **Step 3: Implement cut proposals and review**

    def propose_cut_membership(
        zones: Sequence[CompiledNetworkZone],
        corridors: Sequence[CompiledCorridor],
        boundary_geometries: Sequence[CompiledBoundaryGeometry],
    ) -> tuple[CutProposal, ...]: ...

    def apply_cut_review(
        proposals: Sequence[CutProposal],
        review: CutReviewArtifact,
    ) -> tuple[ApprovedCut, ...]: ...

Unreviewed proposals remain needs_mapping.

- [ ] **Step 4: Render maps**

Generate deterministic SVG and GeoJSON with IDs matching machine artifacts. Unknown map IDs fail review.

- [ ] **Step 5: Assemble unsigned candidate**

Write all canonical artifacts, hashes and CandidatePack without installation.

- [ ] **Step 6: Convert Prompt 98 to facade**

Keep validate_source_inventory and build_candidate signatures and result keys stable while delegating to the workbench compiler.

- [ ] **Step 7: Run gates**

    py -3.10 -m pytest tests/data_workbench/test_cut_membership.py tests/data_workbench/test_gb_candidate.py tests/test_prompt96_zonal_contracts.py tests/test_prompt97_spatialization.py tests/test_prompt98_gb_zonal_pack_builder.py -q

- [ ] **Step 8: Commit**

    git add gridform_core/data_workbench gridform_core/gb_zonal_pack_builder.py scripts/build_gb_zonal_pack.py tests/data_workbench docs/data-construction/GAP_MATRIX.md
    git commit -m "feat(data): build reviewed zonal candidates"

---

### Task 8: DATA-08 validation, reports and promotion

**Files:**
- Create: gridform_core/data_workbench/validators/*.py
- Create: gridform_core/data_workbench/promotion.py
- Create: tests/data_workbench/test_validation_gates.py
- Create: tests/data_workbench/test_promotion.py
- Modify: gridform_core/data_workbench/reporting.py
- Modify: docs/data-construction/GAP_MATRIX.md

**Interfaces:**
- Consumes: CandidatePack and optional prior promoted bundle.
- Produces: ValidationIssue, ValidationReport, review artifacts, PromotionRequest and SignedBundleReceipt.

- [ ] **Step 1: Write mutation tests**

Mutate hash, rights, schema, corridor, cut, rating, demand and interconnector. Assert stable issue code and waivable False.

- [ ] **Step 2: Implement independent validators**

    @dataclass(frozen=True)
    class ValidationIssue:
        code: str
        severity: str
        artifact_role: str
        message: str
        evidence: Mapping[str, object]
        repair: str
        waivable: bool

Validators return issues and never modify artifacts.

- [ ] **Step 3: Implement waiver registry**

Register only symmetric_forward_fallback, capacity_weighted_country_split, inferred_nearest_coast_dso and static_share_fallback. Reject irrelevant or unknown waivers.

- [ ] **Step 4: Implement review reports**

Write discovery, inventory, validation, diff, rights, assumptions, reconciliation JSON and review_report.md.

- [ ] **Step 5: Write promotion failure tests**

Stale Candidate hash, mechanical failure, missing reviewer and duplicate version all leave the formal bundle index unchanged.

- [ ] **Step 6: Implement atomic promotion**

Revalidate, build force.data-bundle/v1, validate archive, write local_approval_attestation and atomically install a new immutable ID.

- [ ] **Step 7: Run gates**

    py -3.10 -m pytest tests/data_workbench/test_validation_gates.py tests/data_workbench/test_promotion.py tests/test_data_bundle.py tests/test_data_bundle_api.py tests/test_prompt98_gb_zonal_pack_builder.py -q

- [ ] **Step 8: Commit**

    git add gridform_core/data_workbench tests/data_workbench docs/data-construction/GAP_MATRIX.md
    git commit -m "feat(data): validate and promote data bundles"

---

### Task 9: DATA-09 CLI and local job API

**Files:**
- Create: gridform_core/data_workbench/cli.py
- Create: gridform_core/data_workbench/jobs.py
- Create: gridform_core/data_workbench/sqlite_jobs.py
- Create: gridform_core/data_workbench/__main__.py
- Create: backend/data_workbench_api.py
- Create: tests/data_workbench/test_cli.py
- Create: tests/data_workbench/test_jobs.py
- Create: tests/data_workbench/test_api.py
- Modify: backend/server.py
- Modify: docs/data-construction/GAP_MATRIX.md

**Interfaces:**
- Consumes: DataWorkbenchService and loopback application state.
- Produces: CLI and /api/data-workbench/v1 routes with equivalent DTOs.

- [ ] **Step 1: Write CLI tests**

Assert sources, candidates and fixture discover outputs equal direct service DTOs.

- [ ] **Step 2: Implement CLI**

Use argparse. Commands dispatch only through a single service composition root.

- [ ] **Step 3: Write job-transition tests**

Allow queued -> running -> completed, queued/running -> cancel_requested -> cancelled and queued/running -> failed. Assert state survives reopening SQLite.

- [ ] **Step 4: Implement jobs**

Store ID, operation, declared input, status, progress, timestamps, issue code and result reference. Cancellation is cooperative between bounded stages.

- [ ] **Step 5: Write API tests**

Cover source listing, job start/status/cancel, reports and promotion rejection for stale hash, missing version/reviewer and forged validation.

- [ ] **Step 6: Implement API delegation**

backend/server.py delegates only /api/data-workbench/v1 to backend/data_workbench_api.py. Science logic stays in the service.

- [ ] **Step 7: Run gates**

    py -3.10 -m pytest tests/data_workbench/test_cli.py tests/data_workbench/test_jobs.py tests/data_workbench/test_api.py tests/test_local_backend.py tests/test_data_bundle_api.py tests/test_run_lifecycle.py -q

- [ ] **Step 8: Commit**

    git add gridform_core/data_workbench backend/data_workbench_api.py backend/server.py tests/data_workbench docs/data-construction/GAP_MATRIX.md
    git commit -m "feat(data): expose workbench CLI and local jobs"

---

### Task 10: DATA-10 frontend, official build and Prompt 98 handoff

**Files:**
- Create: app/features/data-workbench/types.ts
- Create: app/features/data-workbench/client.ts
- Create: app/features/data-workbench/DataWorkbench.tsx
- Create: app/features/data-workbench/InstalledPacks.tsx
- Create: app/features/data-workbench/OfficialSources.tsx
- Create: app/features/data-workbench/BuildBenchmark.tsx
- Create: app/features/data-workbench/CandidateReview.tsx
- Create: app/features/data-workbench/data-workbench.css
- Create: e2e/data-workbench.spec.ts
- Create: scripts/build_official_gb_zonal_candidate.py
- Create: scripts/audit_data_workbench_release.py
- Create: publication/data-construction/DATA_WORKBENCH_FINAL_REPORT.md
- Create: publication/data-construction/data-workbench-final-report.json
- Modify: app/page.tsx
- Modify: docs/data-construction/GAP_MATRIX.md
- Modify: docs/scientific-readiness/PROMPT98_GB_ZONAL_PACK_REVIEW.md

**Interfaces:**
- Consumes: DATA-09 API, pinned official local objects and Prompt 98 facade.
- Produces: frontend, official candidate/review package, optional approved bundle and truthful handoff decision.

- [ ] **Step 1: Write frontend client tests**

Assert force.data-workbench-api/v1 decoding and rejection of unknown schema/status.

- [ ] **Step 2: Implement typed client**

    listSources(): Promise<SourceSummary[]>
    startJob(operation: WorkbenchOperation, input: unknown): Promise<JobSummary>
    cancelJob(jobId: string): Promise<JobSummary>
    listCandidates(): Promise<CandidateSummary[]>
    loadCandidate(candidateId: string): Promise<CandidateDetail>
    promoteCandidate(request: PromotionRequest): Promise<SignedBundleReceipt>

- [ ] **Step 3: Implement focused views**

Render Installed packs, Official sources, Build benchmark, Candidates and review. React sends commands and displays reports; it performs no GIS, demand, capability, split or hash calculation.

- [ ] **Step 4: Integrate existing Data page**

Pass the current Study-aware upload workflow into InstalledPacks. Keep new state in app/features/data-workbench rather than further enlarging page-level science logic.

- [ ] **Step 5: Add browser tests**

Test source review, progress, cancel, mechanical lockout, waiver confirmation, experimental install and promotion.

- [ ] **Step 6: Run frontend gates**

    npm run lint
    npm run build
    npx playwright test e2e/data-workbench.spec.ts

- [ ] **Step 7: Run explicit live source gate**

Request network permission. Run freshness, review rights changes, fetch selected official revisions and pin receipts. Missing/changed sources remain isolated.

- [ ] **Step 8: Build official candidate twice**

    py -3.10 scripts/build_official_gb_zonal_candidate.py --build-label official-a
    py -3.10 scripts/build_official_gb_zonal_candidate.py --build-label official-b

Expected: identical scientific hashes and Candidate IDs.

- [ ] **Step 9: Stop for owner review**

Present map, cut review, source/version diff, postcode coverage, FES weights, landings, rights and all waivers. Without explicit owner approval, record stopped_awaiting_owner_promotion.

- [ ] **Step 10: Promote only if approved and verify handoff**

    py -3.10 -m pytest tests/test_prompt96_zonal_contracts.py tests/test_prompt97_spatialization.py tests/test_prompt98_gb_zonal_pack_builder.py tests/test_data_bundle.py tests/test_retained_source_manifest.py -q

- [ ] **Step 11: Run bounded release verification**

    py -3.10 -m pytest tests/data_workbench tests/test_prompt96_zonal_contracts.py tests/test_prompt97_spatialization.py tests/test_prompt98_gb_zonal_pack_builder.py tests/test_data_bundle.py tests/test_data_bundle_api.py tests/test_path_hygiene.py tests/test_source_release_tree.py tests/test_retained_source_manifest.py -q
    npm run lint
    npm run build

- [ ] **Step 12: Generate reports and commit**

    git add app e2e gridform_core/data_workbench backend scripts tests/data_workbench docs/data-construction docs/scientific-readiness/PROMPT98_GB_ZONAL_PACK_REVIEW.md publication/data-construction
    git commit -m "feat(data): complete local data workbench"

## Plan self-review result

- Every approved design section maps to a task.
- Dataset transforms are isolated from runtime, frontend and promotion.
- Later tasks use interfaces defined in earlier tasks with stable names.
- Mechanical failures remain non-waivable through CLI, API and frontend.
- Prompt 98 compatibility is tested before and after facade conversion.
- Live network access occurs only in DATA-10.
- Owner approval is a hard stop before formal promotion.
