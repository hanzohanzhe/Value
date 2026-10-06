# F3-GBP1-doctoral-comparison 工作报告：GBP1 论文复现口径修复前后对比与 GBP1 doctoral golden（A12）

- 分支：直接提交在 `fix/review-2026-10-04`（INTEG），基点 `ef7807f`（F2 报告）。
- 依据：DECISIONS A12（GBP1 研究包在 35aadb3 与 `doctoral-lineage-0.6.0a2` 下各跑一次复现口径，先跑一年；给出进口、电价、成本、排放、投资的前后对比表；新增一个覆盖 A3、A5 的 GBP1 doctoral golden case）。
- 提交：
  - `9431067` test(golden): GBP1 doctoral golden case D5 on the released research pack (A12)
  - `448dbf0` docs(p0): GBP1 doctoral before/after comparison, 35aadb3 vs doctoral-lineage-0.6.0a2 (A12)
  - 本报告的提交（docs）

## 1 做了什么

### 1.1 运行

- 冻结项目 `tests/golden/projects/D5.json` 的内容：D1–D4 的模块（Q3 参考配置：legacy 储能电价、doctoral 碳因子情景），数据包 `value-uk-open-data-pack-v1`，2025–2025，trace summary，`mode=full`（17520 期）。课程模板不描述 GBP1，所以项目是手写的。
- 数据包使用 `data-audit/staging/gbp1-national`。它的 manifest sha256 为 `17a68154…0025`，即发布版 GBP1 public1。运行前后对整个目录的文件清单（路径、大小、mtime）取哈希，两次相同，说明数据包没有被写入。
- BEFORE：`git archive 35aadb3` 解到 scratch，用 `run_project_application(mode="full", run_id="golden-run")` 运行冻结项目，用时 338 s。35aadb3 没有口径参数。
- AFTER：在本分支上运行同一项目，加 `methodology.profile = doctoral-lineage-0.6.0a2`，用时 351 s。
- 归因：另在 1e61e5e、5fe66a3、5014b7b、7e07437 四个提交上用同样的项目和参数各跑一次。用 golden 摘要比较相邻两步：trajectory 只在 5fe66a3（A3/A5）和 7e07437（A4）变化，其余步骤只改核算。35aadb3 与 1e61e5e 的 trajectory 逐位相同。
- 输出、源码树和环境目录都在 scratch 中，用完已删除（约 2.5 GB）。

### 1.2 golden case D5

- `scripts/golden/run_case.py`：case 可以用 `research_pack = {label, manifest_sha256}` 指定研究包。目录从 `VALUE_P0_5_PACKS` 中找，只接受 manifest sha256 与钉住值相同的目录；找不到时抛出 `ResearchPackUnavailable`，以退出码 3 结束。数据包在构建项目之前解析。
- `scripts/golden/capture.py`：
  - `check` 把缺包的 case 列入 `unavailable`，不判失败；设 `VALUE_GOLDEN_REQUIRE_RESEARCH_PACKS=1` 时判失败。`init`、`revise`、`dump` 缺包时一律失败。
  - `init`、`revise` 新增 `--from-output DIR`（只能配一个 case）和 `--base-commit SHA`。修订 0 用这一功能写入 35aadb3 的输出。
  - `numeric-report` 新增 `--child`，记录产生 `--after-output` 的提交。
- `tests/golden/cases.json` 新增 D5：doctoral 族，tier `full`；notes 写明来源。
  - 修订 0：35aadb3 的输出，base_commit 为 35aadb3 的完整哈希。
  - 修订 1：一次性重基线。findings 为 P6-24、P6-02、P6-03、P6-04、P4-01-thermal（白名单中的 A3/A5/A4 条目，各用一次），以及 D1–D4 已登记的核算 findings P3-01、P7-01、P7-10、P5-03。correction ids 为 p05.interconnector-clock、p05.belgium-price-currency、p05.boundary-identity、p05.demand-utc-clock、p07.thermal-net-revenue，加上 D1–D4 历次核算修订使用的 p04.validation-v2、p04.storage-energy-audit、p04.surplus-routing、p04.surplus-node-boundary、p06.physical-operating-cost、p04.validation-gate、p07.cost-ledger-v2。
  - Delta：trajectory 377、accounting 639、identity 64。
  - 数值报告 `tests/golden/reports/D5-r1.json`：parent 为 35aadb3，child 为 ef7807f；1080 列变化，其中 288 列因行移位只给合计。
- 用真实路径 `capture.py check --cases D5 --mode exact`（经 run_case.py，hermetic 环境）复核：gated 差异 0，identity 差异 0，用时 386 s。

### 1.3 对比脚本与文档

- `scripts/gbp1_doctoral_before_after.py`（只读）：
  - `summarise` 汇总每次运行：进口、出口、价格统计、成本账、排放（权威因子事后计算）、stress（账本表加只读核验）、投资和校验状态。
  - `boundary-inputs` 对每条内核 Connection 比较三种读法下的进出口上限和价格：35aadb3、只修 P6-24、通用读法。
- `docs/dev/GBP1_DOCTORAL_BEFORE_AFTER.md`：结论、运行设置、主要指标表（逐项归因）、逐提交归因表、互联线输入拆分、核电与价格尖峰的机制、注意事项、遗留问题、D5 说明和复现命令。

## 2 主要结果（详见对比文档）

| 指标 | 35aadb3 | 修复后 | 归因 |
|---|---:|---:|---|
| 进口（GWh） | 1,548.2 | 335.9 | A3/A5。荷兰线在 35aadb3 接比利时文件、价格全年为 0（P6-03 + P6-02） |
| 时段均价 / 最高价（£/MWh） | 22.35 / 5,849.5 | 18.23 / 50.4 | A3/A5（核电接受时点变化） |
| 头条系统成本（百万英镑） | 28,126.9 | 27,232.0 | A3/A5 −813.0；P0-6 运营成本口径 −25.3；A7 −56.7 |
| 直接排放（MtCO2，事后计算） | 29.91 | 30.91 | A3/A5 |
| A2 stress（事件/时段/MWh） | 168 / 848 / 302,138 | 157 / 890 / 300,855 | A3/A5；能够精确记录来自 A2 |
| 投资提案（MW） | 4,671.8（CCGT 1,717.1） | 3,036.4（CCGT 0） | A4 取消 CCGT；A3/A5 改变规模 |
| 第一年投运（MW） | 0 | 0 | 提案都在 2026 年完工 |

## 3 测试

- 新增 `tests/test_golden_research_pack.py`（11 个）：
  - 仓库包路径；
  - 只接受钉住的 manifest（错 sha、空环境、多目录）；
  - 缺包时 `check` 列为 unavailable，强制模式下失败；
  - `--from-output` 只能配一个 case；
  - D5 钉住发布版 GBP1 public1，项目为参考配置单年；
  - 修订 0 为 35aadb3，修订 1 正好使用 A3/A5/A4 白名单条目，报告的 parent 为 35aadb3；
  - D5 记账有效；
  - 35aadb3 接线表与 P0-5 基线记录一致；
  - 拉伸时钟的小例子；
  - GBP1 用例（需 `VALUE_P0_5_PACKS`）：35aadb3 荷兰线全年价格为 0，通用读法下比利时线均价为 222.2926。
- 结果：
  - 不设研究包：11 个中 10 个通过，1 个跳过；设研究包后 GBP1 用例通过。
- 修改 `tests/test_p07_s10_acceptance.py`：M5 doctoral trajectory 只因 A4 变化的检查对 D5 例外。D5 修订 1 合并了 A3、A5 和 A4，测试要求它正好包含这五个白名单条目。
- 另跑 `tests.test_p07_s10_acceptance`、`tests.test_golden_digest`、`test_golden_doctoral` 的记账测试：42 个，全部通过。
- 门禁：每个提交前都跑 `p0_gate quick`，结果 passed，backend_ratchet 中 new_failures 与 fixed_but_listed 都为空。
  - 第一次运行因发布清单过期失败，用 `refresh_source_release_manifest.py --index` 刷新后通过。
  - `capture.py validate` 通过。
- `capture.py check --cases D5 --mode exact`（设研究包）：passed，gated 0，identity 0。

## 4 采用的决策

- A12：先跑一年（2025）。用时约 6 分钟，不需要改用更短的窗口。
- Q1、Q12：doctoral trajectory 只在白名单 findings 下重基线一次，并附数值报告。核算变化只列 correction id。
- Q6：价格按 “Average period cost” 解读。
- Q14：修复后运行的原始不变量失败，年度结果不发布。文档如实写明，没有改校验。
- A2：stress 只记录，不改调度。35aadb3 的精确缺口取自 trajectory 相同的 1e61e5e 账本。

## 5 偏差

1. **D5 的修订 0 来自 35aadb3 的 git archive，没有用 `capture.py init` 在当前代码上运行。** D1–D4 的修订 0 是 M0 时在等价于 35aadb3 的代码上采集的；而 GBP1 case 在 A12 之后才加入，在当前代码上采集只能得到修复后的行为，也就谈不上 “覆盖 A3/A5”。为此给 capture.py 加了 `--from-output`/`--base-commit`，并在 cases.json notes 中说明。摘要用当前 golden 库计算。
2. **D5 修订 1 一次合并了全部通用 trajectory 修正（A3/A5/A4）。** `test_p07_s10_acceptance` 中 “M5 的 doctoral trajectory 只因 A4 变化且只在 D4” 的断言原本覆盖所有 case，现对 D5 改为单独的断言。逐提交的分离见对比文档第 4 节。
3. **D5 放在 tier `full`，并且依赖研究包。** 缺包时 golden_full 不判失败，只列为 unavailable。仓库不含 804 MB 的研究包，这样做是为了不让没有研究包的机器上的门禁失败；需要强制时设 `VALUE_GOLDEN_REQUIRE_RESEARCH_PACKS=1`。
4. **冻结项目是手写的**，没有用 `freeze-projects` 生成，因为课程模板不描述 GBP1。
5. **排放用权威因子事后计算。** doctoral 碳账不给 tCO2，表中数值不是运行本身的输出。
6. **A3 与 A5 在运行层面没有拆开**，因为它们在同一个提交（5fe66a3）中生效。拆分改在输入层面完成（每条 Connection 的输入表）。

## 6 遗留问题

- GBP1 doctoral 运行的能量平衡门在 `period.surplus_conservation` 上失败，且没有已声明偏差可以解释（471 个时段，最大 991 MWh）。按 Q14，这次运行的年度结果不在结果页发布。是否登记为新的 declared deviation，需要作者决定。
- 核电在冻结内核中的接受与 must-run 有路径依赖：35aadb3 的 30 个价格尖峰和 2.73 TWh 核电都来自这一机制。是否在方法学中说明，需要作者决定。
- 修正口径的 GBP1（public2）全年运行和对应的 golden 仍未做（F2 报告遗留第 5、6 项）。可以沿用本单元的 research_pack 机制。
- `D5` 需要 `VALUE_P0_5_PACKS` 才会运行。CI 或作者机器若要把它当作必检项，需要设置该变量和 `VALUE_GOLDEN_REQUIRE_RESEARCH_PACKS=1`。

## 7 只读安装与环境检查

- `find …/installed -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*' -print` 只列出 `.supervisor.lock`。这是现网 supervisor 在 2026-10-03 创建的 0 字节锁文件，早于本轮工作，M0 报告已说明。
- `diagnose-value --prefix …/installed` 输出 “Installation integrity and runtime checks passed.”。
- 本单元：
  - 没有启动服务，没有连接 8766/8800，没有向任何进程发信号；
  - 没有改动 SRC 的工作树；
  - 源码树中没有 .pyc；
  - scratch 中的大文件已删除。
