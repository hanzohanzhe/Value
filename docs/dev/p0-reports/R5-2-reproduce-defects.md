# R5-2 复现角色最终验收的缺陷（DECISIONS A28）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `818d88b`。
- 依据：R4 最终四角色验收的复现报告（构建 `c204aac`，`scratchpad/build/r5/reproduce.md`）；A28 通过规则：高、中缺陷和任何影响运行结果的问题必须修并带测试；纯显示的低缺陷顺手能修就修，否则进待办。
- 复现报告没有高等缺陷；2 项中等、13 项低等。界面按 `P0_FRONTEND_DESIGN_SPEC.md` 的现有组件、token 和文案风格实现，规格未覆盖之处记入 `P0_FRONTEND_DEVIATIONS.md` 的 F-R52-1…11。

## 1 结果一览

| 缺陷 | 结果 | 提交 |
|---|---|---|
| R-中1 复现路径和 Runs 启动前看不到口径 | 已修（显示；不加选择控件，见第 3 节） | `eae2914` |
| R-中2 比较和 Run 卡片看不到弃电差异 | 已修 | `9dc3547`、`eae2914` |
| R-低1 准备期间反复请求、404 | 已修 | `eae2914` |
| R-低2 论文口径准备期间显示 Withheld / not evaluated | 已修 | `9dc3547`、`eae2914` |
| R-低3 运行中的 Run 显示历史复现面板 | 已修 | `eae2914` |
| R-低4 Planning evolution Active 与 Inspect 不一致 | 已修（标明口径，见第 2 节） | `eae2914` |
| R-低5 径流水电 advisory 不按资产筛选 | 已修 | `9dc3547` |
| R-低6 Project 列重复、Transition 列全为 “- -> -” | 已修 | `eae2914` |
| R-低7 无扩展 Run 的 Artifacts 页 “Not recorded” | 已修 | `9dc3547`、`eae2914` |
| R-低8 重跑的 `annual_input_state_sha256` 不同 | 待办（不是结果问题，见第 4 节） | — |
| R-低9 Replay CSV 缺 stress 列、价格列口径 | 已修 | `9dc3547` |
| R-低10 Accepted supply 两口径边界不同未说明 | 已修 | `9dc3547`、`eae2914` |
| R-低11 名称为空时按钮变灰无说明 | 已修 | `eae2914` |
| R-低12 比较 CSV 扣发值无原因列 | 已修 | `9dc3547` |
| R-低13 空状态写 “two full years” | 已修 | `eae2914` |

本轮没有改变任何模型数值：调度、投资、成本、碳和能量平衡都不变。新增的只是读出已有账本的字段和界面说明。

## 2 逐项说明

### R-中1 方法学口径

- `methodologyChoice.studyMethodologyText`：按 Study 的 `methodology.profile` 参数（缺省为目录默认口径），给出与 Studies 编辑器单选项相同的名称（`Corrected (default)` / `Doctoral reproduction`）。没有目录时显示记录的 id，不猜。
- 研究路径第 2 步新增 “方法学口径” 一项：名称、profile id，以及一行说明——沿用基线口径；要换口径，可选该口径的基线，或创建后在 Studies 编辑器中更改并保存新版本。
- Runs 页 “What will run” 新增 `Methodology` 一格。
- 研究路径不加口径选择控件。规格第 7 节把口径选择放在 StudyComposer，那里有白名单检查和参考配置预设；派生接口不处理口径切换。是否要在研究路径里直接选择，记为 F-R52-1，待设计方确认。

### R-中2 物理弃电量

- 原因：比较和年度卡片只列 v2 弃电归因三项。归因需要配对的反事实快照，只有 zonal PSM 提供，所以 copperplate Run 全部为 Unavailable。VRE 页显示的 “Unused VRE” 是另一个量：各时段 max(可用 VRE − 接受 VRE, 0) 之和。每种 PSM 都记录它。
- 后端：`results_summary.annual_unused_vre` 用一条 SQL 从 `market/market.sqlite` 读出该量，与 `query_vre_curtailment_summary` 定义一致。
  - 比较的年度指标新增 `unused_vre_mwh` 和 `unused_vre_share_percent`（`value.unused-vre/v1`）。这两项不受弃电归因证据门控，所以给出差值。
  - `model_runner` 在 Run 年度结果中写入 `unused_vre_mwh` 和 `available_vre_mwh`。
- 前端：
  - 年度卡片新增 `Unused VRE (PSM boundary)`：`{x} MWh · {y}% of available`。本次修复以前的 Run 没有这两个字段，卡片写 `Not recorded`。
  - 比较页用标签表新增两项的名称。
  - 原三项归因指标不变。
- 实测（VALUE 101，两年）：

  | 年份 | 修正口径 | 论文口径 |
  |---|---|---|
  | 2025 | 4,002.89 MWh（3.1%） | 2.00 MWh |
  | 2026 | 25,026.50 MWh（14.6%） | 2.00 MWh |

  这些数与 VRE 页和 metrics 中的 `curtailment_mwh` 一致。比较页给出差值 −25,024.5 MWh。
- 说明：论文口径的 “pre-balancing excess”（8,256 / 36,773 MWh）按论文规则在 S 之外分配（储能、出口、溢出）。VRE 页把它与 unused VRE 分开显示（规格 4.5 / G1-08），本轮的比较指标也不把它并入 unused VRE。

### R-低1 轮询

- 新增 `app/features/shared/stableRun.ts`：
  - `useStableRun` 只在 Run 的 id、状态或已完成年数变化时更换对象；
  - `runPreparing` 判断 queued / snapshotting。
- 使用这两个函数的页面：Market replay、VRE、Network & redispatch、Network & water。
- Market replay 在 Run 冻结输入期间显示 “The Run is still preparing”，不发请求。
- Inspect：
  - 准备期间 planning 和 market 页签不发请求；
  - Run 未结束时 planning 页签不请求项目索引，因为索引在 Run 结束时才写入（`application.materialize_planning_index`），页面给出说明。
- 实测：准备期间分别停留在 Market replay、VRE、Inspect 各 15–20 s，4xx 均为 0（原来 30 s 约 15 条）。

### R-低2 待评估

- 后端 `result_publication`：论文口径 Run 仍在进行（ACTIVE_STATUSES）且原始不变量尚未评估时，返回以下字段：
  - `status` 仍为 `withheld`，年度资源照旧门控；
  - `raw_invariants_status: "pending"`；
  - `reason_code: GF_RESULTS_PENDING_RAW_INVARIANTS`，并附说明句。
- 比较扣留原因写 “still running”。
- 前端：
  - 状态条 `Raw invariants` 写 `Pending`；
  - Callout 为 info 色 “Annual results pending the raw-invariant check”；
  - 年度结果区、VRE 页和结果查询面板写 Pending / Running。
- Run 完成后，若仍无证据，照旧写 “not evaluated”。

### R-低3

Run 处于 queued / snapshotting / running / cancel_requested 时，不渲染 “历史复现条件检查” 和 “从此 Run 的冻结输入创建独立 Study” 两块面板。Run 完成后两块面板照常出现（实测）。

### R-低4

- 两处计数口径不同：
  - 年度卡片计的是当年规划步骤之后仍 active 的项目（`planning_advance.active_projects`），不含当年新准入的项目；
  - Inspect 列的是年末的项目年记录。
- 卡片改为 `Active before admission: n` 加 `Admitted this year: m`，并悬停说明 Inspect 的 Active = n + m。
- 论文口径 2026 年实测：卡片为 0 + 1，Inspect 中 active 为 1。

### R-低5

`p07.compatibility-capital-out-of-headline` 的 `applies_when` 改为 `{"assets_any": ["natural_flow_hydro"]}`。`applies_when` 是展示字段，不属于方法身份（`Correction.semantic_identity`），已保存的 Study 和 Run 的方法身份不变。机组清单读不出时仍保留提示，规则同 R3-N7。VALUE 101 论文 Run 的 advisory 从 9 条降为 8 条。目录 sha 变化，`docs/generated/METHODOLOGY_PROFILES.md` 已重新生成。

### R-低6

- 项目名称等于 ID 时，Project 列只显示一次。
- v2 项目索引的事件没有 from/to 阶段。本页没有任何转换记录时，不显示 Transition 列。

### R-低7

- `extension_results.query_extension_artifacts`：先记录模块图 sha。
  - 没有扩展图、且冻结 Study 的 `selected_extensions` 为空时，返回 `no_extensions_selected`，界面只显示一句说明。
  - Study 选了扩展却没有扩展图时，仍为 `frozen_extension_graph_missing`。
- VRE 页的 v2 归因查询面板，在结果为 `unavailable` 或 Run 未结束时，不再显示 “Not recorded” 的来源身份格。这些身份按设计取自归因产物；没有产物，就没有可显示的身份。

### R-低9

- 平面导出（CSV / JSONL）在 `period_start_utc` 之前新增 4 列：
  - `clearing_price_basis`：Q6 口径，例如 `average_period_cost`；
  - `period_shortfall_mwh`、`period_stress`、`shortfall_basis`：与回放 API 的半小时 bucket 同一算法（`market_replay._bucket_stress`）。
- 原 `clearing_price_gbp_per_mwh` 列名不改。它是账本原列，改名会破坏既有使用者；口径由新列说明。
- 一整年 17,520 行的导出约 1 s。

### R-低10

- dispatch timeline 新增 `accepted_supply_boundary`（boundary_id、公式、说明）。
- 窗口卡在 Accepted supply 数值下写明边界：
  - 修正口径：“Full node: covers demand plus storage charge…”；
  - 论文口径：“Source-classified node: storage charged from pre-balancing surplus is outside this figure.”
- 2025-01-01 实测：修正口径 787.02 MWh，论文口径 775.49 MWh，与报告一致。

### R-低11、R-低13

- 名称为空时，按钮下写 “先在第 n 步填写新 Study 名称，才能创建。”。
- 空状态改为 “Choose a scope under Check for, check readiness, then run it. Wiring checks are quick; full scopes compute every model year.”。

### R-低12

比较 CSV 新增 4 列：`value_status`、`value_reason_code`、`delta_shown`、`delta_withheld_reason`。指标表头前缀不变，原有断言仍成立。

## 复审回应（Review response）

独立复审结论为 changes_required，一项 major，其余为 minor（按任务要求留待办）。

### major：比较页把不同边界测得的 unused VRE 当作同一量求差（已修）

- 复审意见成立。论文口径账本（`excess_relationship = separate_prebalancing`，`curtailment_semantics` 为平衡阶段下调）在 S 之外先把预平衡盈余分给储能、出口或溢出，再测 accepted VRE；修正口径（`curtailment_semantics = vre_available_minus_gross_output`）在全节点按可用减总出力测。上表的 −25,024.5 MWh 因此不是同一量的差。
- 修复（不改任何调度、投资或成本账本的数，只改读出和比较门控）：
  - `results_summary.vre_measurement_boundary` 按 `query_vre_curtailment_summary` 读的同一组语义元数据给出边界：`full_node_gross_vre_output`（修正）、`after_separate_prebalancing_excess`（论文）、`unsplit_unused_vre`（perfect foresight）、`not_recorded`（旧账本无元数据）。
  - `annual_unused_vre` 每年附上 `vre_boundary`；论文口径账本另给 `pre_balancing_excess_mwh`（`excess_mwh` 年合计，与 VRE 页 G1-08 的 pre-balancing excess 一致；修正口径下 `excess` 是非 VRE 溢出，所以为 None）。
  - Run 摘要的 `unused_vre_mwh`、`unused_vre_share_percent` 带 `vre_boundary`；新增年度指标 `pre_balancing_excess_mwh`（`value.pre-balancing-excess/v1`；非论文口径为 `not_applicable`、`ledger_does_not_separate_prebalancing_excess`）。
  - `metric_delta_gate` 新增参数 `vre_boundaries`：这三项指标在各 Run 边界不同时不给差值，`reason_code = unused_vre_boundary_differs`，原因句写明两个边界并说明论文口径的预平衡盈余单独列出。各 Run 的数值照常显示；比较值附 `vre_boundary`。同口径比较照常给差值。CSV 的 `delta_shown` 为 false，`delta_withheld_reason` 为上述原因句（CSV 列不变）。
  - 前端：标签表加 `pre_balancing_excess_mwh`，无值时写 `Not applicable`（F-R52-12）。差值隐藏与原因句沿用现有逐指标门控的渲染，无新组件。
- 测试：`tests/test_r5_reproduce_defects.py::UnusedVreBoundaryTests`（3 项：边界与预平衡盈余的读出；论文 vs 修正比较三项差值被隐藏、原因码正确、各 Run 数值保留、成本差值仍显示、CSV `delta_shown=false`；同口径保留差值）；`tests/frontend/unit/r5-reproduce-defects.test.mjs` 新增 1 项（原因句显示、标签、`Not applicable`）。
- 上文“比较页给出差值 −25,024.5 MWh”的说法由此作废：跨口径比较现在只并列两种口径的数值和论文口径的预平衡盈余，不给差值。
- 页面核对：本次只改后端数据和标签表；比较页隐藏差值与显示原因走的是已经过 Playwright 核对的同一渲染路径（AF3-1 逐指标门控），按 A28“不无止境测试”没有再起 scratch 实例做浏览器复测，改用单元测试覆盖。

### minor（留待办，不在本轮修）

- 整文件换行符归一化带来的 diff 噪声；导出压力查询中较大的 IN 列表；unused VRE 求和对 stage 的处理（与 VRE 页相同）。R-低8（`annual_input_state_sha256` 含 Run id）同意列为待办。

## 3 偏差

- R-中1 只显示口径，不在研究路径中加选择控件（F-R52-1，待设计方确认）。
- R-低9 不改原价格列名，以新增 `clearing_price_basis` 列说明口径。
- 新界面文案均列在 `P0_FRONTEND_DEVIATIONS.md` 的 R5-2 一节。

## 4 待办

- R-低8：`annual_input_state_sha256` 是年度输入状态的完整性哈希，用于检查点和年度链路核对（`application.py`、`run_invariants.py`、`model_runner.py`）。状态中的模型投资项目 ID 带 Run id 前缀（例如 `repro-doctoral-20261008-012531-a1838262:2025:onshore_Portsmouth:2`），所以两次重跑的哈希不同。
  - 这不影响结果：报告已确认重跑结果逐位一致。
  - 把 ID 改成与 Run 无关，会改变状态身份和检查点兼容性；另设一个 “去掉 Run id 的可重复性哈希” 是新功能，需要设计。
  - 本轮不改，建议下一轮决定是否新增。

## 5 测试

- 新增 `tests/test_r5_reproduce_defects.py`，15 个用例：
  - pending / not_evaluated；
  - advisory 资产筛选，以及 `applies_when` 不属于方法身份；
  - unused VRE 与 VRE 页一致，进入 summary 和比较且有差值，不受归因门控；
  - 比较 CSV 原因列；
  - 导出 stress 列与 API 一致；
  - timeline 边界；
  - 无扩展的扩展查询。
  - 结果：全部通过。
- 新增 `tests/frontend/unit/r5-reproduce-defects.test.mjs`，6 个用例，全部通过。
- 前端组（`run-ui-tests.mjs`）：unit 203/203、render 71/71、source-contracts 66/66 通过；`tsc -p tsconfig.frontend.json` 通过。
- 相关后端模块（21 个，260 个用例）：失败项与 HEAD 快照逐条对照，只多出 `test_generated_runtime_tables_are_current`，已重新生成 `METHODOLOGY_PROFILES.md` 修复。其余失败均为基线已有项，例如 prompt107 / 108 文档和 prompt123 导出夹具。
- UI 合同夹具：只多出新键 `accepted_supply_boundary`，用 `tests/ui_contract_fixtures.py --write` 重新生成（9 个文件，各 +1 行）。
- 门禁 `scripts/p0_gate.py quick`：
  - 第一次运行发现发布清单过期，以及上面的夹具差异；两项修好后，各提交前都用 `refresh_source_release_manifest.py --index` 刷新了清单。
  - 本报告提交的暂存状态下再次运行：status `passed`，16 步全部通过（backend_ratchet、node_tests、typecheck、eslint_ratchet、release_manifest 等），没有豁免，156 s。
- scratch 实例（API 18890、UI 18891，`VALUE_DATA_HOME=scratchpad/build/r5ui/r52/data`，vinext 重新构建），Playwright headless（chromium 1243）全部 PASS：
  - 准备期间：无历史面板；Pending 文案；What will run 显示口径；Market replay / VRE / Inspect 无 4xx。
  - 研究路径：两个基线都显示口径，空名称有提示；390 px 宽无横向滚动。
  - 完成后：年度卡片的 Unused VRE 与 Planning 计数；比较页 unused VRE 及差值、占比；Inspect 中 ID 只显示一次、无 Transition 列；Artifacts 写 “selected no optional extensions”；VRE 查询面板无 Not recorded 身份格；Market replay 两口径的边界说明。
  - API：两口径 Run 结果都含 unused VRE；论文 Run 原始不变量通过并发布；比较 CSV 含 unused VRE 和原因列；24 h replay CSV 含新列；扩展查询为 `no_extensions_selected`。

## 6 文件

- 后端：
  - `gridform_core/results_summary.py`（`annual_unused_vre`、比较指标与门控、CSV 原因列、扣留原因文本）
  - `backend/model_runner.py`
  - `gridform_core/result_advisories.py`（`WITHHELD_PENDING`）
  - `gridform_core/data/methodology/corrections/p07.json`
  - `gridform_core/market_replay.py`（`accepted_supply_boundary`）
  - `gridform_core/replay_export.py`（`_period_stress` 与新列）
  - `backend/extension_results.py`
- 前端：
  - `app/page.tsx`
  - `app/features/shared/stableRun.ts`（新）
  - `app/features/workspace/ResearchJourney.tsx`、`research-journey.css`、`runValidation.ts`
  - `app/features/runs/RunWorkspace.tsx`、`RunResults.tsx`、`resultMetrics.ts`、`runHistoryView.ts`
  - `app/features/studies/methodologyChoice.ts`
  - `app/features/evidence/AuditView.tsx`
  - `app/features/extensions/ExtensionResultsPanel.tsx`
  - `app/features/results/ResultQueryPanel.tsx`
  - `app/features/network/NetworkRedispatchView.tsx`
  - `app/features/market/dispatchView.ts`、`marketTypes.ts`
  - `app/features/shared/labels.ts`、`reasonCodes.ts`
- 文档：
  - `docs/dev/P0_FRONTEND_DEVIATIONS.md`（R5-2 一节）
  - `docs/generated/METHODOLOGY_PROFILES.md`
  - `CHANGELOG.md`（API contract changes 一行）
  - 本报告

## 7 清理与核对

- 进程：只按记录的 PID 停止了自己启动的 API（2131346、2153347、2200588）和 UI 网关（2200590、2219763、2238349）；各 Run 的 worker 已自行退出；端口 18890–18892 已释放。没有连接 8766/8800，没有按模式 kill。
- 运行中修改了后端源码，导致第一个修正口径 Run 被执行身份检查拒绝（`Execution source or runtime changed after enqueue`），这是预期的保护。之后的验证 Run 都在源码冻结后启动。
- scratch 中的运行数据、HEAD 快照、浏览器配置和截图已删除（`r5ui/r52` 余约 0.4 MB 脚本和日志）。
- INSTALLED 的核对结果见最终回报。
