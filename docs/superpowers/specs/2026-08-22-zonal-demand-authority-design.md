# Zonal demand authority and causal-comparison design

**Date:** 22 August 2026  
**Status:** approved  
**Scope:** Prompt 104 demand alignment, auditability and matched copperplate/zonal comparisons

## Problem

The first real Prompt 104 zonal smoke stopped before clearing because the base
research pack and the signed GB network overlay contain different national
demand chronologies.  The staged PSM read 232.9051895 TWh from the Scheme C
research chronology, while the network overlay carried 233.2112515 TWh of NESO
ND.  Treating both as simultaneous authorities made the signed zonal total fail
the live national-demand equality check.  This is a data-authority ambiguity,
not a redispatch-solver or energy-conservation defect.

## Scientific contract

Every zonal Study declares exactly one `zonal_demand_mode` in
`market_configuration`.

### `scenario_scaled_zonal_shares`

This is the default for newly composed zonal Studies and the only mode eligible
for a controlled copperplate-versus-zonal network comparison.

For period `t` and zone `z`:

```
share[z,t] = network_demand[z,t] / network_national_demand[t]
run_demand[z,t] = share[z,t] * research_pack_real_demand[t]
```

The research pack remains authoritative for national realised and forecast
demand.  The network overlay supplies only spatial shares.  The final zone is
closed by residual so the zonal sum equals national realised demand to machine
precision.  The current signed UK overlay uses fixed 2024 DESNZ postcode
consumption shares, although the contract accepts future year- and
period-specific shares.

### `network_pack_absolute_demand`

This advanced mode makes the network overlay authoritative for realised
national and zonal demand.  Until a network forecast role exists, forecast
demand is transformed with the base chronology's forecast-to-real ratio:

```
run_forecast[t] = network_national_demand[t]
                  * base_forecast[t] / base_real[t]
```

If the base realised demand is zero, both base forecast and network national
demand must also be zero.  Otherwise the run fails rather than inventing a
ratio.  Results from this mode are labelled as an independent zonal-demand
study.  Cost differences against a scenario-demand copperplate run are not
attributed to transmission constraints.

## Validation and failure rules

- A zonal Study without an explicit supported mode fails draft resolution and
  preflight.  Existing saved Studies are not silently migrated.
- New zonal Studies composed in the frontend default explicitly to
  `scenario_scaled_zonal_shares`.
- Network period identifiers must match the requested chronology exactly and
  in order.  Missing, duplicate or shifted identifiers fail.
- A period with zero network national demand and positive research demand
  fails unless a future pack explicitly supplies fallback weights.  The first
  release does not carry forward, interpolate or equal-split weights.
- Every scaling factor must be finite and non-negative.  The audit reports its
  minimum, maximum and annual mean.  A pack-declared advisory range may produce
  a warning, but no hard-coded range blocks a scientifically valid run.
- The network overlay remains immutable.  Alignment produces run input and
  evidence; it never edits or re-signs the overlay.

## Runtime boundary

`gridform_core.zonal_demand_alignment` owns validation and produces an immutable
alignment object before the first market period clears.  The staged PSM consumes
that object for realised zonal demand and, in absolute mode, for the national
realised and forecast chronologies.  Redispatch continues to receive the
original signed network topology and limits.

Each period records:

- demand mode;
- research-pack national realised demand;
- research-pack national forecast demand;
- original network national demand;
- applied scale factor;
- aligned zonal total;
- conservation residual.

These rows are written in batches to the authoritative market SQLite database.
The run result exposes an annual summary only; the normal run screen does not
render all 17,520 records.

## Causal-comparison eligibility

Every completed run writes `comparison-eligibility.json`.  It fingerprints the
real and forecast demand chronologies, initial fleet and SOC, weather and
availability inputs, module graph, storage/bidding parameters, random seed and
years.  A controlled copperplate/zonal comparison is eligible only when these
identities match and the permitted difference is limited to balancing/network
selection.  Mismatches remain viewable side by side but block isolated
network-cost attribution.

The absolute-demand mode always carries this label:

> Independent zonal-demand study. National demand is supplied by the network
> pack. Network-cost attribution against a scenario-demand copperplate run is
> disabled.

## User interface and documentation

The zonal Study composer shows the two demand modes only when zonal balancing is
selected.  Basic mode uses the explicit scenario-scaled choice.  Advanced mode
allows absolute network demand and shows the comparison warning before save.
The Network & redispatch evidence view reports the resolved mode, national
source, spatial-weight source and annual scaling summary.

The English and bilingual README material must state that the current UK pack
uses fixed 2024 DESNZ spatial weights, does not model endogenous regional demand
migration, and can be replaced by a conforming time-varying zonal-demand pack.

## Prompt 104 gate

After implementation, rerun draft/preflight tests and deterministic real smokes
for the matched copperplate and scaled-zonal Studies.  Only if both smokes and
their comparison eligibility pass may the full 17,520-period annual pair run.
The two-year chains remain gated on both annual runs completing with all physics,
accounting and input-identity audits inside tolerance.
