# P0 acceptance handbook (VALUE 0.7.0-alpha.1)

This handbook says how the P0 review fixes of branch `fix/review-2026-10-04`
are accepted: which gate runs when, which golden cases it covers, how long it
takes and how much disk it needs, how to read the golden delta report, and how
a managed installation is later reinstalled from the branch and checked.

Status (2026-10-06): sections 1–5 describe checks that run on the source tree
and are part of the construction. **Section 6, the reinstall, has not been
executed.** It is a release step (plan milestone M8): building installers,
replacing the running installation and every push need the author's explicit
approval, one step at a time. Paths below are placeholders: `<SRC>` is a
checkout of the branch, `<OLD>` the installation prefix in use (0.6.0-alpha.2),
`<NEW>` a new, empty installation prefix.

Authority: `docs/dev/P0_DECISIONS.md` > `docs/dev/P0_CONVENTIONS.md` >
`docs/dev/P0_CONSTRUCTION_PLAN.md` (construction documents, not part of the
public source).

## 1 Gate tiers

`scripts/p0_gate.py <tier>` writes its report to `<tmp>/p0-gate-report.json`.
Only `status: passed` (exit 0) counts as passed; a skipped mandatory step or a
`--skip`/`--only` run is `passed_with_waivers` (exit 2) and is treated as a
failure by the integrator.

| Tier | When | Steps (in order) | Disk floor | Measured |
|---|---|---|---|---|
| `quick` | before every commit | guard, test_environment, release_manifest, release_path_hygiene, methodology_catalog, runtime_overlay, version_ledger, golden_bookkeeping, append_only, backend_ratchet, node_tests, http_harness, typecheck_frontend, eslint_ratchet (+ network_guard, installed_inventory) | 1 GB free | 139 s (2026-10-06, 32-core reference machine) |
| `full` | before a package is merged; at M7 and M8 | quick + pytest_ratchet, golden_full (D4, C5, D5), reference_tables, publication_scope, e2e_offline, energy_balance | 1.5 GB free | 419 s (2026-10-06, without the GBP1 pack, so D5 unavailable; e2e 129 s, golden_full 142 s) |
| `nightly` | at the end of each milestone | full + golden_nightly (C6), validation_oracles, golden_sensitivity | 2 GB free | full + about 17 min (C6) |

Test environment: the gate venv (`VALUE_GATE_VENV`, an overlay venv on the
installation's Python 3.10.18 with the pinned `requirements/value-test-py310.lock`).
The gate never writes into the managed installation (guard and
`installed_inventory`), and no test may connect to or listen on the live ports
8766/8800 (`network_guard`).

The backend unittest ratchet (`scripts/run_backend_tests.py`) and the pytest
ratchet compare against `tests/baselines/known-failures-*.txt`: a new failure,
or a fixed test still listed, fails the gate. Baselines only shrink.

## 2 Golden cases

Inputs are frozen in `tests/golden/projects/<case>.json`; every case runs in
its own hermetic subprocess (`scripts/golden/run_case.py`).

| Case | Family | Tier | Pack | Mode | Time | Output |
|---|---|---|---|---|---|---|
| D1 | doctoral | fast | value-101-baseline-v1 | smoke | about 5 s | 0.8–2.4 MB |
| D2 | doctoral | fast | value-101-baseline-v1 | two_year_smoke | about 5 s | 0.8–2.4 MB |
| D3 | doctoral | fast | value-101-baseline-v1 | value_101_day | about 5 s | 0.8–2.4 MB |
| D4 | doctoral | full | value-101-baseline-v1 | two_year | about 115 s, peak RSS 486 MB | about 96 MB |
| D5 | doctoral | full | GBP1 public1 research pack (not in the repository; `VALUE_P0_5_PACKS`) | full, one model year | one 17,520-period year | research pack 804 MB, read only |
| C1–C4 | corrected | fast | value-101-baseline-v1 | smoke / two_year_smoke / value_101_day / smoke | about 5 s each | 0.8–2.4 MB |
| C5 | corrected | full | value-101-baseline-v1 | two_year (legacy storage) | about 115 s | about 96 MB |
| C6 | corrected | nightly | value-101-baseline-v1 | two_year (dynamic storage) | about 972 s, peak RSS 622 MB | about 100 MB |
| C7 | corrected | fast | value-101-network-v1 | staged copperplate smoke | about 5 s | about 7.5 MB |
| C8 | corrected | fast | value-101-network-v1 | zonal redispatch value_101_day | about 11 s | about 7.5 MB |

Without the GBP1 pack, `capture.py check` lists D5 as `unavailable` and does
not fail (set `VALUE_GOLDEN_REQUIRE_RESEARCH_PACKS=1` to make it fail). Long
cases run one after the other and their output is deleted after digesting.

Commands:

```bash
python -B scripts/golden/capture.py check --tier fast        # D1-D3, C1-C4, C7, C8
python -B scripts/golden/capture.py check --tier full        # + D4, C5, D5
python -B scripts/golden/capture.py validate                 # bookkeeping only, no runs
python -B scripts/golden/delta_report.py --check             # attribution + report up to date
```

## 3 Milestone acceptance

| Milestone | Gate | Acceptance (summary; the plan's chapter 2 table is authoritative) |
|---|---|---|
| M0 foundation | quick, full | baselines collected twice and equal; both golden families at revision 0; delta report empty |
| M1 software safety (P0-1, P0-2, P0-3) | quick, full | no new failures; both golden families unchanged; local API boundary tests and the F5-01 replay refused |
| M2 profiles, advisories, honest display, P0-8a | quick, full | changing only the profile changes only the `method` dimension; pre-fix runs read without disk writes, a recorded `passed` shown as `superseded_pre_fix`; zonal solver contract v4 |
| M3 energy-balance observation, data reading (P0-4 S4–S6, P0-5a) | quick, full | doctoral trajectory bit-identical; accounting revisions only under P0-4 ids |
| M4 default PSM clearing (P0-6, P0-4 S7) | quick, full | doctoral rule set equal to the 96-period synthetic golden; corrected runs pass the oracle (raw residual <= 1e-6) |
| M5 corrected data science, investment (P0-5b, P0-7) | quick, full, nightly | physical acceptance against author-reviewed reference statistics; every dual-profile delta row maps to a correction id |
| M6 network economics (P0-8b) | quick, full | renaming assets changes nothing; single-zone network cost 0; binding boundary dual 66.5 |
| M7 frontend close and integration | full, nightly | no `apiOrigin`; tsc clean, ESLint not growing; e2e passes except registered failures; this handbook's section 5 drill |
| M8 release close and reinstall (author approval per step) | full, nightly | version consistency, `check_publication_scope`, `source_release_scan`; installers rebuilt and verified; section 6 |

## 4 Golden delta report

`scripts/golden/delta_report.py` reads only the committed golden files and
produces `docs/release/P0_GOLDEN_DELTA.md`:

- **Delta against revision 0.** For each case, the columns of the latest
  revision that differ from revision 0 (35aadb3), by zone (trajectory /
  accounting / identity), each attributed to the correction ids of the
  revisions that changed it.
- **Dual-profile delta.** For each doctoral case and its corrected partner on
  the same pack and mode (D1–C4, D2–C2, D3–C3, D4–C5), the columns where the
  latest digests differ. Columns that already differed at revision 0 carry
  `profile.reference-configuration` (the doctoral reference configuration,
  decision Q3, and a different storage-cost module where the partner uses
  one), which is a configuration difference, not a correction.

Every row must map to a correction id; `--check` (and
`tests/test_golden_delta_report.py`) fail otherwise, and also when the
committed report is out of date. A commit that revises a golden file runs
`delta_report.py --write` in the same commit. The report lists which columns
changed and why; the magnitudes of the approved doctoral trajectory
re-baselines (P6-24, P6-02, P6-03, P6-04, P4-01-thermal) are in
`tests/golden/reports/<case>-r<k>.json`.

## 5 Branch acceptance drill (before any reinstall)

Run in `<SRC>` with the gate venv, as an unprivileged user, with nothing
listening on a port the drill uses. A scratch server, if one is started, uses
its own port (for example 18xxx) and its own `VALUE_DATA_HOME`, and is stopped
by the PID recorded when it was started.

1. `git status` is clean; `python -B scripts/refresh_source_release_manifest.py --check`.
2. `python -B scripts/p0_gate.py quick`, then `full`, then `nightly`
   (each `status: passed`).
3. `python -B scripts/golden/delta_report.py --check`.
4. `python -B scripts/check_version_ledger.py`; `python -B -m unittest
   tests.test_documentation_consistency` (the version test passes: package.json
   `0.7.0-alpha.1`, pyproject `0.7.0a1`, README).
5. `python -B scripts/check_publication_scope.py --report <scratch>/scope.json`
   (its source-scope checks are the `full` step `publication_scope`) and
   `python -B scripts/source_release_scan.py --json-output <scratch>/scan.json`.
6. Optional, on a scratch instance: run VALUE 101 once under each profile
   (the corrected default and "Doctoral reproduction (as implemented in VALUE
   0.6.0-alpha.2)"); the doctoral run's annual results are published only if
   every raw invariant passed (decision Q14), otherwise the result page says
   they are withheld and Inspect/export still work. The fast golden cases D3
   and C3 run the same day-length VALUE 101 study under both profiles.

## 6 Reinstall procedure (not executed; each step needs the author's approval)

The Linux installer installs only into an absent or empty directory and never
migrates or overwrites existing state ("upgrade into another empty
directory"). Its receipt pins the absolute runtime paths, so an installed
prefix must not be moved or renamed afterwards. Both versions use the fixed
ports 8766 (API) and 8800 (UI), so they cannot run at the same time.

### 6.1 Preconditions

- The author has approved the reinstall and accepted the branch (M7 drill
  passed, M8 version and claims checks passed).
- At least 10 GB free on the root filesystem (`df -h /`).
- An installer built from the branch and verified on its own
  (`scripts/prepare_private_runtimes.py`, `scripts/build_full_desktop_installers.py`,
  each with its own approval; `app/scripts/value-ui-gateway.mjs` and
  `backend/lifecycle/*` are release members). Building is not part of this
  handbook.
- No run is active in `<OLD>`: its result page shows no running or queued run,
  and when `<OLD>` was last stopped it printed no "keep running in the
  background" line. A run left unfinished by 0.6.0-alpha.2 cannot be resumed
  by 0.7.0-alpha.1 (the backend source hash is part of the execution
  identity); finish or cancel it first.

### 6.2 Stop and record the old installation

1. The author stops `<OLD>` in its own terminal with Ctrl+C (the launcher
   stops the API and the UI). Do not signal processes by name or pattern.
2. Confirm that nothing listens on 8766 or 8800 (`ss -ltnp`).
3. Record the old state for later comparison (read only):

   ```bash
   cd <OLD>/state && find . -type f ! -path './runtime/*' -print0 \
     | sort -z | xargs -0 sha256sum > <scratch>/old-state.sha256
   ```

4. Keep `<OLD>` untouched as the rollback target; it also serves as the base
   interpreter of the construction gate venv until that venv is rebuilt on the
   new runtime (plan X0 Q-E).

### 6.3 Install side by side and carry the state over

1. Unpack the verified installer to a temporary directory and run
   `./install-value --prefix <NEW>` (`<NEW>` absent or empty). The installer
   creates `<NEW>/state` with the VALUE 101 pack only.
2. Before the first start of `<NEW>`, replace its fresh state with a copy of
   the old one, leaving out per-process files:

   ```bash
   mv <NEW>/state <NEW>/state.installer-fresh
   rsync -a --exclude '/runtime/' --exclude '/.backend.lock' <OLD>/state/ <NEW>/state/
   ```

   - `runtime/api-session-<port>.json` (session file) is written by each API
     process for itself and must not be copied; 0.6.0-alpha.2 did not write one.
   - `.backend.lock` (one backend per data directory) and the installation's
     `.supervisor.lock` belong to a running process; they are not copied.
   - Run directories, Studies, packs, modules and `state-metadata.json`
     (`value.local-state/v1`, unchanged schema) are copied byte for byte.
     Immutable run directories are never rewritten by the new version.
3. Verify the copy against the record of 6.2:

   ```bash
   cd <NEW>/state && sha256sum --quiet -c <scratch>/old-state.sha256
   ```

### 6.4 First start and reconciliation

1. `<NEW>/diagnose-value` ends with "Installation integrity and runtime checks
   passed." (stray bytecode, if any, is reported; `--repair-bytecode` moves it
   to `state/quarantine`).
2. The author starts `<NEW>/start-value` in a terminal and waits for
   "VALUE ready: http://127.0.0.1:8800/".
3. At start the backend takes `.backend.lock` and reconciles every run
   before binding its port: a run recorded as queued or running without a
   live worker lease becomes failed (`GF_WORKER_LOST`), a run left in
   `deleting` by an earlier version is repaired, a reservation lock file left
   by the old O_EXCL scheme is removed, and run directories without
   `status.json` move to `trash/orphan-runs`. Read the reconciliation lines in
   `<NEW>/logs/backend.log`; for the six historical runs (all completed) no
   change is expected.

### 6.5 Post-install acceptance

Run from `<NEW>/app` with the installation's interpreter
(`<NEW>/runtime/python/bin/python3.10 -B -s`, `PYTHONDONTWRITEBYTECODE=1`).
Direct API requests carry the session header from
`backend.api_session.authorized_headers(<NEW>/state, 8766)`; the token is
never printed or passed on a command line.

1. **Security boundary.** `scripts/verify_local_security_boundary.py`
   exits 0 (PASS: every probe refused).
2. **Historical runs read only.** For each of the six runs carried over
   (`release-r1…`, `release-r2…`, `release-r3…`, `release-r4…`,
   `release-teachin…`, `value-101-basel…`), `GET /api/runs/<id>` and
   `GET /api/runs/<id>/summary` return `advisories` including
   `VALUE-ADV-2026-10-04-REVIEW`; a recorded `passed` is shown as
   `superseded_pre_fix` with the original value kept in
   `recorded_scientific_validation_status`; the Run context bar shows the
   advisory banner. After the GETs, `sha256sum --quiet -c` of 6.3 step 3
   still passes for `runs/` (read-time advisories write nothing).
3. **Saved Study migration.** For a Study saved under 0.6.0-alpha.2,
   `GET /api/projects/<id>/revision-migration` returns a classification
   (`code_identity_upgrade` and `environment_reidentify` append a revision
   automatically when the Study next starts a run; `method_upgrade_required`
   needs the
   explicit confirmation in the UI, decision Q13) and writes nothing.
4. **VALUE 101 under both profiles.** In the UI, run the VALUE 101 Study once
   with the corrected default and once with "Doctoral reproduction (as
   implemented in VALUE 0.6.0-alpha.2)". The corrected run publishes annual
   results unless a validation gate fails; the doctoral run publishes them only
   when every raw invariant passed (Q14), otherwise the result page says they
   are withheld and Inspect/export still work. Stress events, if any, appear in
   the Run context bar and in Market replay.
5. **Network teaching pack.** The VALUE 101 network two_year_smoke run records
   0 reliability-event rows.
6. **Diagnose again.** `<NEW>/diagnose-value` passes; nothing under
   `<NEW>/app` or `<NEW>/runtime` is newer than `install-receipt.json`.

### 6.6 Rollback

Stop `<NEW>` with Ctrl+C in its terminal and start `<OLD>/start-value`
again: `<OLD>` and its state were never modified. Runs made by 0.7.0-alpha.1
in `<NEW>/state` are not readable as fully verified by 0.6.0-alpha.2 and stay
in `<NEW>`. Remove `<NEW>` only on the author's instruction.
