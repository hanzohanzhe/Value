# Prompt 14 — Executable data adapters, atomic import and deep semantic validation

Continue from accepted Prompt 13. Read scientific Prompt 06 and inspect the data
upload, mapping and validation code before editing. Act as a power-system data
platform engineer.

Apply the preservation boundary in `docs/scientific-readiness/README.md`: never
edit retained Scheme C sources, fixtures, the installed data pack or historical
run bundles.

## Objective

Turn database bindings into executable adapters that normalize foreign schemas to
canonical PSM/CEM roles. Import must be staged and validated atomically; a failed
replacement must never destroy the last valid binding.

## Non-duplication boundary

- Reuse the existing 25 semantic interface definitions and preflight report.
- Extend validation beyond presence/metadata checks; do not create a parallel list
  of role names.
- Do not copy or modify the installed Scheme C data pack.

## Implement

1. Define a versioned adapter contract with declared source format, canonical
   output role/schema, column/key mapping, unit conversions, technology mapping,
   time convention/timezone, transformation version and source/license metadata.
2. Execute adapters during snapshot preparation and make PSM/CEM modules consume
   canonical outputs only. Record source and normalized hashes.
3. Preserve all existing binding metadata during edits. Stage uploaded files in a
   run-safe area, enforce size/disk limits, validate, then atomically promote a new
   binding revision. On failure, keep the previous valid revision unchanged.
4. Add a mapping preview/editor API and English UI for columns, units, technology
   labels, regions and timestamps. Show a bounded sample and validation impact;
   never load a complete annual table into the browser.
5. Deep-validate CSV/JSON and NetCDF/Zarr/optional Parquet sources as applicable:
   dimensions, coordinates, monotonic/unique time, timezone, expected interval,
   selected-year coverage, missing/NaN/inf values, physical ranges, units,
   duplicate IDs and cross-table references.
6. For very large arrays, validate metadata plus bounded chunks and deterministic
   statistics; allow an explicit full validation mode. State exactly which level
   ran instead of calling metadata-only validation complete.
7. Reject path traversal, archive bombs, unsupported executable content and
   ambiguous conversions before promotion.

## Tests and acceptance

- A foreign-schema synthetic pack with renamed columns and different declared
  units runs through the real two-period PSM/CEM path after normalization.
- Bad units, timezone gaps, duplicate IDs, broken cross references, NaNs and wrong
  NetCDF dimensions produce role-specific corrections.
- Failed imports preserve the prior binding byte-for-byte.
- Concurrent import and run prove the run uses its immutable snapshot.
- The installed Scheme C pack still passes without content changes.
- UI tests cover preview, mapping, warning, blocking error and rollback states.

## Stop condition

If a selected module reads a source-specific filename or column directly outside a
declared adapter/compatibility boundary, record it as an unresolved coupling and
fail the adapter-completeness gate.

## Deliverable

Provide the adapter schema, canonical-role table, import state machine, deep
validation levels, foreign-pack demonstration and unresolved-coupling inventory.
