# R4-4 改函数、加功能角色的中低缺陷（DECISIONS A27）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `9b939fe`。
- 范围：最终构建四角色测试报告（`fab9ec2`）第 4.3 节 M-中1…M-中3、M-低1…M-低5，第 5.3 节 F-中1…F-中4、F-低1…F-低5，以及第 7.1、7.2 节的合并项。
- 依据：DECISIONS A27（作者：“四角色测试的中低缺陷你也可以一起修好”）；Q13（纯代码改动自动追加修订，方法改动须明确确认）；A16-4（已安装代码原地改源：接受并记录）；隔离语义不变。界面按 `P0_FRONTEND_DESIGN_SPEC.md` 的现有组件、token 和文案风格实现，规格未覆盖之处记入 `P0_FRONTEND_DEVIATIONS.md` 的 F-R44-1…9。

## 1 结果一览

| 缺陷 | 结果 | 提交 |
|---|---|---|
| M-中1 storage_cost 调用证据总是“未调用” | 已修：存储成本槽位读市场账本证据 | `0291912`、`422b29d` |
| M-中2 内置模块代码级升级后 readiness 不出结果 | 已修（与 F-中1 同一根因，一次修复） | `f493acc` |
| M-中3 迁移或就地改源后无法派生对照 Study | 已修：迁移刷新模块图；派生先自动追加代码级修订；仅代码身份漂移时按当前模块图派生并记录 | `f1a6ca7` |
| M-低1 correction id 不做存在性校验 | 已修：台账检查与 overlay 封存都要求已登记的 id | `852f6f9` |
| M-低2 先确认方法升级、后报 overlay 未封存；确认后 readiness 为空 | 已修 | `021fb53` |
| M-低3 隔离/停用时一个原因报 3 条错误 | 已修（与 F-低3 一起） | `4952d0d` |
| M-低4 ID 冲突的两行隔离条目无法区分；横幅单数 | 已修（与 F-低2 一起） | `ab81f9f` |
| M-低5 合同 ID 不匹配被报为“could not be loaded” | 已修：`GF_MODULE_CONTRACT_MISMATCH` | `8b82b1e`、`d107baa` |
| F-中1 原地改扩展源码后 readiness 不出结果 | 已修（同 M-中2） | `f493acc` |
| F-中2 扩展行为改动被说成“只改了代码身份” | 已修 | `897db23` |
| F-中3 Rescan 不重新导入扩展钩子 | 已修 | `b965fc0` |
| F-中4 加功能草稿不继承选中的基线 | 已修 | `c84e0f9` |
| F-低1 内置命名空间冲突提示“先停用内置扩展” | 已修 | `162f5eb` |
| F-低2 停用区不显示扩展 ID | 已修（同 M-低4） | `ab81f9f` |
| F-低3 扩展出错时的修复建议误导、重复 | 已修（同 M-低3） | `4952d0d` |
| F-低4 含实验性扩展的 Run 没有标记 | 已修 | `2a656b7` |
| F-低5 先确认后做冲突检查；文案说“模块” | 已修（与 F-低1 同一安装路径） | `162f5eb` |

没有未修的缺陷。另有文档提交（本报告、`P0_FRONTEND_DEVIATIONS.md` 的 R4-4 一节、CHANGELOG）。

## 2 逐项说明

### M-中2 / F-中1：readiness 的身份（7.1 合并项）

- 成因：代码级重识别时，预检报告把新计算出的哈希作为 `project_revision_sha256`，前端用它对比已保存修订，于是丢弃报告。
- 修复（后端，选报告建议的第一种）：报告的 `project_revision_sha256` 写所评估的**已保存**修订（declared），计算出的新哈希另列 `calculated_project_revision_sha256`。前端的身份规则不放松：只接受与所选 Study 已保存修订一致的报告。未保存的 Study 仍用计算哈希。
- 测试：`PreflightIdentityTests`（内置 PSM 代码级升级，报告身份为已保存修订、REIDENTIFY 警告、计算哈希另列）；前端单元测试；scratch 实例上扩展原地改源后 readiness 显示 Ready。

### F-中2：扩展原地改源（7.2）

- `extension_bundle.installed_extension_source_changes`：按安装时记录的 `hook_source_identities` 比较钩子源码字节（不导入），与模块的 `installed_source_changes` 同一规则（A16-4：接受并记录）。
- readiness 给出 `GF_PREFLIGHT_EXTENSION_SOURCE_CHANGED` 警告；Modules 页扩展卡片显示 “Source changed since install … Results may change; Runs record the new source hash.”（`/api/workspace` 新增 `extension_source_changes`）。
- 修订分类：模块图差异中，`distribution = installed-source` 的模块或扩展钩子源码哈希变化列为 `source_changes`；分类仍为 `code_identity_upgrade`（自动，A16-4 与 Q13 不变），但 REIDENTIFY 警告改写为“已安装的本地代码被原地修改……结果可能变化，运行开始时追加记录新哈希的修订”，不再写 “no change to methods or results expected”；追加的修订原因为新的 `source-reidentify`，Studies 卡片相应写 “installed local code was edited in place; results may differ”。内置代码（workspace-source）的变化不在此列，仍按 VERSION_LEDGER 分类。

### F-中3：Rescan 导入扩展钩子（7.2）

- Rescan 清除缓存、清理已安装源码并重建目录后，调用 `extension_framework.probe_extension_hooks` 导入每个已注册扩展的钩子；导入失败按原有机制进入运行时隔离（`GF_EXTENSION_HOOK_IMPORT`，health degraded）。响应新增 `reloaded_extensions`、`quarantined_extensions`。手册第 12 节（中英文）的说法现在与实现一致。

### M-中3：迁移或就地改源后的派生

- 迁移修订（自动与确认）写入当前注册表解析的 `module_resolution_graph`（`revision_migration.current_module_graph`），不再沿用旧图；Studies 卡片显示的图哈希也随之正确。
- 派生 API 在来源 Study 有自动（代码级）差异时，先追加该修订（与 Run 启动相同，Q13），再按新修订派生；响应带 `source_migration`。需要确认的方法或数据差异仍被拒绝，提示改为确实可走通的路径：“在 Runs 选中来源 Study，点 Check readiness 审阅并确认，再创建”。
- 来源修订身份已核验（安装代码算出的哈希等于保存的哈希），而保存的模块图只在代码身份上不同（例如 A16-4 的就地改源；无扩展的 Study 中模块图不进入修订哈希）时，派生以当前模块图为准，并在新 Study 的 `derivation.source_module_graph_drift` 和响应 `source_graph_drift` 中记录差异；页面提示“与来源 Study 的新 Run 比较才是单变量对照”。原样保存不刷新已保存的修订记录（修订文件不可变），这一点见偏差 2。

### M-中1：storage_cost 调用证据

- 存储成本模块由 PSM 在内部调用，没有阶段事件。`present_run` 对所选 storage_cost 模块读市场账本索引（`model-output/market/index.json`）：账本记录了储能成本模块（不是 `unknown`/`not_applicable`）时，证据为 `source: market_ledger`、储能资产时段数和年份。PSM 总是用 Run 所选的 storage_cost 模块构造，所以证据归属于该槽位。
- scratch 实例发现：示例模块改了清单 ID 但没改类的 `id`，账本记录的是类 id `example-flat-storage-offer`；第一版按 ID 相等匹配，因此没有显示证据，后续提交 `422b29d` 改为接受任何已记录的模块对象，并在卡片上注明 “its object reports id …”。

### F-中4：加功能草稿

- 扩展编写台的 “Open independent Study draft” 用与 “Edit as new revision” 相同的加载函数复制当前选中的已保存 Study（年份、模块、扩展、确认、市场与求解器设置、参数、运行选项），名称为 `{Study} · extension study`，不处于编辑任何 Study 的状态。没有选中 Study 时保持原行为并说明。没有另做 Studies 卡片上的 “Duplicate Study”（规格未覆盖，按最保守做法只修引导路径）。

### 低等缺陷

- M-低1：`check_version_ledger.py` 要求每个 correction id 已登记——方法学目录（`gridform_core/data/methodology/corrections/`）或 `CHANGELOG.md` 的 “Correction ids” 表；现有台账的 24 个只在 CHANGELOG 登记的 id 均通过。`seal_runtime_overlay.py --correction` 另外接受 VERSION_LEDGER bump 中的 id（手册 12.1 先写台账再封存）和 overlay 已记录的 id。手册 12.1（中英文）已写明。
- M-低2：前端在报告含安装环境错误（scope `environment`）时不弹方法升级确认框；Run 启动在需要确认之前先报 kernel 未封存（409 `GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED`，不写修订）；确认框确认或取消后自动重跑 readiness（取消后不再弹框）。
- M-低3 / F-低3：已报告隔离或停用时，不再追加由它派生的 `GF_PREFLIGHT_MODULE_SELECTION` 和 `GF_PREFLIGHT_PROJECT_REVISION`（`checks.project_revision.blocked_by = local_code`）；扩展钩子隔离只报一次；加载后被改动的钩子源码抛出带代码的 `ExtensionSourceReloadRequired`，readiness 报 `GF_PREFLIGHT_EXTENSION_SOURCE_RELOAD` 并建议 Rescan；隔离的修复建议改为“修复源码并 Rescan，或停用”。
- M-低4 / F-低2：隔离行显示清单文件，同 ID 多份清单时注明；标题与句子按数量和类型；停用区标签含 ID。
- M-低5：安装和启用在导入代码之前检查槽位与合同；不匹配为 `GF_MODULE_CONTRACT_MISMATCH`（信息保留手册引用的句子，再说明怎样改），槽位不支持为 `GF_MODULE_SLOT_UNSUPPORTED`。
- F-低1：命名空间属于内置扩展时提示“给扩展另取命名空间并重建”；本地扩展持有时也给出这一选项。
- F-低4：`present_run` 从 Run 的冻结 Study 快照读出 `selected_extensions`（版本与成熟度优先取快照中的模块图），Run 上下文条显示 `Experimental extension: {id} {version}`。
- F-低5：有 Run 未结束时，先做所有无需写盘的冲突检查（`precheck_module_bundle`、`precheck_extension_bundle`；扩展的检查抽成与安装共用的 `_check_install_conflicts`），再要求确认；确认信息和页面问句区分 modules / extensions。

## 3 改动的文件

- 后端：`gridform_core/preflight.py`、`revision_migration.py`、`project_revision.py`（新修订原因）、`extension_bundle.py`、`extension_framework.py`、`module_installation.py`、`data_validation_layers.py`（顺带关闭文件句柄）、`backend/server.py`、`backend/study_derivation.py`。
- 脚本：`scripts/check_version_ledger.py`、`scripts/seal_runtime_overlay.py`。
- 前端：`app/page.tsx`、`app/features/workspace/preflightIdentity.ts`、`runContext.ts`、`RunContextBar.tsx`、`run-context-validation.css`、`ResearchJourney.tsx`、`app/features/modules/derivationNotes.ts`（新）、`disabledEntries.ts`、`DisabledEntriesPanel.tsx`、`ModuleQuarantinePanel.tsx`、`module-quarantine.mjs`、`module-quarantine.css`、`ModuleAuthorWorkbench.tsx`、`app/features/runs/runHistoryView.ts`、`RunResults.tsx`、`types.ts`、`app/features/studies/studyMigration.ts`、`app/features/shared/workspaceTypes.ts`。
- 文档：`docs/MODULE_DEVELOPER_101.md`、`docs/MODULE_DEVELOPER_101_ZH.md`、`CHANGELOG.md`（API 合同两行和 R4-4 小节）、`docs/dev/P0_FRONTEND_DEVIATIONS.md`（R4-4 一节）、本报告。
- 测试：新增 `tests/test_r4_module_extension_defects.py`（13 个测试类、26 个测试，含 4 个本地 API 测试）、`tests/frontend/unit/r4-module-extension-defects.test.mjs`（10 个）、`tests/frontend/render/r4-module-extension-panels.test.mjs`（2 个）；更新 `tests/test_preflight.py`（停用模块不再附带 SELECTION 错误）、`tests/test_version_ledger.py`（用已登记的 id）。
- golden 与模型数值：没有改动。本单元只改 readiness、修订记录、生命周期、显示和文档，不改调度、成本或任何模型结果；没有新的 correction id。

## 4 测试与结果

- 每个提交前：新测试和相关后端套件（`test_preflight`、`test_project_revision_migration`、`test_study_derivation`、`test_module_installation(_api)`、`test_module_quarantine(_api/_study)`、`test_prompt65_extension_framework`、`test_prompt81_extension_lifecycle`、`test_extension_*`、`test_module_source_changed`、`test_module_authoring`、`test_version_ledger`、`test_runtime_overlay_seal`、`test_server_presentation`、`test_ui_contract_fixtures` 等）均 OK；前端 unit（191）、render（71）测试与 `tsc -p tsconfig.frontend.json` 通过；每个提交用 `refresh_source_release_manifest.py --index` 刷新清单。
- `scripts/p0_gate.py quick` 第一次运行（代码提交完成后）：`backend_ratchet` 报 1 个新失败 `test_r2_developer_guide_contracts…test_pre_value_contract_id_is_refused_with_the_documented_message`——手册逐字引用合同不匹配的信息，M-低5 改了信息。`d107baa` 保留该句为信息开头并在手册中写明错误代码。最终门禁结果见第 7 节。
- scratch 实例（API 18896、UI 18897，`VALUE_DATA_HOME=scratchpad/build/r4ui/r44/data`，vinext 重新构建）：装 VALUE 101 包，装示例储能报价模块（改名 `hx-flat-storage-offer`）和一个带 finalize 钩子的实验性扩展，各建一个 Study 并运行（一日课、两时段）。Playwright headless（chromium 1243）21 项检查全部 PASS：
  - M-中1：Runs 页 storage cost 槽位显示 “Called inside the PSM: the market ledger records its storage offers (48 storage asset-periods); its object reports id example-flat-storage-offer”；
  - F-低4：Runs 和 Inspect 头部显示 `Experimental extension: r44-observer 0.1.0`，无扩展的 Run 没有；
  - F-中4：草稿提示 “opened as a copy of VALUE 101 baseline (revision 1)…”，草稿名 `VALUE 101 baseline · extension study`；
  - F-中2：原地改钩子行为后扩展卡片显示源码变化；
  - F-低3：钩子已加载后被改动，readiness 只报 `GF_PREFLIGHT_EXTENSION_SOURCE_RELOAD` 并建议 Rescan modules，没有 SELECTION/PROJECT_REVISION；
  - F-中3：Rescan 提示 “modules and extension hooks were imported again”；
  - F-中1 / F-中2：Rescan 后 readiness 显示 Ready，REIDENTIFY 写 “The source code of installed local code changed in place … results may change”，并有扩展源码变化警告；重新运行后 Study 追加 revision 2，原因 `source-reidentify`，Studies 卡片写 “installed local code was edited in place; results may differ”；
  - F-中3 / M-低4：钩子改坏并复制一份模块清单后点 Rescan，面板标题 “3 external modules and extensions quarantined”、“VALUE started without them”，两行同 ID 条目分别显示 `modules/hx-flat-storage-offer.json`、`modules/hx-copy.json` 并注明同 ID；停用区列出清单文件；
  - 所有页面无 pageerror 或控制台错误。
  - API 核对：就地修改储能模块源码并 Rescan 后，`POST /api/projects/hx-study/derive`（reproduce）返回 201，带 `source_graph_drift`（storage_cost 的 `source_sha256`）。
  - 截图在 `scratchpad/build/r4ui/r44/shots`。恢复钩子、删掉多余清单后 Rescan 为 ok；两个服务按记录的 PID 停止（API 1289444、1333435，UI 1289525、1333525），端口已释放，Run 的 worker 都已退出；数据目录已删除。
- M-低2 的界面流程没有在 scratch 实例上操作（需要改动工作树中的 runtime kernel），由 API 测试（Run 启动先报未封存、不写修订）和前端单元测试覆盖。

## 5 采用的决定

- A27：中低缺陷全部修复；界面偏差登记为 F-R44-1…9。
- Q13：派生时自动追加的只限分类为 automatic 的代码级修订；方法、数据改动仍须用户在确认框中确认。
- A16-4：已安装模块和扩展的原地改源都“接受并记录”；分类保持代码级（自动），但说明结果可能变化，修订原因单列 `source-reidentify`。
- 隔离语义不变：Rescan 只是在更早的时点导入扩展钩子，隔离、恢复、停用的规则未改。

## 6 偏差

1. **M-中2 选后端修复。** 报告建议的两种做法中选“报告填已保存修订、新哈希另列”，前端身份规则保持“已保存修订必须一致”，不放松。
2. **M-中3 不刷新已保存的修订记录。** 修订文件不可变；原样保存时哈希不变就不写新记录。改为：迁移修订写当前模块图；派生时若身份已核验而模块图只在代码身份上不同，以当前模块图为准并记录差异。派生 API 会为来源 Study 追加自动的代码级修订——这是对来源 Study 的写入（以前派生从不写来源），与 Run 启动的规则相同（Q13），响应和页面提示都说明。
3. **M-中1 证据不按 ID 相等匹配。** 本地模块的类 `id` 可能与清单 ID 不同（示例模板就是这样）；PSM 总是用所选模块构造，所以只要账本记录了储能成本模块就归属到该槽位，并显示对象报告的 id。是否应在安装合规检查中要求两者一致，留待作者决定（见第 8 节）。
4. **M-低1 的“已登记”范围。** 方法学目录只含 39 个 correction；台账中 24 个 id（p08.*、fx5.voll-17000、r32/r33 等）只登记在 CHANGELOG 的 “Correction ids” 表。因此登记范围定为“目录或 CHANGELOG 表”；封存脚本另接受台账 bump 的 id 和 overlay 已有的 id（overlay 中 `p06.native-market-rules`、`p06.realise-period` 两个 id 不在目录也不在 CHANGELOG，为历史记录，未改）。
5. **F-中4 没有新增 “Duplicate Study” 按钮。** 只修引导路径（复制选中 Study），不增加规格未覆盖的新操作。
6. **门禁按代码提交完成后的状态运行**（与 R4-2、R4-3 相同），每个提交前都跑了相关测试、tsc 和清单刷新。

## 7 环境核对

- `scripts/p0_gate.py quick`：第一次（代码提交后）`backend_ratchet` 有 1 个新失败（见第 4 节），`d107baa` 修正；随后在文档提交的暂存状态下重跑：status `passed`，16 步全部通过，没有豁免，158 s；`backend_ratchet` 2,672 个 id，new_failures 0；node 测试、typecheck、eslint ratchet、network_guard、installed_inventory 均通过。
- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（0 字节，属作者实例，测试报告第 8 节已说明）；没有新的 `.pyc`；`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”。
- scratch：`build/r4ui/r44` 只剩脚本、日志和截图（约 0.5 MB），`build/r44gate` 只剩门禁报告；数据目录、bundle 和临时目录已删除。
- 进程：只按记录的 PID 停止了自己启动的 API 和 UI 网关；没有连接 8766/8800 端口，没有使用按模式匹配的 kill。
- Python 全部经 `vpy` 调用；没有 push，没有改 remote。

## 8 留给作者或后续的观察

- 本地模块的清单 ID 与实现类 `id` 可以不同（示例 bundle 的类 id 固定为 `example-flat-storage-offer`），市场账本记录的是类 id。是否在安装合规检查中要求一致，需作者决定；本轮只在显示上注明。
- `RUNTIME_OVERLAY.json` 中 `p06.native-market-rules`、`p06.realise-period` 两个历史 correction id 没有登记在方法学目录或 CHANGELOG 表中。
