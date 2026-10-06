# VALUE 修正口径参考统计表（供作者审阅）

> **状态（2026-10-06 更新）：第 1、2 节已由作者审核（DECISIONS A14）；第 3 节损耗系数已由作者认可（A9）。** 第 3.4 节 DUKES 对照列只作披露（A9），第 3.5 节光伏倾斜面换算的模型选择（A13，F2 单元）仍为 PENDING AUTHOR REVIEW。以下各节标题中的 "PENDING AUTHOR REVIEW" 为第一、二轮编制时的原状态，保留作记录。
>
> 原状态：PENDING AUTHOR REVIEW（全文所有数字、所有建议取值均待作者审阅，未被接受前不得写入 corrected 参数表）
>
> 用途：P0 计划 M5 / P0-5 S7（Q15 风光文献损耗系数）与 S8（核电、水电可用率）的参考数据。
> 编制：2026-10-06 第一轮只读公开网页（WebSearch/WebFetch），未下载数据文件。
> **第二轮补齐（2026-10-06，DECISIONS A11 授权，单元 F1-DESNZ-refstats）：** 从 gov.uk 下载了 6 个 DESNZ 官方 xlsx（DUKES 2026 表 5.6、5.10、6.2、6.3；Energy Trends 2026 年 9 月版表 5.1、6.1），只放在施工临时目录，未入库。文件清单、URL、sha256 与访问时间见第 6 节。原先标 [NV] 的核电与水电数据已全部用 xlsx 单元格补齐，标为 [X]。按 A11，补齐后的本表须再次交作者审核，审核通过前不算验收。
> 访问日期：所有链接实际访问于 **2026-10-06**（任务模板要求写 2026-10-04；为如实起见此处记录实际访问日期，作者可统一改写）。
> 版本说明：本次下载的是 **DUKES 2026**（2026-07-30 发布，含 2025 年数据，2023–2024 年为修订值）和 **Energy Trends 2026 年 9 月版**。第一轮引用的 DUKES 2025 正文数字（[E]）与新版不一致时，以 [X] 为准，原值保留在表中供对照。

## 0. 核实等级说明（每个数字都标注其中之一）

| 标记 | 含义 |
|---|---|
| **[V]** | 已在可读的 HTML 网页上直接读到该数字（一手或指定出版方页面）。 |
| **[V2]** | 已在可读网页上读到，但该网页是二手转述（Statista、Wikipedia、新闻转述等），需作者对照一手表格。 |
| **[E]** | 仅来自搜索引擎对原文（DESNZ PDF、ONR docx、期刊全文）的摘录，原文件本身未能打开（gov.uk 的 DUKES/Energy Trends 只以 PDF/xlsx 发布，WebFetch 无法解析，且本任务禁止下载文件）。**作者必须对照原表复核。** |
| **[D]** | 由上面已核实的数字推导，推导式写在旁边，不是独立来源。 |
| **[NV]** | 未能从任何可读来源核实。按规则**不给数**，只说明应从哪里取。 |
| **[X]** | （第二轮新增）直接读自第 6 节所列 DESNZ 官方 xlsx 的单元格，用运行时自带的 openpyxl 读取（`data_only=True`），表名、工作表与行名写在旁边。四舍五入只在本文展示时进行。 |

重要限制（第一轮）：DESNZ 的 DUKES 表 5.6 / 5.10 / 6.2 / 6.3 和 Energy Trends 表 5.1 / 6.1 只以 xlsx/ods/PDF 发布，第一轮没有读到单元格。**第二轮已按 A11 下载并读取这些表**；凡是第一轮标 [E] 的 DESNZ 数字，现在都有对应的 [X] 值可对照。

---

## 1. 英国核电可用率（PENDING AUTHOR REVIEW → 作者已审核，A14）

> A14：各站 2019–2024 均值获认可，参数表数值不变。F2 单元按 1.6 节把 Heysham 2、Torness 的停发月份 2030-03 写入参数表 `generation_end_month_overrides`（A10，`p05.nuclear-generation-end-month`）。

### 1.1 来源清单

| ID | 出版方 / 文献 | 表或节 | 年份 | URL | 等级 |
|---|---|---|---|---|---|
| N1 | World Nuclear Association Reactor Database（数据标注为 "Operating details – IAEA PRIS"） | 各反应堆页的 Operating history 表：Electricity Supplied (GWh)、Load Factor Annual (%)、Reference Unit Power (MWe) | 2026 年在线版 | https://world-nuclear.org/nuclear-reactor-database/summary/United%20Kingdom ；单堆页面：`https://world-nuclear.org/nuclear-reactor-database/details/<Reactor-Name>`（例如 `Sizewell-B`、`Torness-1`、`Heysham-A-1`、`Hartlepool-A-2`、`Hunterston-B-1`、`Hinkley-Point-B-1`、`Dungeness-B-1`） | [V]（PRIS 数据，经 WNA 页面转载） |
| N2 | EDF Energy 新闻稿 "Investment boost to maintain UK nuclear output at current levels until at least 2026" | 正文 | 2024-01-09 | https://www.edfenergy.com/node/100401 | [V] |
| N3 | EDF Energy 新闻稿 "£1.2billion investment across 2026-28 to help boost reliability and output"（2025 fleet update） | 正文 | 2026-01-21 | https://www.edfenergy.com/media-centre/2025-fleet-update | [V] |
| N4 | EDF Energy 新闻稿 "UK energy security supported by further nuclear power station life extensions" | 正文 | 2026-07-22 | https://www.edfenergy.com/node/123860 | [V] |
| N5 | EDF Energy 各电站页面（Heysham 1、Hartlepool、Heysham 2、Torness、Sizewell B、Dungeness B、Hinkley Point B） | 页面参数框 | 2026 年在线版 | `https://www.edfenergy.com/energy/power-stations/<station>` | [V] |
| N6 | World Nuclear News "Further life extension of two UK nuclear power stations" | 正文 | 2025-09-02 | https://world-nuclear-news.org/articles/further-life-extension-of-two-uk-nuclear-power-stations | [V] |
| N7 | World Nuclear News "EDF seeking maximum use of existing UK reactors" | 正文 | 2026-01-22 | https://world-nuclear-news.org/articles/edf-seeking-maximum-use-of-existing-uk-reactors | [V] |
| N8 | DESNZ 新闻 "Sizewell B power plant given lifetime extension to 2055" | 正文 | 2026-07-08 | https://www.gov.uk/government/news/sizewell-b-power-plant-given-lifetime-extension-to-2055 | [V] |
| N9 | EDF Energy "Hundreds of extra workers at Sizewell B for £60m planned refuelling and maintenance project" | 正文 | 2014-10-10 | https://www.edfenergy.com/node/15266 | [V] |
| N10 | ONR Project Assessment Report，Torness 22-005（Torness 2 号堆定期停堆） | 引言 | 2022 | https://onr.org.uk/publications/regulatory-reports/site-specific-reports/project-assessment-reports/2022/09/torness-22-005 | [E]（docx 文件，未打开） |
| N11 | ONR Inspection record，Torness Inspection ID 54307 | 正文 | 2026-03 | https://www.onr.org.uk/publications/regulatory-reports/site-specific-reports/inspection-records/2026/03/torness-inspection-id-54307 | [V] |
| N12 | World Nuclear News "UK regulator approves restart of Heysham I unit 1" | 正文 | 2015-01-13 | https://world-nuclear-news.org/articles/uk-regulator-approves-restart-of-heysham-i-unit-1 | [V] |
| N13 | DESNZ DUKES 2025 第 5 章（Electricity）及 Chapters 1–7 合订本 | 第 5 章正文、表 5.6 / 5.10 | 2025-07-31 | https://assets.publishing.service.gov.uk/media/688a28656478525675739051/DUKES_2025_Chapter_5.pdf ；https://assets.publishing.service.gov.uk/media/68dbe477ef1c2f72bc1e4c4d/DUKES_2025_Chapters_1-7.pdf | [E] |
| N14 | World Nuclear Association 国家概况 "Nuclear Power in the United Kingdom" | 正文 | 2026 年在线版 | https://world-nuclear.org/information-library/country-profiles/countries-t-z/united-kingdom | [V2] |
| N15 | Statista "Plant load factor of nuclear stations in the UK 2010–2023" | 图表说明文字 | 2025 | https://www.statista.com/statistics/548830/plant-load-factor-nuclear-stations-uk | [V2] |
| N16 | DESNZ DUKES 2020 / 2021 / 2022 / 2024 / 2026 第 5 章正文（逐年变化描述） | 第 5 章正文 | 各年 7 月 | DUKES 合集页：https://www.gov.uk/government/collections/digest-of-uk-energy-statistics-dukes ；第 5 章页：https://www.gov.uk/government/statistics/electricity-chapter-5-digest-of-united-kingdom-energy-statistics-dukes | [E] |
| N17 | Carbon Brief "Analysis: UK nuclear output falls to lowest level since 1982"（数据源注明为 BEIS Energy Trends 5/6 与 BM Reports） | 正文 | 2022-01-07 | https://www.carbonbrief.org/analysis-uk-nuclear-output-falls-to-lowest-level-since-1982/ | [V2] |
| X1 | DESNZ DUKES 2026 表 5.10 "Plant loads, demand and efficiency of major power producers"（xlsx） | 工作表 `5.10.B and 5.10.C`，表 5.10.B 行 "Nuclear stations" | 2026-07-30 | 见第 6 节 | [X] |
| X2 | DESNZ DUKES 2026 表 5.6 "Electricity fuel use, generation and supply"（xlsx） | 工作表 `5.6`，表 5.6.B（generated）、5.6.D（used on works）、5.6.E（supplied (gross)），行 "All generating companies / Nuclear" | 2026-07-30 | 见第 6 节 | [X] |
| X3 | DESNZ Energy Trends 表 5.1 "Fuel used in generation, electricity generated and supplied"，2026 年 9 月版（xlsx） | 工作表 `Quarter`，表 5.1b（generated）、5.1c（supplied），行 "All generating companies / Nuclear" | 2026-09 | 见第 6 节 | [X] |

### 1.2 全国总量（DESNZ 口径与 EDF 口径）

说明：DESNZ 有两种口径。"electricity generated" 是毛发电量，"electricity supplied" 是扣除厂用电后的上网量（ET 5.1 注 11："supplied net of electricity used in generation"；DUKES 5.6.E 的 "(gross)" 指尚未扣除抽水用电，核电不涉及抽水，所以两表核电值相同）。DUKES 5.10 的负荷率按 supplied 除以大型发电商（MPP）申报容量计算（5.10 注 6："All load factors are calculated using the supply and capacity of Major Power Producers"）。EDF 公布的 "UK nuclear output" 与 PRIS 的 supplied 是同一口径（见 1.3 节的逐年合计）。

**第二轮 DESNZ 官方值 [X]（X1、X2、X3）：**

| 年份 | DUKES 5.10.B 核电负荷率 (%)（supplied / MPP 容量） | DUKES 5.6.B 毛发电量 (TWh) | DUKES 5.6.D 厂用电 (TWh) | DUKES 5.6.E supplied (TWh) | ET 5.1c supplied，四季度合计 (TWh) | ET 5.1b generated，四季度合计 (TWh) |
|---|---|---|---|---|---|---|
| 2019 | **62.90** | 56.18 | 5.15 | **51.03** | 51.03 | 56.19 |
| 2020 | **57.19** | 50.24 | 4.16 | **46.08** | 46.08 | 50.24 |
| 2021 | **56.82** | 46.10 | 4.11 | **41.99** | 41.99 | 46.10 |
| 2022 | **72.15** | 47.40 | 3.88 | **43.52** | 43.59 | 47.40 |
| 2023 | **72.37** | 40.60 | 3.30 | **37.30** | 37.30 | 40.60 |
| 2024 | **72.26** | 40.59 | 3.25 | **37.34** | 37.34 | 40.59 |
| 2025（参考） | 64.04 | 35.85 | 2.85 | 33.00 | 33.00 | 35.85 |
| 2019–2024 均值 [D] | 65.62 | 46.85 | | 42.88 | | |
| 2022–2024 均值 [D] | 72.26 | | | 39.39 | | |

ET 5.1 逐季度值 [X]（TWh，Q1 / Q2 / Q3 / Q4）：

| 年份 | supplied（5.1c） | generated（5.1b） |
|---|---|---|
| 2019 | 12.631 / 11.869 / 12.346 / 14.186 | 13.906 / 13.067 / 13.593 / 15.619 |
| 2020 | 12.020 / 10.876 / 10.049 / 13.132 | 13.022 / 11.900 / 11.043 / 14.274 |
| 2021 | 10.583 / 10.424 / 9.705 / 11.278 | 11.554 / 11.491 / 10.733 / 12.326 |
| 2022 | 11.396 / 11.836 / 9.924 / 10.431 | 12.437 / 12.864 / 10.799 / 11.300 |
| 2023 | 8.965 / 9.293 / 9.640 / 9.398 | 9.761 / 10.126 / 10.486 / 10.223 |
| 2024 | 7.597 / 10.497 / 10.444 / 8.803 | 8.272 / 11.361 / 11.324 / 9.632 |

第一轮数字与 [X] 的对照（保留原文以便作者核对）：

| 年份 | 第一轮记录 | [X] 值 | 结论 |
|---|---|---|---|
| 2019 | 年度变化"下降 5.7%"（N16 [E]） | 毛发电量 56.18 TWh | 定性描述无冲突；负荷率 [NV] → 62.90% |
| 2020 | "下降 11%"（N16 [E]） | 50.24 TWh，较 2019 下降 10.6% [D] | 一致；负荷率 [NV] → 57.19% |
| 2021 | 约 46 TWh（N17 [V2]），"下降 7.6%"（N16 [E]） | 46.10 TWh，较 2020 下降 8.2% [D] | 发电量一致；降幅与 DUKES 2022 原文 7.6% 不同，可能是后续修订；负荷率 [NV] → 56.82% |
| 2022 | EDF 43.6 TWh，负荷率 77%（[E]） | supplied 43.52 TWh；DESNZ 负荷率 72.15% | 电量一致；EDF 的 77% 不是 DESNZ 口径（EDF 只计在运电站），不采用 |
| 2023 | 负荷率 72.4（N15 [V2]） | 72.37% | 一致 |
| 2024 | 毛发电量 40.6、负荷率 72.3（N13 [E]） | 40.59 TWh，72.26% | 一致 |

交叉检验 [D]：PRIS 逐堆 supplied 合计（见 1.3）与 DUKES 5.6.E 核电 supplied 的相对差为 2019 年 0.00%、2020 年 −0.89%、2021 年 −0.48%、2022 年 +0.02%、2023 年 −0.05%、2024 年 −0.12%。逐站 PRIS 数据与 DESNZ 全国合计相互印证。2024 年 37.34 TWh ÷（0.7226 × 8784 h）= 5.883 GW，即 DESNZ 负荷率的分母与 PRIS 在运参考功率之和 5,883 MWe 相同 [D]。2019–2024 年毛/净之比为 1.09–1.10 [D]。

为什么 2019–2021 年全国负荷率（57–63%）明显低于在运各站的 PRIS 负荷率 [D]：Dungeness B 在 2019–2021 年没有出力（PRIS 为净用电），Hunterston B 和 Hinkley Point B 有长时间停运，但它们的容量仍计入 MPP 分母。2022 年 Hinkley Point B 在停发前仍计入；2023–2024 年只剩在运 5 站，全国值 72.37% / 72.26% 与在运 5 站 PRIS 加权值 72.3% / 72.2% 一致。2019–2024 年全国均值 65.62% 因此**不能**直接代表在运电站；在运 5 站 2022 年按 PRIS 计为 76.6% [D]（39.47 TWh ÷ 5.883 GW ÷ 8760 h）。

**对 S8 验收标准（"核电对 Energy Trends 5.1 ±10%"）的含义：** 模型核电出力应与 ET 5.1c / DUKES 5.6.E 的 *supplied* 口径比较，不能与 *generated*（毛）口径比较。两者相差约 9–10%，几乎吃掉全部 ±10% 容差。

### 1.3 逐站逐年（IAEA PRIS，经 WNA 页面）[V] / 站级汇总 [D]

单堆原始值来自 N1，单位为 GWh supplied 和 PRIS 年负荷率（%）。站级 TWh 为各堆相加 [D]。站级负荷率 = 站 supplied ÷（PRIS 参考功率之和 × 当年小时数）[D]，闰年 2020 与 2024 取 8784 h。

| 电站（堆型） | PRIS 参考功率 MWe（各堆） | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|
| Heysham 1（AGR） | 485 + 575 = 1060 | 6.82 TWh / 73.4% | 6.11 / 65.7% | 5.76 / 62.0% | 6.33 / 68.2% | 6.46 / 69.6% | 5.77 / 62.0% | 5.23 / 56.3% |
| Hartlepool（AGR） | 590 + 595 = 1185 | 7.60 / 73.2% | 8.50 / 81.7% | 5.71 / 55.0% | 7.71 / 74.2% | 7.30 / 70.3% | 6.11 / 58.7% | 2.07 / 20.0% |
| Heysham 2（AGR） | 620 + 620 = 1240 | 10.29 / 94.7% | 8.94 / 82.1% | 5.79 / 53.3% | 7.91 / 72.8% | 7.56 / 69.6% | 8.56 / 78.6% | 6.61 / 60.8% |
| Torness（AGR） | 595 + 605 = 1200 | 10.07 / 95.8% | 9.85 / 93.5% | 6.68 / 63.5% | 7.16 / 68.1% | 8.28 / 78.8% | 7.97 / 75.6% | 8.63 / 82.1% |
| Sizewell B（PWR） | 1198 | 8.45 / 80.5% | 8.39 / 79.8% | 6.71 / 63.9% | 10.36 / 98.7% | 7.68 / 73.1% | 8.89 / 84.5% | 10.39 / 99.0% |
| Hunterston B（AGR，已关闭） | 490 + 495 | 1.04 / 12.0%* | 2.28 / 26.3%* | 6.42 / 74.4%* | 0.00 | — | — | — |
| Hinkley Point B（AGR，已关闭） | 485 + 480 | 6.95 / 82.2%* | 1.78 / 21.0%* | 4.80 / 56.8%* | 4.07 / 48.1%* | — | — | — |
| Dungeness B（AGR，已关闭） | 545 + 545 | −0.17（净用电） | −0.19 | −0.08 | — | — | — | — |
| **全国 supplied 合计** [D] | | **51.03** | **45.67** | **41.79** | **43.53** | **37.28** | **37.30** | **32.92** |
| 其中 AGR / PWR [D] | | 42.58 / 8.45 | 37.27 / 8.39 | 35.08 / 6.71 | 33.17 / 10.36 | 29.60 / 7.68 | 28.41 / 8.89 | 22.53 / 10.39 |

\* 关闭年份的站级负荷率按全年小时数计算 [D]。PRIS 自身在关闭年份按在役小时数计算负荷率：例如 Hinkley Point B1 2022 年 PRIS 值为 86.7% = 2140.11 GWh ÷（485 MW × 截至 8 月 1 日的 5088 h）[D]；Hunterston B1 2021 年 PRIS 值为 81.9%。建模时不要把 PRIS 关闭年份的负荷率直接当作全年值使用。

逐堆 PRIS 原值（GWh / LF%）[V]，供作者抽查：
- Sizewell B：2019 8452.10/80.5，2020 8393.47/79.8，2021 6709.39/63.9，2022 10357.17/98.7，2023 7676.68/73.2，2024 8887.22/84.4，2025 10386.31/99.0
- Torness 1：5006.74/96.1，4946.16/94.6，3090.34/59.3，4079.44/78.3，4225.69/81.1，3672.53/70.3，4083.39/78.3
- Torness 2：5059.93/95.5，4904.72/92.3，3589.01/67.7，3076.41/58.0，4055.74/76.5，4294.99/80.8，4542.31/85.7
- Heysham B1：5242.90/96.5，4993.67/91.7，2054.15/37.8，3697.11/68.1，4391.00/80.8，4249.11/78.0，2233.59/41.1
- Heysham B2：5042.29/92.8，3948.62/72.5，3733.11/68.7，4213.26/77.6，3168.39/58.3，4307.53/79.1，4374.02/80.5
- Heysham A1：3581.24/84.3，2648.85/62.2，2657.70/62.6，3567.83/84.0，2909.14/68.5，2932.77/68.8，2775.95/65.3
- Heysham A2：3233.76/64.2，3464.20/68.6，3103.23/61.6，2762.77/54.8，3553.41/70.6，2836.46/56.2，2449.08/48.6
- Hartlepool A1：4340.04/84.0，4581.72/88.4，2865.20/55.4，3574.26/69.2，4199.98/81.3，3129.03/60.4，843.68/16.3
- Hartlepool A2：3259.78/62.5，3919.40/75.0，2845.55/54.6，4132.36/79.3，3097.65/59.4，2985.52/57.1，1229.35/23.6
- Hunterston B1（2019–2021）：−78.20/0.0，1253.87/29.1，3177.15/81.9；Hunterston B2（2019–2022）：1116.54/25.8，1022.14/23.5，3246.09/74.9，0.00/0.0
- Hinkley Point B1（2019–2022）：2963.04/69.7，1275.63/29.9，2376.14/55.9，2140.11/86.7；Hinkley Point B2：3983.59/94.7，500.91/11.9，2426.04/57.7，1930.05/90.1
- Dungeness B1 与 B2（2019–2021）：两台机组页面显示完全相同的 −85.83、−92.66、−42.30 GWh。这很可能是厂用电按机组平分，需作者核对 PRIS 原页。

EDF 站级旁证 [V]（N3）：2025 年 Sizewell B 发电 10.4 TWh，负荷率 99%；Torness 发电 8.6 TWh，负荷率 82%。两者都与上表 PRIS 汇总一致。2025 年降幅主要来自 Hartlepool 的长时间停运（N7）[V]。

**容量口径警示 [V]/[D]：** PRIS 参考功率与 EDF 站页面容量（N5）不完全一致。Heysham 1 在 PRIS 中为 1060 MW，EDF 为 1155 MW；Heysham 2 为 1240 对 1230；Torness 为 1200 对 1190。Hartlepool 均为 1185，Sizewell B 均为 1198。仓库 `gridform_core/data/nuclear/value_uk_nuclear_policy_v1.json` 使用 EDF 容量。若沿用 EDF 容量，负荷率必须按 EDF 容量重新折算。例如 Heysham 1 2024 年：5.77 TWh ÷（1.155 GW × 8784 h）= 56.9%，而 PRIS 口径为 62.0% [D]。

### 1.4 按堆型的统计 [D]

| 指标（2019–2024，按全年计） | AGR（仍在运的 4 座站合计） | PWR（Sizewell B） |
|---|---|---|
| 逐年负荷率 2019 / 2020 / 2021 / 2022 / 2023 / 2024 | 84.7 / 81.2 / 58.3 / 70.9 / 72.1 / 69.0 % | 80.5 / 79.8 / 63.9 / 98.7 / 73.1 / 84.5 % |
| 2019–2024 均值（最小，最大） | 72.7%（58.3，84.7） | 80.1%（63.9，98.7） |
| 2025（参考） | 54.9% | 99.0% |
| 各站 2019–2024 均值 | Heysham 1 66.8%；Hartlepool 68.9%；Heysham 2 75.2%；Torness 79.2% | 80.1% |

以上均为 PRIS 参考功率口径。

### 1.4a 各站 2019–2024 平均负荷率（A10 所需表；PENDING AUTHOR REVIEW）

A10 规定：修正口径下各站用自己的 2019–2024 年平均负荷率（PRIS 参考功率口径）作为固定值，退役按月份折算。DESNZ 不公布逐站发电量或负荷率（DUKES 5.10 只有全国 "Nuclear stations" 一行），所以逐站值只能来自 PRIS（N1 [V]）。第二轮用 DUKES 5.6.E 全国 supplied 对 PRIS 逐堆合计做了校核（1.2 节），2019–2024 年各年相对差都在 0.9% 以内。

| 电站（堆型） | PRIS 参考功率 (MWe) | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | **2019–2024 算术均值** | 电量加权均值 | 最小 / 最大 | 换算到 EDF 容量的等电量值（EDF MW） |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Heysham 1（AGR） | 1060 | 73.4 | 65.7 | 62.0 | 68.2 | 69.6 | 62.0 | **66.80%** | 66.80% | 62.0 / 73.4 | 61.31%（1155） |
| Hartlepool（AGR） | 1185 | 73.2 | 81.7 | 55.0 | 74.2 | 70.3 | 58.7 | **68.86%** | 68.86% | 55.0 / 81.7 | 68.86%（1185） |
| Heysham 2（AGR） | 1240 | 94.7 | 82.1 | 53.3 | 72.8 | 69.6 | 78.6 | **75.17%** | 75.18% | 53.3 / 94.7 | 75.78%（1230） |
| Torness（AGR） | 1200 | 95.8 | 93.5 | 63.5 | 68.1 | 78.8 | 75.6 | **79.20%** | 79.20% | 63.5 / 95.8 | 79.87%（1190） |
| Sizewell B（PWR） | 1198 | 80.5 | 79.8 | 63.9 | 98.7 | 73.1 | 84.5 | **80.09%** | 80.09% | 63.9 / 98.7 | 80.09%（1198） |
| 在运 4 座 AGR 合计 | 4685 | 84.7 | 81.2 | 58.3 | 70.9 | 72.1 | 69.0 | **72.71%** | | 58.3 / 84.7 | |
| 参考：DESNZ 全国（DUKES 5.10.B）[X] | MPP 申报容量 | 62.90 | 57.19 | 56.82 | 72.15 | 72.37 | 72.26 | 65.62% | | | 2022–2024 均值 72.26% |

计算方法 [D]：逐年负荷率 = 站 supplied（各堆 PRIS GWh 之和）÷（PRIS 参考功率之和 × 当年小时数），闰年 2020、2024 取 8784 h；"算术均值"为 6 个年值的平均；"电量加权均值" = 6 年 supplied 之和 ÷（参考功率 × 6 年小时数之和）；"等电量值" = 算术均值 × PRIS MW ÷ EDF MW，即仓库 `value_uk_firm_availability_v1.json` 中 `pris_load_factor × pris_reference_mw / model capacity` 的结果。计算脚本：scratchpad `refstats/calc.py`。

与仓库参数表的对照：`gridform_core/data/nuclear/value_uk_firm_availability_v1.json` 中的 `pris_load_factor`（0.668 / 0.689 / 0.752 / 0.792 / 0.801）与上表算术均值四舍五入到 3 位小数后一致，本轮**无需改值**。`national_aggregate` 0.723 与 DESNZ 2022–2024 均值 72.26% 一致；若改用 2019–2024 全国均值则为 65.62%，但该均值受已退役电站拖低（见 1.2 节），不建议用于在运或新建机组。

### 1.5 停运规律 [V]/[E]

| 堆型 | 规律 | 来源与等级 |
|---|---|---|
| PWR（Sizewell B） | 换料与检修停运 "every 18 months"，与 National Grid 提前协调；2014 年那次约 6 周 | N9 [V] |
| PWR（Sizewell B） | 每次换料约更换三分之一燃料组件 | 搜索摘录（ONR PAR）[E] |
| PWR（Sizewell B） | 由此出现"有停运年 / 无停运年"交替：2022 年 98.7%、2025 年 99.0%（无大修）；2021 年 63.9%、2023 年 73.1%（有大修） | N1 [V]，解读 [D] |
| AGR | 定期停堆（statutory outage）受场址许可条件 LC 30 约束；Torness 的间隔为 "every three years"，Heysham 2 的维护计划为距上次启动许可 "maximum period of three calendar years" | N10 [E]（ONR docx 未打开） |
| AGR | Torness 2 号堆 2026 年法定停运编号 S13R2，2026 年 2 月检查 | N11 [V] |
| AGR | 1988 年起暂停满功率不停堆换料，此后只在部分负荷或停堆状态下换料 | Wikipedia "Advanced gas-cooled reactor" [V2] |
| AGR | Hartlepool 和 Heysham 1 须停堆换料；Torness 和 Heysham 2 原设计低功率在线换料，后因换料机部件改造暂停在线换料，改为停堆换料（至少到 2022 年） | 搜索摘录（EDF URD / NEI Magazine）[E] |
| AGR | Hartlepool 机组降负荷运行，以限制锅炉温度 | N12 [V] |

### 1.6 退役与寿期（截至 2026-10-06）

| 电站 | 堆型 | 最终停发 / 当前计划停发 | 来源与等级 |
|---|---|---|---|
| Dungeness B | AGR ×2 | 2021-06-07 转入卸料阶段（PRIS 显示 2019 年起已无出力） | N5（EDF 站页）[V]；N1 [V] |
| Hunterston B | AGR ×2 | 3 号堆 2021-11-26，4 号堆 2022-01-07 | N1（PRIS 永久停堆日期）[V] |
| Hinkley Point B | AGR ×2 | 2022 年 8 月停发（PRIS：B1 为 2022-08-01，B2 为 2022-07-06） | N5 [V]；N1 [V] |
| Heysham 1 | AGR ×2 | **2030 年 3 月** | N4 [V]；N5 站页写 "2030" [V] |
| Hartlepool | AGR ×2 | **2030 年 3 月** | N4 [V]；N5 [V] |
| Heysham 2 | AGR ×2 | **2030 年 3 月** | N6 [V]；N3 [V]；N5 写 "2030" [V] |
| Torness | AGR ×2 | **2030 年 3 月** | N6 [V]；N3 [V]；N5 写 "2030" [V] |
| Sizewell B | PWR | **2055 年**（原定 2035 年；2026-07-08 政府宣布延寿 20 年，2035 年起 CfD 价格 £70.50/MWh，2025 年价格） | N8 [V]；N5 写 "Estimated decommissioning date: 2055" [V] |

Heysham 1 / Hartlepool 的寿期多次延长 [V]：N2（2024-01）延到 2026 年 3 月；N6 称 2024 年 12 月延到 2027 年 3 月、2025 年 9 月再延到 2028 年 3 月；N4（2026-07-22）延到 2030 年 3 月。Heysham 2 / Torness 在 N2 中为 2028 年 3 月，2024 年 12 月起为 2030 年 3 月（N6）。

建模含义 [D]：2030 年不是闰年，1–3 月共 90 天，即 90 × 48 = 4320 个半小时时段。"2030 年 3 月停发" 对应 2030 年第 4320 期起为 0，与计划 S8 中 "Heysham 1 从第 4320 期起为 0" 的测试一致。仓库 `value_uk_nuclear_policy_v1.json`（evidence_as_of 2026-08-31）中四座 AGR 的 announced_generation_end 已与此一致。Sizewell B 的 2055 也一致。

### 1.7 建议取值（PENDING AUTHOR REVIEW，供 S8 使用；仅为建议，非结论）

- **站级年负荷率：** 建议使用 1.3 节各站 2019–2024 均值（Heysham 1 66.8%、Hartlepool 68.9%、Heysham 2 75.2%、Torness 79.2%、Sizewell B 80.1%，PRIS 参考功率口径）[D]。若模型容量采用 EDF 数值，需要按 1.3 节的警示重新折算。另一种做法是按堆型取值：AGR 72.7%，PWR 80.1% [D]。
- **年际波动：** 观测区间 AGR 为 58–85%，PWR 为 64–99% [D]。是否用随机或固定年份序列由作者决定。
- **验收比较：** 应使用 supplied（净）口径，见 1.2 节。第二轮给出的比较基准 [X]：ET 5.1c 2019–2024 年 supplied 为 51.03 / 46.08 / 41.99 / 43.59 / 37.30 / 37.34 TWh，DUKES 5.6.E 为 51.03 / 46.08 / 41.99 / 43.52 / 37.30 / 37.34 TWh。模型的运行年对应在运 5 站（2025 年后），因此建议与 2023–2024 年（只剩在运 5 站）的 supplied 约 37.3 TWh 对比，而不是与含退役电站的 2019–2021 年对比。
- **A10 采用值：** 见 1.4a 节（与现参数表一致，待作者审核）。

---

## 2. 英国径流式（natural flow）水电（PENDING AUTHOR REVIEW → 作者已审核，A14）

> A14：年负荷率取 0.3487，月度形状取 2.4 节阶梯形状；F2 单元已写入参数表（`p05.hydro-dukes-load-factor`）。GBP1 2000 MW 年发电 6.10 TWh，比 DUKES 6.2 2019–2024 均值 5.77 TWh 高 5.8%（±15% 以内）。

### 2.1 来源清单

| ID | 出版方 / 文献 | 表或节 | 年份 | URL | 等级 |
|---|---|---|---|---|---|
| H1 | DESNZ（BEIS）DUKES 2021 第 6 章 | 第 6 章正文（水电） | 2021-07-29 | https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/1006819/DUKES_2021_Chapter_6_Renewable_sources_of_energy.pdf | [E] |
| H2 | DESNZ DUKES 2024 第 6 章 / Chapters 1–7 | 第 6 章正文 | 2024-07 | 第 6 章页：https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes | [E] |
| H3 | DESNZ DUKES 2025 第 6 章 | 第 6 章正文 | 2025-07-31 | https://assets.publishing.service.gov.uk/media/688a193f6478525675739024/DUKES_2025_Chapter_6.pdf | [E] |
| H4 | Statista "Load factor of electricity from hydropower in the UK 2010–2023" | 图表说明 | 2025-01-14 | https://www.statista.com/statistics/555705/hydro-electricity-load-factor-uk | [V2] |
| H5 | DESNZ DUKES 第 6 章页面（列出 DUKES 6.2 发电量、DUKES 6.3 负荷率两张 xlsx） | 表 6.2、6.3 | 2026-07-30 更新 | https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes | [V]（第一轮只核实表存在；第二轮见 X4、X5） |
| X4 | DESNZ DUKES 2026 表 6.2 "Capacity of, and electricity generated from, renewable sources"（xlsx） | 工作表 `6.2`："Installed Capacity (MW)"（年末值）与 "Generation (GWh)" 两表，行 "Hydro:"、"Small scale"、"Large scale"（不含抽水蓄能） | 2026-07-30 | 见第 6 节 | [X] |
| X5 | DESNZ DUKES 2026 表 6.3 "Load factors for renewable electricity generation"（xlsx） | 工作表 `6.3`：上表 "based on average of beginning and end of year capacity"（标准口径，注 1），下表 "for schemes operating on an unchanged configuration basis"（不变配置口径，注 2） | 2026-07-30 | 见第 6 节 | [X] |
| X6 | DESNZ Energy Trends 表 6.1 "Renewable electricity capacity and generation"，2026 年 9 月版（xlsx） | 工作表 `Quarter`："ELECTRICITY GENERATED (GWh)" 与 "LOAD FACTORS (%)" 两表，行 "Hydro"；容量表行 "Small scale hydro"、"Large scale hydro" | 2026-09 | 见第 6 节 | [X] |
| X2/X3 | 同 1.1 节（DUKES 5.6、ET 5.1 的 "Hydro (natural flow)" 行，用于交叉检验） | | | | [X] |

### 2.2 年发电量与负荷率

**第二轮 DESNZ 官方值 [X]（X4、X5、X2）：**

| 年份 | 年末装机 MW（合计 / 小型 / 大型，DUKES 6.2） | 发电量 GWh（合计 / 小型 / 大型，DUKES 6.2） | DUKES 5.6.E supplied (GWh) | 负荷率 %，标准口径（合计 / 小型 / 大型，DUKES 6.3 上表） | 负荷率 %，不变配置口径（合计 / 小型 / 大型，DUKES 6.3 下表） |
|---|---|---|---|---|---|
| 2018（仅作期初容量） | 1877.19 / 404.01 / 1473.18 | 5443.27 | | | |
| 2019 | 1879.86 / 406.69 / 1473.18 | **5932.90** / 1392.59 / 4540.31 | 5865.39 | **36.05** / 39.22 / 35.18 | **35.54** / 38.74 / 35.18 |
| 2020 | 1885.27 / 414.59 / 1470.68 | **6878.00** / 1559.12 / 5319.08 | 6757.57 | **41.59** / 43.22 / 41.14 | **41.27** / 42.83 / 41.10 |
| 2021 | 1890.16 / 419.48 / 1470.68 | **5418.00** / 1289.08 / 4129.29 | 5309.74 | **32.77** / 35.29 / 32.05 | **32.25** / 35.39 / 31.90 |
| 2022 | 1890.83 / 420.15 / 1470.68 | **5068.00** / 1115.54 / 3952.46 | 4984.84 | **30.60** / 30.33 / 30.68 | **30.51** / 30.23 / 30.59 |
| 2023 | 1895.85 / 418.77 / 1477.08 | **5609.00** / 1130.60 / 4478.40 | 5495.22 | **33.82** / 35.50 / 33.34 | **33.56** / 38.33 / 32.89 |
| 2024 | 1895.85 / 418.77 / 1477.08 | **5731.00** / 1048.28 / 4682.72 | 5623.82 | **34.41** / 38.80 / 33.17 | **34.43** / 37.77 / 33.44 |
| 2025（参考） | 1895.85 / 418.77 / 1477.08 | 5386.00 | 5279.22 | 32.34 | 32.43 |
| **2019–2024 均值** [D] | | **5772.8** | 5672.8 | **34.87** / 37.06 / 34.26 | **34.59** / 37.22 / 34.18 |
| 2020–2024 均值 [D] | | 5740.8 | | 34.64 | 34.40 |

口径说明 [X]：
- 标准口径（DUKES 6.3 注 1）："based on the average of capacity at the start of the year and capacity at the end of the year"，即发电量 ÷（期初与期末装机的平均 × 当年小时数）。用 DUKES 6.2 的装机与发电量按此式复算 [D]，2019–2024 年合计行与 DUKES 6.3 全部相符（差 ≤ 0.01 pp）。大型水电 2023、2024 年复算值为 34.69%、36.09%，与表中 33.34%、33.17% 不符，原因不明（可能是 DESNZ 对年内新增或改造机组的处理），作者若要用分规模的值需注意。
- 不变配置口径（注 2）："based on the generation of sites whose capacity did not change throughout the year"，只统计年内容量不变的站点。英国水电装机 2019–2024 年几乎不变（1880–1896 MW），所以两种口径相差不超过 0.6 pp，均值相差 0.28 pp。
- 覆盖范围：DUKES 6.2 的水电装机不含抽水蓄能（注 2 "Excluding pumped storage stations"），含小型（嵌入式）水电约 0.4 GW。DUKES 5.6 的 "Hydro (natural flow)" 合计发电量与 DUKES 6.2 相同（2020 年 5.6.A 为 6880.7、5.6.B 为 6878，差异为 DESNZ 原表取整）。
- 合计负荷率与 DUKES 5.10 注 8 的口径一致：容量未按间歇性降额（DUKES 6.2 的 de-rated 容量另列，水电降额系数 0.365，本文不用）。

第一轮数字与 [X] 的对照：

| 年份 | 第一轮记录 | [X] 值 | 结论 |
|---|---|---|---|
| 2019 | ≈ 5.9 TWh（[D]，倒推） | 5.933 TWh；负荷率 36.05% | 一致；负荷率 [NV] 已补齐 |
| 2020 | 6.8 TWh（H1 [E]） | 6.878 TWh；41.59% | 一致；负荷率已补齐 |
| 2021 | [NV] | 5.418 TWh；32.77% | 已补齐 |
| 2022 | ≈ 5.6 TWh（[D]，由"2023 年下降 2.2% 至 5.5 TWh"倒推） | 5.068 TWh；30.60% | **不一致**。新版 2023 年比 2022 年增加 10.7%，原搜索摘录很可能张冠李戴。以 [X] 为准，第一轮倒推值作废 |
| 2023 | 5.5 TWh（H2 [E]）；5,538 GWh、33.4%（H4 [V2]） | 5.609 TWh；33.82% | 小幅不同，DUKES 2026 对 2023–2024 有修订（封面 "The revisions period is 2023 to 2024"） |
| 2024 | 5.8 TWh（H3 [E]） | 5.731 TWh；34.41% | 小幅修订 |

与模型的量级对比 [D]（只作参考，验收由作者在 GBP1 全年运行后进行）：仓库参数表注明 GBP1 机组的径流水电容量为 2000 MW。按 2019–2024 标准口径均值 34.87% 计，年电量 = 2000 × 8760 × 0.3487 ≈ 6.11 TWh，比 DUKES 2019–2024 均值 5.77 TWh 高 5.8%；按现参数表的 0.334 计为 5.85 TWh，高 1.4%。两者都在 S8 的 ±15% 之内。差异主要来自模型容量 2000 MW 与 DUKES 约 1.89 GW 之差。

### 2.3 月度 / 季度形状

**季度 [X]（X6，ET 6.1 `Quarter` 工作表，"Hydro" 行；与 ET 5.1b "Hydro (natural flow)" 季度值相同）：**

| 年份 | 发电量 GWh（Q1 / Q2 / Q3 / Q4） | 季度负荷率 %（Q1 / Q2 / Q3 / Q4，ET 6.1 注 12：按季初、季末容量平均） | 四季度合计 GWh（= DUKES 6.2） | 季度形状系数 [D]（Q1 / Q2 / Q3 / Q4） |
|---|---|---|---|---|
| 2019 | 1891.3 / 831.8 / 1406.1 / 1803.7 | 46.69 / 20.33 / 33.94 / 43.47 | 5932.9 | 1.293 / 0.562 / 0.940 / 1.206 |
| 2020 | 2476.5 / 1011.8 / 1185.3 / 2204.4 | 60.29 / 24.60 / 28.47 / 52.95 | 6878.0 | 1.448 / 0.592 / 0.686 / 1.275 |
| 2021 | 1772.5 / 1001.2 / 564.5 / 2079.9 | 43.50 / 24.28 / 13.53 / 49.84 | 5418.0 | 1.327 / 0.741 / 0.413 / 1.523 |
| 2022 | 1856.0 / 880.0 / 644.5 / 1687.5 | 45.46 / 21.32 / 15.44 / 40.43 | 5068.0 | 1.485 / 0.696 / 0.505 / 1.321 |
| 2023 | 1839.4 / 844.9 / 1060.2 / 1864.5 | 44.98 / 20.41 / 25.33 / 44.54 | 5609.0 | 1.330 / 0.604 / 0.750 / 1.319 |
| 2024 | 2043.6 / 1077.7 / 1116.4 / 1493.2 | 49.36 / 26.03 / 26.67 / 35.67 | 5731.0 | 1.434 / 0.756 / 0.775 / 1.037 |
| **2019–2024 均值** [D] | | | | **1.386 / 0.659 / 0.678 / 1.280** |
| 区间（最小–最大）[D] | | | | 1.29–1.49 / 0.56–0.76 / 0.41–0.94 / 1.04–1.52 |

形状系数定义 [D]：季度 q 的系数 =（季度发电量 ÷ 季度小时数）÷（年发电量 ÷ 年小时数），即季度平均出力相对全年平均出力的倍数。按 365 天年的季度小时数加权，均值系数的加权平均为 0.9996。计算脚本：scratchpad `refstats/hq.py`。

**月度：仍为 [NV]。** 本次授权下载的 6 个文件（DUKES 5.6、5.10、6.2、6.3，ET 5.1、6.1）都只有年度或季度数据，没有月度水电发电量。月度值需要另取（例如 DESNZ 月度电力统计表或 Elexon BMRS 的 NPSHYD 半小时数据），不在 A11 授权范围内，本次未下载。

### 2.4 建议取值（PENDING AUTHOR REVIEW）

- **年负荷率：** 建议取 DUKES 6.3 标准口径 2019–2024 均值 **34.87%（0.3487）**[D]。不变配置口径均值 34.59%，两者只差 0.28 pp，因为水电装机几乎不变；若作者偏好剔除容量变动影响，可用 0.3459。逐年范围 30.60–41.59%。现参数表用的是 2023 单年二手值 0.334，作者审核后可替换（本单元没有改参数表）。
- **月度形状（由季度推出的阶梯形状）[D]：** 同一季度的 3 个月取相同系数，并归一化为 12 个月算术均值正好为 1（满足 `firm_availability.py` 对 `monthly_shape` 的检查）：

  `[1.3851, 1.3851, 1.3851, 0.6582, 0.6582, 0.6582, 0.6776, 0.6776, 0.6776, 1.2791, 1.2791, 1.2791]`

  这 12 个数之和为 12.0000。按天数加权的均值为 0.9988，即按月历使用时年电量比"负荷率 × 8760 h"低约 0.1%，可以忽略。季度内部的逐月变化未知（见 2.3 节），阶梯形状会低估冬季内部和夏季内部的差别。夏季（Q3）的年际离散最大（0.41–0.94），固定形状无法反映干旱年。
- **验收比较：** S8 的"水电对 DUKES ±15%"建议与 DUKES 6.2 合计发电量比较（2019–2024 均值 5.77 TWh，或运行年对应年份的值），不要与 DUKES 5.6.E 的 supplied（扣厂用电后约低 1.7%）混用。

---

## 3. 风电与光伏文献损耗系数（PENDING AUTHOR REVIEW → 损耗系数已由作者认可，A9）

### 3.0 适用对象（来自代码，非文献）

- **风电：** VALUE 用 ERA5 100 m 风速（`u100,v100` 或 `wind_speed`）的格点值，乘以单台机组的分段三次功率曲线。陆上切入 3 m/s、额定 9.7 m/s、切出 25 m/s；海上分别为 3、10.5、30 m/s。见 `gridform_core/doctoral_weather.py:79-88,149-161`。没有尾流、可用率、电气损耗，也没有功率曲线平滑。因此下列损耗系数作用于 "单机自由流毛出力"。
- **光伏：** CF = ssrd ÷ 3,600,000，即水平面总辐照度（GHI，kWh/m²/h），相当于以 1 kW/m² 为额定（`doctoral_weather.py:143-147`）。没有温度修正，也没有倾角/朝向换算。文献中的 performance ratio（PR）是相对于**组件平面辐照度（POA）**定义的，并且已包含温度损失。把 PR 乘在 GHI 上会遗漏倾角增益，因此结果大概率偏低。英国倾斜面相对水平面的年增益**本次未核实 [NV]**，需在方法学文档中披露。
- **再分析偏差不是损耗：** Staffell & Pfenninger（2016）发现，未校正的 MERRA 再分析会把西北欧风电出力 "overestimating wind output by 50%"（W9 [V]）。Q15 决定不做统计标定，所以损耗系数无法消除 ERA5 自身偏差。应报告所得 CF，并与 DUKES 6.3 负荷率对照披露。

### 3.1 来源清单

| ID | 文献 | 卷期 / DOI | 用途 | URL | 等级 |
|---|---|---|---|---|---|
| W1 | Barthelmie R.J. 等，"Modelling and measuring flow and wind turbine wakes in large wind farms offshore"，*Wind Energy*（同行评审） | 12(5):431–444，2009，doi:10.1002/we.348 | 海上尾流 | https://dspace.lib.ntua.gr/xmlui/handle/123456789/19754?show=full | [V] |
| W2 | Hahmann A. 等（DTU），"Mapping the future offshore wind potential in Denmark: Assessment of 2050 wind farm scenarios"，EGU26-23045（会议摘要，**未经同行评审**） | 2026-03-14 | 海上集群尾流 | https://meetingorganizer.copernicus.org/EGU26/EGU26-23045.html | [V] |
| W3 | Warder S.C. & Piggott M.D.，"Mapping global offshore wind wake losses, layout optimisation potential, and climate change effects"（arXiv 预印本，**未经同行评审**） | arXiv:2408.15028v2，2025 | 海上尾流 | https://arxiv.org/html/2408.15028v2 | [V] |
| W4 | Simley E. 等（NREL），"A Comparison of Pre-Construction and Operational Wake Loss Estimates for Land-Based Wind Plants"，*Wind Energy*（同行评审） | 28(11) e70067，2025，doi:10.1002/we.70067；NREL/JA-5000-87128 | 陆上尾流 | https://research-hub.nlr.gov/en/publications/a-comparison-of-pre-construction-and-operational-wake-loss-estima/ | [V] |
| W5 | Lee J.C.Y. & Fields M.J.（NREL），"An overview of wind-energy-production prediction bias, losses, and uncertainties"，*Wind Energy Science*（同行评审） | 6:311–365，2021，doi:10.5194/wes-6-311-2021 | 损耗总量与分类 | https://wes.copernicus.org/articles/6/311/2021/ | [V] |
| W6 | Conroy N., Deane J.P., Ó Gallachóir B.P.，"Wind turbine availability: Should it be time or energy based? – A case study in Ireland"，*Renewable Energy*（同行评审） | 36(11):2967–2971，2011，doi:10.1016/j.renene.2011.03.044 | 可用率 | https://ideas.repec.org/a/eee/renene/v36y2011i11p2967-2971.html | [V] |
| W7 | ORE Catapult 与 The Crown Estate，SPARTA Portfolio Review 2017/18 新闻稿（英国海上风电基准，覆盖英国在运海上风电装机的 77%） | 报告期 2017-04-01 至 2018-03-31 | 海上可用率（机构来源） | https://ore.catapult.org.uk/press-releases/new-sparta-report-provides-insights-into-the-performance-of-its-uk-offshore-wind-farm-portfolio | [V] |
| W8 | Colmenar-Santos A. 等，"Simplified Analysis of the Electric Power Losses for On-Shore Wind Farms Considering Weibull Distribution Parameters"，*Energies*（同行评审） | 7(11):6856–6885，2014，doi:10.3390/en7116856 | 电气损耗 | https://doi.org/10.3390/en7116856 | 书目信息 [V]（DOAJ / UNED）；数字为正文摘录 [E] |
| W9 | Staffell I. & Pfenninger S.，"Using bias-corrected reanalysis to simulate current and future wind power output"，*Energy*（同行评审） | 114:1224–1239，2016，doi:10.1016/j.energy.2016.08.068 | 再分析偏差披露 | https://ideas.repec.org/a/eee/energy/v114y2016icp1224-1239.html | [V] |
| W10 | Gustavsen B. & Mo O.，"Variable Transmission Voltage for Loss Minimization in Long Offshore Wind Farm AC Export Cables"（arXiv；投稿 IEEE Trans. Power Delivery） | arXiv:1602.02982，2016 | 海上送出电缆损耗（定性） | https://arxiv.org/abs/1602.02982 | [V] |
| S1 | Taylor J., Leloux J., Everard A., Briggs J., Hall L.M.H., Buckley A.（Sheffield Solar），"Performance of distributed PV in the UK: a statistical analysis of over 7000 systems"，31st EU PVSEC 会议论文 | 2015，Hamburg | 英国 PR | 搜索摘录（作者页：https://sheffield.academia.edu/JamieTaylor） | [E] |
| S2 | Dhimish M.，"Thermal impact on the performance ratio of photovoltaic systems: a case study of 8000 photovoltaic installations"，*Case Studies in Thermal Engineering*（同行评审） | 2020，doi:10.1016/j.csite.2020.100693 | 英国 PR | https://eprints.whiterose.ac.uk/id/eprint/177724/ | [V] |
| S3 | Dhimish M., Schofield N., Attya A.，"Insights on the Degradation and Performance of 3000 Photovoltaic Installations of Various Technologies Across the United Kingdom"，*IEEE Trans. Industrial Informatics*（同行评审） | 2021，doi:10.1109/TII.2020.3022762 | 英国 PR | https://eprints.whiterose.ac.uk/id/eprint/177737 | [V] |
| S4 | Leloux J., Narvarte L., Trebosc D.，"Review of the performance of residential PV systems in France"，*Renewable and Sustainable Energy Reviews*（同行评审） | 16(2):1369–1376，2012，doi:10.1016/j.rser.2011.10.018 | PR 下限参考 | https://ideas.repec.org/a/eee/rensus/v16y2012i2p1369-1376.html | [V]（比利时 78% 为 [E]） |
| S5 | European Commission JRC，PVGIS 5 用户手册（"system loss"） | 在线版（PVGIS 5.3） | 机构默认系统损耗 | https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/getting-started-pvgis/pvgis-user-manual_en | [V] |

### 3.2 文献数值

| 损耗项 | 文献数值 | 来源与等级 |
|---|---|---|
| 海上尾流 | 大型海上风场平均尾流损失为总出力的 10–20%（"of the order of 10 to 20%"） | W1 [V] |
| 海上尾流 | 丹麦 2030 年情景 11–20%，2050 年情景 13–24%（集群化后更高） | W2 [V]（会议摘要） |
| 海上尾流 | 欧洲海域 10×10 标准风场约 8.3%；资源越差的地点，百分比损失越大 | W3 [V]（预印本） |
| 陆上尾流 | 北美 5 座陆上风场经长期修正后的运行尾流损失为 1.9–6.4%，均值 4% | W4 [V] |
| 损耗总量 | 8 项研究报告的预测总损耗为 9.5–22.5%；尾流是最大的单项，且估计离散度大 | W5 [V] |
| 电气损耗 | "routine energy reduction with high certainty and relatively low magnitude"（定性） | W5 [V] |
| 电气损耗（陆上） | 风场年电气损耗约 2–3% | W8 [E] |
| 电气损耗（海上） | 长距离交流送出电缆损耗显著；调压可使 200 km、220 kV 案例的年损耗降低 9%。**没有给出绝对值** | W10 [V]；**海上绝对值 [NV]** |
| 可用率（时间口径） | 行业保证值通常为 97%；爱尔兰案例中时间口径不可用率 3%，但对应的**能量损失达 11%** | W6 [V] |
| 可用率（海上，能量口径） | 英国 SPARTA 组合 2017/18 年度，机组平均提取了 94.5% 的可用风能 | W7 [V] |
| 光伏 PR（英国） | 7000 多套英国户用系统年 PR 均值 83%（标准差 7%） | S1 [E] |
| 光伏 PR（英国） | 8000 套英国系统月度 PR 平均 85.74% | S2 [V] |
| 光伏 PR（英国） | 3000 套英国系统：单晶硅 87.97%，多晶硅 85.08%，碲化镉 83.55% | S3 [V] |
| 光伏 PR（法国，参考） | 户用系统 PR 均值 76%（比利时 78% [E]） | S4 [V] |
| 光伏系统损耗（机构默认） | PVGIS 默认 "overall losses" 14%（电缆、逆变器、污渍、老化），**不含**温度与辐照效应（另行建模） | S5 [V] |

### 3.3 建议中心值与区间（PENDING AUTHOR REVIEW；每项都是"选择"，不是文献结论）

| 项目 | 陆上：中心值（区间） | 海上：中心值（区间） | 选择理由 |
|---|---|---|---|
| 尾流损失 | 5%（2–7%） | 12%（8–20%） | 陆上：W4 运行均值 4%，区间 1.9–6.4%；英国陆上风场规模较小，取略高于均值的 5%。海上：W1 为 10–20%，W3 欧洲代表值 8.3%，W2 为 2030 集群情景 11–20%；英国 Hornsea / Dogger Bank 等大型集群取 12%。 |
| 可用率（能量口径） | 0.97（0.89–0.97） | 0.945（单一来源，区间 [NV]） | 陆上：W6 的 97% 行业标准（时间口径），能量口径可能更低，最低到 W6 案例的 89%。海上：W7 英国组合实测 94.5%。海上区间没有第二个来源，建议作者另定敏感性，例如 ±2.5 pp，并标为"非文献值"。 |
| 电气损耗 | 2%（2–3%） | **[NV]**（暂按陆上 2–3% 作为下限处理） | W8 [E]；海上没有核实到绝对值。 |
| **合计乘子**（= (1−尾流) × 可用率 × (1−电气)）[D] | **0.903**（总损耗 9.7%；区间 0.803–0.932） | **约 0.81**（总损耗约 19%，电气按 2–3% 计） | 均落在 W5 的 9.5–22.5% 总损耗区间内。 |
| 光伏 PR | 0.83（0.76–0.88） | — | 中心值取英国大样本均值（S1 83%，S2 / S3 为 84–88%）；下限为 S4 的法国 76%，上限为 S3 的单晶硅 88%。 |

**需要作者裁定的冲突：**
1. **合计幅度：** P0_DECISIONS Q15 写的是"合计约 10–15%"。陆上 9.7% 与之相符。海上约 19% **超出**该范围，主要来自海上尾流文献值。作者需要在两者之间选择：(a) 接受海上约 19%；(b) 把海上尾流压到约 8%（W3 下限），使合计约 15%。
2. **光伏 PR 的基准：** PR 以组件平面辐照度定义，VALUE 用的是水平面 GHI。仅乘 PR 会低估出力。倾角增益未核实，按 Q15 也不能用统计负荷率做标定。建议在方法学文档中披露该偏差，并报告所得 CF。
3. **结果披露：** Q15 规定不做标定。应用上述系数后，应报告各技术的年 CF，并与 DUKES 6.3 负荷率并列展示，只作披露，不做拟合。对照值已在第二轮读取，见 3.4 节。

（第二轮补注：冲突 1 已由作者在 DECISIONS A9 裁定，接受海上合计约 19%，不受"10–15%"限制；修正口径 CF 偏高时保持现状、不做统计标定，但须与 DUKES 并列披露并写明原因。）

### 3.4 DUKES 风电、光伏负荷率对照列（A9 CF 披露用；PENDING AUTHOR REVIEW）

来源：X5（DUKES 2026 表 6.3）[X]；复算用 X4（DUKES 6.2）[X]。

| 年份 | 陆上风电：标准 / 不变配置 (%) | 海上风电：标准 / 不变配置 (%) | 光伏：标准 / 不变配置 (%) | 风电合计：标准 / 不变配置 (%) |
|---|---|---|---|---|
| 2019 | 26.52 / 26.21 | 40.54 / 39.57 | 10.74 / 11.16 | 32.04 / 31.38 |
| 2020 | 28.28 / 28.05 | 45.92 / 45.06 | 10.54 / 11.29 | 27.31* / 35.50 |
| 2021 | 23.44 / 23.30 | 37.75 / 38.09 | 9.93 / 10.64 | 22.84* / 29.80 |
| 2022 | 27.32 / 26.94 | 41.29 / 36.88 | 11.06 / 10.82 | 33.64 / 31.75 |
| 2023 | 25.06 / 24.56 | 39.49 / 40.43 | 10.50 / 10.58 | 32.05 / 31.98 |
| 2024 | 24.98 / 25.11 | 35.99 / 37.03 | 9.22 / 9.57 | 30.41 / 30.91 |
| 2025（参考） | 24.02 / 24.08 | 36.12 / 35.98 | 11.08 / 11.08 | 30.08 / 30.00 |
| **2019–2024 均值** [D] | **25.93** / 25.70 | **40.16** / 39.51 | **10.33** / 10.68 | 29.71* / 31.89 |
| 2020–2024 均值 [D]（与 GBP1 天气年份 2020–2024 对应） | 25.82 / 25.59 | 40.09 / 39.50 | 10.25 / 10.58 | 29.25* / 31.99 |

\* **DESNZ 原表疑点：** 风电合计行标准口径 2020 年 27.31%、2021 年 22.84% 与分项不符。用 DUKES 6.2 的装机与发电量按注 1 公式复算 [D]：风电合计 2020 年 35.62%、2021 年 29.52%，而陆上、海上、光伏、水电各行复算值都与表中相符（差 ≤ 0.3 pp）。合计行这两年很可能是 DESNZ 的发布错误。A9 的披露只用陆上、海上、光伏三个分项，不受影响，但不要引用合计行这两个值。

**A9 并列披露表（模型 CF 取自 `docs/methodology/drafts/0.4/p05b_corrected_data.md` 第 3 节与 M5-P0-5b 报告；DUKES 取标准口径）：**

| 技术 | 模型 CF：GBP1 public1，论文 v1 | 模型 CF：GBP1 public1，修正（v2 + 文献损耗） | DUKES 2019–2024 均值 | DUKES 2020–2024 均值 | 修正 CF ÷ DUKES 2020–2024 [D] |
|---|---|---|---|---|---|
| 陆上风电 | 0.4458 | 0.4026 | 0.2593 | 0.2582 | 1.56 |
| 海上风电 | 0.6028 | 0.4913 | 0.4016 | 0.4009 | 1.23 |
| 光伏 | 0.1201 | 0.0997 | 0.1033 | 0.1025 | 0.97 |

两者不是同口径，披露时须写明 [D]：
1. 模型 CF 是代表站点的等权平均，弃电之前，单机自由流功率曲线；DUKES 是实际发电量（已扣除弃风和约束调度减出力）除以全国装机。
2. 修正口径的陆上、海上风电仍明显偏高（约 1.6 倍和 1.2 倍），A9 认定的主要原因是 ERA5 100 m 风速偏差和单机自由流功率曲线（3.0 节）。代表站点的选址也可能偏向资源好的地点，本文未核实。
3. 光伏约为 DUKES 的 0.97 倍，与 3.3 节冲突 2 的判断一致：PR 乘在水平面 GHI 上，遗漏了倾角增益。
4. DUKES 光伏装机含大量户用小系统，其负荷率按估算出力计算（DUKES 6.2 注 8："estimated using a typical load factor"），精度低于风电。

**F2 补注（A13 倾斜面换算之后）：** 修正口径光伏 CF 由 0.0997 变为 **0.1065**，与 DUKES 2020–2024 均值之比由 0.97 变为 **1.04**；风电不变。同一组数字写入运行结果摘要的 `vre_capacity_factor_disclosure` 字段和参数表 `gridform_core/data/weather/value_uk_vre_cf_disclosure_v1.json`。

### 3.5 光伏倾斜面换算的模型选择（A13，F2 单元；PENDING AUTHOR REVIEW）

| 步骤 | 选择 | 出处 |
|---|---|---|
| 太阳位置 | Spencer（1971）赤纬、时差与日地距离修正；按时段中点（365 天 UTC 年）与站点经纬度计算 | Spencer 1971；Iqbal 1983；Duffie & Beckman 2013 |
| 直射/散射分解 | Erbs、Klein & Duffie（1982）逐时相关式，太阳常数 1361 W/m² | Erbs 等 1982；Kopp & Lean 2011 |
| 斜面换算 | Hay & Davies（1980），地面反照率 0.2 | Hay & Davies 1980；Duffie & Beckman 2013；Loutzenhiser 等 2007 |
| 倾角 | 朝南，Jacobson & Jadhav（2018）北半球最优倾角拟合式（51.5°N 约 36.0°；GBP1 各站 35.7–37.7°） | Jacobson & Jadhav 2018 |
| 适用范围 | 只用于 v2 时钟下的 ERA5 逐时累积量；VALUE 101 合成数据和 R029 public1（`ssrd` 无累积标记）不换算 | — |

GBP1 结果：各站 POA/GHI 1.05–1.10，年散射比例 0.63–0.75；倾角取纬度（A13 允许的另一种选择）时 CF 为 0.1012。增益偏小的主要原因是 GBP1 天气为 2020–2024 多年平均气候态（P6-09），晴空指数被平均抹平（伦敦能量加权 kt 0.47，最大 0.73），Erbs 式给出的散射比例偏高。上述文献的书目信息在 F2 中没有联网复核（F2 未获联网授权）。

---

## 4. 未完成与待作者处理事项（PENDING AUTHOR REVIEW）

1. ~~DESNZ DUKES 5.10、5.6、6.2 / 6.3、ET 5.1 / 6.1 的核电负荷率与水电负荷率 [NV]~~ **第二轮已补齐**（1.2、1.4a、2.2 节，[X]）。按 A11，补齐后的本表仍须作者再次审核。
2. 水电**季度**形状已补齐（2.3 节 [X]）；由季度推出的月度阶梯形状见 2.4 节 [D]。**逐月实测值仍为 [NV]**：授权的 6 个文件没有月度水电数据。
3. 海上电气损耗绝对值 [NV]；海上可用率只有单一来源。（A9 已接受海上合计约 19%。）
4. 英国光伏倾斜面相对水平面的增益 [NV]。（F2 补注：A13 改为由模型逐时段计算，见 3.5 节；统计意义上的增益仍未核实。）
5. AGR 停堆换料与在线换料的逐站现状只有 [E] 级证据。法定停运"三年一次"同样是 [E]（ONR 文件为 docx，未打开）。
6. Dungeness B 两台机组 PRIS 数据完全相同，疑为平分厂用电，需核对。（DESNZ 不公布逐站数据，无法用 xlsx 核对；它对 2019–2021 全国合计的影响不超过 0.2 TWh。）
7. （第二轮新增）DUKES 6.3 风电合计行标准口径 2020、2021 年的值与分项及复算不符（3.4 节注 *），疑为 DESNZ 发布错误；DUKES 6.3 大型水电 2023、2024 年标准口径值无法由 DUKES 6.2 复算（2.2 节）。两处都不影响建议取值，但引用时需注意。
8. （第二轮新增；F2 已处理）仓库参数表 `gridform_core/data/nuclear/value_uk_firm_availability_v1.json` 的水电年负荷率（0.334，2023 年二手值）与月度形状（平直占位）**F1 单元没有修改**；作者在 A14 选定 0.3487 与阶梯形状，F2 单元已写入（`p05.hydro-dukes-load-factor`）。修正族 golden 只用 VALUE 101 包，没有水电资产，因此没有数值变化。作者审核本表后，可按 2.4 节替换为 0.3487（或 0.3459）与阶梯形状；替换会改变修正口径的 golden，需要按 X0 规则做一次修订。核电各站值与 1.4a 节一致，无需修改。

## 5. 编制过程说明

- 第一轮：只用了 WebSearch / WebFetch 读取公开网页，未用 curl/wget，也未主动下载文件。
- 第一轮：有 5 次 WebFetch 指向的是 PDF 或 docx（gov.uk 的 DUKES 2026 第 5 章 PDF、UK Energy in Brief 2025 PDF、OSTI 的一份 PDF、两份 ONR docx）。工具自动把二进制副本存进了会话的 tool-results 缓存，而且都无法解析。这些副本已立即删除，内容未被使用。之后不再尝试 PDF 或 docx。
- 第 1.3 节的汇总计算脚本在 scratchpad 中：`refstats/nuc.py`（第一轮）。
- 第二轮（A11）：用 curl 读取 4 个 gov.uk 统计页面的 HTML，取得附件链接；然后只下载第 6 节所列 6 个 xlsx，放在施工临时目录 `build/desnz/`，**未入库**。读取用运行时自带 Python 的 openpyxl（`read_only=True, data_only=True`）。读取与计算脚本在 scratchpad `refstats/`：`dump.py`（逐行导出）、`q51.py`（ET 5.1 季度）、`qdump.py` 与 `hq.py`（ET 6.1 季度与水电形状）、`calc.py`（核电逐站均值、PRIS 与 DESNZ 校核、DUKES 6.2/6.3 复算）。

## 6. 第二轮下载文件清单（DECISIONS A11）

访问（下载）时间：2026-10-06T02:54:09Z（UTC），即英国夏令时 2026-10-06 03:54。保存位置：施工临时目录 `scratchpad/build/desnz/`（不入库）。

| 表 | 文件名 | URL | 字节数 | sha256 | 发布页 |
|---|---|---|---|---|---|
| DUKES 2026 表 5.6 | `DUKES_5.6.xlsx` | https://assets.publishing.service.gov.uk/media/6a6a3616862aaf18d9c629eb/DUKES_5.6.xlsx | 264774 | `1335dce766c36a3fa4a27be2ad951292b994877998839a9fdb21670957d30d64` | https://www.gov.uk/government/statistics/electricity-chapter-5-digest-of-united-kingdom-energy-statistics-dukes |
| DUKES 2026 表 5.10 | `DUKES_5.10.xlsx` | https://assets.publishing.service.gov.uk/media/6a6a364b0ddb7e4831c629f2/DUKES_5.10.xlsx | 49263 | `ee622e8e5bf7ad6643f348f62090a5e76ef03e7e854537448dc323d359ef9c7d` | 同上 |
| DUKES 2026 表 6.2 | `DUKES_6.2.xlsx` | https://assets.publishing.service.gov.uk/media/6a6a27620c36759b5ccaa1d1/DUKES_6.2.xlsx | 61265 | `63be0161359794618424f9258fffb860ad16e46016248ae90dc5457a380a35b1` | https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes |
| DUKES 2026 表 6.3 | `DUKES_6.3.xlsx` | https://assets.publishing.service.gov.uk/media/6a6a276f8319ab05f7caa1cf/DUKES_6.3.xlsx | 36985 | `4f0c19f1b063ae20f71e11dd3744c1fb37df484e9873f510e817a3a1711bb53a` | 同上 |
| Energy Trends 表 5.1（2026 年 9 月版） | `ET_5.1_SEP_26.xlsx` | https://assets.publishing.service.gov.uk/media/6aba6dd9a9c3d267bcccefb0/ET_5.1_SEP_26.xlsx | 368197 | `2be6ab036d7b034ca544ecb9f17cdcbcb2d60dbad5aec16c15f0ff62ef0eca9d` | https://www.gov.uk/government/statistics/electricity-section-5-energy-trends |
| Energy Trends 表 6.1（2026 年 9 月版） | `ET_6.1_SEP_26.xlsx` | https://assets.publishing.service.gov.uk/media/6aba724dfceb6fb3a65012d2/ET_6.1_SEP_26.xlsx | 477750 | `369b1ba33be10e84a92aa12ad573a1dbd304da3391090181b5c175fbedad84cc` | https://www.gov.uk/government/statistics/energy-trends-section-6-renewables |

DUKES 2026 两章的封面均写明 "published on Thursday 30th July 2026"，修订期为 2023–2024 年。作者复核时可从上述 URL 重新下载并比对 sha256；若 DESNZ 之后替换了文件，sha256 会不同，数字可能随修订变化。
