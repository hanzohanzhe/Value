# 碳排放核算参数

VALUE 将运行排放和设备建设排放分别计算，再按所选核算情景汇总。运行排放随实际发电量和进口电量变化，建设排放随在役设备容量及年化规则变化。因子集由 `value_current_authoritative_v1` 指定。

## 发电与进口电力

运行排放按发电或进口电量乘以所选因子计算。在 `build_operational_carbon_ledger` 中，`activity` 是从 `generation_mwh_by_asset` 读取的各 `asset_id` 电量，单位为 MWh；`kg` 是换算为 kg/MWh 的因子。各条 `emissions_tco2e` 记录排放吨数，`operational` 汇总这些记录：

$$
\begin{aligned}
\mathtt{emissions\_tco2e}_{\mathtt{asset\_id}}
&=\frac{\mathtt{activity}_{\mathtt{asset\_id}}\times
\mathtt{kg}_{\mathtt{asset\_id}}}{1000},\\
\mathtt{operational}&=\sum_{\mathtt{asset\_id}}\mathtt{emissions\_tco2e}_{\mathtt{asset\_id}}.
\end{aligned}
$$

结果单位为吨，气体范围随所用因子的 CO₂ 或 CO₂e 定义保留。表中的零值对应发电环节的直接运行边界，设备建设排放通过下一节按容量计量的排放因子计算。进口因子采用固定的国家均值或备用值。

|发电技术或进口来源|因子 kg/MWh|气体口径|数据依据|
|---|---|---|---|
|联合循环燃气|394|CO₂|NESO 2024 年区域碳强度方法|
|开式循环燃气|651|CO₂|NESO 2024 年区域碳强度方法|
|生物质|120|CO₂e|NESO 2024 年区域碳强度方法|
|风电 光伏 核电 天然水电 抽水蓄能|0|CO₂|NESO 发电环节边界|
|法国进口|53|CO₂|NESO 固定备用因子|
|荷兰进口|474|CO₂|NESO 固定备用因子|
|比利时进口|179|CO₂|NESO 固定备用因子|
|爱尔兰进口|458|CO₂|NESO 固定备用因子|
|挪威进口|11.9|CO₂e|NVE 2024 年实物供电年均值|

各因子统一为 kg/MWh，1 g/kWh 与 1 kg/MWh 数值相同。挪威原单位为 gCO₂e/kWh。

生物质计算采用表中固定因子 120 kgCO₂e/MWh，其原来源给出 ±120 gCO₂/kWh 的不确定范围。

## 按功率容量年化的建设排放

设备建造排放按各在役资产进行年度分摊。在 `_asset_embodied_lines` 中，`capacity_mw` 为在役功率，单位为 MW；`factor.value` 为所选年度因子，单位为 tCO₂e/(MW·年)。单项结果 `emissions` 写入 `line.emissions_tco2e`，`embodied` 汇总这些建造排放记录：

$$
\begin{aligned}
\mathtt{emissions}&=\mathtt{capacity\_mw}\times\mathtt{factor.value},\\
\mathtt{embodied}&=\sum\mathtt{line.emissions\_tco2e}.
\end{aligned}
$$

年度建设因子取自 `embodied_factors_desnz_unece.csv`。开式循环燃气使用联合循环燃气的建设因子，电解槽使用该表列出的代理值。

|技术|年度因子 tCO₂e/(MW·年)|
|---|---|
|光伏|38.544|
|陆上风电|47.304|
|海上风电|96.1848|
|核电|43.362|
|天然水电|61.32|
|抽水蓄能|98.55|
|联合循环燃气|16.2936|
|开式循环燃气|16.2936|
|生物质|22.0752|
|电解槽|1.25|

## 按能量容量计量的储能排放

电池制造排放按额定能量容量与设备寿命进行年度分摊。所选制造因子为 89 kgCO₂e/kWh 容量，来自 Longfield Solar Farm 2022 年环境声明所用的中间值。`_asset_embodied_lines` 读取以 MWh 表示的 `asset.energy_capacity_mwh`，并从 `economic_lifetime_years` 读取以年表示的 `economic_life`。年度制造排放为

$$
\mathtt{emissions}
=\frac{89\times\mathtt{asset.energy\_capacity\_mwh}}
{\mathtt{economic\_life}}
\quad\mathrm{tCO_2e/year}.
$$

氢储能将功率设备与能量储存部分分别计量。能量储存部分采用 0.0006 tCO₂e/MWh 容量的全寿命因子，按资产声明的经济寿命年化；该值对应 `factor_catalog.csv` 的 `ch4_h2_store_lifetime` 参数项。电解槽的功率部分采用上一节的年度因子。

## 储能电量的碳记录

电池放电作为已存电力的转移记入 `storage_carried_transfer`，该项新增运行排放取零。抽水蓄能按表中的零运行因子计量。充电电源的排放已计入发电或进口电量。提供 `storage_trace` 时，模型另行按混合库存法追踪储能中留存的排放；输入包含每期 `charge_mwh`、`discharge_mwh`、`charge_source_kgco2e_per_mwh` 及充放电效率。

库存碳从零开始，充电按电源强度增加库存碳，放电按取出的库存能量比例移出库存碳。以下计算中的 `inventory_energy` 以 MWh 表示，`inventory_kg` 以 kg 表示；期末 `ending_inventory` 换算为吨。每期检查取出量 `withdrawn` 与现有库存，超出量大于 \(10^{-7}\) MWh 时以 `ValueError` 终止计算。

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

氢储能的运行活动在当前账本中进入 `unresolved`。`_normalise_technology` 将 `hydrogen_battery` 转为 `hydrogen_storage`，该名称对应的运行因子为空；该活动使 `operational` 和 `total` 返回 `None`。氢储能设备建设部分仍按前述功率与能量容量因子计算。

## 年度排放与强度

年度排放 `total` 是运行排放 `operational` 与年化建设排放 `embodied` 之和。各活动具有匹配的排放因子、储能具有能量容量和正的经济寿命时，模型汇总这些分项。`delivered_demand_mwh` 是已供电量；其为正时，模型按以下分母计算 kg/MWh 强度：

$$
\begin{aligned}
\mathtt{total}&=\mathtt{operational}+\mathtt{embodied},\\
\mathtt{operational\_intensity}
&=\frac{1000\times\mathtt{operational}}{\mathtt{delivered\_demand\_mwh}},\\
\mathtt{overall\_intensity}
&=\frac{1000\times\mathtt{total}}{\mathtt{delivered\_demand\_mwh}}.
\end{aligned}
$$

## 线路扩建的建设排放

线路建设排放在投运年一次计入 `network_construction_embodied`，并加入该年的 `total`。`adjust_carbon_ledger_for_network` 选择 `commissioning_year == year` 且 `status == "commissioned"` 的网络资产。各资产的 `rating` 以 MW 表示，`factor` 读取以 tCO₂e/MW 表示的 `asset.embodied_carbon_factor_tco2e_per_mw`，`emissions` 以吨表示：

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

更新后的总排放用于 `overall_kgco2e_per_mwh` 和 `delivered_demand_kgco2e_per_mwh`，以正的已供电量 `denominator` 为分母。所选线路缺少排放因子时，其建设条目进入待求值状态，总排放返回 `None`。随附的固定 23 区网络保留其声明的线路；上述新增计算随可选线路扩建模块执行。

## 数据与实现对应

`factor_catalog.csv` 保存因子、单位、核算边界和来源定位，`sources.csv` 保存来源名称。`CarbonFactorDatabase` 读取 `value_carbon_factors.sqlite`，`build_operational_carbon_ledger` 将调度电量、在役资产与所选因子集连接，`_asset_embodied_lines` 计算设备的年化建设排放。
