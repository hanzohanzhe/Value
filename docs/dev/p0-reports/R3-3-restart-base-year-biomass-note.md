# R3-3 工作报告：重启成本换到模型价格基年（A24-4）与生物质披露（A24-2）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `d7882f4`。
- 授权：DECISIONS A24 第 (4) 项：重启成本从 2024 年英镑换算到模型成本参数的基年，与燃料、碳价同一口径，写明换算系数和出处；第 (2) 项：生物质本轮只披露，两个口径的行为都不变，在结果与方法学中写明“没有 CfD/ROC 补贴收入，所以生物质几乎不调度”，补贴放到下一轮（P4-07）。
- 提交：
  - `5a7e7ac` feat(thermal): restart costs in the model's 2025 price base (A24-4)
  - `996a1d2` feat(advisories): disclose that biomass is rarely dispatched without CfD/ROC support (A24-2)
  - 本报告单独提交（docs(p0)）

## 1 A24-4：重启成本的价格基年

### 1.1 基年为什么是 2025 年

仓库中没有一处直接写“燃料价、碳价是某年英镑”。可以确定的依据如下：

| 依据 | 位置 | 内容 |
|---|---|---|
| 起始年币值 | DECISIONS A6 | 模型所有金额都按起始年币值计价，不折现 |
| 各研究的起始年 | `docs/methodology/en/r029_cem.md` 第 3 行；`gridform_core/value_101_lifecycle.py:155`；`tests/golden/cases.json`（D5、C9、C10） | R029 为 2025–2034 年，VALUE 101 为 2025–2026 年，GBP1 为 2025 年 |
| 已声明年份的成本参数 | `gridform_core/data/storage/storage_technology_catalogue.json`（各技术 `currency_base_year: 2025`）；`docs/methodology/en/core.md` 第 121 行（抽水蓄能 CAPEX）；`r029_cem.md` 第 190 行（政策预算） | 都是 2025 年英镑 |
| 燃料与碳价 | `runtime_compat/config.py`（CCGT `fuel_cost` 39.21、`carbon_price` 15.76 等）；各数据包的 `fleet__generators/fleet.json` | 没有单独标注价格年份。按 A6，它们是起始年即 2025 年的币值 |

所以与燃料、碳价同一口径的基年是 2025 年。参考统计表 4.2a 节逐条列出了这些依据，并说明另有少数来源年份不同的输入（核电政策表 `price_year` 2015、2024，BEIS 2020 成本，2022 年欧元价格），它们属于方法学交接中“起始年不变币值的表述”一项，本单元没有处理。

### 1.2 换算

- 方法：英国 CPI（ONS D7BT，2015 = 100）年均值之比，与 R1-1 把各来源换到 2024 年英镑的方法相同（参考统计表 4.2 节）。
- 2024 年年均值 133.9：R1-1 于 2026-10-07 在 ONS 序列页读取 [V]。
- 2025 年年均值 **138.4**：按 2025 年 12 个月度值求平均。本单元没有联网授权，这个数**没有在 ONS 页面上重新读取**，在参数表和参考统计表中都标为 [NV] 并请求核对一次。指数每差 0.1 点，结果变化 0.07%，每 MW 不到 £0.2。
- 系数 138.4 / 133.9 = **1.0336**。取值 = round(2024 年值 × 138.4 / 133.9, 1)：

| 技术 | A22 审核值（2024 年英镑，£/MW） | 模型使用值（2025 年英镑，£/MW） |
|---|---|---|
| CCGT 热 / 温 / 冷 | 110 / 130 / 150 | 113.7 / 134.4 / 155.0 |
| OCGT | 170 | 175.7 |
| 生物质 | 125 | 129.2 |

最小稳定出力、最短停机时间、热/温/冷界线和判定规则都不变。盈亏平衡时长 H\* = S/(m·c) 上升 3.4%（论文成本下：CCGT 3.99 → 4.13 h，OCGT 4.54 → 4.69 h，生物质 4.20 → 4.34 h）。按半小时时段计，OCGT 仍从 H = 5 h 起先停机。

### 1.3 实现

- 参数表 `gridform_core/data/thermal/value_thermal_restart_v1.json`：
  - `restart_cost_gbp_per_mw` 改为 2025 年英镑值；
  - 新增 `restart_cost_gbp2024_per_mw`（A22 原值）、`price_base`（币种、起止年、指数名、两个指数值、系数、取值规则、基年依据、核实状态）、`table_revision`（含 correction id）；
  - `status`、`acceptance`、`price_basis` 写明 A24-4；`applies_to` 补上 r32（R3-2 报告第 9 节第 2 条的建议，在这次修订中顺带完成）；
  - 文件名、`table_id` 与 schema 不变，所以读取路径和 Run 记录字段不变，Run 记录的 `restart_table_sha256` 随内容改变。
- `native_corrected.restart_table()` 新增 `_check_price_base`：有 `price_base` 时，系数必须等于两个指数之比（四位小数），每个取值必须等于 2024 年值按该比值换算后取一位小数。不一致就拒绝读取。没有 `price_base` 的表照常读取。
- 方法改动登记（Q13）：correction id `r33.restart-cost-price-base-2025`。取值进入修正口径的调度排序（默认 PSM 的 r12 和网络模型的 r32），所以两个 PSM 都升版本并要求用户确认：`value-bid-at-cost-psm` 6.5.0 → 6.6.0，`value-staged-bid-at-cost-psm` 1.5.0 → 1.6.0，`requires_user_opt_in = true`。已保存的 Study 会被归为 `method_upgrade_required`，原因中列出这个 id（有测试）。scientific_version 不变（与 R1-2 的做法一致；论文口径白名单中的 scientific_version 因此不受影响）。
- 论文复现口径不读这张表，不受影响。

### 1.4 文档

- 参考统计表第 4 节：状态段加 A24-4 说明；新增 4.2a 节（基年依据、换算、对照表）；4.6 节盈亏平衡表按 2025 年英镑重算并保留 2024 年英镑的 H\*；4.8 节第 4 条“决定价格基年”改为已决定；第 6 条补一句网络模型自动使用新值。文件顶部总状态加一句。
- 方法学 0.4 草稿 `r12_economic_downward_order.md`：取值表改为 2025 年英镑并并列 2024 年值；新增 2a 节“Price base of the restart costs”；算例（CCGT、OCGT）按新值重算；第 6 节加一段 R3-3 的数值结论。
- 方法学 0.4 草稿 `r32_network_economic_downward_order.md`：取值说明改为 2025 年英镑；第 3 节算例按新值重算，同时更正了原稿中 H = 5 h 的“restart GBP 1,700”（停掉的是 20 MW 装机，应为 20 × S，现为 £3,514，原值应为 £3,400）；第 5 节加 C7/C8 的 R3-3 数值。
- 修正目录 `corrections/r12.json` 的 description 和 notes 改为 2025 年英镑值（展示字段，不进方法身份）。
- `VERSION_LEDGER.json` 两条新 bump；CHANGELOG（correction id 表、golden 摘要、Known issues、新小节）；重新生成 `docs/generated/MODULES.md`、`METHODOLOGY_PROFILES.md`、`docs/release/P0_GOLDEN_DELTA.md`、`source-release-manifest.json`；ui-contract 夹具 `value-101-day.capabilities.json` 的 `psm_module_version` 6.5.0 → 6.6.0（用生成器重写）。

## 2 A24-2：生物质披露

### 2.1 机制核实

两个市场内核（`runtime_compat/modular_simulation_model.py` 与 `doctoral_market_kernel.py`）的 `BiomassGenerator.gen_cost` 都是 `gen_cost + carbon_price + fuel_cost + unit_time_cost`，日前报价为 `gen_cost × bid_multiplier`。GBP1 与 R029 数据包的 `bio_and_waste` 行为 0.2 + 燃料 80 + 碳 4.8 + 0 = **85 £/MWh**；上一时段未被接受时再加 `startup_cost` 83 £/MWh。CCGT 为 55.07，OCGT 为 74.92。所以生物质在火电中排在最后，28 GW CCGT 足以覆盖需求，生物质几乎不被调度。模型没有任何 CfD/ROC 收入能把它的报价压到燃料成本以下。

注意：`docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` 第 7 节第 1 项写“报价只用 `gen_cost`（生物质 0.2，CCGT 0.1），不含燃料成本”。这一解释与代码不符：报价包含燃料和碳，原因是全额成本 85 高于燃气。该文件是历史记录，本单元没有改，交负责人决定是否加注。

### 2.2 实现（两个口径的行为都不变）

- 通用 advisory 增加谓词 `fleet_assets`（`gridform_core/result_advisories.py`）：
  - 这类 advisory 必须带 `applies_when`，且只能含非空的 `assets_any`；
  - 证据与 R3-N7 的按资产筛选相同（Run 冻结输入中的 `fleet.generators`，按 `market_replay.canonical_technology` 归类）；
  - 机组读不到时保留 advisory（偏向披露）；
  - 其他谓词不允许带 `applies_when`；
  - 通用 advisory 可选 `findings` 字段。
- 新 advisory `VALUE-ADV-BIOMASS-SUPPORT-NOT-MODELLED`（`data/methodology/advisories.json`），严重度 medium，`assets_any: ["biomass_and_waste"]`，findings A24-2、P4-07：
  - 标题：“Biomass without support revenue”；
  - 正文写明：没有 CfD/ROC 补贴收入（P4-07 下一轮）；按全额燃料与碳成本报价（85，高于 CCGT 55.07 和 OCGT 74.92）；几乎不调度（GBP1 与 R029 2025 年约 0.01 TWh / 4,762 MW）；两个口径都如此。
- 适用范围：
  - 凡冻结机组含生物质的 Run 都显示，与口径和已应用的修正无关；
  - VALUE 101（没有生物质）不显示；
  - 这条 advisory 不是目录修正，不进方法身份（`applied_corrections_sha256` 不变），所以已保存的 Study 不会因此要求确认。
- 严重度选 medium：它应该被看到；但它是两个口径共有的模型范围限制，不是缺陷修正。按现行规则，只有 high/critical 才会把比较置为 needs_review，选 high 会让所有含生物质 Run 的比较都失去归因结论。
- 文档：
  - 新增方法学 0.4 草稿 `docs/methodology/drafts/0.4/r33_biomass_support_disclosure.md`：报价算式（两个内核）、运行数字、advisory 文本、0.3 正文待改处、中文摘要；
  - 模型卡 `docs/SCHEME_C_MODEL_CARD.md` 的“两个口径的已知简化”增加一条；
  - CHANGELOG Known issues 与新小节；`METHODOLOGY_PROFILES.md` 的通用 advisory 表多一行。

## 3 文件

| 位置 | 改动 |
|---|---|
| `gridform_core/data/thermal/value_thermal_restart_v1.json` | 2025 年英镑值、2024 年原值、`price_base`、`table_revision`、`applies_to` 补 r32 |
| `gridform_core/builtin/scheme_c_1000twh/native_corrected.py` | `_check_price_base` 读取校验 |
| `gridform_core/builtin/scheme_c_1000twh/scheme_c_native_psm.py`、`staged_psm.py`、两个 manifest | 版本 6.6.0 / 1.6.0（CRLF 行尾已保持） |
| `docs/release/VERSION_LEDGER.json` | 两条 R3-3 bump（opt-in） |
| `gridform_core/data/methodology/corrections/r12.json` | 展示文字 |
| `gridform_core/result_advisories.py`、`gridform_core/data/methodology/advisories.json` | `fleet_assets` 谓词与生物质 advisory |
| `tests/test_r33_restart_price_base.py`（新，7 个）、`tests/test_r33_biomass_disclosure.py`（新，6 个） | 见第 4 节 |
| `tests/test_r12_economic_downward_order.py`、`tests/test_r32_network_economic_dec.py`、`tests/test_prompt95_staged_copperplate.py`、`tests/test_result_advisories.py` | 按新取值、新版本、新 advisory 更新期望 |
| `tests/golden/corrected/C1–C10.json`、`docs/dev/p0-reports/r33-golden/C8-r16.json` | golden 修订与数值报告 |
| `tests/fixtures/ui-contract/value-101-day.capabilities.json` | 生成器重写（模块版本） |
| 文档 | 参考统计表第 4 节；草稿 r12、r32、r33（新）；模型卡；CHANGELOG；生成的表与清单 |

## 4 测试

- `tests/test_r33_restart_price_base.py`（7 个）：
  - 价格基年为 2025，系数等于 CPI 之比，`price_basis` 写明 2025 GBP；
  - 三种技术的 2024 年值与 2025 年值逐项核对，其他取值不变；
  - 读取校验：漏改的 2024 年值、错误系数都被拒绝；没有 `price_base` 的表照常读取；
  - 基年依据：储能目录所有 `currency_base_year` 都等于 `price_base.to_year`；
  - 网络规则记录与默认 PSM 的 extension 都带新表的 sha；
  - 两个 PSM 的 bump（版本、包、correction id、opt-in、manifest、类版本）与 Study 迁移判为 `method_upgrade_required`；
  - 参数表写明 correction id、A24-4 和 r32。
- `tests/test_r33_biomass_disclosure.py`（6 个）：
  - 目录条目（谓词、资产、严重度、findings、正文要点）；`bio_and_waste` 归类为 `biomass_and_waste`；不在修正目录中；
  - 含生物质的 Run 在两个口径下、且所有修正都已应用时，仍显示这条 advisory；
  - 不含生物质的 Run 不显示；读不到机组时显示；
  - 读取规则：缺 `applies_when`、未知键、空列表、其他谓词带 `applies_when`、`findings` 类型错误，都被拒绝；
  - 模型卡与草稿都写明 advisory id 和 P4-07。
- 更新的测试：
  - test_r12：取值表 2025 年值与 2024 年原值；净节省与 H\* 的数字；零节省平局改用 c = 87.85（= 175.7 / 2），使 a = 0 精确成立；
  - test_r32：算例数字；版本 bump 按包名查找。live 分区 toy 的南区 CCGT 由 £90 改为 £100，原因见第 6 节偏差 3；
  - test_prompt95：staged 版本 1.6.0；
  - test_result_advisories：固定 Run 没有冻结机组，所以列表中多出这条 advisory。
- 回归（`scripts/run_backend_tests.py`，VALUE_P0_5_PACKS 指向本地重建的 GBP1 public2 与 R029 public2）：
  - 范围：r33、r12、r32、版本台账、方法学 profile 与静态扫描、advisory、native 市场规则、golden 各测试、Study 迁移、文档一致性、R2 记录与资产筛选、模块源码、FX8、R1-3，以及全部网络模块测试（`test_network_*`、`test_p08*`、`test_prompt9*/10*/115/67/68/70`、`test_staged*`、`test_zonal*`）；
  - 结果：pass 582，failing 46 全部在基线内，新增失败 0。唯一列出的 “IMPORT:test_fx6_day_ahead_imports” 是我误写的不存在的模块名，不是测试失败。
- `scripts/check_version_ledger.py`、`scripts/check_methodology_catalog.py`、`capture.py validate`、`delta_report.py --check`（未归因 0）都通过。
- `scripts/p0_gate.py quick`：
  - 两个功能提交前各跑一次，最终都是 `status: passed`，没有豁免；
  - 第一个提交第一次运行时 `backend_ratchet` 报 ui-contract 夹具中的模块版本过期，用生成器重写后通过；
  - 第二个提交第一次运行时忘了暂存重新生成的 `METHODOLOGY_PROFILES.md`，暂存并刷新发布清单后通过。

## 5 golden 与数值

- 修订前 `capture.py check`：
  - fast：C1–C4 各 1 列（`restart_table_sha256`）；C7 3 列；C8 109 列；D1–D3 gated 0；
  - C5、C6、C9、C10：各 1 列（`restart_table_sha256`）；
  - C9 与 C10 用 `build_value_uk_pack_revision.py --link hardlink` 在 scratch 重建。manifest sha 与钉住值一致（`8d73e08c…f86f`、`d9876d98…d309`）。构建前后两个 staging 来源目录的清单哈希相同（`dc85a5f8…`）。用后已删除。
- `capture.py revise --cases C1 … C10 --correction-id r33.restart-cost-price-base-2025 --finding A24-4`：

| case | 新修订 | 变化 |
|---|---|---|
| C1 / C2 / C4 | r16 | trajectory 1 列（sha） |
| C3 | r17 | trajectory 1 列（sha） |
| C5 / C6 | r15 / r13 | trajectory 1 列（sha） |
| C9（GBP1 public2 2025） | r5 | trajectory 1 列（sha） |
| C10（R029 public2 2025） | r1 | trajectory 1 列（sha） |
| C7 | r14 | 规则记录 2 列（accounting）+ extension sha 1 列 |
| C8 | r16 | trajectory 51、accounting 58 列 |

- C8 数值报告 `docs/dev/p0-reports/r33-golden/C8-r16.json`（标准命令 `numeric-report --parent HEAD`，父提交输出复现 r15）：
  - CCGT 停机段的最后手段报价由 −373.5 变为 −388.3 £/MWh（66.5 − 113.7 / 0.25），全天仍未被接受；
  - 调度、弃电和成本只有 LP 容差级别的变化：每时段最大 2.2e−10 MWh，全天成本最大 5.3e−7 £。
- **GBP1 与 R029 一年运行在数值上完全不变**，因为没有一个停机段与弃风按价比较。所以 A24-4 对现有参考结果没有数值影响，只改变以后可能出现的边界情形。
- 论文族不受影响（D1–D3 gated 0；D4、D5 不经过这张表）。

## 6 采用的决定与偏差

采用：A24-4、A24-2、A6（起始年币值）、A22/A22a（取值与公式不变）、Q13（opt-in）、Q1（论文口径不变）。

偏差与说明：

1. **2025 年 CPI 年均值没有联网复核。** 任务只允许在仓库内查找和引用基年，没有授权读网页；仓库内没有 2025 年 CPI。138.4 是按 ONS D7BT 2025 年月度值求得的平均，在参数表 `price_base.verification` 和参考统计表 4.2a 节都标为 [NV]，请作者或后续单元核对一次。若与 ONS 公布值不同，只需改 `index_to_year` 和 `factor` 两个字段，再按规则重算五个取值（读取校验会强制一致），并修订一次修正族 golden。
2. **登记方式：模块版本 + correction id，不进修正目录。** 沿用 R3-2 的做法：`r33.*` 是 r12/r32 已用参数的重新表述，所以只登记在两个 PSM 的版本台账中（opt-in）。没有在 `corrections/*.json` 中新增条目，以免改变修正口径的 `applied_corrections_sha256`。CHANGELOG 的 correction id 表中写明了这一点。
3. **R3-2 的 live 分区 toy 改了一个价格。** 新取值下，`test_r32` 的 live staged 分区 Run（H = 3 h）在 zonal LP 的 `physical_throughput` 阶段失败：HiGHS 报 “scaled model optimal, unscaled model NOTSET”（`GF_ZONAL_SOLVER_FAILURE`）。逐项扫描结果如下：
   - 南区 CCGT £90 时，OCGT 重启成本 S = 173–178 都失败，S ≤ 172 或 ≥ 180 都正常；
   - S = 175.7 时，(OCGT 80, CCGT 95) 也失败；
   - 这是 zonal LP 的数值脆弱性，与下调规则无关。zonal 模块（4.0.0）与求解器合同 v4 不在本单元范围内，没有改；
   - toy 中南区 CCGT 只起“更贵的南区供给”作用，所以改为 £100，并在测试中写明原因；
   - 规则相关的断言全部不变：H = 5 h 时 OCGT 先停，H = 3 h 时先弃风；
   - 两区 LP 与 CBC oracle 的对照测试仍用 £90，正常通过；
   - CHANGELOG Known issues 已登记。
4. **生物质 advisory 用通用 advisory，而不是修正目录。** 修正目录中的 advisory 只在 Run 没有应用该修正时出现，而 A24-2 要求两个口径都披露、且没有修正，所以新增通用谓词 `fleet_assets`。
5. **四份交付文档没有改。** 按 A25 和本轮作者的要求，简报、四角色测试报告和两份交接文档由负责人按最终状态从头重写。本单元也没有改 DECISIONS（A22 一行中的 2024 年英镑值是当时的决定原文）。

## 7 交给负责人（重写四份交付文档时使用，只写最终状态）

- 修正口径重启成本按 2025 年英镑：CCGT 113.7 / 134.4 / 155.0、OCGT 175.7、生物质 129.2 £/MW。由 A22 的 2024 年英镑值乘 1.0336（ONS CPI D7BT 138.4 / 133.9）得到。基年依据是 A6 起始年币值，所有发布的研究都从 2025 年开始。2025 年指数待核对一次。
- correction `r33.restart-cost-price-base-2025`；默认 PSM 6.6.0、staged PSM 1.6.0，都须用户确认。盈亏平衡时长 4.13 / 4.69 / 4.34 h。
- 参考结果没有数值变化；只有 C8 的 CCGT 最后手段报价变为 −388.3 £/MWh，且从未被接受。
- 生物质：两个口径都没有 CfD/ROC 收入（P4-07 下一轮）。按 85 £/MWh 全额成本报价，2025 年 GBP1 与 R029 修正口径约 0.01 TWh / 4,762 MW。含生物质的 Run 显示 advisory `VALUE-ADV-BIOMASS-SUPPORT-NOT-MODELLED`（medium）。方法学草稿 `r33_biomass_support_disclosure.md`。methodology 交接第 9 节第 11 条（“报价只用 gen_cost”）的解释与代码不符，按第 2.1 节改写。
- methodology 交接第 9 节第 7 条中“重启成本按 2024 年英镑”已过时。现为 2025 年英镑；输入来源年份混合的问题仍待作者表述。
- zonal LP 数值脆弱性（第 6 节偏差 3）是新的已知问题。

## 8 安全核对

- INSTALLED：
  - `find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`，是现网 supervisor 在本轮之前创建的锁文件，以往报告都有同样记录；
  - `diagnose-value --prefix …/installed` 退出码 0，输出 “Installation integrity and runtime checks passed.”。中间的 vinext “Premature close” 提示与以往相同；
  - 门禁的 `installed_inventory` 步骤每次都通过。本单元没有写入安装目录。
- 进程与网络：
  - 没有启动 HTTP 服务，没有连接 8766/8800，18xxx 端口无监听，没有向任何进程发信号；
  - golden 与测试进程都由我在前台或后台启动，自行结束，使用独立的 TMPDIR 和 VALUE_DATA_HOME（scratch 下）；
  - 没有联网，没有下载，没有改 SRC，没有 push。
- Python 全部经 `vpy` 调用，INTEG 中没有 `__pycache__`。staging 来源目录在重建 public2 前后清单哈希相同。scratch 中重建的数据包与临时目录已删除，本单元 scratch 剩约 224 KB。

## 9 遗留问题

1. 2025 年 CPI 年均值 138.4 待联网核对（第 6 节偏差 1）。
2. zonal LP 数值脆弱性（第 6 节偏差 3）。建议网络负责人在 `zonal_redispatch._run_highs` 中，对 status 4（scaled optimal / unscaled not set）做受控重试，例如关闭 presolve 或改用 IPM，并记录诊断；这需要 zonal 模块升版本，并修订求解器合同。
3. `GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` 第 7 节第 1 项对生物质原因的解释有误（第 2.1 节）。
4. 生物质补贴（CfD/ROC）建模属于 P4-07，下一轮处理。
