# FX3 UI 修复批：设计规格第 11 节（S-D1、S-D2、R-D1、M-D3、M-D4、F-D3、S-D4、S-D5、M-D2）

分支 `fix/review-2026-10-04`（INTEG）。作者授权见 DECISIONS A16（“必须修 + 强烈建议一起修”；A16-4 M-D2 接受并记录）。
11.5（F-D2）已由 FX2 完成，本单元不涉及。

## 1 提交

| 提交 | 内容 |
|---|---|
| `5a4644a` fix(ui): readiness card lists every issue, grouped by priority (S-D1) | 11.1 |
| `15606c7` fix(preflight): show blocked reports without a revision; warn on in-place module edits (M-D3, M-D2) | 11.4 预检部分 + 11.7 |
| `215e92e` fix(ui): doctoral withheld notice names the failed raw invariant; Raw invariants field (R-D1) | 11.3 |
| `ad8a70f` feat(modules): Disabled and quarantined area, global Rescan, Enable from a fresh scan, Remove (M-D4, F-D3) | 11.4 Modules 页部分 |
| `be8179b` docs(modules): in-place source edits are accepted and recorded; Disabled and quarantined area (A16-4) | MODULE_DEVELOPER_101 中英 |
| `f64850d` feat(data): data-pack validation panel with layers and methodology use (S-D2) | 11.2 |
| `b4f8443` feat(data): mapping editor declares a timestamp column; EUR column hint (S-D4, S-D5) | 11.6 |
| `db27794` fix(ui): readiness rows escape the older preflight-card section rules (S-D1) | 截图发现的样式问题 |
| （本提交）docs(p0) | 本报告、偏差 F-FX3-1…16、`fx3-*` 截图 |

## 2 做了什么

### 11.1 Readiness 卡片（S-D1）
- `app/features/runs/readinessGroups.ts`（纯逻辑）+ `ReadinessIssues.tsx` + `readiness-issues.css`，替换 `RunWorkspace` 中的 `slice(0, 6)`。
- 六组按优先级：Errors（红，始终展开、无切换）、Data plausibility（默认展开）、Chronology、Other data warnings、Adapter: unit not declared、Environment and setup（默认折叠，按钮 `Show {n}`）。组头为 `{组名} · {n}` 的 StatusPill。
- 组内按 code + 去掉对象前缀的正文合并，注明 `×n`，悬停（`title`）列出全部对象。
- 后端只读补充：`preflight.data_eligibility_issues` 给数据层发现加 `layer` 字段（chronology / plausibility）；旧报告按 code 回退判断。
- 截图时发现旧的 `.preflight-card section …` 规则（11px 粗体、10px small、teal 左边框）会套到新分组上，改用 `div` / `span` 并提高选择器特异性（单独一个提交）。

### 11.2 数据包校验面板（S-D2）
- `app/features/data/dataPackValidation.ts`、`DataPackValidationPanel.tsx`、`data-pack-validation.css`；`page.tsx` 在 Data 页的输入上下文条下方显示当前数据包的面板。
- 两行：`Validation`（Structural / Chronology / Plausibility）与 `Methodology use`（Corrected / Doctoral reproduction），`Show details ▾` 展开逐层发现（code、对象、一句话）。
- 数据：`GET /api/data-packs/<id>/validation?extensions=…`；加载完成前用列表的 `plausibility_status` 缓存；都没有时 muted `Not evaluated`。
- 原 `required inputs ready` 改为 `inputs present · validation {最差状态}`。

### 11.3 论文复现口径扣发说明（R-D1）
- 后端读模型 `result_advisories.raw_invariant_failures`：由已有证据（gate 状态、`storage_invariants.checks` 计数、`declared_deviations.matched`）列出失败的原始不变量：gate、check、名称、行数/时段数、命中的声明偏差及其一句话（目录 description 第一句）。`present_scientific_status` 写入 `raw_invariant_failures`，列表行保留最多 10 条。
- `runValidation.ts`：withheld Callout 正文改为规格句式（`Annual results withheld: raw invariant "Storage single direction" failed (10 rows). Matches declared deviation DEV-STO-01: …`）；新增 doctoral 专用的 `Raw invariants` 状态条字段（teal `● Passed` / 琥珀 `● {k} failed`，悬停列出名称）；`Energy balance` 字段不变，`Conformant` 保持 teal 和“账闭合 ≠ 物理验证”的悬停说明。
- scratch 实例真实 doctoral VALUE 101 一日 Run 复现了四类用户测试的情形：能量平衡 `reproduction_conformant`，储能单向性 10 行失败，命中 DEV-STO-01；界面显示与上述一致。

### 11.4 隔离和停用后的出路（M-D3、M-D4、F-D3）
- M-D3：`preflightIdentity.ts` 允许 `accepted=false` 且有 errors、缺 `project_revision_sha256` 的报告匹配同一 Study / 数据包 / 范围（已通过的报告仍须 revision 一致）；Readiness 显示 `GF_PREFLIGHT_MODULE_QUARANTINED` 及修复指引；有 errors 时 Run 按钮禁用，旁边写明原因。模块生命周期操作后清空已存的预检报告。
- M-D4 / F-D3：`app/features/modules/disabledEntries.ts` + `DisabledEntriesPanel.tsx`；Modules 页在模块列表下方常驻 `Disabled and quarantined` 区（停用的模块、各扩展当前版本中停用的、隔离的条目），每项 `Enable`、`Rescan`、`Remove`（Remove 有确认对话框）；页头新增全局 `Rescan modules`。
- Enable：后端在启用模块或扩展前先 `clear_negative_caches()`，失败时返回本次扫描的错误；前端把错误留在该行并附 Rescan，Rescan 后清空。
- Remove：新端点 `POST /api/{modules,extensions}/<id>/remove`（`gridform_core.module_recovery.remove_installation`），把安装目录与清单移到 `modules/disabled-manifests/removed/…`，不删除；已启用且正常的条目、被 Study / 活动 Run / 扩展保留运行记录引用的条目拒绝。

### 11.6 映射编辑器防错（S-D4、S-D5）
- 后端：映射目录对半小时/小时序列角色声明 `timestamp_supported` 与 `time_zones`；预览请求可带 `timestamp: {column, time_zone}`；`data_validation_layers.timestamp_row_problems` 逐行检查（不可读、重复、早于上一行、缺口、步长不规则；Europe/London 按当地钟点、秋季重复小时按行序区分），有问题即 `valid=false`、不能提交。提交后 binding 记录 `timestamp_column`、`timestamp_time_zone`、`timestamp_uri`（保留的源文件）、`timestamp_check`；数据包时间轴层从该源文件复查（不改 binding 的 `interval_minutes`，不改读数路径）。
- 前端：`Timestamp column (optional)` 字段组（`Timestamp column`、`Time zone` 两个下拉框），时间戳声明计入审阅身份（修改即作废旧审阅）；审阅报告逐行列出问题。
- S-D5：所选来源列名含 `eur` 或 `€` 且 Currency 为 GBP 时，行内琥珀色提示 `Column name suggests EUR — confirm the currency.`，不阻断。

### 11.7 原地修改模块源码（M-D2）
- `module_installation.installed_source_changes`：对 Study 选中的已启用外部模块，按字节比较安装记录的 `source_sha256` 与当前源码（不导入代码）。
- 预检琥珀色 warning `GF_PREFLIGHT_MODULE_SOURCE_CHANGED`，消息为规格原句（`Module {id} source changed since install ({old8}… → {new8}…). Results will record the new source hash.`）；Readiness 卡片在分组上方另显示 caution Callout。比较页沿用已有的“方法已改变”标记（未改）。
- MODULE_DEVELOPER_101 中英原地修改（A16-4 允许并记录）：第 2 节不再写“拒绝静默源码更新”，改为“接受并记录”；第 12 节补充 Enable 从新扫描开始、全局 Rescan、停用与隔离区、Remove 的去向与拒绝条件，以及修好后的两条路径。

## 3 测试

新增或修改的测试：

| 测试 | 内容 |
|---|---|
| `tests/frontend/unit/readiness-groups.test.mjs`（5） | 分组顺序、计数不丢、默认展开规则、×n 与对象、按 layer / code 归组、对象前缀拆分 |
| `tests/frontend/render/readiness-issues.test.mjs`（4） | 14 条问题时最后一条可见；errors 无切换；source-changed Callout |
| `tests/frontend/render/preflight-blocked-run.test.mjs`（2） | 缺 revision 的阻断报告显示错误、Run 禁用并注明原因；通过时 Run 可用 |
| `tests/preflight-identity.test.mjs`（+1） | 阻断报告匹配规则、按钮旁文案 |
| `tests/test_module_source_changed.py`（4） | 未改无提示；改后报两个哈希；预检琥珀色 warning 原句且仍 accepted |
| `tests/test_data_validation_layers.py`（+1） | 数据层预检问题带 `layer` |
| `tests/test_raw_invariant_failures.py`（5） | DEV-STO-01 的名称、行数、偏差一句话；未解释的失败；时段计数；列表行截断 |
| `tests/frontend/render/run-context-bar.test.mjs`（改 1、+3） | 规格句式、Raw invariants 字段（只在 doctoral）、Conformant 保持 teal |
| `tests/test_module_disabled_exits_api.py`（8） | Enable 报新错误、修好后 Enable 成功且先清缓存（模块、扩展）；Remove 停用模块 / 隔离模块 / 停用扩展；拒绝已启用正常模块、被 Study 引用的模块；未知条目 404 |
| `tests/frontend/unit/disabled-entries.test.mjs`（4）、`render/disabled-entries.test.mjs`（3） | 停用与隔离行、扩展当前版本、三按钮、Enable 错误行 |
| `tests/frontend/unit/data-pack-validation.test.mjs`（4）、`render/data-pack-validation.test.mjs`（2） | 三层配色、阻断口径为红、最差状态、口径可用性、缓存回退、Not evaluated |
| `tests/test_data_mapping.py`（+4） | 时间戳声明、逐行问题阻断提交、声明校验、London 秋季换时 |
| `tests/frontend/csv-mapping-editor.test.mjs`（+1、改 1） | 浏览器 harness：时间戳下拉框与请求、逐行表；EUR 提示出现与消失 |
| `tests/frontend/unit/csv-mapping-fx.test.mjs`（+2） | `columnSuggestsEur`、`timestampRequest` |
| `tests/frontend/unit/frontend-guards.test.mjs` | 新样式表加入 ≥12px / 只用 token 的扫描 |

运行结果（vpy / vnode；PYTHONPATH=INTEG；TMPDIR、VALUE_DATA_HOME 在 scratch）：

| 命令 | 结果 |
|---|---|
| 每个提交前 `refresh_source_release_manifest.py --index` + `scripts/p0_gate.py quick` | 9 个提交前的最后一次全部 `passed`（无豁免，ratchet `new_failures=[]`）。中途两次未通过已修正：一次因我运行 tsc 生成了 `tsconfig.tsbuildinfo`（删除后重跑）；一次 eslint ratchet 报“基线错误减少”，查明是 React Compiler 遇到 catch 块里的闭包而整组件放弃分析（掩盖了 page.tsx 原有的一条错误），改写为组件级 `recordEntryError` 后基线恢复一致，没有更新基线 |
| 后端相关模块：`test_data_validation_layers`、`test_module_source_changed`、`test_module_quarantine_study`、`test_preflight`、`test_raw_invariant_failures`、`test_result_advisories`、`test_ui_contract_fixtures`、`test_server_presentation`、`test_module_disabled_exits_api`、`test_module_recovery`、`test_module_installation_api`、`test_data_mapping` | 全部 OK（GBP1 资格测试按惯例 skip） |
| 前端 unit / render / harness（改动相关文件） | 全部通过 |
| `tsc --noEmit -p .` | `app/` 无错误 |
| eslint（改动文件） | 0 新错误；`page.tsx` 保留基线中原有的 1 条 set-state-in-effect 和 1 条未用类型 warning |
| 离线 e2e `node e2e/run-tests.mjs --offline` | 37 passed，5 个已登记失败，4 skipped，0 新失败 |
| 截图 | scratch 实例（API 18930、UI 18931）真实数据与真实 doctoral Run，14 个元素 × 1280/375 共 28 张 JPEG（`docs/dev/p0-ui-screens/fx3-*`，约 1.1 MB） |

## 4 采用的决策

- A16-1：S-D1、S-D2、S-D4、S-D5、M-D3、M-D4、F-D3、R-D1 按规格第 11 节实现。
- A16-4：M-D2 接受并记录（预检琥珀色提示、Run 记录新哈希、比较页沿用“方法已改变”、开发者文档改为允许）。
- Q14：withheld 规则不变，只改说明文字与状态条字段。
- P0 安全与身份规则：已通过的预检仍须 revision 一致；Remove 不删除文件。

## 5 偏差

见 `docs/dev/P0_FRONTEND_DEVIATIONS.md`“修复轮 FX3”一节（F-FX3-1…16）。要点：
- 非数据类 warning 归入第 6 组 `Environment and setup`；组内去重键为 code + 正文。
- 时间戳问题阻断映射提交（规格只说“逐行显示”）。
- 数据包“不可用”用琥珀色，原因只用后端的 blocking codes，不写规格示例中的“not a thesis-era pack”（后端没有这一判定）。
- Remove 是“移出扫描目录”，不是永久删除；被引用时拒绝。
- M-D4 的“缓存旧错误”确切路径在测试 harness 中未能重现；修复为 Enable 前清缓存（等同 Rescan），测试断言清缓存且报告新错误。真实 scratch 实例中验证：停用、改为另一个错误后 Enable，界面显示的是新错误。
- 映射编辑器截图来自独立渲染（模拟映射 API），其余来自真实实例。

## 6 遗留

- M-D5（Rescan 不重新检查已导入的模块）未在本单元范围内；截图时需重启 scratch API 才能让改坏的模块进入隔离。
- 隔离模块的预检同时列出 `MODULE_SELECTION`、`PROJECT_REVISION` 两条派生错误（后端已有行为），Errors 组显示 3 条。
- 设计规格 2.3 映射表补入 `reproduction_conformant` 属设计文档，未改（实现已为 teal + 悬停说明）。
- 待设计方复核：F-FX3-1、2、4、5、6、10、12、13、14。

## 7 环境与安全核对

- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（在线 supervisor 的锁文件，早于本轮，以往报告已说明）；`diagnose-value --prefix …/installed` 输出 “Installation integrity and runtime checks passed.”。没有向 INSTALLED 写入或复制（VALUE 101 数据包取自 INTEG 的 `data-packs/`）。
- 没有连接 8766/8800，没有向作者的进程发信号；只按 PID 停止了本单元启动的 API（18930）与 UI（18931）进程（UI 的 PID 第一次记录的是外层 shell，按 `ss` 查到的本人进程 PID 停止）；离线 e2e 自启自停。没有使用 pkill / killall。没有 push。
- scratch：`build/fx3/data`（VALUE_DATA_HOME，含两个 doctoral 一日 Run）、e2e 输出与临时目录已删除，`build/fx3` 只剩辅助脚本和截图源文件。
