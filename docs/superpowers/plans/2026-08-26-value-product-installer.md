# VALUE Product Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the VALUE-101-branded Windows pilot package with a side-by-side, self-contained `VALUE-Setup.exe` that installs the complete VALUE application under `%LOCALAPPDATA%\VALUE`, preserves the old VALUE-101 pilot untouched, and can run bundled teaching models plus separately installed research suites.

**Architecture:** Reuse the existing offline payload builder, C# current-user installer, PowerShell launcher, rollback logic and modular VALUE runtime. Change only the public product identity and installation/state boundary, keep `VALUE 101` as an in-application tutorial, then freeze one installer and validate it with the bundled synthetic pack and the existing frozen VALUE-UK research suite.

**Tech Stack:** Python 3.10, C# WinForms installer compiled with the installed .NET Framework compiler, PowerShell 5+, React/vinext frontend bundle, SQLite local state, ReportLab PDF generation, `unittest` focused checks.

**Spec:** `docs/superpowers/specs/2026-08-26-value-product-installer-design.md`

## Global Constraints

- Public product name is `VALUE`; installer is `VALUE-Setup.exe`.
- Application root is `%LOCALAPPDATA%\VALUE\app`; state root is `%LOCALAPPDATA%\VALUE\state`.
- `%LOCALAPPDATA%\VALUE-101` must never be read for migration, modified, stopped, uninstalled or deleted by the new installer.
- `VALUE 101` remains the tutorial name and the two bundled synthetic Data Pack IDs remain `value-101-baseline-v1` and `value-101-network-v1`.
- The installer remains current-user, terminal-free and offline after download.
- Preserve stop-before-replace, payload integrity, progress UI, transactional replacement and rollback behaviour.
- Do not bundle the rights-governed UK data in the EXE.
- Do not change PSM, CEM, storage, planning or network science.
- Do not run full annual or ten-year scientific models for installer acceptance.
- Reuse existing files and dependencies; introduce no new packaging framework or third-party dependency.
- Build the large final EXE once after source checks; a second build is allowed only if final executable validation reveals an installer-code defect.

## File Responsibility Map

| File | Responsibility after this work |
| --- | --- |
| `packaging/windows-pilot/product.json` | Machine-readable public VALUE Windows product identity and bundled tutorial inventory. |
| `packaging/windows-pilot/ValueInstaller.cs` | Install, upgrade, rollback, shortcut, uninstall and service-lifecycle control for `%LOCALAPPDATA%\VALUE`. |
| `packaging/windows-pilot/ValueInstallerWindow.cs` | VALUE-branded progress and failure window. |
| `packaging/windows-pilot/start-portable.ps1` | Start or stop only the formal VALUE private runtime and state. |
| `scripts/build_windows_pilot_installer.py` | Deterministically assemble the complete runtime and emit `VALUE-Setup.exe`. |
| `tests/test_windows_pilot_installer.py` | Focused identity, isolation, compile, payload and rollback contract checks. |
| `docs/tutorial/*.md` | Explain VALUE as the application and VALUE 101 as its tutorial. |
| `output/pdf/*.pdf` | Generated copies of the three maintained user documents included in the installer. |
| `output/value-product-release/acceptance.json` | Local machine-readable installer acceptance evidence; not committed. |

---

### Task 1: Establish the formal VALUE Windows identity and isolation boundary

**Files:**
- Rename: `packaging/windows-pilot/Value101Installer.cs` to `packaging/windows-pilot/ValueInstaller.cs`
- Rename: `packaging/windows-pilot/Value101InstallerWindow.cs` to `packaging/windows-pilot/ValueInstallerWindow.cs`
- Modify: `packaging/windows-pilot/product.json`
- Modify: `packaging/windows-pilot/start-portable.ps1`
- Modify: `tests/test_windows_pilot_installer.py`

**Interfaces:**
- Consumes: existing installer transaction, rollback, shortcut and current-user registry behaviour.
- Produces: C# entry type `ValueInstaller`, progress type `ValueInstallerWindow`, installation root `%LOCALAPPDATA%\VALUE`, state root `%LOCALAPPDATA%\VALUE\state`, and uninstall key `Software\Microsoft\Windows\CurrentVersion\Uninstall\VALUE`.

- [ ] **Step 1: Add failing product-identity and side-by-side tests**

  Update the test source constants to the renamed C# files and replace the pilot identity assertions with exact VALUE assertions:

  ```python
  BOOTSTRAP = ROOT / "packaging" / "windows-pilot" / "ValueInstaller.cs"
  PROGRESS_WINDOW = ROOT / "packaging" / "windows-pilot" / "ValueInstallerWindow.cs"

  def test_manifest_declares_formal_value_product(self):
      product = json.loads(MANIFEST.read_text("utf-8"))
      self.assertEqual(product["product_name"], "VALUE")
      self.assertEqual(product["install_directory"], "%LOCALAPPDATA%/VALUE/app")
      self.assertEqual(product["state_directory"], "%LOCALAPPDATA%/VALUE/state")
      self.assertEqual(product["entrypoint"], "VALUE-Setup.exe")
      self.assertEqual(
          product["data_packs"],
          ["value-101-baseline-v1", "value-101-network-v1"],
      )

  def test_formal_installer_never_targets_pilot_root(self):
      installer = BOOTSTRAP.read_text("utf-8")
      launcher = LAUNCHER.read_text("utf-8")
      self.assertNotIn('"VALUE-101"', installer)
      self.assertNotIn('"VALUE-101"', launcher)
      self.assertIn('"VALUE"', installer)
      self.assertIn('"VALUE"', launcher)
  ```

- [ ] **Step 2: Run the focused tests and confirm the expected identity failures**

  Run:

  ```powershell
  python -m unittest tests.test_windows_pilot_installer.WindowsPilotInstallerContractTests.test_manifest_declares_formal_value_product tests.test_windows_pilot_installer.WindowsPilotInstallerContractTests.test_formal_installer_never_targets_pilot_root -v
  ```

  Expected: FAIL because the manifest and installer still use the pilot product identity.

- [ ] **Step 3: Rename the installer types and replace only public product constants**

  Use `git mv` for the two C# sources. Rename `Value101Installer` to `ValueInstaller` and `Value101InstallerWindow` to `ValueInstallerWindow`. Define the installer boundary in one place:

  ```csharp
  private const string Product = "VALUE";
  private static readonly string Root = Path.Combine(
      Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
      "VALUE");
  private static readonly string App = Path.Combine(Root, "app");
  private static readonly string State = Path.Combine(Root, "state");
  private static readonly string Uninstaller = Path.Combine(Root, "Uninstall VALUE.exe");
  private const string UninstallRegistryPath =
      @"Software\Microsoft\Windows\CurrentVersion\Uninstall\VALUE";
  ```

  Replace shortcut and window strings with `VALUE`, `Stop VALUE`, `VALUE Guide`, `Uninstall VALUE`, `Installing VALUE`, and `VALUE is ready`. Keep tutorial titles and the two `value-101-*` Data Pack IDs unchanged.

- [ ] **Step 4: Point the portable launcher exclusively at the new roots**

  Make the launcher derive both paths without consulting the pilot:

  ```powershell
  $installRoot = Join-Path $env:LOCALAPPDATA "VALUE"
  $projectRoot = Join-Path $installRoot "app"
  $stateRoot = Join-Path $installRoot "state"
  ```

  Preserve existing owned-process checks, `-Stop`, browser launch and the generic `scripts/start-portable-local.ps1` call. Change only user-facing repair text from `VALUE-101-Setup.exe` to `VALUE-Setup.exe`.

- [ ] **Step 5: Update the machine-readable product declaration**

  Set the public fields exactly as follows while preserving runtime flags and tutorial Data Pack IDs:

  ```json
  {
    "product_name": "VALUE",
    "version": "0.6.0-alpha.2",
    "install_scope": "current-user",
    "install_directory": "%LOCALAPPDATA%/VALUE/app",
    "state_directory": "%LOCALAPPDATA%/VALUE/state",
    "entrypoint": "VALUE-Setup.exe"
  }
  ```

  Change `scientific_scope` to state that VALUE is the modular application and that the bundled VALUE 101 packs are synthetic teaching data.

- [ ] **Step 6: Compile the renamed C# installer and run the installer contract tests**

  Run:

  ```powershell
  python -m unittest tests.test_windows_pilot_installer -v
  ```

  Expected: all tests pass, including the existing transaction, rollback, progress-window and shortcut harnesses updated to instantiate `ValueInstaller` and `ValueInstallerWindow`.

- [ ] **Step 7: Commit the identity boundary**

  ```powershell
  git add packaging/windows-pilot tests/test_windows_pilot_installer.py
  git commit -m "feat: establish formal VALUE Windows product"
  ```

---

### Task 2: Make the existing payload builder emit the formal VALUE installer

**Files:**
- Modify: `scripts/build_windows_pilot_installer.py`
- Modify: `tests/test_windows_pilot_installer.py`

**Interfaces:**
- Consumes: `ValueInstaller.cs`, `ValueInstallerWindow.cs`, `product.json`, existing locked Python/Node payload policy, frontend production bundle and two tutorial Data Packs.
- Produces: `output/value-product-release/VALUE-Setup.exe` containing `VALUE-PAYLOAD-MANIFEST.json` and the complete modular VALUE runtime.

- [ ] **Step 1: Add failing builder-output and payload-name assertions**

  Add exact assertions:

  ```python
  def test_builder_emits_formal_value_names(self):
      source = BUILDER.read_text("utf-8")
      self.assertIn('OUTPUT_NAME = "VALUE-Setup.exe"', source)
      self.assertIn('PAYLOAD_MANIFEST_NAME = "VALUE-PAYLOAD-MANIFEST.json"', source)
      self.assertIn('"packaging/windows-pilot/ValueInstaller.cs"', source)
      self.assertIn('"packaging/windows-pilot/ValueInstallerWindow.cs"', source)
      self.assertNotIn('OUTPUT_NAME = "VALUE-101-Setup.exe"', source)
  ```

- [ ] **Step 2: Run the new builder test and confirm it fails on old names**

  Run:

  ```powershell
  python -m unittest tests.test_windows_pilot_installer.WindowsPilotInstallerContractTests.test_builder_emits_formal_value_names -v
  ```

  Expected: FAIL on the old output, manifest and source names.

- [ ] **Step 3: Update builder constants and compiler inputs**

  Replace only packaging identity constants:

  ```python
  OUTPUT_NAME = "VALUE-Setup.exe"
  PAYLOAD_MANIFEST_NAME = "VALUE-PAYLOAD-MANIFEST.json"
  ```

  Update `EXTRA_RELEASE_FILES` and the C# compiler command to use `ValueInstaller.cs` and `ValueInstallerWindow.cs`. Keep `BUNDLED_DATA_PACKS`, runtime hashes, release documents, source allowlist and dependency lock unchanged.

- [ ] **Step 4: Ensure the embedded C# lookup matches the new payload manifest**

  In `ValueInstaller.cs`, change the archive lookup to:

  ```csharp
  ZipArchiveEntry manifest = archive.GetEntry("VALUE-PAYLOAD-MANIFEST.json");
  ```

  Do not change the manifest validation algorithm or rollback order.

- [ ] **Step 5: Run focused builder and compile-contract tests without building the large EXE**

  Run:

  ```powershell
  python -m unittest tests.test_windows_pilot_installer -v
  ```

  Expected: PASS. This test phase may compile the small C# harness but must not assemble the 300 MB runtime payload.

- [ ] **Step 6: Commit the builder identity**

  ```powershell
  git add scripts/build_windows_pilot_installer.py packaging/windows-pilot/ValueInstaller.cs tests/test_windows_pilot_installer.py
  git commit -m "build: emit VALUE Windows installer"
  ```

---

### Task 3: Align maintained guides with VALUE as the application

**Files:**
- Modify: `README.md`
- Modify: `docs/tutorial/VALUE_101.md`
- Modify: `docs/tutorial/VALUE_101_ZH.md`
- Modify: `docs/tutorial/VALUE_101_TO_VALUE_UK.md`
- Modify: `docs/tutorial/JOHN_PILOT_RUNBOOK.md`
- Modify: `tests/test_prompt116_value_101_docs.py`
- Modify: `tests/test_windows_pilot_installer.py`
- Regenerate: `output/pdf/VALUE_101_guide.pdf`
- Regenerate: `output/pdf/VALUE_101_TO_VALUE_UK_guide.pdf`
- Regenerate: `output/pdf/VALUE_Methodology.pdf`

**Interfaces:**
- Consumes: the formal installer identity from Tasks 1–2 and existing maintained Markdown-to-PDF scripts.
- Produces: three PDFs embedded by the builder, with VALUE installation instructions and VALUE 101 tutorial terminology kept separate.

- [ ] **Step 1: Add exact documentation identity checks**

  Add assertions that installation instructions use the formal package and paths while tutorial headings remain valid:

  ```python
  def test_value_application_and_value_101_tutorial_are_distinct(self):
      english = (TUTORIAL / "VALUE_101.md").read_text("utf-8")
      chinese = (TUTORIAL / "VALUE_101_ZH.md").read_text("utf-8")
      supplement = (TUTORIAL / "VALUE_101_TO_VALUE_UK.md").read_text("utf-8")
      for text in (english, chinese, supplement):
          self.assertIn("VALUE-Setup.exe", text)
          self.assertNotIn("VALUE-101-Setup.exe", text)
      self.assertIn("VALUE 101", english)
      self.assertIn("%LOCALAPPDATA%\\VALUE\\state", english)
  ```

- [ ] **Step 2: Run the focused documentation tests and confirm old package references fail**

  Run:

  ```powershell
  python -m unittest tests.test_prompt116_value_101_docs -v
  ```

  Expected: FAIL until installation and state-path wording is updated.

- [ ] **Step 3: Update installation, stop, uninstall and diagnostics wording**

  Apply this terminology consistently:

  ```text
  Application: VALUE
  Installer: VALUE-Setup.exe
  Desktop/Start-menu launcher: VALUE
  Stop shortcut: Stop VALUE
  Uninstaller: Uninstall VALUE
  Application state: %LOCALAPPDATA%\VALUE\state
  Tutorial: Learn -> VALUE 101
  ```

  State explicitly that the old VALUE-101 pilot is a separate installation, is not migrated, and may remain installed. Do not rename teaching Studies, teaching Data Packs or the tutorial itself.

- [ ] **Step 4: Keep the research-upgrade boundary explicit**

  In the VALUE 101 to VALUE-UK guide, retain the existing suite-install instructions and add one concise sentence: the VALUE application accepts the separate suite without reinstalling the application, while the installer itself contains no rights-governed UK data.

- [ ] **Step 5: Regenerate all three maintained PDFs from Markdown**

  Run:

  ```powershell
  python scripts/build_value_101_pdf.py
  python scripts/build_value_101_to_value_uk_pdf.py
  python scripts/build_value_methodology_pdf.py
  ```

  Expected: the three files under `output/pdf` are recreated successfully; no PDF binary is edited by hand.

- [ ] **Step 6: Run bounded text and documentation checks**

  Run:

  ```powershell
  python -m unittest tests.test_prompt116_value_101_docs tests.test_preflight_documentation -v
  python -m unittest tests.test_windows_pilot_installer.WindowsPilotInstallerContractTests.test_builder_is_fail_closed_and_pins_runtime_downloads -v
  ```

  Expected: PASS and PDF text extraction contains `VALUE-Setup.exe`, `VALUE 101`, `network pack`, and `input snapshot` where required by the maintained guide contracts.

- [ ] **Step 7: Commit maintained sources and generated documents**

  ```powershell
  git add README.md docs/tutorial output/pdf tests/test_prompt116_value_101_docs.py tests/test_windows_pilot_installer.py
  git commit -m "docs: distinguish VALUE from VALUE 101 tutorial"
  ```

---

### Task 4: Perform source preflight and build the final installer once

**Files:**
- Read: `packaging/windows-pilot/runtime-payload-policy.json`
- Read: `requirements/value-all-py310.lock`
- Read: `output/pdf/*.pdf`
- Create locally: `output/value-product-release/VALUE-Setup.exe`
- Create locally: `output/value-product-release/build-metadata.json`

**Interfaces:**
- Consumes: all committed implementation and documentation from Tasks 1–3.
- Produces: one frozen installer candidate plus source revision, file size and SHA-256 evidence.

- [ ] **Step 1: Run only affected source-level gates**

  Run:

  ```powershell
  python -m unittest tests.test_windows_pilot_installer tests.test_prompt116_value_101_docs tests.test_preflight_documentation -v
  python -m unittest tests.test_provenance_errors -v
  python -m unittest tests.test_prompt101_staged_cem_integration.Prompt101LiveIntegrationTests.test_live_zonal_path_records_redispatch_avoided_vre_curtailment tests.test_prompt101_staged_cem_integration.Prompt101StudyAndReleaseContractTests.test_explicit_market_fields_must_match_authoritative_module_selection -v
  ```

  Expected: all selected tests pass. These are the retained failure-persistence and live zonal-path checks touched by commit `130004e`; do not expand to the full suite.

- [ ] **Step 2: Check release inputs before paying the build cost**

  Run:

  ```powershell
  git diff --check
  git status --short
  Test-Path output/pdf/VALUE_101_guide.pdf
  Test-Path output/pdf/VALUE_101_TO_VALUE_UK_guide.pdf
  Test-Path output/pdf/VALUE_Methodology.pdf
  ```

  Expected: no whitespace errors, the intended source modifications are committed, unrelated local outputs remain untouched, and all PDFs exist.

- [ ] **Step 3: Build the self-contained installer once**

  Run:

  ```powershell
  python scripts/build_windows_pilot_installer.py --output-dir output/value-product-release --cache-dir output/value-installer-cache
  ```

  Expected: `output/value-product-release/VALUE-Setup.exe` exists and the builder completes without downloading an unverified runtime.

- [ ] **Step 4: Audit the frozen executable without rebuilding**

  Use the existing builder/test helpers to verify the embedded payload manifest, runtime inventory identity, product manifest, frontend bundle, three PDFs, both tutorial packs and renamed C# sources. Record:

  Use these commands as the authoritative evidence source:

  ```powershell
  $installer = Resolve-Path 'output/value-product-release/VALUE-Setup.exe'
  git rev-parse HEAD
  Get-FileHash -LiteralPath $installer -Algorithm SHA256
  Get-Item -LiteralPath $installer | Select-Object FullName,Length,LastWriteTime
  ```

  Store those command results in `output/value-product-release/build-metadata.json` with keys `product`, `installer`, `source_commit`, `sha256` and `size_bytes`. `product` must be `VALUE`, `installer` must be `VALUE-Setup.exe`, and `size_bytes` must be non-zero. Do not rebuild for wording or formatting differences.

- [ ] **Step 5: Stop on an installer-code defect before any second build**

  If executable inspection proves a code defect, patch that single defect, rerun the directly affected test, and permit one final rebuild. If another rebuild would be needed, stop and report the root cause instead of cycling.

---

### Task 5: Validate clean install, research-suite use, upgrade isolation and freeze the handoff

**Files:**
- Read only: `%LOCALAPPDATA%\VALUE-101`
- Install/modify locally: `%LOCALAPPDATA%\VALUE`
- Read: `output/value-uk-release/VALUE-UK-Research-Suite.bundle.zip`
- Create locally: `output/value-product-release/acceptance.json`

**Interfaces:**
- Consumes: frozen `VALUE-Setup.exe`, frozen VALUE-UK suite, existing smoke-run entry points and health endpoints.
- Produces: evidence that the formal VALUE application installs, teaches, accepts research data, runs copperplate and zonal bounded cases, upgrades in place and leaves the pilot/source untouched.

- [ ] **Step 1: Snapshot the protected pilot and source before installation**

  Record directory existence, selected file hashes and Git status without changing either target:

  ```powershell
  Get-FileHash "$env:LOCALAPPDATA\VALUE-101\app\packaging\windows-pilot\product.json" -Algorithm SHA256
  git status --short
  git rev-parse HEAD
  ```

  If the pilot file does not exist, record `pilot_not_installed`; do not create it.

- [ ] **Step 2: Create a recoverable clean formal-product state**

  If `%LOCALAPPDATA%\VALUE` exists, stop its owned services and move that exact directory to a timestamped sibling such as `%LOCALAPPDATA%\VALUE.pre-acceptance-20260826-HHMMSS`. Verify the resolved source and destination are both children of `%LOCALAPPDATA%` before moving. Never target `%LOCALAPPDATA%\VALUE-101`.

- [ ] **Step 3: Run the frozen installer and verify local services**

  Double-click or start `VALUE-Setup.exe`, observe its progress window to 100%, then verify:

  ```text
  http://127.0.0.1:8800  -> VALUE frontend responds
  http://127.0.0.1:8766  -> VALUE backend health responds
  %LOCALAPPDATA%\VALUE\app exists
  %LOCALAPPDATA%\VALUE\state exists
  Desktop shortcut is VALUE
  ```

  A failure here is an installer blocker; save the diagnostic path and do not broaden testing.

- [ ] **Step 4: Run the bundled VALUE 101 baseline**

  In `Learn -> VALUE 101`, create and run the bundled baseline. Confirm that execution and contract checks pass, results remain labelled as teaching evidence, and the run is stored under the new VALUE state root.

- [ ] **Step 5: Install the frozen VALUE-UK research suite**

  Use the existing in-product suite installer with:

  ```text
  output/value-uk-release/VALUE-UK-Research-Suite.bundle.zip
  ```

  Confirm the recorded suite SHA-256 remains `274d7147509e9413b95b0501aae88dcd092d49cb3c6bdd2fb82fac36baa89f14`. Read the complete base and network component identities from the signed bundle manifest and compare them byte-for-byte with the retained release audit in `output/value-uk-release`; if either differs, stop rather than rewriting the suite.

- [ ] **Step 6: Run the bounded VALUE-UK copperplate acceptance case**

  Select the installed VALUE-UK base pack and copperplate system domain, then run `two_year_smoke` with two half-hour periods per model year. Confirm 2/2 years complete, execution passes, contract check passes and no internal network pack is introduced.

- [ ] **Step 7: Run the bounded VALUE-UK zonal acceptance case**

  Select the same base pack, fixed-zonal system domain and compatible installed network pack, then run `two_year_smoke` with two half-hour periods per model year. Confirm 2/2 years complete, execution passes, contract check passes, the exact network-pack ID/hash is frozen, and redispatch artifacts exist.

- [ ] **Step 8: Reinstall while VALUE is running**

  Leave the formal VALUE frontend and backend running, start the same frozen `VALUE-Setup.exe`, and verify that the installer stops only the two owned VALUE processes, replaces `%LOCALAPPDATA%\VALUE\app`, preserves `%LOCALAPPDATA%\VALUE\state`, restarts successfully and retains the baseline plus suite/run records.

- [ ] **Step 9: Prove isolation and source preservation**

  Repeat the pilot hash and source Git checks from Step 1. Expected: the old VALUE-101 hash is identical when present, the source commit is unchanged, and no tracked source file was modified by installation or model runs.

- [ ] **Step 10: Write concise local acceptance evidence and freeze hashes**

  Populate `output/value-product-release/acceptance.json` from the evidence collected in Steps 1–9. It must contain the computed 64-character lowercase installer SHA-256, the fixed suite SHA-256 `274d7147509e9413b95b0501aae88dcd092d49cb3c6bdd2fb82fac36baa89f14`, pass/fail strings for first install, frontend health, backend health, tutorial baseline, copperplate smoke, zonal smoke and running reinstall, plus booleans for new-state preservation, pilot isolation and source-worktree preservation. Validate the file with:

  ```powershell
  python -m json.tool output/value-product-release/acceptance.json
  ```

  Do not commit the EXE, UK suite, run state or acceptance output. Handoff consists of the absolute EXE path, SHA-256, the unchanged UK suite path/hash, and any blocker discovered during these bounded checks.

## Completion Gate

The work is complete only when all five tasks pass. Success means the formal VALUE installer is operational and can accept the existing research suite; it does not claim a new annual or ten-year scientific baseline. A failure in installation, state preservation, suite installation, copperplate smoke, zonal smoke or pilot isolation blocks handoff.
