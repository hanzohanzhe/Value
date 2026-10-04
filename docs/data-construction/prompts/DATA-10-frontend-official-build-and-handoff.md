# DATA-10 — Frontend, official build and Prompt 98 handoff

Execute after DATA-09 passes. Act as a frontend engineer, data-release lead and
integration tester. This prompt completes the local workflow; it does not claim
that the zonal redispatch solver or ten-year network pathway is validated.

## Objective

Add a human-usable Data Workbench to the existing Data page, build and review the
official-source GB candidate, hand an approved bundle to Prompt 98, and publish a
truthful release audit.

## Required work

1. Add focused React types, API client and components under
   `app/features/data-workbench`; keep scientific calculations in Python.
2. Add Installed packs, Official sources, Build benchmark, and Candidates &
   review views without breaking the existing Study-aware upload workflow.
3. Display source freshness, job progress/cancellation, candidate purpose and
   blockers, maps, reconciliation, rights, diffs and named waivers.
4. Disable promotion on mechanical gate failure. Require explicit version,
   reviewer and waiver confirmation before sending a promotion request.
5. Allow a candidate to install only with a visible experimental identity that
   cannot overwrite a promoted pack.
6. Run the real official-source discovery/fetch/build sequence. Preserve every
   unavailable or isolated item in the candidate report and do not invent
   missing official evidence.
7. Obtain explicit owner review before creating the promoted bundle. If review
   is withheld, report a complete candidate rather than claiming Prompt 98 is
   ready.
8. Validate bundle installation, Prompt 98 facade, offline runtime, portable
   paths, release rights and retained Scheme C hashes.

## Acceptance gate

- Frontend lint, production build and focused browser tests pass.
- A non-programmer can complete the frozen-fixture workflow from source review
  through promotion without entering a filesystem path.
- React output matches backend report values and performs no scientific
  reconstruction.
- The official build is deterministic from its pinned inventory.
- Candidate inventory states what is usable, blocked and required next.
- A promoted bundle, if approved, installs through the existing atomic data-pack
  path and satisfies Prompt 98 input contracts.
- Final audit distinguishes data readiness from solver and long-run scientific
  validation.

## Stop conditions

Stop before promotion on unresolved rights, failed mechanical gates, unreviewed
cut membership or absent owner approval. Stop before a readiness claim if the
bundle cannot be rebuilt offline from its pinned inventory.

## Deliverables

- Data Workbench frontend and E2E tests;
- official candidate and complete review package;
- approved promoted bundle or explicit stopped decision;
- Prompt 98 handoff report;
- source-release and portability audit;
- DATA-10 gate record, final data-workstream report and commit.

