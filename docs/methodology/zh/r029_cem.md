# 实验性年度账户与投资

实验性全国路径向独立的年度账户与投资函数提供时段现金流和物理状态。`doctoral.investment_basis=thesis_final9.6` 选择 `build_thesis96_asset_accounts`、`evaluate_thesis96_investment_accounts` 及以下政策和规划规则。第 4 章给出默认投资规则。实验性 PSM 支持固定年份调度，结果中的 `scientific_release_eligible=false` 与 `doctoral_annual_cem_ready=false` 保留其年度接口状态。

R029 是全国研究及其输入系列的名称。public1 含 8,761 个小时光伏值，缺少所需时段声明，其数据资格排除修正读取器与论文复现白名单。public2 移除 2023-01-01 00:00 UTC 的末值，并将三条风光曲线声明为小时数据。public2 随 VALUE 0.7.0-alpha.1 发布，通过[官网数据页](https://value.ac/zh/data/)提供，并已用于修正 Native 调度。本章实验性计算采用显式提供的年度账户、时段序列与参数。

## 年度账户与决策分组

资产运行盈余汇总提前、平衡及政策收入，再扣除可变与固定运营费。`build_thesis96_asset_accounts` 要求完整的 17,520 个半小时时段，每项资产提供 `annual_fixed_opex_gbp` 与 `annualized_capital_cost_gbp`，时段账本提供市场收入及运行成本。以下账户金额均为该年度 GBP：

```text
operating_surplus_gbp = (
    market_income_gbp + balancing_income_gbp
    + cm_income_gbp + decarb_income_gbp + ancillary_income_gbp
    - variable_operating_cost_gbp - annual_fixed_opex_gbp)
annual_profit_gbp = operating_surplus_gbp - annualized_capital_cost_gbp
```

账户将运行盈余保存为 `net_revenue_gbp`，将扣除资本后的利润保存为 `net_profit_gbp`。此处显式提供的固定运营费扣除一次；第 4 章给出默认风电、光伏及储能把固定运营费计入平准化建设成本的处理。

`decide_doctoral_investment` 按投资主体与技术合并在运且容量为正的资产，汇总年度盈余和资本，计算容量加权的单位 MW 建设成本，取最高偏好收益率及最短退役目标，再按运行 MW 份额向各地区分配新增容量。核电与直接电解制氢按外生方式处理，新建天然水电与抽水蓄能要求场址输入。

评估器从 `operating_surplus_gbp` 读取 `surplus`，从 `annualized_capital_cost_gbp` 读取 `annual_capital`，从 `capital_cost_per_mw_gbp` 读取 `capex`，从 `preferred_rate` 读取 `preferred`。年度资本与单位建设成本均须为正，其 `profit`、年利润率 `rate` 和决策分类为：

$$
\mathtt{profit}=\mathtt{surplus}-\mathtt{annual\_capital},\qquad\mathtt{rate}=\frac{\mathtt{profit}}{\mathtt{annual\_capital}}.
$$

```text
if surplus > annual_capital * (1 + preferred):
    recommendation = "Invest_High"
elif profit > 0:
    recommendation = "Invest_Profit"
elif surplus < 0:
    recommendation = "Deplete"
else:
    recommendation = "Do_Nothing"
```

达到高收益门槛等号且利润为正时归入 `Invest_Profit`。运行盈余非负、扣除资本后利润非正时保留容量。`thesis_final96_contract.json` 中光伏与陆上风电偏好率为 0.076，海上风电为 0.089，储能为 0.12，评估器采用各账户显式提供的数值。

亏损退役采用显式的 `target_payback_years`。默认值为光伏、CCGT、OCGT、氢储能 25 年，陆上及海上风电 30 年，生物质 20 年，三类电池 10 年；技术键 `gas` 对应 20 年。

## 扩容上限与投资量

实验性风光扩容限制在运风光与候选新增出力合计超过需求的时段数。`thesis96_vre_annual_expansion_cap` 将 `demand_mwh`、`operational_vre_available_mwh`、`generation_per_mw_mwh` 分别读为 `demand`、`available`、`profile`。前两个数组为时段 MWh，`profile` 为候选技术每 MW 在各时段的 MWh，计算为：

$$
\mathtt{net}=\mathtt{demand}-\mathtt{available},\qquad\mathtt{already\_negative}=\#\{\mathtt{net}<0\}.
$$

`negative_threshold` 默认取 200 个时段，`cap_fraction` 默认取 0.20。`already_negative` 达到 200 时新增上限为零。其余情形，在净需求非负且单位出力为正的时段形成 `transitions=net/profile`，取从小到大第 `needed=negative_threshold−already_negative` 个值作为 `critical` MW，上限为 `cap_fraction×critical`。可用转折点少于 `needed` 时返回零。

储能采用 `annual_caps` 中显式提供的年度技术额度。`storage_expansion_from_traces` 读取接纳风光、实际需求、充电、充电后剩余电量及放电，再应用第 4 章的利用时长计算。标准修正流程对实验性 PSM 以 `leftover_trace_unavailable` 返回零储能扩容空间，因此独立账户分析须输入所选额度及完整序列。储能账户收益门槛为 12%，实验性 PSM 的结果记录仍将年度储能价格与利润上限集成列为待完成。

留存利润形成 `profit_floor_mw=max(profit,0)/capex`。此处 `capacity` 为组内 `current_capacity_mw`，`capacity_by_tech[tech]` 为该技术已解析账户的 MW 总和，`caps` 保存以 MW 计的 `annual_caps` 输入。风光组按运行容量取得技术额度份额：`share=capacity/capacity_by_tech[tech]`，`cap_share=caps[tech]×share`。`evaluate_thesis96_investment_accounts` 按下表给出 `requested_addition_mw`：

|决策与技术|申请 MW|
|---|---|
|`Invest_High`，风光|`cap_share`|
|`Invest_Profit`，风光|`min(cap_share,profit_floor_mw)`|
|`Invest_High`，CCGT、OCGT 或生物质|`0.01×capacity`|
|`Invest_High`，储能|`max(caps[tech],profit_floor_mw)`|
|`Invest_Profit`，其他合格技术|`profit_floor_mw`|
|`Deplete` 或 `Do_Nothing`|0|

高收益储能账户共享同技术额度，并保留各自的利润投资下限。此处 `high` 为一种技术中合格的 `Invest_High` 账户，`total` 为其申请 MW 总和。分配器先计算：

```text
allowed = max(
    sum(row["profit_floor_mw"] for row in high),
    min(total, caps.get(tech, 0)))
```

分配器按申请 MW 比例分配 `allowed`。比例结果低于 `profit_floor_mw` 的账户先获得该下限，剩余额度再按其他申请量重分配，直至全部边界满足。盈利类储能直接获得留存利润对应容量。亏损账户取 `retirement_mw=min(capacity,−operating_surplus_gbp×target_payback_years/capital_cost_per_mw_gbp)`。

接纳新增量决定计划中的留存利润与外部融资。`spent` 为 `accepted_addition_mw` 所需建设资金，`retained` 为正年度利润与该支出中的较小值，余量记入 `externally_funded_capital_gbp`：

```text
spent = accepted_addition_mw * capital_cost_per_mw_gbp
retained = min(max(annual_profit_gbp, 0), spent)
profit_funded_addition_mw = retained / capital_cost_per_mw_gbp
externally_funded_capital_gbp = spent - retained
```

适配器按 `region_addition=addition×region_capacity/capacity` 向各地区分配 `addition`。储能能量取该地区合计的能量功率比，`life` 取成员经济寿命最小值。融资记录采用 0.05 贷款利率和等于 `life` 的期限，独立股权回收与贷款提款计划属于该融资接口的后续集成部分。

内生项目时长与成功率采用第 4 章的相同冻结表。`decide_doctoral_investment` 对每项地区提案调用 `endogenous_planning_terms(state.extensions["planning_parameters"],technology,owner,decision_year)`，记录 `expected_completion_year`、`success_probability`、`timeline_months` 与 `success_rate_source`。燃气、CCGT、OCGT 及生物质采用陆上风电规划参数，氢储能采用光伏参数，普通电池采用 Battery 参数。

```text
terms = endogenous_planning_terms(
    state.extensions["planning_parameters"],
    technology=technology, owner=owner, decision_year=market.year)
expected_completion_year = terms["completion_year"]
success_probability = terms["success_rate"]
```

例如，一个 100 MW 风光组在 1,000 MW 同技术机组中占 0.10 份额。技术额度为 200 MW、单位建设成本为 £1m/MW、年度资本为 £10m、运行盈余为 £11m、偏好率为 7.6% 时，年度利润为 £1m，收益率为 10%。该组进入 `Invest_High`，申请 20 MW，记录 £1m 留存利润融资与 £19m 外部融资。

## 政策转移与支出

政策情景向合格资产分配声明的年度预算。`basic` 将转移支付置零；`with_cm`、`decarbonisation_base`、`subsidy_as_usual` 与 `governmental_target` 启用容量市场及辅助服务转移，后三者还在政策支出中纳入已有脱碳支持。预算以 2025 年 GBP 显式输入。

`allocate_thesis96_policy` 按折减容量分配容量市场收入。资产 `name` 对应 `cm_weights[name]=power×factor`，其中 `power` 为在运 MW，`factor` 为技术折减系数。年度容量市场预算为 £5.44bn，按这些权重分配。

|技术|折减系数|
|---|---:|
|CCGT、OCGT、生物质|0.95|
|核电|0.85|
|抽水蓄能|0.95|
|1C 电池|0.05|
|0.5C 电池|0.15|
|0.25C 电池|0.60|

氢储能须提供情景专用折减系数。辅助服务按火电、核电与储能的运行 MW 分配。`subsidy_as_usual` 和 `governmental_target` 按合格风光 MW 分配新增脱碳支持，后者在技术容量达到声明目标时终止该技术资格。已有支持进入政策支出，新增支持进入合格投资收入；合格容量合计为零时，预算保留未分配。

`build_system_cost_views` 分别保留资源与历史支出视图。资源视图汇总提供的资本、运行及可靠性支出，以已供电量为分母；历史视图汇总资本、运行、政策征费及按 £17,000/MWh 计价的缺口，以包含适用进口的非电池发电量为分母。资源可靠性输入采用运行设定中的 VoLL，默认为 £17,000/MWh。

`legacy_carbon_metric` 以 `unknown_source_scalar` 保留输入的历史碳标量。`physical_carbon_view` 将发电 MWh 乘显式提供的 kgCO₂e/MWh 因子，再除以 1,000，报告运行 tCO₂e。储能碳库存须提供其充电、放电及来源强度输入，第 9 章列出当前因子目录与气体口径。

## REPD 项目与外生计划

REPD 预处理依据项目状态、容量、地区及里程碑日期建立建设计划。`lookup_regional_success_rate` 先读取技术与地区条目，再取该技术地区均值，最后取 0.75；状态表决定是否应用成功率。期望容量模式将项目 MW 缩放一次，带种子的随机模式按名称、地区及技术生成项目结果，规划器保留这一预处理结果。

REPD 项目的 `resolve_repd_success` 按 `project_name`、`region` 和成功率技术标签 `label` 确定随机结果，接纳条件包含等号。配置种子作为元数据保留，抽签值由这三个项目字段固定：

```text
draw = (stable_int_hash(f"{project_name}|{region}|{label}") % 1_000_000) / 1_000_000
succeeds = draw <= rate
```

`completion_year_from_months` 采用 `base_year`、开发时长 `months` 与 `project_key`。项目专用 `jitter` 为 `stable_int_hash(project_key)` 取模 13 后减 6 个月，键为空时扰动取零，返回年份为：

$$
\begin{aligned}\mathtt{rounded\_months}&=\operatorname{round}(\max(1,\mathtt{months}+\mathtt{jitter})),\\\mathtt{completion\_year\_from\_months}&=\mathtt{base\_year}+\left\lfloor\frac{\mathtt{rounded\_months}}{12}\right\rfloor.\end{aligned}
$$

获批项目合并施工准备与施工周期，日期按日优先解析。前向计划还考虑从申请开始的完整开发周期、模型起始年及初始快照的起始年加一下限。外部项目恰在起始年完成时，可按确定规则延后 1 至 3 年；内生提案采用第 4 章规定的决策年加一下限。

`preprocess_doctoral_project_records` 保留容量至少 1 MW、至 2040 年完成的合格项目。过滤范围包括终止、已投运、已过完成期及长期停滞记录。默认陈旧状态年份为 2015 年，施工宽限期为两年，输出包含保留项目的时间、概率与有效容量。

实验抽蓄日程给出合并功率、能量及已经年化的费用。`apply_thesis96_pumped_schedule` 从 `thesis_final96_contract.json` 读取下表，应用到指定抽蓄资产。年度资本额与所选资本回收系数共同确定等效总资本，用于资产经济字段。

|模型年|MW|MWh|年 OPEX，百万 GBP|年化资本，百万 GBP|
|---|---:|---:|---:|---:|
|2025|2,828|26,700|85.4|377.9|
|2026–2027|2,927.9|27,400|87.8|388.5|
|2028|3,377.9|30,200|96.1|425.1|
|2029|3,587.9|31,800|99.9|441.5|
|2030|4,187.9|40,800|112.4|496.8|
|2031–2034|5,687.9|70,800|134.9|596.4|
|2035|11,387.9|195,800|241.9|1,070.8|

核电采用冻结的 `value_uk_nuclear_policy_v1.json` 日程。Heysham 1、Hartlepool、Heysham 2 和 Torness 分别为 1,155、1,185、1,230、1,190 MW，从 2031 年退出年度资产日程；Sizewell B 为 1,198 MW，从 2056 年退出。Hinkley C 两台各 1,630 MW，于 2031、2032 年进入完整模型年运行；Sizewell C 的 3,200 MW 保留在 2035 年管线中。默认修正 Native 调度对具有电站政策的数据包另应用第 5 章负荷率，以及 AGR 在 2030 年第 4,320 期的可用率截止。

## 实验年度间的物理状态

实验逐期引擎在完整年度之间延续批次年龄与机组记忆。绝对时段索引跨年递增，继续运行批次保留其充电索引；原有机组记忆及累计天然资源预算共同传递，新机组采用给定初始状态，新储能采用空批次。

`DoctoralPeriodEngine.advance_year` 要求连续完整模型年及足以容纳继承库存的储能容量。非空储能退役或缩容至低于现有库存时，需要通过后续接入步骤提供显式处置规则。因此，现行转换保留继续运行储能的库存，退役冲销由显式处置接口确定。年度账户准备、物理状态延续和投资提案分别遵循前述输入要求。
