# Prompt 66 — Run-of-river and reservoir hydrology extension

Execute after Prompt 65. Read the current hydro model card, UK-data provenance,
existing-stock/new-build CAPEX boundary, storage catalogue and pumped-hydro
implementation. Act as a hydropower modeller, data engineer and independent
validator. Do not change or duplicate pumped storage.

## Objective

Provide a typed optional hydrology extension for:

- run-of-river generation constrained by exogenous natural inflow/availability;
- conventional reservoir hydro with chronological water balance and finite
  storage; and
- explicit mapping between hydrological sites and electrical assets.

Keep the current UK natural-flow treatment available as a named compatibility
scenario until an authoritative site/time-series mapping is installed. Do not
silently call a constant or generic availability series measured river inflow.

## Domain separation

- Pumped hydro remains in the storage technology catalogue with charging,
  discharge and round-trip losses. It is not a reservoir-inflow technology and
  receives no duplicate water pool or new investment path here.
- Run-of-river has no discretionary intertemporal reservoir unless a declared
  small pondage capability is selected.
- Reservoir hydro has natural inflow, release, spill and stored water. Pumping is
  absent unless a future explicitly combined technology is modelled.
- Existing UK assets remain operating stock. New hydro investment still requires
  site, hydrology, environmental/development evidence and sourced new-build
  CAPEX; this prompt does not create generic greenfield hydro potential.

## Data and contracts

Add conditional roles owned by the Prompt 65 extension, for example:

- `hydrology.site_catalogue`: stable site IDs, technology class, region/bus,
  head or conversion metadata, environmental flow and source provenance;
- `hydrology.asset_site_map`: generator ID to hydrological site and share;
- `hydrology.run_of_river_inflow`: timestamped usable inflow or normalized
  availability with units and conversion method;
- `hydrology.reservoir_inflow`: timestamped natural inflow by site;
- `hydrology.reservoir_parameters`: minimum/maximum volume, initial/terminal
  condition, turbine capacity/efficiency, spill and release limits.

Require calendar, timezone, interval, missing-data, unit, sign and leap-year
semantics. Adapters may support CSV/Parquet/NetCDF, but all must produce one
canonical typed series. Record raw object hashes, adapter version, transformations,
imputation and licence. Fail closed on unmapped assets, impossible units,
duplicate timestamps or insufficient chronology.

## Scientific implementation

1. For run-of-river, derive period maximum electrical energy from canonical
   inflow/availability, capacity, interval and conversion efficiency. Dispatch
   may accept or curtail this energy but cannot shift it across periods.
2. For reservoir hydro, implement the explicit water balance:
   previous storage + natural inflow = release + spill + next storage, with
   volume, turbine, release, environmental-flow and terminal constraints.
   Keep water units and MWh conversion visible and tested.
3. Declare whether dispatch is myopic, rolling-horizon or perfect foresight.
   A module may not use future inflow unless its information structure says so.
4. Publish available energy, accepted generation, curtailment/spill and reservoir
   state as typed artifacts compatible with the existing market ledger, cost and
   carbon ledgers. Never count spill as electrical curtailment without a separate
   named mapping.
5. Route all behavior through the selected PSM capability graph. No hidden
   preprocessing script may modify generator availability outside the snapshot.

## Validation

- Analytical run-of-river fixtures: zero inflow, constant inflow, capacity cap,
  curtailment and missing period.
- Reservoir fixtures: drought, flood/spill, binding minimum flow, empty/full
  bounds, conversion loss and terminal target. Every water balance must close.
- Compare an independent chronological LP with any optimizing reservoir module
  over deterministic 24-hour and 168-hour cases.
- Mutation tests remove inflow, break units, violate volume, double-map a site and
  substitute pumped-hydro data; each must fail for the expected reason.
- Prove that the existing single-node UK Study is unchanged when the extension is
  absent. If the default UK Study is changed to use real hydrology, require source
  audit, full annual and causal two-year tests; otherwise no long run is needed.

## Stop conditions

Do not fabricate UK inflow, infer reservoir volume from power capacity, convert
pumped storage into reservoir hydro, or enable new-build hydro without site and
cost evidence. If authoritative temporal data or asset mapping is unavailable,
ship the extension and synthetic fixtures with the UK path `NOT_EVALUATED`.

## Deliverables

- hydrology extension bundle and conditional canonical data contracts;
- run-of-river and reservoir implementations with explicit information structure;
- provenance-aware adapters and synthetic reference data;
- water/energy balance, independent-LP and mutation evidence;
- updated model card, data guide and human/machine Prompt 66 report.
