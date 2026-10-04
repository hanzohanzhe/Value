# Prompt 24 — Open-source legal, citation and data-publication readiness

Continue from accepted Prompt 23. Inventory all copied Scheme C code, repository
assets, thesis-derived material, imported databases and generated fixtures. Act as
an open-source release steward; this is an engineering compliance audit, not legal
advice.

Apply the preservation boundary in `docs/scientific-readiness/README.md`: never
edit retained Scheme C sources, fixtures, the installed data pack or historical
run bundles.

## Objective

Make code and data publication rights, attribution and distribution boundaries
explicit before a public GitHub release. Build a versioned UK open-data aggregation
pack from sources whose redistribution terms have been verified, while retaining a
small synthetic pack for unrestricted tests.

## Mandatory constraints

- Do not invent a licence, copyright owner, permission or dataset right.
- Open access is not by itself proof of redistribution permission. Verify the
  exact licence/terms for every source file and preserve source attribution; do not
  relicense third-party data as FORCE code.
- If copied Scheme C or a dataset has unresolved rights, mark public release
  blocked and produce an owner decision checklist.
- Never upload or alter the installed data pack or historical outputs in this task.

## Implement

1. Produce a machine-readable inventory of code/data/documentation origins,
   copyright holders if known, licence/terms, attribution requirements,
   redistribution status and evidence link/location.
2. Audit copied Scheme C modules separately from new GridForm code. Define which
   directories may be released only after owner confirmation and prevent package
   builds from silently including unresolved material.
3. Add repository governance files only where facts are known: licence placeholder
   or approved licence, `CITATION.cff`, contributing guide, security policy, code of
   conduct, changelog and third-party notices. Clearly mark owner fields requiring
   confirmation.
4. Extend every publishable data binding/manifest with source URL/reference,
   licence/terms, attribution, access date, version and redistribution class.
5. Create a small synthetic, redistributable PSM/CEM data pack that exercises the
   public contracts and browser workflow without claiming to represent the UK.
6. Create a `force-uk-open-data-pack` aggregation build with a machine-readable
   bill of data for every included object: canonical role, source publisher/URL,
   exact licence and version, attribution text, access date, source and normalized
   hashes, transformation code/version, unit/time mapping, redistribution class
   and downstream module use. Preserve the existing 25-role adapter contract.
7. Where licence verification permits redistribution, package normalized immutable
   data under the source licence/notice and publish it as a separately versioned
   data artifact rather than silently embedding a large pack in the code wheel.
   Where redistribution is conditional or prohibited, package only the adapter and
   a consent-based downloader/import recipe. The aggregate manifest may reference
   both classes but must never claim incomplete data are bundled.
8. Define a consent-based external data acquisition workflow for large packs with
   checksums, expected size, licence notice and resumable download/import. Do not
   place the approximately 800 MB local pack in Git.
9. Add a deterministic aggregation command that rebuilds normalized outputs from
   pinned source revisions where permitted, produces content-addressed archives
   and a third-party notice, and never reads an undocumented Desktop path.
10. Add a release scan that blocks secrets, absolute local paths, prohibited data,
   unresolved licence classes and oversized generated run artifacts.

## Tests and acceptance

- A source archive/wheel contains only allowlisted release material.
- The synthetic pack passes preflight and a two-year small test.
- A deliberately restricted dataset is excluded and causes a useful publication
  gate failure.
- Citation/third-party metadata validate syntactically and match known provenance.
- Every file in the UK aggregation archive is traceable to one verified licence
  record and transformation; a missing/ambiguous right blocks that file from the
  redistributable archive without blocking permitted sources.
- The built data pack passes all 25 interface validations and the real two-year
  PSM/CEM workflow from a clean location.
- A clean clone can discover how to obtain optional data without receiving it
  automatically or bypassing terms.

## Stop condition

Any unresolved right affecting required executable code makes the public release
`NO-GO`. Do not choose a permissive licence on the owner's behalf.

## Deliverable

Provide the rights inventory, unresolved-decision list, redistributable file
allowlist, synthetic pack, data acquisition design and publication GO/NO-GO.
