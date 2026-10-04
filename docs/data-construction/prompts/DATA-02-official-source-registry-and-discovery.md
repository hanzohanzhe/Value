# DATA-02 — Official source registry and discovery

Execute after DATA-01 passes. Act as an official-data provenance engineer. This
prompt discovers metadata only; it does not compile or promote scientific data.

## Objective

Build a reviewed UK network source registry and deterministic discovery adapters
for NESO, DESNZ, ONS and official operator sources, plus a freshness audit that
cannot alter an installed benchmark.

## Required work

1. Add JSON SourceDefinitions for DSO licence areas, ETYS capability workbook,
   ETYS boundary GIS, DESNZ postcode consumption, ONS Postcode Directory, NESO
   FES GSP evidence and the Interconnector Register.
2. Each definition records authority, semantic role, landing page, discovery
   method, allowed domains, expected media type, expected licence and candidate
   uses.
3. Implement adapters for static official resources and NESO catalogue/API
   resources. Redirects must remain on allowlisted official domains.
4. Return SourceRevisions with publication/version evidence and statuses `new`,
   `unchanged`, `superseded` or `unavailable`.
5. Produce machine JSON and human Markdown freshness reports. Report candidate
   sources and their possible uses without placing them in the formal registry.
6. Keep live-portal checks outside ordinary CI; use frozen catalogue responses
   for deterministic tests.

## Acceptance gate

- Registry validation rejects duplicate IDs, unofficial authorities, absent
  licence expectations, missing purposes and non-HTTPS public URLs.
- Discovery fixtures parse revision, date, URL and media type deterministically.
- A changed official revision is reported but does not fetch, compile, install
  or mutate the active benchmark.
- A portal outage produces `unavailable` evidence while installed bundles remain
  valid.
- The freshness report lists every isolated candidate with `usable_for`,
  `not_usable_for`, blocker and required action.

## Stop conditions

Stop if generic search results become compiler inputs, if source URLs are baked
into model runtime code, or if discovery silently accepts a changed licence.

## Deliverables

- reviewed official SourceDefinitions;
- discovery adapter registry;
- offline discovery fixtures and tests;
- freshness and candidate reports;
- DATA-02 gate record and commit.

