# DATA-05 — Regional-demand compiler

Execute after DATA-04 passes. Act as a demand-spatialization scientist. Preserve
the FORCE national demand chronology and total exactly.

## Objective

Build base DSO/network-zone demand weights from DESNZ postcode consumption and
ONS coordinates, then evolve relative yearly weights with NESO FES GSP evidence.

## Required work

1. Stream or chunk pinned DESNZ postcode-level domestic and non-domestic
   consumption and pinned ONS Postcode Directory coordinates.
2. Normalize postcode keys without collapsing distinct valid records; report
   unmatched, terminated, non-GB and duplicated postcodes separately.
3. Assign coordinates by point-in-polygon to DSO resource zones and directly to
   reviewed network-zone candidates where a DSO is split.
4. Aggregate measured base-year energy rather than polygon area.
5. Map pinned FES GSP evidence to resource/network zones and apply its relative
   yearly evolution to the measured base weights.
6. Normalize each year's weights and multiply the existing FORCE national
   half-hour series without changing its values.
7. Emit `measured`, `calibrated` or `static_share_fallback` provenance per zone
   and year, plus coverage and reconciliation evidence.
8. Apply any floating residual deterministically to the largest positive demand
   zone for that period and record the pre/post residual.

## Acceptance gate

- Domestic and non-domestic energy reconcile to source totals after documented
  GB exclusions.
- Each year's weights are non-negative and sum to one.
- Each period's zonal demand sums to the pinned national value within
  `1e-8 MWh`.
- Boundary-point and postcode-mismatch fixtures are deterministic and visible.
- Changing national demand changes only the national scale, not the chosen
  regional-weight method.
- Static fallback is experimental unless explicitly waived at promotion.

## Stop conditions

Stop on pure administrative-area weighting, silent postcode deletion, a demand
series that changes the FORCE national total, or an unexplained residual.

## Deliverables

- postcode/ONS and FES compiler modules;
- yearly zone weights and half-hour zonal demand;
- coverage, method and reconciliation reports;
- DATA-05 gate record and commit.

