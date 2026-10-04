# Prompt 97 — Spatial fleet, ERA5 weather modes and CEM allocation

Execute after Prompt 96. Read the UK REPD normalized/raw bindings, current fleet
identity, ERA5/profile adapters, planning pipeline, commissioned-asset coupling,
investment-owner grouping and shared expansion headroom. Act as data modeller and
CEM spatial-coupling lead.

## Objective

Build reproducible economic-agent-to-physical-tranche preprocessing without
creating asset-level runtime bidders or changing national capacity totals.

## Required work

1. Add immutable `force.spatial-fleet/v1` and
   `force.agent-zone-allocation/v1` records with economic owner, technology,
   source asset/project, zone, MW, location method and provenance.
2. Convert REPD British National Grid coordinates explicitly; preserve raw values
   and transformation metadata.
3. Exclude Northern Ireland from internal GB capacity. Reconcile source,
   operational, active-pipeline, mapped and fallback MW by technology.
4. Derive technology-specific regional allocation weights from operational MW,
   then active pipeline MW, then explicit user weights. Freeze the weights by
   pack revision; never recompute them from endogenous model growth.
5. Rescale physical tranches so each accepted Scheme C/FORCE national technology
   total is preserved exactly. Wind `capacity_multiplier` uses its declared 20 MW
   unit; do not compare raw multipliers with MW.
6. Route unlocated aggregate assets through `ENGLAND_FALLBACK`; report the share
   and set `material_spatial_fallback=true` above 1% per technology.
7. Use real offshore connection/landfall overrides first, otherwise the
   deterministic nearest-coast DSO method and label it as inferred.
8. When a commissioned REPD project has a coordinate/zone, inject it there.
   Abstract agent additions use frozen shares and inherit full economics.

## Weather modules

Register two interchangeable preprocessing modules with one output contract
`force.zonal-availability-profile/v1`:

- `force-representative-point-weather`: copies the Scheme C representative trace
  to all tranches of the regional agent;
- `force-repd-era5-aggregated-weather`: indexes the installed ERA5/profile pack at
  REPD locations offline and aggregates MW-weighted profiles by
  `agent × technology × zone`.

Runtime receives aggregated profiles only. It must not open the raw REPD table,
perform coordinate conversion or query ERA5 per bidder.

## TDD and acceptance

Write failing tests for cross-DSO 2/3–1/3 allocation, fixed weights after model
growth, exact MW rescaling, missing/override/offshore/fallback methods, GB/NI
separation, identical representative profiles, coordinate-aggregated profiles,
bounded agent counts and next-year commissioned project placement.

## Stop conditions

Stop if asset rows become economic bidders, capacities drift, endogenous growth
changes weights, nearest coast is labelled actual connection or runtime requires
GIS/ERA5 downloads.

## Deliverables

- spatial fleet/allocation and weather module contracts;
- offline builders and tests;
- capacity/location audit artifacts and CEM transition fixtures.
