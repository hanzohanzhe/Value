# DATA-07 — Zone, corridor and cut review candidate

Execute after DATA-06 passes. Act as a zonal-network abstraction architect. This
prompt proposes and audits cut membership; it cannot sign a benchmark.

## Objective

Combine DSO resources, reviewed zone splits, computational corridors and ETYS
electrical cuts into a deterministic GB zonal candidate and human review map.

## Required work

1. Build DSO adjacency and candidate network-zone partitions from reviewed ETYS
   geometry; retain the DSO parent for every network zone.
2. Construct a minimal connected computational corridor skeleton. Corridors are
   transport variables, not physical circuits, and contain no reactance or
   voltage claims.
3. Propose signed ETYS cut membership from geometry/topology and emit positive
   side, negative side, member corridor and orientation evidence.
4. Apply a versioned human-override artifact for approved split, merge,
   membership and direction decisions. The compiler must not mutate this
   approval file.
5. Render a static SVG/GeoJSON audit map and machine tables for all accepted,
   excluded and unresolved cuts.
6. Assemble the Prompt 96 canonical roles with demand, interconnector and
   existing Prompt 97 asset/weather mappings.
7. Refactor `gb_zonal_pack_builder.py` into a compatibility facade over the new
   compiler while preserving its public API and deterministic Prompt 98 tests.

## Acceptance gate

- Synthetic one-cut and overlapping-cut cases match hand-authored incidence.
- Every network zone has one DSO parent and every corridor has valid endpoints.
- Every accepted cut is non-empty, directed and tied to an approval record.
- Unreviewed membership remains `needs_mapping` and blocks formal promotion.
- Rendered map IDs reconcile exactly with machine artifacts.
- Prompt 96, Prompt 97 and existing Prompt 98 tests pass unchanged or through a
  documented compatibility assertion.

## Stop conditions

Stop if GIS intersection automatically becomes scientific approval, if a
corridor is described as a physical line, or if the facade forks the canonical
zonal contract.

## Deliverables

- zone/corridor/cut compiler;
- approval-override schema;
- audit map and cut review tables;
- complete unsigned GB candidate;
- Prompt 98 compatibility facade;
- DATA-07 gate record and commit.

