# VALUE 0.7.0-alpha.1 网站交接文档（给 value.ac 上传员）

> **阅读提示（2026-10-07）：** 本文件可以照常阅读，并开始准备网站文字。但按 DECISIONS A17，**网站上传和发布要等前端整体翻新完成之后**，因为网站截图和界面说明要以翻新后的版本为准。以下内容在下一轮还会变动：修正口径的弃电顺序（A19）、电池扩容上限（A20），以及四类用户测试修复带来的界面细节。


- 日期：2026-10-06。分支 `fix/review-2026-10-04`，对照 `main`（35aadb3，即 0.6.0-alpha.2 的源码）。
- 读者：维护 `website/`（`build.py`、`content.py`、`journey.py`、`site.json`、`methodology_page.py`、`publication.py`、`release_candidate.py`、`static/`）并上传 value.ac 的人。
- 本文只写交接内容，没有改动 `website/` 下的任何文件。本分支上 `website/` 与 35aadb3 逐字节相同（`git diff 35aadb3 -- website/` 为空），所以文中的行号对两边都适用。
- 依据：`docs/dev/P0_DECISIONS.md`（Q1–Q15、A1–A18），`CHANGELOG.md` 的 0.7.0-alpha.1 一节，`docs/VALIDATION_AND_CLAIMS.md`，`docs/release/P0_ACCEPTANCE.md`，`docs/generated/METHODOLOGY_PROFILES.md`，`docs/handoff/MODEL_CHANGES_BRIEF.md`，`docs/handoff/FOUR_ROLE_TEST_REPORT.md`（第 9 节为修复轮复测），设计规格 `docs/dev/P0_FRONTEND_DESIGN_SPEC.md` 第 11 节与 `docs/dev/p0-reports/FX3-UI-batch.md`（修复轮界面字符串），以及 `docs/USER_GUIDE.md` / `docs/USER_GUIDE_ZH.md`。两者有出入时，以 DECISIONS 为准。
- **修复轮更新（2026-10-06，A16，HEAD `be30884`）**：四类用户测试之后的修复轮（FX1–FX7）带来的用户可见变化已并入本文：新增第 2.9 节（逐项列出界面字符串），并更新了 2.2–2.4、2.6、2.7、第 3 节（A17 推送时机）、4.1 S-6、4.2 C-9 与 C-11、4.3 J-3 与 J-7、第 5–7 节和附录 A。`website/` 仍未改动（`git diff 35aadb3 -- website/` 为空）。
- **FX8 更新（2026-10-06，A18）**：修正口径的核电开局在运已实施（`fx8.nuclear-in-service-at-start`，value-bid-at-cost-psm 6.4.0）。对网站用户可见的只有两处，都沿用已有的界面机制，没有新界面字符串或组件：修正口径 Study 的方法升级确认（2.9 节最后一行，现为 6.4.0），以及 Run 的 advisory 列表多一条（2.9 节新增一行）。模型说明见 2.3 节“修正口径的核电规则”一段；GBP1 public2 的数字仍只在本地（2.7 节、第 7 节第 8 条）。

---

## 0 先读这一段（结论）

1. **现在不要把 0.7.0-alpha.1 当作“可下载的新版本”上线。** 0.7.0-alpha.1 目前只存在于本地分支：没有推送，没有 tag，没有构建安装包，作者本机的安装也没有重装。网站上能下载的 Full `2026-10-03-rc1` 仍然是 **0.6.0-alpha.2**，不包含本轮任何修复。
2. 网站改动按**发布门槛分四个阶段**（第 3 节）。每个阶段只在对应门槛满足、作者同意之后上线。第 4 节逐条标出每处改动属于哪个阶段。**推送时机（A17）**：作者决定，前端整体翻新（“做法二”，须作者另行下令开工）完成之后才推送到 GitHub 或开 PR，所以阶段 1（源码公开）最早也在那之后；而且翻新会改变界面，第 2.9 节的界面字符串到时要按翻新后的版本重新核对。
3. 用户可见的核心变化有六项：
   - **两个方法学口径**，标签文案固定（第 2.1 节）；
   - **stress event 与结果发布规则**（第 2.4 节）；
   - **本地 API 安全边界与启动器行为**（第 2.5 节）；
   - **四类用户路径**的操作变化（第 2.6 节）；
   - **声明范围**（第 2.7 节）；
   - **版本与下载文案**（第 2.8 节）；
   - 修复轮另加一组：**界面与行为变化**（第 2.9 节），包括 VoLL 17,000 £/MWh、修正口径的日前互联线进口、按组列出的 Readiness、数据包校验面板、Modules 页的停用与隔离区、映射编辑器的时间戳列。4. **需要作者先决定的事项**集中在第 7 节。其中最急的一项是：网站目前提供的 rc1 下载含有一个已确认的本地 API 安全漏洞（审查报告 F5-01，0.7.0-alpha.1 已修复）。是否、以及如何在网站上提示，由作者决定。
5. **不得上传的内容**见第 6 节：
   - 0.7.0 安装包（尚未构建）；
   - 重装结果（重装须作者逐步批准）；
   - 待审核的参考统计；
   - `docs/dev/` 与 `docs/handoff/` 下的内部文档；
   - GBP1 public2；
   - 方法学 0.4 草稿。

---

## 1 版本身份对照

| 项 | 0.6.0-alpha.2（网站现状所描述的版本） | 0.7.0-alpha.1（本分支） |
|---|---|---|
| 应用版本 | `0.6.0-alpha.2` | `0.7.0-alpha.1`（Python `0.7.0a1`；`package.json`、`pyproject.toml`、`docs/release/VERSION_LEDGER.json`） |
| 源码位置 | GitHub `hanzohanzhe/Value`，tag `source-2026-10-04` | 本地分支 `fix/review-2026-10-04`。**未推送，没有 tag** |
| Full 安装包 | `2026-10-03-rc1`，四个平台；`site.json` 已列出，`publication_ready: true` | **没有构建**（`docs/VALIDATION_AND_CLAIMS.md` 中 “0.7.0-alpha.1 installers …” 一行为 `not_evaluated`） |
| 方法学文档 | 0.3 版次（2026-10-04，依据 2026-10-02），网站已导入 | 0.3 不变。0.7.0 的方法学改动写在 `docs/methodology/drafts/0.4/`，**尚未生成，也未审阅** |
| 方法学口径 | 只有一种，不记录口径 | 两种：`value-corrected`（默认）和 `doctoral-lineage-0.6.0a2`（冻结） |

历史版本号必须保留（`tests/test_documentation_consistency.py` 的 `HISTORICAL_VERSION_RECORDS`、`VERSION_LEDGER.json`）：

- `website/content.py` 中的 `0.6.0-alpha.2`，即第 74 行的 BibTeX 和第 80 行的历史元数据；
- `website/static/assets/value-source-CITATION.cff`；
- `website/static/assets/value-source-metadata.bib`。

这几处是历史记录。**不要**改成 0.7.0，否则版本一致性测试会失败。

---

## 2 0.7.0-alpha.1 相对 0.6.0-alpha.2：网站需要反映的变化

### 2.1 方法学口径与标签（Q2、Q3、Q14；`docs/generated/METHODOLOGY_PROFILES.md`）

| 机器 id | 应用内标签（英文原文，网站照抄） | 固定附注 | 默认 | 冻结 |
|---|---|---|---|---|
| `value-corrected` | `Corrected methodology (default)` | Current default methodology with review fixes of 2026-10. | 是 | 否 |
| `doctoral-lineage-0.6.0a2` | `Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)` | `not an exact reproduction of the 2026-07-18 retained trajectory` | 否 | 是 |

网站写法规则：

- 两个英文标签逐字照抄，不改大小写，不缩写。应用的 Study composer 第 1 步 “Methodology” 单选框和 Run 上下文条的徽章用的就是这两个字符串（`app/features/workspace/runValidation.ts:14`）。
- 凡出现 doctoral 标签，**必须同时出现固定附注**（Q2）。中文页写作：“论文复现口径（Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)）——按 VALUE 0.6.0-alpha.2 的实现复现论文行为，**不是** 2026-07-18 保留轨迹的精确复现。”
- 中文统一用“修正口径（默认）”和“论文复现口径”（与 DECISIONS、`USER_GUIDE_ZH.md` 一致），后面括注英文原标签。
- 新建 Study 和 Run 默认使用修正口径。旧 Run 显示 `Methodology not recorded (pre-2026-10 run)`。
- 论文复现口径的限制（Q3）：
  - 只运行论文谱系模块；
  - 只接受论文期数据包：GBP1 public1（`value-uk-open-data-pack-v1`）、`value-uk-1000twh-reproduction`、VALUE 101、synthetic contract pack；
  - **已启用外部代码（外部模块或扩展）时拒绝运行**；
  - 网络模块（staged copperplate、zonal、DC、AC）只在修正口径下运行。
- 论文复现口径的年度结果只有在**全部原始不变量通过**时才在结果页发布；否则结果页显示 `Withheld`，Inspect 和导出仍可使用（Q14）。实测中，VALUE 101 two_year 和 GBP1 第一年的论文口径运行，年度结果都被扣发（`docs/handoff/MODEL_CHANGES_BRIEF.md` 第 1 节、第 5.3 节）。网站**不得**暗示“选论文复现口径就能在结果页看到论文的年度结果”。

### 2.2 两个口径都改的修正（universal；Q9、A3、A4、A5、Q12）

这些是严格冻结的仅有例外，网站在说明“论文复现口径”时要一并写出：

- 互联线序列按 17,520 期时钟逐期对齐，此前被拉伸 2 倍（P6-24）；
- GBP1 的三个读取错误：
  - 比利时电价是逐小时的 EUR，此前被当作半小时的 GBP 读取。现在按 1.1 EUR/GBP 换算（P6-02）；
  - BE/NL 潮流文件对调（P6-03）；
  - 2022-10-30 夏令时之后需求错位 1 小时（P6-04）；
- 火电（燃气、生物质）投资净收入扣除运行成本，即燃料、碳价和单位时间成本（A4）。风电、光伏、储能仍以毛收入作为利润，这是论文设定，不是错误；
- stress event 记账（A2，见 2.4 节）；
- 只改核算区：残差、审计、成本账、验证；
- 修复轮新增两项，也只改核算区：
  - **VoLL（缺电价值）两个口径都是 17,000 £/MWh**（A16-5，`fx5.voll-17000`）。论文代码原为 8,000，参数默认原为 10,000。它只给“记录的切负荷”计价，不改变调度；VALUE 101 和 GBP1 的参考运行都没有记录切负荷，所以头条成本不变。网站若写 VoLL，只写 17,000 £/MWh，旧值只作为“原为”出现；
  - **储能报价写进市场账本**（`storage_orders` 核算表，`fx4.storage-offer-ledger`）：每条储能报价的价格、可报量与接受量都可以从导出的账本中核对。界面上还看不到逐条接受量（复测 M-D1 残留），网站不要写“界面显示储能逐条报价的接受量”。

**对网站的含义**：凡在 0.6.0-alpha.2 及更早版本上用 GBP1 public1 做的结果，都受 P6-02/03/04 和 P6-24 影响。在 GBP1 第一年的论文口径对比中，进口 −78%，价格尖峰消失，系统成本 −3.2%，CCGT 提案取消，排放 +3.4%（A15）。这份对比是否作为勘误在网站公开，由作者决定（第 7 节）。

### 2.3 只改修正口径的设定（概述，网站不需要逐条列）

网站上一句话概括即可，细节链接到 CHANGELOG 和方法学：

- 默认 PSM 的出清与储能规则：储能只报循环损耗，同档排在发电之后，按统一边际价结算（Q8、A8）；
- 风光可用出力：
  - 文献损耗系数：陆上 0.903，海上 0.815，光伏 PR 0.83；
  - ERA5 辐照时间约定修正；
  - 光伏倾斜面换算（A13，文献标准模型，作者已在 A16-6 认可）；
- 核电逐站负荷率与退役月份，径流水电采用 DUKES 负荷率 0.3487 与季节形状（A10、A14）；
- 储能扩容余量与电池上限（P5-01、P5-02）；
- 网络模块的经济口径（P0-8，zonal solver contract v4）；
- **修复轮：互联线进口进入日前出清**（A16-2，`fx6.day-ahead-interconnector-imports`）。论文复现口径中，进口只在实际需求超出日前计划时的平衡环节出现；修正口径中，每条正容量的互联线按当期对侧价格报入日前出清。属于方法改动，0.6.0 保存的修正口径 Study 要在界面确认一次。网站可以写成“修正口径的日前出清接受互联线进口”，不要写成“进口建模已验证”。

**修正口径的核电规则（A18，FX8 已实施）**：默认 PSM 原来每年从“没有机组在运”开始，核电在未运行时报价要加启动成本，在 GBP1 第一年几乎全年不被接受（本地验收只发 2.02 TWh，统计约 37.3 TWh）。修正口径现在让核电开局在运，按各站可用率作基荷，启动成本只在停运后重启时收取（correction id `fx8.nuclear-in-service-at-start`，value-bid-at-cost-psm 6.4.0，旧的修正口径 Study 须确认）；论文复现口径不变，其路径依赖在方法学中披露（A15）。网站如介绍默认 PSM，可以写这条规则；GBP1 public2 上的数字仍只在本地（见下文第 162 行一段与第 8 条），是否公开由作者决定。

**明确没有改的设定**（网站可以写成模型假设，A6、A7）：

- 投资判据不折现，所有金额都以起始年币值计价；
- 风光储没有可变 OPEX，固定 OPEX 视为已含在年金化 CAPEX 中；
- 缺电时段的调度方式不变（A2）。

### 2.4 验证、stress event 与结果发布（A2、Q14、P0-4、P0-9）

- **stress event**：凡接纳的供给小于需求的时段，两个口径都逐期记录缺口（`shortfall_mwh`），并按连续时段分组成事件。年度结果汇总事件次数、stress 时段数和总缺口；能量平衡账把缺口记为“缺电量”。**调度和电价没有因此改变。**
- 0.6.0-alpha.2 及更早版本**不报告**这种缺口（P3-01，缺电被隐藏）。所以旧运行“能量平衡通过”的记录不能作为“没有缺电”的证据。
- **验证门**：任一门失败（运行不变量、能量平衡、储能限值），应用显示 `Validation gate failed: …`。修正口径的 Run 被门挡住时，结果页显示 `Annual results not published`。
- **论文复现口径的扣发说明（修复轮 R-D1）**：Callout 标题为 “Annual results withheld for this reproduction run”，正文写明失败的原始不变量和行数，并说明是否命中已声明偏差，例如：`Annual results withheld: raw invariant "Storage single direction" failed (10 rows). Matches declared deviation DEV-STO-01: …`；下方有 “Open in Inspect” 和 “Export ledger”。状态条只在论文复现口径下多一个字段 `Raw invariants`（全部通过为 teal `● Passed`，否则琥珀色 `● {k} failed`）。`Energy balance ● Conformant` 只表示账目闭合，不等于物理验证通过，网站不要把它写成“已验证”。
- **带扩展的 Run（修复轮 F-D1）**：首轮四角色测试发现，0.7.0 分支上选了扩展的 17,520 期 Run 会因状态链误判而验证失败、年度结果被扣发；修复轮已修，复测中带扩展的 two_year Run 验证通过并发布年度结果。这是 0.7.0 分支自身的问题（状态链检查是 0.7.0 新增的），网站不需要单独提。
- **旧 Run**：修复前的 Run 读取时带 advisory `VALUE-ADV-2026-10-04-REVIEW`。它们原来记录的 `passed` 显示为 `superseded_pre_fix`，涉及旧 Run 的比较标为 `needs_review`。旧 Run 只读，不被改写。
- **对网站的含义**：网站上所有“已通过”“哈希一致”“已完成”的证据都来自 0.6.0-alpha.2 及更早版本，必须标明版本。在 0.7.0 中，它们属于 `superseded_pre_fix` 一类，**本轮没有在 0.7.0 上重跑**。

### 2.5 安全边界与启动器（P0-1、P0-3、Q4、Q11；`SECURITY.md`，`USER_GUIDE_ZH.md` 第 2、13、19 节）

0.7.0-alpha.1 的用户可见变化如下：

- 浏览器只与界面地址通信：`http://127.0.0.1:8800` 或 `http://localhost:8800`。`/api` 由界面网关带着会话转发。用其他主机名、另一份安装的书签打开，或者数据目录不一致时，页面显示 **Open VALUE from its launcher**。处理方法是关闭页面，用启动器重新启动。
- 启动器把 `--api-origin` 交给网关，从不传会话令牌。终端在就绪后打印 `VALUE ready: http://127.0.0.1:8800/`。
- 每个解释器都以 `-B -s -X pycache_prefix=<新目录>` 启动。安装目录里多余的字节码不再阻止启动，可用 `diagnose-value --repair-bytecode` 移入 `state/quarantine/`。
- **关闭 VALUE 不会停止正在运行的 Run**（Q4）。停止时，终端会列出仍在后台运行的 Run，下次启动时通过租约接管。
- 同一个数据目录只能运行一个后端。第二个后端以退出码 3 停止。
- **一台电脑只有一个使用者**（Q11）。不要安装在共用电脑或远程桌面服务器上。本版没有登录功能。
- 直接调用 API 的脚本，除 `GET /api/health` 外，每个请求都必须带 `X-VALUE-Session`（用 `backend.api_session.authorized_headers` 生成）。CORS 已移除。这一项影响“加功能”和“改模块”用户的脚本。
- 外部模块或扩展损坏、或者名字冲突时被隔离，VALUE 照常运行（health 显示 `degraded`）。修好后在 Modules 页点 **Rescan**。离线自救用 `python -m gridform_core.module_recovery`（P0-2）。
- 安装器只装进**不存在或为空的目录**。安装后不得移动或重命名安装目录，因为 receipt 固定了绝对路径。升级做法：把新版装进另一个空目录，再按 `docs/release/P0_ACCEPTANCE.md` 第 6 节迁移状态。0.6.0-alpha.2 留下的未完成 Run 不能在 0.7.0 中恢复，**升级前先完成或取消**。

### 2.6 四类用户路径（网站 `journey.py` 的 ROLES）

网站上的四条路径是：复现（reproduce）、换数据（adapt）、改模块（modify）、加功能（extend）。0.7.0 中各自的变化：

| 路径 | 0.7.0 的变化 | 依据 |
|---|---|---|
| 复现 | Study composer 第 1 步要选口径。“对照参考结果”必须是**同一版本、同一口径**的参考，0.6.0 rc1 的参考不能对照 0.7.0 的修正口径。论文复现口径的年度结果可能扣发，这时到 Inspect 或导出中查看。0.6.0 保存的 Study 首次运行前要在界面确认一次迁移（Q13） | Q2、Q13、Q14 |
| 换数据 | CSV 映射要声明列，隐式整数索引列会被拒绝（`GF_DATA_INDEX_COLUMN`）。EUR 价格必须填 EUR per GBP 汇率、汇率口径和价格年份（`GF_MAPPING_FX`），预览中原值与换算值并排显示。数据包校验分三层（结构、时序、合理性），并按口径判定资格；不符合所选口径的包在 composer 中标为 “not available with this methodology”。**发布版 GBP1 public1 不满足修正口径（默认）的资格**，只能用于论文复现口径。修复轮新增：Data 页每个数据包有校验面板（三层状态与两个口径的资格）；映射编辑器可选声明时间戳列（UTC 或 Europe/London），逐行检查重复、缺口和倒序，有问题不能提交；列名像 EUR 而币种选 GBP 时给琥珀色提示；互联线角色改名为 “<Country> interconnector availability (+ import / - export)”，修正口径下进口进入日前出清 | P0-5a、A16-1、A16-2、`MODEL_CHANGES_BRIEF.md` 5.3 节 |
| 改模块 | 外部模块只能在修正口径下运行，论文复现口径会拒绝已启用的外部代码。模块版本升级若属于方法变化（`requires_user_opt_in`），已保存的 Study 要在界面确认。损坏的模块被隔离，不再阻止 VALUE 启动。修正口径下，内置储能对象只报循环损耗；用户公式和外部模块的报价不变。修复轮新增：Modules 页常驻 “Disabled and quarantined” 区，每项有 Enable、Rescan、Remove，页头有 “Rescan modules”；**原地修改已安装模块的源码是允许的**，预检给琥珀色提示，Run 记录新的源码哈希，比较页显示模块方法已改变（A16-4）；储能报价可从导出账本的 `storage_orders` 表核对 | Q3、Q13、P0-2、`p06.storage-bid-cycle-only`、A16-4 |
| 加功能 | 扩展规则同上：只在修正口径下运行，冲突时隔离，修复后 Rescan，也可离线自救。直接调用 API 的脚本要带会话头。修复轮新增：**一日课程（`value_101_day`）只跑市场步骤，选了扩展时预检阻断**，要改用两时段或更长范围；带扩展的全年 Run 验证正常、年度结果正常发布 | P0-1、P0-2、A16-3 |

**0.7.0 上的四角色测试与修复轮复测已经完成**：报告在 `docs/handoff/FOUR_ROLE_TEST_REPORT.md`（第 1–8 节为首轮，第 9 节为修复轮复测；worktree 根目录副本 `VALUE_four_role_test_report_2026-10-04.md`）。复测结论：四类用户在本地源码分支上都通过，首轮的三项高缺陷（F-D1、F-D2、S-D1）都已修复，没有剩下高缺陷；仍有中等问题 N-1（校验面板与 Study 编辑器对论文复现口径资格的判断不一致）、N-2（Europe/London 时间戳的秋季重复小时只出现一次时映射预览报错）和 F2-N1（全年范围的扩展结果超过 16 MiB，Inspect 看不到，可从 Artifacts 下载）。**测试对象是 Linux 源码树（`git archive` 导出），不是安装包。** 网站 “VALUE four user paths” 的 0.7.0 一行按第 4 节 C-9 与附录 A.2 写，只能在阶段 1 之后上线；原 2026-10-02 / rc1 一行保留并标注版本。

### 2.7 声明范围（`docs/VALIDATION_AND_CLAIMS.md` “Scope of the 0.7.0-alpha.1 claims”）

网站对 0.7.0 的任何表述，都不能超出下面的范围：

- 逐位一致只限于：论文口径 golden D1–D3 的 trajectory 区，在 linux-x86_64、CPython 3.10.18、numpy 1.24.4 上用 exact 模式比较。D4、D5 各重基线一次（A4；A3、A5、A4），并附数值报告。**与 2026-07-18 保留轨迹的比较仍为 failed**。不得写“精确复现论文”。
- GBP1 前后对比只覆盖**一个模型年**（D5）。修复后没有重跑多年 GBP1。
- **已知问题（A15）**：GBP1 论文口径运行在 471 个时段违反 surplus conservation，最大 991 MWh；35aadb3 也一样。此事尚在调查，年度结果按 Q14 扣发，不对它作能量平衡声明。冻结内核中，核电一旦被接受就满功率运行到年底（路径依赖）。
- 投资决策是不折现的 ROI 和回收期检验，使用起始年币值。这是模型假设，不是经过验证的最优解。
- 修正口径是方法变化。不同口径之间的比较是不同方法的比较，不能把差异归因于某一项输入。
- 修正口径的风光容量因子**没有**对统计负荷率标定，只与 DUKES 并列披露。GBP1 代表站点等权（弃电前）陆上约为 DUKES 的 1.56 倍，海上 1.23 倍，光伏 1.04 倍（A9）；本地 public2 全年运行按装机加权为 1.43、1.24、1.09 倍。不得写“与 DUKES 一致”。
- 修正口径在 GBP1 上的全年验收**只在本地做过**（修复轮 A16-7，public2，2025 年，作者要求不发布、不上传）：水电对 DUKES +5.1%，通过；核电在 A18 之前比 Energy Trends 低 95%，A18 实施后（FX8）重跑为 38.26 TWh、+2.5%，**通过**。但这仍是只在本地、用未发布的 public2 做的验收，所以网站在作者同意之前**不得**写“修正口径已在 GBP1 上验证”，也不得引用这些运行的任何数字。public1 不满足修正口径资格，public2 没有发布。
- **R029 public1 在修正口径下的已知问题**（修复轮发现）：它的逐时光伏曲线 `sa.csv` 有 8,761 个值且没有 interval 声明，修正口径的严格读取会拒绝它（`GF_DATA_SHORT_SERIES`），修法待负责人决定。网站不得写“R029 可用于修正口径”。
- VoLL：两个口径都是 17,000 £/MWh（A16-5）。网站上出现 8,000 或 10,000 的地方，只能作为 0.6.0 的历史值。
- 修正口径的互联线日前进口（A16-2）只在 VALUE 101（进口全部被拒绝，数值不变）和本地 GBP1 public2 上跑过，属于方法改动，不是经过验证的进口模型。
- 四角色复测只覆盖 Linux 源码树上的一日、smoke 和 two_year 范围，不覆盖安装包、Windows 或 macOS。
- 本地 API 安全边界只在 Linux 源码树上验证过。已安装的 0.7.0 要重装后才能检查（`scripts/verify_local_security_boundary.py`）。Windows 发布前需要实机 smoke 测试，macOS 没有实机验证。
- 禁用措辞（与 `tests/test_documentation_consistency.py::test_claims_do_not_overstate_validation` 一致）：“globally optimal CEM”，“exact reproduction … passed/proven”，“public release decision is GO”，“smoke test proves annual economics”。

### 2.8 版本与下载文案

- 在 0.7.0 安装包构建、验证并上传到 GitHub Releases 之前：
  - 网站下载区仍然只列 `2026-10-03-rc1`，但要写明它是 **VALUE 0.6.0-alpha.2**，不含 2026-10 的审查修复；
  - 网站上任何地方都不写“0.7.0 可下载”；
  - 可以写“0.7.0-alpha.1 的源码修复已完成，安装包尚未构建”。这句话要等作者推送源码之后才能写，见阶段 1。
- 0.7.0 的 Full 包可用之后：按 `site.json` 的现有结构新增 release 条目，并按 2.5 节更新安装说明和常见问题。

### 2.9 修复轮的界面与行为变化（A16、A18；设计规格第 11 节，FX1–FX8）

以下都是 0.7.0-alpha.1 本地分支上的变化，0.6.0 rc1 中**没有**。网站只在阶段 2（安装包可用）之后写进安装、使用说明和四类用户步骤；阶段 1 最多在“新版本有哪些变化”中概括一句。英文字符串照抄应用界面（`app/`）。

| 位置 | 用户看到的变化（英文原文照抄） | 依据 |
|---|---|---|
| Run 页 Readiness 卡片 | 不再只显示前 6 条：问题按六组列出（Errors 始终展开；Data plausibility 默认展开；Chronology、Other data warnings、Adapter: unit not declared、Environment and setup 默认折叠，按钮 `Show {n}`）；组头 `{组名} · {n}`；同一 code 合并为一行并注明 `×n`，悬停列出全部对象。预检有 error 时 Run 按钮禁用，旁边写明原因 | S-D1、M-D3 |
| Data 页数据包校验面板 | 每个数据包一张：`Validation`（Structural / Chronology / Plausibility）与 `Methodology use`（Corrected / Doctoral reproduction），`Show details ▾` 逐层列出发现；原 `required inputs ready` 改为 `inputs present · validation {最差状态}`。**已知问题 N-1**：对用户数据包，面板可能显示 Doctoral reproduction 可用，而 Study 编辑器按论文期白名单拒绝；以编辑器为准 | S-D2 |
| 映射编辑器 | 可选字段组 `Timestamp column (optional)`：`Timestamp column`、`Time zone`（UTC / Europe/London）；逐行列出不可读、重复、倒序、缺口和步长不规则，有问题不能提交。列名含 `eur` 或 `€` 而 Currency 选 GBP 时，琥珀色提示 `Column name suggests EUR — confirm the currency.`（不阻断）。**已知问题 N-2**：Europe/London 的秋季重复小时只出现一次时，预览报 “Model execution failed”，改用 UTC 或带偏移的时间戳可以避开 | S-D4、S-D5 |
| Data 页数据角色 | 五个互联线角色改名为 “<Country> interconnector availability (+ import / - export)”（正值为进口能力，负值为出口能力） | A16-2 |
| Run 范围下拉框与预检 | Study 选了扩展时，一日选项显示 `One-day market lesson (extensions do not run)`；选它会被阻断：`The one-day lesson runs the market step only, so the selected extension(s) {names} would not execute. Choose two-period or a longer scope, or deselect the extension(s).` | F-D2，A16-3 |
| Run 上下文条与 Callout（论文复现口径） | `Raw invariants` 字段；扣发说明写明失败的原始不变量与声明偏差（第 2.4 节） | R-D1 |
| Modules 页 | 常驻 `Disabled and quarantined` 区（停用的模块与扩展、隔离的条目），每项 `Enable`、`Rescan`、`Remove`（Remove 先确认；只是移到 `modules/disabled-manifests/removed/`，不删除；被 Study 或 Run 引用时拒绝）；页头全局 `Rescan modules`；Enable 失败时显示本次扫描的错误 | M-D4、F-D3 |
| 预检（原地改模块源码） | 琥珀色提示 `Module {id} source changed since install ({old8}… → {new8}…). Results will record the new source hash.`；比较页显示模块方法已改变 | M-D2，A16-4 |
| 成本 | VoLL 默认 17,000 £/MWh（参数 `market.voll_gbp_per_mwh`）；有记录的切负荷时运营成本相应增加 | A16-5 |
| 修正口径的 Study 迁移 | 默认 PSM 升到 6.4.0（6.2.0 VoLL、6.3.0 日前进口、6.4.0 核电开局在运），0.6.0 及 FX8 之前保存的修正口径 Study 首次运行前要在界面确认一次方法升级（Q13）；界面与 6.3.0 时相同，只是升级内容多了一条 correction | A16-2、A16-5、A18 |
| Run 结果页的 advisory 列表（论文复现口径与旧 Run） | 没有应用 A18 的默认 PSM Run（所有论文复现口径 Run，以及 FX8 之前的修正口径 Run）多一条 high 级 advisory，标题照抄：`Nuclear started the year off and paid its start-up cost to enter`。论文复现口径 Run 和 0.6.0 的旧 Run 原来已有其他 high 级 advisory，所以它们的 `needs_review` 不变；只缺这一条的修正口径 Run（本分支上 FX8 之前跑的，0.6.0 用户手里没有）会因此变为 `needs_review`。结果是否在结果页发布不受影响（Q14 只看 raw invariants）。没有核电的数据包（如 VALUE 101）也会列出这一条，因为它按模块而不是按数据包判断 | A18、A15 |

**注意**：`CHANGELOG.md` 已有 VoLL（A16-5）、日前进口（A16-2）、储能报价账本（M-D1）、GBP1 public2（FX7）和核电开局在运（FX8，“Nuclear in service at the start of the year”）各节；但 FX1–FX3 的界面变化（上表前八行中除数据角色以外的各项）**还没有写进 `CHANGELOG.md` 和 `docs/USER_GUIDE*.md`**。网站文案在阶段 2 之前须等这两份文档补齐（第 7 节第 7 条），在那之前只能以设计规格第 11 节和 `docs/dev/p0-reports/FX3-UI-batch.md` 为准，而这两份是内部文档，不得上传。

---

## 3 分阶段发布门槛

| 阶段 | 门槛（全部满足，并经作者同意） | 网站可以上线什么 |
|---|---|---|
| **0 现在** | 只要作者同意文案 | 只限纠错与提示：rc1 的版本标注；旧证据标注为 0.6.0-alpha.2 证据；作者批准后可加 rc1 的安全提示（第 7 节）。**不出现 0.7.0 的功能描述。** |
| **1 源码公开** | 作者把 0.7.0-alpha.1 推送到 `hanzohanzhe/Value`，并打出源码 tag（tag 名由作者定，本文不预设）。按 A17，推送只在前端整体翻新（做法二）完成之后进行，所以推送的版本会比本文描述的分支多出翻新的改动；上线前按推送时的 CHANGELOG 重新核对 | 两个方法学口径的介绍、声明范围、验证页新增行、引用页新增源码条目、Develop 页源码链接、GBP1 勘误（若作者同意公开） |
| **2 安装包可用** | 0.7.0 Full 安装包构建（`scripts/prepare_private_runtimes.py`、`scripts/build_full_desktop_installers.py`，每一步都要作者批准），在目标平台验收，并上传到 GitHub Releases，有确定的文件名、字节数和 SHA256 | `site.json` 的 release 条目、下载页、安装页（启动器、升级、常见问题）、四类用户路径的新步骤、数据页的口径资格说明 |
| **3 方法学 0.4** | methodology 修改员完成 0.4 版次（源稿：`docs/methodology/drafts/0.4/`），作者审阅通过，六个文档（中英文 × docx/pdf/html）有获批的哈希 | 用 `website/sync_methodology.py` 整体导入 0.4，同时更新 `publication-scope.json` 和 `site.json` 的版次字段 |

阶段 2 的四类用户步骤只适用于 0.7.0。**在阶段 2 之前更新这些步骤，会误导仍在使用 rc1（0.6.0）的用户。**

---

## 4 逐文件修改清单

表中“现文”是当前源码字符串，较长的只摘关键片段；“要求”说明应改成什么。中英两种语言都要改，`t(en, zh)` 的两个参数都要动。行号对应本分支，也对应 35aadb3。

### 4.1 `website/site.json`

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| S-1 | `products[0].releases[*]`（4 条，`version: "2026-10-03-rc1"`）以及 `planned_release_assets` | rc1 四个平台的条目，`requirements: "Bundled Python and Node; see platform installation guide"` | 阶段 0：条目不动。如需标版本，在 `requirements` 后补 “· VALUE 0.6.0-alpha.2”（`check_site.py` 只要求该字段非空）。阶段 2：为 0.7.0 新增条目，字段与现有条目相同：`version`、`platform`、`date`、`size`、`bytes`、`requirements`、`url`（必须 https）、`sha256`（64 位十六进制）、`filename`、`native_acceptance`（只有在该平台实机验收通过时才填 `true`）。新条目的值一律取自实际上传的文件，**不要预填** | 0 / 2 |
| S-2 | `candidate_release_id`、`package_evidence_date` | `"2026-10-03-rc1"`、`"2026-10-03"` | 阶段 2 改为新安装包的 id 和日期 | 2 |
| S-3 | `source_tag`、`source_validation` | `"source-2026-10-04"`；`historical_scientific_replay: false` 等 | 阶段 1 改为作者打出的新 tag；`source_validation` 只填对新 tag 实际做过的检查 | 1 |
| S-4 | `evidence_date`、`methodology_edition`、`methodology_revision_date` | `"2026-10-02"`、`"0.3"`、`"2026-10-04"` | **只在阶段 3 改**，并且与 `publication-scope.json` 的 `scientific_basis_date`、`edition`、`revision_date` 同步改。`scripts/check_publication_scope.py` 的 `products()` 会逐项比较，单独改一边就会失败。`sync_methodology.py` 会自动写 `site.json` 的这三项 | 3 |
| S-5 | `data_assets`，`value-uk-open-data-pack-v1-public1-…zip` 的 `interface` | “Import through national Data UI/API; preserve runtime pack ID value-uk-open-data-pack-v1.” | 阶段 2 补一句。英文：“In VALUE 0.7.0-alpha.1 this pack is eligible for the doctoral reproduction profile only; the corrected (default) profile does not accept it. Both profiles read its Belgium price as hourly EUR at 1.1 EUR/GBP, its BE/NL flows by line identity and its demand on the UTC clock.” 中文：“在 VALUE 0.7.0-alpha.1 中，此包只能用于论文复现口径，修正口径（默认）不接受；两个口径都把比利时电价按逐小时 EUR、1.1 EUR/GBP 读取，BE/NL 潮流按线路身份读取，需求按 UTC 时钟读取。” | 2 |
| S-6 | `data_assets`，`value-uk-calendar-vx-trade001-…zip`（R029）的 `interface` | “… Doctoral frozen replay is unsupported on the current Full; no failed doctoral Study template is provided.” | 阶段 2 把 “current Full” 写明为 0.6.0 rc1，并补充：R029 不在 0.7.0 论文复现口径的数据包白名单中。**不要写“可用于修正口径”**：修复轮发现它的光伏曲线在修正口径的严格读取下被拒绝（`GF_DATA_SHORT_SERIES`，2.7 节），修法待定。只写“以应用内 Study composer 的资格提示为准”；若修法在阶段 2 前仍未落地，作者决定是否补一句已知问题 | 2 |
| S-7 | `data_assets` 中 11 区、23 区网络两条 | — | 阶段 2 补一句：网络模块只在修正口径下运行（Q3） | 2 |
| S-8 | `methodology_release_assets` | 指向 `methodology-0.3-2026-10-04` | 阶段 3 才改 | 3 |

### 4.2 `website/content.py`

> 注意：`publication_ready` 为 `true` 时，`publication.py` 会用自己的页面**替换** `releases`、`release-check` 和 `data` 三个路由（`publication.py:14`、`:27`）。所以 `content.py:49-63`（releases）和 `:64-68`（data）、`release_candidate.py` 全文**目前不会出现在网站上**。下载区和数据页的文案要改 `publication.py` 和 `site.json`（4.4 节）；`content.py` 中这几段只在 `publication_ready` 改回 `false` 时才需要同步。

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| C-1 | `:29` 表格 “Configurations are part of the method” 之后（`models/value` 页） | — | 阶段 1 新增一节 “Two methodology profiles / 两种方法学口径”。用 `table()` 列出两个口径，三列：标签（英文原文）、含义、边界。文案见附录 A.1。固定附注必须出现 | 1 |
| C-2 | `:30` note “Read the evidence with its scope” | “The 2025–2034 national baseline completed 175,200 half-hour periods and repeated settlement hashes in engineering checks. …” | 阶段 0 在句首补版本：“In VALUE 0.6.0-alpha.2 (before the October 2026 review fixes), the 2025–2034 national baseline …”；中文：“在 VALUE 0.6.0-alpha.2（2026 年 10 月审查修复之前）中，2025–2034 全国基线……”。再补一句：“It has not been re-run under 0.7.0-alpha.1, where such pre-fix runs are marked `superseded_pre_fix`.” / “该基线未在 0.7.0-alpha.1 上重跑；0.7.0 把修复前的运行标为 `superseded_pre_fix`。”（后半句属于阶段 1） | 0 / 1 |
| C-3 | `:33` `study_data`，national-baseline 的状态 | `t('Engineering checks completed', '基线工程检查已完成')` | 阶段 0 改为 `'Engineering checks completed · 0.6.0-alpha.2'` / `'基线工程检查已完成 · 0.6.0-alpha.2'` | 0 |
| C-4 | `:41` `study_page`，标签 | `'Evidence snapshot · 2 October 2026'` | 保留日期，表明这是快照。阶段 1 有新证据时才改日期，而且只改有新证据的案例 | 1 |
| C-5 | `:46` VALUE 101 复现步骤第 3、4 条 | “Create or open the teaching Study, confirm its 48 periods and explicitly start a Run.” / “Inspect the result tables and compare against the reference bundled with that exact release.” | 阶段 2 改为：第 3 条加 “choose the methodology profile” / “选择方法学口径”；第 4 条加 “of the same version and methodology profile” / “同一版本、同一口径的”，再补一句：“Doctoral reproduction results are published only when every raw invariant passed; otherwise read them in Inspect or the export.” / “论文复现口径的年度结果只有在原始不变量全部通过时才在结果页发布，否则到 Inspect 或导出中查看。” | 2 |
| C-6 | `:47` national-baseline 的 “Engineering evidence” 表与 “Use the evidence correctly” 段 | 三行：时间覆盖、复跑哈希一致、解释范围 | 阶段 0 在表中新增一行 “Software version / 软件版本 → 0.6.0-alpha.2 (before the 2026-10 review fixes) / 0.6.0-alpha.2（2026-10 审查修复之前）”。阶段 1 在 “Use the evidence correctly” 段补充：该版本不报告供给不足的时段（stress event 自 0.7.0 起记录）；GBP1 读取修正与火电净收入修正都在该基线之后。中文同义 | 0 / 1 |
| C-7 | `:48` gb-zonal 案例 | “… fixed, lossless zonal transport formulation …”；“Evidence status …” | 阶段 1 在 “Interpretation boundary” 段补充：0.7.0 的 zonal solver contract 为 v4；P0-8b 之前记录的网络成本和 redispatch 增减弃电量不能支持研究结论；网络模块只在修正口径下运行。中文同义 | 1 |
| C-8 | `:69` validation 表第 1 行（national baseline） | “2025–2034 completed; 175,200 half-hours; rerun settlement hashes identical.” | 阶段 0 在 “VALUE national baseline” 后补 “(0.6.0-alpha.2)” / “（0.6.0-alpha.2）”，边界列补 “Pre-fix evidence; not re-run under 0.7.0-alpha.1.” / “修复前证据，未在 0.7.0-alpha.1 上重跑。” | 0 |
| C-9 | `:69` validation 表第 2 行（four user paths） | “Four specified tasks passed after fixes on 2 October 2026. …” | 阶段 0 补 “on Full 2026-10-03-rc1 (0.6.0-alpha.2)” / “基于 Full 2026-10-03-rc1（0.6.0-alpha.2）”。四角色复测报告已有（2.6 节）：阶段 1 **另起一行**写 0.7.0 源码上的结论（文案见附录 A.2 第 6 行，必须写明“源码树、非安装包”）；阶段 2 有安装包且在安装包上重测后，再改为安装包的结论。原行保留 | 0 / 1 / 2 |
| C-10 | `:69` validation 表第 3 行（GB zonal） | “Longer-horizon validation in progress in the source snapshot.” | 阶段 1 边界列补 “Network modules run only under the corrected profile in 0.7.0-alpha.1.” / “0.7.0-alpha.1 中网络模块只在修正口径下运行。” | 1 |
| C-11 | `:69` validation 表（新增行） | — | 阶段 1 按 `docs/VALIDATION_AND_CLAIMS.md` 新增五行，另按 `docs/handoff/FOUR_ROLE_TEST_REPORT.md` 第 9 节加四角色一行（修复轮），共六行，见附录 A.2。不得超出 2.7 节的范围 | 1 |
| C-12 | `:70` note “Evidence snapshot · 2 October 2026” | 标题和正文 | 阶段 1 有新增行时，把标题日期改为新增证据的日期，正文不变 | 1 |
| C-13 | `:74` `bib`、`:80` 历史元数据段 | `version = {0.6.0-alpha.2}` 等 | **不改**（历史记录，受版本一致性测试保护） | — |
| C-14 | `:76` cite 页 “VALUE · source-2026-10-04” 一节 | 链接 `/assets/value-source-review-CITATION.cff` | 阶段 1 在其上方新增一节 “VALUE · <新源码 tag>”，引用文件取仓库根目录 `CITATION.cff`（由作者在推送前更新为新 tag，**本分支尚未更新**，见第 7 节）。原节保留。另见 9.2 节 | 1 |
| C-15 | `:79` cite 页 rc1 一节 | “Current full-installation candidate. …” | 阶段 0 补 “It contains VALUE 0.6.0-alpha.2.” / “其中的应用版本为 VALUE 0.6.0-alpha.2。”。阶段 2 把 “Current” 改为 “Earlier”，并新增 0.7.0 安装包的引用条目，新文件放在 `static/assets/release-candidate/` 的新子目录或新文件名下，旧文件不覆盖 | 0 / 2 |
| C-16 | `:94` 各页 “Versioned methodology” 注 | “Read the audited equations, numerical parameters, pseudocode and initial dataset identities. …” | 阶段 1 补一句：“Methodology edition 0.3 describes VALUE 0.6.0-alpha.2; the corrected profile of 0.7.0-alpha.1 is documented in the CHANGELOG until edition 0.4 is reviewed.” / “方法学 0.3 版次描述 VALUE 0.6.0-alpha.2；0.7.0-alpha.1 修正口径的改动在 0.4 版次审阅前以 CHANGELOG 为准。”。阶段 3 再删去这句 | 1 / 3 |

### 4.3 `website/journey.py`

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| J-1 | `:2-6` `ROLES` 的说明文字（第 3、4 列） | 复现：“Run VALUE 101 and compare the matching reference.” / “运行 VALUE 101，对照同版参考结果。”；改模块：“Change a supported module and compare its results with the baseline.” | 阶段 2 改为：复现 “Choose a methodology profile, run VALUE 101 and compare the reference of the same version and profile.” / “选择方法学口径，运行 VALUE 101，对照同版本、同口径的参考结果。”；改模块和加功能各补 “(corrected profile)” / “（修正口径）”。第 2 列的英文标签见 9.1 节 | 2 |
| J-2 | `:20` 首页 Install 卡 | `'Full candidates are available. Check platform validation before starting.'`（`publication_ready` 时生效） | 阶段 0 补版本：“Full 2026-10-03-rc1 (VALUE 0.6.0-alpha.2) is available. …” / “Full 2026-10-03-rc1（VALUE 0.6.0-alpha.2）可下载……”。注意 `:50` 的 `replacements` 字典按整句替换，改 `:20` 时要同步改 `:50` 的键和值，否则替换不再生效 | 0 / 2 |
| J-3 | `:29-34` `instructions` / `chinese` 四组步骤 | 见源码 | 阶段 2 按 2.6 节和 2.9 节改写，文案见附录 A.3（修复轮已更新）。中英两组列表的条数必须一致（`zip` 逐条配对） | 2 |
| J-4 | `:40` Develop 页源码链接 | `https://github.com/hanzohanzhe/Value/tree/source-2026-10-04` | 阶段 1 改为新 tag；可以保留旧 tag 作为第二个链接 | 1 |
| J-5 | `:43` Install 页步骤与 note | 第 4 步 “Open the local address printed by the launcher; start with VALUE 101.”；note “Public downloads remain pending. Linux candidate offline installation …” | 阶段 2：第 2 步改为 “… extract the complete archive into a new, empty directory” / “……解压到一个新的空目录”；第 4 步补 “(http://127.0.0.1:8800 or http://localhost:8800)”；新增一步 “To upgrade, install the new version into another empty directory; finish or cancel unfinished runs first.” / “升级时把新版本装进另一个空目录，并先完成或取消未结束的 Run。”。代码框中的 `"$HOME/VALUE-full"` 不必改，升级说明里用另一个目录名举例即可 | 2 |
| J-6 | `:45` note “Included environment” | — | 阶段 2 新增一条 note：“One user per computer. Do not install VALUE on shared computers or remote-desktop servers.” / “一台电脑一个使用者，不要安装在共用电脑或远程桌面服务器上。”（Q11、`SECURITY.md` “Single-user host assumption”） | 2 |
| J-7 | `:47` FAQ | 三问：页面打不开 / 输入校验失败 / 如何停止 | 阶段 2：(a) “如何停止”的答案补 “Runs in progress keep running in the background and are supervised again at the next start.” / “正在运行的 Run 会在后台继续，下次启动时重新接管。”；(b) 新增问题 “The page says ‘Open VALUE from its launcher’.” / “页面显示 Open VALUE from its launcher。”，答案见附录 A.4；(c) 新增问题 “A module or extension is quarantined (health: degraded).” / “模块或扩展被隔离（health 显示 degraded）。”，答案见附录 A.6（修复轮：Modules 页的 Disabled and quarantined 区）；(d) “输入校验失败”的答案补 “declared column, and for EUR prices the rate, FX basis and price year” / “声明的列，欧元价格还要填汇率、汇率口径和价格年份”，修复轮再补 “an optional timestamp column is checked row by row” / “可选的时间戳列会逐行检查”；(e) 修复轮新增问题 “Annual results withheld for this reproduction run.” / “论文复现 Run 的年度结果被扣发。”，答案见附录 A.6；(f) 修复轮新增问题 “The one-day lesson will not start with my extension.” / “选了扩展后一日课程不能运行。”，答案见附录 A.6 | 2 |
| J-8 | `:50` `replacements` | 按整句替换的字典 | 每改一次 `:20`、`:42` 或 `:43` 的句子，都要同步改这里的键和值。改完构建后，用 `grep` 检查 `dist/` 中是否还残留 “pending” 句子（第 8 节第 5 步） | 0 / 2 |

### 4.4 `website/publication.py`（`publication_ready: true` 时它决定下载页和数据页）

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| P-1 | `:7`、`:10` 平台状态 | “Linux offline installation and scoped tasks passed.” / “Experimental candidate; …” | 阶段 0 不动。阶段 2 让状态文字带版本，可以从新增的 `release['version']` 读取 | 2 |
| P-2 | `:12` 下载页 heading 与 note | `w.heading('VALUE / 2026-10-03-rc1', …)`；note “Full includes Python, Node and dependencies. These installer candidates have their own source identity; …” | 阶段 0 在 note 中补 “2026-10-03-rc1 contains VALUE 0.6.0-alpha.2 and predates the October 2026 review fixes.” / “2026-10-03-rc1 的应用版本为 VALUE 0.6.0-alpha.2，早于 2026 年 10 月的审查修复。”。若作者批准安全提示，在这里加第二条 note（第 7 节）。阶段 2：heading 中的批次名改为从 `site.json` 的 `candidate_release_id` 读取，不再写死；新增 0.7.0 卡片，旧 rc1 卡片可以保留并标为 “Earlier candidate” | 0 / 2 |
| P-3 | `:22` 数据页 note “Execution scope” | “The final GBP1 pack … initializes five nuclear stations totalling 5,958 MW. A two-period run passed …” | 阶段 0 补 “(checked on Full 2026-10-03-rc1, VALUE 0.6.0-alpha.2)” / “（在 Full 2026-10-03-rc1、VALUE 0.6.0-alpha.2 上检查）” | 0 |
| P-4 | `:23` 数据页 note “Research boundaries” | “… doctoral initialization/investment eligibility currently fails on Full, so frozen doctoral replay is not offered. …” | 阶段 2 改写。0.7.0 新增了论文复现口径：GBP1 public1 是它的白名单数据包，但 GBP1 论文口径运行的年度结果因已知问题（A15）被扣发；R029 和 11 区、23 区套件不在论文口径白名单中；发布版 GBP1 public1 不满足修正口径的资格。阶段 2 之前**保留原句**，因为它对 rc1 仍然成立，只在 “on Full” 后补 “2026-10-03-rc1” | 0 / 2 |
| P-5 | `:25` 数据页、about、docs 页的 note “Clean source snapshot” | “source-2026-10-04 passed clean installation, frontend build, …” | 阶段 1 新增一条关于新源码 tag 的 note，只写对该 tag 实际做过的检查；旧 note 保留 | 1 |
| P-6 | `:30` `ready_copy` 替换表 | 键值对 | 改 `content.py:46`、`:87`、`:79` 中被替换的原句时，同步改这里 | 0 / 2 |
| P-7 | 新增内容（数据页） | — | 阶段 1 或 2 若作者同意公开 GBP1 勘误（第 7 节），在数据页 GBP1 一行下面加一条 note：0.6.0-alpha.2 及更早版本读 GBP1 public1 时的四个读取问题（P6-02/03/04、P6-24）和一年对比的方向（进口 −78% 等）。数字只能取自 `docs/dev/GBP1_DOCTORAL_BEFORE_AFTER.md` 和 CHANGELOG，**不上传该文件本身** | 1 |

### 4.5 `website/methodology_page.py`

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| M-1 | `:17` heading lead | “Mathematical formulation, algorithms and input data for system operation, annual investment, transmission.” | 不改 | — |
| M-2 | `:23` 之后（methodology-intro 中，修订日期那行之后） | — | 阶段 1 新增一条 `w.note`。英文：“Edition 0.3 describes VALUE 0.6.0-alpha.2. VALUE 0.7.0-alpha.1 adds two methodology profiles; the corrected (default) profile changes are listed in the CHANGELOG until edition 0.4 is reviewed.” 中文：“0.3 版次描述 VALUE 0.6.0-alpha.2。VALUE 0.7.0-alpha.1 新增两种方法学口径；修正口径（默认）的改动在 0.4 版次审阅前以 CHANGELOG 为准。” 阶段 3 导入 0.4 时删去 | 1 / 3 |
| M-3 | `website/methodology/*.json`、`static/assets/methodology/*` | 0.3 版次 | **不要手改**。阶段 3 只能通过 `sync_methodology.py --source ../docs/methodology --build <渲染目录> --documents <六个文件目录>` 整体替换；`docs/methodology/edition.json` 和 `artifacts.json` 要先由 methodology 修改员按 0.4 更新 | 3 |

### 4.6 `website/release_candidate.py`、`website/build.py`、`website/README.md`、`website/UPLOAD-FILES.txt`

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| R-1 | `release_candidate.py:5-8` | “The 2026-10-03-rc1 candidate is an internal review artifact. …” | `publication_ready: true` 时不会显示（被 `publication.py` 替换）。只有作者决定撤下 rc1（把 `publication_ready` 改为 `false`）时才需要改：那时补 “VALUE 0.6.0-alpha.2” 和撤下原因 | 视第 7 节决定 |
| B-1 | `build.py:46`、`:51` 导航与页脚 | — | 不需要改。若新增页面，路由加在 `content.py` 的 `add(...)` 中，中英文都会生成；`check_site.py` 会检查每个页面都有对应译文 | — |
| D-1 | `website/README.md:12`、`:26` | “Full installer downloads remain pending.”；“The reviewed 0.3 edition dated 2026-10-04 …” | 阶段 2 更新下载状态，阶段 3 更新版次。README 不发布到网站，但会进入源码发布清单 | 2 / 3 |
| U-1 | `website/UPLOAD-FILES.txt` | 上传文件清单（静态资源和源文件） | 新增或删除 `static/` 下的文件（例如新的 release-candidate 引用文件、0.4 方法学文档）时同步更新 | 2 / 3 |

改动 `website/` 下的任何文件之后，仓库根目录的 `source-release-manifest.json` 都要刷新（第 8 节第 7 步）。

---

## 5 事实来源（网站文案只能从这里取）

| 内容 | 路径 |
|---|---|
| 所有决策（最高依据） | `docs/dev/P0_DECISIONS.md`（内部，不发布） |
| 版本变化总表、迁移说明、API 变化、已知问题 | `CHANGELOG.md` 的 “0.7.0-alpha.1” 一节 |
| 口径、修正 id、白名单 | `docs/generated/METHODOLOGY_PROFILES.md`（由 `gridform_core/data/methodology/` 生成，不要手改） |
| 声明范围与证据 | `docs/VALIDATION_AND_CLAIMS.md`（含 “Scope of the 0.7.0-alpha.1 claims”）；`docs/SCHEME_C_MODEL_CARD.md` |
| golden 变化 | `docs/release/P0_GOLDEN_DELTA.md`；`tests/golden/reports/D4-r9.json`、`D5-r1.json` |
| 验收与重装步骤 | `docs/release/P0_ACCEPTANCE.md`（第 6 节重装**未执行**） |
| 版本号 | `docs/release/VERSION_LEDGER.json`；`package.json`；`pyproject.toml` |
| 用户可见行为（标签、状态词、启动器、常见问题） | `docs/USER_GUIDE.md`、`docs/USER_GUIDE_ZH.md`（第 2、12、13、19 节）；`SECURITY.md` |
| 模型设定改动（给作者的简报，可作背景） | `docs/handoff/MODEL_CHANGES_BRIEF.md`（内部，不发布） |
| GBP1 前后对比 | `docs/dev/GBP1_DOCTORAL_BEFORE_AFTER.md`（内部；是否公开由作者决定） |
| 参考统计（核电、水电、风光损耗） | `docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md`（内部，部分仍待审核） |
| 方法学 0.4 源稿 | `docs/methodology/drafts/0.4/*.md`（未审阅，发布时排除） |
| methodology 修改员的交接 | `docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md`（worktree 根目录副本 `VALUE_handoff_methodology_editor_2026-10-04.md`） |
| 0.7.0 四角色测试与修复轮复测 | `docs/handoff/FOUR_ROLE_TEST_REPORT.md`（第 9 节为复测；worktree 根目录副本 `VALUE_four_role_test_report_2026-10-04.md`；内部，不发布） |
| 修复轮界面字符串（在 CHANGELOG 与用户指南补齐之前） | `docs/dev/P0_FRONTEND_DESIGN_SPEC.md` 第 11 节、`docs/dev/p0-reports/FX3-UI-batch.md`、`docs/dev/P0_FRONTEND_DEVIATIONS.md`（F-FX2、F-FX3 两节）；都是内部文档，只用来核对字符串 |
| GBP1 修正口径本地验收 | `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md`（内部；作者要求不发布；第 10 节为 A18 之后的重跑，核电通过） |

---

## 6 现在不得上传或不得写的内容

1. **0.7.0 安装包与下载链接**：没有构建。`site.json` 中不能出现 0.7.0 条目，也不能出现猜测的 URL、大小或 SHA256。
2. **“已升级、已重装”之类的表述**：作者本机的安装仍是 0.6.0-alpha.2。重装（`P0_ACCEPTANCE.md` 第 6 节）每一步都要作者批准，目前没有执行。
3. **待审核的参考统计**：
   - ~~光伏倾斜面换算的模型选择（A13）仍为 PENDING AUTHOR REVIEW~~（A16-6 更新：作者已直接认可这些文献模型；网站可写“采用文献标准模型，作者认可”，但不得写“已校准”）；
   - DUKES 对照列（参考统计表第 3.4 节）仍标为 PENDING，只用于披露；
   - 回退值（全国核电 0.723、AGR 0.727、新建 PWR/EPR 0.801）没有逐条审核。

   网站不得把这些说成“经审核”或“已校准”。核电逐站负荷率和水电 0.3487 已审核（A14），风光损耗系数已认可（A9），但网站最多写“文献取值，未对统计负荷率标定”。
4. **内部文档**：`docs/dev/`、`docs/handoff/`（包括本文）、worktree 根目录的 `VALUE_*.md` 都不进入网站，也不进入公开源码（`tests/baselines/release-exclusions.txt`）。
5. **GBP1 public2**：数据包只在本地构建，没有发布（CHANGELOG “Nothing is uploaded”）。修复轮（FX7）在代码中把它的 id 登记为 scientific_reference，并加入核电分站名单，但这只是让本地构建的包能按修正口径运行，**不等于发布**。不得列入 `data_assets`，也不得引用本地验收运行的数字（2.7 节）。
6. **方法学 0.4 草稿**：不得导入 `website/methodology/`，也不得作为下载提供。
7. **超出声明范围的说法**：见 2.7 节的禁用措辞，以及“与 DUKES 一致”“精确复现论文”“能量平衡已验证（GBP1 论文口径）”。
8. **安全漏洞细节**：审查报告中的复现步骤（请求头、端点、DNS rebinding 做法）**不得**写到网站上。是否发安全提示、措辞如何，由作者决定（第 7 节）。

---

## 7 需要作者决定的事项（上传员不要自行决定）

1. **rc1 的安全提示或下架**：rc1（0.6.0-alpha.2）的本地 API 没有 Host、Origin、会话和 Content-Type 校验（审查报告 F5-01，critical；0.7.0-alpha.1 的 P0-1 已修复；DECISIONS D0-4 也记录了现有实例仍有此漏洞）。可选做法：
   - (a) 在下载页和安装页加一条中性提示，不写利用细节（建议文案见附录 A.5）；
   - (b) 把 `publication_ready` 改为 `false`，暂时撤下 rc1 下载，等 0.7.0 安装包可用后再上线；
   - (c) 维持现状。

   本文不替作者选择。
2. **GBP1 勘误是否公开**（A15 说该对比报告“作为论文结果的勘误说明保留”，没有说要在网站公开）。如果公开，写在数据页还是验证页。
3. **新源码 tag 名和推送时间**（阶段 1 的门槛）。根目录 `CITATION.cff` 目前仍是 `version: "source-2026-10-04"`，推送前要由作者更新。
4. **0.7.0 安装包的构建和发布**（阶段 2 的门槛）：包括哪些平台，是否先只发 Linux。
5. **网站上口径的中文译名**：本文建议用“修正口径（默认）”和“论文复现口径”，应用界面本身只有英文。
6. **推送时机（A17，已决定）**：前端整体翻新完成后才推送。上传员不需要决定，只需知道阶段 1 要等到那时。翻新会改界面，第 2.9 节和附录 A.3、A.6 的界面字符串届时要按翻新后的版本重新核对。
7. **修复轮界面变化写进 `CHANGELOG.md` 与用户指南**（代码负责人做，作者批准）：FX1–FX3 的界面变化（第 2.9 节）目前只在内部文档中。阶段 2 之前须补齐，否则网站文案没有可公开引用的依据。
8. **修正口径在 GBP1 上的结果何时可以公开**：A18 已实施并在本地重跑，核电对 Energy Trends +2.5%，验收通过；public2 仍未发布。是否公开、写在哪页，由作者决定。

---

## 8 上传前检查清单（`website/check_site.py`）

网站构建需要 **Python 3.12 或更高版本**：`content.py` 用了 3.12 才支持的 f-string 嵌套同类引号。项目自带的 Python 3.10（安装版运行时，以及施工用的 gate venv）**不能**构建网站。用上传员自己的 Python 3.12+ 在 `website/` 目录下运行。本单元没有构建网站（施工环境只有 3.10）。

1. **工作区干净**：`git status` 中只有本次打算修改的 `website/` 文件。
2. **构建**：`cd website && python3 build.py`，输出 `Generated N localized routes in …/website/dist`。N 应为中英文路由数之和，新增页面时 N 相应增加。
3. **站点检查**：`python3 check_site.py`。退出码 0，JSON 输出中 `local_links_and_assets: "passed"`，`errors: []`。它检查以下几项：
   - 每页的 `lang` 与目录一致，只有一个 `<h1>`，没有重复 id；
   - `origin` 非空时有 canonical 和 hreflang（en、zh、x-default）；
   - 每页都有中英对应页；
   - 本地链接和锚点都存在；
   - `site.json` 中每个 release 的 `version`、`platform`、`date`、`size`、`requirements`、`url`、`sha256` 非空，`sha256` 是 64 位十六进制，`url` 以 `https://` 开头。

   它**不**检查 `data_assets`、文案内容和外部链接是否可达。
4. **版次一致**：在仓库根目录运行 `python3 scripts/check_publication_scope.py --report <临时目录>/scope.json`，必须在 `build.py` 之后运行，因为它读 `website/dist`。`passed: true`。它会比较 `site.json` 与 `publication-scope.json` 的版次和日期，检查 `dist/{zh,en}/methodology/index.html` 中的修订标签，并扫描 `website/static` 和 `website/dist` 中的私有产品标记。
5. **文案自查**（`grep` 构建输出）：
   - `grep -rl "0.7.0" website/dist`：阶段 0 应该**没有**结果；阶段 1、2 只出现在预期的页面；
   - `grep -rn "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)" website/dist`：每一处所在的页面也要含 “not an exact reproduction of the 2026-07-18 retained trajectory”（中文页含“不是 2026-07-18 保留轨迹的精确复现”）；
   - `grep -rniE "globally optimal|exact reproduction|calibrated to DUKES|与 DUKES 一致|精确复现论文" website/dist`：除固定附注中的 “not an exact reproduction” 外，不应有其他命中；
   - `grep -rn "pending" website/dist/en`：检查 `journey.py:50` 和 `publication.py:30` 的整句替换是否仍然生效，不能残留与 `publication_ready` 状态矛盾的句子。
6. **版本测试**：在仓库根目录、用项目的 Python 3.10 运行 `python -B -m unittest tests.test_documentation_consistency`。`website/content.py`、`value-source-CITATION.cff`、`value-source-metadata.bib` 必须仍含 `0.6.0-alpha.2`。
7. **源码发布清单**：`python -B scripts/refresh_source_release_manifest.py`，然后用 `--check` 确认输出 `stale: false`。任何 `website/` 源文件的修改都会改变 `source-release-manifest.json` 中的 sha256 和字节数。
8. **人工抽查**：在浏览器中打开 `website/dist/en/` 和 `website/dist/zh/` 的首页、`models/value`、`validation`、`releases`、`data`、`docs/value`、`community`、`methodology`、`cite`，切换语言链接，在窄屏（375 px）下看表格能否横向滚动。
9. **上传**：只上传 `website/dist/`。部署保持现有的站点受众（`README.md`：仅所有者可见；开放公众访问是单独的发布步骤）。上传后，抽查线上 `/en/releases/` 和 `/zh/releases/` 的 SHA256 与 `site.json` 是否一致。

---

## 9 顺带发现的网站现存问题（与版本变化无关，可以一并修）

1. **`journey.py:3-6` 的四个任务标签没有中文化**。第 2 列（`'reproduce from existing data'`、`'add your new data'`、`'Edit module'`、`'add new function to VALUE'`）在中文页也原样显示，大小写也不统一。`paths()`（`:9`）和 `pages()`（`:35-36`、`:40`）直接用的是 `label`。建议改成 `(en, zh)` 二元组，例如 Reproduce / 复现、Adapt data / 换数据、Edit a module / 改模块、Add a function / 加功能，再用 `w.t` 取值。
2. **引用页的 source 条目版本不一致**。`content.py:76` 的标题是 “VALUE · source-2026-10-04”，下载链接却指向 `static/assets/value-source-review-CITATION.cff`，而该文件写的是 `version: "source-review-2026-10-03"`。仓库根目录 `CITATION.cff` 是 `source-2026-10-04`。建议在阶段 1 处理 C-14 时一并统一。
3. **`methodology_page.py:23` 的回退日期写死**：“Revised 3 October 2026 · …”，只在 `edition.json` 缺失时出现。不影响现网，但阶段 3 之后会更旧。
4. **`content.py:88` 的 “VALUE software use Apache-2.0”** 靠 `publication.py:30` 的替换改成 “uses”，`content.py:88` 本身可以直接改正。

---

## 附录 A 建议文案

A.1 `models/value` 新增一节 “Two methodology profiles / 两种方法学口径”（C-1，阶段 1）：

| Label（英文照抄） | What it is / 含义 | Boundary / 边界 |
|---|---|---|
| `Corrected methodology (default)` | EN: Current default for new Studies and Runs, with the October 2026 review fixes (market clearing and storage rules, interconnector imports in the day-ahead clearing, literature wind and solar losses, nuclear and hydro availability, storage headroom, network economics). ZH：新 Study 与 Run 的默认口径，包含 2026 年 10 月的审查修复（出清与储能规则、互联线进口进入日前出清、风光文献损耗、核电与水电可用率、储能扩容余量、网络经济口径）。 | EN: A method change; compare it with other profiles as a different method. Wind and solar capacity factors are disclosed next to DUKES, not calibrated to it. ZH：属于方法变化，与其他口径比较时按不同方法对待；风光容量因子与 DUKES 并列披露，不对其标定。 |
| `Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)` — not an exact reproduction of the 2026-07-18 retained trajectory | EN: Keeps the 0.6.0-alpha.2 behaviour, except corrections applied to both profiles: interconnector series on the run clock, three GBP1 reading errors, thermal investment net of running cost, stress-event and accounting corrections. Thesis-lineage modules and data packs only; refuses enabled external code. ZH：保留 0.6.0-alpha.2 的行为；只有两个口径共同的修正例外：互联线序列按运行时钟对齐、GBP1 的三个读取错误、火电投资扣除运行成本、stress event 与核算修正。只运行论文谱系模块和数据包；已启用外部代码时拒绝运行。 | EN: Annual results appear on result pages only when every raw invariant passed; otherwise use Inspect or the export. ZH：原始不变量全部通过时，年度结果才在结果页发布；否则到 Inspect 或导出中查看。 |

A.2 验证页新增五行（C-11，阶段 1）：

- “Doctoral reproduction profile, golden D1–D3” | EN: trajectory columns bit-identical to 0.6.0-alpha.2 (35aadb3) | EN: linux-x86_64, CPython 3.10.18, numpy 1.24.4, exact mode; D4 and D5 re-baselined once each with numeric reports; not the 2026-07-18 retained trajectory. ZH 同义。
- “Corrected default PSM energy identity” | EN: closes per period on VALUE 101 day and two-year smoke cases | EN: ahead-stage shortfalls are reported as stress events, not removed. ZH 同义。
- “Stress events (both profiles)” | EN: per-period shortfall recorded and grouped into events; dispatch and prices unchanged | EN: runs made before 0.7.0 did not record shortfalls. ZH 同义。
- “GBP1 doctoral run, first model year” | EN: before/after comparison of the reading corrections | EN: known issue: surplus conservation fails in 471 periods (max 991 MWh), also before the fixes; annual results withheld; under investigation. ZH 同义。
- “0.7.0-alpha.1 installers” | EN: not yet built | EN: `not_evaluated`. ZH：尚未构建，`not_evaluated`。
- （修复轮）“VALUE four user paths, 0.7.0-alpha.1 source” | EN: reproduce, adapt data, edit a module and add a function passed on the source tree after the October 2026 fix round; no high-severity defect remains | EN: Linux source tree, not an installer; one-day, smoke and two-year scopes; open medium issues in data-pack eligibility display, Europe/London timestamps and extension results of full-year runs. ZH：“VALUE 四类用户路径，0.7.0-alpha.1 源码” | 2026 年 10 月修复轮之后，复现、换数据、改模块、加功能四条路径在源码树上通过，没有剩下高严重度缺陷 | 只在 Linux 源码树上测试，不是安装包；覆盖一日、smoke 和两年范围；数据包资格显示、Europe/London 时间戳和全年 Run 的扩展结果三处仍有中等问题。
- VoLL 不单独成行；若作者希望写，放在 “Corrected default PSM energy identity” 一行的边界列：EN: “Recorded unserved energy is valued at £17,000/MWh in both profiles.” ZH：“两个口径的记录切负荷都按 17,000 £/MWh 计价。”

A.3 四类用户步骤（J-3，阶段 2）：

- 复现：
  1. 获取同一版本的软件与 VALUE 101 输入；
  2. 打开或复制教学 Study，在第 1 步选择方法学口径，然后显式启动 Run；
  3. 与同版本、同口径的参考结果比较；论文复现口径的年度结果若被扣发，在 Inspect 或导出中查看。
- 换数据：
  1. 复制 Study 与数据包；
  2. 映射声明的列、字段名、MW/MWh、时区与采样间隔；可以声明时间戳列（UTC 或 Europe/London），逐行检查；欧元价格要填汇率、汇率口径和价格年份；互联线可用量正值为进口、负值为出口；
  3. 在 Data 页的校验面板查看三层校验（结构、时序、合理性），在 Study 编辑器确认数据包可用于所选口径，再运行独立案例。
- 改模块：
  1. 在修正口径下选择受支持的模块，并保留基线；
  2. 在独立副本中修改，以新身份安装（原地修改已安装模块也可以，结果会记录新的源码哈希）；方法变化须在界面确认 Study 迁移；
  3. 运行相同的短案例并比较结果；停用或隔离的模块在 Modules 页的 Disabled and quarantined 区恢复。
- 加功能：
  1. 定义扩展的输入输出契约；
  2. 通过受支持的接口实现并登记；冲突或损坏的扩展会被隔离，修复后 Rescan；直接调用 API 的脚本要带会话头；
  3. 先在修正口径下用两时段或更长范围运行小型示例（一日课程不运行扩展），再开展长期研究。

（英文版逐条对应，条数与中文相同。）

A.4 FAQ “Open VALUE from its launcher”（J-7，阶段 2）：EN: “The page was opened through another address, an old bookmark or another installation. Close it and start VALUE again with its launcher, then use http://127.0.0.1:8800 or http://localhost:8800.” ZH：“页面不是经启动器打开的（用了其他地址、旧书签或另一份安装）。关闭页面，用启动器重新启动 VALUE，再打开 http://127.0.0.1:8800 或 http://localhost:8800。”

A.5 rc1 安全提示草稿（只有作者选择第 7 节 (a) 时才用）：EN: “Full 2026-10-03-rc1 (VALUE 0.6.0-alpha.2) predates the October 2026 hardening of the local API. Use it only on a single-user computer, stop VALUE with Ctrl+C when you are not using it, and install the next release when it is available.” ZH：“Full 2026-10-03-rc1（VALUE 0.6.0-alpha.2）早于 2026 年 10 月对本地 API 的加固。请只在单人使用的电脑上运行，不用时在启动终端按 Ctrl+C 停止，下一版本可用后请改装新版本。”

A.6 修复轮新增的 FAQ（J-7 (c)(e)(f)，阶段 2；界面字符串在前端翻新后要重新核对）：

- “A module or extension is quarantined (health: degraded).” EN: “VALUE keeps running without it. Open Modules: the Disabled and quarantined area lists it with Enable, Rescan and Remove. Fix the code, then press Rescan (or Rescan modules at the top). Remove moves the installation aside and is refused while a Study or Run uses it. Offline: python -m gridform_core.module_recovery.” ZH：“VALUE 会在没有它的情况下继续运行。打开 Modules 页，Disabled and quarantined 区列出该条目，带 Enable、Rescan、Remove 三个按钮。修好代码后点 Rescan（或页头的 Rescan modules）。Remove 只是把安装移到一旁，Study 或 Run 仍在使用时会被拒绝。离线时用 python -m gridform_core.module_recovery。”
- “Annual results withheld for this reproduction run.” EN: “The doctoral reproduction profile publishes annual results only when every raw invariant passed. The notice names the failed invariant and the declared deviation that explains it, if any. Read the results in Inspect or export the ledger.” ZH：“论文复现口径只有在原始不变量全部通过时才发布年度结果。提示中写明失败的不变量，以及能解释它的已声明偏差（如有）。可以在 Inspect 中查看，或导出账本。”
- “The one-day lesson will not start with my extension.” EN: “The one-day lesson runs the market step only, so extensions would not execute. Choose two-period or a longer scope, or deselect the extension.” ZH：“一日课程只运行市场步骤，扩展不会执行。请改用两时段或更长的范围，或取消选择扩展。”
