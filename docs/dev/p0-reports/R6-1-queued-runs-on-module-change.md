# R6-1 有 Run 排队时改模块或扩展（EM-中1、AF-低1；DECISIONS A29）

单元键：`R6-1-queued-runs-on-module-change`。分支 `fix/review-2026-10-04`（INTEG 工作树）。

## 1 问题与做法

- **EM-中1**：有 Run 排队时安装、启用、停用、移除模块或扩展，确认框说尚未开始的 Run “would start with the changed code”；实际上 Run 入队时已记录执行身份（含全部已安装模块和扩展），worker 启动时发现身份变了就抛 `ValueError`，被 `public_failure` 归为通用的 `GF_CONTRACT_001`。
- **AF-低1**：扩展钩子输出被拒（after_psm 以外的钩子返回带 `artifact_type` 的产物等）同样落入 `GF_CONTRACT_001`，原因只在 `diagnostics/error.json` 中。

采用任务建议的首选方案：行为与说明一致——确认后，执行身份已变、尚未开始的 Run 立即以专门错误码失败，并给出一键“按当前代码重新提交”；Runs 页显示诊断首行。没有做“自动重新入队”（会在用户不知情时以新代码重算，且绕过 readiness 与 Q13 方法变更确认，不取）。

## 2 改动

### 后端

1. `gridform_core/errors.py`
   - 新增 `ExecutionIdentityChangedError`（`GF_RUN_EXECUTION_IDENTITY_CHANGED`，类别 `execution_identity`，公开说明：已安装的模块、扩展或 VALUE 代码在 Run 排队后变了，所以没有启动，请重新提交）。仍是 `ValueError` 子类，原有处理（如 resume 的 409 `GF_EXECUTION_IDENTITY_CHANGED`）不变。
   - 新增 `ExtensionOutputError(ContractError)`（`GF_EXTENSION_OUTPUT_REJECTED`，类别 contract）。
   - 新增 `failure_detail()`（异常信息首个非空行，最长 400 字符）与 `DETAIL_CATEGORIES = {contract, execution_identity}`。
2. `backend/run_execution.py`：worker 启动核对执行身份不符时改抛 `ExecutionIdentityChangedError`（信息含记录与当前身份前 12 位、原因和出路）；新增 `source_identity_changed()`。
3. `gridform_core/execution_archive.py`：新增 `current_source_sha256()`，只扫源码半边（app 源码 + modules 下活动清单与已启用安装），不扫运行时；生命周期变化只改这一半，用来廉价判断排队 Run 是否会被拒。
4. `gridform_core/extension_framework.py`：`ExtensionRuntime.invoke` 中“返回非映射”“非 after_psm 钩子返回产物”“产物校验不通过”三处改抛 `ExtensionOutputError`，信息写明扩展、钩子和规则（产物校验原因前缀 `Extension {id}:{hook} returned a rejected artifact:`）。`validate_extension_artifact` 本身不变（`extension_results` 仍按 `ValueError` 捕获）。
5. `backend/model_runner.py`：`record_run_failure` 对 contract / execution_identity 两类失败在 `status.json` 写 `error_detail`（诊断首行）；其他类别不写，并清掉旧值。
6. `backend/server.py`
   - 确认框文字（`require_no_pending_runs`）：尚未开始的 Run 改为 “will not start: the change alters the code they recorded, so VALUE stops them with GF_RUN_EXECUTION_IDENTITY_CHANGED and you resubmit them from the Runs page (Resubmit with current code)”；已运行一句不变。
   - 确认后立即停：五个生命周期响应（模块安装、扩展安装、移除、模块启停、扩展启停）在变更完成、释放 `MODULE_LIFECYCLE_LOCK` 之后调用 `stop_unstarted_runs_with_changed_code()`：只处理 `queued`、本后端不在准备、记录了 `execution-bundle.json` 源码哈希且与当前源码哈希不同、**没有 worker 持有租约**的 Run；在 run action lock 下、status 锁内再次确认仍是 queued 后转为 failed（reason_code 与 error_code 都是 `GF_RUN_EXECUTION_IDENTITY_CHANGED`，`current_stage` = “Not started: the installed code changed after it was queued”），再写 `diagnostics/error.json`。响应加 `stopped_unstarted_runs`。
   - 准备中的 Run（snapshotting）：新增全局“生命周期代数”，每次目录刷新（`refresh_module_catalog`，所有生命周期变更都以它结束）加一。准备线程在记录执行身份时（`EXECUTION_CAPTURE_LOCK` 内、捕获之前）读代数；之后每进入一个准备阶段（snapshot、resources、worker）若代数变了，就在 `MODULE_LIFECYCLE_LOCK` 下重算源码哈希，若与记录不同则以同一错误码记录准备失败、不再快照/预留/启动 worker（取消请求优先）。
   - worker 已持有租约的 Run：由 worker 自己的身份核对抛出新错误码（见第 2 条），不由服务器改写（P0-3：服务器从不覆盖活着的 worker）。
   - 运行列表/详情：失败且类别属 `DETAIL_CATEGORIES`、但没有 `error_detail` 的旧 Run，读 `diagnostics/error.json` 的首行补上（旧的 `GF_CONTRACT_001` 失败也能看到原因）。

### 前端（按规格现有组件实现；偏差记入 `P0_FRONTEND_DEVIATIONS.md` R6-1 节 F-R61-1…4）

- `app/features/runs/RunWorkspace.tsx`：错误框下另起一行显示 `error_detail`（`.run-error-detail`）；错误码为 `GF_RUN_EXECUTION_IDENTITY_CHANGED` 的失败 Run 显示主按钮 `Resubmit with current code`，并隐藏对这类 Run 无意义的 checkpoint Resume 按钮。
- `app/page.tsx`：`resubmitRun(run)` 以该 Run 的 Study 和范围调用现有 `startRun`（与 Run selected scope 同一请求，readiness 与迁移确认照常）；七处生命周期成功提示后追加被停 Run 的说明（`stoppedRunsNotice`）。
- `app/features/modules/module-quarantine.mjs`：`stoppedRunsNotice()`；`app/features/runs/types.ts` 增 `error_detail`；`app/globals.css` 增 `.error-box .run-error-detail`。

### 文档

- `docs/USER_GUIDE.md`、`docs/USER_GUIDE_ZH.md` 模块生命周期一段改为如实描述（尚未开始的 Run 以 `GF_RUN_EXECUTION_IDENTITY_CHANGED` 停止，Runs 页 Resubmit with current code）。
- `docs/dev/P0_FRONTEND_DEVIATIONS.md` 新增 R6-1 节。

## 3 测试

- 新增 `tests/test_r6_queued_runs_module_change.py`（13 个，全部通过）：错误分类与 `failure_detail`；worker 身份核对抛新错误；`record_run_failure` 对两类新错误写 `error_detail`、对运行时错误不写；扩展 after_cem 返回产物抛 `ExtensionOutputError` 并给出扩展、钩子、产物名；准备线程只在代数变化后才重算哈希、哈希未变时采用新代数；API：409 确认文字（含 “will not start”、错误码、按钮名，不含旧句）→ 确认启用 → 记录了旧源码的 queued Run 被停（状态、生命周期记录、诊断文件、`stopped_unstarted_runs`、`/api/runs` 中的 `error_detail`），没有身份记录的 queued Run 不动；源码未变的 queued Run 不被停；旧的 contract 失败从诊断文件补出首行。
- 更新 `tests/test_module_quarantine_api.py` 中对旧确认文字的断言。
- 前端单测 `tests/frontend/unit/module-quarantine.test.mjs` 新增 `stoppedRunsNotice` 用例（4/4 通过）。
- 相关回归（vpy unittest）：`test_doctoral_run_worker_path`、`test_execution_archive`、`test_extension_source_bundle`、`test_lock_order`、`test_module_quarantine_api`、`test_extension_results`、`test_run_status`、`test_prompt65_extension_framework`、`test_provenance_errors`、`test_module_quarantine`、`test_r5_add_feature_defects`、`test_module_recovery`、`test_r6_queued_runs_module_change`、`test_run_execution_admission`、`test_run_async_start`、`test_run_quota_accounting`、`test_r4_module_extension_defects` 共 194 个通过；`test_prompt121_failure_and_recovery`（需 tests 目录在 PYTHONPATH）23 个通过。
- tsc（`tsconfig.frontend.json` 由门禁执行）与 eslint：改动文件无新增问题（eslint 在 page.tsx/RunWorkspace.tsx 报的 1 错 3 警告均为既有行，在基线内）。
- Playwright（headless chromium 1243；scratch 实例 API 18910、UI 18911，`VALUE_DATA_HOME=scratchpad/r61/ui/data`，vinext 重新构建；全部 PASS、无 pageerror）：
  1. 数据目录放入仓库自带的 `value-101-baseline-v1` 包和一个已启用的测试模块，建 VALUE 101 Study；种入一个 queued Run（记录了旧源码哈希，worker 记录处在 30 s 启动宽限内）和一个经 `record_run_failure(ExtensionOutputError)` 记录失败的 Run；
  2. Modules 页 Disable 该模块：确认框为新文字；确认后提示条写 “1 Run that had not started was stopped … (GF_RUN_EXECUTION_IDENTITY_CHANGED): r61-queued. Resubmit it …”；
  3. Runs 页：错误框为 `GF_RUN_EXECUTION_IDENTITY_CHANGED` 及公开说明，下一行为诊断首行；有 `Resubmit with current code`、无 checkpoint Resume；点击后发出 `POST /api/projects/value-101-baseline/runs {"mode":"smoke"}`，选中新 Run 并显示启动提示（该请求在浏览器中被应答，以免 scratch 实例为一次 Run 归档整个运行时；真实启动路径由既有测试覆盖）；
  4. 扩展失败 Run：错误框为 `GF_EXTENSION_OUTPUT_REJECTED`，首行写明 `r61-observer:after_cem` 和 “only from after_psm”，无重新提交按钮。
  截图在 scratchpad `r61/ui/shots/`。实例与占位进程按记录的 PID 停止。
- `scripts/p0_gate.py quick`：见第 6 节。

## 4 遵循的决定

- A29：EM-中1 与 AF-中1 同轮修复；本单元只做 EM-中1 与同根因的 AF-低1，AF-中1（扩展原地改源后重新启用）属 R6-2，未触碰 `extension_bundle.py`。
- P0-3 生命周期：服务器只在没有 worker 持租约时写 queued→failed，且在 run action lock 与 status 锁内复核状态；所有状态变化都经 `update_status` 的转移表；准备线程的失败沿用 `_preparation_failed`。锁顺序：`EXECUTION_CAPTURE_LOCK → RUN_ACTION_LOCKS → MODULE_LIFECYCLE_LOCK`，新增的代数锁是叶锁。
- Q13：重新提交走普通 Run 启动路径，方法变更仍需在 readiness 中明确确认；不自动迁移、不自动重排。

## 5 偏差

- 未实现“自动重新入队”（报告中列为可选）；理由见第 1 节。
- 服务器“立即停止”只覆盖没有 worker 持租约的 queued Run（通常是刚 spawn、尚未取得租约的瞬间）；已持租约的由 worker 自己以同一错误码失败（几秒内），准备中的在下一阶段边界失败。三条路径错误码一致，`stopped_unstarted_runs` 只列服务器当场停下的。
- 这类 Run 隐藏 checkpoint Resume 按钮（F-R61-3），因为它从未开始、恢复必被拒。
- Playwright 中重新提交的启动请求在浏览器中应答，未在 scratch 实例真实启动 Run（避免归档约 1.3 GB 运行时）。

## 6 门禁与安装完整性

- `scripts/p0_gate.py quick`（`VALUE_GATE_VENV=scratchpad/build/gate-venv`，提交前在工作树上运行）：guard、test_environment、release_path_hygiene、methodology_catalog、runtime_overlay、version_ledger、golden_bookkeeping、append_only、node_tests、http_harness、typecheck_frontend、eslint_ratchet、network_guard、installed_inventory 通过；backend_ratchet 2,738 个 id，148 个失败中唯一的新失败是 `test_repository_manifest_is_current`，release_manifest 同因——只因源发布清单尚未刷新。两个代码提交各自用 `refresh_source_release_manifest.py --index` 刷新清单，`--index --check` 均为 `stale: false`。（工作树中另有并行单元未提交的方法学/网站改动，不在本单元提交内，故未再对整个工作树重跑 release_manifest。）
- 安装完整性：`find INSTALLED -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（2026-10-03 05:41，作者在用实例的监督锁，早于本单元，此前报告已记录）；`diagnose-value --prefix INSTALLED`：“Installation integrity and runtime checks passed.”。没有写入 INSTALLED，没有接触 8766/8800。

## 7 遗留

- 无功能性遗留。确认框与按钮的措辞和位置待设计方复核（F-R61-1、F-R61-3）。
