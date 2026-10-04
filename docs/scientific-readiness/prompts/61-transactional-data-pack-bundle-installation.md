# Prompt 61 — Transactional data-pack bundle installation

Execute after Prompt 59 and consume Prompt 60 rights decisions. Read Prompt 14
data import, Prompt 22 safe bundles, Prompt 45 UK asset, Prompt 58 module
installer, `FORCE_DATA_HOME` and current Data-page APIs. Act as a data-platform,
archive-security and frontend engineer.

## Objective

Let an ordinary user install the existing UK benchmark release or another
already-canonical data pack from one local ZIP without hand-copying files, while
preserving the 25-role adapter contract, per-object rights and atomic rollback.

## Non-duplication boundary

- Do not rebuild, transform or rename the accepted 25 UK scientific objects.
- Reuse `validate_data_pack`, immutable binding revisions, disk quota checks and
  Prompt 58's safe staging/inventory patterns; do not reuse the executable-module
  schema or registry for data.
- This is not a no-code arbitrary ETL engine. Prompt 14 adapters remain the place
  for foreign schemas.
- Do not auto-download 803 MiB or accept upstream terms without explicit user
  action. Initial acceptance is a local ZIP installer.

## Bundle contract

Define `force.data-bundle/v1` containing an exact file inventory, one
`gridform.data-pack/v1` manifest, the corresponding rights/attribution records
and data objects. It contains no Python, script, pickle, native binary or module
entry point.

## Implement

1. Add a deterministic streaming builder for the already accepted synthetic and
   UK pack directories. Preserve every scientific object byte and manifest
   binding hash.
2. Add bounded archive/file-count/compressed/uncompressed limits, zip-slip,
   duplicate, link, archive-bomb, disk-headroom and executable-content checks.
3. Stream into same-volume staging under `FORCE_DATA_HOME`; verify bundle
   inventory, per-object SHA-256, manifest, rights and deep semantic validation
   before atomic promotion. Failure leaves the prior installed pack unchanged.
4. Reject an installed ID/revision collision with different bytes. Support a new
   revision and keep completed Study/run identities readable.
5. Add **Data -> Install data pack** with size, expected disk, licence/attribution
   acknowledgement, progress, validation level and exact error. Never load the
   archive into browser memory.
6. Register the pack only after promotion and refresh Study selectors. Show which
   roles are ready and which adapter assumptions select/repeat source chronology.
7. Document offline installation and an optional future consent-based download
   flow. Do not embed private repository credentials or release tokens.

## Tests and acceptance

- Synthetic bundle installs from a clean state and runs the real two-year smoke.
- The complete UK release ZIP installs from a clean data root, matches its
  published asset SHA-256, passes 25/25 and completes a two-period wiring run.
- Bad inventory/hash, traversal, duplicate members, executable content,
  insufficient disk, manifest mismatch and rights-blocked objects fail atomically.
- Reinstall is idempotent; a different revision does not mutate old Studies or
  completed runs.
- API/UI tests cover progress, cancellation before promotion, rollback and
  accessibility.

## Stop condition

Do not weaken full object hashing because the UK ZIP is large. If runtime makes
that impractical, retain streaming verification and report measured time. Do not
silently acquire data from the network.

## Deliverable

Provide the data-bundle contract/builder, transactional installer, UI, tests,
offline user guide and measured UK installation evidence. No annual or ten-year
rerun is required.
