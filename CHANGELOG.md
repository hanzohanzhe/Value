# Changelog

## Unreleased — P0 fixes on fix/review-2026-10-04

### External modules and extensions cannot stop VALUE (P0-2)

- Built-in modules stay fail-closed; locally installed (external) module and
  extension manifests are fail-isolated.  A manifest that cannot be read, an
  implementation that raises anything while importing (including
  `SystemExit`), an external ID or namespace that collides with another
  external entry (every party is quarantined, there is no implicit winner) or
  with a built-in (only the external entry is quarantined) is listed as
  quarantined in memory; nothing is written into `modules/`.  A failed import
  is not retried in the same process until `POST /api/modules/rescan`.
- Install and enable refuse namespace conflicts before writing anything
  (`GF_EXTENSION_NAMESPACE_COLLISION`, naming the real owner) and then check
  the registry twice — in process and in a fresh, worker-like Python process
  — rolling the change back byte for byte if either refuses
  (`GF_EXTENSION_REGISTRY_CONFLICT`, `GF_MODULE_REGISTRY_CONFLICT`,
  `GF_MODULE_PROBE_FAILED`, `GF_MODULE_PROBE_TIMEOUT`).  Each install or
  enable takes about 1–2 s longer.  Disabling is always possible, also for a
  schema-drifted extension and for a quarantined entry that saved Studies
  still name (active runs still block it).
- The module catalogue is built on first use, never at import;
  `DATASET_SLOTS` moved to `gridform_core/dataset_slots.py` (re-exported by
  `gridform_core.catalog`).  A worker no longer imports the catalogue, so a
  broken module fails the run with `GF_MODULE_QUARANTINED` instead of leaving
  it queued.  Draft resolution, preflight and Study derivation report
  `GF_STUDY_MODULE_QUARANTINED` / `GF_PREFLIGHT_MODULE_QUARANTINED` only when
  the Study selects quarantined code; otherwise they add one warning.
  `preflight.json` records `checks.module_quarantine` and
  `checks.external_code`.
- Offline self-rescue without importing any installed code:
  `python -m gridform_core.module_recovery list | disable module|extension <id> |
  park-manifest module|extension <file> | park-installation module|extension <id> [<version>] |
  verify`; the user guide ("Offline module recovery") gives the command for
  an installed VALUE (bundled interpreter, `-B -s`, `PYTHONPATH=<prefix>/app`,
  `--modules-root <prefix>/state/modules`).  A damaged installation record
  (which refuses every run start) is reported as
  `GF_MODULE_INSTALL_RECORD_INVALID` and parked with `park-installation`.
- **API contract changes (additive):** `/api/health` reports
  `status: degraded` with `degraded_reasons [{code, count}]`
  (`GF_MODULE_IMPORT_FAILED`, `GF_EXTENSION_NAMESPACE_COLLISION`,
  `GF_MODULE_CATALOG_STALE`, …); `/api/workspace`, `/api/modules` and
  `/api/extensions` carry `module_quarantine`; new `POST /api/modules/rescan`;
  lifecycle conflicts are 409 (were 400), probe timeout 504, a stale
  catalogue 503 on run start; a lifecycle change while runs are pending is
  409 `GF_MODULE_LIFECYCLE_RUNS_PENDING` until confirmed with
  `{"confirm_pending_runs": true}` (JSON) or
  `X-VALUE-Confirm-Pending-Runs: acknowledged` (ZIP upload); every error
  answer carries `error_code`.  Library: `workspace_registry(...,
  strict=False)` quarantines by default (`strict=True` for release gates);
  catalogue constants are lazy attributes.
- Scientific identity is unchanged: for VALUE 101 the module graph
  (`graph_sha256` e6ff10cd…0ee9) and the Study revision (`revision_sha256`
  8d348df4…626d) are identical before and after this change, and the
  registry content and order are unchanged for every data directory that
  loaded before.

### Local API security boundary (P0-1)

- The browser talks only to the UI origin. `scripts/value-ui-gateway.mjs`
  (mounted by `serve-value-ui.mjs` and, for development, by `vite.config.ts`)
  answers only `127.0.0.1:<port>`/`localhost:<port>` (421 otherwise), refuses
  cross-site `/api` requests and writes without the page Origin (403), needs
  a Content-Length on POST (411), sends a per-response CSP nonce,
  `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`,
  `Referrer-Policy: no-referrer`, COOP/CORP, and forwards `/api` with the
  API session.  A foreign Host on a page gets the "Open VALUE from its
  launcher" explanation.
- The API generates a session token per process and writes it only to
  `<VALUE_DATA_HOME>/runtime/api-session-<port>.json` (0700/0600, atomic;
  removed on exit only by its owner).  Every request passes
  `backend/api_security.evaluate`: Host 421, any Origin 403
  `GF_BROWSER_ORIGIN_REJECTED`, cross-site Sec-Fetch-Site 403, invalid
  Content-Length 400, chunked POST 411, missing/wrong session 403
  `GF_SESSION_REQUIRED`/`GF_SESSION_INVALID`, form-style or missing POST
  Content-Type 415 `GF_CONTENT_TYPE_REJECTED`.
- Launchers pass `--api-origin` after `--port` (process patterns unchanged),
  never the token, and wait until the gateway reaches the API.
- Frontend calls same-origin `/api`; `NEXT_PUBLIC_VALUE_API_ORIGIN` is gone;
  pages are rendered per request (`force-dynamic`).
- `scripts/verify_local_security_boundary.py` probes an installation.
- **API contract changes (breaking for direct clients):** no CORS at all;
  new request header `X-VALUE-Session` (scripts:
  `backend.api_session.authorized_headers`); new response header
  `X-VALUE-Error-Code`; new statuses 421, 403, 415, 411, 400 and, at the
  gateway, 502 `GF_GATEWAY_SESSION_UNAVAILABLE`/`GF_GATEWAY_SESSION_MISMATCH`/
  `GF_GATEWAY_UPSTREAM_UNAVAILABLE`; `GET /api/health` without a session
  returns only `ok, service, version, python,
  authoritative_runtime_compatible, session_required, status,
  degraded_reasons`; the comparison CSV is an attachment.  The backend source
  hash is part of the execution identity, so Runs left unfinished by an
  earlier version cannot be resumed after the upgrade.
- `SECURITY.md` names VALUE, points to the VALUE advisory form and states the
  single-user host assumption; `X-VALUE-Executable-Trust` is documented as
  informed consent, not a security control.

### Run lifecycle (P0-3)

- `status.json` has a single writer API (`backend/lifecycle/run_status.py`):
  per-run file lock, field-level merges, a consecutive `lifecycle_history`,
  late worker writes recorded in `late-worker-*.json` without touching
  sealed artifacts. Cancellation is the `cancel-request.json` file only.
- Workers start through `python -m backend.worker_entry`, take a lease
  (`worker.lock`) before heavy imports, run detached from the backend and
  are reaped, supervised and reconciled at start-up (`GF_WORKER_EXITED`,
  `GF_WORKER_LOST`, `GF_WORKER_IMPORT_FAILED`, `GF_WORKER_TERMINATED`,
  `GF_WORKER_SPAWN_FAILED`); `POST /api/runs/<id>/mark-lost`; one backend
  per data directory (`.backend.lock`, exit code 3).
- Delete moves the run to the trash before recording `deleting`; runs a
  previous version left in `deleting` are repaired at start-up.
- Disk quota counts physical bytes once per inode and reservations only
  for the unwritten output of active runs; one rule for reservation,
  preflight, snapshot readiness and resume; reservation lock is a flock
  (timeout 503); reservation report v2.
- Every API request has one exception boundary (`_dispatch`); listings
  isolate bad records instead of failing.
- Launchers start every interpreter with `-B -s -X pycache_prefix=<fresh
  directory>`; stray `__pycache__` bytecode is quarantined instead of
  blocking start/diagnose (`diagnose-value --repair-bytecode`).
- API additions: `worker_liveness`, `worker`, `cancel_requested_at`,
  `persisted_status`; `worker.json` v2.

### Default PSM clearing and storage dispatch (P0-6)

- `value-bid-at-cost-psm` 6.0.0 runs one of two market rule sets derived from
  the methodology catalogue (`corrections/p06.json`).  The doctoral
  reproduction profile keeps the 0.6.0-alpha.2 dispatch bit for bit and
  reports its known deviations in `market_rule_diagnostics`.  The default
  (corrected) profile clears with: D1-surplus (VRE surplus rebuilt per source
  and kept on the books; must-run surplus never generated twice), storage
  after generation in the same 0.01 GBP/MWh band, an avoided-cost
  down-regulation stack, one net storage position per period (shared rated
  power, buy-back before charging), per-period storage fees, no pre-clearing
  VRE electrolysis, cycle-only dynamic storage bids (pumped hydro and
  hydrogen bid 0) and uniform-price settlement.  Saved Studies on the
  corrected profile need method confirmation (Q13).
- Realisation is unchanged in both profiles (decision A2): a period whose
  ahead stage cannot meet the forecast keeps its shortfall, booked as a
  stress event.
- Operating cost of the default PSM (both profiles) is physical: generation
  at running cost, imports, start-up adder, unserved energy x VoLL (8000
  doctoral, `market.voll_gbp_per_mwh` corrected) and storage cycle wear,
  which was previously counted twice.  New extensions
  `physical_operating_cost_detail_gbp`, `market_settlement_components_gbp`,
  `market_rule_diagnostics`, `market_rule_set`.
- Corrected ledgers declare `native_corrected_full_node_v1`: `vre_accepted`
  is gross VRE output, `curtailed` is VRE availability minus that output,
  `excess` is the non-VRE spill (declared in the ledger semantic metadata).
- `dynamic-annual-storage-cost` 2.0.0 (bid basis owned by the PSM rule set);
  `user-formula-storage-cost` stays 1.0.0; storage recovery adequacy v2.
- Per-period source flows (RealisationLog) stay in memory only; persisting
  them is deferred to ledger v9 (P1).

### Scientific validation recomputed and gated (P0-4)

- No more literal "passed": stage parity v3 and scientific validation v2 are
  recomputed from checks executed on the run (contract checks, run
  invariants, the read-only energy-balance oracle).  A report that ran no
  check is `not_evaluated`.  Pre-fix runs keep their files; a `passed` that
  rests on a non-v2 report is shown as `superseded_pre_fix` and the ledger is
  re-checked read-only when the run is read.
- The default PSM declares its energy-balance boundary
  (`default_psm_surplus_node_v1` doctoral, `native_corrected_full_node_v1`
  corrected), records surplus routing per source and a per-asset storage
  audit, and its compatibility adjustment absorbs numerical noise only (it
  used to close every residual, so the adjusted residual was zero by
  construction).
- Decision A2: dispatch is unchanged when the ahead stage cannot meet the
  forecast; both profiles record stress events (per-period shortfall, events,
  annual summary) and book the shortfall as unserved energy in the
  energy-balance account.  Run status, summaries and market-replay windows
  carry `stress_periods`, `shortfall_mwh` and `shortfall_basis`; on a declared
  full-node boundary the shortfall now equals the booked unserved energy
  (it was a lower bound).
- Validation gates (P0-4 S7): run invariants, the energy-balance account and
  the storage throughput invariants (rated power, no charge and discharge in
  one period, 0 <= SoC <= E, audit identity).  Under the default profile a
  failed gate fails scientific validation and blocks annual economics
  (`publication_blocked.reason_code = GF_VALIDATION_GATE_FAILED`).  The
  doctoral reproduction profile reads gate failures through declared
  deviations with falsifiable signatures
  (`gridform_core/data/methodology/declared_deviations.json`: DEV-BAL-04,
  DEV-STO-01; DEV-BAL-01/02/03 as evidence only) and reports
  `reproduction_conformant` or `reproduction_with_declared_deviations`;
  its annual results follow decision Q14 (withheld unless every raw
  invariant passes).  New report fields: `storage_invariant_status`,
  `storage_invariants`, `validation_gate`, `declared_deviations`,
  `energy_balance.raw_boundary_status`.
- The Q14 verdict is derived from the gate statuses; a stored
  `raw_invariants.status` that disagrees is treated as failed, and the bundle
  validator recomputes it.
- Documentation errata: `docs/visibility-refactor/MARKET_LEDGER.md`,
  `RELEASE_0.4.md` (the 2,353 MWh statement), `ORCHESTRATOR_V2.md`,
  `TWO_YEAR_SMOKE.md`; methodology draft
  `docs/methodology/drafts/0.4/p04_energy_balance_validation.md`.

## 0.6.0-alpha.2 — VALUE Network Extensions identity (2026-08-20)

- Adopted the scientific name **VALUE**: Variable renewable electricity
  Allocation, Load-enabled excess-generation Utilisation, and system Evolution.
- Named this repository **VALUE Network Extensions** and kept the accepted
  single-node baseline distinct from optional network capabilities.
- Preserved `value.*`, `value.*`, `gridform_core`, `VALUE_DATA_HOME` and
  legacy launcher names as 0.x compatibility identifiers so existing Studies,
  checkpoints and external modules remain readable.
- Added VALUE-named launchers without changing the scientific execution path.

## 0.6.0-alpha.1 — Expanded-platform private test candidate (2026-08-19)

- Added versioned, fail-closed extension capability graphs and transactional
  extension bundles without changing the single execution registry.
- Added explicit run-of-river and reservoir hydrology contracts, with pumped
  hydro kept in the existing storage model.
- Added an open chronological DC network PSM independently checked on
  analytical, random, 24-hour and 168-hour cases.
- Added a local-only experimental AC feasibility checker; AC optimal power flow
  and global AC optimality remain not evaluated.
- Added an experimental, causal transmission-expansion lifecycle with explicit
  candidates, budgets, lineage, cost and carbon accounting.
- Preserved the Prompt 64 single-node beta and retained VALUE source hashes.

## 0.5.0-beta.1 — Prompt 58 local module bundles

- Added deterministic `value.module-bundle/v1` packaging and an offline,
  transactional local installer.
- Added the Modules-page install, trust acknowledgement, provenance and
  enable/disable workflow without changing the single execution registry.
- Prevented built-in shadowing, unsafe ZIP paths, native binaries, inventory
  mutation and disabling modules referenced by saved Studies.
- Added an uploadable storage-cost example, bilingual guidance and bounded
  installer/API/security tests.

## Unreleased — post-Prompt 46 corrections (2026-08-10)

- Added versioned commissioned-asset records with CAPEX, FOM, economic life,
  CRF, annualised cost and project lineage; incomplete economics now fail closed.
- Coupled cumulative commissioned assets into the following year's live VALUE
  clearing fleet and reconciled asset economics with the annual capital ledger.
- Declared the public CEM as `force-cem-v1`, VALUE-derived with explicit
  divergences and no exact retained numerical-reproduction claim.
- Closed direct, import and embodied annual carbon ledgers across JSON and
  SQLite outputs.
- Added a separately verified 25-role UK public-data candidate with per-object
  source terms, attribution and integrity evidence.
- Regenerated the one-year, causal two-year, dynamic ten-year and legacy-tariff
  ten-year runs and passed the bounded scientific beta release gates.

## 0.5.0-beta.1 — 2026-08-08

- Added native public-contract execution for the optional perfect-foresight PSM.
- Added canonical CEM cost, carbon, planning, terminal and fleet ledgers.
- Added immutable input snapshots, safe run bundles and lifecycle controls.
- Added independent CBC validation of the HiGHS perfect-foresight formulation.
- Added bounded run comparison and storage-policy experiment contracts.
- Licensed owner-controlled software under Apache-2.0, repository documentation
  under CC BY 4.0 and the deterministic synthetic data pack under CC0 1.0.
- Recorded Hanzhe Xing as copyright owner and project lead, with Stuart Scott and
  John Miles acknowledged as contributing supervisors and advisors.
- Added a metadata-only source register for all 25 local UK data roles and
  verified every installed object's size and SHA-256 without changing VALUE.
- Kept UK data redistribution and VALUE direct-runtime cutover as independent
  release gates.
