# VALUE 0.7.0-alpha.1 模型实质设定改动简报（给作者）

- 日期：2026-10-06。分支 `fix/review-2026-10-04`，对照 `main`（35aadb3，即 0.6.0-alpha.2 的源码）。
- 范围：只写**改变模型数值或模型设定**的改动。纯软件、安全和界面修正只在 2.3 节用一行带过。
- 依据：`git log/diff main..fix/review-2026-10-04`；`docs/dev/P0_DECISIONS.md`（Q1–Q15、A1–A18）；`docs/release/P0_GOLDEN_DELTA.md`；golden 数值报告 `tests/golden/reports/D4-r9.json`、`D5-r1.json`；`docs/dev/GBP1_DOCTORAL_BEFORE_AFTER.md`；`docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md`；`docs/dev/p0-reports/` 中的各单元报告（修复轮为 FX1–FX7）；`docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md`；`docs/handoff/FOUR_ROLE_TEST_REPORT.md` 第 9 节（修复轮复测）。第 6 节的 VALUE 101 数字是为本简报新跑的，跑法见 6.5 节。
- **修复轮更新（2026-10-06，A16）**：四类用户测试之后的修复轮（FX1–FX7，HEAD 至 `be30884`）新增的实质改动已并入下文，用“修复轮”标出：U12、U13（2.2 节）、2.3 节末段、C25–C26（第 3 节）、3.5 节（A18，已决定、未实施）、4.2 节核电路径依赖、第 5 节、6.6 节（GBP1 修正口径本地全年验收）。VALUE 101 two_year 的数值在修复轮中不变（6.2 节说明 5）。
- 两个口径：**论文复现口径** `doctoral-lineage-0.6.0a2`（界面标签 “Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)”）；**修正口径** `value-corrected`（新 Study 的默认口径）。下文的 finding 编号（P4-01 等）取自审查报告 `VALUE_review_2026-10-04.md`，correction id（`p07.thermal-net-revenue` 等）取自方法学目录 `gridform_core/data/methodology/corrections/*.json` 与 `docs/release/VERSION_LEDGER.json`。

## 1 一段话总结

本轮把 VALUE 分成两个口径。**论文复现口径**冻结在 35aadb3 的调度与投资行为上，只接受你批准的少数例外，也就是“两个口径都改”的修正：互联线序列逐期对齐（P6-24）、GBP1 的三个读取错误（比利时价格币种与时间分辨率 P6-02、BE/NL 潮流文件对调 P6-03、夏令时后需求错位 P6-04）、火电投资净收入扣除运行成本（A4），以及只改核算、不改轨迹的修正：缺电 stress 记账、能量平衡边界、物理运营成本、成本账 v2、验证门控。**修正口径**在此之外还改了五类设定：默认 PSM 的出清与储能规则（P0-6）；风光可用出力，即文献损耗系数、ERA5 时间约定和光伏倾斜面；核电与径流水电的可用率（P0-5b、F2）；储能扩容余量（P0-7）；网络模块的经济口径（P0-8）。下面三项论文设定**没有改**：风光储没有 OPEX，投资判据不折现，缺电时段的调度方式不变。在 VALUE 101 两年算例上，论文口径的出力、价格、储能和排放与 35aadb3 逐位相同，只是不再新建 13.05 MW 不赚钱的 CCGT。两年系统成本下降 2.17%，其中 A4 贡献 −1.72%，A7（风光储 FOM 移出头条）贡献 −0.45%。这次运行的储能原始不变量失败（单期放电可达 2 倍额定功率，DEV-STO-01），所以按 Q14 年度结果不在结果页发布。修正口径（默认配置）的两年系统成本下降 2.06%，CCGT 发电量和排放各下降 0.6%，电池从几乎不调度（两年放电 0.36 MWh）变为两年放电 5,208 MWh，也不再新建 CCGT。这背后是两个方向相反、大小相近的变化：新市场规则使 CCGT 发电减少 11%，风光损耗系数又使它增加 12%。在 GBP1 上（论文口径，第一年），读取修正使进口减少 78%，价格尖峰消失，系统成本下降 3.2%，排放增加 3.4%。

**修复轮（A16）**在此之上又改了三处数值或设定：VoLL 两个口径都改为 17,000 £/MWh（只进成本账，所有 golden case 都没有记录切负荷，头条成本不变）；修正口径的互联线进口进入日前出清（方法改动，旧 Study 须确认；VALUE 101 不变，GBP1 修正口径第一年进口 0.33 → 1.56 TWh、系统成本 −25.6 百万英镑）；储能的真实报价写进市场账本的新核算表 `storage_orders`（不改轨迹）。另有三项不改数值、但改变“哪些 Run 能跑、能发布”的修正：带扩展的 Run 不再因状态链误判而扣发年度结果（F-D1）；一日课程选了扩展时预检阻断（F-D2）；原地改已安装模块的源码被接受并记录新哈希（M-D2）。GBP1 修正口径的本地全年验收（public2，2025 年）已经做了：水电 6.06 TWh，对 DUKES +5.1%，通过；风光 CF 为 DUKES 的 1.43/1.24/1.09 倍（陆上/海上/光伏）；**核电只发 2.02 TWh，比 Energy Trends 低 95%**，原因是核电启动成本带来的路径依赖，不是可用率。你已在 A18 决定修正口径的核电从第 0 期起在运，**这条还没有实施**（3.5 节）。仍需你审核的数据只剩 DUKES 对照列、几个回退值和第 5 节列出的施工参数；光伏倾斜面的模型选择（A13）你已在 A16-6 直接认可。

## 2 两个口径都改（universal 修正）

这些是 Q1 严格冻结的例外。按 Q12，doctoral golden 的 trajectory 区只在你批准的白名单 finding 下变化，每个 case 只重基线一次，并附数值报告（`tests/golden/doctoral_trajectory_rebaselines.json`）。

### 2.1 改变调度或投资轨迹的修正

| # | 改了什么 | 为什么 | finding / 决策 / correction id | 主要文件 | VALUE 101 two_year 实测 | doctoral golden delta |
|---|---|---|---|---|---|---|
| U1 | 保留内核的互联线序列改为按运行时钟**逐期**取值，第 p 期取第 p 行，每条 Connection 只接本国序列 | 内核的 `IterLimit_new` 把每个值用两次，第 p 期取第 p//2 行。全年只用到 1 月 1 日至约 7 月 2 日的数据，并把它拉伸到全年 | P6-24；Q9/A3；`p05.interconnector-clock` | `gridform_core/builtin/scheme_c_1000twh/kernel_boundary.py`（新）、`runtime_compat/modular_simulation_model.py`（输入块与逐期赋值）、`scheme_c_native_psm.py`、`gridform_core/series_reader.py` | **0**：101 包的十条市场序列全部为常数，BE/NL/IE/NO 文件逐字节相同，测不出这一项 | D1–D4：0。D5（GBP1）：与 U2–U4、U6 合并重基线一次，即 r1（trajectory/accounting/identity 列数 377/639/64），数值见 6.4 节 |
| U2 | GBP1 比利时价格读 EUR 列，按 1.1 EUR/GBP 换算，并由逐小时展开为半小时 | 原读法：canonical 路径把逐小时 EUR 当作半小时 GBP；保留内核读到第一列国名，价格全为 0 | P6-02；A5；`p05.belgium-price-currency` | `series_reader.py`、`gridform_core/data/validation/known_data_objects_v1.json`（按 sha256 登记的对象语义） | 0 | D5，同上 |
| U3 | 互联线潮流文件按 NESO 线路身份接线（BRITNED→荷兰，NEMO→比利时 …） | BE/NL 两个潮流文件对调。35aadb3 的内核中，荷兰线接的是比利时文件，报价全年为 0，成了免费进口源，一年进口 1.34 TWh；爱尔兰线接的是荷兰文件 | P6-03；A5；`p05.boundary-identity` | `gridform_core/interconnector_identity.py`（新）、`known_data_objects_v1.json`、`kernel_boundary.py` | 0 | D5，同上 |
| U4 | GBP1 需求与预测对齐 UTC：删去 2022-10-30 的重复行 14495、14497，并插补 14514、14542 两处缺口 | 夏令时结束后，需求整体比 UTC 提前 1 小时（共 2,956 期） | P6-04；A5；`p05.demand-utc-clock` | `series_reader.py`、`known_data_objects_v1.json` | 0（101 包本来就是 UTC） | D5，同上（全年需求 +5,407 MWh） |
| U5 | 声明了 `csv_column` 的序列，在任何读取模式下都按声明的列读；隐式选中的整数序号列报错 `GF_DATA_INDEX_COLUMN` | R029 研究包的互联线价格和潮流被读成期序号 0..17519 | P6-01；`p05.declared-column` | `series_reader.py`、`canonical_psm_data.py` | 0 | D1–D5：0（GBP1 public1 没有声明 `csv_column`）。只影响 R029 类数据包 |
| U6 | **火电投资净收入恢复原 Scheme C 规则**：燃气、生物质，以及任何带燃料或碳成本的资产，净收入 = 市场收入 − 发电量 × gen_cost（发电 + 燃料 + 碳价 + 单位时间成本）。风光储仍以毛收入为利润。相对差在 1e-9 以内的净收入按 0 处理 | v2 移植（`v2_module_definitions.py:153`）丢掉了原代码 `runtime_compat/modular_investment_support.py:2150-2152, 2247` 的扣减，CCGT 按毛收入判档。电价等于边际成本时也会扩容：玩具算例中，每 100 MW 判 Invest_High 并新建 10.95 MW | P4-01（只限火电部分）；A4；`p07.thermal-net-revenue`；agent-investment 2.2.0→3.0.0 | `gridform_core/agent_cashflow.py`（新，`value.agent-cashflow/v1`）、`gridform_core/investment_accounts.py`、`builtin/scheme_c_1000twh/v2_module_definitions.py`（decide）、各 PSM 发布运行成本分项（`scheme_c_native_psm.py`、`staged_psm.py`、`perfect_foresight_psm.py`、`network_dc.py`） | 论文口径（D4）：两年提案 21.32 → 8.26 MW（CCGT 13.05 → 0），系统成本 −508,406 £（−1.72%）；出力、价格、排放不变，因为新增的 CCGT 在 101 中只分走原有 CCGT 的出力。修正口径（在 P0-5b 之前单独测量）：CCGT 提案 11.71 → 0 MW，−456,944 £（−1.62%） | D4 r9：trajectory 426、accounting 24、identity 23 列（报告 `D4-r9.json`，A12 已认可）；D1–D3 只有 accounting 列（0/7/4、0/7/4、0/4/2）；D5：CCGT 提案 1,773.8 MW → 0 |

### 2.2 只改核算、验证或发布、不改轨迹的修正（Q12 accounting 区）

| # | 改了什么 | 为什么 | finding / 决策 / correction id | 主要文件 | VALUE 101 two_year 实测 | doctoral golden delta |
|---|---|---|---|---|---|---|
| U7 | **缺电 stress 事件（A2）**：在声明的能量平衡边界上，逐期记录缺口 `shortfall_mwh` 和 stress 标志，按年把连续时段分组成事件；能量平衡账把缺口记作“缺电量”，使账目闭合。run status、摘要和 replay 窗口公开 `stress_periods`、`shortfall_mwh`，新增全年事件列表。**调度不变** | P3-01：日前满足不了预测时，内核按 forecast−real 削减，缺电被记为 0，用户看不到 | P3-01；A2；`p04.surplus-routing`、`p04.surplus-node-boundary` | `gridform_core/energy_balance_contract.py`、`energy_balance_oracle.py`、`market_ledger.py`、`data/contracts/market-ledger-energy-balance-v1.schema.sql`（表 `balance_boundary_period`、`stress_event`）、内核中的只读钩子 | 两个口径都是 0 个事件、0 MWh。35aadb3 的账本没有声明边界，只能给出上下界（D4 两年为 0 到约 8 万 MWh，C6 为 0 到约 4.8 万 MWh），现在是精确的 0 | D1–D4 只有 accounting 列；D5：157 个事件、890 个时段、缺口 300,855 MWh |
| U8 | 能量平衡按声明边界计算：论文口径为 `default_psm_surplus_node_v1`，修正口径为 `native_corrected_full_node_v1`；W_in 作为 `non_vre_spill` 单列；兼容调整只吸收数值噪声；逐资产储能审计 | 原兼容调整没有上限，把原始残差强制归零，所以账本、校验器和 parity 只看到 0；储能充电没有入账 | P7-10/P3-02、P3-14/P5-11；Q7；`p04.surplus-node-boundary`、`p04.storage-energy-audit` | 同上，另有 `builtin/scheme_c_1000twh/native_balance_audit.py` | 原始残差与兼容调整两年都是 0（两个口径） | D1–D4 accounting 36–90 列 |
| U9 | **验证与发布规则**：stage parity v3、scientific validation v2 都由实际执行的检查重新计算；新增三类 gate，即 run 不变量、能量平衡账、储能吞吐不变量（额定功率、不同期充放、0≤SoC≤E、审计恒等式）。论文口径用已声明偏差解读 gate（DEV-BAL-04、DEV-STO-01），**年度结果只在原始不变量全部通过时才在结果页发布**（Q14），否则只在 Inspect 和导出中提供。修正口径只要有一个 gate 失败，就阻止发布年度经济结果（`GF_VALIDATION_GATE_FAILED`） | P7-01：原生路径的 parity 是硬编码的 passed；P7-10 同上 | P7-01、P7-10；Q14；`p04.validation-v2`、`p04.validation-gate`；`gridform_core/data/methodology/declared_deviations.json` | `scientific_validation.py`、`parity.py`、`run_invariants.py`、`declared_deviations.py`、`result_advisories.py` | 论文口径（D4）：由 v1 的 “passed” 变为 `reproduction_with_declared_deviations`；原始不变量 failed（储能 DEV-STO-01），**年度结果在结果页扣发**。修正口径（C5、C6）：passed，正常发布 | D1–D4 accounting 55–249 列 |
| U10 | **物理运营成本**：运营成本 = Σ 运行成本 × 出力（不乘 bid multiplier）+ 进口 + 启动加价 + 记录的缺电 × VoLL + 储能循环磨损。储能报价支付改为结算转移单列。VoLL 两个口径都是 17,000 £/MWh（A16-5，`fx5.voll-17000`）：论文口径为常数（论文代码原为 8000），修正口径取 `market.voll_gbp_per_mwh`（默认 17,000，原为 10000） | 原运营成本把储能报价支付（含 holding 资本回收）算进去，又加一次循环磨损，重复计入；而且不含 VoLL | P5-06；`p06.physical-operating-cost`；value-bid-at-cost-psm 6.0.0 | `scheme_c_native_psm.py`、`runtime_compat/modular_simulation_model.py`、`native_realisation.py` | 论文口径：0 £。修正口径（dynamic 储能）：−19 £，因为旧规则下电池几乎不放电 | D1–D4 accounting 26–35 列；D5：运营成本 −25.28 百万英镑 |
| U11 | **成本账 v2（A7）**：风光储的固定 OPEX 视为已含在平准化 CAPEX 中，移出头条，作为 memo 行列出。完全预见 PSM 的火电 FOM 改读 `annual_fixed_opex_gbp`（原来读的键从未被写入，FOM 恒为 0） | 避免在平准化 CAPEX 之外重复计入风光储 FOM | A7；`p07.cost-ledger-v2` | `gridform_core/cost_ledger.py`、`asset_economics.py`、`application.py`、`backend/model_runner.py`、`perfect_foresight_psm.py` | 两个口径每年 −66,000 £（101 包的储能 FOM 转为 memo） | D1/D2/D4 accounting 20 列，D3 4 列；D5：−56.66 百万英镑 |
| U12 | **修复轮：储能报价账本（M-D1）**。市场账本新增核算表 `storage_orders`：每条储能报价一行，不论是否被接受，记报价（储能成本模块的 `bid_price_gbp_per_mwh(dwell)` × 报价乘数）、可报电量、接受量、状态与原因码（`accepted/cleared`、`partially_accepted/demand_filled`、`rejected/no_energy_delivered`、`rejected/merit_order_not_reached`），`clearing_offer_id` 与 `clearing_inputs` 一一对应。原 `orders` 表一行不动，电池行仍是 0.0 价的净调度记录 | 原 `orders` 只登记发电机报价，放电电池只有一行 0.0 价的 `final_dispatch`，没被接受的储能报价完全不写；改储能成本模块的人无法从账本核对报价公式 | M-D1；A16-1；Q12；`fx4.storage-offer-ledger`；value-bid-at-cost-psm 6.0.0→6.1.0（代码身份，不需确认） | `builtin/scheme_c_1000twh/native_storage_orders.py`（新）、`runtime_compat/modular_simulation_model.py`（5 个只读钩子）、`market_ledger.py`、`data/contracts/market-ledger-storage-orders-v1.schema.sql`（新） | 0（只写 full trace；two_year 是 summary trace，不写这张表） | D3、C3 各一次 accounting 修订（20 列），trajectory 0；其余 case 只有 identity。修正口径按净头寸结算，同期回购时报价接受量之和 ≥ `orders` 电池行（复测 M2-N5：表中没有字段标出回购） |
| U13 | **修复轮：VoLL 17,000 £/MWh（A16-5）**。两个口径都按 17,000 £/MWh（半小时 8,500 £/MW·时段）给记录的切负荷计价：论文复现规则集 `reliability_voll = constant_17000`（忽略参数）；论文代码成本表 `runtime_compat/case3.py`、`modular_case3.py` 和原论文成本视图改为 17,000；参数 `market.voll_gbp_per_mwh` 默认值 10,000 → 17,000，完全预见 LP、参考 DC 网络、分阶段链、doctoral national PSM 一并跟随 | 论文代码用 8,000，参数默认 10,000，分区研究 17,000，三处不一致；作者口径为 17,000 | A16-5；Q12；`fx5.voll-17000`（论文口径为通用核算修正，不进修正目录）；五个读该参数的 PSM 槽模块升版本并要求确认（Q13）：value-bid-at-cost-psm 6.2.0、perfect-foresight-lp 1.1.0、staged 1.4.0、reference-dc-network 1.2.0、doctoral-national-psm 0.3.0 | `gridform_core/voll.py`（新，唯一常数）、`native_market_rules.py`、`parameters.py`、`doctoral_ledgers.py`、`study_market_config.py`（旧默认 10,000 且无显式参数时重新投影为 17,000） | **0**：两个口径都没有记录的切负荷，`blackout × VoLL` 为 0。默认 PSM 内核不读 VoLL，调度不变。完全预见 LP、DC 网络和分区再调度中 VoLL 是目标系数，依赖旧默认值的 Study 调度可能变（C7、C8 实测 0） | D1–D5 各一次 accounting 修订（2 列：VoLL 值与依据），C1–C6 各 1 列，trajectory 0；D5 头条不变（切负荷 0）。A2 的 stress 缺口只按 MWh 报告，不按 VoLL 计入头条（D5 的 300,855 MWh 若计价：17,000 下约 5,114.5 百万英镑） |

### 2.3 一行说明：软件、安全与界面修正

P0-1（本地 API 安全边界）、P0-2（外部模块隔离）、P0-3（Run 生命周期与后台 worker）、P0-9（结果页显示与标签），以及 X0 的口径登记、读时公告和 Study 迁移，都是软件、安全或界面修正，**不改变任何模型数值**。X0 会让旧 Study 在第一次运行前要求确认一次（Q13），但不改变数值。`p05.weather-cache-key`（P7-02，内核天气缓存按文件作键）和 `p05.validation-layers`（P6-11/P6-12，三层数据包校验）同样不改变正常运行的数值：每个 Run 都在自己的进程中运行。

**修复轮（A16）中不改数值、但改变“能不能跑、能不能发布、怎样比较”的修正**（两个口径共用代码；论文复现口径本来就拒绝扩展和外部代码）：

- **F-D1 扩展状态链**（`gridform_core/v2/orchestrator.py`、`run_invariants.py`）：扩展的 initialize 作为状态链上被校验的一环（`value.extension-initialize-link/v1`，记在本次执行的第一年），链为“源状态 → initialize → 年度输入”。修复前，选了扩展的 17,520 期 Run 必然在 `run.state_chain` 失败，修正口径的年度经济结果被扣发。复测：带扩展的 two_year Run 科学验证 passed，年度结果发布，剔除扩展键后，与不带扩展的对照 Run 的年度结果、成本账、碳账、能量平衡和 market.sqlite 都相同。不带扩展的 Run 逐字节不变。
- **F-D2 一日课程与扩展**（A16-3）：`value_101_day` 只跑市场步骤，选了扩展时预检以 `GF_PREFLIGHT_SCOPE_SKIPS_EXTENSIONS` 阻断（API 直接启动同样被拦）；范围下拉框标 “(extensions do not run)”；比较页不再把“记录了但没执行”的扩展判为方法改变；Inspect 说明扩展在此范围不执行。一日路径的执行语义没有改（是否让一日课程调用扩展 hook 属于方法问题，未决）。
- **M-D2 原地修改已安装模块的源码**（A16-4）：接受并记录。预检给琥珀色提示（新旧源码哈希前 8 位），Run 记录新哈希，比较页显示“模块方法已改变”；开发者文档改为允许这种做法。
- **界面（设计规格第 11 节）**：Readiness 卡片不再截断，按六组列出全部问题；Data 页每个数据包有三层校验与口径资格面板；论文复现口径扣发年度结果时写明失败的原始不变量和命中的声明偏差（如 DEV-STO-01），状态条新增 `Raw invariants` 字段；Modules 页常驻 “Disabled and quarantined” 区（Enable / Rescan / Remove）和全局 “Rescan modules”；映射编辑器可声明时间戳列（UTC 或 Europe/London，逐行检查重复、缺口、倒序），列名含 EUR 而币种选 GBP 时给琥珀色提示；互联线数据角色改名为 “<Country> interconnector availability (+ import / - export)”。
- 复测（`FOUR_ROLE_TEST_REPORT.md` 第 9 节）：四类用户都通过，没有剩下高严重度缺陷。仍有三个中等问题：N-1（校验面板说用户包可用于论文复现口径，但 Study 编辑器按白名单拒绝）、N-2（Europe/London 时间戳在秋季重复小时只出现一次时，映射预览报 500）、F2-N1（全年范围的扩展结果超过 16 MiB 上限，Inspect 看不到，可从 Artifacts 下载）。

## 3 只改修正口径（profile-gated 修正）

论文复现口径不应用下列任何一项。“VALUE 101 实测”一列取自第 6.3 节的分步运行（C6，即默认的 dynamic 储能配置）。

### 3.1 数据与可用出力（P0-5a、P0-5b、F2）

| # | 改了什么 | 为什么 | finding / 决策 / correction id | 主要文件 | VALUE 101 two_year 实测 | 其他数据包 |
|---|---|---|---|---|---|---|
| C1 | ERA5 时间约定（天气 v2）：累积量（`ssrd`）第 t 期取标在第 t//2+1 小时的值，瞬时量取离时段中点最近的 (t+1)//2；论文口径仍为 t//2 | `ssrd` 是“小时结束”累积量，原读法按“小时开始”使用，光伏整体滞后约 1 小时 | P6-06；`p05.weather-time-convention` | `gridform_core/site_weather.py`（新）、`doctoral_weather.py`、`canonical_psm_data.py`、`builtin/scheme_c_1000twh/kernel_injection.py`（新） | 与 C2 合并测量，见 C2 | GBP1 伦敦站光伏质心 12.97 → 11.97 UTC；冬至首个非零时段 09:00 → 08:00 |
| C2 | **风光文献损耗系数**，乘在 ERA5→功率曲线换算之后：陆上 0.90307，海上 0.814968，光伏 PR 0.83。**不做统计标定**，逐期形状仍来自 ERA5，弃电仍由出清决定 | 风电 CF 明显高于实测负荷率（GBP1 陆上约 44.6%，海上约 60.3%） | P6-08；Q15、A1、A9；`p05.vre-loss-factors` | `gridform_core/data/weather/value_uk_vre_loss_factors_v1.json`、`site_weather.py`、`kernel_injection.py` | C1+C2：CF 陆上 0.4132 → 0.3731，光伏 0.2500 → 0.2075；两年风光可用量 −13.3%；CCGT 发电 +12.0%；排放 +12.0%；需求加权时段平均成本 25.29 → 28.24 £/MWh；两年系统成本 +1,480,346 £（+5.23%） | GBP1 CF：陆上 0.4458 → 0.4026，海上 0.6028 → 0.4913，光伏 0.1201 → 0.0997。陆上、海上仍为 DUKES 2020–2024 均值的 1.56 倍和 1.23 倍（A9：只披露，不标定） |
| C3 | 光伏倾斜面换算：逐时段 ERA5 GHI → Erbs 直射/散射分解 → Hay–Davies 换算到朝南斜面（反照率 0.2，倾角取 Jacobson & Jadhav 文献最优值），再乘 PR 0.83 | PR 按组件平面辐照定义，直接乘在水平面 GHI 上会漏掉倾角增益 | A13；`p05.solar-plane-of-array` | `gridform_core/solar_irradiance.py`（新）、`site_weather.py` | **0**：101 的合成天气不是 ERA5 累积量，不做换算 | GBP1 光伏 CF 0.0997 → 0.1065（DUKES 的 1.04 倍）。倾角取纬度时为 0.1012 |
| C4 | 核电按站使用 2019–2024 年 PRIS 平均负荷率，作为固定降额：Heysham 1 0.668、Hartlepool 0.689、Heysham 2 0.752、Torness 0.792、Sizewell B 0.801；退役精确到月，Heysham 2、Torness 为 2030-03；不做年际波动 | 原来核电按 100% 可用率运行 | P5-10；A10、A14；`p05.firm-availability`、`p05.nuclear-generation-end-month` | `gridform_core/firm_availability.py`（新）、`gridform_core/data/nuclear/value_uk_firm_availability_v1.json`、`kernel_injection.py` | 0（101 没有核电） | GBP1 public2 修正口径 2025（修复轮 FX7，经 C26 按站）：可用率上限 38.26 TWh，对 Energy Trends 5.1 +2.5%；**实际只发 2.02 TWh（−95%）**，原因是启动成本路径依赖（4.2 节、6.6 节），不是可用率 |
| C5 | 径流水电：年负荷率 0.3487（DUKES 6.3，2019–2024 均值）× 由季度数据推出的阶梯形状 `[1.3851×3, 0.6582×3, 0.6776×3, 1.2791×3]` | 原来按 2000 MW、零成本、全年 100% 可用调度，约 17.5 TWh，实际约 5 TWh | P5-09、P6-10；A14；`p05.firm-availability`、`p05.hydro-dukes-load-factor` | 同 C4 | 0（101 没有径流水电） | GBP1：6.10 TWh，DUKES 6.2 2019–2024 均值为 5.77 TWh（+5.8%，在 ±15% 以内） |
| C6 | 声明式读取：表头推断、分辨率先于截取、闰年删 2 月 29 日、短序列只在声明为 cyclic 时回绕；数据门 fail-closed | P6-05（无表头文件吃掉首行）、P6-07（短窗口把半小时当小时）、P6-11（缺陷数据包照常运行） | `p05.declared-reader`、`p05.series-clock`、`p05.data-gate` | `series_reader.py`、`gridform_core/data_method.py`、`data_validation_layers.py` | two_year：0。smoke 模式下 VRE 扩容余量变化（C1/C2/C4 各 8 个 trajectory 列） | **发布版 GBP1 public1 不满足修正口径的资格**（预检报线路身份、币种、时区错误），修正口径要用本地构建的 public2 |
| C7 | 互联线进口报价和出口价保留负价 | 原来被截断为非负 | 计划 4.5 第 7 点；`p05.raw-boundary-price` | canonical 适配器 | 0 | — |
| C26 | **修复轮：GBP1 public2 本地登记与逐站核电**。`value-uk-open-data-pack-public2` 在代码中登记为 scientific_reference（修正口径按 `declared-v2+declared-v2+strict` 读取；论文复现口径仍拒绝它）；public2 加入核电政策名单，修正口径下取得五个 EDF 电站（各自 A14 负荷率、按月退役）以及外生的 HPC、SZC 管线项目。构建器 `@v2` 把三条逐时 VRE 投资曲线声明为 60 分钟 | 原来逐站规则只作用于 GBP1 public1，而 public1 不满足修正口径资格，逐站规则在任何合格的修正口径运行中都用不上；public2 按单一 `Nuclear` 取全国回退值 0.723 | P5-10；A16-7；`p05.nuclear-stations-public2`（profile_gated，只对 public2） | `methodology.py`（`KNOWN_PACK_CLASSES`）、`pack_source_identity.py`、`nuclear_policy.py`、`scripts/build_value_uk_pack_revision.py` | 0（101 包不受影响，golden 全部 gated 0） | GBP1 public2 修正口径 2025：核电 1.96 → 2.02 TWh，系统成本 −1.64 百万英镑，其他指标变化都在千分之一以内（核电基本没运行，见 4.2 节）。public2 只在本地构建，**未发布、未上传** |

### 3.2 默认 PSM 的出清与储能规则（P0-6；value-bid-at-cost-psm 6.0.0，规则集 `native-corrected-v1`；修复轮后为 6.3.0）

九条规则一起激活（golden 修订 C6 r4），所以只能合并测量。修复轮的 C25（日前进口）是之后单独加的，另行测量。模块版本在修复轮中依次升为 6.1.0（FX4 账本，代码身份）、6.2.0（FX5 VoLL，须确认）、6.3.0（FX6 日前进口，须确认）。

| # | 改了什么 | 为什么 | finding / 决策 / correction id |
|---|---|---|---|
| C8 | D1-surplus：日前结束后，按“可用 − 接受”逐来源重建盈余簿。必发盈余在调度内，先被使用；VRE 盈余被储能、出口、电解或平衡需求消耗时，计为 VRE 毛出力；平衡阶段不再重复计入必发盈余 | DEV-BAL-04（核电盈余重复计入）；VRE 盈余在账上消失 | P5-04、DEV-BAL-04；`p06.d1-surplus-accounting` |
| C9 | 排序键 `(round(price,2), is_storage, price, 输入序)`：同一 0.01 £/MWh 档内，储能排在发电之后 | 零报价储能挡住风电 | Q8；`p06.storage-after-generation-merit-key` |
| C10 | 下调按“避免成本”降序：先降燃气，后弃风；核电带 100 £/MWh 的 dec premium，排在最后；爬坡下限按上期出力计算 | 原削减市场按 `curtail_cost` 升序，先弃零边际成本的风电，燃气继续运行 | P3-03；`p06.avoided-cost-downward-order` |
| C11 | 每台电池每期只有一个净头寸：各阶段共享额定功率；已放电的电池先回购，才能充电；同一期不能既充又放 | 同一时段可以先放、再充、再放，单期放电可达 2 倍额定功率 | P5-03；`p06.storage-net-per-period` |
| C12 | 储能费在本期结算 | 论文代码把上一平衡期的储能费带进后面的削减期 | P5-06；`p06.storage-fee-per-period` |
| C13 | 出清前不再从 VRE 分流去电解 | 每个 VRE 代理最多 1 MW 分去电解，容量不足时这部分能量消失 | P3-08；`p06.no-vre-pre-clearing-skim` |
| C14 | dynamic 储能只报循环折旧：电池报 CAPEX/(E·η_dis·N_max)，抽蓄和氢储能报 0，最老批次先用。holding 回收只用于投资充足性检验 | 报价随存放时长递增，加上 LIFO，电量积压卖不出，1C 电池实际上从不调度 | P5-04；Q8；`p06.storage-bid-cycle-only`；dynamic-annual-storage-cost 2.0.0 |
| C15 | 统一边际价结算：每个阶段所有被接受的供给（含储能、进口）都按该阶段统一边际价结算；充电按当期电价计成本，用弃电充电成本为 0。报价只决定调度顺序 | 储能按自身最高报价 `max_bat_price` 结算 | P5-05；A8(2)；`p06.storage-uniform-price-settlement` |
| C16 | VoLL 取参数 `market.voll_gbp_per_mwh`（默认 17,000，A16-5） | 常数 17,000（A16-5 前为论文常数 8000） | `p06.voll-chronology-parameter` |
| C25 | **修复轮：**互联线进口进入日前出清：每条正容量互联线按当期对侧价格 × 报价乘数、以可用进口量报价，与本国机组同一排序；平衡环节只报日前剩余的进口容量；日前接受的进口在下调时按进口避免成本减少，不付削减费。value-bid-at-cost-psm 6.3.0，旧 Study 须显式确认（Q13）。VALUE 101：法国 82 £/MWh 比 CCGT 66.5 贵，全部拒绝，数值不变。GBP1 第一年（本地 public2，修正口径）：进口 0.331 → 1.560 TWh，CCGT −1.27 TWh，头条系统成本 −25.6 百万英镑 | 论文内核的日前出清不接收互联线，进口只在实际需求超出日前计划时的平衡环节出现（四类用户测试 S-D3）。GBP1 D5（论文口径）的 0.336 TWh 进口全部发生在实际需求高于预测的 1,130 个时段；这一点在论文复现口径中**不变** | S-D3；A16-2；`fx6.day-ahead-interconnector-imports`（2026-10-06 FX6 新增，只在修正口径）。进口报价按 `external_price × 报价乘数`，与平衡环节一致；`orders` 中进口记为 `ahead_offer` 行 |

- **主要文件**：`builtin/scheme_c_1000twh/native_corrected.py`（新）、`native_market_rules.py`（新）、`runtime_compat/storage_cost.py`、`runtime_compat/modular_simulation_model.py`（按规则字段分支）、`scheme_c_native_psm.py`、`gridform_core/storage_recovery.py`、`corrections/p06.json`。
- **列语义随之改变（C20）**：修正口径的 `vre_accepted` 是 VRE 毛出力，`curtailed` = 可用 − 毛出力（真正的弃风弃光），`excess` 是非 VRE spill。所以两个口径的 VRE 与弃电列不能直接相比。
- **VALUE 101 two_year 合并实测**（C6，从 3537374 到 5014b7b，此时还没有损耗系数和 P0-7）：两年系统成本 −1,445,951 £（−4.86%），其中运营成本 −10.4%；CCGT 发电 −11.3%；排放 −11.3%；需求加权时段平均成本 28.21 → 25.29 £/MWh；电池两年放电 0.36 → 6,312 MWh，市场收入 21 → 275,598 £；CCGT 提案 13.19 → 11.71 MW。CCGT 减少的主要原因是 C10（先降燃气）和 C14、C15（电池开始调度）。
- 不变：日前满足不了预测时的出清方式（A2，两个口径都不改）。

### 3.3 投资与成本账（P0-7）

| # | 改了什么 | 为什么 | finding / 决策 / correction id | 主要文件 | VALUE 101 two_year 实测 | 其他数据包 |
|---|---|---|---|---|---|---|
| C17 | 储能扩容余量取“现有储能充电之后剩下的盈余”（PSM 逐期发布 `storage_headroom_inputs`）；不满 17520 期时余量为 0，并记录原因 | 原来只用已接受的 VRE 计算，余量恒为 0，内生储能投资被关闭 | P5-01；`p07.storage-leftover-headroom`；value-storage-expansion-policy 5.0.0 | `builtin/scheme_c_1000twh/storage_headroom.py`（新）、`scheme_c_native_psm.py`、`v2_module_definitions.py` | 2026 年电池扩容上限：35aadb3 为 0。P0-6 改了列语义以后，旧公式给出每种电池 0.552 MW。P0-7 之后改为三种电池共用的池，上限 4.065 MW。电池提案 0.418 MW 在 P0-7 之前就已出现，由统一价收入驱动 | — |
| C18 | 三种功率电池共用一个池（cap_fraction × power_room），超额时按比例缩放 | 三种电池各拿全部上限，合计是文档口径的 3 倍 | P5-02；`p07.power-battery-pool` | 同上 | 101 中池上限没有被用满 | — |
| C19 | 径流水电的兼容资本（`existing_stock_compatibility`）移出头条，作为 memo 行 | 2 GW 径流水电按 £200bn 计入资本，占年金化资本的 47.8%（每年约 £10.96bn），扭曲头条系统成本 | P4-03；`p07.compatibility-capital-out-of-headline` | `cost_ledger.py` | 0（101 没有径流水电） | GBP1 类数据包的头条系统成本会大幅下降 |
| — | 储能投资审核**沿用现规则**：ROI = 年市场收入 ÷ 整体 CAPEX，不折现，不扣 cycle cost，不扣 FOM；扩容上限由物理利用率决定，不启用 tier_roi | A8(3)(4) | — | — | — | — |

P0-7 在修正口径上的合计实测（54fe0ed → HEAD，已含损耗系数）：两年系统成本 −647,786 £（−2.18%），全部来自资本：A4 少建的 CCGT 约 −515,786 £，A7 −132,000 £。调度不变；两年提案 22.60 → 9.49 MW。

### 3.4 网络模块（P0-8；论文口径不允许网络模块，Q3，所以这些修正实际只在修正口径中生效）

| # | 改了什么 | 为什么 | finding / 决策 / correction id | 主要文件 |
|---|---|---|---|---|
| C20 | zonal solver contract v4：primary 阶段解出后，先追加 Σshed ≤ shed*，再对 bid 项加数值锁；£1 只作验收上限。v2/v3 合同可以读，但要显式升级 | 后续阶段用尽 £1 松弛，每个再调度时段约 1e-4 MWh 虚假切负荷，出力按资产 ID 偏离成本最优 | P2-01；Q5；`p08.zonal-solver-v4` | `gridform_core/zonal_redispatch.py`、`zonal_solver_contract.py` |
| C21 | staged 下调报价按经济价：燃料机组 SRMC×m_dec − 补贴；风光 −补贴；核电再减 premium；储能 ≤ 自身上调价。同价同方向按可用电量比例分配，并共享类别次序 | 所有 dec 报价恒为 £0：降火电还是弃风由资产 ID 决定，火电还有横财 | P2-05、P3-04；`p08.dec-economic-pricing`、`p08.pro-rata-ties`、`p08.dec-class-order`；新参数 `market.dec_multiplier` 等 | `builtin/scheme_c_1000twh/staged_psm.py`、`copperplate_balancing.py`、`gridform_core/network_method_rules.py` |
| C22 | 网络成本改为与“无网络 LP 反事实”比较，三个情形共用一张逐期单价表 | zonal 与 copperplate 的单价来源不同，调度完全相同也会算出网络约束成本 | P2-03；`p08.network-free-counterfactual` | `zonal_redispatch.py`、`staged_psm.py`、`cost_ledger.py` |
| C23 | 边界边际值取 primary 阶段 LP 对偶（附状态）；旧结果读为 `not_computed` | 原来写死为 0，却标为“诊断性边际价值” | P2-06；`p08.boundary-primary-dual` | `staged_psm.py`、`zonal_results.py` |
| C24 | DC 网络中分布在多个母线上的资产，按份额展开为子资源（容量、功率、能量、SoC 都乘份额），求解后再汇总；份额之和必须为 1 | 原来把整台资产注入最后一个映射母线 | P1-01；`p08.network-share-expansion`；value-reference-dc-network 1.1.0 | `gridform_core/network_dc.py` |

VALUE 101 two_year（copperplate 默认，无网络）：0。VALUE 101 网络教学算例（C8，value_101_day）自修订 0 起有 111 个 trajectory 列变化；VALUE101-NC 边界的边际值为 66.5 £/MWh。另有只做报告的运行期 fallback 审计（P2-13）和 staged 储能 dwell 披露（P5-15），不改调度。

### 3.5 已决定、尚未实施：修正口径的核电开局在运（A18）

**状态：你已在 A18 决定（2026-10-06），截至本简报（HEAD `be30884`）代码还没有改。** 下文是决定的内容和预期影响，不是实测结果。

| 项 | 内容 |
|---|---|
| 规则 | 修正口径中，核电从第 0 期起处于在运状态，按各站可用率（C4）作为基荷运行；启动成本只在换料或停运后重新启动时收取 |
| 为什么 | FX7 发现：默认 PSM 中上一时段没被接受的机组，报价要加 `startup_cost`（GBP1 核电 500 £/MWh），排在所有资源之后；核电直到第 16593 期（12 月 12 日）才第一次被接受，此后一直运行到年底。GBP1 public2 修正口径 2025 年只发 2.02 TWh，统计约 37.3 TWh |
| 身份与确认 | 方法改动：新规则集版本和 correction id，按 Q13 旧 Study 须显式确认；修正族 golden 修订一次，附数值报告 |
| 论文复现口径 | 不变（Q1）。路径依赖按 A15 在方法学中披露（4.2 节） |
| 验收 | GBP1 public2 修正口径一年，核电对 Energy Trends 5.1 在 ±10% 内；重算 FX7 的验收表（6.6 节），并更新本简报与交接文档 |
| 预期量级 | FX7 的诊断性敏感性运行（临时副本中核电 `startup_cost` 设为 0，不是 A18 规则本身）：核电 2.02 → 38.26 TWh（对 ET 5.1 +2.5%），CCGT −33.9 TWh，弃电 +1.31 TWh，出口 +1.10 TWh，时段均价 24.30 → 16.23 £/MWh，头条系统成本 −1,830.7 百万英镑，排放 −13.0 MtCO2，投资提案 −244 MW。修正口径的可用率是固定降额，没有换料或停运日历，所以 A18 实施后的结果预计接近这组数字，但要以实测为准 |

## 4 明确没有改（论文设定）

### 4.1 两个口径共同保留的设定（你的决定）

- **风光储没有 OPEX**：没有可变 OPEX，毛收入即利润；固定 OPEX 视为已含在平准化 CAPEX 中，不进入投资决策和头条成本（A4、A7）。给风光加 OPEX 属于新功能，不在本轮。火电固定 OPEX 维持原状。
- **投资判据不折现**：所有金额以起始年不变币值计价。四档规则：S<0 → Deplete；S/K > preferred_rate → Invest_High；否则回收期 K/S ≤ 目标年限 → Invest_Profit；否则 Do_Nothing。不引入 NPV、IRR 或年金门槛（A6，P4-02 移出范围）。成本核算中的 CRF 年金化只把存量资本摊到各年，不用于折现投资收入。
- **缺电时段的调度不变**：日前满足不了预测时，出力和价格照旧，只记录 stress 事件（A2）。
- **风光不对统计负荷率做标定**：只把模型 CF 与 DUKES 并列披露，并写明偏高原因（Q15、A9）。
- 默认 PSM 的“价格”仍是时段平均成本（Average period cost，£/MWh demand），只改标签，不改算法（Q6）。
- 储能扩容不启用 tier_roi；储能投资审核不扣 cycle cost，也不另扣 FOM（A8）。
- 投资侧 CSV 资源曲线与调度侧天气不一致：本轮只披露，下一轮统一（Q15）。

### 4.2 论文复现口径冻结的行为（Q1；trajectory 与 35aadb3 逐位相同，只有 U1–U6 是例外）

- 风光储按毛收入判档（P4-01 的风光储部分；这是论文设定，不是错误）。
- 储能扩容余量恒为 0（P5-01）；三种电池各拿全部上限，合计 3 倍（P5-02）。
- 储能报价随存放时长递增并按 LIFO 出售，1C 电池几乎不调度（P5-04）；储能按自身最高报价 `max_bat_price` 结算（P5-05）。
- 同一时段可以多次充放，单期放电可达 2P（P5-03，已声明偏差 DEV-STO-01）；平衡阶段重复计入核电盈余（DEV-BAL-04）；削减市场先弃风后降燃气（P3-03）；出清前 VRE 分流电解（P3-08）；储能费跨期残留；每年新建电池、年末 SoC 丢弃（DEV-BAL-03）。
- 天气 v1 时间约定（P6-06）；没有风光损耗（P6-08）；核电和径流水电全年 100% 可用（P5-09、P5-10、P6-10）。核电一旦被接受，就满功率运行到年底（路径依赖，A15：GBP1 上 2.73 TWh 核电在修复后消失，就来自这一点）。机制是：没运行的核电报价加启动成本（GBP1 为 500 £/MWh），排在最后；被接受后报价为 0，又受 `alter_limit` 每期最多降 500 MW 的约束，所以一直运行。修正口径共用这段日前接受代码，同样存在（修复轮 FX7 实测，见 6.6 节）；A18 只改修正口径（3.5 节，未实施），论文复现口径保留并在方法学中披露。
- 互联线进口只在平衡环节出现，即只用于实际需求高于日前计划的剩余缺口（修复轮 S-D3 的追踪结果；修正口径由 C25 改为日前出清也接受进口）。
- 旧的读法：无表头首行（P6-05）、半小时与小时时钟（P6-07）；径流水电兼容资本留在头条（P4-03）。VoLL 原为 8000 £/MWh，A16-5 起两个口径都是 17,000（只进成本账的通用修正 `fx5.voll-17000`）。
- 参考配置：legacy 储能电价，加 doctoral 碳因子情景（碳账不给物理 tCO2）（Q3）。只允许论文谱系模块和论文期数据包；启用了外部代码时拒绝运行。

## 5 需要你审核的数据

### 5.1 已经审核或认可的数值（列出供核对，不需要再动）

| 项 | 取值 | 出处 | 状态 |
|---|---|---|---|
| 核电各站负荷率（修正口径） | Heysham 1 66.8%、Hartlepool 68.9%、Heysham 2 75.2%、Torness 79.2%、Sizewell B 80.1%；退役月份 Heysham 2、Torness 2030-03 | IAEA PRIS（经 WNA）2019–2024，DUKES 5.6.E 全国合计校核（各年差 ≤0.9%）；WNN 与 EDF 新闻稿 | A14 已审核 |
| 径流水电（修正口径） | 0.3487 × `[1.3851×3, 0.6582×3, 0.6776×3, 1.2791×3]` | DUKES 2026 表 6.3 标准口径；Energy Trends 6.1 季度数据 | A14 已审核 |
| 风电损耗（修正口径） | 陆上：尾流 5%、可用率 0.97、电气 2%，合计 0.90307；海上：尾流 12%、可用率 0.945、电气 2%，合计 0.814968（约 −18.5%） | Barthelmie 2009、Simley 2025、Lee & Fields 2021、Conroy 2011、SPARTA 2017/18、Colmenar-Santos 2014 等（参考统计表第 3 节） | A9 已认可 |
| 光伏性能比（修正口径） | PR 0.83（区间 0.76–0.88） | Sheffield Solar 7000 套系统（Taylor 2015）、Dhimish 2020/2021、Leloux 2012 | A9 已认可 |
| 光伏倾斜面换算的模型选择（修正口径，修复轮） | 太阳位置 Spencer（1971），按时段中点；直射/散射分解 Erbs、Klein & Duffie（1982），太阳常数 1361 W/m²（Kopp & Lean 2011）；斜面换算 Hay & Davies（1980），反照率 0.2；倾角 Jacobson & Jadhav（2018）北半球最优倾角拟合式（51.5°N 约 36.0°）；天顶角大于 87° 时不计直射 | 参数表 `value_uk_vre_loss_factors_v1.json`、参考统计表 3.5 节（已改为 AUTHOR APPROVED，数值不变） | **A16-6 作者直接认可**。书目与拟合系数没有联网复核。影响：GBP1 修正口径光伏 CF 0.0997 → 0.1065（倾角取纬度时 0.1012） |
| VoLL（两个口径，修复轮） | 17,000 £/MWh（8,500 £/MW·时段） | 作者口径 | **A16-5 决定**（原为论文代码 8000、参数默认 10000） |
| 核电下调溢价、比利时价格汇率（修复轮） | 修正口径下调次序中核电 dec premium 100 £/MWh；EUR/GBP 1.1 | 施工值（汇率依据 R029 approved_r03 “Ember 2022 except Ireland 2021”） | **A16-6：维持施工值**，你未提异议 |

### 5.2 仍然待你审核

1. ~~光伏倾斜面换算的模型选择（A13）~~：已由你在 A16-6 直接认可，移入 5.1 节。
2. **DUKES 对照列**（参考统计表 3.4 节，A9 披露用，仍标 PENDING）：DUKES 6.3 标准口径 2020–2024 均值为陆上 0.2582、海上 0.4009、光伏 0.1025。表中风电合计行 2020、2021 年的值与分项不符，疑为 DESNZ 发布错误，没有使用。
3. **数据来源的薄弱处**：海上电气损耗的绝对值没有核实到（[NV]），暂用陆上的 2% 作下限；海上可用率只有 SPARTA 一个来源，区间不是文献值。
4. **回退值**（不在 A14 的逐站表中）：
   - 未分站的 `Nuclear` 资产用全国 0.723（DESNZ 2022–2024）；
   - AGR 默认值 0.727；
   - 新建 PWR/EPR 用 0.801（取 Sizewell B 均值）。
5. **施工中按计划附表采用、DECISIONS 中没有逐条列出的数值**，建议过目（VoLL、核电 dec premium、EUR/GBP 1.1 已在 A16-5、A16-6 定下，移入 5.1 节）：
   - 启动加价单列；
   - A4 的舍入吸收：相对 1e-9 以内的净收入按 0 处理；
   - GBP1 夏令时修复删去和插补的行号（见 U4）；
   - 修复轮 FX6 的两处施工选择：日前进口报价乘报价乘数（与平衡环节一致，默认乘数为 1）；已接受的日前进口在下调时按对侧价格作为避免成本、类别次序排在火电之后，不付削减费。
6. **水电形状的归一化**：按 12 个月算术均值为 1 归一化。按 365 天加权时，年电量比“负荷率 × 8760 h”低 0.12%。是否改为按天数加权，由你决定，不影响 ±15% 的验收。

### 5.3 与数据相关、需要你决定的事项

- **GBP1 论文口径的 surplus conservation 失败**（A15）：修复后 471 个时段越界，最大 991 MWh；35aadb3 同样失败。已登记为待调查的已知问题，下一轮查明。在那之前，这次运行的年度结果按 Q14 保持隐藏。
- ~~修正口径在 GBP1 上的全年验收运行还没有做~~。**修复轮（A16-7，FX7）已在本地完成**：public2 在代码中登记为 scientific_reference，并以 C26 加入核电分站名单；运行、数据包和输出都只在施工临时目录，没有发布、没有上传。结果见 6.6 节：水电通过，光伏差不多，风电偏高（A9 披露项），**核电明显偏离（−95%）**。
- **核电启动路径依赖（修正口径）**：你已在 A18 决定修正口径核电开局在运，**待实施**（3.5 节）。实施后要重跑 FX7 的验收表。
- **修复轮新发现、需要你或负责人决定的数据问题**：
  1. **R029 public1 与 GBP1 public1 的光伏曲线不能被严格读取**：两个包绑定同一份逐时 `sa.csv`，有 8,761 个值（多一小时）且没有 interval 声明，修正口径的严格读取报 `GF_DATA_SHORT_SERIES`。R029 public1 是修正口径的默认国家级数据包（Q4），所以在修正口径下用默认 PSM 跑 R029 会在构建时间序列时失败（FX7 用 `data_method.read_role` 实测，没有跑完整 R029）。数据包验证层没有发现它。修法三选一：给数据包补声明；在真相登记中断言 `sa.csv` 为逐时（会同时改变论文口径的读取，须另立修正）；扩展验证层。public2 的构建器已声明，已发布的包没有改。
  2. **生物质几乎不运行**：GBP1 public2 修正口径 2025 年 4,762 MW 只发 0.05 TWh（CF 0.1%）。报价只用 `gen_cost`（生物质 0.2，CCGT 0.1），排在 CCGT 之后。是否属于论文方法的预期行为，需要判断。
  3. **校验面板与 Study 编辑器对论文复现口径资格的判断不一致**（复测 N-1）：面板只看校验层，编辑器还看口径白名单，用户包在面板上显示 doctoral 可用、在编辑器里被拒。建议在发布前修。
  4. **Run 的方法学记录中看不到 VoLL 改动**（复测 O-3）：`fx5.voll-17000` 是通用核算修正，不进修正目录，所以 doctoral Run 的 `applied_correction_ids` 中没有它，`switch_corrections.reliability_voll` 仍写 `p06.voll-chronology-parameter`。是否在 Run 来源记录中点名，由负责人决定。
- 把 public2 的 `flow_sign` 标为 verified，需要你提供年度参考表 `boundary_flow_reference_2022.json`。

## 6 预期的结果变化

### 6.1 方向（你应该预期什么）

**论文复现口径**（与 35aadb3 相比）：

- 在边界序列为常数、没有比利时价格或夏令时问题的数据包上（例如 VALUE 101），出力、价格、储能和排放逐位不变。变化只有三处：在电价约等于运行成本时不再扩容 CCGT（A4），因此资本成本降低；头条每年少计风光储 FOM（A7）；验证状态改为 v2 的判定。
- 在 GBP1 这类数据包上，互联线与需求的读取修正会改变调度：进口大幅减少，价格尖峰消失，CCGT 发电和排放增加，核电是否被接受（路径依赖）也可能随之改变。
- 能看到原来被隐藏的缺电 stress 事件，调度不变。
- 原始不变量不全部通过时，年度结果在结果页扣发（Q14）。VALUE 101 的复现运行就是这样，原因是储能 2P 偏差。所以复现口径的年度结果在结果页上基本不显示，这一点你已确认知晓。

**修正口径**（与 35aadb3 相比）：

- 风光可用出力下降：陆上约 −10%，海上约 −19%，光伏约 −17%（GBP1 上倾斜面换算会把光伏拉回一部分）。火电发电、平均成本和排放随之上升。
- 新市场规则使下调时先降燃气、储能真正参与调度并按统一价获得收入。火电发电和运营成本随之下降，储能收入不再取决于自身报价，储能投资提案可能出现。
- 在 VALUE 101 上这两项大致抵消：CCGT 发电与排放各 −0.6%。系统成本的下降（−2.1%）主要来自 A4 与 A7。
- 有径流水电和核电的数据包（GBP1）：水电发电大幅下降（约 17.5 → 6.1 TWh），核电按站降额并按月退役，预期火电或进口会补上；头条系统成本因 P4-03 大幅下降。修复轮已在本地 public2 上实测第一年（6.6 节）：水电 6.06 TWh 符合预期；核电因启动路径依赖只发 2.02 TWh，CCGT 补上，这一项要等 A18 实施后才有代表性。
- 互联线进口（修复轮 C25）：对侧价格低于本国边际报价时，日前就进口，进口量上升、CCGT 下降；对侧价格高于本国报价的包（VALUE 101）不变。
- 弃电列现在是真正的风光弃电，非 VRE spill 单列。gate 失败的运行不发布年度经济结果。
- 记录的切负荷按 17,000 £/MWh 计入运营成本（修复轮 U13）；有切负荷的运行，修正口径相对旧默认 10,000、论文口径相对 8,000 的头条成本会上升。

### 6.2 VALUE 101 two_year 实测（两年合计，2025–2026）

| 指标 | 35aadb3，legacy 储能（D4/C5 修订 0） | 论文口径 HEAD（D4） | 修正口径 HEAD，legacy 储能（C5） | 35aadb3，dynamic 储能（C6 修订 0） | 修正口径 HEAD，默认配置（C6） |
|---|---:|---:|---:|---:|---:|
| 系统成本头条（£） | 29,570,717 | 28,930,311（−2.17%） | 29,025,968（−1.84%） | 29,737,943 | 29,124,532（−2.06%） |
| 其中运营（£） | 13,053,554 | 13,053,554（0） | 13,118,963（+0.50%） | 13,194,344 | 13,209,660（+0.12%） |
| 其中资本（£） | 16,517,163 | 15,876,757 | 15,907,005 | 16,543,599 | 15,914,872 |
| 分年头条（£，2025 / 2026） | 14,626,893 / 14,943,823 | 14,560,893 / 14,369,417 | 14,664,891 / 14,361,077 | 14,691,271 / 15,046,671 | 14,699,543 / 14,424,989 |
| 单位成本（£/MWh 供电） | 63.22 | 61.85 | 62.06 | 63.58 | 62.27 |
| 需求加权时段平均成本（£/MWh，2025 / 2026） | 30.64 / 25.18 | 30.64 / 25.18 | 31.08 / 25.01 | 30.91 / 25.50 | 31.23 / 25.25 |
| 最高时段平均成本（£/MWh） | 65.92 | 65.92 | 64.74 | 65.92 | 64.74 |
| CCGT 发电（MWh） | 196,294 | 196,294 | 197,277 | 198,410 | 197,191 |
| 风光可用电量，弃电前（MWh） | 347,046 | 347,046 | 300,498 | 348,063 | 300,803 |
| 风光弃电（MWh，修正口径语义） | 不可比（列语义不同） | 不可比 | 28,812 | 不可比 | 29,029（可用量的 9.7%） |
| 电池放电（MWh） | 33,688 | 33,688 | 5,207 | 0.36 | 5,208 |
| 电池市场收入（£） | 0 | 0 | 154,411 | 21 | 208,524 |
| 直接排放（tCO2） | 77,340 | 77,340 | 77,727 | 78,174 | 77,693 |
| 投资提案（MW） | 21.32（CCGT 13.05，陆上 5.56，光伏 2.71） | 8.26（陆上 5.56，光伏 2.71） | 8.89（陆上 5.80，光伏 3.09） | 21.96（CCGT 13.19，陆上 5.63，光伏 3.13） | 9.49（陆上 5.83，光伏 3.24，1C 电池 0.42） |
| 2026 年投运（MW，含已规划的 15 MW 光伏） | CCGT 7.17，陆上 2.81，光伏 17.71 | 陆上 2.81，光伏 17.71 | 陆上 2.94，光伏 18.09 | CCGT 7.23，陆上 2.84，光伏 18.13 | 陆上 2.95，光伏 18.24 |
| 记录的切负荷（MWh） | 0 | 0 | 0 | 0 | 0 |
| stress 事件 / 缺口 | 无记录（账本无边界，只能给上下界） | 0 / 0 | 0 / 0 | 无记录 | 0 / 0 |
| 科学验证 | v1 “passed”（硬编码） | `reproduction_with_declared_deviations`（DEV-STO-01） | passed | v1 “passed” | passed |
| 结果页发布（Q14） | — | **扣发**（储能原始不变量 failed） | 发布 | — | 发布 |

说明：

1. 论文口径 HEAD 与 35aadb3 的出力、价格、储能、风光和排放逐位相同。差别只有两项：一是 A4 使 2025 年的 CCGT 提案（7.17 MW）不再在 2026 年投运；二是 2026 年的 CCGT 提案取消。2026 年系统成本因此少了这台 CCGT 的年金化资本 508,406 £，A7 又让每年少计 66,000 £。
2. 论文口径和 35aadb3 都把被储能等吸收的 VRE 盈余记在 `excess` 列，`curtailed` 两年只有 4 MWh；修正口径把它们分开（3.2 节，C20），所以弃电一行只对修正口径给出数值。
3. “时段平均成本”就是默认 PSM 的 `clearing_price_gbp_per_mwh`。按 Q6 它不是边际出清价。
4. 排放是事后按同一套权威因子（`value_current_authoritative_v1`）乘以逐资产发电量算出的直接运行排放。论文口径的碳因子情景不给物理 tCO2，所以这样处理，差别只反映调度差别。
5. **修复轮之后本表不变**：U12 只写 full trace 的核算表；U13 的 VoLL 在 101 上乘的是 0 MWh 切负荷；C25 的法国进口（82 £/MWh）比 CCGT（66.5 £/MWh）贵，两年都全部拒绝（FX6 用 HEAD archive 与工作树各跑一次 C5、C6，均价、最高价、残差逐位相同）；C26 只作用于 public2。FX5 报告第 3 节列的 101 头条数比本表多 66,000 £/年，是取了 A7 之前的成本字段，不影响“VoLL 变化为 0”的结论。

### 6.3 分步归因（VALUE 101 two_year，两年合计）

修正口径，默认配置（C6）：

| 步骤 | 提交（golden 修订） | 系统成本（£） | 变化 | 需求加权价（£/MWh） | CCGT 发电（MWh） | 排放（t） | 电池放电（MWh） | CCGT 提案（MW） |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 35aadb3 | r0 | 29,737,943 | — | 28.21 | 198,410 | 78,174 | 0.36 | 13.19 |
| + 物理运营成本（U10） | 3537374（r3） | 29,737,923 | −19 | 28.21 | 198,410 | 78,174 | 0.36 | 13.19 |
| + 修正市场规则（3.2 节）与 P0-4 验证门控 | 5014b7b（r6） | 28,291,972 | −1,445,951（−4.86%） | 25.29 | 176,089 | 69,379 | 6,312 | 11.71 |
| + 天气 v2 与风光损耗（C1、C2） | 54fe0ed（r7） | 29,772,318 | +1,480,346（+5.23%） | 28.24 | 197,191 | 77,693 | 5,208 | 13.11 |
| + P0-7（A4、储能余量、电池池、A7、P4-03）；F2 与 P0-8 在 101 上为 0 | HEAD（r8） | 29,124,532 | −647,786（−2.18%） | 28.24 | 197,191 | 77,693 | 5,208 | 0 |
| 旁证：在 5014b7b 上只加 A4 | 7e07437（lane） | 27,835,028 | −456,944（相对 5014b7b） | 25.29 | 176,089 | 69,379 | 6,312 | 0 |

论文口径（D4）：

| 步骤 | 提交（golden 修订） | 系统成本（£） | 变化 | 其他 |
|---|---|---:|---:|---|
| 35aadb3 | r0 | 29,570,717 | — | — |
| + P0-4、P0-6 的核算修正 | 5014b7b（r8） | 29,570,717 | 0 | 轨迹与成本都不变 |
| + A4 | 7e07437（r9） | 29,062,311 | −508,406（−1.72%） | 提案 21.32 → 8.26 MW |
| + A7 成本账 v2 | HEAD（r10） | 28,930,311 | −132,000（−0.45%） | — |

### 6.4 GBP1 public1，论文口径，第一年（2025）

数据取自 `docs/dev/GBP1_DOCTORAL_BEFORE_AFTER.md`，A15 已认可为新参照。

| 指标 | 35aadb3 | 修复后（doctoral-lineage-0.6.0a2） | 主要原因 |
|---|---:|---:|---|
| 进口合计（TWh） | 1.548 | 0.336（−78%） | U2、U3（荷兰线原先免费进口 1.34 TWh）、U1 |
| 时段平均成本：均值 / 最高（£/MWh） | 22.35 / 5,849.5 | 18.23 / 50.4 | U1–U4，经由核电接受时点（路径依赖） |
| 系统成本头条（百万英镑） | 28,126.9 | 27,232.0（−3.18%） | U1–U4 −813.0；U10 −25.3；U11 −56.7 |
| 直接排放（MtCO2） | 29.91 | 30.91（+3.4%） | 免费进口和核电消失后由 CCGT 补足 |
| 核电发电（TWh） | 2.73 | 0 | 冻结内核的路径依赖（A15） |
| CCGT 提案（MW） | 1,717.1 | 0 | U6（U1–U4 之后为 1,773.8 MW，A4 取消） |
| 风光提案（MW） | 2,954.7 | 3,036.4 | U1–U4 |
| stress 事件 / 时段 / 缺口（MWh） | 168 / 848 / 302,138 | 157 / 890 / 300,855 | 数值差来自 U1–U4；能够记录这些量来自 U7 |
| 原始不变量 | 只读核验为 failed | failed（surplus conservation，A15） | 校验口径变严，不是修复引入 |

### 6.5 第 6.2、6.3 节的测量方法与局限

- **怎么跑的**：每个用例都是一次 VALUE 101 two_year 全量运行（17,520 期 × 2 年），使用 golden 的冻结项目 `tests/golden/projects/{D4,C5,C6}.json`。
  - HEAD 与中间提交：在该提交的源码树上运行 `scripts/golden/run_case.py <case> --keep-output`；
  - 35aadb3：在 `git archive 35aadb3` 的源码树上，用同一冻结项目调用 `run_project_application(mode="two_year")`；
  - 汇总：仿照 `scripts/gbp1_doctoral_before_after.py` 写了一个按年汇总的只读脚本，放在施工临时目录，没有入库。
- **可信度**：11 次运行的 golden 摘要都与对应修订**逐列一致**（gated 差异为 0）：
  - 35aadb3 ↔ D4、C6 的 r0；3537374 ↔ C6 r3；5014b7b ↔ D4 r8、C6 r6；7e07437 ↔ D4 r9；54fe0ed ↔ C6 r7；
  - HEAD ↔ D4 r10、C5 r10、C6 r8，其中 D4 只有 1 个 identity 列不同，是代码哈希。
  - 7e07437 的 C6 运行没有对应修订，因为它在 lane 分支上。
- **VALUE 101 是教学包**：
  - 机组只有 50 MW CCGT、20 MW 陆上风电、35 MW 光伏（2026 年另有 15 MW 规划光伏投运）和 10 MW 1C 电池；
  - 市场序列为常数，没有进出口，没有核电和径流水电，天气是合成数据；
  - 所以 U1–U5、C3–C5、C19 在这里都是 0，这些修正的实际量级要看 GBP1（6.4 节和第 3 节“其他数据包”一列）。
- **只跑两年**：第二年的提案在本次运行内不会投运。
- ~~修正口径在 GBP1 上没有全年运行~~：修复轮已在本地 public2 上跑了第一年（6.6 节），但那是修正口径相对“修正口径”的验收，不是相对 35aadb3 的分步归因；核电的数字要等 A18 实施后重跑。

### 6.6 GBP1 public2，修正口径，第一年（2025；修复轮，本地）

数据取自 `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md`（FX7）与 `docs/dev/p0-reports/FX6-S-D3-ahead-imports.md`。运行设置：golden D5 的冻结项目（参考配置：legacy 储能电价、doctoral 碳因子情景），加 `methodology.profile = value-corrected`、数据包 public2 v2（manifest `f43e0e46…`，本地构建，**未发布**）；17,520 期，summary trace；每次运行用独立数据目录，跑完删除。

验收（你定的标准：“看着差不多”）：

| 项目 | 模型 | 参照 | 偏差 | 判定 |
|---|---:|---:|---:|---|
| 核电发电 | **2.02 TWh** | Energy Trends 5.1，2023–2024 supplied 约 37.3 TWh（±10%） | **−95%** | **明显偏离**：启动路径依赖（4.2 节），A18 待实施 |
| 核电可发上限（按 C4 可用率连续运行） | 38.26 TWh | 同上 | +2.5% | 在 ±10% 内，可用率与逐站名单本身是对的 |
| 径流水电 | 6.06 TWh | DUKES 6.2，2019–2024 均值 5.77 TWh（±15%） | +5.1% | 通过 |
| 陆上 / 海上 / 光伏 CF（按装机加权，弃电后） | 0.370 / 0.499 / 0.112 | DUKES 6.3 标准口径 2020–2024：0.258 / 0.401 / 0.103 | ×1.43 / ×1.24 / ×1.09 | 风电偏高，属于 A9 已接受的披露项；光伏差不多 |
| 生物质 | 0.05 TWh（4,762 MW，CF 0.1%） | — | — | 明显偏离，未调查（5.3 节） |

修复轮各步在这组运行上的作用：

| 步骤 | 进口（TWh） | CCGT（TWh） | 核电（TWh） | 时段均价 / 最高（£/MWh） | 头条系统成本（百万英镑） |
|---|---:|---:|---:|---:|---:|
| FX6 之前（6.2.0，public2 未登记） | 0.331 | 102.72 | — | 24.45 / 100.31 | 28,709.98 |
| + C25 日前进口（6.3.0） | 1.560 | 101.45 | 1.96 | 24.30 / 74.06 | 28,684.40 |
| + C26 登记与逐站核电（验收运行） | 1.558 | 101.41 | 2.02 | 24.30 / 74.06 | 28,682.8 |
| 诊断：核电启动成本设为 0（不是 A18 本身） | 1.38 | 67.53 | 38.26 | 16.23 / 46.30 | 26,852.1 |

其他（验收运行）：需求 232.91 TWh；风电 111.84 TWh，光伏 9.89 TWh；出口 0.413 TWh；弃电 0.43 TWh；储能充/放 1.633/1.184 TWh；运营/资本成本 5,711.6/11,959.2 百万英镑；直接排放 40.58 MtCO2（事后按权威因子）；投资提案 3,054.8 MW；切负荷与 stress 事件都是 0；energy_balance、run_invariants、storage_invariants 三类 gate 全部通过，按修正口径规则可以发布年度结果。价格是 Q6 的时段平均成本，不是批发电价。
