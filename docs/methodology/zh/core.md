# 运行与年度反馈

VALUE 将半小时调度与年度投资连接起来。到期项目在年初进入运行资产组合，全年运行收入用于年末扩建与退役决策。本章说明分段调度、储能报价、投资及系统核算；第 5 章介绍默认全国 PSM，第 6 章介绍实验性全国路径的年度账户。

## 模型时钟与年度状态

模型年采用 UTC 时钟，包含 365 天、17,520 个半小时时段。`period_start_utc` 将从零开始的 `period` 分解为日序号 `day_index` 和日内序号 `offset`，再将 `offset×period_hours` 小时加到 `model_day` 给出的日期上。`period_hours=0.5` 时，计算为：

$$
\mathtt{day\_index}=\left\lfloor\frac{\mathtt{period}}{48}\right\rfloor,\qquad\mathtt{offset}=\mathtt{period}\bmod48.
$$

`model_day` 跳过 2 月 29 日。源数据在调度前对齐到这一时钟，声明为 Europe/London 的记录逐行转换为 UTC。输出时间戳采用带 `Z` 的 ISO 8601 格式。时段电量以 MWh 计，额定功率以 MW 计，库存以 MWh 计。以下公式和伪代码沿用对应函数及字段中的名称。

年度状态保存运行资产、待投运项目、储能定价观察值及累计财务量。年度编排器先通过 `planning.advance_year` 投运到期项目，再由 `psm_input_factory` 组装需求与可用率，调用 `psm.run` 得到调度和收入。各扩容政策随后计算年度容量限额，`investment.decide` 形成投资决策，`planning.admit_projects` 应用成功率模式，`transition.apply` 构造下一年状态。

年度主要调用沿用同一组数据对象。转移前，`transition_state` 保存运行资产、剩余在建项目、累计指标及年度观察值：

```text
advanced = planning.advance_year(run, state)
model_input = psm_input_factory(run, advanced.operating_state)
market = psm.run(model_input)
headroom = []
for slot in sorted(expansion_policies):
    policy = expansion_policies[slot]
    headroom.append(policy.evaluate(run, advanced.operating_state, market))
investment_market = adapt_market_for_investment(
    market, advanced.operating_state)
decision = investment.decide(
    run, advanced.operating_state, investment_market, tuple(headroom))
admission = planning.admit_projects(
    run, advanced.operating_state, decision.proposals)
next_state = transition.apply(run, transition_state, admission, decision)
```

研究期末按所选设置处理。`report_only` 保留最终状态，`pipeline_tail` 推进已有在建项目，`full_extension` 继续年度运行与投资。

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

下调结算按接纳的减发电量与报价乘积退回款项。因此，上调的有符号调整量 `delta` 为正，下调的 `delta` 为负，两者均采用 `cashflow=delta×price_gbp_per_mwh`。修正口径的分段与网络路径采用 `network-economic-v2` 生成报价。

火电下调将提前计划分成运行区间与最小稳定出力区间。`thermal_dec_segments` 取 `shutdown_mwh=min_stable_fraction×scheduled_mwh`，其余电量记为 `running_mwh`。运行区间报价为应用下调乘数后、扣除政策支持的可避免边际成本；停机区间再扣除按预计停机时长分摊的重启费用。在 `RestartParameters.net_saving` 中，`avoided_cost` 的单位为 GBP/MWh，`restart_cost(horizon_h)` 为每次启动的 GBP/MW，`horizon_h` 以小时计：

$$
\begin{aligned}\mathtt{net\_saving}(\mathtt{avoided\_cost},\mathtt{horizon\_h})\\=\mathtt{avoided\_cost}-\frac{\mathtt{restart\_cost}(\mathtt{horizon\_h})}{\mathtt{min\_stable\_fraction}\times \mathtt{horizon\_h}}.\end{aligned}
$$

`shutdown_horizon_hours` 统计当前时段及其后预测需求可由声明风光与核电可用电量覆盖的连续时段，返回 `(1+run_after[period])×period_hours`。预计时长小于 `min_down_time_h` 时，`last_resort_price` 将停机报价置于普通下调报价的最低舍入价格以下至少 0.01 GBP/MWh；达到最短停机时长时，报价取停机净节省。普通报价集合为空时也采用净节省价格。

CCGT 的最小稳定出力比例为 0.50，最短停机时间为 6 h，热、温、冷启动费用分别为 113.7、134.4、155.0 GBP/MW。OCGT 对应值为 0.50、0.5 h、175.7 GBP/MW，生物质对应值为 0.35、6 h、129.2 GBP/MW。CCGT 在停机少于 12 h 时采用热启动，12 至 48 h 采用温启动，超过 48 h 采用冷启动。费用均以 2025 年英镑计。运行区间先于本机组的停机区间下调；停机净节省为正时，停机区间先于无支持的风电下调，价格相同时风电先下调。

其他下调价格由 `resource_dec_price` 给出。进口取 `marginal×dec_multiplier`；风电、光伏及径流水电取 `−support`；核电取 `marginal×dec_multiplier−support−premium`；其他燃料资源取 `marginal×dec_multiplier−support`。`market.dec_multiplier` 默认值为 1，上限为 `market.bid_multiplier`。未列出的政策支持为零，核电默认溢价为 100 GBP/MWh。储能采用 `storage_dec_price`，上限受其上调报价乘充放电效率以及当期最低上调报价共同约束。

铜板平衡按价格从低到高排列上调报价，同价时发电先于储能，VoLL 以上的报价留在接纳集合之外。下调按保留两位小数的价格从高到低排序，再依次按类别和精确价格排序。类别顺序为燃料机组运行区间、进口、储能、径流水电、风光、火电停机、核电、短停机时长区间。同方向、同类别、同价格报价按可用电量比例分配接纳量。

对每个同价组，`total` 为可用 MWh，`fraction` 取待平衡电量与可用电量之比及 1 的较小值。由此得到的 `delta` 更新 `final_dispatch`，并产生 `cashflow`。正的剩余需求记为 `blackout_mwh`，最终供应加停电量与实际需求的差额须在 10⁻⁸ MWh 内。分区平衡在第 7 章网络约束内采用相同计划与报价定义，先按精确价格优化，再处理物理同价选择。

以 50 MWh 预测需求说明两阶段结算。风电按 £0/MWh 报价 30 MWh，燃气按 £60/MWh 报价 30 MWh。提前计划接纳风电 30 MWh、燃气 20 MWh，按统一的 £60/MWh 支付 £3,000。实际需求为 55 MWh 时，燃气再发 5 MWh，获得 £300 平衡收入；其物理支出按最终 25 MWh 计算，为 £1,500。

## 储能库存与报价

储能库存随每期最终净注入更新。在 `CopperplateBalancing.clear` 中，`opening` 是初始储能侧 MWh，`dispatch` 是最终向电网输出的 MWh，负值表示充电。更新后的 `soc` 为：

$$
\mathtt{soc}=\begin{cases}\mathtt{opening}-\mathtt{dispatch}/\mathtt{discharge\_efficiency},&\mathtt{dispatch}\ge0,\\\mathtt{opening}-\mathtt{dispatch}\times \mathtt{charge\_efficiency},&\mathtt{dispatch}<0.\end{cases}
$$

库存范围为零至 `energy_capacity_mwh`，舍入容差为 10⁻⁸ MWh。分区调度分别表示充电与放电，每期至多一个方向超过 10⁻⁸ MWh。每年按 `initial_soc_mwh` 开始：`canonical_psm_data.py` 为普通输入赋予一半库容，为指定研究输入对齐赋予零库存。分段库存逐时段继承，下一年初始库存由年度输入确定。储能定价观察值跨年继承；第 6 章给出实验性带日期批次的状态转移。

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

参考年销量采用按寿命平均的年循环次数与可实现充放电次数中的较小值。`_reference_observation` 计算年循环次数 `cycles_per_year`、以 MWh 计的年度交付销量 `sold`，以及以模型时段数计的参考持有时间 `dwell_periods`：

```python
cycles_per_year = min(
    spec.maximum_cycles / spec.economic_lifetime_years,
    8760 / (2 * spec.duration_hours)
)
sold = energy_capacity_mwh * discharge_efficiency * cycles_per_year
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

循环公式适用于 `has_cycle_depreciation` 为真且两个分母项均为正的情形，其余情形循环折旧取零。`weighted_basis` 为零时，持有回收取零。`bid_price_gbp_per_mwh(dwell_periods)` 将循环折旧与非负持有时长乘持有回收率相加。修正口径的默认 PSM 使用仅含循环项的报价：电池报价为 `cycle_depreciation_gbp_per_mwh`，抽水蓄能与氢储能报价为零，并优先释放最早存入的库存批次。

分段调用传入 `dwell_periods=0`，售电批次年龄也记为零，其报告中的年龄来源为 `not_tracked_staged_single_pool`，因此动态报价的持有项为零。一般持有回收量仍可用于投资成本回收诊断。固定收费方案采用 `storage_fee_gbp_per_mwh+dwell_periods×holding_fee_gbp_per_mwh_period`；论文复现口径使用其旧费率配置。

以 2025 年 GBP/kW/年计，目录固定维护费率分别为：抽水蓄能 13.4，1C、0.5C、0.25C 电池各 6.6，氢储能 19.7。抽水蓄能目录建设成本为 360,000 GBP/MW。这些固定费用进入年度报价成本回收；系统成本账户将风电、光伏及储能固定运营费单独记为备忘项目。

## 储能扩建上限

修正口径的储能扩建采用现有储能充电后的剩余电量。`corrected_storage_headroom` 从 `storage_headroom_inputs` 读取 `leftover_excess_mwh`，从各时段摘要读取 `vre_accepted_mwh`、`real_demand_mwh` 与 `storage_discharge_mwh`。这些字段依次形成以时段 MWh 计的数组 `leftover`、`vre`、`demand` 与 `discharge`。剩余电量形成 `excess`，接纳风光与现有储能放电之后的需求缺口形成 `deficit`：

$$
\begin{aligned}\mathtt{excess}&=\max(\mathtt{leftover},0),\\\mathtt{deficit}&=\max(\mathtt{demand}-\mathtt{vre}-\mathtt{discharge},0).\end{aligned}
$$

虚拟储能从空库开始，取 `power_mw=10⁹` MW、`energy_cap_mwh=10⁹` MWh，充电效率 `rte=0.98`，放电效率为 1。`_simulate_virtual_pool` 每期先充电再放电。以下更新中，`exc` 与 `dfc` 为当期剩余电量和缺口，`max_period_mwh=power_mw×PERIOD_HOURS`：

```text
ch = min(exc, max_period_mwh, (energy_cap_mwh - soc) / rte)
soc += ch * rte
dis = min(dfc, max_period_mwh, soc)
soc -= dis
charge[t] = ch
discharge[t] = dis
```

`aligned_max_mw` 求充电与放电都能达到至少 `min_hours` 使用时长的最大共同功率。`hours_above_power(power_mw,p_mw)` 统计严格超过试探功率的时段数，再乘 0.5 h。搜索在零与充放电峰值中的较小值之间进行 64 次二分；目标时长无法达到时返回零，目标时长非正时返回该峰值。

`aligned_utilisation_spectrum` 分别按 730、365、52、0 小时计算，得到 `mw_730`、`mw_365`、`mw_52` 与 `mw_0`，相邻 MW 区间为：

$$
\begin{aligned}\mathtt{daily}&=\mathtt{mw\_730},\\\mathtt{interday}&=\max(\mathtt{mw\_365}-\mathtt{mw\_730},0),\\\mathtt{weekly}&=\max(\mathtt{mw\_52}-\mathtt{mw\_365},0),\\\mathtt{seasonal}&=\max(\mathtt{mw\_0}-\mathtt{mw\_52},0).\end{aligned}
$$

三类电池各自获得 `power_cap=cap_fraction×power_room`，其中 `power_room=daily+intraday`，`cap_fraction` 默认取 0.20。氢储能取 `hydrogen_cap=cap_fraction×seasonal`。因此，1C、0.5C、0.25C 各有一份相同功率空间的 0.20 配额；同一技术的投资主体按稳定顺序消耗该技术剩余额度。报价与投资收益另行计算。

这一计算要求完整的 17,520 个半小时时段及充电后剩余电量序列。部分年份以 `partial_year_chronology` 返回零，缺少序列时以 `leftover_trace_unavailable` 返回零。Native 调度提供该序列；分段调度、完全预见 LP、DC 调度及实验性全国路径在这些检查下取得零修正储能扩容空间。论文复现口径采用接纳风光减需求形成剩余电量，该 PSM 接纳风光受需求约束，因此扩容空间为零。

## 年度投资

投资按投资主体、技术与地区合并资产。`adapt_market_for_investment` 先按运行 MW 比例将主体收入分配给资产，资产级收入直接进入账户。`SchemeCAgentInvestmentDefinition.decide` 将 `capacity_mw` 汇总为 `capacity`，收入汇总为 `income`，资产总建设成本汇总为 `replacement`，运行支出汇总为 `operational`。

火电运行支出为发电 MWh 乘发电、燃料、碳及单位时间成本之和，`agent_cashflow` 行提供 `generated_mwh`、`generation_cost_gbp_per_mwh`、`fuel_cost_gbp_per_mwh`、`carbon_cost_gbp_per_mwh` 和 `unit_time_cost_gbp_per_mwh`。这一投资规则对风电、光伏及储能的运行扣减取零。组内净收入 `net`、单位建设成本、`roi` 与回收期为：

$$
\begin{aligned}\mathtt{net}&=\mathtt{income}-\mathtt{operational},\\\mathtt{cost\_per\_mw}&=\mathtt{replacement}/\mathtt{capacity},\\\mathtt{roi}&=\mathtt{net}/\mathtt{replacement},\\\mathtt{payback}&=\begin{cases}\mathtt{replacement}/\mathtt{net},&\mathtt{net}>0,\\\infty,&\mathtt{net}\le0.\end{cases}\end{aligned}
$$

`income`、`operational`、`net` 和 `replacement` 以 GBP 计，`cost_per_mw` 以 GBP/MW 计，`roi` 为年收益率，`payback` 以年计。重置资本为零时 `roi` 取零。火电满足以下条件时将 `net` 置零，以吸收舍入差额：

$$
|\mathtt{net}|\le10^{-9}\max(|\mathtt{income}|,\mathtt{operational}).
$$

两个口径都采用这一净收入账户。`preferred` 取成员 `preferred_rate` 的最大值，`life` 取 `economic_lifetime_years` 的最小值，`target_payback` 取 `target_payback_years` 的最小值，默认分别为 0.08、25 年及组内寿命，零值也采用相同默认值。投资以起始年不变价 GBP 比较未折现的 `roi` 与 `preferred`、`payback` 与 `target_payback`。

净收入为负且单位建设成本为正的组按成员 MW 比例分配退役容量。盈利组在 `roi>preferred` 时取 `Invest_High`，否则在 `payback≤target_payback` 时取 `Invest_Profit`，其余取 `Do_Nothing`。两类投资均申请以利润除单位建设成本得到的容量。

$$
\begin{aligned}\mathtt{requested\_retirement}&=\min\left(\mathtt{capacity},\frac{|\mathtt{net}|\times \mathtt{target\_payback}}{\mathtt{cost\_per\_mw}}\right),\\\mathtt{requested}&=\mathtt{net}/\mathtt{cost\_per\_mw},\\\mathtt{addition}&=\min(\max(\mathtt{requested},0),\max(\mathtt{allowed},0)).\end{aligned}
$$

风电、光伏、三类电池与氢储能的 `allowed` 为技术剩余额度，多项政策同时生效时取最小值。CCGT、OCGT、燃气与生物质按无上限资格规则将申请量作为 `allowed`。结算收入等于运行支出时，火电净收入为零，新增容量也为零。核电遵循外生建设计划，水电与抽水蓄能扩建要求场址和水文输入。

储能投资采用记录的提前与平衡收入，其中包含回购时保留的提前报酬。修正口径下，Native 调度按各阶段统一边际价结算储能；论文复现口径按储能自身最高接纳报价结算，接纳发电机集合为空的时段收入为零，具体规则见第 5 章。剩余电量充电免费，投资分子取扣除循环折旧和固定运营费之前的记录收入，`tier_roi` 保持未启用状态。

## 建设周期与规划成功率

内生投资按数据包的建设周期与地区成功率进入规划流程，两个方法学口径都采用这一规则。`native_initial_state` 通过 `freeze_planning_parameters` 将 `development_stage_timelines`、`repd_status_to_timeline`、`success_rates` 与 `timeline_statistic` 保存到 `state.extensions["planning_parameters"]`，年度状态继承这些冻结表。每项新增提案以 `technology`、`owner` 和 `decision_year` 调用 `endogenous_planning_terms`。

技术标签同时选择建设周期表与成功率表。光伏对应 Solar Photovoltaics，陆上风电对应 Wind Onshore，海上风电对应 Wind Offshore，普通电池类型及电解槽对应 Battery。燃气、CCGT、OCGT 与生物质采用 Wind Onshore，`hydrogen_battery` 按默认映射采用 Solar Photovoltaics。这些映射用于投资规划。

开发状态取 Application Submitted。`_timeline_months` 读取该状态对应的周期类型，通常为总开发期中位数；`planning.timeline_statistic=mean` 选择均值。缺少技术条目时采用光伏条目，缺少总周期均值时采用总周期中位数，所得 `months` 为非负月数。缺少光伏回退条目或成功率超出有效范围时，提案构造停止。

同一投资主体的项目时长扰动在各次运行中保持固定。`model_project_key(owner)` 形成 `Model Decision: <owner>`，`stable_int_hash` 将其 MD5 摘要前 64 位转换为整数，取模 13 后减 6，得到 −6 至 +6 个月的 `jitter`。`endogenous_planning_terms` 随后对周期取整，并将投运年下限设为决策年的下一年：

$$
\begin{aligned}\mathtt{rounded\_months}&=\operatorname{round}(\max(1,\mathtt{months}+\mathtt{jitter})),\\\mathtt{source\_completion}&=\mathtt{decision\_year}+\left\lfloor\frac{\mathtt{rounded\_months}}{12}\right\rfloor,\\\mathtt{completion}&=\max(\mathtt{source\_completion},\mathtt{decision\_year}+1).\end{aligned}
$$

取整采用 Python 的半偶数规则，因此 58.5 个月取为 58 个月。提案将 `completion` 保存为 `expected_completion_year`，并记录 `timeline_months`、`timeline_jitter_months`、`timeline_months_applied` 与 `completion_floor_applied`。新增储能继承组内能量功率比。

成功率先取技术标签与投资主体映射地区的条目，其次取该标签各地区的算术平均，再其次取 0.75。`source_success_region` 将光伏及陆上风电城市名称映射到所属地区，将含 offshore 的名称映射到 All Offshore，其余主体映射到 England。因此，表中缺少 England 条目时，电池与火电主体通常采用该技术的地区均值。提案记录 `success_probability=terms["success_rate"]`，并在 `success_rate_source` 中保存取值来源。城市映射为 Nottingham–East Midlands、Ipswich–Eastern、London–London、Newcastle–North East、Manchester–North West、Edinburgh–Scotland、Portsmouth–South East、Bournemouth–South West、Cardiff–Wales、Birmingham–West Midlands、Sheffield–Yorkshire and Humber。

`SchemeCPlanningPipelineDefinition.admit_projects` 将成功结果应用于提案。`expected_capacity` 模式取 `capacity=proposal.capacity_mw×probability`，能量容量、总建设成本与年度总费用均只乘一次该因子。`seeded_stochastic` 模式将 `seed:proposal_id` 的 SHA-256 计算前 52 位除以 2⁵²−1，得到 [0,1] 内的 `draw`；`probability` 为正且满足 `probability=1` 或 `draw<probability` 时按全容量准入。退役在下一年生效。

public2 表对应的 2025 年海上风电决策在 2033 或 2034 年投运，成功率约为 0.917；陆上风电在 2029–2030 年投运，地区成功率约为 0.22–0.71；光伏在 2026–2027 年投运，成功率约为 0.84–0.95；电池在 2027 年投运，成功率约为 0.873；火电在 2030 年投运，成功率约为 0.547。VALUE 101 的周期较短、成功率为 1，其 2025 年提案仍在 2026 年投运。

年度扩容空间由当年运行结果计算，每年以 `remaining_caps=dict(caps)` 开始投资，逐项扣减当年接纳的新增量。此前提案保留于规划流程中，因此多个年份的提案可能在相同扩容机会之上累积。

## 系统成本与排放

资源成本主项由在运资本年化费用、适用的固定运营费及物理运行支出组成。`build_cem_cost_ledger` 将年度资本总额读为 `capital`，物理运行成本读为 `operating`。`excluded` 在两个口径中均含风电、光伏及储能固定运营费，在修正口径中还包含径流水电存量兼容资本。`non_network_capital` 为扣除声明网络建设与固定运营费用后的机组资本，`operating_sum` 为核对后的物理运行总额。保留的核算量为：

```text
headline_fleet_capital = max(non_network_capital - excluded, 0)
headline_capital = capital - (non_network_capital - headline_fleet_capital)
system_cost = headline_capital + operating_sum
served = max(demand - blackout - a2_hidden_unserved_mwh(market), 0)
```

账本的 `cem_system_cost_gbp` 汇总保留资本与物理运行费用，`cem_system_cost_gbp_per_mwh_served` 再除以 `served`。模型将风电、光伏及储能固定运营费视为已包含在平准化建设成本中，因此将其列为备忘项；火电固定运营费保留于主项。径流水电兼容资本在修正口径中列为备忘项，在论文复现口径中计入主项。

Native 物理运行成本包括最终出力对应的发电、燃料、碳与时间成本、适用的运行启动项、按 VoLL 计价的记录停电量及储能循环损耗。用于下调排序的重启费用保留在报价计算中。修正口径的 VoLL 来自 `market.voll_gbp_per_mwh`，默认为 17,000 GBP/MWh；论文复现口径采用 17,000 GBP/MWh。`a2_hidden_unserved_mwh` 从已供需求扣除额外压力短缺，无压力时段的年份返回零。成本主项对记录停电量计价，额外压力短缺作为单独电量列示。

运行排放以发电 MWh 乘所选 kg/MWh 因子，再除以 1,000 换算为吨。`carbon_ledger.py` 将其汇总为 `operational`，与年化 `embodied` 排放相加形成 `total`，按 `overall_intensity=1000×total/delivered_demand_mwh` 报告强度，分母为已供需求。第 9 章列出因子数值及 CO₂ 或 CO₂e 口径，已供需求为零时强度留空。

年度隐含排放按因子声明的单位计算。`tCO2e_per_MW_year` 因子直接给出 `emissions=capacity_mw×factor.value`。以 `kgCO2e_per_kWh_capacity` 表示的电池因子在数值上等于每 MWh 容量的吨数，采用 `emissions=asset.energy_capacity_mwh×factor.value/economic_life`。氢储能功率设备采用年度 MW 因子，能量储存部件采用 `tCO2e_per_MWh_capacity` 因子并除以资产 `economic_life`。缺少因子输入的部件保留待评估状态。

储能碳追踪维护混合库存 `inventory_energy`，单位为 MWh，以及 `inventory_kg`，单位为千克。充电增加按效率折算的储能电量及来源碳量，放电按相同库存比例移除储能侧电量与碳量。系统总排放在来源发电环节核算。

网络约束成本采用资源价格、储能状态、出口范围及 VoLL 相同的分区与无网络调度对照，第 7 章定义资源成本差额和报价目标差额。结算转移、政策支出、建设承诺与残值分别核算。
