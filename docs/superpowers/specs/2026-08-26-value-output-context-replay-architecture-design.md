# VALUE Output, Context and Replay Architecture Design

**Status:** User-approved architecture and written specification

**Date:** 26 August 2026

**Scope:** VALUE staged PSM output, immutable module context delivery, market
evidence, preflight resource protection and bounded result access

## Purpose

The fixed-zonal ten-year run exposed an implementation fault rather than a
zonal-optimisation fault. Every half-hour `BalancingInput` embedded the complete
annual `ZonalNetworkPack`. The repeated payload was approximately 7.6 MB, most
of it the complete annual zonal-demand series. The staged-market writer then
appended the complete input and result to `market/staged-market.jsonl`
regardless of the selected trace level. A stopped run reached about 3.03 GiB
after roughly 400 periods, implying more than 1 TiB for ten model years.

The same path also reconstructed and validated the full network pack inside
each half-hour zonal solve, performed a linear search for the period index and
read the growing JSONL file back into memory to calculate a terminal hash.
These behaviours add no scientific information. They duplicate immutable
inputs, waste time and can exhaust the output disk.

This design makes static and annual inputs explicit, stores each immutable
context once, passes only the current-period slice into clearing, and makes
SQLite the sole authoritative period store. It preserves the existing
half-hour market sequence, zonal redispatch linear programme, settlement rules,
storage update order, CEM state transition and annual checkpoint semantics.

## Scope boundary

This work changes:

- how the staged PSM and balancing module receive immutable inputs;
- how `summary`, `full market replay` and failure evidence are stored;
- how preflight estimates output volume and protects free space;
- how the frontend queries and exports long-running evidence;
- how old ledger and staged-market results remain readable.

This work does not change:

- bid-at-cost offer construction or ordering;
- the four-phase zonal redispatch optimisation;
- demand authority, zonal allocation or network ratings;
- dispatch, settlement, storage SOC or VRE-curtailment equations;
- CEM investment, planning, admission, retirement or expansion rules;
- the retained doctoral Scheme C reproduction;
- the meaning or execution order of the matched copperplate and zonal studies;
- Prompt 105's scientific comparison contract.
- the simple copperplate bid-at-cost, perfect-foresight LP or reference DC-OPF
  execution paths. Ledger v8 is introduced only for the staged bid-at-cost plus
  balancing/redispatch path that produced the repeated zonal payload. A future
  cross-PSM ledger unification is a separate architecture task.

No new contract, table, artifact or user-facing field may use the name FORCE.
The retained Scheme C source and its protected hashes remain untouched.

## Required invariants

The implementation must satisfy all of the following:

1. A complete data pack or network pack is never embedded in a period record.
2. No period record contains an annual time series.
3. A selected network pack is loaded and validated once per run.
4. A year's physical asset state is created and frozen once per model year.
5. Modules cannot mutate a run or year context.
6. Trace level cannot affect dispatch, SOC, CEM decisions, costs or carbon.
7. SQLite is the only authoritative period store for new staged runs.
8. New staged runs do not create `market/staged-market.jsonl`.
9. A failed solve retains the first failing period's declared input even when
   the Study uses summary or off tracing.
10. A zonal run never falls back silently to another network pack or to
    copperplate.
11. Old completed runs are read only and are never migrated in place.
12. A run cannot start when the accepted preflight estimate would violate the
    output quota or free-space reserve.

## Context architecture

### Run static context

`value.run-static-context/v1` is created after Study resolution and preflight.
It is immutable and contains or references:

- run, Study revision and scenario identities;
- model years and clock;
- base data-pack ID, manifest SHA-256 and binding identities;
- the resolved module graph, exact versions and source hashes;
- scientific parameters and frozen runtime controls;
- trace profile and solver contract;
- demand authority and zonal-demand mode;
- network-pack ID, manifest SHA-256 and scientific SHA-256 when applicable;
- the canonical static network topology, zones, cutsets, directed ratings,
  interconnector landings and annual zonal-demand authority;
- the context schema version and canonical content SHA-256.

The canonical run context is stored once at:

```text
market/context/run-context.json
```

Large source datasets are not copied into every run context. Their immutable
data-pack bindings remain in the frozen input snapshot and are referenced by
content identity. The selected network-pack scientific object is materialised
once because the zonal solver must be reproducible without consulting an
arbitrary later pack selection.

### Year context

`value.year-context/v1` is created before each PSM year. It contains:

- the model year and parent run-context SHA-256;
- the commissioned fleet and storage assets used by that year's PSM;
- investment-owner and base-asset identities;
- frozen asset-to-zone shares and interconnector landings;
- power and energy capacities, efficiencies and opening SOC;
- new commissions, retirements and planning admissions inherited from the
  preceding CEM transition;
- annual capacity-headroom state required by the selected expansion modules;
- the context schema version and canonical content SHA-256.

The canonical year context is stored once at:

```text
market/context/year-<YYYY>.json
```

The 2025 PSM uses the frozen 2025 opening context. When the 2025 PSM and CEM
chain completes, the transition result constructs a new 2026 context. The
2025 object is not modified. This pattern repeats at every annual boundary.

### Period input

The outer clearing contract remains `value.balancing-input/v1`. Zonal runs use
`value.zonal-redispatch-domain/v2` in `BalancingInput.domain_payload`:

```json
{
  "schema_version": "value.zonal-redispatch-domain/v2",
  "run_context_ref": {
    "schema_version": "value.run-static-context/v1",
    "sha256": "<64 lowercase hexadecimal characters>"
  },
  "year_context_ref": {
    "schema_version": "value.year-context/v1",
    "year": 2025,
    "sha256": "<64 lowercase hexadecimal characters>"
  },
  "period_slice": {
    "period_id": "<declared period identity>",
    "ahead_result": {},
    "zonal_real_demand_mwh": {},
    "zonal_forecast_demand_mwh": {},
    "forward_boundary_capacity_mwh": {},
    "reverse_boundary_capacity_mwh": {}
  }
}
```

The existing outer fields continue to carry current realised availability,
opening SOC, current bids, VOLL and period duration. The current-period frozen
ahead result remains in the period slice because it is an input to redispatch,
not annual static data. The module resolves static topology and annual asset
metadata from the already-bound read-only context; it does not deserialize the
context reference on every call.

### Runtime lifecycle

Context-aware modules implement this lifecycle:

```python
configure(run_context, resolver)
start_year(year_context)
clear(period_input)
```

`configure` is called once per run, `start_year` once per model year and
`clear` once per half-hour. The resolver returns read-only, content-addressed
objects already validated by the application layer. It never downloads data,
searches the filesystem or chooses a compatible pack at runtime.

Modules return versioned result objects. The application layer alone applies
SOC changes, commissioning, retirement and other state transitions. A module
must not receive a writable global configuration or a writable shared context.

### Module capability declaration

A context-aware balancing module declares these capabilities in its v2 module
manifest:

```text
value.module-context-lifecycle/v1
value.balancing-input/v1
value.zonal-redispatch-domain/v2
value.market-ledger/v8
```

Installation and Study preflight verify the declarations, required data roles
and versions. Incompatible modules fail before execution with the missing
contract and corrective action. An explicit v1 compatibility adapter may wrap
an older module. The core does not contain module-ID-specific compatibility
branches.

## Trace profiles

The canonical stored values remain `off`, `summary` and `full` for backward
compatibility. The UI labels `full` as **Full market replay**.

### Summary

`summary` is the default. Every period records the common scientific
projection needed to inspect and compare a run:

- forecast and realised demand;
- accepted physical dispatch aggregated by zone and canonical technology;
- storage charge, discharge and closing SOC aggregated by zone and technology;
- imports, exports and flexible demand;
- blackout/load shedding;
- VRE availability, dispatch and curtailment attribution;
- zonal injections and boundary flows;
- aggregated redispatch volume and cost;
- clearing and solver status;
- energy-balance and accounting residuals;
- source-input, result and integrity-chain hashes.

Summary does not store individual offers, bid-level acceptance, agent-level
settlement or asset-level solver inputs.

### Full market replay

`full` writes the complete summary projection and additionally stores:

- all ahead and balancing offers;
- pre-clearing declarations;
- accepted and rejected quantities with reason codes;
- asset- and agent-level dispatch and settlement;
- full clearing inputs and outcomes;
- detailed storage state and VRE-curtailment rows;
- complete solver phase evidence.

The additional detail is stored in normalised SQLite tables. It is not written
as an additional JSONL stream.

### Off

`off` is an advanced profile. It disables optional period browsing but does
not disable in-memory physical validators, annual cost and carbon ledgers,
run-state checkpoints, result manifests or failure evidence.

### Frozen selection

The Study revision stores the requested trace profile. Check readiness records
the resolved profile in the frozen input snapshot. A running Study cannot
change trace profile. The result page displays the actual profile used.

## SQLite ledger v8

New staged runs write `value.market-ledger/v8`. Readers retain read-only support for
existing v4 through v7 databases. No existing database is rewritten.

The v8 common projection adds normalised summary tables rather than placing
synthetic aggregate asset IDs into legacy detail tables:

- `dispatch_summary`, keyed by year, period, stage, zone and technology;
- `storage_summary`, keyed by year, period, zone and technology;
- `redispatch_summary`, keyed by year, period, zone, technology and direction;
- `context_registry`, containing run/year context identity and artifact path;
- `period_integrity`, containing common-science and stored-evidence chains;
- `year_integrity`, containing annual roots, counts and completion state.

Existing bounded tables such as period, zone, boundary, reliability,
curtailment and solver summaries remain part of the common projection. For v8
runs, legacy asset-, order- and payload-detail tables are populated only by
`full` tracing. Readers prefer v8 summary tables and fall back to legacy tables
for v4 through v7 runs.

SQLite writes one complete transaction per period. Batched statements may be
used inside that transaction, but a period is never partially committed.

## Integrity chains

Two independent rolling chains prevent trace detail from changing scientific
identity:

```text
science_chain[0] = SHA256(run_context_sha256 || year_context_sha256)
science_chain[p] = SHA256(science_chain[p-1] || canonical_common_projection[p])

evidence_chain[0] = SHA256(science_chain[0] || resolved_trace_profile)
evidence_chain[p] = SHA256(evidence_chain[p-1] || canonical_stored_rows[p])
```

The common projection is identical in summary and full modes. Therefore the
annual science root must match between paired summary and full runs, while the
evidence root may differ because full mode contains more rows.

Hashes are updated as rows are committed. No finaliser reads the complete
database or a growing trace file into memory. The annual and final artifact
manifests record context hashes, science roots, evidence roots, row counts and
trace coverage.

## Replay and export

The local database is authoritative. JSON, CSV and replay ZIP files are
generated on demand for one period, 24 hours, 168 hours, one year or the whole
run. Export generation is a separate background job and never blocks or alters
the scientific run.

A self-contained replay export contains, subject to the installed data pack's
redistribution policy:

- run and selected year contexts;
- requested period inputs and outcomes;
- module and solver identities and settings;
- Study revision and frozen input manifest;
- integrity roots and file checksums;
- a machine-readable statement of included and externally referenced data.

If source rights prohibit redistribution, the export contains immutable data
identities and local references instead of copying restricted content. It is
labelled `reference_only_not_portable`; VALUE must not imply that another
machine can replay it without installing the identified pack.

New staged runs never create `market/staged-market.jsonl`. A legacy JSONL reader
remains available for old completed runs. A user may explicitly request a
bounded JSONL export from a v8 SQLite ledger.

## Failure evidence

The first solver or invariant failure stops the run and creates one failure
bundle containing:

- the run and year contexts;
- the exact failing period input, including bids;
- every completed solver phase and diagnostic;
- solver method, tolerances, version and binary identity;
- raw solver status and message;
- physical, SOC, capacity, settlement and ledger residuals;
- input, output and context hashes;
- run, Study, data-pack, network-pack and module identities.

This bundle is produced for all trace profiles. It is written to a temporary
path and atomically renamed only after its manifest and contents reconcile. A
failure never triggers an alternative solver or copperplate fallback.

## Preflight resource protection

Check readiness uses the exact selected Study graph. It calculates fixed
context size and expected table cardinality from actual assets, storage units,
zones, boundaries, technologies, years, periods and trace profile. No estimate
assumes a hard-coded 14-zone or 50-order system when the selected input exposes
the real values.

When no compatible local calibration is cached, preflight executes a
non-persistent 48-period calibration against a cloned opening state. The
calibration uses the selected modules and solver but does not advance the
official Study, consume its random stream, create a result, update CEM state or
alter the frozen run identity. Calibration evidence is cached by the data,
module, solver, trace and model-clock fingerprint.

The estimate combines:

- the exact once-only context sizes;
- measured bytes and seconds per period;
- declared upper bounds from annual expansion headroom;
- annual checkpoint and result artifacts;
- export-independent temporary database space;
- a 1.5 multiplier on persisted output;
- an additional reserve equal to the larger of 10 GiB or 5% of the target
  volume's capacity.

Runtime is presented as an estimate, not a gate. Disk protection is a hard
gate. A run starts only when both the configured run quota and current free
space cover estimated persisted output, temporary space and reserve. The UI
offers three corrective actions: choose summary, move the output root or free
space. It never silently changes the trace profile.

## Cancellation and recovery

Cancellation waits for the current period transaction to finish and then marks
the current year incomplete. The last completed annual checkpoint remains the
only resumable state. Diagnostic evidence from the incomplete year is retained,
but a resumed run deletes that incomplete year's rows in one scoped transaction
and recomputes the year from its frozen opening context. Subannual resume is not
introduced by this work.

Completed scientific runs are never automatically pruned. Users explicitly
archive, export or move them to trash. Archiving may compress full replay
detail, but cannot change the database's scientific or evidence roots.

## Frontend behaviour

### Studies and readiness

The Study composer exposes Summary, Full market replay and the advanced Off
profile with concise storage implications. Check readiness displays:

- the resolved trace profile;
- exact base and network pack IDs and hashes;
- module and solver identities;
- estimated persisted and temporary bytes;
- current free space and configured quota;
- estimated runtime and its calibration basis;
- a pass/fail resource decision and corrective action.

### Results and replay

Long-run APIs query SQLite by year, bounded period range, resolution, limit and
offset. The frontend never loads a complete annual or ten-year payload. Charts
request only the required aggregation window.

Summary runs show dispatch, SOC, curtailment, zonal flows and redispatch without
pretending to contain individual bids. The bid panel states that full replay
was not recorded and offers to create a new Study revision with Full market
replay selected. It does not mutate or rerun the completed Study automatically.

Exports show progress independently of model execution. The user selects the
time range and output format before generation.

## Compatibility and migration

- Existing Study revisions remain immutable.
- Existing `summary`, `full` and `off` values resolve to the new trace profiles
  without rewriting the Study.
- Existing v4-v7 ledgers and staged-market JSONL streams remain readable.
- New staged runs always write v8 and never write staged-market JSONL.
- Built-in VALUE staged and zonal modules adopt the context lifecycle directly.
- Third-party v1 modules require an explicit installed compatibility adapter.
- An adapter's identity and source hash enter the Study and run fingerprints.
- Missing contexts, mismatched hashes or unsupported contracts fail closed.

## Relationship to the existing Prompt line

Prompts 93-108 established the staged market, zonal network, redispatch,
curtailment and solver science. Prompts 109-117 established VALUE 101 and the
Windows product. This design does not reopen their accepted scientific
decisions or duplicate their interfaces.

Prompt 105 remains the matched ten-year scientific comparison. It is not
restarted until this architecture passes its bounded storage, context and
trace-equivalence gates. The implementation plan created after this
specification is approved will use new post-117 Prompt numbers and will record
which earlier requirements it supersedes only at the implementation level.

## Verification sequence

Implementation is accepted in this order:

1. Contract tests prove that run/year contexts are immutable, canonical and
   content-addressed, and that period payloads contain no annual arrays or
   embedded network pack.
2. Ledger tests prove v8 write behaviour, v4-v7 read-only compatibility,
   transaction boundaries and absence of new staged-market JSONL files.
3. A 48-period zonal run proves one-time network-pack validation, bounded output
   and complete summary evidence.
4. A 336-period zonal run proves that output growth, after subtracting fixed
   context size, remains linear in periods and does not duplicate static input.
5. A two-year PSM-CEM run proves that the 2025 closing transition creates the
   immutable 2026 year context and that commissioned assets enter the 2026 PSM.
6. Matched summary and full runs prove equal annual science roots and equal
   dispatch, SOC, investment, cost, carbon and curtailment results.
7. A deliberately infeasible period proves that every trace profile emits the
   complete first-failure bundle and never falls back.
8. Readiness proves that actual bounded-run disk use remains below its accepted
   estimate and that an insufficient-space fixture fails closed.
9. Frontend checks prove bounded pagination, truthful trace coverage and
   on-demand export behaviour.
10. Only after all earlier gates pass may the stopped matched ten-year studies
    be recreated from fresh output roots.

The 48- and 336-period gates are engineering and contract checks, not annual
economic evidence. The two-year gate proves state coupling but does not replace
a complete annual scientific validation.

## Acceptance criteria

The design is implemented only when:

- a new zonal period input is independent of total annual chronology length;
- the selected network pack is loaded and validated once per run;
- a year context is immutable and uniquely hashed;
- `market/staged-market.jsonl` is absent from new staged runs and manifests;
- summary output contains the agreed scientific projection but no bid detail;
- full output adds replay detail without changing the common science root;
- SQLite writes and rolling hashes complete per period without whole-file
  readback;
- failure evidence is complete under off, summary and full tracing;
- old ledgers and old JSONL results remain readable without mutation;
- Check readiness blocks a run that would violate disk quota or reserve;
- frontend result access is bounded and export is on demand;
- cancellation preserves the last complete year and recomputes an incomplete
  year from its frozen opening state;
- no retained Scheme C file or protected hash changes;
- no new FORCE-named contract, field, artifact or user-facing label is added.
