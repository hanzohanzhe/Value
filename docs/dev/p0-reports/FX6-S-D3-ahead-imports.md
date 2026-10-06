# FX6 S-D3：修正口径的日前互联线进口（DECISIONS A16-2）

分支 `fix/review-2026-10-04`（INTEG）。授权见 A16（作者对四类用户测试修复轮的答复）。A16-2 原文：互联线作为报价方，按当期对侧价格和可用进口量进入日前出清，属于方法改动，只在修正口径生效，按 Q13 须显式确认；论文复现口径不变；须理清 GBP1 论文口径中现有进口发生在哪个环节，并在方法学和界面文案中写清。

## 1 论文内核中进口发生在哪里（追踪结果）

默认 PSM（`value-bid-at-cost-psm`）跑保留内核 `runtime_compat/modular_simulation_model.py`。每期 `kernel_boundary.assign_period` 给每条 `Connection` 设两个量：`transfer_constraint`（MW，带符号：正为进口能力，负为出口能力）和 `external_price`（当期对侧价格）。

| 环节 | 函数 | 互联线的作用（论文规则，`interconnector_import_stage = balancing_residual_only`） |
|---|---|---|
| 日前出清 | `ahead_market_bidding(generators, batterys, …)` | 无。函数不接收 connections，预测需求只由机组报价和储能批次满足 |
| 实时，实际需求 < 预测 | `curtailment_market_bidding` → `store_service_three` | 负约束按正价出口消纳盈余；正约束不起作用 |
| 实时，实际需求 ≥ 预测 | `balancing_market_bidding` | 约束 ≥ 0 的每条线都成为进口报价 `(connection, external_price × 报价乘数, transfer_constraint)`，与边际及之后的机组、存放 ≥ 2 期的储能批次一起排序，只能满足“实际 − 预测”的剩余上调需求。被接受的进口进入最终出力（`import_mwh`），费用记入平衡费和 `bought_fee` |

核对 GBP1（D5，论文口径，本分支代码上重跑，digest 与 golden 最新修订一致，只有 identity 差异）：全年进口 335,895 MWh（0.336 TWh，与 `GBP1_DOCTORAL_BEFORE_AFTER.md` 一致：挪威 164,195、比利时 52,956、荷兰 48,409、爱尔兰 44,495、法国 25,839 MWh），分布在 1,130 个时段，**全部**是实际需求高于预测的时段（全年这样的时段 9,125 个）；实际需求不高于预测的时段一律没有进口。四类用户测试 S-D3 的现象也由此解释：VALUE 101 一日课程 48 个时段中没有一个实际需求高于预测，所以不论法国容量和价格怎么填，都不会出现进口。

## 2 做了什么

提交 1 `c335434`（代码、版本、golden）：

| 位置 | 改动 |
|---|---|
| `native_market_rules.py` | 新字段 `interconnector_import_stage`：doctoral `balancing_residual_only`，corrected `day_ahead_offer_then_balancing_residual`；开关 `fx6.day-ahead-interconnector-imports`（`FIELD_CORRECTIONS` 与字面量查询表） |
| `data/methodology/corrections/fx6.json`（新） | profile_gated 修正，affects trajectory/accounting，trigger fixture `tests.test_fx6_ahead_imports.AheadImportOfferTests`，advisory（info）：论文口径的 Run 只在平衡环节进口 |
| `native_corrected.py` | `import_offers()`、`is_import_offer()`、`ImportSchedule`（逐期记录各线日前进口，`remaining_mw` 给平衡环节）；下调栈识别进口：避免成本 = `external_price`，类别次序 0.5（thermal 之后、hydro/biomass 之前，与 `network_method_rules.DEC_CLASSES` 一致；不改 `DOWNWARD_TABLE`，它属于 P0-8 方法身份），无爬坡下限，不调用 `set_real_gen_energy` |
| `runtime_compat/modular_simulation_model.py` | 全部按规则字段分支，论文路径不变：`ahead_market_bidding` 新增关键字参数 `connections=()`；修正口径把进口报价追加在报价表末尾（稳定排序键使同 0.01 档内顺序为发电、进口、储能，储能报价序号不变）；声明 `ahead:i:` 报价（`resource_kind` import，附对侧价格）和 `imports_in_clearing_offer_set`；出清时进口按 `min(容量, 剩余需求)` 接受，记入 `accepted_bids`（下调费 0）、`gen_list` 和 `ImportSchedule`；平衡环节的边际机组取最后一个被接受的“机组”行（跳过进口），若日前只接受了进口则所有机组从零报价；平衡进口报价容量 = 剩余容量；进口付费诊断（`purchase_fees`）加上日前进口；`orders` 账本把每条进口报价记为 `ahead_offer` 行（offered = 容量 × 0.5 h，accepted = 当期最终进口，状态 accepted/partially_accepted/rejected），不再以 0.0 价的 `final_dispatch` 行出现。已 `seal_runtime_overlay.py --correction fx6.day-ahead-interconnector-imports` |
| 版本 | `value-bid-at-cost-psm` 6.2.0 → 6.3.0，`requires_user_opt_in = true`（VERSION_LEDGER 包 FX6）；manifest、`SchemeCNativePSM.version`、`docs/generated/*`、UI 合同夹具（`psm_module_version`，以及 auction-ahead/orders 夹具中新增的法国进口报价行）同步 |
| 界面文案 | `dataset_slots.py`：五个 `market.<country>.profile` 标签改为 “<Country> interconnector availability (+ import / - export)”，模块说明写明两个口径的用法；`test_catalog_lazy` 的哈希同步（C27） |
| golden | C1–C4 追加修订（correction id `fx6.day-ahead-interconnector-imports`，finding S-D3）：trajectory 16（orders 行与 clearing 声明）、accounting 4、identity 15；出力、价格、成本不变。C5/C6/C7/C8 与 D1–D3 只有 identity 差异；D5 见第 1 节。`P0_GOLDEN_DELTA.md` 重新生成 |
| CHANGELOG | correction id 表新增 FX6 行；新增小节 “Interconnector imports in the day-ahead clearing” |

提交 2 `13b8102`（文档）：方法学草稿 `docs/methodology/drafts/0.4/fx6_day_ahead_imports.md`（论文内核追踪、修正规则、0.3 需改的中英文原句、数字）；`p06_default_psm_clearing.md` 修正规则表加一行；`METHODOLOGY_EDITOR_HANDOFF.md`（C25、N-8、N-9）与 `MODEL_CHANGES_BRIEF.md`（C25）；`VALUE_101.md`、`VALUE_101_ZH.md`、`VALUE_101_TO_VALUE_UK.md`、`README_BILINGUAL.md`、`BUILD_YOUR_OWN_MODEL_101_ZH.md` 的角色说明改为“带符号互联线可用量”，并写明两个口径下进口的用法。

## 3 数值报告

**VALUE 101（修正口径）**：法国 12 MW、82 £/MWh，比 CCGT（含启动加价 66.5 £/MWh）贵。C3 一日：48 条进口报价全部 rejected，进口 0。C5/C6 两年：用 `git archive HEAD` 与工作树各跑一次（`run_case.py --keep-output`），两年进口都是 0，均价、最高价、残差逐位相同，digest 只有 identity 差异。所以 VALUE 101 的出力、价格、成本、投资都不变。

**GBP1 第一年（修正口径）**：发布版 public1 不满足修正口径资格（`GF_DATA_SHORT_SERIES`，修正口径需 public2）。我用 `scripts/build_value_uk_pack_revision.py --link hardlink` 在 scratch 中本地构建 public2（manifest sha `35a58c31…6f30`，未登记、未发布，用完已删除；构建前后对 `data-audit/staging/gbp1-national` 与 `r029-public1` 的文件清单取哈希，相同），以 D5 冻结项目加 `methodology.profile = value-corrected` 跑一年，FX6 前（HEAD archive）与后：

| 2025 | FX6 前（6.2.0） | FX6 后（6.3.0） | 变化 |
|---|---:|---:|---:|
| 进口合计（TWh） | 0.331 | 1.560 | +1.229 |
| 挪威 / 比利时 / 荷兰 / 爱尔兰 / 法国（GWh） | 130.3 / 66.2 / 44.6 / 67.9 / 22.4 | 612.4 / 285.6 / 255.5 / 240.8 / 166.2 | |
| 有进口的时段 | 1,301（全部为实际 > 预测） | 2,837（其中 1,389 为实际 > 预测） | |
| 实际 ≤ 预测时段的进口（TWh） | 0 | 0.774 | |
| CCGT / OCGT（TWh） | 102.722 / 0.846 | 101.449 / 0.941 | −1.273 / +0.095 |
| 出口（TWh） | 0.393 | 0.411 | +0.018 |
| 时段均价 / 最高价（£/MWh，Q6 时段平均成本） | 24.45 / 100.31 | 24.30 / 74.06 | −0.15 / −26.24 |
| 头条运营成本 / 系统成本（百万英镑） | 5,738.82 / 28,709.98 | 5,713.24 / 28,684.40 | −25.58 |
| 记录的切负荷、stress 事件 | 0 / 0 | 0 / 0 | 0 |
| 原始能量平衡残差（绝对值之和，MWh） | 4.2e-8 | 4.3e-8 | 数值噪声 |

OCGT 小幅上升是 CCGT 爬坡状态的路径效应。这只是本地核对，不是标定；A16-7 的修正口径全年验收另行进行。

## 4 测试

- 新增 `tests/test_fx6_ahead_imports.py`（14 个，全部 OK）：
  - 便宜进口（30 £/MWh）在日前挤掉 CCGT（55）：论文口径 CCGT 100、进口 0，修正口径进口 40、CCGT 60，声明中有 `ahead:i:` 报价，统一价下进口收 55；
  - 贵进口（90）在国内容量足够时不被接受（两个口径）；容量不足时修正口径进口补缺 20 MW；
  - 负约束（出口）和零约束不在日前报价；同 0.01 档内排序为发电、进口、储能；
  - 平衡环节只报剩余容量：日前进口 50 后平衡再进口 30（合计 = 80 MW 容量），CCGT 补 20；多个实际需求下进口不超过容量，供给 + 缺口 = 需求；
  - 下调：70 £/MWh 的进口先于 55 的 CCGT 被减少 20 MW，付费随之减少，削减费 0；进口的下调排序键、避免成本、爬坡下限；
  - 96 时段合成场景 live 循环（两个规则集）：修正口径有进口，除 A2 时段 8–12 外原始残差为 0，兼容调整为 0；进口 `orders` 行均为 `ahead_offer`，accepted ≤ offered，逐期之和等于 `import_mwh`；论文口径进口仍只以 `final_dispatch` 行出现；
  - 开关只在修正口径启用；VERSION_LEDGER 的 FX6 升级要求 opt-in；去掉 fx6 的旧修正集合在迁移分类中为 `method_upgrade_required`。
- 更新：`test_native_market_rules`（规则表、开关前缀允许 fx6、临时目录按包写修正文件）、`test_fx5_voll`（按 FX5 包查升级记录）、`test_catalog_lazy`（slot 哈希）、`test_result_advisories`（旧 Run 多一条 info 级 advisory）。
- 结果：
  - `vpy -m unittest tests.test_fx6_ahead_imports tests.test_native_corrected_rules tests.test_fx4_storage_orders tests.test_native_market_rules`：OK；`tests.test_native_reproduction_golden`（论文合成 golden）等相关模块 OK，唯一失败是隔离区已有的 `test_doctoral_market_alignment`（R0 私有源码不在本机）。
  - `capture.py check --tier fast`：修订前 D1–D3、C7、C8 gated 0，C1–C4 各 20 列；修订后由门禁 `golden_bookkeeping` 复核通过。D5 单独跑：gated 0。C5/C6：前后 digest 只有 identity 差异。
  - `check_methodology_catalog.py`、`check_version_ledger.py`、`delta_report.py --check`（0 条无法归因）、`generate_reference_tables.py`、`tests/ui_contract_fixtures.py --write`：通过。
  - `scripts/p0_gate.py quick`：提交 1 前 status passed（16 步，无豁免）；提交 2 前再跑一次 passed。第一次运行时 backend_ratchet 报 `test_result_advisories` 新失败（多一条 advisory），已改测试；release_manifest 因未暂存的文档失败，分两次提交后解决。

## 5 采用的决策

- **A16-2**：只在修正口径生效；按对侧价格和可用进口量进入日前出清；平衡环节不重复计算；出口和削减行为保持一致。
- **Q13**：方法改动。新的 profile_gated 修正改变修正口径的 applied-corrections 哈希，同时 PSM 6.3.0 标 `requires_user_opt_in`，旧 Study 须在界面确认。
- **Q1/Q12**：论文口径 trajectory 逐位不变（D1–D5 gated 0）。DOCTORAL 规则集加了字段，规则集 sha 变化，属于 identity。
- **Q8/P0-6 排序键**：进口不是储能，同档内排在发电之后（输入顺序）、储能之前。

## 6 偏差

1. **报价价格乘报价乘数。** 决策写“按当期对侧价格”。我沿用论文平衡环节已有的报价 `external_price × bidding_factor`，使两个环节的进口报价一致（默认乘数为 1）；物理运营成本与下调避免成本仍按不乘乘数的对侧价格计。
2. **下调与结算。** 决策没有写进口在削减分支怎么处理。我取保守做法：已接受的日前进口按避免成本（对侧价格）参与下调，类别次序 0.5，不付削减费（只是不再购买这部分电量）；结算沿用修正口径的统一边际价，进口可以成为边际报价。
3. **只有进口被日前接受时。** 原代码在没有机组被接受时把首个机组当作边际机组，会把它排除出平衡（GB 机组表中首个总是 VRE，影响为零）。修正口径在“日前只接受了进口”时改为所有机组从零报价，避免该问题；论文路径不变。
4. **orders 账本的进口行。** 修正口径中进口报价以 `ahead_offer` 行记账（accepted 为当期最终进口，含平衡环节，与机组行口径相同），不再出现 0.0 价的 `final_dispatch` 行。C1–C4 因此有 trajectory 区修订（corrected 族允许）。
5. **界面文案只改后端标签。** 设计规格没有针对此项的条目，所以没有改前端组件；数据页显示的角色标签来自 `DATASET_SLOTS`，按口径的说明写在教程、README 和方法学草稿中，论文口径的 Run 另有一条 info 级 advisory。未写入 `P0_FRONTEND_DEVIATIONS.md`（没有前端代码改动）。
6. **GBP1 修正口径数字用本地 public2。** public1 不满足修正口径资格；public2 在 scratch 中构建、用后删除，未登记、未发布。

## 7 未决与提示

- GBP1 修正口径全年数字是 FX6 前后的对比，供作者了解量级；正式验收由 A16-7 单元完成（public2 登记、核电分站名单）。
- 0.4 方法学按 `fx6_day_ahead_imports.md` 第 3 节改 `national_alternatives.md`（en 68、76–77 行；zh 67、75 行）与 `datasets.md` 158 行。
- staged PSM（`value-staged-bid-at-cost-psm`）本来就在日前接受进口，不受本单元影响。

## 8 提交

- `c335434` feat(psm): day-ahead interconnector imports in the corrected profile (A16-2)
- `13b8102` docs(methodology): day-ahead interconnector imports draft for 0.4 and data-role copy (A16-2)
- 本报告单独提交（docs(p0)）。

## 9 安全核对

- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出现网 supervisor 的 `.supervisor.lock`（安装时已有，不在 app/runtime/installer 下，FX4、FX5 报告同样记录）；`diagnose-value --prefix …` 退出码 0，输出 “Installation integrity and runtime checks passed.”。门禁的 `guard` 与 `installed_inventory` 均 passed。
- 没有启动 HTTP 服务，没有连接 8766/8800，没有向任何进程发信号；18xxx 端口无监听。
- 所有 Python 通过 `vpy` 调用；INTEG 中没有 `__pycache__` 或 `.pyc`。scratch 中的运行输出、HEAD archive 与本地 public2 已删除。
