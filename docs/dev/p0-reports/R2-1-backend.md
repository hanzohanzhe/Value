# R2-1-backend：R1 复测遗留项的后端修理（DECISIONS A23）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `1648a94`。
- 授权：DECISIONS A23（负责人对 R1 复测遗留项的裁决）；A21（low 项改动小时顺带修）。
- 范围：A23 的后端项 R3-N1、AF3-1（按指标门控）、R3-N6 / O-3（Run 记录写入生效的 correction id）、R3-N7（advisory 按资产筛选）、R3-N2（p06 advisory 措辞）、A22a 收尾（取值表公式文字 + 修正族 golden 修订一次）、R-D10（D3/C3 identity 区同步），以及 `docs/handoff/FOUR_ROLE_TEST_REPORT.md` 10.7 节“顺带修”中属于后端的 low 项。界面显示（AF3-1 的逐指标原因、R3-N3、R3-N4、R3M-2/3/4/7、L-4、L-6 等）和开发者文档 R3M-1 属于随后的 R2-2 单元，本单元没有改 `app/`。
- 结论：A23 列给后端的各项全部完成。没有改变任何模型数值：修正族 golden 只有 `restart_table_sha256` 一列变化，论文族只同步了 D3 的 identity 区。

## 1 提交

| 提交 | 内容 |
|---|---|
| `16b9ef2` | fix(compare)：保存时数值按注册表类型规范化，比较时按数值比较（R3-N1） |
| `0d0bc98` | fix(compare)：年度差值按指标门控，每个被扣发的指标带原因（AF3-1） |
| `3609f06` | feat(methodology)：Run 记录列出生效的通用核算修正，含 `fx5.voll-17000`（R3-N6、O-3） |
| `fad02ae` | fix(advisories)：核电、径流水电相关 advisory 只用于冻结机组中有该资产的 Run（R3-N7） |
| `e05bea3` | fix(advisories)：p06 下调 advisory 不再把论文的先弃风顺序称为缺陷（R3-N2） |
| `c2ed529` | fix(compare)：原地改源码的模块按字段点名；去掉双重括号（R3M-6、AF3-2） |
| `d1ad608` | fix(preflight)：已隔离的已改源码模块不再声称“结果会记录新哈希”（R3M-5） |
| `a27e1b6` | fix(data)：坏单元格一次列全（空值、非有限值、负需求）；API 采用编辑器的价格年份范围（L-1、L-2、L-3、L-5） |
| `a89b1f4` | fix(thermal)：取值表公式文字改为 a(H) = c − S(H)/(m·H)；修正族 golden 修订一次；D3 identity 同步（A22a、R-D10、R3-N6） |
| 本报告 | docs(p0) |

## 2 逐项状态

| ID | 严重度 | 状态 | 提交 | 做法 / 证据 |
|---|---|---|---|---|
| R3-N1 | 中（必修） | **已修** | `16b9ef2` | 两层都改。**保存：** `resolve_market_configuration` 把 VoLL 写成 float；`resolve_project_draft` 把注册表中 float 类型参数（parameters / runtime_options 及其别名）的 int 值写成 float（`parameters.normalise_numeric_values`）。原样保存不再产生新修订（`save_project_revision` 在哈希相同时返回原记录）。**比较：** `comparison_identity.comparison_key` 把整数值的 float 当作 int 比较（布尔、小数不变），用于 identity 审查、`_differing_paths` 和 `compare_run_summaries` 的运行字段与模块维度。修订哈希的算法没有改，已保存的修订身份不变。测试 `tests/test_r2_numeric_identity.py`：复现 10.6 节的原始调用（修复前返回 `['market_configuration.voll_gbp_per_mwh']`，现为 `[]`）；identity 审查为 same；真实数值变化仍报告；经本地 API 保存两次（第二次 VoLL 为 int）只有 1 个修订文件 |
| AF3-1 | 低-中 | **已修（后端）** | `0d0bc98` | `metric_delta_gate`：三个弃电指标要求各 Run 有一致且已对账的弃电归因证据；成本指标要求 cost、terminal_policy、currency_base_year 定义一致；碳指标要求 carbon 定义一致；未知指标要求所有定义一致（保守）。新字段 `metric_delta_gates`（每个指标 `allowed`、`reason_code`、`definitions`、`reason`）和 `withheld_metric_deltas`。`metric_deltas_allowed` 含义不变（“所有指标都显示差值”），所以现有界面在 R2-2 改版前仍不显示差值，见第 6 节。教学 Run 和 Q14 扣发的比较照旧没有年度行。测试：原 `test_mismatched_attribution_keeps_values_but_nulls_all_deltas` 按 A23 改为只扣发弃电指标；新增 VALUE 101 无反事实快照用例、定义不一致只扣发成本指标用例 |
| R3-N6 / O-3 | 信息 | **已修** | `3609f06` | `methodology.UNIVERSAL_ACCOUNTING_CORRECTIONS` 列出不在修正目录中的通用核算修正：`fx4.storage-offer-ledger`、`fx5.voll-17000`、`p04.storage-energy-audit`、`p04.surplus-node-boundary`、`p04.surplus-routing`、`p04.validation-gate`、`p04.validation-v2`、`p06.physical-operating-cost`、`p07.cost-ledger-v2`。`ResolvedMethodology.to_dict()`（status.json、resolved-run.json、provenance 共用）新增 `universal_accounting_correction_ids` 和 `correction_ids_in_force`（目录 id 与上述 id 的并集）。方法身份（`applied_corrections_sha256`）不变，已保存的 Study 不会因此要求确认。doctoral Run 的记录现在能看到 `fx5.voll-17000`。测试 `tests/test_r2_methodology_record.py` |
| R3-N7 | 信息 | **已修** | `fad02ae` | 修正目录的 `applies_when` 新增 `assets_any`（展示字段，不进方法身份）。证据是 Run 冻结输入 `input-snapshot/pack` 中 `fleet.generators` 角色的机组（发电机、电池、互联线），按 `market_replay.canonical_technology` 分组，按文件身份缓存；读不到机组时保留 advisory（偏向披露）。已加 `assets_any` 的：`fx8.nuclear-in-service-at-start`、`p05.nuclear-generation-end-month`、`p05.nuclear-stations-public2`（nuclear），`p05.firm-availability`（nuclear、natural_flow_hydro），`p05.hydro-dukes-load-factor`（natural_flow_hydro）。VALUE 101 的 doctoral Run 不再列出核电 advisory，high 由 7 条回到 6 条。GBP1 的 fleet 中有 `Nuclear`、`Hydro_natural_flow`，不受影响（已核对 staging 中的 public1 fleet）。测试 `tests/test_r2_advisory_assets.py` |
| R3-N2 | 低-中 | **已修** | `e05bea3` | `p06.avoided-cost-downward-order` 的 advisory 标题改为 “Down regulation bookkeeping (ramp history, breaks, budgets)”，正文只讲三项记账缺陷（爬坡历史按位置匹配、断开后保留旧要求、下调能量只返还水电预算），并写明先弃风是论文规则、不是缺陷（A19），经济顺序见 `r12.economic-downward-order`。严重度保持 high，见第 5 节偏差 3。重新生成 `docs/generated/METHODOLOGY_PROFILES.md` |
| A22a 收尾 | — | **已修** | `a89b1f4` | `value_thermal_restart_v1.json` 的 `rule.shutdown_segment` 改为 “… S per MW of capacity; at minimum stable generation m, removing 1 MW of output shuts 1/m MW of capacity: net saving per MWh a(H) = c - S(H) / (m H) (DECISIONS A22a)”。取值不变，文件 sha256 `d4a5695a…` → `446b1df5…`。0.4 草稿 `p06_default_psm_clearing.md` 中残留的 `c - S(H)/H` 一并改正；参考统计表 4.8 节第 5 条的“遗留”改为已完成。golden 见第 4 节 |
| R-D10 | 信息 | **已修** | `a89b1f4` | D3 追加 revision 13，只有 identity 区 13 列，trajectory、accounting 为 0 |
| R3-N6（复测原义：C3 identity 落后） | 信息 | **已修** | `a89b1f4` | C3 revision 16 同时同步了 identity 区的 1 列（`runtime_kernel_tree_sha256`） |
| R3M-6 | 低 | **已修（后端）** | `c2ed529` | 模块 id 和版本在各 Run 中相同时，变化路径给到字段（`modules.storage_cost.source_sha256`）。storage-cost 模块身份变化（换模块或原地改源码）都算同一种受控的储能成本变化：教学范围写 “controlled teaching diagnostic”，年度范围为 `controlled_storage_cost_module_change`，不再出现两种相反结论 |
| AF3-2 | 低 | **部分修（后端文字）** | `c2ed529` | 句子改用短名：“Only one recorded dimension differs - model method: extensions.”，不再有 “…methodology) (extensions)” 的双重括号；`changed_dimension_details` 每行加 `name`。扩展的选择属于方法维度、扩展参数属于配置维度是原设计，没有改。中英混排属于界面，归 R2-2 |
| R3M-5 | 低 | **部分修（后端文字）** | `d1ad608` | 模块已隔离时，源码变更警告改为 “It is quarantined, so no Run can start; once it is repaired, results record the new source hash.” 同一警告在 readiness 分组中重复计数，属于 `readinessGroups.ts`，归 R2-2 |
| L-1 | 低 | **已修** | `a27e1b6` | 换算列中的空单元格在文件因其他坏单元格被拒绝时一并列出（“'' is missing”），按行排序；只有空单元格时仍交给整文件校验（原行为） |
| L-2 | 低 | **已修** | `a27e1b6` | 整文件校验把 NaN、inf 计入坏单元格（声明列与旧读法两条路径；已核对仓库数据包和 staging 中的 GBP1、R029 都没有这类单元格），计数与逐行清单一致；文字改为 “non-numeric, non-finite or missing”；有坏单元格时不再给 “repeats it cyclically” 的误导性 warning |
| L-3 | 低 | **已修** | `a27e1b6` | 校验写 “demand contains N negative value(s)”；映射编辑器对需求角色逐行列出负值（“Row 5 (CSV line 6), column load: '-1' is negative”） |
| L-5 | 低 | **已修（部分）** | `a27e1b6` | API 的 `price_year` 若给出须在 1990–2100（与编辑器相同），否则 400 `GF_MAPPING_FX`。`price_year` 仍可省略，`fx_basis` 仍为非空自由文本，见第 5 节偏差 4 |
| R3M-3、R3M-4 | 低 | 归 R2-2 | — | 文字都在前端（`DisabledEntriesPanel.tsx:36`、`page.tsx:1593`），后端无对应 |
| R3-N3、R3-N4、R3M-2、R3M-7、L-4、L-6 | 低 | 归 R2-2 | — | 纯界面 |
| R3M-1 | 低-中 | 归 R2-2 | — | 开发者文档，R2-2 的任务明确包含 |

## 3 测试

- 新增测试文件：`tests/test_r2_numeric_identity.py`（7）、`tests/test_r2_methodology_record.py`（3）、`tests/test_r2_advisory_assets.py`（3）。
- 修改或新增的测试：`tests/test_results_summary.py`（1 改 + 2 新）、`tests/test_comparison_identity.py`（措辞期望 + 1 新）、`tests/test_module_source_changed.py`（+1）、`tests/test_executable_data_adapters.py`（+1）、`tests/test_data_mapping.py`（S-D7 期望加入空单元格 + 3 新）。
- 每个提交前用 `scripts/run_backend_tests.py --modules …` 跑相关模块（比较 / 修订 / 方法学 / advisory / 数据映射 / preflight，单次 20–43 个模块、最多 451 个测试 id），全部 `passed: true`、`new_failures: []`、`fixed_but_listed: []`；失败数都在基线内。
- `tests/ui_contract_fixtures.py --check`：没有差异。
- `scripts/p0_gate.py quick`：每个功能提交前一次（`c2ed529`、`d1ad608`、`a27e1b6` 三个提交共用一次门禁，见偏差 5），A22a 提交前一次，均为 `status: passed`、无豁免。第一次给三个小提交跑门禁时 `release_manifest` 失败，原因是先刷新了发布清单才暂存文件；按“先暂存、再 `--index` 刷新”重跑后通过。
- `a89b1f4` 之后 `capture.py check --tier fast`：passed，C1–C4、C7、C8、D1–D3 gated 差异全部为 0；identity 区 C3、D3 为 0（已同步），C8 47 列、D1/D2 各 16 列（A23 只要求 D3/C3，未动）。
- `check_methodology_catalog.py`、`generate_reference_tables.py`、`capture.py validate`、`delta_report.py --check`（0 条无法归因）、`refresh_source_release_manifest.py --index --check`：均通过。

## 4 golden

- 修订前 `capture.py check --tier fast`：C1–C4 各 1 列 trajectory 差异（`restart_table_sha256`），C7 0、C8 只有 identity，D1–D3 gated 0（D1/D2 identity 16 列、D3 13 列）。
- `capture.py revise --cases C1 C2 C3 C4 C5 C6 C9 --correction-id r12.economic-downward-order --finding A22a --finding A23`：

  | case | 新修订 | 变化 |
  |---|---|---|
  | C1 / C2 / C4 | r15 | trajectory 1 列（`year-results-v2.json::market.extensions.downward_restart_economics.restart_table_sha256`） |
  | C3 | r16 | trajectory 1 列（`teaching/one-day-market-result.json::…restart_table_sha256`），identity 1 列 |
  | C5 | r14 | trajectory 1 列 |
  | C6 | r12 | trajectory 1 列 |
  | C9 | r4 | trajectory 1 列（GBP1 public2 2025，本地重建） |

  数值列全部不变，所以没有单独的数值报告（与 R1-2 不同，没有数值差异可报告）。
- C9 的 public2 按 FX7 的方法用 `build_value_uk_pack_revision.py --link hardlink` 在 scratch 重建，manifest sha `f43e0e46…1439` 与钉住值一致；用后已删除。构建前后两个 staging 目录（`gbp1-national`、`r029-public1`）的文件清单（路径、大小、mtime）哈希相同（`dc85a5f8…`）。
- `capture.py revise --cases D3 --finding R-D10 --finding A23`：D3 r13，只有 identity 13 列（R-D10）。
- `docs/release/P0_GOLDEN_DELTA.md` 已重新生成；CHANGELOG 的 golden 摘要加了一段。

## 5 采用的决策与偏差

采用：A23（各项）、A19/A22/A22a（p06 措辞与取值表文字）、Q12（只动核算与展示，不改调度）、Q13（没有方法身份变化，不需要确认）、Q1（论文口径 trajectory 不变）。

偏差：

1. **R3-N6 的实现方式。** A23 写“Run 记录写入实际生效的 correction id（含 `fx5.voll-17000`）”。把这些 id 加进修正目录会改变两个口径的 `applied_corrections_sha256`，所有已保存的 Study 都会被判为方法变化并要求确认（Q13），这与 FX5 报告偏差 5 的约定相反。所以放在 Run 记录的两个新字段中，不进方法身份。`p08.*` 网络修正没有列入：它们随网络模块版本记录，只在网络模块运行时生效。
2. **AF3-1 中 `metric_deltas_allowed` 的含义保持不变**（全部指标都可显示差值时才为真），新增逐指标字段。这样旧界面不会把被扣发的弃电指标误显示为可比；代价是在 R2-2 改界面之前，比较页仍不显示任何差值。成本指标依赖的定义取 cost、terminal_policy、currency_base_year 三项（保守）。
3. **R3-N2 只改措辞，严重度保持 high。** 剩下的三项记账缺陷会影响论文口径的调度，是否降为 medium 属于判断，A23 只要求改措辞，留给负责人决定。
4. **L-5 只对齐年份范围。** API 的 `price_year` 仍可省略，`fx_basis` 仍为非空自由文本：脚本化的调用方（包括现有测试和数据包构建）记录自己的汇率口径，强制三选一会改变 API 合同。界面仍按三选一和必填年份校验。
5. **三个 low 提交共用一次门禁。** `c2ed529`、`d1ad608`、`a27e1b6` 在同一个工作树上跑了门禁（passed），然后按文件拆成三个提交，每个提交前单独刷新发布清单；第三个提交的树就是门禁通过的树，前两个中间提交没有单独跑门禁。
6. **L-2 改了旧读法 `_first_numeric_column`。** 这是数据包校验，不是调度；仓库和 staging 中的数据包都没有 NaN/inf，所以对现有包的校验结果不变。

## 6 交接提示

- **R2-2（界面）：** 比较页的年度差值请改用 `metric_delta_gates[metric].allowed` 判断是否显示 `delta_from_base`，被扣发的指标显示 `reason`（或按 `reason_code` 翻译）；`withheld_metric_deltas` 可用于一句总括。`ComparisonWorkspace.tsx:110` 的中文通用文案可以换成按指标的原因。`changed_dimension_details` 每行多了短名 `name`。方法记录中的 `correction_ids_in_force` 可以在 Run 上下文中显示。
- **methodology 编辑员：** (1) p06 advisory 新措辞（R3-N2）见 `gridform_core/data/methodology/corrections/p06.json` 或 `docs/generated/METHODOLOGY_PROFILES.md`，方法学正文若列论文复现口径的已知问题，应与之一致：先弃风不是缺陷；(2) 取值表与 0.4 草稿 `p06_default_psm_clearing.md` 的停机段公式现为 a(H) = c − S(H)/(m·H)；(3) Run 记录新增 `universal_accounting_correction_ids`，VoLL 修正 `fx5.voll-17000` 在两个口径的 Run 上都能看到。
- **网页上传员：** advisory 标题 “Down regulation in curtail-cost order” 已不存在，改为 “Down regulation bookkeeping (ramp history, breaks, budgets)”；没有核电的 Run 不再显示核电 advisory。
- 交接文档（`docs/handoff/`）本单元没有改，由 R2 收尾单元统一更新。

## 7 安全核对

- INSTALLED：`find <INSTALLED> -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（0 字节，mtime 2026-10-03 05:41:26，安装后首次启动时生成的现网文件，以往报告都有同样记录）；`diagnose-value --prefix <INSTALLED>` 退出码 0，输出 “Installation integrity and runtime checks passed.”（中间那行 vinext “Static file stream error … Premature close” 来自它自己的探测请求，与以往相同）。门禁的 `installed_inventory` 步骤每次都通过。
- 没有启动任何 HTTP 服务；测试中的本地 API 由测试夹具在随机端口起停。没有连接 8766/8800，没有向任何进程发信号，没有使用 pkill 等按模式的 kill。
- Python 全部经 `vpy` 调用；INTEG 中没有 `__pycache__`。scratch 用量：本单元目录 `scratchpad/r21/` 约 140 KB（public2 重建目录已删除）。
- 没有 push，没有改 remote。
