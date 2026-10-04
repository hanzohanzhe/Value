# Prompt 96 — Zonal transport and ETYS cut-set data contract

Execute after Prompt 95. Reuse Prompt 67's one-registry conditional-role and
artifact mechanisms, but do not reuse DC buses/angles/branch equations as the new
scientific claim. Act as a network-data and transport-model architect.

## Objective

Add the solver-neutral data model for fixed, lossless GB zonal redispatch with
DSO resource zones, computational corridors and overlapping ETYS cut sets.

## Canonical contracts

Define and validate:

- `force.zonal-network-pack/v1`;
- `force.network-zone/v1`;
- `force.transport-corridor/v1`;
- `force.etys-cutset/v1`;
- `force.zonal-asset-map/v1`;
- `force.zonal-demand/v1`;
- `force.boundary-rating-profile/v1`;
- `force.interconnector-landing/v1`;
- `force.spatial-audit/v1`.

Zones have stable ID, display name, DSO ownership, optional geometry artifact and
immutable pack identity. Corridors have endpoints and direction only; they do
not accept reactance or voltage fields. A cut set contains signed corridor
members and separate forward/reverse limits. Ratings are fixed across model years
and may have `0..1` period availability multipliers. Optional loss capability is
absent from the first pack with reason `lossless_v1`; never emit a calculated zero
loss result.

## Conditional roles

Add namespaced roles for zones, corridors, cut sets, asset-zone map, zonal demand,
ratings, interconnector landings, spatial audit and optional map geometry. The
roles activate only when `domain.network.zonal_redispatch` is selected. Base 25
roles and Prompt 67 DC roles remain unchanged.

## Validation

Reject unknown/duplicate zones, dangling corridors, disconnected unexplained
zones, empty cut sets, duplicate signed members, invalid direction, negative
ratings, multiplier outside `0..1`, missing active assets, per-technology share
mismatch, zonal demand residual above `1e-8 MWh`, Northern Ireland internal zones,
interconnector double counting and mutable pack identities.

Create deterministic fixtures for one zone, two zones/one cut, three zones/two
overlapping cuts, an England fallback node, asymmetric limits, mirrored reverse
assumption, maintenance derating and invalid topology.

## Stop conditions

Stop if the contract calls a corridor a physical line, requires DC impedance,
introduces runtime downloads, or makes network roles mandatory for copperplate.

## Deliverables

- versioned zonal contracts, adapters and conditional roles;
- canonical synthetic fixtures and validation tests;
- data template and bilingual field dictionary.
