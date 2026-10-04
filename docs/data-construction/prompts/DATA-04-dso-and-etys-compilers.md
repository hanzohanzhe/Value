# DATA-04 — DSO and ETYS compilers

Execute after DATA-03 passes. Act as a GB network-data modeller. Scientific
transforms consume only pinned RawObjectReceipts and never access live URLs.

## Objective

Compile versioned DSO resource zones and ETYS boundary geometry/capability
evidence without yet approving cut membership.

## Required work

1. Add a build-only `data-workbench` dependency extra containing the already
   supported Python 3.10 versions of Shapely 2.1.1, PyProj 3.7.1 and OpenPyXL
   3.1.0. Model runtime and ordinary bundle installation remain GIS-free.
2. Parse the pinned NESO DNO licence-area GeoJSON, retain source CRS evidence,
   create the EPSG:4326 display geometry, and record every deterministic repair.
3. Emit stable DSO `resource_zone` IDs and a candidate network-zone layer.
4. Parse ETYS capability workbook rows by boundary ID, year, direction and
   category. Use 2025 `Capability`; do not treat FES percentiles as ratings.
5. Parse the pinned ETYS boundary GIS and reconcile it with workbook/report
   evidence field by field. Available official information fills a missing
   same-semantic field; newer official information wins a same-field conflict
   while both values remain in the diff report.
6. Emit named reverse-capability assumptions when official reverse evidence is
   absent. Do not encode missing reverse capability as zero.
7. Inventory every discovered ETYS boundary, including excluded or report-only
   B3b/B14 evidence and its page-level provenance.

## Acceptance gate

- Geometry tests cover MultiPolygon input, CRS conversion, invalid geometry,
  duplicate zone ID, unexpected overlap and deterministic output ordering.
- Workbook tests distinguish `Capability` from FES flow percentiles and reject
  negative or unparseable ratings.
- Version tests cover missing fields, newer conflicts and semantically different
  fields that must not be merged.
- Every mirrored reverse value is reported as
  `symmetric_forward_fallback` with a requested scientific waiver.
- Rebuilding from the same raw hashes produces identical scientific files.

## Stop conditions

Stop if a DSO polygon is silently dropped, an ETYS cut is called a line, a
percentile becomes capacity, or a geometry/capability mismatch is hidden.

## Deliverables

- DSO and ETYS compiler modules;
- source and display geometries;
- capability and version-diff artifacts;
- boundary inventory and assumption report;
- DATA-04 gate record and commit.

