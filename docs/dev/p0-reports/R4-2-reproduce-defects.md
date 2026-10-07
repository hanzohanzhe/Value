# R4-2 复现角色的中低缺陷与定点验证缺陷（DECISIONS A27）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `bb9b9c6`。
- 范围：最终构建四角色测试报告（`fab9ec2`）第 2.3 节的 R-中1、R-中2、R-低1…R-低10，第 6.5 节的 T-低1，以及第 7.1 节中与复现角色同根因的 S-低7(c)（规划表、标签表）。
- 依据：DECISIONS A27（作者：“四角色测试的中低缺陷你也可以一起修好”）。界面按 `P0_FRONTEND_DESIGN_SPEC.md` 的现有组件、token 和文案风格实现；规格未覆盖之处记入 `P0_FRONTEND_DEVIATIONS.md` 的 F-R42-1…10。

## 1 结果一览

| 缺陷 | 结果 | 提交 |
|---|---|---|
| R-中1 规划面板 JS 错误 | 已修 | `7b32d8d` |
| R-中2 比较页扣留理由写错、导出为空 | 已修 | `a842d32` |
| R-低1 规划表缺年份 | 已修 | `14c50d2` |
| R-低2 运行中显示不相关的生物质提示 | 已修 | `d3d3184` |
| R-低3 “has started” 提示跟随到其他页面 | 已修 | `43426a7` |
| R-低4 “Export ledger” 不导出 | 已修（改名） | `78dcf93` |
| R-低5 字段名直接上界面 | 已修（统一标签表） | `72530bc` |
| R-低6 恢复包成为默认数据包 | 已修 | `8f59441` |
| R-低7 口径不支持的计算域仍标 ready | 已修 | `c63fc4c` |
| R-低8 运行时间估算差 6 倍 | 已修（首次估算给区间） | `db50b03` |
| R-低9 replay CSV 成本合计差 £195 | 已查明并在导出处说明 | `f32c3bb` |
| R-低10 被扣留 Run 的 VRE 请求 409 记为控制台错误 | 已修 | `a1da5e2` |
| T-低1 准备期间 Execution 显示 Queued | 已修 | `72530bc` |
| S-低7(c)（第 7.1 节共性） | 已随 R-低1、R-低5 修复 | `14c50d2`、`72530bc` |

另有一个文档提交（本报告与 `P0_FRONTEND_DEVIATIONS.md` 的 R4-2 一节）。没有未修的缺陷。

## 2 逐项说明

### R-中1 规划面板 JS 错误

- 成因：`/api/runs/{id}/planning/summary` 原样返回 v2 索引的 `summary.json`（`value.planning-project-index/v2`），其中没有 `years`；前端直接调用 `payload.years.find`。
- 修复：
  - `planning_index.planning_summary_payload`：带 `years[]` 的旧版摘要原样返回；否则从 `project-index.sqlite` 生成按年行，索引级字段一并保留。
  - `query_index_summary` 补充技术、地区、预计完工年份的分组，以及当年事件按类型和原因码的分组，面板的各分栏都有内容。
  - 前端改由 `planningView.planningYearFromPayload` 读取；缺 `years` 时写 “Planning evidence is not recorded for this year.”，不再抛错。
- 测试：v2 样例、payload 规则、HTTP 路由（`tests/test_r4_reproduce_defects.py`）；前端单元测试；scratch 实例上 Playwright 展开面板，无页面错误（见第 4 节）。

### R-中2 比较页扣留理由与导出

- 修复（后端）：
  - `results_summary.annual_withholding_reasons` 按原因各出一行：`teaching_run`，或 `result_publication_withheld`（Q14）。后者写明失败的原始不变量及行数，或写明“未评估”。
  - `build_run_summary` 在 `result_publication` 中带上 `raw_invariant_failures`。
  - 因 Q14 扣留时，`comparison_scope` 为新值 `annual_publication_withheld`，不再写 `annual_scientific`。配置相同时的警告和 `storage_pricing_interpretation` 不再称其为 teaching。
  - Q14 情形下只有被扣留的 Run 没有年度行；已发布 Run 的年度值保留在 `runs[]` 和 CSV 中，不给差值。教学课比较仍然不带年度值。
  - CSV 在指标表头之前写 `comparison_scope`、`annual_metrics_withheld`，并为每个原因写一行 `annual_withheld_reason`。
- 修复（前端）：`comparisonReview.annualWithholdingNotice` 按原因生成信息框（F-R42-2）。
- R4-1 之后，VALUE 101 的论文复现 Run 已能发布（本轮实测 `raw_invariants_status: passed`）。此时修正口径与论文口径比较不出现扣留框，两者的年度值和差值正常显示（R-中2 的“理由写错”在这种情形下不再出现）。
- 扣留情形的界面检查：把测试夹具 `doctoral-no-invariants`（Q14 未评估）复制进 scratch 数据目录，与修正口径 Run 比较。信息框写明该 Run 被扣留的原因；CSV 含原因行，并含已发布 Run 的 2025 年指标行。

### R-低1 规划表

- `query_index_projects` 返回每行的 `year` 和 `record_unit: "project_year"`。
- Inspect 标题改为 “N project-year records”，加一行说明，第一列为 Year，行键改为项目和年份（F-R42-6）。旧版规划账本保持原标题。

### R-低2 运行中的提示

- 成因：Run 冻结输入之前读不到机组清单，按“读不到就保留提示”的规则列出了生物质提示。
- 修复：Run 处于活动状态且机组清单不可读时，不列出按资产筛选的提示（通用 fleet_assets 行，以及带 `assets_any` 的修正提示）。已完成 Run 仍按“宁可多提示”的规则处理。
- 运行记录增加 `advisories_provisional`；界面在摘要后注明 “provisional …”（F-R42-3）。

### R-低3 提示的作用范围

- `StartedRunNotice` 记录发起时的 Study 和页面。`runHistoryView.startedRunNoticeVisible` 只在原 Study 的原页面上显示该提示（F-R42-4）。
- 实例验证：在 Runs 页启动一日课，提示出现；切到 Studies 后消失；切回 Runs 后再次出现；换到另一个 Study 后消失。

### R-低4 “Export ledger”

- 该按钮只是打开 Inspect 的产物列表，因此改名为 “Open ledger files”，行为不变。
- 规格把这个动作命名为 `Export ledger`，改名记为 F-R42-1，待设计方确认。
- 真正的打包下载已有 Inspect 的 “Prepare audit bundle”，没有另做。

### R-低5、T-低1 标签

- 新增 `app/features/shared/labels.ts`，作为指标名、状态词和阶段名的唯一标签表：
  - 代码匹配不区分大小写和分隔符，因此 `Application Submitted` 与 `application_submitted` 是同一个代码；
  - 未知代码按首字母大写的短语显示。
- 使用位置：比较页的指标标题和判读标签、Runs 校验条、年度卡片的规划计数（“Failed: Not applicable”）、规划面板、Inspect 规划项目表和事件表。
- T-低1：准备期间（`snapshotting`）Runs 校验条的 Execution 写 “Preparing”，Run 上下文条写 “preparing”（F-R42-5）。
- 同步更新了已有测试中的旧标题：`comparison-review` 单元测试、e2e `comparison-review.spec.ts`、`run-context-bar` 渲染测试和 e2e `run-context-methodology.spec.ts`。

### R-低6 默认数据包

- 成因：页面载入时的默认 id 不在列表中，刷新时取第一个完整的包；恢复出来的包按名称排在 “VALUE 101” 之前。
- 修复：`studies/draftPack.defaultDraftPackId` 保留仍然存在的选择；回退时跳过带 `frozen_recovery_origin` 的包和网络叠加包。页头 pill 使用同一回退规则。
- 用户明确选中的恢复包仍然保留。

### R-低7 计算域徽章

当前口径不接受的计算域卡片原本已被禁用（当前选中的除外），现在徽章也改为 “not available with this methodology”（F-R42-7）。实例上选论文复现口径后核对过。

### R-低8 运行时间估算

- 查明：两次估算的差别与口径无关。第一次估算时还没有已完成的本地 Run，用的是 0.03 s/期的经验值（GBP1 规模）；第二次用了实测值。
- 修复：
  - 没有可比 Run 时，后端另给 `runtime_range_seconds`（0.005–0.03 s/期，分别对应最小和最大的发行规模）和 `runtime_basis_kind`；`runtime_seconds` 不变。
  - 界面写 “estimated 3 min to 18 min (no comparable completed Run yet)”；有实测时写一个值，90 分钟以下用分钟（F-R42-8）。

### R-低9 replay CSV 与年度成本相差 £195

在 scratch 实例上新跑一个 VALUE 101 修正口径两年 Run 核对：差额来自口径不同，与舍入无关。

- 每期的 `physical_resource_cost_gbp` 是内核的 retained period cost，即已接受报价按报价计价，等于 `market_settlement_components.retained_period_cost`。
- 年度成本账按 `value.native-operating-cost/v1` 计算：发电按调度单位成本，储能按循环损耗。
- 2025 年差额 195.35 的构成：
  - 储能报价支付 34,837.02 减循环损耗 34,651.84，得 185.19；
  - 弃电支付 10.39；
  - 发电报价与单位成本之差 −0.23。
- 2026 年差额 65.60：储能 66.01，发电 −0.41。

处理：不改运行产物；导出面板为各格式加一行说明（F-R42-9）。

### R-低10 被扣留 Run 的 VRE 页

`runValidation.annualResultsWithheld` 先检查发布状态。被扣留时不发年度 VRE 请求，改为显示 “Annual VRE results withheld” 和去向说明（F-R42-10）。实例上用扣留夹具核对过：控制台没有 409。

## 3 改动的文件

- 后端：
  - `gridform_core/planning_index.py`
  - `backend/server.py`
  - `gridform_core/results_summary.py`
  - `gridform_core/result_advisories.py`
  - `gridform_core/preflight.py`
- 前端，新增：
  - `app/features/runs/planningView.ts`
  - `app/features/shared/labels.ts`
  - `app/features/studies/draftPack.ts`
  - `app/features/market/replayExportNotes.ts`
- 前端，修改：
  - `RunResults.tsx`、`RunWorkspace.tsx`、`runHistoryView.ts`、`runs/types.ts`
  - `AuditView.tsx`、`evidence/types.ts`
  - `ComparisonWorkspace.tsx`、`comparisonReview.ts`
  - `runValidation.ts`、`runContext.ts`
  - `StudyComposer.tsx`、`methodologyChoice.ts`、`studies/types.ts`
  - `ReplayExportPanel.tsx`、`app/page.tsx`、`app/globals.css`
- 测试：
  - 新增 `tests/test_r4_reproduce_defects.py`（5 类、10 个测试）；
  - 新增 `tests/frontend/unit/r4-reproduce-defects.test.mjs`（13 个测试）；
  - 更新的已有测试见 R-低5、R-低8 两节。
- 文档：
  - `docs/dev/P0_FRONTEND_DEVIATIONS.md` 的 R4-2 一节；
  - 本报告。

## 4 测试与结果

- **每个提交前：**
  - 运行相关的后端单元测试，均 OK：`test_r4_reproduce_defects`、`test_planning_index`、`test_results_summary`、`test_result_advisories`、`test_comparison_identity`、`test_local_api_boundary`、`test_r33_biomass_disclosure`、`test_preflight`；
  - 运行前端 unit/render 测试和 `tsc -p tsconfig.frontend.json`，均通过；
  - 刷新发布清单：`refresh_source_release_manifest.py --index`。
  - `test_prompt89_value_101_results` 的 1 个错误属于 M0 基线中已有的失败。
- **`scripts/p0_gate.py quick`：**
  - 代码提交完成后在 `f32c3bb` 上运行，状态 `passed`，14 步全部通过，没有豁免；
  - `backend_ratchet` 没有新增失败；
  - node 测试 311 个全部通过；
  - typecheck 和 eslint ratchet 通过；
  - network_guard 和 installed_inventory 通过。
  - 文档提交前在暂存状态下重跑，同样 passed。
- **scratch 实例：**
  - 配置：API 18890、UI 18891，`VALUE_DATA_HOME=scratchpad/build/r4ui/data`，用 vinext 重新构建 dist；
  - 跑了 VALUE 101 修正口径两年 Run 和论文复现口径两年 Run（论文复现口径已发布，raw invariants passed），以及一日课；
  - Playwright headless（chromium 1243）共 19 项检查，全部 PASS，覆盖 R-中1、R-中2（已发布对和扣留夹具两种情形，含 CSV）、R-低1、R-低3、R-低5、R-低7、R-低8、R-低9、R-低10 和 T-低1 的校验条；
  - 截图在 `scratchpad/build/r4ui/shots`；
  - 两个服务按记录的 PID 停止，数据目录（约 750 MB）已删除。

## 5 采用的决定

- A27：中低缺陷全部修复。界面按规格的现有约定实现，偏差登记在 F-R42-*。
- Q14：被扣留 Run 的年度值不在任何结果页或比较差值中出现。已发布 Run 自己的年度值进入比较导出，这与它在自己的结果页上已经公开一致。
- 不改运行产物：R-低9 只加说明，没有修改 ledger 或字段字典，golden 不受影响。

## 6 偏差

1. **R-中2 的“并排显示已发布 Run 的年度值”只写进导出，页面上没有显示。** 这需要新的表格布局，规格没有覆盖，记为 F-R42-2，待设计方确认。
2. **R-低4 选择改名，没有做打包下载。** 已有 Prepare audit bundle；规格中的动作名需设计方确认（F-R42-1）。
3. **R-低9 没有改列名。** 列名 `physical_resource_cost_gbp` 属于 ledger schema，改名会影响已发布的 Run 和 golden；说明放在导出面板，运行产物不变。
4. **门禁按代码提交完成后的状态运行一次，没有在每个提交前各跑一次。** 每个提交前都跑了相关测试、tsc 和清单刷新。这与 R3-4 的做法相同，以减少重复的长时间运行。
5. **R-中2 的扣留情形用测试夹具在 scratch 实例上验证。** R4-1 之后 VALUE 101 的论文 Run 已能发布，自然产生不了扣留情形。

## 7 环境核对

- INSTALLED：
  - `find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（0 字节，属作者实例，测试报告第 8 节已说明）；
  - `diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”。
- 进程：只按记录的 PID 停止了自己启动的 API（690701）和 UI 网关（751934）；没有连接 8766/8800 端口。
- Python 全部经 `vpy` 调用，INTEG 中没有 `__pycache__`；没有 push，没有改 remote。
- scratch：`scratchpad/build/r4ui` 只剩脚本、日志、门禁报告和截图，约 0.6 MB。
- 文档提交的门禁：在暂存状态下运行 `p0_gate.py quick`，status passed，全部步骤通过，没有豁免。

## 8 遗留与建议

- 年度卡片的 “Planning evolution” 计数（例如 Active 0）与规划面板的同年计数（Active 2）出自不同的记录口径。这不在本轮缺陷范围内，未改，建议在下一轮统一说明。
- F-R42-1、F-R42-2、F-R42-5、F-R42-8、F-R42-9 待设计方复核文案。
