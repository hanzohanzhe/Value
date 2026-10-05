# VALUE 修正口径参考统计表（供作者审阅）

> **状态：PENDING AUTHOR REVIEW（全文所有数字、所有建议取值均待作者审阅，未被接受前不得写入 corrected 参数表）**
>
> 用途：P0 计划 M5 / P0-5 S7（Q15 风光文献损耗系数）与 S8（核电、水电可用率）的参考数据。
> 编制：2026-10-06。只读公开网页（WebSearch/WebFetch），未下载任何数据文件。
> 访问日期：所有链接实际访问于 **2026-10-06**（任务模板要求写 2026-10-04；为如实起见此处记录实际访问日期，作者可统一改写）。

## 0. 核实等级说明（每个数字都标注其中之一）

| 标记 | 含义 |
|---|---|
| **[V]** | 已在可读的 HTML 网页上直接读到该数字（一手或指定出版方页面）。 |
| **[V2]** | 已在可读网页上读到，但该网页是二手转述（Statista、Wikipedia、新闻转述等），需作者对照一手表格。 |
| **[E]** | 仅来自搜索引擎对原文（DESNZ PDF、ONR docx、期刊全文）的摘录，原文件本身未能打开（gov.uk 的 DUKES/Energy Trends 只以 PDF/xlsx 发布，WebFetch 无法解析，且本任务禁止下载文件）。**作者必须对照原表复核。** |
| **[D]** | 由上面已核实的数字推导，推导式写在旁边，不是独立来源。 |
| **[NV]** | 未能从任何可读来源核实。按规则**不给数**，只说明应从哪里取。 |

重要限制：DESNZ 的 DUKES 表 5.6 / 5.10 / 6.2 / 6.3 和 Energy Trends 表 5.1 / 6.1 只以 xlsx/ods/PDF 发布。本次没有读到这些表的单元格。凡是标 [E] 的 DESNZ 数字，都需要作者打开 xlsx 复核。

---

## 1. 英国核电可用率（PENDING AUTHOR REVIEW）

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

### 1.2 全国总量（DESNZ 口径与 EDF 口径）

说明：DESNZ 有两种口径。"electricity generated" 是毛发电量，"electricity supplied" 是净上网量。DUKES 5.10 的负荷率按 supplied 除以申报净容量计算。EDF 公布的 "UK nuclear output" 与 PRIS 的 supplied 是同一口径（见 1.3 节的逐年合计）。

| 年份 | DESNZ 毛发电量 (TWh) | DESNZ 核电负荷率 (%) | DESNZ 年度变化描述 | EDF 公布净出力 (TWh) | 来源与等级 |
|---|---|---|---|---|---|
| 2019 | [NV] | [NV] | 下降 5.7%，为 2008 年以来最低，原因是 Dungeness B 和 Hunterston B 长时间停运 | [NV] | N16（DUKES 2020）[E] |
| 2020 | [NV] | [NV] | 下降 11%，创纪录低位；八座电站都曾因长时间检修降低可用容量 | [NV] | N16（DUKES 2021）[E] |
| 2021 | 约 46（Carbon Brief 按 Energy Trends 计算）[V2] | [NV] | DUKES 2022 称下降 7.6% 至纪录低位；Carbon Brief 称下降 9% 至 46 TWh | [NV] | N16 [E]；N17 [V2] |
| 2022 | [NV] | [NV] | [NV] | 43.6（EDF URD 2022 摘录，另称负荷率 77%） | 搜索摘录 [E]（URD 页面被截断，未读到原文） |
| 2023 | [NV] | 72.4 | 下降 14%，所有电站都有换料和计划/非计划检修停运 | 37.3 | 负荷率：N15 [V2]；变化：N13/N16 [E]；EDF：N2 [V] |
| 2024 | 40.6（占全国 285 TWh 的 14%） | 72.3 | 与 2023 年基本持平，是已公布序列中的最低值 | 37.3（"与 2023 年相同"） | 毛发电量：N14 [V2] 与 N13 [E]；负荷率：N13 [E]；EDF：N3 隐含值 [D] 与搜索摘录 [E] |
| 2025（参考，超出要求年份） | 35.9（下降 12%） | [NV] | 换料加计划/非计划停运 | 32.9 | DUKES 2026 搜索摘录 [E]；EDF：N3 [V] |

交叉检验 [D]：PRIS 逐堆 supplied 合计（见 1.3）为 2023 年 37.28 TWh、2024 年 37.30 TWh；除以 PRIS 在运净容量 5,883 MWe 后，负荷率分别为 72.3%（8760 h）和 72.2%（8784 h），与 DESNZ 公布的 72.4% / 72.3% 吻合。2024 年毛/净之比为 40.6 / 37.3 ≈ 1.09 [D]。

**对 S8 验收标准（"核电对 Energy Trends 5.1 ±10%"）的含义：** 模型核电出力应与 ET 5.1 / DUKES 中的 *supplied*（净）口径比较，不能与 *generated*（毛）口径比较。两者相差约 9%，几乎吃掉全部 ±10% 容差。

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
- **验收比较：** 应使用 supplied（净）口径，见 1.2 节。

---

## 2. 英国径流式（natural flow）水电（PENDING AUTHOR REVIEW）

### 2.1 来源清单

| ID | 出版方 / 文献 | 表或节 | 年份 | URL | 等级 |
|---|---|---|---|---|---|
| H1 | DESNZ（BEIS）DUKES 2021 第 6 章 | 第 6 章正文（水电） | 2021-07-29 | https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/1006819/DUKES_2021_Chapter_6_Renewable_sources_of_energy.pdf | [E] |
| H2 | DESNZ DUKES 2024 第 6 章 / Chapters 1–7 | 第 6 章正文 | 2024-07 | 第 6 章页：https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes | [E] |
| H3 | DESNZ DUKES 2025 第 6 章 | 第 6 章正文 | 2025-07-31 | https://assets.publishing.service.gov.uk/media/688a193f6478525675739024/DUKES_2025_Chapter_6.pdf | [E] |
| H4 | Statista "Load factor of electricity from hydropower in the UK 2010–2023" | 图表说明 | 2025-01-14 | https://www.statista.com/statistics/555705/hydro-electricity-load-factor-uk | [V2] |
| H5 | DESNZ DUKES 第 6 章页面（列出 DUKES 6.2 发电量、DUKES 6.3 负荷率两张 xlsx） | 表 6.2、6.3 | 2026-07-30 更新 | https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes | [V]（只核实表存在，未读单元格） |

### 2.2 年发电量与负荷率

| 年份 | 水电发电量 (TWh) | 负荷率 (%) | 说明 | 来源与等级 |
|---|---|---|---|---|
| 2019 | ≈ 5.9 | [NV] | 由 2020 年 "增加 0.9 TWh 至 6.8 TWh" 倒推（6.8 − 0.9） | [D]（基于 H1 [E]） |
| 2020 | 6.8 | [NV] | 增加 16%；当年风速和降雨异常有利 | H1 [E] |
| 2021 | [NV] | [NV] | 只知道风、光、水合计下降 14% | H2/H3 [E] |
| 2022 | [NV] | [NV] | 由 2023 年 "下降 2.2% 至 5.5 TWh" 倒推约 5.6 TWh，仅供参考 | [D]（基于 H2 [E]） |
| 2023 | 5.5（DUKES）；5,538 GWh（Statista） | 33.4 | 下降 2.2%；部分月份降雨偏少 | H2 [E]；H4 [V2] |
| 2024 | 5.8 | [NV] | 增加 6.1% | H3 [E] |

隐含容量 [D]：5,538 GWh ÷（0.334 × 8760 h）≈ 1.89 GW。评审报告 P5-09 指出，模型的 `Hydro_natural_flow` 按可用率 1.0 计，年上限约 17.5 TWh（约 2.0 GW × 8760 h），而实际只有 5–7 TWh，约为上限的 0.3。

### 2.3 月度 / 季度形状

**[NV]**：没有在任何可读网页上找到 2019–2024 年的月度或季度水电数。DESNZ Energy Trends 表 6.1 给出季度可再生发电量（含水电），但只有 xlsx 格式。Elexon BMRS 的 NPSHYD 燃料类型给出输电网接入的非抽蓄水电半小时数据，但需要下载和汇总。建议作者从 ET 6.1 季度数据或 NPSHYD 月度汇总中取形状。DUKES 正文只有定性描述："generation tends to fluctuate in line with rainfall"（H2/H3 [E]）。

### 2.4 建议取值（PENDING AUTHOR REVIEW）

已核实的负荷率只有 2023 年一个点（33.4%，二手）。**本文不提供 2019–2024 均值。** 请作者从 DUKES 6.3（xlsx）读取 2019–2024 年的 "hydro" 负荷率（注意区分 *standard basis* 与 *unchanged configuration basis*），再决定使用均值还是逐年值。S8 的验收标准为"水电对 DUKES ±15%"。

---

## 3. 风电与光伏文献损耗系数（PENDING AUTHOR REVIEW）

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
3. **结果披露：** Q15 规定不做标定。应用上述系数后，应报告各技术的年 CF，并与 DUKES 6.3 负荷率并列展示（作者需从 xlsx 读取对照值），只作披露，不做拟合。

---

## 4. 未完成与待作者处理事项（PENDING AUTHOR REVIEW）

1. DESNZ DUKES 5.10（核电负荷率）、5.6（核电毛/净发电量）、6.2 / 6.3（水电发电量与负荷率）、ET 5.1 / 6.1：本次只能通过搜索摘录 [E] 或二手页面 [V2] 获得少数年份的数值。**2019–2022 年的核电负荷率，以及 2019、2021、2022 年的水电负荷率仍为 [NV]**，需要作者打开 xlsx 补齐。
2. 水电月度或季度形状 [NV]。
3. 海上电气损耗绝对值 [NV]；海上可用率只有单一来源。
4. 英国光伏倾斜面相对水平面的增益 [NV]。
5. AGR 停堆换料与在线换料的逐站现状只有 [E] 级证据。法定停运"三年一次"同样是 [E]（ONR 文件为 docx，未打开）。
6. Dungeness B 两台机组 PRIS 数据完全相同，疑为平分厂用电，需核对。

## 5. 编制过程说明

- 只用了 WebSearch / WebFetch 读取公开网页，未用 curl/wget，也未主动下载文件。
- 有 5 次 WebFetch 指向的是 PDF 或 docx（gov.uk 的 DUKES 2026 第 5 章 PDF、UK Energy in Brief 2025 PDF、OSTI 的一份 PDF、两份 ONR docx）。工具自动把二进制副本存进了会话的 tool-results 缓存，而且都无法解析。这些副本已立即删除，内容未被使用。之后不再尝试 PDF 或 docx。
- 第 1.3 节的汇总计算脚本在 scratchpad 中：`refstats/nuc.py`。
