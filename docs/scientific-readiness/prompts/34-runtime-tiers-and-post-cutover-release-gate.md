# Prompt 34 — Runtime tiers and post-cutover compatibility release gate

Continue only after Prompts 29-33 are accepted. Read scientific Prompts 17B, 25,
27 and 28 and their actual reports. Act as an independent release owner; add no
new scientific feature or market assumption.

## Objective

Separate the Python-3.10 Scheme C reference-reproduction environment from the
portable FORCE native runtime, verify only the Python versions actually supported
by evidence, and rerun the release gates that were previously blocked by replay,
private registries and path hygiene.

## Non-duplication boundary

- Prompt 25 already created locks, installer, doctor and CI. Extend its runtime
  matrix; do not create another launcher/backend stack.
- Prompt 28 remains the integrated release definition. This prompt reruns failed
  prerequisites and then hands control back to Prompt 28 rather than inventing a
  competing release standard.
- Keep reference reproduction on Python 3.10 unless a separate parity study
  explicitly supports another interpreter.
- Do not claim native cross-version support from import success alone; numerical,
  contract and bundle evidence is required.

## Implement

1. Define two explicit capabilities:
   - `force-native`: v2 orchestrator, live registered modules and synthetic/public
     data contracts;
   - `scheme-c-reference`: preserved whole-kernel comparison on verified Python
     3.10 only.
   The UI, doctor, package extras and run provenance must display the selected
   capability and interpreter.
2. Remove the repository-wide `<3.11` restriction only if the native dependency
   set and numerical tests pass on each newly claimed Python version. Keep a
   Python-3.10 lock for the reference extra/process.
3. Make the launcher select or create the required environment explicitly. A
   native run must not fail merely because the reference extra is unavailable;
   requesting reference comparison without Python 3.10 must fail with an
   actionable capability message.
4. Run Prompt 31 all-slot external module proof and Prompt 32 live Scheme C proof
   on every supported native platform/version. Run retained reference comparison
   only in its verified Windows/Python-3.10 matrix.
5. Rerun Prompt 17B against the live public Scheme C PSM. Report FORCE period
   clearing and perfect-foresight validation separately; no replay invocation can
   satisfy either gate.
6. Rerun source/wheel/sdist path scans, clean installation, synthetic browser E2E,
   snapshot/resume, cancellation and bundle validation. Correct stale rights and
   compatibility statements in validation documents and release reports.
7. If all short prerequisites pass, return to Prompt 28 for full one-year,
   two-year and ten-year scientific gates. Do not launch long runs merely to
   compensate for a failed native invocation, independent-validation or package
   gate.

## Tests and acceptance

- Supported native Python versions produce equal deterministic synthetic
  objectives, annual states and bundle hashes where byte equality is intended;
  documented numerical tolerances apply only where platform libraries require it.
- Python 3.10 reference output remains unchanged and retained hashes pass.
- Native installation works without the reference extra; reference selection
  clearly explains and enforces its Python-3.10 requirement.
- Fresh package scans have no real developer paths, false-positive path failures,
  prohibited data or ambiguous PSM entry points.
- Website-selected module IDs, versions and source hashes match actual live calls
  for every slot.
- Prompt 17B returns explicit current decisions for FORCE clearing and perfect
  foresight, with required mutation failures.
- Prompt 28 receives linked immutable evidence for all repaired gates and returns
  new public-code, UK-data and scientific-baseline decisions separately.

## Stop condition

Do not broaden `requires-python`, publish a binary beta or start ten-year runs when
any claimed interpreter, live-module, independent-validation, path or packaging
gate fails. Record the smallest safe next action.

## Deliverable

Provide the runtime capability matrix, lock/installer changes, cross-version
results, live invocation and independent-validation reports, clean artifact scans,
corrected documentation and the updated Prompt 28 release decisions.
