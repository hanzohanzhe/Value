# F2-corrected-data：A9/A10/A13（及 A14）修正口径实现

分支：`fix/review-2026-10-04`（INTEG 工作树）。日期：2026-10-06。只改修正口径（`value-corrected`），论文复现口径（`doctoral-lineage-0.6.0a2`）不变。

## 1 做了什么

### 1.1 A13 光伏倾斜面换算（`p05.solar-plane-of-array`）

- 新增 `gridform_core/solar_irradiance.py`，逐个半小时时段计算：
  - 太阳位置：Spencer（1971）赤纬、时差、日地距离修正；时段中点取 365 天 UTC 模型年（第 `t` 期为第 `t//48+1` 天，UTC `(t mod 48)/2+0.25` 时）；时角由 UTC + 经度/15 + 时差得到；斜面入射角用 Duffie & Beckman 式 1.6.5、1.6.7。
  - 分解：Erbs、Klein & Duffie（1982）`kd(kt)`，`kt = GHI/(I0n cos z)` 截断到 [0,1]，太阳常数 1361 W/m²（Kopp & Lean 2011）。
  - 斜面换算：Hay–Davies（1980），地面反照率 0.2。
  - 倾角：朝南，Jacobson & Jadhav（2018）北半球最优倾角拟合式（51.5°N 约 36.0°，GBP1 各站 35.7–37.7°）。A13 允许"站点纬度或文献最优倾角"，两种规则都实现，参数表选文献最优；纬度规则作为敏感性报告。
  - 天顶角 > 87° 或 GHI = 0 时无直射，按各向同性散射处理，所以倾角为 0 时逐期精确返回 GHI。
  - CF = min(POA × PR 0.83, 1)。
- `site_weather.py`：`SiteWeatherMethod` 增加 `plane_of_array` 字段，方法 id 在 P0-5b id 后加 `+solar-poa-v1`（没有该步骤的旧运行保持原 id）；`method_for` 询问 `enabled("p05.solar-plane-of-array")`；新增 `method_for_correction_ids`（结果披露按运行记录的修正 id 还原天气方法）和 `plane_of_array_applies`。
- 时间约定（P0-5b）：天气 v2 下第 `t` 期取标在 `t//2+1` 的累积量，即包含该时段的小时；几何取时段中点，落在该累积小时之内。
- 适用范围：只对 v2 时钟下的 ERA5 逐时累积量换算。VALUE 101 合成数据（52°N 十二月正午约 1 kW/m²，非物理值）不换算；R029 public1 的 `ssrd` 没有 GRIB step type，也没有声明约定，P0-5b 已把它当瞬时量，因此也不换算。站点证据中写明原因。
- 参数与出处写入 `value_uk_vre_loss_factors_v1.json` 的 `solar_plane_of_array` 段（模型选择 PENDING AUTHOR REVIEW）；该表的损耗系数状态按 A9 改为作者已认可，海上 `author_decision_pending` 改为 A9 的裁定。
- `solar_irradiance.py` 加入 `doctoral_weather.weather_execution_identity` 的源文件清单（与 P0-5b 加入 `site_weather.py` 的做法相同）。

### 1.2 A10 核电按月退役（`p05.nuclear-generation-end-month`）

- 各站负荷率按 A14 不变（0.668 / 0.689 / 0.752 / 0.792 / 0.801，即参考统计表 1.4a 均值四舍五入到 3 位）。
- 站点政策文件 `value_uk_nuclear_policy_v1.json` 中 Heysham 2、Torness 只写 "2030"。该文件两轨共用（asset 扩展字段里也有这个字符串），所以没有改它，而是在 `value_uk_firm_availability_v1.json` 中新增 `generation_end_month_overrides`（2030-03，参考统计表 1.6 节 N6/N3），只在修正口径经新修正 id 使用；覆盖值必须与政策文件的年份一致，否则报错。结果：四座 AGR 都在 2030 年第 4320 期起为 0；Sizewell B（"2055"）全年运行。
- `firm_availability.py` 新增 `FirmMethod`（`LATEST`、`P05B`）与 `method_for_profile`；canonical 适配器和内核注入都传入该方法，证据中记录 `firm_method`；证据 `status` 改为读参数表（"AUTHOR REVIEWED (DECISIONS A14, 2026-10-06)"）。

### 1.3 A14 径流水电（`p05.hydro-dukes-load-factor`）

A14 在本单元开始后才写入 DECISIONS（提交 `fb5db0a`），要求替换水电值、登记 correction id、修订一次修正族 golden。因为它和 A10 改的是同一张参数表、同一次 golden 检查，本单元一并完成：

- 年负荷率 0.3487（DUKES 6.3 标准口径 2019–2024 均值），月度形状 `[1.3851×3, 0.6582×3, 0.6776×3, 1.2791×3]`，数值与 A14 逐字一致。P0-5b 的 0.334 与平直形状保留在 `p05b_values`，供未应用本修正的运行解释。
- 按 365 天日历，形状的时段加权均值为 0.99883，模型年负荷率为 0.3483。GBP1 的 2000 MW 年发电 6.10 TWh，比 DUKES 6.2 2019–2024 均值 5.77 TWh 高 5.8%，在 ±15% 以内（有测试）。

### 1.4 A9 披露（结果载荷与方法学）

- 新参数表 `gridform_core/data/weather/value_uk_vre_cf_disclosure_v1.json`：DUKES 2026 表 6.3 标准口径逐年值与 2019–2024、2020–2024 均值（取自 F1 参考统计表 3.4 节），7 条偏差原因，以及按"天气与 fleet 文件 sha256 × 天气方法"登记的模型弃电前 CF（代表站点等权平均，17520 期）。
- `scripts/vre_cf_disclosure.py --write/--check` 由数据包计算并核对这些行（VALUE 101、GBP1 public1、R029 public1）。
- `gridform_core/vre_cf_disclosure.py`：由运行冻结包 manifest 的 sha256 和记录的方法学（修正 id → 天气方法）选出对应行。
- `results_summary.build_run_summary` 新增 `vre_capacity_factor_disclosure`（模型 CF、DUKES、比值、原因、`disclosure_only: true`）。它描述的是天气方法而不是年度结果，Q14 扣发年度结果时仍保留。未登记的天气给 `not_tabulated` 与 DUKES 列；CSV 天气给 `not_applicable`；未记录方法学的运行给 `methodology_not_recorded`。没有改前端（前端由主管设计）。
- 方法学草稿：新增 `docs/methodology/drafts/0.4/f2_solar_poa_firm_cf_disclosure.md`（中英），`p05b_corrected_data.md` 第 3、4 节加更新说明。参考统计表：第 1、2 节标为作者已审核（A14），第 3 节损耗系数已认可（A9），新增 3.5 节（A13 模型选择），3.4 节补 F2 后的光伏 CF。CHANGELOG、模型卡、VALIDATION_AND_CLAIMS 各加一段。

## 2 所得容量因子（代表站点等权平均，17520 期，弃电前）

| 数据包 | 方法 | 陆上 | 海上 | 光伏 |
|---|---|---|---|---|
| GBP1 public1（public2 天气相同） | 论文 v1 | 0.4458 | 0.6028 | 0.1201 |
| GBP1 public1 | P0-5b（v2 + 损耗） | 0.4026 | 0.4913 | 0.0997 |
| GBP1 public1 | **F2 修正（v2 + 损耗 + 倾斜面）** | **0.4026** | **0.4913** | **0.1065** |
| GBP1 public1 | 敏感性：倾角取纬度（未采用） | — | — | 0.1012 |
| VALUE 101 baseline（合成） | 论文 v1 | 0.4132 | 0.3270 | 0.2500 |
| VALUE 101 baseline | F2 修正（光伏不换算） | 0.3731 | 0.2665 | 0.2075 |
| R029 public1 | F2 修正（光伏不换算） | 0.4022 | 0.4913 | 0.0996 |
| DUKES 6.3 标准口径 2020–2024 均值 | — | 0.2582 | 0.4009 | 0.1025 |
| GBP1 F2 修正 ÷ DUKES 2020–2024 | — | 1.56 | 1.23 | 1.04 |

GBP1 光伏：伦敦年 GHI 约 1080 kWh/m²；各站 POA/GHI 1.05–1.10；年散射比例 0.63–0.75。增益偏小，主要因为 GBP1 天气是 2020–2024 多年平均气候态（P6-09）：伦敦能量加权 kt 只有 0.47、最大 0.73，Erbs 式给出偏高的散射比例。同一代码在合成晴空年（51.5°N，kt 0.65）下的增益为 33%。这一点已写进参数表与草稿，作为披露，不做校正。

## 3 修正登记（`corrections/p05.json` 新增）

| id | 发现 | 轨道 | 说明 |
|---|---|---|---|
| p05.solar-plane-of-array | P6-08 | profile_gated | A13，光伏倾斜面换算；advisory medium |
| p05.nuclear-generation-end-month | P5-10 | profile_gated | A10，Heysham 2 / Torness 按月退役；advisory low，只对 GBP1 public1 |
| p05.hydro-dukes-load-factor | P5-09、P6-10 | profile_gated | A14，水电 0.3487 × 季节形状；advisory low |

`p05.firm-availability` 的描述改为"数值已由作者在 A14 审核"。`check_methodology_catalog.py` 通过（三个新 id 都有字面量 `enabled()` 调用）。

## 4 Golden

- `capture.py check --cases C1–C8 D1–D4`（代码改动之后、提交之前）：12 个用例 `gated_differences` 全为 0；只有 identity 区变化（C7 29、C8 35、D1–D4 各 1）。
- 原因：修正族 C1–C8 全部使用 VALUE 101 包，包里没有核电和径流水电资产，合成光伏也不是 ERA5 累积量，所以 A10/A13/A14 都不改变这些用例的 trajectory 和 accounting。按约定"有变化才 revise"，**没有追加修订**；doctoral 族不变。
- A13/A10/A14 的数值由 `tests/test_f2_corrected_data.py` 覆盖（GBP1 用例需 `VALUE_P0_5_PACKS`）。

## 5 测试

- 新增 `tests/test_f2_corrected_data.py`（24 个）：
  - 手算几何：春分正午 51.5°N 天顶角 51.5°、倾角 51.5° 的面正对太阳（cos θ = 1）；夏至正午天顶角 28.05°；春分日落时角 90°；Spencer 参考日（赤纬、时差、日地距离）；时角与模型时钟；Jacobson 倾角 51.5°N = 36.03°。
  - Erbs 数值（kt 0.1/0.5/0.9 → 0.991/0.65915/0.165）；春分正午单个时段的 Hay–Davies 手算（独立标量算式，相对误差 ≤ 0.2%）；低太阳各向同性；倾角 0 返回 GHI（全年随机 GHI，rtol 1e-12）；合成晴空年的年能量合理性（年 GHI 1300–1900 kWh/m²，最佳倾角 30–50°，增益 15–35%）。
  - 方法 id、修正 id 还原、适用范围；VALUE 101 不换算；模拟 ERA5 单站累积量：值 = min(POA × 0.83, 1)，并核对第 16 期取 09:00 的累积量。
  - GBP1 年能量（需研究包）：各站年 GHI 850–1250 kWh/m²，POA/GHI 1.0–1.25，倾角 35–38.5°，CF 0.1065±0.0005，伦敦质心仍为 12.00±0.15 UTC。
  - 核电：Heysham 2 / Torness 2030 年第 4320 期起为 0，P0-5b 方法下全年可用；站值不变；Sizewell B 无月份。
  - 水电：A14 数值、时段加权均值、GBP1 6.10 TWh 在 DUKES ±15% 内、内核恒等式。
  - 披露：DUKES 均值、原因、GBP1 比值（1.5594 / 1.0393）、`build_run_summary` 的四种状态、脚本 `--check`。
- 修改 `tests/test_p05b_corrected_data.py`：修正口径方法加上倾斜面步骤；损耗表状态改为 A9 已认可；核电证据状态读参数表；水电年均值测试改用 `firm.P05B`。
- 运行结果：
  - `tests.test_f2_corrected_data`、`tests.test_p05b_corrected_data`、`tests.test_methodology_static_scan`（设置 `VALUE_P0_5_PACKS`）：全部通过。
  - `run_backend_tests.py --modules`（f2、results_summary、result_advisories、p05b、local_api_boundary）：99 个 id，新失败 0。
  - `scripts/vre_cf_disclosure.py --check`（含 GBP1、R029）：passed。
  - `p0_gate.py quick`：两个功能提交前各一次，都是 passed（15 步，无豁免，棘轮 new 0、fixed 0）；文档提交前一次，见第 9 节。

## 6 采用的决定

- A13：Erbs + Hay–Davies + 逐时段几何 + PR 0.83；倾角取文献最优；只对修正口径。
- A10：各站固定 2019–2024 均值，按月退役。
- A14（本单元开始后新增，优先于任务描述）：核电值不变、状态改为作者已审核；水电 0.3487 与阶梯形状；登记 correction id。
- A9：只披露、不标定；原因写进结果与方法学。
- Q1：doctoral 不变（D1–D4 无 gated 差异）。C15：规则只经 `enabled()` 询问修正 id。

## 7 偏差

1. **核电值没有标 PENDING AUTHOR REVIEW。** 任务要求"参数表中标为待作者审核"，但 A14 已认可核电值并要求改为作者已审核，按 DECISIONS 执行。A13 的光伏模型参数仍标 PENDING AUTHOR REVIEW。
2. **一并实现了 A14 水电。** 它不在任务原文中，但与 A10 是同一张参数表、同一次 golden 检查，DECISIONS 要求完成。如果主管另派了单元做 A14，以本提交为准即可，不需要重复。
3. **没有追加修正族 golden 修订。** 任务要求"修订一次修正族 golden"，但检查结果没有任何 gated 差异（第 4 节），按约定不追加空修订。
4. **光伏换算不用于非 ERA5 累积量。** VALUE 101 合成数据（非物理辐照）与 R029 public1（无累积标记）保持水平面比例。若对 VALUE 101 强行换算，光伏 CF 会因大量削顶而失真。
5. **倾角选文献最优而不是纬度。** A13 两者都允许；纬度倾角在英国偏陡，GBP1 上只增益约 1%（0.1012），作为敏感性报告。
6. **A9 结果载荷用查表。** 模型 CF 来自按天气文件 sha256 登记的表（脚本可复算、可核对），不是运行时逐个计算；未登记的天气只给 DUKES 列与原因。这样不需要改动运行输出，也不影响 golden。
7. **未联网复核文献书目。** 光伏模型文献（Spencer、Erbs、Hay–Davies、Duffie & Beckman、Kopp & Lean、Loutzenhiser、Jacobson & Jadhav）的书目信息与 Jacobson 拟合系数按文献写入，F2 没有联网授权，未在线复核；参数表 `P_note` 已注明。
8. **Heysham 2 / Torness 的月份没有写进政策文件。** 政策文件两轨共用，改它会改变 doctoral 的资产扩展字段；改为修正口径专用的覆盖表。

## 8 遗留问题（交作者/主管）

1. 审核 A13 的模型选择（倾角规则、反照率 0.2、Erbs、Hay–Davies、87° 截止）与 Jacobson 拟合系数的书目。
2. GBP1 多年平均气候态使倾斜增益偏小（P6-09）；是否在下一轮改用单年逐时 ERA5，由作者决定。
3. R029 public1 的 `ssrd` 没有累积标记，修正口径既不平移一小时（P0-5b 遗留），也不做倾斜面换算；public2 已声明约定。是否给 public1 补登记，或只在 public2 上运行修正口径，待定。
4. 水电阶梯形状按 A14 取 12 个月算术均值为 1，按 365 天日历年电量比"负荷率 × 8760 h"低 0.12%；是否改为按天数加权归一化，由作者决定（不影响 ±15% 验收）。
5. 修正族 golden 没有覆盖核电、水电和 ERA5 光伏；A12 计划新增 GBP1 doctoral golden，可考虑同时新增一个 GBP1 修正口径 case。
6. 核电对 Energy Trends 5.1 的 GBP1 全年验收运行仍未做。
7. 前端尚未显示 `vre_capacity_factor_disclosure`；是否展示、放在哪里，由主管按设计规范决定。

## 9 提交、门禁与安装目录检查

- 提交：
  - `dc9fed7` feat(data): corrected solar plane-of-array, nuclear end month, DUKES hydro (A13, A10, A14)
  - `375f522` feat(results): wind/solar CF next to DUKES load factors in the run summary (A9)
  - 本报告与文档的提交（docs）
- 每个提交都刷新了发布清单（`refresh_source_release_manifest.py --index`）。
- 文档提交前的 `p0_gate.py quick`：passed（15 步全部通过，无豁免）。
- 安装目录：`find …/installed -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（现网 supervisor 早于本轮创建的锁文件，以往报告已说明）；`diagnose-value --prefix …/installed`："Installation integrity and runtime checks passed."
- 本单元没有启动服务器，没有连接 8766/8800，没有向任何进程发信号，没有下载文件，没有改动 SRC 工作树；源码树中没有 .pyc。scratch 中只有几个小脚本。
