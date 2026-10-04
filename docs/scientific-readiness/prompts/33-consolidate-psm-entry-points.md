# Prompt 33 — Consolidate Scheme C PSM identities and retire ambiguous entry points

Continue only after Prompt 32 returns a GO. Audit the compatibility market kernel,
`gridform_core/builtin/scheme_c_1000twh/psm.py`, `factory.py`, v2 module
definitions, manifests, CLI commands, tests and documentation. Act as an API
migration and scientific-versioning owner.

## Objective

Ensure each public PSM module ID identifies exactly one executable implementation
and execution meaning. Keep one live native Scheme C PSM and one clearly separate
reference-comparison runner; deprecate or remove the older direct adapter and
replay identities from production discovery.

## Non-duplication boundary

- Prompt 32 already implements the live PSM. Do not rewrite its clearing logic.
- Do not delete the retained reference kernel or historical bundles.
- Reuse manifest migration, project revision and legacy-result adapter machinery.
- Do not rename historical run metadata in place. Interpret it through versioned
  migration/read adapters.

## Implement

1. Create an entry-point inventory containing implementation class/function,
   module ID, scientific version, callers, contract, whether it clears live or
   reads prior output, and production/reference/deprecated status.
2. Designate one manifest-backed live implementation as `scheme-c-psm`. Make
   imports from the public SDK, workspace registry, backend, CLI and tests resolve
   to that same source hash.
3. Give the retained whole-kernel tool a non-module reference identity such as
   `scheme-c-reference-comparison`. It must not satisfy a project PSM selection or
   an external-module conformance claim.
4. Remove `SchemeCReplayData` and its PSM wrapper from production packaging, or
   confine them to an explicitly private reference/migration namespace. Mark the
   older `psm.py`/`factory.py` route deprecated and route supported callers to the
   canonical application service; delete only after usage/source scans and
   migration tests prove it is safe.
5. Add typed deprecation errors/warnings containing replacement API and removal
   version. Never silently execute a different engine for an old module ID.
6. Update generated module tables, mathematical reference, README, model card and
   UI labels so “Scheme C PSM” consistently means live bid-at-cost execution.
   Reference comparison and perfect foresight remain visibly distinct.
7. Record implementation source hash and execution kind (`live_module` or
   `reference_comparison`) in every new run/bundle.

## Tests and acceptance

- A source/registry test proves no public module ID maps to multiple executable
  classes or both live and replay semantics.
- Website, CLI, SDK and backend worker selecting `scheme-c-psm` record the same
  manifest, source hash and live invocation marker.
- Historical projects/runs remain readable and are labelled with their actual old
  execution path; they are never rewritten.
- Importing a deprecated route gives an actionable migration message or verified
  forwarding that cannot bypass project/module resolution.
- Reference comparison remains runnable only through its explicit command and is
  excluded from module catalogue/conformance success.
- Full tests and retained-source hashes pass.

## Stop condition

If any normal production caller can still reach the older direct/replay path, or
if one ID denotes different algorithms depending on import route, leave the API
consolidation gate failed.

## Deliverable

Provide the entry-point inventory, canonical/deprecated mapping, migration policy,
source/route scans, updated catalogue evidence and proof of historical readability.
