# 运行与储能

VALUE 按半小时时段计算需求与供应，发电、进口、出口及储能受各自物理容量约束。本章给出运行时钟、分阶段市场出清与储能成本计算。第 5 章说明全国 Native 调度算法，第 7 章加入网络约束，第 6 章将年度运行结果接入投资决策。

## 运行时钟与储能初始状态

模型年采用 UTC 时钟，包含 365 天、17,520 个半小时时段。`period_start_utc` 将从零开始的 `period` 分解为日序号 `day_index` 和日内序号 `offset`，再将 `offset×period_hours` 小时加到 `model_day` 给出的日期上。`period_hours=0.5` 时，计算为：

$$
\mathtt{day\_index}=\left\lfloor\frac{\mathtt{period}}{48}\right\rfloor,\qquad\mathtt{offset}=\mathtt{period}\bmod48.
$$

`model_day` 跳过 2 月 29 日。源数据在调度前对齐到这一时钟，声明为 Europe/London 的记录逐行转换为 UTC。输出时间戳采用带 `Z` 的 ISO 8601 格式。时段电量以 MWh 计，额定功率以 MW 计，库存以 MWh 计。

储能在每个模型年开始时具有规定的初始库存。Native 每年创建储能代理时将 `stored_energy` 设为空，第 5 章给出年内批次更新。分阶段、LP 与 DC 调度采用的逐时序输入取 `initial_soc_mwh=0.5×energy_capacity_mwh`。这些初值逐年应用；上一年的售电量与持有时间观察值保留，用于下一年的储能成本准备。

## 提前市场与平衡调度

分段 PSM 先满足预测需求，再针对实际需求进行平衡。对每个非储能 `resource`，`_ahead_offers` 读取当期可用率与边际成本。`availability` 为输入可用率与零的较大值；`physical_cost` 优先采用逐时段成本，其次采用恒定边际成本。`multiplier` 来自 `market.bid_multiplier`，默认值为 1。可报价电量与价格为：

$$
\begin{aligned}\mathtt{available\_mwh}&=\mathtt{resource.capacity\_mw}\times \mathtt{availability}\\&\quad\times\mathtt{model\_input.period\_hours},\\\mathtt{marginal\_cost}&=\mathtt{physical\_cost}\times \mathtt{multiplier}.\end{aligned}
$$

储能报价同时受放电功率和库存约束。`soc[resource.asset_id]` 为时段开始时的储能侧库存，`discharge_efficiency` 将其换算为输出电量：

```text
available_mwh = min(
    resource.discharge_power_mw * model_input.period_hours,
    soc[resource.asset_id] * resource.discharge_efficiency
)
```

`clear_ahead` 按 `price_gbp_per_mwh`、`offer_id` 依次排序报价。初始 `remaining=forecast_demand_mwh`，每次接纳剩余需求与报价电量中的较小值，再扣减剩余需求。最后接纳的报价成为 `clearing_price_gbp_per_mwh`，全部接纳电量按该价格结算。剩余需求达到 10⁻¹² MWh 时结束出清；接纳电量为零时，出清价为零，预测缺口记入 `unserved_forecast_mwh`。

$$
\mathtt{accepted}=\min(\mathtt{remaining},\mathtt{available}),\qquad\mathtt{remaining}\leftarrow\mathtt{remaining}-\mathtt{accepted}.
$$

平衡调度处理实际需求与提前计划之间的差额。在 `CopperplateBalancing.clear` 中，`final_dispatch` 初始取 `schedule_mwh_by_asset`，`gap_mwh=real_demand_mwh−sum(final_dispatch.values())`。发电与进口将剩余可用电量作为上调报价，将计划电量作为下调报价。储能下调先撤回计划放电，再按充电功率、剩余库容及效率吸收电量。出口以负注入进入其声明的接入位置与容量范围。

## 下调报价与结算

下调结算按接纳的减发电量与报价乘积退回款项。因此，上调的有符号调整量 `delta` 为正，下调的 `delta` 为负，两者均采用 `cashflow=delta×price_gbp_per_mwh`。分阶段与网络路径采用 `network-economic-v2` 生成报价。

火电下调将提前计划分成运行区间与最小稳定出力区间。`thermal_dec_segments` 取 `shutdown_mwh=min_stable_fraction×scheduled_mwh`，其余电量记为 `running_mwh`。运行区间报价为应用下调乘数后、扣除政策支持的可避免边际成本；停机区间再扣除按预计停机时长分摊的重启费用。在 `RestartParameters.net_saving` 中，`avoided_cost` 的单位为 GBP/MWh，`restart_cost(horizon_h)` 为每次启动的 GBP/MW，`horizon_h` 以小时计：

$$
\begin{aligned}\mathtt{net\_saving}(\mathtt{avoided\_cost},\mathtt{horizon\_h})\\=\mathtt{avoided\_cost}-\frac{\mathtt{restart\_cost}(\mathtt{horizon\_h})}{\mathtt{min\_stable\_fraction}\times \mathtt{horizon\_h}}.\end{aligned}
$$

`shutdown_horizon_hours` 统计当前时段及其后预测需求可由声明风光与核电可用电量覆盖的连续时段，返回 `(1+run_after[period])×period_hours`。预计时长小于 `min_down_time_h` 时，`last_resort_price` 将停机报价置于普通下调报价的最低舍入价格以下至少 0.01 GBP/MWh；达到最短停机时长时，报价取停机净节省。普通报价集合为空时也采用净节省价格。

CCGT 的最小稳定出力比例为 0.50，最短停机时间为 6 h，热、温、冷启动费用分别为 113.7、134.4、155.0 GBP/MW。OCGT 对应值为 0.50、0.5 h、175.7 GBP/MW，生物质对应值为 0.35、6 h、129.2 GBP/MW。CCGT 在停机少于 12 h 时采用热启动，12 至 48 h 采用温启动，超过 48 h 采用冷启动。费用均以 2025 年英镑计。运行区间先于本机组的停机区间下调；停机净节省为正时，停机区间先于无支持的风电下调，价格相同时风电先下调。

其他下调价格由 `resource_dec_price` 给出。进口取 `marginal×dec_multiplier`；风电、光伏及径流水电取 `−support`；核电取 `marginal×dec_multiplier−support−premium`；其他燃料资源取 `marginal×dec_multiplier−support`。`market.dec_multiplier` 默认值为 1，上限为 `market.bid_multiplier`。未列出的政策支持为零，核电默认溢价为 100 GBP/MWh。储能下调价值为其上调报价乘充放电效率。`storage_dec_price` 还以当期最低可用上调报价及自身上调报价限制该值；以下价格均以 GBP/MWh 计：

```text
value = up_price_gbp_per_mwh * charge_efficiency * discharge_efficiency
if lowest_inc_price_gbp_per_mwh is not None:
    value = min(value, lowest_inc_price_gbp_per_mwh)
value = min(value, up_price_gbp_per_mwh)
```

铜板平衡按价格从低到高排列上调报价，同价时发电先于储能，VoLL 以上的报价留在接纳集合之外。下调按舍入至 0.01 GBP/MWh 的价格从高到低排序，再依次按类别和精确价格排序。类别顺序为燃料机组运行区间、进口、储能、径流水电、风光、火电停机、核电、短停机时长区间。同方向、同类别、同价格报价按可用电量比例分配接纳量。

对每个同价组，`total` 为可用 MWh，`fraction` 取待平衡电量与可用电量之比及 1 的较小值。由此得到的 `delta` 更新 `final_dispatch`，并产生 `cashflow`。正的剩余需求记为 `blackout_mwh`，最终供应加停电量与实际需求的差额须在 10⁻⁸ MWh 内。分区平衡在第 7 章网络约束内采用相同计划与报价定义，先按精确价格优化，再处理物理同价选择。

以 50 MWh 预测需求说明两阶段结算。风电按 £0/MWh 报价 30 MWh，燃气按 £60/MWh 报价 30 MWh。提前计划接纳风电 30 MWh、燃气 20 MWh，按统一的 £60/MWh 支付 £3,000。实际需求为 55 MWh 时，燃气再发 5 MWh，获得 £300 平衡收入；其物理支出按最终 25 MWh 计算，为 £1,500。

## 储能库存与报价

储能库存随每期最终净注入更新。在 `CopperplateBalancing.clear` 中，`opening` 是初始储能侧 MWh，`dispatch` 是最终向电网输出的 MWh，负值表示充电。更新后的 `soc` 为：

$$
\mathtt{soc}=\begin{cases}\mathtt{opening}-\mathtt{dispatch}/\mathtt{discharge\_efficiency},&\mathtt{dispatch}\ge0,\\\mathtt{opening}-\mathtt{dispatch}\times \mathtt{charge\_efficiency},&\mathtt{dispatch}<0.\end{cases}
$$

库存范围为零至 `energy_capacity_mwh`，舍入容差为 10⁻⁸ MWh。充电与放电分别受 `charge_power_mw×period_hours` 和 `discharge_power_mw×period_hours` 限制。分区调度将两个方向分别表示，每期至多一个方向超过 10⁻⁸ MWh。期末库存成为下一期的 `opening`，每年的初始库存按上文设定。

`DynamicAnnualStorageCost` 将设备成本回收分为循环折旧与持有回收。`capital_recovery_factor` 接收 `discount_rate` 与 `lifetime_years`；折现率非正时返回寿命的倒数，正折现率时采用：

$$
\begin{aligned}\mathtt{growth}&=(1+\mathtt{discount\_rate})^{\mathtt{lifetime\_years}},\\\mathtt{capital\_recovery\_factor}&=\frac{\mathtt{discount\_rate}\times \mathtt{growth}}{\mathtt{growth}-1}.\end{aligned}
$$

年度成本为资产年化建设费用与固定维护费之和。`prepare_year` 接收资产实际的 `capital_cost_gbp`、`power_capacity_mw`、`energy_capacity_mwh` 和 `discharge_efficiency`，`spec` 提供目录寿命、时长、循环寿命与固定维护费率。计算保留资产声明的能量功率比。

```text
capex = max(capital_cost_gbp, 0)
annualized_capital_cost_gbp = capex * capital_recovery_factor(
    discount_rate, spec.economic_lifetime_years)
annual_fixed_opex_gbp = (
    max(power_capacity_mw, 0) * 1000 * spec.fixed_opex_gbp_per_kw_year)
annual_levelized_project_cost_gbp = (
    annualized_capital_cost_gbp + annual_fixed_opex_gbp)
```

参考年销量采用按寿命平均的年循环次数与可实现充放电次数中的较小值。`_reference_observation` 分别按循环寿命与充放电时长计算 `life_cycles_per_year` 和 `physical_cycles_per_year`，取其较小值为 `cycles_per_year`，再计算以 MWh 计的年度交付销量 `sold` 及以模型时段数计的持有时间 `dwell_periods`：

```text
life_cycles_per_year = spec.maximum_cycles / spec.economic_lifetime_years
physical_cycles_per_year = 8760 / max(2 * spec.duration_hours, 1e-9)
cycles_per_year = min(life_cycles_per_year, physical_cycles_per_year)
sold = (max(energy_capacity_mwh, 0) * max(discharge_efficiency, 0)
        * cycles_per_year)
dwell_periods = max(spec.duration_hours / period_hours, 2)
```

定价基准优先采用为正的上一年销量，并以参考销量的一定比例作为下限。`reference` 是 `_reference_observation` 返回的观察值，将 `sold` 保存为 `sold_energy_mwh`，将参考持有时间保存为 `average_dwell_periods`；`previous` 保存上一年观察值。选出的 `basis_sold` 以 MWh 计，`average_dwell` 为输出 MWh 加权的持有时段数：

```text
observed = previous
minimum_sold = reference.sold_energy_mwh * max(utilisation_floor, 0)
if observed.sold_energy_mwh > 0:
    basis_sold = max(observed.sold_energy_mwh, minimum_sold)
    average_dwell = max(observed.average_dwell_periods, 2)
else:
    basis_sold = reference.sold_energy_mwh
    average_dwell = reference.average_dwell_periods
```

默认 `utilisation_floor=0`、`discount_rate=0.05`。电池按输出 MWh 回收循环折旧，抽水蓄能和氢储能的循环折旧分量为零。

```text
usable_cycle_output = energy_capacity_mwh * discharge_efficiency
cycle_depreciation_gbp_per_mwh = (
    capex / (usable_cycle_output * spec.maximum_cycles))
expected_cycle_recovery = cycle_depreciation_gbp_per_mwh * basis_sold
remaining_annual_recovery = max(
    annual_levelized_project_cost_gbp - expected_cycle_recovery, 0)
weighted_basis = basis_sold * max(average_dwell, 1)
holding_recovery_gbp_per_mwh_period = (
    remaining_annual_recovery / weighted_basis)
```

当 `has_cycle_depreciation` 为假或分母任一因子为零时，循环折旧项为零；当 `weighted_basis=0` 时，持有回收项为零。Native 采用 `cycle_only` 报价设定，`bid_price_gbp_per_mwh` 返回 `cycle_depreciation_gbp_per_mwh`：三类电池按循环损耗报价，抽水蓄能与氢储能报价为零。同价储能批次按充电顺序释放，最早存入者先放电。

储能成本计算同时给出每个持有时段的回收率。线性持有报价为 `cycle_depreciation_gbp_per_mwh + max(dwell_periods,0)×holding_recovery_gbp_per_mwh_period`。分阶段调度传入 `dwell_periods=0`，相应持有报价项为零。目录提供第 2 章所列寿命、循环与维护参数；固定维护费为抽水蓄能 13.4 GBP/kW/年、三类电池 6.6 GBP/kW/年、氢储能 19.7 GBP/kW/年。

售电记录形成下一年的成本计算基础。`record_sale` 接收交付电量及从充电到放电经过的时段数，在 `current` 中累计售电量与售电量加权持有时间。销量为正时，`average_dwell_periods` 等于加权总量除以销量；销量为零时取零：

```text
delivered = max(delivered_mwh, 0)
dwell = max(dwell_periods, 0)
current.sold_energy_mwh += delivered
current.dwell_weighted_sold_mwh_periods += delivered * dwell
```

年末，`storage_cost_observations` 按储能代理保存这些量。下一年度准备将其作为 `previous`，计算新的成本回收量，并将 `current` 清零。观察值用于成本计算，物理库存按上文初值与调度递推更新。
