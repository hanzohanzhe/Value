# Prompt 54: External launcher-log bundle boundary

Execute after the first Prompt 52 ten-year bundle audit. Do not modify retained
Scheme C or any scientific result artifact.

## Observed defect

A direct Windows test launch redirected stdout and stderr into the model output
directory. FORCE indexed those files before the launcher closed its inherited
file handles. The final handle flush changed `background-resume2-stdout.log`
after provenance was sealed, so bundle validation correctly reported
`GF_BUNDLE_HASH_MISMATCH` even though every scientific, cost, carbon, planning,
lineage and investment check passed.

These files belong to the external process supervisor. The web application
already keeps service logs outside `model-output`, but the public provenance
collector did not make this boundary explicit for direct CLI automation.

## Required change

1. Classify `background-*.log`, `background_*.log`, `launcher-*.log` and
   `launcher_*.log` as external supervisor logs.
2. Exclude them from the immutable scientific artifact index, as `model.log`,
   `status.json` and SQLite transient files already are.
3. Add a unit test that proves scientific JSON remains indexed while launcher
   logs do not.
4. Provide a fail-closed reseal command for already completed Prompt 52 runs.
   It may rewrite only `artifact-index.json` and the provenance artifact list.
   It must hash every scientific artifact before and after, refuse any
   non-launcher validation error, and write a separate repair audit.
5. Re-run bundle and Prompt 52 audits. Do not relabel a scientific failure as a
   packaging repair.

## Acceptance

- launcher logs can continue changing after model exit without invalidating a
  scientific bundle;
- all indexed scientific artifact hashes are unchanged by resealing;
- completed dynamic and legacy bundles validate with ten state transitions;
- retained Scheme C hashes remain unchanged.

