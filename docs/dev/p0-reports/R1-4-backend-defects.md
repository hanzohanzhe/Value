# R1-4-backend-defects：四角色测试剩余缺陷（后端、数据、模块）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `f8ea4c5`。
- 授权：DECISIONS A21（四类用户测试中仍未解决的问题全部修理；medium 及以上必修，low 在改动小的情况下顺带修）。
- 范围：`docs/handoff/FOUR_ROLE_TEST_REPORT.md` 第 3–9 节中仍未修复的后端、数据、模块缺陷。纯前端缺陷属于并行的前端单元，本报告只在表中标明归属，不改 `app/`。
- 结论：复测之后已没有 medium 及以上的后端缺陷未修（N-1、N-2、N-3、F2-N1、M-D1 界面已由 FX9 修复）。本单元修了 13 项 low、low-medium 和观察级问题，共 8 个代码或文档提交。没有改变任何模型数值，没有 golden 修订。

## 1 提交

| 提交 | 内容 |
|---|---|
| `a44831d` | fix(data)：映射编辑器换算值取 15 位有效数字，去掉二进制尾差（S-D6）；坏单元格按行、列列出（S-D7） |
| `f596f3d` | fix(compare)：比较页的说明文字点名变化的维度和路径，不再固定写 storage-policy（S-D9、F-D5），新增 `changed_dimension_details` |
| `2d46eab` | fix(preflight)：停用模块有专门错误码（M2-N2）；readiness 检查内核封印（M-D6）；运行时间估算改为实测量级（F2-N2） |
| `389df35` | fix(modules)：Rescan 重新导入已安装代码（M-D5） |
| `001b14f` | fix(study)：派生的 VALUE 101 Study 记录自己的父 Study 和改动维度（M-D8） |
| `8673fcf` | fix(value101)：缺包提示写出源码检出的安装命令（M-D9 后端部分） |
| `c3ac395` | fix(carbon)：年度碳账 `components_tco2e` 的键顺序固定（F2-N4） |
| `2fe077a` | docs(modules)：模块指南等文档改用代码实际使用的名称；新增“修改内置 module（方法升级）”一节；示例模块不再依赖 compat（M-D7、M-D6、M-D5 文档部分） |
| 本报告 | docs(p0) |

## 2 缺陷逐条状态

“前端单元”指并行的前端修理单元。本单元不改 `app/`，这些条目的后端数据已经齐备，或者问题只在界面。

| ID | 严重度 | 状态 | 提交 | 测试 / 说明 |
|---|---|---|---|---|
| S-D6 | 低 | **已修** | `a44831d` | 映射编辑器（预览和提交时的重建）把换算结果取 15 位有效数字：103.5 EUR ÷ 1.15 写成 `90.0`，不再是 `90.00000000000001`；1001 kW 写成 `1.001` MW。绑定的 `mapping_provenance` 记录 `converted_value_significant_digits: 15`。Run 快照不会重新换算映射文件；快照时换算的 adapter 绑定也不取整，所以已有数据包的字节不变。测试：`test_data_mapping.test_fx_and_unit_conversions_write_no_binary_noise`、`test_executable_data_adapters.AdapterCellProblemTests` |
| S-D7 | 低 | **已修** | `a44831d` | 换算失败的单元格先扫完整个文件，再一并报告：`Row 6 (CSV line 7), column load: 'n/a' is not a number`，最多列 20 条，超出部分给总数。不换算、直接复制的单值序列，在整文件校验给出的计数后面，也按同样格式列出空值和非数值行。规格级错误（未知单位换算、缺汇率）仍然立即报错。有坏单元格时不写输出文件。测试：`test_bad_cells_are_listed_by_row_and_column` 及 adapter 测试 |
| S-D9 | 低 | **部分修**（后端） | `f596f3d` | 说明文字改为点名维度和路径，例如 “Only the data inputs (pack.roles.demand) differ …”，不再提 storage-policy。新增 `changed_dimension_details`：每个变化维度给出标签、最多 12 条路径和剩余条数，前端可以用它代替原始 JSON。原始 JSON 的显示属于前端单元。转换过的角色仍是 `transformation_id: identity/v1`，**保留**：这个字段描述的是“数据包文件 → 冻结文件”这一步，映射时的单位和汇率换算记录在绑定的 `mapping_provenance` 中；改动它会牵动 `frozen_input_integrity` 的冻结身份校验 |
| F-D5 | 低 | **已修**（后端文字） | `f596f3d` | 同上。错误分类的根因（记录了扩展却没有执行）已由 FX2 的预检挡住。变化详情的界面显示属于前端单元 |
| R-D7 | 低 | 后端数据已备 | `f596f3d` | 口径变化 FX 已点名；`changed_dimension_details` 已提供。按维度渲染属于前端单元 |
| M2-N2 | 低 | **已修** | `2d46eab` | 新增 `GF_PREFLIGHT_MODULE_DISABLED`（error，排在通用的 “not registered” 之前），写出模块 ID 和版本，修复指引为 “Open Modules > Disabled and quarantined and Enable it”。新函数 `module_installation.disabled_selections` 只读安装记录，不导入代码。测试：`test_preflight.R14PreflightTests.test_selected_disabled_module_is_named_with_its_own_code` |
| M-D6 | 低 | **已修** | `2d46eab`、`2fe077a` | preflight 调用与 Run 入口相同的 `inspect_runtime_overlay()`（不走进程缓存，约 6 ms）。内核没有封印时报 `GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED`（error），不用再等快照做完才报 `GF_COMPATIBILITY_001`。指南新增“修改内置 module（方法升级）”一节（EN 12.1，ZH 第 12 节）。测试：`test_unsealed_runtime_kernel_blocks_readiness` |
| F2-N2 | 低 | **已修** | `2d46eab` | 默认值从 0.35 s/期改为 0.03 s/期。实测 VALUE 101 两年约 0.005 s/期，GBP1 一年约 0.02 s/期（F3 报告 351 s），0.03 仍偏保守。两年 Run 的估算从 3.4 h 降到约 0.3 h。没有同模式记录时，一年及以上的范围采用任意模式中至少 17,520 期的已完成 Run（短 Run 的启动开销会让每期时间失真，不采用）。测试：`test_runtime_estimate_uses_a_realistic_default_and_annual_runs` |
| M-D5 | 低-中 | **已修** | `389df35` | `POST /api/modules/rescan` 先用 `runtime_paths.purge_installed_sources` 清掉所有安装源码根的已加载模块，再重建目录，因此已加载但源码已改坏的模块会立即隔离。已安装包的导入副作用在每次显式 Rescan 时会再执行一次；生命周期变化后的自动刷新不受影响。响应新增 `reloaded_modules`。测试：`test_module_quarantine_api.test_rescan_reimports_a_loaded_module_whose_source_broke`，测试先复现了“刷新后仍显示 ok”的问题 |
| M-D8 | 低 | **已修** | `001b14f` | 派生 Study 的 `extensions.value_101` 保留课程字段和 variant kind（课程行为不变），`parent_project_id` 改为来源 Study。`changed_dimensions` 按派生方式填写：复现为 `[]`，换数据为 `["data_pack_id"]`，改模块为 `["modules.<slot>"]`。另加 `derivation_intent`。origin 不在 revision payload 中，所以复现得到的 revision 哈希与来源相同（测试断言）。测试：`test_study_derivation` 三处期望更新 |
| M-D9 | 低 | **后端部分已修** | `8673fcf` | 缺包提示补了源码检出时的命令：`python scripts/install_synthetic_pack.py --value-101-only`（在仓库根目录运行，并设好 VALUE_DATA_HOME）。文件框残留和 404 属于前端单元。测试：`test_prompt87_tutorial_runtime.test_read_only_api_descriptor_reports_pack_availability` |
| F2-N4 | 观察 | **已修** | `c3ac395` | `components_tco2e` 原来遍历集合，键顺序随哈希种子变化，现改为排序。数值不变。`capture.py check --tier fast`：C1–C4、C7、C8、D1–D3 的 gated 差异为 0。测试：`test_carbon_ledger` |
| M-D7 | 低 | **已修** | `2fe077a` | 模块指南（EN、ZH）、BUILD_YOUR_OWN_MODEL_101（EN、ZH）、USER_GUIDE（EN、ZH）、INSTALLATION、BRAND_AND_VARIANTS 中的名称已改为代码实际使用的：`value-module.json`、`value.module/v2`、`value.module-bundle/v1`、`VALUE_DATA_HOME`、`%LOCALAPPDATA%\VALUE`。代码只读 `VALUE_DATA_HOME`，不读 `FORCE_DATA_HOME`；BRAND 文档原写“保留 FORCE_DATA_HOME”，与代码不符，已更正。描述文件名 `force-bundle.json` 是代码常量（`module_bundle.BUNDLE_DESCRIPTOR`），**保留**，文档中加了说明。示例模块改用自己的 `AnnualStorageObservation`（字段相同），不再 import `…compat.storage_cost` |
| M2-N5 | 观察 | 保留 | — | FX9 已在报价表下加说明（储能接受量按毛值记）；加列属于界面设计 |
| M-D10 | 观察 | 保留 | — | 内置模块的 `source_sha256` 是转发文件的哈希。要改，就得改每个内置模块的身份，所有已保存的 Study 都会触发迁移分类。Run 级执行身份和 runtime_compat 封印可以兜底；本单元又加了 preflight 封印检查（M-D6） |
| M-D2（小问题） | 低 | 归前端单元 | — | Modules 卡片仍显示安装时的哈希。后端已在 preflight 的 `checks.module_source_changes` 中给出新旧哈希；卡片的显示属于规格 11.7 的界面部分 |
| R-D9 | 信息 | 保留 | — | `market_ledger.uri` 是绝对路径，`psm_input_sha256` 中含 run_id。两者都写在所有 PSM 的结果载荷中，属于 golden 的 identity 或 accounting 区；改动的波及面大于信息级问题的价值。market.sqlite 字节可以重复 |
| R-D10、O-3 | 信息 | 负责人决定 | — | A16-8：D3 的 identity 区何时同步、VoLL 修正 id 是否写进 Run 的来源记录，由负责人决定 |
| S-D10、N-4、O-1、R-D2（后端部分）、R-D4 | 低-中 | 保留，转 P1 | — | 启动 Run 的整个过程（包括执行归档，首次约 3 分钟）都在 `STUDY_LIFECYCLE_LOCK` 内同步完成，所以 POST 和同时发起的 clone 都要等。缩短持锁时间，或改为异步冻结，属于施工计划 P1-11 的 F5-08（“缩短 STUDY_LIFECYCLE_LOCK 的持有时间”），牵动 supervisor 对 snapshotting 状态的判定，不是小改动 |
| S-D13 | 低 | 归前端单元 | — | 两个 SHA 都正确：`snapshot.pack_manifest_sha256` 是冻结后改写过的 manifest，`snapshot_source_manifest.file_sha256` 是源 manifest 文件。缺的只是界面标注 |
| N-6（其余两点） | 低 | 归前端单元 | — | 角色卡片显示时间戳声明；Studies 列表的哈希标注 |
| F2-N3 | 低 | 归前端单元 | — | 页头 pill 用的是数据包的基础角色数（25），Input contract 是 Study 相关的（26）；属于界面文案或数据源的选择 |
| R-D3、R-D5、R-D6、R-D8、R-D11、R-D12、S-D8、S-D11、S-D12、N-5、M2-N1、M2-N3、M2-N4、F-D6 | 低 | 归前端单元 | — | 纯界面问题：文案、轮询 404、状态过期、375 px 布局、标题等。后端已返回所需字段，例如 R-D3 的 `annual_status=non_annual` |
| F-D4 | 中 | 未复现 | — | 复测按原步骤没有复现，`a987ca4..HEAD` 之间也没有针对它的提交，本单元未改动 |

## 3 测试

- 新增或修改的测试：
  - `tests/test_data_mapping.py`：+2；
  - `tests/test_executable_data_adapters.py`：+1；
  - `tests/test_comparison_identity.py`：+1；
  - `tests/test_preflight.py`：新类 `R14PreflightTests`，3 个测试；
  - `tests/test_module_quarantine_api.py`：+1；
  - `tests/test_study_derivation.py`：3 处期望更新；
  - `tests/test_prompt87_tutorial_runtime.py`：扩展 1 个；
  - `tests/test_carbon_ledger.py`：+2 个断言。
- 每个提交前都用 `run_backend_tests.py --modules …` 跑了相关模块：数据映射 13 个、比较 5 个、preflight 与模块 36 个、VALUE 101 与派生 61 个、模块与文档 8–9 个。全部 `passed: true`，`new_failures: []`（失败数都在基线内）。
- `tests/ui_contract_fixtures.py --check`：每次都没有差异（比较、preflight、教程载荷的新字段没有进入夹具）。
- `scripts/golden/capture.py check --tier fast`：所有 case 的 gated 差异为 0（identity 区的差异是原有的）。
- 每个提交前都先运行 `refresh_source_release_manifest.py --index`，再运行 `scripts/p0_gate.py quick`：8 次全部 `status: passed`，16 个步骤都通过，没有豁免，每次约 145 s。

## 4 采用的决策与约定

- A21：剩余问题全部处理；medium 及以上已无遗留；low 只改小处。
- Q12、Q13：不改模型数值和方法。没有 correction id，没有 golden 修订，也没有 VERSION_LEDGER 条目。F2-N4 只改键顺序；S-D6 只影响映射编辑器新写入的文件。
- 约定第 1 节：一个提交只做一件可审查的事。`2d46eab` 含三处互相独立的 preflight 小改动，写在同一提交正文中，见偏差 1。
- CRLF：多个文件是 CRLF 或混合行尾。所有编辑都按原行尾写回；已核对每个改动文件的 CRLF 行数，与原文件一致或只增加了新行。

## 5 偏差

1. `2d46eab` 一个提交含 M2-N2、M-D6、F2-N2 三项。三者都只改 `preflight.py` 中的独立代码块和同一个测试文件，拆开就要逐块暂存。提交正文已逐项说明。
2. S-D9 的 `transformation_id` 保持 `identity/v1`，理由见第 2 节。
3. M-D7 顺带改了 USER_GUIDE、INSTALLATION、BUILD_YOUR_OWN_MODEL_101、BRAND_AND_VARIANTS 中与代码不符的名称（`FORCE_DATA_HOME`、`force.module-bundle/v1`、`gridform.module/v2`、ZIP 目录结构），只改事实错误。这些文档里大量 “FORCE” 品牌文字没有动，不在本单元范围。
4. S-D6 的取整只用于映射编辑器（`execute_adapter(..., significant_digits=15)`）。快照时执行的 adapter 不取整，避免改变已有数据包的冻结字节。

## 6 未决与交接提示

- **前端单元：** 可以用 `changed_dimension_details` 代替原始 JSON（R-D7、S-D9、F-D5）；`GF_PREFLIGHT_MODULE_DISABLED` 和 `GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED` 是新的 readiness 码，scope 分别为 modules 和 environment，现有的分组逻辑会按 error 显示。Rescan 响应新增 `reloaded_modules`。
- **网页上传员 / methodology 编辑员：** 本单元改了 `docs/MODULE_DEVELOPER_101(_ZH).md`、`docs/BUILD_YOUR_OWN_MODEL_101(_ZH).md`、`docs/USER_GUIDE(_ZH).md`、`docs/INSTALLATION.md`、`docs/BRAND_AND_VARIANTS.md`。网站上如果有这些页面的副本，要同步：名称更正，加上模块指南新增的“修改内置 module（方法升级）”一节。方法学正文不受影响。交接文档由负责人更新，本单元没有改 `docs/handoff/`。
- **P1：** S-D10、N-4、O-1、R-D4（启动 Run 时持有 `STUDY_LIFECYCLE_LOCK` 完成执行归档）归入 P1-11 / F5-08。
- **负责人决定：** R-D10、O-3。

## 7 安全核对

- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`，0 字节，mtime 2026-10-03 05:41:26，是安装后首次启动时生成的现网文件，以往报告也有同样记录。`diagnose-value --prefix …` 退出码为 0，输出 “Installation integrity and runtime checks passed.”；中途那行 vinext “Static file stream error … Premature close” 来自它自己的探测请求。门禁的 `installed_inventory` 步骤每次都通过。
- 没有启动任何 HTTP 服务。测试中的本地 API 由测试夹具在随机端口上起停。没有连接 8766/8800，没有向任何进程发信号。
- Python 全部通过 `vpy` 包装器调用；INTEG 中没有 `__pycache__`。scratch 中本单元的临时文件不到 1 MB（`scratchpad/r14/`）。
