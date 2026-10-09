# 碳排放核算参数

VALUE 将运行排放和设备建设排放分别计算，再按所选核算情景汇总。运行排放随实际发电量和进口电量变化，建设排放随在役设备容量及年化规则变化。当前物理核算使用 `value_current_authoritative_v1` 因子集；论文复现口径的参考配置选择 `doctoral_reproduction_2026_07_18`，其中历史储能标量按原始单位保留，碳结果记录为 `not_physically_interpretable`。

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

下表采用研究后处理输入 `embodied_factors_desnz_unece.csv` 中使用的年度因子。因子选择随研究配置固定，其中开式循环燃气沿用联合循环燃气的建设因子，电解槽使用该输入表的文献代理值。

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

氢储能将功率设备与能量储存部分分别计量。能量储存部分采用 0.0006 tCO₂e/MWh 容量的全寿命因子，按资产声明的经济寿命年化；该值对应 `factor_catalog.csv` 的 `ch4_h2_store_lifetime` 参数项，记录保留原论文第 4 章储能参数及其 10 年来源寿命。电解槽的功率部分采用上一节的年度因子。

## 数据与实现对应

`factor_catalog.csv` 保存因子、单位、核算边界和来源定位，`sources.csv` 保存来源名称。`CarbonFactorDatabase` 读取 `value_carbon_factors.sqlite`，`build_operational_carbon_ledger` 将调度电量、在役资产与所选因子集连接，`_asset_embodied_lines` 计算设备的年化建设排放。
