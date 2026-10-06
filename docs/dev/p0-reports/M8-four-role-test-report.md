# M8 工作报告：四角色用户验收报告汇总与高缺陷复核

- 分支：`fix/review-2026-10-04`（INTEG worktree），起点 `a987ca4`。
- 任务：把四份角色验收报告（复现、换数据、改函数、加功能）合并成一份简体中文文档；对其中标为高或严重的缺陷逐项独立复现。复现时 INTEG 只读，所有运行都在 scratch 中完成。
- 交付：
  - 仓库副本 `docs/handoff/FOUR_ROLE_TEST_REPORT.md`，已提交；
  - worktree 根目录副本 `VALUE_four_role_test_report_2026-10-04.md`，被 `.git/info/exclude` 忽略，不提交。

## 1 做了什么

1. 合并四份报告：
   - 每个角色写明结论、测了什么、关键证据和完整的缺陷表；
   - 缺陷编号加角色前缀（R/S/M/F）；
   - 跨角色的重复问题合并为第 5 节的 8 个主题；
   - 需要作者决定的 5 件事放在第 6 节。
2. 复核高缺陷（另含“中-高”的 S-D2），共 4 项。复核时 `PYTHONPATH` 指向 INTEG，Python 一律经 `vpy` 调用；数据包复制到 scratch 后再改；没有启动 HTTP 服务。
   - **F-D1，已独立复现，而且范围比报告的大：**
     - 用 `run_project_application` 跑合成合约包和内置 toy 扩展，smoke 与 two_year_smoke 两种范围；
     - 选了扩展的 Run，`run.state_chain` 都失败（第一年的 `previous_state_is_annual_input`），`scientific_validation_status=failed`，production gate 为 failed；
     - 让 initialize 不返回输出，仍然失败。原因是 orchestrator 总会写入 `extension_state` 键，而 `run_invariants` 拿来比对的是写入前的初始状态哈希；
     - 对照 Run 为 passed；
     - 按代码路径推断：在修正口径下，带扩展的 17520 时段 Run 不发布年度经济结果（`scientific_validation.py:560-564`、`model_runner.py:765-780`）。
   - **F-D2，已独立复现：**
     - golden C3 一日课程加 toy 扩展：只有 `psm.run`，没有 year-results，也没有扩展产物；
     - 但 `module-resolution.json` 的扩展图里有这个扩展；
     - 预检和 `runScope.ts` 都不检查范围与扩展是否相容。
   - **S-D1，已独立复现：**
     - 直接调用 `run_preflight`，数据为 VALUE 101 副本，把法国价格改为 6087、流量改为 500；
     - 共 19 条问题，两条 plausibility 发现排在第 18、19 条；
     - UI 用 `.slice(0, 6)` 截断（`RunWorkspace.tsx:88`）。
   - **S-D2，代码核对确认：**
     - 前端没有任何代码使用 `/validation` 端点或 `plausibility_status`；
     - 设计规格中没有这个视图，属于规格缺口。
3. 顺带核对：R-D2（`RunWorkspace.tsx:97`），代码核对确认；S-D3，代码浏览结果与测试员的观察一致，即 `ahead_market_bidding` 不接收 connections，是否属于设计行为由作者判断。

## 2 测试与门禁

- 复核脚本：`…/build/roles/consolidate/repro_af_d1.py`、`repro_af_d2.py`、`repro_sd_d1.py`。输出见汇总报告附录 A。
- 快速门：本次提交只改文档。提交前运行了 `scripts/p0_gate.py quick`，结果为 passed：16 个步骤全部通过，没有豁免。步骤包括 guard、release_manifest、backend_ratchet、node_tests、http_harness、typecheck_frontend、eslint_ratchet、network_guard、installed_inventory 等。
- 没有新增或修改测试。汇总报告第 4.1 节建议在 `tests/test_prompt65_extension_framework.py` 中补上 run invariants 的断言，留给修复单元去做。

## 3 采用的决策

- **Q14：** doctoral 年度结果是否扣发，依据是原始不变量是否全部通过；复核 F-D1 时据此推断扩展对 doctoral 的影响。
- **P0-4 S7：** 修正口径下 production gate 失败即阻止年度经济结果发布，这是 F-D1 影响判断的依据。
- **Q13：** S-D3、F-D2 如果改为执行方法改动，都需要显式确认，所以列为作者决定事项。

## 4 偏差

1. 没有为复核另起 HTTP 实例，而是直接调用与 API 相同的函数（`run_project_application`、`run_preflight`），因为高缺陷都在后端函数或前端代码中，用不到 UI 会话。
2. F-D1 在修正口径下扣发年度结果的后果，是按代码路径推断的，没有跑 17520 时段的整年 Run。这是为了遵守“不搞无止境测试”。
3. 中、低等级缺陷没有逐项复核，汇总报告中标为“未复核”。

## 5 安全核对

- INTEG：复核后 `git status --short` 为空，没有新的 `__pycache__`。
- 各角色记录的进程都已不存在，18xxx 端口没有监听。没有连接 8766/8800，也没有向任何进程发信号。
- INSTALLED：
  - `find … -newer install-receipt.json …` 只列出安装时就有的 `.supervisor.lock`（0 字节，2026-10-03 05:41:26）；
  - `diagnose-value --prefix …` 退出码为 0，输出 “Installation integrity and runtime checks passed.”。
- scratch：`roles/consolidate/` 约 8 MB。
- 快速门：passed（rc=0，`installed_inventory` 与 `network_guard` 均为 passed）。
