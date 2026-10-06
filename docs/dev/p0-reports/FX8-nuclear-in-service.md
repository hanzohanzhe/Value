# FX8 工作报告：修正口径核电开局在运（DECISIONS A18）

- 分支：`fix/review-2026-10-04`（INTEG）。开始时的基点为 `39c5dd7`。
- 授权：A18。作者决定修正口径中核电从第 0 期起处于在运状态，按各站可用率作基荷；启动成本只在换料或停运后重启时收取。这是方法改动，需要新规则集版本和 correction id，按 Q13 须显式确认，修正族 golden 修订一次并附数值报告。论文复现口径不变（Q1），路径依赖按 A15 披露。验收：GBP1 public2 修正口径一年，核电对 Energy Trends 5.1 在 ±10% 内。
- 提交：
  - `7bf170e` feat(psm): corrected-profile nuclear starts each year in service (A18)
  - `6631fc1` docs(methodology): nuclear in-service rule and doctoral path dependency for 0.4; GBP1 corrected re-acceptance after A18
  - 本报告单独提交（docs(p0)）

## 1 机制核查

默认 PSM（`value-bid-at-cost-psm`）每个模型年调用一次 `run_simulation`（`scheme_c_native_psm.py` 每年新建机组对象）。`run_simulation` 中 `accepted_bids = []`，`ahead_market_bidding` 对“不在上一期接受集合中”的燃气、生物质、核电在报价上加 `startup_cost`；`physical_cost_terms` 按同一集合（`_p06_previous_accepted`）记物理启动项。所以每年第一期所有火电和核电都带启动加项，核电（GBP1 为 500 £/MWh）一直排在最后，直到第一次缺电。

`accepted_bids` 在第一次出清前只用于这两处（只读每行的资产），第一次出清会整体替换它（`accepted_bids[:] = accepted_bids_period`）。因此最小改动是：修正口径下在出清前把每个核电机组放进 `accepted_bids`。

## 2 做了什么（`7bf170e`）

| 位置 | 改动 |
|---|---|
| `native_market_rules.py` | 新字段 `nuclear_initial_state`：论文 `off_until_accepted`，修正 `in_service_at_start`；开关 `fx8.nuclear-in-service-at-start`（`FIELD_CORRECTIONS` 与字面量查询表）。规则集 id 不变，sha 变化（与 FX6 的做法相同） |
| `data/methodology/corrections/fx8.json`（新） | profile_gated，scope market_clearing，affects trajectory/accounting，trigger fixture `tests.test_fx8_nuclear_in_service.NuclearInServiceTests`；advisory（high）：论文口径的 Run 核电年初不在运、要付启动成本才能进入，披露 A15 的路径依赖和 GBP1 的量级；deviation_signature 写明论文口径的行为 |
| `native_corrected.py` | `initial_running_rows(generators)`：每个 `NuclearGenerator` 一行 `[asset, 0, 0, 0]`；`IN_SERVICE_AT_START_TYPES = ("NuclearGenerator",)` |
| `runtime_compat/modular_simulation_model.py` | `run_simulation` 在 `accepted_bids = []` 之后，规则为 `in_service_at_start` 时改为 `initial_running_rows(generators)`。论文路径不变。已 `seal_runtime_overlay.py --correction fx8.nuclear-in-service-at-start` |
| 版本 | `value-bid-at-cost-psm` 6.3.0 → 6.4.0，`requires_user_opt_in = true`（VERSION_LEDGER 包 FX8）；manifest、`SchemeCNativePSM.version`、`docs/generated/*`、UI 合同夹具（`psm_module_version` 与规则集 sha）同步 |
| golden | 新增修正族 case **C9**（见第 4 节）；C1–C8、D1–D3 只有 identity 差异；`P0_GOLDEN_DELTA.md` 重新生成 |
| CHANGELOG | correction id 表加 FX8 行；新增小节 “Nuclear in service at the start of the year”；Known issues 中修正口径的核电路径依赖标为已解决；golden 摘要加 C9 |

规则的结果：

- 年初核电第一期报价 = 运行成本（GBP1 为 0），排在最前，按可用率（`p05.firm-availability`，A10/A14 各站负荷率）作基荷；
- 某期未被接受（可用率为 0、换料、停运或未出清，例如预测需求为 0 的时段）之后，下一期起报价重新带启动成本，直到再次被接受；重启那一期物理运营成本记一次启动项；
- 燃气、生物质不变（仍是年初不在运）。

## 3 测试

新增 `tests/test_fx8_nuclear_in_service.py`（9 个，全部 OK）：

- `NuclearInServiceTests`（trigger fixture，直接调用 `ahead_market_bidding`）：
  - 规则字段与 `initial_running_rows` 只包含核电；
  - 带 500 £/MWh 启动成本的核电：修正口径第 0 期报价 0、`startup_component_applied` 为 False、出力 40 MW、物理启动项 0；论文口径第 0 期报价 500、未被接受；
  - 强制停运：第 2 期可用率为 0，未被接受；第 3 期报价 500（仅这一期带启动加项），被接受；物理启动项只在第 3 期出现一次，等于重启电量 × 500；
  - 开关只在修正口径启用，目录条目为 gated。
- `SyntheticLoopTests`（96 时段合成场景，live loop，即当前 `run_simulation` 文本）：
  - 修正口径核电第 0 期 20 MWh，到第 81 期（合成场景中预测需求为 0 的时段，什么都不出清）之前每期都在运，此前启动项为 0；第 81 期之后的重启付一次启动成本；论文口径前 8 期核电为 0；
  - 用替换的 driver 在第 40、41 期把核电可用率设为 0、第 42 期设高需求：停运两期，第 42 期重启，第 81 期之前只在第 42 期付一次启动成本，金额等于重启电量 × 500；兼容调整为 0。
- `MethodChangeTests`：VERSION_LEDGER 的 FX8 升级要求 opt-in；去掉 fx8 的旧修正集合在迁移分类中为 `method_upgrade_required`；论文口径不含此修正。

修改的已有测试：`test_native_market_rules`（规则表两行、开关前缀允许 `fx8.`）、`test_result_advisories`（旧 Run 多一条 high 级 advisory，排在 review 之后）。

运行结果：

- `vpy -m unittest tests.test_fx8_nuclear_in_service tests.test_fx6_ahead_imports tests.test_native_corrected_rules tests.test_fx4_storage_orders tests.test_native_market_rules tests.test_fx5_voll tests.test_native_operating_cost tests.test_p04_balance_boundary tests.test_native_realise_period tests.test_native_reproduction_golden tests.test_result_advisories tests.test_runtime_overlay_seal tests.test_methodology_profiles tests.test_methodology_identity`：修改两个测试后 OK（第一次运行的 3 个失败都是预期的规则表和 advisory 列表更新）。
- golden 与相关：`test_golden_digest`、`test_golden_research_pack`、`test_golden_corrected`、`test_golden_delta_report`、`test_golden_doctoral`、`test_fx7_gbp1_public2`、`test_catalog_lazy`、`test_ui_contract_fixtures`、`test_methodology_static_scan` 等共 166 个：OK（skipped 2，Windows 路径）。
- `capture.py check --tier fast`：C1–C4、C7、C8、D1–D3 gated 0（只有 identity）。`capture.py validate`：passed。`capture.py check --cases C9`（未提供 `VALUE_P0_5_PACKS`）：列为 unavailable，passed。
- `check_methodology_catalog.py`、`check_version_ledger.py`、`seal_runtime_overlay.py --verify`、`generate_reference_tables.py`、`delta_report.py --check`（0 条无法归因）、`refresh_source_release_manifest.py --check`：通过。
- `scripts/p0_gate.py quick`：提交 1 之前在完整工作树上 passed（14 步，无豁免，backend_ratchet 无新失败）；文档提交后、报告提交前再跑一次，见第 8 节。

## 4 golden：新 case C9 与数值报告

VALUE 101 的机组没有核电，所以 C1–C8 的 trajectory 和 accounting 都不变，修正族中没有可以“修订”的已有 case。按 FX7 偏差 3（“等作者决定核电规则后再加 GBP1 修正口径 golden”），本单元新增 **C9**：

- 定义：`tests/golden/cases.json`（family corrected，tier full，`research_pack` = `gbp1-public2-local`，manifest sha `f43e0e46…1439`），冻结项目 `tests/golden/projects/C9.json` = D5 项目改 `data_pack_id = value-uk-open-data-pack-public2`；默认修正口径（corrected case 不能钉 profile 参数，由 `test_golden_digest` 检查）；模块与参数同 D5（legacy 储能电价、doctoral 碳因子情景），与 FX7 验收运行相同。
- revision 0：`git archive 39c5dd7`（A18 之前；只补入 C9 的 case 定义和冻结项目）的 `run_case.py C9 --keep-output`，`capture.py init --from-output --base-commit 39c5dd7`。
- revision 1：工作树的同一运行，`capture.py revise --from-output --correction-id fx8.nuclear-in-service-at-start --finding A18`。差异：trajectory 394、accounting 220、identity 28 列。
- 数值报告：`capture.py numeric-report --case C9 --before-output … --after-output …`，写到 `docs/dev/p0-reports/fx8-golden/C9-r1.json`。`tests/golden/reports/` 按 `capture.py validate` 的规则只能放论文口径的 trajectory 重基线报告，放修正族报告会被判为错误，所以放在 p0-reports 下（见第 6 节偏差 2）。
- 论文口径 golden 不变：D1–D3 gated 0；D5 不受影响（规则字段只在修正口径生效）。

## 5 GBP1 public2 修正口径本地重跑（验收）

完整结果见 `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` 第 10 节。做法同该文档第 2、9 节：`build_value_uk_pack_revision.py --link hardlink` 在 scratch 中构建 public2（manifest `f43e0e46…`，与 FX7 相同），两次运行（before = 39c5dd7 archive，281 s；after = 工作树，535 s），独立的 `VALUE_DATA_HOME/HOME/TMPDIR`，网络守卫无越界；构建前后两个来源目录的文件清单哈希相同；运行输出和临时包用完已删除，没有发布、没有上传。

| 2025 | A18 前 | A18 后 | 参照 / 判定 |
|---|---:|---:|---|
| 核电（TWh） | 2.02（第 16593 期起 927 期） | **38.26（17,520 期全部在运）** | ET 5.1 约 37.3：**+2.5%，通过** |
| 径流水电（TWh） | 6.06 | 6.01 | DUKES 5.77：+4.2%，通过 |
| 陆上 / 海上 / 光伏 CF | 0.370 / 0.499 / 0.112 | 0.362 / 0.498 / 0.110 | DUKES 0.258 / 0.401 / 0.103（A9 披露项） |
| CCGT / OCGT（TWh） | 101.41 / 0.95 | 67.53 / 1.47 | |
| 弃电（TWh） | 0.43 | 1.74 | |
| 进口 / 出口（TWh） | 1.558 / 0.413 | 1.376 / 1.511 | |
| 时段均价 / 最高（£/MWh） | 24.30 / 74.06 | 16.23 / 46.30 | Q6 时段平均成本口径 |
| 头条运营 / 系统成本（百万英镑） | 5,711.6 / 28,682.8 | 3,880.9 / 26,852.1 | −1,830.7 |
| 直接排放（MtCO2） | 40.58 | 27.56 | |
| 投资提案（MW） | 3,054.8 | 2,810.5 | |
| 校验 / stress | 全部通过 / 0 | 全部通过 / 0 | |

- before 与 FX7 验收的 after 逐项相同（可复现）。
- after 与 FX7 的诊断运行（核电 `startup_cost` 设为 0）所有汇总指标逐位相同：核电全年没有停过，启动成本从未起作用。规则上的区别只在停运后（toy 测试覆盖）。

## 6 采用的决定与偏差

采用：A18（只改修正口径；年初在运；启动成本只在停运后重启时收取）；Q13（新 correction id 改变修正口径的 applied-corrections 哈希，PSM 6.4.0 标 opt-in）；Q1/Q12（论文口径 trajectory 不变）；A15（方法学草稿和 advisory 披露论文口径的路径依赖）；A16-7（public2 只在本地）。

偏差：

1. **“新规则集版本”的实现方式。** 规则集 id `native-corrected-v1` 是能量平衡边界登记的键（C19），改 id 会牵动边界登记和已有账本。我按 FX6 的先例新增规则字段（规则集 sha 变化）并升级 PSM 模块版本 6.4.0，没有改规则集 id。
2. **修正族数值报告的位置。** `capture.py validate` 只允许 `tests/golden/reports/` 存放论文口径 trajectory 重基线报告，所以 C9 的报告放在 `docs/dev/p0-reports/fx8-golden/C9-r1.json`（同一个 `numeric-report` 命令，`--out` 指定位置）。
3. **新增 C9 而不是修订已有 case。** VALUE 101 没有核电，C1–C8 的 gated 区不变；只有新增 GBP1 case 才能让这条规则进入 golden。C9 依赖本地构建的 public2（`VALUE_P0_5_PACKS`），没有它时 check 列为 unavailable，不失败（与 D5 相同）。
4. **“在运”的范围。** 只有核电年初在运；燃气、生物质保持论文规则。可用率为 0 的核电年初也被视为在运，但因为不能出清，下一期即按“停运后重启”处理。新投运的核电项目（HPC、SZC 以整年为单位进入）在其第一个运行年的第 0 期同样在运。
5. **advisory 级别。** 论文口径 Run 的 advisory 取 high，因为 GBP1 上的量级（核电约 36 TWh）很大；它只影响展示顺序，不影响结果发布（Q14 只看 raw invariants）。
6. **启动后的“停运”定义沿用内核。** 某期未被接受即视为停运（包括预测需求为 0 这类没有任何出清的时段）。这是 A18 原文“换料或停运后重新启动”的保守实现：没有引入新的停运日历（A10 的可用率是固定值）。

## 7 遗留问题

1. 生物质几乎不运行（0.01 TWh）仍未处理（FX7 遗留第 3 项）。
2. public2 仍只在本地；是否发布、网站是否引用 GBP1 修正口径数字，由作者决定。C9 只有提供 public2 时才会运行。
3. 根目录的 `VALUE_*_2026-10-04.md` 是负责人的本地副本（git exclude），本单元没有改；`docs/handoff/` 下的三份交接文档已更新。
4. R029/GBP1 public1 的光伏曲线严格读取问题（FX7 遗留第 2 项）不变。

## 8 门禁、安装目录与环境检查

- `p0_gate.py quick`：提交 1 前在完整工作树上 passed；报告提交前再跑一次 passed（提交说明记录）。
- 安装目录：`find …/installed -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（作者在运行的 supervisor 的锁文件，以往报告都有记录）；`diagnose-value --prefix …/installed` 退出码 0，输出 “Installation integrity and runtime checks passed.”（中间有一行 vinext 静态文件流 “Premature close” 提示，不影响结论）。本单元没有写入安装目录。
- 没有启动 HTTP 服务，没有连接 8766/8800，没有向任何进程发信号；两次模型运行是我启动的后台进程，按记录的 PID 等待结束（只用 `kill -0` 检查是否存在）。18xxx 端口无监听。
- 所有 Python 通过 `vpy` 调用；INTEG 中没有 `__pycache__` 或 `.pyc`。没有下载文件，没有改动 SRC 工作树，没有 push。
