# Zonal redispatch network design

Date: 21 August 2026

Status: approved after decision grilling Q1–Q74

Scope: optional fixed-network extension to the retained GB copperplate FORCE/VALUE model

## Purpose

Add an optional Great Britain transmission-constrained operating mode without
changing retained Scheme C. The new mode keeps the national bid-at-cost market,
then clears forecast-error balancing and network redispatch together at each
half-hour. It is a zonal transport and ETYS cut-set model. It is not an AC or DC
power-flow model and does not perform transmission expansion.

The accepted single-node/copperplate path remains a first-class selectable
model. The existing chronological perfect-foresight DC-OPF remains a separately
labelled experimental/reference method. The Prompt 70 transmission-expansion
contract remains available for future external implementations, but no bundled
executable transmission-expansion policy is selectable in this release line.

## Non-negotiable boundaries

- Do not edit retained Scheme C source or change its accepted hashes.
- Copy and adapt the required market stages into public modules.
- Do not add an implicit second registry, runner, project format or result store.
- Do not silently fall back from a failed network run to copperplate.
- Do not expose Northern Ireland as an internal GB zone.
- Do not present transport-corridor routing as physical line flow.
- Do not call this DC power flow, AC power flow, security analysis or N-1 analysis.
- Do not bundle an executable transmission CEM in this workstream.
- Keep interconnectors as external signed boundary bids at declared landing zones.
- Keep fixed internal transmission capability across 2025–2034; optional
  half-hour/seasonal availability factors may reduce it.
- Loss fields are versioned and optional. The first benchmark is explicitly
  lossless; it must not populate an unsupported loss result with zero.

## Selected architecture

### Market stages

The public PSM family gains a staged information contract:

1. A national ahead-market module consumes only the information declared at the
   ahead stage and produces the GB schedule, national clearing price and base
   settlement quantities.
2. A balancing module consumes the immutable ahead result, realised demand and
   availability, signed flexibility bids, current storage state and optional
   network data.
3. The thesis-compatible copperplate balancing implementation preserves the
   original single-node method.
4. The optional zonal implementation clears forecast error and congestion in one
   simultaneous current-period problem.
5. Final physical dispatch and storage SOC, not the ahead schedule, enter the
   annual result and the next CEM stage. The ahead schedule remains settlement and
   audit evidence.

Old Studies that select a monolithic PSM continue to execute unchanged. New
staged Studies explicitly select both the staged PSM and one balancing provider.
The registry and saved revision hold both identities and their schema hashes.

### Spatial resolution

- A signed and immutable network data pack defines approximately 18–24 zones.
- DSO licence areas are the resource, reporting and abstract-investment layer.
- A curated subset of material ETYS boundaries splits DSO areas where required.
- The pack determines the exact zone count. Code contains no fixed count.
- Once signed, a zone pack is immutable. Any geometry, boundary, rating, mapping
  or weighting change creates a new `network_pack_id`.
- Within-zone transfer is copperplate. Internal routing corridors are a
  computational transport skeleton only.
- ETYS cut-set constraints apply to signed sums of corridor flows. All selected
  cut sets bind simultaneously.

Each internal boundary supports `forward_limit_mw` and `reverse_limit_mw`. If the
source supplies only the prevailing direction, the first benchmark may mirror
the limit with `reverse_limit_method=assumed_symmetric`; it must retain the
assumption and support sensitivity replacement. Optional maintenance/seasonal
profiles multiply the fixed rating and cannot increase it unless the source pack
explicitly declares an uprating.

### Assets and agents

Economic agents remain aggregated. Physical network representation uses
`agent_id × technology × zone_id` tranches. The default network bid contains one
block per tranche, not one bidder per REPD project. Prices and economic ownership
remain at the agent level; availability and network location remain at tranche
level; accepted cashflows aggregate back to the economic agent.

Existing and planned assets use connection/site coordinates and explicit
overrides where available. Abstract model expansion remains one regional-agent
decision and is allocated by frozen, technology-specific MW shares. The shares
are derived in this order:

1. operational assets of the same technology;
2. active REPD pipeline MW of the same technology;
3. explicit user-supplied weights.

Shares do not evolve endogenously. Projects with an actual coordinate or declared
connection zone enter there and do not change the abstract allocation weights.
All zonal tranches are rescaled to preserve the accepted Scheme C/FORCE national
technology totals exactly.

Unlocated aggregate assets enter an explicit `ENGLAND_FALLBACK` calculation node
connected without a limit to a declared central England transport zone. The
result reports fallback MW and share by technology. A share above 1% is visibly
marked `material_spatial_fallback=true`; it is not described as a validation
failure.

Northern Ireland REPD rows do not enter the GB internal fleet. Irish exchange is
represented only through the external interconnector contract.

### Weather and offshore location

Two separately selectable, contract-compatible weather modules are required:

1. `representative_point`: the Scheme C regional representative coordinate and
   profile are retained. All zone tranches of that regional agent share the
   representative profile.
2. `repd_coordinate_aggregated`: each REPD asset coordinate indexes the installed
   ERA5 data/profile pack offline. Profiles are then MW-weighted by
   `agent × technology × zone` before runtime.

Ordinary users do not install GIS or download ERA5 during a run. The published
pack contains the resolved crosswalk and aggregated profiles.

Offshore assets have separate `weather_location` and `network_connection_zone`.
The weather location is the offshore REPD coordinate. Network injection uses a
known connection/landfall override where available; otherwise the deterministic
nearest-coast DSO method is used and labelled
`network_location_method=inferred_nearest_coast_dso`. This is a reproducible
approximation, not a claim about the actual connection point.

### Demand and data builder

The offline builder combines national half-hour demand with the selected
GSP/FES/DFES/DSO spatial sources. Every period's zonal demand must sum to the
unchanged GB total. Each zonal series records one provenance class:
`measured`, `calibrated` or `static_share_fallback`.

Before signing a pack, the builder produces:

- zone and ETYS boundary geometry plus a rendered audit map;
- source, mapped and fallback MW by technology and status;
- every region-to-zone allocation weight;
- offshore location-method counts and MW;
- per-period zonal-to-GB demand residuals;
- boundary direction, limits, availability and assumptions;
- interconnector landing-zone assignments;
- source dates, licences, transformation log and SHA-256 values.

The runtime reads only immutable tables/profiles. It never downloads or rebuilds
scientific inputs.

## Single-period zonal redispatch

Each half-hour is solved independently with `scipy.optimize.linprog(method="highs")`.
There is no rolling or annual foresight. Actual SOC from period `t-1` bounds
period `t` and actual period `t` actions update period `t+1`.

The objective minimizes accepted signed bid cost. It does not replace bids with
an administrator's estimate of physical cost. Built-in modules bid at cost, so
the accepted result has the intended cost-based competition. A custom bid
strategy may deliberately produce a different outcome and must receive a visible
warning that redispatch follows bids, not hidden physical cost.

All available actions enter one solve:

- thermal upward and downward movement within declared limits;
- VRE increase up to realised availability and network curtailment downward;
- storage signed net power subject to MW, MWh, SOC and efficiencies;
- signed interconnector movement within the period profile envelope;
- DSR under its declared bid and capacity;
- zonal load shedding at the run's pinned VOLL, default £17,000/MWh.

The built-in storage bid curve is convex over one signed net-power axis. Actual
power is charge, idle or discharge, never simultaneous charge and discharge.
Non-convex/custom storage bids that could self-cycle fail module conformance;
future MILP implementations may declare a separate capability.

An interconnector's positive profile is an import envelope `0..profile`; a
negative profile is an export envelope `profile..0`. It cannot reverse beyond
the declared sign in that period.

Equal-price bids with the same direction and identical network effect are
allocated pro rata by available volume. Remaining mathematical ties use a stable,
recorded order. The accepted result is deterministic.

The solver uses transport flow variables to satisfy zonal balance and selected
ETYS cut-set constraints. It records zone net positions and boundary transfers.
Artificial corridor flows are never described as line flows. A secondary
lexicographic objective minimizes total deviation from the ahead schedule after
the primary bid-cost optimum.

## Settlement and accounting

For each accepted adjustment:

```text
accepted_delta_mwh > 0  means increased injection or reduced consumption
accepted_delta_mwh < 0  means reduced injection or increased consumption
cashflow_to_agent = accepted_delta_mwh × bid_price_gbp_per_mwh
```

The base schedule remains settled at the GB national clearing price. Redispatch
cashflows are separate pay-as-bid adjustments. Investment agents read their own
actual cashflow: national settlement plus redispatch settlement plus declared
policy payments minus their costs. Dynamic storage cost recovery uses final
actual discharge MWh, not scheduled or cancelled discharge.

The following ledgers are separate and reconciled:

- `system_resource_cost`: commissioned-fleet annualized CAPEX/FOM plus final
  physical operating resource cost, imports, storage degradation, DSR delivery
  and VOLL load shedding;
- `transmission_constraint_resource_cost`: constrained realised physical cost
  minus the matched realised copperplate counterfactual;
- `redispatch_settlement`: signed pay-as-bid adjustment cashflows;
- national market settlement;
- policy/support transfers;
- `boundary_shadow_value`: marginal accepted-bid objective value of one more MW.

The shadow value is a diagnostic. It is neither a zonal market price nor actual
physical cost.

### Counterfactual attribution

For each declared comparison, the same realised inputs support:

1. perfect-forecast copperplate;
2. forecast schedule plus realised copperplate balancing;
3. forecast schedule plus realised zonal balancing/redispatch.

Forecast-error cost is `2 - 1`, constraint cost is `3 - 2`, and total control
penalty is `3 - 1`. The methodology and run identities travel with the result.

VRE evidence separately reports economic/copperplate unused energy, realised
availability change, network-added curtailment and final total curtailment.

## Evidence, reliability and results

The existing batched SQLite market ledger remains authoritative. Summary mode
stores period, zone, boundary, final dispatch, SOC, curtailment and reliability
rows. Full mode also stores every bid, acceptance, price, cashflow and rejection
reason. Ordinary annual runs default to summary; research templates default to
full after showing estimated disk use. CSV/JSONL/optional Parquet are exports,
not competing stores.

Load shedding is a valid model result, not automatically a software failure.
Report observed loss-of-load hours, EENS, event count, affected zones and maximum
deficit. A single chronology is not called statistical LOLE. Statistical LOLE is
available only from weighted multi-scenario evidence.

The frontend gains a dedicated **Network & redispatch** page linked to the same
period in Market replay. It shows the frozen map, zone net positions, boundary
transfer/capacity/utilisation, before/after dispatch, accepted up/down bids,
curtailment, DSR, VOLL, physical constraint cost, pay-as-bid settlement and
diagnostic shadow values. React never reconstructs scientific results.

## Failure behaviour

Any non-optimal solver status, residual outside tolerance, invalid SOC, boundary
violation or non-convex unsupported bid fails the network run. The system saves
the immutable pre-clearing input, solver status, residuals, logs and environment
identity. It never continues that run as copperplate.

The UI may offer **Rerun as copperplate**. This creates a new run ID and records
the failed network run as its comparison parent. The diagnostic bundle tells the
user how to report the problem to the maintainer or reproduce it independently.

## Optional capabilities retained outside this baseline

- `force-reference-dc-network` remains a full-chronology perfect-foresight DC-OPF
  benchmark with its existing truthful label.
- AC feasibility remains an experimental declared-schedule check.
- The versioned transmission-expansion contract remains public for later module
  authors. No bundled implementation is registered/selectable on this line.
- Network loss fields remain available for a future sourced module/data pack.

## Acceptance sequence

1. Infinite-limit equivalence to copperplate.
2. Hand-calculated one-boundary and overlapping cut-set cases.
3. Signed bid, settlement, curtailment, storage, interconnector, DSR and VOLL
   fixtures.
4. Independent formulation and constraint-mutation failures.
5. Deterministic random convex cases.
6. Production 24-hour and 168-hour invocations.
7. Signed GB network pack and full 17,520-period year.
8. Causal two-year PSM–CEM chain with actual cashflow, SOC and spatial expansion.
9. Only after all earlier gates pass, matched ten-year copperplate and fixed-
   network runs.
