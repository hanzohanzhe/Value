# VALUE 0.7.0-alpha.1 网站交接文档（给 value.ac 上传员）

- 日期：2026-10-08。
- 依据的代码状态：分支 `fix/review-2026-10-04`，代码状态 `6014421`（此后的提交只改文档）；对照 `main` 的 `35aadb3`，即 0.6.0-alpha.2 的源码。本文只描述这一状态下的规则和事实，施工经过见 git 历史与 `docs/dev/p0-reports/`。
- 读者：维护 `website/` 并上传 value.ac 的人。`website/` 包括 `build.py`、`content.py`、`journey.py`、`site.json`、`methodology_page.py`、`publication.py`、`release_candidate.py`、`check_site.py`、`sync_methodology.py` 和 `static/`。
- 本文只写交接内容，不改 `website/` 下的任何文件。本分支的 `website/` 与 35aadb3 逐字节相同（`git diff 35aadb3 -- website/` 为空），文中的行号对两边都适用。
- 依据的优先次序：`docs/dev/P0_DECISIONS.md` 最高（同一事项有多条时，以编号靠后的为准），其次是代码，再次是 `CHANGELOG.md` 等公开文档，最后是本文。各项内容的出处见第 5 节。

---

## 0 先读这一段

1. **网站的上传和发布都要等前端整体翻新完成（DECISIONS A17、A21）。**
   - 整体翻新（“做法二”）须作者另行下令才开工。翻新完成之后才推送源码、开 PR。
   - 网站上的截图只能从翻新后的界面拍。第 2.12 节和附录 A.3、A.4 中的界面字符串，届时要逐条重新核对。
   - 现在可以按本文起草文案，但不要上传。
2. **0.7.0-alpha.1 目前只在本地分支上。** 没有推送，没有 tag，没有构建安装包，作者本机的安装也没有重装。网站上能下载的 Full `2026-10-03-rc1` 是 **0.6.0-alpha.2**，不含本版的任何修正。
3. **网站方法学的定位（A26）。** 网站上的方法学描述的是在网上发布的 VALUE 新模型，即默认的修正口径，**不是**博士论文。论文复现口径是一个兼容口径：它保留论文时期的设定，同时接受两个口径共同的错误修正。网站任何地方都不写“网站方法学对标论文”“与论文一致”或“复现论文”（2.1 节）。
4. 网站改动分四个阶段（第 3 节），每处改动属于哪个阶段见第 4 节。阶段 0 只纠正 rc1 现有页面的版本标注，与 0.7.0 的内容无关；它能否在翻新之前单独上线，由作者决定（第 7 节第 2 条）。
5. 本版要在网站上反映的内容（第 2 节）：
   - 网站方法学的定位（2.1）；
   - 两个方法学口径及其固定标签（2.2）；
   - 两个口径共同的修正（2.3），只在修正口径中使用的设定（2.4），以及两个口径都保留的模型设定（2.5）；
   - 验证门、stress event、未供电量和年度结果的发布规则（2.6）；
   - 本地 API 安全边界与启动器（2.7）；
   - Run 的启动与准备（2.8）；
   - 四类用户路径的操作（2.9）；
   - 声明范围（2.10）；
   - 版本与下载文案（2.11）；
   - 界面字符串（2.12）。
6. 不得上传或不得写的内容见第 6 节。需要作者决定的事项见第 7 节，其中最急的一项是：rc1 的本地 API 存在安全问题（审查报告 F5-01），0.7.0-alpha.1 已解决，网站是否要提示。

---

## 1 版本身份对照

| 项 | 0.6.0-alpha.2（网站现在描述的版本） | 0.7.0-alpha.1（本分支） |
|---|---|---|
| 应用版本 | `0.6.0-alpha.2` | `0.7.0-alpha.1`；Python 包为 `0.7.0a1`。见 `package.json`、`pyproject.toml`、`docs/release/VERSION_LEDGER.json` |
| 源码位置 | GitHub `hanzohanzhe/Value`，tag `source-2026-10-04` | 本地分支 `fix/review-2026-10-04`，**未推送，没有 tag** |
| Full 安装包 | `2026-10-03-rc1`，四个平台；`site.json` 已列出，`publication_ready: true` | **没有构建**。`docs/VALIDATION_AND_CLAIMS.md` 中 “0.7.0-alpha.1 installers …” 一行为 `not_evaluated` |
| 方法学文档 | 0.3 版次（2026-10-04，依据日期 2026-10-02），网站已导入 | 仍是 0.3。本版的方法学改动写在 `docs/methodology/drafts/0.4/`，0.4 版次尚未生成，也未审阅 |
| 方法学口径 | 不区分口径 | 两个：`value-corrected`（默认）和 `doctoral-lineage-0.6.0a2`（冻结的兼容口径） |

以下几处是历史记录，必须保留版本号 `0.6.0-alpha.2`（受 `tests/test_documentation_consistency.py` 的 `HISTORICAL_VERSION_RECORDS` 和 `VERSION_LEDGER.json` 保护）。**不要**改成 0.7.0，否则版本一致性测试会失败：

- `website/content.py` 第 74 行的 BibTeX，以及第 80 行的历史元数据；
- `website/static/assets/value-source-CITATION.cff`；
- `website/static/assets/value-source-metadata.bib`。

---

## 2 网站需要反映的内容

### 2.1 网站方法学的定位（A26）

- **网站方法学描述 VALUE 模型本身。** 它对应网上发布的新模型，也就是新 Study 和 Run 默认使用的修正口径（`value-corrected`）。网站不把它写成博士论文的方法，也不写“对标论文”“与论文一致”“复现论文”。
- **论文复现口径是兼容口径。** 它按 VALUE 0.6.0-alpha.2 的实现保留论文时期的设定，例如：
  - 下调时先削零成本的风电；
  - 风电、光伏不乘损耗系数；
  - 核电和水电不按可用率折减；
  - 沿用原有的数据读法。

  这些是**设定，不是错误**，网站不要写成“论文的做法是错的”。实现错误、数据读取错误和记账口径的修正，对论文复现口径同样适用（2.3 节）。
- **论文本身的代码**以 GitHub 上已锁定的历史研究档案为准。网站已有的 “Historical archive / 历史研究档案” 说明（about 页，`content.py:87`，链接定义在 `:85`）把它写成较早的研究档案、不是当前 VALUE 的源码，这一定位与 A26 一致，保留不动。
- **建议写法**（中文页）：“修正口径是 VALUE 的默认模型，网站方法学描述的就是它。论文复现口径按 VALUE 0.6.0-alpha.2 的实现保留论文时期的设定，同时包含两个口径共同的错误修正，用于对照，不是论文结果的精确复现。”

### 2.2 两个方法学口径与标签（Q2、Q3、Q14；`docs/generated/METHODOLOGY_PROFILES.md`）

| 机器 id | 完整标签（英文原文，网站照抄） | 界面短名 | 固定附注 | 默认 | 冻结 |
|---|---|---|---|---|---|
| `value-corrected` | `Corrected methodology (default)` | `Corrected (default)` | Current default methodology with review fixes of 2026-10. | 是 | 否 |
| `doctoral-lineage-0.6.0a2` | `Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)` | `Doctoral reproduction` | `not an exact reproduction of the 2026-07-18 retained trajectory` | 否 | 是 |

- **标签照抄。** 完整标签定义在 `gridform_core/data/methodology/profiles.json` 和 `app/features/workspace/runValidation.ts:14-15`，出现在 Run 上下文条的口径标记、Run 记录（`resolved-run.json`）、`CHANGELOG.md` 和 `METHODOLOGY_PROFILES.md` 中。网站首次提到某个口径时用完整标签，逐字照抄，不改大小写，不缩写。
- **界面短名。** 以下三处界面用短名：
  - Study composer 第 1 步（`1. Study identity`）的 `Methodology` 单选框。论文复现一项下附说明 `Locks thesis-era reference settings: legacy storage tariff, doctoral carbon factors, thesis-era modules and data packs only. External code is not allowed.`；
  - `Research guide` 页（研究路径）第 2 步的“方法学口径”一项（口径名和 profile id）；
  - Runs 页 `What will run` 中的 `Methodology` 一格。

  网站写操作步骤时可以引用短名，但介绍口径时用完整标签。
- **固定附注（Q2）。** 凡出现 doctoral 完整标签，必须同时出现固定附注。中文页写作：“论文复现口径（Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)）：按 VALUE 0.6.0-alpha.2 的实现保留论文时期的设定，**不是** 2026-07-18 保留轨迹的精确复现。”
- **中文名。** 中文统一写“修正口径（默认）”和“论文复现口径”，后面括注英文原标签。应用界面目前中英混排（主工作区为英文，`Research guide` 页和映射编辑器的说明为中文）；统一的中英切换放在前端整体翻新中（`docs/dev/P0_FRONTEND_DEVIATIONS.md` F-R22-3），翻新后以应用的中文为准。
- **默认口径与旧 Run。** 新建的 Study 和 Run 默认使用修正口径。0.6.0-alpha.2 及更早版本的 Run 显示 `Methodology not recorded (pre-2026-10 run)`。
- **论文复现口径的边界（Q3）：**
  - 只运行论文谱系模块（清单见 `METHODOLOGY_PROFILES.md`），并把参考配置写进 Study：legacy storage tariff 和 doctoral 碳因子情景；
  - 只接受四个论文期数据包：GBP1 public1（`value-uk-open-data-pack-v1`）、`value-uk-1000twh-reproduction`、VALUE 101（`value-101-baseline-v1`）、`value-synthetic-contract-pack-v1`。R029 不在其中；
  - 已启用外部模块或扩展时拒绝运行；
  - 网络模块（staged PSM 及其 copperplate、zonal 平衡，DC、AC 网络）只在修正口径下运行。
- **年度结果的发布（Q14）。**
  - 论文复现口径的 Run，只有全部原始不变量都通过，年度结果才在结果页发布；否则结果页显示 `Withheld`，Inspect 和账本文件照常可用。Run 还在进行时显示待定（2.6 节）；
  - 本版代码上的论文复现参考运行，即 VALUE 101 一天、VALUE 101 两年和 GBP1 public1 第一个模型年（golden D3、D4、D5），原始不变量全部通过，年度结果在结果页发布；
  - 在其他数据或配置上，扣发仍可能出现，所以网站不要写“论文复现口径的年度结果总会发布”。

### 2.3 两个口径共同的修正（universal；Q9、Q12、A2、A3、A4、A5、A16-5、A26、A28）

论文复现口径冻结 0.6.0-alpha.2 的行为，下面这些修正是冻结之外仅有的变化，两个口径都适用。它们修正的是实现错误、数据读取错误和记账口径，不改变论文时期的设定。网站介绍论文复现口径时要一并写出：

- **互联线序列**按 17,520 期时钟逐期对齐（`p05.interconnector-clock`）。
- **GBP1 的三处读取**：
  - 比利时电价按逐小时的 EUR 读取，以 1.1 EUR/GBP 换算，并展开为两个半小时（`p05.belgium-price-currency`）；
  - BE/NL 潮流文件按线路身份分配（`p05.boundary-identity`）；
  - 需求放到 UTC 时钟上，处理 2022-10-30 的夏令时切换（`p05.demand-utc-clock`）。
- **按声明的列读取**：读取数据包声明的 CSV 列，隐式选中的整数序号列会被拒绝（`p05.declared-column`）。
- **火电投资净收入**扣除运行成本，即燃料、碳价和单位时间成本（`p07.thermal-net-revenue`，A4）。风电、光伏、储能仍以毛收入作为利润，这是两个口径都保留的设定（2.5 节）。
- **论文内核的三项实现错误（A26）：**
  - 削减分支的下调只做一次（`r41.down-regulation-taken-once`）：某台非 VRE 机组已满足剩余的下调需求时，需求随即清零，不再从后面的报价（通常是风电）重复削减；
  - 每个储能每个时段只有一个净头寸（`p06.storage-net-per-period`）：各出清阶段共用额定功率，已放电的储能先减少本时段放电才能充电，已充电的储能不再报放电；
  - 平衡阶段的必发核电盈余只计一次（`r41.must-run-surplus-counted-once`），不再重复发电、重复付费。
- **缺电价值（VoLL）**在两个口径中都是 17,000 £/MWh（`fx5.voll-17000`）。它只给模型（PSM）记录的切负荷计价，不改变调度，也不给 stress event 的缺口计价（2.6 节）。
- **stress event 记账**（A2），见 2.6 节。
- **已供电量扣除 stress 缺口**（`r5.served-energy-net-of-stress-shortfall`）：每 MWh 供电成本和每 MWh 交付电量的碳强度，分母都是需求减去全部未供电量（PSM 记录的切负荷加 stress 缺口）。只改账，不改调度；没有 stress 时段的年份不受影响。
- **只在核算区或记录层面的修正**（Q12）：
  - 残差、审计、成本账 v2、验证报告；
  - 储能报价账本（`fx4.storage-offer-ledger`）：导出账本的 `storage_orders` 表和 Market replay 的拍卖视图逐条列出储能报价；
  - 账本时钟标注为 UTC（`r43.model-clock-utc-label`），只改元数据标签，不改任何数值；
  - 储能状态记录有上限（`r53.bounded-storage-state-record`）：完整市场回放中，一个储能的存量批次超过 128 个时，出清声明只列出本阶段报价用到的批次和一项汇总。调度、其他账本表和全部结果不变。
- **Study 身份与迁移**：Run 记录口径身份；已保存的 Study 在代码或方法变化时按 Q13 分类（2.9 节）。

**对网站的含义**：用 0.6.0-alpha.2 及更早版本（包括 rc1）得到的结果，没有这些修正。在 GBP1 public1 上影响尤其明显。是否在网站公开一份勘误，由作者决定（第 7 节第 3 条）。

### 2.4 只在修正口径中使用的设定

网站用一两句话概括即可。细节链接到 `CHANGELOG.md`；0.4 版次审阅通过后，再链接方法学。现行规则如下：

1. **默认 PSM 的出清、储能与结算（Q8、A8）。**
   - VRE 盈余按来源逐期重建并记账；必发盈余先于 VRE 使用，不重复发电；
   - 同一 0.01 £/MWh 价位内，储能排在发电之后；
   - 内置动态储能成本对象：电池只报循环损耗，抽水蓄能和氢储能报 0。用户公式、legacy tariff 和外部模块的报价不变；
   - 每个阶段所有被接受的供给方（含储能）都按该阶段的统一边际价结算；储能报价费在本时段结算；
   - 不在出清前直接用 VRE 制氢。
2. **互联线进口进入日前出清**（`fx6.day-ahead-interconnector-imports`）。
   - 当期有正进口能力的互联线，按当期对侧价格报入日前出清，与国内发电同一排序；平衡阶段只报日前没有用完的进口能力；
   - 论文复现口径保持论文规则：进口只在平衡阶段出现；
   - 网站可以写“修正口径的日前出清接受互联线进口”，不要写“进口建模已验证”。
3. **核电在每个模型年开始时就在运**（`fx8.nuclear-in-service-at-start`）。
   - 核电按各站可用率作为基荷运行；启动成本只在换料、停运或未被接受之后重新启动时收取一次；
   - 论文复现口径保持论文规则：核电未运行时报价要加启动成本，被接受后一直运行到年底。这一路径依赖在方法学中披露。
4. **下调与弃电的经济顺序**（`p06.avoided-cost-downward-order`；默认 PSM 用 `r12.economic-downward-order`，staged/zonal 网络模型用 `r32.network-economic-downward-order`）。实际需求低于计划、需要往下调时：
   - 按省下的成本从高到低排序（核电带 100 £/MWh 的下调加价）；
   - 燃气和生物质先降到最小稳定出力（CCGT、OCGT 50%，生物质 35%）。这一段不需要停机，排在弃风之前；
   - 再往下就要停机。按日前预测估计的停机时长 H，比较省下的燃料、碳与可变成本和重启成本：净节省 a(H) = c − S(H)/(m·H)（m 为最小稳定出力比例）大于 0 时先停火电，否则先弃风；
   - H 短于最短停机时间（CCGT 6 h、OCGT 0.5 h、生物质 6 h）时，停机只作为最后手段；
   - 重启成本取自文献和英国平衡机制数据，经作者审核，并按英国 CPI 换算到模型的 2025 年价格基准。2025 年的 CPI 指数值还要核对一次（第 7 节第 9 条），核对之前网站不列具体数字；
   - 论文复现口径保持论文的顺序，即先削零成本的风电；
   - 网站可以写“修正口径按重启成本与省下的成本，决定先降火电还是先弃风”。不要写成哪一方总是先降（A19：不得预设火电一定比风电贵），也不要写“论文的顺序是错的”。在参考运行中，这条规则很少起作用（2.10 节）。
5. **储能扩容**（`p07.storage-leftover-headroom`、`r13.per-type-battery-caps`）。
   - 新储能只能用现有储能充电之后剩下的盈余；
   - 1C、0.5C、0.25C 三种电池各自取 0.2 × 功率余量（`expansion.storage_cap_fraction`），这是论文的设计。
6. **风电与光伏（A9、A13、Q15）。**
   - ERA5 的累积辐照用于它累积的那一小时；
   - 风光出力乘文献损耗系数：陆上风电 0.903，海上风电 0.815，光伏性能比 0.83；
   - 光伏辐照逐时段换算到朝南倾斜面：Erbs 分解，Hay–Davies 换算（反照率 0.2），倾角取 Jacobson & Jadhav 的最优值，太阳位置用 Spencer 公式；
   - 不对统计负荷率标定，容量因子与 DUKES 并列披露（每个 Run 的结果摘要里都有）。
7. **核电与径流水电的可用率（A10、A14）。** 核电用各站 2019–2024 年的平均负荷率，按月份退役（Heysham 2、Torness 为 2030 年 3 月）；径流水电用 DUKES 负荷率 0.3487，乘季节形状。取值经作者审核。
8. **数据读取与数据门。**
   - 修正口径按声明读取分辨率和闰年，严格模式下拒绝有歧义的列；
   - 有登记缺陷或时序问题的非工作区数据包，不能用于修正口径。因此发布版 GBP1 public1 只能用于论文复现口径；发布版 R029 public1 在修正口径下读取逐时光伏曲线时被拒绝（2.10 节）；
   - 互联线报价和出口价格保留源数据中的负价。
9. **成本账。** 修正口径的头条成本不含径流水电的兼容资本，这部分在 Runs 页作为备忘行显示（`Memo: run-of-river hydro compatibility capital (excluded from headline)`）。
10. **网络模型**（只在修正口径下运行）：
    - zonal solver contract v4；
    - 分布在多个母线的资产按份额拆分；
    - staged 平衡的 dec 按经济成本定价，同价按比例接受，结果与资产名称无关；
    - 网络成本对照一个不含网络约束的 LP 反事实计算；
    - 边界边际值是 primary 阶段的对偶值，是诊断量，不是分区电价；
    - 下调顺序见第 4 条。

### 2.5 两个口径都保留的设定（可作为模型假设或模型限制来写）

- **投资判据不折现。** 用 ROI 和回收期判断，所有金额都按起始年币值计价（A6）。
- **运营成本口径（A4、A7）。** 只有火电（燃气、生物质）有可变运营成本，并在投资净收入中扣除。风电、光伏、储能没有可变 OPEX，固定 OPEX 视为已含在年金化 CAPEX 中，所以它们的毛收入即利润；它们的固定 OPEX 只作为成本账的备忘行，不进入头条。
- **供给不足时不改调度（A2）。** 缺口记为 stress event，出力和电价不变。
- **生物质没有 CfD/ROC 补贴收入（A24-2）。**
  - 它按燃料加碳价的全额成本报价，在 GB 参数下为 85 £/MWh，高于 CCGT 的 55.07 和 OCGT 的 74.92，所以几乎不被调度；
  - 机组中有生物质的 Run 会显示 advisory `Biomass without support revenue`；
  - 补贴建模放在后续版本（P4-07）。
- **储能能量不跨年。** 默认 PSM 每年新建储能对象，年末存储的能量不带入下一年；这一点只在报告中披露。

### 2.6 验证门、stress event、未供电量与年度结果的发布（A2、Q14）

- **stress event（两个口径）：**
  - 凡是接纳的供给小于需求的时段，都逐期记录缺口（`shortfall_mwh`），并把连续的时段分组成事件；
  - 年度结果汇总事件数、stress 时段数和总缺口；能量平衡账把缺口记为未供电量，所以账能闭合；
  - **调度和电价不因此改变**；
  - 界面显示位置：Run 上下文条的 `Stress events` 字段（`None`，或 `● {n} periods · {缺口}`）、Market replay 窗口卡片的 `Shortfall`，以及全年 stress 事件列表（表头 `Start (model date & time, UTC)`）；
  - Market replay 的 CSV/JSONL 导出逐时段带 `clearing_price_basis`、`period_shortfall_mwh`、`period_stress`、`shortfall_basis` 四列。
- **未供电量的三种写法，网站不要混为一谈：**
  - 年度卡片的 `Unserved demand` 是全部未供电量，即 PSM 记录的切负荷加 stress 缺口，旁注 `incl. stress shortfall · {x} MWh recorded by the PSM`；
  - 比较页分两行列出：`Unserved energy incl. stress shortfall (MWh)` 和 `Unserved energy recorded by the PSM (MWh)`，另有 `Annual demand (MWh)` 和 `Demand served (MWh)`；
  - 成本账按 VoLL（17,000 £/MWh）计价的**只有** PSM 记录的切负荷。stress 缺口不按 VoLL 计入成本，网站不要写“缺口按 VoLL 计入成本”；
  - 每 MWh 供电成本（结果页写作 `£{x}/MWh served`）和碳强度的分母已扣除全部未供电量（2.3 节）。
- **未利用的 VRE（Unused VRE）：**
  - 年度卡片 `Unused VRE (PSM boundary)` 显示 `{x} MWh · {y}% of available`；比较页列 `Unused VRE at the PSM boundary (MWh)` 和 `Unused VRE share of available VRE (%)`；
  - 两个口径的测量边界不同：论文复现口径的账本把预平衡盈余（分给储能、出口、溢出的部分）单独列出，比较页另列 `Pre-balancing excess, reported separately (MWh)`；修正口径在全节点上按“可用减总出力”计算；
  - 所以跨口径比较时，比较页只并列两边的数值，不给差值，并写明原因；同一口径的 Run 之间照常给差值；
  - 网站不要把两个口径的弃电量当作同一个量相减。
- **模型时钟。** 模型在 UTC 半小时、固定 365 天的模型年上运行（闰年跳过 2 月 29 日，没有夏令时切换）。Market replay 写作 `(UTC model time)`，导出的时间带 `Z`。
- **旧运行的证据效力。** 0.6.0-alpha.2 及更早版本不报告这种缺口，所以旧运行的“能量平衡通过”不能作为“没有缺电”的证据。
- **验证门。**
  - 验证门包括运行不变量、能量平衡和储能限值。任一失败时，应用显示 `Validation gate failed: {gate 名称}`；
  - 修正口径的 Run 被门挡住时，结果页不显示年度合计，改为显示 `Annual results not published`，并给出进入 Inspect 和账本文件的入口。
- **论文复现口径的发布状态：**
  - 上下文条只在论文复现口径下多一个字段 `Raw invariants`：全部通过时为 `● Passed`，否则为琥珀色 `● {k} failed`；Run 还在进行时为 `Pending`，提示框为 `Annual results pending the raw-invariant check`；
  - 原始不变量没有全部通过时，提示框标题为 `Annual results withheld for this reproduction run`，正文写明失败的原始不变量和行数，下方有 `Open in Inspect` 和 `Open ledger files`；
  - 论文复现口径的能量平衡状态 `● Conformant` 只表示论文账本在其声明的边界上闭合，不等于物理验证通过，网站不要写成“已验证”。
- **advisory：**
  - 每个 Run 在上下文条下方的折叠区列出读取时生成的 advisory；
  - 论文复现口径的 Run，会列出它没有应用的各项修正口径设定；
  - high 或 critical 级的 advisory 会使涉及该 Run 的比较标为 `needs_review`；
  - 关于核电、径流水电或生物质的 advisory，只在 Run 冻结的机组中有这类资产时出现；Run 还没冻结完输入时，advisory 标为暂定。
- **0.6.0-alpha.2 的旧 Run：**
  - 只读，不被改写；
  - 带 advisory `VALUE-ADV-2026-10-04-REVIEW`（`Produced before the 2026-10 review fixes`，high）；
  - 这些 Run 记录的 `passed` 显示为 `superseded_pre_fix`，涉及它们的比较标为 `needs_review`。
- **对网站的含义**：网站上现有的“已通过”“哈希一致”“已完成”等证据，都来自 0.6.0-alpha.2 及更早版本，必须标明版本。在 0.7.0 中它们属于 `superseded_pre_fix`，而且**没有在 0.7.0 上重跑**。

### 2.7 本地 API 安全边界与启动器（`SECURITY.md`；`CHANGELOG.md` “Local API security boundary”“Run lifecycle”；`docs/USER_GUIDE_ZH.md` 第 2、13、19 节）

- **只经界面地址访问。**
  - 浏览器只与界面地址通信：`http://127.0.0.1:8800` 或 `http://localhost:8800`。`/api` 由界面网关带着会话转发；
  - 用其他主机名、另一份安装的书签打开，或者数据目录不一致时，页面显示 **Open VALUE from its launcher**。处理方法是关闭页面，用启动器重新启动。
- **启动器。**
  - 启动器把 `--api-origin` 交给网关，从不传递会话令牌；
  - 就绪后终端打印 `VALUE ready: http://127.0.0.1:8800/` 和 `Keep this window open. Ctrl+C stops the API and frontend.`。
- **字节码。** 每个解释器都以 `-B -s -X pycache_prefix=<新目录>` 启动；安装目录里多余的字节码不会阻止启动，可以用 `diagnose-value --repair-bytecode` 移入 `state/quarantine/`。
- **关闭 VALUE 时（Q4）：**
  - 已经启动模型 worker 的 Run 会在后台继续。终端列出这些 Run（`VALUE: {n} run(s) keep running in the background and are supervised again at the next start: …`），下次启动时通过租约重新接管；
  - 还在准备阶段的 Run 不会继续，见 2.8 节。
- **一个数据目录只能有一个后端。** 第二个后端以退出码 3 停止，不改动任何内容。
- **一台电脑一个使用者（Q11，`SECURITY.md` “Single-user host assumption”）。** 不要安装在共用电脑或远程桌面服务器上。本版没有登录功能。
- **直接调用 API 的脚本。**
  - 除 `GET /api/health` 和 `OPTIONS` 外，每个请求都必须带 `X-VALUE-Session`，用 `backend.api_session.authorized_headers` 生成；
  - CORS 已移除；
  - 新建 Study（`POST /api/projects`）时，若同名 Study 已存在而请求没有带 `base_revision_sha256`，返回 409 `GF_STUDY_ID_EXISTS`，要改名；
  - 这些影响“改模块”和“加功能”用户的脚本。
- **损坏的外部模块或扩展。**
  - 外部模块或扩展损坏，或名字冲突时，会被隔离，VALUE 照常运行，health 显示 `degraded`；
  - 修好后在 Modules 页点 Rescan（Rescan 也会重新导入扩展钩子）；
  - 离线自救用 `python -m gridform_core.module_recovery`。
- **安装与升级。**
  - 安装器只装进不存在或为空的目录；
  - 安装后不要移动或重命名安装目录，因为 receipt 固定了绝对路径；
  - 升级时把新版本装进另一个空目录，状态不会自动迁移。手工迁移步骤见 `docs/release/P0_ACCEPTANCE.md` 第 6 节；
  - 0.6.0-alpha.2 留下的未完成 Run 不能在 0.7.0 中恢复，**升级前先完成或取消**；
  - 新旧版本使用同样的端口（8766、8800），不能同时运行。

### 2.8 Run 的启动与准备（A24-5）

- **立即返回。** 点击启动后，请求立即返回，Run 马上出现在 Runs 列表中。
- **进度显示。** Runs 页和 Learn 页显示准备进度：`Preparing · step {i} of 4: {阶段} · {用时} elapsed`。四个阶段依次是：
  1. `Recording and archiving the execution environment`；
  2. `Freezing the Study's inputs`；
  3. `Checking disk space and reserving output space`；
  4. `Starting the model worker`。
- **首个 Run 较慢。** 在新数据目录中，第一个 Run 要先把 Python 运行环境归档一次，约 3 分钟；之后的 Run 冻结输入不到一分钟。界面原文：`The first Run in a new data folder archives the Python runtime once (about 3 minutes); later Runs freeze their inputs in under a minute.`。准备期间，其他页面和操作照常可用；结果页不读取这个 Run 的结果，Market replay 和 Inspect 显示 `The Run is still preparing`。
- **运行时间估算。** 还没有可比的已完成 Run 时，估算给出区间，例如 `estimated 3 min to 18 min (no comparable completed Run yet)`；有实测后给一个值。
- **取消。** 准备中可以点 `Request safe cancellation`，Run 在模型 worker 启动之前停止。如果正在归档运行环境，取消要等这一阶段结束才生效。
- **关闭 VALUE。** 准备期间关闭 VALUE，这个 Run 不会在后台继续。下次启动时它显示为 `Run preparation interrupted`，需要重新启动 Run。
- **数据包冻结。** 被冻结的数据包在准备期间不能替换文件：上传或提交映射会返回 409 `GF_DATA_PACK_FREEZING`。
- **直接调用 API 的脚本：**
  - `POST /api/projects/<id>/runs` 返回 202 和 Run 记录。此时 `status` 为 `snapshotting`，`preparation.state` 为 `preparing`；之后轮询 `GET /api/runs/<id>`；
  - 准备阶段的失败记在 Run 上，保留原错误码，或记为 `GF_RUN_PREPARATION_FAILED`；
  - preflight 拒绝时仍返回 400，并且不建 Run；
  - preflight 期间 Study 被改动时，返回 409 `GF_RUN_START_STUDY_CHANGED`。
- **文档缺口。** 这一行为还没有写进 `CHANGELOG.md` 和用户指南（第 7 节第 7 条）。

### 2.9 四类用户路径（网站 `journey.py` 的 `ROLES`）

网站上的四条路径是复现（reproduce）、换数据（adapt）、改模块（modify）、加功能（extend）。0.7.0 中各路径的操作如下：

| 路径 | 0.7.0 的操作 | 依据 |
|---|---|---|
| 复现 | 在 Study composer 第 1 步选择方法学口径；`Research guide` 页和 Runs 页 `What will run` 都显示 Study 当前的口径（研究路径只显示，不提供切换）。“对照参考结果”必须对照**同一版本、同一口径**的参考，0.6.0 rc1 的参考不能对照 0.7.0。0.6.0 保存的 Study 首次运行前，界面显示 `This Study needs your confirmation before it runs`，确认后另存为新修订（`Review and save as new revision`）。启动后 Run 立即列出并显示准备进度（2.8 节）。论文复现口径的年度结果若被扣发，在 Inspect 或账本文件中查看。年度卡片和比较页列出未利用的 VRE；跨口径比较只并列数值，不给差值（2.6 节） | Q2、Q13、Q14、A24-5 |
| 换数据 | 映射 CSV 时要声明列，隐式整数序号列会被拒绝（`GF_DATA_INDEX_COLUMN`）。**需求**至少覆盖一个模型年：半小时数据至少 17,520 个值；逐时数据（8,760 或 8,784 行，或声明的时间戳步长为 60 分钟）在映射时每小时用于两个半小时，审阅中给出 `GF_MAPPING_HOURLY_DEMAND` 说明。**VALUE 101 的需求文件**表头写 mwh、包内标为 MWh/period，但 VALUE 按 MW（半小时平均功率）读取；角色卡和映射编辑器写明这一点，按这些数值改写需求时映射中选 MW。新需求序列的年电量与被替换的文件相比超过 1.5 倍或低于 0.67 倍时，给出 `GF_DATA_DEMAND_SCALE` 警告（不阻止提交）。逐时的价格和可用量，每个值用于两个半小时；需求以外的序列不满一个模型年时从开头重复补齐，提交前要另行确认。可以声明时间戳列（UTC 或 Europe/London）和日期顺序（自动识别、DD/MM/YYYY 或 MM/DD/YYYY），系统逐行检查重复、缺口、倒序和步长，有问题不能提交；Europe/London 时间在映射时换成 UTC。EUR 价格必须填 EUR per GBP 汇率、汇率口径（年均、月均或固定汇率）和价格年份；价格年份不是 2025 时给出提示（VALUE 只换算币种，不按年份折算）。CSV 须为逗号分隔。Data 页每个数据包有校验面板：三层校验（Structural、Chronology、Plausibility），以及两个口径的资格。Study composer 把不符合所选口径的数据包标为 `not available with this methodology`。互联线数据角色写作 “{Country} interconnector availability (+ import / - export)”：正值为进口能力，负值为出口能力。用户映射的数据包只能用于修正口径；发布版 GBP1 public1 只能用于论文复现口径。正在被 Run 冻结的数据包不能替换文件；有 Run 在准备或运行时，映射编辑器中暂存的文件和列选择保留不变 | P0-5a、A16-1、A16-2、A24-5、A27、A28 |
| 改模块 | 外部模块只能在修正口径下运行；论文复现口径拒绝已启用的外部代码。属于方法变化的模块升级（`requires_user_opt_in`），已保存的 Study 要在界面确认；纯代码身份的变化自动追加修订。损坏的模块被隔离，不会阻止 VALUE 启动；合同 ID 不匹配时安装或启用直接报 `GF_MODULE_CONTRACT_MISMATCH`。Modules 页常驻 `Disabled and quarantined` 区，每项有 `Enable`、`Rescan`、`Remove`，并显示清单文件和 ID；页头有 `Rescan modules`；模块计数写作 `{n} of {m} ready · {k} experimental`。同一模块 ID 有两份清单时两份都被隔离（`GF_MODULE_ID_DUPLICATE`）：在任一行点 Disable 会停用该模块，并把另一份清单移到 `modules/disabled-manifests/modules/`；仍有副本时 Enable 被拒（`GF_MODULE_ID_COLLISION`，提示写出副本文件名）。允许原地修改已安装模块的源码：预检给出琥珀色提示，Run 记录新的源码哈希，比较页显示模块方法已改变；之后仍可从该 Study 派生对照 Study。Run 排队时记录已安装的代码，不会用别的代码启动：有 Run 排队或在准备时安装、启用、停用或移除模块或扩展，确认框写明尚未开始的 Run 不会启动；确认后它们以 `GF_RUN_EXECUTION_IDENTITY_CHANGED` 停止，Runs 页提供 `Resubmit with current code`，用同一 Study 和范围新建 Run；已在运行的 Run 保持原代码，但变更后不能再 Resume。修正口径下，内置储能对象只报循环损耗；用户公式和外部模块的报价不变。储能报价可以在导出账本的 `storage_orders` 表和 Market replay 中核对；Runs 页的 storage cost 槽位显示 PSM 内部调用该模块的账本证据。完整市场回放选了非内置储能成本模块时，readiness 给出 `GF_PREFLIGHT_ESTIMATE_STORAGE_MODULE` 警告：运行时间和磁盘占用可能超出估算，建议先跑短范围，长运行改用 Summary 追踪 | Q3、Q13、P0-2、A16-4、A27、A28、A29 |
| 加功能 | 扩展规则与改模块相同：只在修正口径下运行，冲突时被隔离，修复后 Rescan（Rescan 重新导入扩展钩子），也可以离线自救。扩展编写台的 `Open independent Study draft` 复制当前选中的 Study，草稿名与已有 Study 重名时自动加序号（例如 `… · extension study 2`）。**Run 只记录 `initialize` 钩子的状态和 `after_psm` 钩子返回的产物**；其他钩子返回声明产物（带 `artifact_type`）时 Run 失败（`GF_EXTENSION_OUTPUT_REJECTED`），Runs 页在错误下方写明扩展、钩子和应从 `after_psm` 返回。原地修改已安装扩展的钩子源码与模块规则相同：启用中修改，或停用后修好再 Enable，都被接受，安装记录追加 `accepted_source_edits`，预检给出琥珀色提示（`GF_PREFLIGHT_EXTENSION_SOURCE_CHANGED`），Run 记录新的钩子源码哈希，比较页显示方法已改变；钩子无法导入（`GF_EXTENSION_HOOK`），或已安装清单声明的钩子与安装时不同（`GF_EXTENSION_SOURCE_CHANGED`）时，Enable 仍被拒绝。含实验性扩展的 Run 在上下文条显示 `Experimental extension: {id} {version}`。直接调用 API 的脚本要带会话头（2.7 节），并按 2.8 节处理异步启动。一日课程（`value_101_day`）只运行市场步骤：选了扩展时，范围选项写作 `One-day market lesson (extensions do not run)`，选它会被预检阻断（`GF_PREFLIGHT_SCOPE_SKIPS_EXTENSIONS`）；要运行扩展，改用两时段或更长的范围 | P0-1、P0-2、A16-3、A24-5、A27、A28、A29 |

- 0.7.0 的四角色测试记录在 `docs/handoff/FOUR_ROLE_TEST_REPORT.md`（内部，不发布）。它依据四个角色在源码树导出上的完整走查，以及在当前代码上对每项修复的定向验证和两个口径的两整年冒烟 Run（A28）；测试对象不是安装包。
- 网站验证页 “VALUE four user paths” 的 0.7.0 一行（附录 A.2 第 8 行），结论和范围只能取自这份报告，并且只能在阶段 1 之后上线。报告中有未关闭的高等缺陷时，这一行不上线。
- 报告的现状：四条路径都能从头走通，结论都是“通过”；0 个高等、0 个中等、6 个低等缺陷，没有发现算错的结果。低等缺陷都不影响模型结果，包括独立 Study 草稿在页面刷新后丢失、界面中英混排、比较页没有选择参照 Run 的控件（年度表上方写明差值以第一个勾选的 Run 为参照）、Run 开始准备的头几秒内停用模块时 Run 以笼统的 `GF_INPUT_SNAPSHOT_FAILED` 失败等。
- 原有的 2026-10-02 / rc1 一行保留，并标注版本。

### 2.10 声明范围

网站对 0.7.0 的任何表述，都不能超出下面的范围。

- **逐位一致的范围。**
  - 逐位一致只限于论文复现口径 golden D1、D2（VALUE 101 smoke、two_year_smoke）的 trajectory 区，在 linux-x86_64、CPython 3.10.18、numpy 1.24.4 上用 exact 模式比较（`docs/release/P0_GOLDEN_DELTA.md`）；
  - D3、D4、D5 按经作者批准的通用修正各重基线，每项修正一次，并附数值报告（`tests/golden/reports/`）；
  - 与 2026-07-18 保留轨迹的比较结果为 **failed**。不得写“精确复现论文”。
- **论文复现参考运行。**
  - VALUE 101（一天、两年）和 GBP1 public1 第一个模型年：原始不变量全部通过，能量平衡门和储能门在论文账本的声明边界上为 conformant，年度结果发布；
  - 能量平衡通过的含义是论文账本在其声明的边界上闭合，不是物理验证；
  - GBP1 第一年记录 487 个 stress 时段、74 个事件、缺口 78.8 GWh（A2，调度不变）；
  - GBP1 只跑了一个模型年，没有用本版代码重跑多年的 GBP1。
- **核电路径依赖（论文复现口径）。** 论文规则下，核电一旦被接受，就满功率运行到年底。
- **投资判据。** 投资决策是不折现的 ROI 和回收期检验，使用起始年币值。这是模型假设，不是经过验证的最优解。
- **口径之间的比较。** 修正口径是方法变化。不同口径之间的比较是不同方法的比较，不能把差异归因于某一项输入；两个口径的未利用 VRE 测量边界不同，不能相减（2.6 节）。
- **网络模块。**
  - 只在修正口径下运行；
  - 验证范围是玩具算例和 VALUE 101 算例（`VALIDATION_AND_CLAIMS.md` 中的相应各行）；
  - 本版没有用 11 区、23 区研究套件做研究运行；
  - 已知问题：在某些系数组合下，分区再调度 LP 会以求解器状态错误停止（`GF_ZONAL_SOLVER_FAILURE`，见 CHANGELOG Known issues）。
- **风光容量因子。** 修正口径的风光容量因子**没有**对统计负荷率标定，只与 DUKES 并列披露。GBP1 代表站点等权、弃电前的值，与 DUKES 2020–2024 相比：陆上风电约 1.56 倍，海上风电约 1.23 倍，光伏约 1.04 倍（A9）。不得写“与 DUKES 一致”。
- **GBP1 上的修正口径验收。** 只在本地用未发布的 GBP1 public2 做过，作者要求不发布。网站在作者同意之前，不得写“修正口径已在 GBP1 上验证”，也不得引用这些运行的任何数字。
- **R029 与修正口径。**
  - 发布版 R029 public1 在修正口径下运行时会被拒绝（`GF_DATA_SHORT_SERIES`）：它的逐时光伏曲线有 8,761 个值，最后一个值是 2023 年的第一个小时。数据包校验面板仍显示它可用于修正口径，因为校验层不检查 VRE 曲线的时钟；
  - 本地新版 R029 public2 去掉了这个值，并声明为逐时分辨率，可以用新建 Study 的默认模块在修正口径下运行（golden C10），但没有发布；
  - 网站不得写“R029 可用于修正口径”。
- **互联线日前进口。** 这是方法设定，只在 VALUE 101 和本地 GBP1 public2 上运行过。在 VALUE 101 中，法国线的报价（12 MW、82 £/MWh）每个时段都被拒绝，数值不变。不是经过验证的进口模型。
- **经济下调顺序。**
  - 单元测试的玩具算例覆盖了三种情形：省下的成本高于重启成本时先停火电，低于时先弃风，只需在最小稳定出力以上下调时先降火电；
  - 参考运行中，VALUE 101 两年只有 2025 年的 1 个时段受影响；本地 GBP1 public2 和 R029 public2 的一年运行都没有用到停机段；网络参考算例中 CCGT 没有被下调；
  - 网站不得写“经济下调顺序已在 GB 系统上验证”。它是有文献取值的方法设定；重启成本是文献与平衡机制申报数据的换算值，不是机组实测。
- **生物质。** 生物质几乎不被调度，原因是模型没有补贴收入。这是模型限制，不是对现实的描述。
- **本地 API 安全边界。** 只在 Linux 源码树上验证过。已安装的 0.7.0 要在安装后用 `scripts/verify_local_security_boundary.py` 检查。Windows 发布前需要实机 smoke 测试，macOS 没有实机验证。
- **四角色测试。** 范围以 `FOUR_ROLE_TEST_REPORT.md` 为准，对象是 Linux 源码树，不覆盖安装包、Windows 或 macOS。
- **禁用措辞**（与 `tests/test_documentation_consistency.py::test_claims_do_not_overstate_validation` 一致，另加 A26 的定位要求）：
  - “globally optimal CEM”；
  - “exact reproduction … passed/proven”；
  - “public release decision is GO”；
  - “smoke test proves annual economics”；
  - “网站方法学对标论文 / 与论文一致 / 复现论文”及其英文说法（“aligned with the thesis”“reproduces the thesis”）。

### 2.11 版本与下载文案

- **0.7.0 安装包构建、验证、上传到 GitHub Releases 之前：**
  - 网站下载区仍然只列 `2026-10-03-rc1`，但要写明它是 **VALUE 0.6.0-alpha.2**，不含 2026 年 10 月的审查修正；
  - 网站任何地方都不写“0.7.0 可下载”；
  - 源码推送之后（阶段 1），可以写“0.7.0-alpha.1 的源码已公开，安装包尚未构建”。
- **0.7.0 Full 包可用之后：** 按 `site.json` 现有的结构新增 release 条目，并按 2.7、2.8 节更新安装说明和常见问题。

### 2.12 界面字符串（翻新前的现状，翻新后要逐条重新核对）

下表是代码状态 `6014421` 的应用界面（`app/`）中，网站步骤和常见问题可能引用的英文字符串，网站照抄。这些字符串多数还没有写进 `CHANGELOG.md` 和用户指南（第 7 节第 7 条），前端整体翻新还会改界面。阶段 2 之前，网站只在“新版本有哪些变化”中概括一句，不逐条引用。

| 位置 | 字符串（英文原文） |
|---|---|
| Study composer | 第 1 步 `1. Study identity` 中的 `Methodology` 单选框：`Corrected (default)`、`Doctoral reproduction`（附说明 `Locks thesis-era reference settings: …`）；数据包和计算域不符合所选口径时标为 `not available with this methodology` |
| Study 迁移对话框 | `This Study needs your confirmation before it runs`；按钮 `Review and save as new revision` |
| Runs：What will run | `Years`、`Data pack`、`Methodology`（短名）、`Annual sequence` |
| Runs：范围与预检 | 一日选项 `One-day market lesson`，Study 选了扩展时为 `One-day market lesson (extensions do not run)`；阻断原因 `The one-day lesson runs the market step only, so the selected extension(s) {names} would not execute. Choose two-period or a longer scope, or deselect the extension(s).`；起止年份相同的 Study 不列出两年范围；Readiness 卡片按组列出：`Errors`（始终展开）、`Data plausibility`（默认展开）、`Chronology`、`Other data warnings`、`Adapter: unit not declared`、`Environment and setup`（默认折叠，按钮 `Show {n}`）；预检有错误时，物理预览徽章为 `inputs ready · Run blocked` |
| Runs：启动与准备 | `Preparing · step {i} of 4: {阶段} · {用时} elapsed`；四个阶段名见 2.8 节；`Request safe cancellation`；取消后进度句末尾加 `Cancellation requested: the Run stops before its model worker starts.`；中断时为 `Run preparation interrupted`；首次估算 `estimated {a} to {b} (no comparable completed Run yet)` |
| 年度卡片 | `Unserved demand`（旁注 `incl. stress shortfall · {x} MWh recorded by the PSM`）；`Unused VRE (PSM boundary)`（`{x} MWh · {y}% of available`）；`Planning evolution`：`Active before admission: {n}`、`Admitted this year: {m}` |
| 结果与上下文条 | `Withheld`；`Annual results withheld for this reproduction run`；`Annual results pending the raw-invariant check`；`Raw invariants`（`● Passed` / `● {k} failed` / `Pending`）；`Open in Inspect`；`Open ledger files`；`Annual results not published`；`Validation gate failed: {gates}`；`Stress events`；`Shortfall`；`Methodology not recorded (pre-2026-10 run)`；`Experimental extension: {id} {version}` |
| Market replay | 窗口行末尾 `(UTC model time)`；stress 事件表表头 `Start (model date & time, UTC)` |
| Data 页校验面板 | `Validation`（`Structural` / `Chronology` / `Plausibility`）；`Methodology use`（`Corrected` / `Doctoral reproduction`，状态为 `Eligible` 或 `Not eligible — {原因}`，例如 `Not eligible — not a thesis-era pack`）；`Show details ▾`；数据包摘要 `{n}/{m} inputs present · validation {最差状态}` |
| Data 页数据角色 | `{Country} interconnector availability (+ import / - export)` |
| `Research guide` 换数据路径 | VALUE 101 需求文件的角色卡和映射编辑器中的单位说明（中文：“单位：按 MW 读取（每半小时平均功率）……映射中请选择 MW。”） |
| 映射编辑器 | `Timestamp column (optional)`：`Timestamp column`、`Time zone`（UTC / Europe/London）、`Date order`（`Auto-detect (DD/MM/YYYY unless a row shows MM/DD/YYYY)` / `DD/MM/YYYY (day first)` / `MM/DD/YYYY (month first)`）；`Column name suggests EUR — confirm the currency.`。编辑器的说明文字目前是中文，翻新时统一界面语言 |
| Modules 页 | 计数徽章 `{n} of {m} ready · {k} experimental`；`Disabled and quarantined` 区，每项 `Enable`、`Rescan`、`Remove`；页头 `Rescan modules`。Remove 前先确认：文件移到 `modules/disabled-manifests/removed/`，不删除；仍被 Study 或 Run 引用时拒绝。Enable 失败后提示 `Fix the cause, then press Enable again (Enable scans afresh; Rescan alone leaves a disabled entry disabled).`；原地改过源码的卡片写 `Source changed since install ({old8}… → {new8}…).` |
| 预检（原地改模块源码） | `Module {id} source changed since install ({old8}… → {new8}…). Results will record the new source hash.`；模块已被隔离时，后一句为 `It is quarantined, so no Run can start; once it is repaired, results record the new source hash.` |
| 预检（原地改扩展钩子源码） | `Extension {id} source {implementation} changed since install ({old8}… → {new8}…). Results may change; the Run records the new source hash.`；扩展停用后修好再 Enable 成功时提示 `{id} is enabled. Check readiness again before running a Study that uses it.` |
| Modules 页（有 Run 未结束时更改模块或扩展） | 确认框：`Runs have not finished: {n} run(s) not started yet ({ids}) will not start: the change alters the code they recorded, so VALUE stops them with GF_RUN_EXECUTION_IDENTITY_CHANGED and you resubmit them from the Runs page (Resubmit with current code); {n} run(s) already running ({ids}) keep their code but could not be resumed after the change. Confirm to change installed modules anyway.`（只出现适用的分句；改扩展时末尾为 `extensions`）；服务器当场停下了 Run 时，成功提示后追加 `{n} Run(s) that had not started was/were stopped because the installed code changed (GF_RUN_EXECUTION_IDENTITY_CHANGED): {ids}. Resubmit it/them with the current code from the Runs page.` |
| Runs 页（失败的 Run） | 错误框 `{error_code}: {说明}`，契约类和执行身份类失败在下一行显示诊断首行；`GF_RUN_EXECUTION_IDENTITY_CHANGED` 的说明为 `The installed modules, extensions or VALUE code changed after this Run was queued, so it did not start. Resubmit it to run with the current code.`，下方按钮 `Resubmit with current code`；`GF_EXTENSION_OUTPUT_REJECTED` 的说明为 `An extension hook returned an output that VALUE does not accept; the detail below names the extension, the hook and the rule.` |
| 比较页 | `Identity check before comparison`，每个维度标为 `Same` / `Changed` / `Cannot verify`；年度表上方 `Deltas (+ and %) are measured against {Study} ({run id}), the first Run ticked. To measure against another Run, clear the selection and tick that Run first.`；年度差值按指标分别显示，被扣发的指标写 `Delta withheld: {reason}`，年份列表上方有 `Deltas withheld` 提示；新指标名见 2.6 节 |
| 页头 | `{n} of {m} base inputs ready`；工作区读不到时为 `Inputs not loaded` |
| 任意页面 | `Open VALUE from its launcher` |
| advisory 标题（举例） | `Produced before the 2026-10 review fixes`；`Biomass without support revenue` |

---

## 3 分阶段发布门槛

| 阶段 | 门槛（全部满足，并经作者同意） | 网站可以上线什么 |
|---|---|---|
| **0 纠错** | 作者同意文案，并决定是否在前端翻新之前上线（第 7 节第 2 条） | 只限纠错与提示：rc1 的版本标注；把旧证据标为 0.6.0-alpha.2 的证据；作者批准后，可加 rc1 的安全提示（第 7 节第 1 条）。**不出现 0.7.0 的功能描述** |
| **1 源码公开** | 前端整体翻新完成（A17、A21）；第 7 节第 7 条的公开文档已同步；作者把 0.7.0-alpha.1 推送到 `hanzohanzhe/Value`，并打出源码 tag（tag 名由作者定）。推送的版本包含翻新的改动，所以上线前要按推送时的 `CHANGELOG.md` 和界面，重新核对第 2 节与附录 A | 网站方法学定位与两个口径的介绍、声明范围、验证页新增行、引用页的新源码条目、Develop 页的源码链接；作者同意时加 GBP1 勘误。截图（如有）只用翻新后的界面 |
| **2 安装包可用** | 0.7.0 Full 安装包已构建（`scripts/prepare_private_runtimes.py`、`scripts/build_full_desktop_installers.py`，每一步都要作者批准），已在目标平台验收，并上传到 GitHub Releases，有确定的文件名、字节数和 SHA256；`FOUR_ROLE_TEST_REPORT.md` 没有未关闭的高等缺陷，或作者决定在步骤中写明规避方法 | `site.json` 的 release 条目、下载页、安装页（启动器、升级、常见问题）、四类用户路径的新步骤、数据页的口径资格说明 |
| **3 方法学 0.4** | methodology 修改员完成 0.4 版次（源稿在 `docs/methodology/drafts/0.4/`），作者审阅通过；六个文档（中英文 × docx/pdf/html）有获批的哈希 | 用 `website/sync_methodology.py` 整体导入 0.4，同时更新 `publication-scope.json` 和 `site.json` 的版次字段 |

阶段 2 的四类用户步骤只适用于 0.7.0。**在阶段 2 之前更新这些步骤，会误导仍在使用 rc1（0.6.0）的用户。**

---

## 4 逐文件修改清单

- 表中“现文”是当前源码中的字符串，较长的只摘关键片段；“要求”说明应改成什么。
- 中英两种语言都要改：`t(en, zh)` 的两个参数都要动。
- 行号对应本分支，也对应 35aadb3。

**哪些代码段会出现在网站上**（`publication.py:2-27`）：

- `publication.pages()` 总是先调用 `data_pages()`。所以 data 页**始终**由 `publication.py` 生成（`:27`）；“Clean source snapshot” 注释**始终**追加到 about 和 docs 两页（`:26`）。`content.py:64-68` 的 data 页内容在任何情况下都不会出现。
- `publication_ready` 为 `true` 时（现状），`publication.py` 还会：
  - 用自己的下载页替换 `releases` 和 `release-check` 两个路由（`:14`）；
  - 用 `ready_copy()`（`:29-32`）整句替换其他页面中的“pending”句子。
- 所以 `content.py:49-63`（releases）和 `release_candidate.py` 全文目前都不会出现在网站上。下载区和数据页的文案要改 `publication.py` 和 `site.json`。

### 4.1 `website/site.json`

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| S-1 | `products[0].releases[*]`（4 条，`version: "2026-10-03-rc1"`），以及 `planned_release_assets` | rc1 四个平台的条目；`requirements: "Bundled Python and Node; see platform installation guide"` | **阶段 0**：条目不动。如需标版本，在 `requirements` 后补 “ · VALUE 0.6.0-alpha.2”（`check_site.py` 只要求该字段非空）。**阶段 2**：为 0.7.0 新增条目，字段与现有条目相同：`version`、`platform`、`date`、`size`、`bytes`、`requirements`、`url`（必须 https）、`sha256`（64 位十六进制）、`filename`、`native_acceptance`（只有该平台实机验收通过时才填 `true`）。新条目的值一律取自实际上传的文件，**不要预填** | 0 / 2 |
| S-2 | `candidate_release_id`、`package_evidence_date` | `"2026-10-03-rc1"`、`"2026-10-03"` | 改为新安装包的 id 和日期 | 2 |
| S-3 | `source_tag`、`source_validation` | `"source-2026-10-04"`；`historical_scientific_replay: false` 等 | 改为作者打出的新 tag；`source_validation` 只填对新 tag 实际做过的检查 | 1 |
| S-4 | `evidence_date`、`methodology_edition`、`methodology_revision_date` | `"2026-10-02"`、`"0.3"`、`"2026-10-04"` | **只在阶段 3 改**，并与 `publication-scope.json` 的 `scientific_basis_date`、`edition`、`revision_date` 同步。`scripts/check_publication_scope.py` 会逐项比较两边，单独改一边就会失败。`sync_methodology.py` 会自动写入 `site.json` 的这三项 | 3 |
| S-5 | `data_assets` 中 `value-uk-open-data-pack-v1-public1-…zip` 的 `interface` | “Import through national Data UI/API; preserve runtime pack ID value-uk-open-data-pack-v1.” | 补一句。英文：“In VALUE 0.7.0-alpha.1 this pack is eligible for the doctoral reproduction profile only; the corrected (default) profile does not accept it. Both profiles read its Belgium price as hourly EUR at 1.1 EUR/GBP, its BE/NL flows by line identity and its demand on the UTC clock.” 中文：“在 VALUE 0.7.0-alpha.1 中，此包只能用于论文复现口径，修正口径（默认）不接受；两个口径都把比利时电价按逐小时 EUR、1.1 EUR/GBP 读取，BE/NL 潮流按线路身份读取，需求按 UTC 时钟读取。” | 2 |
| S-6 | `data_assets` 中 `value-uk-calendar-vx-trade001-public1-…zip`（R029）的 `interface` | “… Doctoral frozen replay is unsupported on the current Full; no failed doctoral Study template is provided.” | 把 “current Full” 写明为 “Full 2026-10-03-rc1 (VALUE 0.6.0-alpha.2)” / “Full 2026-10-03-rc1（VALUE 0.6.0-alpha.2）”。再补一句。英文：“In VALUE 0.7.0-alpha.1 this pack is not a doctoral reproduction pack, and the corrected profile refuses it when a Run reads its hourly solar profile (8,761 values).” 中文：“在 VALUE 0.7.0-alpha.1 中，此包不属于论文复现口径的数据包；修正口径在 Run 读取其逐时光伏曲线（8,761 个值）时拒绝它。” **不要写“可用于修正口径”**（2.10 节）。若作者决定发布 R029 public2，按 S-9 另立条目 | 2 |
| S-7 | `data_assets` 中三条网络相关条目：`11-zone overlay family`、`GBP1 + 23-zone suite`、`23-zone network overlay` | — | 补一句。英文：“In VALUE 0.7.0-alpha.1 the network modules run only under the corrected (default) methodology profile.” 中文：“在 VALUE 0.7.0-alpha.1 中，网络模块只在修正口径（默认）下运行。” 不要写这些套件已在 0.7.0 上跑通（2.10 节） | 2 |
| S-8 | `methodology_release_assets` | 指向 `methodology-0.3-2026-10-04` | 导入 0.4 时再改 | 3 |
| S-9 | `data_assets`（新增） | — | **只有作者决定发布** GBP1 public2 或 R029 public2 时才新增（第 7 节第 8 条）。字段与现有条目相同，值一律取自实际上传的文件 | 视作者决定 |

### 4.2 `website/content.py`

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| C-1 | `:29` 表格 “Configurations are part of the method” 之后（`models/value` 页） | — | 新增一节 “Two methodology profiles / 两种方法学口径”：先用一段话写明网站方法学描述的是默认的修正口径（2.1 节），再用 `table()` 列出两个口径，三列为标签（英文原文）、含义、边界。文案见附录 A.1，固定附注必须出现 | 1 |
| C-2 | `:30` note “Read the evidence with its scope” | “The 2025–2034 national baseline completed 175,200 half-hour periods and repeated settlement hashes in engineering checks. …” | **阶段 0**：句首补版本。英文 “In VALUE 0.6.0-alpha.2 (before the October 2026 review fixes), the 2025–2034 national baseline …”；中文 “在 VALUE 0.6.0-alpha.2（2026 年 10 月审查修正之前）中，2025–2034 全国基线……”。**阶段 1**：再补一句。英文 “It has not been re-run under 0.7.0-alpha.1, where such pre-fix runs are marked `superseded_pre_fix`.”；中文 “该基线未在 0.7.0-alpha.1 上重跑；0.7.0 把修正之前的运行标为 `superseded_pre_fix`。” | 0 / 1 |
| C-3 | `:33` `study_data` 中 national-baseline 的状态 | `t('Engineering checks completed', '基线工程检查已完成')` | 改为 `'Engineering checks completed · 0.6.0-alpha.2'` / `'基线工程检查已完成 · 0.6.0-alpha.2'` | 0 |
| C-4 | `:41` `study_page` 的标签 | `'Evidence snapshot · 2 October 2026'` | 保留日期，表明这是快照。有新证据时才改日期，而且只改有新证据的案例 | 1 |
| C-5 | `:46` VALUE 101 复现步骤第 3、4 条 | “Create or open the teaching Study, confirm its 48 periods and explicitly start a Run.” / “Inspect the result tables and compare against the reference bundled with that exact release.” | 第 3 条改为 “Create or open the teaching Study, choose its methodology profile, confirm its 48 periods and explicitly start a Run.” / “创建或打开教学 Study，选择方法学口径，确认 48 个时段，再显式启动 Run。”；第 4 条改为 “Inspect the result tables and compare against the reference of the same release and methodology profile.” / “查看结果表，并与同一版本、同一口径的参考结果比较。” | 2 |
| C-6 | `:47` national-baseline 的 “Engineering evidence” 表和 “Use the evidence correctly” 段 | 表中三行：时间覆盖、复跑哈希一致、解释范围 | **阶段 0**：表中新增一行 “Software version / 软件版本”，内容为 “0.6.0-alpha.2 (before the October 2026 review fixes) / 0.6.0-alpha.2（2026 年 10 月审查修正之前）”。**阶段 1**：“Use the evidence correctly” 段补一句。英文 “These checks were made with VALUE 0.6.0-alpha.2, which did not record supply shortfalls (stress events) and predates the corrections of VALUE 0.7.0-alpha.1; the baseline has not been re-run.”；中文 “这些检查用 VALUE 0.6.0-alpha.2 完成：该版本不记录供给不足的时段（stress event），也早于 VALUE 0.7.0-alpha.1 的各项修正；该基线没有重跑。” | 0 / 1 |
| C-7 | `:48` gb-zonal 案例的 “Interpretation boundary” 段 | “The case is not an AC power-flow calculation or an N−1 security assessment. …” | 补一句。英文 “In VALUE 0.7.0-alpha.1 the network modules run only under the corrected (default) methodology profile, with zonal solver contract v4. Network cost and redispatch curtailment recorded by earlier versions must not support research conclusions.”；中文 “在 VALUE 0.7.0-alpha.1 中，网络模块只在修正口径（默认）下运行，使用 zonal solver contract v4；更早版本记录的网络成本和再调度弃电量不能作为研究结论的依据。” | 1 |
| C-8 | `:69` validation 表第 1 行（national baseline） | “2025–2034 completed; 175,200 half-hours; rerun settlement hashes identical.” | 在 “VALUE national baseline” 后补 “(0.6.0-alpha.2)” / “（0.6.0-alpha.2）”；边界列补 “Pre-fix evidence; not re-run under 0.7.0-alpha.1.” / “修正之前的证据，未在 0.7.0-alpha.1 上重跑。” | 0 |
| C-9 | `:69` validation 表第 2 行（four user paths） | “Four specified tasks passed after fixes on 2 October 2026. …” | **阶段 0**：补 “on Full 2026-10-03-rc1 (0.6.0-alpha.2)” / “基于 Full 2026-10-03-rc1（0.6.0-alpha.2）”。**阶段 1**：**另起一行**写 0.7.0 源码上的结论（附录 A.2 第 8 行，必须写明“源码树、非安装包”，并受 2.9 节的上线条件约束）。**阶段 2**：在安装包上重测之后，再写安装包的结论。原行保留 | 0 / 1 / 2 |
| C-10 | `:69` validation 表第 3 行（GB zonal） | “Longer-horizon validation in progress in the source snapshot.” | 边界列补 “Network modules run only under the corrected profile in 0.7.0-alpha.1.” / “0.7.0-alpha.1 中网络模块只在修正口径下运行。” | 1 |
| C-11 | `:69` validation 表（新增行） | — | 按附录 A.2 新增八行，不得超出 2.10 节的范围 | 1 |
| C-12 | `:70` note “Evidence snapshot · 2 October 2026” | 标题和正文 | 有新增行时，把标题日期改为新证据的日期，正文不变 | 1 |
| C-13 | `:74` `bib`、`:80` 历史元数据段 | `version = {0.6.0-alpha.2}` 等 | **不改**（历史记录，受版本一致性测试保护） | — |
| C-14 | `:76` cite 页 “VALUE · source-2026-10-04” 一节 | 链接 `/assets/value-source-review-CITATION.cff` | 在其上方新增一节 “VALUE · <新源码 tag>”，引用文件取仓库根目录的 `CITATION.cff`。该文件目前仍是 `version: "source-2026-10-04"`，要由作者在推送前更新（第 7 节第 4 条）。原节保留。另见第 9 节第 2 条 | 1 |
| C-15 | `:79` cite 页 rc1 一节 | “Current full-installation candidate. …” | **阶段 0**：补 “It contains VALUE 0.6.0-alpha.2.” / “其中的应用版本为 VALUE 0.6.0-alpha.2。”。**阶段 2**：把 “Current” 改为 “Earlier”，并新增 0.7.0 安装包的引用条目；新文件放在 `static/assets/release-candidate/` 的新子目录或新文件名下，不覆盖旧文件 | 0 / 2 |
| C-16 | `:93-97` 各页的 “Versioned methodology” 一节 | “Read the audited equations, numerical parameters, pseudocode and initial dataset identities. …” | **阶段 1**：补一句。英文 “Methodology edition 0.3 describes VALUE 0.6.0-alpha.2. The methodology describes the VALUE model published here; the changes of VALUE 0.7.0-alpha.1 are listed in the CHANGELOG until edition 0.4 is reviewed.”；中文 “方法学 0.3 版次描述 VALUE 0.6.0-alpha.2。方法学描述的是本网站发布的 VALUE 模型；VALUE 0.7.0-alpha.1 的改动，在 0.4 版次审阅之前以 CHANGELOG 为准。”。**阶段 3**：删去这句 | 1 / 3 |
| C-17 | `:87` about 页 “Historical archive” 注释 | “The SCHEME-C PhD reproduction repository is an earlier research archive, not the source or download location of the current VALUE application. …” | **不改**。它与 A26 的定位一致（2.1 节） | — |

### 4.3 `website/journey.py`

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| J-1 | `:2-6` `ROLES` 的说明文字（第 3、4 列） | 复现：“Run VALUE 101 and compare the matching reference.” / “运行 VALUE 101，对照同版参考结果。”；改模块：“Change a supported module and compare its results with the baseline.”；加功能：“Define inputs and outputs, add an extension, and run a small example.” | 复现改为 “Choose a methodology profile, run VALUE 101 and compare the reference of the same version and profile.” / “选择方法学口径，运行 VALUE 101，对照同版本、同口径的参考结果。”；改模块改为 “Change a supported module under the corrected profile and compare its results with the baseline.” / “在修正口径下修改支持的模块，与基线结果比较。”；加功能改为 “Define inputs and outputs, add an extension and run a small example of two periods or longer under the corrected profile.” / “定义输入输出，接入扩展，在修正口径下运行两时段或更长的小型示例。”。第 2 列的标签见第 9 节第 1 条 | 2 |
| J-2 | `:20` 首页 Install 卡 | `'Full candidates are available. Check platform validation before starting.'`（`publication_ready` 时生效） | 改为 “Full 2026-10-03-rc1 (VALUE 0.6.0-alpha.2) is available. Check platform validation before starting.” / “Full 2026-10-03-rc1（VALUE 0.6.0-alpha.2）可下载；开始前查看平台验收状态。”。`:50` 的 `replacements` 字典中也有这两句，作为“pending”句的替换值，要同步改 | 0 / 2 |
| J-3 | `:29-34` `instructions` / `chinese` 四组步骤 | 见源码 | 按附录 A.3 改写。中英两组列表的条数必须一致，因为 `zip` 逐条配对 | 2 |
| J-4 | `:40` Develop 页的源码链接 | `https://github.com/hanzohanzhe/Value/tree/source-2026-10-04` | 改为新 tag；可以保留旧 tag 作为第二个链接 | 1 |
| J-5 | `:43` Install 页步骤与 note | 第 3 步 “Run the platform installer, launch VALUE, and keep its terminal open.”；第 4 步 “Open the local address printed by the launcher; start with VALUE 101.”；note “Public downloads remain pending. Linux candidate offline installation …” | 第 3 步改为 “Run the platform installer into a directory that does not exist or is empty, launch VALUE, and keep its terminal open.” / “运行安装器，安装到不存在或为空的目录，启动 VALUE，并保持终端打开。”；第 4 步补 “(http://127.0.0.1:8800 or http://localhost:8800)”；新增第 5 步 “To upgrade, finish or cancel unfinished Runs, then install the new version into another empty directory; do not move or rename an installed directory.” / “升级时先完成或取消未结束的 Run，再把新版本装进另一个空目录；不要移动或重命名已安装的目录。”。代码框中的 `"$HOME/VALUE-full"` 不必改 | 2 |
| J-6 | `:45` note “Included environment” 之后 | — | 新增一条 note：“One user per computer. Do not install VALUE on shared computers or remote-desktop servers.” / “一台电脑一个使用者，不要安装在共用电脑或远程桌面服务器上。”（Q11、`SECURITY.md` “Single-user host assumption”） | 2 |
| J-7 | `:47` 常见问题 | 三问：页面打不开 / 输入校验失败 / 如何停止 | (a) “如何停止”的答案按附录 A.4 第 1 条改写；(b) “输入校验失败”的答案按附录 A.4 第 2 条改写；(c) 新增附录 A.4 第 3–9 条七问 | 2 |
| J-8 | `:50` `replacements` | 按整句替换的字典 | 每改一次 `:20`、`:42` 或 `:43` 中被替换的句子，都要同步改这里的键和值。改完构建后，用 `grep` 检查 `dist/` 中是否残留 “pending” 句子（第 8 节第 6 步） | 0 / 2 |

### 4.4 `website/publication.py`（决定下载页和数据页）

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| P-1 | `:7`、`:10` 平台状态 | “Linux offline installation and scoped tasks passed.” / “Experimental candidate; …” | 阶段 0 不动。阶段 2 让状态文字带版本，可以从新增的 `release['version']` 读取 | 2 |
| P-2 | `:12` 下载页的 heading 与 note | `w.heading('VALUE / 2026-10-03-rc1', …)`；note “Full includes Python, Node and dependencies. These installer candidates have their own source identity; …” | **阶段 0**：在 note 中补 “2026-10-03-rc1 contains VALUE 0.6.0-alpha.2 and predates the October 2026 review fixes.” / “2026-10-03-rc1 的应用版本为 VALUE 0.6.0-alpha.2，早于 2026 年 10 月的审查修正。”。若作者批准安全提示，在这里加第二条 note（附录 A.5）。**阶段 2**：heading 中的批次名改为从 `site.json` 的 `candidate_release_id` 读取，不再写死；新增 0.7.0 卡片，旧 rc1 卡片可以保留，并标为 “Earlier candidate” | 0 / 2 |
| P-3 | `:22` 数据页 note “Execution scope” | “The final GBP1 pack … initializes five nuclear stations totalling 5,958 MW. A two-period run passed …” | 补 “(checked on Full 2026-10-03-rc1, VALUE 0.6.0-alpha.2)” / “（在 Full 2026-10-03-rc1、VALUE 0.6.0-alpha.2 上检查）” | 0 |
| P-4 | `:23` 数据页 note “Research boundaries” | “R029 provides inputs compatible with the ordinary VALUE chain; doctoral initialization/investment eligibility currently fails on Full, so frozen doctoral replay is not offered. …” | **阶段 0**：原句对 rc1 仍然成立，保留，只在 “on Full” 后补 “2026-10-03-rc1”。**阶段 2**：改写为 0.7.0 的边界。英文：“In VALUE 0.7.0-alpha.1 the doctoral reproduction profile accepts GBP1 public1. R029 and the 11-zone and 23-zone suites are not doctoral reproduction packs, and the network modules run only under the corrected profile. The released GBP1 public1 and R029 public1 packs are not usable with the corrected profile.” 中文：“在 VALUE 0.7.0-alpha.1 中，论文复现口径接受 GBP1 public1；R029 与 11 区、23 区套件不属于论文复现口径的数据包，网络模块只在修正口径下运行；发布版 GBP1 public1 与 R029 public1 不能用于修正口径。” | 0 / 2 |
| P-5 | `:25` “Clean source snapshot” note（追加到 about 和 docs 两页，`:26`） | “source-2026-10-04 passed clean installation, frontend build, …” | 新增一条关于新源码 tag 的 note，只写对该 tag 实际做过的检查；旧 note 保留 | 1 |
| P-6 | `:30` `ready_copy` 的替换表 | 键值对 | 改动 `content.py:46`、`:79`、`:87`、`:88` 中被替换的原句时，同步改这里 | 0 / 2 |
| P-7 | 数据页新增内容 | — | 若作者同意公开 GBP1 勘误（第 7 节第 3 条），在数据页加一条 note，写明 0.6.0-alpha.2 及更早版本在 GBP1 public1 上的问题和一年对比的方向。数字只能取自已公开的文档（见第 7 节第 3 条），**不上传** `docs/dev/` 下的任何报告 | 1 |

### 4.5 `website/methodology_page.py`

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| M-1 | `:17` heading lead | “Mathematical formulation, algorithms and input data for system operation, annual investment, transmission.” | 不改 | — |
| M-2 | `:23`（methodology-intro 的修订日期行）之后 | — | 新增一条 `w.note`。英文：“Edition 0.3 describes VALUE 0.6.0-alpha.2. This methodology describes the VALUE model published here, which is the corrected (default) profile from VALUE 0.7.0-alpha.1; until edition 0.4 is reviewed, the changes are listed in the CHANGELOG.” 中文：“0.3 版次描述 VALUE 0.6.0-alpha.2。本方法学描述本网站发布的 VALUE 模型，自 VALUE 0.7.0-alpha.1 起即修正口径（默认）；0.4 版次审阅之前，改动以 CHANGELOG 为准。”。阶段 3 导入 0.4 时删去 | 1 / 3 |
| M-3 | `website/methodology/*.json`、`static/assets/methodology/*` | 0.3 版次 | **不要手改**，包括其中关于论文口径的措辞。只能通过 `sync_methodology.py --source ../docs/methodology --build <渲染目录> --documents <六个文件所在目录>` 整体替换；`docs/methodology/edition.json` 和 `artifacts.json` 要先由 methodology 修改员按 0.4 更新 | 3 |

### 4.6 `website/release_candidate.py`、`website/build.py`、`website/README.md`、`website/UPLOAD-FILES.txt`

| 编号 | 位置 | 现文 | 要求 | 阶段 |
|---|---|---|---|---|
| R-1 | `release_candidate.py:5-8` | “The 2026-10-03-rc1 candidate is an internal review artifact. …” | `publication_ready: true` 时不显示。只有作者决定撤下 rc1（把 `publication_ready` 改为 `false`）时才需要改，那时补 “VALUE 0.6.0-alpha.2” 和撤下原因 | 视第 7 节第 1 条 |
| B-1 | `build.py:44-51` 导航（`nav`）与页脚（`footer`） | — | 不需要改。若新增页面，路由加在 `content.py` 的 `add(...)` 中，中英文都会生成；`check_site.py` 会检查每个页面都有对应译文 | — |
| D-1 | `website/README.md:12`、`:26` | “Full installer downloads remain pending. …”；“The reviewed 0.3 edition dated 2026-10-04 …” | 阶段 2 更新下载状态，阶段 3 更新版次。README 不发布到网站，但属于源码发布清单 | 2 / 3 |
| U-1 | `website/UPLOAD-FILES.txt` | 上传文件清单（1,210 行） | 在 `static/` 下新增或删除文件时（例如新的 release-candidate 引用文件、0.4 方法学文档）同步更新 | 2 / 3 |

改动 `website/` 下的任何源文件之后，都要刷新仓库根目录的 `source-release-manifest.json`（第 8 节第 4、8 步）。

---

## 5 事实来源（网站文案只能从这里取）

| 内容 | 路径 |
|---|---|
| 所有决策（最高依据） | `docs/dev/P0_DECISIONS.md`（内部，不发布）。同一事项有多条时，以编号靠后的为准 |
| 版本变化、correction id、迁移说明、API 变化、已知问题 | `CHANGELOG.md` 的 “0.7.0-alpha.1” 一节。其中的 “Two methodology profiles”“Correction ids”“Migration notes”“API contract changes” 描述现行规则；按施工步骤写成的各小节，有些句子只描述该步骤当时的状态，网站文案以本文第 2 节为准（另见第 7 节第 7 条） |
| 口径、修正 id、白名单、advisory | `docs/generated/METHODOLOGY_PROFILES.md`（由 `gridform_core/data/methodology/` 生成，不要手改） |
| 声明范围与证据 | `docs/VALIDATION_AND_CLAIMS.md`（含 “Scope of the 0.7.0-alpha.1 claims”）；`docs/SCHEME_C_MODEL_CARD.md`。上线前须先同步（第 7 节第 7 条） |
| golden 变化 | `docs/release/P0_GOLDEN_DELTA.md`（生成文件，与代码一致）；`tests/golden/reports/` 的数值报告 |
| 验收与重装步骤 | `docs/release/P0_ACCEPTANCE.md`（第 6 节的重装**未执行**） |
| 版本号 | `docs/release/VERSION_LEDGER.json`、`package.json`、`pyproject.toml` |
| 用户可见行为（标签、状态词、启动器、常见问题） | `docs/USER_GUIDE.md`、`docs/USER_GUIDE_ZH.md`（第 2、12、13、19 节）；`docs/MODULE_DEVELOPER_101.md`（扩展钩子输出的记录范围、扩展原地改源的规则）；`SECURITY.md`；随安装包分发的各平台说明（`packaging/full-local/linux/README-LINUX.md`、`packaging/full-local/windows/README-WINDOWS.md`、`packaging/desktop-local/macos/README-MACOS.md`） |
| 界面字符串（在 CHANGELOG 和用户指南补齐之前） | 应用源码 `app/features/`；设计规格 `docs/dev/P0_FRONTEND_DESIGN_SPEC.md` 与 `docs/dev/P0_FRONTEND_DEVIATIONS.md`（内部，只用来核对）。前端翻新会再改这些字符串 |
| 模型设定改动（作者简报，可作背景） | `docs/handoff/MODEL_CHANGES_BRIEF.md`（内部，不发布） |
| GBP1 论文复现口径的数值 | golden D5 的数值报告（`tests/golden/reports/D5-*.json`）；`docs/dev/p0-reports/r41-golden/` 的摘要（内部） |
| GBP1 修正口径本地验收 | `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md`（内部；作者要求不发布） |
| 参考统计（核电、水电、风光损耗、火电重启成本） | `docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md`（内部；各节已由作者审核，A14、A21、A22） |
| 方法学 0.4 源稿 | `docs/methodology/drafts/0.4/*.md`（未审阅，发布时排除） |
| methodology 修改员的交接 | `docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md`（worktree 根目录副本 `VALUE_handoff_methodology_editor_2026-10-04.md`） |
| 0.7.0 四角色测试 | `docs/handoff/FOUR_ROLE_TEST_REPORT.md`（worktree 根目录副本 `VALUE_four_role_test_report_2026-10-04.md`；内部，不发布）；各角色完整走查的原始报告 `docs/dev/p0-reports/final-role-*.md`，修复与定向验证的记录也在 `docs/dev/p0-reports/` |

---

## 6 现在不得上传或不得写的内容

1. **0.7.0 安装包与下载链接。** 安装包没有构建。`site.json` 中不能出现 0.7.0 条目，也不能出现猜测的 URL、大小或 SHA256。
2. **“已升级”“已重装”之类的表述。** 作者本机的安装仍是 0.6.0-alpha.2。重装（`P0_ACCEPTANCE.md` 第 6 节）每一步都要作者批准，目前没有执行。
3. **把网站方法学写成论文方法学的表述。** 见 2.1 节：不写“对标论文”“与论文一致”“复现论文”。论文复现口径只作为兼容口径介绍。
4. **参考统计表本身。**
   - 它是内部文档，**不上传，也不整表引用**；
   - 网站可以写“取值来自公开统计与文献，经作者审核”；**不得**写“已校准”或“与 DUKES 一致”。原因：风光损耗系数是文献取值，容量因子只与 DUKES 并列披露（A9）；重启成本是文献与平衡机制数据的换算值，不是机组实测。
5. **内部文档。** `docs/dev/`、`docs/handoff/`（包括本文）、`docs/methodology/drafts/` 和 worktree 根目录的 `VALUE_*.md`，既不进入网站，也不进入公开源码：前三个目录列在 `tests/baselines/release-exclusions.txt` 中，根目录副本不入库。
6. **GBP1 public2 与 R029 public2。**
   - 这两个包只在本地构建，没有发布。它们在代码中登记为 `scientific_reference`，是为了让本地构建的包能按修正口径运行，**不等于发布**；
   - 作者决定发布之前，不得列入 `data_assets`，也不得引用它们的任何运行数字（2.10 节）。
7. **方法学 0.4 草稿。** 不得导入 `website/methodology/`，也不得作为下载提供。
8. **翻新前的界面截图。** `docs/dev/p0-ui-screens/` 中的截图是内部验收记录，界面在前端翻新后会改变。网站上的截图只从翻新后的界面拍。
9. **超出声明范围的说法。** 见 2.10 节的禁用措辞，以及“与 DUKES 一致”“精确复现论文”“修正口径已在 GBP1 上验证”“R029 可用于修正口径”“经济下调顺序已在 GB 系统上验证”“stress 缺口按 VoLL 计入成本”“两个口径的弃电量之差”。
10. **声明偏差的编号。** 网站不列任何声明偏差编号；它们只出现在内部文档和 Run 的证据中。
11. **安全漏洞细节。** 审查报告中的复现步骤（请求头、端点、DNS rebinding 的做法）**不得**写到网站上。是否发安全提示、措辞如何，由作者决定（第 7 节第 1 条）。

---

## 7 需要作者决定的事项（上传员不要自行决定）

1. **rc1 的安全提示或下架。**
   - 背景：rc1（0.6.0-alpha.2）的本地 API 没有 Host、Origin、会话和 Content-Type 校验（审查报告 F5-01，critical）。0.7.0-alpha.1 已解决这个问题；DECISIONS D0-4 也记录了现有安装仍有此问题。
   - 可选做法：
     - (a) 在下载页和安装页加一条中性提示，不写利用细节（草稿见附录 A.5）；
     - (b) 把 `publication_ready` 改为 `false`，暂时撤下 rc1 下载，等 0.7.0 安装包可用后再上线；
     - (c) 维持现状。
   - 本文不替作者选择。
2. **阶段 0 能否在前端翻新之前上线。** A21 规定网站的上传和发布等翻新之后。阶段 0 只纠正 rc1 的版本标注，并可能加安全提示，与 0.7.0 的内容无关。是否例外先上线，由作者决定。
3. **GBP1 勘误是否公开，写在哪一页。**
   - 内容：0.6.0-alpha.2（rc1）在 GBP1 public1 上运行时，没有 2.3 节的通用修正。
   - 用 35aadb3 与本版论文复现口径（golden D5 现行修订）各跑第一个模型年，对比如下：
     - 进口由 1.548 降到 0.361 TWh（−76.7%）；
     - 时段平均价格由 22.35 降到 18.17 £/MWh，最高价由 5,849.5 降到 50.4 £/MWh；
     - 头条系统成本由 28,126.9 降到 27,201.5 百万英镑（−3.3%）。这一差额包含成本账 v2 等核算口径的变化；
     - 直接排放由 29.91 增加到 30.68 MtCO2（+2.6%）；
     - CCGT 新建提案取消。
   - 出处：35aadb3 一侧取自 `docs/dev/GBP1_DOCTORAL_BEFORE_AFTER.md` 中 35aadb3 的一列；本版一侧取自 `docs/dev/p0-reports/r41-golden/D5-gbp1-summary-before-after.json` 的 `after-r41`（之后的 D5 修订只改核算区的已供电量和每 MWh 供电成本，上面这些数值不变）。
   - 这两份都是内部文档，网站只能引用公开文档。公开之前，要由代码负责人先把这组数字写进 `CHANGELOG.md`。`CHANGELOG.md` 现有的 D5 数字只对应部分修正，不能单独作为本版的勘误数字引用。
4. **新源码 tag 的名称和推送时间**（阶段 1 的门槛，按 A17 在翻新之后）。根目录 `CITATION.cff` 目前仍是 `version: "source-2026-10-04"`，推送前要更新。
5. **0.7.0 安装包的构建和发布**（阶段 2 的门槛）：包括哪些平台，是否先只发 Linux。
6. **网站上口径的中文名。** 本文建议用“修正口径（默认）”和“论文复现口径”。翻新加入中英切换后，以应用的中文为准。
7. **公开文档在阶段 1 之前要同步的内容**（代码负责人做，作者批准）。网站文案没有可公开引用的依据时，不能上线：
   - (a) 还没有写进 `CHANGELOG.md` 和 `docs/USER_GUIDE*.md` 的行为：Run 的异步启动（2.8 节，含 API 行为）；2.12 节的界面字符串；新建 Study 同名时的 409 `GF_STUDY_ID_EXISTS`、扩展钩子输出的记录范围和扩展原地改源后停用再启用的规则（A29；这两项目前只写在 `docs/MODULE_DEVELOPER_101.md`）；用户指南也还没有写逐时需求的映射和 VALUE 101 需求文件按 MW 读取（这两项 `CHANGELOG.md` 已有）；有 Run 未结束时更改模块或扩展的处理（`GF_RUN_EXECUTION_IDENTITY_CHANGED`、`Resubmit with current code`）用户指南已写，`CHANGELOG.md` 还没有；
   - (b) `docs/VALIDATION_AND_CLAIMS.md` 有几处与当前代码不一致，网站不照抄：
     - 论文复现口径一行的边界列，写的逐位一致范围不对。当前只有 D1、D2 的轨迹逐位一致，D3–D5 已重基线（`P0_GOLDEN_DELTA.md`）；
     - golden 归因一行写 13 个用例，当前是 15 个；
     - 表格之后关于论文复现运行的段落，没有反映论文复现运行现在能通过能量平衡；
     - “Scope” 一节的通用修正清单不全，缺 VoLL、论文内核的三项修正和已供电量的核算修正；该节还有一段把 GBP1 论文复现运行写成已知问题，已不适用；
   - (c) `CHANGELOG.md` 0.7.0 一节中，按施工步骤写成的小节有些句子只描述该步骤当时的状态，与当前代码不一致：
     - “Golden delta summary” 第一段的逐位一致范围；
     - P0-4、P0-6 小节关于论文复现口径声明偏差和“调度逐位不变”的说法；
     - A16-2 小节的 GBP1 论文复现进口量（当前为 0.361 TWh）；
     - FX7 小节关于核电偏低的说法；
     - Known issues 中已划掉的条目。

     网站只取现行规则，以本文第 2 节为准。
8. **修正口径的 GBP1 结果、GBP1 public2 和 R029 public2 是否公开、何时公开。** 公开前，网站不得引用相关数字，也不得列出这两个包。
9. **重启成本的 2025 年 CPI 指数值（138.4）尚待对照 ONS 核对一次**（参考统计表 4.2a 节）。核对之前，网站不列重启成本的具体数字。

---

## 8 上传前检查清单（`website/check_site.py`）

网站构建需要 **Python 3.12 或更高版本**：`content.py` 用了 3.12 才支持的 f-string 嵌套同类引号，项目自带的 Python 3.10 解析它会报 `SyntaxError`（第 26 行）。请用上传员自己的 Python 3.12+，在 `website/` 目录下运行构建和站点检查。仓库根目录的检查脚本用项目的 Python 3.10（`python -B …`）运行。

1. **工作区干净**：`git status` 中只有本次打算修改的 `website/` 文件。
2. **构建**：`cd website && python3 build.py`。输出为 `Generated N localized routes in …/website/dist`，N 是中英文路由数之和，新增页面时相应增加。构建同时写出 `dist/assets/releases.json`（取自 `site.json` 的 `products`）。
3. **站点检查**：`python3 check_site.py`。要求退出码为 0，JSON 输出中 `local_links_and_assets: "passed"`、`errors: []`（另有 `localized_pages`、`bilingual_metadata`、`static_bytes`）。它检查以下几项：
   - 每页的 `lang` 与所在目录一致，只有一个 `<h1>`，没有重复 id；
   - `site.json` 的 `origin` 非空时，每页都有 canonical 和 hreflang（en、zh、x-default）；
   - 每页都有中英对应页；
   - 本地链接、资源和锚点都存在；
   - `site.json` 中每个 release 的 `version`、`platform`、`date`、`size`、`requirements`、`url`、`sha256` 非空，`sha256` 是 64 位十六进制，`url` 以 `https://` 开头。

   它**不**检查 `data_assets`、文案内容和外部链接是否可达。
4. **源码发布清单**（第 5 步依赖它）：在仓库根目录运行 `python -B scripts/refresh_source_release_manifest.py`，再用 `--check` 确认输出 `"stale": false`。任何 `website/` 源文件的修改都会改变 `source-release-manifest.json` 中的 sha256 和字节数；`website/dist/` 被 gitignore，不在清单中。
5. **版次与公开文本**：在仓库根目录运行 `python -B scripts/check_publication_scope.py --report <临时目录>/scope.json`。它要读 `website/dist`，所以必须在第 2 步之后运行。要求 `passed: true`。它检查以下几项：
   - 源码发布清单是否最新；
   - `site.json` 与 `publication-scope.json` 的版次和日期是否一致；
   - `dist/{zh,en}/methodology/index.html` 中的修订标签；
   - 方法学文档的哈希；
   - `website/static` 和 `website/dist` 中是否有私有产品标记。
6. **文案自查**（对构建输出 `grep`）：
   - `grep -rl "0.7.0" website/dist`：阶段 0 应该**没有**结果；阶段 1、2 只出现在预期的页面；
   - `grep -rln "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)" website/dist`：列出的每个页面，也要含 “not an exact reproduction of the 2026-07-18 retained trajectory”（中文页含“不是 2026-07-18 保留轨迹的精确复现”）；
   - `grep -rniE "globally optimal|exact reproduction|calibrated to DUKES|与 DUKES 一致|精确复现论文" website/dist`：除固定附注中的 “not an exact reproduction” 外，不应有其他命中；
   - `grep -rniE "aligned with the (doctoral )?thesis|reproduces the thesis|对标论文|与论文一致|复现论文" website/dist`：不应有命中（A26，2.1 节）；
   - `grep -rniE "shortfall.{0,40}(VoLL|lost load)|缺口.{0,20}VoLL" website/dist`：不应有把 stress 缺口写成按 VoLL 计价的句子（2.6 节）；
   - `grep -rn "pending" website/dist/en`：检查 `journey.py:50` 和 `publication.py:30` 的整句替换是否仍然生效，不能残留与 `publication_ready` 状态矛盾的句子。
7. **版本测试**：在仓库根目录用项目的 Python 3.10 运行 `python -B -m unittest tests.test_documentation_consistency`。`website/content.py`、`value-source-CITATION.cff`、`value-source-metadata.bib` 必须仍含 `0.6.0-alpha.2`。
8. **再次确认清单**：所有改动完成后，再运行一次 `python -B scripts/refresh_source_release_manifest.py --check`，输出 `"stale": false`。
9. **人工抽查**：
   - 在浏览器中打开 `website/dist/en/` 和 `website/dist/zh/` 下的这些页面：首页、`models/value`、`validation`、`releases`、`data`、`docs/value`、`docs`、`community`、`methodology`、`cite`、`about`；
   - 切换语言链接；
   - 在 375 px 窄屏下查看表格能否横向滚动。
10. **上传**：
    - 只上传 `website/dist/`；
    - 部署保持现有的站点受众（`website/README.md` 第 28 行：仅所有者可见；开放公众访问是单独的发布步骤）；
    - 上传后，抽查线上 `/en/releases/` 和 `/zh/releases/` 的 SHA256 是否与 `site.json` 一致。

---

## 9 网站现存问题（与版本变化无关，可以一并修）

1. **`journey.py:3-6` 的四个任务标签没有中文化。**
   - 第 2 列（`'reproduce from existing data'`、`'add your new data'`、`'Edit module'`、`'add new function to VALUE'`）在中文页也原样显示，大小写也不统一。`paths()`（`:9`）和 `pages()`（`:36`、`:40`）直接使用 `label`。
   - 建议改成 `(en, zh)` 二元组，再用 `w.t` 取值，例如：Reproduce / 复现、Adapt data / 换数据、Edit a module / 改模块、Add a function / 加功能。
2. **引用页 source 条目的版本不一致。**
   - `content.py:76` 的标题是 “VALUE · source-2026-10-04”，下载链接却指向 `static/assets/value-source-review-CITATION.cff`，而该文件写的是 `version: "source-review-2026-10-03"`；
   - 仓库根目录的 `CITATION.cff` 是 `source-2026-10-04`；
   - 建议在处理 C-14 时一并统一。
3. **`methodology_page.py:23` 的回退日期写死**：“Revised 3 October 2026 · …”。它只在 `edition.json` 缺失时出现，不影响现网，但阶段 3 之后会显得更旧。
4. **`content.py:88` 的 “VALUE software use Apache-2.0”**：现在靠 `publication.py:30` 的替换改成 “uses”。可以直接改正 `content.py:88`，再删去替换表中的这一项。

---

## 附录 A 建议文案

### A.1 `models/value` 新增一节 “Two methodology profiles / 两种方法学口径”（C-1，阶段 1）

**导语**（表格之前）：

- EN: “The methodology on this website describes the VALUE model as published: the corrected methodology, which new Studies and Runs use by default. A doctoral reproduction profile is kept for comparison with the thesis-era settings.”
- ZH：“本网站的方法学描述发布的 VALUE 模型，即新 Study 与 Run 默认使用的修正口径。另保留论文复现口径，用于与论文时期的设定对照。”

| Label（英文照抄） | What it is / 含义 | Boundary / 边界 |
|---|---|---|
| `Corrected methodology (default)` | EN: The VALUE model that the methodology describes, and the default for new Studies and Runs. Besides the corrections shared with the doctoral profile, it uses storage bids at cycle wear with uniform-price settlement, interconnector imports in the day-ahead clearing, nuclear in service from the start of each year, down regulation that weighs restart cost against the fuel, carbon and variable cost avoided, literature wind and solar losses with plane-of-array solar, station nuclear and DUKES hydro availability, storage headroom from the post-charge surplus with one cap per battery type, declared data reading, and network economics. ZH：方法学描述的 VALUE 模型，也是新 Study 与 Run 的默认口径。除两个口径共同的修正外，还包括：储能按循环损耗报价、统一边际价结算；互联线进口进入日前出清；核电在每年开始时在运；按重启成本与省下的燃料、碳和可变成本决定下调顺序；风光文献损耗与光伏倾斜面换算；核电分站与 DUKES 水电可用率；储能扩容用充电后剩余的盈余，并按电池类型分别设上限；按声明读取数据；网络经济口径。 | EN: A different method from the doctoral reproduction profile; compare the two as different methods. Wind and solar capacity factors are disclosed next to DUKES, not calibrated to them. ZH：与论文复现口径是不同的方法，比较时按不同方法对待；风光容量因子与 DUKES 并列披露，不对其标定。 |
| `Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)` — not an exact reproduction of the 2026-07-18 retained trajectory | EN: A compatibility profile that keeps the thesis-era settings as implemented in VALUE 0.6.0-alpha.2, such as wind curtailed first at zero cost, no wind and solar loss factors, no availability derating of nuclear and hydro, and the original data readings. The corrections shared with the default profile apply to it: interconnector series on the run clock, three GBP1 reading errors, declared-column reading, thermal investment net of running cost, a value of lost load of £17,000/MWh, down regulation taken once, one storage position per period, must-run nuclear surplus counted once, stress events and accounting corrections. Thesis-lineage modules and data packs only; refuses enabled external code. ZH：兼容口径，按 VALUE 0.6.0-alpha.2 的实现保留论文时期的设定，例如零成本风电先削、风光不乘损耗系数、核电与水电不按可用率折减、沿用原有的数据读法。两个口径共同的修正同样适用：互联线序列按运行时钟对齐、GBP1 的三处读取、按声明的列读取、火电投资扣除运行成本、缺电价值 17,000 £/MWh、下调只做一次、每个储能每个时段一个净头寸、必发核电盈余只计一次、stress event 与核算修正。只运行论文谱系模块和数据包；已启用外部代码时拒绝运行。 | EN: Annual results appear on result pages only when every raw invariant passed; otherwise read them in Inspect or the ledger files. Not an exact reproduction of the thesis results. ZH：原始不变量全部通过时，年度结果才在结果页发布；否则到 Inspect 或账本文件中查看。不是论文结果的精确复现。 |

中文页的标签列：第一行写 “`Corrected methodology (default)`（修正口径，默认）”；第二行写 “`Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)`（论文复现口径）：不是 2026-07-18 保留轨迹的精确复现”。

### A.2 验证页新增八行（C-11，阶段 1；须在第 7 节第 7 条的公开文档同步之后）

格式：标题 | 证据 | 边界。中文页的三列与英文同义。

1. **“Doctoral reproduction profile, golden D1–D5”**
   - 证据：EN: D1 and D2 trajectory columns bit-identical to VALUE 0.6.0-alpha.2 (35aadb3); D3–D5 re-baselined once per approved correction, with numeric reports.
   - 边界：EN: linux-x86_64, CPython 3.10.18, numpy 1.24.4, exact mode; not the 2026-07-18 retained trajectory; not an exact reproduction of the thesis results.
2. **“Corrected default PSM energy identity”**
   - 证据：EN: closes per period on the VALUE 101 one-day and two-year smoke cases.
   - 边界：EN: ahead-stage shortfalls are reported as stress events, not removed.
   - 若作者希望写 VoLL，加在这一行的边界列，不单独成行：EN: “Unserved energy recorded by the model is valued at £17,000/MWh in both profiles; stress-event shortfalls are reported separately and are deducted from energy served.” ZH：“两个口径都按 17,000 £/MWh 给模型记录的切负荷计价；stress event 的缺口单独报告，并从已供电量中扣除。”
3. **“Stress events (both profiles)”**
   - 证据：EN: per-period shortfall recorded and grouped into events; dispatch and prices unchanged.
   - 边界：EN: runs made before 0.7.0 did not record shortfalls.
4. **“GBP1 doctoral reproduction, first model year”**
   - 证据：EN: raw invariants pass; energy balance and storage limits are conformant on the doctoral ledger boundary; annual results are published.
   - 边界：EN: one model year; the doctoral ledger closing is not physical validation; 487 stress periods (78.8 GWh shortfall) are recorded with dispatch unchanged; in the doctoral rules an accepted nuclear unit runs to the end of the year.
5. **“Local API security boundary”**
   - 证据：EN: browser-driven, cross-origin and sessionless requests are refused (tests and browser E2E).
   - 边界：EN: Linux source tree; one user per computer assumed; an installed 0.7.0 is checked after installation.
   - 与第 7 节第 1 条的决定一起上线。
6. **“0.7.0-alpha.1 installers”**
   - 证据：EN: not yet built.
   - 边界：`not_evaluated`。ZH：尚未构建，`not_evaluated`。
7. **“Corrected wind and solar capacity factors”**
   - 证据：EN: disclosed next to DUKES 6.3 load factors in every run summary.
   - 边界：EN: not calibrated by design; GBP1 representative sites before curtailment: onshore about 1.56x, offshore 1.23x, solar 1.04x the DUKES 2020–2024 load factors.
8. **“VALUE four user paths, 0.7.0-alpha.1 source”**
   - 证据：从 `docs/handoff/FOUR_ROLE_TEST_REPORT.md` 的结论一节照录四条路径（reproduce、adapt data、edit a module、add a function）各自的结论。
   - 边界：EN: Linux source tree, not an installer; scopes as tested（按报告写明一日、两年等范围）。
   - 报告中有未关闭的中等缺陷时，在边界列写明（按本文依据的代码状态，报告中没有中等缺陷，见 2.9 节）；有高等缺陷时这一行不上线。

### A.3 四类用户步骤（J-3，阶段 2；中英各三条，逐条对应）

**复现**

1. 获取同一版本的软件与 VALUE 101 输入。
   - EN: Obtain the same release of the software and its VALUE 101 inputs.
2. 打开或复制教学 Study，在第 1 步选择方法学口径，然后显式启动 Run；Run 立即列出，并显示准备进度。
   - EN: Open or copy the teaching Study, choose its methodology profile in step 1 and explicitly start a Run; the Run is listed at once and shows its preparation.
3. 与同版本、同口径的参考结果比较；论文复现口径的年度结果若被扣发，在 Inspect 或账本文件中查看。
   - EN: Compare it with the reference of the same release and methodology profile; if doctoral reproduction annual results are withheld, read them in Inspect or the ledger files.

**换数据**

1. 复制 Study 与数据包。
   - EN: Copy a Study and its data pack.
2. 映射声明的列、字段名、单位、时区和采样间隔：需求用半小时或逐时数据，VALUE 101 的需求数值按 MW 读取，改写时选 MW；可以声明时间戳列（UTC 或 Europe/London）和日期顺序，系统逐行检查；欧元价格要填汇率、汇率口径和价格年份；互联线可用量正值为进口、负值为出口。
   - EN: Map the declared column, field names, units, time zone and sampling interval: demand is half-hourly or hourly, and the VALUE 101 demand values are read as MW, so map them as MW; optionally declare a timestamp column (UTC or Europe/London) and its date order, which are checked row by row; give EUR prices a rate, FX basis and price year; interconnector availability is positive for import and negative for export.
3. 在 Data 页的校验面板查看三层校验，在 Study 编辑器确认数据包可用于所选口径，再运行独立案例。
   - EN: Check the three validation layers in the Data page panel, confirm in the Study editor that the pack is available for the chosen profile, then run a separate case.

**改模块**

1. 在修正口径下选择受支持的模块，并保留基线。
   - EN: Under the corrected profile, choose a supported module and keep its baseline.
2. 在独立副本中修改，并以新身份安装；原地修改已安装的模块也可以，结果会记录新的源码哈希。属于方法变化时，要在界面确认 Study 迁移。
   - EN: Change it in a separate copy and install it under a new identity (an in-place edit of an installed module is allowed and Runs record the new source hash); confirm the Study migration when the method changes.
3. 运行相同的短案例并比较结果；停用或隔离的模块，在 Modules 页的 Disabled and quarantined 区恢复。
   - EN: Run the same short case and compare results; restore a disabled or quarantined module from Disabled and quarantined on the Modules page.

**加功能**

1. 定义扩展的输入输出契约。
   - EN: Define the extension's input and output contract.
2. 通过受支持的接口实现并登记，产物从 after_psm 钩子返回；冲突或损坏的扩展会被隔离，修复后点 Rescan；直接调用 API 的脚本要带会话头，并轮询异步启动的 Run。
   - EN: Implement and register it through the supported interface and return artifacts from the after_psm hook; a conflicting or broken extension is quarantined until you fix it and Rescan; API scripts send the session header and poll the Run they start.
3. 先在修正口径下用两时段或更长范围运行小型示例（一日课程不运行扩展），再开展长期研究。
   - EN: Run a small example of two periods or longer under the corrected profile (the one-day lesson does not run extensions) before a longer study.

### A.4 常见问题（J-7，阶段 2；界面字符串在前端翻新后重新核对）

1. **“How do I stop the application?” / “如何停止应用？”**
   - EN: Press Ctrl+C in the launch terminal. Runs whose model worker has started keep running in the background and are supervised again at the next start; a Run that is still being prepared stops and shows “Run preparation interrupted”, so start it again. Install new versions in a separate, empty directory.
   - ZH：在启动终端按 Ctrl+C。已经启动模型 worker 的 Run 会在后台继续，下次启动时重新接管；还在准备阶段的 Run 会停止，下次显示 “Run preparation interrupted”，需要重新启动。新版本安装到另一个空目录。
2. **“Inputs fail validation.” / “输入校验失败。”**
   - EN: Check field names, units, missing values and timestamps, the declared column and, for EUR prices, the rate, FX basis and price year. Demand needs at least one model year: 17,520 half-hourly values, or hourly rows (8,760 or 8,784), each hour being used for two half-hour periods. The VALUE 101 demand files are read as MW although their header says mwh, so map rewritten demand as MW; a demand whose annual energy differs from the replaced file by more than about 1.5 times gets a warning. Hourly prices and availability are each used for two half-hour periods. Save the file as comma-separated CSV. Any other series shorter than a model year is filled by repeating it from its start and needs your confirmation before it is committed. An optional timestamp column is checked row by row, with the date order detected or chosen. The Data page shows the three validation layers of each pack. Start with VALUE 101.
   - ZH：检查字段、单位、缺失值、时间戳和声明的列；欧元价格还要填汇率、汇率口径和价格年份。需求至少覆盖一个模型年：半小时数据 17,520 个值，或逐时数据 8,760、8,784 行，每小时用于两个半小时。VALUE 101 的需求文件表头写 mwh，但按 MW 读取，改写需求时映射选 MW；新需求的年电量与被替换文件相差约 1.5 倍以上时会有警告。逐时的价格和可用量，每个值用于两个半小时。文件要存为逗号分隔的 CSV。需求以外的序列不满一个模型年时，从开头重复补齐，提交前要另行确认。可选的时间戳列会逐行检查，日期顺序可自动识别或手动选择。Data 页列出每个数据包的三层校验。先运行 VALUE 101。
3. **“The page says ‘Open VALUE from its launcher’.” / “页面显示 Open VALUE from its launcher。”**
   - EN: The page was opened through another address, an old bookmark or another installation. Close it, start VALUE again with its launcher, then use http://127.0.0.1:8800 or http://localhost:8800.
   - ZH：页面不是经启动器打开的（用了其他地址、旧书签或另一份安装）。关闭页面，用启动器重新启动 VALUE，再打开 http://127.0.0.1:8800 或 http://localhost:8800。
4. **“A module or extension is quarantined (health: degraded).” / “模块或扩展被隔离（health 显示 degraded）。”**
   - EN: VALUE keeps running without it. Open Modules: the Disabled and quarantined area lists it with its manifest file and Enable, Rescan and Remove. Fix the code, then press Rescan (or Rescan modules at the top); Rescan also imports extension hooks again. If two manifests declare the same module ID, press Disable on either row: the copy is moved aside, then Enable restores the module. Remove moves the installation aside and is refused while a Study or Run uses it. Hook files of an installed extension may be edited in place, as for modules: Enable re-imports them and Runs record the new source hash; Enable is refused while a hook does not import. If you install, enable, disable or remove a module or extension while Runs are waiting, VALUE asks you to confirm: Runs that have not started are stopped, so resubmit them from the Runs page (Resubmit with current code) or start them again from the Study; Runs already running keep their code but cannot be resumed after the change. Offline: python -m gridform_core.module_recovery.
   - ZH：VALUE 会在没有它的情况下继续运行。打开 Modules 页，Disabled and quarantined 区列出该条目和它的清单文件，带 Enable、Rescan、Remove 三个按钮。修好代码后点 Rescan（或页头的 Rescan modules）；Rescan 也会重新导入扩展钩子。同一模块 ID 有两份清单时，在任一行点 Disable，副本会被移到一旁，之后点 Enable 恢复。Remove 只是把安装移到一旁；Study 或 Run 仍在使用时会被拒绝。已安装扩展的钩子文件与模块一样可以原地修改：Enable 会重新导入，Run 记录新的源码哈希；钩子无法导入时 Enable 会被拒绝。有 Run 在等待时安装、启用、停用或移除模块或扩展，VALUE 会请你确认：尚未开始的 Run 会被停下，可在 Runs 页点 Resubmit with current code 重新提交，或从 Study 重新启动；已在运行的 Run 保持原代码，但变更后不能再 Resume。离线时用 python -m gridform_core.module_recovery。
5. **“Annual results withheld for this reproduction run.” / “论文复现 Run 的年度结果被扣发。”**
   - EN: The doctoral reproduction profile publishes annual results only when every raw invariant passed. While the Run is still going, the check is pending. The notice names the raw invariant that failed. Read the results in Inspect or open the ledger files.
   - ZH：论文复现口径只有在原始不变量全部通过时才发布年度结果；Run 进行中显示待定。提示中写明失败的原始不变量。可以在 Inspect 中查看，或打开账本文件。
6. **“The one-day lesson will not start with my extension.” / “选了扩展后一日课程不能运行。”**
   - EN: The one-day lesson runs the market step only, so extensions would not execute. Choose two-period or a longer scope, or deselect the extension.
   - ZH：一日课程只运行市场步骤，扩展不会执行。请改用两时段或更长的范围，或取消选择扩展。
7. **“The first Run takes several minutes to start.” / “第一个 Run 要等几分钟才开始。”**
   - EN: In a new data folder the first Run archives the Python runtime once (about 3 minutes). The Run is listed at once and shows its preparation step; other pages stay usable, and you can cancel it before its model worker starts. Until a comparable Run has finished, the runtime estimate is a range.
   - ZH：在新数据目录中，第一个 Run 要先把 Python 运行环境归档一次（约 3 分钟）。Run 会立即列出并显示准备步骤；其他页面照常可用，模型 worker 启动之前可以取消。还没有可比的已完成 Run 时，运行时间估算给出一个区间。
8. **“Why are replay times in UTC?” / “为什么回放时间是 UTC？”**
   - EN: VALUE runs on UTC half-hours of a fixed 365-day model year: 29 February is skipped in a leap year and there is no daylight-saving shift. Timestamps declared in Europe/London are converted to UTC when the file is mapped. Market replay and exports label times as UTC model time.
   - ZH：VALUE 的模型时钟是 UTC 半小时、固定 365 天的模型年：闰年跳过 2 月 29 日，没有夏令时切换。按 Europe/London 声明的时间戳在映射时换成 UTC。Market replay 和导出把时间标为 UTC model time。
9. **“Why is Unserved demand larger than the unserved energy in the costs?” / “为什么年度卡片的 Unserved demand 比成本中的切负荷大？”**
   - EN: Unserved demand includes the stress shortfall: periods in which the accepted supply fell short of demand, recorded without changing dispatch or prices. The cost accounts value only the unserved energy recorded by the model, at £17,000/MWh. Both are removed from energy served, so the cost per MWh served and the carbon intensity use the energy actually delivered.
   - ZH：Unserved demand 包含 stress 缺口，即接纳的供给小于需求的时段；记录缺口时不改变调度和电价。成本账只按 17,000 £/MWh 给模型记录的切负荷计价。两者都从已供电量中扣除，所以每 MWh 供电成本和碳强度按实际交付的电量计算。

### A.5 rc1 安全提示草稿（只有作者选择第 7 节第 1 条 (a) 时才用）

- EN: “Full 2026-10-03-rc1 (VALUE 0.6.0-alpha.2) predates the October 2026 hardening of the local API. Use it only on a single-user computer, stop VALUE with Ctrl+C when you are not using it, and install the next release when it is available.”
- ZH：“Full 2026-10-03-rc1（VALUE 0.6.0-alpha.2）早于 2026 年 10 月对本地 API 的加固。请只在单人使用的电脑上运行，不用时在启动终端按 Ctrl+C 停止；下一版本可用后，请改装新版本。”
