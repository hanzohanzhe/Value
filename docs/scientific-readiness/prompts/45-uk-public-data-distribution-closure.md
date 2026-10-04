# Prompt 45 — UK public-data distribution closure

Continue after Prompt 44. The installed UK pack remains read-only. This prompt
changes manifests, download/transform tooling and distributable artifacts only.

## Objective

Turn the working local 25-interface pack into a legally separable public data
workflow without relicensing third-party data.

## Required implementation

- Resolve exact landing pages, licences and permitted transformations for each of
  the five wholesale-price roles, raw REPD treatment and every policy-workbook
  row.
- Classify each object as redistributable, download-on-user-machine, derived-only,
  owner-licensed or excluded. Record attribution text and licence version.
- Prefer a pinned manifest plus checksummed downloader/transformer whenever raw
  redistribution is uncertain. Never place a conditional or local-only object in
  a public combined archive.
- Generate a small CC0 synthetic pack for all 25 interfaces and a local installer
  that can assemble the real UK pack from user-authorised downloads.
- Validate hashes, schema, units, time coverage, clock convention and provenance
  after assembly.

## Acceptance

- The public artifact scan proves it contains no conditional/local-only bytes.
- The synthetic pack passes all 25 adapters and a smoke run.
- The locally assembled pack reproduces the frozen interface inventory and
  semantic preflight without duplicating the installed source pack.
- A rights report gives a separate GO/NO-GO decision per object and for the final
  public archive.

## Stop condition

If any object remains uncertain, distribute its pointer/transform contract, not
the data itself.
