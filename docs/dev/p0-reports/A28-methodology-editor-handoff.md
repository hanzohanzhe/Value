# A28 工作报告：方法学修改员交接文档按最终状态重写

- 分支：`fix/review-2026-10-04`（INTEG），代码状态为 `6560189`（R5 定点复核之后，A28 的缺陷已全部修完）。
- 授权：DECISIONS A25（交付文档按最终状态从头重写）、A26（网站方法学描述网上发布的新模型；论文复现口径是兼容口径；三项内核真错误为通用修正）、A28（缺陷修完后一次性重写四份文件）；作者原话“这一轮记得四个新文件都重新生成，不要把之前已经发现有错并且改过的东西给我”“最后缺陷都修好了再写四份文件”。
- 性质：只改文档，不改代码、参数表、修正目录、golden 或 `website/`。

## 1 完成的步骤

1. 从头重写 `docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md`，只写 HEAD 的最终状态；复制到 worktree 根目录 `VALUE_handoff_methodology_editor_2026-10-04.md`（被 exclude，不入库），`cmp` 逐字节相同。
2. 结构：先读要点（第 0 节，含 A26 定位与写法规则）；文件现状；术语与命名；设计假设、论文复现口径保留的论文时期设定、已声明偏差与最终修正总表；0.3 → 0.4 逐章修改清单（位置、现文、新文与 LaTeX、口径、草稿）；三份参考文档；15 份草稿可用与不可照抄的内容；版次升级；双语检查清单；写 0.4 之前须确认的事项；本轮范围之外的过时表述与顺带发现。
3. 按 A26 定位：方法学描述修正口径（默认）这一模型；论文复现口径写成保留论文时期设定的兼容口径；论文时期设定不写成缺陷；正文先写修正口径，论文复现口径作标注段落；通用修正写成两个口径共同的规则，不写修复经过。第 1 章新小节的中英文稿按此重写。
4. 并入 A26–A28 的最终状态：
   - 两个口径共同的三项内核规则（下调只扣一次、每个储能每期一个净头寸、必发盈余只计一次）写进 N-5、N-7、N-9，归入 U 类；已声明偏差只剩 DEV-BAL-01/02/03，三条都不改变 gate 结论；
   - 论文复现参考运行（VALUE 101 一天、两年，GBP1 public1 第一年）原始不变量全部通过、年度结果发布；GBP1 第一年的数字只用当前结果（stress 74 个事件、487 个时段、78,810 MWh；进口 0.361 TWh；核电 0 TWh）；
   - 已供电量规则（`r5.served-energy-net-of-stress-shortfall`）写进 K-14（每 MWh 成本与碳强度的分母）；
   - 模型时钟（UTC、固定 365 天、无夏令时）写进 K-0、DS-0 与 `VALUE_METHODOLOGY.md` §1；
   - 需求单位、逐时需求展开、用户映射数据的读法（时区、日期顺序、覆盖范围、汇率、价格年份）写进 DS-0、DS-10。
5. 没有写入的内容：已修正问题的经过、被推翻的做法（“永远先降火电”、三种电池共用功率池、旧公式 c − S/H、DEV-STO-01/DEV-BAL-04/DEV-BAL-05 的偏差登记、A15 的待决状态）、逐轮历史与阅读横幅。草稿中这类句子只在第 6 节按行号列出，不复述内容。核电路径依赖按 A15 写进 N-7，只用当前结果，另有一句可选的敏感性说明（A15 原要求以 GBP1 为例）。

## 2 核对依据（只读）

- **代码与目录：** 两套市场规则集字段（`native_market_rules.py`，`storage_position` 两个规则集都是 `net_per_period`）；R4-1 的内核改动（`runtime_compat/modular_simulation_model.py` 的 `store_service_three`、`_thesis_absorb_excess`、`balancing_market_bidding`、时段收尾）；下调类别值与分段（`native_corrected.py` 第 72–92、296、377–389、448–492 行）；重启参数表（含 `price_base` 与 CPI 未复核标记）；已供电量（`cost_ledger.py` 第 74–96、130 行，`application.py` 的碳账分母）；通用核算修正清单（`methodology.py` 第 78–94 行）；模型时钟（`model_clock.py`）；读取时钟与严格/宽松选择（`series_reader.py` 第 402–453 行、`data_method.py` 第 118 行）；映射提示 `GF_MAPPING_PRICE_YEAR`、`GF_DATA_TIMESTAMP_YEAR`（`backend/data_mapping.py`）；价格标签（`app/features/shared/format.ts` 第 179–185 行）；legacy 储能电价的报价式（`runtime_compat/storage_cost.py` 第 367–420 行）；advisory 选择逻辑与文字（`result_advisories.py`、`corrections/*.json`）；修正目录、`METHODOLOGY_PROFILES.md`（13 / 39 个已应用修正）、`declared_deviations.json`（三条，`withdrawn` 两条）、VERSION_LEDGER（默认 PSM 6.7.0 等）、`P0_GOLDEN_DELTA.md`（15 个用例、4 对，D1、D2 轨迹逐位相同）、`doctoral_trajectory_rebaselines.json`、`tests/golden/reports/`。
- **0.3 源稿与参考文档的行号**：`docs/methodology/` 下的 0.3 源稿、`VALUE_METHODOLOGY.md` 与 `main` 逐字相同（`git diff 35aadb3`），交接引用的行号逐处抽查；模型卡按 HEAD 重新编号；`MATHEMATICAL_REFERENCE.md` 第 220–221 行公式损坏仍在（M-5）。
- **实测结果：** `r41-golden/D5-gbp1-summary-before-after.json` 的 `after-r41` 一栏与 `D5-market-before-after.json`（D5 之后的 r4、r5 只改核算区：时钟标签与已供电量，轨迹不变）；`D3-`、`D4-market-before-after.json`（进口 0、stress 0、三类 gate 通过）；R5-1 报告中的已供电量 232,831,786.3 MWh 与 116.828773 £/MWh（用成本账数字复算一致）；`GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` 第 10 节；UI 合同夹具中 VALUE 101 一天的 stress 时段为 0。
- **测试**（施工 wrapper，unittest，独立 TMPDIR 与 VALUE_DATA_HOME）：交接第 5.3 节引用的 24 个模块共 309 个测试——`test_r41_doctoral_kernel_errors`、`test_r5_swap_data_defects`、`test_p07_investment_corrections`、`test_p04_balance_boundary`、`test_stress_events_query`、`test_result_advisories`、`test_methodology_profiles`、`test_p04_validation_gate`、`test_fx5_voll`、`test_fx6_ahead_imports`、`test_fx8_nuclear_in_service`、`test_fx4_storage_orders`、`test_r12_economic_downward_order`、`test_r32_network_economic_dec`、`test_r33_restart_price_base`、`test_r13_per_type_battery_caps`、`test_r33_biomass_disclosure`、`test_r31_solar_8761`、`test_r4_swap_data_defects`、`test_energy_balance_oracle`、`test_p08_network_shares`、`test_network_dec_pricing`、`test_p08b_network_counterfactual`、`test_p08b_boundary_duals`：OK（1 个跳过）。
- 提交前：只暂存本单元的两个文件，`scripts/refresh_source_release_manifest.py --index` 后 `--check`；`scripts/p0_gate.py quick --changed-since HEAD`（gate venv）。结果写在提交说明中。

## 3 采用的决策

A28、A26、A25、A24（1）–（5）、A23、A22a、A22、A21、A20、A19、A18、A17、A16、A15（核电路径依赖的披露）、A14、A13、A9、A8、A7、A6、A4、A2、Q1–Q15。

## 4 偏差

1. **核电路径依赖的例子。** A15 要求以 GBP1 对比为例；A26 与本轮要求不写修复前后叙述。交接把当前结果（论文复现口径核电 0 TWh，修正口径 38.26 TWh）作为正文例子，0.6.0-alpha.2 读法下的一句敏感性说明标为可选，只用于说明路径依赖，不写成勘误。
2. **GBP1 勘误不进方法学。** 按 A26（方法学描述新模型），交接建议勘误不写进方法学正文，是否在网站公开见网站交接文档第 7 节第 3 条。
3. **VoLL 的论文代码原值。** 正文只写 17,000 £/MWh；fx5 草稿中关于论文代码原值的括号列为不照抄。
4. **顺带发现只记录、不修改**（交接第 10.2 节）：两条 advisory 的文字与论文复现口径的当前行为不一致（`p06.avoided-cost-downward-order` 的 “stale requirements after a break”，`fx8.nuclear-in-service-at-start` 的 GBP1 例子）；`CHANGELOG.md` 第 57、86–87 行与当前状态不一致；`P0_GOLDEN_DELTA.md` 生成脚本的两句固定文字没有列出 A26 的三项轨迹例外和新的数值报告。三处都只影响显示或文字，不影响模型结果；按 A28“纯显示类低缺陷进待办，不阻塞”，本单元不改代码，留给代码负责人。

## 5 待决事项（交接第 9 节）

CSV 技术曲线的时间标注；2025 年 CPI 年均值待核对；起始年不变币值的表述；本地修订包是否发布；R029 研究的数据包与数值；23 区研究的基础包；Doctoral 路径是否改名；网络模型两处实现选择请作者知悉；光伏模型文献的书目复核。

## 6 安全核对

- 没有启动服务，没有连接 8766/8800，没有向任何进程发信号；没有联网、下载、push 或改 remote；Python 全部经 `vpy` 或 gate venv（带 `-B`），INTEG 中没有 `__pycache__`。
- INSTALLED 的两项检查结果写在提交说明中。
