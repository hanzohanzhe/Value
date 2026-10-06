# FX7 工作报告：光伏模型认可状态与 GBP1 修正口径本地全年验收（DECISIONS A16-6、A16-7）

- 分支：`fix/review-2026-10-04`（INTEG）。开始时的基点为 `f008114`。
- 授权：A16-6 要求把光伏倾斜面换算的文献模型标为作者认可。A16-7 要求只在本地完成：登记 public2，把它加入核电分站名单（另立 correction id），跑一年，核对核电和水电的量级，结果写进报告。
- 提交：
  - `49ce403` docs(data): A13 solar plane-of-array model choices approved by the author (A16-6)
  - `63fb6e8` feat(data): GBP1 public2 local registration and station nuclear on public2 (A16-7)
  - 本报告与验收文档的提交（docs）

## 1 做了什么

### 1.1 A16-6：光伏模型认可状态（`49ce403`）

- 参数表 `gridform_core/data/weather/value_uk_vre_loss_factors_v1.json`：表头状态和 `solar_plane_of_array.status` 都改为 `AUTHOR APPROVED (DECISIONS A16-6, 2026-10-06)`，列出认可的模型（Spencer、Erbs、Hay–Davies、反照率 0.2、Jacobson & Jadhav 最优倾角）。数值不变。`P_note` 写明作者没有要求联网复核书目。
- 参考统计表：表头状态段和 3.5 节标题都改为作者已认可（A16-6），并加了一段说明。第 4 节第 4 项补注。
- 方法学草稿 `f2_solar_poa_firm_cf_disclosure.md`：中英两处状态措辞已改。
- 修正目录 `corrections/p05.json` 改了两处描述。描述属于展示字段，不进入方法哈希。
  - `p05.solar-plane-of-array` 原写 “tilted at the site latitude”，与代码不符（代码用 Jacobson & Jadhav 最优倾角），已改正。这是方法学交接第 9 节第 3 项提出的问题。
  - `p05.vre-loss-factors` 原写 PENDING AUTHOR REVIEW，但 A9 已认可，已改正。
  - 重新生成了 `docs/generated/METHODOLOGY_PROFILES.md`。
- 交接文档（`docs/handoff/` 下的模型改动简报、网站上传交接、方法学编辑交接）不再把 A13 列为待审。仓库根目录的 `VALUE_*_2026-10-04.md` 是负责人的本地副本（git exclude），没有改动。

### 1.2 A16-7：public2 本地登记与逐站核电（`63fb6e8`）

- **登记。** 在 `methodology.KNOWN_PACK_CLASSES` 中加入 `value-uk-open-data-pack-public2 → scientific_reference`。修正口径因此按 `declared-v2+declared-v2+strict` 读取 public2。论文口径的白名单没有钉住 public2，仍然拒绝它（有测试）。
- **构建器 `@v2`。** 三条逐时 VRE 曲线声明 `interval_minutes` 60。第一次验收运行在严格读取下失败：`sa.csv` 有 8,761 个逐时值，没有声明，声明时钟不认为它是逐时序列，报 `GF_DATA_SHORT_SERIES`。见验收文档第 7 节第 3 项。manifest 由 `35a58c31…` 变为 `f43e0e46…`，数据字节不变。
- **新修正 `p05.nuclear-stations-public2`**（profile_gated，kernel_input，affects trajectory/accounting，发现 P5-10）：
  - `pack_source_identity`：新增 `VALUE_UK_OPEN_DATA_PACK_PUBLIC2_ID`。public2 加入 `NUCLEAR_POLICY_PACK_IDS`，因而也在 `ID_KEYED_PACK_IDS` 中，冻结输入恢复不会把它的恢复副本认作源包。新增 `NUCLEAR_POLICY_GATED_PACK_IDS = {public2}`。
  - `nuclear_policy.applies_to_data_pack(manifest, methodology=None)`：public1 不变。public2 依次向传入的方法学、当前 Run 的方法学、目录默认口径查询 `.enabled("p05.nuclear-stations-public2")`。修正口径下，public2 取得五个 EDF 电站（各自的 A14 负荷率，按月退役）以及外生的 HPC、SZC 管线项目。
  - 目录条目包含 advisory（low）、trigger fixture 和 deviation_signature。修正口径中与数据方法相关的各条修正，`applies_when` 都加上了 public2（展示字段）。
  - CHANGELOG：correction id 表加一行，新增一节，Known issues 加两条（修正口径的核电路径依赖；R029/public1 光伏曲线不能被严格读取）。重新生成 `P0_GOLDEN_DELTA.md` 和参考表。方法学交接第 9 节第 2、6 项写入 FX7 结果。
- **没有改 VERSION_LEDGER。** 做法与 F2 新增修正 id 时相同。新 id 改变了修正口径的 applied-corrections 哈希，旧的修正口径 Study 会按迁移分类提示方法升级。

### 1.3 本地全年验收

详见 `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md`。做法：

- D5 项目，加 `value-corrected`，数据包为 public2，2025 年，full。
- 跑了四次：before（基点代码，未登记的 public2 v1）、mid（基点代码，public2 v2）、after（本单元代码）、sens（只用于诊断：临时副本中核电启动成本为 0）。
- 每次运行都用独立的数据目录。运行后对两个来源包的文件清单取哈希，结果不变。所有输出和临时包都已删除。

结果：

| 项目 | after | 参照 | 判定 |
|---|---:|---:|---|
| 核电 | 2.02 TWh | ET 5.1 约 37.3 TWh | **明显偏离（−95%）**。可用率上限 38.26 TWh（+2.5%）是对的；原因是默认 PSM 的核电启动路径依赖：未运行时报价加 500 £/MWh 启动成本，第 16593 期才第一次被接受 |
| 水电 | 6.06 TWh | DUKES 6.2 5.77 TWh | 通过（+5.1%） |
| 陆上 / 海上 / 光伏 CF | 0.370 / 0.499 / 0.112 | DUKES 0.258 / 0.401 / 0.103 | ×1.43 / ×1.24 / ×1.09。风电偏高，属于 A9 已接受的披露项；光伏差不多 |
| 其他偏离 | 生物质 0.05 TWh（CF 0.1%）；CCGT 101.4 TWh | — | 已标出，未调查 |

敏感性（核电启动成本 0）：核电 38.26 TWh，系统成本 −1,830.7 百万英镑，排放 −13.0 Mt，均价 24.30 → 16.23 £/MWh。

before 与 FX6 报告中 “FX6 后” 的数字逐项一致。mid 与 before 逐位相同，说明 VRE 投资曲线声明对 2025 年结果没有影响。after 与 before 的差异只来自逐站核电，量级很小（系统成本 −1.64 百万英镑）。

## 2 测试

- 新增 `tests/test_fx7_gbp1_public2.py`，共 11 个：
  - `SolarModelApprovalTests`（3 个）：参数表状态、数值不变、参考统计表 3.5 节、目录描述与代码一致。
  - `Public2RegistrationTests`（3 个）：
    - pack_class 登记；
    - 冲突的自报 pack_class 仍判为 user_workspace；
    - 修正口径下为 strict；论文口径不钉住 public2，修正口径接受；
    - 构建器的 PACK_ID 与登记一致。
  - `Public2ProfileIntervalTests`（1 个）：用玩具包构建，验证 `interval_minutes` 60 与 `@v2`；8,761 个逐时值在严格读取下得到 17,520 个时段（每小时重复两次）；去掉声明后报 `GF_DATA_SHORT_SERIES`。
  - `NuclearStationsPublic2Tests`（4 个，是新修正的 trigger fixture）：
    - 目录条目；修正口径开、论文口径关；
    - public2 跟随修正：显式方法学、activate、默认口径三种情况；public1 两个口径都适用，R029 都不适用；
    - id-keyed 集合；
    - GBP1 用例（需要 `VALUE_P0_5_PACKS`）：用硬链接构建 public2，修正口径下 `native_initial_state` 得到五个电站（共 5,958 MW）、nuclear_policy 扩展和核电管线项目，论文口径下得到单一 `Nuclear`；各站可用率依据都是 station。
- 修改 `tests/test_methodology_static_scan.py`：玩具树复制 `nuclear_policy.py`，因为新修正的 `enabled()` 调用在这个文件里。
- 运行结果：
  - 设 `VALUE_P0_5_PACKS` 后，`test_fx7_gbp1_public2`、`test_pack_source_identity`、`test_nuclear_policy`、`test_f2_corrected_data`、`test_p05b_corrected_data`、`test_p05b_pack_revision`、`test_methodology_static_scan`、`test_result_advisories`、`test_methodology_profiles` 共 130 个，OK（skipped 2，跳过的都是其他模块中依赖 Windows 路径的用例）。另外 `test_ui_contract_fixtures`、`test_catalog_lazy` 也 OK。
  - `check_methodology_catalog.py`：passed。
  - `capture.py check --tier fast`：C1–C4、C7、C8、D1–D3 的 gated 差异全为 0（C7、C8、D1–D3 只有 identity 区差异），没有修订。public2 只出现在新 id 中，VALUE 101 包不受影响。
  - `delta_report.py --check`：第一次门禁时因目录多了一行而过期，`--write` 后通过（0 条无法归因）。
  - `p0_gate.py quick`：提交 1 前 passed（16 步）；提交 2 前第一次运行 backend_ratchet 报 `test_golden_delta_report` 新失败（delta 报告过期），重新生成后 passed，new_failures 0、fixed_but_listed 0；文档提交前再跑一次，见第 6 节。
  - `build_value_uk_pack_revision.py --check`：v1、v2 两次构建都一致。数据包验证层：public2 v1、v2 的三层都通过，修正口径资格为 eligible。

## 3 采用的决定

- A16-6：A13 的模型选择由作者直接认可，只改状态，数值不变。
- A16-7：只在本地完成，不发布、不上传。public2 另立 correction id 加入核电分站名单。跑一年，核对核电（ET 5.1，±10%）、水电（DUKES 6.2，±15%）、风光 CF（DUKES 6.3）。标准是“看着差不多”，偏离大的明确标出。
- A9：风光 CF 只披露，不标定。
- A2/P3-01 与 Q13：不改调度规则。核电路径依赖只报告，并给出敏感性。
- Q1：论文口径不变（D1–D3 gated 0；public2 不是论文口径的包）。

## 4 偏差

1. **构建器多声明了 VRE 曲线的 interval。** 任务没有要求，但不声明的话，登记后的严格读取无法运行 public2（第 1.2 节）。声明只对 public2 生效，不改任何已发布的包，也不改真相登记（真相登记中的断言会同时改变论文口径的读取）。
2. **没有修正核电路径依赖。** 验收中核电明显偏离，但原因是调度和报价规则，不是可用率。按 DECISIONS（A2 不改调度；Q13 方法改动须作者确认），只报告并给出敏感性运行。
3. **没有新增 GBP1 修正口径 golden case。** 任务没有要求，而且当前修正口径 GBP1 的核电结果明显偏离，用它作参照不合适。等作者决定核电规则后再加。
4. **public2 的 pack_class 按 id 登记，不按 manifest sha 登记。** 与 public1、R029 的做法相同。理由是 public2 的 manifest 会随边界潮流证据变化（flow_sign verified 与否），按 sha 钉住会让日后补证据的构建失效。M5 报告曾建议 “按哈希登记”，此处取与现有登记一致的做法。
5. **没有升级模块版本。** 与 F2 的做法相同（见第 1.2 节）。
6. **验收的运行设置。** 沿用 D5 的参考配置（legacy 储能电价、doctoral 碳因子情景）加修正口径，以便与 FX6 的核对对照，没有使用修正口径的默认模块组合。

## 5 遗留问题（交负责人或作者）

1. **核电路径依赖（修正口径）。** 是否修改核电的报价或启动规则（例如作为 must-run，或不加启动成本），是否只作用于修正口径。改了之后 GBP1 核电约 38.3 TWh，在 ±10% 内。
2. **R029 public1 与 GBP1 public1 的光伏曲线不能被严格读取**（`GF_DATA_SHORT_SERIES`），而数据包验证层没有发现这个问题。R029 是修正口径的默认国家级数据包。需要决定修法：给数据包补声明、在登记中断言逐时（须另立修正），或扩展验证层。
3. **生物质几乎不运行**（报价只用 gen_cost，排在 CCGT 后面），需要判断是否属于论文方法的预期行为。
4. public2 的边界潮流符号仍未核实（缺 `boundary_flow_reference_2022.json`）。
5. public2 的发布需要作者另行同意。本单元只做了本地登记。

## 6 门禁、安装目录与环境检查

- 文档提交前的 `p0_gate.py quick`：见提交说明（passed）。
- 安装目录：`find …/installed -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`。这是作者在运行的 VALUE supervisor 的锁文件，早于本轮，以往报告都有记录。`diagnose-value --prefix …/installed`：退出码 0，输出 “Installation integrity and runtime checks passed.”。本单元没有写入安装目录。
- 没有启动 HTTP 服务，没有连接 8766/8800，没有向任何进程发信号。四次模型运行都是我自己启动的后台进程，按记录的 PID 等待结束，没有用 kill。18xxx 端口没有监听。
- 所有 Python 都通过 `vpy` 调用。INTEG 中没有 `__pycache__` 和 `.pyc`。临时目录中的运行输出（每次约 340 MB）、临时数据包、源码归档和环境目录都已删除，只留下几个小日志和汇总 JSON（约 120 KB）。没有下载文件。没有改动 SRC 工作树。
