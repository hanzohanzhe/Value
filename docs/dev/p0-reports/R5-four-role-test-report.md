# R5 工作报告：四角色测试报告按最终状态重写（A25、A26、A28）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `6560189`（代码与 `cbdb69a` 相同）。
- 授权：DECISIONS A25（交付文档按当前最终状态从头重写）、A26（网站方法学描述网上发布的新模型；论文复现口径是兼容口径）、A28（R5 修完缺陷后，四角色报告依据 R4 四角色完整验收与 R5 定向验证一次性重写）。
- 性质：只改文档，不改代码、参数表、golden 或界面。

## 1 完成的步骤

1. 从头重写 `docs/handoff/FOUR_ROLE_TEST_REPORT.md`，只写当前代码的状态：
   - 开头是总览表（各角色结论与现存高/中/低数）、现存缺陷一览和待作者或设计方决定的事项；
   - 各角色写测试内容和可用功能，每条证据标注来源（完整验收 `c204aac`、定向验证 `cbdb69a`、修复单元检查）；
   - 只列 R5 之后仍存在的缺陷，使用新编号（RP/SD/EM/AF）；已验证修复的缺陷不列；
   - 没有逐轮历史、阅读横幅或被推翻的做法，历史只用一句话指向 git 和 `docs/dev/p0-reports/`。
2. 现存缺陷共 0 高、2 中、6 低：
   - EM-中1：有 Run 排队时更改模块或扩展，确认框说排队的 Run 会用新代码启动，实际以 `GF_CONTRACT_001` 失败（定向验证的观察 1）；
   - AF-中1：原地改源的扩展停用后不能直接重新启用（R5-4 只改了信息，规则待作者决定）；
   - RP-低1（`annual_input_state_sha256` 含 Run id）、EM-低1（比较页无参照选择器）、EM-低2（用户指南中 11 处 FORCE）、AF-低1（钩子产物被拒时 Runs 页只显示通用错误码，定向验证的观察 2）、AF-低2（草稿刷新丢失）、AF-低3（中英混排）。
3. 把完整验收中尚未入库的两份角色报告复制为 `docs/dev/p0-reports/final-role-reproduce.md`、`final-role-edit-module.md`（内容与 scratch 中 `build/r5/` 的原文件逐字节相同），使四份角色报告都在仓库中，供本报告附录引用。
4. 复制到 worktree 根目录 `VALUE_four_role_test_report_2026-10-04.md`（被 `.git/info/exclude` 排除，不入库），并用 `cmp` 核对与仓库文件逐字节相同。

## 2 核对依据（只读）

- 依据文件：`scratchpad/build/r5/{reproduce,swap-data,edit-module,add-feature}.md`（`c204aac` 完整验收）、`docs/dev/p0-reports/R5-verify.md`（`cbdb69a` 定向验证）、`R5-1` 至 `R5-4` 工作报告、`docs/dev/P0_DECISIONS.md`（最后一条为 A28）、`docs/dev/P0_FRONTEND_DEVIATIONS.md`（R5 各节的“待确认”）。
- 对照当前代码确认的事项：
  - EM-中1：`backend/server.py:476-494` 的确认框文字；`gridform_core/execution_archive.py:123-150` 的执行身份包含全部活动清单和已安装的模块、扩展；`backend/run_execution.py:45` 的拒绝；`gridform_core/errors.py:90` 起把 `ValueError` 归为 `GF_CONTRACT_001`；
  - AF-中1：`gridform_core/extension_bundle.py:626-648` 的钩子源码核对；`docs/frontend/EXTENSION_AUTHORING_PHASE5.md:16` 与 `docs/MODULE_DEVELOPER_101.md:568-571`（中文版 552 行）的说法不一致；
  - AF-低1：`gridform_core/extension_framework.py` 对非 after_psm 钩子产物抛 `ValueError`；
  - RP-低1：投资提案 ID 带 Run id 前缀（`v2_module_definitions.py:205`、`doctoral_policy.py:514`），哈希在 `gridform_core/v2/orchestrator.py:372` 求得；
  - EM-低2：`grep` 得 `docs/USER_GUIDE.md` 5 行、`USER_GUIDE_ZH.md` 6 行仍把产品称作 FORCE；
  - AF-低2：`app/page.tsx` 没有草稿持久化；AF-低3：研究路径、复现面板、需求单位说明等组件含中文界面文字；
  - 其他引用的标识与文案（`GF_DATA_DEMAND_SCALE` 阈值 `data_pack_validation.py:241`、`GF_MAPPING_HOURLY_DEMAND`、`r5.served-energy-net-of-stress-shortfall`、`GF_PREFLIGHT_ESTIMATE_STORAGE_MODULE`、`STORAGE_STATE_TRANCHE_RECORD_LIMIT = 128`、`GF_STUDY_ID_EXISTS`、`unused_vre_boundary_differs`、模块徽标、方法升级建议句、模板名、碳账 `legacy_storage_scalars_have_no_declared_physical_unit`）都在当前代码中 grep 确认；
  - D5 golden 的 r5 核算值（116.828773 GBP/MWh，扣除 78,810.2 MWh）取自 `tests/golden/doctoral/D5.json`。
- 没有启动服务，没有重跑模型：现存缺陷都已由完整验收或定向验证复现，代码核对足以确认成因。

## 3 采用的决策与偏差

- 采用：A25、A26、A28、A16（第 4 条，用于 AF-中1 的待决事项）。
- 偏差：
  1. EM-中1 来自定向验证报告的“观察”（该报告标为范围外）。它符合本报告“中”的定义（提示与事实相反，功能失败），所以按中等计入，并放在改函数角色下；同一问题也出现在扩展生命周期操作中。
  2. 只为纯显示类修复引用“修复单元检查”作证据；这些项定向验证没有再跑，本报告明确标注。
  3. 两份新入库的角色报告是 `c204aac` 时的原文，保留其中的旧缺陷编号和当时的现象，作为证据，不作修改。

## 4 门禁与安全

- `scripts/refresh_source_release_manifest.py --index` 与 `--check`、`scripts/p0_gate.py quick --changed-since HEAD`：结果写在提交说明中。
- 没有连接 8766/8800，没有向任何进程发信号；项目脚本全部经 `vpy` 调用（另用系统 python3 对 `FOUR_ROLE_TEST_REPORT.md` 做过一次文本替换，不涉及项目代码，不产生字节码）。INSTALLED 的核对结果写在提交后的最终报告中。
