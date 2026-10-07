# R4-3 换数据角色的中低缺陷（DECISIONS A27）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `a18da7a`。
- 范围：最终构建四角色测试报告（`fab9ec2`）第 3.3 节的 S-中1…S-中3、S-低1…S-低7，以及第 7.3 节的时钟、日期与覆盖范围说明。
- 依据：DECISIONS A27（作者：“四角色测试的中低缺陷你也可以一起修好”）。界面按 `P0_FRONTEND_DESIGN_SPEC.md` 的现有组件、token 和文案风格实现；规格未覆盖之处记入 `P0_FRONTEND_DEVIATIONS.md` 的 F-R43-1…6。

## 1 结果一览

| 缺陷 | 结果 | 提交 |
|---|---|---|
| S-中1 回放把 UTC 时钟标成 Europe/London | 已修：统一为 UTC、固定 365 天年，账本元数据、读模型、导出和界面同一规则 | `6a0f2d0` |
| S-中2 逐时/闰年数据被说成“循环重复” | 已修：按读取器的实际分支生成说明 | `4ee6b1e` |
| S-中3 日/月/年被按月/日解析 | 已修：日期顺序自动检测或声明，报告写明依据并提示 | `4ee6b1e` |
| S-低1 分号分隔 CSV 报错误导 | 已修：明确说明“看起来是分号分隔”，请另存为逗号分隔 | `4ee6b1e` |
| S-低2 不满一年也“no problems”，数据年份无提示 | 已修：报告覆盖范围和数据年份，不满一年须另行确认才能提交 | `4ee6b1e` |
| S-低3 Row 含义不一致 | 已修：两处都给数据行号和 CSV 行号 | `4ee6b1e` |
| S-低4 时间戳失败而完整报告写 passed | 已修：完整报告并入时间戳检查 | `4ee6b1e` |
| S-低5 角色卡片看不到汇率；只读时不能浏览角色 | 已修 | `4ee6b1e` |
| S-低6 fx_basis 不校验；price_year 不提示 | 已修：三个枚举值；与 2025 价格基准不同时提示 | `4ee6b1e` |
| S-低7(a) 数据变化被说成“不是储能成本实验” | 已修 | `7929b7b` |
| S-低7(b) Unavailable / Not evaluated 不一致 | 已修 | `7929b7b` |
| S-低7(c) 规划表、标签表 | R4-2 已修（`14c50d2`、`72530bc`），本轮未再改 | — |
| 7.3 时钟、日期、覆盖范围的说明 | 随 S-中1、S-中2、S-中3、S-低2 一并完成 | `6a0f2d0`、`4ee6b1e` |

另有两个提交：`e8ae45d`（S-中1 的后续：`test_stress_events_query` 的时间戳期望改为带 `Z`，重新生成 `docs/generated/MODULES.md` 中完全预见 PSM 的源码哈希；第一次门禁运行时发现），以及文档提交（本报告、`P0_FRONTEND_DEVIATIONS.md` 的 R4-3 一节和 CHANGELOG）。没有未修的缺陷。

## 2 逐项说明

### S-中1 模型时钟

- 查明：所有时序在运行前都放到 UTC 半小时、固定 365 天的时钟上（`series_reader.align_clock` 删去 2 月 29 日；`weather_demand_ensembles.normalize_half_hour_year` 写明 “VALUE uses UTC internally”；`solar_irradiance.period_clock` 按 UTC 小时）。用户按 Europe/London 声明的时间戳在映射时已逐行换成 UTC。只有账本标签写成了 Europe/London。
- 规则（选 UTC 并明确标注，不换算成伦敦当地时间）：模型年 Y 的第 p 期从 Y 年第 `p // 每日期数` 个模型日（闰年跳过 2 月 29 日）的 00:00 UTC 起算，加上日内偏移；没有夏令时；时间写成带 `Z` 的 ISO 8601。不选当地时间的理由：模型日历不含闰日、也没有夏令时的重复和缺失小时，换算成当地时间会在 3 月和 10 月各造出一个不存在或重复的小时，反而误导。
- 实现：
  - 新增 `gridform_core/model_clock.py`（规则、`period_start_iso`、`ledger_clock`）。
  - 账本：`SQLiteMarketLedger` 自己写入 `timezone: UTC`、`calendar: fixed_365_day_utc_periods`，不再由 PSM 提供；默认 PSM 和完全预见 PSM 删除了旧的两行标签。修复前创建的账本在续跑时保留原有（不可变的）标签，不会因元数据不一致而拒绝续跑。
  - 读模型：调度时间线、VRE 摘要、stress 事件都返回同一时钟；时间戳带 `Z`，闰年跳过 2 月 29 日（原来用 `1 月 1 日 + 期数 × 0.5 h`，闰年 2 月 28 日之后偏一天）。旧账本按 UTC 报告，并给出 `clock_label_corrected: true` 和 `clock_note`。
  - 导出：CSV/JSONL 最后一列 `period_start_utc`；ZIP 的 manifest 有 `model_clock`。
  - 界面：回放窗口行 `(UTC model time)`；stress 事件表和网络可靠性事件表表头 `Start (model date & time, UTC)`；VRE 峰值事件时间后加 `UTC`；前端统一用 `app/features/shared/modelClock.ts`，网络页原来的计算也改成 365 天年。旧账本的 `clock_note` 显示在窗口行下方（F-R43-1，取代 F-P09-3）。
- golden：账本元数据的这两列属于核算区，全部 15 个用例各追加一次修订（correction id `r43.model-clock-utc-label`，finding S-中1）。每个用例只有 `market/metadata.json::semantic_metadata.timezone` 与 `.calendar` 两列核算差异，轨迹区 0 列；其余是身份区（账本哈希、R4-1 之后的模块版本）。C7、C8 的 staged 账本以前没有这两个字段，现在也写入。修订在 scratch 中用 `git archive HEAD` 加本改动的树运行（`--jobs 4`，约 11 分 27 秒）。D5 用 staging 中的 GBP1 public1（manifest `17a68154…0025`）；C9、C10 用 `build_value_uk_pack_revision.py --link hardlink` 重建的 GBP1 public2（`8d73e08c…f86f`）和 R029 public2（`d9876d98…d309`），与钉住值一致。`capture.py validate`、`delta_report.py --check`（未归因 0）通过，`P0_GOLDEN_DELTA.md` 已重新生成。UI 合同夹具用生成器重写。
- 数值没有变化：这是标签修正，不改调度、成本或任何结果数值。

### S-中2 时钟说明

- `series_reader.clock_alignment` 按声明时钟（`declared-v2`）逐步给出计划：逐时值每小时用于两个半小时；17,568 期删去 2 月 29 日（需求另按年电量重新缩放）；超过一年只用前 17,520 期；不足一年从开头重复补齐最后 N 期（写出期数和天数）；严格读取且未声明循环时拒绝。单元测试把计划与 `align_clock` 在 8760、8784、17568、17000、20000 以及声明 30 分钟的 8760 行上逐一对照。
- 数据包校验（`data_pack_validation`）的需求和互联线角色都改用这句说明，并在 `details.clock_alignment` 记录计划。映射审阅使用同一说明，并且校验时用的是提交时会写入的绑定声明（`interval_minutes`、`csv_column` 等），审阅看到的说明与运行时的读法一致。
- 说明写明是 “VALUE corrected methodology” 的读法：用户映射的包只能用修正口径（论文口径只接受钉住的论文时代数据包）。

### S-中3 日期顺序

- 映射编辑器的时间戳框新增 `Date order`：自动 / DD/MM/YYYY / MM/DD/YYYY。自动时，任一行第一个字段大于 12 则按日/月，第二个字段大于 12 则按月/日，都没有时按英国习惯的日/月，并在报告里写明依据（例如 “detected: CSV line 578 has a first field above 12”）。ISO 日期不受影响。
- 声明的顺序与数据矛盾时，不可能的日期逐行报告为 “not a valid date in MM/DD/YYYY order”；缺口多为约一个月时给出提示 “the dates may be in DD/MM/YYYY order”。
- 提交后绑定记录 `timestamp_date_order`，数据包时序层复查时用同一顺序。

### S-低2 与第 7.3 节：覆盖范围和数据年份

- 时间戳报告新增 `coverage`：跨度天数、是否满一年、数据所在年份。
- 序列不满一个模型年（会从开头重复补齐）时，审阅列出 `acknowledgements_required`；界面多一个确认框，后端提交时也要求 `acknowledged`，否则返回 409 `GF_MAPPING_ACKNOWLEDGEMENT`。没有时间戳列时同样适用（按行数判断）。
- 编辑器把基线 Study 的首个模型年传给预览（`model_start_year`）。数据年份不同时给出 `GF_DATA_TIMESTAMP_YEAR`：说明 VALUE 按行序把序列当作模型年读取，每个模型年重复使用，不移动日期、星期或节假日。

### 低等缺陷

- S-低1：表头含分号或制表符而没有逗号时，暂存即拒绝，说明 “This file looks semicolon-separated … Save the file as comma-separated CSV (UTF-8) with decimal points”。没有做自动转换：转换会改变保留的原始文件身份，规格未覆盖。
- S-低3：时间戳问题带 `data_row` 与 `csv_line`（`row` 仍为 CSV 行号，兼容旧读者）；表格拆成 `Data row`、`CSV line` 两列；“重复”写作 `duplicate of data row 3 (CSV line 4)`，与单元格错误 `Row 51 (CSV line 52)` 同一对编号。
- S-低4：有时间戳列时，完整文件校验报告带 `timestamp_check`；时间戳有问题时 `status` 为 `failed` 并列出错误。
- S-低5：角色卡片显示 `原币种 EUR · 汇率 … · 汇率口径 … · 价格年份 …`；时间戳行在有日月顺序时加 `DD/MM/YYYY`。只读时角色下拉框仍可选择，上传和映射仍禁用。
- S-低6：API 只接受 `annual average`、`monthly average`、`fixed rate`（与界面相同）。`price_year` 与模型价格基准 2025（`MODEL_PRICE_BASE_YEAR`，测试核对它等于重启成本表的 `price_base.to_year`）不同时，给出 `GF_MAPPING_PRICE_YEAR`：VALUE 只换算币种，不按年份折算价格。
- S-低7(a)：单维变化的比较说明改为 “The comparison describes the effect of this one change.”，不再提储能成本实验。
- S-低7(b)：比较页三个依赖 VRE 弃电证据的指标缺值时写 `Unavailable`，与 Runs 页一致。
- 顺带：`data_validation_layers` 读互联线价格表头时未关闭文件（ResourceWarning），改用 `with`。

## 3 改动的文件

- 后端：`gridform_core/model_clock.py`（新）、`market_ledger.py`、`market_replay.py`、`replay_export.py`、`builtin/scheme_c_1000twh/scheme_c_native_psm.py`、`perfect_foresight_psm.py`、`series_reader.py`、`data_pack_validation.py`、`data_validation_layers.py`、`results_summary.py`、`backend/data_mapping.py`。
- 前端：`app/features/shared/modelClock.ts`（新）、`page.tsx`、`market/StressEventList.tsx`、`market/marketTypes.ts`、`market/market-replay.css`、`network/reliabilityView.ts`、`network/NetworkRedispatchView.tsx`、`data/CsvMappingEditor.tsx`、`data/csvMappingFx.ts`、`data/csvMappingTypes.ts`、`workspace/JourneyDataEditor.tsx`、`workspace/journey-data-editor.css`、`results/ComparisonWorkspace.tsx`、`results/comparisonReview.ts`。
- golden 与夹具：`tests/golden/{corrected,doctoral}/*.json`（15 个）、`docs/release/P0_GOLDEN_DELTA.md`、`tests/fixtures/ui-contract/*`（15 个，生成器重写）、`tests/ui_contract_fixtures.py`。
- 测试：新增 `tests/test_r4_swap_data_defects.py`（7 类、21 个测试）、`tests/frontend/unit/r4-swap-data-defects.test.mjs`（4 个）；更新 `tests/test_data_mapping.py`（重复行文案、`fx_basis` 改为枚举值）、`tests/test_comparison_identity.py`、`tests/frontend/unit/csv-mapping-fx.test.mjs`、`tests/frontend/render/journey-data-editor.test.mjs`（新增 1 个）、`tests/frontend/csv-mapping-editor.test.mjs`。
- 文档：`P0_FRONTEND_DEVIATIONS.md`（R4-3 一节；F-P09-3 标为已取代）、`CHANGELOG.md`（correction id、golden 摘要、API 合同变化、R4-3 小节）、本报告。

## 4 测试与结果

- 每个提交前：相关后端单元测试（`test_r4_swap_data_defects`、`test_market_replay`、`test_market_ledger`、`test_ui_contract_fixtures`、`test_data_mapping`、`test_data_validation_layers`、`test_series_reader`、`test_data_pack_validation`、`test_comparison_identity`、`test_results_summary`）均 OK；golden 相关 100 个（`test_native_reproduction_golden`、`test_p04_variant_fixtures`、`test_golden_*`）OK；前端 unit/render 测试、浏览器测试 `csv-mapping-editor.test.mjs`（3 个）和 `tsc -p tsconfig.frontend.json` 通过；每个提交用 `refresh_source_release_manifest.py --index` 刷新清单。
- `test_market_ledger_v6`、`test_doctoral_ledgers`、`test_prompt123_bounded_replay_export` 中直接运行时出现的失败均在 M0 基线或依赖 Windows 路径，与本改动无关（见第 6 节门禁结果）。
- scratch 实例（API 18894、UI 18895，`VALUE_DATA_HOME=scratchpad/build/r4ui/r43/data`，vinext 重新构建）：
  - VALUE 101 修正口径两年 Run 通过；API 第 8,720 期返回 `2025-07-01T16:00:00Z`，`timezone UTC`、`calendar fixed_365_day_utc_periods`。
  - Playwright headless（chromium 1243）18 项检查全部 PASS：回放窗口 `(UTC model time)`，页面无 Europe/London；分号文件的说明；日期顺序选项；DD/MM/YYYY 文件 0 个问题且写明依据；覆盖 354.17 天、数据年份 2023；覆盖警告写明最后 520 期（10.8 天）；数据年份与 Study 年份不同的提示；价格年份提示；未勾选覆盖确认时提交按钮禁用、两项都勾选后可用；提交后角色卡片显示汇率与日月顺序；重复时间戳表格为 Data row / CSV line 两列；完整报告为 failed。唯一的控制台记录是分号文件被拒绝时的 400，属预期。截图在 `scratchpad/build/r4ui/r43/shots`。
  - 观察（不属于本轮缺陷）：同一角色提交映射后立刻重新载入页面、切换到另一角色时，映射编辑器偶尔显示 “映射目录与当前目标包版本不一致，请刷新目标包”，稍后重新载入即正常。原因未查明，可能是工作区列表的 manifest 哈希短暂滞后，建议后续核查。
  - 第一次启动 API 时用的是 `python backend/server.py`，Run 在 worker 校验执行环境时失败（`sys.path[0]` 不同，import_paths 不一致）；改用 `python -m backend.server` 后正常。这是启动方式问题，不是本轮改动引起的。
  - 两个服务按记录的 PID 停止（API 948882 与 971702、UI 951719），端口已释放，Run 的 worker 都已退出。

## 5 采用的决定

- A27：中低缺陷全部修复；界面按规格现有约定实现，偏差登记为 F-R43-1…6。
- S-中1 的规则选择“显示 UTC 并明确标注”，与规格 3.1 原文（窗口行写 `(UTC)`）一致，并取代当时的偏差 F-P09-3。
- Q12：账本元数据属于核算区，golden 按修正 id 追加一次修订；论文 golden 的轨迹区没有变化，不需要数值报告。
- Q13：PSM 源码只删了两行标签（代码级改动，模块版本不变），已保存 Study 按代码级自动修订处理。

## 6 偏差

1. **S-中1 的旧账本不改写。** 修复前已完成的 Run 的账本保留 Europe/London 标签（账本元数据不可变）；读取时按 UTC 报告并给出说明。
2. **S-低1 不做自动转换。** 只给出明确说明；自动把分号/小数逗号转成标准 CSV 会改变保留原文件的身份，规格未覆盖。
3. **S-低2 的数据年份提示以 Study 的首个模型年为准。** 映射编辑器只在研究引导中知道基线 Study；直接调用 API 而不传 `model_start_year` 时只报告数据年份，不比较。
4. **S-中2 的说明只描述修正口径的读法。** 用户映射的包不能用于论文口径；论文口径的冻结读法（35aadb3）不在说明中展开。
5. **门禁按代码提交完成后的状态运行一次**（与 R4-2 相同），每个提交前都跑了相关测试、tsc 和清单刷新。

## 7 环境核对

- `scripts/p0_gate.py quick`：
  - 第一次在代码提交完成后运行，`backend_ratchet` 报 2 个新失败：`test_stress_events_query`（期望旧的无 `Z` 时间戳）和 `test_generated_runtime_tables_are_current`（生成表中完全预见 PSM 的源码哈希过期）。两者都是 S-中1 的直接后果，在 `e8ae45d` 中修正；
  - 修正后在文档提交的暂存状态下重跑：status `passed`，16 步全部通过，没有豁免，154 s；`backend_ratchet` 2,646 个 id、失败 147 个全部在基线内，new_failures 0；node 测试 316 个全部通过；typecheck 和 eslint ratchet、network_guard、installed_inventory 通过。
- INSTALLED：
  - `find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（0 字节，属作者实例，测试报告第 8 节已说明）；没有新的 `.pyc`；
  - `diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”。
- 研究包：构建前后两个 staging 来源目录（`gbp1-national`、`r029-public1`）的文件清单（路径、大小、mtime、链接数）哈希相同；硬链接构建的 public2 和 golden 用的树已删除。
- 进程：只按记录的 PID 停止了自己启动的 API 和 UI 网关；没有连接 8766/8800 端口，没有使用按模式匹配的 kill。
- Python 全部经 `vpy` 调用，INTEG 中没有 `__pycache__`；`dist/`（gitignored）已用 vinext 重新构建；没有 push，没有改 remote。
- scratch：`scratchpad/r43`、`build/r4ui/r43`、`build/r43gate` 只剩脚本、日志、门禁报告和截图，合计约 20 MB。
