# R5-4 加功能角色缺陷修复（DECISIONS A28）

缺陷来源：R4 最终构建验收“加功能”角色报告（构建 c204aac，`scratchpad/build/r5/add-feature.md`，副本在 `docs/dev/p0-reports/final-role-add-feature.md`），0 高、3 中、6 低。按 A28：中缺陷必须修；纯显示的低缺陷能顺手修就修，否则进待办。本轮没有新增探索性测试。

## 1 结论表

| 缺陷 | 结果 | 提交 / 原因 |
|---|---|---|
| F-中1 原地改源的扩展停用后无法重新启用 | **部分修复，需作者决定** | 9dbe20b：拒绝信息写出改动的文件和两条出路（恢复原文件后 Enable；或改版本号和 Python 包名重建后作为新包安装）。放开 Enable 的哈希核对没有做，见第 2 节 |
| F-中2 草稿默认名与已有 Study 重名时报 “revision conflict” | 已修 | 9dbe20b（后端 409 `GF_STUDY_ID_EXISTS`，提示改名）；eb86bee（第二个草稿自动命名为 `… extension study 2`） |
| F-中3 只有 initialize 状态和 after_psm 产物被记录，其他钩子输出静默丢弃 | 已修（按报告建议二：明确拒绝并写清） | 9dbe20b（运行时拒绝非 after_psm 钩子返回的声明产物；生成的 README、MODULE_DEVELOPER_101 中英文写明记录范围）；eb86bee（编写台说明） |
| F-低1 停用确认框和 readiness 对扩展写 “module” | 已修 | 9dbe20b（readiness 建议按种类：扩展写 “deselect the extension in the Study (saved as a new revision)”）；eb86bee（隔离面板确认框） |
| F-低2 命名空间冲突提示建议先停用被引用的占用者 | 已修 | 9dbe20b：先给总能走通的“另取命名空间并重建”，停用占用者注明“只在没有 Study 或保留 Run 使用它时可行” |
| F-低3 卡片 Disable 禁止、隔离面板 Disable 允许 | 已修（说明） | eb86bee：卡片说明隔离状态下可在 Disabled and quarantined 停用以便修复 Study；两处规则本身不变 |
| F-低4 Data 页草稿状态仍写 “Selected saved Study … new revision” | 已修 | eb86bee：草稿语境显示 “Independent Study draft”；“Input contract for” 下拉框仍列出全部 Study（它本来就是选择器） |
| F-低5 独立草稿刷新后丢失 | 待办 | 草稿持久化需要新的存储与恢复设计，超出 A28 范围；已上传的数据绑定在包里不丢 |
| F-低6 界面中英混排 | 待办 / 非本轮缺陷 | 规格明确不引入 i18n，报告本身记为观察 |
| 观察：同名“VRE curtailment”一处不可用一处有数 | 不处理 | 两个口径不同，手册已说明；报告列为观察，不计缺陷 |
| 观察：被保留 Run 引用的扩展不能停用 | 不处理 | 有意设计（保留复现能力），`GF_EXTENSION_IN_USE` 已列出 Run |

没有发现影响模型运行数值、单位、能量/成本核算或读入数据的问题：本组缺陷都在扩展生命周期、Study 保存和界面文字上。F-中3 的改动只作用于扩展钩子返回值，不改变任何调度或投资计算。

## 2 F-中1 为什么只做了一半

报告的情形：A16-4 对已安装 module 原地改源是“接受并记录”，但扩展的 Enable 要求钩子源码与安装时记录的哈希一致，所以原地改过的扩展一旦停用就无法重新启用。

我先尝试按 A16-4 放开 Enable 的哈希核对（只要求当前源码能导入、声明的钩子可调用，继续记录改动、Run 冻结新哈希），但这一步被本环境的自动权限检查判为“移除安全检查”而拒绝。按规则，我没有用其他方式绕过。另外两份文档本身也有矛盾：

- `docs/frontend/EXTENSION_AUTHORING_PHASE5.md` 写明“重新启用校验原 hook 身份”（这是有意设计）；
- `docs/MODULE_DEVELOPER_101.md` “Same ID after a fix” 一条写“Repair the source in place and Enable or Rescan”，对扩展而言这条和上面的设计冲突。

所以本轮只保留核对，改进拒绝信息，使用户知道怎样恢复：

> Installed hook source no longer matches the source recorded at install (`<package>.hooks`). Enable only restores an extension whose installed hook files are unchanged: restore the original files and press Enable again, or rebuild the edited project with a new version and Python package (scripts/build_extension_bundle.py) and install it as a new bundle.

**需要作者决定：** 扩展是否与 module 一样适用 A16-4（停用后重新启用时接受原地改动并记录）。若决定适用，改动只有 `gridform_core/extension_bundle.py::_set_extension_enabled` 中三行（把哈希比较换成只校验可导入），需由作者在权限设置中放行或亲自确认；若决定不适用，应把 MODULE_DEVELOPER_101 的 “Same ID after a fix” 改成对扩展写明“恢复原文件或以新版本重装”。

## 3 改动

后端（9dbe20b）：
- `gridform_core/extension_framework.py`：新增 `STATE_RECORDING_HOOKS = ("initialize",)`、`ARTIFACT_RECORDING_HOOKS = ("after_psm",)`；`ExtensionRuntime.invoke` 对其他钩子返回带 `artifact_type` 的值抛 `ValueError`，信息写出扩展、钩子、产物类型和“只有 after_psm 的产物被记录”。不带 `artifact_type` 的普通映射仍然接受（不记录）。内置 toy 扩展和编写台生成的扩展都只从 after_psm 返回产物，不受影响。
- `backend/server.py`：`POST /api/projects` 在已有 Study 有修订而请求没有 `base_revision_sha256` 时返回 409 `GF_STUDY_ID_EXISTS`。原来同样返回 409（revision conflict），只是信息和代码变了；带基修订的编辑和过期基修订的冲突照旧。
- `gridform_core/extension_bundle.py`：F-中1 的拒绝信息；F-低2 的命名空间冲突建议。
- `gridform_core/preflight.py`：`_replacement_advice` 按被阻断条目的种类给建议（F-低1）。
- `backend/extension_authoring.py`：生成的 README 增加 “What a Run records” 一节。
- `docs/MODULE_DEVELOPER_101.md`、`_ZH.md`：增加扩展钩子输出记录范围的说明。

前端（eb86bee）：
- `app/features/studies/draftName.ts`：`studyIdFromName`（与后端 `slug` 一致）、`uniqueStudyName`（加 ` 2`、` 3`…，超长名称先截短）。`app/page.tsx` 打开独立草稿时使用。
- `app/page.tsx`：Data 页草稿语境条（F-低4）；扩展卡片引用说明（F-低3）。
- `app/features/modules/module-quarantine.mjs`、`ModuleQuarantinePanel.tsx`：确认框按种类（F-低1）。
- `app/features/extensions/ExtensionAuthorWorkbench.tsx`：记录范围一句话（F-中3）。
- `docs/dev/P0_FRONTEND_DEVIATIONS.md`：F-R54-1…5。

## 4 测试

- 新增 `tests/test_r5_add_feature_defects.py`（6 个，全部通过）：after_psm 产物记录、after_cem 普通映射接受、after_cem 产物被拒绝且信息正确；README 与开发文档写明范围；原地改源后停用再启用被拒绝且信息写出文件和两条出路，恢复原文件后启用成功；readiness 建议按种类；命名空间冲突建议顺序；HTTP：同名新建第二个 Study 得 409 `GF_STUDY_ID_EXISTS`，带基修订的编辑 201，过期基修订仍报 revision conflict。
- 新增 `tests/frontend/unit/r5-add-feature-defects.test.mjs`（6 个，全部通过），`module-quarantine.test.mjs` 原断言不变仍通过。
- 相关套件：`test_extension_source_bundle`、`test_prompt65_extension_framework`、`test_prompt81_extension_lifecycle`、`test_r4_module_extension_defects`、`test_extension_authoring`、`test_project_revision`、`test_module_quarantine`、`test_study_lifecycle_api`、`test_extension_results`、`test_module_source_changed`：105 个全部通过。
- `scripts/p0_gate.py quick`（`VALUE_GATE_VENV=scratchpad/build/gate-venv`）：除 `release_manifest` 与 ratchet 中的 `test_repository_manifest_is_current` 外全部通过（backend_ratchet 2,725 个 id，其余失败都在基线内；typecheck、eslint ratchet、node_tests、network_guard、installed_inventory 通过）。这两项只因源发布清单未刷新；用 `refresh_source_release_manifest.py --index` 刷新后，`--only release_manifest` 通过，`test_refresh_source_release_manifest` 4 个通过。两个提交各自刷新了清单。
- Playwright headless（chromium 1243），scratch 实例 API 18898、UI 网关 18899，`VALUE_DATA_HOME=scratchpad/build/r5ui/r54/data`，vinext 重新构建，全部 PASS、无 pageerror：已有 `VALUE 101 baseline · extension study` 时，再从 Modules 打开独立草稿，名称为 `… extension study 2`；Studies 与 Data 页语境条都写 “Independent Study draft”，Data 页输入语境为 draft；API 同名重复新建返回 409 `GF_STUDY_ID_EXISTS` 和改名提示。

## 5 偏差

1. F-中1 只改信息，没有放开核对（第 2 节）。
2. F-中3 采用报告建议二（明确拒绝并写清），没有记录其他钩子的产物：记录它们需要修改 year-results 格式、流式读取器（`backend/extension_results.py`）和 Inspect，而 finalize 在最后一年写出之后才运行，没有可挂靠的年度结果，属于新功能。代价：finalize 返回声明产物的扩展会在全部年份算完后才报错；手册和 README 已写明，开发者按说明应从 after_psm 产出。
3. 前端措辞与语境条的选择记录为 F-R54-1…5。

## 6 待办（一行一条）

- F-中1：作者决定扩展是否适用 A16-4（第 2 节），并据此统一 MODULE_DEVELOPER_101 与 EXTENSION_AUTHORING_PHASE5。
- F-低5：独立草稿跨刷新保存（需要设计）。
- F-低6：界面语言统一（规格不引入 i18n）。
- F-中3 延伸：若以后需要 after_cem/finalize 产物，需设计年度外产物的记录位置和 Inspect 展示。

## 7 环境与清理

- 只按记录的 PID 停止了自己启动的 API（2661128）和 UI 网关（2661129），端口 18898/18899 已释放；没有连接 8766/8800，没有按模式 kill。
- scratch 数据目录、浏览器配置已删除，`r5ui/r54` 只留脚本、日志和截图（约 0.2 MB）。
- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（作者实例的 0 字节锁，以往报告已说明），没有 `.pyc`；`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”。
- Python 全部经 `vpy` 调用，INTEG 中没有 `__pycache__`；`dist/`（gitignored）已用 vinext 重新构建；没有 push，没有改 remote。
- 注意：仓库中 `gridform_core/extension_bundle.py`、`backend/server.py` 等文件是 CRLF/LF 混排，编辑器整文件改写会改掉全部行尾；本轮所有改动都按字节保留了原行尾。
