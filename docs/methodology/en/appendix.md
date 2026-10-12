# Carbon accounting parameters

VALUE calculates operational emissions and equipment-construction emissions separately before combining them under the selected accounting scenario. Operational emissions vary with generation and imported electricity, while construction emissions vary with installed capacity and the annualisation rule. The `value_current_authoritative_v1` factor set supplies the accounting factors.

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

Annual construction factors come from `embodied_factors_desnz_unece.csv`. Open-cycle gas uses the combined-cycle gas construction factor, and the electrolyser uses the proxy recorded in that table.

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

Hydrogen storage accounts separately for power equipment and energy storage. The energy-storage component uses a lifetime factor of 0.0006 tCO₂e/MWh of capacity, annualised over the asset's declared economic life. It is stored as `ch4_h2_store_lifetime` in `factor_catalog.csv`. The electrolyser power component uses the annual factor in the preceding section.

## Carbon carried by stored electricity

Battery discharge enters `storage_carried_transfer` as a transfer of stored electricity, with zero additional operational emissions. Pumped hydro uses the zero operational factor in the table. Emissions from the charging source enter the generation or imported-electricity account. When `storage_trace` is supplied, a mixed-inventory calculation also tracks the emissions held in storage. Its inputs are period `charge_mwh`, `discharge_mwh`, `charge_source_kgco2e_per_mwh` and charge and discharge efficiencies.

The carbon inventory starts at zero. Charging adds emissions at the source intensity; discharging removes the fraction associated with the withdrawn inventory energy. In the calculation below, `inventory_energy` is in MWh and `inventory_kg` in kg; `ending_inventory` converts the closing carbon inventory to tonnes. Each period checks `withdrawn` against available inventory; an excess above \(10^{-7}\) MWh terminates the calculation with `ValueError`.

```text
inventory_energy = 0.0
inventory_kg = 0.0
for charge, discharge, intensity in zip(
    storage_trace["charge_mwh"],
    storage_trace["discharge_mwh"],
    storage_trace["charge_source_kgco2e_per_mwh"]):
    admitted = charge * storage_trace["charge_efficiency"][0]
    inventory_energy += admitted
    inventory_kg += charge * intensity
    withdrawn = discharge / storage_trace["discharge_efficiency"][0]
    if withdrawn > inventory_energy + 1e-7:
        raise ValueError("Storage withdrawal exceeds available inventory")
    share = withdrawn / inventory_energy if inventory_energy > 0 else 0.0
    inventory_kg *= 1.0 - share
    inventory_energy -= withdrawn
ending_inventory = inventory_kg / 1000.0
```

Hydrogen-storage operation enters `unresolved` in the current ledger. `_normalise_technology` maps `hydrogen_battery` to `hydrogen_storage`, whose operational factor is empty; this activity makes `operational` and `total` return `None`. Hydrogen-storage construction emissions still use the power- and energy-capacity factors specified above.

## Annual emissions and intensity

Annual emissions `total` sum operational emissions `operational` and annualised construction emissions `embodied`. Aggregation requires a matching factor for each activity and energy capacity and a positive economic life for storage. `delivered_demand_mwh` is served electricity; a positive value supplies the denominator for the following kg/MWh intensities:

$$
\begin{aligned}
\mathtt{total}&=\mathtt{operational}+\mathtt{embodied},\\
\mathtt{operational\_intensity}
&=\frac{1000\times\mathtt{operational}}{\mathtt{delivered\_demand\_mwh}},\\
\mathtt{overall\_intensity}
&=\frac{1000\times\mathtt{total}}{\mathtt{delivered\_demand\_mwh}}.
\end{aligned}
$$

## Construction emissions from line expansion

Line construction enters `network_construction_embodied` once in the commissioning year and is added to that year's `total`. `adjust_carbon_ledger_for_network` selects network assets with `commissioning_year == year` and `status == "commissioned"`. For each selected asset, `rating` is MW, `factor` reads `asset.embodied_carbon_factor_tco2e_per_mw` in tCO₂e/MW, and `emissions` is tonnes:

$$
\begin{aligned}
\mathtt{rating}
&=\mathtt{asset.thermal\_rating\_mw\_per\_circuit}\\
&\qquad\times\mathtt{asset.circuits},\\
\mathtt{emissions}&=\mathtt{rating}\times\mathtt{factor},\\
\mathtt{network\_total}&=\sum\mathtt{emissions},\\
\mathtt{total}&\leftarrow\mathtt{total}+\mathtt{network\_total}.
\end{aligned}
$$

The updated total supplies `overall_kgco2e_per_mwh` and `delivered_demand_kgco2e_per_mwh`, using served electricity as `denominator` when it is positive. A selected line with a missing factor receives an unresolved construction entry and makes the total return `None`. The supplied fixed 23-zone network retains its declared branches; this additional calculation accompanies the optional line-expansion module.

## Data and implementation

`factor_catalog.csv` stores the factors, units, accounting boundaries and source locations, while `sources.csv` stores source names. `CarbonFactorDatabase` reads `value_carbon_factors.sqlite`. `build_operational_carbon_ledger` connects dispatched electricity and operating assets to the selected factor set, and `_asset_embodied_lines` calculates annualised equipment-construction emissions.
