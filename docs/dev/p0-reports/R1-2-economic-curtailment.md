# R1-2-economic-curtailment：修正口径的经济下调顺序（DECISIONS A19、A22）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `c9c1cc1`。
- 授权：A19（撤回"永远先降火电"，火电下调代价由重启成本和省下的燃料、碳、可变成本共同决定，再与风电 0 比较，不得预设火电更贵）；A22（认可参考统计表第 4 节取值；H 取日前预测中连续盈余时段数 × 0.5 h；H ≥ 最短停机时间才允许进入停机段；不停机段先于弃风，停机段 a(H) = c − S/H > 0 先停火电，否则先弃风；审查后按 A22a 改为 a(H) = c − S/(m·H)，见第 9 节）。只在修正口径实施，属于方法改动（Q13）；论文复现口径不变（Q1）。
- 提交：
  - `92fc86e` feat(psm): corrected down-regulation weighs restart cost against avoided cost (A19/A22)
  - `56a806d` docs(methodology): economic down-regulation order draft for 0.4; restart-cost table author-reviewed (A19/A22)
  - 本报告单独提交（docs(p0)）

## 1 规则（实现内容）

默认 PSM（`value-bid-at-cost-psm`）在实际需求低于预测时进入削减分支：先由储能、出口、灵活负荷消纳（Q5 顺序不变），剩余量从日前已接受的出力中下调。修正口径原来的 P0-6 S7 规则按避免成本降序排列，燃气、生物质总是先降到爬坡下限，然后才弃风。本单元改为：

1. **燃气（CCGT、OCGT）与生物质的一行拆成两段**。在线容量取该机组当期日前接受出力 P（聚合机组没有开停机状态，按"日前排了的机组都在线且满载"处理）。
   - **不停机段**：`max(P − max(爬坡下限, m·P), 0)`。仍在最小稳定出力以上，不触发重启，每 MWh 省 c = `gen_cost`（燃料 + 碳 + unit_time_cost + 基数），沿用 P0-6 的排序键，因此总在弃风之前。
   - **停机段**：`max(min(P, m·P) − 爬坡下限, 0)`。净节省 `a(H) = c − S(H)/(m·H)`（审查后修正，原为 `c − S(H)/H`，见第 9 节）。H ≥ 最短停机时间且 a > 0 时，按 a 排序，排在弃风之前；a ≤ 0 时排在弃风之后（同一取整值下排在核电之前）；H < 最短停机时间时只作最后手段，放在所有其他资源之后。这样 P0-6 栈原本能消纳的盈余不会留在节点里。
2. **H（预计停机时长）**：`H = (1 + n_t) × 0.5 h`。n_t 是 t+1、t+2……中连续满足"日前预测盈余"的时段数，盈余定义为预测需求 ≤ 预测 VRE 可用量 + 核电可用量（不需要任何火电）。VRE 与核电的逐时段可用量取自修正口径已有的 site-CF 与 firm-availability 数组（P0-5b，`kernel_site_inputs`）。当前时段计 1，因为下调正是因为它已处于盈余。没有这些数组时（单元测试会话），H 只取当前时段。
3. **取值**（A22，写入 `gridform_core/data/thermal/value_thermal_restart_v1.json`，附出处与等级）：

   | 技术 | S（£/MW） | 热/温/冷判定 | 最小稳定出力 m | 最短停机时间 |
   |---|---|---|---|---|
   | CCGT | 110 / 130 / 150 | H < 12 h 热，12–48 h 温，> 48 h 冷 | 50% | 6 h |
   | OCGT | 170 | — | 50% | 0.5 h |
   | 生物质 | 125 | — | 35% | 6 h |

4. **其他行沿用 P0-6 的键**：VRE 用自身 `gen_cost`（包中为 0.0001，取整为 0.00），进口用对侧价格（FX6），水电、核电（含 100 £/MWh 下调溢价）不变。排序键为 `(−round(成本, 2), 类别次序, 名称, 段号)`，稳定排序。停机段类别次序为 2.5（VRE 之后、核电之前），所以 a 取整后等于 VRE 时归弃风，满足 A22 中 "a > 0" 的严格不等号。
5. **重启成本只用于排序**，成本账不变：物理运营成本的启动项仍是 P5-06 的论文 `startup_cost` 加价。
6. **新输出**：每个修正口径市场年记录 `market.extensions.downward_restart_economics`（`value.downward-restart-economics/v1`），内容包括规则、取值表 id 与 sha256、H 的口径与 VRE 覆盖数、下调时段数、平均 H，以及按段（thermal_running_range、thermal_shutdown_net_saving、thermal_shutdown_after_vre、thermal_shutdown_below_min_down_time、vre、import、hydro、nuclear、other）统计的 MWh 与时段数。

## 2 文件

| 位置 | 改动 |
|---|---|
| `native_corrected.py` | 新增 `restart_table`、`RestartParameters`、`restart_technology`、`economic_segments`、`economic_downward_stack`、`DownwardTally`、`SurplusOutlook`、`surplus_run_after`、`build_surplus_outlook`。原 `downward_stack` 保持不动，FX6 测试照常直接调用 |
| `native_market_rules.py` | 新字段 `downward_restart_economics`：论文 `not_modelled`，修正 `restart_cost_vs_avoided_cost_v1`；开关 `r12.economic-downward-order`。规则集 id 不变，sha 变化（同 FX6、FX8 做法） |
| `runtime_compat/modular_simulation_model.py` | `_P06State` 增加 `outlook`、`downward_tally`、`restart_economics`；`store_service_corrected` 按字段选择经济栈；`run_simulation` 在 `_site_inputs` 之后建立 outlook 与 tally（只在修正口径）。已用 `seal_runtime_overlay.py --correction r12.economic-downward-order` 封存，`--verify` 通过 |
| `native_realisation.py` / `scheme_c_native_psm.py` | RealisationLog 携带 tally；适配器写出新 extension。`scheme_c_native_psm.py` 是 CRLF/LF 混合文件，已按字节编辑，保持原有行尾 |
| `data/thermal/value_thermal_restart_v1.json`（新） | A22 取值、规则说明、出处（R1、R3–R6、R8、R10、R11） |
| `data/methodology/corrections/r12.json`（新） | profile_gated，scope market_clearing，affects trajectory/accounting；advisory medium；trigger fixture `tests.test_r12_economic_downward_order.EconomicDownwardOrderTests`；deviation_signature 写明论文口径行为 |
| 版本 | `value-bid-at-cost-psm` 6.4.0 → 6.5.0，VERSION_LEDGER 包 R1-2，`requires_user_opt_in = true`；同步 manifest、`SchemeCNativePSM.version`、`docs/generated/*`、UI 合同夹具 |
| `pyproject.toml` | package-data 增加 `data/thermal/*.json` |
| golden | 见第 4 节；`P0_GOLDEN_DELTA.md` 重新生成，`delta_report --check` 结果为 0 条无法归因 |
| CHANGELOG | correction id 表加 R1-2 行；golden 摘要加一段；新增小节 "Economic down-regulation order"，含数字 |
| 方法学 | 新草稿 `docs/methodology/drafts/0.4/r12_economic_downward_order.md`（规则、取值表、算例、输出、0.3 待改处、数字）；`p06_default_psm_clearing.md` 修正规则表的下调行指向新规则 |
| 参考统计表 | 第 4 节状态改为"作者已审核 (2026-10-07, DECISIONS A22)"，4.8 第 1–3 条标为已决定 |

## 3 测试

新增 `tests/test_r12_economic_downward_order.py`（16 个，全部 OK；审查后为 17 个，下列 toy 的数字已按修正式更新）：

- 任务要求的三个 toy：
  - (a) 省下的燃料成本高于重启成本，先降火电：OCGT 20 MW、风 30 MW、需下调 25 MW、H = 5 h，a = 75 − 170/(0.5×5) = 7 > 0（停 20 MW 装机重启 £3,400 < 省 £3,750），结果 OCGT 降到 0，风只弃 5 MW。CCGT 在 H = 6 h 时同样成立（a = 55 − 110/3 = 18.3）。
  - (b) 重启成本高于节省，先弃风：同一 OCGT 在 H = 0.5 h 时 a = −605，结果 OCGT 只降不停机段 10 MW，风弃 15 MW。H = 3 h 时 a = −38.3（审查指出的情形：重启 £3,400 > 省 £2,250），同样先弃风。H = 2 h 时 a = −95，风弃完后才进入停机段。CCGT 在 H = 3 h < 6 h 时停机段为最后手段。
  - (c) 下调在不停机段内，先降火电：CCGT 70 MW 降 20 MW，风全部保留。
- 论文口径经 `curtailment_market_bidding` 仍是先弃风，且不调用经济栈；修正口径经同一入口先降 CCGT。
- A22 取值表（热/温/冷边界：11.5 h 热，12 h 温，48 h 温，48.5 h 冷）、技术映射、a = 0 平局归风、爬坡下限截断两段且生物质预算返还、水电/核电/VRE 的分类统计、确定性（同名机组按输入顺序）。
- outlook：`surplus_run_after`；由 VRE 与核电数组构造 H，水电不计入；无数组时退回当前时段；内核分支读取当期 H（第 3 期 H = 6 h 先停 CCGT，第 2 期 H = 0.5 h 先弃风），并核对 tally 与 summary。
- Q13：开关只在修正口径启用；VERSION_LEDGER 的 R1-2 升级要求 opt-in；去掉 r12 的旧修正集合在迁移分类中为 `method_upgrade_required`；论文口径不含此修正。

修改的已有测试：`test_native_market_rules`（规则表两行，开关前缀允许 `r12.`）、`test_result_advisories`（修复前的 Run 多一条 medium 级 advisory）。

运行结果：

- `vpy -m unittest` 运行 r12、fx8、fx6、native_corrected_rules、fx4、native_market_rules、fx5、native_operating_cost、p04_balance_boundary、native_realise_period、native_reproduction_golden、result_advisories、runtime_overlay_seal、methodology_profiles、methodology_identity、ui_contract_fixtures、catalog_lazy、methodology_static_scan 共 18 个测试模块，226 个测试，OK（skipped 2）。golden 相关模块（digest、research_pack、corrected、delta_report、doctoral、fx7）在修订前按预期失败，修订后由门禁复核通过。
- `capture.py check --tier fast`（修订前）：D1–D3、C7、C8 gated 0；C1–C4 只有 10 个新增 extension 列，出力不变。
- `check_methodology_catalog.py`、`check_version_ledger.py`、`seal_runtime_overlay.py --verify`、`generate_reference_tables.py`、`delta_report.py --check`、`capture.py validate`、`refresh_source_release_manifest.py --index --check`：全部通过。
- `scripts/p0_gate.py quick`：两次提交前各跑一次，都在暂存状态下运行，status passed，16 步全部通过，没有豁免。

## 4 golden 与数值报告

- **论文族**：D1–D3 gated 0。D4、D5 不受影响，因为规则字段只在修正口径生效。
- **C1–C4**：各追加一次修订，只多了 10 个新 extension 列（trajectory 区，内容是零或很小的下调统计），出力不变。
- **C5（r12）、C6（r10）**：VALUE 101 two_year。before 为 `git archive c9c1cc1`，after 为工作树，均用 `run_case.py --keep-output` 运行，然后 `revise --from-output`。变化只在 2025 年第 8766 期，trajectory 28 列，accounting 41/43 列。
- **C9（r2）**：GBP1 public2 2025。只多了新 extension 列，出力、价格、成本逐位不变。
- 数值报告在 `docs/dev/p0-reports/r12-golden/C5-r12.json`、`C6-r10.json`、`C9-r2.json`。与 FX8 相同，修正族报告不能放在 `tests/golden/reports/`。
- C5、C6 的报告由 scratch 脚本调用 `golden.build_numeric_report` 生成，没有走 `capture.py numeric-report`（见第 6 节偏差 3）。

## 5 重跑结果（修正口径）

**VALUE 101 two_year（C5 legacy；C6 dynamic 结果相同）**

| 年 | 下调时段 | 平均 H | 各段下调量 | before → after |
|---|---:|---:|---|---|
| 2025 | 1 | 0.5 h | 不停机段 0.16 MWh，VRE 0.84 MWh | CCGT 109,314.91 → 109,315.06 MWh（+0.16）；弃电 4,002.74 → 4,002.89 MWh（+0.16）；直接排放 43,070.07 → 43,070.14 tCO2（+0.06）；运营成本、系统成本 +£10.39（C5 系统成本 14,730,891 → 14,730,901）；投资提案不变（6.03 MW） |
| 2026 | 2 | 0.5 h | VRE 8.37 MWh | 不变 |

在这一期，原规则把 CCGT 降到最小稳定出力以下，新规则因为 H = 0.5 h 小于 6 h 的最短停机时间，改为弃 0.16 MWh 光伏。

**GBP1 public2 2025（本地，C9）**：本地按 FX7 的方法用 `build_value_uk_pack_revision.py --link hardlink` 构建 public2，manifest sha `f43e0e46…1439`，与 C9 钉住的值一致。before 和 after 各跑一年。

| 指标 | before = after |
|---|---|
| 弃电 | 1.735 TWh |
| CCGT / OCGT | 67.53 / 1.47 TWh |
| 核电 | 38.26 TWh |
| 直接排放 | 27.56 MtCO2 |
| 头条运营成本 | £3,880.9 m |
| 时段均价 | 16.23 £/MWh |
| 进口 / 出口 | 1.376 / 1.511 TWh |
| stress | 0 |
| 校验 | 全部通过 |

summary 逐项相同，年度结果只差新 extension。新规则下的统计：下调时段 357 个，平均 H = 3.77 h。各段下调量为：水电 91,515 MWh（341 期）、VRE 21,996 MWh（102 期）、进口 3,750 MWh（16 期）、燃气不停机段 190.7 MWh（2 期）。没有任何时段用到停机段。

**为什么影响很小**：下调（实际需求低于预测，且储能、出口、灵活负荷消纳之后仍有剩余）几乎只出现在日前没有安排燃气的时段。新旧两条规则排序不同的燃气行很少出现。即使出现，需要的下调量也在不停机段之内，而两条规则都先降这一段。两条规则只在下调必须低于最小稳定出力时才有差别。GBP1 的 CCGT 爬坡限值为 14,000 MW（装机 28,000 MW 的一半），爬坡下限不是原因。这是数据和规则共同的结果，不是实现没有生效：toy 测试和内核分支测试都证明了排序切换。

## 6 采用的决定与偏差

采用：A19、A22（取值、H 的取法、两段下调）、Q13（新 correction 改变修正口径的 applied-corrections 哈希，PSM 6.5.0 标 opt-in）、Q1（论文口径逐位不变）、A16-7（public2 只在本地，用后删除）。

偏差与解释：

1. **"新规则集版本"的实现方式**：沿用 FX6、FX8 的先例，新增规则字段（规则集 sha 变化）并升级 PSM 模块版本，没有改规则集 id `native-corrected-v1`，因为它是能量平衡边界登记的键。
2. **H 的口径细节**（A22 原文是"从当前时段起，日前预测中连续盈余的时段数 × 0.5 h"）：
   - 当前时段计为 1，因为它正处于实际盈余。
   - 后续时段的"盈余"取预测需求 ≤ 预测 VRE + 核电可用量。水电有能量预算，进口、储能是可调度资源，都不计入。这是保守做法：H 偏短，偏向先弃风。
   - 预测 VRE 用的是内核本来就使用的可用量。没有可用量数组时（单元测试的合成循环），H 只取当前时段，即 R1-1 的选项 (b)。VALUE 101 与 GBP1 的修正口径运行中，VRE 覆盖为 43/43。
3. **C5、C6 数值报告的生成方式**：`capture.py numeric-report` 要求 parent 输出与上一修订的完整指纹相同（含 identity 区）。C5、C6 的上一修订（r11、r9）早于 FX8 等单元的代码身份变化，HEAD 的输出在 identity 区有 15 列不同，gated 区为 0。所以我在 scratch 中先用 `compare_digests` 核对 parent 的 gated 区为 0、child 与新修订一致，再直接调用同一个 `golden.build_numeric_report` 生成报告，并在报告中加了 `parent_reproduction` 说明字段。C9 走标准命令。
4. **重启成本不进成本账**：A19、A22 只规定排序。把 S 记入物理运营成本会与论文 `startup_cost` 加价的启动项重复，属于另一项方法决定，未做。
5. **在线容量 = 当期日前接受出力**：聚合机组没有开机容量状态，这是保守近似，使不停机段最小。部分负荷效率损失和空载成本不计（参考统计表 4.7 已列）。
6. **H < 最短停机时间时的处理**：A22 说"只有 H ≥ 最短停机时间才允许进入停机段"。如果完全禁止，原来能消纳的盈余会变成节点内溢出，所以实现为"最后手段"：其他资源（含核电）都用完后才使用，并单独统计（thermal_shutdown_below_min_down_time）。本次重跑中这一段始终为 0。
7. **新输出列的区**：新增 extension 列采用默认 trajectory 区，内容是下调数量，没有新增 zones 规则。

## 7 遗留问题

1. 交接文档（`docs/handoff/` 下的方法学编辑、网站上传、模型改动简报）本单元没有改。需要加入：C 条目 "修正口径经济下调顺序"、`r12.economic-downward-order`、PSM 6.5.0、方法学草稿位置、本报告第 5 节的数字。建议由负责交接的单元统一更新。
2. 网络模型（P0-8 分区再调度）的 dec 定价与类别次序（`network_method_rules.DEC_CLASSES`，fuel 在 VRE 之前）不在本单元范围。它是阻塞管理的报价规则，不是系统削减顺序。是否也按 A19 处理，交作者决定。
3. 价格基年：参考统计表 4.8 第 4 条 A22 没有单独表态，参数表沿用 2024 年英镑并已注明。
4. `pyproject.toml` 的 package-data 原本就没有 `data/nuclear/*.json` 和 `data/weather/*.json`（只影响 wheel 打包；源码发布清单包含这些文件）。本单元只加了 `data/thermal/*.json`，其余两项留给打包单元。
5. 两套参考运行中新规则几乎不起作用（第 5 节）。如果作者希望看到规则在其他情景下的影响（例如 VRE 更多或预测误差更大），需要另行安排敏感性运行。

## 8 安全与环境核对

- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`，这是现网 supervisor 在本轮之前创建的锁文件，以往报告都已记录。`diagnose-value --prefix …/installed` 退出码 0，输出 "Installation integrity and runtime checks passed."，中间有一行 vinext 静态文件流 "Premature close" 提示，与以往相同。本单元没有写入安装目录。
- 没有启动 HTTP 服务，没有连接 8766/8800，没有向任何进程发信号；18xxx 端口无监听。模型运行是我启动的后台进程，等待其自行结束。
- 所有 Python 都通过 `vpy` 调用；INTEG 中没有 `__pycache__`。没有下载，没有改 SRC，没有 push。
- 本地 public2 用硬链接构建。构建前后两个来源目录的清单哈希相同（`dc85a5f8…`）。scratch 中的运行输出、HEAD archive 与 public2 用后已删除，剩余约 144 KB（摘要与门禁报告）。

## 9 审查回应（Review response，2026-10-07）

审查结论 changes_required，只有 1 条 major，没有 blocker。

**Major：停机段净节省的单位错了（a = c − S/H 应为 c − S/(m·H)）。接受，已修。**

- 审查意见成立。S 按"每 MW 装机每次启动"计（取值表、代码 docstring 都这样定义）。不停机段总是先降，所以进入停机段时，在运机组都处在最小稳定出力 m×P。再减 x MW 出力要停 x/m MW 装机，重启成本是 S·x/m，省下的是 c·x·H，所以 a = c − S/(m·H)。原式把重启成本低估 1/m 倍（CCGT、OCGT 2 倍，生物质 2.86 倍）。错误来自参考统计表 4.6 节的推导（把停掉的装机 ΔP 同时当成重启基数和少发的出力），A22 照抄了它。
- 这次修正符合 A19 的原意（"省下的燃料等成本高于重启成本时先降火电"），只改公式，不改 A22 认可的取值。但 A22 的原文写的是 c − S/H，所以修正式**仍需作者确认**。我在 DECISIONS 新增 **A22a**，明确标注"待作者确认，不是作者决定"。作者如不同意，应在 A22a 记为接受的简化，并回退 `net_saving`（只有一行）。
- 提交 `4e3bab2`：
  - `RestartParameters.net_saving` 改为 `c − S(H)/(m·H)`。m = 0 没有停机段，此时调用会报错（`economic_segments` 在 m = 0 时停机段为空，不会调用）。新增 `break_even_hours`，给出 H\* = S/(m·c)。
  - toy 重新推导：
    - (a) OCGT 改为 H = 5 h，a = 75 − 68 = 7 > 0，先停 OCGT。
    - (b) 新增审查指出的 H = 3 h 情形：a = −38.3，先弃风。重启 £3,400，大于节省的 £2,250。
    - 平局用例改为 H = 4 h（a = 0）。
    - 爬坡下限用例新增一段：需下调 25 MW 时，生物质停机段（a = 25.5）排在 CCGT 不停机段（55）之后，只停 2 MW。按原式，生物质停机段 a = 64.2，会先停满 7 MW。
    - 新增 `test_net_saving_charges_restart_per_mw_of_capacity`：逐项核对 a 值和 H\*（3.99 / 4.54 / 4.20 h）；用"S × 停掉的装机"核对单位；核对 m = 0 时报错。r12 测试共 17 个，全部 OK。
  - 文档：
    - 参考统计表 4.6 节：推导、表格（新增 m 列；H\* 为 CCGT 3.99 h、OCGT 4.54 h、生物质 4.20 h）、解读，并加勘误说明；4.8 节新增第 5 条（待作者确认）。
    - 0.4 草稿 `r12_economic_downward_order.md`：§2 的推导与单位核对、H\* 列；§3 算例改为 CCGT a(6 h) = 55.07 − 110/3 = 18.4，重启 £22,000 < 节省 £33,042；OCGT 算例改为 H = 0.5/2/3 h 先弃风，5 h 先停 OCGT。
    - 同步修改：r12 catalogue 描述、`docs/generated/METHODOLOGY_PROFILES.md`、VERSION_LEDGER 的 R1-2 reason、CHANGELOG、`native_market_rules.py` 注释、内核注释。内核注释改动后已用 `seal_runtime_overlay.py --correction r12.economic-downward-order` 重新封存，并保留原 note；`--verify` 通过。
  - 规则字段值 `restart_cost_vs_avoided_cost_v1`、PSM 6.5.0 和 VERSION_LEDGER 条目都不变：R1-2 还没有发布，这是同一个方法改动的更正，不另开版本。
- golden 复核：按审查要求，在 `4e3bab2` 上运行 `capture.py check`：
  - C5（VALUE 101 two_year，134 s）、C6（130 s）：gated 差异均为 0。
  - C9（GBP1 public2 2025，本地重建 manifest `f43e0e46…1439`，528 s）：gated 差异为 0。
  - 三个 case 的 identity 区各有 1 项差异，即代码身份哈希。
  - 快档 C1–C4 由门禁复核，也不变。
  - 结论：第 5 节的数字全部不变。两套参考运行都没有用到带价停机段：VALUE 101 那一期 H = 0.5 h，低于 CCGT 的最短停机时间；GBP1 中燃气只在不停机段内下调。
  - public2 用后已删除。构建前后，两个来源目录的清单哈希相同（`588cbcf3…`）。
- 修正后的实际影响：CCGT 与生物质的 H\* 仍短于 6 h 最短停机时间。在 GBP1 成本下，允许停机时 a 总为正，判定仍由最短停机时间决定；但如果某机组 c < S/(m·6 h)（例如 CCGT 低于 36.7 £/MWh），结论会翻转。OCGT 在 H 约 2.3–4.5 h 时判定翻转，由先停 OCGT 改为先弃风。

**有意没做的一项（转入遗留问题）：** 取值表 `gridform_core/data/thermal/value_thermal_restart_v1.json` 的 `rule.shutdown_segment` 说明文字仍写着 `a(H) = c - S(H) / H`。这段文字参与 `restart_table_sha256`，而这个哈希是修正族 golden（C1–C6、C9）trajectory 区的一列。只改说明文字，就要给 7 个 case 各追加一次完整修订（每次几千到上万行）。修正式本身还待作者确认，所以我把这处文字留到作者确认 A22a 时，与一次 golden 修订一起改。改法已存成补丁，只改这一句。取值和代码都不受影响，代码与 0.4 草稿以修正式为准。

**本轮门禁与安全核对：**

- `scripts/p0_gate.py quick`（`VALUE_GATE_VENV` 指向 gate venv）在暂存状态下运行：status passed，16 步全部通过，无豁免。
- r12、native_market_rules、result_advisories、runtime_overlay_seal、methodology_profiles 共 79 个测试 OK。
- `refresh_source_release_manifest.py --index --check` 未过期。
- INSTALLED：`find … -newer install-receipt.json …` 只列出原有的现网 `.supervisor.lock`。`diagnose-value` 输出 "Installation integrity and runtime checks passed."（中间那行 vinext "Premature close" 提示与以往相同）。
- 没有启动服务，18xxx 端口无监听，没有向任何进程发信号，INTEG 中没有 `__pycache__`，没有 push。

**遗留问题补充：**

6. **A22a 待作者确认。** 确认后，把取值表的 `rule.shutdown_segment` 说明文字改为修正式，并对 C1–C6、C9 做一次 golden 修订（只有 `restart_table_sha256` 一列）。如果作者不同意，回退 `net_saving` 和本轮的文档改动，并在 A22a 记为接受的简化。
7. 交接文档目前没有写停机段公式（已 grep 核对）。补写 R1-2 内容时（第 7 节第 1 条），应以 0.4 草稿的修正式为准。
