# R2-handoff-update：R2 定向复核与交接文档收尾（工作报告）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `71cd564`（R2-2 报告之后）。
- 授权：DECISIONS A23（“本轮之后只做定向复核，不做四角色全量复测”）、A21（交接文档照常交给 methodology 编辑员和网页上传员，文档顶部标明本轮状态）、A17（网站上传等前端翻新）。
- 性质：只改文档，不改代码、参数表和 golden。
- 提交：本报告与四份交接文档在同一个提交中（docs(handoff)：R2 targeted re-check and hand-off banners）。

## 1 完成的步骤

1. 读取 DECISIONS A23、R2-1 与 R2-2 工作报告、`P0_FRONTEND_DEVIATIONS.md` 的 F-R22-1…11、`FOUR_ROLE_TEST_REPORT.md` 第 10 节，以及三份交接文档中涉及 R1 遗留项的段落。
2. **定向复核**（INTEG 只读，Python 经 `vpy`，没有启动服务）：
   - 重跑 `tests.test_r2_numeric_identity`、`tests.test_r2_methodology_record`、`tests.test_r2_advisory_assets`、`tests.test_r2_developer_guide_contracts`：18 个，OK；
   - 重跑 `tests.test_results_summary`、`tests.test_comparison_identity`、`tests.test_module_source_changed`：46 个，OK；
   - 第 10.6 节复现 R3-N1 的原始调用 `_differing_paths(...17000.0 / 17000...)`：现在返回 `[]`；
   - p06 advisory 目录文字：标题 “Down regulation bookkeeping (ramp history, breaks, budgets)”，severity high；
   - `value_thermal_restart_v1.json`：`rule.shutdown_segment` 为 a(H) = c - S(H) / (m H)，sha256 `446b1df5…`；
   - `methodology.UNIVERSAL_ACCOUNTING_CORRECTIONS`：9 项，含 `fx5.voll-17000`；
   - 界面新字符串在 `app/` 中逐条核对（`Delta withheld`、`Deltas withheld`、`Inputs not loaded`、Enable 失败提示、Learn 启动说明、隔离模块的源码变更句）。`correction_ids_in_force` 在 `app/` 中没有使用，所以网站交接文档写明“界面暂不显示”。
3. `FOUR_ROLE_TEST_REPORT.md`：文件头加第 11 节指引；新增第 11 节“R2 定向复核（2026-10-07）”：范围与证据来源、A23 各项状态表（11.1）、10.7 节低项状态表（11.2）、测试与门禁（11.3）、仍未关闭的项（11.4）与结论。
4. `MODEL_CHANGES_BRIEF.md`：阅读提示换成 R2 之后的版本；依据补 A23、R2 报告、第 11 节；新增“R2 更新”条；2.3 节新增“R2 轮中不改数值的修正”一段；3.6 节 A22a 行、golden 行、仍待处理行按 R2 更新；5.3 节 O-3、R3-N2、R3-N7、AF3-1 四条注明已按 A23 处理。
5. `METHODOLOGY_EDITOR_HANDOFF.md`：阅读提示换成 R2 之后的版本（参数表文字与 p06 草稿公式已改；r12 草稿的 “author confirmation pending” 仍要编辑员改；p06 advisory 新措辞；严重度待负责人定）；事实来源补 A23 与 R2 报告；新增“R2 轮更新”条（A22a 文字、R3-N2、R3-N7、R3-N6 / O-3，以及开发者指南的 `value.*` contract ID）；U13 行注明 Run 记录字段；N-9 的 advisory 一句、第 6 节 p06 草稿第 ② 条、第 9 节第 13、14 条按 R2 关闭。
6. `WEBSITE_UPLOADER_HANDOFF.md`：阅读提示换成 R2 之后的版本（网站上传仍等前端翻新，A17）；新增“R2 轮更新”条；依据补第 11 节；2.6 节写明 R3-N1 已修；2.7 节补“R2 只经单元测试、截图和定向复核确认”；2.9 节标题补 R1、R2，A18 advisory 行（R3-N7 按资产筛选）、R1-2 行（p06 advisory 改名）、预检行（隔离时的新句子）更新，新增 “比较页、Modules、Learn 与页头（R2，A23）” 一行；2.9 节末的注意补开发者指南 contract ID；附录 A.2 四类用户一行删去 R3-N1 的边界句（原文要求修复并复核后删去）。
7. 四份文档复制到 worktree 根目录的 `VALUE_four_role_test_report_2026-10-04.md`、`VALUE_model_changes_brief_2026-10-04.md`、`VALUE_handoff_methodology_editor_2026-10-04.md`、`VALUE_handoff_website_uploader_2026-10-04.md`（被 exclude，不入库），已用 `cmp` 核对与仓库副本逐字节相同。

## 2 阅读提示的口径（四份共同）

- 已定稿：C28 经济下调顺序（A19/A22/A22a，参数表文字已在 R2 改为修正式）；按类型电池上限（A20）；参考统计表全部作者已审核（A21、A22）；R2 按 A23 关闭 R1 复测遗留项（R3-N1、AF3-1、R3-N2 措辞、R3-N7、R3-N6 / O-3、R3M-1 与低项），不改模型数值。
- 仍待定：重启成本的价格基年；分区再调度的下调次序是否按 A19 处理；p06 advisory 严重度是否降为 medium（负责人）；F-R22-3、F-R22-6 等界面文案（设计方）；网站上传与发布按 A17 等前端整体翻新。

## 3 测试与门禁

- 定向复核的单元测试见第 1 节第 2 条：64 个，全部通过。
- 提交前：`git add` 后 `scripts/refresh_source_release_manifest.py --index`，然后 `scripts/p0_gate.py quick` 一次（`VALUE_GATE_VENV` 指向 scratch 的 gate venv）。结果写在提交说明中。

## 4 采用的决策与偏差

- 采用：A23（只做定向复核）、A21、A17、Q12/Q13（只改文档）。
- 偏差：
  1. 第 10.8 节第 2 条原建议由对应角色复核 R3-N1 和 R3M-1。按 A23 与作者“不要无止境测试”的要求，本轮没有起角色测试员，改用单元测试（含经本地 API 原样保存两次、按指南 ID 构建并安装示例包）与 R2-2 的实例截图作为证据，第 11 节开头写明。
  2. 第 11 节中 R2-1、R2-2 两个单元自己的测试与 golden 结果引自它们的报告，本单元没有重跑 `capture.py check` 和前端测试。
  3. `VALUE_fix_decisions_2026-10-04.md`（根目录的 DECISIONS 副本）与 `docs/dev/P0_DECISIONS.md` 不同（A23 之后没有同步）。它不在本任务的四份文档之内，本单元没有改，留给负责人。

## 5 安全核对

- INSTALLED：`find <INSTALLED> -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（0 字节，mtime 2026-10-03 05:41:26，安装后首次启动时生成，以往报告都有同样记录）；`diagnose-value --prefix <INSTALLED>` 退出码 0，输出 “Installation integrity and runtime checks passed.”（中间两行 vinext “Static file stream error … Premature close” 来自它自己的探测请求，与以往相同）。
- 没有启动任何服务；测试中的本地 API 由测试夹具在随机端口起停。没有连接 8766/8800，没有向任何进程发信号。
- Python 全部经 `vpy` 调用；没有 push，没有改 remote。
