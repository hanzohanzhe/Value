# Prompt 22 — Run cancellation, retention, quotas and safe recovery artifacts

Continue from accepted Prompt 21. Read scientific Prompts 09-10, current process
management, checkpoint serialization and run-directory code. Act as a local
scientific-computing operations and security engineer.

Apply the preservation boundary in `docs/scientific-readiness/README.md`: never
edit retained Scheme C sources, fixtures, the installed data pack or historical
run bundles.

## Objective

Give multi-hour runs a complete, recoverable lifecycle without corrupting evidence
or allowing untrusted run bundles/checkpoints to execute code.

## Non-duplication boundary

- Reuse atomic annual checkpoints, resume validation, estimates and artifact index.
- Add lifecycle and security controls; do not redesign the model equations.
- Never automatically delete completed scientific evidence without an explicit
  user retention policy.

## Implement

1. Define a run state machine covering queued, snapshotting, running,
   cancel-requested, cancelled, failed, completed, archived and deleting. Make
   transitions atomic and preserve stable error/reason codes.
2. Persist worker identity safely and implement cooperative cancellation at
   declared safe boundaries, with bounded escalation only for a stuck child.
   Completed annual checkpoints remain valid; partial period writes roll back.
3. Resume cancelled and failed runs only from a verified compatible checkpoint and
   distinguish resumed lineage from a new run.
4. Replace executable/untrusted checkpoint serialization with versioned safe
   formats such as JSON plus NPZ/SQLite as appropriate, or strictly quarantine
   legacy pickle as trusted-local and prohibit importing it from shared bundles.
5. Add full-bundle export with hashes and validation. Import must reject path
   traversal, archive bombs, oversized inputs, executable payloads and incompatible
   schema/source without running code.
6. Add disk quotas/headroom checks, per-run size estimates, upload limits and a
   retention dashboard. Archive/delete must identify exact targets, require
   confirmation and be recoverable where practical.
7. Profile the two long ten-year runs by stage and artifact writer. Optimize only
   measured hot paths while preserving deterministic ordering and numerical gates.
8. Expose the lifecycle through the real local API and frontend: cancel with the
   coarsest guaranteed safe boundary, archive, restore, delete, resume and export.
   Destructive actions show the exact run ID/path/estimated bytes and require
   confirmation. Deletion follows a declared trash/grace/permanent-delete policy;
   it never recursively targets an unresolved or workspace-root path.
9. Reserve disk headroom before snapshotting and again before each annual stage.
   Support configurable global and per-run quotas, predicted input/checkpoint/
   ledger/export sizes and a protected minimum-free-space floor. Refuse the run
   before disk exhaustion with required/available/reserved byte counts.
10. Define portable export profiles: compact results, complete audit bundle and
   checkpoint-capable bundle. Include versioned JSON/CSV/SQLite/NPZ artifacts,
   manifest hashes and relative paths; include source data only when its data-pack
   licence and user selection permit redistribution. Import validates fully in a
   staging directory before creating a run record.

## Tests and acceptance

- Cancel during PSM, ledger flush and between years; status and artifacts remain
  internally consistent.
- Resume a cancelled two-year run and match uninterrupted output.
- Corrupt, mismatched and malicious bundles/checkpoints are rejected without code
  execution or writes outside the staging directory.
- Quota tests block a run/import before disk exhaustion and preserve existing runs.
- Archive/restore validates hashes; deletion never follows an unresolved path.
- API/UI show progress, cancellation and recovery states without stale success.
- Compact/full/checkpoint exports round-trip on a second clean directory without
  absolute developer paths. A results-only export cannot be misrepresented as
  resumable.

## Stop condition

If safe cooperative cancellation is unavailable inside a long copied kernel call,
state the coarsest guaranteed cancellation boundary and do not advertise immediate
cancellation.

## Deliverable

Provide the state machine, safe serialization policy, cancellation boundaries,
retention/quota UX, security tests and measured performance profile.
