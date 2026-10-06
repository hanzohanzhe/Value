# FX4 M-D1：把真实的储能报价写进账本（DECISIONS A16-1，Q12）

分支 `fix/review-2026-10-04`（INTEG）。作者授权见 A16（“必须修 + 强烈建议一起修”），M-D1 属于“强烈建议一起修”。

## 1 问题

四类用户测试 M-D1（`docs/handoff/FOUR_ROLE_TEST_REPORT.md` 3.3 节）：默认 PSM 内核
`runtime_compat/modular_simulation_model.py`（原 3451-3461 行）写 `orders` 时只登记发电机报价。
放电的电池只得到一行 `final_dispatch`：reason 为 `accepted_non_generator_offer`，报价写死为 0.0，
offered 等于 accepted；没有被接受的储能报价完全不写。真实报价只能在 `clearing_inputs.payload_json`
里找到。所以储能成本模块的作者没法从订单表核对自己的报价公式。

## 2 先确认冻结范围（报告 7 节的前提）

- `orders` 表各列在 golden 中**第一次记录时就是 trajectory 区**。zones.json 只把 `orders.physical_resource_cost_gbp`
  和 `orders.market_payment_gbp` 划为 accounting。按 `golden.pinned_zones`，列的区只能变严，不能变松。
  所以改写电池那一行，或者往 `orders` 里加行，都会让 doctoral trajectory 变化（`orders.#rows`、
  `offer_price_gbp_per_mwh`、`status` 等）。这既违反 Q12，工具也会直接拒绝。
- 结论：`orders` 一行不动，真实报价写进一张**新的 accounting 表** `storage_orders`。它和 `orders`
  在同一个 market.sqlite 里，首列结构与 `orders` 平行。这是本单元对任务措辞“写进 orders 账本”的保守解读，
  记为偏差 1。

## 3 做了什么

| 位置 | 改动 |
|---|---|
| `gridform_core/builtin/scheme_c_1000twh/native_storage_orders.py`（新） | `StorageOfferTrace`：只读记录。两个阶段在排序前声明各自的报价列表，用的是清算声明生成 `offer_id` 的同一个列表、同一套序号；内核在每次 `Battery.discharge` 之后报告这条报价交付的功率。按 `id(item)` 对应，并持有该列表，保证同一时段内 id 唯一。ahead 阶段开启新时段；时段不符也会重置，所以冻结 HEAD 循环（复现 harness）不会累积。`rows()` 生成账本行，状态和原因码为 `accepted/cleared`、`partially_accepted/demand_filled`、`rejected/no_energy_delivered`（轮到了但没交付）和 `rejected/merit_order_not_reached`（还没轮到，阶段就已满足）。 |
| `runtime_compat/modular_simulation_model.py` | 加了 5 个钩子，都不改动报价、排序或放电：模块级 `_STORAGE_OFFERS`（不重新绑定）；ahead 和 balancing 在 `declared_offers` 之前各调一次 `declare`；两处 `discharge` 之后各调一次 `deliver`；full trace 写完 `orders` 后调用 `record_storage_orders`。已用 `seal_runtime_overlay.py --correction fx4.storage-offer-ledger` 登记。 |
| `gridform_core/market_ledger.py` | 新增 `StorageOrderLedgerRow`（17 列）。`storage_orders` 加入可选表登记（首次写入才建表，没有储能报价的账本表集合不变）。在 Protocol、Null 和 SQLite 三处加 `record_storage_orders`。`metadata.rows.storage_orders` 自动计数。文件原本混用 CRLF 和 LF，按行保留原来的行尾。 |
| `gridform_core/data/contracts/market-ledger-storage-orders-v1.schema.sql`（新） | 表结构、各列口径、状态和原因码的定义，以及与 `orders` 电池行的对账关系。 |
| `tests/golden/zones.json` | `market/market.sqlite::storage_orders.*` 划为 accounting（why 引用 M-D1、A16-1、Q12）。`metadata.json::*` 原本就是 accounting。 |
| golden | D3、C3 追加 accounting 修订（20 列：新表 18 列、`metadata.rows.storage_orders`、一日教学结果中的 ledger 行数），**trajectory 0**，identity 11（PSM 版本号与代码身份）。D1、D2、C1、C2、C4 的 smoke 时段没有储能报价，所以不建表，只有 identity 差异；C7、C8 不受影响；D4、C5、C6 是 summary trace，不写这张表；D5 缺研究包，unavailable。`docs/release/P0_GOLDEN_DELTA.md` 已重新生成，`--check` 结果为 0 条无法归因。 |
| 版本 | `value-bid-at-cost-psm` 6.0.0 → 6.1.0，`requires_user_opt_in=false`（只是代码身份升级，Q13），已在 VERSION_LEDGER 登记 bump（package FX4，correction `fx4.storage-offer-ledger`）。同步修改了 manifest、`SchemeCNativePSM.version`、`docs/generated/MODULES.md`（生成脚本），以及 UI 合同夹具 `value-101-day.capabilities.json`（`psm_module_version`，由生成器 `--write` 写入）。 |
| `tests/native_reproduction_harness.py` | `RecordingLedger.record_storage_orders` 只记录、不进入合成 golden 的列。live 循环会调用这个方法，缺了会抛 `NotImplementedError`。 |
| 文档 | `docs/visibility-refactor/MARKET_LEDGER.md` 增加一段“Storage offers (M-D1)”；`CHANGELOG.md` 在 correction id 表中加一行，并新增一个小节。 |

## 4 口径（模块作者怎么对账）

- `offer_price_gbp_per_mwh` = 储能成本模块的 `bid_price_gbp_per_mwh(dwell_periods)` × `bidding_factor`（报价乘数）。
  `dwell_periods = period - charge_period`。
- `clearing_offer_id` 等于 `clearing_inputs` 中同一报价的 `offer_id`（`ahead:s:<序号>:<资产>:<充电时段>`、
  `balancing:s:...`）；`offered_mwh` = 声明的 `maximum_power_mw` × 时段长度。
- `accepted_offer_value_gbp` = 报价 × 接受 MWh，也就是内核记入的储能费（`add_price_*`）。
- doctoral 规则集下，一个电池在一个时段的各条报价 accepted 之和，等于 `orders` 中它的 `final_dispatch` 行，
  也等于 `storage_energy_audit.discharge_output_mwh`。corrected 规则集按时段净头寸结算，同时段买回后，
  `orders` 行是净值，所以报价之和 ≥ `orders` 行（C3 第 30 时段：报价 5 MWh，买回后净值约为 0）。

## 5 测试

新增 `tests/test_fx4_storage_orders.py`，共 8 个测试，全部 OK：

- 模块作者公式（12 + 3 × dwell）接入真实内核的 `ahead_market_bidding` 和 `balancing_market_bidding`：
  - 每一行，不论是否被接受，报价都等于公式 × 乘数；
  - ahead 的三档分别为 cleared、demand_filled、merit_order_not_reached；
  - balancing 阶段的报价 dwell ≥ 2，接受量合计等于缺口；
  - 接受量之和等于电池的销售账。
- 关掉钩子与开着钩子的清算结果逐位相同，证明记录是只读的。
- 时段不符时返回空；无关的 item 被忽略。
- 真实 SQLite 账本：`storage_orders` 与 `clearing_inputs` 中全部 `storage_discharge` 报价一一对应，价格、
  offered 和充电时段都一致，且价格不是 0.0；没有储能报价时不建表。
- 96 时段合成场景的 live 循环（dynamic、legacy_tariff 两种）：既有 accepted 也有 rejected；
  每个时段、每个电池的接受量之和等于冻结的 `orders` 电池行，而该行价格仍为 0.0。
- corrected 规则集：报价按毛值记，`orders` 行 ≤ 报价之和（买回）。

`tests/test_p04_variant_fixtures.py`（VALUE 101 七个变体，doctoral 规则集）：

- `storage_orders` 加入允许新增的 accounting 表集合；
- 新测试 `test_storage_orders_reconcile_with_the_bid_formula_and_dispatch` 检查四件事：报价与 `clearing_inputs` 声明一致；每个资产、每年的 价格/乘数 对 dwell 呈线性（doctoral 线性报价）；接受量等于审计放电和 `orders` 电池行；全体变体中出现了 rejected。

运行结果：

- `vpy -m unittest tests.test_fx4_storage_orders tests.test_p04_variant_fixtures`：18 个，OK。
- `capture.py check --tier fast`：修订前只有 D3、C3 的 20 列 accounting 差异，trajectory 0；修订后通过。
- `capture.py validate`：passed。
- `delta_report.py --check`：passed。
- `check_version_ledger.py`：passed。
- `generate_reference_tables.py --check`：passed。
- `tests/ui_contract_fixtures.py --check`：重新生成后通过；唯一的差异是 `psm_module_version`。
- `capture.py check --cases D4 C5`（full 档，two_year，summary trace）：gated 差异 0，只有 identity 差异，passed。
- `scripts/p0_gate.py quick`（提交 `08ee3d7` 的暂存内容）：status passed，16 个步骤全部 passed，没有豁免。步骤包括 guard、test_environment、release_manifest、release_path_hygiene、methodology_catalog、runtime_overlay、version_ledger、golden_bookkeeping、append_only、backend_ratchet、node_tests、http_harness、typecheck_frontend、eslint_ratchet、network_guard、installed_inventory。

## 6 采用的决策

- **Q12**：只新增 accounting 区的表和列；`orders` 和其他 trajectory 列一律不动。golden 修订只记在 D3、C3，并带 universal correction id `fx4.storage-offer-ledger`。
- **A16-1**：M-D1 在修复范围内；两个口径都写。
- **Q13**：这次是代码身份升级（6.1.0，不需要用户确认），不是方法改变。

## 7 偏差

1. **新表，不改 `orders`。** 任务要求把报价“写进 orders 账本”。但 `orders` 各列已固定在 doctoral trajectory 区，
   改写或加行都会改变冻结的 trajectory，与“doctoral 逐位不变”冲突，工具也会拒绝。所以我选了保守做法：
   在同一个市场账本里新建 accounting 表 `storage_orders`，`orders` 的电池行保持原样，并在 schema 和
   MARKET_LEDGER.md 中写明它是净调度记录、不是报价。
2. **版本号 6.1.0。** 计划 3.5 中 `planned_sequence` 写的是“6.1.0 (P0-7)”，只是参考信息。P0-7 实际没有升
   PSM 版本，所以这次由 FX4 使用 6.1.0。如果同一轮里其他 FX 单元（例如 S-D3 的修正口径日前进口，属于方法改动）
   也要升 PSM，应在当时的现行版本上继续递增（C23）。
3. **合成 golden 不纳入新表。** 复现 harness 的 `RecordingLedger` 只记录 `storage_orders`，不计入合成 golden 的列，
   所以 `doctoral_reproduction_golden_v1.json` 不加修订。覆盖由新测试中的 live 循环对账承担。
4. **只写 full trace。** 与 `orders` 相同，summary trace 不写这张表（D4、C5、C6、D5 不受影响）。

## 8 未决与提示

- 前端尚未展示 `storage_orders`（设计规格没有这个视图）。`AuditView` 的订单表仍只读 `orders`。是否在 Inspect 中加一个“Storage offers”表，由设计方决定。
- 账本数据字典 `market/field-dictionary.json` 只覆盖 VRE 削减和网络列，所以没有加这张表的字段说明。字段口径写在 schema SQL 和 MARKET_LEDGER.md 中。

## 9 提交

- `08ee3d7` feat(psm): real storage offers in the market ledger (M-D1)
- 本报告单独提交（docs(p0)）。

## 10 安全核对

- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出现网 supervisor 的 `.supervisor.lock`。这个文件安装时就有，不在 app/runtime/installer 之下，M8 报告也有同样记录。`diagnose-value --prefix …` 退出码为 0，输出 “Installation integrity and runtime checks passed.”。
- 没有启动 HTTP 服务；没有连接 8766/8800；没有向任何进程发信号。18xxx 端口没有监听。
- INTEG 中没有 `__pycache__` 或 `.pyc`，所有 Python 都通过 `vpy` 调用。scratch 中的临时运行输出（约 6 MB）已删除。
