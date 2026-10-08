# VALUE 0.7.0-alpha.1 四角色用户验收报告

- 日期：2026-10-08。
- 被测版本：分支 `fix/review-2026-10-04`，代码状态 `cbdb69a`（此后的提交只改文档），`package.json` 版本 0.7.0-alpha.1。
- 结果的得出方式：先在构建 `c204aac` 上按四个角色各自从头完整走一遍，再在 `cbdb69a`（即当前代码）上逐项定向验证此后的每项修复，并用两个方法学口径各跑一次两整年冒烟 Run。
- 四个角色按首页的四条路径命名：
  1. **复现**：reproduce from existing data；
  2. **换数据**：add your new data；
  3. **改函数**：edit a module；
  4. **加功能**：add new function to VALUE。
- 两个方法学口径：
  - **修正口径**（默认，`Corrected (default)`）就是网上发布的 VALUE 模型，网站方法学描述的是它；
  - **论文复现口径**（`doctoral-lineage-0.6.0a2`，`Doctoral reproduction`）是兼容口径。它保留论文时期的设定，这些设定不是错误；全部通用修正也作用于它。
- 本报告只写当前代码的状态。以前各轮的测试与修复记录见 git 历史和 `docs/dev/p0-reports/`。

**阅读说明**

- 严重度：
  - **高**：结果算错、数据丢失，或主路径走不通；
  - **中**：主路径能走通，但某个功能失败、提示与事实相反，或必须绕行；
  - **低**：文案、显示、一致性问题，或需要另行设计的小功能。
- 编号：RP 复现、SD 换数据、EM 改函数、AF 加功能，后接严重度和序号，例如 EM-中1。
- 证据来源标注：
  - 「完整验收」：`c204aac` 上的四角色完整走查。只用于此后没有改动的功能，或经定向验证确认数值未变的结果；
  - 「定向验证」：`cbdb69a` 上的定向验证与冒烟 Run；
  - 「修复单元检查」：各修复单元在独立 scratch 实例上的 Playwright 检查和单元测试，针对纯显示类改动，定向验证没有再跑。

## 0 总览

### 0.1 各角色结论

| 角色 | 结论 | 已走通的主路径 | 高 | 中 | 低 |
|---|---|---|---:|---:|---:|
| 复现 | 通过 | Home → VALUE 101 → 建修正口径与论文复现口径 Study → 两整年 Run → 结果页 → 比较 → 导出与审计包 → 重跑。重跑后年度结果、投资决策和市场账本逐字节相同 | 0 | 0 | 1 |
| 换数据 | 通过 | 复制数据包 → 映射逐时、闰年、日/月/年、GW、EUR（带汇率）、当地时间等 CSV → 校验 → 派生 Study → 两整年 Run → 回放与比较。单位、币种和时钟只换算一次，需求量级变化有告警，已供电量扣除 stress 缺口 | 0 | 0 | 0 |
| 改函数 | 通过但有问题 | 构建 → 安装 → 派生只改一个槽位的对照 Study → 两时段与两整年 Run → 比较。就地改源、隔离、同 ID 两份清单、停用/启用/移除、离线恢复、内置模块方法升级确认都正常 | 0 | 1 | 2 |
| 加功能 | 通过但有问题 | 编写扩展 → 校验 → 安装 → 独立草稿启用并绑定数据 → 两时段与两整年 Run → Inspect 查看扩展结果 → 原地改源 → Rescan → 重跑对比。命名空间冲突、隔离、停用/启用都正常 | 0 | 1 | 3 |
| **合计** | | | **0** | **2** | **6** |

**一句话结论：** 四条用户路径都能从头走通，没有高等缺陷，没有发现算错的结果；两个口径的冒烟 Run 与完整验收的数值一致。两项中等缺陷都不影响模型结果：

- **EM-中1**：有 Run 排队时更改模块或扩展，确认框说排队的 Run 会用新代码启动，实际它们会失败，而且错误码笼统；
- **AF-中1**：原地改过钩子源码的扩展一旦停用，就不能直接重新启用。是否放开，需要作者决定。

### 0.2 现存缺陷一览

| ID | 严重度 | 现象 | 建议修复（要点） |
|---|---|---|---|
| EM-中1 | 中 | 有 Run 排队时安装、启用、停用或移除模块（或扩展），确认框写排队的 Run “would start with the changed code”；实际它们以 `GF_CONTRACT_001`（模块不满足契约）失败，日志原因是执行身份在入队后改变 | 确认框如实写“未开始的 Run 会失败，需要重新提交”；执行身份变化用专门的错误码和说明；或确认后自动把未开始的 Run 重新入队 |
| AF-中1 | 中 | 原地改过钩子源码的扩展，停用后再 Enable 被拒（400 `GF_EXTENSION_SOURCE_CHANGED`）。信息写出改动的文件和两条出路；开发者手册第 12 节对扩展的说法与此不符 | 作者决定扩展是否与模块一样适用 A16-4，再相应地放开核对或改手册 |
| RP-低1 | 低 | 两次逐位一致的重跑，第二个模型年的 `annual_input_state_sha256` 不同，因为状态中的投资项目 ID 带 Run id 前缀 | 另设与 Run 无关的可重复性哈希；现有哈希不动 |
| EM-低1 | 低 | 比较页以第一个勾选的 Run 为参照，页面写明了参照，但没有选择控件（换数据、改函数两条路径都会遇到） | 加参照 Run 选择，默认取基线；待设计方决定 |
| EM-低2 | 低 | 英文和中文用户指南中仍有 11 处把产品称作 FORCE | 统一改为 VALUE |
| AF-低1 | 低 | 扩展钩子产物被拒导致 Run 失败时，Runs 页只显示通用的 `GF_CONTRACT_001`，具体原因只在 `diagnostics/error.json` | 用专门的错误类型带出原因，或在 Runs 页显示诊断首行（与 EM-中1 同一根因） |
| AF-低2 | 低 | 独立 Study 草稿在浏览器刷新后丢失，没有提示 | 保存草稿，或至少在离开页面前提示 |
| AF-低3 | 低 | 界面中英混排：研究路径、Run 复现面板、需求单位说明等是中文，其余是英文 | 发布前定一种界面语言 |

### 0.3 需要作者或设计方决定的事项

1. **扩展的原地改源规则（AF-中1）**：作者决定扩展停用后重新启用时，是否像模块一样接受并记录原地改动（A16-4）。
2. **研究路径中能否直接选择口径**（`P0_FRONTEND_DEVIATIONS.md` F-R52-1）：现在研究路径和 Runs 页都显示口径，但要换口径必须到 Studies 编辑器。待设计方确认。
3. **比较页的参照 Run 选择器**（F-R51-3，即 EM-低1）：待设计方确认。
4. **储能 tranche 是否允许合并**（见 4.4 第 1 条）：只在需要进一步缩短“很少放电的储能 + full 追踪”的运行时间时才需要决定。
5. 若干界面措辞待设计方确认（`P0_FRONTEND_DEVIATIONS.md` R5 各节中“待确认”为“是”的条目），不影响功能。

## 1 测试方法与条件

### 1.1 完整验收（`c204aac`）

- 每个角色各用 `git archive` 把代码导出到 scratch，重新执行 `vinext build`，再用全新的 `VALUE_DATA_HOME` 启动后端和界面网关（18xxx 端口）。
- VALUE 101 教学包按页面提示用 `scripts/install_synthetic_pack.py --value-101-only` 安装（源码检出的安装路径）。
- 测试员以第一次使用的新用户身份从 Home 出发，用 Playwright（headless chromium 1243）操作界面。只有界面没有入口的边界情形，以及需要核对磁盘记录时，才直接调 API 或读文件。
- 四个角色互相独立，不参考以前的报告结论。

### 1.2 定向验证（`cbdb69a`）

- 环境同上（API 18870、UI 网关 18871，全新数据目录）。
- 范围：重跑完整验收中每个高、中缺陷的复现步骤，以及影响结果标注或导出内容的修复，逐项确认现状；另跑两个口径的两整年冒烟 Run。按 DECISIONS A28，没有完整重跑四个角色，也没有做新的探索性测试。
- 纯显示类修复由各修复单元的 Playwright 检查和单元测试确认（「修复单元检查」）。

### 1.3 冒烟 Run（VALUE 101，两整年，35,040 个时段，「定向验证」）

| | 修正口径 | 论文复现口径 |
|---|---|---|
| 状态 | completed；execution、scientific 通过；能量平衡通过；无 stress；年度结果已发布 | completed；execution 通过；scientific 为 `reproduction_conformant`；raw invariants 通过，年度结果已发布 |
| 2025 系统成本 | £14,699,553（£62.85/MWh） | £14,458,446（£61.82/MWh） |
| 2026 系统成本 | £14,424,989（£61.68/MWh） | £14,230,219（£60.85/MWh） |
| 碳排放 2025 / 2026 | 46,239 / 38,635 tCO2e | 不给总量，标为 not physically interpretable（论文时期的储能碳标量没有物理单位，`legacy_storage_scalars_have_no_declared_physical_unit`） |
| 未用 VRE 2025 / 2026 | 4,002.9 / 25,026.5 MWh（3.1% / 14.6%） | 2.0 / 2.0 MWh |
| 年需求 / 已供电量 | 233,870.27 / 233,870.27 MWh | 233,870.27 / 233,870.27 MWh |
| advisory | 0 条 | 8 条 |

两个口径的系统成本、碳排放和未用 VRE 与完整验收报告的数值一致。

## 2 复现角色（reproduce from existing data）

### 2.1 结论

**通过。** 整条复现路径能走通：建 VALUE 101 基线和两个口径的 Study，在界面中启动 Run，查看结果，比较两个口径，导出 CSV、JSON、回放导出和审计包，两个口径各重跑一次。现存 1 项低等缺陷（RP-低1），不影响结果。

### 2.2 已验证可用（附证据）

1. **Home → Research guide → VALUE 101**（完整验收）
   - 教学包未安装时，页面给出安装方法和命令；
   - 装好后点 “Create baseline Study” 得到 revision 1，页面写明 “Run started: no”。
2. **复现路径与口径**
   - 选基线、填名称、创建复现 Study 后转到 Runs 页，提示尚未启动 Run。以论文复现口径 Study 为基线时，新 Study 继承 `methodology.profile=doctoral-lineage-0.6.0a2` 和对应的碳因子参数（完整验收）。
   - 研究路径第 2 步和 Runs 页的 “What will run” 都显示口径：`Doctoral reproduction` 或 `Corrected (default)`（定向验证）。
   - 名称为空时，创建按钮下写明要先填写名称（修复单元检查）。
3. **在 Studies 编辑器中选择论文复现口径**（完整验收）
   - 不兼容的数据包标为 “not available with this methodology” 并说明原因；
   - Review 一步显示方法学和模块图 SHA，保存成功。
4. **启动 Run、进度与响应**（完整验收）
   - Check readiness 给出 35,040 个时段，首次估计 3–18 min；重跑时估计改为 “about 2 min”。
   - 点击后立即显示 “Preparing · step 1 of 4…”、elapsed 计时和 “1 Run running in background” 徽标。第二个 Run 正确排队，依次进入 Computing year、Finishing outputs，最后 completed。
   - 首次冻结输入约 3 min，计算约 2 min。运行期间在 Market replay、VRE、Inspect、Runs 之间切换，每次 45–96 ms，页面不卡顿。
   - Run 准备期间，Market replay、VRE、Inspect 不发请求，页面说明 Run 仍在准备（4xx 为 0）；论文复现口径的 Run 在完成前把年度结果标为 Pending（`GF_RESULTS_PENDING_RAW_INVARIANTS`）；历史复现面板只在 Run 结束后出现（修复单元检查）。
5. **结果**
   - 两个口径的数值见 1.3 节（定向验证）。
   - 论文复现口径的 raw invariants 通过，年度结果按 `raw_invariants_must_pass` 规则发布；advisory 只附适用的条目，VALUE 101 上共 8 条（没有径流水电，就不附径流水电资本的提示）（定向验证）。
   - 年度卡片显示 `Unused VRE (PSM boundary)`：修正口径 2026 年 25,026.5 MWh（14.6% of available），论文复现口径 2 MWh（<0.1%）（定向验证）。
   - Market replay 显示 shortfall 和 Stress events；Network 页正确说明这是 copperplate Run；Inspect 能看到规划项目和生命周期事件（完整验收）。
   - Market replay 窗口卡写明 Accepted supply 的统计边界：2025-01-01 修正口径 787.02 MWh（全节点，含储能充电），论文复现口径 775.49 MWh（来源分类节点，预平衡盈余给储能的充电不在此数内）（修复单元检查）。
   - 年度卡片的规划计数分为 “Active before admission” 和 “Admitted this year”，与 Inspect 的 Active 一致；Inspect 的 Project 列每个 ID 只显示一次；没有扩展的 Run 的 Artifacts 页说明未选可选扩展（修复单元检查）。
6. **比较与导出**
   - 修正口径对论文复现口径的比较列出方法学差异和每条 advisory，逐指标说明扣留差值的原因（完整验收）。
   - 未用 VRE 两个口径的数值都给出；差值不给，页面写明原因：两个口径的 PSM 边界不同（定向验证）。论文复现口径的预平衡盈余另列一行（修复单元检查）。
   - 比较 CSV 和 JSON 导出成功（完整验收）；CSV 每个指标都有 `value_status`、`value_reason_code`、`delta_shown`、`delta_withheld_reason`（修复单元检查）。
   - 回放有界导出（168 h，336 行）在后台完成并可下载（完整验收）。导出含 `clearing_price_basis`、`period_shortfall_mwh`、`period_stress`、`shortfall_basis` 四列（定向验证）。
   - “Prepare audit bundle” 7.6 s 完成，zip 含 43 个文件，校验完好；“核对冻结输入与执行身份” 22 s 完成，输入完整性 verified，25 个规范角色（完整验收）。
7. **重跑可重复性**（完整验收）
   - 两个口径的重跑与首跑相比，年度结果和投资决策完全相同；
   - `market/market.sqlite` 逐字节相同；碳账本去掉 Run id 后相同；
   - 比较页 identity 各维度都是 Same，各指标 “+0 · 0%”。
8. **手机宽度**：390 px 下 run、journey、projects 三个页面没有横向滚动（完整验收）。

### 2.3 现存缺陷

#### RP-低1 两次逐位一致的重跑，`annual_input_state_sha256` 不同

- **现象：** 同一 Study 重跑两次，结果逐位一致，但第二个模型年（2026）的 `annual_input_state_sha256` 不同（完整验收：修正口径 `de94…` 对 `2934…`，论文复现口径 `39fb…` 对 `f945…`）。第一个模型年相同。
- **复现：** 同一 Study 连续跑两次两整年 Run，比较两次 2026 年年度结果中 transition lineage 的 `annual_input_state_sha256`。
- **原因：** 年度输入状态里有模型投资项目，项目 ID 带 Run id 前缀（`gridform_core/builtin/scheme_c_1000twh/v2_module_definitions.py:205`、`doctoral_policy.py:514`，例如 `repro-doctoral-…:2025:onshore_Portsmouth:2`）。这个哈希在 `gridform_core/v2/orchestrator.py:372` 对整个状态求得。
- **影响：** 该哈希用于同一 Run 内检查点和年度链路的完整性核对，这一用途不受影响；结果也不受影响。但它不能用来跨 Run 核对可重复性。
- **建议：** 另设一个与 Run 无关的可重复性哈希，例如求哈希前把项目 ID 中的 Run id 前缀换成固定占位。现有哈希不改，否则检查点兼容性会变。这是新功能，需要先设计。

### 2.4 需要知道的情况（不计缺陷）

- 口径只能在 Studies 编辑器中选择。研究路径沿用基线的口径，并写明如何更换（见 0.3 第 2 条）。
- 年度卡片上的 “Final VRE curtailment” 是 v2 弃电归因指标，需要配对的反事实快照，只有 zonal PSM 提供，所以 copperplate Run 显示 Unavailable。物理上未用的 VRE 看同一卡片上的 `Unused VRE (PSM boundary)`。

## 3 换数据角色（add your new data）

### 3.1 结论

**通过，没有现存缺陷。** 从新数据目录开始，复制独立数据包，用映射编辑器导入各种格式的 CSV，校验，派生 Study，完成两整年 Run，查看结果、回放和比较，全部能走通。数值抽查与输入一致。

### 3.2 已验证可用（附证据）

1. **首次启动与基线**（完整验收）
   - 新数据目录下，VALUE 101 页提示教学包未安装并给出命令；安装后 25/25 输入就绪。
   - “Create baseline Study” 创建 revision 1；两整年 Run 约 5 分钟完成（含首次归档运行环境），状态 passed。
2. **复制数据包**：研究路径第 2 步复制出独立包，基线包的文件哈希前后不变（`88ca2112…`）（完整验收）。
3. **映射编辑器**
   - **逐时 EUR 价格**（Belgium，8,760 行，ISO，UTC）：选 EUR 后必须填 `EUR per GBP`、`FX basis`、`Price year`，未填时预览按钮不可用；列名提示 “Column name suggests EUR”；报告写明 “each hour is used for two half-hour periods”；90.00 EUR 按 1.17 换成 76.923 £；角色卡写出原币种、汇率、汇率口径和价格年份（完整验收）。
   - **日/月/年、GW**（demand.forecast，17,520 行）：自动识别为 DD/MM/YYYY，并写明依据 “CSV line 578 has a first field above 12”；0.063614 GW 换成 63.614 MW；Run 中第 0 期预测需求 31.807 MWh，与文件一致（完整验收）。
   - **闰年半小时**（demand.real，2024 年 17,568 行，MW）：报告写明删去 2 月 29 日并按年电量重新缩放；数据年份与 Study 首年不同时给出 `GF_DATA_TIMESTAMP_YEAR`。Run 中第 0、2783、2784、2832（3 月 1 日 00:00）、17519 期的需求都等于文件值 × 0.5 × 1.0030462（完整验收）。
   - **逐时需求**（2024 年 8,784 行，ISO，UTC，MW，带时间戳列）：完整校验通过，只给一条说明 `GF_MAPPING_HOURLY_DEMAND`（展开为 17,568 个半小时）。规范文件 17,568 行，每小时的值用于该小时的两个半小时（63.7691、63.7691、63.9805、63.9805…）（定向验证）。
   - **Europe/London 当地时间**（MWh/period）：夏令时文件 0 个问题；把每天 48 期的“天真”当地时间文件逐行报出 2 个不存在的春季时刻和 2 个无法定位的秋季重复时刻（完整验收）。
   - **美式日期**：自动识别 MM/DD/YYYY（“CSV line 290 has a second field above 12”）；若声明为 DD/MM/YYYY，报出问题并提示 “132 gaps last about a month: the dates may be in MM/DD/YYYY order”（完整验收）。
   - **其他校验**：分号分隔文件在暂存时拒绝并说明另存为逗号分隔；重复和缺口逐行列出 Data row / CSV line；半年序列须另勾确认框；价格年份 2023 给出 `GF_MAPPING_PRICE_YEAR`（完整验收）。
   - 显示：标签为“列与单位映射 SHA”，并注明时间戳列、时区、日期顺序记录在时间戳报告和绑定中；校验详情的 `clock_adapter` 按实际读法写（`as_is`、`hourly_to_half_hour`、`leap_day_removed` 等）；覆盖说明按期数写（如 “1 period (30 minutes)”）；审阅有效期显示本地时间（修复单元检查）。
4. **需求单位与量级检查**（定向验证）
   - VALUE 101 两份需求文件的表头写作 `mwh`、绑定标签为 `MWh/period`，模型按 MW 读。工作区绑定带 `runtime_unit_interpretation`（declared MWh/period → runtime MW）；角色卡和映射编辑器都写明“按 MW 读取……已知误标……改写时请选择 MW”。
   - 上传基线 ×1.15 但按 MWh/period 声明的文件：审阅给出 `GF_DATA_DEMAND_SCALE`，写出新序列约 537,902 MWh/年，是被替换文件（约 233,870 MWh/年）的 2.30 倍；复制包的数据包校验对 demand.real、demand.forecast 各告警一次。
   - 比较页有 `Annual demand (MWh)` 一行：233,870.27 对 537,901.63（+130%）。
5. **Run 运行时也能准备数据**（定向验证）：有 Run 处于 queued 或 snapshotting 时暂存 CSV，20 秒内工作区轮询 11 次，不重新解析 Study、不重拉映射目录；列选择 10 次采样都保留，之后预览和提交成功。
6. **校验面板**：25/25；Structural 按角色列出警告；Chronology、Plausibility 通过；修正口径 Eligible，论文复现口径 “Not eligible — not a thesis-era pack”（完整验收）。
7. **派生 Study 与 Run**（完整验收）
   - 研究路径第 3 步显示基线、年份、修订哈希、原包和新包；创建后转到 Runs，Check readiness 为 Ready（约 2 分钟，35,040 期）；两整年 Run 约 2.5 分钟完成，契约、科学校验、能量平衡均通过。
   - 新 Study 保存后再改该包，提示 “该数据包已被保存的 Study 引用。请再次复制后编辑”。
8. **已供电量与未供电量**（定向验证，需求为基线 2.3 倍的 Run）
   - 2025 年缺口 28,333.03 MWh，其中 PSM 记录 2,736.46 MWh，其余 25,596.57 MWh 为 stress 缺口。
   - 已供电量 509,568.60 MWh = 需求 537,901.63 − 28,333.03。每 MWh 供电成本 156.62 GBP、每 MWh 碳强度 283.74 kg 都以已供电量为分母。
   - 年度卡片（2026）显示 `Unserved demand 23,325.39 MWh · incl. stress shortfall · 2,411.73 MWh recorded by the PSM`；比较页把“含 stress 缺口的未供电量”和“PSM 记录的未供电量”分两行。
9. **回放时间**（完整验收）
   - 窗口行写 `2025-01-01 00:00 → 2025-01-02 00:00 (UTC model time)`，stress 表头写 `Start (model date & time, UTC)`；API 返回 `timezone: UTC`、`calendar: fixed_365_day_utc_periods`。
   - 点 stress 事件的 “Replay →” 跳到对应窗口。
10. **比较**
    - 勾选两个 Run 后，身份检查只有 “Base and network data: Changed”，并列出改动的角色；CSV 导出正常（完整验收）。
    - 年度表上方写明增量相对哪个 Run（第一个勾选的 Run，写出 Study 名和 run id），以及如何换参照（修复单元检查）。参照选择控件见 EM-低1。

### 3.3 现存缺陷

无。

### 3.4 需要知道的情况（不计缺陷）

1. **VALUE 101 需求文件的单位标注。** 两份需求文件保留原有字节和 manifest（表头 `mwh`、标签 `MWh/period`），所以 `methodology/profiles.json` 中的 manifest 钉值、已有 Study 和 Run 的输入哈希都不变。界面按内容识别这两份文件并说明按 MW 读取。
2. **年电量检查只告警，不阻止提交。** 新需求与被替换文件的年电量之比大于 1.5 或小于 0.67 时告警（`gridform_core/data_pack_validation.py:241`），因为大幅改变需求可能是有意的情景。
3. **逐时需求在映射时展开为半小时。** 需求读取器只接受 30 分钟数据；逐时原文件随映射保留，并按 60 分钟重查时间轴。
4. **已供电量规则是通用核算修正**（`r5.served-energy-net-of-stress-shortfall`，两个口径都生效，不改调度，不属于方法身份）。没有 stress 时段的年份不扣 A2 账中 1e-8 MWh 量级的数值噪声。golden 中只有论文复现参考运行 D5（GBP1，2025，487 个 stress 时段）的核算区受影响：已供电量扣除 78,810.2 MWh stress 缺口，每 MWh 供电成本 116.828773 GBP/MWh。
5. **成本账的定义 ID 没有因该修正而改变**（仍为 `value.cem-system-resource-cost/v1`），修正 id 记在每个 Run 的通用核算修正列表中。因此，如果把更早的构建产生、不含该修正的 Run 与当前版本的 Run 比较，且其中有 stress 时段，比较页会照常显示每 MWh 成本的增量，不会因分母规则不同而扣留。只用当前版本产生的 Run 时不受影响。

## 4 改函数角色（edit a module）

### 4.1 结论

**通过但有问题。** 主路径（构建改过的模块 → 安装 → 派生只改一个槽位的对照 Study → readiness → 运行 → 比较）能走通；就地改源、隔离、同 ID 两份清单、停用、启用、移除、离线恢复和内置模块方法升级确认都符合手册。现存 1 项中等缺陷（EM-中1，在定向验证中发现）和 2 项低等缺陷。

### 4.2 已验证可用（附证据）

1. **构建**：示例改为 73 GBP/MWh，ID `hx-flat-offer-73`、版本 1.1.0、包 `hx_flat_offer_73`。连续构建两次，SHA-256 都是 `2ff84a0f…`（完整验收）。
2. **安装**：Modules 页显示 “passed structural conformance”。以下错误情形都被拒绝，信息正确：再次安装同一 ID（`GF_MODULE_ID_COLLISION`）、使用 `gridform.storage-cost/v1`（`GF_MODULE_CONTRACT_MISMATCH`，保留手册引用的句子）、使用内置 ID（`GF_MODULE_BUILTIN_COLLISION`）、顶层包同名（`GF_MODULE_PACKAGE_COLLISION`）（完整验收）。
3. **检视**：显示身份、契约和源码 SHA，可以查看已记录的源码，也能和参考模块对比 manifest 差异（完整验收）。
4. **派生**：“Create an independent Study with one method change” 只改 `storage_cost` 一个槽位；实验性模块必须勾选确认（`GF_EXPERIMENTAL_ACK_REQUIRED`）；保存后 Runs 页显示 A/B 标题（完整验收）。
5. **两时段运行**：Ready 后运行完成；storage cost 槽位显示 “Called inside the PSM: the market ledger records its storage offers (2 storage asset-periods)”（完整验收）。
6. **两整年运行与比较**
   - 比较时身份检查只有 “Model method … Changed (modules.storage_cost)”。2025 年 CEM 系统成本：基线 14,699,553.28，flat-73 为 14,789,538.15（+0.61%）；碳排放 46,239.27 对 46,977.72 tCO2e。VRE 弃电归因三项不给差值并写明原因。年度储能报告中 `fixed_offer_gbp_per_mwh=73`、`current_year_sold_mwh=0`（完整验收）。
   - flat-73 模块、full 追踪、两整年：readiness 给出 `GF_PREFLIGHT_ESTIMATE_STORAGE_MODULE` 警告；计算 6.8 分钟（与另两个 Run 同时运行），输出 1.6 GB，`clearing_inputs` 单行最大 26,823 B；2025 年 CEM 成本 14,789,538.15，与完整验收逐位相同（定向验证）。同配置的内置模块基线为 1.4 GB、3.7 分钟（完整验收）。
7. **就地改源（73→31）**：readiness 出现琥珀色警告 “Module source changed since install (7cb4350d… → 11377575…)”；新 Run 冻结新哈希；`/api/comparisons` 在 `identity.method` 下按 `source_sha256` 标出差异（完整验收）。
8. **隔离**（插入错误 import 后点 Rescan）（完整验收）
   - `/api/health` 为 `degraded`（`GF_MODULE_IMPORT_FAILED`），面板列出原因和清单文件；
   - 选了该模块的 Study 报 `GF_PREFLIGHT_MODULE_QUARANTINED`，Run 按钮不可用；没选它的 Study 为 Ready，只有 `GF_PREFLIGHT_MODULE_QUARANTINE_PRESENT` 环境提示。
9. **停用、移除、启用**（完整验收）
   - 隔离面板的 Disable 有确认框，之后 health 回到 ok；卡片显示 “Used by 2 saved Studies”；readiness 报 `GF_PREFLIGHT_MODULE_DISABLED`。
   - 被引用时 Remove 被拒（`GF_MODULE_IN_USE`，列出 Study），卡片上的 Disable 不可点。
   - 源码未修好就 Enable，报出新的导入错误；修好后 Enable 成功，health ok，readiness Ready。
   - 未被引用的模块：Disable → Remove → 文件移到 `disabled-manifests/removed/…` → 同 ID 可以重新安装。
10. **同 ID 两份清单**（定向验证）
    - Rescan 后两行都被隔离（`GF_MODULE_ID_DUPLICATE`），各显示自己的清单文件。
    - 在副本那一行点 Disable：提示写出被移走的副本（`modules/disabled-manifests/modules/…`），隔离面板消失，health ok。
    - 安装已停用而副本仍在时，Enable 返回 409 `GF_MODULE_ID_COLLISION` 并写出副本文件名；Disable 移走副本后 Enable 成功。
    - `module_recovery list` 对停用安装留下的清单标出问题和 `park-manifest` 修复命令（修复单元检查）。
11. **离线恢复**：`module_recovery list`、`verify` 正常；VALUE 运行时离线 `disable` 被拒；停机后 `park-manifest` 能恢复（完整验收）。
12. **内置模块方法升级（手册 12.1）**
    - 改 `runtime_compat/storage_cost.py`（2.0.0→2.1.0），同步 manifest、`VERSION_LEDGER`（`requires_user_opt_in=true`）和 CHANGELOG 中的修正 id。修正 id 拼错时 `check_version_ledger` 失败，`seal_runtime_overlay` 也拒绝；未封存时 readiness 报 `GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED` 和 `METHOD_UPGRADE_REQUIRED`（完整验收）。
    - 封存后 Check readiness 弹出 “This Study needs your confirmation…”，列出 2.0.0→2.1.0；取消则被阻断，确认后生成新修订并变为 Ready，新 Run 记录新版本；不用该模块的 Study 不受影响；对升级前的 Run 做严格复现核对，结果为“当前方式存在阻断”并列出版本差异（完整验收）。
    - readiness 的建议写 “Press Check readiness again: VALUE lists the changes for your confirmation and saves them as a new revision of this Study.”；确认后 “Saved as a new revision (revision N)” 提示保留（修复单元检查）。
13. **模板与显示**
    - 可下载可编辑的源码模板，构建后能安装并通过一致性检查（完整验收）。storage_cost 模板名为 “Draft fixed-offer storage example (GBP 42/MWh)”，与其固定 42 GBP/MWh 的行为一致（修复单元检查）。
    - Modules 页徽标写 “13 of 18 ready · 5 experimental”；起止年份相同的 Study 只列出能运行的范围（修复单元检查）。

### 4.3 现存缺陷

#### EM-中1 有 Run 排队时更改模块或扩展：确认框说排队的 Run 会用新代码启动，实际它们失败，错误码笼统

- **来源：** 定向验证中观察到，代码确认。
- **复现：**
  1. 启动一个两整年 Run，再启动第二个，使它处于 queued 或 snapshotting；
  2. 在 Modules 页安装、启用、停用或移除任一本地模块或扩展；
  3. 确认框写：`Runs have not finished: 1 run(s) not started yet (…) would start with the changed code. Confirm to change installed modules anyway.`，点确认；
  4. 排队的 Run 失败，显示 `GF_CONTRACT_001`（“A selected module did not satisfy its declared contract.”）；日志原因是 “Execution source or runtime changed after enqueue”。重新提交后正常完成。
- **原因：**
  - Run 入队时记录执行身份，其中包含 `modules/` 下全部活动清单以及已安装的模块和扩展（`gridform_core/execution_archive.py:123-150`）。所以任何模块或扩展的生命周期变更都会改变它，与排队的 Run 是否用到该模块无关。
  - worker 启动时，`backend/run_execution.py:45` 发现执行身份变化，抛出 `ValueError`；`gridform_core/errors.py:90` 起的 `public_failure` 把所有 `ValueError` 归为 `GF_CONTRACT_001`。
  - 确认框文字来自 `backend/server.py:476-494`（`require_no_pending_runs`），对尚未开始的 Run 的说法与实际相反。
- **影响：** 安全失败，不产生错误结果。但用户按提示确认后，排队的 Run 全部失败，错误码又指向“模块不满足契约”，容易误以为模块本身有问题。
- **建议修复：**
  1. 确认框如实写明：“尚未开始的 Run 会失败，需要重新提交”；
  2. 执行身份变化改用专门的错误码和公开说明（例如“Run 排队后已安装的代码发生了变化，请重新提交该 Run”），不再落入 `GF_CONTRACT_001`；
  3. （可选）确认后自动把未开始的 Run 重新入队，重新记录执行身份。

#### EM-低1 比较页不能选择参照 Run

- **现象：** 年度增量以第一个勾选的 Run 为参照。页面写明参照（“Deltas (+ and %) are measured against …, the first Run ticked. To measure against another Run, clear the selection and tick that Run first.”），但没有选择控件。换数据和改函数的对照通常以基线为参照，用户要清空选择后按顺序重新勾选。
- **复现：** 比较页先勾派生 Run，再勾基线 Run，增量以派生 Run 为 “+0 · 0%”。
- **建议：** 增加参照 Run 选择，默认取基线 Study 的 Run。是否增加，待设计方对 F-R51-3 决定。

#### EM-低2 用户指南中仍把产品称作 FORCE

- **位置：** `docs/USER_GUIDE.md` 第 253、261、287、392、532 行；`docs/USER_GUIDE_ZH.md` 第 206、220、260、347、499、507 行。界面和其余用户文档都用 VALUE。模块 ID（如 `force-perfect-foresight-lp`）不在此列。
- **建议：** 产品名统一改为 VALUE。

### 4.4 需要知道的情况（不计缺陷）

1. **很少放电的储能在 full 追踪下仍比基线慢。** 一个储能的 tranche 超过 128 个时，声明状态只列本阶段报价用到的 tranche，其余合并为一项汇总（`value.storage-tranches-offered-plus-aggregate/v1`，修正 id `r53.bounded-storage-state-record`）；只影响记录，不改调度，128 个以内记录格式不变。内存中的 tranche 年内仍会增长，所以 flat-73 两整年 full 追踪约 6.4 分钟、1.63 GB（修复单元单独运行实测），基线为 3.7 分钟、1.4 GB；readiness 对 full 追踪且选了非内置 storage_cost 模块的 Study 给出警告。若要再缩短，需要合并 tranche，这会改变 dwell 记账，须由作者决定。
2. **运行前的磁盘和时间估计按内置储能模块校准。** 对第三方储能模块，估计可能偏低，这正是上一条警告的用意；建议先跑短范围，或长运行改用 Summary 追踪。

## 5 加功能角色（add new function to VALUE）

### 5.1 结论

**通过但有问题。** 加功能主路径全部能走通（编写 → 校验 → 下载 → 安装 → 独立草稿启用 → 复制数据包并绑定扩展输入 → 确认实验性 → 保存 → readiness → 两时段与两整年运行 → Inspect 查看扩展结果 → 原地改源 → Rescan → 重跑与对比 → 命名空间冲突 → 停用/重新启用），扩展结果与运行记录逐项对得上。现存 1 项中等缺陷（AF-中1，需要作者决定规则）和 3 项低等缺陷。

### 5.2 已验证可用（附证据）

1. **编写与校验**（完整验收）
   - Modules → add new function，填 ID `fin-af-observer`、命名空间 `local.fin-af`、研究问题；校验前下载按钮不可用，校验后显示完整清单（数据角色、钩子 initialize/after_psm、结果模式、包身份 SHA-256），下载得到 `fin-af-observer-0.1.0.zip`（含 README、示例 CSV、schema、源码）。
   - 高级清单编辑中加 `after_investment` 钩子、加未支持的摘要字段、只改清单名称，三种都被拒绝并说明原因。
   - 编写台和生成的 README 写明 Run 记录的范围：initialize 返回的状态和 after_psm 返回的产物（修复单元检查）。
2. **安装**：不勾选信任时安装按钮不可用；安装后卡片显示 `local bundle · enabled`、实验性和包身份（完整验收）。
3. **独立草稿**
   - “Open independent Study draft” 复制当前选中的 Study（`VALUE 101 baseline · extension study`），在 Advanced → Optional domains 勾选扩展；Data 页出现扩展角色 `local.fin-af.audit-input`；“Copy data pack for this draft” 生成独立包并自动选中；上传示例 CSV 后 26/26，校验通过（有警告）；未勾选实验性确认时报 `GF_EXTENSION_ACK_REQUIRED`，勾选后保存，Study 记录 `selected_extensions` 和 `extension:fin-af-observer@0.1.0` 确认（完整验收）。
   - 再从同一基线打开第二个草稿，默认名为 “VALUE 101 baseline · extension study 2”；用已有名称新建时返回 409 `GF_STUDY_ID_EXISTS` 并提示改名（定向验证）。
   - Studies 和 Data 页在草稿语境下显示 “Independent Study draft”（修复单元检查）。
4. **运行**：两时段 readiness Ready，运行完成；两整年（35,040 时段）约 3 分钟完成，scientific validation 通过，能量平衡通过，无 stress。Run 头部显示 `Experimental extension: fin-af-observer 0.1.0`（完整验收）。
5. **扩展结果**：Inspect → Artifacts & provenance 的 “Extension artifact summaries” 显示冻结扩展、年份筛选、冻结模块图和扩展图哈希；两整年 Run 有 2025、2026 两条 `local.fin-af.year-summary`。每年的 `source_inputs_sha256` 与 `orchestrator-events.jsonl` 中该年 `psm.run` 的 `input_state_sha256` 一致（2025 `bdc988c9…`，2026 `04ab4350…`）（完整验收）。
6. **启用状态下原地改源**（完整验收）
   - 改 `installed-extensions/.../hooks.py` 后，卡片显示 “Source changed since install (… 8712394f… → 4887cb03…)”；未 Rescan 时 readiness 只报一条 `GF_PREFLIGHT_EXTENSION_SOURCE_RELOAD` 并建议 Rescan。
   - Rescan 返回 `reloaded_extensions`；之后 readiness Ready，带 `GF_PREFLIGHT_EXTENSION_SOURCE_CHANGED` 和 `GF_PREFLIGHT_REVISION_REIDENTIFY`（写明结果可能变化）。
   - 重跑后 Study 追加修订 2（原因 `source-reidentify`），新 Run 的 year-results 含新字段，钩子源码哈希为新值；对比两次两整年 Run，只有 `extensions.hook_source_identities` 一个维度不同。
7. **改坏与隔离**：钩子中加语法错误后 Rescan，health 为 `degraded`，隔离面板写明 `GF_EXTENSION_HOOK_IMPORT`、行号和清单文件；readiness 只报一条 `GF_PREFLIGHT_MODULE_QUARANTINED`（完整验收）。
8. **命名空间冲突**
   - 编写台对已占用的命名空间（本地 `local.fin-af`、内置 `value.toy-audit`）在校验阶段拒绝；用 `scripts/build_extension_bundle.py` 重建的冲突包在安装时返回 409 `GF_EXTENSION_NAMESPACE_COLLISION`；Python 包名重复时返回 409 `GF_EXTENSION_SOURCE_COLLISION`（完整验收）。
   - 冲突提示先给“另取命名空间并重建”；停用占用者一项注明只在它没有被 Study 或保留的 Run 使用时可行（修复单元检查）。
9. **停用与重新启用**（完整验收）
   - 未被引用的扩展可以停用；停用后另一个扩展可以占用它的命名空间，此时重新启用被 409 拒绝并说明原因；停用占用者后重新启用成功，并提示重新检查 readiness。
   - 被 Study 和 Run 引用的扩展：卡片 Disable 不可用并说明原因，API 返回 409 `GF_EXTENSION_IN_USE`（列出 Study 和 Run）；Remove 未停用的扩展返回 `GF_EXTENSION_REMOVE_ENABLED`；停用后的 Remove 有确认框，文件移到 `disabled-manifests/removed/`。
   - 停用确认框和 readiness 对扩展写“在 Study 中取消选择该扩展（另存修订）”（修复单元检查）。
10. **本地开发的扩展**
    - 按 README 解压、改 ID、命名空间和包名，用构建脚本重建，安装、建 Study、两整年运行都成功（完整验收）。
    - 其他钩子（如 after_cem、finalize）返回普通值时照常运行；若返回带 `artifact_type` 的产物，Run 明确失败，`diagnostics/error.json` 写明 VALUE 只记录 after_psm 的产物（定向验证）。
11. 全部页面没有 pageerror；控制台错误只有预期的 409 响应（完整验收）。

### 5.3 现存缺陷

#### AF-中1 原地改过钩子源码的扩展，停用后不能直接重新启用

- **现象：** 启用状态下原地改源会被接受并记录（见 5.2 第 6 条）。但扩展一旦停用，Enable 要求钩子源码与安装时记录的哈希逐字节一致，否则返回 400 `GF_EXTENSION_SOURCE_CHANGED`。信息写出改动的钩子模块和两条出路：恢复原文件后再 Enable；或改版本号和 Python 包名，用 `scripts/build_extension_bundle.py` 重建后作为新包安装。恢复原文件后 Enable 成功（定向验证）。
- **复现：**
  - 往返：安装扩展 → 原地合法修改 `hooks.py` → Rescan → Disable → Enable → 400。
  - 隔离恢复：被 Study 引用的扩展原地改源后又改坏 → Rescan 隔离 → 隔离面板 Disable → 修好源码 → Enable → 400；Study 的 readiness 停在 `GF_PREFLIGHT_MODULE_DISABLED`。
- **原因：** `gridform_core/extension_bundle.py` 的 `_set_extension_enabled`（第 626–648 行）比较 `hook_source_identities`；模块没有这条限制。文档也不一致：`docs/frontend/EXTENSION_AUTHORING_PHASE5.md` 第 16 行写“重新启用校验原 hook 身份”，`docs/MODULE_DEVELOPER_101.md` 第 12 节 “Same ID after a fix”（第 568–571 行；中文版第 552 行）写原地修复后 Enable 或 Rescan，对扩展不成立。
- **影响：** 想保留改动的用户只能以新版本重装，Study 要改选新扩展并另存修订；或者先恢复原文件启用，再改回。不影响任何结果。
- **建议：** 由作者决定扩展是否与模块一样适用 A16-4（接受并记录原地改源）。
  - 适用：`_set_extension_enabled` 改为只校验当前源码能导入、声明的钩子可调用，继续记录新哈希，Run 冻结新身份；
  - 不适用：把 MODULE_DEVELOPER_101 中英文第 12 节对扩展的写法改为“恢复原文件，或以新版本重装”。

#### AF-低1 扩展钩子产物被拒导致 Run 失败时，Runs 页只显示通用错误码

- **现象：** 扩展在 after_psm 以外的钩子返回带 `artifact_type` 的产物时，Run 按设计失败；但 Runs 页只显示 `GF_CONTRACT_001`（“A selected module did not satisfy its declared contract.”），扩展、钩子和“只记录 after_psm 产物”的具体说明只在 `diagnostics/error.json` 中（定向验证）。
- **复现：** 给扩展加 after_cem 钩子并返回带 `artifact_type` 的映射，重建、安装、运行。
- **原因：** `gridform_core/extension_framework.py` 对此抛出 `ValueError`，`gridform_core/errors.py:90` 起的 `public_failure` 把它归为 `GF_CONTRACT_001`。与 EM-中1 同一根因。
- **建议：** 改用带具体公开说明的错误类型（例如 `ContractError` 的子类），或在 Runs 页显示诊断信息的首行。

#### AF-低2 独立 Study 草稿在浏览器刷新后丢失

- **现象：** “草稿 → Data 页复制数据包并绑定 → 返回 Review → 保存”必须在同一页面会话内完成；刷新后回到空白新建表单，没有提示。已上传的数据绑定保存在包中，不会丢。
- **建议：** 保存草稿（浏览器本地存储或服务端草稿）；至少在有未保存草稿时，离开页面前提示。

#### AF-低3 界面中英混排

- **现象：** 研究路径（如“方法学口径”）、Run 的历史复现面板、需求单位说明（“按 MW 读取……”）等是中文，其余界面是英文。设计规格不引入 i18n。
- **建议：** 发布前确定一种界面语言，并统一这些组件的文案。

### 5.4 需要知道的情况（不计缺陷）

1. **扩展的记录范围。** Run 只记录 initialize 返回的状态（扩展命名空间下）和 after_psm 返回的产物（每个模型年一组，在 Inspect 中显示）。其他钩子照常运行但不记录返回值；返回声明产物会使 Run 失败。finalize 在全部年份算完后才运行，所以它返回产物时，要到最后才报错。README、MODULE_DEVELOPER_101 中英文和编写台都写明了这一点。
2. **被保留的 Run 引用的扩展不能停用。** 这是有意设计，用于保留复现能力；`GF_EXTENSION_IN_USE` 会列出引用它的 Run。

## 6 安全与环境核对

- 完整验收与定向验证的每个实例都用 18xxx 端口和全新的 `VALUE_DATA_HOME`，只按记录的 PID 停止自己启动的进程；没有连接作者的实例（8766/8800），没有按模式 kill。
- 每次结束时都核对了只读安装 INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出作者实例的 0 字节锁文件 `.supervisor.lock`，没有 `.pyc`；`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”。
- 测试中的 Run、数据目录和浏览器配置已删除，只保留脚本和截图（见附录）。
- Python 全部经项目包装器调用，没有向 INTEG 写入字节码。

## 附录 证据位置

| 内容 | 位置 |
|---|---|
| 完整验收（`c204aac`）四份角色报告 | `docs/dev/p0-reports/final-role-reproduce.md`、`final-role-swap-data.md`、`final-role-edit-module.md`、`final-role-add-feature.md` |
| 定向验证（`cbdb69a`）与冒烟 Run | `docs/dev/p0-reports/R5-verify.md` |
| 截图（scratch，未入库） | `scratchpad/build/final_roles/<角色>/shots/`（各 9–10 张）；`scratchpad/build/r5verify/shots/`（15 张） |
| 本报告新编号对应的证据 | RP-低1：`final-role-reproduce.md` 当前缺陷“低等”第 8 条；EM-中1、AF-低1：`R5-verify.md` 第 3 节；EM-低1：`final-role-edit-module.md` 低5、`final-role-swap-data.md` 低 5；EM-低2：本报告撰写时 grep 核对；AF-中1、AF-低2、AF-低3：`final-role-add-feature.md` F-中1、F-低5、F-低6，AF-中1 的现状见 `R5-verify.md` 第 1 节 |

各项修复的实现、测试和偏差记录在 `docs/dev/p0-reports/R5-1-swap-data-defects.md` 至 `R5-4-add-feature-defects.md`。
