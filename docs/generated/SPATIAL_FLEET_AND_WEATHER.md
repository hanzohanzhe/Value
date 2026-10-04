# FORCE spatial fleet and weather preprocessing

## What this stage does

Prompt 97 adds an offline translation between national economic agents and
zonal physical tranches. It does not turn each power station or REPD row into a
market bidder. Investment, profit and cashflow remain attached to the economic
owner; network injection and weather availability are represented by aggregated
`owner × technology × zone` tranches.

The accepted national capacity remains authoritative. Wind values declared as
Scheme C capacity multipliers are converted using the recorded `20 MW` unit,
then all tranches are rescaled to the accepted national technology totals. The
builder fails if the mapped totals drift by more than `1e-8 MW`.

## Allocation precedence

For an abstract economic agent, the pack builder freezes shares in this order:

1. operational MW of the same technology by zone;
2. active-pipeline MW of the same technology by zone;
3. explicit user weights;
4. `ENGLAND_FALLBACK` if no usable location evidence exists.

The selected shares carry the immutable pack revision. Endogenous growth uses
those frozen shares; it does not feed new model capacity back into the weights.
A located REPD project remains a single, exact zonal project and retains its full
CAPEX, FOM, lifetime and owner record when commissioned.

Northern Ireland project rows are excluded from internal GB capacity. Irish
exchange remains an external interconnector offer. The audit reports excluded
IDs, fallback MW and whether fallback exceeds 1% of any technology.

## Coordinates and offshore projects

British National Grid coordinates are converted from `EPSG:27700` to
`EPSG:4326` offline. Raw eastings/northings, CRS identifiers and the pyproj
transformation description are retained. Offshore weather uses the offshore
coordinate. Network injection uses a declared connection/landfall override when
one exists; otherwise it uses a deterministic nearest-coast DSO reference point
and is labelled `inferred_nearest_coast_dso`. Missing coordinates use the
explicit England fallback and are never presented as an actual connection.

## Interchangeable weather methods

- `force-representative-point-weather` copies the declared Scheme C regional
  representative trace to all zonal tranches of that economic agent.
- `force-repd-era5-aggregated-weather` samples an installed weather pack at REPD
  locations offline and writes MW-weighted `owner × technology × zone` traces.

Both output `force.zonal-availability-profile/v1`. Annual runtime consumes only
the aggregated artifact; it does not convert coordinates, query GIS services or
open raw REPD/ERA5 data per bidder. The selected method and output hashes must be
bound by the zonal data pack built in Prompt 98.

## Compatibility boundary

The existing monolithic/copperplate module graph identity is unchanged. Spatial
metadata is attached only when a pack binds `force.zonal.asset-map`. The legacy
planning and transition copies preserve frozen-share metadata, while the typed
planning path already preserves project extension fields through commissioning.
No transmission solver is introduced by this prompt.
