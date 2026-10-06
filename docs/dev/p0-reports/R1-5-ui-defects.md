# R1-5-ui-defects：四角色测试剩余缺陷（界面）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `b4449fc`（R1-4 报告之后）。
- 授权：DECISIONS A21（四类用户测试中仍未解决的问题全部修理；medium 及以上必修，low 在改动小的情况下顺带修）。
- 范围：`docs/handoff/FOUR_ROLE_TEST_REPORT.md` 第 3–9 节中仍未修复的界面缺陷，即 R1-4 报告第 2 节标为“归前端单元”或“后端数据已备”的条目。
- 结论：剩余缺陷中没有 medium 及以上的界面问题（F-D4 为中，但复测按原步骤未复现）。本单元修了 26 项 low、low-medium 和信息级界面问题（其中 F-D6、S-D10、O-1、R-D4、S-D9 为部分修复），共 13 个代码提交，另有本报告和偏差记录 1 个文档提交。没有改模型数值、方法或 golden；只有 1 处后端改动，是 `GET /api/workspace` 新增一个只读字段。

## 1 提交

| 提交 | 内容 |
|---|---|
| `8038526` | fix(runs)：Run history 下拉项可区分；不再残留 “No runs yet”；Check for 跟随所选 Run；开始提示跟随 Run 到结束；已结束 Run 的模块证据不写 pending（R-D2、S-D12、M2-N1、R-D12） |
| `4936764` | fix(runs)：启动 Run 和冻结输入核对时说明为什么要等；启动结束后不把用户拉回 Runs（S-D10、O-1、R-D4） |
| `6747eaf` | fix(runs)：readiness 有错误时，物理预览不显示 teal ready；冻结 manifest SHA 加标注（M2-N3、S-D13） |
| `25bb525` | fix(ui)：输入快照每个 Run 只读一次，只读快照记录的文件；一日课程的 Inspect 默认打开 Market（R-D6、S-D11、M-D9 的 404 部分） |
| `12f5b05` | fix(market)：非年度 Run 的 stress 列表不再写 “0% of the year”（R-D3） |
| `828be0d` | fix(network)：只有全国市场的 Run 按铜板处理，只给一个原因，不再写 “network evidence pending”（R-D5） |
| `1a20328` | fix(compare)：变化维度按“标签 + 路径”列出，原始 JSON 折叠（R-D7、S-D9、F-D5） |
| `c09ab06` | fix(run-context)：任何 Run 的 advisory 都能在上下文条中看到，不只限修复前的 Run（R-D11） |
| `dab2231` | fix(studies)：编辑已保存 Study 时标题为 “Edit study”；已保存 Study 的哈希加标注（R-D11、F-D6、N-6） |
| `fa42682` | fix(modules)：已安装模块卡片显示状态和原地改源码；安装后文件框清空（M2-N4、M-D2、M-D9、F-D6） |
| `1a7f370` | fix(data)：映射提交后确认句保留；角色卡显示时间戳声明；引导 Data 页刷新后不失效；页头 pill 改为 base inputs（S-D8、N-6、N-5、F2-N3） |
| `5a6910a` | fix(ui)：375 px 下 Studies、Inspect、Market replay 不再整页横向滚动（R-D8） |
| `bb196c3` | fix(compare)：模块选择变化写成 “id 版本 → id 版本”（R-D7 补充，截图时发现） |
| 本提交 | docs(p0)：本报告、`P0_FRONTEND_DEVIATIONS.md` 新增 F-R15-1…17、`r1-*` 截图 50 张 |

## 2 缺陷逐条状态

| ID | 严重度 | 状态 | 提交 | 测试 / 说明 |
|---|---|---|---|---|
| R-D2 | 低-中 | **已修** | `8038526` | 下拉项格式为 `范围 · 状态 · 创建时间 · ID 后缀`，例如 `One-day market lesson · completed · 2026-10-06 23:17 · fc41b4c7`，悬停显示完整 ID。只有 Study 没有 Run 时才出现 “No runs yet for this Study”；有 Run 但未选中时，占位项为禁用的 `Choose a Run (n)`，结果区写 `{n} Runs for this Study`。启动中写 `Starting the Run…`。POST 阻塞属于后端（见 S-D10 行）。测试：unit `run-history-view`、render `run-history` |
| S-D12 | 低 | **已修** | `8038526` | ① Run 结束后不再显示 “lesson has started”：开始提示跟随该 Run，结束后改为 completed、cancelled 或 failed 加错误码。② 用户没有手动选范围时，`Check for` 跟随所选 Run，所以重新加载后仍是一日范围（实测 `value_101_day`）。③ “No runs yet” 同 R-D2 |
| M2-N1 | 低 | **已修** | `8038526` | 同 S-D12。失败的 Run 在页面顶部提示中写出错误码，并指向 Run history 中的原因 |
| R-D12 | 信息 | **已修** | `8038526` | 已结束的一日课程中，PSM 以外的槽位写 “Not called in this scope”；其他范围没有调用记录时写 “No calls recorded”；“Evidence pending” 只用于进行中的 Run |
| S-D10、O-1 | 低 | **界面部分已修** | `4936764` | 启动中，Run 按钮下说明：先冻结输入和执行环境；新数据目录的第一次 Run 要归档 Python 运行环境，约 3 分钟，之后不到 1 分钟。`snapshotting` 状态行也有一句说明。启动返回时，如果用户已切到别的页面，不再自动切回 Runs。POST 在 `STUDY_LIFECYCLE_LOCK` 内同步归档，属于 P1-11 / F5-08，未改（R1-4 已登记） |
| R-D4 | 低 | **界面部分已修** | `4936764` | 冻结输入核对和创建进行中，面板显示状态行：通常约 20 秒；创建行提醒关闭页面后服务端仍会完成，不要重复创建。请求本身的耗时没有改。测试：harness `frozen-input-recovery` 增加断言 |
| M2-N3 | 低 | **已修** | `6747eaf` | 预检有错误、物理输入 ready 时，徽章改为琥珀色 `inputs ready · Run blocked`。实测：隔离模块的 Study 显示此徽章（截图 `r1-preview-run-blocked-*`）。测试：render `readiness-labels` |
| S-D13 | 低 | **已修** | `6747eaf` | 标签改为 `Frozen data pack manifest SHA-256`，并说明它与 Data 页的源 manifest SHA 为何不同 |
| R-D6、S-D11 | 低 | **已修** | `25bb525` | 原来每次工作区轮询都重新读 `input-snapshot/*`，现在每个 Run 只读一次，并且等 Run 离开 queued/snapshotting 后才读。`resource-readiness.json` 只在 `snapshot.json` 记录了 `resource_readiness_path` 时才读。实测：从启动一日 Run 到完成，全程 404 为 0 次，`input-snapshot` 请求共 2 次（复测时首次快照期间有 89 次 404）。一日课程的 Inspect 默认打开 Market；Planning 标签说明本范围没有规划记录，不再请求 `planning/*`。测试：render `audit-scope` |
| M-D9（404 和文件框部分） | 低 | **已修** | `25bb525`、`fa42682` | 404 同上；文件框见 F-D6 行。安装提示由 R1-4 修复（`8673fcf`） |
| R-D3 | 低 | **已修** | `12f5b05` | 标题改为 `Stress events — 2025 (non-annual run)`；空列表写 `No stress events in the 48 periods of 2025 this non-annual Run computed.`；记录了 stress 但为 0 时写 `None`。测试：unit `stress-events-view` +2 |
| R-D5 | 低 | **已修** | `828be0d` | 实测：两个口径的一日 Run 都没有 balancing 模块。它们的市场账本有分区表但没有行，capabilities 返回 200。修正口径因此显示了完整的分区工作区，页头写 “network evidence pending”；doctoral 的 annual 返回 409 withheld，界面把两个原因拼成一句。现在这类 Run 按铜板处理，只写一个原因，并给出 `Open Market replay →`，不再请求 annual。测试：unit `network-copperplate`；e2e 新增一例（offline 子集下限 22 → 23） |
| R-D7 | 低 | **已修** | `1a20328`、`bb196c3` | 例如修正对 doctoral：`definition.carbon`、`module · storage cost: dynamic-annual-storage-cost 2.0.0 → value-legacy-storage-tariff 1.0.0`、`model method … differs at methodology.profile_id, modules.storage_cost …`。原始 JSON 折叠在 `Recorded values (JSON)` 中。测试：unit `comparison-review` +3 |
| S-D9 | 低 | **界面部分已修** | `1a20328` | 说明文字由 R1-4（`f596f3d`）修复；转换过的角色仍是 `identity/v1`，R1-4 已说明保留理由 |
| F-D5 | 低 | **已修** | `1a20328` | 同 R-D7 |
| R-D11 | 低 | **已修** | `c09ab06`、`dab2231` | ① doctoral Run 的 11 条 advisory（7 high、3 medium、1 info）现在在上下文条下方的折叠区中列出，每条带严重度。② 编辑时标题为 `Edit study · {名称}`。测试：render `run-context-advisories`、`study-methodology` +2 |
| F-D6 | 低 | **部分已修** | `dab2231`、`fa42682` | 已修：编辑时的标题；扩展安装后清空 `<input>`（实测 `files.length=0`）。**未修：独立 Study 草稿只保存在内存中，整页刷新后丢失。** 要持久化草稿，需要先决定存放位置（URL、浏览器存储或后端草稿），这是设计问题，已记入偏差记录 |
| N-6 | 低 | **已修** | `dab2231`、`1a7f370` | Studies 列表写出数据包，并在哈希上方注明 `Model graph SHA-256 (modules and extensions; not the data pack)`；角色卡显示 `时间戳列 timestamp_utc · UTC · 已核对 17520 行`。春季不存在的时刻报为 “unreadable timestamp”，属于后端文案，未改 |
| M2-N4 | 低 | **已修** | `fa42682` | 卡片新增 State（Enabled / Disabled / Quarantined），停用或隔离时不再提供卡片自己的开关，改为指向 Disabled and quarantined 区。实测三种状态都有截图 |
| M-D2（卡片小问题） | 低 | **已修** | `fa42682` | 后端 `GET /api/workspace` 新增 `module_source_changes`，复用 preflight 的只读字节比较，不导入代码。卡片显示 `Source changed since install (4e783295… → 334020d8…). Runs record the new source hash.`。测试：`test_module_installation_api` 断言原地修改前后的字段 |
| S-D8 | 低 | **已修** | `1a7f370` | 提交后，引导编辑器在该角色下保留确认句。实测 1280 和 375 各提交一次（demand.real、demand.forecast） |
| N-5 | 低 | **已修** | `1a7f370` | 引导数据上下文写入 URL（`journeyRevision`、`journeyPack`），重新加载、前进或后退后都能恢复。实测：直接打开带参数的链接，以及提交后重新加载，都不再出现“引导上下文已失效”。测试：`workspace-location` +2 |
| F2-N3 | 低 | **已修** | `1a7f370` | 页头 pill 改为 `25 of 25 base inputs ready`，悬停说明扩展角色在 Data 页的输入合同中计数 |
| R-D8 | 低 | **已修（需设计方确认）** | `5a6910a` | 实测 375 px：13 个视图和 composer 五步的 scrollWidth 都是 375。修改前 Inspect（smoke Run）为 866，Studies 为 488，Market replay 为 391。做法是新增窄屏样式表，只在 760 px 以下放开旧元素的最小宽度，见偏差 F-R15-16 |
| N-4 | 低-中 | 未修，转 P1 | — | 首次快照期间 clone 被 `STUDY_LIFECYCLE_LOCK` 阻塞，属于后端 P1-11 / F5-08。“正在创建 Study…” 的按钮文案来自引导页的 busy 状态，要等锁的处理定了再改 |
| R-D9、R-D10、O-3 | 信息 | 保留 | — | 后端或负责人决定（R1-4 第 2 节） |
| M-D10、M2-N5 | 观察 | 保留 | — | R1-4 已说明；M2-N5 的说明句由 FX9 加上 |
| F-D4 | 中 | 未复现 | — | 复测按原步骤未复现，本单元未改动 |

## 3 测试

- **新增或修改的前端测试：**
  - unit：`run-history-view`（5）、`stress-events-view`（+2）、`network-copperplate`（2）、`comparison-review`（+3）、`disabled-entries`（+2）、`frontend-guards`（加入 4 个新样式表）；
  - render：`run-history`（4）、`readiness-labels`（2）、`audit-scope`（3）、`run-context-advisories`（3）、`study-methodology`（+2）、`journey-data-editor`（2）；
  - source-contracts：`workspace-location`（+2）；
  - harness：`frozen-input-recovery`（进度断言）；
  - e2e：`network-redispatch` +1。
- **后端测试：** `tests/test_module_installation_api.py`（workspace 的 `module_source_changes`），与 `test_module_source_changed` 一起运行：9 个测试，OK。
- **每个提交前都运行：**
  - `refresh_source_release_manifest.py --index`，再运行 `scripts/p0_gate.py quick`：13 次全部 `status: passed`，16 个步骤都通过，没有豁免，eslint 基线没有变；
  - UI 的 unit、render、source-contracts 三组：最后一次分别为 153、64、66 个测试全部通过；
  - `tsc -p tsconfig.frontend.json`：无错误。
- **harness 组**（`VALUE_E2E_CHROMIUM` 指向 chromium 1243）：4/4 通过。
- **离线 e2e**（`node e2e/run-tests.mjs --offline`）：38 passed、5 个已登记的已知失败、4 skipped、0 个新失败（FX3 时为 37 passed）。
- **实例验证：** scratch 实例（API 18950、UI 18951、`VALUE_DATA_HOME=scratchpad/build/r15/data`），使用真实 VALUE 101 数据：
  - 修正口径和 doctoral 口径的一日 Run 共 6 个，smoke Run 1 个；
  - 用 UI 完成映射提交、模块安装、隔离和停用；
  - 用 Playwright 逐项核对上表的实测结果，截图 50 张，在 `docs/dev/p0-ui-screens/r1-*.jpg`，约 1.4 MB。

## 4 采用的决策与约定

- **A21：** 剩余问题全部处理；medium 及以上已无遗留；low 只做小改动。
- **规格与偏差记录：** 规格第 11 节没有覆盖这些低等级问题。按任务要求，没有自行发挥设计；每一处新文案和新做法都记入 `P0_FRONTEND_DEVIATIONS.md` 的 F-R15-1…17，交设计方复核。新元素遵守第 1.3 节：文字不小于 12px，只用已有 token，有 `:focus-visible`。新样式表都加入了 CSS guard 的扫描。
- **Q12、Q13：** 不改模型和方法，没有 correction id，没有 golden 修订，没有 VERSION_LEDGER 条目。唯一的后端改动是 `/api/workspace` 新增只读字段。
- **CRLF：** `app/page.tsx`、`NetworkRedispatchView.tsx`、`networkRedispatch.ts`、`backend/server.py`、`e2e/network-redispatch.spec.ts` 是 CRLF 和 LF 混用。编辑时先统一按 LF 处理，暂存前用 `keepeol.py` 按 HEAD 逐行恢复原行尾，diff 中只有实际改动的行。

## 5 偏差

1. **R-D8 改了旧元素的窄屏最小宽度。** 这与做法一“不改旧元素样式”（F-P09-13、F-M7-13）不同。A21 要求修理剩余问题，所以只在 760 px 以下放开 `min-width`，不改颜色、字号和桌面布局。需设计方确认（F-R15-16）。
2. **F-D6 的草稿持久化未做。** 要先决定草稿存在哪里（URL、浏览器存储或后端草稿），这是设计问题。
3. **M2-N4：停用或隔离的模块卡片不再提供 Enable/Disable 开关**，改由 Disabled and quarantined 区处理。这样所有出路都集中在一处，Enable 会显示最新一次扫描的错误（规格 11.4）。需设计方确认（F-R15-13）。
4. **R-D5 的归类规则：** 没有 balancing 模块的 Run 按铜板处理。依据是一日 Run 的模块记录，以及 capabilities 中分区行数为 0（F-R15-9）。
5. **截图缺 375 px 的两项：** 页头 pill 在 375 px 下收进菜单，模块安装框只截了 1280 px。另外，离线 e2e 会重建 `dist/`；截图前已重建一次 UI，确认 scratch 网关提供的是本分支的构建。

## 6 未决与交接提示

- **设计方：** 请复核 F-R15-1…17，重点是 F-R15-13（卡片不再提供开关）和 F-R15-16（窄屏样式）。
- **methodology 编辑员和网页上传员：** 本单元没有改方法学正文或 `docs/` 中的用户指南。界面文案有变化：Run history 的标签、stress 列表的非年度措辞、网络页对铜板 Run 的说明、Compare 页的变化维度、模块卡片的 State 字段、Data 页的 base inputs pill。网站上如有这些界面的截图，需要按 `r1-*` 截图更新。交接文档由负责人更新，本单元没有改 `docs/handoff/`。
- **P1：** N-4、S-D10 和 O-1 的后端部分（启动 Run 时持有 `STUDY_LIFECYCLE_LOCK` 完成执行归档）、F-D6 的草稿持久化。

## 7 安全核对

- **INSTALLED：**
  - `find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`。该文件 0 字节，mtime 为 2026-10-03 05:41:26，是安装后首次启动时生成的现网文件，以往报告也有记录；
  - `diagnose-value --prefix …` 退出码为 0，输出 “Installation integrity and runtime checks passed.”。中途那行 vinext “Static file stream error … Premature close” 来自它自己的探测请求；
  - 门禁的 `installed_inventory` 步骤每次都通过。
- **进程：**
  - 本单元只按自己记录的 PID 停止进程：API 81031（重启前）和 624698，UI 网关 625332、640100、789241（每次重建后按 pid 文件停止再启动）；
  - 端口 18950、18951 已释放；
  - 离线 e2e 由它的运行器自启自停（18800、18766）；
  - 没有连接 8766 或 8800，没有使用 pkill、killall 或按模式的 kill，没有 push。
- **其他：**
  - Python 全部通过 `vpy` 包装器调用，INTEG 中没有 `__pycache__`；
  - scratch 实例的 `VALUE_DATA_HOME`（约 590 MB，大部分是执行归档）已删除，`scratchpad/build/r15` 只剩脚本和截图源文件，约 2 MB。
