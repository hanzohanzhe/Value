# 年度核算与投资

VALUE 每个模型年更新一次在役容量。全年调度给出售电量、运行费用与可再生能源剩余电量，进而确定投资和退役。获准新增的容量进入建设队列，在完工年成为在役资产。年度计算由此连接当期机组、市场收入、建设时长与未来容量。

## 年度输入与计算顺序

年度输入 `YearState` 包含年份、在役资产、规划项目和储能成本观察值。各资产带有以 MW 表示的 `capacity_mw`，储能还带有以 MWh 表示的 `energy_capacity_mwh`，并记录技术、地区及投资主体。经济字段包括总资本 `total_capex_gbp`、年度固定费用 `annual_fixed_opex_gbp`、年化资本 `annualized_capital_cost_gbp`、寿命 `economic_lifetime_years`、要求的年度收益率 `preferred_rate` 和目标回收期 `target_payback_years`。第 2 章给出初始机组、项目清单与输入值。

项目在当年调度开始前投运。`SchemeCPlanningPipelineDefinition.advance_year` 将成功且满足 `expected_completion_year≤state.year` 的项目容量及经济字段加入在役机组，并从当前建设队列移除。后续完工的项目保留在队列中。水电项目在站点与水文输入齐备后投运，失败项目对在役容量的贡献为零。

调度产生年度 `MarketYearResult`，记为 `market`。逐期汇总包括实际需求、已接纳风光发电、储能充放电、停电电量和价格，资产账户包括发电 MWh 与市场收入。随后按下列顺序计算技术扩容上限、投资量、规划准入与下一年状态：

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
decision = inherit_frozen_zone_shares(decision, advanced.operating_state)
admission = planning.admit_projects(
    run, advanced.operating_state, decision.proposals)
```

其中 `advanced.operating_state` 为当年可用机组，`headroom` 为各技术允许增加的 MW，`decision` 包含新增提案与资产退役量，`admission.next_pipeline` 包含继续建设及新获准的项目。输入工厂按第 2—3 章处理更新后的机组，第 4—5、7—8 章定义所选调度计算。最终状态更新见本章末节。

## 资产资本与年度系统成本

资产资本按经济寿命通过资本回收因子年化。`build_asset_economic_extensions` 读取以 GBP 表示的 `total_capex`、以年表示的 `life` 及 `discount_rate`，并令 `annualized_capital_cost_gbp=total_capex×crf`。`crf=capital_recovery_factor(discount_rate,life)` 使用第 4 章公式，默认利率为 0.05。发电资本为容量乘以 GBP/MW 单位造价，储能资本与固定维护费按第 2 章技术目录声明的功率或能量计价基础计算。

年度系统成本汇总在役资产的资源费用。调度结果中的 `total_levelized_capital_cost_gbp` 包含年化资本与固定维护费，`total_operational_cost_gbp` 包含实际运行支出。Native 的实际运行支出由第 5 章发电与进口费用、停电电量乘以 `market.voll_gbp_per_mwh`（默认 17,000 GBP/MWh），以及储能循环折旧组成。用于下调排序的重启费用进入相应报价计算。选择网络扩建时，网络资产的资本与固定维护费进入年度资源账户。

系统成本将风电、光伏和储能的固定维护费视为已包含在其平准化资本中，单独记录的维护费保留为备忘项。已有径流式水电的 `existing_stock_compatibility_capital_gbp` 也列为备忘项。火电固定维护费与已投运网络的资源费用进入成本总额。

`build_cem_cost_ledger` 将输入资本总额读为 `capital`，并用 `excluded` 扣除上述两类备忘项。`network_capex` 与 `network_fom` 分别为年度网络资本与维护费，`operating_sum` 汇总各项实际运行费用。以下成本单位均为 GBP/模型年，`demand`、`blackout` 与 `served` 为年度 MWh：

```text
network_resource_cost = network_capex + network_fom
non_network_capital = max(capital - network_resource_cost, 0)
excluded = vre_storage_fom + compatibility
headline_fleet_capital = max(non_network_capital - excluded, 0)
headline_capital = capital - (non_network_capital - headline_fleet_capital)
system_cost = headline_capital + operating_sum
served = max(demand - blackout - a2_hidden_unserved_mwh(market), 0)
```

`vre_storage_fom` 与 `compatibility` 分别保存风光储固定维护费及已有径流式水电资本的备忘金额。`a2_hidden_unserved_mwh` 从年度能量平衡账户读取额外未供电量；该账户记录的额外缺口为零时，函数返回零。输出为 `cem_system_cost_gbp=system_cost`，已供需求为正时，`cem_system_cost_gbp_per_mwh_served=system_cost/served`；已供需求为零时，每 MWh 成本留空。市场支付、政策转移、建设承诺支出与剩余价值分别记账，运行资源费用按上述实际支出汇总。

## 年度收入与投资分组

投资分组汇集同一主体、技术和地区下具有正容量的资产。主体名称依次取 `investment_owner_id`、`source_agent_id` 和现有资产标识。标记为 `investment_eligible=False` 的资产继续参加调度，其内生投资为零。`SchemeCAgentInvestmentDefinition.decide` 按排序后的 `(owner,technology,region)` 顺序处理各组。

投资计算采用归属于各资产的年度市场收入。Native 按第 5 章将市场代理收入分配给对应资产。主体层面结算由 `adapt_market_for_investment` 按在役 MW 分配：`allocated[asset.asset_id]=income×asset.capacity_mw/capacity`，其中 `capacity` 是该主体的总 MW。直接提供的资产账户按其记录进入投资计算。

火电投资收入扣除发电量乘以发电、燃料、碳及单位时间费用。资产的 `agent_cashflow` 行提供 `generated_mwh` 及四项 GBP/MWh 费用，乘积形成 `operating_cost_gbp`，组内汇总为 `operational`。风电、光伏、三类电池和氢储能采用 `operational=0`。储能投资由此使用已记账的日前与平衡收入，包括回购后保留的日前报酬。剩余电量充电的购电费用为零，循环折旧和固定维护费进入上述各自的资源成本账户。

各组的 `capacity` 汇总在役 MW，`income` 汇总年度 GBP 收入，`replacement` 汇总 `total_capex_gbp`。单位资本费用 `cost_per_mw` 为 GBP/MW，`roi` 为年度净收入与资本之比，`payback` 为年数：

$$
\begin{aligned}
\mathtt{net}&=\mathtt{income}-\mathtt{operational},\\
\mathtt{cost\_per\_mw}&=\mathtt{replacement}/\mathtt{capacity},\\
\mathtt{roi}&=\mathtt{net}/\mathtt{replacement},\\
\mathtt{payback}&=\begin{cases}
\mathtt{replacement}/\mathtt{net},&\mathtt{net}>0,\\
\infty,&\mathtt{net}\le0.
\end{cases}
\end{aligned}
$$

重置资本为零时，`roi=0`。当 `abs(net)≤10⁻⁹×max(abs(income),operational)` 时，火电 `net` 置零，以吸收同组现金流分别求和产生的差值。`preferred` 取成员中最大的 `preferred_rate`，`life` 取最短的 `economic_lifetime_years`，`target_payback` 取最短的 `target_payback_years`。缺失或零值分别采用 0.08、25 年和 `life`。初始默认资产构造将生物质、CCGT 和 OCGT 的目标回收期设为 25 年，其余初值见第 2 章。决策直接通过 `roi` 与 `payback` 比较年度输入金额。

## 年度风电与光伏扩容上限

风电和光伏扩容受需求峰值与技术可用出力曲线限制。在 `canonical_psm_data` 中，`demand` 为半小时需求 MWh，`period_hours=0.5`，`availability` 为无量纲技术出力曲线，`capacity_by_technology[technology]` 为在役 MW。输入采用第 3 章的投资曲线，曲线最大值为 `peak`，新增容量空间计算如下：

$$
\begin{aligned}
\mathtt{peak}&=\max_t\mathtt{availability}[t],\\
\mathtt{headroom}[\mathtt{technology}]&=\max\left(0,
\frac{\max_t\mathtt{demand}[t]}
{\mathtt{period\_hours}\times\max(\mathtt{peak},10^{-12})}
\right.\\
&\qquad\left.-\mathtt{capacity\_by\_technology}[\mathtt{technology}]
\right),\\
\mathtt{limits}[\mathtt{technology}]&=
\mathtt{fraction}\times\mathtt{headroom}[\mathtt{technology}].
\end{aligned}
$$

`SchemeCVREExpansionPolicyDefinition.evaluate` 从 `expansion.vre_cap_fraction` 读取 `fraction`，默认 0.20，返回以 MW 表示的 `limits`。需求峰值为 1,000 MW、`peak=0.8`、在役容量为 300 MW 时，`headroom=950` MW，年度上限为 190 MW。曲线峰值为零时，分母取下限 10⁻¹²。光伏、陆上风电与海上风电分别计算各自上限。

## 年度储能扩容上限

储能扩容采用现有储能充电后剩余的可再生电量。`corrected_storage_headroom` 将 `storage_headroom_inputs` 中的 `leftover_excess_mwh` 读为 `leftover`，并将逐期 `vre_accepted_mwh`、`real_demand_mwh` 和 `storage_discharge_mwh` 分别读为 `vre`、`demand` 和 `discharge`。这些数组均为每期 MWh，新增储能可用剩余电量与剩余需求缺口为：

$$
\begin{aligned}
\mathtt{excess}&=\max(\mathtt{leftover},0),\\
\mathtt{deficit}&=\max(\mathtt{demand}-\mathtt{vre}-\mathtt{discharge},0).
\end{aligned}
$$

虚拟储能将上述序列转为充放电曲线。`_simulate_virtual_pool` 从 `soc=0` 开始，取 `power_mw=10⁹` MW、`energy_cap_mwh=10⁹` MWh，并将往返效率 `rte=0.98` 全部作用于充电侧。`PERIOD_HOURS=0.5`，`exc`、`dfc`、`ch` 和 `dis` 为每期 MWh。每期先充电，再放电：

```text
max_period_mwh = power_mw * PERIOD_HOURS
soc = 0
charge = zeros(len(excess))
discharge = zeros(len(excess))
for t in range(len(excess)):
    exc = excess[t]
    dfc = deficit[t]
    if exc > 1e-9 and soc < energy_cap_mwh - 1e-9:
        ch = min(exc, max_period_mwh, (energy_cap_mwh - soc) / max(rte, 1e-9))
        soc += ch * rte
        charge[t] = ch
    if dfc > 1e-9 and soc > 1e-9:
        dis = min(dfc, max_period_mwh, soc)
        soc -= dis
        discharge[t] = dis
```

充放电量除以 0.5 h 后得到 `charge_mw` 与 `discharge_mw`。`aligned_max_mw` 求两条曲线均至少超过 `min_hours` 的最大功率，`hours_above_power(power_mw,p_mw)` 统计严格高于 `p_mw` 的期数并乘 0.5 h。搜索上界 `peak` 取充、放电峰值中较小者。峰值为零，或高于零的时数不足时，结果为零；`min_hours≤0` 时返回 `peak`。对可达到的正时长，从 `lo=0`、`hi=peak` 开始，执行 64 次二分：

```text
for _ in range(64):
    mid = 0.5 * (lo + hi)
    if (hours_above_power(charge_mw, mid) >= min_hours
            and hours_above_power(discharge_mw, mid) >= min_hours):
        lo = mid
    else:
        hi = mid
return lo
```

`aligned_utilisation_spectrum` 分别在 730、365、52 和 0 小时求解，得到 `mw_730`、`mw_365`、`mw_52` 和 `mw_0`。依次划分的容量段均以 MW 表示：

$$
\begin{aligned}
\mathtt{daily}&=\mathtt{mw\_730},\\
\mathtt{interday}&=\max(\mathtt{mw\_365}-\mathtt{mw\_730},0),\\
\mathtt{weekly}&=\max(\mathtt{mw\_52}-\mathtt{mw\_365},0),\\
\mathtt{seasonal}&=\max(\mathtt{mw\_0}-\mathtt{mw\_52},0).
\end{aligned}
$$

输出将 `daily` 存为 `daily_loop`，将 `interday` 存为 `intraday`。`corrected_storage_headroom` 将后者读入 `intraday`，计算 `power_room=max(daily+intraday,0)`，并令 `power_cap=fraction×power_room`。`1c_battery`、`0.5c_battery` 和 `0.25c_battery` 分别获得这一技术上限，氢储能获得 `hydrogen_cap=fraction×max(seasonal,0)`。`fraction` 取自 `expansion.storage_cap_fraction`，默认 0.20；周尺度容量段保留在报告结果中。同年各组按前述顺序使用所属技术的剩余上限。

储能计算使用完整的 17,520 期及现有储能充电后的剩余电量序列，Native 调度提供该序列。时序较短、期长异于 0.5 h，或缺少该剩余电量序列时，储能上限返回零。分阶段、LP 或 DC 调度提供的年度结果缺少该序列时，也按这一规则将储能投资上限设为零。

## 投资量与退役

各技术采用 `investment_eligibility.json` 规定的准入方式。光伏、陆上风电、海上风电、三类电池和氢储能采用 `headroom_required`；CCGT、OCGT、`gas` 和 `bio_and_waste` 采用 `explicit_uncapped`。核电容量按外部项目及退役日程更新，抽水蓄能和径流式水电按站点项目推进；通用利润规则对这些技术生成零提案。

并行扩容规则按各技术最小限额合并。`caps` 保存该最小值，每年以 `remaining_caps=dict(caps)` 开始分配。前期项目继续留在建设队列中，只有当年投资计算产生的新增提案扣减 `remaining_caps`，因此多个决策年可以围绕同一容量空间保留待建项目。

当一组资产满足 `net<0` 且 `cost_per_mw` 为正时，该组退役部分容量。退役量受组内现有 MW 限制，并按各成员的 MW 比例分摊。其余分组在 `roi>preferred` 时选择 `Invest_High`，否则在 `payback≤target_payback` 时选择 `Invest_Profit`，剩余分组选择 `Do_Nothing`。两类投资均请求 `net/cost_per_mw`，请求退役量与允许新增量为：

$$
\begin{aligned}
\mathtt{requested\_retirement}&=\min\left(\mathtt{capacity},
\frac{|\mathtt{net}|\times\mathtt{target\_payback}}
{\mathtt{cost\_per\_mw}}\right),\\
\mathtt{requested}&=\mathtt{net}/\mathtt{cost\_per\_mw},\\
\mathtt{addition}&=\min\left(\max(\mathtt{requested},0),
\max(\mathtt{allowed},0)\right).
\end{aligned}
$$

在 `headroom_required` 下，`allowed=remaining_caps.get(technology,0)`，正的 `addition` 扣减该剩余额度；在 `explicit_uncapped` 下，`allowed=requested`。`Do_Nothing`、非正单位资本费用和非正 `addition` 均产生零新增容量。例如，一个 100 MW 分组拥有 1 亿英镑总资本、1,000 万英镑净收入、`preferred=0.08` 和 20 MW 剩余空间，则 `roi=0.10`、`payback=10` 年、`requested=10` MW，规划成功率应用前的提案为 10 MW。

新增储能保留组内能量与功率之比。对带有能量容量的成员，`duration=sum(asset.energy_capacity_mwh)/capacity`，单位为小时，提案能量为 `proposal_energy=addition×duration` MWh。提案经济字段由技术资本参数与 `life` 构造，非储能固定维护费按 `fixed_om×addition/capacity` 分配，储能资本及维护费采用技术目录。提案保留投资主体，后续调度收入继续进入该主体分组。分区运行中的 `inherit_frozen_zone_shares` 按成员容量加权，给新增提案分配分区份额。

## 建设时长与规划成功率

每项内生新增容量从 Application Submitted 阶段进入规划。初始载入将 `development_stage_timelines`、`repd_status_to_timeline`、`success_rates` 和 `timeline_statistic` 复制到 `state.extensions["planning_parameters"]`，后续年份继续使用这些表。`endogenous_planning_terms` 按提案的 `technology`、`owner` 和 `decision_year` 读取这些参数。

技术决定规划表的匹配标签。光伏使用 Solar Photovoltaics，陆上风电使用 Wind Onshore，海上风电使用 Wind Offshore，普通电池和电解槽使用 Battery。Gas、CCGT、OCGT 和生物质使用 Wind Onshore，`hydrogen_battery` 使用 Solar Photovoltaics。相应建设时长键为 `solar`、`onshore`、`offshore` 和 `battery`。

阶段表提供项目阶段时长 `months`。`_timeline_months` 通常读取 Application Submitted 的总时长中位数；`planning.timeline_statistic=mean` 选择相应均值。缺少该技术时长时采用 `solar`，缺少总时长均值时采用总时长中位数。所需时长为有限非负值，数据与初始项目时长规则见第 2 章。

项目时长包含由主体名称确定的 −6 至 +6 个月偏移。`model_project_key(owner)` 返回 `Model Decision: <owner>`，`stable_int_hash` 取其 MD5 结果前 16 个十六进制位转为整数。以下计算得到完工年。`round` 的中点取偶数规则使 58.5 个月舍入为 58：

```text
key = model_project_key(owner)
jitter = (stable_int_hash(key) % 13) - 6
rounded_months = int(round(max(1, months + jitter)))
year = int(decision_year)
source_completion = year + rounded_months // 12
completion = max(source_completion, year + 1)
```

提案将 `completion` 存为 `expected_completion_year`，内生项目最早在投资决策次年投运。按 public2 参数表，2025 年海上风电提案在 2033 或 2034 年完工，陆上风电在 2029—2030 年，光伏在 2026—2027 年，普通电池在 2027 年，火电在 2030 年。VALUE 101 使用较短工期，2025 年提案在 2026 年投运。

成功概率按技术标签与地区读取。`source_success_region` 将光伏和陆上风电主体名中的城市映射为地区：Nottingham—East Midlands、Ipswich—Eastern、London—London、Newcastle—North East、Manchester—North West、Edinburgh—Scotland、Portsmouth—South East、Bournemouth—South West、Cardiff—Wales、Birmingham—West Midlands、Sheffield—Yorkshire and Humber。包含 offshore 的主体名映射为 All Offshore，其余主体映射为 England。`_success_rate` 依次采用匹配地区值、该技术各地区记录的算术均值和 0.75，概率范围为 [0,1]。

public2 的海上风电概率约为 0.917，陆上风电地区值约为 0.22—0.71，光伏约为 0.84—0.95。普通电池主体通过技术均值采用约 0.873，火电主体采用约 0.547。VALUE 101 的成功概率为 1。这些概率在新增提案进入规划时应用。

默认 `planning.success_mode=expected` 选择 `mode=expected_capacity`，接纳 `capacity=proposal.capacity_mw×probability`。能量容量、总资本、年化资本与年度固定费用同时乘以该概率一次，单位价格、寿命与收益率参数保留原值。零概率对应零准入容量，后续年份按日程将获准容量投入运行。

`planning.success_mode=stochastic` 选择 `mode=seeded_stochastic`，在确定性抽取值低于成功概率时接纳完整提案。`seed` 来自 `planning.random_seed`，默认 0。提案标识结合 `run.run_id`、决策年、主体及排序后投资组从零开始的序号；相同输入产生相同抽取值，变更运行标识将改变该值：

```text
proposal_id = f"{run.run_id}:{market.year}:{owner}:{index}"
digest = hashlib.sha256(f"{seed}:{proposal_id}".encode("utf-8")).hexdigest()
draw = int(digest[:13], 16) / float(16 ** 13 - 1)
success = probability > 0 and (probability == 1 or draw < probability)
capacity = proposal.capacity_mw if success else 0
```

`SchemeCPlanningPipelineDefinition.admit_projects` 将获准项目加入当前建设队列。后续年份开始时，到期项目成为名为 `commissioned:<project_id>` 的资产，并保留获准 MW、MWh、主体和经济字段。径流式水电项目要求 `hydrology_profile_id`、`capital_cost_scope=new_build` 和 `new_build_cost_source_id`，抽水蓄能还要求 `site_constraint_id` 与 `energy_capacity_mwh`。缺少站点字段的到期项目继续在队列中推迟。

## 状态更新与年度输出

退役改变下一年的容量与经济量。`SchemeCStateTransitionDefinition.apply` 令 `next_year=current_state.year+1`；达到资产声明的 `model_unavailable_from_year` 时整项退役，其余资产按请求退役量调整。`resize_asset_economics` 将容量下限设为零，并按剩余资产比例缩放能量容量、固定维护费与资本：

```text
new_capacity = max(capacity_mw, 0)
ratio = new_capacity / old_capacity
new_energy = old_energy * ratio
total_capex = (capital_cost_per_mw * new_capacity
               + capital_cost_per_mwh * new_energy)
annual_fixed_opex_gbp *= ratio
annualized_capital_cost_gbp = total_capex * capital_recovery_factor(
    capital_discount_rate, economic_lifetime_years)
```

其中 `capacity_mw` 为原有容量减请求退役量，`old_capacity` 与 `new_capacity` 为 MW；储能的 `old_energy` 与 `new_energy` 为 MWh。项目级资本的两个单位造价字段均为零时，`total_capex` 取原资本乘 `ratio`。剩余容量为零时，资产状态设为 `retired`。经济寿命用于年化和投资回收期的默认值；退役时间按声明的停用年或上述亏损退役量确定。

下一年 `YearState` 包含剩余资产、`admission.next_pipeline` 和本年的储能成本观察值。`transition_state` 向 `transition.apply` 提供已投运机组、继续建设的项目和更新后的观察值，输出年份增加一。物理储能按第 4 章初始条件重新开始，售电观察值进入下一年成本计算。

年度输出包含调度电量、收入、系统成本、技术上限、投资提案、规划准入及下一年容量。每已供 MWh 成本按上述账户计算。第 9 章定义运行与建设排放、储能碳记录及可选新增网络的建设排放。在研究期末，`report_only` 返回最终状态，`pipeline_tail` 推进已在建设队列中的项目，`full_extension` 继续年度运行与投资。
