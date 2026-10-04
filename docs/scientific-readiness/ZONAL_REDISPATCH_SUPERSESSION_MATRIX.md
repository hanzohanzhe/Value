# Zonal redispatch supersession and identity matrix

Date: 21 August 2026

Status: Prompt 93 contract freeze; implementation remains planned

This matrix prevents Prompts 93–106 from silently replacing or renaming earlier
work. It contains product identities only and changes no scientific equation.

## Earlier work

| Earlier prompt/capability | Decision for Prompts 93–106 | Boundary |
| --- | --- | --- |
| Prompt 67 network contract family | Reuse generic extension negotiation, conditional data roles and artifact linkage | Do not describe the new transport/cut-set method as the Prompt 67 DC bus/branch formulation |
| Prompt 68 `force-reference-dc-network` | Retain unchanged as a separate perfect-foresight DC-OPF benchmark | It is not the staged zonal balancing implementation and is not the default PSM |
| Prompt 69 `force-reference-ac-feasibility` | Retain unchanged and experimental | It supplies no AC/security validation for the zonal method |
| Prompt 70 network-expansion contracts | Retain public contract types and historical evidence | The bundled `reference-transmission-expansion` implementation is not selectable on this release line |
| Prompt 83 domain-result presentation | Reuse artifact discovery, pagination and read-only rendering patterns | Replace DC/AC/expansion terminology with zone, computational-corridor and redispatch terminology only for new artifacts |
| Existing monolithic `scheme-c-psm` | Retain selection, project hashes and execution unchanged | Old Studies do not acquire a balancing slot |
| Castle 101 | Retain as the first copperplate teaching path | It requires no network pack or network configuration |
| Existing market ledger v4 | Migrate in place to v5 | Do not create a parallel scientific result database |

## Frozen module and capability identities

| Slot | Module ID | Version | Provides | Requires |
| --- | --- | --- | --- | --- |
| `psm` | `force-staged-bid-at-cost-psm` | `1.0.0` | `market.ahead-schedule/v1` | `market.balancing/v1` |
| `balancing` | `force-copperplate-balancing` | `1.0.0` | `market.balancing/v1`, `domain.single_node` | staged ahead result |
| `balancing` | `value-zonal-redispatch-balancing` | `2.0.0` | `market.balancing/v1`, `domain.network.zonal_redispatch` | signed zonal network pack |
| `weather_spatialisation` | `force-representative-point-weather` | `1.0.0` | `weather.zonal-availability/v1` | representative regional profiles |
| `weather_spatialisation` | `force-repd-era5-aggregated-weather` | `1.0.0` | `weather.zonal-availability/v1` | pinned REPD crosswalk and installed ERA5/profile pack |

`balancing` and `weather_spatialisation` are conditional slots. They must not be
added to an existing monolithic Study's canonical payload, graph hash or run
snapshot.

## Frozen contract identities

### Staged market

- `force.ahead-market-input/v1`
- `force.ahead-market-result/v1`
- `force.flexibility-bid/v1`
- `force.balancing-input/v1`
- `force.balancing-result/v1`
- `force.staged-market-year-result/v1`
- `force.balancing-module/v1`

### Fixed zonal network and spatial data

- `force.zonal-network-pack/v1`
- `force.network-zone/v1`
- `force.transport-corridor/v1`
- `force.etys-cutset/v1`
- `force.zonal-asset-map/v1`
- `force.zonal-demand/v1`
- `force.boundary-rating-profile/v1`
- `force.interconnector-landing/v1`
- `force.spatial-audit/v1`
- `force.spatial-fleet/v1`
- `force.agent-zone-allocation/v1`
- `force.zonal-availability-profile/v1`
- `force.zonal-redispatch-declaration/v1`

### Evidence and results

- `gridform.market-ledger/v5`
- `force.zonal-period-summary/v1`
- `force.boundary-period-summary/v1`
- `force.redispatch-settlement/v1`
- `force.reliability-event/v1`
- `force.zonal-results-query/v1`
- `force.zonal-counterfactual-attribution/v1`

## Conditional data-role identities

The following roles activate only with capability
`domain.network.zonal_redispatch`:

- `force.network.zonal.zones`
- `force.network.zonal.corridors`
- `force.network.zonal.cutsets`
- `force.network.zonal.asset-map`
- `force.network.zonal.demand`
- `force.network.zonal.ratings`
- `force.network.zonal.interconnector-landings`
- `force.network.zonal.spatial-audit`
- `force.network.zonal.map-geometry` (optional)
- `force.network.zonal.availability-profiles`

They do not alter the 25 base roles or the Prompt 67 DC-network roles.

## Result definitions pinned for implementation

| Result | Definition |
| --- | --- |
| Final dispatch | Physical dispatch after realised forecast-error balancing and network redispatch; this alone updates SOC and CEM operating evidence |
| National settlement | Ahead schedule settled at the national clearing price |
| Redispatch settlement | Signed pay-as-bid adjustment cashflow stored separately from national settlement |
| System resource cost | Commissioned-fleet annualised CAPEX/FOM plus final physical operating resource cost under the existing FORCE CEM ledger identity |
| Constraint resource cost | Realised zonal physical resource cost minus the matched realised copperplate balancing counterfactual |
| Boundary shadow value | Diagnostic marginal accepted-bid objective value; neither a zonal market price nor an observed cash cost |
| Reliability | Observed loss-of-load half-hours, EENS, event count, affected zones and maximum deficit; not statistical LOLE |
| Corridor output | Computational routing only; publish zone net position and ETYS boundary transfer, not real line flow |

## Dependency and stop graph

```text
93 → 94 → 95 → 96 → 97 → 98 → owner sign-off
                                  ↓
                                 99 → 100 → 101 → 102 → 103
                                                        ↓ GO
                                                       104
                                                        ↓ GO
                                                       105 → 106
```

- Prompt 98 cannot issue a final `network_pack_id` without owner sign-off.
- Prompt 103 blocks full-year execution.
- Prompt 104 blocks the matched ten-year matrix.
- A failed network solve remains a failed immutable run. Copperplate rerun uses a
  new run ID and comparison-parent link.

## Preserved identities

- Prompt 92 source commit: `4915811ad1d5e6bc950e65cea89840cd67f7611a`
- Prompt 92 tag: `value-castle-101-prompt92-20260820`
- Prompt 93 rollback tag: `pre-zonal-redispatch-prompt93-20260821`
- Retained Scheme C hash manifest:
  `docs/visibility-refactor/retained-source-hashes.json`
