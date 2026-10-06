# FX1-F-D1：选了扩展的 Run 科学验证失败（状态链起点）

单元：FX1-F-D1-state-chain（DECISIONS A16 (1) 必须修 F-D1）
分支：fix/review-2026-10-04（INTEG）
来源：`docs/handoff/FOUR_ROLE_TEST_REPORT.md` 4.1 节

## 1 问题

`AnnualModelOrchestratorV2.run` 只要有 `extension_runtime`，就在第一年之前调用扩展的
initialize，并把 `extension_state` 写进初始状态（即使 initialize 没有输出，也会写入空的 `{}`）。
第一年的 `annual_input_state_sha256` 用的是写入后的状态；而 `application.py` 传给
`run_invariants` 的 `initial_state_sha256` 是写入前的 `contract_hash(source_initial_state)`。
于是 `run.state_chain` 第一年的 `previous_state_is_annual_input` 必然失败，修正口径的
production gate 失败，`scientific_validation_status = failed`，17520 时段的 Run 年度经济结果被扣发。

## 2 做法（采用测试报告建议的第二种：把 initialize 作为链上的一环记录并校验）

没有简单地把起点换成 initialize 之后的哈希。那样第一年的链接会变成自己和自己比较，
源状态到 initialize 的这一步就不再被校验。改为：

1. **orchestrator**（`gridform_core/v2/orchestrator.py`）：有扩展时，在 initialize 前后各取一次
   状态哈希，生成 `extension_initialize` 记录（`schema_version: value.extension-initialize-link/v1`，
   `input_state_sha256` = 源状态，`output_state_sha256` = 写入 `extension_state` 后的状态，
   另记 `extension_ids` 和 `initialized_namespaces`），挂在**本次执行的第一年**的
   `YearResult.extensions` 上。没有扩展时不写这个键，年度结果与之前逐字节相同。
2. **run_invariants**（`gridform_core/run_invariants.py` `_check_state_chain`）：某一年带有
   `extension_initialize` 时，先校验新链接 `previous_state_is_extension_initialize_input`
   （记录的 input = 上一环的输出，第一年即源状态哈希），再把链的“上一环输出”换成记录的
   output，然后照常校验 `previous_state_is_annual_input`（或网络扩展的
   `previous_state_is_network_advance_input`）。缺 output 时记一条失败链接。
   链因此是 source → initialize → annual input，两端都被校验。
3. **网络扩展事件的输入哈希**：原代码第一年的 `network_expansion.advance_year` 事件把
   `initial_state`（initialize 之前）记为输入，实际输入是 initialize 之后的 `state`。改为记录实际
   传入 `advance_year` 的状态。没有扩展时两者相同，事件逐字节不变。
4. **断点续跑**：续跑时 orchestrator 会对 checkpoint 状态再调一次 initialize，记录挂在续跑的第一年；
   其 input 等于上一年 `next_state` 的哈希，链照样闭合（单元测试覆盖）。

`application.py` 不需要改：传入的仍是源状态哈希，作为链的锚点。`provenance.py` 已有的
`source_initial_state_sha256` / `effective_initial_state_sha256` 区分保持不变。

## 3 两个口径

- **修正口径（value-corrected）**：修复直接生效。带扩展的 Run 的 run invariants 与不带扩展的对照 Run
  相同（passed），validation gate、`scientific_validation_status` 也与对照相同。
- **论文复现口径（doctoral-lineage-0.6.0a2）**：`profiles.json` 中 `supported_extensions: []`，
  任何扩展在预检时就被 `VALUE_PROFILE_COMBINATION_UNSUPPORTED`（sub_reason `extension`）拒绝，
  不会进入年度状态链。不带扩展的 doctoral Run 没有 `extension_initialize` 键，事件与链与修复前
  完全相同，doctoral trajectory 不受影响，无需重设 golden。修复代码与口径无关，两个口径共用。

## 4 测试

新增：

- `tests/test_run_invariants.py` `ExtensionInitializeChainTests`（不变量计算的单元测试）：
  - source → initialize → annual input 两年链通过（9 条链接）；
  - 去掉 initialize 记录时复现修复前的失败（2025 年 `previous_state_is_annual_input`）；
  - 篡改 initialize 的 input、output 或缺 output 时失败；
  - initialize 之后接网络扩展 advance 通过；
  - 续跑：initialize 记录挂在续跑年时链通过；
  - **整年路径**：`execution_scope=annual`、`periods_per_year=17520`、2025–2050 共 26 年，
    `run.state_chain` passed（105 条链接），报告状态不是 failed；去掉 initialize 记录则
    `run.state_chain` 进入 failed_checks。
- `tests/test_prompt65_extension_framework.py`：
  - `test_noop_extension_run_passes_invariants_and_scientific_validation`：注册一个没有任何 hook、
    数据角色和参数的 no-op 扩展，经 `run_project_application` 跑 smoke；断言 `run.state_chain`
    与 run invariants 为 passed，gate 中 `run_invariants: passed`，gate 与
    `scientific_validation_status` 与不选扩展的对照 Run 完全一致（默认口径与显式 value-corrected 各一次）；
  - `test_initializing_extension_run_passes_invariants_and_scientific_validation`：同样断言，扩展为带
    initialize 的 toy 扩展（对应测试报告变体 A）；
  - `test_doctoral_profile_refuses_any_extension_before_the_state_chain`：doctoral 拒绝 toy 和 no-op 扩展，
    corrected 接受；
  - 原 `test_toy_extension_runs_two_years_through_normal_application_path` 补上 run invariants 为
    passed 的断言（测试报告指出的缺口），并断言 `extension_initialize` 只挂在第一年。

修复前后对照：撤回 orchestrator 改动后，上述两个 Run 级测试的 4 个子用例全部失败；恢复后全部通过。
smoke Run 的哈希与测试报告一致（源 `a0fbd278…`，initialize 后 `8f4a6915…`）。

运行结果见第 5 节。

提交：`cac5fce fix(validation): extension initialize is a verified link of the state chain (F-D1)`（代码、测试、发布清单刷新）。

## 5 运行记录

| 命令（均经 vpy，PYTHONPATH=INTEG，TMPDIR/VALUE_DATA_HOME 在 scratch） | 结果 |
|---|---|
| `-m unittest tests.test_prompt65_extension_framework tests.test_run_invariants` | 35 个测试 OK（约 16 s） |
| 同上，但撤回 orchestrator 改动 | 新增的两个 Run 级测试 4 个子用例 FAIL（确认测试能抓住 F-D1） |
| `-m unittest tests.test_orchestrator_v2 tests.test_prompt70_network_expansion tests.test_golden_corrected tests.test_golden_doctoral tests.test_frozen_input_recovery tests.test_prompt119_value_context_runtime tests.test_comparison_identity tests.test_prompt115_value_101_network_exercise` | 56 个测试，1 个失败：`test_prompt115…test_frontend_teaches_scope_and_uses_existing_results_page`（前端源码断言，已在 `tests/baselines/known-failures-linux-py310.txt` 中，与本改动无关） |
| `scripts/p0_gate.py quick`（第一次） | failed：只因 `source-release-manifest.json` 过期（release_manifest 与 ratchet 中的 `test_repository_manifest_is_current`） |
| `refresh_source_release_manifest.py --index` 后再跑 `scripts/p0_gate.py quick` | **passed**，138.6 s，无豁免；ratchet new_failures=[]、fixed_but_listed=[]、forbidden_port_attempts=[] |
| INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` | 只列出 `.supervisor.lock`（现网 supervisor 2026-10-03 创建的 0 字节锁文件，早于本轮，以往报告已说明） |
| INSTALLED：`diagnose-value --prefix …/installed` | “Installation integrity and runtime checks passed.” |

没有启动任何服务，没有连接 8766/8800，没有对任何进程发信号。

## 6 偏差

- 任务要求“在两个口径下”通过。doctoral 口径按 profiles.json 不允许任何扩展，无法跑带扩展的 doctoral Run；
  改为测试 doctoral 拒绝扩展，并说明不带扩展的 doctoral Run 不受影响。没有放开 doctoral 的扩展白名单。
- Run 级测试用的是 smoke（2 时段）范围，`scientific_validation_status` 在对照 Run 中本来就是
  `not_evaluated`（不是 17520 时段），所以断言为“与对照相同且不是 failed”；17520 整年路径由
  不变量计算的单元测试覆盖，没有跑真实整年 Run。

## 7 遗留

- 续跑时 orchestrator 会对 checkpoint 状态再调一次 initialize，并覆盖已有命名空间的
  `extension_state`。对确定性的 initialize 没有影响；如果某个扩展的 initialize 不确定，续跑会改变状态
  （链会如实记录这一步，不会误报）。是否续跑时跳过 initialize 属于扩展语义，未改动。
- F-D2（一日范围静默跳过扩展）、F-D5 不在本单元范围。
