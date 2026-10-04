# Prompt 13 — Immutable run input snapshots and content-addressed data revisions

Continue from accepted Prompt 12. Read scientific Prompts 05, 09 and 10 and the
current enqueue/worker data-loading path before editing. Act as a reproducible
research and concurrency engineer.

## Objective

Eliminate the time-of-check/time-of-use gap between clicking Run and the worker
reading project, module and database files. Every run must execute only a frozen,
content-addressed input revision captured at enqueue time.

## Non-duplication boundary

- Reuse project fingerprints, provenance, preflight and checkpoint hash checks.
- This task freezes the actual bytes and resolved runtime composition; it does not
  redesign project forms or data adapters.
- Never modify an installed data pack or a historical run bundle in place.

## Implement

1. Define a versioned `RunInputSnapshot` containing the immutable project revision,
   resolved manifests/source hashes, resolved parameters, data-binding metadata,
   byte hashes and an input-tree fingerprint.
2. Create the snapshot atomically before the run is accepted into the queue. The
   worker receives only the snapshot ID/path and must not re-resolve a mutable
   current project or live binding.
3. For local files, create a read-only frozen view using a safe strategy supported
   on Windows. Verify every byte hash before execution. Do not depend on symlinks
   or copy semantics without documenting them.
4. For very large immutable datasets, allow a content-addressed shared object only
   when size, hash and immutability are verified. Mutation creates a new revision;
   it cannot alter an active snapshot.
5. Make resume require the same input-tree fingerprint and module source hashes.
   Surface a typed mismatch instead of starting from live data.
6. Record snapshot creation state so a crash cannot leave an apparently runnable
   partial snapshot. Garbage collection may remove only unreferenced incomplete
   snapshots under an explicit policy.

## Tests and acceptance

- Race test: mutate project settings immediately after enqueue; the run uses the
  enqueued revision.
- Race test: replace a bound file after enqueue; the run either uses the frozen
  bytes or fails hash validation before the first model period.
- Concurrent runs from two revisions remain isolated.
- Resume after source/data mutation refuses the mismatch; resume from unchanged
  snapshot is deterministic.
- Interrupted snapshot creation is not runnable and does not corrupt a previous
  revision.
- Snapshot/provenance APIs expose IDs and hashes, not absolute local paths.

## Stop condition

Do not call the system reproducible while any production stage can open a mutable
project-selected input outside the frozen snapshot. List every exception and keep
the release gate failed.

## Deliverable

Provide the snapshot schema, atomic lifecycle, storage-size implications, race-test
results and a source scan proving the worker reads the frozen view.

