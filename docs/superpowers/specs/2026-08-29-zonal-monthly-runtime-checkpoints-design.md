# Zonal monthly runtime checkpoints

**Status:** approved design

**Date:** 29 August 2026

**Scope:** future VALUE zonal PSM runs only; no change to the running 2025–2034 v2 studies

## 1. Purpose

Full zonal VALUE studies solve and record every half-hour separately. Recomputing an entire interrupted model year is therefore unnecessarily expensive. VALUE shall add a solver-neutral PSM runtime-checkpoint contract that lets a compatible zonal PSM resume from the end of the latest verified calendar month.

This feature changes recovery mechanics only. It must not change market clearing, zonal constraints, redispatch, storage physics, annual CEM decisions, investment, planning, admission, transition, cost definitions, carbon definitions or final scientific results.

## 2. Settled decisions

1. Checkpoints occur after the final committed half-hour of each real calendar month.
2. Monthly checkpoints are enabled by default for the maintained zonal PSM. Copperplate runs retain annual recovery by default.
3. CEM, investment and the planning pipeline remain annual. A monthly checkpoint is a PSM runtime boundary, not a monthly capacity-expansion step.
4. The current v2 copperplate and zonal runs continue without hot modification. The new contract applies only to subsequently launched runs.
5. VALUE keeps the latest two verified monthly checkpoints for the active model year. A completed annual checkpoint supersedes and removes that year's monthly checkpoints.
6. Resumption is explicit: a user selects **Resume from checkpoint** in the frontend or supplies the CLI resume option. VALUE never silently resumes an old run.
7. Unconfirmed SQLite rows after the selected checkpoint are retained in an immutable diagnostic snapshot and then atomically removed from the live ledger before resumption.
8. An identity mismatch, discontinuity or failed invariant closes the gate. VALUE must not fall back to copperplate or silently choose a different checkpoint.

## 3. Chosen architecture

VALUE shall complete the already reserved optional contract
`value.subannual-checkpoint/v1`. Prompt 63 created this contract as an
explicitly unsupported future extension and no runtime checkpoint has ever
been emitted under it. This work turns that single reserved contract into the
implemented monthly capability; it must not create a second overlapping PSM
checkpoint contract. The JSON Schema `$id` must also be changed from the stale
`force-model.org` identifier to
`urn:value:contract:subannual-checkpoint:v1`.

### 3.1 PSM module responsibility

A compatible PSM exposes solver-neutral export and restore operations. Conceptually:

```python
export_runtime_checkpoint(boundary) -> PSMRuntimeCheckpoint
restore_runtime_checkpoint(checkpoint) -> None
```

The exact Python protocol may use equivalent names, but it must remain optional. A PSM without this capability continues to use the existing annual recovery path.

The PSM owns the meaning and serialization of its dynamic physical and accounting state. It must not serialize PuLP, CBC or other solver objects.

### 3.2 VALUE runtime responsibility

The application runtime owns:

- calendar-month boundary detection from the frozen chronology;
- checkpoint schema validation and identity binding;
- atomic publication, hashing and retention;
- recovery discovery and the user-facing recovery candidate;
- exclusive, one-use recovery authorization;
- diagnostic preservation and atomic SQLite tail cleanup;
- final orchestration of restore and continuation.

### 3.3 Annual orchestration boundary

The annual sequence remains:

```text
opening YearState
  -> planning advance
  -> PSM periods
       -> verified calendar-month runtime checkpoints
  -> complete MarketYearResult
  -> expansion caps
  -> investment
  -> planning/admission/transition
  -> next YearState
```

No downstream CEM stage is invoked at a monthly boundary.

## 4. Runtime-checkpoint data contract

Each checkpoint is a versioned JSON artifact with a canonical SHA-256. It contains at least:

### 4.1 Boundary identity

- schema and capability version;
- run ID and model year;
- calendar month and boundary timestamp;
- last committed period index and period ID;
- next period index and period ID;
- period duration and frozen chronology identity.

### 4.2 Frozen model identity

- Study revision and resolved-run identity;
- RunContext and YearContext SHA-256 values;
- base Data Pack ID and manifest SHA-256;
- Network Pack ID and manifest SHA-256;
- resolved module graph and module versions;
- zonal solver contract ID and version;
- declared scientific parameters and relevant runtime-control identity.

### 4.3 Dynamic physical state

- storage SOC by asset or aggregate agent;
- charge and discharge availability;
- stored-energy cohorts required to preserve dwell-time accounting;
- any PSM-carried physical state needed by the next period;
- deterministic random-generator state when the selected module uses randomness.

### 4.4 Year-to-date accumulators

- generation, imports, storage charge and discharge;
- unserved demand and VOLL;
- VRE curtailment and its declared attribution components;
- physical operating cost, settlement and policy-accounting accumulators required by the annual result;
- operational and overall carbon accumulators required by the annual ledgers;
- zonal flows, congestion, redispatch, DSR, regional curtailment and redispatch impact;
- agent cash flow, sold energy and other year-end investment inputs consumed by the selected CEM modules.

### 4.5 Ledger boundary

- SQLite database identity;
- committed period count and maximum committed period;
- integrity hashes or equivalent canonical summaries for the committed prefix;
- checkpoint payload SHA-256 and publication state.

The checkpoint must contain enough state to produce the same complete `MarketYearResult` as an uninterrupted execution. Timestamps and operational audit metadata may differ; scientific and settlement values may not.

## 5. Publication protocol and invariants

A checkpoint may be marked `verified` only after all of the following hold:

1. The month's last half-hour has completed and its SQLite transaction has committed.
2. Every required period table has the same continuous committed prefix.
3. Checkpoint accumulators reconcile with SQLite aggregates at that prefix.
4. Storage energy conservation and zonal energy balance pass existing numerical tolerances.
5. No transaction or solver operation remains open.
6. The JSON payload has been written to a temporary file, flushed, atomically renamed and re-read successfully.
7. Its canonical SHA-256 and all frozen-input identities verify.

Publication order is data commit, runtime-state capture, invariant validation, temporary-file write, `fsync`, atomic rename, then manifest update. A failed publication leaves the preceding verified checkpoint usable and records a runtime warning; it does not alter scientific calculations already completed.

## 6. Recovery protocol

1. Scan verified monthly checkpoints newest first.
2. Validate the latest candidate against the exact Run, Study revision, contexts, packs, modules, parameters, chronology and solver contract.
3. Present the candidate in the UI as, for example, `Recoverable from 31 March 2028; next period 1 April 00:00`.
4. Require explicit user authorization through the frontend or CLI.
5. Atomically claim that authorization so no second process can consume it.
6. Inspect the live SQLite ledger. If rows exist beyond the checkpoint boundary, create an immutable diagnostic database with its own SHA-256.
7. After the product writer has exited, acquire the same ledger ownership domain in recovery mode. Dry-run and exactly verify the cleanup on a working copy, then apply the identical tail deletion and `year_integrity` rewrite to the live ledger in one SQLite transaction with `synchronous=FULL`; verify the exact prefix inside that transaction and commit. Do not replace the live database file or manually delete/replace its WAL or SHM files.
8. Restore the PSM state and resume at `next_period_index`.
9. At the next monthly or annual boundary, perform the full publication checks again.

Every product `SQLiteMarketLedger` writer must hold the writer role from before its first SQLite open until its connection is closed; recovery fails closed unless the mutually exclusive recovery role is held. The cleanup must cover every period-indexed table and dependent row. It must neither leave orphan rows nor double-count settlements. SQLite transaction/WAL recovery is the crash-consistency primitive. The checkpoint and diagnostic snapshot remain byte-for-byte unchanged if recovery fails; a rolled-back live transaction preserves logical ledger contents, although SQLite may update WAL/SHM coordination bytes. Diagnostic-directory fsync is enforced on platforms that expose directory fsync; Windows directory-entry durability remains best-effort because Python 3.10 exposes no enforceable directory-fsync operation.

If the latest checkpoint is corrupt, VALUE may offer the previous verified monthly checkpoint, but it must name the failure and require a second explicit choice. It must never downgrade automatically.

## 7. Retention and artifacts

Use a dedicated directory below the Run output, separate from annual `checkpoints-v2`, with stable names that contain the year and month. Maintain a small manifest that identifies the two retained verified checkpoints and their hashes.

After a third monthly checkpoint becomes verified, remove the oldest monthly checkpoint only after the new manifest is atomically published. After the annual result and next-year `YearState` checkpoint are verified, remove all monthly checkpoints for the completed year.

Interrupted ledger snapshots belong to recovery diagnostics. They are not ordinary scientific outputs and are excluded from the normal result bundle unless the user prepares an audit or failure bundle.

## 8. Frontend and CLI behaviour

The Runs page shall distinguish:

- **Resume from checkpoint**: continue the same immutable Run from the named verified boundary;
- **Run again**: create a new Run and start from its declared opening state;
- **No compatible checkpoint**: explain the first mismatch and the corrective action.

The ordinary results view shows only the recoverable boundary and recovery status. Detailed identities, hashes and tail-cleanup evidence remain available through Inspect or an audit bundle.

The CLI provides an explicit resume option and returns a non-zero exit code for missing, already-claimed, corrupt or incompatible checkpoints. It must not infer resume intent merely because an output directory already exists.

## 9. Compatibility and migration

- Existing annual checkpoints remain readable under their current contracts.
- Existing and currently running v2 studies are not converted in place.
- `value.subannual-checkpoint/v1` remains optional for third-party PSM modules.
- The pre-existing unsupported placeholder becomes the first implemented
  version; no second checkpoint schema or compatibility alias is introduced.
- The maintained zonal module is the first implementation.
- Modules lacking the capability remain fully usable, with the existing annual recovery message shown truthfully.
- A future module may implement the same capability without depending on the maintained zonal solver internals.

## 10. Failure handling

VALUE fails closed when:

- any frozen identity differs;
- committed periods are discontinuous;
- the checkpoint boundary and SQLite boundary disagree;
- storage or zonal balance fails;
- the authorization is missing, invalid or already claimed;
- the selected PSM cannot restore the checkpoint schema;
- atomic diagnostic retention or ledger cleanup cannot complete.

There is no automatic solver change, model-parameter change, copperplate fallback or checkpoint repair. Failure evidence is preserved before any repair is considered.

## 11. Acceptance verification

Implementation is accepted only when these bounded checks pass:

1. **Deterministic cross-month parity:** a three-month zonal fixture run continuously and with an end-of-January stop/resume produces identical period dispatch, storage state, flow, redispatch, cost, carbon, curtailment and annual accumulators, excluding operational timestamps and recovery metadata.
2. **Mid-month interruption:** rows after a January checkpoint are preserved diagnostically, removed from the live ledger and recomputed without missing or duplicate periods or settlement.
3. **Identity and corruption gates:** altered Data Pack, Network Pack, module, parameter, solver contract or checkpoint content is rejected.
4. **Exclusive authorization:** a second consumer cannot claim the same recovery authorization.
5. **Atomicity and retention:** an interrupted checkpoint write leaves the previous checkpoint valid; three completed months retain two verified files; a verified annual checkpoint removes that year's monthly files.
6. **Real-structure bounded run:** the maintained zonal PSM and an installed structurally representative network pack run across two calendar months on both uninterrupted and resumed paths with equivalent scientific results.

Floating-point differences are not accepted by default. If a solver produces a non-bitwise-equivalent but scientifically equivalent solution, the comparison must use the already declared numerical contract and document the exact degeneracy or tolerance source. Tests must not loosen ledger tolerances merely to pass recovery.

No annual, two-year or ten-year production run is required to accept the recovery mechanism itself. A later production run may use it after these gates pass.

## 12. Out of scope

- modifying the current v2 long runs;
- changing zonal optimization or redispatch methodology;
- changing output trace profiles or ledger definitions;
- monthly CEM, investment or planning decisions;
- serializing solver-native objects;
- adding monthly checkpoints to copperplate by default;
- automatic cloud upload or distributed execution.
