# R6 定向验证报告（DECISIONS A28、A29）

- 被测构建：`fix/review-2026-10-04` @ `6014421`（`git archive HEAD` 到 `scratchpad/build/r6verify/src`，不含工作树中他人未提交的方法学/网站改动；vinext 重新构建）。
- 实例：API 18870（PID 3652035）、UI 网关 18871（PID 3652036），`VALUE_DATA_HOME=scratchpad/build/r6verify/state`（全新目录，`install_synthetic_pack.py --value-101-only`）。Playwright headless（chromium 1243）+ API。
- 范围（A28）：只重跑 `docs/handoff/FOUR_ROLE_TEST_REPORT.md` 中 EM-中1、AF-低1、AF-中1 的复现步骤，以及任务指定的 AF-中1 检查项。不做探索性测试，不改代码。
- 测试对象：本地模块 `hx-flat-offer-73`（R5 验证用的同一构建包）；扩展 `ver-af-hooks`（after_cem 返回带 `artifact_type` 的产物）和 `ver-af-plain`（只有 initialize、after_psm）。

## 1 缺陷对照表

| 缺陷 | 结论 | 证据 |
|---|---|---|
| EM-中1 有 Run 排队时改模块：确认框说会用新代码启动，实际以 `GF_CONTRACT_001` 失败 | 已修（主路径）；残留 1 个低等竞态，见第 2 节 | ① 启动两个两整年 Run 后立即在 Modules 页 Disable，确认框为 “2 run(s) not started yet (…) will not start: the change alters the code they recorded, so VALUE stops them with GF_RUN_EXECUTION_IDENTITY_CHANGED and you resubmit them from the Runs page (Resubmit with current code)”，不再有 “would start with the changed code”；第二次（Enable）确认框还分列 “2 run(s) already running … keep their code”。② 准备中的 Run `…084537-ac85a42f`（确认 Enable 时处于 snapshotting）：failed，`GF_RUN_EXECUTION_IDENTITY_CHANGED`，类别 `execution_identity`，`error_detail` 为诊断首行。③ 已持租约的 Run `…084746-87ab39ab`（变更时 queued、`worker.json` 已写入）：服务器不改写，worker 约 24 s 后以同一错误码失败，首行写明记录与当前身份（`0e5bdceb098f…` → `cf8d76fc0479…`）。④ Runs 页：错误框为新错误码及公开说明，下一行是诊断首行；有 `Resubmit with current code`；点击后发出 `POST /api/projects/value-101-baseline/runs {"mode":"two_year"}`，选中新 Run `…084730-752a7086`，提示 “The complete two-year model has started.”，该 Run 实际完成（execution passed、scientific passed，2/2 年）。⑤ 服务器当场停止“未持租约的 queued Run”（`stopped_unstarted_runs`）在真实时序下没有触发：worker 几毫秒内就取得租约，这条路径只由 R6-1 的单测覆盖 |
| AF-低1 扩展钩子产物被拒时，Runs 页只显示 `GF_CONTRACT_001` | 已修 | `hooks-study` 两时段 Run `…085213-017d9fda`：status.json 写 `GF_EXTENSION_OUTPUT_REJECTED`，类别 contract。Runs 页错误框：“GF_EXTENSION_OUTPUT_REJECTED: An extension hook returned an output that VALUE does not accept; …”，下一行 “Extension ver-af-hooks:after_cem returned artifact 'local.ver-af.year-summary', but VALUE records extension artifacts only from after_psm …”；页面上没有 `GF_CONTRACT_001`，也不提供重新提交按钮 |
| AF-中1 原地改过钩子源码的扩展，停用后不能重新启用 | 已修（按 A29） | **往返（未被引用的 `ver-af-hooks`）**：合法地原地改 `hooks.py` → Rescan → Disable → Enable 返回 200；`installation.json` 追加 `accepted_source_edits[0]` = {accepted_at, changed_modules `["value_ext_37b20e8142d6c184.hooks"]`, hook_source_identities `8c6c3e9e…`}，安装身份 `e815fbf3…` 保持不变。改坏的钩子：Enable 返回 400 `GF_EXTENSION_HOOK`（“failed to import: SyntaxError … line 3”），扩展保持停用，不追加记录。清单改为声明其他钩子：Enable 返回 400 `GF_EXTENSION_SOURCE_CHANGED`（要求以新版本重建）。恢复后 Enable 200。**被 Study 引用（`ver-af-plain`、`plain-study`）**：卡片 Disable 返回 409 `GF_EXTENSION_IN_USE`；改坏后 Rescan，隔离 `GF_EXTENSION_HOOK_IMPORT` → 界面上在隔离面板点 Disable（确认框）→ 修成合法改动 → 在 Disabled 面板点 Enable，提示 “ver-af-plain is enabled. Check readiness again before running a Study that uses it.”，记录 `accepted_source_edits` 1 条（`3ba16106…`）。readiness：`GF_PREFLIGHT_EXTENSION_SOURCE_CHANGED`（“changed since install (d4dd5b4e… → 3ba16106…)”），另有 `GF_PREFLIGHT_REVISION_REIDENTIFY`。重跑后 Study 追加修订 2，原因 `source-reidentify`；`/api/comparisons` 比较改前、改后两次 Run，只有 `identity.method` 一维变化，路径为 `extensions.hook_source_identities`，review status 为 verified。第二轮（改坏 → 隔离面板 Disable → 仍坏时 Enable 400 `GF_EXTENSION_HOOK` → 修好 → Enable 200，记录 2 条，`00883d08…`）后跑两次两整年 Run，产生修订 3（`source-reidentify`）。界面 Compare 的 “Identity check before comparison” 中，“Model method (modules, extension selection, methodology)” 为 Changed，其余维度为 Same；`metric_deltas_allowed=false` |

## 2 残留（EM-中1 的一个竞态，低等，不阻塞）

- **现象：** 在 Run 正在记录执行环境的前几秒内停用模块，该 Run 不会以 `GF_RUN_EXECUTION_IDENTITY_CHANGED` 失败，而是以 `GF_INPUT_SNAPSHOT_FAILED` 失败，错误框显示原始信息 `[Errno 2] No such file or directory: '…/state/modules/hx-flat-offer-73.json'`，也没有 `Resubmit with current code` 按钮。
- **复现（4/4）：** 界面路径（启动 Run 后立即 Disable）出现 1 次：`…084212-410b0bb8`；API 在启动后 0.3 s、1 s、3 s 停用，各出现 1 次：`…085037-be693c57`、`…085049-55e5977e`、`…085100-d3d75f16`。改为 8 s 后停用（`…084952-a6660aa1`）时，Run 正确地以新错误码失败。
- **原因：** `gridform_core/execution_archive.py` 的 `_source_roots`（第 123–135 行）在采集开始时列出 `modules/*.json`，之后在计算哈希时才读取文件。模块生命周期操作不获取 `EXECUTION_CAPTURE_LOCK`，清单在两步之间被移走。产生的 `OSError` 进入 `backend/server.py` 中 `_prepare_run_stages` 的通用分支，被记为 `GF_INPUT_SNAPSHOT_FAILED`。
- **影响：** 安全失败，不产生结果；用户在 Study 中重新运行即可。只是错误码和提示仍然笼统。
- **修法建议（未改）：** 让五个生命周期操作先获取 `EXECUTION_CAPTURE_LOCK`（锁顺序允许它排在 `MODULE_LIFECYCLE_LOCK` 之前）；或者把采集期间 `modules/` 下出现的 `FileNotFoundError` 归为 `ExecutionIdentityChangedError`。
- **附带观察（不计缺陷）：** 第一次试验的第二个 Run `…084212-8a071744` 在等待采集锁。确认框把它列为 “will not start”，但它在变更之后才采集，实际按新代码启动并正常完成。这里文字比实际保守，不会产生错误结果。

## 3 门禁

- 在 INTEG（工作树有他人未提交的改动）上运行 `scripts/p0_gate.py quick`（`VALUE_GATE_VENV=scratchpad/build/gate-venv`）。guard、test_environment、release_path_hygiene、methodology_catalog、runtime_overlay、version_ledger、golden_bookkeeping、append_only、node_tests、http_harness、typecheck_frontend、eslint_ratchet、network_guard、installed_inventory 均通过。
- 有两步失败，都只由未提交的改动引起：
  - `release_manifest`：stale 列表只包含他人未提交的方法学/网站文件和未跟踪的 `output/pdf/VALUE_Methodology.pdf`。`refresh_source_release_manifest.py --index --check` 对已提交内容的结果为 `stale: false`。
  - `backend_ratchet`：共 2,740 个 id，149 个失败，新增失败 2 个。其一是 `test_refresh_source_release_manifest…test_repository_manifest_is_current`，原因同上。其二是 `test_r33_biomass_disclosure.BiomassAdvisoryTests.test_documents_name_the_disclosure`：该测试读取 `docs/SCHEME_C_MODEL_CARD.md`。HEAD 中这个文件含 `VALUE-ADV-BIOMASS-SUPPORT-NOT-MODELLED`，工作树中未提交的改写删掉了这个编号。**请做方法学/网站改动的一方在提交前补回该披露编号**，否则这个测试会在提交后失败。
- 本单元没有触碰、暂存或提交上述文件。

## 4 环境与清理

- 两个服务按记录的 PID（3652035、3652036）停止，端口 18870/18871 已释放。没有连接 8766/8800，没有按模式 kill。Run 的 worker 都已自行结束。
- 删除了 `src`、`state`（约 1.1 GB）和浏览器配置；`scratchpad/build/r6verify` 剩约 3 MB，包括脚本、日志、gate.json 和 10 张截图（`shots/`）。
- INSTALLED：`find … -newer install-receipt.json …` 只列出 `.supervisor.lock`（2026-10-03 05:41，作者实例的锁文件，早于本轮）。`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”（另有已知的 vinext “Premature close” 日志行）。
- Python 全部经 `vpy` 调用。本单元不改代码，只提交本报告。
