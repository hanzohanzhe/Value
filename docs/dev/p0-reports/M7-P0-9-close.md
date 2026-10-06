# M7-P0-9-close 工作报告：P0-9 语义适配、stress event 界面、设计裁决与 S12 文档

- 分支：直接提交在 `fix/review-2026-10-04`（INTEG），起点 `1f527e6`（设计方 2026-10-06 裁决）。
- 解释器一律经 `build/bin/vpy`，Node 经 `build/bin/vnode`；浏览器测试用本机 chromium 1243（`VALUE_E2E_CHROMIUM`）。
- 用户要求“基本顺利后迅速推进”：每个提交前跑受影响的测试与 `p0_gate quick`；另外跑了一次离线 e2e（带棘轮）、golden fast 与全部前端测试组，没有跑 `p0_gate full/nightly`（属 X0 S13 集成验收）。

## 0 接手时的状态

上一次尝试中断，工作树里有一组**已暂存、未提交**的改动（16 个文件），内容是 M2 界面审查小问题 1–3。我逐项核对：

- 小问题 1：`unitCostText` 按 `system_cost_definition_id` 选 `served` / `generated` / `(basis not recorded)`，与 `model_runner._frontend_results` 的实际口径一致（有 CEM 账时取 `cem_system_cost_gbp_per_mwh_served`，遗留口径取 `Cost_per_MWh_GBP`，即 total_system_cost / total_energy_generated）。
- 小问题 2：新增状态词 `stopped`（`Stopped · n%`），`Withheld` 只留给 Q14。
- 小问题 3：`result_queries` 对“已取消或失败、缺少声明年份”的 Run 返回 `unavailable`。

这些改动正确、有测试，quick gate 通过，因此全部保留，作为第一个提交；没有丢弃任何内容。

## 1 提交

| 提交 | 内容 |
|---|---|
| `f267219` fix(results) | M2 小问题 1–3（接手的暂存改动） |
| `f002c3e` fix(ui) | M2 小问题 4–6：孤立点画成圆点（`seriesShapes`）、无事件组显示 `No events recorded`、窗口摘要网格改为固定三列（1280 px 无空白格）、`server.py` PEP 8 空行 |
| `aab6134` feat(ui) | F-P04-1…5、F-P09-6：下界 `≥`（状态条、stress 提示、窗口卡共用 `shortfallDisplay`）、`● Conformant`、gate 失败 Callout（列出各 gate）、`Annual results not published`、Inspect 原始残差面板、Q14 与 gate 的 reason code |
| `dbccf51` feat(market) | 规格 4.4：全年 stress event 读模型 `query_stress_events` 与接口 `GET /api/runs/<id>/market/stress-events`；Market replay 中的列表（分页 50、数值排序、Replay →）；`Show stress events` 打开该列表；网络页可靠性列表加指引 |
| `b7ba862` feat(results) | P0-6/P0-7 语义适配：C30（native 运营成本含 VoLL，读取 `physical_operating_cost_detail_gbp`）、C20（corrected 列语义与 `corrected_unused_vre`）、UI 契约夹具重新生成 |
| `68c6fa0` feat(data) | F-P05A-1：CSV 映射的 Currency / EUR per GBP / FX basis / Price year、`GF_MAPPING_FX` 字段错误、预览原值与换算值并排（后端审阅报告增加 `source_sample_rows`、`fx`） |
| `6544b04` feat(network) | 规格 4.6 最后一条（F-P08-1、F-P09-8）：运行期 fallback 审计 caution Callout |
| `2702d18` docs(p09) | P0-9 S12：字段映射、契约增量、MARKET_LEDGER、USER_GUIDE 中英、CHANGELOG、偏差记录 F-M7-1…14、文档一致性测试 |
| `a691c0b` fix(ui) | e2e 发现：stress 列表收到非预期响应体时整页崩溃 → 校验后显示错误框；截图发现：成本构成表继承全局 `table { min-width: 800px }`，使 Runs 页在 1280 px 下溢出 227 px → `min-width: 0` |
| （本提交）docs(p0) | 本报告与 `docs/dev/p0-ui-screens/` 截图 |

## 2 实现要点

### 2.1 stress event（规格 2.3(4)、3.1、3.3、4.4；决策 A2）

后端字段自 M2/M4 起已存在（run 级 `stress`、replay 窗口的 `shortfall_mwh`/`stress_periods`/`shortfall_basis`/`shortfall_upper_mwh`、账本 `stress_event` 表）。本单元补齐界面：

- 状态条 Stress events 字段与 Callout 4：沿用 M2b 的实现，下界按 F-P04-1 加 `≥`，悬停给上界。
- 窗口卡 `Shortfall` 与 `● n stress periods`，图上 4 px 琥珀带与图例（M2 已有，本单元核对并加下界显示）。
- 4.4 全年列表：新读模型只读 `stress_event` 表，没有该表的旧账本返回 `status=not_recorded`，界面说明“不记录”，不说“没有事件”；空列表文案沿用 4.4 的覆盖率规则。列表位置的偏差见 F-M7-4。
- 不改调度，不在前端做任何减法（A2、规格原则 1 与验收清单第 9 条）。

### 2.2 语义适配（计划 4.9 集成修订、C20/C29/C30）

- **成本定义 v2（P0-7）**：Runs 页早已读取 `ror_hydro_compatibility_capital_gbp`（P0-7 S8 的实际键名），memo 行文案按 F-P09-7；只有 corrected 口径把兼容资本移出头条时该字段才非空，doctoral 为 null，不显示 memo 行。
- **VoLL 计入 operating（P0-6 S4，C30）**：M2 的 `VOLL_BASIS_BY_LEDGER_LINE` 把 `operation.generation_import_and_reliability` 标为“只有分区时含 VoLL”，P0-6 之后 native PSM 的这一行在铜板下也含“记录缺电 × VoLL”。现在 model_runner 按年读取 `orchestrator_results[].market.extensions.physical_operating_cost_detail_gbp`，有 `blackout_reliability` 即判为含 VoLL，并导出 VoLL 部分与单价供提示使用。`test_native_mechanism_scope` 中 C2（native 铜板）的旧断言 `False` 已过时，改为 `True`。
- **corrected VRE 事件口径（C20）**：读取账本声明的 `curtailment_semantics`；corrected 下 `event_basis=corrected_unused_vre`，不再给出“excess + curtailment”组；VRE 页标签改为 Non-VRE spill / VRE curtailment / Accepted VRE (gross output)。doctoral 不变。
- **边界边际值（P0-8b）**：M6 已完成（F-P09-9），本单元核对无需再改。

### 2.3 设计裁决

M2 小问题 1–6、F-P04-1…5、F-P09-5…7、F-P05A-1 全部实现；F-P09-5 为“批准”，无需改动。与裁决字面不完全一致的地方都记入 `P0_FRONTEND_DEVIATIONS.md` 的 M7 一节（F-M7-1…14），需设计方确认的有：F-M7-4（stress 列表放在 Market replay）、F-M7-7（各 gate 的一句话文案）、F-M7-10（corrected VRE 标签文案）、F-M7-12（fallback Callout 标题与说明句）。

## 3 规格第 9 节验收清单

| # | 检查 | 结果 |
|---|---|---|
| 1 | 七个视图（含 Runs 页内的 Compare）搜不到 `£0/MWh`、`0 TWh`、`valid single-node`、`Result invalid`、`Clearing price` | 截图脚本对 24 张截图的页面文本逐一检索：0 命中 |
| 2 | 缺电 Run：窗口卡 Shortfall 与 stress 时段数、状态条 Stress events、图上琥珀带 | 通过（`market-replay-*`、`m7-show-stress-events-*`：Release R2 预测数据的修正口径新 Run，48 期、779.1 MWh，exact） |
| 3 | doctoral 被 withheld：Withheld Callout、无年度合计、Inspect/导出可用 | 通过（`m7-runs-doctoral-withheld-*`，两年 Run，`GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED`） |
| 4 | 修复前旧 Run：`Methodology not recorded`、`Superseded`，无绿色 passed | 通过（`m7-run-context-r2-prefix-*`，并显示 `≥ 571 MWh`） |
| 5 | 6 个结果视图都有口径徽章 | 通过（Run 上下文条在全部 Run 视图出现；SSR 与 `run-context-methodology` e2e 4/4） |
| 6 | 新元素无 < 12 px 字号 | 通过（CSS guard，新增 `residual-panel.css` 已加入扫描名单） |
| 7 | 键盘与 focus-visible；axe critical/serious | 新列表加了 `:focus-visible`；`market-visibility` e2e 的 axe 检查通过 |
| 8 | 375 px 新组件不引起页面级横向滚动 | 新组件自身不溢出；页面级溢出来自旧侧栏导航与旧表格（逐元素排查确认），同 F-P09-13，记 F-M7-13。1280 px 下 Runs 页的溢出由本单元修复 |
| 9 | 前端不做物理量减法 | 通过（frontend guard；EUR 原值由后端报告，不反算） |

## 4 测试与结果

| 测试 | 结果 |
|---|---|
| `p0_gate quick`（每个提交前） | 共运行 12 次，每个提交前最后一次均为 `passed`。另有两次未通过：一次因工作树中的临时截图脚本使发布清单过期（删除后重跑通过）；一次因我提前删除了 gate 的 TMPDIR，`tests/ui-gateway.test.mjs` 挂起，按 PID 停止本人启动的该次 gate 进程后重建目录重跑通过 |
| 前端 unit / render / harness / source-contracts | 117 / 32 / 3 / 63，全部通过 |
| 新增前端测试 | `stress-events-view`、`csv-mapping-fx`、`fallback-audit-view`；`vre-view`（圆点、无事件、corrected 标签）、`result-metrics`（单位成本口径、VoLL 提示）、`run-context-bar`（F-P04-1…5 的 SSR）、`network-coverage`、`reason-codes`；`csv-mapping-editor` 浏览器 harness 新增 EUR 流程 |
| 新增后端测试 | `test_stress_events_query`（3）、`test_p09_result_view_docs`（2）、`test_result_queries`（取消/失败归档 Run 为 unavailable）、`test_native_mechanism_scope`（VoLL 明细）、`test_data_mapping`（`source_sample_rows`、`fx`） |
| 受影响后端模块 | `test_result_advisories`、`test_market_replay`、`test_server_presentation`、`test_ui_contract_fixtures`、`test_results_summary`、`test_p06_corrected_acceptance`、`test_native_mechanism_scope`、`test_data_mapping`、`test_result_queries`：全部 OK |
| UI 契约夹具 | `--check` 只报预期差异（`curtailment_semantics` 键；value-101-day 的 corrected 事件口径），`--write` 后一致，207,712 字节 |
| 离线 e2e（带棘轮） | 37 passed，5 个已登记失败，4 skipped，0 新失败（首次运行发现 stress 列表崩溃，已修复） |
| golden `capture.py check --tier fast` | passed |
| 截图 | scratch 实例（API 18966、UI 18967，VALUE_DATA_HOME 在 scratch）上的真实 Run，12 个场景 × 1280/375 共 24 张 JPEG，覆盖并更新了 M2 的同名截图，新增 `m7-*` 截图；目录共 6.2 MB |

## 5 采用的决策

- **A2**：stress 只记录、不阻断、不改调度；界面不做减法。
- **Q14**：Withheld 只用于复现口径原始不变量未全通过；读取实际字段 `result_publication`（F-M7-1）。
- **Q6**：价格按口径标注（M2 已实现，本单元未改）。
- **P0-4 S7 gate**：production 口径 gate 失败用红色，与 Q14 的琥珀 Withheld 分开。
- **A7 / P0-7**：风光储 FOM 与兼容资本只作 memo，不进头条；界面只显示后端给出的 memo 字段。

## 6 偏差

见 `docs/dev/P0_FRONTEND_DEVIATIONS.md` 的“M7「P0-9 收口」”一节（F-M7-1…14）。另外两点：

1. 计划 S12 写“用 grep 核对文档与夹具一致”，我实现为单元测试 `test_p09_result_view_docs`：字段映射表中每个字段都必须出现在读模型源码或契约夹具中，并核对用户指南中英两版的关键短语。
2. 新增 API（stress-events）与审阅报告字段（`source_sample_rows`、`fx`）是只读读模型的增量，不改任何账本写入方，符合计划 4.9“只改读模型、序列化、前端和测试”。

## 7 遗留问题

- F-M7-4、F-M7-7、F-M7-10、F-M7-12 的文案或位置需设计方确认。
- F-P04-4 的 Callout 只有 SSR 测试，没有真实 Run 截图（scratch 中没有 gate 失败的修正口径 Run）。
- 375 px 下的页面级横向滚动来自旧布局（侧栏导航、Inspect 旧表格、merit order 阶段选择），属做法二。
- `p0_gate full/nightly` 与全量 e2e 留给 X0 S13 集成验收。

## 8 环境与安全核对

- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出在线 supervisor 的 `.supervisor.lock`（按惯例排除，非本单元写入）；`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”。从 INSTALLED 只做了只读复制（Release R2 的 Study、数据包与一个 Run，用于截图），没有写入。
- 没有连接 8766/8800，没有发送任何信号给作者的进程；只按记录的 PID 停止了本单元自己启动的 API（18966）与 UI（18967）服务；e2e runner 在 18800/18766 自启自停，结束后端口空闲。没有使用 pkill/killall。
- 工作树无 `.pyc`；SRC 工作树干净，main 仍为 `35aadb3`；没有 push。
- scratch：VALUE_DATA_HOME（含两年 Run，约 2.1 GB）已删除；`build/m7p09` 剩约 0.1 MB 的辅助脚本。
