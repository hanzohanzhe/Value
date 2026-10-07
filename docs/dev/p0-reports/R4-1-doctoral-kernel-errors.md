# R4-1 工作报告：论文内核的三项真错误作为通用修正（DECISIONS A26）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `6fecfc6`。
- 授权：A26（论文复现口径中的真错误一律作为通用修正修好，两个口径都生效，各配 correction id，论文 golden 重基线一次并附数值报告，已保存 Study 按 Q13 确认）；A27（同轮修复）。
- 提交：
  - `03e39ed` chore(golden): A26 doctoral trajectory exceptions A15, DEV-BAL-04, DEV-STO-01 (integrator step)
  - `3c52a2d` fix(psm): three thesis-kernel errors corrected in both profiles (A26)
  - `da761ca` docs(methodology): R4-1 kernel corrections draft, A15 investigation closed, before/after numbers (A26)
  - 本报告单独提交（docs(p0)）

## 1 修了什么

| 错误 | correction id | 修复 |
|---|---|---|
| A15：削减分支重复下调 | `r41.down-regulation-taken-once`（新，通用） | `store_service_three` 两个子分支中，非 VRE 机组一次削够剩余需求时，`break` 前把 `need_curtailed_energy` 清零（做法 C）。论文的下调顺序（按 curtail cost 升序，风电 0 价先削）不变 |
| DEV-STO-01：储能功率上限按出清阶段重置 | `p06.storage-net-per-period`（原修正口径的开关，改为通用） | 论文规则集也采用“每个储能每个时段一个净头寸”：各阶段共用额定功率；已放电的储能先减少本时段放电（buy-back），没有剩余放电才充电；已充电的储能不再报放电；时段收尾 `close_period` 记录销售并检查四项不变量。`storage_position` 不再是规则集开关（两个规则集都是 `net_per_period`） |
| DEV-BAL-04：平衡阶段把必发核电盈余再计一次 | `r41.must-run-surplus-counted-once`（新，通用） | `balancing_market_bidding` 的论文分支中，非 VRE（必发核电）盈余行服务平衡需求时只扣减盈余，不再加到核电出力上，也不再付平衡费；VRE 盈余行照旧调度并付费 |

论文的报价、价格、结算规则不变。修正口径原本就走自己的函数（`store_service_corrected`、D1-surplus 账、净头寸），调度不变。

**执行中的内核副本。** 只有 `runtime_compat/modular_simulation_model.py`（默认 PSM）被口径和模块执行，三项都改在这里，并用 `seal_runtime_overlay.py` 重新封存（correction id 记入 `RUNTIME_OVERLAY.json`）。`compat/` 是按哈希钉住的原始源码参考，只被不属于任何模块的 `exact_run.py` 引用，未改；`runtime_compat/simulation_model.py` 只被非模块化的 `case3.py` / `investment_support.py` 使用（另有 `map_projects_to_generators_by_location.py` 只从它取 `acm_energy`、`acm_solar` 两个函数），不执行任何出清，未改。实验性的 `value-doctoral-national-psm` 用的 `doctoral_market_kernel.py` 已经按实际削减量扣减需求、平衡阶段也不再重复计核电盈余，无需修改。

## 2 实现细节与记账

- **净头寸的记账（论文规则集的 surplus-node 边界）。** buy-back 时：削减分支用 need（预测减实际，调度内）抵消放电，计为 `surplus_routing.curtailed`（从 S 中拿走）；用 excess 抵消放电，计为 `to_dispatch`：必发核电盈余本来就在 S 中，VRE 盈余（S 外）则按 excess 行的比例作为 VRE 出力进入 S，与论文平衡阶段的再调度一致。充电仍计 `to_storage`。这样 surplus conservation、节点边界和包络都闭合。第一版把 buy-back 一律计为 `to_storage`，在 D3 上出现包络下界越界（S < D，VRE 能量在 S 外直接服务需求），所以改成上面的分类，并重跑了全部受影响的 golden 与夹具。
- `Battery.close_period` 改为幂等（`StoragePeriodBook.closed`），论文规则集在每个时段收尾时调用它。
- `native_balance_audit`：`non_vre_double_counted_mwh` 改为记录内核实际重复计入的量（`SurplusTrace.double_counted_mw`，修复后恒为 0），`to_dispatch` 照常记录盈余用于平衡需求的量。
- **声明偏差。** `declared_deviations.json` 删除 DEV-BAL-04、DEV-STO-01，另设 `withdrawn` 列表保存两条说明，旧 Run 的证据（matched 的 deviation id）在界面上仍能显示是什么；DEV-BAL-05 草案从未登记。oracle 删除两个门控匹配器（`in_dispatch_double_count`、`stage_power_reset`），`match_declared_deviations` 中门控失败一律为 `failed`；为保持报告形状（以及所有 golden 摘要）稳定，`signature_matches` 仍输出这两个键，计数恒为 0。保留 DEV-BAL-01/02/03（定义与证据）。
- **advisory。** 两条 r41 correction 的 advisory 只对论文复现口径和没有记录口径的 Run 显示：`applies_when` 新增键 `profiles_any`（`methodology.APPLIES_WHEN_KEYS`，`result_advisories._applies` 读取 Run 记录的 profile id；没有记录时保留，倾向披露）。p06 的储能 advisory 改为同时说明修正口径（P0-6 前）和论文口径（R4-1 前）；`p06.d1-surplus-accounting` 的 advisory 去掉了“必发核电被重复计入”这一已不成立的说法。
- **Q13。** `value-bid-at-cost-psm` 6.6.0 → 6.7.0，VERSION_LEDGER 包 R4-1，三个 correction id，`requires_user_opt_in = true`；两个口径的 applied-corrections 哈希都变，已保存的 Study 会被归为 `method_upgrade_required`（已验证：原因列出三个 id）。
- **模块一致性检查**（`module_conformance.check_storage_lifecycle`）在充电后和放电后调用 `close_period`，与内核循环一致，否则外部储能成本模块的检查会因为销售延迟记录而失败。
- 其他：`market-ledger-storage-orders-v1.schema.sql` 的注释与 `MARKET_LEDGER.md` 改为“两个口径的电池行都扣除同时段 buy-back”（注释在 `CREATE TABLE` 之前，不进入 sqlite_master）；生成文档、UI 合同夹具、P0_GOLDEN_DELTA（0 条无法归因）、source-release-manifest 已刷新。

## 3 golden 与夹具

| 对象 | 处理 |
|---|---|
| D1、D2 | r11，只有核算区 3 列（验证报告中声明偏差由 5 条变 3 条） |
| D3 | r14，轨迹 48 列、核算 138 列，报告 `tests/golden/reports/D3-r14.json` |
| D4 | r12，轨迹 110 列、核算 162 列，报告 `D4-r12.json` |
| D5 | r3，轨迹 99 列、核算 360 列，报告 `D5-r3.json` |
| C1–C8 | `capture.py check`：门控区不变 |
| C9、C10 | 需要本地构建的 GBP1 public2 / R029 public2，未重建；修正口径代码路径未改，oracle 报告形状保持不变 |
| 96 期合成复现 golden | 修订 4（新增的 A26 专用轨迹路径，见偏差 3） |
| P0-4 逐表夹具 `tests/fixtures/p04_trajectory_golden.json` | 按 R4-1 重新采集一次（偏差 4） |

数值报告的生成：`capture.py numeric-report` 要求父提交的输出与上一修订完全一致，而父提交 6fecfc6 与 D3 r13 / D4 r11 / D5 r2 在身份区有 16–17 列不同（R1-2、R3-3 后的模块版本、来源哈希；轨迹区、核算区逐位相同，已核对）。按 R1-2 的先例，用 `gridform_validation.golden.build_numeric_report` 直接生成，报告中加 `parent_reproduction` 一栏列出这些身份列；修订 delta 中有、但父子输出相同的那一列（父提交之前的身份漂移）记为 `unchanged_since_parent`。`capture.py validate` 通过。前后对比摘要在 `docs/dev/p0-reports/r41-golden/`。

## 4 实测结果

**GBP1 public1 2025，论文复现口径（D5）**

| 指标 | 修复前 | 修复后 |
|---|---:|---:|
| `period.surplus_conservation` | 失败 563 行 | 通过 |
| `period.envelope` | 471 个时段下界越界 | 通过 |
| A2 缺口 | 300,855 MWh | 78,810 MWh（−222,045 MWh） |
| stress 时段 / 事件 | 890 / 157 | 487 / 74 |
| 储能门 | 带声明偏差（单向 15,653 行，超额定 448 行） | 通过（`reproduction_conformant`） |
| 能量平衡门 | `failed` | `reproduction_conformant` |
| 原始不变量（Q14） | `failed`，年度结果隐藏 | `passed`，年度结果发布 |
| 储能充 / 放 | 5.05 / 3.66 TWh | 2.42 / 1.75 TWh |
| 头条运营成本 | £4,317.5 m | £4,287.0 m |
| 直接排放（统一因子集） | 30.91 MtCO2 | 30.68 MtCO2 |
| 投资提案 | 3,036.4 MW | 3,029.3 MW |

缺口减少 222 GWh，任务估计约 217 GWh：多削的 217,140 MWh 全部消失，其余约 5 GWh 来自储能不再同时充放。剩下的 78.8 GWh 是 P3-01 的隐藏缺电（A2 记账保留）。oracle 自身的原始状态仍是 `failed`，原因只有 `period.boundary_residual`（487 个 stress 时段，只作证据，不是门控）。

**VALUE 101 论文复现口径**：D3（一天）和 D4（两年）的储能门由带声明偏差（单向 10 / 9,343 行）变为通过，原始不变量 `passed`，按 Q14 年度结果会发布；surplus conservation 修复前后都通过。D3 接纳供给 780.5 → 775.5 MWh（等于需求），VRE 接纳 315.9 → 347.0 MWh。

## 5 测试

- 新增 `tests/test_r41_doctoral_kernel_errors.py`（17 个，全部 OK），每项都有手算 oracle：
  - A15：水电 20 MW 可削、需削 15 MW → 水电 5、风电保持 30（修复前风电 15）；两个子分支（有零价出口线路 / 无出口线路）都测；第 301 期形态（水电全削、CCGT 补 10 MW）；VRE 分支本来就正确（对照）。
  - DEV-BAL-04：核电盈余 4 MW、平衡需求 3 MW → 核电保持 14 MW、平衡费 0（修复前 17 MW、费 30）；需求超过盈余时核电按爬坡 +1、CCGT 1；VRE 盈余照旧调度并付费。
  - DEV-STO-01：平衡阶段共用额定功率（储能 200 而非 300、调峰机 150）；削减分支 buy-back（交付 60、不充电、SoC = 200·(1−0.000021) − 30）；平衡盈余与放电相抵（储能恰好 17 MW、供给 52 = 需求）；VRE 盈余相抵后进入 S；未分类盈余不相抵、在放电的储能不充电；`close_period` 拒绝既充又放。
  - 目录与身份：三项都是通用修正、两个口径都生效；去掉它们的旧集合哈希不同（Q13）；VERSION_LEDGER R4-1 opt-in；advisory 只对论文口径和无口径 Run 显示。
- 修改的已有测试：`test_native_corrected_rules`、`test_native_market_rules`、`test_native_reproduction_golden`（HEAD 语义改在修订 0 上验证，新增 R4-1 语义测试，修订测试改用 `_frozen_base`）、`test_native_operating_cost`（论文 carry 改在 legacy tariff 变体上展示）、`test_p04_validation_gate`、`test_p04_variant_fixtures`、`test_p04_surplus_routing`、`test_p04_validation_presentation`、`test_run_invariants`、`test_raw_invariant_failures`、`test_fx4_storage_orders`、`test_result_advisories`、`test_r33_restart_price_base`、`test_golden_digest`、`test_golden_research_pack`。
- 全量后端 ratchet（`run_backend_tests.py`）与 `p0_gate.py quick`：第二个提交前在暂存状态下运行，status passed（前端 typecheck 与 eslint 因 app/ 未改动按规则跳过，其余步骤全部通过，append_only 对新基点），ratchet 无新增失败。`capture.py validate`、`delta_report.py --check`、`check_methodology_catalog.py`、`check_version_ledger.py`、`seal_runtime_overlay.py --verify`、`refresh_source_release_manifest.py --check` 均通过。`test_documentation_consistency` 中直接运行时失败的 6 个是 M0 基线中已有的失败。
- 收尾检查：INSTALLED 的 `find … -newer install-receipt.json …` 只列出 `.supervisor.lock`（现网 supervisor 2026-10-03 创建的 0 字节锁文件，早于本单元，以往报告已说明）；`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”。没有启动服务器；scratch 中的运行输出已删除。

## 6 采用的决定

A26（三项通用修正、论文 golden 重基线一次、Q13 确认）、A15（做法 C）、Q1（论文设定本身不改）、Q12（核算区与轨迹区分开记录）、Q13、Q14、A2（P3-01 缺电仍记为 stress，不改调度）。

## 7 偏差

1. **DEV-STO-01 的 correction id 沿用 `p06.storage-net-per-period`，改为通用**，没有另起 `r41.*`。理由：任务要求“修正口径已有规则且物理相同就复用”；如果另起新 id，原来的 profile-gated 开关就成了不再切换任何行为的死开关（目录检查要求每个 profile-gated 修正被代码查询），旧论文 Run 还会同时显示两条重复 advisory。复用后语义清楚：修正口径从 P0-6 起、论文口径从 R4-1 起都适用。
2. **`APPEND_ONLY_BASE` 由集成者步骤移动**（8336d18 → 03e39ed）。新增论文轨迹例外必须这样做（gate 的提示原文如此）。为此拆成两个提交：第一个只登记例外（该提交单独看 append_only 不通过，提交说明已写明），第二个移动基点并包含全部实现。
3. **96 期合成复现 golden 新增轨迹修订路径**：原工具只允许核算修订（当时的理由是“合成输入绕过数据读取，没有任何通用修正能改变它”），A26 的修正改的正是它运行的市场函数。新增 `append_revision(..., trajectory=True)`，只接受 A26 的三个 correction id，每个只能一次；轨迹修订有自己的体积预算（320 KiB，本次约 264 KiB）。冻结的 35aadb3 循环没有时段收尾调用，驱动在时段边界替它关闭储能头寸（幂等）。
4. **P0-4 逐表夹具整体重新采集一次**，替换 M0 的 HEAD 采集（git 历史中保留，采集脚本新增 `--plan-step` 标注）。
5. **数值报告不用 `capture.py numeric-report`**（原因见第 3 节，R1-2 先例）。
6. **buy-back 不退还日前储能报酬**（与修正口径相同，方法学草稿已写明）；VRE 盈余相抵后作为 VRE 出力进入 S，但不另付平衡费（VRE 报价 0.0001 £/MWh，影响可忽略）。
7. 交接文档（`docs/handoff/*`）按 A27 将在 R4 结束后从头重写，本单元没有改它们；方法学 0.4 草稿已更新。

## 8 遗留问题

- C9、C10（GBP1 public2、R029 public2 修正口径）没有在本地重建研究包后复核；修正口径的代码路径与 oracle 报告形状未变，预期不变。
- `docs/visibility-refactor/RELEASE_0.4.md` 中关于 DEV-BAL-04 的旧发布说明是历史记录，未改。
- 前端渲染测试中的 DEV-STO-01 文字是合成夹具，旧 Run 仍可能出现该 id，未改。
