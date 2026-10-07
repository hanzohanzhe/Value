# R3-4 工作报告：Run 异步启动与全局锁拆分（A24-5：O-1、N-4、L-4、F5-08、P1-11）

工作位置：`value-fix-review-2026-10-04`（分支 `fix/review-2026-10-04`）。本单元只改启动流程、锁和界面显示，不改模型、方法或数据；没有 correction id，没有 golden 修订，没有 VERSION_LEDGER 条目（Q13：纯代码改动）。

## 1 改动前的情况（实测）

在 scratch 实例（API 18970，`VALUE_DATA_HOME` 在 scratchpad，真实 VALUE 101 数据包）上，用改动前的代码实测：

- 启动请求同步执行。首次在新数据目录启动一日 Run，POST 用了 **172.2 s**（其中执行环境归档约 171 s）；第二次启动 **36.0 s**。
- 整个过程持有全局 `STUDY_LIFECYCLE_LOCK`，期间 clone、保存 Study、回收站、映射目录等请求全部挂起（F5-08、N-4）。
- 界面只能显示 “Starting…”（O-1、L-4）。
- preflight 只用 0.7 s。慢的是执行身份采集与归档，以及输入快照。

## 2 实现

### 2.1 启动分三段，然后立即返回 202

`Handler._start_run`（`backend/server.py`）：

1. **准入**（持 `STUDY_LIFECYCLE_LOCK`）：`_admit_run` 读 Study，做校验、范围与策略、数据包选择、Study 修订分类与自动迁移，分配 run_id，并记下 `project.json` 的字节哈希。
2. **preflight**（不持锁）：`_preflight_admitted_run`。拒绝时仍然是 400，带 preflight 报告，不建 Run。这与原接口和界面一致。
3. **建 Run**（持 `STUDY_LIFECYCLE_LOCK`）：`_create_preparing_run` 先确认已保存的 Study 与准入时逐字节相同。如果不同（例如 preflight 期间被保存或移入回收站），返回 409 `GF_RUN_START_STUDY_CHANGED`，不建 Run。相同则在 `RUN_ACTION_LOCKS[run_id]` 内建目录，写 `snapshotting` 状态（带 `preparation` 块，以及 `completed_years: 0`、`total_years`），并在释放该锁之前登记准备线程。

随后启动线程，答复 `202 {"ok": true, "run": present_run(...)}`。返回的 `run.status` 是 `snapshotting`，`run.preparation.state` 是 `preparing`。

### 2.2 后台准备线程 `_prepare_run`

模块级函数，四个阶段依次写入 `status.json` 的 `preparation`：

| # | stage | 显示文字 |
|---|---|---|
| 1 | `execution` | Recording and archiving the execution environment |
| 2 | `snapshot` | Freezing the Study's inputs |
| 3 | `resources` | Checking disk space and reserving output space |
| 4 | `worker` | Starting the model worker |

- `preparation`（schema `value.run-preparation/v1`）记录 `state`、`stage`、`stage_label`、`stage_index`/`stage_count`、开始时间、每个已完成阶段的用时（`stages`）。结束时写 `finished_at` 与总用时 `elapsed_seconds`。`present_run` 对进行中的准备按服务器时钟补上 `elapsed_seconds`、`stage_elapsed_seconds` 和 `in_progress`。界面每 2 s 轮询一次，所以用时随之更新。
- 每次写状态只短暂持有 `RUN_ACTION_LOCKS[run_id]`。排队和 spawn worker 在同一把 run 锁内完成，与 P0-3 相同。线程**从不持有** `STUDY_LIFECYCLE_LOCK`。
- 执行身份采集与归档放在新的进程内锁 `EXECUTION_CAPTURE_LOCK` 中。原因是 `capture_execution_bundle` 会改 `sys.path`，并可能发布共享的执行归档（staging 加 replace；并发发布同一目录会失败）。这些操作以前由全局锁串行，现在由这把专用锁串行。
- 每个阶段开始前读取 `cancel-request.json`。已请求取消时，Run 从 `snapshotting` 记为 `cancelled`（`GF_RUN_CANCELLED_BEFORE_WORKER`），不启动 worker。
- 失败的记录方式：
  - 磁盘门槛与预留的拒绝、预留锁超时、快照或归档错误、spawn 失败：保留原错误码，在 Run 上记为 failed，`preparation.failed_stage` 记失败阶段。以前这些情况由请求返回 507/503/409/500。
  - 意外异常：记为 `GF_RUN_PREPARATION_FAILED`，`error` 写异常类型和消息，`current_stage` 为 `Run preparation failed`，同时把 traceback 写入后端日志。Run 不会停在 `snapshotting`。
- 线程结束时注销登记（`finally`）。

### 2.3 崩溃安全（P0-3 生命周期、租约接管）

- `RunSupervisor` 新增 `preparing` 回调，服务器传入 `run_is_preparing`。tick 跳过本后端正在准备的 Run。登记发生在 run 锁内、创建状态之后，因此 tick 在任何时刻都不会判定一个正在创建或准备的 Run。
- 如果后端在准备途中停止，下次启动时 `reconcile_all` → `judge` 会看到 Run 处于 `snapshotting` 且没有 spawn 记录（liveness `not_started`），把它记为 failed，原因码为 **`GF_RUN_PREPARATION_INTERRUPTED`**：`current_stage` 为 `Run preparation interrupted`，`preparation.state` 为 `interrupted`，错误说明写“没有计算任何内容，请重新启动 Run”。已有取消请求的则记为 cancelled。之后照常进入失败 provenance 的封存队列。
- `mark-lost` 对正在准备的 Run 返回 409 `GF_RUN_PREPARING`。
- 已有 worker 的 Run 仍按原来的租约逻辑处理，这部分没有改。

### 2.4 锁的拆分与正确性

- 全局顺序（`P0_CONVENTIONS` 第 5 节与 `server.py` 注释已更新）：`.backend.lock → STUDY_LIFECYCLE_LOCK → EXECUTION_CAPTURE_LOCK → RUN_ACTION_LOCKS[run] → MODULE_LIFECYCLE_LOCK → .reservation.lock → status.lock`。`_RUN_PREPARATIONS_GUARD` 是叶子锁。
- `STUDY_LIFECYCLE_LOCK` 现在只保护短的目录区段：准入，以及建 Run 时的复核和首次写状态。
- 冻结期间不需要再按 Study 加锁，理由如下：
  - 准备线程使用准入时冻结在内存中的 Study 副本，保存同一个 Study 不影响它；
  - Run 处于 `snapshotting`（活动状态）时，Study 移入回收站、VALUE 101 重置、模块删除原本就因为“有活动 Run”而被拒绝；
  - 被冻结数据包的文件替换（上传、映射提交）在冻结期间返回 409 `GF_DATA_PACK_FREEZING`；
  - 快照对每个源文件做哈希核对（“Source changed before snapshot”），即使发生竞争也会让 Run 明确失败，不会得到混合快照。
- clone 数据包、保存 Study 和其他 Study 的启动只在短时间内拿全局锁，不再被冻结阻塞。

### 2.5 界面（规格第 5 节约定；偏差 F-R34-1…4）

- **Runs 页：** 所选 Run 处于准备中时，状态行下显示 `Preparing · step {i} of {n}: {阶段} · {用时} elapsed`（13px、600、`--ink`、`role=status`），下面保留原来的首次归档说明。准备中可以 `Request safe cancellation`；取消后进度句末尾加 “Cancellation requested: the Run stops before its model worker starts.”。启动按钮下的说明和空状态文案改为“检查 readiness 并建 Run，随后在后台冻结”。
- **Learn 页：** 课程的 Run（一日、两年、网络练习的两个 Run）处于准备中时，课程标题下显示 `learn-run-preparation` 块，每个 Run 一行 `{One-day Run / Two-year Run / Copperplate Run / Constrained Run}: {进度句}`。启动中的说明改为新的 `LEARN_RUN_FREEZE_NOTE`。
- 新元素遵守规格第 1.3 节：文字不小于 12px，只用已有 token。

## 3 文件

- 后端：`backend/server.py`（启动三段、准备线程、登记与等待、`present_run` 进度、上传的冻结检查）、`backend/run_supervisor.py`（`preparing` 回调、`GF_RUN_PREPARATION_INTERRUPTED`、mark-lost 拒绝）、`backend/data_mapping.py`（`busy_packs` 回调，映射提交的冻结检查）。
- 前端：`app/features/runs/types.ts`（`RunPreparation`）、`runHistoryView.ts`（`formatElapsed`、`preparationProgressText`、文案）、`RunWorkspace.tsx`、`run-history.css`、`app/features/learn/Value101Learn.tsx`、`app/page.tsx`（`value101Preparations`）。
- 文档：`docs/dev/P0_CONVENTIONS.md` 第 5 节；`docs/dev/P0_FRONTEND_DEVIATIONS.md` 新增 R3-4 节（F-R34-1…4，取代 F-R15-3、F-R22-10 的文案）；截图 `docs/dev/p0-ui-screens/r34-*.jpg`（6 张，约 120 KB）。
- 测试：新增 `tests/test_run_async_start.py`；修改 `tests/test_lock_order.py`、`tests/test_run_quota_accounting.py`、`tests/test_doctoral_run_worker_path.py`、`tests/test_project_revision_migration.py`、`tests/local_api_harness.py`（停止前等待后台准备结束）。前端测试：`run-history-view`、`r2-ui-low-items`、`run-history`、`r2-learn-and-readme`。

## 4 测试

- **新增 `tests/test_run_async_start.py`（9 个，全部通过）：**
  - POST 在 5 s 内返回 202，Run 为 `snapshotting` 加 `preparing`；
  - **首个 Run 冻结期间的并发 clone**：clone 在 3 s 内返回 201；全局锁可在 2 s 内取得；另一个 Study 的启动、冻结、排队都完成，第一个 Run 仍在 `snapshotting`；
  - **进度可见**：`GET /api/runs/<id>`、`/api/runs`、`/api/workspace` 都给出 stage `snapshot`（2/4）、用时和 `in_progress`；结束后四个阶段都有用时，生命周期为 `snapshotting → queued`；
  - **冻结期间崩溃的报告**：快照抛异常时，Run 为 failed，错误码 `GF_RUN_PREPARATION_FAILED`，带错误消息和 `failed_stage = snapshot`，没有启动 worker；后端在准备途中停止时，活的后端的 tick 不处理该 Run，重启后的 reconcile 记为 `GF_RUN_PREPARATION_INTERRUPTED`；
  - 准备中 mark-lost 返回 409；
  - 准备中取消时，Run 为 cancelled（`GF_RUN_CANCELLED_BEFORE_WORKER`），没有启动 worker；
  - preflight 期间 Study 被保存时，返回 409 `GF_RUN_START_STUDY_CHANGED`，不建 Run；
  - 被冻结的数据包上传替换时返回 409 `GF_DATA_PACK_FREEZING`。
- **更新的测试：**
  - 锁顺序断言加入 `EXECUTION_CAPTURE_LOCK`（rank 位于 study 与 run_action 之间），并覆盖准备线程（记录器按线程记录）。50 次模块启停与 50 次启动交错的测试仍无死锁、无顺序违例；
  - 配额测试改为 202 加上 Run 上的失败码（`GF_RUN_RESERVATION_LOCK_TIMEOUT`、`VALUE_PREFLIGHT_DISK_SPACE`、`GF_WORKER_SPAWN_FAILED`、`GF_RUN_PREPARATION_FAILED`）；
  - doctoral worker 路径与 Study 迁移测试在桩仍然生效时等待后台准备结束。
- **相关后端测试集**（async_start、lock_order、quota、doctoral worker path、revision migration、module quarantine API、p08、run_supervisor、run_status、delete safety、study_lifecycle、study_lifecycle_api）：137 个，全部 OK。
- **前端：**
  - `tsc -p tsconfig.frontend.json` 无错误；
  - 改动文件的 eslint 问题数与 HEAD 相同（runHistoryView 0、RunWorkspace 2、Value101Learn 3、page 2、types 0），都是原有问题；
  - UI 测试三组：unit 164、render 68、source-contracts 66，全部通过。
- **`scripts/p0_gate.py quick`：** 见第 7 节偏差 1 与第 8 节。
- **实例验证**（scratch API 18970、UI 18971、真实 VALUE 101，改动后的代码）：
  - 首次启动（先删除 scratch 的执行归档）：POST **0.76 s** 返回 202。冻结期间 clone 数据包 0.05 s 返回 201，`GET /api/projects` 0.004 s。轮询显示 `Recording and archiving the execution environment` 和递增的用时；171.2 s 后进入 queued，然后完成。四个阶段的用时为 execution 171.2 s，snapshot、resources、worker 各约 0.02 s 以下；
  - 从界面启动两年 Run：约 1 s 后 Runs 页出现进度句；Learn 页显示同样的进度；在 Runs 页点 `Request safe cancellation`，执行归档结束后 Run 记为 cancelled，没有启动 worker；
  - 两个 Run 同时准备时，第二个等待 `EXECUTION_CAPTURE_LOCK`，190 s 后同样正确取消；
  - 准备中终止 API 进程（按自己记录的 PID）后重启：该 Run 被记为 failed `GF_RUN_PREPARATION_INTERRUPTED`，reconcile 报告中列出该 Run；
  - 截图：`r34-runs-preparing`、`r34-learn-preparing`、`r34-runs-cancel-requested`，各有 1280 和 375 两种宽度。

## 5 采用的决策

- A24-5：启动立即返回，冻结在后台进行并显示进度，其他操作不被阻塞。
- Q4/P0-3：保留崩溃安全和租约接管，补上准备阶段中断的判定。
- Q13：纯代码改动，不触发 Study 修订确认，不修订 golden。
- 规格第 5 节与第 1.3 节；第 0 节第 5 条（说明“意味着什么、下一步去哪”）。

## 6 交给负责人（重写交付文档时使用，只写最终状态）

- **网页上传员与 methodology 编辑员：**
  - 启动 Run 立即返回，Run 马上出现在列表中，状态为 `snapshotting`；
  - Runs 页和 Learn 页显示 “Preparing · step i of 4 …” 与已用时间；
  - 首次在新数据目录启动仍需约 3 分钟归档执行环境，但不再阻塞其他页面和操作；
  - 准备中可以取消；
  - 后端在准备途中停止时，Run 显示为 `Run preparation interrupted`，需要重新启动。
  - 网站上若有 Runs 或 Learn 启动等待的截图或文字，按 `r34-*` 截图更新。
- **API 使用者：** 磁盘或预留不足、spawn 失败不再体现为启动请求的 507/503/500，而是 202 之后 Run 上的 failed 状态，原错误码不变。新错误码：`GF_RUN_START_STUDY_CHANGED`（409）、`GF_DATA_PACK_FREEZING`（409）、`GF_RUN_PREPARING`（409）、`GF_RUN_PREPARATION_FAILED`、`GF_RUN_PREPARATION_INTERRUPTED`、`GF_RUN_CANCELLED_BEFORE_WORKER`（生命周期原因码）。

## 7 偏差

1. **门禁按两个提交共用一次。** 后端提交（`4e24b26`）提交前只跑了相关后端测试集（137 个，OK）。第一次 `p0_gate quick` 在工作区还有未暂存的前端改动时运行，`release_manifest` 和 `backend_ratchet`（`test_repository_manifest_is_current`）因此失败，两者都只是发布清单与工作区不一致。前端提交暂存后，在工作区与暂存区一致的状态下重跑门禁（结果见第 8 节）。这一次门禁覆盖两个提交的最终状态。
2. **状态名仍为 `snapshotting`，没有新增 `preparing` 生命周期状态。** 任务要求返回 “status preparing”。但状态表（`backend/lifecycle/states.py`）、监督器、配额、回收站、模块生命周期和整个前端都以 `snapshotting` 表示“worker 启动前冻结输入”。新增状态需要改动持久化合同和所有判定，风险大且没有收益，所以采取保守做法：生命周期状态保持 `snapshotting`，用 `preparation.state = "preparing"` 表达“准备中”，202 响应里两者都有。
3. **preflight 仍在请求内同步执行（不持全局锁）。** 任务点名的是冻结、快照和归档在后台进行。preflight 是准入判定，拒绝时要返回 400 和报告（界面据此显示 readiness 面板，测试也依赖这个合同），而且实测只需 0.7 s。staged zonal 网络 Study 首次 preflight 可能要做资源校准求解，这时请求会慢，但不阻塞其他操作（校准缓存有自己的文件锁）。
4. **没有按 Study 分锁。** 理由见 2.4：冻结已经完全移出全局锁，冻结期间对同一 Study 和同一数据包的危险操作都已有拒绝路径。再加按 Study 的锁只会增加锁序复杂度。锁顺序文档和断言测试已更新。
5. **取消在阶段边界生效。** 执行环境归档（首次约 3 分钟）进行中时，取消要等这一阶段结束才生效，不会中断归档本身。进度句写明“在 worker 启动前停止”。
6. 界面新增的文案和取消按钮属于规格未覆盖的部分，记为 F-R34-1…4，交设计方复核。

## 8 安全核对

- **提交：** `4e24b26`（后端、锁、测试、锁序文档）和 `1ca9c85`（界面、前端测试、偏差记录、截图）。
- **`scripts/p0_gate.py quick`：** 前端提交暂存后，在工作区与暂存区一致的状态下运行，结果 `status: passed`，14 个步骤全部通过，没有豁免。`backend_ratchet` 没有新增失败，`eslint_ratchet` 基线未变。第一次运行时前端改动尚未暂存，失败原因见第 7 节偏差 1。
- **INSTALLED：**
  - `find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`。该文件 0 字节，mtime 为 2026-10-03 05:41:26，是安装后首次启动时生成的现网文件，以往报告也有记录；
  - `diagnose-value --prefix …` 退出码为 0，输出 “Installation integrity and runtime checks passed.”。中途那行 vinext “Static file stream error … Premature close” 来自它自己的探测请求，与以往相同。
- **进程：** 只按自己记录的 PID 停止进程：scratch API 3231314、3302705、3324748（以及准备中被终止、随后重启的那一次），UI 网关 3315709、3324934。端口 18970、18971 已释放。没有连接 8766 或 8800，没有使用 pkill、killall 或按模式的 kill。
- **其他：** Python 全部经 `vpy` 调用，INTEG 中没有 `__pycache__`。scratch 实例的 `VALUE_DATA_HOME`（含两次重建的执行归档，约 550 MB）已删除，`scratchpad/build/r34` 约 160 KB（脚本、日志）。`dist/` 为截图重建过一次，已被 gitignore。没有 push，没有改 remote。

## 9 遗留问题

- **`current_execution` 没有缓存**（F5-08 建议 2）。第二次以后的启动，执行阶段仍约 20–30 s（在后台，不阻塞）。worker 内的 `verify_run_execution` 还会再完整哈希一遍，约 25 s，属于 `running` 阶段。都可以留到 P1。
- 两个 Run 同时准备时，第二个在执行阶段等待 `EXECUTION_CAPTURE_LOCK`，界面上只显示同一阶段和递增的用时，没有写明“在等另一个 Run 的归档”。
- 被中断的 Run（`GF_RUN_PREPARATION_INTERRUPTED`）没有可恢复的快照，界面仍显示通用的 Resume 按钮，点击后会被 resume 预检拒绝。是否隐藏该按钮，交设计方决定。
- 后端正常停止时不等待准备线程（守护线程），这样的 Run 在下次启动时记为 interrupted。
