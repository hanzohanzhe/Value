# R3-2 工作报告：分区再调度的经济下调次序（DECISIONS A24-3，依据 A19、A22、A22a）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `1724b8d`。
- 授权：A24 第 (3) 项：分区再调度的下调次序也按 A19/A22/A22a 处理。不停机段先降；停机段按 a = c − S/(m·H) 与弃风的 0 比较。只在修正口径的网络模型中生效，属于方法改动（Q13），golden 修订并附报告。
- 提交：
  - `babd81a` feat(network): staged/zonal dec order weighs restart cost against avoided cost (A24-3, A19/A22/A22a)
  - 本报告单独提交（docs(p0)）

## 1 原来的问题

staged PSM（`value-staged-bid-at-cost-psm`）先在铜板上排日前计划，再平衡实际时段。平衡可以用铜板（`value-copperplate-balancing`），也可以用分区 LP（`value-zonal-redispatch-balancing`）。P0-8b 的规则集 `network-economic-v1` 让燃气、生物质机组把整个日前出力按避免成本 c = SRMC × m_dec − 补贴 报一个 dec。c > 0，而无补贴风电的 dec 价为 0，所以平衡总是先把火电降到零，然后才弃风，与重启成本无关。这就是 A19 在默认 PSM 中撤回的“先降火电”次序。A24-3 要求网络模型也改。

## 2 规则（实现内容）

新规则集 `network-economic-v2`（`network_method_rules.ECONOMIC`，字段 `thermal_shutdown = restart_cost_vs_avoided_cost_v1`）。燃气（CCGT、OCGT）和生物质机组 k 在时段 t 的日前计划量为 P_k。与 R1-2 相同，日前排了的机组视为在线且满载。

| 段 | 量（MWh） | dec 报价（£/MWh） | dec 类别 |
|---|---|---|---|
| 不停机段 | (1 − m_k)·P_k | c_k（与 P0-8b 相同） | `fuel` |
| 停机段，H ≥ T_k | m_k·P_k | a_k(H) = c_k − S_k(H)/(m_k·H) | `fuel_shutdown` |
| 停机段，H < T_k | m_k·P_k | min(a_k, 当期其他 dec 的最低 0.01 价位 − 0.01) | `fuel_shutdown_last_resort` |

- **取值**：直接读 R1-2 的参数表 `gridform_core/data/thermal/value_thermal_restart_v1.json`，文件不改。m 为 0.50 / 0.50 / 0.35；S 为 CCGT 110/130/150（热/温/冷，按 H 选），OCGT 170，生物质 125 £/MW；T 为 6 h / 0.5 h / 6 h。a 的计算直接调用 `native_corrected.RestartParameters.net_saving`，与 R1-2 同一个函数，测试逐项核对。
- **H**：H = (1 + n_t) × 时段长度。n_t 是 t 之后连续满足“预测需求 ≤ 申报的 VRE 与核电可用量”的时段数，计数用 `native_corrected.surplus_run_after`，与 R1-2 相同。分区模式下用对齐后的全国预测需求。staged 的可用量数组同时用于日前和实际，所以这里的“预测可用量”就是申报可用量，记为 `declared_period_availability_vre_plus_nuclear`。
- **技术映射**：staged 的技术名为 `CCGT`、`OCGT`；`gas` 视为 CCGT，资产 id 含 OCGT 时视为 OCGT（对应内核按名称判断）；`bio*`（`bio_and_waste`）视为生物质。其他燃料机组（DSR、油）仍按 c 报一段。核电、径流水电、进口、储能、出口都不变。
- **排序**：
  - 共享类别次序改为 `fuel, import, storage, run_of_river, vre, fuel_shutdown, nuclear, fuel_shutdown_last_resort`。
  - 铜板：先按 0.01 取整价降序，再按类别次序，再按精确价。
  - 分区 LP：primary 阶段最小化 −价×量；精确同价时，由 physical tie 阶段的类别权重决定，新增 `fuel_shutdown` 3.5、`fuel_shutdown_last_resort` 5。PuLP/CBC oracle 的独立权重表同步增加这两项。
  - 结果：不停机段（c > 0）总在弃风之前；停机段只有在 a 高于风电 dec 价时才先于弃风，同价归风电，即 A22 的严格不等号“a > 0”；因为 a < c，同一机组的停机段在 LP 中也不会先于它自己的不停机段被接受。
- **H < T 的最后手段**：做法与 R1-2 偏差 6 相同（见第 6 节偏差 2）。
- **结算**：被接受的 dec 按自身报价退款。a < 0 的停机段相当于每 MWh 收到 |a|，即扣除省下燃料后净承担的重启成本。物理运营成本的口径不变，重启成本不入账，与 R1-2 相同。
- **新输出**：
  - 停机段的 bid id 为 `balance:<年>:<期>:down-shutdown:<资产>`。不停机段沿用原 id `...:down:<资产>`。provenance 记录 `dec_segment`、`net_saving_gbp_per_mwh`、`expected_downtime_h`、`start_class`、`restart_cost_gbp_per_mw`、`min_stable_fraction`、`min_down_time_h`。两段都进入 orders 与 redispatch_settlement 账本。
  - 每个 staged 市场年记录 `extensions.downward_restart_economics`（`value.network-downward-restart-economics/v1`），内容包括规则、取值表 id 与 sha256、H 口径、全年平均 H、下调时段数及其平均 H，以及按段统计的已接受 dec 量（MWh）和时段数。分段为：不停机段、正节省停机段、排在弃风后的停机段、低于最短停机时间的停机段、VRE、跨境、储能、水电、核电、其他。
  - 年度累计放在 `zonal_account_totals` 的前缀键 `downward_restart_economics::` 下，做法与 C22 的 agent 成本相同，所以分年内 checkpoint 恢复后仍连续，`StagedPSMRuntimeState` 的 schema 不变。低于 1e-6 MWh 的接受量视为 LP 数值噪声，不计入。

## 3 方法改动登记（Q13）

- correction id：`r32.network-economic-downward-order`。
- `value-staged-bid-at-cost-psm` 1.4.0 → 1.5.0，`requires_user_opt_in = true`。scientific_version 改为 `value-staged-network-restart-economics-2026.10.07`。已保存的 Study 会被归为 `method_upgrade_required`，原因中列出这个 id（有测试）。
- 规则集 id 由 `network-economic-v1` 改为 `network-economic-v2`，规则记录写入八类次序、取值表 id 与 sha256 和公式。旧规则集保留为 `ECONOMIC_P08`，与 `LEGACY` 一样不再被任何模块默认使用，只供测试对照。它的定义和 sha 逐字节不变（`3f858ac9…922f`，有测试）。
- copperplate 1.1.0 与 zonal 4.0.0 的源码没有改，版本也不变，两者从共享表读取新类别（台账说明中写明）。

## 4 文件

| 位置 | 改动 |
|---|---|
| `gridform_core/network_method_rules.py` | `DEC_CLASSES` 八类，另设 `DEC_CLASSES_P08`；`NetworkMethodRules.thermal_shutdown`；`ECONOMIC` = v2，`ECONOMIC_P08` = v1；新增 `restart_technology`、`ThermalDecSegments`、`thermal_dec_segments`、`last_resort_price`、`shutdown_horizon_hours`、`dec_segment_label`；物理权重新增两类 |
| `gridform_core/builtin/scheme_c_1000twh/staged_psm.py` | 版本 1.5.0；逐期计算 H；`_flexibility_bids(…, horizon_h)` 拆段（`_thermal_dec_bids`），最后手段定价（`_price_last_resort_shutdowns`）；平衡后汇总，年度结果写 extension。文件是 CRLF/LF 混合行尾，已按原行尾逐行恢复，diff 只含实际改动 |
| `gridform_validation/zonal_oracle.py` | 独立权重表增加 `fuel_shutdown` 3.5、`fuel_shutdown_last_resort` 5 |
| `gridform_core/manifests/value-staged-bid-at-cost-psm.json` | 版本、scientific_version（混合行尾已保持） |
| `docs/release/VERSION_LEDGER.json` | staged 1.4.0 → 1.5.0（R3-2，opt-in） |
| `tests/test_r32_network_economic_dec.py`（新） | 20 个测试，见第 5 节 |
| `tests/test_network_dec_pricing.py` | `test_nuclear_is_decremented_last` 按新规则改期望（燃气不停机段 1 MWh，然后弃风 6 MWh，停机段为最后手段，核电不动），并保留 P0-8b 规则下的旧期望作对照；`run_staged` 只对 LEGACY 用 bid_id 平局规则 |
| `tests/test_prompt95_staged_copperplate.py` | 版本断言 1.5.0 |
| `tests/golden/corrected/C7.json`、`C8.json` | 各追加一次修订（C7 r13、C8 r15） |
| `docs/dev/p0-reports/r32-golden/C7-r13.json`、`C8-r15.json` | 数值报告 |
| `docs/methodology/drafts/0.4/r32_network_economic_downward_order.md`（新） | 方法学 0.4 草稿：规则、H、算例、输出、数字、0.3 待改处、中文摘要 |
| `docs/methodology/drafts/0.4/p08_network_economics.md` | dec 价表燃料行加注，新增 R3-2 修订段，中文摘要加一条 |
| `docs/MATHEMATICAL_REFERENCE.md`、`docs/scientific-readiness/ZONAL_SOLVER_CONTRACT_V4.md` | 规则集 id、权重、两段公式 |
| `docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md` | 4.8 节新增第 6 条记录（网络模型也使用本节取值，取值不变） |
| `CHANGELOG.md` | correction id 表、golden 摘要、新增小节 “Economic down-regulation order in the network models” |
| `docs/generated/MODULES.md`、`docs/release/P0_GOLDEN_DELTA.md`、`source-release-manifest.json` | 重新生成 |

## 5 测试

新增 `tests/test_r32_network_economic_dec.py`，共 20 个测试，全部 OK。

- **规则单元**（`SegmentRuleTests`，7 个）：
  - a(H) 与默认 PSM 的 `net_saving` 逐项相同（CCGT、OCGT、生物质，多个 H），并与 c − S/(m·H) 一致；R1-2 的算例值（OCGT H = 5 h 时 a = 7；H = 3 h 时 a = −38.3）。
  - 类别与标签（正节省、排在弃风后、a < 0、H < T 的最后手段、H = T 的边界）。
  - 只拆分燃气和生物质；核电、水电、DSR 不拆；v1 规则集和 LEGACY 下不拆；技术名映射。
  - 最后手段价格。
  - H 的计数。
  - 规则身份：v2 记录完整；v1 的 sha 不变；模块默认用 v2。
  - 铜板分组次序：不停机段 > 正节省停机段 > 风 > 同价停机段 > 核电 > 最后手段。
- **staged 铜板 toy**（`StagedCopperplateToyTests`，6 个；镜像 R1-2：OCGT 20 MW、c = 75，风 30 MW，需下调 25 MWh，H 由多时段的预测盈余自动算出）：
  - (a) H = 5 h：OCGT 降到 0，风只弃 5 MWh。extension 记下 1 个下调时段、H = 5 h，按段为不停机 10、正节省停机 10、VRE 5。
  - (b) H = 3 h：OCGT 只降不停机段 10 MWh，风弃 15 MWh。
  - P0-8b 规则下同一算例 OCGT 降到 0，且没有新 extension。
  - (c) 下调量在不停机段之内：CCGT 70 → 50，风不动。
  - CCGT c = 55、H = 3 h < 6 h：先降不停机段 10 MWh，再弃完全部风电 5 MWh，最后只停 3 MWh；最后手段段记 3 MWh。
  - bid 证据：两条 bid 的 id、量、价、provenance，以及不给 H 时取当期 1 个时段。
- **两区 LP 与 CBC oracle**（`TwoZoneLPTests`，4 个）：北区有 OCGT 20 和风 30，南区需求 35，南区 CCGT 报价 £90；北区需求 10，南北边界 15 MWh。边界迫使北区下调 25 MWh，而全国盈余只有 5 MWh。
  - H = 5 h：OCGT 0、风 25、南区 CCGT +20。
  - H = 3 h：OCGT 10、风 15。
  - P0-8b：OCGT 0、风 25。
  - 以上三例中，生产 LP（HiGHS）与独立 PuLP/CBC oracle 的 `compare_zonal_solutions` 都 passed，调度逐项一致。
  - 精确同价（停机段价为 0，等于风电价）：physical tie 阶段先弃风（OCGT 10、风 15）。这一例中生产解的锁定容差被 stable 阶段花掉约 1.1e−6 MWh，比较工具判为 “degenerate_solution_or_tie_break_difference”。两侧审计都通过，调度差 < 1e−5，测试按此断言。这是 LP 锁定容差在精确平局下的已知性质，不是规则不一致。
- **实际 staged 分区 Run**（`LiveZonalRunTests`，1 个，两种 H）：同一两区算例经 staged PSM 和 `ZonalRedispatchBalancing` 实跑，H 由 PSM 从预测需求和风电可用量算出（5 h 和 3 h），结果与上面一致。规则集记录为 `network-economic-v2`。
- **Q13**（`MethodChangeTests`，2 个）：台账 1.4.0 → 1.5.0 带 opt-in，与 manifest 和类版本一致；`revision_migration` 把 1.4.0 → 1.5.0 归为 `method_upgrade_required`，原因中含 correction id。

回归：

- 网络相关 34 个测试模块（`test_network_*`、`test_p08*`、`test_prompt9x/10x/115/67/68/70`、`test_staged*`、`test_zonal*`），加上 r32、r12、native_market_rules、methodology_profiles，改动前后用同一命令各跑一次（改动前在 `git archive 1724b8d` 上跑）。改动前失败 29 个，改动后失败集合完全相同，新增失败 0。这 29 个都是既有失败，例如 prompt95 的旧模块身份 `value-copperplate-balancing 1.0.0` 与 `force-copperplate-balancing 1.1.0` 不一致、prompt102 的 solver_validated 判定，与本单元无关。
- `check_version_ledger.py` passed；`check_methodology_catalog.py` passed；`generate_reference_tables.py --check` passed；`capture.py validate` passed；`delta_report.py --check` passed（未归因 0）；`refresh_source_release_manifest.py --index --check` 未过期。
- `scripts/p0_gate.py quick`（`VALUE_GATE_VENV` 指向 gate venv，在暂存状态下、功能提交之前运行）：status passed，16 步全部通过（guard、test_environment、release_manifest、release_path_hygiene、methodology_catalog、runtime_overlay、version_ledger、golden_bookkeeping、append_only、backend_ratchet、node_tests、http_harness、typecheck_frontend、eslint_ratchet、network_guard、installed_inventory），没有豁免。

## 6 采用的决定与偏差

采用：A19、A22、A22a（公式与取值）、A24-3、Q3（网络模块不进论文口径）、Q13（opt-in）、Q8（上调方向储能在发电之后，不变）。

偏差与解释：

1. **方法改动的登记方式**：沿用 P0-8 的先例，correction id 只登记在模块版本台账（staged 1.5.0，opt-in），不写入方法学目录（`corrections/*.json`）。
   - 原因：staged、zonal 等模块只在修正口径可用（Q3），不需要按口径开关；`methodology.py` 的注释也写明 p08.* 这类网络模型修正由网络模块版本承载。
   - 如果写入目录，会改变修正口径的 `applied_corrections_sha256`，从而让所有修正族 golden（C1–C6、C9、C10）的身份全部变化，而这些 case 根本不经过网络模型。
   - 规则集 id 与 sha 改变，Run 记录可以区分新旧规则。
2. **H < 最短停机时间**：A22 说只有 H ≥ T 才允许进入停机段。与 R1-2 偏差 6 相同，实现为最后手段，否则无其他下调资源的分区会让 LP 无可行解。
   - 在 LP 中“最后”只能靠价格表达，所以报价取 min(a, 当期其他 dec 的最低 0.01 价位 − 0.01)，类别次序和物理权重也排在最后。
   - 代价是：被迫走到这一步时，该机组按这个更低的价结算。provenance 里同时保留经济净节省 a。
   - C8 中这一段一直被拒绝，没有实际结算发生。
3. **与风电比较的“0”**：A24-3 写的是“与弃风的 0 比较”。网络模型中风电 dec 价本来就是 −补贴（P0-8b 的经济定价），默认无补贴时为 0。停机段与风电按价格比较，有补贴时比较对象是 −补贴。这是 A19“与风电弃电代价比较”在已有定价下的直接推广；默认参数下与“与 0 比较”完全一致。分段标签 `thermal_shutdown_net_saving` / `thermal_shutdown_after_vre` 按 a 的正负划分，与 R1-2 一致。
4. **0.01 价位的不一致（既有）**：铜板按 0.01 取整价分组，LP 的 primary 用精确价。a 落在 (0, 0.005) 时，铜板判为与风同价（先弃风），LP 先停火电。这是 P0-8b 已记录的性质（p08 草稿第 1 节末），本单元没有改。
5. **重启成本不入成本账、在线容量 = 日前计划量**：与 R1-2 偏差 4、5 相同。
6. **copperplate 的 docstring 仍列六类**：为保持 copperplate 与 zonal 模块源码逐字节不变（版本不变），没有改它们的注释。类别次序以 `network_method_rules.DEC_CLASSES` 和文档为准。
7. **C8 数值报告的生成方式**：与 R1-2 偏差 3 相同。`capture.py numeric-report` 要求 parent 输出与 r14 的完整指纹一致，而 r14 之后其他单元改过代码身份，parent 在 identity 区有 47 列不同（gated 区 0）。所以先核对 parent 的 gated 区为 0、child 与 r15 完全一致，再直接调用 `golden.build_numeric_report`，并在报告中写入 `parent_reproduction` 说明。C7 走标准命令。

## 7 golden 与数值

- **C7**（staged 铜板 smoke）r13：这个 case 里没有平衡 dec。变化只有规则记录（metadata 中规则集 id、sha、类别次序和新增字段，accounting 区 8 列）和新 extension（trajectory 区 9 列，全部为 0；全年平均 H 0.5 h）。报告 `docs/dev/p0-reports/r32-golden/C7-r13.json`。
- **C8**（分区 LP，VALUE 101 一天）r15：
  - 新 extension：42 个下调时段全部是弃风（257.1 MWh），平均 H 0.93 h（全天平均 0.875 h）。
  - CCGT 在这一天从未被下调，与改动前相同。它的 40 条 dec 现在各拆成两条：不停机段 66.5 £/MWh；停机段因 H < 6 h 为最后手段，报价约 −373.5 £/MWh（= 66.5 − 110/(0.5×0.5)）。所以 bid 账本多 40 行。
  - 调度、弃电、成本只有求解器容差级别的变化：发电和弃电最大差 1.4e−7 MWh，系统成本最大差 9.3e−6 £。原因是 LP 多了变量，各阶段锁定后的解在容差内移动。
  - 共 94 列 trajectory、81 列 accounting 变化，几乎都是 bid 行和上述噪声。报告 `docs/dev/p0-reports/r32-golden/C8-r15.json`。
  - 修订说明中写明是在 `1724b8d` 之上的 R3-2 工作树捕获。
- 论文族、C1–C6、C9、C10 不经过网络模型，不受影响（规则集只由 staged PSM 使用；默认 PSM 的 R1-2 规则未改）。

**影响为什么很小**：两个参考网络 case 都只有一天以内，H 很短（≤ 1 h），而 CCGT 的最短停机时间是 6 h，所以停机段即使出现也只能是最后手段。C8 的下调由分区约束触发，全部落在风光上。改动前 CCGT 的 dec 也从未被接受，因为它与风电不在同一个受约束分区。规则切换的效果由 toy、两区 LP 与 CBC oracle、实际 staged 分区 Run 证明（第 5 节）。

## 8 提交、门禁与安全核对

- 功能提交 `babd81a`；本报告单独提交。门禁结果见第 5 节。
- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`。这是现网 supervisor 在本轮之前创建的锁文件，以往报告都已记录。`diagnose-value --prefix …/installed` 退出码 0，输出 “Installation integrity and runtime checks passed.”，中间的 vinext “Premature close” 提示与以往相同。本单元没有写入安装目录。
- 没有启动 HTTP 服务，没有连接 8766/8800，18xxx 端口无监听，没有向任何进程发信号。golden 运行都是我在前台启动、自行结束的进程，使用独立的 TMPDIR 和 VALUE_DATA_HOME（scratch 下）。
- 所有 Python 都通过 `vpy` 调用；INTEG 中没有 `__pycache__`。没有下载，没有改 SRC，没有 push。
- scratch 中的 HEAD archive 与运行输出用后已删除。

## 9 遗留问题

1. **四份交付文档**（简报、四角色测试报告、两份交接文档）本单元没有改。按 A25，由负责人在 R3 结束后按最终状态从头重写。需要写入的内容：`r32.network-economic-downward-order`、规则集 `network-economic-v2`、staged PSM 1.5.0、方法学草稿 `r32_network_economic_downward_order.md`、本报告第 7 节的数字。
2. **重启成本的币值**（A24-4）由另一单元处理。本单元直接读参数表，换算后自动生效；规则记录中的 `restart_table.sha256` 和 extension 中的 `restart_table_sha256` 会随之变化，C7/C8 届时需要再修订一次（只变这一列）。参数表的 `applies_to` 文字目前只写了 r12，可以在那次修订中顺带加上 r32，避免为改一句说明文字单独修订全部修正族 golden。
3. 两个网络参考 case 时长太短，看不到停机段的实际作用。如果作者想看规则在 GB 尺度分区算例中的影响（例如 GBP1 zonal 一年），需要另行安排运行（耗时长）。
4. 第 6 节偏差 2（最后手段的结算价）和偏差 3（有补贴时比较对象为 −补贴）请作者知悉；如果不同意，改动集中在 `network_method_rules.last_resort_price` 和 `thermal_dec_segments`。
