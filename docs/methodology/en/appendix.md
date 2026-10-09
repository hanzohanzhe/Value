# Carbon accounting parameters

VALUE calculates operational emissions and equipment-construction emissions separately before combining them under the selected accounting scenario. Operational emissions vary with generation and imported electricity, while construction emissions vary with installed capacity and the annualisation rule. Current physical accounting uses the `value_current_authoritative_v1` factor set. The doctoral-reproduction reference configuration selects `doctoral_reproduction_2026_07_18`, retaining historical storage scalars in their original units and recording the carbon result as `not_physically_interpretable`.

## Generation and imported electricity

Operational emissions multiply generated or imported electricity by its selected factor. In `build_operational_carbon_ledger`, `activity` is the MWh read from `generation_mwh_by_asset` for each `asset_id`; `kg` is the factor converted to kg/MWh. Each `emissions_tco2e` entry records the resulting tonnes, and `operational` sums these entries:

$$
\begin{aligned}
\mathtt{emissions\_tco2e}_{\mathtt{asset\_id}}
&=\frac{\mathtt{activity}_{\mathtt{asset\_id}}\times
\mathtt{kg}_{\mathtt{asset\_id}}}{1000},\\
\mathtt{operational}&=\sum_{\mathtt{asset\_id}}\mathtt{emissions\_tco2e}_{\mathtt{asset\_id}}.
\end{aligned}
$$

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

Construction emissions are annualised for each operating asset. In `_asset_embodied_lines`, `capacity_mw` is operating power in MW and `factor.value` is its selected annual factor in tCO₂e/(MW·year). The per-asset value `emissions` becomes `line.emissions_tco2e`; `embodied` sums the construction entries:

$$
\begin{aligned}
\mathtt{emissions}&=\mathtt{capacity\_mw}\times\mathtt{factor.value},\\
\mathtt{embodied}&=\sum\mathtt{line.emissions\_tco2e}.
\end{aligned}
$$

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

Battery manufacturing emissions are annualised by rated energy capacity and equipment life. The selected factor is 89 kgCO₂e/kWh of capacity, the midpoint applied in the Longfield Solar Farm environmental statement of 2022. `_asset_embodied_lines` reads `asset.energy_capacity_mwh` in MWh and `economic_life` in years from `economic_lifetime_years`. Annual manufacturing emissions are

$$
\mathtt{emissions}
=\frac{89\times\mathtt{asset.energy\_capacity\_mwh}}
{\mathtt{economic\_life}}
\quad\mathrm{tCO_2e/year}.
$$

Hydrogen storage accounts separately for power equipment and energy storage. The energy-storage component uses a lifetime factor of 0.0006 tCO₂e/MWh of capacity, annualised over the asset's declared economic life. It is stored as `ch4_h2_store_lifetime` in `factor_catalog.csv`, with the original thesis Chapter 4 storage parameters and their 10-year source lifetime retained in the factor record. The electrolyser power component uses the annual factor in the preceding section.

## Data and implementation

`factor_catalog.csv` stores the factors, units, accounting boundaries and source locations, while `sources.csv` stores source names. `CarbonFactorDatabase` reads `value_carbon_factors.sqlite`. `build_operational_carbon_ledger` connects dispatched electricity and operating assets to the selected factor set, and `_asset_embodied_lines` calculates annualised equipment-construction emissions.
