# FX2 F-D2：一日范围与扩展（DECISIONS A16-3，设计规格 11.5）

分支 `fix/review-2026-10-04`（INTEG）。作者授权见 A16（“必须修 + 强烈建议一起修”）。

## 1 问题

四类用户测试 F-D2（报告 4.2）：`value_101_day` 走纯 PSM 分支（`gridform_core/application.py` 1874 行起），
在创建 `ExtensionRuntime` 之前就返回，所以扩展从不执行；但 `module-resolution.json` 和输入快照仍记录了
扩展图。结果是：预检不提示；Run 显示 completed；Inspect 只给出 `year_results_missing`；比较页把
“记录了但没执行”的扩展当作方法改变（F-D5 的成因）。

## 2 做了什么

按 A16-3 和规格 11.5 选最小改动：**不改一日路径的执行语义**（不让一日课程去调用扩展 hook，那是方法改动，
需作者另行决定），只阻断并说清楚。

| 位置 | 改动 |
|---|---|
| `gridform_core/run_policy.py` | 新增 `PSM_ONLY_RUN_MODES = {"value_101_day"}`、`scope_runs_extensions(mode)`、`scope_extension_block_message(ids)`（规格原文）。预检、比较、Inspect 共用这一处定义；未记录 mode 时按“会执行扩展”处理（保守） |
| `gridform_core/preflight.py` | Study 选了扩展且范围为纯市场步骤时，加阻断级 error `GF_PREFLIGHT_SCOPE_SKIPS_EXTENSIONS`，message 为规格 11.5 原句（`{names}` 填扩展 id），corrective action 指向“改两时段或更长范围，或取消扩展”。`checks.extension_readiness.executes_in_scope` 记录判定。服务器启动 Run 时本来就拒绝 `accepted=false` 的预检，所以 API 直接启动也会被拦下 |
| `gridform_core/comparison_identity.py` | 一日 Run 记录的扩展不进入 method 维度（`extensions` 置 None，与“没选扩展”一致），config 维度的 `extension_parameters` 置 `{}`；被排除的扩展保留在顶层 `non_executed_extensions`（`reason_code=extensions_not_executed_in_scope`），供审计，不参与比较。其他范围不变 |
| `backend/extension_results.py`（Inspect 的扩展结果） | 冻结扩展图校验通过后，若 Run 的 mode 不执行扩展，返回 `unavailable` + `extensions_not_executed_in_scope`，说明一日课程只跑市场步骤、所记录的扩展没有执行，并提示改用两时段或更长范围；不再报 `year_results_missing`。`capabilities.extensions` 仍列出冻结的扩展 |
| `app/features/workspace/runScope.ts` | `PSM_ONLY_RUN_MODES`（镜像后端）、`EXTENSIONS_DO_NOT_RUN_NOTE`、`runScopeOptionLabel(mode, study)` |
| `app/features/runs/RunWorkspace.tsx` | 范围下拉框用 `runScopeOptionLabel`：选了扩展时一日选项显示 `One-day market lesson (extensions do not run)`。选项仍保留（由预检阻断，符合规格），其余选项不变 |
| `app/features/extensions/ExtensionResultsPanel.tsx` | 遇到 `extensions_not_executed_in_scope` 时显示 `Extensions did not run in this scope.` 加后端原文，不再拼出原始 reason code |
| `docs/dev/P0_FRONTEND_DEVIATIONS.md` | 新增 F-FX2-1（Inspect 文案，规格 11.5 未给出）、F-FX2-2（`{names}` 用 id） |

## 3 测试

新增：

- `tests/test_preflight_scope_extensions.py`（4 个）：只有 `value_101_day` 跳过扩展；消息与规格原文逐字一致；
  VALUE 101 Study + `value-toy-audit-extension` 在 `value_101_day` 下被阻断（唯一一条该 code、severity error、
  `executes_in_scope=false`）；不选扩展的一日范围、选了扩展的 `smoke` 都不出现该 code。
- `tests/test_comparison_identity.py::test_one_day_lesson_recorded_extension_is_not_a_method_change`：
  一日范围下，带扩展（及扩展参数）与不带扩展的两个 Run，method、config 都是 same，`changed_dimensions` 为空，
  解释为 `matching_teaching_configuration`；`smoke` 下同样的差异仍判为 method、config changed。
- `tests/test_extension_results.py::test_one_day_lesson_names_the_scope_instead_of_missing_year_results`：
  一日 Run 返回 `extensions_not_executed_in_scope`；改为 `smoke` 后仍如实报 `year_results_missing`。
- `tests/frontend/unit/run-scope-extensions.test.mjs`（3 个）：标注只出现在一日选项且只在选了扩展时出现；一日选项仍在可选列表中。
- `tests/frontend/render/run-scope-extensions.test.mjs`（2 个）：离线 SSR 渲染 `RunWorkspace`，下拉框中
  `<option value="value_101_day">One-day market lesson (extensions do not run)</option>` 恰好一次；无扩展时没有标注。

运行记录（均经 vpy / vnode；PYTHONPATH=INTEG，TMPDIR、VALUE_DATA_HOME 在 scratch）：

| 命令 | 结果 |
|---|---|
| `-m unittest tests.test_preflight_scope_extensions` | 4 OK |
| `-m unittest tests.test_comparison_identity tests.test_extension_results` | 19 OK |
| `-m unittest tests.test_preflight … tests.test_prompt87_tutorial_runtime tests.test_prompt65_extension_framework` | 48 个，4 个失败均为 `test_prompt87_*`，已在 `tests/baselines/known-failures-linux-py310.txt`（M0 基线） |
| `-m unittest tests.test_run_policy tests.test_scenario_comparison tests.test_prompt104_comparison_eligibility tests.test_prompt122_preflight_resource_gate tests.test_module_quarantine_study tests.test_methodology_profiles` | 56 个，1 个 error（`test_prompt122…test_real_value_101_snapshot_normalization…`），已在基线中 |
| `node --test` 新增两份前端测试 + `tests/run-scope.test.mjs` | 全部通过 |
| `tsc --noEmit -p .` | `app/` 无错误（`e2e/`、`worker/` 的既有类型错误与本改动无关） |
| eslint（改动的 3 个前端文件 + 2 个测试） | 0 error；2 个 warning 为 `RunWorkspace` 既有的未用参数 |
| `refresh_source_release_manifest.py --index` 后 `scripts/p0_gate.py quick` | **passed**，138 s，无豁免；ratchet `new_failures=[]`；node_tests 217 pass / 0 fail |
| INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` | 只列出 `.supervisor.lock`（现网 supervisor 的 0 字节锁文件，早于本轮，以往报告已说明） |
| INSTALLED：`diagnose-value --prefix …/installed` | “Installation integrity and runtime checks passed.” |

没有启动服务，没有连接 8766/8800，没有对任何进程发信号。

## 4 偏差

- 规格 11.5 没有给 Inspect 文案；按任务要求补了一句，记为 F-FX2-1，待设计方复核。
- `{names}` 填扩展 id 而不是显示名（F-FX2-2）。
- 冻结输入恢复（frozen_recovery）若锁定 `value_101_day` 且 Study 带扩展，也会被同一预检阻断。这类历史 Run
  本来就没有执行扩展；按保守做法不为它开例外。
- 比较页前端没有新增提示；`non_executed_extensions` 只在比较身份记录（JSON 导出）中可见。规格只要求“不判为方法改变”。

## 5 遗留

- 已有的一日 Run 的 `module-resolution.json` 仍记录扩展图（历史证据不改写）；比较与 Inspect 已按“未执行”处理。
- 是否让一日课程也调用 initialize / after_psm 属于方法语义，未改动（报告 4.2 的另一种做法，需作者决定）。
