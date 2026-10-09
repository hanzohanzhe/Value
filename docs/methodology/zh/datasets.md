# 初始数据与输入处理

VALUE 将需求、天气、资产、规划数据和外部市场输入组织到同一模型时钟上。来源年份决定需求或天气样本，模型年份决定资产运行与投资。数据包和方法学口径共同规定读取规则。

| 数据配置 | 数据包 | 范围与可用性 |
|---|---|---|
| VALUE 101 | `value-101-baseline-v1` | 随安装提供的 2025–2026 年合成教学数据，每年 17,520 个半小时，另设 48 时段练习 |
| GBP1 public1 | `value-uk-open-data-pack-v1` | 已发布的英国输入，适用于论文复现口径 |
| GBP1 public2 | `value-uk-open-data-pack-public2` | 适用于修正口径的修订包，已随 VALUE 0.7.0-alpha.1 发布（[下载](https://value.ac/zh/data/)） |
| R029 public2 | `value-uk-calendar-vx-trade001-public2` | 适用于修正口径的修订包，已随 VALUE 0.7.0-alpha.1 发布（[下载](https://value.ac/zh/data/)）；研究期为 2025–2034 年，需求取自 2022 年，天气取自 2020–2024 年 |

修正口径的英国研究要求明确声明列名、源单位和时间分辨率，可由 public2 修订包或合格的用户工作区数据包提供。R029 public1（`value-uk-calendar-vx-trade001`）位于论文复现口径的白名单之外，其含 8,761 个数值的光伏投资曲线也未满足修正读取器的全年长度要求。第 3 章说明修订后的曲线。英国 23 区网络研究采用 GBP1 public2 研究套件 `value-uk-research-suite-v1-public2`，从[数据页](https://value.ac/zh/data/)下载。该套件提供修正口径所需的相容国家级与空间输入。

## 时间分辨率与输入角色

全国模型按半小时电量完成供需平衡。`canonical_psm_data` 的 `series` 数组存储以 MW 表示的需求功率；乘以 `period_hours` 后，得到以 MWh/时段表示的实际需求 `demand` 和预测需求 `forecast_demand`。全年电量为各时段电量之和：

$$
\begin{aligned}
\mathtt{demand}[t]&=\mathtt{series}[\text{demand.real}].\mathtt{values}[t]\times\mathtt{period\_hours},\\
\mathtt{forecast\_demand}[t]&=\mathtt{series}[\text{demand.forecast}].\mathtt{values}[t]\times\mathtt{period\_hours},\\
\mathtt{period\_hours}&=0.5\ \mathrm{h},\qquad \mathtt{periods}=365\times24\times2=17{,}520.
\end{aligned}
$$

模型年由 365 日组成，采用固定 UTC 时钟，2 月包含 28 日。声明为闰年的需求序列按下文和第 4 章的规则保留全年电量。容量以 MW 表示，库存以 MWh 表示，金额以 GBP 表示，电价以 GBP/MWh 表示。

需求按 MW 进入模型，调度时再乘以时段长度。VALUE 101 保留了 `mwh` 列名和 MWh/period 数据包标签，其中数值在两个口径下均按 MW 读取。用户映射的需求则按声明的源单位处理：MWh/period 除以用小时表示的源时段长度，得到 MW。

数据绑定将物理文件分配给确定的计算角色。需求文件提供实际需求与日前预测，机组表提供技术、容量和代表位置，规划表提供项目状态与日期；天气和技术平均曲线分别用于空间化可用出力与相应投资规则。

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

## 声明式读取与全年对齐

两个口径均按声明的 `csv_header` 表头规则读取 `csv_column`。隐式选中的整数序号列会终止读取。R029 的需求与边界序列通过 `data_method.read_role` 和 `data_method.read_boundary` 使用这一共享读取器。

修正口径采用 `declared-v2`。未声明表头时，仅当首行所有单元格均为非数值才将其视为表头。未声明列名时，严格读取要求文件仅有一列全部为数值。源分辨率取自 `interval_minutes`，或根据 8,760、8,784 个数值推断为逐时；每个小时值随后用于两个半小时。

含 17,568 期的闰年需求序列删除 2 月 29 日的 48 期，并重新缩放余下数值以保留全年电量。`normalize_half_hour_year` 将源序列读为 `numbers`，保留值记为 `reduced`；保留值之和为正时，返回

$$
\begin{aligned}
\mathtt{original}&=\sum\mathtt{numbers},\qquad \mathtt{retained}=\sum\mathtt{reduced},\\
\mathtt{scale}&=\mathtt{original}/\mathtt{retained},\\
\mathtt{normalize\_half\_hour\_year}(\mathtt{values})&=\bigl(\mathtt{item}\times\mathtt{scale}\ :\ \mathtt{item}\in\mathtt{reduced}\bigr).
\end{aligned}
$$

保留值之和为零、原值之和非零时终止读取；全零序列保持为零。其他角色仅移除闰日，维持其余数值。绑定可以通过 `leap_policy=keep` 显式保留闰日，此时运行取所需的前若干期。

严格读取将足够长的序列截取至运行长度；短序列仅在声明循环或角色约定循环时从头重复，边界角色采用该循环约定。修正口径下的非工作区数据包采用严格读取，用户工作区数据包采用宽松读取，短序列从开头重复补齐；映射时需确认这一重复方式。

```text
read = read_series(path, spec, mode=policy.reader_mode,
                   strictness=policy.strictness, legacy_header=header)
values = align_clock(read.values, periods, spec, mode=policy.clock_mode,
                     strictness=policy.strictness,
                     hourly_repeat=hourly_repeat, cyclic_default=cyclic)
return values
```

论文复现口径采用 `legacy-v1`：按角色设置表头、选择有效数值最多的列和重复短序列的规则与声明列读取共同生效。在 GBP1 public1 中，无表头预测文件的首值 21,560 被作为表头消耗，预测数值因此比实测序列领先一期。修正读取器将该首值保留为数据。

## 需求序列与日历处理

R029 采用 NESO 的 2022 年日前半小时需求预测及相应实际需求，作为各模型年的基础需求形状。GBP1 的需求在两个口径下采用相同的 UTC 预处理规则。`actual_mw.csv` 与 `forecast_mw.csv` 各含 17,520 行，初始序列的统计量如下；后续情景缩放作用于这一基础形状。

| 序列 | 最小功率 MW | 最大功率 MW | 平均功率 MW | 年电量 MWh |
|---|---:|---:|---:|---:|
| 实际需求 | 15,080 | 46,042 | 26,587.967637 | 232,910,596.5 |
| 日前预测 | 14,240 | 46,760 | 26,611.131963 | 233,113,516 |

需求预处理以结算日期和结算时段识别重复记录，再将英国本地日期转换为 UTC 时间轴。对于同一结算时段，采用最新发布时间的记录；发布时间相同则取最后一行。原始 17,518 行经过重复项合并后形成 17,516 行，四个缺失半小时时段采用 UTC 线性插值补齐。

线性插值将缺口两端已知值之差等分。缺一个半小时时，补值为两个端点的均值；缺两个半小时时，补值依次位于前一观测值向后一观测值变化的三分之一和三分之二处。

2022 年输入的每段缺口至多包含两个连续时段，补值集中在 10 月 30 日。表中数值以 MW 表示，展示到六位小数。

| UTC 时刻 | 预测需求 MW | 实际需求 MW |
|---|---:|---:|
| 2022-10-30 09:00 | 22,638.666667 | 24,649 |
| 2022-10-30 09:30 | 22,899.333333 | 24,727 |
| 2022-10-30 23:00 | 19,063.333333 | 20,494.666667 |
| 2022-10-30 23:30 | 19,086.666667 | 19,689.333333 |

## 初始资产与规划项目

初始风光储资产由 REPD 的项目技术、投运状态、投运年份和容量共同确定。输入采用 DESNZ《Renewable Energy Planning Database》2025 年第二季度、7 月发布版本；原表包含 12,977 个项目、53 个字段，规范化后保留 10,653 个项目、14 个字段。

规范化过程保留可识别技术且容量为正的项目，并统一技术名称、数值和日期字段。14 个字段覆盖项目编号、站名、规范技术与原技术名称、MW 容量、开发状态、地区、国家、申请日期、获批日期、施工日期、投运日期以及两个坐标；数值转换失败和原始缺失日期继续作为缺失值参与后续筛选。规范技术包括陆风、海风、光伏、电池和气电。

运行初始容量由研究起始年以前已投运的资产构成。`build_repd_operational_snapshot` 选取状态为 `Operational`、投运年早于或等于起始年、容量为正的风光储项目，并将其映射到对应代表资产；电池容量按储能模板的 `pool_limit` 权重分配。核电容量采用单独的电站政策与年度投退运计划。

R029 的 2025 年初始资产设定包含下表容量，核电、燃气和部分其他技术采用聚合表示。修正口径的默认路径对具备电站政策的 GBP1 研究采用逐站核电可用率及按月停发规则，R029 聚合核电采用 0.723 的可用率。径流水电采用负荷率 0.3487 与季节形状的乘积（第 5 章）。论文复现口径保留 100% 可用率；独立的 R029 实验路径也采用这一输入约定。

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

规划输入按技术和地区给出成功率，按技术和阶段给出时间分布。`regional_technology_success_rates.csv` 含 46 条记录，`planning_timelines.json` 提供以月计的阶段时间。两张表同时用于 REPD 项目和内生投资；模型将 `development_stage_timelines`、`repd_status_to_timeline`、`success_rates` 冻结在初始状态中。

两个方法口径均从这些冻结表取得内生提案的开发期和成功率。技术标签、地区匹配、确定性月份扰动、投运日期及期望容量或带种子随机准入规则见第 4、6 章。`endogenous_planning._success_rate` 依次取技术标签与地区对应的成功率、该标签各地区的平均值、默认值 0.75。输入的开发期和施工期中位数为

| 技术 | 开发期中位数 月 | 施工期中位数 月 |
|---|---:|---:|
| 光伏 | 27.8 | 4.9 |
| 陆风 | 62.5 | 15.0 |
| 海风 | 110.1 | 32.2 |
| 电池 | 31.3 | 10.1 |

## 成本与储能参数

投资输入分别规定单位资本成本、投资回收目标和技术运行参数。R029 使用研究配置中的 `capital_costs.json` 与 `model_parameters.json`；资本成本的上游依据包括 BEIS《Electricity Generation Costs 2020》及 Arup 材料，表中数值为模型采用的参数。年度资本回收利率默认取 0.05，投资决策直接比较未折现收益率与回收期。下表列出基础配置的投资回收目标和 `preferred_rate` 参数。R029 投资规则将四类可扩张储能的有效门槛统一设为 0.12，具体利润率定义及决策规则见第 6 章。

| 技术 | 资本成本 GBP/MW | `preferred_rate` | 投资回收目标 年 |
|---|---:|---:|---:|
| 光伏 | 659,000 | 0.076 | 25 |
| 陆风 | 1,588,000 | 0.076 | 30 |
| 海风 | 3,976,000 | 0.089 | 30 |
| CCGT / OCGT | 2,400,000 | 0.089 | 25 |
| 生物质与废弃物 | 1,500,000 | 0.089 | 20 |
| 1C 电池 | 330,000 | 0.0825 | 10 |
| 0.5C 电池 | 350,000 | 0.165 | 10 |
| 0.25C 电池 | 415,000 | 0.0825 | 10 |
| 氢储能 | 600,000 | 0.01375 | 25（默认） |

储能参数将充电效率、放电效率、持续时间和寿命分别用于库存递推与成本计算。往返效率为 `charge_efficiency * discharge_efficiency`，例如 0.5C 电池取 \(0.98^2=0.9604\)。技术目录中的经济寿命与上表的投资回收目标分开参与计算。循环参数 `maximum_cycles` 用于参考年循环数；三类电池同时用它计算循环折旧。动态储能成本模块对抽蓄和氢储能采用时间回收；修正口径的默认调度采用第 5 章的仅循环折旧报价规则。

| 技术 | 目录持续时间 h | 充电效率 | 放电效率 | 目录经济寿命 年 | 循环参数 `maximum_cycles` |
|---|---:|---:|---:|---:|---:|
| 抽水蓄能 | 4 | 0.87 | 0.87 | 30 | 1,000,000 |
| 1C 电池 | 1 | 0.81 | 0.81 | 15 | 3,000 |
| 0.5C 电池 | 2 | 0.98 | 0.98 | 15 | 5,000 |
| 0.25C 电池 | 4 | 0.81 | 0.81 | 15 | 8,000 |
| 氢储能 | 250 | 0.57 | 0.57 | 10 | 1,000 |

年度资产计划可以直接给定储能功率与电量。2025 年抽水蓄能因此采用 2,828 MW 和 26,700 MWh 的资产状态。

初始储能库存随调度路径设定。R029 实验时序配置取零，通用时间序列输入默认取最大库存的 50%，也可显式指定。默认全国 PSM 在每个年度边界新建储能对象，具体见第 5 章。

财务核算按计算用途与技术配置选取时间参数。生物质经济寿命为 25 年、投资回收目标为 20 年；气电原型的回收目标为 20 年，R029 运行配置将 CCGT 和 OCGT 设为 25 年。

金额按起始年不变币值解释，随模型提供的研究从 2025 年开始。储能目录、抽蓄资本成本和政策预算明确采用 2025 年英镑，燃料与碳价按同一基年解释，重启成本采用第 5 章所述换算。BEIS 2020 年成本、2022 年欧元价格序列，以及标注 2015 或 2024 价格年的核电政策条目，在完成适用的币种换算后保留来源年份数值。因此，共同的货币计价约定包含多个来源价格年，读取器仅执行已声明的币种换算。

政策支出输入由历史汇总与前推假设组成。`mechansim cost.xlsx` 汇集 NESO 容量市场与平衡成本、Ofgem 的 RO/FIT/REGO 资料以及 LCCC 的 CfD 数据，供年度政策支出计算使用。

## 互联线与分区需求

外部市场输入用每个半小时时段的流量界限和价格描述跨境交换机会。R029 为法国、比利时、荷兰、挪威和爱尔兰各提供一个 17,520 行文件，同时绑定流量和价格；字段包括 `period`、`flow_mw`、`price_gbp_per_mwh`、来源价格小时、半小时标记及流量与价格的来源行号。

边界价格采用 Ember 整理的欧洲日前价格，其上游来源为 ENTSO-E。法国、比利时、荷兰和挪威取 2022 年，爱尔兰取 2021 年；每小时价格重复两次，按 EUR/MWh 除以 1.1 EUR/GBP 转为 GBP/MWh 后保存。修正口径保留负的边界价格。论文复现口径将通用时序资源价格的下界设为零，R029 实验路径保留负价。

各边界按 NESO 线路身份连接：`NEMO_FLOW` 对应比利时，`BRITNED_FLOW` 对应荷兰，`NSL_FLOW` 对应挪威。已登记的 GBP1 文件 `Belgium_price.csv` 以 `Price (EUR/MWhe)` 列提供逐小时 EUR/MWh。`read_series` 将 `values` 除以 `spec.eur_per_gbp = 1.1` 一次，再将每小时价格用于两个半小时；内核读取各时段对应的潮流。

这组规则适用于两个口径。GBP1 潮流数值按 MW 读取，其文件仍保留 MWh/period 标签。

边界流量按源时段顺序提供外生交换上限。`flow_mw` 字段以正值表示进口、负值表示出口；`canonical_psm_data` 将其转换为带符号的 MWh，记为 `raw_availability`。非负电量上限 `import_energy`、`export_energy` 为

$$
\begin{aligned}
\mathtt{raw\_availability}[t]&=\mathtt{flow\_mw}[t]\times\mathtt{period\_hours},\\
\mathtt{import\_energy}[t]&=\max(\mathtt{raw\_availability}[t],0),\\
\mathtt{export\_energy}[t]&=\max(-\mathtt{raw\_availability}[t],0).
\end{aligned}
$$

修正口径的默认全国 PSM 将进口容量用于日前出清，论文复现口径仅在平衡环节使用（第 5 章）。public2 修订包沿用正值进口、负值出口的声明符号，状态为 `declared_unverified`，逐国年净潮流的来源核对仍待完成。下表给出 R029 输入文件的范围与平均价格。

| 边界 | 流量范围 MW | 价格年 | 平均价格 GBP/MWh |
|---|---:|---:|---:|
| 比利时 | −1,022 至 1,020 | 2022 | 222.292608 |
| 法国 | −3,091 至 2,997 | 2022 | 250.789325 |
| 爱尔兰 | −987 至 998 | 2021 | 123.937076 |
| 荷兰 | −1,076 至 1,062 | 2022 | 219.917959 |
| 挪威 | −1,263 至 1,399 | 2022 | 126.503575 |

分区研究采用网络包的逐时段地区份额分配全国研究需求。`align_zonal_demand` 在 `scenario_scaled_zonal_shares` 模式下将 `output_real` 设为研究的实际需求，并在各 `index` 从网络包读取 `network_national`。需求量的单位均为 MWh/时段；各区分配值 `value` 追加到 `aligned[zone_id]`：

$$
\begin{aligned}
\mathtt{scale}&=\frac{\mathtt{output\_real}[\mathtt{index}]}{\mathtt{network\_national}},\\
\mathtt{value}&=\mathtt{network\_demand\_mwh\_by\_zone}[\mathtt{zone\_id}][\mathtt{index}]\times\mathtt{scale}.
\end{aligned}
$$

最后一个区域以全国量减去其他区域之和赋值，使空间分配守恒；当网络全国量为零且研究需求具有非零值时，读取器终止运行。可选的 `network_pack_absolute_demand` 直接采用网络包全国量，并按原预测与实际需求的比值调整预测。区域、走廊和资产映射的具体约束在传输章定义。

## VALUE 101 合成输入

VALUE 101 通过 `build_value_101_packs` 中的确定性函数生成日内峰值、季节变化及两次局部需求扰动。`_demand` 返回以 MW 表示的需求功率；它由半小时时段编号 `period` 计算 `day`、`hour`，并组合早间、晚间、夜间与冬季项。`day % 7 < 5` 时 `weekday` 为 1，其余取 0.92；`day` 为 0 或 182 且 `period % 48 == 31` 时，`teaching_peak` 为 30 MW，其余为零：

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

预测函数 `_forecast_demand` 在 `_demand(period)` 上加 `balancing_margin`，再保留六位小数。`day` 为 0 或 182 且 `period % 48 == 30` 时，`balancing_margin` 为 12 MW，其余时段为零。

光伏投资曲线 `_solar_profile` 将日照与季节系数相乘。`hour < 6` 或 `hour > 18` 时返回零；日照窗口内沿用上述 `day`、`hour` 定义，计算

$$
\begin{aligned}
\mathtt{daylight}&=\sin((\mathtt{hour}-6)\pi/12),\\
\mathtt{season}&=0.58+0.42\sin^2((\mathtt{day}-80)2\pi/365),\\
\mathtt{\_solar\_profile}(\mathtt{period})&=\operatorname{round}\bigl[\max(0,\min(\mathtt{daylight}\times\mathtt{season},1)),\ 6\bigr].
\end{aligned}
$$

风电投资曲线 `_wind_profile` 叠加日内、29 日和年周期分量，并将系数限定在 0.08–0.92：

$$
\begin{aligned}
\mathtt{within\_day}&=\mathtt{period}\bmod48,\\
\mathtt{value}={}&0.42+0.13\sin((\mathtt{within\_day}+5)2\pi/48)\\
&+0.12\sin((\mathtt{day}+17)2\pi/29)\\
&+0.08\cos((\mathtt{day}+31)2\pi/365),\\
\mathtt{\_wind\_profile}(\mathtt{period})&=\operatorname{round}\bigl[\max(0.08,\min(\mathtt{value},0.92)),\ 6\bigr].
\end{aligned}
$$

海风投资系数取 `_wind_profile(period)` 的 1.08 倍，以 1 为上限，保留六位小数。三条序列分别保存为 `profiles.vre_solar`、`profiles.vre_onshore`、`profiles.vre_offshore`。

教学天气另在 52°N、0°E 的一个格点给定 8,760 小时序列。此处 `hour` 为从零开始的全年小时编号；太阳数组 `hourly_solar` 的单位为 J/m²，风速数组 `hourly_wind` 的单位为 m/s：

$$
\begin{aligned}
\mathtt{hourly\_solar}[\mathtt{hour}]&=\mathtt{\_solar\_profile}(2\mathtt{hour})\times3{,}600{,}000,\\
\mathtt{hourly\_wind}[\mathtt{hour}]&=7+2\sin((\mathtt{hour}+3)2\pi/24)\\
&\quad+1.2\sin((\lfloor\mathtt{hour}/24\rfloor+17)2\pi/29).
\end{aligned}
$$

天气风速经发电曲线转换后用于调度，技术曲线用于投资规则。法国边界进口上限为 12 MW、价格为 82 GBP/MWh；其余四个边界交换容量为零，占位价格为 200 GBP/MWh。`build_value_101_packs` 将上述需求、天气与市场序列写入教学数据包。

## 数据资格与用户映射

数据包校验区分结构有效性、时序和物理合理性。结构层决定数据包能否安装；时序层检查边界身份、价格币种、本地时间需求、已知行序问题、预测对齐及声明时间戳；合理性层采用 `value_data_plausibility_v1.json` 中的范围。

`profile_eligibility` 将这些发现与口径的数据包白名单共同用于资格判断。修正口径下，非工作区包的时序问题和科学参考包的合理性失败会阻止预检查通过。论文复现口径将其作为警告，同时由白名单排除用户工作区和 VALUE 101 网络包。数据包校验通过后仍需执行按角色读取，风光投资曲线的时钟要求在该步骤检查。

用户需求映射声明列名、单位，并可提供 UTC 或 Europe/London 时间戳。本地时间戳逐行转换为 UTC。日期可声明为 DD/MM/YYYY 或 MM/DD/YYYY，其余情况由数据推断。不可读、重复、倒序、存在缺口或步长不规则的时间戳会阻止提交。

映射序列按行序从模型年的 1 月 1 日 00:00 UTC 起使用，并在各模型年重复。源年份不同会产生提示，读取仍保留输入的行序、星期和节假日。逐时需求由 8,760 或 8,784 行、或 60 分钟时间戳步长识别，完成源单位换算后展开为半小时。短输入需确认重复补齐；替换需求的全年电量超过原序列的 1.5 倍或低于 0.67 倍时，提示同时列出两个全年电量。

映射的欧元价格采用声明的汇率及其年均、月均或固定汇率依据。价格年份被记录，声明年份与 2025 年不同时给出提示，数值仅作币种换算。

## 数据与实现对应

需求来源为 NESO，项目来源为 DESNZ REPD，天气来源为 Copernicus ERA5 single levels，边界价格来源为 Ember 整理的 ENTSO-E 数据。`import_scheme_c_1000twh` 完成项目规范化，`series_reader.py` 和 `data_method` 读取时序，`interconnector_identity` 分配边界序列，`known_data_objects_v1.json` 将已识别输入文件与其声明及行变换关联。`data_validation_layers` 判断数据包资格，`model_clock` 定义 UTC 时段，`zonal_demand_alignment` 将全国需求分配到各区。
