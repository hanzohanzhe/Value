# DATA-08 — Validation, reporting and promotion

Execute after DATA-07 passes. Act as a scientific data-release auditor. This
prompt may promote only a candidate whose mechanical gates pass and whose
scientific waivers are accepted explicitly.

## Objective

Implement the six-gate validation matrix, candidate inventory, rights/diff
review package and atomic local approval/promotion into `force.data-bundle/v1`.

## Required work

1. Implement source/rights, schema, spatial/topology, scientific reconciliation,
   determinism/regression and owner-review gates as independent validators.
2. Assign stable issue codes, severity, affected artifact, evidence and repair
   guidance. Validators never modify candidate files.
3. Enforce non-waivable mechanical failures for rights, hashes, schema,
   references and conservation.
4. Permit only registered scientific waivers, initially symmetric reverse
   ratings, country-profile allocation, nearest-coast location and static demand
   shares.
5. Generate candidate inventory, validation, version diff, rights, assumptions,
   human review and reconciliation artifacts.
6. Revalidate Candidate ID and manifest immediately before promotion; create a
   local approval attestation and atomically install the immutable final bundle.
7. Keep rejected/superseded candidates as evidence without adding them to the
   formal bundle index.

## Acceptance gate

- Mutation tests fail each mechanical gate and prove it cannot be waived.
- Unknown waiver IDs and waivers unrelated to observed issues are rejected.
- Promotion with a stale Candidate hash fails without changing installed packs.
- Promotion is byte-deterministic apart from declared approval metadata.
- Candidate and human reports answer what is usable, not usable, blocked and
  required for promotion.
- The existing data-bundle validator and atomic installer accept the promoted
  archive.

## Stop conditions

Stop if validation edits data, if a mechanical failure can be clicked through,
if promotion overwrites an immutable bundle or if local approval is called a
cryptographic identity signature.

## Deliverables

- independent validator suite and issue catalogue;
- candidate/review reports;
- waiver registry;
- atomic promotion and local approval attestation;
- DATA-08 gate record and commit.

