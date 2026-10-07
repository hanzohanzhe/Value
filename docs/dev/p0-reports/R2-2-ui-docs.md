# R2-2-ui-docs：R1 复测遗留的界面与文档项（DECISIONS A23）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `d6046df`（R2-1 报告之后）。
- 授权：DECISIONS A23（R3M-1 本轮修；AF3-1 按指标门控并注明扣发原因；10.7 节“顺带修”的 low 项一并修）；A21（low 项改动小时顺带修）。
- 范围：A23 中属于界面和文档的项：R3M-1（开发者文档的 contract ID）、AF3-1 的界面显示，以及 `docs/handoff/FOUR_ROLE_TEST_REPORT.md` 10.7 节“顺带修”中 R2-1 留给界面的项（R3-N3、R3-N4、R3M-2、R3M-3、R3M-4、R3M-5 的界面部分、R3M-7、AF3-2 的界面部分、L-4 的界面部分、L-6）。
- 结论：上述各项全部处理。没有改模型数值、方法、golden 或后端代码；只改了 `app/`、`docs/`、测试和 e2e 子集的下限。

## 1 提交

| 提交 | 内容 |
|---|---|
| `7d7cd57` | docs(modules)：开发者指南中英文写安装器实际接受的 `value.*` contract ID（R3M-1） |
| `cbfca6a` | fix(compare)：年度差值按指标门控，被扣发的指标写出原因；身份核对块改英文（AF3-1、AF3-2、R3M-7） |
| `930faf0` | fix(modules)：停用、Enable 失败、隔离代码被改后，卡片、停用区和 readiness 的说法一致（R3M-3、R3M-4、R3M-5） |
| `fe87166` | fix(ui)：Inspect 按范围打开默认标签；health degraded 时页头 pill 照常；Learn 说明启动等待；其他低项（R3-N3、R3-N4、R3M-2、R3M-7、L-4、L-6） |
| `431af90` | fix(learn)：启动说明移到课程标题下，靠近被禁用的按钮（L-4，截图时发现位置偏远） |
| 本报告提交 | docs(p0)：本报告、`P0_FRONTEND_DEVIATIONS.md` 新增 F-R22-1…11、`r2-*` 截图 20 张 |

## 2 逐项状态

| ID | 严重度 | 状态 | 提交 | 做法 / 证据 |
|---|---|---|---|---|
| R3M-1 | 低-中 | **已修** | `7d7cd57` | `MODULE_DEVELOPER_101.md` / `_ZH.md`：第 4 节 slot 表全部改为 `gridform_core/v2/module_manifest.py` 中 `SUPPORTED_CONTRACTS` 的 ID（`value.psm/v2`、`value.storage-cost/v1`、`value.expansion-policy/v2`、`value.investment/v2`、`value.planning/v2`、`value.state-transition/v2`），表后加一段：`contract_version` 必须与表一致，安装器拒绝其他写法（含 `gridform.*`），并引用安装器的原文错误；第 7 节不再说 contract ID 沿用旧名；第 8 节 manifest 示例为 `value.investment/v2`。EN 第 5 节的 `force.vre-counterfactual-snapshot/v1` 改为 `value.vre-counterfactual-snapshot/v1`，`gridform.market-ledger/v6` 改为当前写入版本 `value.market-ledger/v8`（`market_ledger.SCHEMA_VERSION`）。`USER_GUIDE_ZH.md:170` 的 `force-module.json` 改为 `value-module.json`（`force-bundle.json` 是构建脚本写入的兼容文件名，说明保留），“FORCE Python 进程”改为 VALUE（EN 同步）。`BRAND_AND_VARIANTS.md` 不再把 slot contract 列为保留的 `gridform.*` ID。**按文档构建并安装验证：** ① 单元测试 `tests/test_r2_developer_guide_contracts.py` 从两份指南的表中读出 storage_cost 的 contract ID，用它构建示例包并安装，conformance passed；`gridform.storage-cost/v1` 的包被拒绝，错误原文与文档引用一致。② scratch 实例中按指南第 9 节的命令（`scripts/build_module_bundle.py`）构建 `r2-guide-flat-offer`，两次构建 ZIP 字节相同（`17058756…e8d6`），经 Modules 页安装成功（截图 `r2-guide-module-installed`）；`gridform.*` 版本经页面安装得到 `GF_MODULE_RESOLUTION: … uses gridform.storage-cost/v1; expected value.storage-cost/v1`（截图 `r2-guide-gridform-refused`） |
| AF3-1 | 低-中 | **已修（界面）** | `cbfca6a` | 读取 R2-1 新增的 `metric_delta_gates`：每个指标按自己的门控显示差值；被扣发的指标在数值下写 `Delta withheld: {reason}`；年份列表上方的总括改为 info-box（`Deltas withheld` + 计数和名称）。原来的红框中文句子删除。没有逐指标字段的旧响应仍按 `metric_deltas_allowed`。证据：用后端 `compare_run_summaries` 生成的 VALUE 101 式响应（两个 two_year Run、无反事实快照），成本和碳显示 `+0 · 0%`，`Vre Curtailment Mwh` 写出扣发原因（截图 `r2-compare-per-metric-deltas`、`r2-compare-withheld-summary`） |
| AF3-2 | 低 | **已修（界面）** | `cbfca6a` | 身份块标签改为 `Model method (modules, extension selection, methodology)` 与 `Parameters and extension settings`，写明扩展的选择属于方法维度；中英混排去掉（后端文字由 R2-1 `c2ed529` 修） |
| R3M-7 | 低 | **部分修** | `cbfca6a`、`fe87166` | 改了英文界面中的中文：比较页身份块、加载提示和错误；Modules 页方法对照 Study 保存后的提示。Read me 的“正在读取使用说明…”只在读取中出现，不再常驻 `role=status`。研究引导页、Read me 对话框等整页中文的界面没有翻译，见偏差 1 |
| R3-N3 | 低 | **已修** | `fe87166` | `onOpenInspect` 不带标签时不再写死 `planning`；侧栏导航、Runs 页链接和网络页的 “Open in Inspect” 都会清除之前请求的标签，Inspect 按范围选默认标签（一日课程为 Market） |
| R3-N4 | 低 | **已修** | `fe87166` | 研究引导创建成功后保持原基线并清空名称；重名时提示（不阻止，见偏差 2）。截图 `r2-journey-duplicate-name` |
| R3M-2 | 低 | **已修** | `fe87166` | 页头 pill 只在工作区读不到时写 `Inputs not loaded`（`shared/headerPill.ts`）。真实实例：模块源码被改坏并 Rescan 后，侧栏为 `● Backend degraded`，pill 仍为 `0 of 25 base inputs ready`（scratch 的研究数据包没有文件），下拉框可用（截图 `r2-pill-degraded-health`） |
| R3M-3 | 低 | **已修** | `930faf0` | 能 Enable 的条目在 Enable 失败后提示“修好后再点 Enable”，不再只说 Rescan（截图 `r2-enable-failure-hint`） |
| R3M-4 | 低 | **已修** | `930faf0` | 卡片引用说明按状态区分（截图 `r2-disabled-card-usage-note`）；`USER_GUIDE.md:434` 与中文版同步写明隔离面板可以停用仍被引用的模块 |
| R3M-5 | 低/观察 | **已修（界面）** | `930faf0` | Readiness 中源码变更 warning 只在 Callout 中出现一次；已隔离模块卡片不再承诺记录新哈希（真实实例截图 `r2-quarantined-card-source-change`）。后端文字由 R2-1 `d1ad608` 修 |
| L-4 | 低 | **界面已修** | `fe87166`、`431af90` | Learn 页启动 Run 期间在课程标题下说明等待原因（截图 `r2-learn-launch-note`、`r2-learn-launch-course`）。POST 在 `STUDY_LIFECYCLE_LOCK` 内同步归档仍属 P1-11 / F5-08 |
| L-6 | 低 | **已修** | `fe87166` | 报告为空时写“尚未运行：先修正上面列出的映射或换算错误……”，不再显示 `null`。没有截图，见第 6 节 |
| R3M-6、L-1、L-2、L-3、L-5、R3-N1、R3-N2、R3-N6、R3-N7 | — | R2-1 已修 | — | 后端项，本单元没有再改 |

## 3 测试

- **新增后端测试：** `tests/test_r2_developer_guide_contracts.py`（5）：两份指南的 slot 表、manifest 示例与 `SUPPORTED_CONTRACTS` 一致；`gridform.*` 只出现在引用的拒绝原文中；不再出现 `force-module.json`、`force.vre-counterfactual-snapshot`、“FORCE Python”；按指南的 ID 构建并安装示例包；`gridform.*` 包按引用的原文被拒绝。结果：5 个全部通过。
- **新增或修改的前端测试：**
  - unit：`comparison-review`（+2）、`disabled-entries`（+3）、`readiness-groups`（+1）、新文件 `r2-ui-low-items`（4，含 `page.tsx` 源码契约：不再有 `tab ?? "planning"`、导航清除请求的标签、pill 用 `baseInputsPill`、方法对照提示为英文）；
  - render：`disabled-entries`（新提示）、`readiness-issues`（+1；原用例 “Environment and setup · 1” 的期望按 R3M-5 改为不重复计数）、新文件 `r2-learn-and-readme`（2）；
  - e2e：`comparison-review.spec.ts` +1（AF3-1 逐指标），原用例改为英文文字；`e2e/offline-subset.json` 中该 spec 的下限 1 → 2。
- **每个提交前：** `refresh_source_release_manifest.py --index` 后运行 `scripts/p0_gate.py quick`（`VALUE_GATE_VENV` 指向 scratch 的 gate venv）：5 个代码/文档提交前共 5 次，全部 `status: passed`、16 步、无豁免；本报告提交前再跑一次，见第 7 节。
- UI 三组（最后一次）：unit 163、render 67、source-contracts 66，全部通过；`tsc -p tsconfig.frontend.json` 无错误；改动文件的 eslint 只有 `Value101Learn.tsx` 原有的 3 个 warning。
- **离线 e2e**（`node e2e/run-tests.mjs --offline`）：39 passed、5 个已登记的已知失败、4 skipped、0 个新失败（R1-5 时为 38 passed；新增的是 AF3-1 用例）。提交 `cbfca6a` 前单独跑过 `comparison-review.spec.ts`：2 passed。
- **实例验证：** scratch 实例 API 18960 / UI 18961，`VALUE_DATA_HOME` 在 scratch（只装模块，没有启动 Run）。截图 20 张（多数 1280 与 375 各一张；模块安装两张、页头 pill 和 Learn 课程整块只截了 1280，pill 在 375 下收进菜单），在 `docs/dev/p0-ui-screens/r2-*.jpg`，约 0.5 MB。

## 4 采用的决策与约定

- **A23：** AF3-1 只扣发依赖弃电证据的指标并注明原因（界面按后端逐指标字段显示）；R3M-1 本轮修；10.7“顺带修”的 low 项一并修。
- **A21：** low 项只做小改动；整页翻译、草稿持久化之类的较大改动没有做。
- **规格：** 规格第 11 节没有覆盖这些项；所有新文案和做法记入 `P0_FRONTEND_DEVIATIONS.md` 的 F-R22-1…11，交设计方复核。新元素遵守第 1.3 节：文字不小于 12px，只用已有 token。扣发说明用 info-box，不用红框（规格第 4 节：红框只用于 invalid）。
- **Q12、Q13：** 不改模型和方法，没有 correction id、golden 修订或 VERSION_LEDGER 条目。
- **CRLF：** `app/page.tsx`、`docs/MODULE_DEVELOPER_101*.md` 是 CRLF 或混用。编辑时按原行尾逐行写回，diff 只有实际改动的行。

## 5 偏差

1. **R3M-7 只改了英文界面中夹杂的中文。** 研究引导页、Read me 对话框（内容是中文 README）、数据映射编辑器、冻结输入恢复面板整页都是中文；测试员列出的“选择基线 Study / 核对新研究”属于研究引导页。逐页翻译不是小改动，也涉及界面语言策略，留给设计方（F-R22-3）。
2. **R3-N4 的重名只提示、不阻止。** 后端允许 Study 重名；是否在界面阻止属于设计决定（F-R22-6）。
3. **AF3-1 的总括与逐指标原因用英文句子**，取自后端 `metric_delta_gates[*].reason`，界面不另行翻译 reason_code。
4. **截图用了两种来源。** 模块安装、隔离和页头 pill 是真实实例；比较页、停用卡片、Enable 失败、研究引导和 Learn 启动等待用 Playwright 拦截 `/api/workspace` 与被测请求（比较响应由后端 `compare_run_summaries` 实际生成，其 `reason_code` 为 `vre_curtailment_artifact_schema_unsupported`，因为输入是合成的归因记录）。没有为截图启动真实 Run：一次 Run 要归档约 590 MB 的执行环境，超过 scratch 限额。
5. **L-4 的说明位置在截图后调整了一次**（从页面上方移到课程标题下，靠近被禁用的按钮），因此多了一个提交。

## 6 未决与交接提示

- **设计方：** 请复核 F-R22-1…11，重点是 F-R22-3（界面语言是否统一）和 F-R22-6（重名是否阻止）。
- **没有截图的项：** R3-N3（需要带 Callout 的真实 Run，由源码契约测试覆盖）、L-6（需要真实换算失败的映射）。
- **methodology 编辑员：** 本单元没有改方法学正文。
- **网页上传员：** 开发者指南（EN/ZH）第 4、7、8 节的 contract ID 已改为 `value.*`；网站若转载了 slot 表或 manifest 示例，需要同步。比较页的身份块和年度差值显示有变化（`r2-compare-*` 截图），模块卡片、停用区和 Learn 页各有一句新文案。
- **P1：** L-4 的后端部分（启动 Run 时持锁归档）；指南第 13 节“只有七个 slot 可替换”与 `SUPPORTED_CONTRACTS` 中另外三个 slot（network_expansion、balancing、weather_spatializer）的关系没有核对，本单元没有改这段文字。
- 交接文档（`docs/handoff/`）本单元没有改，由 R2 收尾单元统一更新。

## 7 安全核对与收尾测试

- **INSTALLED：**
  - `find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（0 字节，mtime 2026-10-03 05:41:26，安装后首次启动时生成的现网文件，以往报告都有同样记录）；
  - `diagnose-value --prefix <INSTALLED>` 退出码 0，输出 “Installation integrity and runtime checks passed.”（中间那行 vinext “Static file stream error … Premature close” 来自它自己的探测请求，与以往相同）；
  - 门禁的 `installed_inventory` 步骤每次都通过。
- **进程：** 只按自己记录的 PID 停止进程：scratch API 1885006、UI 网关 1885144（重建后按 pid 文件停止）和 1895047。端口 18960、18961 已释放。离线 e2e 由它的运行器自启自停（18800）。没有连接 8766 或 8800，没有使用 pkill、killall 或按模式的 kill。
- **其他：** Python 全部经 `vpy` 调用，INTEG 中没有 `__pycache__`；scratch 实例的 `VALUE_DATA_HOME` 已删除，`scratchpad/build/r22` 约 1 MB（脚本、日志、截图源文件）。没有 push，没有改 remote。
- **本报告提交前：** `refresh_source_release_manifest.py --index` 后 `scripts/p0_gate.py quick` 一次，结果写在提交说明中。
