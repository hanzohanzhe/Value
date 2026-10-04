# FORCE zonal-network data contract

## Scope

`force.zonal-network-pack/v1` is the input boundary for the optional fixed,
lossless zonal redispatch method. It describes resource zones, computational
routing corridors and signed ETYS-style cut sets. It does not describe physical
transmission lines, AC or DC power flow, N-1 security, voltage, losses or
endogenous network expansion.

The eight required roles appear in **Data** only when the zonal redispatch
extension is selected. The ordinary 25-input copperplate pack and the earlier
Prompt 67 DC/AC contracts are unchanged.

## Demand authority

A zonal Study must declare one mode. In `scenario_scaled_zonal_shares`, period
\(t\) uses the signed network-pack share
\(s_{z,t}=D^{network}_{z,t}/D^{network}_{GB,t}\) and constructs
\(D^{run}_{z,t}=s_{z,t}D^{research}_{GB,t}\). The research pack therefore keeps
authority over national realised and forecast demand. In
`network_pack_absolute_demand`, the network pack supplies zonal and national
demand; the research forecast-to-real ratio is retained for the corresponding
forecast. This second mode is an independent demand study and is not eligible
for network-cost attribution against a scenario-demand copperplate run.

The shipped GB pack uses fixed 2024 DESNZ postcode-derived zonal weights. A
replacement pack may declare time- or year-varying shares, but it must provide
unique, exactly aligned period IDs and reconcile each period without cyclic
repeat, interpolation or an equal-share fallback.

## Field dictionary

| Contract / field | Meaning | Validation boundary |
| --- | --- | --- |
| `network_pack_id` | Stable identity of the assembled zonal pack | Cannot be blank or mutate after a Study is declared |
| `scientific_sha256` | Hash of the fully assembled typed pack | Must match after every role is loaded |
| `zone_id` | Stable scientific zone identifier | Unique; display names and optional geometry do not replace it |
| `display_name` | Human-readable zone label | Informational |
| `dso_owner` | DSO association used by the pack builder | Required provenance label, not a claim of legal exclusivity |
| `nation` | GB nation containing the resource zone | Northern Ireland internal zones are rejected in v1 |
| `is_unconstrained_fallback` | England fallback for unresolved assets | Must be explicitly identified and audited |
| `corridor_id` | Computational routing-edge identifier | Unique; cannot double as an interconnector asset |
| `from_zone_id`, `to_zone_id` | Corridor endpoints | Both must be known zones; self-loops fail |
| `positive_direction` | Sign convention for corridor flow | Exactly `from_to_positive` |
| `purpose` | Scientific meaning of the corridor | Exactly `computational_routing`; physical-line language fails |
| `boundary_id` | Stable ETYS-style cut-set identifier | Unique |
| `members[].coefficient` | Contribution of a corridor to boundary flow | Only `+1` or `-1`; a corridor cannot appear twice in one cut set |
| `forward_limit_mw` | Positive-direction cut-set rating | Finite and non-negative |
| `reverse_limit_mw` | Negative-direction cut-set rating magnitude | Finite and non-negative; may differ from forward |
| `reverse_limit_method` | Evidence basis for the reverse rating | Independent source or an explicitly declared symmetry assumption |
| `rating_profile_id` | Optional maintenance availability profile | Must reference a declared profile |
| `multipliers` | Per-period rating availability | `0..1`, same clock as zonal demand, fixed across model years in v1 |
| `asset_id`, `zone_id`, `share` | Fixed asset-to-zone allocation | All active assets covered; shares for each asset sum to one |
| `mapping_method` | Coordinate, regional-share, landing or fallback rule | Preserved for audit; zone cannot change during a Study |
| `demand_mwh_by_zone` | Raw absolute demand or the source of zonal shares, according to the Study mode | Non-negative; every and only declared zone is present |
| `national_demand_mwh` | National demand used for reconciliation | Zonal sum residual cannot exceed `1e-8 MWh` per period |
| `interconnector_id`, `asset_id`, `zone_id` | External boundary offer landing | Signed profile remains the envelope; never an internal corridor |
| `capacity_mw_by_technology` | Capacity before spatial allocation | Must reconcile to mapped capacity within declared tolerance |
| `fallback_asset_ids` | Assets assigned to the England fallback | Reported rather than silently hidden |
| `loss_capability_absent_reason` | Explicit absence of loss calculation | Exactly `lossless_v1`; no fabricated zero-loss result is emitted |

## Conditional data roles

`force.zonal.zones`, `corridors`, `cutsets`, `asset-map`, `demand`, `ratings`,
`interconnector-landings` and `spatial-audit` are required together. Optional
`force.zonal.geometry` is display-only. The example at
`examples/zonal-network-pack` is the canonical CC0 template.

## Identity and failure behaviour

Every bound file has a SHA-256 checksum. The assembled typed pack has a second
scientific SHA-256 identity. Unknown zones, dangling or unexplained disconnected
zones, invalid limits, missing active assets, demand/capacity residuals and
interconnector double counting fail before a solver can run. FORCE performs no
runtime data download at this boundary.
