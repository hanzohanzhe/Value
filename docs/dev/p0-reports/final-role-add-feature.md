# 最终构建验收：加功能（add new function to VALUE）角色

- 被测构建：`fix/review-2026-10-04` @ `c204aac`（`git archive` 到 scratch，`vinext build` 重新构建）。
- 环境：API 18886、UI 网关 18887，`VALUE_DATA_HOME=scratchpad/build/final_roles/add-feature/state`（新建空目录），VALUE 101 包按手册的源码路径安装（`scripts/install_synthetic_pack.py --value-101-only`）。Playwright headless（chromium 1243）驱动界面，必要处用 API 和磁盘记录核对。
- 以新用户身份从头操作，不参考以前的报告结论。

## 结论：通过但有问题

加功能主路径（编写 → 校验 → 下载 → 安装 → 独立草稿启用 → 复制数据包并绑定扩展输入 → 确认实验性 → 保存 → readiness → 两时段与两整年运行 → Inspect 查看扩展结果 → 原地改源 → Rescan → 重跑与对比 → 命名空间冲突 → 停用/重新启用）全部能走通，扩展结果与运行记录逐项对得上。发现 0 个高、3 个中、6 个低缺陷。

## 1 能用的部分与证据

1. **编写与校验**：Modules → add new function，填 ID `fin-af-observer`、命名空间 `local.fin-af`、研究问题；校验前下载按钮不可用，校验后显示完整清单（数据角色、钩子 initialize/after_psm、结果模式、包身份 SHA-256），下载 `fin-af-observer-0.1.0.zip`（含 README、示例 CSV、schema、源码）。高级清单编辑：加 `after_investment` 钩子、加未支持的摘要字段、只改清单名称，三种都被拒绝且说明原因，下载保持不可用。
2. **安装**：不勾选信任时安装按钮不可用；安装后卡片显示 `local bundle · enabled`、实验性、包身份。
3. **独立草稿**：“Open independent Study draft” 复制已选 VALUE 101 baseline（名称 `VALUE 101 baseline · extension study`），Advanced → Optional domains 勾选扩展；Data 页出现扩展角色 `local.fin-af.audit-input`；“Copy data pack for this draft” 生成独立包并自动选中；上传示例 CSV 后 26/26、校验通过（有警告）；Review 未勾选实验性确认时报 `GF_EXTENSION_ACK_REQUIRED`，勾选后保存，Study 记录 `selected_extensions` 和 `extension:fin-af-observer@0.1.0` 确认。
4. **运行**：两时段 readiness Ready → 运行完成（execution/contract passed）；两整年（35,040 时段）约 3 分钟完成，scientific validation passed，能量平衡 Passed，无 stress event。Run 头部显示 `Experimental extension: fin-af-observer 0.1.0`。
5. **扩展结果**：Inspect → Artifacts & provenance 的 “Extension artifact summaries” 显示冻结扩展、年份筛选、冻结模块图/扩展图哈希；两整年 Run 有 2025、2026 两条 `local.fin-af.year-summary`。核对：每年的 `source_inputs_sha256` 与 `orchestrator-events.jsonl` 中该年 `psm.run` 的 `input_state_sha256` 一致（2025 `bdc988c9…`，2026 `04ab4350…`）；两时段 Run 同样一致（`4c16287d…`）。
6. **原地改源**：改 `installed-extensions/.../hooks.py`（initialize 状态加字段）后，扩展卡片显示 “Source changed since install (… 8712394f… → 4887cb03…)”；未 Rescan 时 readiness 只报一条 `GF_PREFLIGHT_EXTENSION_SOURCE_RELOAD` 并建议 Rescan；Rescan 返回 `reloaded_extensions`、提示 “modules and extension hooks were imported again”；之后 readiness Ready，带 `GF_PREFLIGHT_EXTENSION_SOURCE_CHANGED` 与 `GF_PREFLIGHT_REVISION_REIDENTIFY`（写明结果可能变化）。重跑后 Study 追加修订 2（原因 `source-reidentify`），Studies 卡片写 “installed local code was edited in place; results may differ”；新 Run 的 year-results 含新字段（`observer_revision: 2`），钩子源码哈希为新值。对比两次两整年 Run：只有 `extensions.hook_source_identities` 一个维度不同，描述正确。
7. **改坏与隔离**：在钩子中加语法错误后 Rescan → health `degraded`，隔离面板写明 `GF_EXTENSION_HOOK_IMPORT`、行号、清单文件；readiness 只报一条 `GF_PREFLIGHT_MODULE_QUARANTINED`。
8. **命名空间冲突**：编写台对已占用命名空间（本地 `local.fin-af`、内置 `value.toy-audit`）在校验阶段拒绝；用 `scripts/build_extension_bundle.py` 重建的冲突包在安装时 409 `GF_EXTENSION_NAMESPACE_COLLISION`，内置命名空间的提示为“给扩展另取命名空间并重建”；Python 包名重复时 409 `GF_EXTENSION_SOURCE_COLLISION`。
9. **停用/重新启用**：未被引用的扩展可停用（停用区显示名称与 ID）；停用后另一个扩展可以占用它的命名空间，此时重新启用被 409 拒绝且说明原因；停用占用者后重新启用成功并提示重新检查 readiness。被 Study 和 Run 引用的扩展：卡片 Disable 不可用并说明原因，API 返回 409 `GF_EXTENSION_IN_USE`（列出 Study 和 Run）；Remove 未停用的扩展返回 `GF_EXTENSION_REMOVE_ENABLED`；停用的扩展 Remove 有确认框，文件移到 `disabled-manifests/removed/`。
10. **本地开发的扩展**：按 README 解压、改 ID/命名空间/包名、增加 after_cem 和 finalize 钩子并用构建脚本重建，安装、建 Study、两整年运行均成功。
11. 所有页面没有 pageerror；控制台错误只有预期的 409 响应。

## 2 当前缺陷

### 中

**F-中1 原地改过源码的扩展一旦停用就无法重新启用。**
A16-4 规定已安装代码原地改源“接受并记录”，启用状态下确实如此；但 Enable 要求钩子源码与安装时记录的哈希逐字节一致（`gridform_core/extension_bundle.py` 约 624 行），否则 400 `GF_EXTENSION_SOURCE_CHANGED: Installed hook source no longer matches its retained identity`。界面同时提示“Fix the cause, then press Enable again”，但没有说明怎样修。
- 复现 A（往返）：安装扩展 → 原地改 `hooks.py`（合法改动）→ Rescan（正常）→ Disable → Enable → 400。
- 复现 B（隔离恢复）：被 Study 引用的扩展原地改源后又改坏 → Rescan 隔离 → 隔离面板的 Disable 成功（见 F-低3）→ 修好源码（回到已运行过的合法版本）→ Enable → 400；Study 的 readiness 停在 `GF_PREFLIGHT_MODULE_DISABLED`。
- 唯一出路是把源码恢复为安装时的字节，启用后再改回。用户的改动若无备份就无法恢复，Study 只能改选扩展。

**F-中2 独立草稿默认名称与已有 Study 重名时，保存报“revision conflict”，提示误导。**
从同一基线第二次打开加功能草稿，默认名仍是 `VALUE 101 baseline · extension study`，生成的 ID 与已有 Study 相同；服务端把它当成对已有 Study 的修改（没有 expected base revision），返回 409 “Project revision conflict: reload the latest project before saving changes”，页面照此显示。按提示重新加载会丢掉整个草稿（草稿不保留，见 F-低5），问题本身是重名。改名后保存成功。
- 复现：已有 `VALUE 101 baseline · extension study` 时，在 Modules 加功能区再点 “Open independent Study draft”，选扩展、选数据包、确认、保存。
- 建议：草稿名去重（加序号），或服务端对没有基修订的新建请求报“ID 已存在，请改名”。

**F-中3 只有 initialize 的状态和 after_psm 的产物会被记录；其他钩子的输出静默丢弃。**
安装器接受声明 `preflight/before_psm/before_cem/after_cem/transition/finalize` 钩子的扩展，并对带 `artifact_type` 的返回值做模式校验；但编排器（`gridform_core/v2/orchestrator.py` 中 `invoke("after_cem", …)`、`invoke("finalize", …)` 等）不保存返回值。本地开发者给 after_cem/finalize 写的产物在 year-results 和 Inspect 中都看不到，也没有任何警告；手册没有说明哪些钩子的输出会被记录。
- 复现：在生成项目中增加 after_cem 和 finalize（返回同一 artifact 类型），重建、安装、建 Study、两整年运行；Inspect 只有 2 条（after_psm，每年 1 条），year-results 中没有 `decision_sha256` 或 `results_sha256` 产物。
- 建议：要么记录这些产物，要么在安装校验时或手册中写明只有 after_psm 产物会被记录。

### 低

- **F-低1 停用确认框和 readiness 对扩展仍写 “module”。** 隔离面板 Disable 的确认框写 “Studies that use it will need another module before they can run.”；Study 选中已停用扩展时 readiness 建议 “Enable it, or select another module in the Study”。对扩展应说“取消选择该扩展（另存修订）”。
- **F-低2 命名空间冲突提示建议“先停用占用者”，但占用者被 Study 引用时停用被禁止。** 安装 `local.fin-af` 冲突包时提示 “disable fin-af-observer before installing…”，而该扩展卡片写 “disabling is blocked”。提示应按占用者能否停用给出可走通的选项。
- **F-低3 同一个被引用的扩展，卡片 Disable 被禁止，隔离面板 Disable 却能执行。** 隔离面板为了恢复而允许停用是合理的，但两处规则不同，卡片也没有说明；与 F-中1 结合时，Study 会卡在 “disabled” 状态。
- **F-低4 Data 页在独立草稿状态下仍显示 “Selected saved Study … Editing is saved as a new revision.”**，“Input contract for” 下同时列出草稿和来源 Study 两行，容易让人以为在修改来源 Study。
- **F-低5 独立草稿在浏览器刷新后丢失。** 必须在一个页面会话内完成“草稿 → Data 复制包和绑定 → 返回 Review → 保存”；刷新后回到空白新建表单，没有提示。已上传的数据绑定保存在包中，不会丢。
- **F-低6 界面中英混排。** Home 的四条路径卡片、Studies/Runs 页的“复现 Study”和“历史复现条件检查”面板是中文，其余是英文（规格明确不引入 i18n，记录为观察）。

### 观察（不计缺陷）

- VALUE 101 铜板 Run 的 Runs 页写 “Final VRE curtailment: Unavailable — module does not provide counterfactual snapshot”，VRE 页同时显示账本口径 VRE curtailment 4 GWh（2025）。两者口径不同，手册有说明，但同名指标一处“不可用”、一处有数，第一次看容易困惑。
- 扩展被任何保留的 Run 引用后就不能停用（`GF_EXTENSION_IN_USE` 也列出 Run），只能先移走 Run。若这是有意的（保留复现能力），建议在卡片上写明“含 Run 历史”。

## 3 环境核对

- 服务：只按记录的 PID 停止了自己启动的 API（1507759）和 UI 网关（1507761），端口 18886/18887 已释放；所有 Run 的 worker 已结束。没有连接 8766/8800，没有使用按模式匹配的 kill。
- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（0 字节，属于作者正在运行的实例，以前的报告已说明），没有 `.pyc`；`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”。
- Python 全部通过 `vpy` 调用。scratch：已删除 state（约 850 MB）、src 归档、浏览器 profile 和解压目录；保留脚本、日志、作者 ZIP 和 10 张截图（`scratchpad/build/final_roles/add-feature/shots`），合计约 5 MB。
- 本角色只做测试，没有改动代码。
