# A25 工作报告：方法学修改员交接文档按最终状态重写

- 分支：`fix/review-2026-10-04`（INTEG）。代码状态以 `fab9ec2` 为准；提交时 HEAD 为 `5d7690d`（其间只有网站交接文档的提交，不改代码）。
- 授权：DECISIONS A25（四份交付文档按最终状态从头重写，不写已改正的问题、被推翻的做法和逐轮历史）；作者本轮要求“四个新文件都重新生成，不要把之前已经发现有错并且改过的东西给我”。
- 性质：只改文档，不改代码、参数表、修正目录和 golden。

## 1 做了什么

1. 从头重写 `docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md`，并复制到 worktree 根目录 `VALUE_handoff_methodology_editor_2026-10-04.md`（被 exclude，不入库；`cmp` 逐字节相同）。
2. 结构：先读要点（第 0 节）；文件现状（第 1 节）；术语与命名（第 2 节）；设计假设、论文复现口径保留的行为与已声明偏差、最终修正总表（第 3 节）；0.3 → 0.4 逐章修改清单，含位置、现文、新文与 LaTeX（第 4 节）；三份参考文档（第 5 节）；13 份草稿中可用与不可照抄的内容（第 6 节）；版次升级（第 7 节）；双语检查清单（第 8 节）；待决事项（第 9 节）；顺带发现（第 10 节）。
3. 只写最终规则：下调次序写成一套（不停机段与停机段，\(a=c-S/(m\,H)\)，重启成本按 2025 年英镑）；电池上限只写按类型；网络模型写规则集 `network-economic-v2` 与八类次序；A15 写调查结论（563 行、217 GWh，471 为包络越界数），归类留给作者。没有写施工轮次、旧规则和已改正的问题；草稿中描述非最终规则的句子只在第 6 节列出位置，不复述内容。

## 2 核对（只读）

- 逐项对照代码：两套市场规则集字段（`native_market_rules.py`）、下调分段与类别次序（`native_corrected.economic_segments`、`DOWNWARD_CLASS_RANK`、`IMPORT_DOWNWARD_CLASS_RANK`、`SHUTDOWN_CLASS_RANK`）、网络模型的 `DEC_CLASSES` 与物理权重、`last_resort_price`、重启参数表（含 `price_base`）、核电与水电参数表、损耗系数与 CF 披露表、价格口径标签（`market_replay`、`app/features/shared/format.ts`）、VoLL 常数（`voll.py`）、成本账 id、储能余量只由默认 PSM 发布、`value.agent-cashflow/v1` 的发布方、thesis96 路径在任何口径下用冻结输入（`canonical_psm_data.py` 第 1017–1028 行）、修正目录与 VERSION_LEDGER、18 个 manifest id 与版本。
- 0.3 源稿与三份参考文档的行号在本分支上逐处核对；`MATHEMATICAL_REFERENCE.md` 第 220–221 行发现公式损坏（`\ne` 变成换行），已列入交接第 5.1 节 M-5，本单元没有改该文件。
- 用参数表重算：\(0.5476061707\times0.90307\)、三个 \(H^\*\)（4.13 / 4.69 / 4.34 h）、OCGT 在 \(H=4.5\)/5 h 的净节省、C8 最后手段报价 −388.3、CPI 系数 1.0336、水电形状均值 0.99883 与 6.10 TWh、第 4,320 期。
- 单元测试（施工 wrapper，unittest，独立 TMPDIR 与 VALUE_DATA_HOME）：`test_p07_investment_corrections`、`test_p04_balance_boundary`、`test_stress_events_query`、`test_result_advisories`、`test_methodology_profiles`、`test_fx5_voll`、`test_fx6_ahead_imports`、`test_fx8_nuclear_in_service`、`test_r12_economic_downward_order`、`test_r13_per_type_battery_caps`、`test_r32_network_economic_dec`、`test_r33_biomass_disclosure`、`test_r33_restart_price_base`、`test_r31_solar_8761`、`test_documentation_consistency`、`test_p04_validation_gate`、`test_energy_balance_oracle`，共 223 个：2 个 failure 与 6 个 error（含子测试）都属于 `test_documentation_consistency` 的 6 个既有失败 id，均登记在 `known-failures-linux-py310.txt`；另有 `test_value_methodology` 在 wrapper 运行时中缺 pypdf 而无法导入；在 gate venv 中运行 `test_value_methodology`：OK（PDF 不存在，源稿检查已执行后跳过 PDF 部分）。交接中引用为 passed 的测试都在这组里通过。
- 提交前：只暂存本单元的两个文件，`scripts/refresh_source_release_manifest.py --index` 刷新发布清单，`scripts/p0_gate.py quick --changed-since HEAD`（gate venv），结果写在提交说明中。

## 3 采用的决策与偏差

- 采用：A25、A24（1）–（5）、A22a、A23、A21、A20、A19、A18、A16、A15、A14、A9、A6、A4、Q1–Q15。
- 偏差：
  1. 草稿中的非最终句子没有在交接中复述，只给出位置（第 6 节），这样交接正文不出现被取代的做法。
  2. 交接引用的 GBP1 public2、R029 public2 数字来自 C9、C10 的最终 golden 与 `GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` 第 10 节；FX6 草稿第 4 节的前后对比测量于核电规则生效之前，交接要求只引用最终年度量（进口 1.376 TWh）。
  3. 本单元没有改 `MATHEMATICAL_REFERENCE.md` 的损坏公式，也没有改草稿，二者都留给方法学修改员（交接第 5.1、6 节）。

## 4 待决事项（交接第 9 节）

削减分支重复下调的归类（DEV-BAL-05 或内核修正）；CSV 技术曲线的时间标注；2025 年 CPI 年均值待核对；起始年不变币值的表述；本地修订包是否发布；R029 研究的数据包与数值；23 区研究的基础包；Doctoral 路径是否改名；GBP1 勘误框；光伏模型文献的书目复核；网络模型两处实现选择请作者知悉。

## 5 安全核对

- 没有启动服务，没有连接 8766/8800，没有向任何进程发信号；没有联网、下载、push 或改 remote；Python 全部经 `vpy` 或 gate venv（带 `-B`），INTEG 中没有 `__pycache__`。
- INSTALLED 的两项检查结果写在提交说明中。
