# Prompt 98: GB zonal benchmark candidate review

Date: 21 August 2026  
Decision: **owner approved; signed and installed locally**

Prompt 98 produced a complete GB zonal candidate from the nine required local
data roles. Hanzhe Xing approved the candidate and all decisions listed below
on 21 August 2026. The signing path revalidated every reviewed scientific file,
created a local approval attestation, assigned the immutable network-pack ID
`force-gb-zonal-network-v1-c9e841112c40`, and installed the pack through the
existing atomic data-bundle installer. Prompt 99 may now start.

The candidate scientific hash is
`c9e841112c40d3a6acfe20d62116bf3f5f877f3da1a76f409e99ac6fe9c251f2`.
Three builds, including one after a review-only battery-label correction,
produced the same scientific hash and the same ten scientific artifact hashes.
The validator reloaded the contracts, checked every artifact identity and
confirmed `passed_unsigned_candidate_validation`.

The final repository-wide Python run after owner sign-off passed 497 tests,
skipped 21 declared optional tests, passed 89 subtests and reported no failures.
The Prompt 98 and Data Workbench subset passed 97 tests; the retained Scheme C
source-manifest protection test also passed.

## Proposed network

The first candidate contains 22 constrained internal zones and one visible,
unconstrained `ENGLAND_FALLBACK` zone. The internal zones begin with the NESO
DNO licence-area geometry and are split only where the selected ETYS boundaries
require it. This remains a zonal transport abstraction: the 22 computational
corridors are routing edges, not claims about individual transmission circuits.

Only two ETYS boundaries are constrained in this first benchmark:

| Boundary | Forward limit | Reverse limit | Reverse evidence |
| --- | ---: | ---: | --- |
| B6 | 6,700 MW | 6,700 MW | assumed symmetric from the published forward capability |
| B7a | 9,400 MW | 9,400 MW | assumed symmetric from the published forward capability |

The DNO geometry contains very small fragments and embedded licence-area
overlaps. The compiler preserves the smaller embedded area, removes the overlap
from the larger parent, and merges 221 pieces smaller than 1% of their parent
area. Three North Scotland geometry gaps require explicit routing bridges:

- North Scotland 2 ↔ North Scotland 4;
- North Scotland 3 ↔ North Scotland 4;
- North Scotland 1 ↔ North Scotland 2.

These bridges keep the computational graph connected. They do not represent
identified physical circuits. The fallback zone connects without a transmission
constraint at West Midlands, in line with the previously approved treatment of
unlocated aggregate England assets.

The rendered review map is
[`publication/prompt98-gb-zonal-zone-map.svg`](../../publication/prompt98-gb-zonal-zone-map.svg).

## Demand and weather

The national demand series has 17,520 half-hour periods. Regional weights come
from 2024 DESNZ individual-postcode electricity consumption joined to the
corrected May 2026 ONS Postcode Directory and allocated to the proposed zones.
The compilation assigned 1,293,698 postcodes. Of 94,445,757.831 MWh in the
individual-postcode source rows, 94,397,979.657 MWh was assigned inside the GB
zones, 35,561.008 MWh was unmatched and 12,217.165 MWh was invalid or outside
the geometry. The accepted weights are renormalised over the included GB
energy. Every model period then reconciles exactly to the accepted national
demand series; the maximum residual is 0 MWh.

FES GSP data is pinned and retained as calibration evidence, but it is not
silently applied. A reviewed GSP-to-candidate-zone crosswalk does not yet exist.

Both previously approved weather modes are present:

- Scheme C representative-coordinate ERA5 profiles; and
- operational-REPD, MW-weighted zonal ERA5 profiles.

Each mode contains 40 zonal technology profiles with 17,520 values. One
aggregated-weather group—`offshore20` in Yorkshire 3—has no operational offshore
REPD source in the same zone and therefore uses the declared GB technology-pool
fallback. This is visible in the review record rather than silently substituted.

## Fleet and interconnectors

The model fleet has 58 active assets. Capacity is conserved exactly for every
technology between the copied source and the zonal mapping. Nine aggregate
assets lack defensible site coordinates and remain on `ENGLAND_FALLBACK`:

`0.25c_battery`, `0.5c_battery`, `1c_battery`, `CCGT`,
`Hydro_natural_flow`, `Nuclear`, `OCGT`, `bio_and_waste` and
`pumpedhydro_battery`.

The REPD comparison now aggregates FORCE's 1C, 0.5C and 0.25C battery classes
to REPD's single `Battery` category for review only. The internal model classes
and their capacities are unchanged. Offshore capacity matches REPD to floating
point precision; onshore differs by 2.5 MW. Battery, solar, natural-flow hydro
and pumped-hydro differences remain visible because Scheme C's retained fleet
is not identical to the Q2 July 2025 REPD operational cohort.

Nine built physical interconnector tranches are mapped to GB landing zones and
retain the five Scheme C country-agent price/profile semantics. Their landing
coordinates are a curated crosswalk accepted by the owner for this network-pack
revision. A changed landing assignment requires a new candidate and network ID.

## Rights boundary

The source objects were pinned by revision and SHA-256. The derived DNO layer,
interconnector register output and copied model-fleet contract are recorded as
redistributable. The ETYS capability workbook remains pointer-only. ONSPD-based
regional demand evidence, the local demand series, REPD research copy and ERA5
profiles remain local-use-only under the conservative object-level decision.

Therefore the complete real-UK candidate is a separate rights-governed local
asset. It must not be bundled unchanged in the public source release. Public CI
and tutorials continue to use the CC0 synthetic pack.

## Owner decisions accepted

The owner accepted all of the following for the first experimental GB zonal
benchmark:

1. B6 and B7a are the only constrained ETYS boundaries in this version.
2. The spatial resolution is 22 internal zones plus the visible unconstrained
   England fallback.
3. B6 and B7a reverse limits are symmetric assumptions, not separately sourced
   reverse capabilities.
4. The three North Scotland routing bridges and 221 small-fragment merges are
   acceptable computational treatments.
5. The disclosed postcode-demand exclusions and exact national reconciliation
   are acceptable.
6. Nine unlocated aggregate fleet assets may remain on the fallback zone.
7. The single offshore weather fallback is acceptable.
8. The nine interconnector landing-zone mappings are accepted or corrected.
9. FES GSP evidence remains unapplied until its crosswalk is reviewed.
10. The full candidate remains a local, rights-governed asset rather than a
    bundled public benchmark.

## Sign-off state

Owner sign-off is **approved**. The approved candidate hash remains
`c9e841112c40d3a6acfe20d62116bf3f5f877f3da1a76f409e99ac6fe9c251f2`.
Assigning the final ID and portable installed paths produces the installed
scientific identity
`73866744184560532ad89f8c1d933941153269c977ea54039a6309973765f791`;
the signed receipt records this exact candidate-to-install mapping. The
candidate directory itself was not modified.

The complete pack remains a local rights-governed asset and is installed under
`<FORCE_DATA_HOME>/data-workbench/installed-packs/force-gb-zonal-network-v1-c9e841112c40`.
It is deliberately absent from the public source tree. The machine-readable
decision and signed receipt are
[`publication/prompt98-gb-zonal-pack-candidate.json`](../../publication/prompt98-gb-zonal-pack-candidate.json)
and
[`publication/prompt98-signed-installation.json`](../../publication/prompt98-signed-installation.json).
