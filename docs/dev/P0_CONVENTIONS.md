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
| `python -B scripts/run_backend_tests.py --pytest` | pytest 风格测试棘轮（单独基线 `known-failures-pytest-linux-py310.txt`） |
| `python -B scripts/golden/capture.py check --tier fast` | golden 快速集合 |
| `python -B scripts/golden/capture.py revise --cases C1 ... --reason ... --correction-id ...` | 在改变数值的同一提交中追加 golden 修订 |
| `python -B scripts/golden/capture.py numeric-report --case D1 --parent HEAD` | doctoral trajectory 重基线的数值差异报告，写入 `tests/golden/reports/<case>-r<k>.json` |
| `python -B scripts/seal_runtime_overlay.py --correction <id>` | 每次改动 `runtime_compat/` 之后登记 |

规则：

- **“门禁通过”的定义。** 只有 `status: passed`（退出码 0）算通过；报告提交时写“p0_gate quick passed”即指此状态。`--skip` 跳过或 `--only` 略去该档的**任一**步骤（不论是否强制，例如 full 档的 `golden_full` 是 D4、C5 的唯一检查），强制步骤（`guard`、`runtime_overlay`、`golden_bookkeeping`、`append_only`、`backend_ratchet`、`golden_full`、`golden_nightly`、`version_ledger`、`release_manifest`，以及 P0-9 S0 之后 full/nightly 档的 `e2e_offline`；未设 `VALUE_E2E_CHROMIUM` 时它自动取 Playwright 缓存中最新的 chromium headless shell，找不到浏览器才自行跳过）自行跳过，或 `--append-base` 不等于 `APPEND_ONLY_BASE`，结果都是 `passed_with_waivers`（`passed: false`，退出码 2），集成者按失败处理；`--skip`/`--only` 只用于本地迭代。只有非强制步骤可以自行跳过，而且必须在报告中记录原因（如“no frontend change since --changed-since”“arrives with X0 S8”）。
- **不得访问现网安装。** 本机现网安装占用 127.0.0.1:8766（API）与 8800（UI）。测试与门禁一律不得连接或监听这两个端口：棘轮在每个测试子进程的 `PYTHONPATH` 首位放入生成的 `sitecustomize.py`（加载 `scripts/value_test_netguard.py`），node 子进程经 `NODE_OPTIONS=--import` 加载 `scripts/value-test-netguard.mjs`；对本机地址（回环、通配、localhost、本机主机名）上这两个端口的 connect/connect_ex/bind/listen 直接拒绝（不触网），连同测试 id 记入日志。只要有一次尝试，棘轮报告 `forbidden_port_attempts` 并失败（不受基线影响、不能进基线），p0_gate 另有 `network_guard` 结果覆盖门禁自身的子进程，golden case 子进程同样失败。凡调用默认指向 8766 的脚本（如 `audit_value_101_release.audit_release`、`doctor.py`、`build_value_101_release_evidence.py`），测试必须传入自己预留并释放的端口，或 patch 掉探测函数。守卫覆盖不到非 Python/node 子进程（curl、PowerShell）以及用 `-I/-S/-E` 或丢弃 `PYTHONPATH` 启动的 Python 子进程，这些仍靠代码审查。
- **不得写入受管安装（INSTALLED）。** INSTALLED 的 `app/`、`runtime/`、`installer/` 只读且必须逐字节不变（`state/`、`logs/` 与现网 supervisor 的 `.supervisor.lock` 属于现网，不在此列）。**每一次**调用 INSTALLED 的 python3.10，包括一次性的 `-c` 小片段、在另一个 shell 调用中执行的命令，都必须同时带 `-B` 与 `PYTHONDONTWRITEBYTECODE=1`（以及指向 scratch 的 `PYTHONPYCACHEPREFIX`），或者一律通过施工 wrapper（`build/bin/vpy`）调用；环境变量的 `export` 不会跨 shell 调用保留，不能依赖。2026-10-05 00:24 的 10 个 stdlib `.pyc`（json、re、enum、sre_*、copyreg）就是一次不带 `-B` 的 `python3.10 -c "import json ..."` 写入的（M0-X0 报告第 9 节）。门禁强制：`guard` 步骤在 app/、runtime/、installer/ 下发现任何比 `install-receipt.json` 新的文件即失败；门禁开始时对这三棵树（含目录）与顶层文件记录路径、类型、大小、mtime 清单，结束时比对（`installed_inventory` 结果），有任何增、删、改即失败。P0 入口脚本（p0_gate、run_backend_tests、golden/capture、golden/run_case、seal_runtime_overlay、refresh_source_release_manifest、check_version_ledger）在导入项目模块之前设置 `sys.dont_write_bytecode = True` 并导出 `PYTHONDONTWRITEBYTECODE=1`，所有 Python 子进程都带 `-B`（`test_p0_gate` 静态与动态检查）。
- **测试环境（F4）。** 作者已批准 pytest 与 pypdf。规范测试环境是 gate venv：以 INSTALLED 的 Python 3.10.18 为只读基础的 `--system-site-packages` 叠加 venv，只额外装 `requirements/value-test-py310.lock` 中的精确版本（pytest 8.4.2、pypdf 6.1.1 及其依赖）。用环境变量 `VALUE_GATE_VENV=<venv>` 指向它（施工 wrapper `build/bin/vpy` 已导出），`p0_gate` 与 `run_backend_tests` 的 `--python` 默认取 `<venv>/bin/python`；quick 档的强制步骤 `test_environment` 在版本不符时失败，full 档的 `pytest_ratchet` 也是强制步骤，pytest 不可导入即失败。基线指纹描述的是测试解释器（`--python`），不是编排进程。
- **测试棘轮。** 基线 `tests/baselines/known-failures-linux-py310.txt`（首行为环境指纹）。新失败或“已修好仍在基线”都让门禁失败。真回归一律修复，不进基线。环境相关的失败放在 `tests/baselines/quarantine.txt`，必须写 reason/owner/expires；当前里程碑只取自 `tests/baselines/milestone.txt`，每个里程碑结束时由集成者推进（环境变量 `VALUE_P0_MILESTONE` 不再生效；`--milestone` 仅供运行器自身的测试使用，会记入报告的 `milestone_source`，门禁的 `backend_ratchet` 遇到它即失败）。`expires=Mk` 的含义是“有效至 Mk（含）”：当前里程碑晚于 Mk 时该条目让棘轮失败，owner 必须在此之前处理（原先因缺 pytest/pypdf 而设的 6 条 gate venv 条目已在 F4 删除）。`expires=host` 是永久的宿主隔离，只用于本机固有、任何 P0 包都改变不了的原因（作者私有 Windows R0 源码树、Windows 专用工具或被现网安装占用的 8766 端口、磁盘余量）。
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
- 快照中的 `solver_contract` 同理（P0-8 S4 起）：历史求解合同（v2、v3）只能读取，执行时一律报 `GF_SOLVER_CONTRACT_UPGRADE_REQUIRED`。`run_case.derived_solver_contract` 只在快照记录的是**当代内置默认值**（`is_builtin_default=true`）时，于运行时换成当前内置默认合同（v4）；自定义合同不改写，照常失败。由此带来的数值变化必须在同一提交中以 correction id 追加 golden 修订（C8 的 `p08.zonal-solver-v4`）。
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
- **P0-2 实现说明**：`MODULE_LIFECYCLE_LOCK` 定义在 `gridform_core/module_quarantine.py`（进程内唯一的 RLock）。模块/扩展的安装、启停库函数自己持有它；server 的生命周期端点在锁内执行“库函数 + 目录刷新”；`gridform_core.catalog.get_catalog_snapshot` 也用这把锁（不另设目录锁，避免 ABBA）。启动 Run 只读取 server 的缓存全局 `MODULE_REGISTRY`，不申请这把锁；start-run 与 resume 在入口处把它一次绑定为局部变量 `registry` 并全程使用（评审后补，`test_lock_order.test_one_run_admission_uses_one_registry`），一次准入中途完成的生命周期变更不会换掉注册表。`test_lock_order.test_module_lifecycle_and_run_starts_interleave_in_order` 覆盖 50×50 交错。

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

## 10 口径（methodology profile）约定（X0 S8–S11 已实现）

- **目录**：`gridform_core/data/methodology/profiles.json`（两个口径：默认 `value-corrected`、冻结 `doctoral-lineage-0.6.0a2`）与 `corrections/<pkg>.json`（每包只改自己的文件，文件名即包名）。加载与校验在 `gridform_core/methodology.py`；`scripts/check_methodology_catalog.py`（门禁 quick 档 `methodology_catalog`）检查目录 schema、参数默认值与允许值是否等于目录、代码中 `.enabled(<id>)` 的 id 是否存在、每条 profile_gated 修正是否至少被代码查询一次、Python 代码中是否出现口径 id 字面量（白名单见脚本）。
- **修正条目字段**：`id`（`^[a-z0-9]+(\.[a-z0-9-]+)+$`，首段为包名）、`package`、`findings`、`track`（universal | profile_gated）、`scope`、`affects`（trajectory/accounting/identity/presentation）、`applies_when`（`modules_any`/`modes_any`/`data_packs_any`/`engines_any`，全部命中才算命中；`{}` 命中所有 Run）、`advisory`（null 或 `{severity, title, summary, affected_metrics}`）、`trigger_fixture`（profile_gated 必填 `{test: ...}`）、`introduced_in`、可选 `deviation_signature`、`description`。
- **开关**：规则集只通过 `ResolvedMethodology.enabled(correction_id)` 判断（未知 id 抛 `UnknownCorrectionError`），不得比较口径 id（C15）。参考路线与测试使用 `methodology.REFERENCE_PROFILE_ID`。运行中（`run_project_application` 与各 PSM.run 内）用 `methodology.current_methodology()` 取当前口径；尚未激活时抛 `MethodologyNotActiveError`。
- **冻结绊线**：`tests/test_methodology_profiles.py` 的 `DOCTORAL_DEFINITION_SHA256` 覆盖 doctoral 的 id、version、gated 集合、白名单、参考预设、发布规则。某包若升级谱系模块的 scientific_version 而 doctoral 行为由 gated 修正保持不变，须在同一提交中把新 scientific_version 追加进 doctoral 的 `supported_modules` 并更新该常量，提交正文说明原因。
- **组合白名单**（C16）：`supported_modules`（模块 id → 允许的 scientific_version）、`supported_extensions`、`supported_data_packs`（id、pack_class、manifest_sha256）、`external_code_policy`。在 Study 解析（`resolve_study_draft`）、预检（`checks.methodology`）、运行入口三处调用同一个 `methodology.selection_combination_violations`；错误码统一为 `VALUE_PROFILE_COMBINATION_UNSUPPORTED`，`sub_reason` 取 module/extension/data_pack/external_code/reference_path。`pack_class` 的判定暂由 `methodology.classify_data_pack` 提供（P0-5 S3 接管并扩展 `KNOWN_PACK_CLASSES`）。doctoral 白名单按 manifest sha（文件字节 sha 或规范 JSON sha）钉住 GBP1 public1、`value-101-baseline-v1` 与 `value-synthetic-contract-pack-v1`；任何重建或改动这三个包 manifest 的提交，都必须在同一提交中把新 sha 追加进 doctoral 的 `supported_data_packs` 并更新 `DOCTORAL_DEFINITION_SHA256`，否则 D1–D4 会被白名单拒绝。冻结口径的每个条目都写明 id（目录解析拒绝 `"*"` id）；`synthetic` 类只来自 `KNOWN_PACK_CLASSES`，不再从自报的 `country: SYNTHETIC` 推断。条目的 `label`、`pin_note` 只用于展示，不进入 `profile_definition_sha256`（定义只取 id、pack_class 与排序后的 sha）。Run 在 `input-snapshot/pack` 上执行，该副本的 manifest 被冻结改写；白名单按冻结时记录并经一致性核验的源 manifest（`snapshot_source_manifest`，`gridform_core/pack_source_identity.py`）认定它，记录缺失或不一致的副本一律拒绝。记录（schema v2）保存源 manifest 文件的原始字节（UTF-8 文本）及其文件 sha 与规范 JSON sha，只按内容核验（文本的 sha 等于文件 sha、解析结果的规范 sha 等于规范 sha，再与冻结副本的 bindings 与顶层字段逐项一致），因此冻结副本与源包给出**同样的两个候选 sha**，按任一 sha 钉住都对 Study 解析、预检和 worker 同样有效；修订迁移的口径选择（`classify_revision_mismatch`/`migrate_project_revision` 的 `whitelist_packs`）由服务端的迁移接口、启动 Run 与预检传入同样的 `pack_entry` 行（含 manifest 文件字节，`server._study_whitelist_packs`），结论一致；未传 `whitelist_packs` 的调用方（Study 派生、研究套件重装，只看分类种类）退回只有规范 sha 的 revision manifest，所以新增钉住仍应同时列出两个 sha（现有钉住都如此）；自报的 sha 从不直接进入候选。Study 解析、预检、运行入口（worker）与恢复审查只调用同一个解析器 `pack_source_identity.resolve_pack_identity`（`methodology.whitelist_manifest`/`manifest_sha256_candidates` 只是它的薄封装），不得另写判定。把 `runs/<id>/input-snapshot/pack` 当作数据包再次冻结时，`_freeze_pack` 保留原记录与 bindings 的变换身份（不再重跑适配器），新副本仍认定为原始源包。开发分支上 21865c1 起写入的 v1 记录（不含源字节，从未发布）不再被核验，按无记录处理。冻结输入恢复（frozen-input recovery）发布的 `recovered-base-<suffix>` 包按**经核验的内容身份**认定：`frozen_recovery_origin.source_qualification` 中的源记录（v2）自洽；恢复包是 base 包；每个 binding 在源包中为 identity 变换，且数据 sha（及字节数）相同；除定位、恢复簿记与历史字段外，binding 字段不变；除恢复改写的字段（`RECOVERY_REWRITTEN_FIELDS` 与 `RECOVERY_QUALIFICATION_FIELDS`：id、名称、时间戳、资格字段）外，顶层字段不变。满足时，恢复包与源包的数据字节相同，除 id、名称、时间戳与资格字段外的 manifest 字段也相同；但 id 本身可能决定模型行为，所以这还不等于“内容相同”。**按包 id 决定模型行为的包**只有一份清单 `pack_source_identity.ID_KEYED_PACK_IDS`（`NUCLEAR_POLICY_PACK_IDS`：GBP1 public1 启用 VALUE-UK 核电机组口径；`DOCTORAL_WEATHER_PACK_IDS`：GBP1 public1 与 `value-uk-1000twh-reproduction` 启用 doctoral 站点天气适配器），`nuclear_policy.applies_to_data_pack` 引用它；`doctoral_weather.py` 的字节属于调度天气身份（改动会让所有带站点天气的 35aadb3 Study 无法重建修订 basis），所以保留自己的字面集合，由 `tests/test_pack_source_identity.py` 断言该集合等于 `DOCTORAL_WEATHER_PACK_IDS`，且其他模块不比较这些 id；源包 id 在这份清单中的恢复包**不认定**为源包（解析结果 `unverified='recovery_id_keyed'`，违规说明含 “model behaviour keys on the pack id”），因为换了 id 的副本不会按源包运行（例如 GBP1 的核电会变回一个聚合资产）。今后任何按包 id 改变行为的代码都必须引用这份清单，并按方法变更处理（修正 id、golden 检查）。不在清单中的源包（如 `value-101-baseline-v1`）认定为源包，因此 doctoral Run 可以恢复为仍用 doctoral 口径的 Study 并照常运行（`test_doctoral_run_worker_path` 断言重跑的 year-results-v2 数值与源 Run 相同，计时字段除外）；恢复包的 `scientific_baseline_eligible=false` 保持不变，恢复不等于科学验证。以下情形不认定：源包 id 在 `ID_KEYED_PACK_IDS` 中、适配器变换的 binding、网络叠加包、网络角色被投影出去的 base 包、只有 v1 记录或没有记录的快照。不钉住包的口径（value-corrected）照常允许恢复，但源包 id 在清单中时，审查报告的 `limitations` 写明恢复包的新 id 会失去按 id 选择的行为（遗留问题，早于 P0）。冻结口径下，这类恢复在 `review_frozen_recovery` 阶段就以 `VALUE_PROFILE_COMBINATION_UNSUPPORTED` 列为阻断原因（报告字段 `methodology_violations`），不会等到发布时才失败。恢复包的字段集合只在 `pack_source_identity` 中定义，`backend/frozen_input_recovery.py` 引用同一组常量；审查与暂存共用 `recovered_manifests` 生成的 manifest。是否允许在 value-corrected 口径下恢复 doctoral Run（需要改口径，`configuration_identity` 目前禁止），待作者决定。`value-uk-1000twh-reproduction` 只在本地导入、manifest 含导入时间戳，无法钉住（`pin_note` 说明原因，待作者提供发布版 manifest 后钉住）。
- **参考预设**（Q3）：`methodology.apply_reference_preset(project, profile_id)` 显式写入 `reference_configuration`；偏离允许运行，记录在 `methodology.reference_deviations`。
- **测试**：编码 35aadb3 数值的测试用 `methodology.with_profile(project, REFERENCE_PROFILE_ID)` 固定口径；直接调用 PSM 的测试用 `methodology.profile_scope(REFERENCE_PROFILE_ID)` 激活。
- **读时展示与 advisory（S10）**：所有读取路径（`present_run`、`build_run_summary`、比较、VALUE 101 结果）只经 `gridform_core.result_advisories.present_scientific_status(run, run_root)`，P0-4 S3 的展示改动只改这个函数，不再碰 `server.py`。状态词汇：passed、failed、not_evaluated、superseded_pre_fix、reproduction_with_declared_deviations、reproduction_conformant。只覆盖正向声明：没有口径记录的 Run（修复前），以及（P0-4 S3 起）任何依据非 v2 验证报告的 Run（不论是否记录了口径；X0 S9 之后、P0-4 S2 之前的 v1 报告同样写死了合同 passed），`scientific_scenario_status`/`scientific_validation_status`/`contract_validation_status` 为 passed 的显示为 `superseded_pre_fix`，原值在 `recorded_validation_statuses`（`recorded_scientific_validation_status` 同步保留）。advisory：每条“本 Run 未应用且 `applies_when` 命中”的修正一条（模块 id 先经 `legacy_module_ids` 归一化），加 `data/methodology/advisories.json` 的通用条目（`VALUE-ADV-2026-10-04-REVIEW`：修复前的 Run，high；`GF_VALIDATION_LEGACY_REPORT`：v1 验证报告，medium）。比较：任一 Run 有 high 及以上 advisory、验证 failed、口径不同或年度结果被 withheld，`attribution_status='needs_review'`，`causal_claim_allowed=false`。
- **结果发布（Q14）**：口径的 `result_publication.rule` 为 `raw_invariants_must_pass`（doctoral）时，只有原始不变量全部通过才在结果页发布年度结果，否则 `result_publication.status='withheld'`（`present_run` 清空 `results` 并给出 `withheld_result_year_count`；summary 的 `annual` 为空，`planning`、`vre_curtailment_attribution`、`terminal` 为 null，`result_publication.withheld_fields` 列出这四个字段，`comparison_identity` 与 `comparison_eligibility` 保留；比较不出年度差值），Inspect 与导出不受影响。原始不变量的证据只认 v2 scientific-validation 报告（P0-4 S2 起由运行重算写入）：判定由报告中的 gate 状态推出，即 `run_invariant_status`、`energy_balance_status` 与（P0-4 S7 起）`storage_invariant_status`（passed/reproduction_conformant/not_applicable 为通过，failed/reproduction_with_declared_deviations 为不通过）；报告中存的 `raw_invariants.status` 与推出值不一致时视为证据自相矛盾，判 failed（P0-4 S7），bundle 校验器也复算这一项；status.json 中的同名字段只是 model_runner 的副本，单独存在时不被采信（P0-4 S3）。没有 v2 报告的 Run 在读取时由只读 oracle 复核账本，最多得到 failed，否则 not_evaluated，均 withheld。**服务端统一门控**（不依赖前端）：`result_advisories.withheld_annual_result(run_root, resource)` 对 withheld 的 Run 返回 `{schema_version:'value.result-withheld/v1', status:'withheld', resource, reason_code, error_code, error, available_in:['inspect','export'], result_publication}`；`/api/runs/<id>/market/vre-summary`、`/planning/summary`、`/domains/network/summary`、`/domains/expansion/summary`、`/network-redispatch/annual` 以 HTTP 409 返回这个体（现有页面的 `getJson` 会把 `error` 显示在错误框里，不会渲染年度数）；`/results/vre-curtailment?resolution=annual` 按结果查询自己的状态词汇返回 200、`status:'withheld'`、`items:[]`；`value_101_results._row` 对 withheld 的 Run 不出 `teaching_window_*` 合计（`totals_withheld:true`），比较被拒。半小时与日/周时间线（`market/dispatch`、`market/vre-timeline`、`resolution=half_hour`）、Inspect、provenance 与导出保持可用。完整清单见 `result_advisories.WITHHELD_ANNUAL_RESOURCES`；新增任何年度结果数据源都必须走这个函数。`planning/projects`、`planning/events`、`domains/expansion/events` 等逐项目、逐事件、逐时段的账本属于 Inspect 层，**有意不门控**（清单见 `result_advisories.INSPECT_LEVEL_UNGATED_RESOURCES`）；结果页若要把它们汇总成年度数，必须改用已门控的资源。
- **验证门控（P0-4 S7，附表 P0-4 Q5，决策 A2）**：run 不变量、能量平衡与储能吞吐不变量（P0-6 S8 之后）三项是 gate，severity 记为 `gate`。能量平衡的 gate 是 A2 能量平衡账：缺口记为缺电量（unserved），`closing = raw − 记录的 blackout + 缺口`，只要 closing 在容差内就闭合，所以单纯的缺电只是 stress event，不判 failed；原始边界残差的判定保留为证据（`energy_balance.raw_boundary_status`）。没有可评估边界的旧账本沿用 oracle 的包络判定（永不 passed）。储能三项（额定功率、同期不同时充放、0≤SoC≤E）加审计恒等式取自 `storage_energy_audit` 与 `storage_state`；没有储能行为 `not_applicable`，有储能但无审计为 `not_evaluated`。策略由 Run 的口径决定（`declared_deviations.gate_policy`）：非冻结口径为 `production`，任一 gate failed 则 `scientific_validation_status=failed`、`annual_economics_eligible=false`（model_runner 的 `publication_blocked.reason_code=GF_VALIDATION_GATE_FAILED`）；冻结口径为 `declared_deviations`，gate 失败时只有每个失败时段或行都符合 `data/methodology/declared_deviations.json` 中本口径声明的签名（`energy_balance_oracle.match_declared_deviations`）才记为 `reproduction_with_declared_deviations`，否则 failed，通过记为 `reproduction_conformant`；run 不变量从不按偏差解释。doctoral 的年度结果仍按 Q14 在读取时决定是否发布（带已声明偏差即 withheld），结果本身照常写入，供 Inspect 与导出。新增 gate 检查或偏差签名时，同时更新 `ENERGY_BALANCE_GATE_CHECKS`/`STORAGE_GATE_CHECKS`、目录与 `tests/test_p04_validation_gate.py`。
- **Study 修订迁移（S11，Q13）**：修订身份（`canonical_project_payload`）自 S11 起包含所选口径的 identity（profile_id、version、definition 与 applied-corrections 哈希），因此口径目录或默认口径的变化会让已保存 Study 不再匹配，由 `gridform_core.revision_migration.classify_revision_mismatch` 分类，绝不静默重认身份。每个修订文件写入 `fingerprint_basis`（payload 与 applied_correction_ids）和 `revision_reason`（user-save、code-identity-upgrade、environment-reidentify、method-upgrade-confirmed、data-change-confirmed、basis-reestablished-confirmed）；四处簿记字段列表与 `ALLOWED_DRAFT_FIELDS` 已加入这两个字段。分类：`code_identity_upgrade`（台账中 `requires_user_opt_in=false` 的升版、只影响 identity/presentation 的修正）与 `environment_reidentify`（调度天气适配身份）在启动 Run 时自动追加修订，预检只报警告 `GF_PREFLIGHT_REVISION_REIDENTIFY`；`method_upgrade_required`（opt-in 升版、contract 变化、口径首次写入或变化、改变数值的修正，`GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED`；solver contract 为 `GF_SOLVER_CONTRACT_UPGRADE_REQUIRED`）、`data_changed`（同 id 数据包内容变化，`GF_PREFLIGHT_DATA_CHANGED`）、`unverifiable`（无 basis 且无法用 35aadb3 版本重建，`GF_PREFLIGHT_PROJECT_REVISION`）须用户确认；`content_changed`（Study 自身字段被改而未保存，`GF_PREFLIGHT_PROJECT_REVISION`）不能迁移，只能正常保存。S11 之前保存的修订按台账 `baseline_version` 且不含口径重建 basis。接口：`GET /api/projects/<id>/revision-migration`（只读分类，含 `diff_sha256`）；`POST` 同一路径带 `{"diff_sha256": ...}` 确认迁移（首次写入时把默认口径显式写进 Study，过期 solver contract 换成安装版默认值）。修订前 Study 首次写入口径时，分类带 `profile_choices`（各口径是否 `supported`、是否 `matches_reference_preset`），符合某个冻结口径参考预设的 Study 在方法行带 `hint:'matches_reference_preset'`；GET 加 `?profile_id=` 预览所选口径的分类，POST 带 `profile_id` 确认，`selected_profile_id` 计入 `diff_sha256`（换口径须重新取 diff）；对非首次写入的分类给 `profile_id` 返回 `GF_REVISION_MIGRATION_PROFILE_NOT_APPLICABLE`，未知或不支持的口径返回 `VALUE_PROFILE_UNKNOWN`/`VALUE_PROFILE_COMBINATION_UNSUPPORTED`（均为 409）；启动 Run 遇到需确认的分类返回 409 和 `revision_migration`。新增升版的包必须在台账中正确填写 `requires_user_opt_in`，它决定 Study 是否需要确认。台账在运行时从 `docs/release/VERSION_LEDGER.json` 读取，必须随每个发布树发货：`build_linux_frontend_release.py` 的 `REQUIRED_MEMBERS` 缺它即拒绝打包，`test_source_release_tree.test_version_ledger_ships_with_every_release_tree` 检查源码发布清单、Linux 与 Windows pilot 的选择规则；缺失时分类的 `ledger_status` 为 unavailable。
- **API**：`GET /api/methodology/profiles` 返回目录；`resolve-draft` 的响应带 `methodology` 块与各模块选项的 `methodology_supported`/`methodology_reason`。

## 11 前端测试：UI 契约夹具与离线 e2e（P0-9 S0/S2）

- **UI 契约夹具跟随数值重新生成。** `tests/fixtures/ui-contract/` 由 `tests/ui_contract_fixtures.py` 从真实读模型生成，其中 `value-101-day.*` 来自 corrected 族 golden case C3 的真实 Run，`toy-v7`/`toy-v8` 来自账本写入器。凡改变市场数值或读模型输出的提交（P0-4、P0-5b、P0-6、P0-7、P0-8、P0-9 S3 及以后，包括只改字段或键顺序的提交），必须在**同一提交**中运行 `build/bin/vpy tests/ui_contract_fixtures.py --write`（任何 Python 都要带 `-B`），逐项审阅夹具 diff，在提交正文 `Tests:` 中写明“ui-contract fixtures regenerated”。不重新生成时，`tests/test_ui_contract_fixtures.py` 会在 backend_ratchet 中作为新失败出现，报错信息给出同一条命令。
- **合并时不手工合并夹具 JSON。** 两条线都改了夹具时，任取一侧，合并后由集成者在合并结果上重新运行 `--write` 并单独提交（或并入合并提交），再跑 `--check`。夹具总量预算 256 KB（计划写的是 200 KB，提高的理由与待批准状态见 M0-P0-9-S0 报告），生成时间预算 30 s，都由 `--check` 和测试检查。
- **e2e 与 `p0_gate full` 跨 lane 串行。** e2e 服务使用固定端口 18800（UI）与 18766（API）：API 的 CORS 白名单和若干 spec 写死了这两个端口，不能按 lane 改。同一台机器上同一时间只能有一个 e2e 运行（`e2e/run-tests.mjs`、`p0_gate full`/`nightly` 的 `e2e_offline`）。端口被占用时 `run-tests.mjs` 在构建之前就以退出码 1 结束并说明原因；此时等待另一条线结束后重跑，不得结束别人的进程。
- **e2e 不依赖 PATH 上的 node。** `playwright.config.ts` 用运行 Playwright 的同一个 node（`process.execPath`）启动服务；门禁通过 `VALUE_NODE`（施工环境为 `build/bin/vnode`）找到 node。新增的 Playwright 配置不得在 `webServer.command` 中写裸 `node`。
- **离线运行不留产物。** `node e2e/run-tests.mjs --offline` 把 JSON 报告和失败用例的 trace、截图写到临时目录，结束后删除；需要保留时设置 `VALUE_E2E_OUTPUT_DIR=<目录>`。spec 中的截图一律写到 `test.info().outputPath(...)`，不写死 `test-results/`。
