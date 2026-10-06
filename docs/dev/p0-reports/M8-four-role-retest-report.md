# M8 工作报告：修复轮四角色复测汇总

- 分支：`fix/review-2026-10-04`（INTEG worktree），起点 `cd2d72c`（A16 修复轮 FX1–FX7 之后）。
- 任务：把修复轮之后的四份角色复测报告合并进 `docs/handoff/FOUR_ROLE_TEST_REPORT.md`，新增第 9 节“修复轮复测（2026-10-06）”；对剩余的高缺陷自行复核。
- 交付：
  - 仓库副本 `docs/handoff/FOUR_ROLE_TEST_REPORT.md`，已提交；
  - worktree 根目录副本 `VALUE_four_role_test_report_2026-10-04.md`，与仓库副本逐字节相同，被 `.git/info/exclude` 忽略，不提交。

## 1 做了什么

1. 第 1–8 节保留首轮记录，不改写；文首加一条指向第 9 节的说明。
2. 新增第 9 节，内容包括：
   - 9.1 各角色复测结论；
   - 9.2–9.5 每个角色的关键证据、首轮缺陷逐条状态、新发现；
   - 9.6 汇总人的独立复核；
   - 9.7 第 5 节共性问题在修复轮之后的状态；
   - 9.8 建议；
   - 9.9 安全核对。
3. 附录 A 增加 `$ROLES2` 路径和 N-2 复现脚本。

**复测结果摘要：**

- 首轮三项高缺陷 F-D1、F-D2、S-D1 都已修复。F-D1 在真实的 two_year（35,040 时段）Run 中确认：状态链通过，年度结果发布。
- A16-1 的 11 项中 9 项已修复；S-D4 大部分修复；M-D1 只修好了账本，界面仍看不到逐条接受量。
- 复测没有报告新的高缺陷。

## 2 复核

剩余高缺陷为零，没有必须复核的项。对三项中等新问题另做了核对，INTEG 只读，Python 经 `vpy` 调用，没有启动服务：

- **N-2，已独立复现：**
  - 脚本 `…/build/roles2/consolidate/repro_n2.py`；
  - 不带偏移、按 30 分钟连续的 17,520 行时间戳，以 Europe/London 解析，`parse_declared_timestamps` 抛出 `pytz.exceptions.AmbiguousTimeError`（pandas 2.3.2）；
  - 根因：`data_validation_layers.py:397-400` 的回退分支只捕获 `(ValueError, TypeError)`，而 pytz 的这个异常不是 `ValueError` 的子类。
- **N-1，代码核对确认：** `profile_eligibility` 不检查口径的数据包白名单；编辑器走的是 `methodology._pack_supported`。两条路径不一致。
- **F2-N1，代码核对确认：** `backend/extension_results.py:16` 的 16 MiB 上限，两年 Run 的 year-results（34.5 MB）必然超限。

## 3 测试与门禁

- 本次提交只改文档，没有新增或修改测试。
- 提交前运行了 `scripts/p0_gate.py quick`：passed，16 个步骤全部通过，没有豁免，用时 142 s。

## 4 采用的决策

- **A16-1：** 用来区分本轮“预期修复”和“范围外仍存在”的缺陷。
- **A16-2、A16-3、A16-4、A16-5：** 分别作为 S-D3、F-D2、M-D2、VoLL 的验收依据。
- **A16-8：** R-D10 由负责人决定，不设门。

## 5 偏差

- 四份复测报告原定写入各自的 `REPORT.md`，但运行环境拒绝子代理写报告文件。第 9 节因此是它们唯一入库的记录，各缺陷的证据都保留在节内。
- 中等新问题本来不在“必须复核”的范围内。考虑到 N-1、N-2 改动很小，又可能影响发布，所以顺带做了核对。

## 6 安全核对

- 没有启动服务，没有向任何进程发信号。
- INTEG 中只改动这两个文档文件，没有 `__pycache__`。
- INSTALLED（提交前执行）：
  - `find … -newer install-receipt.json …` 只列出安装时就有的 `.supervisor.lock`；
  - `diagnose-value --prefix …` 退出码 0，输出 “Installation integrity and runtime checks passed.”。
- scratch：`roles2/consolidate/` 只有复现脚本、一个 17,520 行的 CSV 和诊断输出，不到 1 MB。
