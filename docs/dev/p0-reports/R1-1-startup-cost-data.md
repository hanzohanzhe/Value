# R1-1-startup-cost-data：A19 火电重启成本数据（工作报告）

- 单元：R1-1-startup-cost-data（DECISIONS A19 的数据部分；A21 的状态更新）
- 工作位置：INTEG（`fix/review-2026-10-04`）
- 日期：2026-10-07
- 性质：只改文档，不改代码、参数表和 golden。

## 1. 完成的步骤

1. 读取 DECISIONS A19–A21、审查报告 P3-03，以及修正口径下调顺序的现行代码：`native_corrected.avoided_cost` / `downward_key`、`physical_cost_terms`，默认 PSM 内核 `modular_simulation_model.py` 中的 `startup_cost` 加价（:1434）与 `gen_cost` 组成（:607,688），以及论文参数 `runtime_compat/config.py:79-106`。
2. 用 WebSearch / WebFetch 查找文献和数据，没有下载文件，也没有打开 PDF。来源共 11 个，详见参考统计表 4.1 节：
   - 文献：Kumar 等 2012（NREL）；Bailera 等 2020（转述 Kumar）；Staffell & Green 2015（英国）；DIW DD68（Schröder 等 2013）；PyPSA-Eur `unit_commitment.csv`；Badesa 等 2019（英国 2030）；Oates & Jaramillo 2013。
   - 英国实际数据：Elexon Insights API 中 9 台 BM 机组的 SEL / MZT / MNZT / MEL，以及 Elexon 术语表。
   - 换算依据：英格兰银行年均汇率、ONS CPI。
3. 在 `docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md` 新增第 4 节"火电重启成本（A19，PENDING AUTHOR REVIEW）"，含以下各小节：
   - 4.0 模型现状
   - 4.1 来源清单
   - 4.2 换算方法（2024 年英镑）
   - 4.3 启动成本对照表
   - 4.4 最小稳定出力与最短停机时间（英国申报值和文献值）
   - 4.5 建议取值
   - 4.6 每次启动成本如何折成每 MWh，与燃料 + 碳 + VOM 节省比较
   - 4.7 局限
   - 4.8 待作者处理事项
4. 把第 1–3 节（含 3.4、3.5，以及 1.4a、1.7、2.4、3.3 小节标题）的状态改为"作者已审核 (2026-10-07, DECISIONS A21)"，并更新文件头的状态说明。原第 4、5、6 节顺延为第 5、6、7 节，正文中"见第 6 节"（下载文件清单）全部改为"见第 7 节"。第 6 节"编制过程说明"补记了第三轮的读取方式。

## 2. 主要结果（均为 PENDING AUTHOR REVIEW）

每次启动成本 = 磨损（Kumar 中位数）+ 启动燃料与碳（Staffell & Green 英国值），统一换算为 2024 年英镑：

| 技术 | 建议每次启动成本 (£/MW) | 最小稳定出力 | 最短停机时间 | 盈亏平衡停机时长 H\* = S / c |
|---|---|---|---|---|
| CCGT | 热 110 / 温 130 / 冷 150（单一取值用 110） | 50% | 6 h | 2.0 h（c = 55.07）；1.65 h（VALUE 101，c = 66.5） |
| OCGT | 170（另一选择：只计磨损 30） | 50% | 0.5 h | 2.27 h（只计磨损时 0.40 h） |
| 生物质（燃煤改烧代理） | 125（热启动） | 35% | 6 h | 1.47 h |

折算规则：不停机段（机组仍在最小稳定出力以上）每下调 1 MWh 省 c > 0，总是先于弃风。停机段每 MWh 的净节省为 a = c − S / H，a > 0 时先停火电，否则先弃风。H 是这次盈余预计持续的时长；建议同时要求 H ≥ 最短停机时间。只看单个半小时时段时，重启成本折合 2S £/MWh，单时段的小幅盈余应先弃风；盈余持续约 2 h 以上时，先停火电更省。论文的 `startup_cost` 加价折合每次启动只有 £25 / £15 / £41.5 每 MW，论文口径不改（Q1）。

## 3. 测试与检查

- `vpy -m unittest tests.test_fx7_gbp1_public2 tests.test_p05b_corrected_data`：32 个，OK（skipped=2）。前者检查本文件第 3 行与 3.5 节标题中的 A16-6 字样，改动后仍然通过。
- `refresh_source_release_manifest.py --index --check`：`stale: false`。`docs/dev` 不在发布清单内，清单无需刷新。
- `scripts/p0_gate.py quick`：两次提交前各运行一次（在暂存状态下），都是 `status: passed`，16 个步骤全部通过，没有豁免，用时分别为 144 s 和 145 s。
- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`。这是现网 supervisor 于 2026-10-03 05:41 创建的 0 字节锁文件，早于本轮，以往报告已说明。`diagnose-value --prefix …/installed` 输出 "Installation integrity and runtime checks passed."。
- 没有启动任何服务器，没有访问 8766 / 8800 端口，也没有向 SRC 或 INSTALLED 写入。

## 4. 采用的决定

- A19：只提供数据和折算方法，不预设火电比风电贵；明确给出盈亏平衡时长，使结果由 H 决定。
- A21：第 1–3 节状态改为作者已审核。
- Q1：论文口径的 `startup_cost` 不动。
- Q13：两段下调与"在运容量"状态属于方法改动，留给实施单元，本单元只写建议。
- 任务规则：只读网页，不下载。凡原文只有 PDF 的数字都标 [E]；读不到的标 [NV]，不给数。

## 5. 偏差

1. 任务要求每项至少两个独立来源。启动成本、最小稳定出力和最短停机时间各有 2 个以上来源，但以下几处达不到"独立且已核实"：
   - 生物质没有专属来源，用燃煤改烧机组代理（英国大型生物质机组本来就是燃煤改烧）。
   - OCGT 的燃料 + 碳只有 Staffell & Green 一个来源。
   - Kumar 的燃气轮机和燃煤温、冷启动值 [NV]。
   - R5（PyPSA-Eur）很可能沿用 R4（DIW）的数据，两者不算独立。
2. 任务举例的 DESNZ/BEIS Electricity Generation Costs、ENTSO-E/ACER 没有采用：前者不含启动成本，后者只以 PDF/xlsx 发布。英国数据改用 Elexon BM 动态参数，属于官方实际申报值。
3. 价格基年选 2024 年英镑。模型的货币基年随各资产成本来源而定，作者可以另选（4.8 节第 4 条）。
4. 原第 4–6 节顺延编号。任务只要求新增"第 4 节"，为保持该编号，对后续各节作了顺延。

## 6. 未决事项（交作者）

见参考统计表 4.8 节：
1. 审核建议取值（OCGT 在 £170 与 £30 之间二选一）。
2. 选择 H 的取法：(a) 日前预测中连续盈余的时长，为编制者建议；(b) 0.5 h；(c) 最短停机时间。
3. 决定是否采用两段下调。
4. 决定价格基年。

作者审核前，A19 的实施单元不得把这些数值写入修正口径参数表。

## 7. 文件

- 修改：`docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md`
- 新增：`docs/dev/p0-reports/R1-1-startup-cost-data.md`（本报告）
- scratch（不入库）：`refstats/startup.py`（换算与盈亏平衡计算）、`refstats/section4.md`（第 4 节草稿）、`refstats/ref_before.md`（改动前副本）、`build/r11-gate/`（gate 报告）。
