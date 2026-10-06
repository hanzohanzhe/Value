# M8 工作报告：给 methodology 修改员的交接文档

- 分支：`fix/review-2026-10-04`（INTEG worktree），起点 `7db1d76`（网站上传员交接文档的提交）。
- 任务：DECISIONS“收尾交付”第 2 项。给维护方法学文档的人写一份交接文档（简体中文），说明方法学文档需要改动的位置和内容。
- 交付：
  - 仓库副本 `docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md`，已提交；
  - worktree 根目录副本 `VALUE_handoff_methodology_editor_2026-10-04.md`。它在 `.git/info/exclude` 第 14 行中，不提交。

## 1 做了什么

1. **通读事实来源**：
   - DECISIONS（Q1–Q15、A1–A15）；
   - 七份方法学草稿 `docs/methodology/drafts/0.4/*.md`；
   - 修正目录 `gridform_core/data/methodology/`，以及生成的 `METHODOLOGY_PROFILES.md`；
   - `VERSION_LEDGER.json`、`P0_GOLDEN_DELTA.md`；
   - 作者简报 `MODEL_CHANGES_BRIEF.md`，以及网站交接文档；
   - `GBP1_DOCTORAL_BEFORE_AFTER.md`、参考统计表；
   - 各单元报告（M3-P0-5a、M4-P0-4-S7-S8、M4-P0-6、M5-P0-5b、M5-P0-7、M5-P0-7-S10、M6-P0-8b、F2、F3、M7-X0-S13-S14）；
   - 审查报告中涉及文档的条目。
2. **逐行读了 0.3 方法学的九章（en、zh）**、`VALUE_METHODOLOGY.md`，以及三份参考文档的现状。对每处要改的段落，用唯一锚点（LaTeX 片段或代码名）求出 en 与 zh 的行号，记下两版的行号偏移：
   - `core.md`：zh = en − 1；
   - `national_alternatives.md`：第 82 行之后 zh = en − 2；
   - `r029_cem.md`：第 104 行之后 zh = en − 2；
   - 其余各章两版行号相同。
3. **在代码上核对交接文档中的公式和数值**，不只抄草稿：
   - A4：火电判定、舍入吸收 `A4_NET_NOISE_RTOL`，见 `investment_accounts.py`、`v2_module_definitions.py` 第 290–312 行；
   - 修正口径的储能余量：`storage_headroom.py`，`build_deficit_for_cap` 的 scheme_c 模式，daily_loop + intraday = \(B(365)\)；
   - 电池池分配：`allocate_capped_requests`；
   - 统一边际价结算：`modular_simulation_model.py` 第 1745–1752、2448–2455 行；
   - 物理运营成本：`scheme_c_native_psm.py` 第 536–566、815–832 行；
   - 下调次序：`native_corrected.py` 第 39–56、187–199 行；
   - 天气 v2 时钟：`site_weather.py` 第 192–195 行；
   - 倾斜面换算与 Erbs 系数：`solar_irradiance.py`；
   - 核电与水电可用率：`firm_availability.py`；
   - 核电路径依赖：`modular_simulation_model.py` 第 1593–1640、1728–1733 行。
4. **核对构建与测试对文档的约束，写进交接文档**：
   - `assemble.py`：九章写死；禁止 32–64 位十六进制串和本地路径；中英结构配对；
   - `sync_methodology.py`：九章、六个文件、私有产品名正则；
   - `check_publication_scope.py`：逐字比较网站章节与源稿；`publication-scope.json` 的版次字段与文件名；
   - `tests/test_value_methodology.py`：必含短语；禁止 `force`；
   - `tests/test_documentation_consistency.py`：版本行、求解合同短语、禁止的声明。
5. **按要求组织交接文档**：
   - 每处改动写明文件、小节和 en/zh 行号，旧表述与新表述，公式用 LaTeX；
   - 标注轨道：通用、修正口径、论文复现口径保留，以及设计假设；
   - 设计假设（风光储无 OPEX、投资不折现、起始年币值等 S1–S11）与修正分开写；
   - 列出已有草稿及其中已过时的句子；
   - 给出版次升级（0.3 → 0.4）步骤和双语一致性检查清单；
   - 列出写 0.4 之前须确认的九件事，以及不属于 P0 的过时表述。

## 2 文件

| 文件 | 说明 |
|---|---|
| `docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md` | 交接文档（新增） |
| `docs/dev/p0-reports/M8-methodology-editor-handoff.md` | 本报告（新增） |

两个路径都在发布排除清单中（`docs/handoff/`、`docs/dev/`），不影响 `source-release-manifest.json`。没有修改任何方法学文档、参考文档、生产代码或测试。

## 3 测试与门禁

本单元只新增两份排除在发布之外的文档，所以没有新增测试。提交前运行了以下检查：

- `refresh_source_release_manifest.py --index --check`：`stale: false`。
- `p0_gate quick`：`status: passed`，没有新增失败。详见第 7 节。

## 4 应用的决策

- **C26、Q-X3**：0.3 源稿冻结；改动进入 0.4；0.4 的发布须经作者同意。交接文档只写改动位置，不改文档。
- **Q1、Q12、A3、A4、A5、Q9**：通用修正与口径受控修正分开列出。
- **A2**：调度不改，只记 stress event。
- **A4、A6、A7、A8**：作为设计假设写明（风光储无 OPEX，不折现，储能审核规则），不引入 NPV。
- **A9、A10、A13、A14**：区分已审核与仍待审核的数值；A13 的模型选择和 DUKES 对照列仍待审核。
- **A15**：核电路径依赖写进论文复现口径（第 4.5 节 N-7）；surplus conservation 失败写成待调查的已知问题。
- **Q2、Q6、Q14**：口径标签、价格标签与结果发布规则按固定字符串列出。

## 5 偏差

1. 任务要求列出“每一项实质改动”。除 P0 的改动外，交接文档第 10 节还附了审查报告中指出、但不属于 P0 范围的文档过时表述（P1-19、P3-07、P4-05、P5-13、P5-14、G3-03、G3-04、R2-06 等）。这些标为“可选”，避免修改员在 0.4 中原样保留明显错误。
2. 下列内容没有草稿，交接文档给出了公式或要点，但标注了事实来源，并在需要时注明“写之前须确认”：
   - 修正口径储能余量与电池池的公式；
   - A8 储能审核式；
   - DC 份额展开；
   - 核电路径依赖。
   
   其中两点我没有在代码中确认，所以没有写成结论，而是列入交接文档第 9 节：
   - 修正口径下核电接受路径依赖的量级；
   - thesis96 路径在修正口径下是否使用 P0-5b 的输入。

## 6 遗留问题（已写进交接文档第 9 节）

- **修正目录描述与代码不符**：`p05.solar-plane-of-array` 的描述写 “tilted at the site latitude”，代码取 Jacobson & Jadhav 最优倾角（`gridform_core/data/methodology/corrections/p05.json` 第 243 行）。`p05.vre-loss-factors` 的描述仍写 “PENDING AUTHOR REVIEW”，但 A9 已认可。这两处也出现在生成的 `METHODOLOGY_PROFILES.md` 中。描述只是展示字段，不进入方法哈希。按任务要求，本单元不改代码与目录，留给代码负责人修正后重新生成。
- **逐站核电实际上用不上**：逐站核电只作用于 `NUCLEAR_POLICY_PACK_IDS`（GBP1 public1），而该包在修正口径下不合格。在 public2 和 R029 上，核电取回退值 0.723。是否扩大名单，由作者决定。
- **R029 研究的口径归属**，以及第 3、6 章 R029 数值例子是否重算。
- **23 区 GB 研究的基础数据包口径资格**：网络模块只在修正口径下运行，而 GBP1 public1 在修正口径下不合格。

## 7 检查结果与 INSTALLED 核对

- `refresh_source_release_manifest.py --index --check`（两个新文件暂存后）：`stale: false`。
- `p0_gate quick`（提交前，含本单元的两个文件）：`status: passed`，用时 209 s，16 步全部 passed，没有豁免。`TMPDIR` 与 `VALUE_DATA_HOME` 都在 scratch 的 `build/m8meth/` 下。backend 棘轮的结果：
  - 失败 147 个（与 M8 简报单元相同，全部在基线内）；
  - `new_failures`、`fixed_but_listed`、`flaky`、`forbidden_port_attempts` 均为空；
  - `guard`、`installed_inventory`、`network_guard` 均为 passed。
- `find <INSTALLED> -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'`：只列出 `<INSTALLED>/.supervisor.lock`。它是现网 supervisor 早先留下的锁文件，前几份报告已记录；`app/`、`runtime/` 下没有新文件。
- `diagnose-value --prefix <INSTALLED>`：退出码 0，输出 “Installation integrity and runtime checks passed.”。其中两行 vinext “Premature close” 与以前各单元相同，是诊断工具自身的请求被提前关闭所致。
- worktree 中没有 `.pyc`。本单元没有启动任何服务器，没有连接 8766/8800，也没有向任何进程发信号。
- 并行单元（网站上传员交接）的提交 `7db1d76` 在本单元开始写作时已暂存，随后由该单元提交。本单元提交时只指定了自己的两个路径。
