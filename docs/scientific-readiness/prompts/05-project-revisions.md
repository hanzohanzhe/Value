# Prompt 05 — Immutable research-project revisions

Act as a reproducible-research architect. A project must identify an immutable
experimental composition rather than a mutable form.

## Implement

1. Define a canonical project fingerprint over data-pack identity, years, module
   IDs/versions, scientific parameters, runtime controls and random seed.
2. Save append-only project revisions. Editing creates a child revision with
   parent hash and change summary; never silently overwrite an executed revision.
3. Snapshot the exact revision and resolved module versions at run start.
4. Display project revision/fingerprint in the UI and run provenance.
5. Keep migration support for existing v1 projects without changing historical runs.

## Tests and acceptance

- Canonical key order does not change the fingerprint.
- A scientific change changes the fingerprint; a display-name change does not.
- Concurrent stale edits are rejected.
- Old projects migrate deterministically and still run.
