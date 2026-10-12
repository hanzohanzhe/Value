# 初始数据与输入处理

VALUE 用需求、天气、运行资产、规划项目、技术参数以及外部市场价格和交换上限构建电力系统研究。来源年份确定观测样本，研究起始年确定初始机组及后续投资日历。默认 `value-corrected` 配置采用下列 public2 数据包，可从[数据页](https://value.ac/zh/data/)取得。

| 研究输入 | 数据包 | 内容 |
|---|---|---|
| 英国全国系统 | `value-uk-open-data-pack-public2` | 需求、代表点天气、机组、规划、成本及五个外部市场 |
| 英国 2025–2034 年日历平均天气研究 | `value-uk-calendar-vx-trade001-public2` | R029 配置，采用 2022 年需求与 2020–2024 年天气 |
| 英国 23 区系统 | `value-uk-research-suite-v1-public2` | 全国输入、分区需求、资产分配、走廊与外部边界 |
| VALUE 101 | 合成教学输入 | 2025–2026 年研究，包含完整的 17,520 时段年和 48 时段练习；生成规则见下文 |

输入角色将文件与物理量相连接。数据包的 `manifest.json` 为每个角色指定文件，并声明列名、单位及时间分辨率。下表列出 R029 文件和它们向计算提供的量。

| 输入角色 | 主要数据或字段 | 计算用途 |
|---|---|---|
| 实际需求、需求预测 | `actual_mw.csv` 的 `demand_mw`；`forecast_mw.csv` 的 `forecast_mw` | 实时平衡、日前出清及需求误差 |
| 机组与初始资产 | `fleet.json`、年度 `operating_state` | 技术参数、代表位置和进入调度的容量 |
| 项目及规划 | `repd_projects_normalized.csv`、`regional_technology_success_rates.csv`、`planning_timelines.json` | 初始投运资产、项目成功率与阶段时间 |
| 天气 | `calendar_mean_solar_2020_2024.nc`、`calendar_mean_wind_2020_2024.nc` | 代表点风光可用出力 |
| 技术平均曲线 | `sa.csv`、`wa.csv`、`we.csv` | 光伏、陆风、海风的技术平均投资输入 |
| 资本与政策 | `capital_costs.json`、`model_parameters.json`、`mechansim cost.xlsx` | 投资成本、财务参数及政策支出 |
| 外部市场 | 各国 `flow_mw`、`price_gbp_per_mwh` | 互联线可用交换量与外部报价 |
| 分区网络 | 区域、走廊、边界、资产映射、分区需求 | 空间供需平衡和传输约束 |

## 模型时钟与单位

运行年在 365 日 UTC 日历上包含 17,520 个半小时。第零期从 1 月 1 日 00:00 开始，2 月包含 28 日。资产容量以 MW 表示，储能电量以 MWh 表示，金额以 GBP 表示，电价以 GBP/MWh 表示。`period_start_utc` 为每个时段确定日历时间。

需求以 MW 功率载入。默认全国算法由 `_kernel_inputs` 将 `read_role` 取得的 MW 数值传给 `run_simulation`；分阶段与优化接口通过 `canonical_psm_data` 的 `build_chronology` 构造时段电量，其中 `series["demand.real"].values`、`series["demand.forecast"].values` 存储 MW，`demand`、`forecast_demand` 存储 MWh/时段。对从零开始的时段编号 `t`，

$$
\begin{aligned}
\mathtt{demand}[t]&=\mathtt{series}[\text{demand.real}].\mathtt{values}[t]\times\mathtt{period\_hours},\\
\mathtt{forecast\_demand}[t]&=\mathtt{series}[\text{demand.forecast}].\mathtt{values}[t]\times\mathtt{period\_hours},\\
\mathtt{period\_hours}&=0.5\ \mathrm{h},\qquad \mathtt{periods}=365\times24\times2=17{,}520.
\end{aligned}
$$

全年需求电量为 `demand` 各项之和。用户提供的需求列若以 MWh/源时段表示，先除以该源时段的小时数得到 MW，再对齐至半小时。VALUE 101 在名为 `mwh` 的列中写入合成功率值，这些数值也按上述 MW 至 MWh 关系进入计算。

## 列选择、缺失值与全年对齐

时序载入按声明的列名和表头执行。`read_series` 在 `csv_header=true` 时读取 `csv_column`，要求该列每个单元格均为有限数值。空序列、缺少指定列或无效数值会终止载入。自动选列若得到至少三个连续递增整数且步长为一，则要求显式声明列名。

表头和列名的推断依据文件内容。声明的 `csv_header` 优先；其余情况下，首行至少有一个非空单元格且所有非空单元格均为非数值时，将该行作为表头。缺少 `csv_column` 时，严格读取选择唯一的全数值列；多列全为数值时要求指定其中一列。用户工作区读取在多列情形下选择第一列全数值列，声明列名后由该声明确定选择。

逐时输入先展开，再截取运行所需窗口。`align_clock` 对 `interval_minutes=60` 的输入将每个源值复制两次，对 `interval_minutes=30` 的输入按每半小时一个值读取。缺少时间间隔声明时，8,760 或 8,784 个数值对应逐时年；其他声明分辨率会终止载入。逐时至半小时的转换执行一次。

闰年需求在 365 日日历上保留全年电量。逐时展开后的 17,568 时段年移除从 `(31 + 28) * 48` 开始的 48 个值，即 2 月 29 日。`normalize_half_hour_year` 中，`numbers` 为源值，`reduced` 为保留值；保留值之和为正时，

$$
\begin{aligned}
\mathtt{original}&=\sum\mathtt{numbers},\qquad \mathtt{retained}=\sum\mathtt{reduced},\\
\mathtt{scale}&=\mathtt{original}/\mathtt{retained},\\
\mathtt{normalize\_half\_hour\_year}(\mathtt{values})&=\bigl(\mathtt{item}\times\mathtt{scale}\ :\ \mathtt{item}\in\mathtt{reduced}\bigr).
\end{aligned}
$$

全零需求序列保持为零。保留值之和为零且原总量为正时，转换终止。其他时序角色移除相同的 48 个值并保留其余数值。显式设置 `leap_policy="keep"` 时保留源日历，再取所需的前若干期。

运行从足够长的对齐序列中取前 `periods` 个值。较短的序列在 `cyclic=true` 或该角色约定循环时从开头重复，外部市场流量和价格采用这一约定。严格数据包读取要求较短的需求或投资曲线显式声明循环；用户工作区读取按重复方式补足短序列。这组规则共同确定全年或部分年份运行实际使用的数值。

下列步骤返回对齐序列。`path` 为绑定文件，`spec` 包含其声明，`policy.strictness` 选择严格数据包读取或用户工作区读取，`cyclic` 为角色的默认重复规则。

```text
read = read_series(path, spec, mode="declared-v2", strictness=policy.strictness)
values = align_clock(read.values, periods, spec, mode="declared-v2",
                     strictness=policy.strictness, cyclic_default=cyclic)
return values
```

## 观测需求与缺失结算时段

英国需求形状采用 NESO 的 2022 年半小时实际需求及日前预测。UTC 预处理后，`actual_mw.csv` 和 `forecast_mw.csv` 各包含 17,520 个值；后续模型年依次重复使用这两条已对齐的 2022 年需求序列。功率统计与全年电量为

| 序列 | 最小功率 MW | 最大功率 MW | 平均功率 MW | 年电量 MWh |
|---|---:|---:|---:|---:|
| 实际需求 | 15,080 | 46,042 | 26,587.967637 | 232,910,596.5 |
| 日前预测 | 14,240 | 46,760 | 26,611.131963 | 233,113,516 |

需求预处理先合并结算记录，再插值补齐时段。对于同一结算日期和结算时段，按发布时间排序后取最新记录，发布时间相同时取最后一行；随后将英国本地结算时刻转换到 UTC 半小时时间轴。17,518 条源记录形成 17,516 个独立时段，留下四个半小时缺口。

缺失需求由相邻已知值作线性插值。缺一期间取两个端点的均值；连续缺两期间，依次在前一值上加端点差值的三分之一、三分之二。2022 年输入的四个补值均位于 10 月 30 日：

| UTC 时刻 | 预测需求 MW | 实际需求 MW |
|---|---:|---:|
| 2022-10-30 09:00 | 22,638.666667 | 24,649 |
| 2022-10-30 09:30 | 22,899.333333 | 24,727 |
| 2022-10-30 23:00 | 19,063.333333 | 20,494.666667 |
| 2022-10-30 23:30 | 19,086.666667 | 19,689.333333 |

用户需求时间戳先转换为 UTC，再进入相同的模型年对齐。映射接受 UTC 或 Europe/London 时区，以及声明的 DD/MM/YYYY 或 MM/DD/YYYY 日期顺序。时间戳须严格递增并具有规则的 30 或 60 分钟步长；重复、无法解析的日期和时间缺口会终止映射。转换后的行序从各模型年 1 月 1 日 00:00 UTC 起排列，保留输入中星期和节假日效应的先后顺序。

## 初始运行资产

初始风光和电池装机取自 DESNZ《Renewable Energy Planning Database》2025 年第二季度、7 月发布版本。原表含 12,977 个项目和 53 个字段，经过技术及正容量筛选后形成 10,653 行、14 个字段。`normalize_repd` 保留陆风、海风、光伏、电池和气电，将 `capacity_mw`、`x_coordinate`、`y_coordinate` 转换为数值，转换失败的值记为缺失。

规范化项目表保存日期与位置筛选需要的信息。字段为 `project_id`、`site_name`、`technology`、`technology_source`、`capacity_mw`、`development_status`、`region`、`country`、`planning_application_submitted`、`planning_permission_granted`、`under_construction`、`operational`、`x_coordinate`、`y_coordinate`。日期字符串由资产和规划读取步骤继续解析。

初始风光储项目须具有 `Operational` 状态、早于或等于研究起始年的有效投运日期，以及正的 MW 装机。`build_repd_operational_snapshot` 按日优先顺序解析日期，跳过日期缺失或容量无效的记录。光伏与陆风首先采用第 3 章的地区至城市映射；剩余项目按坐标选择同技术最近的代表点，必要时将 OSGB 坐标由 EPSG:27700 转换为 EPSG:4326。地区和坐标均无法给出分配的项目，对映射后初始风光装机的贡献为零。

初始电池 MW 按权重分配至抽蓄以外的储能条目。各条目的 `weighted[asset_id]` 取其 `pool_limit` 与 1 的较大值，`weight_total` 为这些权重之和。`native_initial_state` 按 `capacity = operational_storage_mw * weighted[asset_id] / weight_total` 分配功率，再以 `capacity * duration` 计算电量，其中 `duration` 取技术目录的持续时间。2025 年抽蓄独立指定为 2,828 MW 和 26,700 MWh。

R029 的 2025 年初始装机如下。其聚合核电可用率为 0.723，径流水电以 0.3487 乘以第 5 章的季节形状计算出力。GBP1 按电站计划选择核电机组，逐站可用率与退运规则也在第 5 章定义。

| 技术 | 资产行数 | 功率 MW | 储能电量 MWh |
|---|---:|---:|---:|
| 联合循环燃气 CCGT | 1 | 28,000 | — |
| 径流式水电 | 1 | 2,000 | — |
| 核电 | 1 | 5,958 | — |
| 开式循环燃气 OCGT | 1 | 4,146 | — |
| 生物质与废弃物 | 1 | 4,762 | — |
| 海上风电 | 18 | 14,679 | — |
| 陆上风电 | 11 | 14,711.65 | — |
| 光伏 | 11 | 10,066.98 | — |
| 0.25C 电池 | 1 | 299.984165 | 1,199.936659 |
| 0.5C 电池 | 1 | 2,465.869834 | 4,931.739667 |
| 1C 电池 | 1 | 74.996041 | 74.996041 |
| 氢储能 | 1 | 0.749960 | 187.490103 |
| 抽水蓄能 | 1 | 2,828 | 26,700 |

## 规划输入

项目开发采用按技术和地区给定的成功率，以及按技术给定的阶段时间。`regional_technology_success_rates.csv` 包含 46 条记录，`planning_timelines.json` 给出以月计的时间。`development_stage_timelines`、`repd_status_to_timeline`、`success_rates` 存入初始状态，同时服务于已有规划项目和新增投资提案。

输入中位数分别描述开发期和施工期。状态映射确定项目尚需经过的阶段。下述预处理构造初始项目清单，第 6 章推进这些项目并在各年接收新增投资提案。

| 技术 | 开发期中位数 月 | 施工期中位数 月 |
|---|---:|---:|
| 光伏 | 27.8 | 4.9 |
| 陆风 | 62.5 | 15.0 |
| 海风 | 110.1 | 32.2 |
| 电池 | 31.3 | 10.1 |


初始规划项目按容量、开发状态和进展日期筛选。`native_initial_state` 采用下表控制量，默认 `planning.success_mode="expected"` 读为 `success_mode="expected_capacity"`。`year` 为研究起始年，`capacity` 为源项目的 MW 容量。

| 参数 | 默认值 | 用途 |
|---|---|---|
| `planning.minimum_project_size_mw` | 1 MW | 进入清单的最小正容量 |
| `planning.include_uncertain_projects` | `true` | 接收申请、上诉和修订状态 |
| `planning.zombie_filter_enabled` | `true` | 启用状态、进展和施工超期筛选 |
| `planning.zombie_status_stale_year` | 2015 | 不确定项目最新进展年份的截止值 |
| `planning.construction_grace_years` | 2 年 | 加至估计施工完成年份的宽限期 |
| `planning.max_completion_year` | 2040 | 接收项目的最晚完成年份 |
| `planning.timeline_statistic` | `median` | 选择阶段时间中位数或均值 |
| `planning.defer_spread_years` | 3 年 | 推算完成日期的最大附加延期 |
| `planning.random_seed` | 0 | 项目成功率抽样的输入 |
| `planning.repd_battery_assignment` | `value_proportional_split` | 将通用电池容量分至四类储能 |

替代申请取代其旧项目记录。预处理读取 REPD 原表的 `Ref ID` 与 `Are they re-applying (New REPD Ref)`；后者给出不同于原标识、非空且确实存在于原表的替代标识时，移除旧记录。容量低于 `minimum_size`、容量非正或无法解析的记录也被移除。

开发状态按去除两端空白并转为小写后的标签筛选。`terminal_statuses` 始终移除 `operational`、`abandoned`、`planning permission refused`、`application withdrawn`。`zombie_filter=true` 时还移除 `application refused`、`appeal refused`、`appeal withdrawn`、`decommissioned`、`application expired`、`finished`。设置 `include_uncertain=false` 后，仅保留 `under construction`、`awaiting construction`、`planning permission granted`。

进展年份筛选作用于 `application submitted`、`appeal lodged`、`revised`。`_date_year` 从日期字符串提取首个以 19 或 20 开头的四位年份，缺少年份时返回 `None`；`latest_progress_year` 再取 `planning_application_submitted`、`planning_permission_granted`、`under_construction`、`operational` 中最近的已知年份。进展筛选启用时，该年份早于或等于 `zombie_stale_year` 的不确定项目被移除；进展年份缺失的项目通过此项筛选。

完成年份优先采用记录中的未来年份，其余项目按剩余阶段时间推算。`timeline_months(source_technology, status)` 从 `repd_status_to_timeline` 选择 `timeline_type`，将其均值或中位数后缀换为 `timeline_statistic`，再读取 `development_stage_timelines` 中对应技术的数值。状态映射缺失时默认采用 `total_median`；阶段条目缺失时采用 `development_timelines`，最终缺省值为 12 个月。储能组件采用电池阶段时间表。

推算完成日期附加零至 `defer_spread_years` 个整年的确定性延期。下列步骤由源项目的 `project_id` 计算延期；已经给定未来日期的项目直接采用该日期。

```text
completion = next((candidate for candidate in (
    _date_year(row.get("operational")),
    _date_year(row.get("under_construction")),
) if candidate is not None and candidate > year), None)
if completion is None:
    months = timeline_months(source_technology, status)
    completion = year + max(1, int(math.ceil(months / 12.0)))
    if defer_spread_years > 0:
        completion += int(
            hashlib.sha256(project_id.encode("utf-8")).hexdigest()[:8], 16
        ) % (defer_spread_years + 1)
```

施工中项目另作历时检查。对于状态为 `under construction` 且 `construction_year` 已知的项目，预处理计算 `construction_end = construction_year + max(1, math.ceil(timeline_months(source_technology, status) / 12)) + construction_grace`。`zombie_filter=true` 且该值早于 `year` 时移除项目；`completion` 晚于 `maximum_completion` 的项目也被移除。

初始项目成功率按技术和地区查表。`_planning_probability` 读取 `technology`、`region`、`success_rate`，将可解析的成功率限制在 [0,1]，跳过无法解析的值；缺少必要列时，成功率表为空。查询时先查项目地区的小写标签，再查同技术的 `gb` 条目，最终缺省为 1.0。下式给出成功率 `probability`、无量纲抽样值 `draw` 与接收容量，同一实体电池项目的全部组件采用同一个抽样值。

```text
probability_key = "battery" if source_technology == "battery" else _technology(source_technology)
probability = success_rates.get(
    (probability_key, region.strip().lower()),
    success_rates.get((probability_key, "gb"), 1.0),
)
draw = int(
    hashlib.sha256(f"{random_seed}:{project_id}".encode("utf-8")).hexdigest()[:13], 16
) / float(16 ** 13 - 1)
realised_failure = success_mode == "seeded_stochastic" and draw > probability
components = typed_project_components(project_id, source_technology, capacity)
for component_id, technology, declared_component_capacity, assignment_method in components:
    effective_capacity = (
        declared_component_capacity * probability
        if success_mode == "expected_capacity" else declared_component_capacity
    )
```

通用电池项目先拆分，再记录经过成功率处理的容量。`typed_project_components` 采用 `scheme_c_storage_weights`，按初始电池装机使用的正机组权重，将源 MW 分至 `1c_battery`、`0.5c_battery`、`0.25c_battery`、`hydrogen_battery`；各 `declared_component_capacity` 等于源容量乘以该权重占总权重的比例。`all_1c`、`all_0.5c`、`all_0.25c` 分别将全部容量分给一种技术，`exclude_untyped` 从初始清单移除通用电池项目。技术已经明确的项目保留其技术与容量。

期望容量模式将组件声明 MW 乘以成功概率。随机模式 `planning.success_mode="stochastic"` 读为 `seeded_stochastic`，保留全部声明 MW；`draw > probability` 时设为 `phase="failed"`、`outcome="failed_planning"`，两者相等时通过。通过抽样的项目与期望容量项目采用 `phase="active"`、`outcome="active"`。储能电量为 `effective_capacity * duration_hours`，单位 MWh。`PlanningProject` 将这些值与 `expected_completion_year=completion`、起始年、状态、技术和地区一并保存，供第 6 章逐年推进。

新增投资提案采用 `endogenous_planning._success_rate` 查询成功率。它依次选择地区成功率、同技术各地区均值和缺省值 0.75。第 6 章规定提案容量及后续规划过程。

## 资本成本与储能参数

资本成本、目标收益率和回收期分别作为财务输入。R029 从 `capital_costs.json` 和 `model_parameters.json` 读取参数；资本成本材料包括 BEIS《Electricity Generation Costs 2020》及 Arup。下表给出赋予初始资产的财务参数。年度资本回收采用 `capital_discount_rate=0.05`，投资计算和实际决策门槛见第 6 章。

| 技术 | 资本成本 GBP/MW | `preferred_rate` | 投资回收目标 年 |
|---|---:|---:|---:|
| 光伏 | 659,000 | 0.076 | 25 |
| 陆风 | 1,588,000 | 0.076 | 30 |
| 海风 | 3,976,000 | 0.089 | 30 |
| CCGT / OCGT | 2,400,000 | 0.089 | 25 |
| 生物质与废弃物 | 1,500,000 | 0.089 | 25 |
| 1C 电池 | 330,000 | 0.0825 | 10 |
| 0.5C 电池 | 350,000 | 0.165 | 10 |
| 0.25C 电池 | 415,000 | 0.0825 | 10 |
| 氢储能 | 600,000 | 0.01375 | 25（默认） |

储能损耗由充电效率与放电效率分别描述。往返效率为 `charge_efficiency * discharge_efficiency`，0.5C 电池对应 \(0.98^2=0.9604\)。技术目录还提供持续时间、经济寿命和 `maximum_cycles`，这些量进入第 4、6 章的库存递推与成本计算，初始库存随运行算法在第 4 章给定。

| 技术 | 目录持续时间 h | 充电效率 | 放电效率 | 目录经济寿命 年 | 循环参数 `maximum_cycles` |
|---|---:|---:|---:|---:|---:|
| 抽水蓄能 | 4 | 0.87 | 0.87 | 30 | 1,000,000 |
| 1C 电池 | 1 | 0.81 | 0.81 | 15 | 3,000 |
| 0.5C 电池 | 2 | 0.98 | 0.98 | 15 | 5,000 |
| 0.25C 电池 | 4 | 0.81 | 0.81 | 15 | 8,000 |
| 氢储能 | 250 | 0.57 | 0.57 | 10 | 1,000 |

各输入沿用其来源价格年的数值。储能成本与政策预算以 2025 年英镑计价；BEIS 资本成本输入保留 2020 年值，欧洲电价样本在币种换算后保留 2022 或 2021 年值，核电政策条目带有其声明的 2015 或 2024 价格年。重启成本采用第 5 章的换算。币种读取器按 `eur_per_gbp` 将欧元转换为英镑。

年度政策支出采用 `mechansim cost.xlsx` 中的序列。该表汇集 NESO 容量市场与平衡成本、Ofgem RO/FIT/REGO 材料以及 LCCC CfD 数据，第 6 章定义这些输入进入年度核算的方式。

## 外部市场与分区需求

外部电力交换由时变交换上限和对应市场价格描述。R029 为法国、比利时、荷兰、挪威和爱尔兰各提供一个 17,520 行文件，包含 `flow_mw`、`price_gbp_per_mwh` 及其时段和来源时间戳。NESO 线路名将 `NEMO_FLOW` 对应到比利时、`BRITNED_FLOW` 对应到荷兰、`NSL_FLOW` 对应到挪威。

外部价格采用 Ember 汇集的 ENTSO-E 日前市场数据。法国、比利时、荷兰和挪威取 2022 年，爱尔兰取 2021 年；每个逐时 EUR/MWh 值除以 1.1 EUR/GBP，再用于对应的两个半小时，负价保留其符号。R029 保存已转换的 GBP/MWh 值；GBP1 的 `Belgium_price.csv` 等文件由 `Price (EUR/MWhe)` 列提供输入，通过 `read_series` 执行相同换算。

`flow_mw` 的正值定义进口上限，负值定义出口上限。乘以 `period_hours` 得到带符号的时段电量 `raw_availability`，再计算两个非负电量界限：

$$
\begin{aligned}
\mathtt{raw\_availability}[t]&=\mathtt{flow\_mw}[t]\times\mathtt{period\_hours},\\
\mathtt{import\_energy}[t]&=\max(\mathtt{raw\_availability}[t],0),\\
\mathtt{export\_energy}[t]&=\max(-\mathtt{raw\_availability}[t],0).
\end{aligned}
$$

默认全国市场在日前出清中接受进口报价。第 5 章给出交换上限在出清与平衡中的用法，第 7 章将外部边界容量用于分区模型。R029 的输入范围与平均价格为

| 边界 | 流量范围 MW | 价格年 | 平均价格 GBP/MWh |
|---|---:|---:|---:|
| 比利时 | −1,022 至 1,020 | 2022 | 222.292608 |
| 法国 | −3,091 至 2,997 | 2022 | 250.789325 |
| 爱尔兰 | −987 至 998 | 2021 | 123.937076 |
| 荷兰 | −1,076 至 1,062 | 2022 | 219.917959 |
| 挪威 | −1,263 至 1,399 | 2022 | 126.503575 |

分区需求由全国研究总量和网络输入的地区份额确定。`align_zonal_demand` 按 `period_ids` 对应网络和研究时段，要求时段标识唯一且具有对应记录。实际需求和预测需求均须为有限非负电量，长度须与时段列表相同。在 `scenario_scaled_zonal_shares` 模式下，`output_real` 为研究实际电量，`network_national` 为该 `index` 的网络全国电量，单位均为 MWh：

$$
\begin{aligned}
\mathtt{scale}&=\frac{\mathtt{output\_real}[\mathtt{index}]}{\mathtt{network\_national}},\\
\mathtt{value}&=\mathtt{network\_demand\_mwh\_by\_zone}[\mathtt{zone\_id}][\mathtt{index}]\times\mathtt{scale}.
\end{aligned}
$$

最后一个区域接收全国电量扣除此前各区分配后的余量。两组全国输入均为零时，`scale=1.0`；研究需求为正而网络全国需求为零时终止对齐。以下步骤给出完整分配过程，`zone_ids` 保留网络声明的区域顺序：

```text
aligned = {zone_id: [] for zone_id in zone_ids}
for index, period_id in enumerate(periods):
    network_national = network_national_mwh[index]
    if network_national == 0.0 and output_real[index] == 0.0:
        scale = 1.0
    elif network_national == 0.0:
        raise ValueError("Zonal demand requires positive network national demand")
    else:
        scale = output_real[index] / network_national
    remaining = output_real[index]
    for zone_id in zone_ids[:-1]:
        value = network_demand_mwh_by_zone[zone_id][index] * scale
        aligned[zone_id].append(value)
        remaining -= value
    aligned[zone_ids[-1]].append(remaining)
```

可选模式 `network_pack_absolute_demand` 将 `output_real` 设为 `network_national_mwh`，并取 `scale=1.0`；预测电量为 `output_real[index] * forecast[index] / real[index]`。当 `real[index]` 为零时，要求 `forecast[index]` 和 `output_real[index]` 同为零，此时预测也取零。最后一区仍采用余量分配，以保留全国电量总和。

## VALUE 101 合成输入

VALUE 101 采用确定性需求、天气和投资曲线。`_demand` 返回从零开始的半小时时段编号 `period` 对应的 MW，`day` 和 `hour` 表示该期的日与小时。`day % 7 < 5` 时 `weekday` 取 1，其余取 0.92；第 0、182 日的 `period % 48 == 31` 时，`teaching_peak` 取 30 MW，其余为零：

$$
\begin{aligned}
\mathtt{day}&=\lfloor\mathtt{period}/48\rfloor,\qquad
\mathtt{hour}=(\mathtt{period}\bmod48)/2,\\
\mathtt{morning}&=9\exp\bigl[-((\mathtt{hour}-8)/2.2)^2\bigr],\\
\mathtt{evening}&=19\exp\bigl[-((\mathtt{hour}-19)/2.5)^2\bigr],\\
\mathtt{overnight}&=2\exp\bigl[-((\mathtt{hour}-1)/3.5)^2\bigr],\\
\mathtt{winter}&=1+0.16\cos(2\pi\mathtt{day}/365).
\end{aligned}
$$

$$
\begin{aligned}
\mathtt{\_demand}(\mathtt{period})=\operatorname{round}\bigl[&
(22+\mathtt{morning}+\mathtt{evening}+\mathtt{overnight})\\
&\times\mathtt{winter}\times\mathtt{weekday}+\mathtt{teaching\_peak},\ 6\bigr].
\end{aligned}
$$

日前预测为 `_demand(period) + balancing_margin`，保留六位小数。第 0、182 日的 `period % 48 == 30` 时，`balancing_margin` 取 12 MW，其余为零。这两次 12 MW 附加量分别位于实际需求峰值前半小时。

光伏投资系数由日照项与季节项相乘得到。`hour < 6` 或 `hour > 18` 时 `_solar_profile` 返回零；日照窗口内沿用同一 `day`、`hour` 定义：

$$
\begin{aligned}
\mathtt{daylight}&=\sin((\mathtt{hour}-6)\pi/12),\\
\mathtt{season}&=0.58+0.42\sin^2((\mathtt{day}-80)2\pi/365),\\
\mathtt{\_solar\_profile}(\mathtt{period})&=\operatorname{round}\bigl[\max(0,\min(\mathtt{daylight}\times\mathtt{season},1)),\ 6\bigr].
\end{aligned}
$$

风电投资系数叠加日内、29 日和年度分量。`_wind_profile` 将结果限定在 0.08–0.92，并保留六位小数：

$$
\begin{aligned}
\mathtt{within\_day}&=\mathtt{period}\bmod48,\\
\mathtt{value}={}&0.42+0.13\sin((\mathtt{within\_day}+5)2\pi/48)\\
&+0.12\sin((\mathtt{day}+17)2\pi/29)\\
&+0.08\cos((\mathtt{day}+31)2\pi/365),\\
\mathtt{\_wind\_profile}(\mathtt{period})&=\operatorname{round}\bigl[\max(0.08,\min(\mathtt{value},0.92)),\ 6\bigr].
\end{aligned}
$$

海风投资系数取 `_wind_profile(period)` 的 1.08 倍，上限为 1，保留六位小数。光伏、陆风、海风数组分别绑定至 `profiles.vre_solar`、`profiles.vre_onshore`、`profiles.vre_offshore`。

合成天气在 52°N、0°E 处设一个格点，给定 8,760 个小时值。此处 `hour` 为从零开始的全年小时编号，`hourly_solar` 为 J/m² 累计辐射，`hourly_wind` 为 m/s 风速：

$$
\begin{aligned}
\mathtt{hourly\_solar}[\mathtt{hour}]&=\mathtt{\_solar\_profile}(2\mathtt{hour})\times3{,}600{,}000,\\
\mathtt{hourly\_wind}[\mathtt{hour}]&=7+2\sin((\mathtt{hour}+3)2\pi/24)\\
&\quad+1.2\sin((\lfloor\mathtt{hour}/24\rfloor+17)2\pi/29).
\end{aligned}
$$

调度按第 3 章风电曲线转换上述风速，并按该章瞬时输入规则转换太阳序列；投资采用前述系数。法国边界采用恒定 12 MW 进口上限和 82 GBP/MWh 电价，其余四个边界交换容量为零，价格输入为 200 GBP/MWh。`build_value_101_packs` 将这些序列写入教学输入。
