# VALUE-UK Research Suite and Methodology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild VALUE 101 so one separately downloaded non-executable UK research suite installs the UK base and zonal network packs, creates copperplate and constrained 2025-2034 Studies, and ships an implementation-grounded Methodology PDF.

**Architecture:** Add one small `value.research-suite/v1` transaction layer above the existing Data Pack installers. The backend validates and atomically promotes two independently hashed packs, then saves two ordinary immutable Study revisions through the existing registry and fingerprint code. The frontend adds one file-install action; the Windows EXE remains data-light and is rebuilt only after focused source, API, UI and documentation checks pass.

**Tech Stack:** Python 3.10 standard library, existing VALUE validators and module registry, React/TypeScript, ReportLab/PyPDF, existing C# Windows installer.

**Spec:** `docs/superpowers/specs/2026-08-25-value-uk-research-suite-and-methodology-design.md`

## Global Constraints

- VALUE is a new model and every active product identity added or changed by this plan uses VALUE naming.
- Do not modify the preserved doctoral Scheme C source or its data.
- Do not place UK research bytes inside `VALUE-101-Setup.exe` or the source release.
- The research suite contains no executable content and installs both component packs atomically.
- The copperplate and zonal templates use identical base data, national demand, annual clock, storage-cost method and CEM chain; only the network domain differs.
- Zonal failure is fail-closed and never falls back to copperplate.
- No AC power flow, security assessment, transmission expansion or scientific-baseline claim is added.
- Add only focused tests for the new trust boundary and user flow; do not run the unrelated full test suite or annual/ten-year production models.
- Build the approximately 300 MiB Windows installer once after source verification; one corrective rebuild is allowed only for an installer defect.

---

### Task 1: Research-suite archive contract and transaction

**Files:**
- Create: `gridform_core/research_suite.py`
- Test: `tests/test_research_suite.py`

**Interfaces:**
- Produces: `build_research_suite(base_bundle: Path, network_bundle: Path, studies_path: Path, rights_paths: Sequence[Path], destination: Path) -> dict[str, object]`
- Produces: `validate_research_suite(path: Path) -> ValidatedResearchSuite`
- Produces: `install_research_suite(path: Path, *, packs_root: Path, network_packs_root: Path, projects_root: Path, dataset_slots: Sequence[Mapping[str, object]], registry: ModuleRegistryV2, validate_project: Callable[[dict[str, object]], dict[str, object]], revision_manifest: Callable[[dict[str, object], dict[str, object]], dict[str, object]], rights_acknowledged: bool, minimum_free_space_bytes: int) -> dict[str, object]`
- Consumes: existing `validate_data_bundle`, `install_data_bundle`, `save_project_revision` and component manifests.

- [ ] **Step 1: Write one failing transaction test**

Create a fixture from the existing VALUE 101 base and network bundles. Assert that one suite installs the two packs into separate roots, creates two saved/unrun Studies, is idempotent, rejects an executable member, and rolls back a newly promoted base pack when the network component is corrupted.

```python
result = install_research_suite(
    suite,
    packs_root=state / "data-packs",
    network_packs_root=state / "data-workbench" / "installed-packs",
    projects_root=state / "projects",
    dataset_slots=DATASET_SLOTS,
    registry=registry,
    validate_project=validate,
    revision_manifest=revision_manifest,
    rights_acknowledged=True,
    minimum_free_space_bytes=0,
)
self.assertEqual(result["component_pack_ids"], [base_id, network_id])
self.assertEqual(result["study_ids"], ["value-uk-copperplate-2025-2034", "value-uk-zonal-2025-2034"])
self.assertFalse(any((state / "runs").glob("*")))
```

- [ ] **Step 2: Run the focused test and observe the missing-module failure**

Run the embedded Python 3.10 test runner against `test_research_suite.py`. Expected: import failure for `gridform_core.research_suite`.

- [ ] **Step 3: Implement the minimal archive and installer**

Use `zipfile`, `hashlib`, `tempfile`, `shutil` and `os.replace`. The outer archive accepts only:

```text
research-suite.json
components/base.data-bundle.zip
components/network.data-bundle.zip
study-templates.json
RIGHTS.json
ATTRIBUTION.md
```

Stream hashes, reject links/traversal/undeclared members, store inner ZIPs without double compression, validate both inner bundles before promotion, track which targets were newly created, and remove only those exact new targets during rollback. Save Studies only after both packs exist and both templates validate. Return pack, Study and SHA identities.

- [ ] **Step 4: Run `test_research_suite.py` and confirm it passes**

- [ ] **Step 5: Commit Task 1**

```text
feat: add atomic VALUE research suite contract
```

### Task 2: UK Study templates and backend installation API

**Files:**
- Create: `gridform_core/value_uk.py`
- Modify: `backend/server.py`
- Test: `tests/test_research_suite_api.py`

**Interfaces:**
- Produces: `value_uk_study_templates(base_pack_id: str, network_pack_id: str) -> tuple[dict[str, object], dict[str, object]]`
- Produces: `POST /api/research-suites/install`
- Consumes: Task 1 installer, `validate_project`, `_revision_manifest`, `MODULE_REGISTRY`, `DATASET_SLOTS`, `PACKS_ROOT`, `PROJECTS_ROOT`, `STATE_ROOT`.

- [ ] **Step 1: Write one failing API test**

Start the existing loopback server with an isolated `VALUE_DATA_HOME`, upload the fixture suite with `X-VALUE-Data-Rights: acknowledged`, and assert HTTP 201, exact VALUE pack IDs, two Study revisions, no Runs, and an idempotent second upload. Upload a suite with a mismatched network ID and assert HTTP 400 with rollback evidence.

- [ ] **Step 2: Run the API test and observe HTTP 404**

- [ ] **Step 3: Implement canonical templates**

The common module chain is:

```python
{
    "psm": "value-staged-bid-at-cost-psm",
    "storage_cost": "dynamic-annual-storage-cost",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
    "transition": "value-annual-state-transition",
}
```

The copperplate template selects `value-copperplate-balancing` and no network extension. The zonal template selects `value-zonal-redispatch-balancing`, `value-zonal-redispatch-extension`, `scenario_scaled_zonal_shares`, the exact Network Pack ID, the current solver contract and version-pinned experimental acknowledgements. Both cover 2025-2034 and use compact market trace plus checkpoints.

- [ ] **Step 4: Add the streaming endpoint**

Mirror the existing 2 GiB Data Pack upload limit and disk-headroom handling. Use VALUE-only error codes beginning `VALUE_RESEARCH_SUITE_`. Return exact component and Study identities plus rollback text. Do not add an Internet downloader.

- [ ] **Step 5: Run `test_research_suite_api.py` and the existing data-bundle and Study-lifecycle tests**

- [ ] **Step 6: Commit Task 2**

```text
feat: install VALUE UK studies from one research suite
```

### Task 3: Data-page and Study/Run user flow

**Files:**
- Modify: `app/page.tsx`
- Modify: `app/globals.css`
- Test: `tests/value-uk-research-suite-ui.test.mjs`

**Interfaces:**
- Consumes: `POST /api/research-suites/install` and workspace Study/Data Pack records.
- Produces: one research-suite file control, rights acknowledgement, component result summary and Study-opening actions.

- [ ] **Step 1: Write one failing source/render test**

Assert that the Data page exposes **Install a VALUE-UK research suite**, accepts one ZIP, never says FORCE, does not launch a Run, and renders both returned Study names and component hashes. Assert that copperplate text contains no Network Pack requirement and zonal text names the exact verified Network Pack.

- [ ] **Step 2: Run the UI test and observe the missing control failure**

- [ ] **Step 3: Add the smallest UI state and upload handler**

Reuse the existing Data Pack installer card, file input, rights checkbox, progress/busy state and notice handling. Add no new UI framework. On success refresh workspace and show:

```text
VALUE-UK copperplate 2025-2034 — saved, not run
VALUE-UK fixed-zonal network 2025-2034 — saved, not run
```

Each action selects the Study and opens Studies. It does not call the run API.

- [ ] **Step 4: Update Study and Run wording**

Ensure the two system domains are described as national single node and fixed GB zones with redispatch. Zonal is marked **Experimental post-thesis network method**. Before a zonal launch, display the base pack, Network Pack, 350,400 periods and resource estimate. Copperplate never shows an empty network workspace.

- [ ] **Step 5: Run the focused UI test, frontend lint and production build**

- [ ] **Step 6: Commit Task 3**

```text
feat: add VALUE UK research suite workflow
```

### Task 4: Assemble the local VALUE-named UK research suite

**Files:**
- Create: `scripts/build_value_uk_research_suite.py`
- Create: `publication/value-uk-research-suite/README.md`
- Generate locally, do not commit: `output/value-uk-release/VALUE-UK-Research-Suite.bundle.zip`
- Test: `tests/test_build_value_uk_research_suite.py`

**Interfaces:**
- Consumes: the existing local 25-role UK pack, installed GB zonal pack, Task 1 builder and Task 2 templates.
- Produces: one VALUE-named suite ZIP and SHA-256 record without mutating either legacy source directory.

- [ ] **Step 1: Write one failing builder test using tiny copied fixture packs**

Assert source manifests remain byte-identical, generated active IDs contain VALUE and no FORCE, template references match components, and the output passes `validate_research_suite`.

- [ ] **Step 2: Run the builder test and observe the missing script failure**

- [ ] **Step 3: Implement the builder**

Read source paths from explicit CLI arguments. Copy to temporary staging, change only active manifest IDs/names and identity references required by the validated VALUE contracts, recompute binding/manifest hashes, build each standard Data Bundle, then build the outer suite. Never write into source packs. Emit a machine-readable build receipt containing source hashes, generated IDs, bytes and SHA-256.

- [ ] **Step 4: Run the focused builder test**

- [ ] **Step 5: Build the real local suite**

Use the verified local UK base pack and owner-approved installed zonal pack. Validate the completed suite and write `VALUE-UK-Research-Suite.bundle.zip.sha256.txt`. If source rights or manifests prevent deterministic resealing, stop rather than weaken validation.

- [ ] **Step 6: Commit source and provenance documentation, excluding the large ZIP**

```text
build: assemble VALUE UK research suite
```

### Task 5: Implementation-grounded Methodology and updated manuals

**Files:**
- Create: `docs/methodology/VALUE_METHODOLOGY.md`
- Create: `scripts/build_value_methodology_pdf.py`
- Modify: `docs/tutorial/VALUE_101_TO_VALUE_UK.md`
- Modify: `scripts/build_value_101_to_value_uk_pdf.py` only if its maintained source list needs the new suite flow.
- Generate: `output/pdf/VALUE_Methodology.pdf`
- Test: `tests/test_value_methodology.py`

**Interfaces:**
- Produces: one maintained English methodology source and generated PDF.
- Consumes: active module manifests, source code, current tutorial sources and the approved design.

- [ ] **Step 1: Write one failing documentation test**

Require the module lifecycle, inputs, outputs, units, equations/algorithms, parameters and limitations. Extract PDF text and require `bid at cost`, `dynamic annual-average`, `planning pipeline`, `fixed zonal`, `redispatch`, `£17,000/MWh`, `scenario_scaled_zonal_shares`, `post-thesis`, `not a security analysis`, and the absence of FORCE.

- [ ] **Step 2: Run the documentation test and observe missing source/PDF**

- [ ] **Step 3: Write the methodology from active implementation evidence**

Cover the 14 sections in the approved spec. For transmission, document DSO-aligned zones, immutable mapping, ETYS-derived signed directional limits, time-dependent ratings, national clearing followed by pay-as-bid redispatch, thermal/VRE/storage/import/DSR/load-shedding participation, actual post-redispatch SOC, curtailment attribution, demand authority, separate ledgers, and all excluded claims. Mark it as post-thesis and do not attribute it to Scheme C.

- [ ] **Step 4: Add the PDF builder by reusing existing ReportLab styles**

Import the existing Markdown-to-flowable helpers; add no PDF dependency. Generate metadata with VALUE title and Hanzhe Xing author.

- [ ] **Step 5: Update the VALUE 101 to VALUE-UK guide**

Replace the manual 25-role-only path with the one-file research-suite path as the prepared-data route, while retaining the route for a researcher to build their own pack. Explain the two created Studies and that installation never starts a Run.

- [ ] **Step 6: Regenerate all three PDFs and run the focused text test**

- [ ] **Step 7: Commit Task 5**

```text
docs: publish VALUE implementation methodology
```

### Task 6: Rebuild and freeze the Windows pilot

**Files:**
- Modify: `scripts/build_windows_pilot_installer.py` only for allowlist/document-link changes required by Tasks 1-5.
- Modify: `tests/test_windows_pilot_installer.py` only if the payload contract changes.
- Generate: `output/value-uk-release/VALUE-101-Setup.exe`
- Generate: `output/value-uk-release/START-HERE-VALUE-101-Guide.pdf`
- Generate: `output/value-uk-release/START-HERE-VALUE-101-TO-VALUE-UK-Guide.pdf`
- Generate: `output/value-uk-release/VALUE-Methodology.pdf`
- Generate: SHA-256 files and `publication/value-uk-research-suite/release-evidence.json`.

**Interfaces:**
- Consumes: completed source, the existing locked Python/Node runtime cache, Task 4 suite and Task 5 PDFs.
- Produces: the final installer and separate UK suite distribution folder.

- [ ] **Step 1: Run focused pre-build verification**

Run only:

```text
test_research_suite.py
test_research_suite_api.py
test_build_value_uk_research_suite.py
test_value_methodology.py
test_data_bundle.py
test_study_lifecycle.py
test_prompt117_value_101_release_gate.py
value-uk-research-suite-ui.test.mjs
npm run lint
npm run build
```

Scan the active installer payload, UI/API output, generated Study/data manifests and three PDFs for obsolete product names. Exclude retained historical audit and doctoral reproduction sources from the scan and from the installer payload.

- [ ] **Step 2: Build the final EXE once**

Use the existing locked builder and reviewed runtime payload policy. Do not embed `VALUE-UK-Research-Suite.bundle.zip`.

- [ ] **Step 3: Perform bounded clean-state acceptance**

In an isolated pilot directory: first-install the EXE, start VALUE, install the research suite, confirm two saved/unrun Studies, run readiness for both templates, and execute one bounded copperplate and one bounded zonal PSM-CEM smoke. Confirm zonal artifacts and fail-closed behaviour with a temporarily unavailable Network Pack. Reinstall while VALUE is running and confirm research packs and Studies remain.

- [ ] **Step 4: Verify the original model and unrelated state are unchanged**

Compare retained Scheme C hashes and the main model directory snapshot; record that no old data or Study was overwritten.

- [ ] **Step 5: Freeze release files and evidence**

Write exact paths, bytes, SHA-256 values, focused test counts, install results, Study IDs and remaining scientific-audit caveats. Do not claim a completed ten-year scientific run.

- [ ] **Step 6: Commit Task 6 source/evidence files, excluding large binaries and local UK data**

```text
release: build VALUE UK capable Windows pilot
```
