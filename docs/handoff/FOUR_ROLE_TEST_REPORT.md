# VALUE 0.7.0-alpha.1 四角色用户验收报告（最终构建）

- 日期：2026-10-07。
- 被测版本：分支 `fix/review-2026-10-04` 的代码状态 `fab9ec2`（`fab9ec286e6f73f26bbb885935695b333a9f4269`），`package.json` 版本 0.7.0-alpha.1。此后的提交只改交付文档，没有改代码。
- 四个角色按首页的四条路径命名：
  1. **复现**：reproduce from existing data；
  2. **换数据**：add your new data；
  3. **改函数**：edit a module；
  4. **加功能**：add new function to VALUE。
- 另做了一次**定点验证**：首个 Run 的异步启动，以及修正口径用本地构建的 R029 public2 数据包跑一整年。
- 测试方式：
  - 每个角色都用 `git archive` 把 `fab9ec2` 导出到 scratch，重新执行 `vinext build`，再用全新的 `VALUE_DATA_HOME` 启动后端和界面网关。
  - 测试员以第一次使用的新用户身份从 Home 出发，用 Playwright（headless chromium 1243）操作界面。只有界面没有入口的边界测试才直接调 API。
  - 每个角色都独立从头测试。
- 本报告只描述这个构建的现状。以前各轮的测试与修复记录见 git 历史和 `docs/dev/p0-reports/`。

**阅读说明**

- 严重度：
  - **高**：结果算错、数据丢失，或主路径走不通；
  - **中**：主路径能走通，但某个功能报错、提示与事实相反，或必须绕行；
  - **低**：文案、显示或一致性问题。
- 编号格式为“角色字母-严重度序号”：R 复现，S 换数据，M 改函数，F 加功能，T 定点验证。例如 S-中2 是换数据角色的第 2 个中等缺陷。
- 复核情况：
  - 撰写本报告时，每项中等缺陷都对照当前代码确认了成因，表中记为“代码确认”。S-中2、S-中3 还在当前代码上用小脚本重现过（见附录 A）。
  - 低等缺陷以测试员的证据为准，其中一部分做了代码核对。
  - 本轮没有高严重度缺陷，所以不需要在 scratch 实例上单独复跑高项。


## 0 总览

### 0.1 各角色结论

| 角色 | 结论 | 已走通的主路径 | 高 | 中 | 低 |
|---|---|---|---:|---:|---:|
| 复现 | 通过但有问题 | Home → VALUE 101 → 一日课 → 修正口径和论文复现口径的两年完整 Run → 比较 → 导出 → 重跑。重跑后结果和六个账本逐字节相同 | 0 | 2 | 10 |
| 换数据 | 通过但有问题 | 复制数据包 → 映射欧元价格（带汇率）和按 MWh/期给出的需求 → 校验 → 建 Study → 一日课和两年 Run → 比较。单位和币种只换算一次，当地时间正确换成 UTC | 0 | 3 | 7 |
| 改函数 | 通过但有问题 | 构建 → 安装 → 派生对照 Study → 一日课和两年 Run → 比较。就地改源、方法升级确认、隔离、停用/启用/移除、离线救援都正常 | 0 | 3 | 5 |
| 加功能 | 通过但有问题 | 编写扩展 → 构建 → 安装 → 在独立 Study 中启用并绑定数据 → 两时段和两年 Run → 与基线对照。命名空间冲突、停用/启用、隔离都正常 | 0 | 4 | 5 |
| 定点验证 | 通过 | 首个 Run 异步启动，冻结输入期间页面仍可操作；修正口径用 R029 public2 跑完一整年，全部校验通过，结果与 golden C10 一致 | 0 | 0 | 1 |
| **合计** | | | **0** | **12** | **28** |

**一句话结论：** 四条用户路径在最终构建上都能从头走通，没有高严重度缺陷，也没有发现算错的结果。12 项中等缺陷都出在显示、提示和工作流上，分为以下几类：

- 两处界面报错或说明写错：规划面板出现 JS 错误；比较页的扣留理由写错。
- 时钟说明与实际处理不符。
- 代码身份变化后，readiness 不出结果。
- 迁移后无法派生对照 Study。
- 扩展的源码改动检测和 Rescan 不完整。
- 其余几处引导问题。

### 0.2 中等缺陷一览

| ID | 现象 | 复核 | 建议修复（要点） |
|---|---|---|---|
| R-中1 | Runs 年度卡片中展开 Planning pipeline，显示 JS 错误 `Cannot read properties of undefined (reading 'find')` | 代码确认 | 当 `summary.json` 没有 `years` 字段时，接口返回按年的索引摘要；前端遇到缺字段时给出说明，不再抛错 |
| R-中2 | 比较修正口径和论文复现口径的 Run 时，扣留理由被写成“48 时段教学课”，导出的 CSV 只有表头 | 代码确认 | 后端区分扣留原因（教学课 / Q14），前端按原因显示；CSV 和 JSON 都写明原因 |
| S-中1 | 市场回放把 UTC 时钟标成 “Europe/London model time”，夏令时期间看起来整体早 1 小时 | 代码确认 | 账本元数据和界面标签都改为 UTC，或换算成伦敦当地时间显示并加注明 |
| S-中2 | 逐时数据和闰年数据的审阅警告写成“循环重复”，实际处理是“每小时复制成两个半小时”或“删去 2 月 29 日” | 代码确认 + 脚本重现 | 按读取器的实际处理生成说明 |
| S-中3 | 日/月/年格式的日期被按月/日解析，报出 154 条 “gap of 43230 minutes” | 脚本重现 | 提供日期顺序选项，或在缺口长度接近整月时提示“可能是日月顺序” |
| M-中1 | storage_cost 槽位的调用证据总显示“未调用”，但模块实际已经生效 | 代码确认 | PSM 内部调用存储成本模块时写入调用证据，或界面对这类槽位改用账本证据 |
| M-中2 | 内置模块做代码级升级后，Check readiness 一直不出结果（与 F-中1 同一根因） | 代码确认 | 预检报告用“已保存修订”的哈希做身份匹配，计算出的新哈希另列一项 |
| M-中3 | 方法升级迁移或就地改源后，无法从该 Study 派生对照 Study，提示的修复办法也无效 | 代码确认 | 追加迁移修订时刷新 `module_resolution_graph`；派生时如果只是代码级差异，先走迁移而不是直接拒绝 |
| F-中1 | 原地修改扩展源码后，Check readiness 一直不出结果（与 M-中2 同一根因） | 代码确认 | 同 M-中2 |
| F-中2 | 扩展源码的行为改动被提示为“只改了代码身份，结果不会变” | 代码确认 | 把已安装的扩展纳入源码变更检测，提示方式与模块一致 |
| F-中3 | Rescan 不重新导入扩展钩子，坏掉的扩展不会被隔离 | 代码确认 | Rescan 时导入每个已启用扩展的钩子，导入失败即隔离 |
| F-中4 | 加功能路径打开的独立 Study 草稿不继承当前选中的基线 Study | 代码确认 | 草稿复制选中 Study 的配置，或在 Studies 卡片上提供“复制 Study” |

低等缺陷分别列在各角色一节。跨角色的共性问题和建议的修复顺序见第 7 节。


## 1 测试方法与共同条件

| 角色 | 端口（API / UI） | 数据 | 驱动方式 |
|---|---|---|---|
| 复现 | 18880 / 18881 | VALUE 101 教学包 | Playwright 操作界面。API 只用来读状态和核对账本 |
| 换数据 | 18882 / 18883 | VALUE 101 教学包，加角色自己构造的测试 CSV | Playwright 操作界面；边界用例用带会话令牌的 API 调用 |
| 改函数 | 18884 / 18885 | VALUE 101 教学包 | Playwright 操作界面；API 只用于读运行记录和做负向测试 |
| 加功能 | 18886 / 18887 | VALUE 101 教学包 | Playwright 操作界面；界面没有入口的操作才调 API |
| 定点验证 | 18870 / 18871 | VALUE 101 教学包；R029 public2（由 R029 public1 在本地重建） | Playwright 和 curl |

共同条件：

1. **起点**：全新的数据目录里只有一个空的 UK 包。Learn 页提示 “VALUE 101 cannot start yet”，并给出命令 `scripts/install_synthetic_pack.py --value-101-only`。各角色照提示装好教学包后开始测试。桌面安装器要求空的安装前缀和完整的发行包，所以没有走桌面安装器。
2. **运行规模**：
   - 一日课：48 时段；
   - 两时段接线检查；
   - 两个完整模型年：35,040 时段；
   - 定点验证另跑了 R029 public2 的一整年：17,520 时段。
3. **进程与端口**：各角色只按自己记录的 PID 停止进程，没有连接 8766/8800 端口，也没有向作者的进程发信号。


## 2 复现角色（reproduce from existing data）

### 2.1 结论

**通过但有问题。** 新用户从 Home 出发，能在 VALUE 101 上用修正口径和论文复现口径走完“运行 → 看结果 → 比较 → 导出 → 重跑”。重跑结果逐字节一致。没有高严重度缺陷；有 2 项中等、10 项低等缺陷。

### 2.2 已验证可用（附证据）

1. **首次使用引导**：新数据目录中，Learn 页给出安装教学包的命令。执行后点 Check again，教学包变为就绪。
2. **创建 Study 与一日课**：
   - Create baseline Study 得到 revision 1。
   - 点击 Run one market day 后约 1.5 秒返回，Run 是异步启动的。
   - 进度显示 “Preparing · step 1 of 4”，并说明首次需要归档运行时，约 3 分钟。
   - Run 全程约 3.5 分钟完成。Execution 和 Contract 均为 passed，Energy balance 为 Passed，Stress 为 None。
3. **修正口径的两年完整 Run（9749a2a3）**：
   - 从 Learn 页启动后约 3 秒返回，模型本身约 2 分钟跑完。
   - 结果已发布（published）。scientific、energy balance、storage、run invariants 全部 passed，stress 为 0。
   - 2025 年系统成本 £14.70m（£62.85/MWh served），2026 年 £14.425m，未满足需求为 0。这两个数与模型改动简报中 VALUE 101 修正口径算例 C6 的分年头条一致（£14,699,553 / £14,424,989）。
   - 这个 Run 在后台运行期间，测试员用 Research guide 建了复现 Study，又用 composer 建了论文复现 Study。两个 Run 可以同时运行，互不阻塞。
4. **论文复现口径**：
   - Composer 里可以选 Doctoral reproduction。不支持的数据包被禁用，并写明原因。
   - Run 完成后（ab225ce5）：
     - Scientific validation 显示 “Declared deviations”。
     - Raw invariants 显示 “1 failed”，即 Storage single direction 9,343 行，对应已声明的偏差 DEV-STO-01。
     - 运行记录显示：run invariants 4/4 passed；能量平衡为 `reproduction_conformant`，最大闭合残差 3.6e-15 MWh；储能不变量为 `reproduction_with_declared_deviations`。
   - 年度结果按 Q14 扣留，提示原因准确。Inspect 的 Planning、Market 页，Market replay，76 个产物和各账本都能打开或下载。
   - 账本中 2025 年 CEM 系统成本为 £14,560,893，与简报中算例 D4 的 2025 年值一致。
5. **重跑一致性**（运行身份完全相同）：
   - 修正口径：重跑 d3c1b6ae 与原 Run 9749a2a3 相比，results、input_tree、execution_identity 都相同。以下六个文件逐字节相同：cost 账本、carbon 账本、terminal-state、energy-balance-oracle、run-invariants、fleet-vintage。
   - 论文复现口径：重跑 02113b2f 与 ab225ce5 相比，同样全部相同。
   - 通过 Research guide 新建的复现 Study（902f0b8f）：结果和账本与基线相同。
   - 严格核对冻结输入后重放论文复现 Run（在 recovered Study 中，920d9575）：results 和六个账本都与原 Run 相同。
6. **比较**：基线与重跑比较时，身份核对的 5 项都是 Same，所有差值都是 +0。Export CSV 有 36 行数据，Export JSON 正常。
7. **导出**：
   - Market replay 按年导出 2025 年的 CSV，共 17,520 行，与年度指标一致：需求 233,870.274 MWh，弃电 4,002.893 MWh，充电 2,310.578 MWh，最大平衡残差 3.6e-15。
   - Prepare audit bundle 生成 13.2 MB 的 zip，含 45 个文件，`testzip` 检查通过。
8. **VRE 页**：未用的 VRE 比例为 2025 年 3.1%、2026 年 14.6%。

### 2.3 现存缺陷

#### R-中1 Run 结果中的 “Planning pipeline” 展开后显示 JS 错误

- **复现**：修正口径两年 Run（9749a2a3）→ Runs → 任一年度卡片 → 展开 Planning pipeline。
- **现象**：界面显示 “Cannot read properties of undefined (reading 'find')”，规划摘要无法查看。
- **成因（代码确认）**：
  - `app/features/runs/RunResults.tsx` 第 62–65 行的 `PlanningPipelinePanel` 读取 `payload.years.find(...)`。
  - `/api/runs/{id}/planning/summary`（`backend/server.py` 第 2541–2549 行）原样返回 `model-output/planning/summary.json`。
  - 这个文件由 `materialize_planning_index` 写出（`gridform_core/application.py` 第 2116–2127 行），格式是 `value.planning-project-index/v2`，只有 `project_year_rows`、`event_rows`、`expected_capacity` 等字段，没有 `years`。
  - 能给出 `years` 的 `query_index_summary`（`gridform_core/planning_index.py` 第 103 行）只在 `summary.json` 不存在时才作为回退使用。
- **建议修复**：
  - 当 `summary.json` 没有 `years` 字段时，接口改用 `query_index_summary(project-index.sqlite)`，或者把按年摘要单独写成一个文件。
  - 前端在 `years` 缺失时显示 “Planning evidence is not recorded for this year”，不要抛错。
  - 给界面契约测试补一个 v2 格式的样例。

#### R-中2 比较修正口径与论文复现口径时，扣留理由写错，导出为空

- **复现**：在比较页同时勾选 9749a2a3（修正口径）和 ab225ce5（论文复现口径）。
- **现象**：
  - 界面给出 “Teaching boundary: … withheld because these runs contain one 48-period market day”。可这两个 Run 都是完整的两年 Run，与 48 时段的一日课无关。
  - Export CSV 只有表头，没有数据行，也没有说明原因。连修正口径本来已经发布的年度值也不出现。
  - JSON 中 `annual_comparison` 为空，`comparison_scope` 却是 `annual_scientific`。
- **成因（代码确认）**：
  - `gridform_core/results_summary.py` 第 539–545 行：只要有一个 Run 按 Q14 扣留，`annual_metrics_withheld` 就为真，于是 `annual_comparison` 为空（第 669 行），各 Run 的 `annual` 也被清空（第 702–704 行）。
  - `app/features/results/ComparisonWorkspace.tsx` 第 113 行只要看到这个标志，就一律显示教学课的文案。
- **建议修复**：
  - 后端返回扣留原因：教学课、Q14 扣留，或两者兼有。前端按原因显示文案，例如 “ab225ce5 是论文复现 Run，其年度结果按 Q14 扣留（原始不变量 storage.single_direction 失败），见 Inspect”。
  - CSV 和 JSON 写入扣留原因。
  - 可以考虑并排显示已发布 Run 自己的年度值，只是不给差值。
  - 年度比较整体被扣留时，`comparison_scope` 不应再写 `annual_scientific`。

#### 低等缺陷

| ID | 现象与复现 | 建议修复 |
|---|---|---|
| R-低1 | Inspect 的规划表标题写 “8 durable project records”，但同一个 project_id 出现两次，一次是 commissioned，一次是 active。表格没有年份列，API 返回的行也没有年份字段（`planning_index.py` 中 `query_index_projects` 不返回 `year`）。这些记录实际是“项目×年份”，用户会以为结果自相矛盾 | API 返回 `year`，表格加年份列，标题改为“项目×年份记录”；或者默认只显示最新年份 |
| R-低2 | Run 处于 queued/running 时，显示通用提示 “Biomass without support revenue”，文中用的是 GBP1/R029 的数字，而 VALUE 101 根本没有生物质。Run 完成后提示条数会变：修正口径从 1 条变为 0 条，论文复现口径从 2 条变为 10 条 | Run 完成前不显示按资产筛选的提示，或注明“完成后按本次资产筛选” |
| R-低3 | 提示 “The complete two-year model has started.” 在切到 Studies 页、或切到另一个 Study 的 Runs 页后仍然显示 | 把提示绑定到发起它的 Study 和页面，切换时清除 |
| R-低4 | 按钮 “Export ledger” 只是跳到 Inspect 的产物列表，并不下载文件（`RunWorkspace.tsx` 把它接到 `openInspect("artifacts")`） | 改名为 “Open ledger files”，或者直接打包下载账本 |
| R-低5 | 界面直接显示原始字段名，例如 “Failed: not_applicable”、“Scientific scenario: Reproduction_with_declared_deviations”，比较表中的 “Cem System Cost Gbp Per Mwh Served”、“Total Carbon Emissions Tco2e”、“Redispatch Net Impact Mwh”。阶段名同时有 “application_submitted” 和 “Application Submitted” 两种写法 | 建一张统一的标签表，界面上的指标名、状态名和阶段名都从这张表取 |
| R-低6 | 做完严格重放后，顶部 “Draft data pack” 默认选中了 “Recovered BASE inputs from doctoral-101-…” | 恢复出来的包不作为默认值，保持用户原来的选择 |
| R-低7 | Composer 第 2 步选论文复现口径时，“Fixed zonal network and redispatch” 显示 ready 标签，下面同时写着 “not a thesis-lineage module…”（测试员没有试它能否被选中） | 口径不支持的模块显示为不可用并禁用，与数据包的禁用方式保持一致 |
| R-低8 | 数据和时段数都相同，readiness 估算的运行时间却是修正口径 0.3 小时、论文复现口径 <0.1 小时，实际两者都约 2 分钟 | 按口径校准估算，或者只给一个范围 |
| R-低9 | replay CSV 中 `physical_resource_cost` 合计 £7,304,311.46，年度运营成本为 £7,304,116.11，相差 £195（约 0.003%），界面没有说明差额来源 | 查明差额来自口径差异还是舍入，并在导出说明中写明 |
| R-低10 | 论文复现 Run 打开 VRE 页时，被扣留的 `vre-summary` 请求返回预期的 409，但浏览器控制台把它记成 error | 对已扣留的 Run 不发这个请求，或者返回 200 并带 withheld 状态 |

### 2.4 需要作者知道的情况（不算缺陷）

1. 在 VALUE 101 上，论文复现口径的 `storage.single_direction` 每次都失败（DEV-STO-01：同一储能可在同一时段既充又放）。因此论文复现口径的年度结果永远不会出现在结果页和比较里，只能在 Inspect 和导出中查看。这符合 Q14 的设计。
2. 论文复现口径的账本中，2025 年 `gross_generation_mwh` 为 222,273 MWh，低于需求 233,870 MWh；同时 imports 为 0，excess 为 7,661 MWh。可能的解释如下：
   - 论文复现口径 PSM 统计发电量时不计电池放电（`gridform_core/builtin/scheme_c_1000twh/scheme_c_native_psm.py` 第 805–814 行；代码注释说明放电是单独守恒的流量）。所以这个数不能直接与需求相比。
   - 独立的能量平衡检查在声明的边界上闭合：结果为 `reproduction_conformant`，最大闭合残差 3.6e-15 MWh，stress 事件为 0。
   - 但本轮没有把这三个数逐项对平。


## 3 换数据角色（add your new data）

### 3.1 结论

**通过但有问题。** 整条换数据路径都能走通，数值核对正确。没有会算错结果的缺陷。有 3 项中等、7 项低等缺陷，主要是时钟和日期的说明与实际处理不一致，以及报错信息不清楚。

### 3.2 已验证可用（附证据）

1. **准备独立数据包**：
   - 在 Research guide 第 2 步复制 BASE 包，得到 `my-eur-price-data-16267dd658e0`。
   - 直接对原始包做映射会被拒绝，错误码 `GF_MAPPING_BASE_COPY_ONLY`，符合设计。
2. **CSV 映射编辑器：欧元价格加汇率**：
   - 测试文件 `fr_price_eur_local.csv`：17,520 行，Europe/London 当地时间，包含夏令时缺口和重复的一小时。价格为 70 / 150 EUR，按 1.17 EUR/GBP 换算。
   - 币种选 GBP 时，因为列名含 EUR，界面提示 “Column name suggests EUR”。
   - 选 EUR 后，汇率、汇率口径、价格年份三项必填，缺任何一项预览按钮都不可用。汇率超过 4 位小数会报错。
   - 审阅报告并排显示原值和换算值（70.0 → 59.8290598290598），并注明 “converted at 1.17 EUR/GBP (annual average, 2025)”。
   - 时间戳检查结果为 “17520 rows … no problems”，首尾时间为 2025-01-01T00:00Z 和 2025-12-31T23:30Z。
   - 不勾选确认框时提交按钮不可用；修改汇率后原审阅作废，提交按钮消失。
   - 提交后的 manifest 记录了：`source_currency EUR`、`eur_per_gbp 1.17`、`fx_basis`、`price_year`、`timestamp_check passed 17520`，以及三组 SHA 的来源。
   - 规范化后的文件中，150 EUR 变成 128.205 GBP，共 2,190 行（每天当地 17:00–20:00 共 6 个半小时 × 365 天）。7 月 1 日当地 17:00 的高价落在 UTC 16:00 那一期（第 8,720 期），说明当地时间正确换成了 UTC。
3. **单位换算**：
   - `demand.real` 按 MWh/period 导入，带 UTC 时间戳，数值是原需求的 0.55 倍。换算成 MW 后正好是原需求的 1.1 倍（30.42397）。
   - 一日课当天的需求为 853.04 MWh，等于 775.49 × 1.1。
4. **能拦住的错误输入**：
   - 时间戳缺口和重复会逐行列出。
   - 把当地时间当作 UTC 解读时，报出 3 个问题，分别在第 4228、14308、14309 行。
   - 非数字单元格会指出 “Row 51 (CSV line 52)”。
   - 空单元格、千分位、重复表头、非 CSV 文件、超过 32 MiB 的文件都会被拦住。
   - 汇率为 0、未提供汇率、给 GBP 列提供汇率、需求列使用 EUR 单位，都会被拒绝（`GF_MAPPING_FX` / `GF_MAPPING_UNITS`）。
   - 包版本已过期时拒绝，错误码 `GF_MAPPING_STALE_TARGET`。
   - 已被 Study 引用的包不能再写：API 返回 409 `GF_DATA_PACK_REFERENCED`，界面变为只读，并提示“请再次复制”。
   - 序列起点不是 1 月 1 日时，给出 `GF_DATA_TIMESTAMP_ORIGIN` 警告。
5. **校验面板**：
   - 映射后结构警告从 14 条降到 12 条，`demand.real` 和 `france.price` 两条消失。
   - 时序检查和合理性检查都通过。
   - 修正方法论可用；论文复现方法论不可用，理由是 “not a thesis-era pack”。
6. **创建 Study、检查、运行**：
   - 换数据 Study 为 `eur-france-price-demand-10pct-f3eeafeac7`。
   - 一日课（48 时段）约 65 秒完成，执行和契约检查均为 passed，能量平衡通过，没有 stress 事件。
   - 市场回放中 Interconnect_France 的报价为 £59.83/MWh，即 70/1.17，只换算了一次。
   - 基线和换数据各跑一次两个完整模型年（35,040 时段），两者可以同时运行，约 3 分钟完成，科学校验通过。
7. **比较**：
   - 一日课对比只显示身份差异，并正确标出改动在 `pack.roles.demand.real` 和 `pack.roles.market.france.price`。
   - 年度对比中只有数据输入一项不同。2025 年系统成本 +£1.00m（+6.82%），每 MWh 服务成本 −2.89%，碳排放 −29.1%。服务电量之比为 1.0999，与需求 +10% 吻合。碳排放下降的方向合理：法国非高峰时段电价便宜，进口替代了 CCGT。
   - 三项依赖 VRE 弃电证据的指标按设计不给差值，并逐项说明原因。导出的 CSV 内容完整。

### 3.3 现存缺陷

#### S-中1 市场回放把时间标成 “Europe/London model time”，但模型时钟是 UTC

- **复现**：
  1. 按当地时间导入法国价格，当地 17:00–20:00 为 150 EUR。
  2. 跑两年，查看 2025 年第 8,712–8,735 期（7 月 1 日）的半小时调度。
  3. 进口为 0 的时段显示为 16:00–18:30，进口在 19:00 恢复，比用户导入数据时用的当地时间整体早 1 小时；而标签声称这是伦敦当地时间。
- **影响**：夏令时期间，用户拿自己导入的数据核对时，会看到整体偏移 1 小时。计算本身没有错：映射编辑器已把当地时间按行对齐到 UTC。
- **成因（代码确认）**：
  - 模型的时段时钟是 UTC：VALUE 101 本来就用 UTC；GBP1 需求按 `p05.demand-utc-clock` 放到 UTC 时钟；ERA5 天气也是 UTC。
  - 但 PSM 写入账本的语义元数据是 `timezone: Europe/London`、`calendar: fixed_365_day_local_periods`（`scheme_c_native_psm.py` 第 664–665 行，`perfect_foresight_psm.py` 第 471–472 行）。
  - 回放的时间戳按 “1 月 1 日 + 期数 × 0.5 小时” 计算（`market_replay.py` 第 596–597 行），界面再加上 “(Europe/London model time)”（`app/page.tsx` 第 195 行）。
- **建议修复**：
  - 把元数据改为 UTC，界面标签改成 “UTC model time”。
  - 如果要显示伦敦当地时间，就在显示层按夏令时换算，并注明换算方式。
  - 改元数据前，先核对 golden 摘要是否包含这些字段。

#### S-中2 逐时数据和闰年数据的提示写成“循环重复”，与实际处理不符

- **复现**：
  - 给价格类角色导入 8,760 行逐时数据（带时间戳）。时间戳检查接受 60 分钟步长，结果为 “no problems”，但审阅报告的警告写的是 “the VALUE interconnector adapter repeats it cyclically”。
  - 导入 17,568 行（2024 闰年）数据，同样出现这句警告。
- **实际处理**（脚本重现，附录 A.1）：修正口径的读取器 `align_clock`（`gridform_core/series_reader.py` 第 411 行起）对这两种情况的处理如下：
  - 8,760 行：每个小时复制成两个半小时；
  - 17,568 行：删去 2 月 29 日；
  - 只有不足一年的序列才会循环补齐。
- **成因（代码确认）**：`gridform_core/data_pack_validation.py` 第 362–369 行对 `CYCLIC_MARKET_ROLES` 只要行数不等于 17,520，就一律写 “repeats it cyclically”。
- **影响**：用户在确认提交前读到的时钟说明是错的。
- **建议修复**：按读取器的实际分支生成说明：
  - 逐时数据：“每小时用于两个半小时时段”；
  - 闰年数据：“删去 2 月 29 日”；
  - 不足一年：“循环补齐，最后 N 期取自开头”；
  - 超过一年：“只取前 17,520 期”。
  映射编辑器的审阅报告使用同一套文字。

#### S-中3 日/月/年格式（英国常用）被按月/日解析，报错误导

- **复现**：导入时间戳格式为 `02/01/2025 00:00` 的文件。`02/01/2025` 被读成 2 月 1 日，于是报出 154 条 “gap of 43230 minutes after the previous row”（脚本重现，附录 A.2）。
- **成因（代码确认）**：`gridform_core/data_validation_layers.py` 第 412–422 行用 `pd.to_datetime(..., format="mixed")` 解析时间戳，没有日期顺序参数。界面也没有日期格式选项，没有“可能是日月顺序”之类的提示。
- **影响**：文件会被拦住，不会导致结果算错，但用户很难看懂原因。
- **建议修复**：
  - 映射编辑器增加日期顺序选项（日/月/年、月/日/年、ISO）。
  - 自动检测：如果任何一行的第一个字段大于 12，就按日/月/年解析。
  - 当大量缺口长度接近整月时，提示“可能是日月顺序”。

#### 低等缺陷

| ID | 现象与复现 | 建议修复 |
|---|---|---|
| S-低1 | 分号分隔、小数用逗号的 CSV（欧洲常见格式）提交时报 “CSV row 2 does not match the header width”。如果只是分号分隔、小数用点，整行表头会被当成一列 | 自动检测分隔符；不支持时明确说明“看起来是分号分隔，请另存为逗号分隔” |
| S-低2 | 数据不满一年时（17,000 行，时间戳到 12-21），时间戳报告仍是 “no problems”，只有一句泛泛的“循环重复”警告，可以照常提交。结果是最后 520 期（约 10.8 天）用 1 月 1 日起的数据补上。另外，2023 年的数据用于 2025 年的模型，也没有任何提示 | 时间戳检查报告覆盖范围不足，并要求用户确认；数据年份与模型年份不一致时给出提示 |
| S-低3 | 同一个审阅面板里 “Row” 的含义不一致：时间戳表格中是文件行号（表头算第 1 行），单元格错误 “Row 51 (CSV line 52)” 中是数据行号 | 统一用文件行号，或者两处都同时写出两种行号 |
| S-低4 | 时间戳校验失败时，面板标题是“校验未通过”，而同一面板里的“完整文件校验报告”显示 `"status": "passed"` | 把时间戳结果并入完整报告，或注明完整报告只覆盖数值单元格 |
| S-低5 | 提交后在界面上看不到汇率信息：角色卡片显示了 SHA 和时间戳声明，但没有汇率、汇率口径和价格年份。包被 Study 引用后，角色下拉框整体被禁用，无法再查看各角色当时是怎么导入的 | 角色卡片显示这三项汇率信息；只读状态下仍然允许浏览各角色 |
| S-低6 | `price_year` 只做记录，不按年份折算价格，也不提示它与模型的不变价基准年不同（填 2015 也能直接通过）。后端接受任意 `fx_basis` 字符串，界面只给三个选项，但 API 不检查 | 后端按界面的三个枚举值校验 `fx_basis`；`price_year` 与基准年不同时给出提示 |
| S-低7 | 文案问题：(a) 换数据的比较说明写着 “not a controlled storage-cost experiment”，与本次改的是数据无关；`results_summary.py` 第 727 行对任何单维变化都这样写。(b) 同一缺项，Runs 页写 “Unavailable”，比较区写 “Not evaluated”。(c) 规划表和指标名的问题同 R-低1、R-低5 | (a) 按变化维度生成说明；(b) 统一用一个词；(c) 见 R-低1、R-低5 |


## 4 改函数角色（edit a module）

### 4.1 结论

**通过但有问题。** 改函数这条路径可以从头走通：构建并安装改过的模块、派生对照 Study、运行、比较，以及方法变更确认、隔离、停用、重新启用、移除和离线救援都正常。没有高严重度缺陷；有 3 项中等、5 项低等缺陷。

测试用的模块：

- `hx-flat-storage-offer-73`：以示例模块为底，报价从 42 改为 73，版本 1.1.0；
- `hx-template-test`：用源码模板生成，报价 £55。

### 4.2 已验证可用（附证据）

1. **构建与安装**：
   - 同一模块连续构建两次，ZIP 字节完全相同（sha256 `607443c0…`）。
   - 不勾选执行代码信任时，安装按钮不可用；勾选后安装成功，横幅提示 “passed structural conformance”。
   - 下表四类错误包都被拒绝，并注明 “No built-in or previously enabled module was changed”：

     | 错误情况 | 拒绝代码 |
     |---|---|
     | 使用 `gridform.*` 合同 ID | `GF_MODULE_RESOLUTION` |
     | 与内置模块同 ID | `GF_MODULE_BUILTIN_COLLISION` |
     | 与已装模块同顶层包名 | `GF_MODULE_PACKAGE_COLLISION` |
     | 重复安装同一 ID | `GF_MODULE_ID_COLLISION` |

   - 有 Run 尚未结束时安装，会弹出确认框；选取消则返回 409，什么都不改。
   - “Download editable source template” 下载的模板项目能直接构建和安装。
2. **派生、运行、比较**：
   - 派生对照 Study 前必须勾选 “experimental” 确认，否则不能保存；勾选后创建成功，并跳到 Runs 页。
   - 一日课和两年完整 Run 都完成：
     - 冻结的模块身份为 `hx-flat-storage-offer-73 1.1.0`，source sha 为 `e19dc34e…`；
     - `storage_orders` 中的储能报价全部为 73，基线为 18.52。
   - 两年比较：
     - 只把 storage cost 识别为变化维度；
     - 成本和碳排放各自给出差值：2025 年 CEM 系统成本 +£89,985（+0.61%），碳排放 +738 tCO2e；
     - 只扣发 3 个依赖弃电证据的指标，并逐条说明原因（按指标分别门控，DECISIONS A23）。
   - 一日课比较时，年度差值被扣发，并给出说明。
3. **就地修改已安装模块的源码（A16-4：接受并记录）**：
   - 把源码中的报价改为 60 后点 Rescan：模块没有被隔离，卡片显示 `Source changed since install (e19dc34e… → 87603a82…)`。
   - Check readiness 显示琥珀色警告。
   - 新 Run 冻结了新的源码哈希，报价确实变成 60。
   - 比较页标出变化在 `modules.storage_cost.source_sha256`。
4. **内置模块的方法升级**（手册 §12.1，在测试员自己的源码副本上操作）：
   - 把 2.0.0 升到 2.1.0，并在版本台账中设 `requires_user_opt_in: true`。
   - Check readiness 先弹出 “This Study needs your confirmation before it runs”，列出 `2.0.0 → 2.1.0` 和 correction id。选 Cancel，Study 不变；选确认，保存为 revision 2，原因记为 `method-upgrade-confirmed`。
   - runtime overlay 未封存时，readiness 报 `GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED` 并阻止运行；封存后可以运行。
   - 比较页显示 `dynamic-annual-storage-cost 2.0.0 → 2.1.0`。
5. **隔离**：
   - 让模块在导入时 `raise`，再点 Rescan：模块立即被隔离，`/api/health` 变为 degraded（`GF_MODULE_IMPORT_FAILED`）。
   - 只有选用该模块的 Study 被拒，另外两个 Study 的 preflight 仍为 accepted。
   - 修好源码后，在该条目上点 Rescan 即恢复，health 回到 ok。
   - 同一 ID 出现两份清单时，两份都被隔离（`GF_MODULE_ID_DUPLICATE`）；删掉多余的一份再 Rescan 后恢复。
   - 带着坏模块重启后端，后端照常启动，只是状态为 degraded。
6. **停用、启用、移除**：
   - 被 Study 引用的模块：Disable 按钮不可用，API 返回 `GF_MODULE_IN_USE`；Remove 返回 `GF_MODULE_REMOVE_ENABLED`。
   - 未被引用的模块：
     - 停用后从注册表消失，出现在 “Disabled and quarantined” 区，带 Enable、Rescan、Remove 三个按钮。
     - 源码里写了导入时 `SystemExit` 再点 Enable：返回 409，错误显示在该行；模块目录结构不变，清单文件与之前逐字节一致，后端没有退出。修好后 Enable 成功。
     - Remove 前有确认框，文件被移到 `disabled-manifests/removed/…` 而不是删除；之后可以用同一 ID 重新安装。
   - 把 Study 移到回收站后，可以停用它用的模块；从回收站恢复后，readiness 报 `GF_PREFLIGHT_MODULE_DISABLED`。
7. **离线救援（`module_recovery`）**：
   - VALUE 运行中执行 `disable` 会被拒，并提示先停 VALUE。
   - 停掉后端后，`disable module` 成功；`verify` 显示 quarantined 为 0；再启动后 health 为 ok；`list` 也正常。

### 4.3 现存缺陷

#### M-中1 storage_cost 槽位的调用证据总是显示“未调用”，实际模块已经生效

- **复现**：
  1. 选用外部 storage_cost 模块的 Study 跑一日课，Runs 页的模块证据显示 `storage cost / hx-flat-storage-offer-73 / Not called in this scope`。
  2. 跑两时段接线检查时显示 `No calls recorded`。
- **实际情况**：一日课 `market.sqlite` 的 `storage_orders` 中报价全部是 73；接线检查的 `year-results-v2.json` 中有 `fixed_offer_gbp_per_mwh: 55.0`。
- **成因（代码确认）**：
  - 调用证据只统计 `orchestrator-events.jsonl` 中带 `module_id` 的事件（`backend/server.py` 第 1730–1758 行）。
  - storage cost 由 PSM 在内部调用，不产生这类事件。
  - `app/features/runs/runHistoryView.ts` 第 73–78 行的 `moduleEvidenceText` 在没有计数时，显示 “Not called in this scope” 或 “No calls recorded”。
- **影响**：模块开发者手册正是以 storage_cost 作为示例槽位，开发者会被告知“你的模块没被调用”。
- **建议修复**：
  - PSM 每年调用存储成本模块时，写一条带 `module_id` 的证据事件；
  - 或者界面对由 PSM 内部调用的槽位改用账本证据，例如 “N storage offers priced by this module”。

#### M-中2 内置模块做代码级升级后，Check readiness 一直不出结果

- **复现**：
  1. 给内置模块做一次 `requires_user_opt_in: false` 的版本升级，封存 overlay 后重启后端。
  2. 对选用该模块的已保存 Study 点 Check readiness。
  3. 页面只显示 “Preflight identity changed. Refresh the saved Study and check it again.”，没有 readiness 结果。刷新页面后重试，结果一样。
- **后端实际返回**：200，`accepted: true`，并带 `GF_PREFLIGHT_REVISION_REIDENTIFY` 警告，说明 Run 开始时会自动追加修订。
- **成因（代码确认）**：
  - 遇到代码级身份变化时，`gridform_core/preflight.py` 第 592–616 行把新计算出的哈希作为报告的 `project_revision_sha256`（第 885 行）。
  - `app/features/workspace/preflightIdentity.ts` 第 20 行的 `preflightMatches` 拿这个值去比 Study 已保存的哈希，两者在这种情况下必然不同。
  - `app/page.tsx` 第 1336 行于是抛错。
  - 方法升级那条路径用的是 `declared_sha256`（第 1331 行），所以不受影响。`environment_reidentify` 也会走到这条出错的路径。
- **现状与绕行**：可以不做检查直接点 Run，后端会自动追加 revision 3（`code-identity-upgrade`）。但在这种情况下 readiness 这一道检查用不了，提示里让用户去 “Refresh” 也没有用。
- **建议修复**：
  - 预检报告中，`project_revision_sha256` 填所评估的已保存修订，计算出的新哈希另列一个字段；
  - 或者前端在 `checks.project_revision.classification.automatic` 为真、且 `declared_sha256` 等于已保存哈希时接受报告，并把 REIDENTIFY 显示为“开始运行时会自动追加修订”。
  - 这样修好后，F-中1 也随之解决。

#### M-中3 迁移或就地改源之后，无法再从该 Study 派生方法对照 Study，提示的修复办法也无效

- **复现 a**：
  - 基线 Study 先后经过方法升级确认（revision 2）和自动的代码身份迁移（revision 3）。
  - 之后在 Modules 页点 “Create Study with this module”，返回 409 `GF_STUDY_DERIVATION_METHOD_DRIFT`，提示 “review and save a new revision first”。
  - 检查发现：两个迁移修订的 `fingerprint_basis` 已记为 2.1.0 和 2.1.1，但 `module_resolution_graph` 仍是 2.0.0。
- **复现 b**：对已安装的外部模块按 A16-4 就地改源，再以使用它的 Study 为来源派生，报同样的 409。唯一的差异是 graph 中该模块的 `source_sha256`。
- **提示的办法无效**：按提示走 “Edit as new revision → Save this exact Study revision”，返回 201 并显示 “Project saved and contracts validated”，但修订号不变、graph 不刷新，再次派生仍然 409。
- **成因（代码确认）**：
  - `backend/study_derivation.py` 第 227–243 行把已保存的 `module_resolution_graph` 与当前注册表解析出的 graph 逐字段比较。
  - 自动迁移会把 Study 原样复制后保存（`gridform_core/revision_migration.py` 第 646 行；`project_revision.py` 第 175–180 行的 `attach_revision_identity` 只重算哈希），旧 graph 因此原样保留。
  - 对没有选扩展的 Study，graph 不参与修订哈希；“原样保存”时哈希不变，`save_project_revision` 直接返回旧记录（第 287–288 行），graph 也就不会刷新。
- **现有绕行办法**：把源码还原后可以派生（已验证）；或者在 Studies 编辑器里从头新建一个 Study。
- **建议修复**：
  - 追加迁移修订（包括自动迁移和用户确认的迁移）时，按当前注册表重新解析并写入 `module_resolution_graph`。
  - 原样保存时，如果 graph 已过期，也要刷新。
  - 派生时，如果差异只是代码级的，先执行迁移，不要直接拒绝；如果仍要拒绝，提示里给出确实有效的办法。

#### 低等缺陷

| ID | 现象与复现 | 建议修复 |
|---|---|---|
| M-低1 | correction id 不做存在性校验：在版本台账里写一个 corrections 目录中不存在的 id（`x0.uat-edit-module-optin`），`check_version_ledger.py` 显示 passed，`seal_runtime_overlay.py --correction` 也照样接受（前者只检查列表非空，后者只检查格式）。这个 id 会原样出现在用户看到的确认框里，拼写错误发现不了 | 两个脚本都与方法学 corrections 目录对照，不存在的 id 报错 |
| M-低2 | 方法升级的确认发生在 overlay 封存检查之前：overlay 未封存时，用户会先确认迁移并写入新修订，之后才看到 `GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED`。另外，无论确认还是取消，readiness 区都是空的，必须再点一次 Check readiness | 先检查封存再要求确认；确认或取消后自动重跑 readiness |
| M-低3 | 隔离或停用模块时，一个原因会报出 3 条错误：除了正确的 `GF_PREFLIGHT_MODULE_QUARANTINED`（或 `GF_PREFLIGHT_MODULE_DISABLED`），还有 `GF_PREFLIGHT_MODULE_SELECTION`（“Select one compatible registered module…”）和 `GF_PREFLIGHT_PROJECT_REVISION`（“Correct the project modules and save a new revision.”）。后两条引导用户去改 Study，而正确做法是修复或启用模块 | 已识别为隔离或停用时，不再输出由它派生的另外两条错误 |
| M-低4 | ID 冲突时，两行隔离条目完全相同（同名同版本），也不显示各自的清单文件名，无法看出哪个是多余的文件。横幅写 “VALUE started without it”，实际有 2 个模块，单数不对 | 显示清单文件路径；横幅按数量使用单复数 |
| M-低5 | 使用 `gridform.*` 合同 ID 被拒时，报错前缀是 “Module implementation could not be loaded:”，错误码是 `GF_MODULE_RESOLUTION`（`module_installation.py` 第 211、397 行）。实际原因是合同 ID 不匹配，而不是代码加载失败 | 为合同 ID 不匹配单独设错误码和文案 |


## 5 加功能角色（add new function to VALUE）

### 5.1 结论

**通过但有问题。** 编写、安装、启用、运行、对照、冲突处理、停用/启用和隔离都能走通，观察型扩展没有扰动模型结果。没有高严重度缺陷；有 4 项中等、5 项低等缺陷。

### 5.2 已验证可用（附证据）

1. **编写扩展**（Modules 页，add new function to VALUE）：
   - 提案校验通过后，界面列出数据角色、钩子（`initialize` 和 `after_psm`）、产物 schema 和状态命名空间，可以下载 ZIP。
   - 测试员在本地扩展了功能：产物新增 `observed_run_id` 和 `hook_call_index` 两个字段，并同步修改了 schema 和 manifest 的 `summary_fields`。
   - 用 `build_extension_bundle.py` 重建两次，字节完全相同（`bundle_sha256` 7f18b09b…）。
2. **安装**：界面安装器返回 201，提示 “passed structural extension validation”。
3. **在独立 Study 中启用**：
   - 在 Studies → Advanced → Optional domains 中勾选扩展。
   - 在 Data 页复制一个独立数据包，选文件后自动上传并绑定 `audit-input.csv`，26/26 输入就绪。
   - 不勾选实验性确认时无法保存（`GF_EXPERIMENTAL_ACK_REQUIRED`）；勾选后保存，得到 `uatf-observer-study-a` 的第 1 版。
4. **两时段运行**（907da84c）：
   - 状态为 completed。Inspect → Artifacts 中能看到 2025 年的扩展摘要，含新增字段。
   - 摘要中的 `source_inputs_sha256` 与 orchestrator-events 里 psm.run 的 `input_state_sha256` 一致（d42899…）。
5. **两整年运行**（35,040 时段，e4e6ac50）：
   - 两年都通过。2025 和 2026 年各有一条产物，`hook_call_index` 依次为 1、2。
   - 按年份和按扩展筛选都正确，哈希与 psm.run 事件逐年一致。
6. **与基线对照**（value-101-baseline 两年 Run 285c7d7f）：
   - 两次运行的 year-results 中，所有物理和经济数值完全相同，说明观察型扩展没有扰动模型。
   - Compare 页如实列出三处变化维度：数据角色、扩展和参数。
7. **命名空间和身份冲突**：以下 4 种安装都在写入前被拒（409），modules 目录逐字节不变：

   | 冲突情况 | 拒绝代码 |
   |---|---|
   | ID 不同但命名空间相同 | `GF_EXTENSION_NAMESPACE_COLLISION` |
   | 同一 ID 升级版本 | `GF_EXTENSION_MIGRATION_REQUIRED` |
   | 占用内置扩展的命名空间 | `GF_EXTENSION_NAMESPACE_COLLISION` |
   | 复用已安装的 Python 包名 | `GF_EXTENSION_SOURCE_COLLISION` |

   编写台本身也会阻止这类冲突，此时下载按钮保持禁用。
8. **停用与重新启用**：
   - 被 Study 和运行历史引用的扩展：Disable 按钮禁用，提示 “Used by …”；直接调接口返回 `GF_EXTENSION_IN_USE`，并列出依赖它的 Study 和 Run。
   - 未被引用的扩展：可以停用。停用后它从 Optional domains 中消失，出现在 “Disabled and quarantined” 面板；点 Enable 后恢复可选。
   - 停用期间命名空间被新扩展占用时，再点 Enable 会被拒（`GF_EXTENSION_NAMESPACE_COLLISION`），并显示具体原因。
   - Remove 前有确认框，文件被移到 `disabled-manifests/removed/…` 而不是删除。
9. **隔离**：`hooks.py` 导入失败时，readiness 阻止运行（`GF_PREFLIGHT_MODULE_QUARANTINED`），health 变为 degraded。修好源码并 Rescan 后恢复 Ready。
10. **网关安全**：从页面以外直接 POST 会被拒（`GF_GATEWAY_ORIGIN_REJECTED`）。有 Run 在跑时，生命周期操作会先弹窗确认。

### 5.3 现存缺陷

#### F-中1 原地修改已安装扩展的源码后，Check readiness 一直不出结果

- **复现**：
  1. 修改 `state/modules/installed-extensions/uatf-observer/0.1.0/src/value_ext_e6676fbf33c7e32e/hooks.py`。改一次，或改完再还原，都会出现。
  2. 在 Runs 页点 Check readiness。
- **现象**：
  - 不显示 readiness 面板，只提示 “Preflight identity changed. Refresh the saved Study and check it again.”。刷新页面、多次重试都一样（连续复现 3 次）。
  - Run 按钮仍可点击。只有在没有 readiness 结果的情况下直接跑一次（系统自动追加第 3 版修订）之后，才恢复为 “Ready”。
- **后端证据**：preflight 返回 `accepted=true` 和 `GF_PREFLIGHT_REVISION_REIDENTIFY`，但报告中的 `project_revision_sha256` 是重新计算出的哈希，与已保存的修订（第 2 版 c5fa40…）不同。前端的 `preflightMatches` 判定不一致，丢弃了结果。
- **成因与修复**：与 M-中2 同一根因，见 M-中2，一次修复即可。

#### F-中2 扩展源码的行为改动被提示为“只改了代码身份”

- **复现**：把 hook 的输出改成 `hook_call_index * 10`，然后 Rescan、Check readiness。
- **现象**：
  - 预检只给出 `GF_PREFLIGHT_REVISION_REIDENTIFY`，文案是 “Only the code identity of this Study changed (no change to methods or results expected)”。
  - `module_source_changes` 为空，也没有琥珀色的“源码已改”提示。
  - 但实际产物从 1 变成了 10（Run 4d094bb5）。
- **可追溯性**：新的哈希 d1456… 已经冻结在 Run 里，可以追溯。问题在于提示内容与事实相反，而且与模块原地改源的处理方式（A16-4）不一致。
- **成因（代码确认）**：
  - `gridform_core/module_installation.py` 第 86–110 行的 `installed_source_changes` 只遍历模块安装记录，不检查扩展。
  - 预检中自动重识别的文案是固定写死的（`gridform_core/preflight.py` 第 610–616 行）。
- **建议修复**：
  - 把已安装的扩展纳入源码变更检测，卡片和 readiness 的提示方式与模块一致。
  - 源码哈希变化时，不要再写 “no change to methods or results expected”，改写为“源码已改，结果可能变化，新哈希将被记录”。

#### F-中3 Rescan 不重新导入扩展钩子，坏掉的扩展不会被隔离

- **复现**：
  1. 在已安装扩展的 `hooks.py` 末尾追加 `raise RuntimeError(...)`。
  2. 点 Modules → Rescan modules。
- **现象**：
  - 界面提示 “Rescan complete: no module is quarantined.”，health 仍为 ok。
  - 直到 Check readiness 时，才出现 `GF_EXTENSION_HOOK_IMPORT` 隔离。
  - 钩子已经加载过之后再改坏，Rescan 同样发现不了（复现 2 次）。
- **与手册不符**：`docs/MODULE_DEVELOPER_101.md` 第 12 节（第 547–549 行）写的是 “Rescan also re-imports every installed module and extension”。
- **成因（代码确认）**：
  - Rescan（`backend/server.py` 第 4326–4337 行）会清掉已安装源码的导入缓存并重建模块目录。
  - 但扩展钩子只在解析 Study 的选择时才导入（`gridform_core/extension_framework.py` 第 272–283 行），所以 Rescan 不会触发钩子的导入错误。
- **建议修复**：Rescan 时逐个导入已启用扩展的钩子模块，失败就隔离，并把扩展计入重新加载的数量。如果暂时不改代码，至少要修正手册。

#### F-中4 加功能路径打开的独立 Study 草稿不继承当前选中的基线

- **复现**：选中 VALUE 101 baseline，在扩展编写台点 “Open independent Study draft”（URL 带 `study=value-101-baseline`）。
- **现象**：
  - 草稿名称是 “VALUE UK transition · extension study”，年份为 2025–2034。
  - 保存后，`planning.defer_spread_years` 从 0 变成默认值 3，`runtime.checkpoint_enabled` 丢失。
  - Compare 页报告 “Multiple Dimensions Changed”，无法按引导路径做“只加扩展”的单变量对照。
  - Studies 卡片上也没有复制操作，只有 Edit as new revision 和 Move to trash。
- **成因（代码确认）**：`app/page.tsx` 第 1611–1615 行的处理函数沿用了编辑器里当前的表单内容，只改了名称和实验性确认，没有从选中的 Study 复制配置。
- **建议修复**：
  - 草稿从当前选中的 Study 复制年份、参数和运行选项，只增加扩展相关的改动；
  - 或者在 Studies 卡片上提供 “Duplicate Study”，并在编写台的引导里指向它。

#### 低等缺陷

| ID | 现象与复现 | 建议修复 |
|---|---|---|
| F-低1 | 内置命名空间冲突的拒绝提示写 “disable value-toy-audit-extension before installing uatf-builtin-ns”（`extension_bundle.py` 第 378 行），但内置扩展不能停用：接口返回 `GF_EXTENSION_BUILTIN_LIFECYCLE`，界面上也没有 Disable 按钮 | 冲突对象是内置扩展时，改为提示“请换一个命名空间” |
| F-低2 | “Disabled and quarantined” 面板只显示名称和版本，不显示 ID。安装器允许两个扩展同名；uatf-second 停用后显示为 “UATF final observer uatf-observer 0.1.0”，与 uatf-observer 无法区分（同名是测试包复用名称造成的） | 显示扩展 ID |
| F-低3 | 扩展出错时，readiness 的修复建议有误导：隔离时同一条错误出现两次，另附 `GF_PREFLIGHT_PROJECT_REVISION`（“Correct the project modules and save a new revision”）；源码在加载后被改动时，建议是 `GF_PREFLIGHT_MODULE_SELECTION`（“Select one compatible registered module…”）。正确做法是修复源码再 Rescan | 与 M-低3 一起修：去重，并抑制派生出来的错误 |
| F-低4 | 含实验性本地扩展的 Run 没有任何标记：Runs 页和 Inspect 页的运行头部只显示 “Scientific scenario Passed”，全页找不到 experimental 或扩展字样。扩展只出现在 Inspect 的 Artifacts 标签页和 Compare 页 | 在运行头部显示 “Experimental extension: <id>” 标记 |
| F-低5 | 有 Run 在跑时安装扩展，会先弹确认、后做冲突检查。确认框文案是 “Confirm to change installed modules anyway”（`backend/server.py` 第 489 行），说的是模块而不是扩展；用户确认之后才知道包本来就会因冲突被拒 | 先做冲突检查，再请求确认；文案区分模块和扩展 |


## 6 定点验证：首个 Run 异步启动；修正口径跑 R029 public2

### 6.1 结论

**通过。** 从界面启动首个 Run 后，页面始终可以操作，进度实时显示，冻结输入期间 clone 数据包在几十毫秒内返回。修正口径用 R029 public2 跑完一整年，全部校验通过，结果与 R3-1 的记录和 golden C10 一致。

### 6.2 环境

- **代码**：`fab9ec2`，dist 按该版本重新构建。
- **数据目录**：全新的 `VALUE_DATA_HOME`，开始时 runs 和 archives 都为空，所以这是真正的“首个 Run”。
- **R029 public2**：用 `build_value_uk_pack_revision.py --pack r029-public2 --link hardlink` 从 staging 中的 R029 public1 在本地重建。manifest sha 为 `d9876d98…d309`，与 R3-1 的记录一致。这个包只在本地构建，没有发布。
- **VALUE 101 教学包**：用 `install_synthetic_pack.py --value-101-only` 装入。

### 6.3 首个 Run 从界面启动（Learn → Run one market day）

- **启动**：`POST /api/projects/value-101-baseline/runs` 用 729 ms 返回 202。点击后 939 ms 页面跳到 Runs，显示 `Preparing · step 1 of 4: Recording and archiving the execution environment · 0 s elapsed`。
- **冻结期间页面可用**（执行环境归档进行到约 1 分 51 秒时测量）：
  - 切换 Data、Studies、Market replay、Runs 四个页面，各用 44–135 ms；
  - 2 秒内最长帧间隔 17 ms，主线程没有卡顿。
- **冻结期间 clone 很快返回**：
  - 通过界面网关 clone `value-101-baseline-v1`：201，23 ms；
  - Run 处于第 1 步、已用时 62 s 时，用 curl 直接 clone：201，0.024 s；
  - `GET /api/projects` 用时 5 ms，`/api/workspace` 用时 0.03 s。
- **进度显示**：
  - 已用时间每 8 秒刷新一次（1 min 58 s、2 min 06 s … 2 min 45 s），之后依次进入 queued → running → completed。
  - 各阶段用时：execution 173.1 s，snapshot 0.022 s，resources 0.013 s，worker 0.002 s。

### 6.4 修正口径跑 R029 public2

Study `r3check-r029-corrected` 按 C10 的配置经 API 建立：默认模块，2025 年，`methodology.profile = value-corrected`，`methodology_supported` 为 true。两个 Run 都从 Runs 页界面启动。

- **两时段接线检查**：POST 用 1,324 ms 返回 202，1.85 s 后出现进度；冻结期间 clone 返回 201，41 ms；状态依次为 snapshotting → queued → running → completed。
- **完整一年（17,520 时段）**：
  - POST 用 1,595 ms 返回 202，2.3 s 后出现进度；冻结期间 clone 返回 201，45 ms。
  - 准备阶段：execution 39.3 s，snapshot 2.07 s（冻结约 848 MB 输入）。运行约 3 分钟后完成，原因码 `GF_RUN_COMPLETED`。
  - 以下各项全部 passed：execution、契约校验、科学校验、运行不变量、能量平衡、储能不变量，以及 production gate（profile `value-corrected`）。
  - `raw_invariant_failures` 为空，`result_publication` 为 published，年度覆盖 100%。
  - 最大能量平衡残差 1.63e-11 MWh。stress 时段和事件都是 0，没有缺电。

**结果与 R3-1 / golden C10 一致：**

| 指标 | 本次结果 |
|---|---:|
| 需求 / 发电 | 232.91 / 234.73 TWh |
| CEM 系统资源成本（成本账 v2） | 158.94 亿英镑，68.24 £/MWh |
| 弃电 | 1.24 TWh |
| 进口 | 1.27 TWh |
| 储能充电 / 放电 | 3.26 / 2.54 TWh |
| 排放（含隐含排放；其中运行排放 28.11 Mt） | 31.93 Mt CO2e |
| 光伏装机 | 10,067 MW |

### 6.5 缺陷与观察

| ID | 现象 | 建议修复 |
|---|---|---|
| T-低1 | 准备期间，Runs 页的 “Execution” 格显示 “Queued”，而生命周期状态是 snapshotting，两处表述不一致 | 准备期间该格显示 “Preparing” |

另有一项观察，不算缺陷：说明“首个 Run 需约 3 分钟归档执行环境”的文字在之后的 Run 上也会显示。由于文字本身写明“之后的 Run 一分钟内完成冻结”，这样可以接受。


## 7 跨角色的共性问题与建议修复顺序

### 7.1 同一根因，一次修好

| 合并项 | 共同根因 | 修复位置 |
|---|---|---|
| M-中2 + F-中1 | 自动重识别时，预检报告用新计算出的哈希做身份，前端拿它与已保存修订比较，结果丢弃 | `gridform_core/preflight.py`（报告字段）或 `app/features/workspace/preflightIdentity.ts`（匹配规则） |
| M-低3 + F-低3 | 模块或扩展已被隔离或停用时，又派生出 `GF_PREFLIGHT_MODULE_SELECTION`、`GF_PREFLIGHT_PROJECT_REVISION` 两条误导性的建议，且有重复 | `gridform_core/preflight.py` 的错误汇总 |
| R-低1 + S-低7(c) | 规划表的行是“项目×年份”，但没有年份列 | `planning_index.query_index_projects` 和 Inspect 规划表 |
| R-低5 + S-低7(c) | 指标名、状态名直接由字段名生成 | 前端统一标签表 |
| M-低4 + F-低2 | “Disabled and quarantined” 中的条目无法区分（不显示清单文件名或 ID） | `ModuleQuarantinePanel` 和停用列表 |

### 7.2 扩展的处理落后于模块

模块已经具备的三项能力，扩展还没有：

- 源码变更检测与提示（F-中2）；
- Rescan 时重新导入（F-中3）；
- 运行头部的实验性标记（F-低4）。

建议按模块现有的做法补齐，并同步修正手册第 12 节。

### 7.3 时钟、日期与覆盖范围的说明

S-中1、S-中2、S-中3、S-低2 的计算本身都是对的：

- 当地时间正确换成了 UTC；
- 逐时数据被复制成两个半小时，闰日被删除；
- 日期顺序错误的文件会被拦住。

问题出在给用户看的标签和说明上，建议一次性梳理：

- 模型时钟统一标为 UTC；
- 审阅报告按读取器的实际分支写说明；
- 时间戳检查同时报告覆盖范围和数据年份。

### 7.4 建议的修复顺序

1. **R-中1**：结果页上用户可见的 JS 错误，改动小。
2. **R-中2**：比较页给出错误的扣留理由，导出为空且没有说明。
3. **M-中2 / F-中1**：readiness 在常见的升级和改源场景下不可用。
4. **M-中3**：迁移后无法派生对照 Study，而且提示的办法无效。
5. **S-中1、S-中2**：时钟标签和时钟说明与事实不符。
6. **F-中2、F-中3**：扩展的源码变更检测与 Rescan。
7. **M-中1**：storage_cost 的调用证据。
8. **F-中4、S-中3**：引导与输入格式。
9. 低等缺陷按 7.1 的合并项分批处理。


## 8 安全与环境核对

- **进程**：各角色和定点验证都只按自己记录的 PID 停止自己启动的进程（API、UI 网关、Playwright 驱动或 chrome），各自使用的端口都已释放。复现角色还核对过各 Run 的 worker 进程都已退出。没有使用 pkill、killall 或按模式匹配的 kill，没有连接 8766/8800 端口。
- **INSTALLED**：各角色和定点验证结束时都核对过，撰写本报告时又核对了一次：
  - `find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`。这个文件为 0 字节，mtime 是 2026-10-03 05:41:26，比安装回执晚 17 秒，由作者正在运行的实例在安装时生成，不是测试写入的；
  - 没有任何 `.pyc` 文件；
  - `diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”。
- **staging 数据**：定点验证前后，R029 public1 的 33 个文件逐个 sha256 完全相同；链接计数已回到 1，权限 664 不变。
- **scratch 用量**：
  - 各角色已删除 state、源码导出和浏览器 profile 中的大文件，保留截图和证据。改函数角色剩约 186 MB，主要是源码副本和界面构建产物。
  - 定点验证中，冻结完整一年的输入时，对象库和 runs 临时占用约 1.3 GB，超过了约定的 500 MB 上限（当时可用空间 214 GB）。验证结束后已全部删除。


## 附录 A 撰写本报告时的复核脚本

都在当前代码（`fab9ec2`）上执行，Python 经 `vpy` 包装器调用，没有启动服务。

**A.1 `align_clock` 对逐时、闰年、不足一年序列的处理（S-中2、S-低2）**

```python
from gridform_core.series_reader import align_clock, SeriesSpec, DECLARED
align_clock(np.arange(8760.), 17520, SeriesSpec(role="market.france.price"), mode=DECLARED)
# → [0, 0, 1, 1, 2, 2, …]，长度 17520：每小时复制成两个半小时
align_clock(np.arange(17568.), 17520, SeriesSpec(role="market.france.price"), mode=DECLARED)
# → 第 2832 期取值 2880：删去 2 月 29 日的 48 期
align_clock(np.arange(17000.), 17520, SeriesSpec(role="market.france.price"), mode=DECLARED, cyclic_default=True)
# → 第 17000 期取值 0，最后一期取值 519：最后 520 期从开头补
```

**A.2 日/月/年时间戳的解析（S-中3）**

用 `%d/%m/%Y %H:%M` 写出 2025 年全年 17,520 个半小时时间戳，调用 `timestamp_row_problems(path, "t", 30, time_zone="UTC")`：

- 结果 `problem_count = 154`；
- 第一条问题是第 50 行 “gap of 43230 minutes after the previous row (expected 30)”，该行被读成 2025-02-01；
- 与测试员报告的现象一致。

**A.3 代码核对**：各中等缺陷“成因”中列出的文件和行号，都在 `fab9ec2` 上逐一读过。


## 附录 B 证据位置

以下路径都在 scratch 下，`$SCR` = `/tmp/claude-1000/-home-deepseek--config-Claude-scratch-workspaces-236b67cc-cc11-47c6-901f-9efac7ff2b1f-954fe4c9-9c87-4a98-b62f-216510b0e0f0-scratch-2026-10-04-a946e8/fd56b27b-0c52-4166-89c3-a4a8b5e4ea96/scratchpad/build`。scratch 是临时目录，需要长期保留的证据应另行归档。

| 角色 | 位置 | 内容 |
|---|---|---|
| 复现 | `$SCR/final_roles/reproduce/` | `shots/` 截图 10 张（01-home … 10-market，其中 07-compare-repeat、08-compare-doctoral 对应 R-中2）；三个 Run 的状态 JSON（9749a2a3、902f0b8f、ab225ce5）；`doc-cost.json`；`cmp.py`；Playwright 脚本 `pw/` |
| 换数据 | `$SCR/final_roles/swap-data/` | `shots/` 截图 10 张；测试 CSV `input/`；Playwright 脚本 `pw/`；API 边界测试 `neg_api.py` |
| 改函数 | `$SCR/final_roles/edit-module/` | `shots/` 截图 10 张（12-codeonly-preflight-loop 对应 M-中2，14-quarantined-study-readiness 对应 M-低3，19-id-collision 对应 M-低4）；`ev/`（preflight-codeonly.json、wiring.txt、run-page-full.txt）；`author/` 测试 bundle；`pw/` |
| 加功能 | `$SCR/final_roles/add-feature/` | `shots/` 截图 10 张（17-readiness-edited-ext 对应 F-中1，13-disabled-panel 对应 F-低2）；`ev/` 安装和运行日志；`author/` ZIP 与冲突变体包；`pw/` |
| 定点验证 | `$SCR/r3check/` | 日志（first-run.log、follow.log、r029.log、r029full.log、api.log、diagnose.txt）；状态（full.json、smoke.json、run1-final.json）；staging 哈希（staging-r029-before/after.sha）；`shots/` 截图 7 张；`pw/` |
