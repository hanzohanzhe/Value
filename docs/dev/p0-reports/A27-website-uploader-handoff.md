# A27 工作报告：网站上传员交接文档按最终状态重写

- 分支：`fix/review-2026-10-04`（INTEG），起点 `c442545`。
- 授权：DECISIONS A25（交付文档按当前最终状态从头重写）、A26（网站方法学描述网上发布的新模型，论文复现口径是兼容口径，三项内核真错误为通用修正）、A27（四角色中低缺陷一并修复后重写四份交付文档）；作者原话“这一轮记得四个新文件都重新生成，不要把之前已经发现有错并且改过的东西给我”。
- 性质：只改文档，不改代码、参数表、golden 或 `website/`。

## 1 完成的步骤

1. 从头重写 `docs/handoff/WEBSITE_UPLOADER_HANDOFF.md`，只写 HEAD `c442545` 的状态。没有阅读横幅、逐轮历史、已修复问题的叙述或被推翻的做法；同一事项按 DECISIONS 中编号靠后的条目写最终规则。
2. 按 A26 的定位新增 2.1 节：网站方法学描述 VALUE 新模型（默认修正口径）；论文复现口径是保留论文时期设定的兼容口径，设定不是错误；论文代码以 GitHub 上锁定的历史研究档案为准（`content.py:87` 的现有说明保留）。附录 A.1、`content.py` C-1/C-16、`methodology_page.py` M-2 的文案与检查清单第 6 步的 grep 都按这一定位写。
3. 并入 R4 各单元的最终状态：
   - R4-1（A26）：三项内核修正列入通用修正；论文复现参考运行（D3、D4、D5）原始不变量全部通过、年度结果发布；逐位一致只剩 D1、D2，D3–D5 已重基线；GBP1 论文复现第一年仍记录 487 个 stress 时段、78.8 GWh 缺口；
   - R4-2：`Open ledger files`、首次运行时间估算区间、advisory 暂定；
   - R4-3：UTC 模型时钟、日期顺序、覆盖确认、价格年份提示、需求须为半小时数据；
   - R4-4：Rescan 导入扩展钩子、`GF_MODULE_CONTRACT_MISMATCH`、扩展草稿复制选中的 Study、`Experimental extension` 标记、storage cost 槽位的账本证据。
4. 核对出的现存事项，写入第 7 节：
   - `docs/VALIDATION_AND_CLAIMS.md` 与 `CHANGELOG.md` 有几处句子与当前代码不一致（逐位一致范围、golden 用例数、论文复现运行的能量平衡、通用修正清单、按施工步骤写成的小节中的旧状态），阶段 1 之前要由代码负责人同步；
   - Run 异步启动和新界面字符串仍未写进 CHANGELOG 和用户指南；
   - GBP1 勘误若公开，要用 35aadb3 与本版 D5 的直接对比，数字须先写进公开文档；
   - 换数据路径的终版验收（`final-role-swap-data.md`）仍有 1 个高等缺陷（S-F-高1），因此验证页 0.7.0 四路径一行和阶段 2 的步骤都受其约束。
5. 复制到 worktree 根目录 `VALUE_handoff_website_uploader_2026-10-04.md`（被 `.git/info/exclude` 排除，不入库），并用 `cmp` 核对与仓库副本逐字节相同。

## 2 核对依据（只读）

- **代码与配置：**
  - `git diff 35aadb3 -- website/` 为空；`website/` 各文件的行号逐一核对（`content.py`、`journey.py`、`publication.py`、`methodology_page.py`、`release_candidate.py`、`build.py`、`check_site.py`、`README.md`、`site.json` 的键和 `data_assets` 文案）；
  - 用项目 Python 3.10（`vpy`）对 `website/*.py` 做 `ast.parse`：只有 `content.py` 报 `SyntaxError`（第 26 行），证实网站构建需要 3.12+；按规则没有用系统 Python 运行网站构建；
  - `gridform_core/data/methodology/profiles.json` 与生成的 `METHODOLOGY_PROFILES.md`：两个口径、论文口径白名单、13 个与 39 个已应用修正、剩余声明偏差的门控效果均为 none；
  - `docs/release/P0_GOLDEN_DELTA.md`：15 个用例、4 对，D1、D2 轨迹 0 列变化，D3–D5 已重基线；
  - `VERSION_LEDGER.json`：默认 PSM 6.7.0、staged PSM 1.6.0、储能扩容策略 5.1.0、zonal 4.0.0；
  - 界面字符串逐条在 `app/features/`、`gridform_core/`、`backend/`、`packaging/desktop-local/desktop_value.py` 中 grep 核对；`Export ledger` 已不存在，改为 `Open ledger files`；
  - 安装器的“目标目录须不存在或为空”（`desktop_value.py:195`）、需求至少 17,520 个值（`data_pack_validation.py:367-370`）、advisory 的 `needs_review` 严重度（`result_advisories.py:88`）。
- **实测结果：**
  - `docs/dev/p0-reports/r41-golden/D5-gbp1-summary-before-after.json`（R4-1 的运行输出摘要）：`after-r41` 的 `raw_invariants_status = passed`，三个门为 passed / reproduction_conformant，stress 487 时段、74 事件、78,810 MWh，`recorded_unserved_mwh = 0`（所以 VoLL 项为 0，stress 缺口不进入该项）；
  - 用该摘要与 `GBP1_DOCTORAL_BEFORE_AFTER.md` 中 35aadb3 一列计算第 7 节第 3 条的对比：进口 1,548,150 → 360,542 MWh（−76.7%）、头条系统成本 28,126.92 → 27,201.45 百万英镑（−3.29%）、排放 29.907 → 30.685 MtCO2（+2.60%）、均价 22.348 → 18.174、最高价 5,849.53 → 50.40 £/MWh、CCGT 提案取消；
  - 四角色终版验收：`final-role-swap-data.md`（1 高、3 中、6 低）、`final-role-add-feature.md`（0 高、3 中、6 低）；复现与改模块两个角色的终版报告在本单元开始时尚未入库，本文没有替 `FOUR_ROLE_TEST_REPORT.md` 预写结论。

## 3 测试与门禁

- `scripts/refresh_source_release_manifest.py --index` 后 `--check`：结果写在提交说明中（`docs/handoff/` 与 `docs/dev/` 都在发布排除清单中，预期清单不变）。
- `scripts/p0_gate.py quick --changed-since HEAD`（`VALUE_GATE_VENV` 指向 scratch 的 gate venv）：结果写在提交说明中。

## 4 采用的决策与偏差

- 采用：A25、A26、A27、A17、A21、A24（各项）、A19/A22/A22a、A20、A18、A16、Q2、Q3、Q13、Q14。
- 偏差：
  1. 第 7 节第 7 条列出了公开文档中与当前代码不一致的句子，但没有逐字引用，也没有写出已撤销的声明偏差编号。这是上传员必须知道的现存不一致，不是历史叙述。
  2. 第 7 节第 3 条给出的 GBP1 勘误数字是本单元用两份已有的运行摘要计算的，没有重跑模型；它们目前只在内部文档中，网站引用前须先写进公开文档。
  3. 本单元没有修改 `docs/VALIDATION_AND_CLAIMS.md` 和 `CHANGELOG.md`（不在交接文档的范围内），只列为阶段 1 的前提。

## 5 安全核对

- 没有启动服务，没有连接 8766/8800，没有向任何进程发信号；Python 全部经 `vpy` 调用。
- INSTALLED 的核对结果写在提交后的最终报告中。
