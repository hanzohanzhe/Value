# A25 工作报告：网站上传员交接文档按最终状态重写

- 分支：`fix/review-2026-10-04`（INTEG），起点 `fab9ec2`。
- 授权：DECISIONS A25（简报、四角色报告和两份交接文档按当前最终状态从头重写，不写已经发现有错并改过的内容、被推翻的旧做法或逐轮历史）；作者本轮原话“这一轮记得四个新文件都重新生成，不要把之前已经发现有错并且改过的东西给我”。
- 性质：只改文档，不改代码、参数表、golden 或 `website/`。

## 1 完成的步骤

1. 从头重写 `docs/handoff/WEBSITE_UPLOADER_HANDOFF.md`。去掉了阅读提示横幅、各轮更新条、已修复问题的叙述和被推翻的做法。被推翻的做法包括：先降火电的旧顺序、电池共用池、旧公式 a = c − S/H，以及已改名的 advisory 标题。全文只写 HEAD `fab9ec2` 的状态，按 DECISIONS 中后出的条目（A19/A22/A22a/A24 优先于 P3-03 和 A22，A20 优先于 P5-02）只写最终规则。
2. 并入 R3 各单元的最终状态：
   - 共享光伏曲线多出的一小时，以及 R029 public2（A24-1）；
   - 网络模型的经济下调顺序（A24-3）；
   - 重启成本换算到 2025 年英镑，以及生物质披露（A24-4、A24-2）；
   - Run 异步启动（A24-5）；
   - A15 调查结论（563 个时段，原因是内核在下调时重复削减）。
3. 核对出的现存问题与新增事项：
   - `publication.py` 的 `data_pages()` 无论 `publication_ready` 取何值都会执行，所以 data 页始终由 `publication.py` 生成，“Clean source snapshot” 注释只追加到 about 和 docs 两页；
   - `CHANGELOG.md` 的 Known issues 和 `docs/VALIDATION_AND_CLAIMS.md` 仍写 471 个时段（包络检查的计数），与 A15 调查结论不一致，列为公开文档待补项；
   - Run 异步启动和界面字符串还没有写进 `CHANGELOG.md` 和用户指南，同样列为待补项。
4. 复制到 worktree 根目录的 `VALUE_handoff_website_uploader_2026-10-04.md`（被 exclude，不入库），并用 `cmp` 核对与仓库副本逐字节相同。

## 2 核对依据（只读）

- **代码与数据：**
  - `website/` 各文件的行号逐一核对；`git diff 35aadb3 -- website/` 为空；
  - 用项目 Python 3.10 解析 `website/content.py`，报 `SyntaxError`，证实网站构建需要 3.12+；
  - 核对的界面字符串：`app/features/` 中的各项（Readiness 分组、准备进度、校验面板、Modules、比较页、页头等），以及 `gridform_core/run_policy.py`、`backend/server.py`、`backend/run_supervisor.py` 和 `gridform_core/dataset_slots.py` 中的英文原文；
  - 方法学目录：advisory 标题与严重度、`assets_any` 筛选、四个论文期数据包白名单；
  - 模块版本：默认 PSM 6.6.0、staged 1.6.0、储能扩容策略 5.1.0、zonal 4.0.0；
  - 重启成本表：2025 年英镑取值与 `price_base`；
  - `SECURITY.md`、`P0_ACCEPTANCE.md` 第 6 节、`check_site.py`、`check_publication_scope.py`、`sync_methodology.py`、`release-exclusions.txt`、`HISTORICAL_VERSION_RECORDS`。
- **实测结果：**
  - 四角色终版复现角色在 `fab9ec2` 上产生的 Run 记录（scratch，只读）：VALUE 101 两年论文复现 Run 的 `result_publication.status = withheld`，储能门为 `reproduction_with_declared_deviations`，advisory 10 条，其中 6 条为 high；两个修正口径 Run 为 `published`，没有 advisory；
  - A15 数字取自 `docs/dev/GBP1_SURPLUS_CONSERVATION_INVESTIGATION.md`；
  - R3 各单元的数值取自各自的报告和 `CHANGELOG.md`。
- **四角色的结论**：本文没有替 `FOUR_ROLE_TEST_REPORT.md` 预写。附录 A.2 第 8 行要求照录那份报告终版的结论和范围。

## 3 测试与门禁

- `scripts/refresh_source_release_manifest.py --index`，然后 `--check`：`stale: false`（`docs/handoff/` 和 `docs/dev/` 都在发布排除清单中，清单内容不变）。
- `scripts/p0_gate.py quick --changed-since HEAD`（`VALUE_GATE_VENV` 指向 scratch 的 gate venv）：结果写在提交说明中。

## 4 采用的决策与偏差

- 采用：A25、A17、A21、A24（各项）、A19/A22/A22a、A20、Q2、Q3、Q13、Q14。
- 偏差：
  1. 第 2.8 节和第 7 节保留了一句“公开文档目前写 471 个时段”。这是当前两份公开文档与调查结论的不一致，不是历史叙述。上传员需要知道不能引用这个数字。
  2. 第 0 阶段（只纠正 rc1 的版本标注）是否例外地在前端翻新之前上线，A21 没有明说。本文按保守做法列为作者决定事项。

## 5 安全核对

- 没有启动服务，没有连接 8766/8800，没有向任何进程发信号；Python 全部经 `vpy` 调用。
- INSTALLED 的核对结果写在提交后的最终报告中。
