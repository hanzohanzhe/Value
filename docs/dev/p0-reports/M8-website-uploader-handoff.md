# M8 工作报告：给网页上传员（value.ac）的交接文档

- 分支：`fix/review-2026-10-04`（INTEG worktree），起点 `5b05c98`。
- 任务：DECISIONS“收尾交付”第 1 项。交接文档要写清三件事：新版改了什么、文件在哪、网站哪些页面要改。用简体中文。**不改 `website/`**。
- 交付：
  - 仓库副本 `docs/handoff/WEBSITE_UPLOADER_HANDOFF.md`（已提交；`docs/handoff/` 已在发布排除表中）；
  - worktree 根目录副本 `VALUE_handoff_website_uploader_2026-10-04.md`（已列在 `.git/info/exclude` 中，不提交）。

## 1 做了什么

1. 逐行通读 `website/` 的全部源文件：`build.py`、`content.py`、`journey.py`、`publication.py`、`methodology_page.py`、`release_candidate.py`、`check_site.py`、`sync_methodology.py`、`site.json`、`methodology-sync.json`、`README.md`。确认本分支的 `website/` 与 35aadb3 逐字节相同。
2. 对照下列文件，整理出网站需要反映的变化：
   - DECISIONS（Q1–Q15、A1–A15）；
   - CHANGELOG 的 0.7.0-alpha.1 一节；
   - `VALIDATION_AND_CLAIMS.md`、`P0_ACCEPTANCE.md`、`METHODOLOGY_PROFILES.md`；
   - 用户手册中英文版、`SECURITY.md`；
   - 模型改动简报、参考统计表的审核状态；
   - 前端标签源码（`runValidation.ts`、`StudyComposer.tsx`）、启动器（`desktop_value.py`）和网关（`value-ui-gateway.mjs`）。

   这些变化分为六项：口径与标签、stress event 与发布规则、安全与启动器、四类用户路径、声明范围、版本与下载文案。
3. 列出逐文件修改清单，共 40 余条，每条给出 `file:line`、现文、要求和发布阶段。发布分四个阶段，以“源码公开、安装包可用、方法学 0.4 审阅通过”为门槛。
4. 写出事实来源表、不得上传清单、需作者决定事项、`check_site.py` 检查清单，以及附录中的中英文建议文案。

## 2 主要发现（写进交接文档）

- **当前网站的 `releases`、`release-check`、`data` 三个路由，实际由 `publication.py` 生成**（因为 `publication_ready: true`）。`content.py:49-68` 和 `release_candidate.py` 的文案目前不显示。上传员若改错文件，改动不会生效。
- **网站正在提供的 rc1 下载是 0.6.0-alpha.2**，含审查报告 F5-01（critical）所述的本地 API 漏洞。是否提示或撤下，交由作者决定（交接文档第 7 节）。文档中没有写入漏洞细节。
- **发布版 GBP1 public1 不满足修正口径（默认）的资格**，在 0.7.0 中只能用于论文复现口径，而该口径下 GBP1 运行的年度结果因 A15 被扣发。数据页文案必须写明这一点。
- 网站的版次字段与 `publication-scope.json` 由 `check_publication_scope.py` 联动检查。`content.py` 等三处历史 `0.6.0-alpha.2` 受 `test_documentation_consistency` 保护，不能改。
- 网站构建需要 Python 3.12+，施工环境的 Python 3.10 无法构建。
- 网站上已有的问题（与版本无关）：
  - 四个任务标签在中文页没有翻译；
  - 引用页 source 条目的标题与所链 CFF 的版本不一致（`source-2026-10-04` 对 `source-review-2026-10-03`）。

## 3 测试与门禁

- 本单元只新增两份文档（交接文档和本报告），没有改生产代码、测试或 `website/`，所以没有新增测试。
- 没有构建网站：`content.py` 需要 Python 3.12，按施工规则不得用系统 Python 运行项目代码。交接文档第 8 节把构建和检查列为上传员的步骤。
- `refresh_source_release_manifest.py --index --check`（提交前）：`stale: false`。
- `p0_gate quick`（提交前，`VALUE_GATE_VENV` 为 gate venv）：`status: passed`，140 s，16 步全部 passed，无豁免。

## 4 应用的决策

- Q2：两个标签逐字照抄，doctoral 标签必须带固定附注。
- Q3、Q14：白名单、拒绝外部代码、年度结果的发布规则。
- A2：stress event 只记账，不改调度。
- A6、A7：不折现，风光储没有 OPEX。
- A9、A13、A14：已审核、已认可和仍待审核的数值分开写。
- A15：GBP1 已知问题与路径依赖。
- Q4、Q11、Q13：后台 Run、单用户主机、Study 迁移。
- D0-4、Q10：不重装，不打包，不推送。交接文档把相关网站改动都放在门槛之后。

## 5 偏差

1. 任务描述写的是“reference statistics pending review”。按 DECISIONS A9、A14，核电、水电和风光损耗已经审核或认可，只有光伏倾斜面的模型选择（A13）、DUKES 对照列和回退值仍待审核。交接文档按实际状态写，没有把已审核的项写成待审核。
2. 0.7.0 的四角色复测（收尾交付第 3 项）在本文提交时还不在分支上。交接文档只给出预期路径，并规定验证页的相应一行必须等报告出来后才能更新。

## 6 遗留问题与核对结果

- 目录中两处描述仍写着 “PENDING AUTHOR REVIEW”，与 DECISIONS A9（损耗系数已认可）不一致：
  - `gridform_core/data/methodology/corrections/p05.json:187`，`p05.vre-loss-factors` 的 description，以及由它生成的 `docs/generated/METHODOLOGY_PROFILES.md:70`；
  - `p05.json:7` 的包说明。

  改动会改变目录 sha256，需要主管另行处理。本单元没有改。
- 根目录 `CITATION.cff` 仍是 `source-2026-10-04`，推送前要由作者更新（交接文档第 7 节第 3 项）。

## 7 INSTALLED 与环境核对

- `find <INSTALLED> -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'`：只列出 `<INSTALLED>/.supervisor.lock`。这是现网 supervisor 早先留下的锁文件，前几份报告已记录；`app/`、`runtime/` 下没有新文件。
- `diagnose-value --prefix <INSTALLED>`：退出码 0，输出“Installation integrity and runtime checks passed.”。其中 vinext 的 “Premature close” 一行与以前相同。
- 本单元没有启动服务器，没有连接 8766/8800，没有向任何进程发信号。
