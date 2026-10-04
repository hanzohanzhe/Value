# Carbon accounting parameters

VALUE calculates operational emissions and equipment-construction emissions separately before combining them under the selected accounting scenario. Operational emissions vary with generation and imported electricity, while construction emissions vary with installed capacity and the annualisation rule. Current physical accounting uses the `value_current_authoritative_v1` factor set. Historical R029 results use the factor set associated with that research configuration.

## Generation and imported electricity

Operational emissions are calculated by multiplying interval generation by the corresponding technology factor. Let \(Q_{a,t}\) denote the electricity supplied by technology or import source \(a\) in interval \(t\), in MWh, and let \(e_a\) denote its factor in kg/MWh. Annual operational emissions are

$$M_{op}=\frac{1}{1000}\sum_{a,t}Q_{a,t}e_a.$$

The result is in tonnes, retaining the CO₂ or CO₂e definition of the selected factor. Zero values in the table refer to the direct operational generation boundary. Equipment-construction emissions are calculated using the capacity-based emissions factors in the next section. Import factors use fixed national averages or fallback values.

|Generation technology or import source|Factor kg/MWh|Gas basis|Data basis|
|---|---|---|---|
|Combined-cycle gas|394|CO₂|NESO regional carbon-intensity methodology 2024|
|Open-cycle gas|651|CO₂|NESO regional carbon-intensity methodology 2024|
|Biomass|120|CO₂e|NESO regional carbon-intensity methodology 2024|
|Wind Solar Nuclear Conventional hydro Pumped hydro|0|CO₂|NESO generation boundary|
|Imports from France|53|CO₂|NESO fixed fallback factor|
|Imports from the Netherlands|474|CO₂|NESO fixed fallback factor|
|Imports from Belgium|179|CO₂|NESO fixed fallback factor|
|Imports from Ireland|458|CO₂|NESO fixed fallback factor|
|Imports from Norway|11.9|CO₂e|NVE annual mean for physical electricity delivery in 2024|

The source factors are converted to kg/MWh, with 1 g/kWh numerically equal to 1 kg/MWh. The original unit of Norway's factor is gCO₂e/kWh.

The biomass calculation uses the fixed factor of 120 kgCO₂e/MWh in the table. Its source reports an uncertainty range of ±120 gCO₂/kWh.

## Construction emissions annualised by power capacity

Construction emissions from generating equipment are annualised by operating power capacity. Let \(P_k\) denote the installed capacity of technology \(k\), in MW, and \(b_k\) its annual construction-emissions factor, in tCO₂e/(MW·year). Then

$$M_{build}=\sum_k P_k b_k.$$

The following annual factors are those used in the research postprocessing input `embodied_factors_desnz_unece.csv`. The study configuration fixes the factor selection. Open-cycle gas uses the combined-cycle gas construction factor, and the electrolyser uses the literature proxy recorded in that input table.

|Technology|Annual factor tCO₂e/(MW·year)|
|---|---|
|Solar|38.544|
|Onshore wind|47.304|
|Offshore wind|96.1848|
|Nuclear|43.362|
|Conventional hydro|61.32|
|Pumped hydro|98.55|
|Combined-cycle gas|16.2936|
|Open-cycle gas|16.2936|
|Biomass|22.0752|
|Electrolyser|1.25|

## Storage emissions measured by energy capacity

Battery manufacturing emissions are annualised by rated energy capacity and equipment life. The model uses a manufacturing factor of 89 kgCO₂e/kWh of capacity, the midpoint applied in the Longfield Solar Farm environmental statement of 2022. For capacity \(E\) in MWh and life \(L\) in years, annual manufacturing emissions are

$$M_{battery}=\frac{89E}{L}\quad\mathrm{tCO_2e/year}.$$

Hydrogen storage accounts separately for power equipment and energy storage. The energy-storage component uses a lifetime factor of 0.0006 tCO₂e/MWh of capacity, annualised over a 10-year life. It is stored as `ch4_h2_store_lifetime` in `factor_catalog.csv`, with the original thesis Chapter 4 storage parameters recorded as its source. The electrolyser power component uses the annual factor in the preceding section.

## Data and implementation

`factor_catalog.csv` stores the factors, units, accounting boundaries and source locations, while `sources.csv` stores source names. `CarbonFactorDatabase` reads `value_carbon_factors.sqlite`. `build_operational_carbon_ledger` connects dispatched electricity and operating assets to the selected factor set, and `_asset_embodied_lines` calculates annualised equipment-construction emissions.
