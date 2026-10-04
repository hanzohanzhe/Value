# Prompt 98 — GB zonal benchmark build and human sign-off

Execute after Prompt 97. Use official/versioned local source assets for DSO
licence areas, NESO ETYS boundaries/capabilities, national demand,
GSP/FES/DFES/DSO spatial evidence, interconnector landings, REPD and the installed
ERA5/profile pack. Act as UK network-data lead. This prompt builds data; it does
not run a scientific network model.

## Objective

Produce a candidate immutable GB fixed-network benchmark pack, then stop for
human review before assigning its final `network_pack_id`.

## Builder requirements

1. Add an offline source-discovery/inventory helper for NESO national demand,
   GSP/FES/DFES/DSO regional-demand evidence, ETYS boundaries/ratings, DSO areas,
   REPD, interconnector landings and the installed ERA5/profile pack. It records
   authoritative URL, publication/version, licence, access result and local
   object hash. Scientific transforms consume pinned local objects; the runtime
   never searches or downloads data.
2. Use DSO areas as the base resource layer and a curated material subset of ETYS
   boundaries. Merge meaningless slivers and target approximately 18–24 zones;
   code and schemas must not require a specific count.
3. Generate a computational corridor graph and signed cut-set incidence matrix.
   Validate that every selected cut separates the intended zone sets.
4. Store fixed forward/reverse MW capabilities and source direction. Where only
   one direction is sourced, mirror it with
   `reverse_limit_method=assumed_symmetric`. Add only sourced maintenance or
   seasonal derating multipliers.
5. Create calibrated half-hour zonal demand whose exact sum equals the accepted
   GB demand every period. Label each zone's method measured, calibrated or
   static-share fallback.
6. Map generators, storage, hydro, imports and demand; create offshore and
   fallback audits; place interconnectors only at declared landing zones.
7. Build both accepted weather-profile variants without changing economic-agent
   count or national technology totals.
8. Store source URL/title, publication date, local object hash, licence,
   transformation step, coordinate reference system and builder version.

## Mandatory review package

Write machine-readable reconciliation plus a human review report containing:

- zone/boundary/interconnector/power-station map;
- source/mapped/fallback MW by technology and status;
- national model versus REPD operational capacity comparison;
- region-to-zone weights;
- offshore actual/override/inferred connection counts and MW;
- maximum zonal-demand reconciliation residual;
- every assumed-symmetric boundary and derating profile;
- all unmapped/excluded records and reasons;
- licence and redistribution decision per object.

Do not sign or install the final pack automatically. Present the candidate hash
and review package to the owner. Only explicit approval may create the immutable
ID and signed manifest. A rejected candidate remains evidence and is not used by
later prompts.

## Acceptance

- All active internal assets map or use the visible fallback contract.
- National capacities and every demand period reconcile to declared tolerances.
- The pack contains no runtime absolute path or live-download dependency.
- Rebuilding from the same source inventory produces the same scientific files
  and hashes, excluding declared build timestamp metadata.

## Stop conditions

Stop on unclear rights, unexplained capacity/demand difference, invalid boundary
direction, unreviewed zone split or absent owner sign-off.

## Deliverables

- deterministic offline builder and candidate pack;
- source-discovery inventory and pinned raw-object manifest;
- rendered map and reconciliation/rights reports;
- owner-signed immutable benchmark manifest or an explicit stopped decision.
