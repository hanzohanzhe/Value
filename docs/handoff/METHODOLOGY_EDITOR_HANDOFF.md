# VALUE 方法学修改员交接文档（方法学 0.4 版次）

- 日期：2026-10-08。依据：分支 `fix/review-2026-10-04` 的 HEAD（代码状态为提交 `6014421`，应用版本 0.7.0-alpha.1，只在本地，未推送）。对照基线是 `main` 的 35aadb3，即 VALUE 0.6.0-alpha.2 的源码。
- 读者：维护以下文件的人：
  - `docs/methodology/` 下的 `en/`、`zh/`、`VALUE_METHODOLOGY.md`、`README.md`、`edition.json`、`generation.json`、`artifacts.json`；
  - `docs/MATHEMATICAL_REFERENCE.md`、`docs/SCHEME_C_MODEL_CARD.md`、`docs/VALIDATION_AND_CLAIMS.md`；
  - 方法学构建工具：`scripts/methodology/`、`scripts/build_value_methodology_pdf.py`、`website/sync_methodology.py`。
- 交付：DECISIONS“收尾交付”第 2 项。仓库副本为 `docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md`；worktree 根目录副本为 `VALUE_handoff_methodology_editor_2026-10-04.md`。
- 本文只写当前最终状态：每一处改哪里、改成什么。施工经过只保留在 git 历史和 `docs/dev/p0-reports/` 中。
- 事实来源（按权威排序）：
  1. `docs/dev/P0_DECISIONS.md`（Q1–Q15、A1–A29；同一事项以编号靠后的一行为准）；
  2. 修正目录 `gridform_core/data/methodology/`（`profiles.json`、`corrections/*.json`、`declared_deviations.json`、`advisories.json`），以及由它生成的 `docs/generated/METHODOLOGY_PROFILES.md`；
  3. `docs/release/VERSION_LEDGER.json`（模块版本）、`docs/release/P0_GOLDEN_DELTA.md`（golden 变化的归因）、`CHANGELOG.md` 开头的 “Correction ids” 表（只登记在版本台账或 CHANGELOG 中的 id）；
  4. 参数表：
     - `gridform_core/data/thermal/value_thermal_restart_v1.json`；
     - `gridform_core/data/nuclear/value_uk_firm_availability_v1.json`；
     - `gridform_core/data/weather/value_uk_vre_loss_factors_v1.json`；
     - `gridform_core/data/weather/value_uk_vre_cf_disclosure_v1.json`；
  5. 草稿 `docs/methodology/drafts/0.4/*.md`（使用前看第 6 节）；
  6. 实测结果：
     - `docs/dev/p0-reports/r41-golden/D5-gbp1-summary-before-after.json` 的 `after-r41` 一栏（GBP1 public1 论文复现口径，第一个模型年；只用这一栏）；
     - `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` 第 10 节（GBP1 public2 修正口径）；
     - `docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md`（参考统计，作者已审核）。
- 行号：`docs/methodology/` 下的 0.3 源稿、`VALUE_METHODOLOGY.md` 和 `README.md` 在本分支上与 `main` 逐字相同。下文所有行号都在本分支 HEAD 上核对过。

## 0 先读这一段

1. **网站方法学描述的是 VALUE 新模型，不是博士论文（DECISIONS A26）。**
   - 方法学描述网上发布的 VALUE 模型，也就是新 Study 和 Run 默认使用的修正口径（`value-corrected`）。
   - 论文复现口径（`doctoral-lineage-0.6.0a2`）是**兼容口径**：它按 VALUE 0.6.0-alpha.2 的实现保留论文时期的设定，同时接受两个口径共同的修正（第 3.3 节的 U 类）。
   - 论文时期的设定是**设定，不是错误**，例如零成本风电先削、风光不乘损耗系数、核电与径流水电 100% 可用、原有的数据读法。正文不要写成缺陷。
   - 正文任何地方都不写“方法学对标论文”“与论文一致”“复现论文”，英文也不写 “aligned with the thesis”“reproduces the thesis”。论文本身的代码以 GitHub 上已锁定的历史研究档案为准。
2. **写法规则。**
   - 正文先写修正口径的规则，这就是模型。论文复现口径与之不同的地方，用标注好的段落写在后面：“In the doctoral reproduction profile …” / “论文复现口径中……”。
   - 通用修正（U 类）就是两个口径共同的模型规则，正文直接写规则本身，**不写**“原来的实现错了、现在改了”。修复经过只出现在 CHANGELOG 中。
   - 修正 id（如 `p05.interconnector-clock`）是 Run 记录中的机器标识。正文可以在第 1 章口径小节或脚注中引用，便于读者对照 Run 记录；本文其他地方给出的 id 是给修改员定位用的，不要求写进正文。
   - 正文不写施工代号（P0-x、R4-1、FX6 等）、提交号和内部报告路径。
3. **0.3 版次冻结，所有改动进入 0.4。**
   - `docs/methodology/{en,zh}/*.md` 是已发布 0.3 文件（六个 docx/pdf/html，哈希登记在 `artifacts.json`）的源稿，网站章节 JSON 也由它们生成。
   - 0.4 整体生成之前，不要就地修改 0.3 源稿：改了以后源稿与已发布文件不一致，`scripts/check_publication_scope.py` 逐字比较网站章节与源稿也会失败。
   - 0.4 的发布须经作者同意。网站导入 0.4 由上传员负责。按 DECISIONS A17、A21，推送和网站上传都要等前端整体翻新之后。
4. **草稿共 15 份**，在 `docs/methodology/drafts/0.4/`：p04、p05a、p05b、p06、p07、p08、f2、fx5、fx6、fx8、r12、r32、r33、r41、r5。
   - 草稿按工作包组织，不按章节组织。本文第 4 节给出每一处的落点。
   - 草稿中有一些句子带有内部编号、版本号、修复前后对比或旧数字，不能照抄。逐份清单见第 6 节。
   - 中文部分：只有 p04 是全文；f2、p05b、p08、r32、r33 有摘要；fx5、fx6、fx8 有替换句；p05a、p06、p07、r12、r41、r5 没有中文。
5. **以下内容没有草稿，按本文新写：**
   - 第 1 章新增小节 “Methodology profiles / 方法学口径”（I-1，本文给出中英文稿）；
   - 模型时钟一句（K-0）；
   - 修正口径的储能扩容余量与按类型电池上限的公式（K-9）；
   - 储能投资审核公式（K-12）；
   - 价格标签（N-11 与第 3.1 节 S8）；
   - DC 网络的份额展开（T-8）；
   - R029 章节的口径归属（R-1）；
   - `VALUE_METHODOLOGY.md` 的全部改动（第 4.10 节）。
6. **设计假设和修正分开写**（第 3 节）。以下是作者明确保留的模型设定，不是修正，也不是缺陷：
   - 风电、光伏、储能没有 OPEX（可变 OPEX 为 0，固定 OPEX 含在平准化 CAPEX 中）；
   - 投资决策不折现，不引入 NPV 或 IRR；
   - 一律以起始年不变币值计价。
7. **九章结构不变。**
   - `scripts/methodology/assemble.py` 写死了九个章节 id；`website/sync_methodology.py` 要求恰好九章、六个文件；`check_publication_scope.py` 要求章节编号为 1–9。
   - 口径总述写进第 1 章的新小节，不要新增第十章。
8. **构建与测试会拦截的写法：**
   - `VALUE_METHODOLOGY.md` 及其 PDF 中不得出现子串 `force`，不分大小写（`tests/test_value_methodology.py`）。“forced part”“enforce”`force_current_...``force-reference-...` 都会命中；
   - 章节正文不得含 32–64 位十六进制串（例如 sha256），不得含 `/home/` 或 `/mnt/`（`assemble.py`）；
   - 章节正文与 HTML 不得出现私有产品名（`sync_methodology.py` 的 PRIVATE 正则：VALUE-single、Electrace、SDX 等）；
   - 三份参考文档有固定短语和禁止短语（第 5 节开头）。
9. **命名陷阱。** 0.3 第 5、6 章的 “Doctoral” 路径是实验模块 `value-doctoral-national-psm`（R029 thesis96），**不是**论文复现口径 `doctoral-lineage-0.6.0a2`。论文复现口径的参考运行（golden D1–D5）走第 5 章的 “Native” 路径，即默认 PSM `value-bid-at-cost-psm`。0.4 必须在第 1、5 章写清这一点（第 2.2 节）。
10. **写 0.4 之前须确认的事项**见第 9 节。影响正文最多的三条：
    - R029 研究（第 6 章）在 0.7.0 中按哪个数据包、哪条路径描述；
    - 起始年不变币值的表述；
    - “Doctoral” 路径是否改名。

## 1 文件现状

| 文件 | 现状 | 还要做什么 |
|---|---|---|
| `docs/methodology/en/*.md`、`zh/*.md` | 0.3，与已发布文件一致 | 合并为 0.4，见第 4 节 |
| `docs/methodology/drafts/0.4/*.md` | 15 份草稿 | 按第 6 节取用；0.4 获批后删除，或在首行注明“已并入 0.4”（第 7.5 节） |
| `docs/methodology/VALUE_METHODOLOGY.md` | 0.3 的内容 | 第 4.10 节，版次改为 0.4 |
| `docs/methodology/README.md`、`edition.json`、`generation.json`、`artifacts.json` | 0.3 | 0.4 生成并审阅后更新，见第 7 节 |
| `docs/MATHEMATICAL_REFERENCE.md` | 版本行为 0.7.0-alpha.1；§2.4 已写分区下调报价（含两段式）、网络成本、边界边际值与求解合同 v4；§5.1 的参照情形已是无网络 LP | §2.4 有一处公式损坏和几处施工轮次字样；§2.1、§2.2、§2.3、§2.5、§2.6、§3、§4、§5、§7、§8 仍是 0.6.0-alpha.2 的内容。见第 5.1 节 |
| `docs/SCHEME_C_MODEL_CARD.md` | 已有口径段、两个口径的已知简化（含生物质）、投资规则、默认 PSM 规则集段（已写三项内核规则）、修正口径输入两段 | 口径段缺若干通用修正；第 27–31 行一段与当前结果不符；规则集段带历史说法；输入段带过时状态；成本定义 id；数据资格与 Q14 一般规则。见第 5.2 节 |
| `docs/VALIDATION_AND_CLAIMS.md` | 有 0.7.0 的若干行和 “Scope of the 0.7.0-alpha.1 claims” 一节 | 论文复现口径一行、golden 归因一行、表后三段和 Scope 一节中有多处与当前结果不符；缺若干行。见第 5.3 节 |
| `scripts/build_value_methodology_pdf.py` | 页脚日期写死为 “25 August 2026” | 第 7.3 节 |
| `scripts/methodology/*`、`website/sync_methodology.py` | 不需要改代码 | 按第 7 节流程使用 |
| `docs/generated/METHODOLOGY_PROFILES.md` | 生成文件 | **不要手改**。目录描述有误时，请代码负责人改目录后重新生成 |

另外两份交接文档：网站上传员 `docs/handoff/WEBSITE_UPLOADER_HANDOFF.md`（网站导入 0.4 的前提是本文第 7 节完成）；给作者的简报 `docs/handoff/MODEL_CHANGES_BRIEF.md`。

## 2 术语与命名约定

### 2.1 方法学口径（字符串固定，Q2）

| 机器 id | 界面标签（中英文版都照写英文原文） | 固定附注 | 中文称呼 | 定位 |
|---|---|---|---|---|
| `value-corrected` | Corrected methodology (default) | Current default methodology with review fixes of 2026-10. | 修正口径（默认） | 方法学描述的模型 |
| `doctoral-lineage-0.6.0a2` | Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2) | not an exact reproduction of the 2026-07-18 retained trajectory | 论文复现口径 | 兼容口径 |

- 凡出现论文复现口径的标签，固定附注必须同时出现。
- 论文复现口径的白名单（Q3）：
  - 模块只接受论文谱系模块，按各自的 scientific_version 核对：`agent-investment`、`planning-pipeline`、`value-annual-state-transition`、`value-bid-at-cost-psm`、`value-copperplate-balancing`、`value-doctoral-national-psm`、`value-legacy-storage-tariff`、`value-repd-era5-aggregated-weather`、`value-storage-expansion-policy`、`vre-expansion-cap`；
  - 数据包只接受四个论文期数据包：GBP1 public1（`value-uk-open-data-pack-v1`）、`value-uk-1000twh-reproduction`、`value-101-baseline-v1`、`value-synthetic-contract-pack-v1`；
  - 已启用外部代码时拒绝运行。
- 参考配置：储能成本模块 `value-legacy-storage-tariff`，碳因子情景 `doctoral_reproduction_2026_07_18`。选择该口径时写入 Study；偏离参考配置允许，但记录在 Run 上。
- 用户工作区数据包（包括映射的 CSV）不在论文复现口径的白名单中，只能用修正口径运行。

### 2.2 三条全国 PSM 路径的名称对照（0.4 必须写清）

| 0.3 的叫法 | 模块 id 与当前版本 | 两个口径下的情况 |
|---|---|---|
| 第 5 章 “Native” | `value-bid-at-cost-psm` 6.7.0，运行保留的 Scheme C 内核 `runtime_compat/modular_simulation_model.py` | **默认 PSM**。修正口径使用市场规则集 `native-corrected-v1`，论文复现口径使用 `native-doctoral-thesis-v1`（`native_market_rules.py`）。规则集只由口径决定。golden D1–D5、C1–C6、C9、C10 都走这条路径 |
| 第 4 章 “staged market” | `value-staged-bid-at-cost-psm` 1.6.0，加平衡模块 `value-copperplate-balancing` 1.1.0 或 `value-zonal-redispatch-balancing` 4.0.0 | 分阶段与网络路径。网络模块不在论文复现口径的白名单中（Q3），所以实际只在修正口径下运行（golden C7、C8） |
| 第 5、6 章 “Doctoral” | `value-doctoral-national-psm` 0.3.0（experimental），R029 thesis96 | **不是**论文复现口径。它的输入走 “doctoral national” 对齐分支：无论哪个口径，都使用冻结的 v1 天气、不加损耗系数、不做倾斜面换算、核电与径流水电 100% 可用、保留负的边界价格（`gridform_core/canonical_psm_data.py` 第 1017–1028 行） |

0.4 写法：
- 第 5 章开头加一句。
  - EN：“Native is the default national PSM (`value-bid-at-cost-psm`); it runs one of two market rule sets, selected by the methodology profile. The Doctoral pathway below is a separate experimental module (`value-doctoral-national-psm`); it is not the doctoral reproduction profile.”
  - ZH：“Native 即默认全国 PSM（`value-bid-at-cost-psm`），按方法学口径运行两套市场规则之一。下文的 Doctoral 路径是另一个实验模块（`value-doctoral-national-psm`），不是论文复现口径。”
- 是否把 “Doctoral pathway” 改名（例如 “Thesis-96 national pathway”），由作者决定（第 9 节第 7 条）。
- `VALUE_METHODOLOGY.md` 第 42 行写 “The built-in PSM is `value-staged-bid-at-cost-psm`”，与默认配置不符，0.4 一并改正（V-3）。

### 2.3 本文的轨道标记与修正 id

| 标记 | 含义 | 登记在哪里 |
|---|---|---|
| **U** | 两个口径共同的模型规则（通用修正）：改轨迹的读取与内核规则，以及只改核算区的规则（Q12） | 目录中 `track = universal`；或只在 VERSION_LEDGER、CHANGELOG 中 |
| **C** | 只在修正口径生效（口径受控修正） | 目录中 `track = profile_gated` |
| **N** | 网络模型（staged、copperplate、zonal、DC）的规则。这些模块只在修正口径下运行，所以正文写“只在修正口径下运行” | VERSION_LEDGER（模块版本，均需用户确认） |
| **D** | 论文复现口径保留的论文时期设定 | 论文规则集 `native-doctoral-thesis-v1` 与冻结的输入路径；`declared_deviations.json` 中的三条定义与证据 |
| **设计假设** | 作者确认的模型设定 | — |

- 只登记在 VERSION_LEDGER 或 CHANGELOG、不在修正目录中的 id：`p04.*`、`p06.physical-operating-cost`、`p06.staged-dwell-disclosure`、`p07.cost-ledger-v2`、`fx4.storage-offer-ledger`、`fx5.voll-17000`、`p08.*`、`r32.network-economic-downward-order`、`r33.restart-cost-price-base-2025`、`r43.model-clock-utc-label`、`r5.served-energy-net-of-stress-shortfall`、`r53.bounded-storage-state-record`。正文引用这些 id 时，不要说它们“在修正目录中”。
- Run 的方法记录在 `universal_accounting_correction_ids` 与 `correction_ids_in_force` 中列出生效的通用核算修正：`fx4.storage-offer-ledger`、`fx5.voll-17000`、`p04.*`（五个）、`p06.physical-operating-cost`、`p07.cost-ledger-v2`、`r5.served-energy-net-of-stress-shortfall`（`gridform_core/methodology.py` 第 78–94 行）。
- 正文不写的 id：
  - `p07.power-battery-pool`：已被 `r13.per-type-battery-caps` 取代，只为旧 Run 的身份可读而保留；
  - `r53.bounded-storage-state-record`：只压缩 full 追踪中出清声明的记录格式，不改任何结果；
  - `r43.model-clock-utc-label`：只改账本元数据中的时钟标签。正文写模型时钟本身（K-0），不写这个 id。

### 2.4 中英术语表（全文统一）

| English | 中文 | 备注 |
|---|---|---|
| methodology profile | 方法学口径 | |
| corrected methodology (default) | 修正口径（默认） | 方法学描述的模型 |
| doctoral reproduction profile | 论文复现口径 | 兼容口径。不要简称“doctoral 口径”，以免与 Doctoral 路径混淆 |
| compatibility profile | 兼容口径 | 用于说明论文复现口径的定位 |
| thesis-era setting | 论文时期的设定 | 不写成“错误”或“缺陷” |
| universal correction / profile-gated correction | 通用修正 / 口径受控修正 | 只在第 1 章口径小节与 CHANGELOG 中用这两个词；其他章节直接写规则 |
| declared deviation | 已声明偏差 | 只剩 DEV-BAL-01、DEV-BAL-02、DEV-BAL-03 |
| market rule set | 市场规则集 | `native-corrected-v1`、`native-doctoral-thesis-v1`；网络模型为 `network-economic-v2` |
| model clock | 模型时钟 | UTC，固定 365 天模型年 |
| stress event / stress period / shortfall | stress event / stress 时段 / 缺口 | 界面用英文 “stress”，中文版照写 |
| unserved energy (booked) / recorded blackout | 缺电量（记账）/ 记录的切负荷 | 前者是能量平衡账补记的缺口，后者是 PSM 记录的切负荷 |
| energy served | 已供电量 | 需求 − 记录的切负荷 − stress 缺口 |
| raw residual / compatibility adjustment | 原始残差 / 兼容调整 | |
| headline (cost) / memo line | 头条（成本）/ 备忘项 | |
| levelised CAPEX | 平准化 CAPEX | |
| physical operating cost | 物理运营成本 | |
| settlement transfer | 结算转移 | |
| uniform marginal price | 统一边际价 | |
| average period cost | 时段平均成本 | 界面标签 “Average period cost (£/MWh demand)” |
| cycle wear / cycle depreciation | 循环损耗 / 循环折旧 | |
| holding recovery | 持有回收 | |
| net position (per period) | （逐期）净头寸 | |
| buy-back | 回购 | |
| down regulation / down-regulation stack | 下调 / 下调次序 | |
| economic down-regulation order | 经济下调顺序 | 修正口径（A19、A22、A22a） |
| running range / shutdown segment | 不停机段 / 停机段 | 以最小稳定出力为界 |
| restart cost (per MW of capacity per start) | 重启成本（每 MW 装机每次启动） | 符号 \(S\)；热/温/冷启动 hot / warm / cold start |
| net saving per MWh | 每 MWh 净节省 | \(a(H)=c-S(H)/(m\,H)\) |
| minimum stable generation / minimum down time | 最小稳定出力 / 最短停机时间 | 符号 \(m\) / \(T\) |
| expected downtime \(H\) | 预计停机时长 \(H\) | 日前预测中连续盈余的时长 |
| break-even downtime \(H^\*\) | 盈亏平衡停机时长 | \(H^\*=S/(m\,c)\) |
| dec (down) bid / dec class | 下调报价 / 下调类别 | 网络模型 |
| network-free counterfactual | 无网络反事实 | |
| boundary marginal value | 边界边际值 | |
| wake / availability / electrical loss | 尾流 / 可用率 / 电气损耗 | |
| performance ratio (PR) | 性能比 | |
| plane-of-array irradiance (POA) | 组件平面辐照 | |
| load factor / capacity factor | 负荷率 / 容量因子 | DUKES 用“负荷率”，模型用“容量因子” |
| unused VRE | 未利用的 VRE | 各时段 \(\max(\text{可用}-\text{接纳},0)\) 之和 |
| constant start-year money | 起始年不变币值 | |
| undiscounted | 不折现 | |
| storage expansion headroom / per-type power-battery cap | 储能扩容余量 / 按类型的功率电池上限 | |
| leftover surplus (after existing charge) | 现有储能充电后的剩余盈余 | |
| support revenue (CfD, ROC) | 补贴收入（差价合约、可再生能源义务证书） | |

## 3 设计假设、论文复现口径保留的设定与修正总表

### 3.1 设计假设（写成模型设定，不写成修正）

| # | 设定 | 依据 | 口径 | 写在哪里 | 措辞要点 |
|---|---|---|---|---|---|
| S1 | **风电、光伏、储能没有 OPEX**：可变 OPEX 为 0，毛收入即利润；固定 OPEX 视为已含在平准化 CAPEX 中，投资决策和头条成本中都不再单独扣除。数据包给出的风光储 FOM 只作备忘项 | A4、A7 | 两者 | ch4 投资与成本；`VALUE_METHODOLOGY.md` §8、§11；模型卡；数学参考 §4、§5 | 写成 “wind, solar and storage carry capital cost and depreciation only”，不要写“暂未建模” |
| S2 | **投资决策不折现**：四档规则比较 ROI 与 preferred_rate、回收期与目标年限，不用 NPV、IRR 或年金门槛 | A6 | 两者 | ch4；数学参考 §4；`VALUE_METHODOLOGY.md` §8 | 说明成本核算中的 CRF 只把存量资本摊到各年，不对投资收入折现（p07 草稿 “Money basis” 可用） |
| S3 | **起始年不变币值**：所有金额按起始年币值计价，未来收入与现在等价 | A6、A24-4 | 两者 | ch1 新小节；ch2 成本与储能参数 | 见下方说明。整体表述待作者确认（第 9 节第 3 条） |
| S4 | **缺电时段的调度不变**：日前满足不了预测时，出力和价格照旧，缺口记为 stress event | A2 | 两者 | ch5 N-8、N-13 | 写成已知简化，配合 U 类的 stress event 记账 |
| S5 | **风光不对统计负荷率标定**：只与 DUKES 并列披露，并写明偏高原因 | Q15、A1、A9 | 修正口径（论文复现口径没有损耗系数） | ch3 W-4 | f2 草稿 §4 可用 |
| S6 | **储能投资审核**：ROI = 年市场收入 ÷ 整体 CAPEX，不扣循环成本，不另扣 FOM，不折现；扩容上限由物理利用率决定，不启用 `tier_roi` | A8(3)(4) | 两者 | ch4 K-12 | — |
| S7 | **储能只用盈余充电**，充电成本为 0，不从市场购电 | A8(2) | 两者 | ch5；`VALUE_METHODOLOGY.md` §5 | 所以 K-12 中“充电量 × 充电时电价”一项在默认 PSM 中为 0 |
| S8 | **默认 PSM 显示的“价格”是时段平均成本**，不是边际出清价；只改标签，不改算法 | Q6 | 两者 | ch5 N-11；ch4 分阶段价格；ch8 完全预见 | 标签见下表 |
| S9 | **投资侧 CSV 资源曲线与调度侧天气不一致**：只披露，下一轮统一 | Q15 | 两者 | ch3 W-5 | CSV 曲线不乘损耗系数，也不做倾斜面换算 |
| S10 | **火电固定 OPEX 维持原状** | A7 | 两者 | ch4 | 火电的显式 FOM 照常进入头条 |
| S11 | **核电和径流水电可用率取固定值**：没有年际波动，也没有换料或停运日历 | A10、A14 | 修正口径 | ch5 N-4 | — |
| S12 | **生物质没有补贴收入**（没有 CfD 差价补贴，没有 ROC）：按全额燃料与碳成本报价，几乎不被调度 | A24-2 | 两者 | ch5 N-1；ch1 局限；模型卡 | 写成模型范围限制；补贴建模是下一轮工作（审查 P4-07），不要写成已修复或待修的缺陷 |
| S13 | **重启经济学只用于排序**：最小稳定出力、最短停机时间和重启成本只决定下调先后，不是机组组合约束；重启成本也不进成本账 | A19、A22 | 修正口径 | ch5 N-9；ch4 K-3；ch7 | 避免读者以为模型有机组组合，或成本账含 \(S\) |
| S14 | **模型时钟**：UTC 半小时时段，固定 365 天模型年，没有夏令时，2 月 29 日不是模型日 | A27（四角色 S-中1） | 两者 | ch4 K-0；ch2 DS-0；`VALUE_METHODOLOGY.md` §1 | 规则见 K-0。不要写成“英国当地时间” |

S3 的说明（照实写，不要写“全部输入已换算到 2025 年英镑”）：
- 随模型发布的研究都从 2025 年开始。日期明确的成本输入是 2025 年英镑：储能目录（`currency_base_year` 2025）、抽蓄 CAPEX、政策预算。
- 燃料与碳价没有自己的价格年份，按 A6 视为 2025 年币值。
- 重启成本已按英国 CPI 从 2024 年英镑换到 2025 年英镑（系数 1.0336，见 N-9）。
- 仍有来源年份不同、未做通胀调整的输入：BEIS 2020 成本、2022 年欧元价格按 1.1 换算、核电政策表的 2015/2024 价格年。
- 用户映射的价格若声明了 2025 以外的价格年份，VALUE 只换算币种，不按年份折算，映射审阅给出提示 `GF_MAPPING_PRICE_YEAR`（`backend/data_mapping.py` 第 607–612 行）。

S8 的价格标签（`market_replay` 记录价格口径，界面只渲染；`app/features/shared/format.ts` 第 179–185 行）：

| 价格口径 | 界面标签 | 适用 |
|---|---|---|
| `average_period_cost` | Average period cost (£/MWh demand) | 默认 PSM（时段总费用除以需求） |
| `national_ahead_clearing_price` | National ahead clearing price | staged PSM（日前最后接受报价的统一价） |
| `balance_shadow_price` | Balance shadow price | 完全预见 LP（能量平衡约束的对偶） |
| `ahead_settlement_price` | Ahead settlement price | `value-doctoral-national-psm`（只含日前发电结算） |
| `not_declared` | Price (basis not recorded) | 账本没有声明口径 |

### 3.2 论文复现口径（兼容口径）保留的论文时期设定（D）

这一节写进第 1 章的新小节，并在第 5 章相应位置逐条标注。措辞是“论文复现口径保留……”，不写“论文的做法是错的”。

**市场规则集 `native-doctoral-thesis-v1`：**
- 论文的列语义：调度外盈余不在接纳供给 \(S\) 中，所以能量平衡在 `default_psm_surplus_node_v1` 边界上计算（DEV-BAL-01）；
- 日前与平衡阶段按价格稳定排序（没有“同档储能排在发电之后”）；
- 削减分支按 `curtail_cost` 升序下调，零边际成本的风电先被削减，燃气继续运行；没有重启经济学（论文内核没有机组组合状态，也不比较重启成本）；
- 出清前把 VRE 分流到直接电解：每个 VRE 代理按 \(\min(\text{上期电解出力}+\text{爬坡},\ \text{电解上限})\)，可用量不足时这部分记为泄漏（诊断 `vre_skim_to_electrolysis_mwh`、`vre_skim_leak_mwh`）；
- 储能报价由储能成本模块给出（参考配置 legacy 电价：报价随存放时长线性递增，新批次更便宜）；储能按自身最高报价 `max_bat_price` 结算，没有发电机被接受时收入函数返回空映射；最后一个平衡时段的储能费结转到后续削减时段；
- 互联线进口只在平衡分支出现（N-8）；
- 核电年初未运行，首次被接受之前报价带启动加价（**核电路径依赖**，A15 要求披露，见 N-7）；
- VoLL 为常数 17,000 £/MWh，不读参数。

**输入与读取：**
- 天气 v1 时钟，没有损耗系数，没有倾斜面换算；
- 核电与径流水电 100% 可用；
- 旧读法 legacy-v1（无表头首行、短序列循环），以及预测序列比实测领先一期；
- 通用时序资源的边界价格截为 \(\max(p,0)\)。

**投资与扩容：**
- 储能扩容余量恒为 0（K-9）；
- 三种功率电池各拿 \(0.20B(365)\)（论文设计，修正口径相同）；
- 径流水电兼容资本留在头条（备忘项标为 included）。

**已声明偏差**（`declared_deviations.json`；三条都不改变任何 gate 结论，`gate_effect` 均为 none）：

| 偏差 | 内容 | 口径 | 作用 |
|---|---|---|---|
| DEV-BAL-01（P7-10） | 论文列语义：调度外盈余不在接纳供给 \(S\) 中，能量平衡在 `default_psm_surplus_node_v1` 边界上计算 | 论文复现 | 边界的定义 |
| DEV-BAL-02（P3-01） | 日前满足不了预测时，实现规则仍按预测与实际之差削减，不记切负荷；调度不变，缺口记为 stress event 与缺电量 | 两者 | 只作证据 |
| DEV-BAL-03（P3-14、P5-11） | 默认 PSM 每年新建储能对象，年末存量被丢弃；只报告（`storage_year_boundary`） | 两者 | 只作证据 |

注意：两个口径共同的三项内核规则（下调只做一次、每个储能每期一个净头寸、必发核电盈余只计一次）**不是**论文复现口径的偏差，是两个口径共同的模型规则（U7–U9），正文按规则写。

### 3.3 修正总表（最终状态）

“0.4 位置”写的是落点，en 与 zh 行号见第 4 节。

**两个口径共同的规则（U）**

| # | 规则 | id | 类别 | 0.4 位置 | 草稿 |
|---|---|---|---|---|---|
| U1 | 互联线序列按运行时钟逐期取值 | `p05.interconnector-clock`（P6-24，Q9、A3） | 轨迹 | ch2 互联线；ch5 Native 可用出力 | p05a |
| U2 | GBP1 比利时价格：EUR、逐小时，按 1.1 EUR/GBP 换算，每小时用于两个半小时 | `p05.belgium-price-currency`（P6-02，A5） | 轨迹 | ch2 互联线 | p05a |
| U3 | 互联线潮流文件按 NESO 线路身份接线 | `p05.boundary-identity`（P6-03，A5） | 轨迹 | ch2 互联线 | p05a |
| U4 | GBP1 需求与预测按 R029 审计规则放到 UTC 时钟 | `p05.demand-utc-clock`（P6-04，A5） | 轨迹 | ch2 需求 | p05a |
| U5 | 一律读声明的 `csv_column`，拒绝隐式整数索引列 | `p05.declared-column`（P6-01） | 轨迹 | ch2 读取规则 | p05a |
| U6 | 火电投资净收入扣除运行成本 | `p07.thermal-net-revenue`（P4-01 火电部分，A4） | 轨迹 | ch4 K-10 | p07 |
| U7 | 削减分支的下调每台机组只扣一次，剩余要求降到 0 即停止 | `r41.down-regulation-taken-once`（A15、A26） | 轨迹 | ch5 N-9 | r41 §1 |
| U8 | 每个储能每个时段一个净头寸，各出清阶段共用额定功率 | `p06.storage-net-per-period`（P5-03，A26） | 轨迹 | ch5 N-5 | r41 §2 |
| U9 | 平衡阶段的必发核电盈余只计一次 | `r41.must-run-surplus-counted-once`（A26） | 轨迹 | ch5 N-7 | r41 §3 |
| U10 | 声明的能量平衡边界、盈余路由、逐资产储能审计 | `p04.surplus-node-boundary`、`p04.surplus-routing`、`p04.storage-energy-audit`（P7-10、P3-02、P3-14、P5-11，Q7） | 核算 | ch5 N-13 | p04 |
| U11 | 缺电 stress event 与能量平衡账 | 同 U10（P3-01，A2） | 核算 | ch5 N-13 | p04 |
| U12 | 验证报告 v2、三类 gate、结果发布规则 | `p04.validation-v2`、`p04.validation-gate`（P7-01，Q14） | 核算/发布 | ch1 I-1；ch5 N-13 | p04 |
| U13 | 物理运营成本（不乘报价乘数；含启动项、记录切负荷 × VoLL、循环损耗） | `p06.physical-operating-cost`（P5-06） | 核算 | ch5 N-12；ch4 K-14 | p06 |
| U14 | 成本账 v2：风光储 FOM 为备忘项；完全预见 LP 读 `annual_fixed_opex_gbp` | `p07.cost-ledger-v2`（A7、P4-08） | 核算 | ch4 K-14；ch8 O-1 | p07 |
| U15 | VoLL 17,000 £/MWh | `fx5.voll-17000`（A16-5） | 核算（默认 PSM 的论文规则集）；完全预见 LP、DC、分区中为目标系数 | ch5 N-12；ch6 R-4；ch8 O-2；ch4 K-14 | fx5 |
| U16 | 已供电量 = 需求 − 记录的切负荷 − stress 缺口，用于每 MWh 成本与碳强度 | `r5.served-energy-net-of-stress-shortfall`（A28） | 核算 | ch4 K-14 | r5 §1 |
| U17 | 储能报价账本 `storage_orders`（每条报价的价格、可报量、接受量、状态） | `fx4.storage-offer-ledger`（M-D1） | 核算 | ch5 N-15（可选一句） | 无 |
| U18 | 数据包三层校验与按口径的资格 | `p05.validation-layers`（P6-11、P6-12） | 展示 | ch2 DS-8 | p05a |
| U19 | 内核天气缓存按文件作键 | `p05.weather-cache-key`（P7-02） | 软件 | ch3 W-8（可选） | p05b §1 |
| U20 | 方法身份与 Study 迁移 | `x0.methodology-identity`、`x0.study-revision-migration`（Q13） | 身份 | ch1 I-1 一句 | 无 |

**只在修正口径生效的规则（C）**

| # | 规则 | id | 类别 | 0.4 位置 | 草稿 |
|---|---|---|---|---|---|
| C1 | 天气 v2 时间约定 | `p05.weather-time-convention`（P6-06） | 轨迹 | ch3 W-1 | p05b §2 |
| C2 | 风光文献损耗系数 | `p05.vre-loss-factors`（P6-08，A1、A9） | 轨迹 | ch3 W-2、W-3 | p05b §3（数值以 f2 为准） |
| C3 | 光伏组件平面辐照换算 | `p05.solar-plane-of-array`（A13、A16-6） | 轨迹 | ch3 W-3 | f2 §1 |
| C4 | 核电逐站负荷率、按月停发；GBP1 public2 用逐站名单 | `p05.firm-availability`、`p05.nuclear-generation-end-month`、`p05.nuclear-stations-public2`（A10、A14、A16-7） | 轨迹 | ch5 N-4；ch2 DS-6；ch6 R-5 | f2 §2 |
| C5 | 径流水电 0.3487 × 季节形状 | `p05.firm-availability`、`p05.hydro-dukes-load-factor`（A14） | 轨迹 | ch5 N-4；ch2 DS-6 | f2 §3 |
| C6 | 声明式读取、时钟与数据门 | `p05.declared-reader`、`p05.series-clock`、`p05.data-gate`（P6-05、P6-07、P6-11） | 轨迹/展示 | ch2 DS-3、DS-8 | p05a |
| C7 | 边界价格保留负值 | `p05.raw-boundary-price` | 轨迹 | ch2 DS-7 | p05b §1 |
| C8 | D1-surplus 盈余簿与修正列语义 | `p06.d1-surplus-accounting` | 轨迹/核算 | ch5 N-7 | p06 |
| C9 | 排序键：同 0.01 £/MWh 档内储能排在发电之后 | `p06.storage-after-generation-merit-key`（Q8） | 轨迹 | ch5 N-7 | p06 |
| C10 | 储能费在本期结算 | `p06.storage-fee-per-period` | 轨迹/核算 | ch5 N-10 | p06 |
| C11 | 出清前不分流 VRE 去电解 | `p06.no-vre-pre-clearing-skim`（P3-08） | 轨迹 | ch5 N-8 | p06 |
| C12 | 储能只报循环折旧 | `p06.storage-bid-cycle-only`（Q8） | 轨迹 | ch5 N-6；ch4 K-6 | p06 |
| C13 | 统一边际价结算（含储能、进口） | `p06.storage-uniform-price-settlement`（P5-05，A8(2)） | 核算/轨迹 | ch5 N-10 | p06 |
| C14 | VoLL 读参数 `market.voll_gbp_per_mwh`（默认 17,000） | `p06.voll-chronology-parameter` | 核算 | ch5 N-12 | p06、fx5 |
| C15 | 经济下调顺序：按避免成本排序，燃气与生物质分不停机段与停机段 | `p06.avoided-cost-downward-order`、`r12.economic-downward-order`（P3-03，A19、A22、A22a）；取值币值 `r33.restart-cost-price-base-2025`（A24-4） | 轨迹 | ch5 N-9 | r12（按第 6 节取用） |
| C16 | 互联线进口进入日前出清 | `fx6.day-ahead-interconnector-imports`（S-D3，A16-2） | 轨迹 | ch5 N-8、N-9、N-10；ch2 DS-7 | fx6 |
| C17 | 核电开局在运 | `fx8.nuclear-in-service-at-start`（A18） | 轨迹 | ch5 N-4、N-7 | fx8 |
| C18 | 储能扩容余量取现有储能充电后的剩余盈余 | `p07.storage-leftover-headroom`（P5-01） | 轨迹 | ch4 K-9 | p07（无公式） |
| C19 | 三种功率电池各自的扩容上限 | `r13.per-type-battery-caps`（A20） | 轨迹 | ch4 K-9 | p07（无公式） |
| C20 | 径流水电兼容资本移出头条 | `p07.compatibility-capital-out-of-headline`（P4-03） | 核算 | ch4 K-14 | p07 |

**网络模型（N，只在修正口径下运行）**

| # | 规则 | id | 类别 | 0.4 位置 | 草稿 |
|---|---|---|---|---|---|
| N1 | 分区求解合同 v4：先锁切负荷，再锁报价成本 | `p08.zonal-solver-v4`（P2-01，Q5） | 轨迹 | ch7 T-5 | 数学参考 §2.4 |
| N2 | 下调报价按经济价格；同价按比例分配；下调类别次序 | `p08.dec-economic-pricing`、`p08.pro-rata-ties`、`p08.dec-class-order`（P2-05、P3-04） | 轨迹 | ch4 K-3、K-5；ch7 T-1、T-3 | p08 §1 |
| N3 | 燃气、生物质下调报价按经济下调顺序分两段 | `r32.network-economic-downward-order`（A24-3，依据 A19、A22、A22a），规则集 `network-economic-v2`；取值币值 `r33.restart-cost-price-base-2025` | 轨迹 | ch4 K-3；ch7 T-1 | r32（按第 6 节取用） |
| N4 | 网络成本 = 分区解 − 无网络 LP 反事实 | `p08.network-free-counterfactual`（P2-02/03/04） | 核算 | ch7 T-4；ch4 K-14 | p08 §2 |
| N5 | 边界边际值取 primary 阶段对偶 | `p08.boundary-primary-dual`（P2-06） | 核算 | ch7 T-6 | p08 §3 |
| N6 | DC 网络按母线份额展开 | `p08.network-share-expansion`（P1-01） | 轨迹 | ch7 T-8 | **无** |
| N7 | staged 储能 dwell 披露（数值不变） | `p06.staged-dwell-disclosure`（P5-15） | 展示 | ch4 K-7 | p06（末段） |
| N8 | 运行期 fallback 审计（只报告） | `p08.runtime-fallback-audit`（P2-13） | 展示 | ch7 T-9 | 无 |

**两个口径共同的披露（不是修正）**

| 披露 | id | 0.4 位置 | 草稿 |
|---|---|---|---|
| 生物质没有补贴收入，几乎不被调度 | advisory `VALUE-ADV-BIOMASS-SUPPORT-NOT-MODELLED`（A24-2；medium；只对冻结机组含生物质的 Run 显示；不进方法身份） | ch5 N-1；ch1 局限 | r33 |

**数据包修订（不是方法修正）**：
- R029 public1 与 GBP1 public1 共用的逐时光伏曲线 `sa.csv` 有 8,761 个值，多出的是最后一行（ERA5 时次 2023-01-01T00:00Z，夜间的 0）。
- 本地修订包 R029 public2（`value-uk-calendar-vx-trade001-public2`）与 GBP1 public2（`value-uk-open-data-pack-public2`）去掉这一行，并声明三条 VRE 曲线为逐时（`interval_minutes` 60）。所有现有读法的数值不变。
- 两个修订包都只在本地构建、登记为 `scientific_reference`，没有发布（A24-1、A16-7）。

## 4 方法学正文逐章修改清单（0.3 → 0.4，en 与 zh 同步）

格式：
- **位置**：en 行号 / zh 行号与小节标题；
- **现文**：摘录 0.3 原句；
- **新文**：写 0.4 应表达的内容，公式给出 LaTeX；
- **口径**：用第 2.3 节的标记。

每一处都要中英两版同时改，见第 8 节。

### 4.1 `introduction.md`（第 1 章）

**I-1 新增小节 “Methodology profiles / 方法学口径”**
- 位置：en 第 30–34 行、zh 第 29–33 行（“Data and research configurations / 数据与研究配置”）之后。口径：两者。草稿：无。
- 结构：中英两版各只新增一个 `##` 标题，最多一张表，以保证 `assemble.py` 的配对检查通过。
- 新文（EN）：

> ## Methodology profiles
>
> This methodology describes the VALUE model as published: the corrected methodology (`value-corrected`, “Corrected methodology (default)”), which new Studies and Runs use by default. Every Run records its methodology profile. A second profile, the doctoral reproduction (`doctoral-lineage-0.6.0a2`, “Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)”; it is not an exact reproduction of the 2026-07-18 retained trajectory), is a compatibility profile. It keeps the thesis-era settings as implemented in VALUE 0.6.0-alpha.2, for example wind curtailed first at zero cost, no wind and solar loss factors, no availability derating of nuclear and hydro, and the original data readings. Where it differs from the corrected methodology, the chapters below say so.
>
> Some rules apply to both profiles: the interconnector series on the period clock; the GBP1 Belgium price in EUR per hour, interconnector flows by line identity and demand on the UTC clock; declared-column reading; thermal investment net of running cost; down regulation in the curtailment branch taken once; one storage position per store and period; must-run surplus counted once in balancing; stress events for unmet demand; and the accounting rules (energy-balance boundary, validation report, cost ledger, value of lost load, energy served). All other rules of this methodology apply to the corrected methodology only.
>
> The doctoral reproduction accepts only thesis-lineage modules and thesis-era data packs (GBP1 public1, the VALUE UK 1000 TWh reproduction pack, VALUE 101 and the synthetic contract pack), refuses to run when external code is enabled, and writes its reference configuration (legacy storage tariff, doctoral carbon-factor scenario) into the Study. Its annual results appear on result pages only when every raw invariant passes; otherwise they remain available in Inspect and exports. Under the corrected methodology a failed validation gate withholds annual economic results. The profile is part of a Run's method identity: Runs of different profiles are compared as different methods, and a change of method in a saved Study requires explicit confirmation.
>
> Three settings are model assumptions in both profiles: money is in constant start-year terms; investment tests compare return and payback without discounting; wind, solar and storage carry capital cost and depreciation only, their fixed operating cost being part of levelised capital.

- 新文（ZH）：

> ## 方法学口径
>
> 本方法学描述发布的 VALUE 模型，即修正口径（`value-corrected`，“Corrected methodology (default)”），也是新 Study 和 Run 的默认口径。每个 Run 都记录所用的方法学口径。另一个口径是论文复现口径（`doctoral-lineage-0.6.0a2`，“Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)”；它不是 2026-07-18 保留轨迹的精确复现），属于兼容口径：它按 VALUE 0.6.0-alpha.2 的实现保留论文时期的设定，例如零成本风电先削、风光不乘损耗系数、核电与水电不按可用率折减、沿用原有的数据读法。它与修正口径不同的地方，在后面各章中逐一注明。
>
> 以下规则两个口径都适用：互联线序列按时段时钟逐期取值；GBP1 的比利时价格按逐小时欧元读取、互联线潮流按线路身份分配、需求放到 UTC 时钟；按声明的列读取；火电投资扣除运行成本；削减分支的下调只做一次；每个储能每个时段只有一个头寸；平衡阶段的必发盈余只计一次；未满足需求记为 stress event；以及核算规则（能量平衡边界、验证报告、成本账、失负荷价值、已供电量）。本方法学的其他规则只适用于修正口径。
>
> 论文复现口径只接受论文谱系模块和论文期数据包（GBP1 public1、VALUE UK 1000 TWh 复现包、VALUE 101 和合成合同包）；启用了外部代码时拒绝运行；选择该口径时，参考配置（legacy 储能电价、论文碳因子情景）写入 Study。只有原始不变量全部通过，它的年度结果才在结果页发布，否则只在 Inspect 和导出中提供。修正口径下，任一验证 gate 失败，年度经济结果不发布。口径是 Run 方法身份的一部分：不同口径的 Run 按不同方法比较；已保存 Study 的方法变化须在界面上显式确认。
>
> 以下三项在两个口径中都是模型设定：金额按起始年不变币值计价；投资判据比较收益率与回收期，不折现；风电、光伏和储能只有资本成本和折旧，固定运营成本含在平准化资本中。

- 可选：加一张已声明偏差表（第 3.2 节三行），或放在第 5 章 N-13；两版放在同一位置。
- 可选实例：随模型发布的论文复现参考运行（VALUE 101 一天、VALUE 101 两年、GBP1 public1 第一个模型年）原始不变量全部通过，年度结果在结果页发布。不要写“论文复现口径的年度结果总会发布”：在其他数据或配置上仍可能扣发。

**I-2 第 1 章 “Annual calculation / 年度计算结构” 末段**
- 位置：en 第 28 行 / zh 第 27 行。口径：两者（编辑性）。
- 现文：“The current staged market, the R029 national research algorithm, national joint clearing, and perfect-foresight linear programming each specify their own bidding…”
- 新文：补一句，说明默认全国 PSM 是第 5 章的 Native（`value-bid-at-cost-psm`），staged 市场用于网络与分区研究。

**I-3 第 1 章局限（可放在 I-1 末段或章末）**
- 补一句：生物质没有补贴收入（CfD、ROC），见 S12，草稿 r33 §4。

### 4.2 `datasets.md`（第 2 章，en 与 zh 行号相同）

**DS-0 第 12–18 行，“Temporal resolution and input roles / 时间分辨率与输入角色”**
- 口径：两者（S14）。草稿：r5 §2、§3（需求单位与逐时需求）。
- 第 16 行公式不变。第 18 行（需求按 MW 载入）保留，后面补三点：
  - 时段在 UTC 时钟上，模型年固定 365 天，没有夏令时；闰年的源序列删去 2 月 29 日，需求序列删去后按全年电量重新缩放（`weather_demand_ensembles.normalize_half_hour_year`）。完整规则写在第 4 章 K-0，这里链接过去；
  - VALUE 101 需求文件的表头 `mwh` 和数据包标签 MWh/period 是已知的误标，这些字节一直按 MW 读取；文件本身不改写，两个口径的读数相同；
  - 用户替换的需求序列按声明的源单位换算：MWh/period ÷ 时段时长（小时）= MW。逐时数据见 DS-10。

**DS-1 第 9 行，研究配置表 “Current GB zonal study … `value-uk-open-data-pack-v1`”**
- 口径：C 与 D。
- 新文：加注三点：
  - GBP1 public1 只满足论文复现口径的资格；
  - 修正口径可用的 GB 国家级研究包是本地修订包 GBP1 public2 与 R029 public2，都没有发布；正文写成 “local revision, not published”；
  - 网络模块只在修正口径下运行（Q3）。
- 23 区研究以哪个基础包运行，写之前须确认（第 9 节第 6 条）。

**DS-1b 第 8 行，R029 一行**
- 新文：补注 R029 public1 在 0.7.0 中的情况（见 R-1）：
  - 论文复现口径不接受 R029；
  - 修正口径下，R029 public1 的逐时光伏曲线 8,761 个值在严格读取中报 `GF_DATA_SHORT_SERIES`，所以只有本地修订包 R029 public2 能运行。

**DS-2 第 34 行**
- 口径：U（命名）。
- 现文：“`doctoral_demand` preserves the decimal precision … The interconnector reader also checks …”
- 新文：R029 的需求与互联线由共享声明式读取器读取（`series_reader.py`，经 `data_method.read_role` / `read_boundary`）。`doctoral_demand`、`doctoral_interconnectors` 在源码中不存在。草稿：p05a “One declarative reader”。

**DS-3 第 36–53 行，通用读取规则段落与伪代码**
- 口径：修正口径的读法（C6）为正文；论文复现口径的读法作标注段落；两者共同的 U5 写在前面。草稿：p05a。
- 现文：“selects the column with the most valid numbers … cycles or truncates sequences …”，以及 `read_series`/`align` 伪代码。
- 新文：
  - **两个口径共同（U5）**：binding 声明了 `csv_column`、`csv_header` 时一律按声明读取；隐式选中的整数序号列报 `GF_DATA_INDEX_COLUMN`。
  - **declared-v2（修正口径）**：
    - 只有首行全部是非数值时才推断为表头；多个数值列有歧义时，严格读取报 `GF_DATA_AMBIGUOUS_COLUMN`；
    - 时钟先按 `interval_minutes`（或逐小时长度 8,760/8,784）确定分辨率，逐时值每小时用于两个半小时，再截取前 17,520 期；
    - 17,568 期的闰年序列删去 2 月 29 日，需求角色删去后按全年电量重新缩放；
    - 短于一年的序列：声明为 `cyclic`（或按角色约定循环）时从开头重复补齐；未声明时，严格读取报 `GF_DATA_SHORT_SERIES`。严格读取适用于修正口径下的非工作区数据包；用户工作区数据包用宽松读取，从开头重复补齐，映射时须另行确认（DS-10）。
  - **legacy-v1（论文复现口径）**：保留旧规则（选有效数值最多的列、短序列循环或截断），除上面的 U5 外不变。
  - 伪代码按两种模式各给一份，或者给一份并用条件分支标注。依据：`gridform_core/series_reader.py` 第 411–453 行（`align_clock`）、`gridform_core/data_method.py` 第 118 行（严格与宽松的选择）。

**DS-4 第 55 行，“the first forecast value, 21,560, is treated as a header …”**
- 口径：D 与 C。
- 新文：写明这是 legacy-v1 的行为，论文复现口径保留它，所以论文复现口径的预测序列比实测领先一期；修正口径下首值作为数据读入。

**DS-5 第 66–81 行，需求 UTC 处理**
- 口径：U（U4）。草稿：p05a 表中 `p05.demand-utc-clock` 一行。
- 新文：补一段，说明同一规则（R029 审计规则）也作用于 GBP1 public1 的需求与预测，两个口径都适用：
  - 2022-10-30 重复的结算时段保留较晚的发布；
  - 四个缺口（09:00、09:30、23:00、23:30 UTC）线性插补；
  - 效果（可选）：夏令时结束后的需求曲线位于正确的 UTC 时段，全年需求比旧读法多 5,407 MWh。

**DS-6 第 89 行与第 96–97 行的表（核电、径流水电）**
- 口径：C。
- 新文：补一句并链接到第 5 章 N-4：修正口径下核电按站降额、按月停发，径流水电按 DUKES 负荷率乘季节形状；论文复现口径下两者 100% 可用。

**DS-7 第 152–173 行，“Interconnectors and zonal demand”**
- 第 156 行：
  - 现文：“R029 retains negative input prices; the current general chronology resources apply \(\max(p,0)\).”
  - 新文：修正口径的通用时序资源保留负价（C7，`p05.raw-boundary-price`）；论文复现口径的通用时序资源截为 \(\max(p,0)\)；R029 thesis96 路径保留负价。
- 新增一段：GBP1 public1 的读取规则（U1–U3，两个口径）。三条规则都按对象 sha256 在真相登记表 `known_data_objects_v1.json` 中识别：
  - **比利时价格（U2）**：`Belgium_price.csv` 是逐小时 EUR/MWh。读 `Price (EUR/MWhe)` 列，按 R029 approved_r03 的固定汇率 1.1 EUR/GBP 换算，每个 UTC 小时用于两个半小时：

$$
p^{\mathrm{GBP}}_{t}=\frac{p^{\mathrm{EUR}}_{\lfloor t/2\rfloor}}{1.1}.
$$

  - **线路身份（U3）**：潮流文件按 NESO 线路身份接线（`NEMO_FLOW` 为比利时，`BRITNED_FLOW` 为荷兰，`NSL_FLOW` 为挪威 …），每条 Connection 只接本国序列。
  - **逐期时钟（U1）**：内核第 \(t\) 期取第 \(t\) 行：

$$
F^{\mathrm{kernel}}_{t}=F_{t},\qquad t=0,\dots,17{,}519 .
$$

  - 正文只写规则，不写“旧读法错在哪里”，也不写修复前后的数字（A26：方法学描述新模型，不是论文结果的勘误）。
- 第 158–163 行公式不变。补一句：GBP1 的潮流文件标为 MWh/period，实际是瞬时 MW，按 MW 读取（P6-12）。
- 第 158 行，进口能力的用途（C16）：
  - 现文：“positive values assign import capacity and negative values assign export capacity”。
  - 新文：句后补一句。EN：“Under the corrected methodology the import capacity is offered to the day-ahead clearing; under the doctoral reproduction only to the balancing stage (Chapter on national dispatch).” ZH：“修正口径中进口容量进入日前出清；论文复现口径中只进入平衡环节（见全国调度章）。”（fx6 §3）
  - 应用中的数据角色名为 “<Country> interconnector availability (+ import / - export)”，正文提到角色时用这个名字。
- 第 165 行之后补披露：本地修订包的互联线潮流符号记为 `declared_unverified`（正值进口、负值出口沿用旧模型约定，逐国年净潮流没有用来源核实）。

**DS-8 新增一段：数据包校验与口径资格**
- 位置：“Data and implementation” 之前。口径：U18 加 C6。草稿：p05a “Validation layers”。
- 新文：
  - 数据包校验分三层：结构层（只有它决定 `valid`）；时序层（线路身份、价格币种、无时间戳的本地时间需求、登记的行序缺陷、预测与实测错位、声明的时间戳）；合理性层（范围检查，`value_data_plausibility_v1.json`）。
  - `profile_eligibility` 决定哪些发现阻断哪个口径：修正口径下，非工作区包的时序发现和科学参考包的合理性失败是 preflight 错误；论文复现口径下只是警告。所以 GBP1 public1 能安装，但修正口径的 preflight 拒绝它。
  - `profile_eligibility` 同时套用口径的数据包白名单（与 Study 解析、preflight 同一个检查 `methodology.data_pack_violation`）：论文复现口径没有列出的包（任何用户工作区包、VALUE 101 网络包）对它不可用，阻断码 `VALUE_PROFILE_COMBINATION_UNSUPPORTED`，理由 “not a thesis-era pack”。
  - 校验层不检查 VRE 技术曲线的时钟，所以正文不要写“三层校验通过即可运行”。

**DS-9 第 229 行，“Data and implementation”**
- 口径：U。
- 新文：把 `doctoral_demand`、`doctoral_interconnectors` 换为 `series_reader`、`data_method`，并补 `interconnector_identity`、`data_validation_layers`、`model_clock`、真相登记表 `known_data_objects_v1.json`。

**DS-10 新增一段：用户映射的数据**
- 位置：DS-8 之后。口径：修正口径（用户工作区数据包只能用修正口径运行）。草稿：r5 §2、§3（只有需求部分）。
- 新文（只写会改变读数的规则）：
  - 时间戳列可以声明为 UTC 或 Europe/London；Europe/London 的时间在映射时逐行换成 UTC。日期顺序可声明为 DD/MM/YYYY 或 MM/DD/YYYY，或由数据自动判定。时序层逐行检查不可读、重复、倒序、缺口和步长不规则，有问题不能提交。
  - VALUE 按行序把序列当作模型年读取（从 1 月 1 日 00:00 UTC 起），每个模型年重复使用，不移动日期、星期或节假日；时间戳的年份与模型年不同时给出提示，但不改读法。正文不要写“时间戳已与模型时钟对齐”。
  - 逐时需求（8,760 或 8,784 行，或声明的时间戳步长为 60 分钟）在映射时展开：每小时的 MW 用于该小时的两个半小时，逐时的 MWh/period 按每小时电量换算为 MW；之后 8,784 小时的闰年按 DS-3 的规则处理。
  - 不满一个模型年的序列从开头重复补齐，映射时须另行确认。
  - 价格按声明的汇率从 EUR 换算为 GBP，汇率口径为 annual average、monthly average 或 fixed rate；价格年份不折算（S3）。
  - 替换需求的年电量与被替换序列相差超过 1.5 倍（或不足 0.67 倍）时给出提示，写出两个年电量；只是提示，不拒绝。

### 4.3 `core_weather.md`（第 3 章，en 与 zh 行号相同）

**W-1 第 35 行，代表点小时取值**
- 口径：C1 为正文，D 作标注。草稿：p05b §2。
- 现文：“Half-period \(t\) uses source hour \(h(t)=\lfloor t/2\rfloor\bmod H\) …”
- 新文：修正口径（天气 v2）：

$$
h(t)=\begin{cases}
\left(\lfloor t/2\rfloor+1\right)\bmod H, & \text{accumulated field stamped at the end of its hour (ERA5 \texttt{ssrd})},\\[2pt]
\left\lfloor (t+1)/2\right\rfloor\bmod H, & \text{instantaneous field (\texttt{u100}, \texttt{v100}, \texttt{wind\_speed})}.
\end{cases}
$$

  - binding 可以声明 `time_convention`，否则按 GRIB `stepType` 判定，没有 step type 的变量按瞬时量处理。
  - 效果：GBP1 伦敦站光伏质心为 11.97 UTC；12 月 21 日首个非零半小时从 08:00 UTC 开始，最后一个在 16:00 结束。
  - 论文复现口径（天气 v1）保留原式 \(h(t)=\lfloor t/2\rfloor\bmod H\)。

**W-2 第 39–53 行，风电曲线**
- 口径：C2。草稿：p05b §3；披露见 f2 §4。
- 新文：在第 51 行之后加入损耗系数：

$$
a^{\mathrm{corr}}_{w}(v)=\lambda_k\,a_w(v),\qquad
\lambda_{\mathrm{on}}=0.95\times0.97\times0.98=0.90307,\qquad
\lambda_{\mathrm{off}}=0.88\times0.945\times0.98=0.814968 .
$$

  - 三个因子依次为尾流、可用率（按电量计）、电气损耗；海上合计损耗约 18.5%，作者已在 A9 接受。
  - 出处：陆上 Simley et al. 2025、Conroy et al. 2011、Colmenar-Santos et al. 2014、Lee & Fields 2021；海上 Barthelmie et al. 2009、Warder & Piggott 2025（预印本）、ORE Catapult & The Crown Estate SPARTA 2017/18、Colmenar-Santos et al. 2014。书目信息见参数表 `sources`。
  - 必须写明：不对统计负荷率标定（Q15）；逐期形状仍来自 ERA5，弃电仍由出清决定；ERA5 自身的风速偏差不是损耗，没有去除。
  - 第 53 行的数值例子（8 m/s → 0.5476061707）是不乘损耗系数的曲线值，标注为论文复现口径的取值。修正口径的例子：\(0.5476061707\times0.90307=0.4945267046\)，100 MW 陆上风电可用 49.45 MW。

**W-3 第 55–64 行，光伏曲线**
- 口径：C2、C3。草稿：f2 §1。
- 第 58–62 行的 \(a_s(R)\) 保留，作为水平面 GHI（kW m⁻²）：

$$
G_t=a_s\!\left(R_{h(t)}\right).
$$

- 修正口径对 v2 时钟下的 ERA5 逐时累积量做组件平面换算，再乘性能比 PR = 0.83。
- 太阳位置按时段**中点**计算：模型年为 365 天 UTC 年，第 \(t\) 期是第 \(\lfloor t/48\rfloor+1\) 天，UTC 时刻为 \((t\bmod 48)/2+0.25\)。赤纬、时差和日地距离修正用 Spencer (1971)。换算公式：

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

- 说明：
  - \(k_d\) 用 Erbs, Klein & Duffie (1982)；斜面换算用 Hay & Davies (1980)，地面反照率 \(\rho=0.2\)，朝南；
  - 倾角 \(\beta\) 用 Jacobson & Jadhav (2018) 的北半球拟合式，\(\phi\) 为站点纬度（度），GBP1 各站约 35.7–37.7°；
  - 天顶角大于 87° 或 \(G_t=0\) 时 \(B_t=0\)，全部按各向同性散射处理；倾角为 0 时逐期精确返回 GHI。
- 不换算的情形：不是 v2 ERA5 累积量的光伏源，修正口径取 \(a^{\mathrm{corr}}_{s,t}=0.83\,G_t\)。具体是 VALUE 101 的合成样本，以及 R029 的天气文件（`ssrd` 没有 GRIB step type，也没有声明时间约定；R029 public1 与 public2 用同一份天气）。
- 状态：模型选择已由作者认可（A16-6），性能比已在 A9 接受。正文不带待审核标记，但不要写“已校准”。书目信息与拟合系数没有联网复核，发布前请核对一次（第 9 节第 9 条）。
- 结果（GBP1 public1 气候态，11 个光伏站）：各站 POA/GHI 1.05–1.10，年散射比例 0.63–0.75，代表站点平均 CF 0.1065。
- 披露：GBP1 天气是 2020–2024 多年平均气候态（P6-09）。平均后晴空指数被抹平（伦敦能量加权 \(k_t\) 0.47，最大 0.73），散射比例偏高，倾斜增益偏小；同一代码在合成晴空年（51.5°N，所有白天时段 \(k_t=0.65\)）中增益为 33%。只报告，不校正。f2 §1 末段可用。

**W-4 新增小节 “Capacity factors compared with DUKES / 容量因子与 DUKES 对照”**
- 位置：第 120 行之后、“Annual wind and solar capacity limits” 之前。口径：C（S5 披露）。草稿：f2 §4（表格与六条原因可用；表格只保留下面几列）。
- 表（模型 CF：代表站点等权平均，17,520 个半小时，弃电前；DUKES：表 6.3 标准口径）：

| 技术 | GBP1 修正口径 | DUKES 2019–2024 | DUKES 2020–2024 | 修正口径 / DUKES 2020–2024 | GBP1 论文复现口径（无损耗） |
|---|---:|---:|---:|---:|---:|
| 陆上风电 | 0.4026 | 0.2593 | 0.2582 | 1.56 | 0.4458 |
| 海上风电 | 0.4913 | 0.4016 | 0.4009 | 1.23 | 0.6028 |
| 光伏 | 0.1065 | 0.1033 | 0.1025 | 1.04 | 0.1201 |

  - 可加一行注释：VALUE 101（合成，不与 DUKES 比较）修正口径 0.3731 / 0.2665 / 0.2075；R029 修正口径 0.4022 / 0.4913 / 0.0996（光伏不换算）。
  - 运行结果摘要的 `vre_capacity_factor_disclosure` 字段给出同一张表（`vre_cf_disclosure.py`）。
  - 六条原因照 f2 §4 写：ERA5 100 m 风速未做偏差校正（Staffell & Pfenninger 2016）；每站一条单机自由流功率曲线；模型 CF 为弃电前可用出力，DUKES 为扣除弃电和约束调度后的实际发电；代表站点等权平均，不是全国装机加权；GBP1 为多年平均气候态；DUKES 小型光伏发电量是估算值。
  - DUKES 对照列作者已审核（A21），只作披露、不作标定。DUKES 风电合计行 2020、2021 年的值与分项不符，没有使用。中文版表格的行列须与英文版一致。

**W-5 第 122–133 行，“Annual wind and solar capacity limits”**
- 口径：两者（S9）。
- 新文：补披露：投资侧技术平均曲线 `sa.csv`、`wa.csv`、`we.csv` 不乘损耗系数、不做倾斜面换算，形状和水平都与调度侧天气不同；下一轮统一。

**W-6 第 131 行，`sa.csv` 的 8,761 个值**
- 现文：“Solar `sa.csv` contains 8,761 values, of which the first 8,760 hours are used after conversion to half-hours …”
- 新文：保留这句，补两点：
  - 多出的第 8,761 个值对应 ERA5 时次 2023-01-01T00:00Z（下一年的第一个时次，夜间的 0）；逐时重复后截取 17,520 期的读法自然丢掉它，所以论文复现口径的读数不变；
  - 修正口径的严格读取要求声明分辨率，所以只有本地修订包（R029 public2、GBP1 public2：去掉最后一行并声明逐时）能被修正口径读取，读数与上面逐位相同。
- 时间标注（曲线按时间戳标注，即每行是截至该时次的一小时累积）是否改为按区间起点，作者未定（第 9 节第 1 条）。写之前按现状写“按时间戳标注”。

**W-7 第 164 行，R029 2025 年的 1,878 个负净需求时段**
- 口径：待确认。这是 R029 thesis96 路径的数值，该路径在任何口径下都用冻结的 v1 天气（第 2.2 节）。0.4 中要么标注 “computed with the thesis96 pathway (weather v1)”，要么在确定的数据包与口径上重算（第 9 节第 5 条）。

**W-8 第 166–168 行，“Data and implementation”**
- 补 `site_weather.py`、`solar_irradiance.py`、`firm_availability.py`、`data/weather/value_uk_vre_loss_factors_v1.json`、`vre_cf_disclosure.py`。
- 可选：天气缓存按文件作键（U19）。

### 4.4 `core.md`（第 4 章：staged 市场、通用投资、成本；从第 42 行起 zh = en − 1）

**K-0 第 5–7 行，“Model clock and annual state / 时钟与年度状态”**
- 口径：两者（S14）。草稿：无（规则见 `gridform_core/model_clock.py` 开头的说明）。
- 现文：“Each model year contains 365 days and 17,520 half-hour periods, with \(\Delta t=0.5\) h. …”
- 新文：保留原句，补模型时钟规则：
  - 时段是 UTC 半小时；模型年固定 365 天，2 月 29 日不是模型日，没有夏令时；
  - 模型年 \(Y\) 的第 \(p\) 期从 \(Y\) 年第 \(\lfloor p/48\rfloor\) 个模型日的 00:00 UTC 起算（从 0 计，跳过 2 月 29 日），加上日内偏移 \((p\bmod48)\times0.5\) h；
  - 所有时序输入在运行前放到这个时钟上：闰年的源序列删去 2 月 29 日；声明为 Europe/London 的映射数据在映射时逐行换成 UTC；
  - 结果、回放和导出中的时间一律写成带 `Z` 的 ISO 8601，标注 UTC。

**K-1 第 43/42 行，日前按“价格、报价标识”排序**
- staged 日前阶段仍按 `(price, offer_id)` 排序，不改。

**K-2 第 49/48 行，“Any ahead shortfall is recorded and passed to the realisation stage”**
- staged 不改。默认 PSM 在这一点上不同（S4），写在第 5 章 N-8，不要在这里写成全局规则。

**K-3 第 51/50 行，下调容量“价格取弃电成本的相反数，缺省为 0”**
- 口径：N（N2、N3）。草稿：p08 §1、r32 §2。
- 现文：“Their downward capacity is \(q_a^0\), priced at the negative of the curtailment cost, which defaults to 0.”
- 新文：平衡报价按平衡机制约定：接受的上调报价得到 \(x\,p\)，接受的下调报价退回 \(x\,p\)，平衡目标中下调项为 \(-p^{\mathrm{dec}}x\)，下调价最高者先被接受。下调价：

$$
p^{\mathrm{dec}}_{a,t}=\begin{cases}
c_a=m_{\mathrm{dec}}\,SRMC_a-s_a, & \text{fuel units; for gas and biomass the running range } (1-m_a)P_a,\\[2pt]
a_a(H)=c_a-\dfrac{S_a(H)}{m_a\,H}, & \text{gas and biomass shutdown segment } m_aP_a,\ H\ge T_a,\\[6pt]
\min\!\big(a_a(H),\ \min_{j\ne a}\mathrm{round}(p^{\mathrm{dec}}_{j,t},2)-0.01\big), & \text{gas and biomass shutdown segment},\ H<T_a,\\[2pt]
m_{\mathrm{dec}}\,p_{a,t}, & \text{imports},\\
-s_a, & \text{wind, solar, run-of-river hydro},\\
m_{\mathrm{dec}}\,SRMC_a-s_a-\pi_a, & \text{nuclear}\ (\pi_a=100\ \text{GBP/MWh by default}),\\
\min\!\left(p^{\mathrm{up}}_{a,t}\,\eta^c_a\eta^d_a,\ \min_k p^{\mathrm{up}}_{k,t}\right), & \text{storage}.
\end{cases}
$$

  - 参数：
    - \(m_{\mathrm{dec}}\) 为 `market.dec_multiplier`（默认 1，且不大于报价乘数）；
    - \(s_a\) 来自 `market.policy_support_gbp_per_mwh_by_technology`（未列出的技术为 0）；
    - \(\pi_a\) 来自 `network.inflexible_dec_premium_gbp_per_mwh_by_technology`；
    - \(P_a\) 为日前计划量（聚合机组没有开停机状态，日前排了的机组视为在线满载）；
    - \(m\)、\(S(H)\)、\(T\) 与 \(H\) 的取值见第 5 章 N-9（与默认 PSM 同一张参数表、同一个净节省函数）。
  - \(H=(1+n_t)\,\Delta t\)，\(n_t\) 为 \(t\) 之后连续满足“预测需求 ≤ 申报的 VRE 与核电可用量”的时段数；分区模式用对齐后的全国预测需求。
  - 技术映射：CCGT、OCGT、`gas`（资产 id 含 OCGT 时按 OCGT，否则按 CCGT）、生物质（`bio*`）分两段；其他燃料机组（DSR、油）只有一段，价为 \(c_a\)。
  - 写明后果：
    - 被下调的燃气机组恰好退回它节省的运行成本，没有横财；
    - 不停机段（\(c>0\)）总在弃风之前；
    - 停机段只有净节省高于风电下调价（无补贴为 0，有补贴为 \(-s\)）时才先于弃风，同价时风电在前；
    - \(a<c\)，所以同一机组的停机段不会先于它自己的不停机段被接受；
    - 最后手段段按它的报价结算。
  - 这是阻塞管理与平衡的报价规则，只在修正口径的网络模型中运行。

**K-4 第 58/57 行，“Storage downward bids are priced at 0.”**
- 新文：使用 K-3 的储能一行。

**K-5 第 60/59 行，“Identifiers break price ties …”**
- 口径：N（N2、N3）。
- 新文：同价、同方向、同类别的报价按可用电量比例分配：

$$
\frac{x_k}{\overline x_k}=\frac{x_{k_0}}{\overline x_{k_0}}\qquad\text{for all }k\text{ in the tie group of }k_0 .
$$

  - 上调：价格升序；同价时储能排在发电之后（Q8）。
  - 下调：按取整到 0.01 £/MWh 的下调价降序，再按共享类别次序，最后按精确价格。类别次序：燃料机组（不停机段）→ 进口 → 储能充电 → 径流水电 → 风光 → 燃气与生物质停机段 → 核电 → 短于最短停机时间的停机段（`fuel, import, storage, run_of_river, vre, fuel_shutdown, nuclear, fuel_shutdown_last_resort`）。
  - 写明后果：改名不会改变调度；储能在风光被弃之前先吸收盈余（储能下调价常被上限压到 0，与无补贴风电同价，类别次序让储能先充）。

**K-6 第 94–119/93–118 行，动态储能报价**
- 公式作为模块定义保留。补：
  - 修正口径的默认 PSM 中，`dynamic-annual-storage-cost` 2.0.0 只报循环折旧（C12，Q8）：

$$
p_s=c_{\mathrm{cycle}}\ \ (\text{batteries}),\qquad p_s=0\ \ (\text{pumped hydro, hydrogen}),\qquad \text{oldest tranche first}.
$$

  - \(h_{\mathrm{hold}}\) 仍计算并报告，只用于投资充足性诊断，不进入报价，也不进入投资决策。
  - legacy 电价、用户公式和外部储能模块保留各自的报价。论文复现口径的参考配置是 legacy 电价，它的白名单不含 `dynamic-annual-storage-cost`。

**K-7 第 119/118 行，“The current staged caller passes a holding time \(d=0\) …”**
- 补披露（N7）：staged 储能报告记 `dwell_source = not_tracked_staged_single_pool`；与基于 dwell 的成本模块搭配时，preflight 给出警告 `GF_STAGED_DWELL_NOT_TRACKED`。数值不变。

**K-8 第 121–131/120–130 行，储能固定运维表**
- 表保留（它是报价年成本 \(A\) 的输入）。补一句（S1）：成本账中风光储 FOM 是备忘项，不进头条，也不在投资决策中扣除。

**K-9 第 135–167/134–166 行，“Current storage expansion limit”**
- 口径：C（C18、C19）为正文，D 作标注。草稿：p07 “Storage expansion headroom”（只有文字，公式按下面新写）。
- **修正口径**（`value-storage-expansion-policy` 5.1.0）：

$$
X_t=\max(L_t,0),\qquad L_t=XS_t+W^{\mathrm{VRE}}_t,\qquad
N_t=\max\!\left(D_t-G_t-d_t,\ 0\right),
$$

  - \(L_t\) 是现有储能充电之后剩下的盈余，由默认 PSM 逐期发布为 `storage_headroom_inputs`；在修正规则集的列语义下等于非 VRE spill \(XS_t\) 加 VRE 弃电 \(W^{\mathrm{VRE}}_t\)；
  - \(G_t\) 是 VRE 毛出力（修正列语义）；\(d_t\) 是现有储能放电。
  - 虚拟储能与 \(B(h)\) 同 en 第 145–165 行（zh 第 144–164 行）。功率电池与氢储的上限：

$$
H^{\mathrm{bat}}=f\,B(365),\qquad H^{\mathrm{H_2}}=f\,\max\!\big(B(0)-B(52),0\big),\qquad f=\texttt{expansion.storage\_cap\_fraction}=0.2,
$$

$$
\Delta P_{k}\le H^{\mathrm{bat}},\qquad k\in\{\mathrm{1C},\mathrm{0.5C},\mathrm{0.25C}\}.
$$

  - \(B(365)\) 等于代码中 daily_loop 与 intraday 两段之和，即 0.3 第 165 行的“日”与“跨日”两段之和。
  - 1C、0.5C、0.25C 三种电池**各自**以 \(H^{\mathrm{bat}}\) 为上限，合计最多 \(3H^{\mathrm{bat}}\)。这是论文的设计：三种电池服务时长不同，0.2 本身已是削弱过的比例。投资步对每种电池分别扣减各自的上限；同一种电池有多个 owner 时按 owner 顺序贪心分配。
  - 年度时钟不是 17,520 个半小时时，余量为 0，原因记 `partial_year_chronology`；PSM 没有给出剩余盈余序列时，余量为 0，原因记 `leftover_trace_unavailable`。目前只有默认 PSM 发布这条序列；与其他 PSM（staged、完全预见 LP、DC、Doctoral 路径）组合时，修正口径的储能扩容关闭，并记录原因。
- **论文复现口径**：第 137–141 行原式保留。补一句：默认 PSM 中接纳的 VRE 从不超过需求，所以 \(X_t\equiv0\)，储能余量恒为 0。三种电池各拿 \(0.20B(365)\) 与修正口径相同。

**K-10 第 179/178 行，运营成本字段**
- 口径：U6。草稿：p07 “Net revenue”。
- 现文：“Operating-cost field \(O_a\) comes from `annual_operational_cost_gbp` and defaults to 0.”
- 新文（agent-investment 3.0.0）：

$$
O_a=\begin{cases}
Q_a\left(c^{\mathrm{gen}}_a+c^{\mathrm{fuel}}_a+c^{\mathrm{carbon}}_a+c^{\mathrm{time}}_a\right), & a\ \text{thermal: gas, biomass, or any asset with a fuel or carbon cost},\\
0, & a\ \text{wind, solar or storage}.
\end{cases}
$$

  - \(Q_a\) 是年发电量（MWh）。它和各成本分项都来自 PSM 的 `value.agent-cashflow/v1` 扩展；可决策的火电分组缺这一扩展时运行报错，不按 0 处理；资产上另行写入的 `annual_operational_cost_gbp` 也被拒绝。
  - 收入 \(I_a\) 仍取 PSM 的 `market_income_gbp_by_agent`。
  - 火电分组的舍入吸收：

$$
\pi\leftarrow 0\quad\text{if}\quad |\pi|\le10^{-9}\max(|I|,O).
$$

  - 后果：电价等于边际成本时，CCGT 既不扩容也不退役。
  - 两个口径都适用。

**K-11 第 181–184/180–183 行，\(\pi=I-O\)、ROI、PB**
- 公式不变。紧接其后加 S2：金额以起始年不变币值计价；ROI 与 preferred_rate、回收期与目标年限都不折现，是模型规则，不是 NPV 检验的近似；不引入 NPV 或 IRR。p07 草稿 “Money basis” 可用。

**K-12 第 186/185 行，退役与投资分档**
- 分档不变。补储能投资审核（S6）：

$$
I^{\mathrm{sto}}=\sum_t\lambda_t\,q^{\mathrm{dis}}_t\Delta-\sum_t p^{\mathrm{ch}}_t\,q^{\mathrm{ch}}_t\Delta,\qquad
ROI^{\mathrm{sto}}=\frac{I^{\mathrm{sto}}}{C^{\mathrm{sto}}},
$$

  - \(\lambda_t\) 是出清价（修正口径下是统一边际价，C13）；默认 PSM 中储能只用盈余充电，\(p^{\mathrm{ch}}_t=0\)（S7）；\(C^{\mathrm{sto}}\) 是整体 CAPEX；
  - 不扣循环成本，不另扣 FOM，不折现；扩容上限由物理利用率决定（K-9），不启用 `tier_roi`。

**K-13 第 189–192/188–191 行**
- 补一句：CCGT、OCGT 不受余量约束；电价等于边际成本时，净收入为 0，不扩容。

**K-14 第 198–216/197–215 行，“Costs and emissions”**
- 第 200–205 行（U14、C20、U13、U16）：现文 \(C_{system}=C_{capital}+C_{fixed}+C_{operation}\)、\(LC_{served}=C_{system}/(D-U)\) 改为

$$
C^{\mathrm{head}}=C^{\mathrm{cap}}+C^{\mathrm{fix}}_{\neg\mathrm{VRE,sto}}+C^{\mathrm{op}}_{\mathrm{phys}}
\;\big[+\,C^{\mathrm{compat}}_{\mathrm{RoR}}\ \text{doctoral reproduction only}\big],\qquad
LC_{\mathrm{served}}=\frac{C^{\mathrm{head}}}{D-B-U^{\mathrm{stress}}}.
$$

  - 备忘项：\(C^{\mathrm{fix}}_{\mathrm{VRE,sto}}\)（两个口径）；\(C^{\mathrm{compat}}_{\mathrm{RoR}}\)（径流水电存量的兼容资本，UK 包约每年 109.6 亿英镑；修正口径不计入头条，论文复现口径计入头条并把备忘项标为 included）。
  - \(C^{\mathrm{op}}_{\mathrm{phys}}\) 的定义见第 5 章 N-12。账本 schema 为 `value.annual-cost-ledger/v2`，成本定义 id 为 `value.cem-system-resource-cost/v1`（`gridform_core/cost_ledger.py` 第 14–15 行）。
  - **已供电量**（U16，两个口径）：\(D-B-U^{\mathrm{stress}}\)。\(B\) 是 PSM 记录的切负荷；\(U^{\mathrm{stress}}\) 是能量平衡账在其外记入的 stress 缺口（`hidden_unserved_mwh`），只在该年有 stress 时段时计入（`cost_ledger.py` 第 74–96、130 行）。分母为 0 时强度为空。
  - 第 211–216/210–215 行的碳强度 \(CI\)（公式在第 215/214 行）用同一个分母：把 \(D-U\) 改为 \(D-B-U^{\mathrm{stress}}\)。
  - 例（可选；GBP1 public1 第一个模型年，论文复现口径）：已供电量 232,831,786.3 MWh（需求减去 78,810.2 MWh stress 缺口），每 MWh 供电成本 116.83 £/MWh。只写这一组最终数字。
  - 结果页分列年度需求、已供电量、含 stress 缺口的未供电量和其中 PSM 记录的部分。
- 第 207/206 行：
  - 现文：“Zonal constraint expenditure is attributed through the difference between zonal and copperplate operation …”
  - 新文：网络约束成本 = 分区解 − 无网络反事实；两者是同一个 LP，后者去掉网络（单节点），使用同一张逐期单价表（N4，见第 7 章 T-4）。
- 第 209/208 行，可靠性费用：补一句：默认 PSM 的物理运营成本含“记录的切负荷 × VoLL”，两个口径的 VoLL 都是 17,000 £/MWh（论文复现规则集为常数，修正口径读 `market.voll_gbp_per_mwh`，默认 17,000）；网络成本比较中两个情形都按 VoLL 计入缺电；stress 缺口单独报告，不按 VoLL 计入任何头条，但从已供电量中扣除。

**K-15 第 222–224/221–223 行，“Data and implementation”**
- 补 `agent_cashflow.py`、`investment_accounts.py`、`storage_headroom.py`、`cost_ledger.py`（v2）、`network_method_rules.py`、`model_clock.py`。

### 4.5 `national_alternatives.md`（第 5 章；第 82 行之前 en 与 zh 行号相同，之后 zh = en − 2）

**N-0 第 3 行，章首段**
- 新文：加入第 2.2 节的两句：Native 即默认 PSM，按口径运行两套规则集；Doctoral 是另一个实验模块。

**N-1 第 9–15 行，成本组成与报价式**
- 报价式不变。补三点：
  - 物理运营成本中的 \(c_i\) 不乘 \(m\)，见 N-12；
  - 年初接受集合（第 15 行之后）：修正口径中核电属于 \(\mathcal A_{-1}\)；论文复现口径每个模型年从 \(\mathcal A_{-1}=\varnothing\) 开始。中英文替换句见草稿 fx8 §3 第一、二行；
  - 生物质（S12）：在第 9 行 “Gas and biomass unit costs combine …” 之后补：
    - 随模型发布的 GB 参数中，生物质按 \(0.2+80+4.8=85\) £/MWh 报价（上一时段未被接受时再加 83 £/MWh 启动加价），高于 CCGT 55.07 和 OCGT 74.92，是火电中最贵的；
    - 模型没有 CfD/ROC 补贴收入，所以生物质几乎不被调度（GBP1 public2 与 R029 public2 修正口径 2025 年，4,762 MW 约发 0.01 TWh），两个口径相同；
    - 补贴建模是下一轮工作。草稿 r33 §1、§2、§4。

**N-2 第 24 行，“creates new agents each year … Physical inventory follows the initial state of the newly created objects.”**
- 口径：两者（DEV-BAL-03）。补一句：年末储存的电量随旧对象一起丢弃，记在 `storage_year_boundary`；是否跨年结转留到下一轮。

**N-3 第 30–32 行，Native 可用出力**
- 修正口径：内核不按自己的 `IterLimit` 时钟重读天气文件，而是接收 `site_weather.site_cf_by_source` 给出的逐期容量因子（与 canonical 适配器同一组数组，经 `kernel_injection.KernelSiteInputs` 注入）：

$$
\overline g_{j,t}=K_j\,a^{\mathrm{corr}}_{j,t}.
$$

  - 风电按 20 MW 单位乘倍率 \(K_j/20\)，光伏按 1 MW。天气 v2、损耗系数和组件平面换算都已含在 \(a^{\mathrm{corr}}\) 中。核电与径流水电的可用率经同一注入传入（N-4）。
- 第 32 行现文 “Hourly values are repeated for two half-hour periods, following the compatibility clock.” 改为论文复现口径的标注。
- 互联线序列在两个口径下都逐期取值（U1）。

**N-4 新增一段：核电与径流水电可用率**
- 位置：第 32 行之后。口径：C4、C5、C17；论文复现口径为 100% 可用。草稿：f2 §2–3、fx8 §2。

$$
a^{\mathrm{nuc}}_{n,t}=\min\!\left(1,\ \frac{\ell_n\,P^{\mathrm{PRIS}}_n}{K_n}\right)\cdot\mathbf 1\!\left[t<t^{\mathrm{end}}_n\right],\qquad
a^{\mathrm{nuc}}_{N,t}=\frac{\sum_{n\in N}K_n\,a^{\mathrm{nuc}}_{n,t}}{\sum_{n\in N}K_n},
$$

  - \(\ell_n\)：各站 PRIS 2019–2024 平均负荷率，Heysham 1 0.668、Hartlepool 0.689、Heysham 2 0.752、Torness 0.792、Sizewell B 0.801（作者已审核，A14）。
  - \(P^{\mathrm{PRIS}}_n/K_n\)：把 PRIS 参考功率折算到模型容量，以保持电量。
  - \(t^{\mathrm{end}}_n\)：在宣布停发的年份，取停发月份次月的第一期。四座 AGR 都是 2030 年第 4,320 期，即 4 月 1 日 00:00 UTC；Sizewell B 全年运行。
  - 内核只有一个 `Nuclear` 代理，得到成员资产按容量加权的可用率。
  - 回退值：在建 PWR/EPR 取 0.801；未分站的 `Nuclear` 资产取 DESNZ 全国值 0.723；AGR 缺省 0.727。
  - **数据包范围**：逐站规则只作用于有核电站点政策的包：GBP1 public1（论文复现口径不使用这些可用率）与本地 GBP1 public2（只在修正口径，`p05.nuclear-stations-public2`：五座 EDF 电站各自的负荷率与按月退役，HPC、SZC 为外生管线项目）。R029 上核电是一个合并资产，按回退值 0.723。

$$
a^{\mathrm{RoR}}_{t}=0.3487\cdot s_{m(t)},\qquad
s=\left[1.3851,1.3851,1.3851,0.6582,0.6582,0.6582,0.6776,0.6776,0.6776,1.2791,1.2791,1.2791\right].
$$

  - 0.3487 是 DUKES 6.3 标准口径 2019–2024 均值；季节形状由 Energy Trends 6.1 的季度数据推出，12 个月算术均值为 1（A14）。按 365 天加权，形状均值为 0.99883，模型年负荷率为 0.3483。GBP1 的 2,000 MW 可用电量 6.10 TWh，比 DUKES 6.2 的 2019–2024 均值 5.77 TWh 高 5.8%，在 A14 的 ±15% 以内。
  - **核电开局在运**（C17）：
    - 每个模型年开始前核电视为在运，从第 0 期起按 \(a^{\mathrm{nuc}}_{N,t}\) 作基荷；
    - 某期未被接受（可用率为 0、未出清或其他原因）之后，重新启动时收取一次启动加价；物理运营成本的启动项也只在重启那一期记一次；
    - 燃气、生物质仍从“未运行”开始；
    - 规则集字段 `nuclear_initial_state`：修正口径 `in_service_at_start`，论文复现口径 `off_until_accepted`。
  - 验收（本地运行，GBP1 public2 未发布；写成 “local check, pack not published”）：2025 年核电 38.26 TWh，17,520 期全部在运，对 Energy Trends 5.1 的 2023–2024 年 supplied 约 37.3 TWh 为 +2.5%（±10% 以内）；径流水电实发 6.01 TWh，对 DUKES 6.2 为 +4.2%。

**N-5 第 34–44 行，Native 批次与充电**
- 口径：U8（两个口径）。草稿：r41 §2。
- 现文：en 第 44 行 “Each stage constructs its power budget separately, so total output is read from the combined stage results.”；zh 第 44 行 “两个阶段分别构造功率预算……”。
- 新文：改为每个储能每期一个净头寸：

$$
0\le d_{k,t}\le P_k,\qquad 0\le c_{k,t}\le P_k,\qquad d_{k,t}\,c_{k,t}=0,\qquad 0\le \mathrm{SoC}_{k,t}\le E_k ,
$$

  - \(d\)、\(c\) 为本期放电与充电（MW），\(P\) 为额定功率，\(E\) 为能量容量。
  - 各出清阶段（日前、削减或平衡）共用额定功率：后面的阶段只报前面阶段剩下的功率 \(P_k-d_{k,t}\)；本期已充电的储能不再报放电。
  - 本期已放电的储能被要求吸收盈余时，先减少自己的放电（回购，撤回的电量回到原来的批次），没有剩余放电才充电。两个口径都先用预测差额、再用盈余回购。
  - 售电按时段收尾时的净头寸记录，收尾检查上面四个条件。
  - 回购不退还日前的储能报酬（两个口径）。
  - 论文复现口径的记账（`default_psm_surplus_node_v1` 边界）：用预测差额回购，计为 `surplus_routing.curtailed`（从 \(S\) 中拿走）；用必发或 VRE 盈余回购，计为 `to_dispatch`，VRE 盈余按比例作为 VRE 出力进入 \(S\)；充电计为 `to_storage`。
- 正文只写规则，不写“原来每个阶段重置功率上限”。

**N-6 第 46–52 行，按批次年龄的动态报价**
- 修正口径（C12）：

$$
b_{b,k,t}=m\,c^{\mathrm{cycle}}_b\ \ (\text{batteries}),\qquad b_{b,k,t}=0\ \ (\text{pumped hydro, hydrogen}),
$$

  最老的批次先卖，持有回收不进入报价。
- 论文复现口径保留原式（其参考配置用 legacy 电价）。第 52 行 “Positive holding fees make newer batches cheaper” 只适用于论文复现口径。

**N-7 第 56–62 行，Native 出清**
- **排序键**（C9）：修正口径的日前和平衡阶段都用

$$
\kappa_i=\big(\mathrm{round}(b_i,2),\ \mathbf 1[i\in\mathcal S],\ b_i,\ \text{input order}\big),
$$

  即同一 0.01 £/MWh 档内储能排在发电之后，零价储能不能挤掉报价 0.0001 的风电。论文复现口径按价格稳定排序。
- **D1-surplus**（C8）：修正口径在日前结束后按“可用 − 接受”逐来源重建盈余簿；必发盈余在调度内，先被使用；被储能、出口或柔性负荷消耗的 VRE 盈余计为 VRE 毛出力。列语义：`vre_accepted` 为 VRE 毛出力，`curtailed` = 可用 − 毛出力，`excess` 为非 VRE spill。
- **必发盈余只计一次**（U9，两个口径；草稿 r41 §3）：必发核电降不到预测时，盈余 \(s_t=g_t-F_t\) 属于接纳供给 \(S\)，在日前结算。实际需求更高（\(R_t>F_t\)）时，这部分盈余先满足平衡需求，用掉即止，不再重复发电，也不再付费；\(S\) 之外的 VRE 盈余满足平衡需求时，仍按平衡电量调度并付费。账本列 `non_vre_double_counted_mwh` 恒为 0。修正口径通过 D1-surplus 盈余簿实现同一规则。
- **未利用的 VRE**（可选一句）：结果页的 “Unused VRE (PSM boundary)” 是各时段 \(\max(\text{可用 VRE}-\text{接纳 VRE},0)\) 之和（`value.unused-vre/v1`）。论文复现口径的列语义中，平衡前在 \(S\) 外分配的盈余（储能、出口、溢出）不计入这一量，所以两个口径的这一量按各自的边界解读。
- **核电路径依赖（论文复现口径，A15 要求披露）**：第 62 行之后新增一段。草稿：fx8 §1 的机制部分。要点：
  - 报价 \(b_{i,t}=m\,c_i+s_i\,\mathbf 1[i\notin\mathcal A_{t-1}]\)，论文复现口径 \(\mathcal A_{-1}=\varnothing\)。GBP1 上未运行的核电报价 \(0+500\) £/MWh，排在所有资源之后；
  - 被接受后报价回到运行成本，每期下调不超过 `alter_limit`（GBP1 为 500 MW），接受量为 \(\max(g_{t-1}-r,L)\)，所以一直运行到年底；没有被接受的时段，记忆出力每期乘 0.99；
  - 所以核电年发电量取决于当年第一次缺电出现的时间，而不是可用率；
  - GBP1 public1 第一个模型年：论文复现口径下核电全年没有被接受（0 TWh）；它的本地修订包 GBP1 public2 在修正口径下核电开局在运，2025 年 38.26 TWh（N-4）；
  - 可选一句（A15 原要求以 GBP1 为例说明敏感性）：同一数据包在 VALUE 0.6.0-alpha.2 的输入读法下，核电从 12 月 12 日起被接受并运行到年底（约 2.7 TWh），全年的价格尖峰都在这个窗口里。只写这一句，用来说明复现结果中的核电与价格尖峰可能随输入的微小变化整段出现或消失，不写成勘误；
  - 正文不引用 advisory 的文字（第 10.2 节第 1 条）。

**N-8 第 64–80 行（zh 第 64–78 行），伪代码与新增段落**
- 按规则集标注以下改动，或给出两份伪代码：
  - **出清前 VRE 分流**：修正口径没有（C11）；论文复现口径有（第 3.2 节）。
  - **“Charge storage from forecast oversupply, then from existing surplus”**：两个口径都改为“先回购本期放电，没有剩余放电才充电”（N-5）。
  - **“then apply downward dispatch”**：按 N-9 的下调规则。
  - **进口（C16）**：en 第 68、76–77 行、zh 第 67、75 行按草稿 fx6 §3 前四行改写；伪代码之后新增 fx6 §3 第五行给出的 “Interconnector imports / 互联线进口” 段落（中英文原文都在草稿中）。语义要点：
    - 修正口径：每条正容量互联线按当期对侧价格 × 报价乘数，把可用进口容量报入日前出清，与本国机组同一排序键，同一 0.01 £/MWh 档内排在发电之后、储能之前，没有爬坡和启动加价；平衡分支只报 \(\max(\text{transfer\_constraint}-\text{day-ahead import},0)\)；出口不变；日前进口在 `orders` 中记为 `ahead_offer` 行。
    - 论文复现口径：日前出清不接收互联线；进口只在平衡分支（实际需求 ≥ 预测）出现，报价为 `external_price × 报价乘数`，只满足“实际 − 预测”的剩余上调需求；负约束在削减与平衡分支按正价出口。
    - 数字（只引用最终状态）：
      - GBP1 public1 第一个模型年，论文复现口径：进口 0.361 TWh（挪威 177.9、比利时 55.7、爱尔兰 52.0、荷兰 48.5、法国 26.5 GWh），全部来自实际需求高于预测的时段；
      - GBP1 public2 修正口径 2025 年：进口 1.376 TWh（本地、未发布、不是标定）；
      - VALUE 101：法国进口报价（12 MW、82 £/MWh）高于 CCGT，修正口径的日前报价全部被拒绝；论文复现口径的参考运行（一天、两年）进口为 0。
- **新增一段：隐藏缺电与 stress event（S4，DEV-BAL-02）**：
  - 实时阶段按 \(D_t\) 与 \(\widehat D_t\) 的比较选择分支；
  - 日前接纳供给不足以满足预测、且 \(D_t<\widehat D_t\) 时，削减分支仍按 \(\widehat D_t-D_t\) 削减，真实需求并没有被满足，PSM 不记切负荷；
  - 两个口径的调度都不变；缺口记账见 N-13。

**N-9 第 84/82 行，下调（削减分支）与预算返还**
- **两个口径共同（U7）**：储能、出口和柔性负荷先吸收（N-5），剩余的下调要求 \(n'_t\) 按各口径的次序从日前接受量中扣减。每台机组（或每段）给出 \(\delta_i=\min(\Delta_i,\,n'_{t,i})\)，其中 \(\Delta_i\) 是它的爬坡下限允许的下调量，要求随之减少，降到 0 后不再下调任何机组：

$$
n'_{t,i+1}=n'_{t,i}-\delta_i,\qquad \sum_i \delta_i=\min\!\Big(n'_t,\ \sum_i \Delta_i\Big).
$$

  - 草稿 r41 §1 的公式与例子（需削 15 MW，水电可削 20 MW 在前、风电 30 MW 在后：水电 20 → 5 MW，风电保持 30 MW）可用；删去例子中关于旧内核的括号。
- **修正口径（C15）**，写成**一套**下调次序（草稿 r12 §2、§2a、§3 可并入，按第 6 节删去非最终句子）：
  - 除燃气与生物质外，每个已接受行 \(i\) 为一段，可下调到爬坡下限 \(F_i=\max(g_{i,t-1}-r_i,0)\)（上期出力按对象身份读取），排序值

$$
v_i=\mathrm{round}\!\left(c_i-\pi_i,\,2\right),\qquad \pi_{\mathrm{nuclear}}=100,\ \pi_{\mathrm{other}}=0,
$$

    日前接受的进口取进口避免成本（对侧价格，不乘报价乘数），不付削减费。
  - 燃气（CCGT、OCGT）与生物质的一行 \(k\) 拆成两段。在线容量取当期日前接受出力 \(P_k\)（聚合机组没有开停机状态，日前排了的机组视为在线满载）：

$$
q^{\mathrm{run}}_k=\max\!\big(P_k-\max(F_k,\,m_kP_k),\,0\big),\qquad
q^{\mathrm{sd}}_k=\max\!\big(\min(P_k,\,m_kP_k)-F_k,\,0\big),
$$

$$
a_k(H)=c_k-\frac{S_k(H)}{m_k\,H},\qquad H=(1+n_t)\times0.5\ \mathrm{h}.
$$

    - \(c_k\) 是 `gen_cost`（基数 + 燃料 + 碳 + 单位时间成本）；\(n_t\) 是 \(t\) 之后连续满足“预测需求 ≤ 预测 VRE 可用量 + 核电可用量”的时段数（取自注入的逐期可用率；没有这些数组时 \(H=0.5\) h）。
    - 不停机段按 \(c_k\) 排序（\(c_k>0\)，所以总在弃风之前）。
    - 停机段：\(H\ge T_k\) 时按 \(\mathrm{round}(a_k,2)\) 与其他各行一起降序排列，\(a_k>0\) 时在弃风之前，\(a_k\le0\) 时在弃风之后，取整后与风电同值时风电在前、与核电同值时停机段在前；\(H<T_k\) 时只作最后手段，排在所有资源之后。
  - 同值时按类别次序：thermal 0、进口 0.5、水电与生物质 1、VRE 2、停机段 2.5、核电 3，再按名称与输入顺序（稳定排序；`native_corrected.py` 第 72–92、296 行）。
  - 水电与生物质的下调量返还预算；整个次序用完后仍剩的要求记为调度内 spill。
  - 推导写出来（r12 §2）：不停机段总是先降，所以进入停机段时在运机组都在 \(m_kP_k\)；再减 \(x\) MW 出力要停 \(x/m_k\) MW 装机，\(H\) 小时内省 \(c_kxH\)，重启付 \(S_kx/m_k\)。正文只写这个式子。
  - 取值表（作者在 A22 审核；按 A24-4 以模型价格基年 2025 年英镑表述）：

| 技术 | \(S\)（2025 年英镑 / MW 装机 / 次） | 启动类别 | \(m\) | \(T\) | \(H^\*=S/(m\,c)\)（GBP1 成本） |
|---|---|---|---|---|---|
| CCGT | 热 113.7 / 温 134.4 / 冷 155.0 | \(H<12\) h 热，12–48 h 温，\(>48\) h 冷 | 50% | 6 h | 4.13 h（\(c=55.07\)） |
| OCGT | 175.7 | — | 50% | 0.5 h | 4.69 h（\(c=74.92\)） |
| 生物质 | 129.2 | — | 35% | 6 h | 4.34 h（\(c=85.0\)） |

  - 取值来源：磨损取 Kumar et al. (2012, NREL/SR-5500-55433) 的中位数（下界），启动燃料与碳取 Staffell & Green (2016, IEEE Trans. Power Systems 31(1):43–53) 的 GB 口径，按英格兰银行年均汇率与英国 CPI（ONS D7BT）换到 2024 年英镑，再乘 \(138.4/133.9=1.0336\) 换到 2025 年英镑；最小稳定出力与最短停机时间参考 Elexon BMRS 申报值（SEL/MEL、MZT）、Badesa et al. (2019)、Schröder et al. (2013) 与 PyPSA-Eur。正文引用文献，不写内部文件路径。2025 年 CPI 年均值待核对一次（第 9 节第 2 条）。
  - 推论：
    - CCGT 与生物质的 \(T\ge H^\*\)，所以在 GBP1 成本下，允许停机（\(H\ge6\) h）的 CCGT 或生物质停机段总有 \(a>0\)，先于弃风；
    - 更便宜的机组在 \(H\) 刚达到最短停机时间时仍可能先弃风，例如 \(c<37.9\) £/MWh 的 CCGT 在 \(H=6\) h 时 \(a=c-113.7/3<0\)；
    - OCGT 由比较决定，按半小时时段计从 \(H=5\) h 起先停机。
  - 算例：r12 §3 的 CCGT 表与 OCGT 例子（数值已是 2025 年英镑）可直接使用，删去表后一句与非最终规则的比较。
  - **重启成本只用于排序**：物理运营成本仍按 N-12 的启动加价，不含 \(S\)，要写明。
  - 每个修正口径的市场年记录 `market.extensions.downward_restart_economics`（`value.downward-restart-economics/v1`）：规则、取值表 id、\(H\) 的口径、下调时段数及其平均 \(H\)、按段（不停机段、正节省停机段、排在弃风后的停机段、低于最短停机时间的停机段、VRE、进口、水电、核电、其他）的 MWh 与时段数。
  - 数字（GBP1 与 R029 为本地运行、数据包未发布）：
    - VALUE 101 two_year（C5）：2025 年 1 个下调时段（\(H=0.5\) h，不停机段 0.16 MWh、VRE 0.84 MWh），2026 年 2 个（VRE 8.37 MWh）；
    - GBP1 public2 2025 年：357 个下调时段，平均 \(H=3.77\) h；燃气只在不停机段内下调（2 个时段、190.7 MWh），其余为水电 91,515、VRE 21,996、进口 3,750 MWh，没有用到停机段；
    - R029 public2 2025 年：174 个下调时段，平均 \(H=4.0\) h；
    - 说明：下调多发生在日前已没有燃气的时段，燃气出现时需要的下调又在不停机段之内，所以停机段在参考运行中没有被用到（r12 §6 末段可改写使用）。
- **论文复现口径**：削减市场按 `curtail_cost` 升序下调，先削零边际成本的风电，燃气继续运行；没有重启经济学；只有水电的下调量返还预算（第 84/82 行 “Native 只处理水电的预算返还” 保留）。这是论文时期的设定，正文不写“顺序颠倒”。U7 的“只扣一次”同样适用。

**N-10 第 86/84 行，结算**
- 修正口径（C13、C10、C16）：每个阶段所有被接受的供给（含储能和进口）按同一个边际价结算，报价只决定调度顺序：

$$
\lambda^{A}_t=\max_{i\in\mathcal A^{A}_t} b_i,\qquad R^{A}_{i,t}=g^{A}_{i,t}\,\Delta\,\lambda^{A}_t\quad\forall i\in\mathcal A^{A}_t,
$$

$$
\lambda^{B}_t=\max\!\left(\lambda^{B}_{\mathrm{gen},t},\ \lambda^{B}_{\mathrm{sto},t},\ \max_{k\in\mathcal I^{B}_t}p^{\mathrm{imp}}_{k,t}\right).
$$

  - \(\mathcal A^{A}_t\) 含日前进口，进口也可以是边际报价；储能费在本期结算，不结转。
- 论文复现口径：保留原文。发电与储能分别统一定价；储能按自身最高报价 `max_bat_price` 结算；没有发电机被接受时，收入函数返回空映射；最后一个平衡时段的储能费结转到后续削减时段。

**N-11 第 88–93/86–91 行，显示价格**
- 公式不变。加标签（S8）：显示为 “Average period cost (£/MWh demand)”，它是时段总费用除以需求，不是边际出清价。修正口径下 \(F_t\) 不含跨期结转的储能费。

**N-12 第 95/93 行，年度运行费用**
- 口径：U13、U15、C14。草稿：p06 “Physical operating cost”、fx5 §1。
- 现文：“Annual operating expenditure is \(\sum_tC_t^{reported}\) plus reported current-cycle depreciation …”
- 新文：

$$
C^{\mathrm{op}}_{\mathrm{phys},y}=\sum_t\Big[\sum_i c_i\,g_{i,t}\Delta+\sum_k p^{\mathrm{imp}}_{k,t}M_{k,t}+\sum_i s_i\,g_{i,t}\Delta\,\mathbf 1[i\notin\mathcal A_{t-1}]\Big]+V\sum_t B_t+W^{\mathrm{cyc}}_y .
$$

  - \(c_i\) 不乘报价乘数；启动加价单列为 `startup_adder_resource`，它跟随同一个接受集合（修正口径的核电在年初不记启动项）。
  - \(B_t\) 是**记录的**切负荷；stress 缺口不进头条，单独报告（并从已供电量中扣除，K-14）。
  - \(V=17{,}000\) £/MWh（每 MW·半小时 8,500 £），两个口径相同：修正口径为参数 `market.voll_gbp_per_mwh`，默认 17,000，可在 0–1,000,000 £/MWh 内设置；论文复现规则集取常数 17,000，不读参数。在默认 PSM 中 VoLL 只进成本账，不改调度。
  - \(W^{\mathrm{cyc}}\) 是储能成本模块报告的当年循环折旧。储能报价支付（已含循环损耗）作为结算转移单列（`market_settlement_components_gbp`），不重复计入运营成本。

**N-13 第 97–108/95–106 行，原始残差与兼容调整**
- 口径：U10–U12。整段替换为 p04 草稿 “Declared boundary and the raw residual”、“Stress events and the energy-balance account” 与 “Validation gates”（草稿有中英全文，按第 6 节删去非最终句子）：

$$
r_t = S_t + B_t - D_t - C_t - E_t - X_t - XS_t\quad(\texttt{native\_corrected\_full\_node\_v1},\ \text{corrected}),
$$

$$
r_t = S_t + B_t + U^{out}_t - W^{in}_t - D_t - C_t - E_t - X_t\quad(\texttt{default\_psm\_surplus\_node\_v1},\ \text{doctoral reproduction}),
$$

$$
u_t=\max\!\big(0,-(r_t-B_t)\big),\qquad \mathrm{closing}_t=r_t-B_t+u_t .
$$

  - 兼容调整只吸收数值噪声：\(10^{-9}<|r_t|\le\tau_t\) 时 \(a_t=-r_t\)，否则为 0；精确算术 \(\tau_t=\max(10^{-6},10^{-9}\max(D_t,S_t))\) MWh（LP 求解器为 \(10^{-5}\) 与 \(10^{-7}\)）。物理不平衡在 \(r_t\) 中保持可见。
  - stress 时段：只有需求未满足这一种缺陷、因此闭合的时段；同一年内连续的 stress 时段构成一个 event；年度汇总给出事件数、stress 时段数和总缺口。
  - 三类 gate：run 不变量；能量平衡（上述账加账本完整性：自报一致、盈余守恒、年度调整量占比 \(\sum|a_t|/\sum D_t\le10^{-6}\)）；储能吞吐（充放电不超过额定功率乘时段长度、同一时段不对同一储能既充又放、荷电状态在 \([0,E]\) 内、逐储能审计恒等式）。
  - 发布：修正口径下任一 gate 失败，年度经济结果不发布；论文复现口径的年度结果只有原始不变量全部通过才在结果页发布。stress 时段只报告，不算 gate 失败。
  - 已声明偏差表（第 3.2 节三行）放在本节末或第 1 章 I-1，两版同一位置。三条都不改变 gate 结论。
  - 例：
    - GBP1 public1 第一个模型年，论文复现口径：74 个事件、487 个 stress 时段（最长一个事件 40 个时段）、缺口 78,810 MWh，记录的切负荷为 0；三类 gate 全部通过，原始不变量通过，年度结果在结果页发布；
    - GBP1 public2 修正口径 2025 年没有 stress 时段；
    - VALUE 101 两个口径的参考运行都没有 stress 时段。

**N-14 第 110–214/108–212 行，Doctoral 路径**
- 算法没有改动。第 110/108 行之前加一句（第 2.2 节）。补两点：
  - 这条路径的输入在任何口径下都使用冻结的 v1 天气、无损耗系数、核电与径流水电 100% 可用（第 2.2 节）；
  - 局限：这个 PSM 不发布 `value.agent-cashflow/v1`，与 agent-investment 组合且有可决策火电时，运行在投资决策处报错。
- 第 211/209 行 \(VoLL\sum_tU_t\)：该模块的 VoLL 读 `market.voll_gbp_per_mwh`，默认 17,000。

**N-15 第 216–218/214–216 行，“Data and implementation”**
- 补 `native_market_rules.py`、`native_corrected.py`、`native_realisation.py`、`native_balance_audit.py`、`energy_balance_contract.py`、`energy_balance_oracle.py`、`kernel_injection.py`、`kernel_boundary.py`、`firm_availability.py`、`storage_headroom.py`、`voll.py`（唯一的 VoLL 常数）、`native_storage_orders.py`。
- 可选一句（U17）：市场账本另有核算表 `storage_orders`，记录每条储能报价（价格 = 储能成本模块报价 × 报价乘数，可报量，接受量，状态）；`orders` 中电池行仍是价格 0.0 的净调度记录；两个口径都按净头寸记录，同期回购时报价接受量之和可以大于电池净放电。

### 4.6 `r029_cem.md`（第 6 章；第 120 行之后 zh = en − 2）

**R-1 第 3 行，R029 研究**
- 口径：待确认（第 9 节第 5 条）。写之前要知道的事实：
  - R029 数据包（`value-uk-calendar-vx-trade001`）不在论文复现口径的白名单中，所以 R029 研究只能在修正口径下运行；
  - R029 public1 的逐时光伏曲线有 8,761 个值且没有分辨率声明，修正口径的严格读取在构建时间序列时报 `GF_DATA_SHORT_SERIES`，所以 R029 public1 在 0.7.0 中两个口径都不能运行；
  - 本地修订包 R029 public2（去掉第 8,761 个值并声明逐时，A24-1）能在修正口径下用默认 PSM 跑（golden C10），尚未发布；
  - thesis96 路径（`value-doctoral-national-psm`）的输入在任何口径下都保留冻结 v1 天气、无损耗、核电与径流水电 100% 可用（第 2.2 节），口径受控的数据规则对它不起作用。
- 0.4 须写明 R029 按哪个数据包、哪条 PSM 路径运行，以及本章数值是否重算。

**R-2 第 39–68 行，年度账户与决策单位**
- 公式不变。R029 的 \(S_a\) 已扣 \(O^{var}_a\) 和 \(F_a\)，与 K-10 一致。
- 区分两条规则：R029 规则以年度资本费用 \(A_i\)（股权按 \(E/L\) 回收，债务按 5% 利率付息还本）为比较基准，这是融资成本，不是对未来收入折现；第 4 章的 agent-investment 用 \(ROI=\pi/C\)。不要把两者写成同一条规则，也不要改成 NPV。若作者希望在第 1 章统一表述 “undiscounted”，请作者确认措辞（第 9 节第 3 条）。

**R-3 第 94–104 行**
- 不改。“Charging procurement … are 0” 与 S7 一致。

**R-4 第 211/209 行，VoLL**
- 现文：“unserved energy valued at £8,000/MWh … VoLL supplied by the run configuration”。
- 新文：历史论文费用视图按 £17,000/MWh 计缺电；资源费用视图按运行的 VoLL（默认 £17,000/MWh）。fx5 §2 前两行可用，但删去其中关于论文代码原值的括号（第 6 节）。

**R-5 第 252/250 行，核电日程**
- 现文：“… Heysham 1, Hartlepool, Heysham 2 and Torness … withdraw from model year 2031 …”
- 新文：这是 R029（合并核电资产）的冻结日程，保留；补一句链接到第 5 章 N-4：默认 PSM 的修正口径在有核电站点政策的包（GBP1 public2）上，四座 AGR 在 2030 年第 4,320 期起为 0，并全年按负荷率降额。

**R-6 第 271–279/269–277 行，2025 年 CCGT 退役例子**
- 数值来自 0.6.0-alpha.2 时期的 R029 运行。0.4 中要么注明 “computed with the 0.6.0-alpha.2 implementation”，要么在确定的数据包与口径上重算（第 9 节第 5 条）。

**R-7 第 17 行，“Existing nuclear retains positive initial output from its source parameters.”**
- 不改（R029 事件核算）。补一句交叉引用第 5 章默认 PSM 的核电规则（N-4、N-7）。

### 4.7 `transmission.md`（第 7 章，en 与 zh 行号相同；只在修正口径下运行）

**T-1 第 29–35 行，目标函数**
- 口径：N2、N3。\(J_3\) 加入下调类别权重：

$$
J_3=\sum_s(c_s+d_s)+\sum_lh_l+\sum_{k\in\mathcal K^{\mathrm{down}}\setminus\mathcal S}w_{c(k)}\,x_k,
$$

$$
w_{\mathrm{fuel}}=0,\ w_{\mathrm{import}}=0.5,\ w_{\mathrm{RoR}}=2,\ w_{\mathrm{VRE}}=3,\ w_{\mathrm{fuel\_shutdown}}=3.5,\ w_{\mathrm{nuclear}}=4,\ w_{\mathrm{fuel\_shutdown\_last\_resort}}=5 .
$$

  - 储能充放电和走廊潮流的权重为 1。
  - 后果：同价时，一个区内储能充电先于径流水电、风光和核电下调；燃气、生物质停机段排在风光之后、核电之前；跨区时，类别权重与走廊潮流的 MWh 相互权衡。primary 阶段用精确价，所以下调价相差不到 0.01 £ 的两条报价，在 LP 中按价格排序，在铜板平衡中按类别排序。

**T-2 第 38 行**
- \(V=17{,}000\) 和下调项的符号约定不变。补一句：下调报价由 staged PSM 按经济价格构造，燃气与生物质分不停机段与停机段，见第 4 章 K-3。

**T-3 第 51–54 行，同价比例分配**
- 口径：N1（求解合同 v4）。
- 现文：“Ordinary non-storage bids sharing zone, direction, network effect, price and resource class are accepted in proportion …”，以及 \(\overline x_{k_0}x_k-\overline x_kx_{k_0}=0\)。
- 新文：上调报价按区、方向、网络效应和价格分组，不按资源类别分组；下调报价的分组键另带下调类别；下调报价中由最终出力上界（实际可用量，或互联线包络）决定、必须让出的部分 \(f_k\) 先划出，只有剩余的自由部分按比例分配：

$$
(x_k-f_k)\,\overline x^{\mathrm{free}}_{k_0}=(x_{k_0}-f_{k_0})\,\overline x^{\mathrm{free}}_{k},\qquad \overline x^{\mathrm{free}}_k=\overline x_k-f_k .
$$

- 事实来源：`MATHEMATICAL_REFERENCE.md` §2.4、`docs/scientific-readiness/ZONAL_SOLVER_CONTRACT_V4.md`。
- 英文原文 “forced part” 含子串 `force`：章节正文不受测试限制，但写进 `VALUE_METHODOLOGY.md` 时必须换词（例如 “mandatory part”）。

**T-4 第 82–88 行，费用核算**
- 口径：N4。草稿：p08 §2（删去括号中的旧数值比较）。

$$
C^{\mathrm{net}}_t=C_t(\text{zonal})-C_t(\text{network-free}),\qquad
J_1(\text{zonal})\ \ge\ J_1(\text{network-free})-\mathrm{tol}.
$$

  - 无网络情形是同一个 LP 去掉走廊和割集，报价、出口包络、储能物理、按 VoLL 计价的切负荷和求解器设置都相同；两个情形、资源行和代理运行成本使用同一张逐期单价表。
  - 所以全国性缺电、逐期进口价和出口套利都不计为网络成本。每期报告差值 `network_constraint_bid_objective_gbp`。
- 第 88 行现文：“The current copperplate balancing result uses the first term of this expression …”。新文：完美预测与实际预测两个参照情形都是无网络 LP，不是贪心的铜板平衡。

**T-5 第 92 行与第 94–103 行伪代码，数值求解**
- 口径：N1（Q5）。
- 现文：“The first stage permits at most 1 GBP of payment-objective degradation per complete period …”
- 新文：primary 解出后先锁总切负荷，再对报价成本项加系数感知的数值锁：

$$
u_z=0\ \ \forall z\quad\text{if}\ \textstyle\sum_z u^*_z=0,\qquad\text{otherwise}\quad \sum_z u_z\le\sum_z u^*_z ,
$$

$$
J^{\mathrm{bid}}_1(x)\le J^{\mathrm{bid}}_1(x^*)+\tau_1 .
$$

  - \(\tau_1\) 的公式见 `ZONAL_SOLVER_CONTRACT_V4.md` “Numerical lexicographic method”；£1 只作验收上限；伪代码 “solve J1 … retaining earlier objective caps” 改为“先锁切负荷，再锁报价成本”。

**T-6 新增一段：边界边际值**
- 口径：N5。草稿：p08 §3。

$$
\lambda_b=-\frac{\partial J_1}{\partial \overline F_b}=m^{\mathrm{rev}}_b-m^{\mathrm{fwd}}_b ,\qquad
\text{annual diagnostic}=\sum_t\sum_b\left|\lambda_{b,t}F_{b,t}\right| .
$$

  - 对偶值只从 primary LP 读取，在加入任何锁定行之前；状态有 `computed`、`degenerate_dual`、`shared_member`；年度量是诊断量，不是分区电价，也不是现金成本；没有计算该值的账本显示为 “Not computed”。VALUE 101 网络 Study 的 NC 边界为 66.5 £/MWh。

**T-7 第 107 行，23 区案例**
- 基础数据包的口径资格同 DS-1，须确认（第 9 节第 6 条）。

**T-8 第 140–161 行，DC 网络调度**
- 口径：N6（`value-reference-dc-network` 1.2.0）。草稿：无。
- 新增：映射到多个母线的资产，按份额 \(\sigma_{a,n}\) 展开为子资源（\(\sum_n\sigma_{a,n}=1\)，否则报错），求解后按资产汇总：

$$
K_{a,n}=\sigma_{a,n}K_a,\qquad P_{a,n}=\sigma_{a,n}P_a,\qquad E_{a,n}=\sigma_{a,n}E_a,\qquad s^{0}_{a,n}=\sigma_{a,n}s^{0}_a .
$$

  - 事实来源：VERSION_LEDGER 中该模块 1.1.0 的说明、`gridform_core/network_dc.py`、`tests/test_p08_network_shares.py`。
- 第 161 行附近补：VoLL 读 `market.voll_gbp_per_mwh`，默认 17,000。

**T-9 第 222–226 行，“Data and implementation”**
- 补：
  - `network_method_rules`（规则集 `network-economic-v2`）、`value.network-free-lp/v1`、`zonal_results`；
  - 运行期 fallback 审计（N8，只报告，不改调度）；
  - 每个 staged 市场年的 `extensions.downward_restart_economics`（`value.network-downward-restart-economics/v1`）；
  - 读取端为旧账本派生的已知缺陷 id：`p08.staged-dec-zero-pricing`、`p08.copperplate-counterfactual-mismatch`、`p08.boundary-shadow-not-computed`、`p08.zonal-v3-gbp1-lock`（只列 id，不写缺陷内容）。
- 数字（可选，VALUE 101 网络）：
  - 铜板 smoke（C7）没有平衡下调；
  - 分区一日（C8）42 个下调时段全是弃风（257.1 MWh），平均 \(H=0.93\) h；CCGT 的停机段因 \(H<6\) h 为最后手段，报价 \(66.5-113.7/0.25=-388.3\) £/MWh，全天未被接受；
  - 两个参考案例都短于一天，看不到停机段的实际作用。

### 4.8 `optional_modules.md`（第 8 章，en 与 zh 行号相同）

**O-1 第 36 行**
- 口径：U14。价格加标签 “Balance shadow price”（S8）。
- 系统成本中的固定运维：读资产的 `annual_fixed_opex_gbp`，只计非风光储资产；风光储 FOM 是备忘项（S1）。

**O-2 第 25 行**
- 现文：“Defaults are \(\Delta t=0.5\) h, \(V=10{,}000\) GBP/MWh and \(\delta_s=0\) …”
- 新文：\(V=17{,}000\) GBP/MWh（`value-perfect-foresight-lp` 1.1.0）。中英文替换句见 fx5 §2 第三、四行。补一句：完全预见 LP 中 VoLL 是目标系数，改变它可能改变调度。

**O-3 第 51–65 行，径流水电模块**
- 不改。补一句：默认 PSM 修正口径中的径流水电用统计负荷率乘季节形状（第 5 章 N-4），这是声明的统计可用率，不是本章的水文模块。

### 4.9 `appendix.md`（第 9 章）

- 不改。第 3 行提到历史 R029 用其研究配置的因子集；论文复现口径的碳因子情景 `doctoral_reproduction_2026_07_18` 不给物理 tCO2，现有措辞不矛盾。

### 4.10 `docs/methodology/VALUE_METHODOLOGY.md`（只有英文）

约束：必须保留 “bid at cost”“dynamic annual-average”“planning pipeline”“fixed zonal”“redispatch”“£17,000/MWh”“scenario_scaled_zonal_shares”“post-thesis”“not a security analysis”“state reads”“state writes”“Known limitations”；不得出现 `force`。

| # | 位置 | 改动 |
|---|---|---|
| V-1 | 第 3 行 | “edition 0.3” 改为 “edition 0.4” |
| V-2 | §1 第 7 行 | 时钟句补：periods are UTC half-hours on a fixed 365-day model year, with no daylight saving and no 29 February（S14、K-0） |
| V-3 | §2（第 24–38 行）之后 | 新增小节 “Methodology profiles”：I-1 的精简版（方法学描述修正口径；论文复现口径是兼容口径；两个口径共同的规则；Q14；方法身份；三项设计假设） |
| V-4 | §3 第 42 行；第 48–55 行合同表 | 把 “The built-in PSM is `value-staged-bid-at-cost-psm`” 改为：默认 PSM 是 `value-bid-at-cost-psm`（两套规则集）；`value-staged-bid-at-cost-psm` 是网络与分区用的分阶段变体。合同表 “Configurable parameters” 补 VoLL（`market.voll_gbp_per_mwh`）与 dec multiplier |
| V-5 | §3 第 57 行 | 现文 “The model does not include thermal start-up decisions, minimum up and down times, ramping, reserve co-optimization or integer unit-commitment variables …”。新文：没有机组组合（无整数开停机变量、无最短开停机时间约束、无备用协同优化）；默认 PSM 有启动报价加价与逐期爬坡限值；修正口径只用最小稳定出力、最短停机时间与重启成本决定下调先后（S13） |
| V-6 | §4 第 65–71 行 | 默认 PSM 的 VoLL：两个口径都是 17,000（论文复现规则集为常数，修正口径为参数）。新增 stress event 一段（N-8、N-13）。补一句经济下调顺序（N-9）：修正口径中燃气、生物质先降到最小稳定出力（在弃风之前），再往下按停机净节省与弃风比较；论文复现口径先削风电。补一句下调只扣一次（两个口径）。补一句修正口径的日前进口（C16）。保留 “£17,000/MWh” |
| V-7 | §5 第 77–97 行 | 每个储能每期一个净头寸（两个口径，N-5）；储能只用盈余充电（S7）；DEV-BAL-03 年末存量 |
| V-8 | §6 第 99–133 行 | 修正口径的默认 PSM 只报循环折旧，持有回收只用于充足性诊断；\(A[y]\) 中的 FOM 只用于报价年成本，成本账中是备忘项；staged dwell 披露。保留 “dynamic annual-average” |
| V-9 | §7 第 135–145 行 | 修正口径的储能余量（剩余盈余）与按类型的功率电池上限；论文复现口径余量为 0（K-9） |
| V-10 | §8 第 147–157 行 | 火电净收入、不折现、风光储无 OPEX、储能审核（K-10 至 K-12）；生物质没有补贴收入（S12） |
| V-11 | §11 第 183–195 行 | 头条成本按成本账 v2；备忘项；物理运营成本；已供电量（U16）；网络成本 = 分区 − 无网络反事实（第 189 行 “matched unconstrained” 改写） |
| V-12 | §12 第 197–207 行 | 第 207 行 “VALUE does not infer hydrology from installed electrical capacity …” 改写为：默认 PSM 的径流水电在修正口径下使用声明的统计负荷率与季节形状，不是水文推断；水文域仍需流量数据 |
| V-13 | §13 第 209–254 行 | 求解阶段按 v4（先锁切负荷，再锁报价成本）；下调经济价格（含燃气、生物质两段）、同价比例分配、类别次序（第 225 行 “There is no hidden physical priority list” 与类别次序协调措辞）、边界边际值；第 240 行 “matched copperplate counterfactual” 改为 “matched network-free counterfactual”。**不要写 “forced part”** |
| V-14 | §14 第 256–272 行 | 验证 gate；Q14 发布规则；价格标签（S8）；风光 CF 与 DUKES 并列披露；归档清单加方法学口径身份；结果与导出的时间按 UTC 模型时钟 |

### 4.11 `docs/methodology/README.md`

- 版次行、实现依据日期、六个下载链接（文件名中的日期取 `edition.json` 的 `date`）。
- 维护段补一句：0.4 由 `drafts/0.4` 合并而来。

## 5 三份参考文档

测试约束：
- `MATHEMATICAL_REFERENCE.md` 须含 “Version 0.7.0-alpha.1, October 2026”、v4 求解合同的六个关系式与上限句（`tests/test_documentation_consistency.py` 第 60–80 行）、“numerical tolerance does not relax physical feasibility”、“up to 10%”、“above 10% and up to 100%”、“above 100% is”；每个 manifest 模块 id 须在本文或 `docs/generated/MODULES.md` 中出现。
- `VALIDATION_AND_CLAIMS.md` 须含 “VALUE Network Extensions 0.7.0-alpha.1 source”。
- `README.md`、`MATHEMATICAL_REFERENCE.md`、`VALIDATION_AND_CLAIMS.md` 合起来不得匹配：“globally optimal cem”、“exact reproduction … passes/passed/proven”（80 字符以内）、“public release decision is go”、“smoke (test) proves/publishes annual economics”；三者合起来须含 “not_evaluated”、“single-node”、“no internal transmission”。
- 三份文档同样按 A26 定位：描述 VALUE 模型（修正口径为默认），论文复现口径写成兼容口径。

### 5.1 `docs/MATHEMATICAL_REFERENCE.md`

| # | 位置 | 现状 | 改成 |
|---|---|---|---|
| M-1 | §2.1（第 34–72 行） | 仍写 `scheme-c-psm`、“Dynamic storage orders positive holding-cost tranches newest first”（第 62 行）等 0.6.0-alpha.2 内容 | 模块 id 改为 `value-bid-at-cost-psm`；写两套规则集与 N-5、N-6、N-7、N-9、N-10、N-12 的公式（修正口径为主，论文复现口径作标注）；两个口径共同的三项内核规则（下调只扣一次、每期一个净头寸、必发盈余只计一次）；修正口径的日前进口、核电开局在运、VoLL 17,000；第 61–62 行的 dwell 排序限定为论文复现口径；加 stress event 一句 |
| M-2 | §2.2（第 74–112 行） | 模块 id `force-perfect-foresight-lp` | 改为 `value-perfect-foresight-lp`；价格标签 “Balance shadow price”；系统成本的 FOM 键（U14）；VoLL 默认 17,000 |
| M-3 | §2.3（第 114–132 行） | 模块 id `force-reference-dc-network`；LaTeX 用双反斜杠 `\\(`、`\\[` | 改为 `value-reference-dc-network`；加份额展开（T-8）；修正 LaTeX 转义 |
| M-4 | §2.4 第 189–209 行 | 小节标题带 “(P0-8b)”；第 195 行 “rule set `network-economic-v2` since R3-2, `network-economic-v1` in P0-8b”；类别次序句列六类 | 只写现行规则集 `network-economic-v2` 与八类次序（K-5），删去施工轮次与旧规则集 |
| M-5 | §2.4 第 211–223 行 | 段首 “Since R3-2 (decisions …)”；**第 220–221 行公式损坏**：`\min_{j` 与下一行 `e k}` 之间断开（`\ne` 被写成了换行） | 段首改为陈述句；公式改为 `\(\min(a_k,\ \min_{j\ne k}\mathrm{round}(p_j,2)-0.01)\)`；可补一句“重启成本按 2025 年英镑，取值见参数表” |
| M-6 | §2.4 第 247–248 行 | “Ledgers written before P0-8b stored a hard-coded 0.0; they are read as `not_computed`.” | 改为“没有计算该值的账本读作 `not_computed`”，不提施工轮次 |
| M-7 | §2.5（第 300–313 行） | `force-reference-ac-feasibility`；双反斜杠 | 改为 `value-reference-ac-feasibility`，注明是默认不注册的实验模块（审查 P1-19）；修正 LaTeX 转义 |
| M-8 | §2.6（第 315–324 行） | 第 319 行 “FORCE does not thereby become …”；第 321 行 “The current built-in market omits binary commitment, start-up/shut-down, minimum stable output, minimum up/down times, ramping …” | 与 V-5 同一口径：没有机组组合；默认 PSM 有启动报价加价与逐期爬坡限值；修正口径的最小稳定出力、最短停机时间与重启成本只用于下调排序 |
| M-9 | §3 与 §3.1（第 326–391 行） | 第 387 行 `scheme-c-legacy-storage-tariff`；第 369 行持有系数分母写 \(\max(\bar h,1)\) | 改为 `value-legacy-storage-tariff`；修正口径只报循环折旧、持有回收只用于充足性诊断；staged dwell 披露；分母中的 dwell 下限按代码为 \(\max(\bar h,2)\)（`gridform_core/builtin/scheme_c_1000twh/runtime_compat/storage_cost.py` 第 127、156 行） |
| M-10 | §4（第 393–413 行） | 第 397 行 `storage-expansion-scheme-c`、第 404 行 `scheme-c-state-transition` | 模块名改为 `value-storage-expansion-policy` 5.1.0、`value-annual-state-transition`、`agent-investment` 3.0.0；加 K-10 净收入式、S2 四档规则与不折现、S1、S6、K-9 储能余量与按类型上限 |
| M-11 | §5（第 444–472 行） | 第 462 行碳情景 id 写 `force_current_authoritative_v1` / `scheme_c_reproduction_2026_07_18` | 改为 `value_current_authoritative_v1` / `doctoral_reproduction_2026_07_18`；头条按成本账 v2，已供电量按 U16（K-14）；新增 §5.2 “Energy balance, stress events and validation gates”（取自 p04 草稿，按第 6 节删去非最终句子；含 Q14） |
| M-12 | §5.1 第 474–481 行 | “(since P0-8b both references are the network-free LP …)” | 去掉施工轮次，直接写两个参照情形都是无网络 LP |
| M-13 | §7（第 547–561 行） | 模块清单含 `scheme-c-psm`、`force-perfect-foresight-lp`、`force-reference-ac-feasibility`、`scheme-c-legacy-storage-tariff`、`storage-expansion-scheme-c`、`scheme-c-state-transition` | 按 `gridform_core/manifests/` 的 18 个 id 重写：`agent-investment`、`dynamic-annual-storage-cost`、`planning-pipeline`、`reference-transmission-expansion`、`user-formula-storage-cost`、`value-annual-state-transition`、`value-bid-at-cost-psm`、`value-copperplate-balancing`、`value-doctoral-national-psm`、`value-legacy-storage-tariff`、`value-perfect-foresight-lp`、`value-reference-dc-network`、`value-repd-era5-aggregated-weather`、`value-representative-point-weather`、`value-staged-bid-at-cost-psm`、`value-storage-expansion-policy`、`value-zonal-redispatch-balancing`、`vre-expansion-cap` |
| M-14 | §8（第 563–579 行） | 推迟项清单 | 补：抽蓄和氢储没有水价；储能不能从市场购电；年末储能存量是否跨年结转；生物质补贴收入（P4-07）；投资侧与调度侧天气的统一（Q15）；CSV 技术曲线的时间标注（第 9 节第 1 条） |

### 5.2 `docs/SCHEME_C_MODEL_CARD.md`

| # | 位置 | 现文 | 新文 |
|---|---|---|---|
| MC-1 | 第 15–25 行（口径段） | 列出的通用修正只有 P6-24、P6-02/03/04、A4、A2 与核算修正；把论文复现口径写成 “frozen doctoral reproduction” | 按 A26 改写：模型卡描述的模型是修正口径（默认）；论文复现口径是保留论文时期设定的兼容口径。两个口径共同的规则写全：互联线时钟、GBP1 三处读取、按声明的列读取、火电净收入、下调只扣一次、每期一个储能净头寸、必发盈余只计一次、stress event、VoLL 17,000、核算规则（含已供电量） |
| MC-2 | 第 27–31 行 | “… Its GBP1 run fails the surplus-conservation invariant in 471 periods (up to 991 MWh), as the 35aadb3 code did. This is a known issue under investigation (A15), and the run's annual results stay withheld.” | 只保留核电路径依赖一句：论文复现口径的核电年初未运行，首次被接受前一直带启动加价，被接受后每期下调不超过爬坡量，所以一直运行到年底；GBP1 public1 第一个模型年核电全年未被接受（N-7）。可补一句：该运行的原始不变量全部通过，年度结果发布，stress 74 个事件、487 个时段、78.8 GWh |
| MC-3 | 第 39 行 | “the market is energy only, without reserves, unit commitment or ramping;” | “the market is energy only, without reserves or unit commitment; the retained kernel applies a start-up bid adder and a per-period ramp allowance;” |
| MC-4 | 第 37–50 行（两个口径的已知简化） | — | 补：储能只用盈余充电（S7）；年末储能存量丢弃（DEV-BAL-03）；投资侧 CSV 曲线与调度天气不一致（S9）；回购不退还日前储能报酬（两个口径；目前写在第 56 行的修正口径清单中，移过来）。生物质一条保留 |
| MC-5 | 第 52–56 行（修正口径的已知简化） | 两条（抽蓄、氢储无水价；回购不退日前储能费） | 删去回购一条（已移到 MC-4）；补：聚合火电没有开停机状态，在线容量取日前接受出力；重启成本只用于下调排序，不进成本账；核电与径流水电可用率为固定值，没有换料或停运日历 |
| MC-6 | 第 71–75 行 | “… it has no unit start/stop, ramping, minimum-output or minimum up/down constraints.” | 与 V-5 同一口径 |
| MC-7 | 第 81–87 行 | “FORCE-CEM system cost definition `force.cem-system-resource-cost/v1` uses … explicit fixed O&M …” | 定义 id 改为 `value.cem-system-resource-cost/v1`（`cost_ledger.py` 第 15 行）；成本按成本账 v2（K-14）：风光储 FOM 为备忘项；径流水电兼容资本在修正口径不计入头条、在论文复现口径计入；物理运营成本含“记录的切负荷 × VoLL（17,000 £/MWh，两个口径）”；每 MWh 成本的分母是已供电量（U16）；“explicit fixed O&M” 只指火电 FOM |
| MC-8 | 第 94–100 行（投资规则） | — | 补储能投资审核一句（S6） |
| MC-9 | 第 102–116 行（默认 PSM 规则集） | 论文复现口径一句写 “declares their known deviations”；三项内核规则一句带 “(formerly DEV-BAL-04)”“(formerly DEV-STO-01)” 与 “(R4-1, decision A26)”；第 113–116 行把 “a buy-back does not refund …” 写成修正口径独有 | 改为：两个口径共同的三项内核规则（只写规则，删去 “formerly …” 与施工代号）；论文复现口径保留的论文时期设定（第 3.2 节：先削风电、进口只在平衡分支、核电年初未运行、出清前分流 VRE 去电解、储能按自身最高报价结算、储能费结转、dwell 线性报价），不写“偏差”；修正口径的规则（燃气与生物质先降到最小稳定出力，再按停机净节省 \(c-S/(m\,H)\) 与弃风比较；进口进入日前出清；核电开局在运；VoLL 读参数） |
| MC-10 | 第 118–135 行（修正口径输入两段） | 第 122–124 行 “the reference values were PENDING AUTHOR REVIEW at this step (reviewed by the author in A14, see below)” | 两段合为一段，只写最终状态：天气 v2、文献损耗系数、光伏组件平面换算、核电逐站负荷率与按月停发、径流水电 0.3487 × 季节形状，参考值作者已审核；风电 CF 与 DUKES 并列披露（陆上约 1.56 倍、海上约 1.23 倍、光伏 1.04 倍），不标定；GBP1 public2 本地验收：核电 38.26 TWh（对 Energy Trends 5.1 +2.5%），径流水电 6.01 TWh（对 DUKES 6.2 +4.2%） |
| MC-11 | 新增一段 | — | 数据资格：GBP1 public1 只用于论文复现口径；修正口径可用本地修订包 GBP1 public2、R029 public2（都未发布）；R029 public1 在 0.7.0 中不能运行；逐站核电只作用于有站点政策的包（GBP1 public1、public2；public2 只在修正口径）；R029 核电按合并资产 0.723；用户工作区数据包只能用修正口径 |
| MC-12 | 第 27–31 行附近 | — | Q14 写成一般规则：论文复现口径的年度结果只有原始不变量全部通过才在结果页发布；修正口径任一 gate 失败即不发布年度经济结果。随模型发布的论文复现参考运行（VALUE 101 一天、两年，GBP1 public1 第一年）都通过 |
| MC-13 | 第 1–13 行 | “FORCE model card”“FORCE-CEM v1” 等产品名 | 是否改为 VALUE 由作者决定（第 10.1 节表第一行）；第 8–9 行 “It is derived from the Scheme C research structure but is not an exact numerical reproduction” 可保留，但不要扩写成“对标论文” |

### 5.3 `docs/VALIDATION_AND_CLAIMS.md`

| # | 位置 | 改动 |
|---|---|---|
| VC-1 | 第 24–28 行（prompt52 系列 “passed”） | 这些证据由 0.6.0-alpha.2 时期的代码产生，证据文件不在本源码树中（`publication/` 下没有这些 JSON，审查 R2-07）。Status 改为带限定的写法（例如 “passed (0.6.0-alpha.2 code, evidence not in this source tree)”），或移到“历史证据”小节。避开禁止正则 |
| VC-2 | 第 17–18 行 | Boundary 列补：修正口径的默认 PSM 只报循环折旧，首年满利用基准只影响持有回收诊断 |
| VC-3 | 第 41 行（论文复现口径一行） | Claim 改为 “Doctoral reproduction profile changes its trajectory only under the rules shared with the corrected methodology”，不写 “keeps the 0.6.0-alpha.2 trajectory bit for bit”。Boundary 改为：D1、D2（VALUE 101 smoke、two_year_smoke）的轨迹列与 35aadb3 逐位相同；D3、D4、D5 按两个口径共同的规则各重基线，附数值报告（`tests/golden/reports/`）；平台限定与 “not the 2026-07-18 retained trajectory” 保留 |
| VC-4 | 第 42 行 | “13 golden cases and 4 doctoral/corrected pairs” 改为 “15 golden cases (D1–D5, C1–C10) and 4 doctoral/corrected pairs” |
| VC-5 | 第 57–64 行 | “NO-GO for a fresh GitHub checkout because 460 intended source members are not tracked” 已过时。是否删改由作者决定（与源码公开的决定相关） |
| VC-6 | 第 66–73 行（Default PSM 段） | 末句 “Doctoral runs reproduce 0.6.0-alpha.2 dispatch and carry declared deviations; they do not establish closure of the energy identity.” 改为：论文复现口径按自己的边界 `default_psm_surplus_node_v1` 记账；随模型发布的论文复现参考运行（D3、D4、D5）能量平衡账闭合，储能 gate 通过，原始不变量全部通过；剩余的已声明偏差只是定义和证据 |
| VC-7 | 第 75–93 行（P0-5b 段与 F2 段） | 两段合为一段，只写最终状态：光伏时间约定（伦敦质心 11.97 UTC）；损耗系数是文献值，不是拟合；CF 为陆上 0.4026、海上 0.4913、光伏 0.1065（对 DUKES 2020–2024 为 1.56、1.23、1.04 倍），不声称与 DUKES 一致；核电与径流水电参考值作者已审核（A14、A21）；GBP1 public2 修正口径 2025 年本地运行，核电 38.26 TWh（对 Energy Trends 5.1 +2.5%），径流水电 6.01 TWh（对 DUKES 6.2 +4.2%），写成 “local check, pack not published”。删去 “PENDING AUTHOR REVIEW at this step”“deferred to the author”“has not been made” |
| VC-8 | 第 106–110 行 | “reproduces VALUE 0.6.0-alpha.2 as implemented, with the universal corrections P6-24, P6-02, P6-03, P6-04 and the thermal net revenue (A4)” 改为：论文复现口径是兼容口径，按 0.6.0-alpha.2 的实现保留论文时期的设定，并适用两个口径共同的规则（列全，见 MC-1）；与 2026-07-18 保留轨迹的比较仍为 failed；Q14 一句保留 |
| VC-9 | 第 111–113 行 | “The GBP1 before/after comparison of the doctoral profile covers one model year (golden D5)” 改为：GBP1 public1 的论文复现证据只覆盖第一个模型年（golden D5）；多年运行没有做 |
| VC-10 | 第 114–119 行（Known issue A15） | 整段删去。改为一句：GBP1 public1 第一个模型年的论文复现运行原始不变量全部通过，stress 74 个事件、487 个时段、78.8 GWh，记录的切负荷为 0。核电路径依赖一句保留 |
| VC-11 | 新增行 | 两个口径共同的三项内核规则：`tests/test_r41_doctoral_kernel_errors.py`，passed；边界：手算玩具算例与 golden D3–D5 |
| VC-12 | 新增行 | 火电净收入（A4）：`tests/test_p07_investment_corrections.py`，passed；边界：玩具算例与 golden D4；电价等于边际成本时既不扩容也不退役 |
| VC-13 | 新增行 | stress event 记账（A2）与已供电量：`tests/test_p04_balance_boundary.py`、`tests/test_stress_events_query.py`、`tests/test_r5_swap_data_defects.py`，passed；边界：调度不变，只记账 |
| VC-14 | 新增行 | Q14 发布规则：`tests/test_result_advisories.py`、`tests/test_methodology_profiles.py`、`tests/test_p04_validation_gate.py`，passed |
| VC-15 | 新增行 | VoLL 17,000 两个口径（`tests/test_fx5_voll.py`）；修正口径日前进口（`tests/test_fx6_ahead_imports.py`）；核电开局在运（`tests/test_fx8_nuclear_in_service.py`）；储能报价账本（`tests/test_fx4_storage_orders.py`）。passed；边界：合成或 VALUE 101 算例，核电规则另有 GBP1 public2 本地验收 |
| VC-16 | 新增行 | 修正口径的经济下调顺序：默认 PSM（`tests/test_r12_economic_downward_order.py`）与网络模型（`tests/test_r32_network_economic_dec.py`，含两区 LP 与独立 PuLP/CBC oracle），重启成本的价格基年（`tests/test_r33_restart_price_base.py`）。passed；边界：玩具算例、VALUE 101；GBP1 public2 与 R029 public2 的一年运行中没有用到停机段，所以停机段在真实数据包上没有被行使过 |
| VC-17 | 新增行 | 按类型电池上限（`tests/test_r13_per_type_battery_caps.py`），passed；边界：玩具算例与 VALUE 101 |
| VC-18 | 新增行 | 生物质披露（`tests/test_r33_biomass_disclosure.py`）：只是 advisory，不改结果；status 可写 “disclosed (not modelled)” |
| VC-19 | 新增行 | 修正口径可运行 R029（本地修订包 R029 public2，golden C10；`tests/test_r31_solar_8761.py`），passed；边界：数据包未发布，R029 public1 本身在修正口径下不能运行 |
| VC-20 | 第 38–40 行附近（网络行的 Boundary 列） | 补已知问题：分区 LP 对个别参数组合数值脆弱（HiGHS 报 scaled optimal / unscaled not set，运行以 `GF_ZONAL_SOLVER_FAILURE` 失败，不会给出错误结果） |

第 5.3 节引用的测试模块已在本分支 HEAD 上运行（unittest，施工 wrapper）：24 个模块共 309 个测试，全部通过（1 个跳过）。

## 6 草稿使用说明

| 草稿 | 并入位置 | 可直接使用 | 不要照抄的内容 |
|---|---|---|---|
| `p04_energy_balance_validation.md` | ch5 N-13；ch1 I-1 | 英文与中文的 “Declared boundary …”“Stress events …”“Validation gates” 三节（删去右栏所列句子） | “What the 0.3 text got wrong / 0.3 版本的表述错在哪里”整节（第 14–27、116–118 行）；第 31、68、78 行与第 122、140、146 行的施工标签（“From P0-4 S6”“(P0-4 S7)”“(after P0-6 S8)” 等）；第 98–106 行与第 158 行（内核规则的历史说法，规则本身写在 N-5、N-7、N-9）；第 109–110 行与第 160 行括号中的 “reports written before R4-1” |
| `p05a_data_reading.md` | ch2 | 全文 | 无（finding 编号可按需删去） |
| `p05b_corrected_data.md` | ch3、ch2、ch5 | §1（一次换算）、§2（天气 v2）、§3 的损耗系数表与“不标定”一段、§5、§6 | 第 6 行与第 152 行的状态 “PENDING AUTHOR REVIEW”（参考值已全部审核）；§3 的两条 “disclosures” 与 CF 表（以 f2 为准）；§3 末 “the author reads the values from the DUKES 6.3 workbook”（以 f2 §4 为准）；§4 的核电与水电数值和 “Heysham 1” 一处（以 f2 §2–3 为准）；§3、§4 开头的 “Updated by F2” 引文框；§7 “Historical runs”（讲旧 Run 的 advisory，不属于方法学） |
| `p06_default_psm_clearing.md` | ch5、ch4 | “What does not change”、“Kernel corrections in both rule sets” 三条规则（只取规则）、“Physical operating cost”、修正规则集表（除下调一行）、“Ledger column semantics”、“Energy balance” | 第 7 行模块版本 6.0.0（正文不写版本号）；第 49 行 “no longer a switch”；第 68 行括号 “10000 before A16-5”；第 71–72 行 “before P0-6 the wear was counted twice”；表中 “down regulation” 一行按 N-9 重写为一套规则，“storage position” 一行的 “Universal since R4-1” 改为“两个规则集”；第 124–134 行 “Doctoral rule set: declared deviations” 一节的施工说明（96 期合成 golden 的修订、`non_vre_double_counted_mwh` 的历史）；第 146–147 行 “since R4-1”；第 148–149 行（改为 K-12 的储能投资审核） |
| `p07_investment.md` | ch4 | “Money basis”、“Net revenue”、“Cost ledger v2” 与储能余量一节前半 | 储能余量一节最后一段（“Between P0-7 and R1-3 …”）不是现行规则；“its golden was re-baselined once (D4 …)” 是施工记录；公式按 K-9 补写 |
| `p08_network_economics.md` | ch7、ch4 | §1 表与报价规则、§2 网络成本、§3 边界边际值、§4 旧账本 | §1 “Before P0-8b every dec was priced at GBP 0 …” 与六类次序句（以八类次序为准，K-5）；“R3-2 amendment” 应并入表与次序句，不作为修订段；“(Edit for `transmission.md` 0.3 …)” 是编辑说明；§2 各括号中的 “(before: …)”；中文只有摘要，须按英文全文译写 |
| `f2_solar_poa_firm_cf_disclosure.md` | ch3、ch5、ch2 | §1 换算表与披露、§2、§3、§4 原因六条、§5 参考文献 | §1 “Before A13 the corrected profile multiplied …” 一句；§3 末 “Runs recorded without this correction used the provisional P0-5b values …”；§4 表中 “GBP1 P0-5b (v2 + losses)” 一列；R029 写 “R029 public1” 处改为 R029（public1 与 public2 共用天气文件） |
| `fx5_voll_17000.md` | ch5、ch6、ch8、ch4 | §1 表（第 15–21 行）、第 33–35 行、§2 替换句（en/zh optional_modules 两行与 core 一行原样可用） | 第 23–28 行（参数旧默认值与论文代码原值的历史）；§2 r029 两行中的括号 “(the thesis code used £8,000/MWh; decision A16-5)” / “（论文代码原为 £8,000/MWh，决策 A16-5）”；§3 第 59 行 “(8000 or 10000 -> 17000)” |
| `fx6_day_ahead_imports.md` | ch5、ch2 | §1 的规则表与其后一段（第 10–36 行）、§2（修正规则）、§3 替换句 | 第 38–48 行 “GBP1 doctoral numbers” 一段（数字不是当前结果；当前值见 N-8）；第 87–89 行（“unchanged (trajectory bit-identical, golden D1-D5)” 与模块版本号）；§4 GBP1 前后对比表（测量时核电规则尚未生效，只引用最终年度量 1.376 TWh） |
| `fx8_nuclear_in_service.md` | ch5 | §1 第 10–39 行到 “not on nuclear availability.” 为止（机制）、§2 第 1–4 条、§3 前两行替换句 | §1 第 39 行 “GBP1 first model year” 起到第 51 行的 35aadb3 数字叙述（按 N-7 只写当前结果和一句可选的敏感性说明）；§2 末第 79–82 行（模块版本号与 “trajectory bit-identical, golden D1-D5”）；§3 第三行替换句中的 “2.7 TWh at 35aadb3 … after the input reading corrections”（按 N-7 改写）；§4 的 “before A18” 一列与 before/after 说法，最终数字只用 after 一列 |
| `r12_economic_downward_order.md` | ch5 N-9 | §2（规则与取值表）、§2a（价格基年）、§3 算例、§4 输出、§5 | 文件头的内部路径；§1 第二点（不是现行规则）；§2 开头的模块版本号；§2 公式后第 84 行附近 “corrected after the R1-2 review, author confirmation pending …”（A22a 已确认，只保留单位核对一句）；§3 末句；§6 的 “Before” 与 “Change” 两列和 “R3-3 … do not change” 一段（只用 N-9 中的最终统计） |
| `r32_network_economic_downward_order.md` | ch4 K-3、ch7 | §2 规则表与说明、§3 前两行算例、§4 输出、§6 | §1 第一点（不是现行规则）；“1.4.0 -> 1.5.0”；§3 表 “P0-8b” 一行；§5 中的 “(as before)”“now two bids”“-373.5”（最终为 −388.3）；中文摘要第一点的“原来……”句 |
| `r33_biomass_support_disclosure.md` | ch5 N-1；ch1 局限 | 全文 | §2 表中 “(0.05 TWh before FX8)” |
| `r41_kernel_corrections.md` | ch5 N-5、N-7、N-9 | §1 第 14–29 行的规则与公式、§2 第 39–66 行的规则与记账、§3 第 76–83 行的规则与第 85–88 行的例子（删去 “not 17.5 MWh”；只有英文，中文按英文译写） | 第 3–6 行状态与模块版本；第 31–37 行与第 68–74 行（旧内核的行为和 GBP1 旧数字；例子可保留，删去 “the retained kernel also cut wind to 15 MW” 一类括号）；§4 第 90–101 行的修复前后对比（当前结果见 N-13 与第 8 节）；§5 第 103–112 行（“no longer bit for bit”“no longer exist” 是历史说法） |
| `r5_served_energy_demand_units.md` | ch4 K-14；ch2 DS-0、DS-10 | §1 的定义（第 9–13、17–21 行）与第 25–26 行；§2；§3（只有英文） | 第 3–5 行状态；第 15–16 行 “Before R5-1 …”；第 22–23 行例子的修复前数字（只用 232,831,786.3 MWh 与 116.829 £/MWh） |

## 7 版次升级（0.3 → 0.4）

### 7.1 何时升

- 只升一次：所有章节合并、中英配对检查通过、作者审阅通过之后。不要分章节逐步发布。
- 发布 0.4 须经作者同意。网站导入 0.4 是上传员的工作，前提是源码已经公开（见网站交接文档）。
- 0.4 发布之前，0.3 的六个文件和网站章节保持不变。网站上由上传员加临时说明（网站交接文档 M-2、C-16）。

### 7.2 要改的元数据

| 文件 | 字段 | 0.4 的值 |
|---|---|---|
| `docs/methodology/edition.json` | `edition` | `"0.4"` |
| | `date` | 生成日期（`YYYY-MM-DD`）。六个文件名也用这个日期（`build_document.py` 第 14–15 行） |
| | `basis` | 正文描述的实现与数据依据日期，建议取作者确认发布的 0.7.0-alpha.1 源码提交的日期 |
| | `revision.zh` / `revision.en` | 保持现有格式，含三个空格：`"修订版 0.4   YYYY年M月D日"` / `"Edition 0.4   D Month YYYY"` |
| | `basisLabel.zh` / `basisLabel.en` | `"模型实现与数据依据 YYYY年M月D日"` / `"Implementation and data basis D Month YYYY"`；是否加 “VALUE 0.7.0-alpha.1” 由作者决定 |
| | `chapterIDs` | 不变（九个） |
| `docs/methodology/generation.json` | `edition`、`date`、`basis` | 同上 |
| | `scope_changes` | 改写为 0.4 的范围：方法学描述修正口径（默认），论文复现口径作为兼容口径；两个口径共同的规则与只在修正口径生效的规则（第 3.3 节）；设计假设；模型时钟；论文复现口径的论文时期设定与核电路径依赖；修正口径的数据与天气（v2、损耗系数、组件平面、核电与径流水电可用率）；默认 PSM 的规则（每期一个储能净头寸、下调只扣一次、必发盈余只计一次、经济下调顺序、日前进口、核电开局在运）；投资与成本账（含已供电量）；网络经济学（含两段式下调报价）；VoLL 17,000 |
| | `checks` | 重新执行后填写。原有的 `numeric_tokens_preserved_after_chapter_reference_updates` 是 0.3 只改章节号时的检查；0.4 是内容修订，建议改为第 8 节的双语数值一致检查 |
| | `dependencies` | 不变，除非构建工具升级 |
| `docs/methodology/artifacts.json` | `edition`、`date`、`basis`、`files[6]`（path、sha256、bytes、render_review）、`review` | 六个文件审阅通过后填写，`review.status = "passed"` |
| `docs/methodology/README.md` | 版次行、下载链接 | 同上 |
| `docs/methodology/VALUE_METHODOLOGY.md` | 第 3 行 | “edition 0.4” |
| `publication-scope.json` | `edition`、`revision_date`、`scientific_basis_date`、`expected_artifacts` | 须与 `edition.json` 和新文件名一致（`check_publication_scope.py` 逐项比较）。与上传员协调，由上传员在导入时同步 |

### 7.3 构建

1. 按 `scripts/methodology/README.md` 准备文档构建环境，它与模型运行时分开：python-docx 1.2.0、lxml 6.1.1、MathJax 3.2.2、marked 17.0.5、sharp 0.35.4，再加 LibreOffice 和中文、数学字体。先设置 `VALUE_METHODOLOGY_SOURCE`、`VALUE_METHODOLOGY_WORK`、`VALUE_DOCUMENT_DIR`。
2. 依次运行 `assemble.py` → `render_math.cjs zh|en` → `build_document.py zh|en`，把 DOCX 转为 PDF，逐页检查公式、表格和中文排版。0.3 的审阅范围是中文 50 页、英文 46 页，0.4 会增加。
3. `scripts/build_value_methodology_pdf.py` 把 `VALUE_METHODOLOGY.md` 单独构建为开发者概览 PDF（`output/pdf/VALUE_Methodology.pdf`）。要改三处：
   - 第 35 行页脚写死 “VALUE methodology | 25 August 2026”，改为新日期或从 `edition.json` 读取；
   - 第 71 行封面表 “Model clock” 一行补 “UTC, fixed 365-day year”；
   - 第 70–76 行封面表可补一行 “Methodology profiles: corrected (default) and doctoral reproduction (compatibility)”。
   - `tests/test_value_methodology.py` 在 PDF 存在时对 PDF 文本做同样的短语与 `force` 检查。这个测试需要 pypdf，施工 wrapper 的运行时没有 pypdf，请在 gate venv（`requirements/value-test-py310.lock`）或文档构建环境中运行。
4. 把六个文件的哈希和大小写入 `artifacts.json`，交给上传员运行 `website/sync_methodology.py --source docs/methodology --build <渲染目录> --documents <六个文件目录>`。不要手改 `website/methodology/` 或 `website/static/assets/methodology/`。

### 7.4 合并 0.4 的提交

- 中英两版同一提交修改，每章一个提交，便于审阅。最后一个提交更新 `edition.json`、`generation.json`、`artifacts.json`、`README.md`、`VALUE_METHODOLOGY.md` 第 3 行。
- 每个提交前运行 `tests.test_value_methodology` 与 `tests.test_documentation_consistency`（unittest），并刷新发布清单（`scripts/refresh_source_release_manifest.py --index`）。`test_documentation_consistency` 中有 6 个既有失败登记在 `tests/baselines/known-failures-linux-py310.txt`，与方法学无关。

### 7.5 合并后

- `docs/methodology/drafts/` 已在发布排除清单中（`tests/baselines/release-exclusions.txt` 第 11 行）。0.4 获批后，建议在同一提交中删除已并入的草稿，避免出现两个事实来源；或在每份草稿首行注明“已并入 0.4（日期）”。删除时不需要改排除清单。
- 修正目录的描述若需要改，`docs/generated/METHODOLOGY_PROFILES.md` 须重新生成（`scripts/generate_reference_tables.py`，有测试拦截），由代码负责人处理。

## 8 双语一致性检查清单

### 8.1 机器检查

1. **结构配对**：`assemble.py` 输出 `assembly-check.json`，九个 `pairs[*].matching_structure` 必须全为 `true`，即每章中英的标题数、表格分隔行数、代码块栏数和行间公式数相等。新增小节、表格、伪代码和公式时，两版同时加。
2. **行间公式逐字相同**：同一章两版的 `$$…$$` 块应逐字相同，LaTeX 不翻译。可用以下片段比较（文档构建环境的 Python，或施工 wrapper）：

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

   数值不一致不一定是错误（例如中文写“第四章”、英文写 “Chapter 4”），逐条人工核对，最后在 `generation.json` 的 `checks` 中如实记录。
3. **代码标识一致**：口径 id、模块 id、修正 id（如引用）、文件名、参数名（反引号内的内容）两版集合相同。
4. **禁用内容**：章节正文没有 32–64 位十六进制串、`/home/`、`/mnt/` 路径和私有产品名；`VALUE_METHODOLOGY.md` 中没有 `force`。可用：`grep -n -i -E 'force|/home/|/mnt/|\b[0-9a-fA-F]{32,64}\b' docs/methodology/{en,zh}/*.md docs/methodology/VALUE_METHODOLOGY.md`。
5. **定位与历史用语**：正文中没有 “aligned with the thesis”“reproduces the thesis”“对标论文”“与论文一致”，也没有施工代号与修复前后叙述。可用：`grep -n -i -E 'aligned with the thesis|reproduces? the thesis|对标论文|与论文一致|R[0-9]-[0-9]|P0-[0-9]|FX[0-9]|before the fix|formerly|已修复' docs/methodology/{en,zh}/*.md docs/methodology/VALUE_METHODOLOGY.md`，命中项逐条判断（例如 “P0” 也可能出现在合法的参数名中）。
6. **测试**：`tests.test_value_methodology`、`tests.test_documentation_consistency`；网站构建后由上传员运行 `scripts/check_publication_scope.py`。

### 8.2 人工检查

1. 第 2.4 节术语表中的每个术语，全文只用一种译法；第一次出现时中英对照。
2. 口径标签与固定附注保留英文原文（界面字符串），中文版在引号中照写英文，再加中文说明。
3. 只适用于一个口径的表述，两版标注相同。统一用 “(corrected methodology)” / “（修正口径）”、“(doctoral reproduction)” / “（论文复现口径）”。修正口径是正文主体，论文复现口径的段落放在后面。
4. 数值逐个核对：
   - 损耗系数 0.90307、0.814968，性能比 0.83，反照率 0.2，天顶角截止 87°，倾角拟合四个系数；
   - 核电五站负荷率 0.668 / 0.689 / 0.752 / 0.792 / 0.801，回退值 0.801 / 0.723 / 0.727，2030 年第 4,320 期；
   - 水电 0.3487、12 个形状值、0.99883、0.3483、6.10 TWh、5.77 TWh；
   - VoLL 17,000（每 MW·半小时 8,500）；核电下调溢价 100；
   - 重启成本 113.7 / 134.4 / 155.0、175.7、129.2 £/MW（2025 年英镑；A22 原值 110 / 130 / 150、170、125 为 2024 年英镑，系数 1.0336 = 138.4 / 133.9），最小稳定出力 50% / 50% / 35%，最短停机时间 6 / 0.5 / 6 h，热/温/冷边界 12 h、48 h，\(H^\*\) 4.13 / 4.69 / 4.34 h；
   - 默认 PSM 下调类别值 0 / 0.5 / 1 / 2 / 2.5 / 3；网络下调类别权重 0 / 0.5 / 2 / 3 / 3.5 / 4 / 5，储能与走廊 1；
   - 舍入吸收 \(10^{-9}\)，\(\tau_t\) 的三个数；汇率 1.1；
   - 生物质 85、83、CCGT 55.07、OCGT 74.92、4,762 MW、约 0.01 TWh；
   - CF 表各值；
   - 论文复现口径 GBP1 public1 第一个模型年：进口 0.361 TWh（177.9 / 55.7 / 52.0 / 48.5 / 26.5 GWh）；核电 0 TWh；stress 74 个事件 / 487 个时段 / 78,810 MWh / 最长 40 个时段；已供电量 232,831,786.3 MWh；每 MWh 供电成本 116.83 £/MWh；
   - 修正口径 GBP1 public2 2025（本地、未发布）：核电 38.26 TWh（+2.5%）、水电 6.01 TWh（+4.2%）、进口 1.376 TWh、357 个下调时段、平均 \(H\) 3.77 h；R029 public2：174 个下调时段、平均 \(H\) 4.0 h；
   - VALUE 101：C5 的 0.16 / 0.84 / 8.37 MWh；C8 的 42 个时段、257.1 MWh、0.93 h、−388.3 £/MWh；NC 边界 66.5 £/MWh。
5. 正文不带任何待审核标记：参考统计表第 1–4 节都已由作者审核（A14、A21、A22），A13 模型选择已认可（A16-6），A22a 公式已确认。只有 2025 年 CPI 年均值（第 9 节第 2 条）与第 9 节所列事项需要在写之前确认。
6. 交叉引用（章号、节名）两版一致；新增小节后，引用它们的地方都要更新。
7. 中文用全角标点，数字用半角，千分位与英文版一致（例如 17,520）。

## 9 写 0.4 之前须确认的事项

| # | 事项 | 为什么重要 | 找谁 |
|---|---|---|---|
| 1 | 投资侧 CSV 技术曲线的时间标注：现在按 ERA5 时间戳（每行是截至该时次的一小时累积）；是否改为按区间起点（整体提前 1 小时，与 NetCDF 天气的 v2 处理一致）。改动属于方法改动（Q13） | 第 3 章 W-5、W-6 的措辞 | 作者 |
| 2 | 2025 年 CPI 年均值 138.4（ONS D7BT）没有在 ONS 页面上复核（参数表 `price_base.verification` 标为 NV）。若不同，参数表两字段与五个取值按规则重算，修正族 golden 修订一次。正文引用换算系数 1.0336 之前请核对 | 第 5 章 N-9 取值表 | 代码负责人 |
| 3 | 起始年不变币值的表述：基年 2025（随模型发布的研究都从 2025 年开始），但有来源年份不同、未做通胀调整的输入（第 3.1 节 S3）；另有 R029 年度资本费用中的 5% 利率与“不折现”如何并列表述 | 第 1 章 I-1 设计假设句、第 2 章成本段、第 6 章 R-2 | 作者 |
| 4 | 本地修订包 GBP1 public2、R029 public2 是否发布；修正口径的默认国家级数据包是否改指 R029 public2。发布前正文只写 “local revision, not published” | 第 2 章 DS-1、第 6 章 R-1、模型卡数据资格 | 作者 |
| 5 | R029 研究（第 6 章）在 0.7.0 中按哪个数据包、哪条 PSM 路径描述；第 3 章第 164 行与第 6 章第 271–279 行的 R029 数值是否重算。已知：R029 public1 在 0.7.0 中两个口径都不能运行；thesis96 路径在任何口径下都用冻结输入 | 第 3、6 章的口径归属与数值例子 | 作者、代码负责人 |
| 6 | 23 区 GB 研究的基础数据包是哪个。网络模块只在修正口径下运行，而 GBP1 public1 在修正口径下不合格 | 第 2 章第 9 行、第 7 章第 107 行 | 代码负责人 |
| 7 | 方法学中 “Doctoral” 路径是否改名。按 A26 的定位，建议改为不含 “doctoral” 的名称（例如 “Thesis-96 national pathway”），避免读者以为它就是论文复现口径 | 第 5、6 章标题与交叉引用 | 作者 |
| 8 | 网络模型的两处实现选择请作者知悉：停机段低于最短停机时间时作为最后手段，按其报价结算；有补贴时停机段的比较对象是风电下调价 \(-s\)（默认无补贴时为 0） | 第 4 章 K-3、第 7 章 | 作者（知悉；不同意时由代码负责人改） |
| 9 | f2 草稿与参数表中光伏模型参考文献（Spencer 1971、Erbs 1982、Hay & Davies 1980、Jacobson & Jadhav 2018 等）的书目信息与拟合系数没有联网复核 | 第 3 章参考文献 | 方法学修改员（发布前核对） |

GBP1 public1 在 0.6.0-alpha.2 与本版之间的结果差异（勘误）不写进方法学：按 A26，方法学描述新模型，不是论文结果的勘误。是否在网站上公开勘误，见网站交接文档第 7 节第 3 条。

## 10 本轮范围之外、但仍过时的表述与顺带发现

**10.1 正文中仍过时的表述（可以在 0.4 一并改，也可以不改）**

| 位置 | 问题 | 审查编号 |
|---|---|---|
| `MATHEMATICAL_REFERENCE.md` 全文、模型卡第 1–13 行 | 正文仍用 “FORCE” 作为模型名（“FORCE model card”“FORCE algorithm”“FORCE-CEM v1”）。`docs/BRAND_AND_VARIANTS.md` 只保留 `force.*` 等历史标识符，没有保留产品名；是否改为 VALUE 由作者决定 | — |
| 模型卡第 77–79 行 | “Short diagnostic runs only verify wiring and never publish annual economic indicators”，与实现不一致（短运行把全年资本年金与部分时段运行费用混算） | P4-18 |
| `r029_cem.md` 第 240–250 行 | 外生抽蓄日程只在 Doctoral 路径中调用；起始年不是 2025 时初始参数跳变 | P5-14 |
| `r029_cem.md` 第 225、266 行；`VALUE_METHODOLOGY.md` 第 163 行 | 称内生投资应用了建设期和规划成功率；实现中恒为 1 年、成功率为 1 | P4-05 |
| `VALUE_METHODOLOGY.md` 第 191 行 | 称储能碳库存已覆盖，实际未计算 | G3-03 |
| `VALUE_METHODOLOGY.md` 第 193 行 | 论文碳情景“保留历史边界”，实际端到端不产出量 | G3-04 |
| `VALIDATION_AND_CLAIMS.md` 第 14 行 | 独立 oracle 依赖系统 `cbc`（只从 PATH 查找）的边界没有注明 | R2-06 |

各项细节在 `VALUE_review_2026-10-04.md` 中，可按编号 `grep -n` 查找。

**10.2 顺带发现（交代码负责人，方法学不要照抄这些文字）**

1. **两条 advisory 的文字与论文复现口径的当前行为不一致**（只影响显示，不影响结果）。这两条 advisory 对每个论文复现口径的 Run 都显示：
   - `p06.avoided-cost-downward-order` 的说明写 “kept stale requirements after a break in the down-regulation stack”。两个口径的下调现在都只扣一次（U7），这半句已不适用于当前的论文复现 Run。其余两点（爬坡历史按位置匹配、只有水电返还预算）仍然成立；
   - `fx8.nuclear-in-service-at-start` 的说明举例 “on GBP1 2025 nuclear first cleared on 12 December and generated about 2 TWh”。当前的 GBP1 public1 论文复现运行中，核电全年没有被接受（N-7）。

   方法学正文按 N-7、N-9 写，不引用这两条 advisory 的文字。
2. **`CHANGELOG.md` 的两处与当前状态不一致**（方法学修改员引用 CHANGELOG 时注意）：
   - 第 57 行 “Correction ids” 表 P0-6 一行把 `p06.storage-net-per-period` 列在 “Corrected profile only”，而第 69 行 R4-1 一行写它已是通用修正。以修正目录为准：通用；
   - 第 86–87 行写 “The trajectory columns of D1–D3 … are bit-identical to 35aadb3”，而 `P0_GOLDEN_DELTA.md` 只有 D1、D2 逐位相同，D3 已重基线。以 `P0_GOLDEN_DELTA.md` 为准。
3. **`docs/release/P0_GOLDEN_DELTA.md` 的两句固定文字没有跟上**（文字写在生成脚本 `scripts/golden/delta_report.py` 第 456、474 行附近）：
   - 第 10–11 行只列出数值报告 `D4-r9.json`、`D5-r1.json`，`tests/golden/reports/` 中还有 `D3-r14.json`、`D4-r12.json`、`D5-r3.json`；
   - 第 33–35 行列出的轨迹例外只有 P6-24、P6-02、P6-03、P6-04 和 P4-01-thermal，`tests/golden/doctoral_trajectory_rebaselines.json` 中还有 A15、DEV-BAL-04、DEV-STO-01 三项（A26）。

   方法学引用 golden 的重基线范围时，以 `doctoral_trajectory_rebaselines.json` 和 `tests/golden/reports/` 为准（第 5.3 节 VC-3）。
