# 模型框架

VALUE 将电力系统的逐期运行与年度资产演化连接起来。发电、储能和外部电力交换在给定需求与天气下参与市场出清，年度运行收入、成本及扩容余量随后进入投资与退役规则。模型输出包括发电与储能运行、未供电量、系统资源成本、碳排放、在役容量和建设项目。

## 时间与空间表示

VALUE 以 0.5 小时为运行步长，每个模型年固定为 365 天、17,520 期。时钟采用 UTC，2 月按 28 天排列。功率以 MW 表示，期间电量以 MWh 表示；期间电量等于功率乘以时段长度。投资决策在完整运行年之后更新。

全国模型将大不列颠电力系统表示为一个供需节点，互联线以外部边界报价参与交换。分区模型进一步给定资源与需求的位置、区间通道容量及边界约束。网络数据中的区域映射、需求分配和容量共同确定所求解的空间系统，第 7 章给出约束与求解方法。

## 方法学口径

修正口径 `value-corrected` 是 VALUE 的默认设定，也是本文各章的主要描述对象。默认全国调度模块 `value-bid-at-cost-psm` 使用 `native-corrected-v1` 规则集；分阶段调度模块 `value-staged-bid-at-cost-psm` 将全国计划与随后发生的平衡或分区再调度连接起来。两条运行路径的报价、结算和储能计算分别在第 4、5、7 章展开。

论文复现口径 `doctoral-lineage-0.6.0a2` 是保留 VALUE 0.6.0-alpha.2 所实现论文时期设定的兼容配置。它使用 `native-doctoral-thesis-v1` 规则集，保留原有天气转换、下调顺序和储能定价。两个口径共同采用 UTC 需求与互联线对齐、声明列读取、火电净收入、每期单一储能净头寸、下调与必发盈余的单次记账，17,000 £/MWh 的已记录切负荷价值、包含物理运行成本的成本账 v2、验证报告，以及相同的缺口和已供电量定义。两个口径的内生提案均采用从数据包冻结的建设周期和地区成功率。各章在相关方程之后说明兼容口径的具体取值。

实验性全国路径 `value-doctoral-national-psm` 另行定义全国出清与年度核算接口。它提供固定年度调度与实验现金记录，整合年度 CEM 的就绪标记为 false。第 5、6 章分别给出其运行算法和独立年度辅助函数，口径选择与调度模块选择共同构成一次计算的方法身份。

界面分别选择方法学口径与调度模块。下表将本文使用的名称对应到 Study 编辑器。

|正文名称|英文界面标签|中文界面标签|模块或口径|
|---|---|---|---|
|修正口径|Corrected methodology (default)|修正口径（默认）|`value-corrected`|
|兼容口径|Doctoral reproduction|论文复现口径|`doctoral-lineage-0.6.0a2`|
|Native 全国调度|National single node|全国单节点|VALUE live bid-at-cost PSM; `value-bid-at-cost-psm`|
|实验性全国路径|Doctoral national physical PSM (experimental)|Doctoral national physical PSM (experimental)|`value-doctoral-national-psm`|

## 年度计算流程

默认年度路径根据初始资产、建设项目、需求和天气决定当年运行。年初推进已有建设项目，并形成可用发电与外部交换输入；调度模块计算全年运行；年末根据运行结果、投资规则和建设周期更新下一年的资产与项目状态。

```text
state = initial_state
for year in range(initial_state.year, run.end_year + 1):
    advanced = self.planning.advance_year(run, state)
    model_input = self.psm_input_factory(run, advanced.operating_state)
    market = self.psm.run(model_input)
    headroom = []
    for slot in sorted(self.expansion_policies):
        policy = self.expansion_policies[slot]
        value = policy.evaluate(run, advanced.operating_state, market)
        headroom.append(value)
    investment_market = adapt_market_for_investment(
        market, advanced.operating_state)
    decision = self.investment.decide(
        run, advanced.operating_state, investment_market, tuple(headroom))
    decision = inherit_frozen_zone_shares(decision, advanced.operating_state)
    admission = self.planning.admit_projects(
        run, advanced.operating_state, decision.proposals)
    transition_state = YearState(
        year, advanced.operating_state.assets, advanced.active_projects,
        cumulative_metrics=state.cumulative_metrics,
        extensions=transition_extensions)
    next_state = self.transition.apply(
        run, transition_state, admission, decision)
    state = next_state
```

`run` 保存选定模块、参数和模型年份。`state` 保存在役资产与建设项目，`advanced.operating_state` 是年初规划更新后的资产状态。`market` 包含调度和年度账户，`headroom` 包含各技术的扩容上限，`decision.proposals` 包含新投资提案。`transition_extensions` 将年度储能成本观察值和求解验证状态带入 `next_state`。这些名称和调用对应 `gridform_core/v2/orchestrator.py` 的默认年度流程；选定的网络扩建模块另行执行其年度步骤。


默认投资采用年度收入形成的收益率与回收期判据，资本年化核算使用资本回收因子。燃气和生物质的投资净收入扣除发电、燃料、碳与单位时间运行成本；风电、光伏和储能的设定将毛收入作为投资利润，其固定运维费用并入资本成本口径。第 4 章定义这些默认计算，第 6 章给出独立的实验账户与投资接口。

模型金额采用起始年不变币值的情景约定，默认起始年为 2025 年。输入表同时保留各自的原始价格年份，包括技术成本、进口电价与政策参数。第 2 章列出价格来源与换算，第 5 章列出重启成本的 2025 年英镑取值。

## 数据与结果

模型输入包括需求、天气、初始资产、技术经济参数、建设项目和外部电力交换。第 2 章给出输入文件、时间覆盖、单位及适用口径，第 3 章给出天气到可用出力的转换。数据文件与函数名紧接对应计算，便于读者从设定定位到实现。

年度经济结果在物理与核算检查通过后进入结果页。修正口径检查所选路径的验证门，论文复现口径检查全部原始不变量；逐期账本保留出力、储能、缺口和成本记录。第 4 章说明这些检查与年度结果的关系，第 9 章给出碳核算参数。
