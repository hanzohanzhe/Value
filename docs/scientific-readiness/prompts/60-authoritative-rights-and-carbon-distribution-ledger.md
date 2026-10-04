# Prompt 60 — Authoritative rights and carbon-distribution ledger

Execute from the canonical Prompt 59 branch. Read Prompts 24, 40, 45 and 55,
`RIGHTS.json`, `rights-inventory.json`, `uk-source-plan.json`,
`THIRD_PARTY_NOTICES.md`, the UK source register and every carbon database source
record. Act as an open-data release steward and scientific provenance engineer;
this is an engineering compliance audit, not legal advice.

## Objective

Remove contradictory redistribution statements and establish one generated,
machine-readable authority for code, documentation, the synthetic pack, each UK
benchmark object and each carbon-database release component.

## Non-duplication boundary

- Reuse the 25 object hashes, source research, licence evidence, attribution and
  assembled UK asset accepted by Prompt 45. Do not repeat broad web research or
  rebuild unchanged data.
- Reuse the carbon SQLite/CSV snapshot and two scenario boundaries accepted by
  Prompts 21, 44 and 55. Do not change factor values to make licensing easier.
- Do not invent permissions, apply Apache/CC0 to third-party data, or treat open
  access as a redistribution licence.
- Metadata corrections alone do not require scientific runs.

## Implement

1. Define one versioned rights-ledger schema and precedence rule. Make all human
   notices generated summaries or checked projections of that ledger rather
   than independent claims.
2. Reconcile the currently conflicting interconnector-price attribution,
   policy-workbook status and UK pack GO decision. For each object record exact
   source/version, licence evidence, attribution, transformation, permitted
   release product and unresolved caveat.
3. Decide the public carbon product record by record. Distinguish database
   schema/software, owner-authored reproduction snapshot, third-party factual
   factor rows and cited documents. Either clear each shipped row, or exclude
   uncleared rows from the wheel and provide a local builder/pointer. Never ship
   a mixed database under an unsupported blanket licence.
4. Make `pyproject.toml`, wheel/sdist/source manifests, the UK data asset and
   notices consume the authoritative release decision. A prohibited object must
   fail the package gate.
5. Retain the policy workbook's approximate/projected scientific caveat and the
   carbon factor boundary/variant warnings independently of copyright status.
6. Generate a human-readable bill of data and third-party notice from the same
   ledger. Include a change log from the superseded records.

## Tests and acceptance

- Every shipped or separately downloadable object has exactly one non-conflicting
  release disposition, licence/evidence record and required attribution.
- No generated notice says `local-only` while the same bytes are in a public
  asset, and no `GO` object lacks its evidence.
- Wheel, sdist, source ZIP and UK asset scans agree with the ledger.
- Carbon database tests and factor/scenario hashes remain unchanged unless an
  explicit new dataset version is created.
- Deliberately conflicting or missing rights records fail CI.

## Stop condition

If an object cannot be cleared, exclude its bytes and ship only a pointer,
adapter or consent-based acquisition recipe. If exclusion would make a required
public data pack incomplete, report that product as NO-GO without blocking the
software plus synthetic-pack release.

## Deliverable

Provide the authoritative ledger, generated notices, package-boundary decision,
conflict-resolution table and per-product GO/NO-GO. Do not run annual or
ten-year models unless scientific data bytes changed.
