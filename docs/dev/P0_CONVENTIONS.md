# P0 施工约定（P0_CONVENTIONS）

本文件是 `fix/review-2026-10-04` 上所有 P0 工作包共用的工程约定。权威顺序：`P0_DECISIONS.md` > 本文件 > `P0_CONSTRUCTION_PLAN.md`。本文件由 X0（M0）建立；第 4–8 节所述的公共骨架由对应工作包实现，实现时必须遵守这里写定的接口，接口如需改动，先改本文件并在提交正文中说明。

## 1 分支、提交与清单

- 所有工作合入 `fix/review-2026-10-04`。各包可在本地 worktree 开话题分支，合回时保持线性、可审查的小提交，不 squash。不 push，不开 PR，不改 remote。
- 一个提交只做一件可审查的事。改变数值的提交单独成提交，纯重构不得与数值改动混在一起。
- 提交正文必须包含下列小节（没有内容的写 `none` / `n/a`），末尾空一行后附 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`：

  ```
  Findings: <审查发现 id，如 P7-24>
  Track: universal | profile-gated
  Correction ids: <修正目录 id，如 p05.interconnector-clock>
  Golden: doctoral 不变 | doctoral accounting 修订(原因) | corrected 已追加修订 | n/a
  Delta: <数值类提交填写，引用 capture.py revise 输出的 by_zone 计数>
  Tests: <新增/运行的测试；棘轮 new/fixed 计数>
  ```

- correction id 必须匹配 `^[a-z0-9]+(\.[a-z0-9-]+)+$`：第一段是不含连字符的包名（`x0`、`p04`、`p05` …），后面各段可含连字符，例如 `p05.interconnector-clock`、`p04.surplus-node-boundary`。
- 凡新增、删除或修改文件的提交，都在同一提交中刷新发布清单：

  ```bash
  git add <本提交的文件>
  python -B scripts/refresh_source_release_manifest.py --index   # 按暂存区内容精确刷新
  git add source-release-manifest.json
  ```

  `--index` 只看暂存区（路径与内容都取自 index），未暂存的其他工作不会混进清单。不进入公开发布的路径写在 `tests/baselines/release-exclusions.txt`（目前为 `docs/dev/`，因为这些施工文档含本机绝对路径）。清单冲突时任选一侧，再重跑刷新脚本（C25）。
- 所有 Python 命令加 `-B`，并设置 `PYTHONDONTWRITEBYTECODE=1`、`PYTHONPYCACHEPREFIX=<scratch>`。源码树中不得出现 `.pyc`。

## 2 门禁、测试棘轮与 golden

| 命令 | 用途 |
|---|---|
| `python -B scripts/p0_gate.py quick` | 每个提交前。约 2–3 分钟（参考机 32 核） |
| `python -B scripts/p0_gate.py full` | 每个工作包合入前 |
| `python -B scripts/p0_gate.py nightly` | 每个里程碑结束 |
| `python -B scripts/run_backend_tests.py [--modules m ...]` | 后端单元测试棘轮（每个模块独立子进程、隔离的 HOME/TMPDIR/VALUE_DATA_HOME） |
| `python -B scripts/run_backend_tests.py --update-baseline` | 修好已知失败后删除基线条目（只删不增） |
| `python -B scripts/golden/capture.py check --tier fast` | golden 快速集合 |
| `python -B scripts/golden/capture.py revise --cases C1 ... --reason ... --correction-id ...` | 在改变数值的同一提交中追加 golden 修订 |
| `python -B scripts/golden/capture.py numeric-report --case D1 --parent HEAD` | doctoral trajectory 重基线的数值差异报告，写入 `tests/golden/reports/<case>-r<k>.json` |
| `python -B scripts/seal_runtime_overlay.py --correction <id>` | 每次改动 `runtime_compat/` 之后登记 |

规则：

- **“门禁通过”的定义。** 只有 `status: passed`（退出码 0）算通过；报告提交时写“p0_gate quick passed”即指此状态。`--skip` 跳过或 `--only` 略去该档的**任一**步骤（不论是否强制，例如 full 档的 `golden_full` 是 D4、C5 的唯一检查），强制步骤（`guard`、`runtime_overlay`、`golden_bookkeeping`、`append_only`、`backend_ratchet`、`golden_full`、`golden_nightly`、`version_ledger`、`release_manifest`，以及 P0-9 S0 之后 full/nightly 档的 `e2e_offline`；未设 `VALUE_E2E_CHROMIUM` 时它自动取 Playwright 缓存中最新的 chromium headless shell，找不到浏览器才自行跳过）自行跳过，或 `--append-base` 不等于 `APPEND_ONLY_BASE`，结果都是 `passed_with_waivers`（`passed: false`，退出码 2），集成者按失败处理；`--skip`/`--only` 只用于本地迭代。只有非强制步骤可以自行跳过，而且必须在报告中记录原因（如“no frontend change since --changed-since”“arrives with X0 S8”）。
- **不得访问现网安装。** 本机现网安装占用 127.0.0.1:8766（API）与 8800（UI）。测试与门禁一律不得连接或监听这两个端口：棘轮在每个测试子进程的 `PYTHONPATH` 首位放入生成的 `sitecustomize.py`（加载 `scripts/value_test_netguard.py`），node 子进程经 `NODE_OPTIONS=--import` 加载 `scripts/value-test-netguard.mjs`；对本机地址（回环、通配、localhost、本机主机名）上这两个端口的 connect/connect_ex/bind/listen 直接拒绝（不触网），连同测试 id 记入日志。只要有一次尝试，棘轮报告 `forbidden_port_attempts` 并失败（不受基线影响、不能进基线），p0_gate 另有 `network_guard` 结果覆盖门禁自身的子进程，golden case 子进程同样失败。凡调用默认指向 8766 的脚本（如 `audit_value_101_release.audit_release`、`doctor.py`、`build_value_101_release_evidence.py`），测试必须传入自己预留并释放的端口，或 patch 掉探测函数。守卫覆盖不到非 Python/node 子进程（curl、PowerShell）以及用 `-I/-S/-E` 或丢弃 `PYTHONPATH` 启动的 Python 子进程，这些仍靠代码审查。
- **不得写入受管安装（INSTALLED）。** INSTALLED 的 `app/`、`runtime/`、`installer/` 只读且必须逐字节不变（`state/`、`logs/` 与现网 supervisor 的 `.supervisor.lock` 属于现网，不在此列）。**每一次**调用 INSTALLED 的 python3.10，包括一次性的 `-c` 小片段、在另一个 shell 调用中执行的命令，都必须同时带 `-B` 与 `PYTHONDONTWRITEBYTECODE=1`（以及指向 scratch 的 `PYTHONPYCACHEPREFIX`），或者一律通过施工 wrapper（`build/bin/vpy`）调用；环境变量的 `export` 不会跨 shell 调用保留，不能依赖。2026-10-05 00:24 的 10 个 stdlib `.pyc`（json、re、enum、sre_*、copyreg）就是一次不带 `-B` 的 `python3.10 -c "import json ..."` 写入的（M0-X0 报告第 9 节）。门禁强制：`guard` 步骤在 app/、runtime/、installer/ 下发现任何比 `install-receipt.json` 新的文件即失败；门禁开始时对这三棵树（含目录）与顶层文件记录路径、类型、大小、mtime 清单，结束时比对（`installed_inventory` 结果），有任何增、删、改即失败。P0 入口脚本（p0_gate、run_backend_tests、golden/capture、golden/run_case、seal_runtime_overlay、refresh_source_release_manifest、check_version_ledger）在导入项目模块之前设置 `sys.dont_write_bytecode = True` 并导出 `PYTHONDONTWRITEBYTECODE=1`，所有 Python 子进程都带 `-B`（`test_p0_gate` 静态与动态检查）。
- **测试棘轮。** 基线 `tests/baselines/known-failures-linux-py310.txt`（首行为环境指纹）。新失败或“已修好仍在基线”都让门禁失败。真回归一律修复，不进基线。环境相关的失败放在 `tests/baselines/quarantine.txt`，必须写 reason/owner/expires；当前里程碑只取自 `tests/baselines/milestone.txt`，每个里程碑结束时由集成者推进（环境变量 `VALUE_P0_MILESTONE` 不再生效；`--milestone` 仅供运行器自身的测试使用，会记入报告的 `milestone_source`，门禁的 `backend_ratchet` 遇到它即失败）。`expires=Mk` 的含义是“有效至 Mk（含）”：当前里程碑晚于 Mk 时该条目让棘轮失败，owner 必须在此之前处理（gate venv 的 6 条为 `M7`，作者须在最后一个里程碑之前决定是否批准离线安装）。`expires=host` 是永久的宿主隔离，只用于本机固有、任何 P0 包都改变不了的原因（作者私有 Windows R0 源码树、Windows 专用工具或被现网安装占用的 8766 端口、磁盘余量）。
- **golden 两族。** `tests/golden/doctoral/*`（冻结）与 `tests/golden/corrected/*`（快照）。digest 按“产物 × 列”保存，分三个区：
  - trajectory：出力、潮流、价格、SoC、装机、投资提案（Q12）。doctoral 族永不修订，唯一例外是 `tests/golden/doctoral_trajectory_rebaselines.json` 中作者批准的 universal correction（P6-24 [Q9/A3]、P6-02/03/04 [A5]、火电净收入 P4-01-thermal [A4]），每个 finding 对每个 case 只能重基线一次。这份名单被钉死：`test_golden_digest` 断言其键集合恰为上述五项，`append_only` 拒绝相对锚点新增 finding（说明文字可改，删除 finding 只会收紧冻结）；今后作者再批准例外，必须由集成者同时修改该测试并移动 `APPEND_ONLY_BASE`。
  - **数值差异报告（Q9/A4/A5 的“差异报告”）**：`revise` 打印的 delta 只有变化的列名与区，没有幅度，不能作为差异报告。每个改变 trajectory 列的 doctoral 修订，必须在同一提交中附 `tests/golden/reports/<case>-r<k>.json`：先 `capture.py revise ... --finding <id>` 追加修订 k（此时修订 k 的报告视为“待补”，`revise` 只核对更早修订的报告，写入修订并提示下一步），再 `capture.py numeric-report --case <case> --parent HEAD`（在 `git archive HEAD` 与工作树上各用 `run_case.py --keep-output` 跑一次该 case，先核对两边分别复现修订 k-1 与 k 的 digest），最后把 golden 文件与报告放进同一提交；报告补齐之前 `capture.py validate` 与门禁 `golden_bookkeeping` 一律失败。报告逐列给出 max abs / max rel 变化、变化值个数、总和与按年合计（覆盖 period_summary 价格与供给、physical_dispatch、storage_state、装机与投资提案等全部变化列），并记录 parent/child 提交与修订 k 的 digest 指纹。（schema v2）SQLite 行按自然键对齐（`golden.NATURAL_KEY_COLUMNS` 中表内存在的列，如 orders 为 year, period, stage, asset_id, side；`order_id` 这类序号会随插入移位，不作键），键在两边都唯一时逐值比较并分别计数两边独有的行；插入/删除/重排了行而又没有唯一键的表（以及列表长度变化的 JSON 列）标为 `not comparable (rows shifted)`，不给逐值幅度，只给总和、按年合计、按 period 汇总（变化的 period 数与最大变化）和按技术/资产合计；键列与标识列（year、period、`*_id`、`*_sha256`、行数等）只计变化个数，不求和、不算幅度。`capture.py validate`（quick 档 `golden_bookkeeping`）对缺失、指纹不符、列集合与 delta 不一致的报告，没有对应修订的孤立报告，以及为 corrected 族或不改变 doctoral trajectory 的修订提交的报告一律报错；两族 golden 测试按 case id 归属同样拦截报告错误。S13 的 `delta_report.py` 落地之前以此为准。
  - accounting：残差、调整项、审计表、成本与收入账、验证与归因报告。可以在 universal correction id 下修订。
  - identity：代码/模块/上下文身份哈希与版本号，任何代码改动都会变，由方法身份与 `VERSION_LEDGER.json` 管理；门禁只报告不拦截。
  - 区的划分写在 `tests/golden/zones.json`（首个匹配生效，未匹配的列默认 trajectory）。修改 zones.json 需在提交正文说明理由，并且**不得把 Q12 列出的 trajectory 列改划到 accounting 或 identity**。这一点由工具强制：每列的区由 golden 文件中**第一次记录它的修订**固定（`golden.pinned_zones`），之后的修订只能把它改得更严（identity < accounting < trajectory），delta 一律按固定的区归类；`capture.py validate` 对任何“改弱”报错。
  - **append-only（quick 档 `append_only` 步骤）**：以 `p0_gate.APPEND_ONLY_BASE`（M0 锚点提交，可用 `--append-base` 覆盖，但改锚点只能由集成者在提交正文中说明）为基准，要求：每个 golden 文件在基准处的修订是当前文件修订的逐条相同前缀（不得改写、删除、截断）；`tests/golden/projects/` 中基准已有的冻结项目逐字节不变；`known-failures-*.txt` 的 id 是基准的子集；`quarantine.txt` 的 id 不增加、`expires` 不后移；ESLint 基线各键计数不增加；`test_golden_*` 的 id 永远不得进入基线或隔离区（`run_backend_tests.py --allow-add` 与 `read_quarantine` 也直接拒绝）。
  - **新增列的分区**：A2 的 stress event（`shortfall_mwh`、stress 标志、`stress_periods`、事件表与年度汇总、能量平衡账中的缺电量 `*unserved*`）与 Q7 的节点边界（`non_vre_spill`、`non_vre_double_counted`、`*balance_boundary*`）已在 zones.json 中预先登记为 accounting。其他纯新增的 accounting 列，必须在新增它的同一提交中写入 zone 规则，`why` 中引用决策 id；未登记的新列默认 trajectory，在 doctoral 族中会被当作未经批准的 trajectory 变化而拒绝。已有的 trajectory 列不可移动（见上条的区固定）。
  - 第 0 号修订只写一次：`capture.py init` 遇到已存在的文件一律拒绝，没有覆盖开关。
- corrected 族任何 trajectory/accounting 变化都必须在同一提交中 `capture.py revise`，写明 correction id、原因；`capture.py validate`（quick 档）检查修订簿记与 delta 的一致性。
- 每个 golden case 在独立子进程中直接调用 `run_project_application`（避开 P7-02 的进程级天气缓存与 R2-05 的磁盘预检）。
- golden case 的输入是冻结的 `tests/golden/projects/<case>.json`（35aadb3 课程模板 + 网络变体 + case 覆盖项一次性解析，已用 35aadb3 代码复核逐字节相同），不再读取可变的 `value_101_study()` 模板；cases.json 中的覆盖项在其上合并。已有快照不可修改，新 case 用 `capture.py freeze-projects` 冻结。
- 快照中的 `maturity_acknowledgements`（如 `module:value-zonal-redispatch-balancing@3.0.0`）不约束 golden：`run_case.build_project` 在运行时按注册表中的当前版本重新推导实验性模块/扩展的确认键（用户同意的语义不适用于 golden 夹具），仍有效的键保持原顺序与取值，过期的键丢弃。因此按 `VERSION_LEDGER` 升级模块版本（如 P0-8 把 zonal 升到 4.0.0）不需要、也不允许修改快照；版本号变化本身只出现在 identity 区。
- **X0 S8 的硬性要求**：引入口径参数的同一提交必须给每个 D case 的 parameters 加上 `"methodology.profile": "doctoral-lineage-0.6.0a2"`，否则 D1–D4 会在默认的 value-corrected 口径下运行。

## 3 运行时内核（runtime_compat）

- `RUNTIME_OVERLAY.json` v2 逐文件登记 `runtime_compat/`：`source_identical`、`mechanical_substitution`、`value_instrumentation`（P0 之前已有的 VALUE 插桩，即 pre-P0 基线）、`declared_runtime_edit`（必须带 correction ids）、`value_added_module`、`data`。
- 改内核的提交顺序：改代码 → `seal_runtime_overlay.py --correction <id>` → 跑门禁 → 提交。`compat/`（保留源）必须逐字节不变。
- 每次运行在入口调用 `ensure_runtime_overlay_sealed()`（进程内缓存），结果写入 provenance 的 `runtime_overlay` 字段。内核文件串行修改顺序见计划 5.1-3。

## 4 HTTP Handler 骨架（C1；由 P0-3 S7 实现，P0-1 S6、P0-2 S6 往里填）

```python
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  self._dispatch(self._route_get)
    def do_POST(self): self._dispatch(self._route_post)
    def do_OPTIONS(self): self._dispatch(self._route_options)

    def _dispatch(self, route):
        self.response_started = False          # 每个请求先复位
        try:
            self._guard()                      # P0-1：Host/Origin/令牌/方法；自带 try，拒绝时直接写 4xx
            route()
        except Exception as exc:               # 唯一的异常出口
            self._send_mapped_error(exc)
```

异常映射（`_send_mapped_error`，按顺序匹配；响应头已发出时只关闭连接，不再写体）：

| 异常 | 状态码 | 说明 |
|---|---|---|
| `ConnectionError`（含 BrokenPipe/Reset） | 不响应 | 关闭连接 |
| `QueryParameterError` | 400 | |
| `UnsupportedMediaType` | 415 | |
| `DataMappingError` / `DataPackCloneError` | 按其 `status` | |
| 带 `code` 的 `ContractError`、`ModuleQuarantinedError` | 查 P0-2 的错误码表 | 体内带 `error_code` |
| `ValueError` | 400 | 体内带 `error_code` |
| `LockTimeout` | 503 | 带 `Retry-After` |
| 其他 | 500 | 不回显内部路径 |

`end_headers` 的覆盖（安全头）由 P0-1 放在同一个类里。新路由一律在 `_route_*` 中分派，不得自己 try/except 后写 500。

**P0-1 S6 实现说明**：`_guard()` 返回 bool，`_dispatch` 写作 `if self._guard(): route()`；拒绝时 `_guard` 自己读完不超过 2 MiB 的请求体并写出 4xx（带 `X-VALUE-Error-Code`），更大的请求体在应答后关闭连接。判定是纯函数 `backend.api_security.evaluate(method, path, headers, *, bound_port, token)`，顺序为 Host（421）→ Origin（403）→ Sec-Fetch-Site（403）→ Content-Length/Transfer-Encoding（400/411）→ `X-VALUE-Session`（403 `GF_SESSION_REQUIRED`/`GF_SESSION_INVALID`；只有不带该头的 `GET /api/health` 和 `OPTIONS` 免令牌）→ POST 的 Content-Type（415）。`UnsupportedMediaType`（`backend.api_security`）按上表映射为 415。`end_headers` 给每个响应（含 `send_error`）追加 nosniff、`X-Frame-Options: DENY`、`CSP default-src 'none'`、`Referrer-Policy`、CORP；`_json` 对带 `error_code` 的 4xx/5xx 加 `X-VALUE-Error-Code`。全部 CORS 已删除。

**P0-3 S7 实现说明（163a9f9）**：映射表实现为模块级函数 `backend.server.map_request_exception(exc) -> (status, body, headers)`，P0-1/P0-2 的条目按表中顺序插入该函数（`UnsupportedMediaType` 在 `QueryParameterError` 之后，带 code 的 `ContractError`/`ModuleQuarantinedError` 在 `LockTimeout` 之前）。另加一条：`UnicodeError`（`ValueError` 子类）映射为 500，因为它表示存储的记录损坏，不是请求错误。`QueryParameterError` 定义在 `backend.server`。`send_response` 被覆盖以设置 `response_started`。

**P0-2 S6 实现说明（d70851f）**：错误码表是 `gridform_core.module_quarantine.ERROR_CODE_STATUS`（`status_for_code(code)`，表外的码为 400）。`map_request_exception` 在 `LockTimeout` 之前匹配带字符串 `code` 的 `ModuleQuarantinedError`、`ContractError`、`ExtensionBundleError`、`ModuleInstallationError` 与带码的 `ExecutionArchiveError`，响应体为 `{error, error_code[, quarantine]}`。新包新增的生命周期类错误码在该表登记状态码，不在 handler 里另写 try/except。

## 5 全局锁顺序（C6；P0-2、P0-3 实现，附断言测试）

获取顺序（只能从左往右拿，释放顺序相反）：

```
.backend.lock (进程单例, 文件锁)
  → STUDY_LIFECYCLE_LOCK (server.py, RLock)
    → RUN_ACTION_LOCKS[run_id]
      → MODULE_LIFECYCLE_LOCK
        → <runs>/.reservation.lock (run_quota._reservation_lock, 文件锁)
          → <run>/status.lock (status 写入 API 内部)
```

- 持有 `MODULE_LIFECYCLE_LOCK` 时不得再申请 `STUDY_LIFECYCLE_LOCK`。
- start-run 在拿预留锁之前取好缓存的模块注册表，不在持锁期间扫描磁盘上的模块。
- `REPLAY_EXPORT_JOBS_LOCK` 是叶子锁：持有它时不得申请上表任何锁。
- 断言测试（由先落地的 P0-2/P0-3 提交新增，放在 `tests/test_lock_order.py`）：两个线程交叉执行“启停模块”和“启动 Run”各 50 次，`join(timeout=30)` 不超时；并对 `acquire` 打桩记录顺序，断言符合上表。
- **P0-2 实现说明**：`MODULE_LIFECYCLE_LOCK` 定义在 `gridform_core/module_quarantine.py`（进程内唯一的 RLock）。模块/扩展的安装、启停库函数自己持有它；server 的生命周期端点在锁内执行“库函数 + 目录刷新”；`gridform_core.catalog.get_catalog_snapshot` 也用这把锁（不另设目录锁，避免 ABBA）。启动 Run 只读取 server 的缓存全局 `MODULE_REGISTRY`，不申请这把锁。`test_lock_order.test_module_lifecycle_and_run_starts_interleave_in_order` 覆盖 50×50 交错。

## 6 后端 HTTP 测试夹具（C14；P0-1 S2 实现）

```python
from tests.local_api_harness import start_local_api

with start_local_api(data_home=tmp) as (httpd, origin, token):
    # origin = "http://127.0.0.1:<随机端口>"；token 为本次会话令牌
    # 安装一个只补 Host/Origin/令牌头的 urllib opener，退出上下文后恢复原 opener
    ...
```

- 端口一律 bind 0；不得使用 8766/8800（棘轮的网络守卫强制执行，见第 2 节）；`VALUE_DATA_HOME` 必须是测试自己的临时目录，不触碰默认用户目录。
- 新写的 HTTP 测试不得直接 `ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)`；`p0_gate quick` 的 `http_harness` 步骤对自分支点以来新增的测试文件做静态检查。
- **P0-3 S7 已提交最小实现**（`tests/local_api_harness.py`）：patch `backend.server` 的全部 state 根目录与 `SUPERVISOR`，构造 data workbench，bind 0，安装只补 `Origin` 头（以及传入的 `token`）的 opener，返回 `(httpd, origin, token)`；P0-1 S2 在此文件上加入会话令牌，不另起一套。
- **P0-1 S2 实现说明**：`start_local_api` 经 `make_api_server` 建服务并生成会话令牌，把会话文件发布到 `data_home/runtime/`（`backend.api_session.authorized_headers(data_home, port)` 可用），opener 只为本服务补 `X-VALUE-Session`，**不再补 `Origin`**（S6 起后端拒绝任何 Origin）。需要自行选择 state 根的旧测试用 `start_local_api(data_home=..., patch_state_roots=False)` 与 `start()`/`stop()`；此时不发布会话文件、不挂 data workbench。直接测守卫的测试用 `http.client` 原样发头（参见 `tests/test_local_api_boundary.py`），不要依赖全局 opener。

## 7 status.json 写入 API（C5；P0-3 S1–S2 实现）

```python
create_status(run_dir, payload) -> dict                      # 仅新建，已存在则报错
update_status(run_dir, *, mutate: Callable[[dict], None]) -> dict
record_run_failure(...)    # 签名保持不变
record_run_cancelled(...)  # 签名保持不变
```

- `update_status` 在 `status.lock` 内读—改—原子写（tmp + replace），`mutate` 原地修改字典；不得整体覆盖 status.json。
- 写入方（`model_runner.py`、`application.py`、`server.py`）全部迁到这两个函数；其他包新增的字段（P0-4 验证、P0-2 降级原因、P0-9 证据、X0 口径、P0-6 stress 汇总）通过 `mutate` 或 final patch 透传。
- GET 请求只读，不写 status。
- **P0-3 S1–S2 实现说明**（`backend/lifecycle/run_status.py`）：`update_status(run_dir, *, mutate=None, transition=None, reason_code=None, details=None, writer=None, legacy_replace=False, merge_unknown=False, repair=False)`。状态迁移只经 `transition`（必须带 `reason_code`，追加连续 `lifecycle_history`）；`mutate` 改 `status`/`lifecycle_history` 一律抛 `LifecycleError`。`writer="worker"` 在 Run 已非活动态时只写根目录 `late-worker-*.json` 并抛 `LateWriteRejected`；`writer="server"` 在活动态且 `worker.lock` 被持有时抛 `LeaseHeldError`。遗留态 `unknown` 只能由 `record_*`（`legacy_replace=True`）替换；application 的恢复证据用 `merge_unknown=True`。取消只写 `cancel-request.json`，呈现层显示 `cancel_requested`（`persisted_status` 保留磁盘状态）。

## 8 worker 解释器参数（C4/C31；P0-3 S9 实现）

`backend/lifecycle/python_argv.py`：

```python
def isolated_python_argv(python: str, prefix: Path) -> list[str]:
    return [python, "-B", "-s", "-X", f"pycache_prefix={prefix}"]   # prefix 每次新建临时目录

def worker_python_argv(python: str, prefix: Path) -> list[str]:
    return [*isolated_python_argv(python, prefix), "-m", "backend.worker_entry"]
```

- P0-3 的 `_spawn_worker`、P0-2 的子进程探针、`desktop_value.py` / `local_value.py` 启动器都从这里取参数；P0-1 的 `--api-origin` 追加在 helper 输出末尾。
- `clean_environment` 设置 `PYTHONPYCACHEPREFIX`；会话令牌不进入 worker 环境变量。
- 不使用 `-I`（linux-local 依赖 PYTHONPATH）。
- **P0-3 实现说明**：`worker_python_argv(python, prefix, *, match_parent_user_site=False)`。`no_user_site` 属于执行身份（`execution_archive.SEMANTIC_FLAGS`），worker 必须与后端一致，因此 `_spawn_worker`（`run_supervisor.spawn_worker`）传 `match_parent_user_site=True`：后端本身没有 `-s` 时 worker 也不加（受管启动器总是带 `-s` 启动后端）。模块入口为 `-m backend.worker_entry`（`backend/worker_entry.py` 是 `backend/lifecycle/worker_entry.py` 的薄壳）。desktop/linux-local 启动器在 app/ 可导入之前运行，各自内置同契约的 `isolated_python_argv`，由 `tests/test_desktop_bytecode_policy.py` 断言三者一致。

## 9 版本台账

`docs/release/VERSION_LEDGER.json` 记录每个模块版本的每一次升级：`{module_id, from, to, package, correction_ids, reason, requires_user_opt_in}`。合并时以当时的现行版本递增；`requires_user_opt_in=true` 的升级在 Study 迁移中归为 `method_upgrade_required`（需要界面确认，Q13）。`scripts/check_version_ledger.py`（quick 档）检查：台账的最新版本与模块清单一致、版本单调递增。

## 10 口径（methodology profile）约定预告

口径机制由 X0 S8–S9 建立。各包规则集只能通过 `ResolvedMethodology.enabled(correction_id)` 判断开关，不得对口径 id（`doctoral-lineage-0.6.0a2`、`value-corrected`）做字符串比较（C15）。编码 35aadb3 数值的测试统一用 `with_profile("doctoral-lineage-0.6.0a2")` 固定口径。

## 11 前端测试：UI 契约夹具与离线 e2e（P0-9 S0/S2）

- **UI 契约夹具跟随数值重新生成。** `tests/fixtures/ui-contract/` 由 `tests/ui_contract_fixtures.py` 从真实读模型生成，其中 `value-101-day.*` 来自 corrected 族 golden case C3 的真实 Run，`toy-v7`/`toy-v8` 来自账本写入器。凡改变市场数值或读模型输出的提交（P0-4、P0-5b、P0-6、P0-7、P0-8、P0-9 S3 及以后，包括只改字段或键顺序的提交），必须在**同一提交**中运行 `build/bin/vpy tests/ui_contract_fixtures.py --write`（任何 Python 都要带 `-B`），逐项审阅夹具 diff，在提交正文 `Tests:` 中写明“ui-contract fixtures regenerated”。不重新生成时，`tests/test_ui_contract_fixtures.py` 会在 backend_ratchet 中作为新失败出现，报错信息给出同一条命令。
- **合并时不手工合并夹具 JSON。** 两条线都改了夹具时，任取一侧，合并后由集成者在合并结果上重新运行 `--write` 并单独提交（或并入合并提交），再跑 `--check`。夹具总量预算 256 KB（计划写的是 200 KB，提高的理由与待批准状态见 M0-P0-9-S0 报告），生成时间预算 30 s，都由 `--check` 和测试检查。
- **e2e 与 `p0_gate full` 跨 lane 串行。** e2e 服务使用固定端口 18800（UI）与 18766（API）：API 的 CORS 白名单和若干 spec 写死了这两个端口，不能按 lane 改。同一台机器上同一时间只能有一个 e2e 运行（`e2e/run-tests.mjs`、`p0_gate full`/`nightly` 的 `e2e_offline`）。端口被占用时 `run-tests.mjs` 在构建之前就以退出码 1 结束并说明原因；此时等待另一条线结束后重跑，不得结束别人的进程。
- **e2e 不依赖 PATH 上的 node。** `playwright.config.ts` 用运行 Playwright 的同一个 node（`process.execPath`）启动服务；门禁通过 `VALUE_NODE`（施工环境为 `build/bin/vnode`）找到 node。新增的 Playwright 配置不得在 `webServer.command` 中写裸 `node`。
- **离线运行不留产物。** `node e2e/run-tests.mjs --offline` 把 JSON 报告和失败用例的 trace、截图写到临时目录，结束后删除；需要保留时设置 `VALUE_E2E_OUTPUT_DIR=<目录>`。spec 中的截图一律写到 `test.info().outputPath(...)`，不写死 `test-results/`。
