# M8 工作报告：给作者的“模型实质设定改动”简报

- 分支：`fix/review-2026-10-04`（INTEG worktree），起点 `51bcba5`。
- 任务：DECISIONS“收尾交付”第 4 项，写一份给作者的模型实质设定改动简报（简体中文）。
- 交付：
  - 仓库副本 `docs/handoff/MODEL_CHANGES_BRIEF.md`（已提交）；
  - worktree 根目录副本 `VALUE_model_changes_brief_2026-10-04.md`（被 `.git/info/exclude` 忽略，不提交）。

## 1 做了什么

1. 通读 `main..HEAD` 的提交、DECISIONS（Q1–Q15、A1–A15）、`docs/release/P0_GOLDEN_DELTA.md`、golden 数值报告 D4-r9 与 D5-r1、`GBP1_DOCTORAL_BEFORE_AFTER.md`、各单元报告和参考统计表。按以下几类整理：
   - 两个口径都改的修正，分为改变轨迹的（U1–U6）和只改核算、验证或发布的（U7–U11）；
   - 只改修正口径的修正（C1–C24），分为数据、出清、投资、网络四组；
   - 明确没有改的论文设定；
   - 待审核的数据；
   - 结果影响。
2. 为第 6 节新跑 11 次 VALUE 101 two_year（冻结项目 `tests/golden/projects/{D4,C5,C6}.json`）。所有运行都在 scratch 中完成，每个运行有自己的 `VALUE_DATA_HOME`、`HOME`、`TMPDIR`：
   - 35aadb3：用 `git archive` 的源码树运行 D4 与 C6；
   - 中间提交：3537374（C6）、5014b7b（D4、C6）、7e07437（D4、C6）、54fe0ed（C6），在各自的源码树上运行 `scripts/golden/run_case.py`；
   - HEAD：运行 D4、C5、C6。
3. **核对**：11 次运行的 golden 摘要与对应修订逐列一致，gated 差异全部为 0：
   - 35aadb3 ↔ D4/C6 r0；3537374 ↔ C6 r3；5014b7b ↔ D4 r8、C6 r6；7e07437 ↔ D4 r9；54fe0ed ↔ C6 r7；
   - HEAD ↔ D4 r10、C5 r10、C6 r8；
   - 只有 HEAD 的 D4 有 1 个 identity 列不同，是代码哈希。

   用 `result_advisories.result_publication` 核对了 Q14：HEAD 的 D4 判为 `withheld`（`GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED`，储能 DEV-STO-01），C6 判为 `published`。
4. 汇总脚本仿照 `scripts/gbp1_doctoral_before_after.py`，改为按年读取。它是一次性的只读工具，放在 scratch，没有入库。
5. 把 `docs/handoff/` 加入 `tests/baselines/release-exclusions.txt`，与 `docs/dev/` 一样不进入公开源码发布；刷新 `source-release-manifest.json`（`--index`）。

## 2 主要实测结果（写进简报第 6 节）

- **论文口径（D4）**：出力、价格、储能和排放与 35aadb3 逐位相同。两年系统成本 −640,406 £（−2.17%），其中 A4 −508,406 £，A7 −132,000 £；提案 21.32 → 8.26 MW。年度结果按 Q14 扣发。
- **修正口径（C6）**：两年系统成本 −613,410 £（−2.06%）；CCGT 发电与排放各 −0.6%；电池两年放电 0.36 → 5,208 MWh；不再有 CCGT 提案。分步看：
  - 市场规则 −4.86%；
  - 损耗系数 +5.23%；
  - P0-7 −2.18%；
  - 物理运营成本 −19 £。

## 3 测试与门禁

- 本单元只改文档和发布排除表，没有改生产代码或测试，所以没有新增测试。
- `refresh_source_release_manifest.py --index --check`：`stale: false`。
- `p0_gate quick`（提交前，含本报告以外的全部改动）：`status: passed`，195 s，16 步全部 passed，无豁免。棘轮：2381 个 id，147 个失败，基线 106，new 0，fixed_but_listed 0，flaky 0，forbidden ports 0。`guard` 与 `installed_inventory` 均为 passed。

## 4 应用的决策

- Q1、Q12：doctoral 只列白名单例外；核算类修正单列。
- A2：调度不改。
- A4、A6、A7：风光储没有 OPEX，投资判据不折现；P4-02 不在范围内。
- A9、A13、A14：哪些数值已审核、哪些仍待审核。
- A15：GBP1 的 surplus conservation 是已知问题，写明核电路径依赖。
- Q14：VALUE 101 复现运行实测为扣发。

## 5 偏差

1. 任务要求写出“对 VALUE-101 的数值影响”。现有 golden 只存摘要，没有数值，所以本单元按提交逐步重跑，得到分步数值。归因按提交组给出：P0-6 的九条规则一起激活，P0-5b 的 C1 与 C2 是同一修订，无法再拆到单条修正。A4 在修正口径上的单独影响，用 lane 提交 7e07437 旁证。
2. 新增发布排除 `docs/handoff/`。理由：交接文档面向作者和内部人员，引用 `docs/dev/` 的内部材料，不是发布文本。如果主管希望这些交接文档进入公开源码，删去这一行并重新刷新清单即可。

## 6 遗留问题

- 修正口径在 GBP1 上没有全年运行：public1 不满足资格，public2 没有登记，public2 上核电不按站处理。核电、水电、光伏倾斜面和 P4-03 在全国尺度的合计影响仍未实测（简报 5.3 节）。
- A13 的光伏倾斜面模型选择仍待作者审核。

## 7 INSTALLED 与环境核对

- `find <INSTALLED> -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'`：只列出 `<INSTALLED>/.supervisor.lock`。这是现网 supervisor 早先留下的锁文件，前几份报告已记录；app/、runtime/ 下没有新文件。
- `diagnose-value --prefix <INSTALLED>`：退出码 0，“Installation integrity and runtime checks passed.”。其中两行 vinext “Premature close” 与以前相同。

本单元没有启动服务器，没有连接 8766/8800，没有向任何进程发信号；只运行过自己的后台运行驱动，它已正常退出。scratch 中的运行输出和源码树在提交后删除。
