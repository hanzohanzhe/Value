# VALUE 方法学修改员交接文档（方法学 0.4 版次）

- 日期：2026-10-06。分支 `fix/review-2026-10-04`（只在本地，未推送），对照 `main`（35aadb3，即 VALUE 0.6.0-alpha.2 的源码）。应用版本 0.7.0-alpha.1。
- 读者：维护以下文件的人：`docs/methodology/`（`en/`、`zh/`、`VALUE_METHODOLOGY.md`、`README.md`、`edition.json`、`generation.json`、`artifacts.json`）、`docs/MATHEMATICAL_REFERENCE.md`、`docs/SCHEME_C_MODEL_CARD.md`、`docs/VALIDATION_AND_CLAIMS.md`，以及方法学文档构建工具（`scripts/methodology/`、`scripts/build_value_methodology_pdf.py`、`website/sync_methodology.py`）。
- 交付：DECISIONS“收尾交付”第 2 项。仓库副本为 `docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md`，worktree 根目录副本为 `VALUE_handoff_methodology_editor_2026-10-04.md`。
- 事实来源（按权威排序）：
  1. `docs/dev/P0_DECISIONS.md`（Q1–Q15、A1–A15）；
  2. 修正目录 `gridform_core/data/methodology/{profiles.json,corrections/*.json,declared_deviations.json}`，以及由它生成的 `docs/generated/METHODOLOGY_PROFILES.md`；
  3. `docs/release/VERSION_LEDGER.json`、`docs/release/P0_GOLDEN_DELTA.md`；
  4. 草稿 `docs/methodology/drafts/0.4/*.md`；
  5. `docs/handoff/MODEL_CHANGES_BRIEF.md`（下文的 U1–U11、C1–C24 编号沿用该简报）；
  6. `docs/dev/GBP1_DOCTORAL_BEFORE_AFTER.md`、`docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md`；
  7. `docs/dev/p0-reports/*.md`。
  
  文中凡是“代码中”的描述，都在本分支的源码上核对过，行号以本分支 HEAD 为准。
- 本文只写**改哪里、改成什么**。本单元没有改动任何方法学文档。P0 各包已经写好的内容见第 1 节。

## 0 先读这一段

1. **0.3 版次冻结，所有改动进入 0.4。** `docs/methodology/{en,zh}/*.md` 是已发布 0.3 文档（六个 docx/pdf/html，哈希登记在 `artifacts.json`）的源稿，网站章节 JSON 也由它们生成（计划 C26，Q-X3）。
   - 在 0.4 整体生成之前，不要就地修改 0.3 源稿。
   - 理由一：改了以后，源稿与已发布文件不一致。
   - 理由二：`scripts/check_publication_scope.py` 逐字比较 `website/methodology/chapters*.json` 与源稿（“Generated markdown diverges from source”），改了就会失败。
   - 0.4 的发布须经作者同意（Q-X3：本轮只发布 `METHODOLOGY_PROFILES.md` 和模型卡，0.4 放到 P1 或经作者同意后单独发布）。
2. **七份草稿已经写好**，在 `docs/methodology/drafts/0.4/` 下：p04、p05a、p05b、p06、p07、p08、f2。它们覆盖了大部分正文改动，但有三个问题：
   - 草稿按工作包组织，不按章节组织；
   - 有几处已被后续决定取代，见第 6 节；
   - 中文部分大多只是摘要，p04 除外。
3. **以下内容没有草稿，需要你根据本文新写**：
   - 方法学口径总述（第 1 章新增一节）；
   - A15 核电路径依赖；
   - 修正口径储能余量和电池池的公式；
   - Q6 价格标签；
   - A8 储能投资审核的公式；
   - DC 网络的份额展开（P1-01）；
   - R029 章节的口径归属；
   - `VALUE_METHODOLOGY.md` 的全部改动。
4. **设计假设和修正必须分开写**（第 3 节）。以下三项是作者明确保留的论文设定，不是修正：
   - 风光储没有 OPEX；
   - 投资决策不折现；
   - 一律以起始年币值计价。
   
   不要把它们写成“已知缺陷”或“待修”，也不要引入 NPV。
5. **九章结构不变。**
   - `scripts/methodology/assemble.py` 写死了九个章节 id；
   - `website/sync_methodology.py` 要求恰好九章、六个文件；
   - `check_publication_scope.py` 要求章节编号为 1–9。
   
   所以口径总述写进第 1 章的新小节，不要新增第十章。
6. **构建与测试会拦截的写法**：
   - `VALUE_METHODOLOGY.md` 及其 PDF 中不得出现子串 `force`，不分大小写（`tests/test_value_methodology.py`）。注意 “forced part”、“enforce”、`force_current_...`、`force-reference-...` 都会命中；
   - 章节正文不得含 32–64 位十六进制串（例如 sha256），不得含 `/home/` 或 `/mnt/` 路径（`assemble.py`）；
   - 章节正文不得出现私有产品名（`sync_methodology.py` 的 PRIVATE 正则）；
   - 三份参考文档有固定短语和禁止短语（第 5 节开头）。
7. **命名陷阱。** 方法学第 5、6 章里的 “Doctoral” 路径是另一个模块 `value-doctoral-national-psm`（R029 thesis96），**不是**“论文复现口径” `doctoral-lineage-0.6.0a2`。复现口径的 golden（D1–D5）走的是第 5 章的 “Native” 路径，即默认 PSM `value-bid-at-cost-psm`。0.4 必须在第 1、5 章写清这一点（第 2.2 节）。
8. **写 0.4 之前须确认的事项**见第 9 节，共九条。其中最重要的三条：
   - R029 研究在 0.7.0 中按哪个口径运行，哪些修正对 thesis96 路径生效；
   - 逐站核电可用率实际上只对 GBP1 public1 生效，而该包在修正口径下不合格；
   - 修正目录中 `p05.solar-plane-of-array` 的描述把倾角写成“站点纬度”，与代码不符。代码取 Jacobson & Jadhav 最优倾角。

## 1 文件现状

| 文件 | 本轮是否已由各包改过 | 已改内容 | 还要做什么 |
|---|---|---|---|
| `docs/methodology/en/*.md`、`zh/*.md`（0.3） | 否（C26 冻结） | — | 合并为 0.4，见第 4 节 |
| `docs/methodology/drafts/0.4/*.md` | 是（7 份） | 各包的方法学改动 | 并入 0.4 后，删除或标注“已并入”，见第 7.5 节 |
| `docs/methodology/VALUE_METHODOLOGY.md` | 否 | — | 按第 4.10 节改，并把版次改为 0.4 |
| `docs/methodology/README.md`、`edition.json`、`generation.json`、`artifacts.json` | 否 | — | 0.4 生成并审阅后更新，见第 7 节 |
| `docs/MATHEMATICAL_REFERENCE.md` | 部分（`09221f6`、`bca6607`、`4324ac7`、`8e34038`、`020d402`） | 版本行、§2.4 网络经济学与求解合同 v4、§5.1 参照情形 | §2.1、§2.2、§2.3、§3、§4、§5、§7、§8，见第 5.1 节 |
| `docs/SCHEME_C_MODEL_CARD.md` | 部分（`e12b41d`、`b1a5206`、`50fc6bd`、`ef7807f`、`69b7fa1`、`f2d7463`） | 口径段、已知简化、投资规则、P0-6/P0-5b/F2 段、A15 | 成本定义段、水电段、数据资格、Q14 一般规则，见第 5.2 节 |
| `docs/VALIDATION_AND_CLAIMS.md` | 部分（同上，另有 `4324ac7`、`020d402`） | 第 38–46 行新增声明、P0-6/P0-5b/F2 段、0.7.0 声明范围 | 旧证据行的定性、补 A4/A2/Q14 行，见第 5.3 节 |
| `scripts/build_value_methodology_pdf.py` | 否 | — | 页脚日期（第 35 行写死 “25 August 2026”）、封面表，见第 7.3 节 |
| `scripts/methodology/*`、`website/sync_methodology.py` | 否 | — | 不需要改代码，按第 7 节流程使用 |
| `docs/generated/METHODOLOGY_PROFILES.md` | 生成文件 | — | **不要手改**。它由修正目录生成；目录的描述错误要请代码负责人改，见第 9 节第 3 条 |

另外两份交接文档：
- 网站上传员：`docs/handoff/WEBSITE_UPLOADER_HANDOFF.md`。其中阶段 3 是导入 0.4，前提是本文第 7 节完成；
- 给作者的改动简报：`docs/handoff/MODEL_CHANGES_BRIEF.md`。

## 2 术语与命名约定

### 2.1 口径（字符串固定，Q2）

| 机器 id | 界面标签（英文原文，中英文版都照写） | 固定附注 | 中文称呼 |
|---|---|---|---|
| `value-corrected` | Corrected methodology (default) | Current default methodology with review fixes of 2026-10. | 修正口径（默认） |
| `doctoral-lineage-0.6.0a2` | Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2) | not an exact reproduction of the 2026-07-18 retained trajectory | 论文复现口径 |

### 2.2 三条 PSM 路径的名称对照（0.4 必须写清）

| 方法学 0.3 中的叫法 | 模块 id（版本） | 两个口径下的情况 |
|---|---|---|
| 第 5 章 “Native” | `value-bid-at-cost-psm`（6.0.0），保留的 Scheme C 内核 `runtime_compat/modular_simulation_model.py` | **默认 PSM**。论文复现口径使用规则集 `native-doctoral-thesis-v1`，修正口径使用 `native-corrected-v1`（`native_market_rules.py`）。golden D1–D5、C1–C6 都走这条路径 |
| 第 4 章 “staged market” | `value-staged-bid-at-cost-psm`（1.3.0）加平衡模块 `value-copperplate-balancing`（1.1.0）或 `value-zonal-redispatch-balancing`（4.0.0） | 分阶段与网络路径。论文复现口径不允许使用（Q3），实际只在修正口径下运行（C7、C8） |
| 第 5、6 章 “Doctoral” | `value-doctoral-national-psm`（0.2.0，experimental），R029 thesis96 | 论文复现口径的白名单包含它，但 P0 没有修改它的算法。它**不是**论文复现口径本身 |

0.4 的写法建议：
- 第 5 章开头加一句：“Native is the default PSM (`value-bid-at-cost-psm`); it runs one of two market rule sets selected by the methodology profile. The Doctoral pathway below is a separate experimental module (`value-doctoral-national-psm`); it is not the doctoral reproduction profile.”
- 中文：“Native 即默认 PSM（`value-bid-at-cost-psm`），按方法学口径运行两套市场规则之一。下文的 Doctoral 路径是另一个实验模块（`value-doctoral-national-psm`），不是论文复现口径。”
- 是否把 “Doctoral pathway” 改名（例如 “Thesis-96 national pathway”）由作者决定（第 9 节第 8 条）。

`VALUE_METHODOLOGY.md` 第 42 行写 “The built-in PSM is `value-staged-bid-at-cost-psm`”，与默认配置不符。默认是 `value-bid-at-cost-psm`，见 `examples/*.scenario.json` 与 golden 冻结项目。0.4 一并改正。

### 2.3 本文的轨道标记

| 标记 | 含义 | 目录中的 `track` |
|---|---|---|
| **U** | 两个口径都改（universal）。属于 Q1 冻结的例外，或只改 accounting 区（Q12） | `universal`；或只在 VERSION_LEDGER 与 golden 修订中登记 |
| **C** | 只在修正口径下生效（profile_gated） | `profile_gated` |
| **D** | 论文复现口径有意保留的 35aadb3 行为，部分有已声明偏差 | `declared_deviations.json` |
| **设计假设** | 作者确认的模型设定，不是修正 | — |

`p04.*`、`p08.*`、`p06.physical-operating-cost`、`p06.staged-dwell-disclosure`、`p07.cost-ledger-v2` 不在修正目录中，只登记在 VERSION_LEDGER 或 golden 修订里（M7-X0-S13-S14 报告偏差 3）。写进正文时照样引用这些 id，但不要说它们“在目录中”。

P0-8 的 id 在 CHANGELOG 中列在“两个口径”栏。但论文复现口径不允许网络模块（Q3），所以正文应写“只在修正口径下运行”。

### 2.4 中英术语表（全文统一）

| English | 中文 | 备注 |
|---|---|---|
| methodology profile | 方法学口径 | |
| corrected profile (default) | 修正口径（默认） | |
| doctoral reproduction profile | 论文复现口径 | 不要简称“doctoral 口径”，以免与 Doctoral 路径混淆 |
| universal correction / profile-gated correction | 通用修正 / 口径受控修正 | |
| declared deviation | 已声明偏差 | DEV-BAL-01…04、DEV-STO-01 |
| market rule set | 市场规则集 | `native-doctoral-thesis-v1`、`native-corrected-v1` |
| stress event / stress period / shortfall | stress event / stress 时段 / 缺口 | 界面用英文 “stress”，中文版照写（`USER_GUIDE_ZH.md` 第 305–326 行） |
| unserved energy (booked) / recorded blackout | 缺电量（记账）/ 记录的切负荷 | 前者是 A2 补记的缺口，后者是内核记录的 blackout |
| raw residual / compatibility adjustment | 原始残差 / 兼容调整 | |
| headline (cost) / memo line | 头条（成本）/ 备忘项 | |
| levelised CAPEX | 平准化 CAPEX | |
| physical operating cost | 物理运营成本 | |
| settlement transfer | 结算转移 | |
| uniform marginal price | 统一边际价 | |
| average period cost | 时段平均成本 | Q6 标签 “Average period cost (£/MWh demand)” |
| cycle wear / cycle depreciation | 循环损耗 / 循环折旧 | |
| holding recovery | 持有回收 | |
| net position (per period) | （逐期）净头寸 | |
| buy-back | 回购 | |
| avoided-cost down-regulation stack | 按避免成本的下调次序 | |
| dec / down bid | 下调报价 | |
| network-free counterfactual | 无网络反事实 | |
| boundary marginal value | 边界边际值 | |
| wake / availability / electrical loss | 尾流 / 可用率 / 电气损耗 | |
| performance ratio (PR) | 性能比 | |
| plane-of-array irradiance (POA) | 倾斜面辐照（组件平面辐照） | |
| load factor / capacity factor | 负荷率 / 容量因子 | DUKES 用“负荷率”，模型用“容量因子” |
| constant base-year money | 起始年不变币值 | |
| undiscounted | 不折现 | |
| storage headroom / power-battery pool | 储能扩容余量 / 功率电池共用池 | |
| leftover surplus (after existing charge) | 现有储能充电后的剩余盈余 | |

## 3 设计假设、已声明偏差与修正

### 3.1 设计假设（写成模型设定，不写成修正）

| # | 设定 | 依据 | 适用口径 | 写在哪里 | 建议措辞要点 |
|---|---|---|---|---|---|
| S1 | **风光储没有 OPEX**：没有可变 OPEX，毛收入即利润；固定 OPEX 视为已含在平准化 CAPEX 中。投资决策和头条成本中都不再单独扣除。数据包若给出风光储 FOM，只作为备忘项 | A4、A7 | 两者 | 第 4 章“当前投资与建设规则”、“成本与碳排”；`VALUE_METHODOLOGY.md` §8、§11；模型卡；数学参考 §4、§5 | 写成 “thesis assumption: VRE and storage carry only capital cost and depreciation”。不要写“暂未建模” |
| S2 | **投资决策不折现**：四档规则比较 ROI 与 preferred_rate、回收期与目标年限，不用 NPV、IRR 或年金门槛。P4-02 移出范围 | A6 | 两者 | 第 4 章（agent-investment）；数学参考 §4；`VALUE_METHODOLOGY.md` §8 | 说明成本核算中的 CRF 年金化只把存量资本摊到各年，不对投资收入折现（p07 草稿已写） |
| S3 | **起始年不变币值**：所有金额按起始年币值计价，未来收入与现在等价 | A6 | 两者 | 第 1 章新小节；第 2 章“成本与储能参数” | 不要写死“2025 GBP 适用于全部输入”。现有正文中有 2025 GBP（抽蓄 CAPEX、政策预算）、2022 年欧元价格按 1.1 换算、BEIS 2020 成本等不同来源年份，且没有做通胀调整。要么照实列出，要么由作者确认后统一表述（第 9 节第 7 条） |
| S4 | **缺电时段的调度不变**：日前满足不了预测时，出力和价格照旧，只记录 stress event（A2） | A2 | 两者 | 第 5 章 Native 出清 | 写成已知简化，并配合第 3.3 节 U7 的核算修正 |
| S5 | **风光不对统计负荷率做标定**：只与 DUKES 并列披露，并写明偏高原因 | Q15、A1、A9 | 修正口径（论文复现口径没有损耗） | 第 3 章 | f2 草稿第 4 节可直接使用 |
| S6 | **储能投资审核沿用现规则**：ROI = 年市场收入 ÷ 整体 CAPEX，不扣循环成本，不另扣 FOM，不折现；扩容上限由物理利用率决定，不启用 tier_roi | A8(3)(4) | 两者 | 第 4 章 | 公式见第 4.4 节 K-12 |
| S7 | **储能只用盈余充电**，充电成本为 0，不从市场购电 | P5-20 未改；A8(2) | 两者 | 第 5 章、`VALUE_METHODOLOGY.md` §5 | 因此 A8(3) 中“充电量 × 充电时电价”一项在默认 PSM 中为 0 |
| S8 | **默认 PSM 显示的“价格”是时段平均成本**，不是边际出清价。只改标签，不改算法 | Q6 | 两者 | 第 5 章 Native 显示价格段；第 4 章分阶段价格；第 8 章完全预见 | 标签：默认 PSM 为 “Average period cost (£/MWh demand)”；staged v8 为 “National ahead clearing price”；PF 为 “Balance shadow price”；口径未知时为 “basis not recorded” |
| S9 | **投资侧 CSV 资源曲线与调度侧天气不一致**：只披露，下一轮统一 | Q15 | 两者 | 第 3 章“年度风光容量上限” | CSV 曲线没有乘损耗系数 |
| S10 | **火电固定 OPEX 本轮维持原状** | A7 | 两者 | 第 4 章 | UK 包的发电技术 FOM 为 0 |
| S11 | **核电和径流水电可用率取固定值**：没有年际波动，也没有换料或停运日历 | A10、A14 | 修正口径 | 第 5 章 | — |

### 3.2 论文复现口径保留的行为与已声明偏差（D）

这一节写进第 1 章的新小节，并在第 5 章相应位置逐条标注。签名与 gate 效果见 `declared_deviations.json` 和 p04 草稿中的表。

| 偏差 | 内容 | gate 效果 |
|---|---|---|
| DEV-BAL-01（P7-10） | 论文列语义：调度外盈余不在接纳供给 S 中，因此在 `default_psm_surplus_node_v1` 边界上计算 | 只是定义 |
| DEV-BAL-02（P3-01） | 隐藏缺电。两个口径都保留，用 stress event 记账 | 不影响 gate |
| DEV-BAL-03（P3-14、P5-11） | 默认 PSM 每年新建储能对象，年末存量被丢弃。两个口径都只报告（`storage_year_boundary`），P1 再决定 | 不影响 gate |
| DEV-BAL-04 | 平衡阶段重复计入必发核电盈余 | 可以解释 gate 失败 |
| DEV-STO-01（P5-03） | 每个阶段重置储能功率上限，同一时段可以既充又放，单期放电可达 2P | 可以解释 gate 失败 |

其余冻结行为（Q1，没有单独的偏差号）：
- 风光储按毛收入判档；
- 储能扩容余量为 0，三种电池各拿一份上限（合计 3 倍）；
- 储能报价随存放时长递增，并按 LIFO 出售；储能按 `max_bat_price` 结算；
- 削减市场按 `curtail_cost` 升序，先弃风；
- 出清前把 VRE 分流去电解；储能费跨期结转；
- 天气 v1 时钟，没有损耗；核电和径流水电 100% 可用；
- 旧读法（无表头首行、短序列时钟）；
- 径流水电兼容资本留在头条（VoLL 原为 8000 £/MWh，A16-5 起两个口径都是 17,000，属于只进成本账的通用修正 `fx5.voll-17000`）；
- **核电路径依赖（A15）**，见第 4.5 节 N-7。

### 3.3 修正总表

“位置”列写的是 0.4 的落点。en 与 zh 的行号相同时只写一个；不同时写 “en/zh”。

| 简报编号 | 修正 | id | 轨道 | 类别 | 0.4 位置 | 草稿 |
|---|---|---|---|---|---|---|
| U1 | 互联线序列按运行时钟逐期取值 | `p05.interconnector-clock`（P6-24） | U | 轨迹 | ch2 “互联线与分区需求”；ch5 Native 可用出力 | p05a |
| U2 | GBP1 比利时价格：EUR、逐小时，按 1.1 换算 | `p05.belgium-price-currency`（P6-02） | U | 轨迹 | ch2 互联线 | p05a |
| U3 | 互联线文件按线路身份接线 | `p05.boundary-identity`（P6-03） | U | 轨迹 | ch2 互联线 | p05a |
| U4 | GBP1 需求对齐 UTC（DST） | `p05.demand-utc-clock`（P6-04） | U | 轨迹 | ch2 需求序列 | p05a |
| U5 | 一律读声明的 `csv_column`，拒绝隐式整数索引列 | `p05.declared-column`（P6-01） | U | 轨迹 | ch2 读取规则 | p05a |
| U6 | 火电投资净收入恢复原 Scheme C 规则 | `p07.thermal-net-revenue`（P4-01 火电部分） | U | 轨迹 | ch4 投资规则 | p07 |
| U7 | 缺电 stress event 与能量平衡账 | `p04.surplus-routing`、`p04.surplus-node-boundary`（P3-01） | U | 核算 | ch5 Native（替换残差段） | p04 |
| U8 | 声明的能量平衡边界、兼容调整上限、逐资产储能审计 | `p04.surplus-node-boundary`、`p04.storage-energy-audit`（P7-10、P3-02、P3-14、P5-11） | U | 核算 | ch5 | p04 |
| U9 | 验证 v2、三类 gate、Q14 发布规则 | `p04.validation-v2`、`p04.validation-gate`（P7-01、P7-10） | U | 核算/发布 | ch1 新小节；ch5 | p04 |
| U10 | 物理运营成本（含 VoLL 和循环损耗，不乘 bid multiplier） | `p06.physical-operating-cost`（P5-06） | U | 核算 | ch5 年度费用；ch4 成本 | p06 |
| U11 | 成本账 v2：风光储 FOM 改为备忘项；PF 改读 FOM 键 | `p07.cost-ledger-v2`（A7、P4-08） | U | 核算 | ch4 成本；ch8 PF | p07（部分） |
| — | 数据包三层校验，按口径判定资格 | `p05.validation-layers`（P6-11、P6-12） | U | 展示 | ch2 | p05a |
| — | 内核天气缓存按文件作键 | `p05.weather-cache-key`（P7-02） | U | 软件 | ch3 实现段（可选） | p05b §1 |
| C1 | 天气 v2 时间约定 | `p05.weather-time-convention`（P6-06） | C | 轨迹 | ch3 | p05b §2 |
| C2 | 风光文献损耗系数 | `p05.vre-loss-factors`（P6-08） | C | 轨迹 | ch3 | p05b §3、f2 |
| C3 | 光伏倾斜面换算 | `p05.solar-plane-of-array`（A13） | C | 轨迹 | ch3 | f2 §1 |
| C4 | 核电逐站负荷率，按月停发 | `p05.firm-availability`、`p05.nuclear-generation-end-month` | C | 轨迹 | ch5 Native 可用出力；ch2；ch6 核电日程 | p05b §4、f2 §2 |
| C5 | 径流水电 0.3487 × 季节形状 | `p05.firm-availability`、`p05.hydro-dukes-load-factor` | C | 轨迹 | ch5；ch2 | f2 §3 |
| C6 | 声明式读取、时钟与数据门 | `p05.declared-reader`、`p05.series-clock`、`p05.data-gate`（P6-05、P6-07、P6-11） | C | 轨迹/展示 | ch2 | p05a |
| C7 | 互联线报价保留负价 | `p05.raw-boundary-price` | C | 轨迹 | ch2 互联线 | p05b §1 |
| C8–C16 | 默认 PSM 修正规则集 `native-corrected-v1`（九条） | `p06.*`（除 physical-operating-cost） | C | 轨迹/核算 | ch5 Native | p06 |
| C17 | 储能余量取现有储能充电后的剩余盈余 | `p07.storage-leftover-headroom`（P5-01） | C | 轨迹 | ch4 储能新增上限 | p07（无公式） |
| C18 | 三种功率电池共用一个池 | `p07.power-battery-pool`（P5-02） | C | 轨迹 | ch4 | p07（无公式） |
| C19 | 径流水电兼容资本移出头条 | `p07.compatibility-capital-out-of-headline`（P4-03） | C | 核算 | ch4 成本 | p07 |
| C20 | zonal 求解合同 v4 | `p08.zonal-solver-v4`（P2-01，Q5） | 只在修正口径下运行 | 轨迹 | ch7 | MATHEMATICAL_REFERENCE §2.4 |
| C21 | staged 下调报价的经济价格、同价按比例分配、类别次序 | `p08.dec-economic-pricing`、`p08.pro-rata-ties`、`p08.dec-class-order`（P2-05、P3-04） | 只在修正口径下运行 | 轨迹 | ch4 实际平衡；ch7 | p08 §1 |
| C22 | 无网络 LP 反事实 | `p08.network-free-counterfactual`（P2-02/03/04） | 只在修正口径下运行 | 核算 | ch7；ch4 成本 | p08 §2 |
| C23 | 边界边际值取 primary 阶段对偶 | `p08.boundary-primary-dual`（P2-06） | 只在修正口径下运行 | 核算 | ch7 | p08 §3 |
| C24 | DC 网络的份额展开 | `p08.network-share-expansion`（P1-01） | 只在修正口径下运行 | 轨迹 | ch7 DC | **无** |
| C25 | 互联线进口进入日前出清（按当期对侧价格和可用进口量报价；平衡环节只报剩余容量；下调按进口避免成本）。论文复现口径保留“只在平衡环节进口” | `fx6.day-ahead-interconnector-imports`（S-D3，A16-2） | C | 轨迹 | ch5 Native 伪代码与新段落（N-8）；ch2 互联线一句 | fx6 |
| — | 运行期 fallback 审计（只报告） | `p08.runtime-fallback-audit`（P2-13） | 只在修正口径下运行 | 展示 | ch7 实现段 | 无 |
| — | staged dwell 披露（数值不变） | `p06.staged-dwell-disclosure`（P5-15） | staged | 展示 | ch4 储能报价 | p06（末段） |
| — | 方法身份与 Study 迁移 | `x0.methodology-identity`、`x0.study-revision-migration`（Q13） | U | 身份 | ch1 新小节一句话 | 无 |

## 4 方法学正文逐章修改清单（0.3 → 0.4，en 与 zh 同步）

格式说明：
- **位置**写 en 行号 / zh 行号与小节标题；
- **旧**摘录 0.3 原句；
- **新**写 0.4 应表达的内容，公式统一给出 LaTeX；
- **口径**用第 2.3 节的标记。

每一处都要中英两版同时改，见第 8 节。

### 4.1 `introduction.md`（第 1 章）

**I-1 新增小节 “Methodology profiles / 方法学口径”**
- 位置：放在 en 第 30–34 行、zh 第 29–33 行（“Data and research configurations / 数据与研究配置”）之后。
- 口径：两者。草稿：无。事实来源：`METHODOLOGY_PROFILES.md`、CHANGELOG 0.7.0-alpha.1 “Two methodology profiles”、模型卡第 15–49 行。
- 内容：
  1. 两个口径的 id、标签和固定附注（第 2.1 节）。新 Study 默认用修正口径。
  2. 通用修正与口径受控修正的区别。论文复现口径冻结在 35aadb3 的已实现行为上，只有以下例外：
     - 互联线时钟（P6-24）；
     - GBP1 的三项读取错误（P6-02、P6-03、P6-04）；
     - 火电净收入（A4）；
     - stress event（A2）；
     - accounting 区的修正（Q12）。
  3. 已声明偏差（第 3.2 节表）。
  4. 论文复现口径的参考配置：legacy 储能电价，doctoral 碳因子情景。白名单：
     - 模块：论文谱系模块；
     - 数据包：GBP1 public1、`value-uk-1000twh-reproduction`、VALUE 101、synthetic contract pack；
     - 已启用外部代码时拒绝运行（Q3）。
  5. 结果发布（Q14）：
     - 论文复现口径：原始不变量全部通过才在结果页发布年度结果，否则只在 Inspect 和导出中提供；
     - 修正口径：任一 gate 失败即不发布年度经济结果；
     - 实例：VALUE 101 two_year 的论文复现运行因 DEV-STO-01 被扣发；GBP1 第一年因 A15 被扣发。
  6. 口径是方法身份的一部分（`x0.methodology-identity`）。不同口径的运行按不同方法比较；Study 的方法升级须在界面确认（Q13）。
  7. 设计假设 S1–S3（第 3.1 节）用一段话写在这里，后文各章引用。
- 结构提示：中英两版都只新增一个 `##` 标题和最多一张表，以保证 `assemble.py` 的配对检查通过。

**I-2 第 1 章 “Annual calculation / 年度计算结构” 末段**
- 位置：en 第 28 行 / zh 第 27 行。口径：两者（编辑性修改）。
- 旧：“The current staged market, the R029 national research algorithm, national joint clearing, and perfect-foresight linear programming each specify their own bidding…”
- 新：补一句，说明默认全国 PSM 是第 5 章的 Native（`value-bid-at-cost-psm`），staged 用于网络与分区研究。

### 4.2 `datasets.md`（第 2 章，en 与 zh 行号相同）

**DS-1 第 9 行，研究配置表 “Current GB zonal study … `value-uk-open-data-pack-v1`”**
- 口径：C 与 D。
- 新：加注三点：
  - GBP1 public1 只满足论文复现口径的资格；
  - 修正口径要使用 R029 public1，或本地构建的 `value-uk-open-data-pack-public2`（未发布）；
  - 网络模块只在修正口径下运行（Q3）。
- 写之前须确认 23 区研究以哪个基础包运行（第 9 节第 4 条）。

**DS-2 第 34 行**
- 口径：U（命名）。
- 旧：“`doctoral_demand` preserves the decimal precision … The interconnector reader also checks …”
- 新：R029 的需求与互联线由共享声明式读取器读取，即 `series_reader.py` 经 `data_method.read_role` / `read_boundary`。这两个旧模块在源码中不存在（审查 P6-01 已指出）。
- 草稿：p05b §6、p05a “One declarative reader”。

**DS-3 第 36–53 行，通用读取规则段落与伪代码**
- 口径：U 加 C。草稿：p05a。
- 旧：“selects the column with the most valid numbers … cycles or truncates sequences …”，以及 `read_series`/`align` 伪代码。
- 新：改成两种读取模式：
  - **legacy-v1（论文复现口径）**：保留旧规则，有两处例外（U，P6-01，`p05.declared-column`）：
    - binding 声明了 `csv_column`、`csv_header` 时，一律按声明读取；
    - 隐式选中的整数序号列报 `GF_DATA_INDEX_COLUMN`。
  - **declared-v2（修正口径）**：
    - 只有首行全部是非数值时才推断为表头（P6-05，`p05.declared-reader`）；
    - 多个数值列有歧义时，strict 模式报 `GF_DATA_AMBIGUOUS_COLUMN`；
    - 时钟先按 `interval_minutes`（或逐小时长度 8760/8784）确定分辨率，再截取；
    - 闰年删去 2 月 29 日；
    - 只有声明为 `cyclic` 时才把短序列回绕（P6-07，`p05.series-clock`）。
  - 伪代码按两种模式各给一份，或者给一份并用条件分支标注。

**DS-4 第 55 行，“the first forecast value, 21,560, is treated as a header …”**
- 口径：D 与 C。
- 新：
  - 写明这是 legacy-v1 的行为。论文复现口径保留它，所以预测序列比实测领先一期（`p05.demand-utc-clock` 的描述：doctoral forecast keeps its one-period lead）。
  - 修正口径下，首值作为数据读入。

**DS-5 第 66–81 行，需求 UTC 处理**
- 口径：U。草稿：p05a 表 `p05.demand-utc-clock`。
- 新：补一段，说明同一规则（R029 audit rule）现在也作用于发布版 GBP1 public1 的需求与预测，两个口径都适用（P6-04，A5）：
  - 删去 2022-10-30 重复的结算时段（保留较晚的发布）；
  - 线性插补四个缺口。
- 补一句后果：修复前，GBP1 在夏令时结束后的需求整体早 1 小时（2,956 期）；修复后全年需求增加 5,407 MWh（`GBP1_DOCTORAL_BEFORE_AFTER.md` 第 3、5 节）。

**DS-6 第 89 行，“Nuclear capacity follows a separate station policy …”；第 96–97 行的表**
- 口径：C。
- 新：补一句，并链接到第 5 章 N-4：
  - 修正口径下，核电按站降额并按月停发；径流水电按 DUKES 负荷率乘季节形状；
  - 论文复现口径下两者都是 100% 可用。

**DS-7 第 152–173 行，“Interconnectors and zonal demand”**
- 第 156 行：
  - 旧：“R029 retains negative input prices; the current general chronology resources apply \(\max(p,0)\).”
  - 新：论文复现口径下，canonical 资源截为 \(\max(p,0)\)；修正口径保留负价（C，`p05.raw-boundary-price`）。
- 新增一段 GBP1 public1 读取修正（U，A3/A5）。三条修正都按对象的 sha256 在真相登记表 `known_data_objects_v1.json` 中识别：
  - **比利时价格（P6-02）**：`Belgium_price.csv` 是逐小时 EUR/MWh。读 `Price (EUR/MWhe)` 列，按 R029 approved_r03 的固定汇率 1.1 EUR/GBP 换算，每个 UTC 小时用于两个半小时：

$$
p^{\mathrm{GBP}}_{t}=\frac{p^{\mathrm{EUR}}_{\lfloor t/2\rfloor}}{1.1}.
$$

  - **线路身份（P6-03）**：潮流文件按 NESO 线路身份接线（`NEMO_FLOW` 为比利时，`BRITNED_FLOW` 为荷兰，`NSL_FLOW` 为挪威 …），每条 Connection 只接本国序列。
  - **逐期时钟（P6-24）**：内核第 \(t\) 期取第 \(t\) 行，不再取第 \(\lfloor t/2\rfloor\) 行：

$$
F^{\mathrm{kernel}}_{t}=F_{t}\quad\text{instead of}\quad F^{\mathrm{kernel}}_{t}=F_{\lfloor t/2\rfloor},\qquad t=0,\dots,17{,}519.
$$

  - 修复前，荷兰线接的是比利时文件，价格读成 0，成了免费进口源。修复后 GBP1 进口减少 78%。作者决定把这份对比作为论文结果的勘误说明保留（A15）。是否在方法学中加“勘误”框，由作者决定（第 9 节第 9 条）。
- 第 158–163 行的公式不变。补一句：GBP1 的潮流文件标为 MWh/period，实际是瞬时 MW，登记表按 MW 读取（P6-12）。
- 第 165 行之后补披露：R029 的 `flow_sign` 为 `declared_unverified`，逐国年净潮流还没有核实（P0-5 Q13）。

**DS-8 新增一段：数据包校验与口径资格**
- 位置：在 “Data and implementation” 之前。口径：U（展示）加 C。草稿：p05a “Validation layers”。
- 新：数据包校验分三层：
  - 结构层，只有它决定 `valid`；
  - 时序层：线路身份、价格币种、无时间戳的本地时间需求、行序缺陷、预测与实测错位；
  - 合理性层：范围检查，见 `value_data_plausibility_v1.json`。
- `profile_eligibility` 决定哪些发现阻断哪个口径：在修正口径下是 preflight 错误，在论文复现口径下只是警告。所以 GBP1 public1 能安装，但在修正口径下不能运行。

**DS-9 第 229 行，“Data and implementation”**
- 口径：U。
- 新：把 `doctoral_demand`、`doctoral_interconnectors` 换为 `series_reader`、`data_method`，并补 `interconnector_identity`、`data_validation_layers`、真相登记表。

### 4.3 `core_weather.md`（第 3 章，en 与 zh 行号相同）

**W-1 第 35 行，代表点小时取值**
- 口径：D 与 C。草稿：p05b §2。
- 旧：“Half-hour period \(t\) uses source hour \(h(t)=\lfloor t/2\rfloor\bmod H\) …”
- 新：论文复现口径（天气 v1）保留旧式。修正口径（天气 v2，`p05.weather-time-convention`，P6-06）为

$$
h(t)=\begin{cases}
\left(\lfloor t/2\rfloor+1\right)\bmod H, & \text{accumulated field stamped at the end of its hour (ERA5 \texttt{ssrd})},\\[2pt]
\left\lfloor (t+1)/2\right\rfloor\bmod H, & \text{instantaneous field (\texttt{u100}, \texttt{v100}, \texttt{wind\_speed})}.
\end{cases}
$$

- binding 可以声明 `time_convention`，否则按 GRIB `stepType` 判定。
- 效果：GBP1 伦敦站光伏质心由 12.97 变为 11.97 UTC；12 月 21 日首个非零时段由 09:00 提前到 08:00 UTC。

**W-2 第 39–53 行，风电曲线**
- 口径：C。草稿：p05b §3，f2 第 4 节披露。
- 新：在第 51 行之后加入损耗系数（`p05.vre-loss-factors`，P6-08，A1，A9）：

$$
a^{\mathrm{corr}}_{w}(v)=\lambda_k\,a_w(v),\qquad
\lambda_{\mathrm{on}}=0.95\times0.97\times0.98=0.90307,\qquad
\lambda_{\mathrm{off}}=0.88\times0.945\times0.98=0.814968 .
$$

- 三个因子依次为尾流、可用率（按电量计）、电气损耗。
- 出处：Simley et al. 2025、Conroy et al. 2011、Colmenar-Santos et al. 2014、Lee & Fields 2021（陆上）；Barthelmie et al. 2009、Warder & Piggott 2025、SPARTA 2017/18（海上）。
- 必须写明以下几点：
  - 不对统计负荷率标定（Q15）；
  - 逐期形状仍来自 ERA5，弃电仍由出清决定；
  - ERA5 自身的风速偏差不是损耗，没有去除；
  - 海上合计损耗约 18.5%，作者已在 A9 认可。
- 第 53 行的数值例子（8 m/s → 0.5476061707）保留为论文复现口径。可以补一个修正口径的例子：0.5476061707 × 0.90307 = 0.4945267046，100 MW 陆上风电可用 49.45 MW。

**W-3 第 55–64 行，光伏曲线**
- 口径：C。草稿：f2 §1。
- 第 58–62 行的 \(a_s(R)\) 保留，作为水平面 GHI（kW m⁻²）：

$$
G_t=a_s\!\left(R_{h(t)}\right).
$$

- 修正口径对 v2 时钟下的 ERA5 逐时累积量做倾斜面换算（`p05.solar-plane-of-array`，A13），再乘性能比 PR = 0.83（A9）。
- 太阳位置按时段**中点**计算。模型年为 365 天 UTC 年：第 \(t\) 期是第 \(\lfloor t/48\rfloor+1\) 天，UTC 时刻为 \((t\bmod 48)/2+0.25\)。赤纬、时差和日地距离修正用 Spencer (1971)。
- 换算公式：

$$
k_t=\min\!\left(1,\max\!\left(0,\frac{G_t}{I_{0n}\cos\theta_z}\right)\right),\qquad I_{0n}=1.361\,E_0\ \mathrm{kW\,m^{-2}},
$$

$$
k_d=\begin{cases}
1-0.09\,k_t, & k_t\le0.22,\\
0.9511-0.1604\,k_t+4.388\,k_t^2-16.638\,k_t^3+12.336\,k_t^4, & 0.22<k_t\le0.80,\\
0.165, & k_t>0.80,
\end{cases}
\qquad D_t=k_dG_t,\quad B_t=G_t-D_t,
$$

$$
G^{\mathrm{POA}}_t=B_tR_b+D_t\left[A_iR_b+(1-A_i)\frac{1+\cos\beta}{2}\right]+G_t\,\rho\,\frac{1-\cos\beta}{2},
\qquad R_b=\frac{\max(\cos\theta,0)}{\cos\theta_z},\quad A_i=\frac{B_t/\cos\theta_z}{I_{0n}},
$$

$$
\beta=1.3793+\phi\left(1.2011+\phi\left(-0.014404+0.000080509\,\phi\right)\right)\ [^\circ],\qquad \rho=0.2,
$$

$$
a^{\mathrm{corr}}_{s,t}=\min\!\left(\mathrm{PR}\cdot G^{\mathrm{POA}}_t,\ 1\right),\qquad \mathrm{PR}=0.83 .
$$

- 各式说明：
  - \(k_d\) 用 Erbs, Klein & Duffie (1982)；
  - 斜面换算用 Hay & Davies (1980)，地面反照率 \(\rho=0.2\)，朝南；
  - 倾角 \(\beta\) 用 Jacobson & Jadhav (2018) 的北半球拟合式，\(\phi\) 为站点纬度（度），GBP1 各站约 35.7–37.7°；
  - 天顶角大于 87° 或 \(G_t=0\) 时 \(B_t=0\)，全部按各向同性散射处理；
  - 倾角为 0 时，逐期精确返回 GHI（已测试）。
- **不换算的情形**：不是 v2 ERA5 累积量的光伏源，修正口径取 \(a^{\mathrm{corr}}_{s,t}=0.83\,G_t\)，不封顶。具体是：
  - VALUE 101 的合成样本；
  - R029 public1：`ssrd` 没有 GRIB step type，也没有声明时间约定。
- 状态：模型选择（Spencer、Erbs、Hay–Davies、反照率 0.2、Jacobson–Jadhav 倾角、87° 截止）仍为 **PENDING AUTHOR REVIEW**（参考统计表 3.5 节）。0.4 正文要么标注“待作者审核”，要么等作者审核后再发布。
- 披露：GBP1 是 2020–2024 多年平均气候态（P6-09），平均后晴空指数被抹平，倾斜增益偏小。f2 §1 末段可直接使用。

**W-4 新增小节 “Capacity factors compared with DUKES / 容量因子与 DUKES 对照”**
- 位置：放在第 120 行之后，“Annual wind and solar capacity limits” 之前。口径：C（披露）。草稿：f2 §4，表格和六条原因都可以直接使用。
- 状态：DUKES 对照列在参考统计表 3.4 节中仍标 PENDING。表中风电合计行 2020、2021 年的值与分项不符，没有使用。
- 中文版的表格行列须与英文版一致。

**W-5 第 122–133 行，“Annual wind and solar capacity limits”**
- 口径：两者（设计假设 S9）。
- 新：补披露：投资侧技术平均曲线 `sa.csv`、`wa.csv`、`we.csv` 没有乘损耗系数，形状和水平都与调度侧天气不同（Q15）；下一轮统一。

**W-6 第 164 行，R029 2025 年的 1,878 个负净需求时段**
- 口径：需确认。
- 这是用 0.6.0-alpha.2 时期的实现算出的数值（天气 v1）。在 0.7.0 的修正口径下，这个数会变。0.4 中要么标注“computed with the 0.6.0-alpha.2 implementation”，要么重算（第 9 节第 1 条）。

**W-7 第 166–168 行，“Data and implementation”**
- 补 `site_weather.py`、`solar_irradiance.py`、`firm_availability.py`、`data/weather/value_uk_vre_loss_factors_v1.json`、`vre_cf_disclosure.py`。
- 可选：补一句，说明天气缓存按文件作键（P7-02，U）。
- 补一句历史运行公告（p05b §7）：没有应用这些修正的 ERA5 运行，读取时附公告。

### 4.4 `core.md`（第 4 章：staged 市场、通用投资、成本；en 行号 = zh 行号 + 1）

**K-1 第 43/42 行，日前按“价格、报价标识”排序**
- 口径：staged。不改。
- staged 日前阶段仍按 `(price, offer_id)` 排序（`staged_psm.py` 第 1079–1085 行）。审查 P3-18 不在 P0 范围。

**K-2 第 49/48 行，“Any ahead shortfall is recorded and passed to the realisation stage”**
- staged 不改。
- 默认 PSM 在这一点上不同（A2），写在第 5 章 N-8。不要在这里写成全局规则。

**K-3 第 51/50 行，下调容量“价格取弃电成本的相反数，缺省为 0”**
- 口径：staged，只在修正口径下运行（`p08.dec-economic-pricing`）。草稿：p08 §1。
- 新：下调报价按经济价格。接受的下调报价按 \(x\,p^{\mathrm{dec}}\) 退款，平衡目标中对应项为 \(-p^{\mathrm{dec}}x\)，最高的下调价先被接受：

$$
p^{\mathrm{dec}}_{a,t}=\begin{cases}
m_{\mathrm{dec}}\,SRMC_a-s_a, & \text{fuel units (gas, coal, biomass, oil)},\\
m_{\mathrm{dec}}\,p_{a,t}, & \text{imports},\\
-s_a, & \text{wind, solar, run-of-river hydro},\\
m_{\mathrm{dec}}\,SRMC_a-s_a-\pi_a, & \text{nuclear}\ (\pi_a=100\ \text{GBP/MWh by default}),\\
\min\!\left(p^{\mathrm{up}}_{a,t}\,\eta^c_a\eta^d_a,\ \min_k p^{\mathrm{up}}_{k,t}\right), & \text{storage}.
\end{cases}
$$

- 参数：
  - \(m_{\mathrm{dec}}\) 为 `market.dec_multiplier`（默认 1，且 \(m_{\mathrm{dec}}\le m\)）；
  - \(s_a\) 来自 `market.policy_support_gbp_per_mwh_by_technology`（未列出的技术为 0）；
  - \(\pi_a\) 来自 `network.inflexible_dec_premium_gbp_per_mwh_by_technology`。
- 写明后果：被下调的燃气机组恰好退回它节省的运行成本，不再有横财。

**K-4 第 58/57 行，“Storage downward bids are priced at 0.”**
- 新：使用 K-3 的储能一行。

**K-5 第 60/59 行，“Identifiers break price ties …”**
- 口径：staged（`value-copperplate-balancing` 1.1.0，`p08.pro-rata-ties`、`p08.dec-class-order`）。
- 新：同价、同方向、同类别的报价按可用电量比例分配：

$$
\frac{x_k}{\overline x_k}=\frac{x_{k_0}}{\overline x_{k_0}}\qquad\text{for all }k\text{ in the tie group of }k_0 .
$$

- 跨类别的次序：
  - 上调：价格升序；同价时储能排在发电之后（Q8）；
  - 下调：按取整到 0.01 £ 的下调价降序，再按共享类别次序（燃料机组 → 进口 → 储能充电 → 径流水电 → 风光 → 核电），最后按精确价格。
- 写明后果：改名不会改变调度；储能在风光被弃之前先吸收盈余。

**K-6 第 94–119/93–118 行，动态储能报价**
- 公式作为模块定义保留。补充以下内容：
  - 修正口径的默认 PSM 中，`dynamic-annual-storage-cost` 2.0.0 只报循环折旧（`p06.storage-bid-cycle-only`，Q8）：

$$
p_s=c_{\mathrm{cycle}}\ \ (\text{batteries}),\qquad p_s=0\ \ (\text{pumped hydro, hydrogen}),\qquad \text{oldest tranche first}.
$$

  - \(h_{\mathrm{hold}}\) 仍计算并报告，但只用于投资充足性诊断（`storage_recovery` v2），不进入报价，也不进入投资决策。
  - legacy 电价、用户公式和外部储能模块保留各自的报价（`module_defined`）。
  - 论文复现口径的参考配置是 legacy 电价；它的白名单不包含 dynamic 模块。

**K-7 第 119/118 行，“The current staged caller passes a holding time \(d=0\) …”**
- 补 P5-15 披露（`p06.staged-dwell-disclosure`）：staged 储能报告记 `dwell_source = not_tracked_staged_single_pool`；与基于 dwell 的成本模块搭配时，preflight 给出警告 `GF_STAGED_DWELL_NOT_TRACKED`。数值不变。

**K-8 第 121–131/120–130 行，储能固定运维表**
- 表保留（它是报价年成本 \(A\) 的输入）。
- 补一句（A7）：成本账中风光储 FOM 是备忘项，不进头条，也不在投资决策中扣除。

**K-9 第 135–167/134–166 行，“Current storage expansion limit”**
- 口径：D 与 C。草稿：p07 “Storage expansion headroom”（只有文字，下面的公式需要新写）。
- **论文复现口径（D，Q1 冻结）**：第 137–141 行原式保留。须补一句：在默认 PSM 中，接纳的 VRE 从不超过需求，所以 \(X_t\equiv0\)，储能余量恒为 0；三种电池各拿 \(0.20B(365)\)，合计 3 倍。
- **修正口径（C，`p07.storage-leftover-headroom`、`p07.power-battery-pool`，`value-storage-expansion-policy` 5.0.0）**：

$$
X_t=\max(L_t,0),\qquad L_t=XS_t+W^{\mathrm{VRE}}_t,\qquad
N_t=\max\!\left(\max(D_t-G_t,0)-d_t,\ 0\right),
$$

  - \(L_t\) 是现有储能充电之后剩下的盈余，由 PSM 逐期发布为 `storage_headroom_inputs`；在修正规则集的列语义下，它等于非 VRE spill \(XS_t\) 加 VRE 弃电 \(W^{\mathrm{VRE}}_t\)；
  - \(G_t\) 是 VRE 毛出力（修正口径列语义）；
  - \(d_t\) 是现有储能放电。
  
  虚拟储能和 \(B(h)\) 与 en 第 145–165 行（zh 第 144–164 行）相同。功率电池和氢储的上限为

$$
H^{\mathrm{bat}}=f\,B(365),\qquad H^{\mathrm{H_2}}=f\,\max\!\big(B(0)-B(52),0\big),\qquad f=\texttt{expansion.storage\_cap\_fraction}.
$$

  - \(B(365)\) 等于代码中的 daily_loop 加 intraday 两段，即 0.3 第 165 行的“日”与“跨日”两段之和。
  - 1C、0.5C、0.25C 三种电池**共用** \(H^{\mathrm{bat}}\)：先收集各自的请求 \(r_{k}\)，按技术上限 \(H_k\) 缩放，再按池上限缩放（`allocate_capped_requests`）：

$$
r'_{k}=r_{k}\min\!\left(1,\frac{H_k}{\sum_{j\in k}r_{j}}\right),\qquad
\Delta P_{k}=r'_{k}\min\!\left(1,\frac{H^{\mathrm{bat}}}{\sum_{k'\in\mathrm{pool}}r'_{k'}}\right).
$$

  - 年度时钟不是 17,520 个半小时时，余量为 0，原因记 `partial_year_chronology`。PSM 没有给出序列时，余量为 0，原因记 `leftover_trace_unavailable`。staged、PF、DC 目前不发布这条序列，所以在修正口径下，这些 PSM 的储能扩容关闭，并记录原因（M5-P0-7 偏差 3）。

**K-10 第 179/178 行，运营成本字段**
- 口径：U。草稿：p07 “Net revenue”。
- 旧：“Operating-cost field \(O_a\) comes from `annual_operational_cost_gbp` and defaults to 0.”
- 新（`p07.thermal-net-revenue`，A4，agent-investment 3.0.0）：

$$
O_a=\begin{cases}
Q_a\left(c^{\mathrm{gen}}_a+c^{\mathrm{fuel}}_a+c^{\mathrm{carbon}}_a+c^{\mathrm{time}}_a\right), & a\ \text{thermal: gas, biomass, or any asset with a fuel or carbon cost},\\
0, & a\ \text{VRE or storage (thesis assumption, A4/A7)}.
\end{cases}
$$

  - \(Q_a\) 是年发电量（MWh）。它和各成本分项都来自 PSM 的 `value.agent-cashflow/v1` 扩展。
  - 可决策的火电分组缺少这一扩展时，运行报错，不按 0 处理。
  - 收入 \(I_a\) 仍取 PSM 的 `market_income_gbp_by_agent`。
  - 火电分组的舍入吸收：

$$
\pi\leftarrow 0\quad\text{if}\quad |\pi|\le10^{-9}\max(|I|,O).
$$

  - 写明后果：电价等于边际成本时，CCGT 既不扩容也不退役。
  - 写明这条规则来自原 Scheme C（`runtime_compat/modular_investment_support.py` 第 2150–2152、2246–2247 行）；v2 移植时丢失。它是 Q1 冻结的例外，两个口径都适用。

**K-11 第 181–184/180–183 行，\(\pi=I-O\)、ROI、PB**
- 公式形式不变。
- 紧接其后加 A6 说明：金额以起始年不变币值计价；ROI 与 preferred_rate、回收期与目标年限都不折现，是模型规则，不是 NPV 检验的近似；不引入 NPV 或 IRR。p07 草稿第一节可直接使用。

**K-12 第 186/185 行，退役与投资分档**
- 分档不变。
- 补储能投资审核（设计假设 S6，A8(3)(4)）：

$$
I^{\mathrm{sto}}=\sum_t\lambda_t\,q^{\mathrm{dis}}_t\Delta-\sum_t p^{\mathrm{ch}}_t\,q^{\mathrm{ch}}_t\Delta,\qquad
ROI^{\mathrm{sto}}=\frac{I^{\mathrm{sto}}}{C^{\mathrm{sto}}},
$$

  - \(\lambda_t\) 是出清价（修正口径下是统一边际价，C15）；
  - 默认 PSM 中储能只用盈余充电，所以 \(p^{\mathrm{ch}}_t=0\)（设计假设 S7）；
  - \(C^{\mathrm{sto}}\) 是整体 CAPEX；
  - 不扣循环成本，不另扣 FOM，不折现；
  - 扩容上限由物理利用率决定，不启用 `tier_roi`。
  - 实例：C6（修正口径，dynamic）2026 年，1C 电池 ROI 0.042，回收期 23.9 年，判 Invest_Profit，新建 0.418 MW（M5-P0-7-S10 报告第 3.4 节）。

**K-13 第 189–192/188–191 行**
- 补一句：CCGT、OCGT 仍不受余量约束。A4 生效后，电价等于边际成本时不会再按毛收入扩容。

**K-14 第 198–209/197–208 行，“Costs and emissions”**
- 第 200–205 行，口径 U 加 C（`p07.cost-ledger-v2`、`p07.compatibility-capital-out-of-headline`），旧式 \(C_{system}=C_{capital}+C_{fixed}+C_{operation}\) 改为：

$$
C^{\mathrm{head}}=C^{\mathrm{cap}}+C^{\mathrm{fix}}_{\neg\mathrm{VRE,sto}}+C^{\mathrm{op}}_{\mathrm{phys}}
\;\big[+\,C^{\mathrm{compat}}_{\mathrm{RoR}}\ \text{doctoral only}\big],
$$

  - 备忘项为 \(C^{\mathrm{fix}}_{\mathrm{VRE,sto}}\)（两个口径），以及 \(C^{\mathrm{compat}}_{\mathrm{RoR}}\)（修正口径不计入头条；论文复现口径计入头条，并把备忘项标为 included）；
  - \(LC_{\mathrm{served}}=C^{\mathrm{head}}/(D-U)\)；
  - \(C^{\mathrm{op}}_{\mathrm{phys}}\) 的定义见第 5 章 N-12；
  - 账本 schema 为 `value.annual-cost-ledger/v2`，成本定义 id 仍是 `value.cem-system-resource-cost/v1`（M5-P0-7 偏差 6）。
- 第 207/206 行：
  - 旧：“Zonal constraint expenditure is attributed through the difference between zonal and copperplate operation …”
  - 新：网络约束成本 = 分区解 − 无网络反事实。两者是同一个 LP，去掉网络（单节点），使用同一张逐期单价表（C22，见第 7 章 T-4）。
- 第 209/208 行，可靠性费用：补一句：默认 PSM 的物理运营成本含“记录的切负荷 × VoLL”，两个口径的 VoLL 都是 17,000 £/MWh（A16-5）：论文复现口径为常数 17,000（论文代码原为 8000），修正口径为 `market.voll_gbp_per_mwh`（默认 17,000，原为 10000）；在网络成本比较中，两个情形都按 VoLL 计入缺电。

**K-15 第 222–224/221–223 行，“Data and implementation”**
- 补 `agent_cashflow.py`、`investment_accounts.py`、`storage_headroom.py`、`cost_ledger.py`（v2）、`network_method_rules.py`。

### 4.5 `national_alternatives.md`（第 5 章；第 82 行之前 en 与 zh 行号相同，之后 zh = en − 2）

**N-0 第 3 行，章首段**
- 口径：两者。
- 新：加入第 2.2 节建议的两句话：Native 即默认 PSM，按口径运行两套规则集；Doctoral 是另一个实验模块。

**N-1 第 9–15 行，成本组成与报价式**
- 不改。
- 可以补一句：物理运营成本中的 \(c_i\) 不乘 \(m\)，见 N-12。

**N-2 第 24 行，“creates new agents each year … Physical inventory follows the initial state of the newly created objects.”**
- 口径：两者（DEV-BAL-03）。
- 新：补一句：年末储存的电量随旧对象一起丢弃，记在 `storage_year_boundary`；是否跨年结转，P1 再定。

**N-3 第 30–32 行，Native 可用出力**
- 第 32 行：
  - 旧：“Hourly values are repeated for two half-hour periods, following the compatibility clock.”
  - 论文复现口径保留。
  - 修正口径：内核不再按自己的 `IterLimit` 时钟重读天气文件，而是接收 `site_weather.site_cf_by_source` 给出的逐期容量因子（与 canonical 适配器同一组数组，`kernel_injection.KernelSiteInputs`）：

$$
\overline g_{j,t}=K_j\,a^{\mathrm{corr}}_{j,t}.
$$

  - 风电按 20 MW 单位乘倍率 \(K_j/20\)，光伏按 1 MW。天气 v2、损耗系数和倾斜面换算都已含在 \(a^{\mathrm{corr}}\) 中。
- 互联线序列在两个口径下都逐期取值（U1）。

**N-4 新增一段：核电与径流水电可用率**
- 位置：第 32 行之后。口径：C；论文复现口径为 100% 可用。草稿：p05b §4（数值以 f2 为准）、f2 §2–3。

$$
a^{\mathrm{nuc}}_{n,t}=\min\!\left(1,\ \frac{\ell_n\,P^{\mathrm{PRIS}}_n}{K_n}\right)\cdot\mathbf 1\!\left[t<t^{\mathrm{end}}_n\right],\qquad
a^{\mathrm{nuc}}_{N,t}=\frac{\sum_{n\in N}K_n\,a^{\mathrm{nuc}}_{n,t}}{\sum_{n\in N}K_n},
$$

  - \(\ell_n\)：各站 PRIS 2019–2024 平均负荷率。Heysham 1 0.668、Hartlepool 0.689、Heysham 2 0.752、Torness 0.792、Sizewell B 0.801。作者已在 A14 审核。
  - \(P^{\mathrm{PRIS}}_n/K_n\)：把 PRIS 参考功率折算到模型容量，以保持电量。
  - \(t^{\mathrm{end}}_n\)：在宣布停发的年份，取停发月份次月的第一期。四座 AGR 都是 2030 年第 4,320 期，即 4 月 1 日 00:00 UTC（A10，`p05.nuclear-generation-end-month`）。
  - 内核只有一个 `Nuclear` 代理，它得到成员资产按容量加权的可用率。
  - 回退值：在建 PWR/EPR 取 0.801；未分站的 `Nuclear` 资产取 DESNZ 全国值 0.723；AGR 默认值 0.727。

$$
a^{\mathrm{RoR}}_{t}=0.3487\cdot s_{m(t)},\qquad
s=\left[1.3851,1.3851,1.3851,0.6582,0.6582,0.6582,0.6776,0.6776,0.6776,1.2791,1.2791,1.2791\right].
$$

  - 0.3487 是 DUKES 6.3 标准口径 2019–2024 均值。季节形状由 Energy Trends 6.1 的季度数据推出，12 个月算术均值为 1（A14，`p05.hydro-dukes-load-factor`）。
  - 按 365 天加权，形状均值为 0.99883，模型年负荷率为 0.3483。GBP1 的 2,000 MW 一年发电 6.10 TWh，比 DUKES 6.2 的 5.77 TWh 高 5.8%，在 ±15% 以内。
  - 未应用 A14 的运行使用 P0-5b 临时值（0.334，平直形状）。
- **数据包限制，必须写明**：逐站规则只作用于 `NUCLEAR_POLICY_PACK_IDS` 中的包（`pack_source_identity.py` 第 121 行），目前只有 GBP1 public1，而 GBP1 public1 不满足修正口径的资格。public2 和 R029 上，核电按单一资产取回退值 0.723。见第 9 节第 2 条。
- 验收：核电对 Energy Trends 5.1 的 ±10% 验收**还没有运行**；GBP1 修正口径的全年运行也没有做。只能写成“机制与参数”，不能写成“已验证”。

**N-5 第 34–44 行，Native 批次与充电**
- 论文复现口径（D，DEV-STO-01）：保留原文“每个阶段分别构造功率预算”。须补明后果：同一时段可以既充又放，单期放电可达 \(2P_b\Delta\)。
- 修正口径（C，`p06.storage-net-per-period`，P5-03）：每个储能每期只有一个净头寸：

$$
\sum_{\sigma\in\{\mathrm{ahead},\mathrm{bal}\}} q^{\mathrm{dis}}_{b,t,\sigma}\le P_b,\qquad
q^{\mathrm{dis}}_{b,t}\,q^{\mathrm{ch}}_{b,t}=0,\qquad
0\le s_{b,t}\le E_b .
$$

  - 已经放电的储能，先回购（先满足需求，再用盈余），之后才能充电；
  - 已经充电的储能，当期不再报放电；
  - 售电按净头寸记录；
  - `close_period` 检查上述三个不变量。

**N-6 第 46–52 行，按批次年龄的动态报价**
- 论文复现口径保留原式（实际上论文复现口径的参考配置用 legacy 电价）。
- 修正口径：

$$
b_{b,k,t}=m\,c^{\mathrm{cycle}}_b\ \ (\text{batteries}),\qquad b_{b,k,t}=0\ \ (\text{pumped hydro, hydrogen}).
$$

  - 最老的批次先卖；持有回收不进入报价（`p06.storage-bid-cycle-only`）。
- 第 52 行 “Positive holding fees make newer batches cheaper” 只适用于论文复现口径。

**N-7 第 56–62 行，Native 出清**
- **排序键（C，`p06.storage-after-generation-merit-key`）**：日前和平衡阶段都用

$$
\kappa_i=\big(\mathrm{round}(b_i,2),\ \mathbf 1[i\in\mathcal S],\ b_i,\ \text{input order}\big),
$$

  即同一 0.01 £/MWh 档内，储能排在发电之后，零价储能不能挤掉报价 0.0001 的风电。论文复现口径按价格稳定排序。
- **D1-surplus（C，`p06.d1-surplus-accounting`）**：日前结束后，按“可用 − 接受”逐来源重建盈余簿：
  - 必发盈余在调度内，先被使用；
  - VRE 盈余被储能、出口或柔性负荷消耗时，计为 VRE 毛出力；
  - 平衡阶段不再重复计入必发盈余（论文复现口径为 DEV-BAL-04）。
- **核电路径依赖（D 必写，A15）**：第 62 行之后新增一段。草稿：无。事实来源：`GBP1_DOCTORAL_BEFORE_AFTER.md` 第 6 节；`modular_simulation_model.py` 第 1593–1640、1728–1733 行。
  - 机制：内核把核电当作不能降出力的机组，接受量为 \(\max(g_{t-1}-r,L)\)。一旦被接受，下一期的出发点仍是满出力，所以会一直满功率运行到年底。没有被接受的时段，记忆出力 \(g\) 每期乘 0.99。
  - GBP1 实例（第一年）：35aadb3 中，核电从第 16,588 期（约 12 月 12 日 14:00 UTC）开始被接受，此后运行 932 个时段，发电 2.73 TWh；全年 30 个超过 1000 £/MWh 的时段都在这个窗口里。读取修正（A3/A5）之后，核电全年没有被接受，价格尖峰随之消失。
  - 写明两点：这不是针对核电的修正，而是冻结内核对边界输入敏感的表现；复现结果的核电与价格尖峰可能随输入的微小变化而整段出现或消失。
  - 修正口径共用同一段日前接受代码，但修正口径有核电降额（N-4），并且下调次序带 100 £/MWh 的核电溢价（N-9），后果不同。这一点在修正口径下的量级没有测量；写进修正口径部分之前请代码负责人确认（第 9 节第 6 条）。

**N-8 第 64–80 行（zh 第 64–78 行），伪代码**
- 按规则集标注以下改动，或者给出两份伪代码：
  - **出清前 VRE 分流**：论文复现口径每个 VRE 代理最多分 1 MW 去电解，电解容量不足时这部分能量丢失（P3-08，诊断 `vre_skim_*`）；修正口径没有（`p06.no-vre-pre-clearing-skim`）。
  - **“储能先吸收预测多发，再吸收已有过剩电量”**：修正口径改为“先回购，后充电”（N-5）。
  - **“then apply downward dispatch”**：修正口径改为按避免成本下调（N-9）。
  - **进口（C25，A16-2）**：“Construct generator and storage-batch offers” 与 “import offers” 两处按草稿 `fx6_day_ahead_imports.md` 第 3 节改写；论文复现口径的进口只出现在平衡分支（GBP1 D5 的 0.336 TWh 全部来自实际需求高于预测的时段），修正口径的日前出清也接受进口，平衡分支只报剩余容量。
- **新增一段：隐藏缺电与 stress event（U，A2，DEV-BAL-02）**：
  - 平衡分支按 \(D_t\) 与 \(\widehat D_t\) 的比较选择。当日前接纳供给不足以满足预测、且 \(D_t<\widehat D_t\) 时，削减分支仍按 \(\widehat D_t-D_t\) 削减，而真实需求并没有被满足；内核不记录切负荷。
  - 两个口径的**调度都不变**。缺口记账见 N-13。

**N-9 第 84/82 行，下调后的自然预算返还**
- 论文复现口径：保留“Native 只处理水电”。削减市场按 `curtail_cost` 升序，先弃零边际成本的风电，燃气继续运行（P3-03）。
- 修正口径（`p06.avoided-cost-downward-order`）：

$$
v_i=\mathrm{round}\!\left(c_i-\pi_i,\,2\right),\quad \pi_{\mathrm{nuclear}}=100,\ \pi_{\mathrm{other}}=0;\qquad
\text{reduce in order of}\ \big(-v_i,\ \mathrm{rank}(i),\ \mathrm{name}_i\big),
$$

  - 类别次序：thermal 0、hydro/biomass 1、VRE 2、nuclear 3；日前接受的进口（C25）按进口避免成本（对侧价格）参与，类别次序 0.5，即排在 thermal 之后、hydro/biomass 之前，不付削减费；
  - 爬坡下限 \(\max(g_{i,t-1}-r_i,0)\)，上期出力按对象身份读取；
  - 水电和生物质的削减量都返还预算；
  - 下调次序用完后仍剩的要求，记为调度内 spill。

**N-10 第 86/84 行，结算**
- 论文复现口径：保留原文。发电与储能分别统一定价；储能按自身最高报价 `max_bat_price` 结算；没有发电机被接受时，收入函数返回空映射。
- 修正口径（`p06.storage-uniform-price-settlement`，A8(2)，P5-05）：每个阶段所有被接受的供给（含储能和进口）按同一个边际价结算，报价只决定调度顺序：

$$
\lambda^{A}_t=\max_{i\in\mathcal A^{A}_t} b_i,\qquad R^{A}_{i,t}=g^{A}_{i,t}\,\Delta\,\lambda^{A}_t\quad\forall i\in\mathcal A^{A}_t,
$$

$$
\lambda^{B}_t=\max\!\left(\lambda^{B}_{\mathrm{gen},t},\ \lambda^{B}_{\mathrm{sto},t},\ \max_{k\in\mathcal I^{B}_t}p^{\mathrm{imp}}_{k,t}\right).
$$

  - 储能费在本期结算，不再结转（`p06.storage-fee-per-period`）。

**N-11 第 88–93/86–91 行，显示价格**
- 公式不变。
- 加标签（Q6）：显示为 “Average period cost (£/MWh demand)”，它是时段总费用除以需求，不是边际出清价。
- 修正口径下，\(F_t\) 不含跨期结转的储能费。

**N-12 第 95/93 行，年度运行费用**
- 口径：U（核算）。草稿：p06 “Physical operating cost”。
- 旧：“Annual operating expenditure is \(\sum_tC_t^{reported}\) plus reported current-cycle depreciation …”
- 新（`p06.physical-operating-cost`、`p06.voll-chronology-parameter`）：

$$
C^{\mathrm{op}}_{\mathrm{phys},y}=\sum_t\Big[\sum_i c_i\,g_{i,t}\Delta+\sum_k p^{\mathrm{imp}}_{k,t}M_{k,t}+\sum_i s_i\,g_{i,t}\Delta\,\mathbf 1[i\notin\mathcal A_{t-1}]\Big]+V\sum_t B_t+W^{\mathrm{cyc}}_y .
$$

  - \(c_i\) 不乘 bid multiplier。
  - 启动加价单列为 `startup_adder_resource`。
  - \(B_t\) 是**记录的**切负荷。stress 缺口不进头条，单独报告。
  - \(V\)：17,000 £/MWh（A16-5）。论文复现口径为常数 17,000（论文代码原为 8000）；修正口径为 `market.voll_gbp_per_mwh`，默认 17,000（原为 10000）。
  - \(W^{\mathrm{cyc}}\) 是储能成本模块报告的当年循环折旧。
  - 储能报价支付（已含循环损耗）作为结算转移单列（`market_settlement_components_gbp`）。修复前它被计入运营成本，循环损耗被重复计入。

**N-13 第 97–108/95–106 行，原始残差与兼容调整**
- 口径：U（核算）。整段替换为 p04 草稿 “Declared boundary and the raw residual” 与 “Stress events and the energy-balance account”。草稿有中英全文，公式如下：

$$
r_t = S_t + B_t + U^{out}_t - W^{in}_t - D_t - C_t - E_t - X_t\quad(\texttt{default\_psm\_surplus\_node\_v1},\ \text{doctoral}),
$$

$$
r_t = S_t + B_t - D_t - C_t - E_t - X_t - XS_t\quad(\texttt{native\_corrected\_full\_node\_v1},\ \text{corrected}),
$$

$$
u_t=\max\!\big(0,-(r_t-B_t)\big),\qquad \mathrm{closing}_t=r_t-B_t+u_t .
$$

  - 兼容调整只吸收数值噪声：当 \(10^{-9}<|r_t|\le\tau_t\) 时 \(a_t=-r_t\)，否则为 0；\(\tau_t=\max(10^{-6},10^{-9}\max(D_t,S_t))\)。
  - stress 时段：只有需求未满足这一种缺陷、因此闭合的时段。同一年内连续的 stress 时段构成一个 event。年度汇总给出事件数、stress 时段数和总缺口。
  - 可以引用 GBP1 第一年的数字：157 个事件、890 个时段、缺口 300,855 MWh。
- 另外从 p04 草稿 “Validation gates” 中取三类 gate 和已声明偏差表。这部分可以放在第 5 章本节末尾，也可以放进第 1 章新小节；两版放在同一位置。

**N-14 第 110–214/108–212 行，Doctoral 路径**
- 算法没有 P0 改动。在第 110/108 行之前加一句（第 2.2 节）。
- P0-6 的 D1-surplus、D1-shortfall、D1-power 参照了这个模块的内核（计划第 1063 行），可以作为交叉对照提及。
- 局限：这个 PSM 不发布 `value.agent-cashflow/v1`，与 agent-investment 组合、且有可决策的火电时，运行会在决策处报错（M5-P0-7 遗留问题）。
- 修正口径的 P0-5b 输入是否作用于这条路径，须确认（第 9 节第 1 条）。

**N-15 第 216–218/214–216 行，“Data and implementation”**
- 补 `native_market_rules.py`、`native_corrected.py`、`native_realisation.py`、`native_balance_audit.py`、`energy_balance_contract.py`、`energy_balance_oracle.py`、`kernel_injection.py`、`kernel_boundary.py`、`firm_availability.py`、`storage_headroom.py`。

### 4.6 `r029_cem.md`（第 6 章；第 120 行之后 zh = en − 2）

**R-1 第 3 行，R029 研究**
- 口径：需确认。
- R029 数据包（`value-uk-calendar-vx-trade001`）不在论文复现口径的白名单中，所以 0.7.0 中 R029 研究只能用修正口径运行（P0-5 Q4：修正口径的默认全国包是 R029 public1）。
- 0.4 须写明 R029 按哪个口径运行，以及哪些口径受控修正作用于 thesis96 路径。例如 R029 public1 的光伏不做倾斜面换算。确认后再写（第 9 节第 1 条）。

**R-2 第 39–68 行，年度账户与决策单位**
- 口径：两者，不改公式。
- R029 的 \(S_a\) 已扣 \(O^{var}_a\) 和 \(F_a\)，与 A4 一致。
- A6 的说明要区分两条规则：
  - R029 规则以年度资本费用 \(A_i\)（股权按 \(E/L\) 回收，债务按 5% 利率付息还本）作为比较基准，这是融资成本，不是对未来收入折现；
  - 第 4 章的 agent-investment 用 \(ROI=\pi/C\)。
  - 不要把两者写成同一条规则，也不要改成 NPV。
  - 若作者希望在第 1 章统一表述 “undiscounted”，请让作者确认措辞（第 9 节第 7 条）。

**R-3 第 94–104 行（两版相同）**
- 不改。“Charging procurement … are 0” 与设计假设 S7 一致。

**R-4 第 211/209 行，VoLL**
- 旧：“unserved energy valued at £8,000/MWh … VoLL supplied by the run configuration”。
- 新：与 N-12 对齐：
  - 论文复现规则集为常数 17,000（A16-5；论文代码原为 8000）；
  - 修正口径为 `market.voll_gbp_per_mwh`（默认 17,000；原为 10000）；
  - 分区为 17,000；
  - 完全预见默认 10,000。

**R-5 第 252/250 行，核电日程**
- 旧：“… Heysham 1, Hartlepool, Heysham 2 and Torness … withdraw from model year 2031 …”
- 新：
  - 论文复现口径：2030 年全年满额，2031 年退出；
  - 修正口径：凡按站建模的数据包，四座 AGR 在 2030 年第 4,320 期起为 0，并且全年按负荷率降额（N-4）。
  - 这一条是否作用于 R029，取决于第 9 节第 2 条的确认结果。

**R-6 第 271–279/269–277 行，2025 年 CCGT 退役例子**
- 数值来自 0.6.0-alpha.2 时期的运行（`2025/year-result.json.gz`，实现依据 2026-10-02）。
- 0.4 中要么注明 “computed with the 0.6.0-alpha.2 implementation”，要么在 0.7.0 上按确定的口径重算（第 9 节第 1 条）。

### 4.7 `transmission.md`（第 7 章，en 与 zh 行号相同；只在修正口径下运行）

**T-1 第 29–35 行，目标函数**
- 口径：C21，`p08.dec-class-order`。
- \(J_3\) 加入类别权重：

$$
J_3=\sum_s(c_s+d_s)+\sum_lh_l+\sum_{k\in\mathcal K^{\mathrm{down}}\setminus\mathcal S}w_{c(k)}\,x_k,\qquad
w_{\mathrm{fuel}}=0,\ w_{\mathrm{import}}=0.5,\ w_{\mathrm{RoR}}=2,\ w_{\mathrm{VRE}}=3,\ w_{\mathrm{nuclear}}=4 .
$$

  - 储能充放电和走廊潮流的权重仍为 1。
  - 写明后果：同价时，一个区内储能充电先于径流水电、风光和核电下调；跨区时，类别权重与走廊潮流的 MWh 相互权衡。

**T-2 第 38 行**
- \(V=17{,}000\) 和 dec 的符号约定不变。
- 补一句：下调报价由 staged PSM 按经济价格构造，见第 4 章 K-3。

**T-3 第 51–54 行，同价比例分配**
- 口径：C20，求解合同 v4。
- 旧：“Ordinary non-storage bids sharing zone, direction, network effect, price and resource class are accepted in proportion …”，以及式 \(\overline x_{k_0}x_k-\overline x_kx_{k_0}=0\)。
- 新：
  - 上调报价按区、方向、网络效应和价格分组，**不再按资源类别分组**；
  - 下调报价的分组键另带下调类别；
  - 下调报价中的强制部分 \(f_k\) 不参与分配。强制部分指资产计划高于其最终出力上界（实际可用量，或互联线包络）而必须让出的量。只有剩余的自由部分按比例分配：

$$
(x_k-f_k)\,\overline x^{\mathrm{free}}_{k_0}=(x_{k_0}-f_{k_0})\,\overline x^{\mathrm{free}}_{k},\qquad \overline x^{\mathrm{free}}_k=\overline x_k-f_k .
$$

- 事实来源：`MATHEMATICAL_REFERENCE.md` 第 171–181 行（已更新）、`docs/scientific-readiness/ZONAL_SOLVER_CONTRACT_V4.md`。
- 注意：英文 “forced part” 含子串 `force`。章节正文不受测试限制，但写进 `VALUE_METHODOLOGY.md` 时必须换词，例如 “mandatory part”。

**T-4 第 82–88 行，费用核算**
- 口径：C22。草稿：p08 §2。
- 新增网络成本定义：

$$
C^{\mathrm{net}}_t=C_t(\text{zonal})-C_t(\text{network-free}),\qquad
J_1(\text{zonal})\ \ge\ J_1(\text{network-free})-\mathrm{tol}.
$$

  - 无网络情形是同一个 LP 去掉走廊和割集，报价、出口包络、储能物理、VoLL 计价的切负荷和求解器设置都相同。
  - 两个情形、资源行和代理运行成本都使用同一张逐期单价表。
  - 因此全国性缺电、逐期进口价和出口套利都不再计为网络成本。
  - 每期报告差值 `network_constraint_bid_objective_gbp`。
- 第 88 行，旧：“The current copperplate balancing result uses the first term of this expression …”。新：两个参照情形（完美预测与实际预测）都是无网络 LP，不再是贪心的 copperplate。
- 补一句：P0-8b 之前记录的网络成本和再调度弃电归因，不能用于研究结论（`VALIDATION_AND_CLAIMS.md` 第 39 行）。

**T-5 第 92 行与第 94–103 行伪代码，数值求解**
- 口径：C20，Q5，`p08.zonal-solver-v4`。
- 旧：“The first stage permits at most 1 GBP of payment-objective degradation per complete period …”
- 新：primary 解出后，先锁定总切负荷：

$$
u_z=0\ \ \forall z\quad\text{if}\ \textstyle\sum_z u^*_z=0,\qquad\text{otherwise}\quad \sum_z u_z\le\sum_z u^*_z .
$$

  然后只对报价成本项加系数感知的数值锁：

$$
J^{\mathrm{bid}}_1(x)\le J^{\mathrm{bid}}_1(x^*)+\tau_1 .
$$

  - \(\tau_1\) 的公式见 `ZONAL_SOLVER_CONTRACT_V4.md` “Numerical lexicographic method”；
  - £1 只作为验收上限；
  - 伪代码 “solve J1 … retaining earlier objective caps” 改为“先锁切负荷，再锁报价成本”。

**T-6 新增一段：边界边际值**
- 口径：C23。草稿：p08 §3。

$$
\lambda_b=-\frac{\partial J_1}{\partial \overline F_b}=m^{\mathrm{rev}}_b-m^{\mathrm{fwd}}_b ,\qquad
\text{annual diagnostic}=\sum_t\sum_b\left|\lambda_{b,t}F_{b,t}\right| .
$$

  - 对偶值只从 primary LP 读取，在加入任何锁定行之前读取。
  - 状态有 `computed`、`degenerate_dual`、`shared_member` 三种。
  - 年度量是诊断量，不是分区电价，也不是现金成本。
  - P0-8b 之前的账本没有计算这个值，显示为 “Not computed”。
  - VALUE 101 NC 边界的值为 66.5 £/MWh。

**T-7 第 107 行，23 区案例**
- 基础数据包的口径资格同 DS-1，须确认（第 9 节第 4 条）。

**T-8 第 140–161 行，DC 网络调度**
- 口径：C24，`p08.network-share-expansion`，P1-01，`value-reference-dc-network` 1.1.0。草稿：无。
- 新增：映射到多个母线的资产，按份额 \(\sigma_{a,n}\) 展开为子资源（\(\sum_n\sigma_{a,n}=1\)，否则报错）：

$$
K_{a,n}=\sigma_{a,n}K_a,\qquad P_{a,n}=\sigma_{a,n}P_a,\qquad E_{a,n}=\sigma_{a,n}E_a,\qquad s^{0}_{a,n}=\sigma_{a,n}s^{0}_a ,
$$

  - 求解后按资产汇总。
  - 修复前，整台资产注入最后一个映射母线。
  - 事实来源：VERSION_LEDGER 中该模块的升版说明、`gridform_core/network_dc.py`、`tests/test_p08_network_shares.py`。

**T-9 第 222–226 行，“Data and implementation”**
- 补以下内容：
  - `network_method_rules`、`value.network-free-lp/v1`、`zonal_results`；
  - 运行期 fallback 审计（P2-13，只报告，不改调度）；
  - 旧账本的派生已知缺陷：`p08.staged-dec-zero-pricing`、`p08.copperplate-counterfactual-mismatch`、`p08.boundary-shadow-not-computed`、`p08.zonal-v3-gbp1-lock`（p08 §4）。

### 4.8 `optional_modules.md`（第 8 章，en 与 zh 行号相同）

**O-1 第 36 行**
- 口径：U11，完全预见只在修正口径下可用。
- 价格加标签：“Balance shadow price”（Q6）。
- 系统成本中的固定运维：
  - 原来读的键 `fixed_om_gbp` 从未被写入，FOM 恒为 0；
  - 现在改读 `annual_fixed_opex_gbp`，并且只计非风光储资产；
  - 风光储 FOM 是备忘项（A7）。

**O-2 第 25 行**
- \(V=10{,}000\) 不改，与 `market.voll_gbp_per_mwh` 默认值一致。

**O-3 第 51–65 行，径流水电模块**
- 不改。
- 补一句：默认 PSM 修正口径中的径流水电，用的是统计负荷率乘季节形状（第 5 章 N-4）。它是声明的统计可用率，不是本章的水文模块。

### 4.9 `appendix.md`（第 9 章）

- 没有 P0 改动。
- 第 3 行提到历史 R029 用其研究配置的因子集；论文复现口径的碳因子情景（`doctoral_reproduction_2026_07_18`）不给物理 tCO2。现有措辞不矛盾，不需要改。

### 4.10 `docs/methodology/VALUE_METHODOLOGY.md`（只有英文）

先看约束：
- 必须保留以下短语：“bid at cost”、“dynamic annual-average”、“planning pipeline”、“fixed zonal”、“redispatch”、“£17,000/MWh”、“scenario_scaled_zonal_shares”、“post-thesis”、“not a security analysis”、“state reads”、“state writes”、“Known limitations”；
- 不得出现 `force`（`tests/test_value_methodology.py`）。

| # | 位置 | 改动 |
|---|---|---|
| V-1 | 第 3 行 | “edition 0.3” 改为 “edition 0.4” |
| V-2 | §2（第 24–38 行）之后 | 新增一小节 “Methodology profiles”，内容为第 4.1 节 I-1 的精简版：两个口径、通用修正与口径受控修正、Q14、方法身份 |
| V-3 | §3 第 42 行 | 把 “The built-in PSM is `value-staged-bid-at-cost-psm`” 改为：默认 PSM 是 `value-bid-at-cost-psm`（两套规则集）；`value-staged-bid-at-cost-psm` 是网络与分区用的分阶段变体。第 48–55 行合同表的 “Configurable parameters” 补上 VoLL 与 dec multiplier |
| V-4 | §4 第 65–71 行 | 默认 PSM 的 VoLL：两个口径都是 17,000（A16-5；论文复现规则集为常数，修正口径为参数，默认 17,000）。新增 stress event 一段（A2，第 4.5 节 N-8/N-13）。保留 “£17,000/MWh” |
| V-5 | §5 第 77–97 行 | 净头寸（修正口径）与 DEV-STO-01（论文复现口径）；储能只用盈余充电（S7）；DEV-BAL-03 年末存量 |
| V-6 | §6 第 99–133 行 | 修正口径的默认 PSM 只报循环折旧，持有回收只用于充足性诊断；A[y] 中的 FOM 只用于报价的年成本，成本账中是备忘项（A7）；staged dwell 披露（P5-15）。保留 “dynamic annual-average” 与 “zero floor reproduces the published thesis-exact rule” |
| V-7 | §7 第 135–145 行 | 修正口径的储能余量（剩余盈余）与功率电池池；论文复现口径余量为 0（K-9） |
| V-8 | §8 第 147–157 行 | A4 火电净收入、A6 不折现、A7 风光储无 OPEX、A8(3)(4) 储能审核（K-10 至 K-12） |
| V-9 | §11 第 183–195 行 | 头条成本按成本账 v2；备忘项；物理运营成本；网络成本 = 分区 − 无网络反事实（第 189 行 “matched unconstrained” 改写） |
| V-10 | §12 第 197–207 行 | 第 207 行 “VALUE does not infer hydrology from installed electrical capacity …” 与修正口径的径流水电统计可用率（N-4）表面上矛盾。改写为：默认 PSM 的径流水电在修正口径下使用声明的统计负荷率与季节形状，不是水文推断；水文域仍需流量数据 |
| V-11 | §13 第 227–242 行 | 求解阶段改为 v4：切负荷锁加报价成本锁。加入下调经济价格、同价比例分配（第 225 行 “There is no hidden physical priority list” 与类别次序要协调措辞）、边界边际值；第 240 行 “matched copperplate counterfactual” 改为 “matched network-free counterfactual”。**不要写 “forced part”** |
| V-12 | §14 第 256–272 行 | 补以下内容：验证 gate；Q14 扣发；价格标签（Q6）；风光 CF 与 DUKES 并列披露（A9）；归档清单加入方法学口径身份 |

### 4.11 `docs/methodology/README.md`

- 版次行、实现依据日期、六个下载链接（文件名中的日期取 `edition.json` 的 `date`）。
- 维护段补一句：0.4 由 `drafts/0.4` 合并而来。

## 5 三份参考文档

这三份文档有测试约束（`tests/test_documentation_consistency.py`）：
- `MATHEMATICAL_REFERENCE.md` 须含 “Version 0.7.0-alpha.1, October 2026”、v4 求解合同的六个关系式、上限句（正则见测试第 76–80 行）、“numerical tolerance does not relax physical feasibility”、“up to 10%”、“above 10% and up to 100%”、“above 100% is”；
- `VALIDATION_AND_CLAIMS.md` 须含 “VALUE Network Extensions 0.7.0-alpha.1 source”；
- 三份文档加 README 合起来，不得匹配以下模式：“globally optimal cem”、“exact reproduction … passes/passed/proven”（80 字符以内）、“public release decision is go”、“smoke proves annual economics”；
- 必须含 “not_evaluated”、“single-node”、“no internal transmission”。

### 5.1 `docs/MATHEMATICAL_REFERENCE.md`

已改：版本行、§2.4 的同价分配与 “Network economics of the staged path (P0-8b)”、“Numerical lexicographic solver contract v4”、§5.1 的参照情形。以下待改。

| # | 位置 | 改动 | 依据 |
|---|---|---|---|
| M-1 | §2.1（第 34–72 行） | 模块 id `scheme-c-psm` 改为 `value-bid-at-cost-psm` 6.0.0。加入两套规则集，以及第 4.5 节的 N-5、N-6、N-7、N-9、N-10、N-12。第 61–62 行 “Dynamic storage orders positive holding-cost tranches newest first” 限定为论文复现口径。加入 A2 stress event 一句 | p06 草稿、C8–C16、U10 |
| M-2 | §2.2（第 74–112 行） | PF 价格标签 “Balance shadow price”；系统成本的 FOM 键（U11） | Q6、A7 |
| M-3 | §2.3（第 114–132 行） | 份额展开（T-8）；模块 id 改为 `value-reference-dc-network` 1.1.0 | C24 |
| M-4 | §3 与 §3.1（第 310–375 行） | 修正口径只报循环折旧；持有回收只用于充足性诊断；staged dwell 披露；`scheme-c-legacy-storage-tariff` 改为 `value-legacy-storage-tariff` | C14、P5-15 |
| M-5 | §4（第 377–397 行） | 模块名：`storage-expansion-scheme-c` 改为 `value-storage-expansion-policy` 5.0.0，`scheme-c-state-transition` 改为 `value-annual-state-transition`，agent-investment 3.0.0。加入 A4 净收入式（K-10）、A6 的四档规则与不折现说明、A7、A8(3)(4)、修正口径储能余量与电池池（K-9） | U6、C17、C18 |
| M-6 | §5（第 428–456 行） | 头条按成本账 v2 写（K-14）。第 446 行碳情景 id 改为 `value_current_authoritative_v1` / `doctoral_reproduction_2026_07_18`（审查 G3-11，顺带修正）。新增 §5.2 “Energy balance, stress events and validation gates”，内容取自 p04 草稿，含 Q14 | U7–U11、C19 |
| M-7 | §7（第 531–545 行） | 模块清单按 `docs/generated/MODULES.md` 的真实 id 重写。测试只要求每个模块 id 在本文或 MODULES.md 中出现 | — |
| M-8 | §8（第 547–563 行） | 补以下“推迟”项：抽蓄和氢储没有水价（修正口径）；储能不能从市场购电；论文源规则版（thesis-source）口径留到下一轮（Q1）；DEV-BAL-03 是否跨年结转（P1）；A15 surplus conservation 的调查；投资侧与调度侧天气的统一（Q15） | — |

### 5.2 `docs/SCHEME_C_MODEL_CARD.md`

已改：第 15–49 行（口径、A15、已知简化），以及第 87–123 行（投资规则、P0-6、P0-5b、F2）。以下待改。

| # | 位置 | 改动 |
|---|---|---|
| MC-1 | 第 74–80 行 | 第 76 行 `force.cem-system-resource-cost/v1` 是过时 id，代码中是 `value.cem-system-resource-cost/v1`（`cost_ledger.py` 第 15 行）。成本按成本账 v2 写（K-14）：风光储 FOM 是备忘项；径流水电兼容资本在修正口径下不计入头条，在论文复现口径下计入；物理运营成本含“记录的切负荷 × VoLL”。“explicit fixed O&M” 改为只指火电 FOM |
| MC-2 | 第 58–62 行 | 水电存量值：补 P4-03 按口径的头条处理；补修正口径下的径流水电可用率（N-4） |
| MC-3 | 第 37–49 行 | 已知简化补：储能只用盈余充电（S7）；DEV-BAL-03；投资侧 CSV 与调度天气不一致（S9）；A13 模型选择仍待审核 |
| MC-4 | 第 27–31 行附近 | Q14 写成一般规则，并补 VALUE 101 two_year 论文复现运行因 DEV-STO-01 被扣发的实例 |
| MC-5 | 新增一段 | 数据资格：GBP1 public1 只用于论文复现口径；修正口径用 R029 public1 或本地 public2；逐站核电只作用于 `NUCLEAR_POLICY_PACK_IDS` 中的包 |

### 5.3 `docs/VALIDATION_AND_CLAIMS.md`

已改：第 38–46 行的新声明、第 66–93 行的 P0-6/P0-5b/F2 段、“Scope of the 0.7.0-alpha.1 claims”。以下待改。

| # | 位置 | 改动 |
|---|---|---|
| VC-1 | 第 24–28 行（prompt52 系列 “passed”） | 这些证据由 0.6.0-alpha.2 时期的代码产生，在 P0 修复之前（公告 `VALUE-ADV-2026-10-04-REVIEW` 适用），而且证据文件不在公开源码中（审查 R2-07）。Status 改为带限定的写法（例如 “passed (pre-fix, 0.6.0-alpha.2)”），或移到“历史证据”小节。改写时避开禁止正则 |
| VC-2 | 第 17–18 行 | Boundary 列补：修正口径的默认 PSM 只报循环折旧，首年满利用基准只影响持有回收诊断 |
| VC-3 | 新增行 | A4 火电净收入：`tests/test_p07_investment_corrections.py`，passed，边界为“玩具算例与 D4；电价等于 MC 时既不扩容也不退役” |
| VC-4 | 新增行 | A2 stress event 记账：`tests/test_p04_balance_boundary.py`、`tests/test_stress_events_query.py`，passed，边界为“调度不变，只记账” |
| VC-5 | 新增行 | Q14 发布规则：`tests/test_result_advisories.py`、`tests/test_methodology_profiles.py`，passed |
| VC-6 | 第 85–93 行 | 写明 A13 模型选择仍待审核；核电对 Energy Trends 5.1 的验收没有运行，属于 not_evaluated |
| VC-7 | 第 57–64 行 | “NO-GO for a fresh GitHub checkout because 460 intended source members are not tracked” 已过时（审查 R2-07）。是否删改由作者决定，因为它与源码公开的决定相关 |

## 6 草稿使用说明：哪些句子已经过时

| 草稿 | 并入位置 | 已过时、不要照抄的内容 | 以哪份为准 |
|---|---|---|---|
| `p05a_data_reading.md` | ch2 | 无 | — |
| `p05b_corrected_data.md` | ch3、ch2、ch5 | ① 状态段 “Every numeric reference value named here is PENDING AUTHOR REVIEW”：作者已在 A9 认可损耗系数、在 A14 审核核电与水电，只有 A13 的模型选择和 DUKES 对照列仍待审核。② §3 两条披露：海上约 18.5% 已在 A9 接受；“PV 乘水平 GHI、缺倾角增益”已由 A13 解决。③ §3 GBP1 光伏修正口径 CF 0.0997，现在是 0.1065。④ §4 只写 Heysham 1 按月停发，现在四座 AGR 都是 2030-03。⑤ §4 水电 0.334 乘平直占位形状，现在是 0.3487 乘季节形状。⑥ §3 “the author reads the values from the DUKES 6.3 workbook”：f2 已给出数值 | f2 草稿；DECISIONS A9、A13、A14 |
| `p06_default_psm_clearing.md` | ch5、ch4 | “Known approximations” 中 “Storage charging cost and the storage investment test are P0-7's”：P0-7 已按 A8(3) 维持现规则，改写为 K-12 | M5-P0-7、M5-P0-7-S10 报告 |
| `p07_investment.md` | ch4 | 储能余量一节只有文字，公式按 K-9 补写 | 本文 K-9 |
| `p04_energy_balance_validation.md` | ch5（替换残差段） | 无。它说替换 “Native retains both raw supply-demand residuals …” 一段，位置是 en 第 97–108 行、zh 第 95–106 行 | — |
| `p08_network_economics.md` | ch7、ch4 | 中文只有摘要，中文正文须按英文全文译写。§1 末尾括号中 “(Edit for `transmission.md` 0.3 …)” 是给你的编辑说明，不要并入正文 | — |
| `f2_solar_poa_firm_cf_disclosure.md` | ch3、ch5、ch2 | 无。注意它的倾角写法正确，修正目录 `p05.json` 第 243 行的描述是错的 | 代码 `solar_irradiance.py` |

## 7 版次升级（0.3 → 0.4）

### 7.1 何时升

- 只升一次：所有章节合并、中英配对检查通过、作者审阅通过后再升。不要分章节逐步发布。
- 发布 0.4 须经作者同意（Q-X3）。网站导入 0.4 是上传员的阶段 3，前提是源码已经公开（阶段 1，见网站交接文档第 3 节）。
- 0.4 发布之前，0.3 的六个文件和网站章节保持不变。上传员在阶段 1 加一条临时说明：“0.3 描述 0.6.0-alpha.2，0.7.0 的改动以 CHANGELOG 为准”（网站交接文档 M-2、C-16）。

### 7.2 要改的元数据

| 文件 | 字段 | 0.4 的值 |
|---|---|---|
| `docs/methodology/edition.json` | `edition` | `"0.4"` |
| | `date` | 生成日期（`YYYY-MM-DD`）。六个文件名也用这个日期（`build_document.py` 第 14–15 行） |
| | `basis` | 正文描述的实现与数据依据日期，建议取作者确认发布的 0.7.0-alpha.1 源码提交的日期 |
| | `revision.zh` / `revision.en` | 保持现有格式，含三个空格：`"修订版 0.4   YYYY年M月D日"` / `"Edition 0.4   D Month YYYY"` |
| | `basisLabel.zh` / `basisLabel.en` | `"模型实现与数据依据 YYYY年M月D日"` / `"Implementation and data basis D Month YYYY"`。是否加上 “VALUE 0.7.0-alpha.1” 由作者决定 |
| | `chapterIDs` | 不变（九个） |
| `docs/methodology/generation.json` | `edition`、`date`、`basis` | 同上 |
| | `scope_changes` | 改写为 0.4 的范围：两个方法学口径；通用修正与口径受控修正（第 3.3 节）；设计假设 S1–S3；已声明偏差；A15 核电路径依赖；网络经济学（P0-8） |
| | `checks` | 重新执行后填写。原有的 `numeric_tokens_preserved_after_chapter_reference_updates` 是 0.3 只改章节号时的检查，0.4 是内容修订，建议改为第 8 节的双语数值一致检查 |
| | `dependencies` | 不变，除非构建工具升级 |
| `docs/methodology/artifacts.json` | `edition`、`date`、`basis`、`files[6]`（path、sha256、bytes、render_review）、`review` | 六个文件审阅通过后填写，`review.status = "passed"` |
| `docs/methodology/README.md` | 版次行、下载链接 | 同上 |
| `docs/methodology/VALUE_METHODOLOGY.md` | 第 3 行 | “edition 0.4” |
| `publication-scope.json` | `edition`、`revision_date`、`scientific_basis_date`、`expected_artifacts` | 必须与 `edition.json` 和新文件名一致（`check_publication_scope.py` 逐项比较）。这一步与上传员协调：网站交接文档写的是由上传员在阶段 3 同步更新 |

### 7.3 构建

1. 按 `scripts/methodology/README.md` 准备文档构建环境。它与模型运行时分开：python-docx 1.2.0、lxml 6.1.1、MathJax 3.2.2、marked 17.0.5、sharp 0.35.4，再加 LibreOffice 和中文、数学字体。
2. 依次运行：`assemble.py` → `render_math.cjs zh|en` → `build_document.py zh|en`。之后把 DOCX 转为 PDF，逐页检查 PDF 中的公式、表格和中文排版。0.3 的审阅范围是中文 50 页、英文 46 页，0.4 预计会增加。
3. `scripts/build_value_methodology_pdf.py` 用于把 `VALUE_METHODOLOGY.md` 单独构建为开发者概览 PDF，输出到 `output/pdf/VALUE_Methodology.pdf`。需要改两处：
   - 第 35 行页脚写死了 “VALUE methodology | 25 August 2026”，改为新日期，或改为从 `edition.json` 读取；
   - 第 70–76 行封面表，可以补一行 “Methodology profiles: corrected (default) and doctoral reproduction”。
   
   注意 `tests/test_value_methodology.py`：PDF 存在时，它对 PDF 文本做同样的短语检查和 `force` 禁止检查。
4. 把六个文件的哈希和大小写入 `artifacts.json`，然后交给上传员运行 `website/sync_methodology.py --source docs/methodology --build <渲染目录> --documents <六个文件目录>`。不要手改 `website/methodology/` 或 `website/static/assets/methodology/`。

### 7.4 合并 0.4 的提交

- 中英两版同一提交修改，每章一个提交，便于审阅。最后一个提交更新 `edition.json`、`generation.json`、`artifacts.json`、`README.md`、`VALUE_METHODOLOGY.md` 第 3 行。
- 每个提交前运行 `tests.test_value_methodology` 和 `tests.test_documentation_consistency`，用施工 wrapper 加 unittest。

### 7.5 合并后

- `docs/methodology/drafts/0.4/` 已在发布排除清单中（`tests/baselines/release-exclusions.txt` 第 11 行）。0.4 获批后，建议在同一提交中删除已并入的草稿，避免出现两个事实来源；或者在每份草稿首行注明“已并入 0.4（日期）”。删除时不需要改排除清单。
- 修正目录如果因第 9 节第 3 条被修改，`docs/generated/METHODOLOGY_PROFILES.md` 须重新生成（`scripts/generate_reference_tables.py`，有测试拦截），由代码负责人处理。

## 8 双语一致性检查清单

### 8.1 机器检查

1. **结构配对**：`assemble.py` 输出 `assembly-check.json`。九个 `pairs[*].matching_structure` 必须全为 `true`，即每章中英的标题数、表格分隔行数、代码块栏数和行间公式数都相等。新增小节、表格、伪代码和公式时，两版要同时加。
2. **行间公式逐字相同**：同一章两版的 `$$…$$` 块应逐字相同，LaTeX 不翻译。可以用以下片段比较（用文档构建环境的 Python 运行，或用施工 wrapper）：

```python
import re, pathlib
S = pathlib.Path("docs/methodology")
ids = ["introduction", "datasets", "core_weather", "core", "national_alternatives",
       "r029_cem", "transmission", "optional_modules", "appendix"]
for cid in ids:
    en, zh = ((S / l / f"{cid}.md").read_text(encoding="utf-8") for l in ("en", "zh"))
    m = lambda t: [b.strip() for b in re.findall(r"\$\$(.*?)\$\$", t, re.S)]
    nums = lambda t: sorted(re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?", re.sub(r"\$\$.*?\$\$", "", t, flags=re.S)))
    code = lambda t: sorted(set(re.findall(r"`([^`]+)`", t)))
    print(cid, "math", m(en) == m(zh), "numbers", nums(en) == nums(zh), "code", code(en) == code(zh))
```

   - 数值不一致不一定是错误，例如中文写“第四章”而英文写 “Chapter 4”。逐条人工核对，最后在 `generation.json` 的 `checks` 中如实记录。
3. **代码标识一致**：correction id、口径 id、模块 id、文件名、参数名（反引号内的内容）两版集合相同。
4. **禁用内容**：
   - 章节正文没有 32–64 位十六进制串，没有 `/home/`、`/mnt/` 路径，没有私有产品名；
   - `VALUE_METHODOLOGY.md` 中没有 `force`；
   - 可以用以下命令检查：`grep -n -i -E 'force|/home/|/mnt/|\b[0-9a-fA-F]{32,64}\b' docs/methodology/{en,zh}/*.md docs/methodology/VALUE_METHODOLOGY.md`。
5. **测试**：`<vpy> -m unittest tests.test_value_methodology tests.test_documentation_consistency`，`<vpy>` 为施工 wrapper；网站构建后由上传员运行 `scripts/check_publication_scope.py`。

### 8.2 人工检查

1. 第 2.4 节术语表中的每个术语，全文只用一种译法；第一次出现时中英对照。
2. 口径标签与固定附注保留英文原文（界面字符串），中文版在引号中照写英文，再加中文说明。
3. 每处只适用于一个口径的表述，两版标注相同。建议统一用 “(corrected profile)” / “（修正口径）”、“(doctoral reproduction profile)” / “（论文复现口径）”。
4. 数值逐个核对：
   - 损耗系数 0.90307、0.814968、0.83；
   - 核电五站负荷率、退役月份与第 4,320 期；
   - 水电 0.3487 与 12 个形状值；
   - VoLL 17,000（A16-5；8000 和 10000 只作为“原值”出现）；
   - 核电下调溢价 100；
   - 类别权重 0 / 0.5 / 2 / 3 / 4；
   - 舍入吸收 \(10^{-9}\)，\(\tau_t\) 的三个数；
   - 汇率 1.1；
   - GBP1 的进口 −78%、系统成本 −3.2%、排放 +3.4%；
   - CF 表；
   - stress 157 / 890 / 300,855。
5. 待审核标记一致：DUKES 对照列两版都标 PENDING AUTHOR REVIEW，或都在作者审核后去掉。A13 模型选择已由作者在 A16-6 认可，两版都去掉 PENDING 标记。
6. 交叉引用（章号、节名）两版一致。新增小节后，引用这些小节的地方都要更新。
7. 中文用全角标点，数字用半角，千分位与英文版一致（例如 17,520）。

## 9 写 0.4 之前须确认的事项

| # | 事项 | 为什么重要 | 找谁 |
|---|---|---|---|
| 1 | R029 研究（thesis96，`value-doctoral-national-psm`）在 0.7.0 中按哪个口径运行，P0-5b 的天气 v2、损耗系数与核电可用率是否作用于这条路径；第 3 章第 164 行与第 6 章第 271–279 行的 R029 数值是否重算 | 第 5、6 章的口径归属与数值例子 | 代码负责人、作者 |
| 2 | 逐站核电只对 `NUCLEAR_POLICY_PACK_IDS`（目前只有 GBP1 public1）生效，而 GBP1 public1 在修正口径下不合格；public2 和 R029 上核电取全国回退值 0.723。是否把 public2 加入名单（需要另立 correction id） | 否则正文中的逐站规则在任何合格的修正口径运行中都不会被用到 | 作者 |
| 3 | 修正目录 `corrections/p05.json` 第 243 行 `p05.solar-plane-of-array` 的描述写 “tilted at the site latitude”，与代码（`tilt_rule = jacobson-jadhav-2018`）、参数表、f2 草稿不符；它也出现在生成的 `METHODOLOGY_PROFILES.md` 中。另外 `p05.vre-loss-factors` 的描述仍写 “PENDING AUTHOR REVIEW”，但 A9 已认可 | 描述只是展示字段，不进入方法哈希（`methodology.py` 第 171–179 行），但会被网站和读者引用 | 代码负责人：修目录描述后重新生成表（FX7 已修：两条描述已改正，`METHODOLOGY_PROFILES.md` 已重新生成） |
| 4 | 23 区 GB 研究的基础数据包是哪个。网络模块只在修正口径下运行，而 GBP1 public1 在修正口径下不合格 | 第 2 章第 9 行、第 7 章第 107 行 | 代码负责人 |
| 5 | ~~A13 光伏倾斜面换算的模型选择~~（A16-6 已认可），以及 DUKES 对照列 | 0.4 正文是否带 PENDING 标记 | 作者 |
| 6 | 修正口径下，核电日前接受的路径依赖是否仍然存在、量级多大 | 第 5 章 N-7 能否把这段写进修正口径 | 代码负责人 |
| 7 | 起始年不变币值的表述：哪个价格基年、是否承认输入的来源年份混合；以及 R029 年度资本费用中的 5% 利率与“不折现”如何并列表述 | 第 1 章新小节、第 2 章、第 6 章 | 作者 |
| 8 | 方法学中 “Doctoral” 路径是否改名 | 避免与论文复现口径混淆 | 作者 |
| 9 | 是否在方法学中加入 GBP1 的勘误说明（A15 说该对比作为论文结果的勘误保留），以及 A15 surplus conservation 失败（471 个时段、最大 991 MWh）在方法学中怎样写：它是待调查的已知问题，不是已声明偏差 | 第 2 章或第 5 章的写法 | 作者 |

## 10 顺带发现、不属于 P0 的过时表述（可以在 0.4 一并改，也可以不改）

| 位置 | 问题 | 审查编号 |
|---|---|---|
| `MATHEMATICAL_REFERENCE.md` 第 116 行及 §7 | 模块 id 写成 `force-reference-dc-network`、`force-perfect-foresight-lp`、`force-reference-ac-feasibility`，实际是 `value-*` | P1-19 |
| `MATHEMATICAL_REFERENCE.md` §2.3、§2.5 | LaTeX 用了双反斜杠 `\\(`、`\\[`，渲染会出错 | — |
| `MATHEMATICAL_REFERENCE.md` §2.6；模型卡第 64–68 行 | 写“没有启动、爬坡、最小出力约束”，但默认 PSM 有启动加价、`alter_limit` 爬坡和核电必发下限 | P3-07、P5-10 |
| `MATHEMATICAL_REFERENCE.md` §3.1 | dwell 下限写 \(\max(\bar h,1)\)，代码是 2.0 | P5-13 |
| 模型卡第 70–72 行 | “Short diagnostic runs … never publish annual economic indicators”，与实现不一致 | P4-18 |
| `r029_cem.md` 第 240–250 行 | 外生抽蓄日程只在 Doctoral 路径中调用；起始年不是 2025 时使用魔数 | P5-14 |
| `r029_cem.md` 第 225、266 行；`VALUE_METHODOLOGY.md` 第 163 行 | 称内生投资应用了建设期和规划成功率，v2 中恒为 1 年、成功率为 1 | P4-05 |
| `VALUE_METHODOLOGY.md` 第 191 行 | 称储能碳库存已覆盖，实际从未计算 | G3-03 |
| `VALUE_METHODOLOGY.md` 第 193 行 | doctoral 碳情景“保留历史边界”，实际端到端不产出量 | G3-04 |
| `VALIDATION_AND_CLAIMS.md` 第 12 行 | 独立 oracle 依赖系统 CBC 的边界没有注明 | R2-06 |

以上各项的细节都在 `VALUE_review_2026-10-04.md` 中，可以按编号 `grep -n` 查找。
