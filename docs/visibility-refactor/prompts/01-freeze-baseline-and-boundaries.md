# Prompt 01 — Freeze baseline and preservation boundaries

Act as a senior Python scientific-software maintainer. Work only in the current
GridForm repository. Read `docs/visibility-refactor/ARCHITECTURE_PLAN.md` in full
before editing.

## Objective

Create enforceable preservation and regression boundaries before any refactor.
Do not change model behavior in this task.

## Mandatory constraints

- Preserve unrelated user changes in the dirty worktree.
- Never edit the retained reference Scheme C files listed in
  `docs/visibility-refactor/README.md`.
- Do not regenerate historical outputs or overwrite the authoritative fixture.
- Use Python 3.10 for Scheme C tests.
- Do not declare success because a process merely exits zero; distinguish source
  preservation, contract execution and numerical parity.

## Work

1. Inspect the existing preservation/parity tests and source metadata.
2. Add a machine-readable retained-source hash manifest covering the immutable
   Scheme C files. Prefer paths relative to the repository and SHA-256 values.
3. Add a test that fails with a useful per-file message if a retained file is
   missing or its hash changes.
4. Inventory every production use of:
   - `compat/modular_case3.py::main`;
   - numeric indexing into `run_simulation` results;
   - scientific environment variables;
   - global `compat.config` mutation;
   - broad exceptions followed by `pass` in market/planning execution.
5. Store the inventory as a versioned JSON or Markdown audit artifact under
   `docs/visibility-refactor/`. Include file and line anchors, but do not rewrite
   the audited code yet.
6. Add or confirm minimal fast fixtures for:
   - two-period execution;
   - one complete year;
   - retained 2025-2026 comparison.
7. Document exact commands, runtime and expected artifacts for each level.

## Tests

- Run the retained-source hash test.
- Run existing contract/orchestrator tests.
- Run the two-period test with Python 3.10.
- Do not launch a full annual run merely to create a fixture unless one is missing;
  report that as an explicit blocker rather than fabricating data.

## Deliverable

Report files changed, hashes protected, inventories found, tests run and any
existing baseline failure. Do not begin contract v2 work in this task.
