# R5-1 工作报告：换数据角色最终验收的缺陷（DECISIONS A28）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `5b483a2`。
- 依据：R4 最终四角色验收的换数据报告（构建 `c204aac`，`scratchpad/build/r5/swap-data.md`）；A28 通过规则：高、中缺陷和任何影响运行结果的问题必须修并带测试；纯显示的低缺陷顺手能修就修，否则进待办。
- 提交：
  - `9f06f3d` fix(data,accounting): swap-data defects - demand unit relabel, energy served, hourly demand (A28)
  - `68de989` fix(ui): swap-data defects - unit note, editor survives Run polls, served/unserved on Runs and Compare (A28)
  - `2846052` fix(application): cost history reads demand and served energy defensively (R5-1 follow-up)
  - 本报告与文档（CHANGELOG、方法学草稿）单独提交（docs(p0)）

## 1 缺陷处理表

| 缺陷 | 结论 | 提交 | 说明 |
|---|---|---|---|
| S-F-高1 需求标签 MWh/period、实际按 MW 读 | 已修 | `9f06f3d`、`68de989` | 采用**登记表重标**（不是新包修订）：VALUE 101 两份需求文件的字节、manifest、两个口径的读法都不变（论文口径读法逐位相同）。`legacy_demand_unit()` 按内容（`LEGACY_DEMAND_MW_SHA256`）识别；工作区数据包的绑定带 `runtime_unit_interpretation`；角色卡（原文件、目标文件）和映射编辑器写明“按 MW 读取，表头 mwh、标签 MWh/period 是已知误标，改写时请选 MW”。映射编辑器的默认源单位本来就是 MW（`source_unit = target_unit`），未改。模型侧检查：映射审阅中新需求序列的年电量（平均 MW × 8,760 h）与被替换文件之比 > 1.5 或 < 0.67 时给出 `GF_DATA_DEMAND_SCALE`，写出两个年电量和倍数；复制包的数据包校验对每个改动过的需求文件与来源包比较，同样告警。比较页新增 `Annual demand (MWh)`、`Demand served (MWh)` |
| S-F-中1 Run 运行时映射编辑器被清空 | 已修 | `68de989` | Data 页按 Study 内容（去掉 `linked_run_count`、`warnings`）作解析键，不再按对象身份；轮询得到同内容的新对象时不重发 `resolve-draft`，`readOnlyReason` 不闪变，编辑器不重挂载 |
| S-F-中2 单位成本把 stress 缺口算作已供电 | 已修 | `9f06f3d`、`68de989` | 通用核算修正 `r5.served-energy-net-of-stress-shortfall`（两个口径；只改账，不改调度）：已供电量 = 需求 − PSM 记录的缺电 − A2 账在其外记入的隐藏未供电量（`hidden_unserved_mwh`，仅在该年有 stress 时段时计入；无 stress 的年份那部分是 1e-8 MWh 量级的数值噪声）。用于每 MWh 供电成本和每 MWh 交付电量的碳强度。与 `fx5.voll-17000` 一样列在 `UNIVERSAL_ACCOUNTING_CORRECTIONS`，不进方法身份，已保存 Study 不需要确认。Run 状态新增 `demand_mwh`、`unserved_energy_a2_mwh`；年度卡片 `Unserved demand` 显示 A2 总量并写出 PSM 记录部分；比较页 `Unserved energy incl. stress shortfall (MWh)`（定义 `value.adequacy-unserved-energy/v2`）与 `Unserved energy recorded by the PSM (MWh)` 分列 |
| S-F-中3 逐时需求无法导入、说明矛盾 | 已修 | `9f06f3d`、`68de989` | 需求的逐时数据（8,760/8,784 行，或时间戳步长 60 分钟）在映射时展开：每小时的 MW 用于该小时的两个半小时（`AdapterSpec.repeat_rows=2`，为 1 时不进规格哈希，原有映射 SHA 不变）；MWh/period 按 60 分钟换算；规范文件仍是半小时、`interval_minutes` 30；保留的逐时原文件由时间轴层按 60 分钟重查（`timestamp_check.interval_minutes`）。审阅报告给出 `GF_MAPPING_HOURLY_DEMAND` 一条说明，不再同时出现“至少 17520 期”“60 分钟缺口”“重复补齐/请确认” |
| S-F-低1 映射 SHA 不含时间戳声明 | 已修（措辞） | `68de989` | 标签改为“列与单位映射 SHA”，并注明时间戳列、时区、日期顺序记录在时间戳报告和绑定中。未改哈希定义（改定义会让已提交映射的规格哈希失配） |
| S-F-低2 `clock_adapter` 与实际读法不一致 | 已修 | `9f06f3d` | 由同一计划生成：`as_is`、`hourly_to_half_hour`、`leap_day_removed`、`first_periods_used`、`repeated_from_start`（可用 `+` 组合） |
| S-F-低3 只读时显示“正在核对…” | 已修 | `68de989` | 改为“当前不能映射 CSV，原因见下方。” |
| S-F-低4 “1 periods (0.0 days)” | 已修 | `9f06f3d` | `period_span_text`：`1 period (30 minutes)`、`3 periods (1.5 hours)`、`520 periods (10.8 days)`；单数用 is |
| S-F-低5 比较参照不明确 | 已修（说明） | `68de989` | 年度表上方写明增量相对第一个勾选的 Run（Study 名和 run id）及如何换参照；未加参照选择控件（规格未覆盖，见 F-R51-3） |
| S-F-低6 审阅有效期原始 ISO 串 | 已修 | `68de989` | 本地时间到分钟，`… local time` |
| 观察 3 条（提交后无“已提交”、Check for 默认值、Belgium 容量为 0） | 不计缺陷 | — | 第一条 R1-5 已有 `mappedConfirmationText`（本次验证中提交后显示“已提交 demand.real 的映射…”）；后两条测试报告已注明不是缺陷 |

## 2 改动的文件

- 后端：`gridform_core/cost_ledger.py`（`a2_hidden_unserved_mwh`、served）、`gridform_core/application.py`（碳账分母、成本历史的需求与已供电量）、`gridform_core/methodology.py`（通用核算修正登记）、`backend/model_runner.py`（状态指标）、`gridform_core/results_summary.py`（年度指标、`_a2_balance_by_year`）、`gridform_core/data_pack_validation.py`（重标、年电量检查、`clock_adapter`）、`backend/server.py`（绑定标注）、`backend/data_mapping.py`（逐时需求、年电量检查、措辞）、`gridform_core/data_adapters.py`（`repeat_rows`）、`gridform_core/data_validation_layers.py`（保留原文件按自身步长重查）、`gridform_core/series_reader.py`（`period_span_text`）。
- 前端：`app/page.tsx`、`app/features/studies/studyResolutionKey.ts`（新）、`app/features/workspace/demandUnit.ts`（新）、`JourneyDataEditor.tsx`、`journey-data-editor.css`、`CsvMappingEditor.tsx`、`csvMappingFx.ts`、`RunResults.tsx`、`resultMetrics.ts`、`labels.ts`、`ComparisonWorkspace.tsx`、`comparisonReview.ts`。
- golden：`tests/golden/doctoral/D5.json` r5；`docs/release/P0_GOLDEN_DELTA.md` 重新生成。
- 文档：`docs/dev/P0_FRONTEND_DEVIATIONS.md`（R5-1 一节，F-R51-1…5）、`CHANGELOG.md`（correction id 表一行、R5-1 小节）、`docs/methodology/drafts/0.4/r5_served_energy_demand_units.md`（新）。

## 3 golden 与数值

- 所有 15 个 golden（研究包由本地 hardlink 构建的 GBP1 public2、R029 public2 与 staging 中的 GBP1 public1 提供，manifest sha 与钉值一致）跑 `capture.py check`：只有 D5、C9、C10 有差异，全部在核算区。C9、C10 的差异是无 stress 年份 1e-8 MWh 的 A2 噪声造成的末位浮点变化；随后规定无 stress 时段的年份不扣这部分噪声，C9、C10 复查后与原修订一致，不需修订。
- D5（GBP1 public1 2025，论文复现口径）追加 r5，只有核算区 2 列：已供电量 232,910,596.5 → 232,831,786.3 MWh（扣除 78,810.2 MWh stress 缺口，487 个 stress 时段），每 MWh 供电成本 116.789242 → 116.828773 GBP/MWh（+0.034%）。轨迹区不变，按规则不需要数值报告。复查 D5、C9、C10、D3、C5：全部通过。
- VALUE 101 各案例（D1–D4、C1–C8）无变化：无 stress 时段，或噪声低于年需求的一个 ulp。

## 4 测试与结果

- 新增 `tests/test_r5_swap_data_defects.py`（16 个，OK）：手算的已供电量与单位成本（需求 1,000、记录缺电 10、隐藏 90 → 900、111.11 GBP/MWh）；无 A2 账与无 stress 年份保持旧分母；修正 id 是通用核算修正且不在目录中；VALUE 101 重标（字节哈希不变）与非旧字节不重标；年电量告警（2.31 倍、0.50 倍、1.15 倍不告警）；以 VALUE 101 复制包的映射：测试人员的单位误差路径给出 2.30 倍告警、按 MW 正确读法不告警；复制包的数据包校验与来源包比较；逐时需求（无时间戳、MWh/period 按小时换算、2024 闰年带时间戳 0 个问题且时间轴层通过、半小时不变、价格不在映射中展开）；`period_span_text`；`clock_adapter`。
- 新增 `tests/frontend/unit/r5-swap-data-defects.test.mjs`（6 个，通过）。
- 相关已有测试：`test_data_mapping`、`test_r4_swap_data_defects`、`test_demand_unit_contract`、`test_executable_data_adapters`、`test_p07_cost_ledger_v2`、`test_release_upgrade_ledgers`、`test_r2_methodology_record`、`test_results_summary`、`test_comparison_identity`、`test_methodology_identity`、`test_p04_validation_presentation` 共 115 个 OK；前端 unit 197、render 71、source-contracts 66 全部通过；`tsc -p tsconfig.frontend.json` 通过。
- `capture.py validate`、`delta_report.py --check` 通过。
- `scripts/p0_gate.py quick`：第一次（两个代码提交后）`backend_ratchet` 报 1 个真实新失败 `test_application_service…test_native_payload_exposes_compact_causally_inherited_solver_status`（替身对象没有 `total_demand_mwh`），由 `2846052` 修正；另一个是暂存了 CHANGELOG 而未刷新清单造成的 `release_manifest` 过期。最终结果见第 7 节。
- scratch 实例（API 18896、UI 18897，`VALUE_DATA_HOME=scratchpad/build/r5ui/data`，vinext 重新构建），Playwright headless（chromium 1243）全部 PASS：
  - 角色卡原文件、目标文件和映射编辑器都显示“按 MW 读取…”；需求说明含逐时一句；
  - 基线两年 Run 排队/运行期间，20 秒内工作区轮询 10 次，`resolve-draft` 与映射目录请求 0 次，暂存文件和列选择一直保留（S-F-中1）；
  - 基线 ×1.15 按 MWh/period 上传：审阅给出 `GF_DATA_DEMAND_SCALE … 537,902 MWh per model year … 2.30 times … (about 233,870 MWh per year)`；“列与单位映射 SHA”说明、本地时间有效期；提交成功；
  - 2024 逐时（8,784 行、ISO、UTC）需求带时间戳列：完整校验通过，`GF_MAPPING_HOURLY_DEMAND … 17,568 half-hour periods`，没有矛盾说明；
  - 派生 Study（需求 2.3 倍）两年 Run passed；年度卡片 `Unserved demand 19,651.03 MWh · incl. stress shortfall · 19,651.03 MWh recorded by the PSM`（该 Run 的缺口全部由 PSM 记录，隐藏部分为 0）；比较页先勾基线：参照句写出基线，年度表出现 Annual demand（233,870.27 对 537,901.63 MWh，+130%）、Demand served（233,870.27 对 510,152.74 MWh）、Unserved incl. stress（0 对 27,748.89 MWh，百分比 n/a）、PSM 记录部分。截图在 `scratchpad/build/r5ui/shots`（已随清理删除，见第 7 节）。

## 5 采用的决定

- A28：高、中缺陷和影响运行结果的问题全部修复并带测试；低缺陷均为小改动，一并修复，没有待办。
- S-F-高1 选登记表重标：不改字节与 manifest，因此 VALUE 101 包、`methodology/profiles.json` 的 manifest 钉值、已有 Study 和 Run 的输入哈希都不变，已安装实例（包括 INSTALLED 和作者的实例）升级代码后即可得到说明，无需重装包。
- S-F-中2 按任务要求作为两个口径的核算修正，配 correction id，golden 只在核算区修订；按 Q12 与 `fx5.voll-17000` 的先例，不进方法身份。
- 决策 2（P3-01 不改调度）保持：只改分母。

## 6 偏差

1. **成本账的 `definition_id` 未升级。** `value.cem-system-resource-cost/v1` 不变，否则所有 golden 的核算区都会变化；分母规则的变化由 Run 记录中的通用核算修正 id 标明。修复前的 Run 与修复后的 Run 比较每 MWh 成本时，比较页不会因定义不同而扣留增量；只有有 stress 时段的 Run 受影响。
2. **无 stress 时段的年份不扣 A2 剩余量。** 该部分只是 1e-8 MWh 量级的数值噪声（GBP1 修正口径 C9、C10），按 A2 的 stress 标志只把有 stress 的年份计入；这样 C9、C10、VALUE 101 的 golden 不因噪声变化。
3. **逐时需求在映射时展开，而不是让读取器读 60 分钟需求。** 需求的输入单位契约要求 30 分钟，论文口径的读法也只认半小时；在映射层展开不触碰任何口径的读取代码。逐时原文件随映射保留。
4. **年电量检查只是告警。** 阈值 1.5 / 0.67 取自任务说明；不阻止提交，因为大幅改变需求可能是有意的情景。
5. **映射 SHA（S-F-低1）只改措辞**，理由见第 1 节。
6. **S-F-中1 仍可能在 Study 内容真的变化时（例如 Run 启动后 `linked_run_count` 以外的字段变化）重新解析一次**；这是正确行为。

## 7 环境核对与收尾

- `scripts/p0_gate.py quick`（`VALUE_GATE_VENV=scratchpad/build/gate-venv`，在本报告提交的暂存状态下）：status `passed`，16 步全部通过，没有豁免，156 s；`backend_ratchet` 2,688 个 id、失败 147 个全部在基线内，new_failures 0；node 测试、typecheck、eslint ratchet、network_guard、installed_inventory 通过。
- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（作者实例的 0 字节锁文件，以往报告已说明），没有 `.pyc`；`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”（过程中有一行 vinext 静态文件流 “Premature close” 日志，以往报告已说明，不影响结果）。
- 进程：只按记录的 PID 停止了自己启动的 API（1939346，重启后 1989669）和 UI 网关（1939531）；端口 18896/18897 已释放，两个 Run 的 worker 已退出；没有连接 8766/8800，没有按模式 kill。
- 研究包：GBP1 public2、R029 public2 在 scratch 中用 hardlink 构建（manifest sha 与钉值一致），用后已删除；staging 来源目录中没有链接数大于 1 或比构建更新的文件。scratch 中的运行输出、数据目录、浏览器配置和截图已删除（`r5ui` 余 0.5 MB，`r51` 余 2.2 MB）。
- Python 全部经 `vpy` 调用，INTEG 中没有 `__pycache__`；`dist/`（gitignored）已用 vinext 重新构建；没有 push，没有改 remote。
