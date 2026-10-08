# P0 前端实现与设计规格的偏差记录（P0_FRONTEND_DEVIATIONS）

依据：`docs/dev/P0_FRONTEND_DESIGN_SPEC.md`。每条写明规格条目、实际实现、原因与是否需要设计方确认。没有偏差的条目不列出。

## P0-1（第 8 节：安全相关的前端改动）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-P01-1 | 网关返回 403 或 421（令牌缺失、Host 错误）时显示整页说明 | 触发条件为：421；403 且错误码属于网关/会话类（`GF_GATEWAY_CROSS_SITE`、`GF_GATEWAY_ORIGIN_REJECTED`、`GF_BROWSER_ORIGIN_REJECTED`、`GF_SESSION_*`）；**以及 502 且错误码为 `GF_GATEWAY_SESSION_MISMATCH`**（网关读到的令牌被 API 拒绝）。502 `GF_GATEWAY_SESSION_UNAVAILABLE`（会话文件不存在）**不**触发整页：它通常表示引擎还在启动或已停止，侧栏显示原有的 “Model service offline” 与 Retry；`GF_GATEWAY_UPSTREAM_UNAVAILABLE` 与业务 403 同样不触发 | 网关设计（计划 4.1 方案第 1 点）把“令牌不匹配”表达为 502 `GF_GATEWAY_SESSION_MISMATCH`，不是 403；若只按 403 判断，规格想覆盖的“未经启动器打开”场景显示不出来。会话文件缺失若也触发整页，后端启动稍慢时页面会卡在整页说明（e2e happy-path 实测），因此排除。判定集中在 `app/features/shared/api.ts` 的 `isLauncherAccessFailure` | 是（触发集合） |
| F-P01-2 | 整页说明由网页显示 | Host 错误（421）时浏览器根本拿不到 VALUE 页面，因此网关对**页面请求**的 421 直接返回同文案的静态 HTML（标题与正文逐字相同，内联样式，CSP `default-src 'none'`）；对 `/api` 请求仍返回 JSON。页面内的整页组件 `OpenFromLauncher` 用于页面已加载、但 API 被拒的情形 | 421 发生在页面加载之前，React 组件无法渲染 | 否（文案与规格一致） |
| F-P01-3 | 整页说明仅在初次加载时出现？（规格未写明） | 只在 `refresh()`（加载/重试 workspace）收到上述响应时切换为整页；其他请求（如单个 Run 详情）不切换 | 避免一次偶发失败把整个工作台替换掉；workspace 是每个视图的前提 | 是 |

### 设计方裁决（2026-10-05，Claude）

- **F-P01-1 批准。** 整页「Open VALUE from its launcher」的触发集合按实现执行：
  - 421；
  - 403 且错误码为网关/会话类；
  - 502 `GF_GATEWAY_SESSION_MISMATCH`。

  502 `GF_GATEWAY_SESSION_UNAVAILABLE` 和 `GF_GATEWAY_UPSTREAM_UNAVAILABLE` 不触发整页，沿用侧栏的 offline/Retry，这与规格第 5 节「降级不整页」的原则一致。
- **F-P01-2 批准**（文案一致，静态 HTML 合理）。
- **F-P01-3 批准。** 只在 workspace 的 `refresh()` 中切换到整页；单个请求失败按各视图的错误状态处理，不替换整个工作台。

## X0 S10b（Q14 年度结果门控；交给 m2-ui 线）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-X0-1 | 4.2 只给年度卡片加 `Withheld` pill；4.5 VRE 页、4.6 网络页没有 Q14 门控 | 门控在服务端：withheld 的 Run 请求 `market/vre-summary`、`planning/summary`、`domains/network/summary`、`domains/expansion/summary`、`network-redispatch/annual` 得到 409 `{status:'withheld', reason_code, error, available_in}`；`results/vre-curtailment?resolution=annual` 得到 200 `status:'withheld'`、`items:[]`。现有页面因此显示错误框（文案为 `error`），不显示年度数 | 只按规格在卡片上门控，VRE 页与网络页仍会显示 doctoral 年度数，违反 Q14（复审意见）。m2-ui 线应在这些页面识别 `status==='withheld'`（或 409 体中的 `status`），改用 4.2 的 `Withheld` Callout（文案与 4.2 相同，附 Inspect/导出入口），而不是错误框 | 是（4.5/4.6 的 Withheld 展示需设计方补充） |
| F-X0-2 | 7 迁移对话框只列 diff 并保存为新修订；修订前的 Study 首次写入口径时没有选择，一律写入默认口径 | 后端为“修订前 Study 首次写入口径”的分类返回 `profile_choices`（每个口径的 `label`、`default`、`supported`、`unsupported_reasons`、`matches_reference_preset`），方法行带 `hint:'matches_reference_preset'` 与 `matches_reference_preset:[口径 id]`；`GET /api/projects/<id>/revision-migration?profile_id=<id>` 返回该选择下的分类与 `diff_sha256`（含 `selected_profile_id`），`POST` 同一路径带 `{diff_sha256, profile_id}` 确认。不带 `profile_id` 时行为不变（写入默认口径） | 复审意见：golden D1 这类按 doctoral 参考预设配置的论文复现 Study，一次确认就会静默改用 corrected 口径；P0-4..P0-7 的 gated 修正落地后数值会变。m2-ui 线应在方法行带 `hint` 时，在对话框中加一个与 StudyComposer 相同文案的 `Methodology` 单选组（只列 `supported` 的口径，默认选中 `matches_reference_preset` 的口径），切换时重新 GET 取 `diff_sha256` 后再确认 | 是（对话框中的口径选择需设计方补充） |

## P0-8a（第 4.6 节：网络页；M2 lane m2-net）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-P08-1 | 4.6 网络页：可靠性数值用统一格式化（<0.01 MWh 不显示为 0）、运行期 fallback 审计超阈值时顶部 caution Callout `Spatially indicative: {x}% of {tech} capacity fell back to {zone}.` | 本 lane 只交付后端字段与 TS 类型：`known_defects`、`load_shedding_reporting_threshold_mwh`、`numerical_residual_unserved_mwh`（年度简报）、`runtime_fallback_audit`（能力接口，含 `spatially_indicative_technologies` 的 year/technology/fraction/zone，足以拼出规格文案），`networkRedispatch.ts` 增加对应可选类型。`NetworkRedispatchView.tsx` 未改 | 冲突热点 C11 规定 P0-8 的网络页改动放在 P0-9 S6 之后；`Callout` 与 `format.ts` 由并行的 P0-9 lane 新建，本分支上尚不存在，自行实现会与设计方的组件重复 | 是：集成者在 P0-9 S6 合入后补一个提交，用 `Callout`（caution）与 `formatEnergy` 渲染上述字段 |
| F-P08-2 | 规格未覆盖 SolverSettingsEditor | 历史合同（v2、v3）显示 `Historical {v2 / v3 GBP 1 lock} policy` 徽章；升级说明框里新增一张只读对照表（Setting / Recorded / Current v4），按钮文案改为 `Use current v4 policy`；当前合同徽章改为 `Built-in v4 default settings` / `Custom v4 settings`。只用已有的 `Badge`、`info-box`、`table-scroll` 样式（对照表按应用惯例包在 `.table-scroll` 里，避免全局 `table { min-width: 800px }` 撑破设置面板；评审 M2-P0-8a 指出后补上），没有新增颜色或字号 | P0-8 S5 要求升级前预览差异（Q13 method_upgrade_required）；原文案写死 “£1 policy”，在 v4 下会误导 | 是：文案与表格样式 |

## P0-9 / P0-2 S9 / P0-3 S8（M2-P0-9：第 1、3–6 节）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-P09-1 | 1.2：`formatNumber` 缺失时返回 `null` | `shared/format.ts` 的 `formatNumber` 返回 `null`；保留签名的 `presentation.tsx` 版本对缺失返回状态词 `—`（`VALUE_STATES.missing`） | 规格要求旧签名不变，旧调用方需要字符串；计划 6.9 的测试写的是 `formatNumber(undefined)='—'`，两者在不同层同时满足 | 否 |
| F-P09-2 | 1.2：非零小值显示 `<0.01` / `>-0.01`；`formatMoney(999999.9)` 显示 `£1.00m` | 按规格实现（`formatNumber(-0.001)` 为 `>-0.01`，金额 k/m/bn 段保留 2–3 位小数：`£1.00m`、`£12.346bn`、`£1.234k`）。负数写作 `-£1.234k`，亚便士写作 `<£0.01` | 计划 6.9 的手算表写的是 `formatNumber(-0.001)='0'`、`formatMoney(999999.9)='£1m'`，与规格冲突；按规格（设计方）执行 | 是（计划测试表需同步） |
| F-P09-3 | 3.1：窗口行写 `(UTC)` | 写作 `({timezone} model time)`，取自读模型的 `timezone`（当前为 Europe/London）；网络页事件列表表头为 `Start (model date & time)` | 账本时间戳是固定 365 天日历上的本地模型时间，不是 UTC；标成 UTC 会误导。**已由 F-R43-1 取代**（R4-3 查明模型时钟是 UTC，原依据不成立） | 是 |
| F-P09-4 | 3.1/3.3/4.4：shortfall、stress period、stress band、`stress (supply < demand)` 类型 | 窗口卡显示 `Shortfall: Not recorded`；`shortfall_mwh`/`stress_periods` 字段一到即显示数值与 amber pill，图上画 4px amber 带并加图例；可靠性列表目前只有 `lost load (network)` 一类 | A2 的后端字段**已在 M2 落地**（P0-4 S3：run status、summary 与 replay 窗口的 `shortfall_mwh`/`stress_periods`/`shortfall_basis`；M3 起新 Run 为 exact，M4 P0-4 S7 起 corrected 声明边界上也为 exact）；前端不做减法。旧 Run（没有 surplus routing）的 `shortfall_basis='lower_bound'` 在窗口卡上不加限定词，见 F-P04-1 | 否（展示方式见 F-P04-1） |
| F-P09-5 | 4.2：非 Complete 时不显示年度合计 | 后端给出 coverage 时严格执行；**后端没有给出 coverage（旧后端）时**，合计照常显示，pill 为 `Coverage not recorded`（muted） | 原则 3「不确定就降级」：降级的是标签而不是隐藏数值；同时保持旧 mock 的 e2e 不被整体改写 | 是 |
| F-P09-6 | 4.2：`Withheld` pill（复现口径未通过不变量，Q14） | `coveragePill(…, { withheld: true })` 已就绪，但当前没有后端字段可读，界面不会出现 Withheld | 复现口径的发布判定由 X0/M4 提供字段；不臆造字段名 | 是（需约定字段） |
| F-P09-7 | 4.3：修正口径径流水电兼容资本的 memo 行 | 当 Run 指标中有 `ror_hydro_compatibility_capital_gbp` 时在构成表末尾列出（不计入头条、不画进条形）；当前后端没有该字段 | 该数值属于修正口径（P0-7/X0），字段名先按此约定，需对方实现时采用 | 是（字段名） |
| F-P09-8 | 4.6：运行期 fallback 审计 Callout | 未实现 | 依赖 P0-8 S12 的后端字段，接口未定 | 是（P0-8 交付后补） |
| F-P09-9 | 4.6：P0-8b 后表头改为 `Boundary marginal value (£/MWh)` | 〔M6-P0-8b 已消解〕表头已按规格改为 `Boundary marginal value (£/MWh)`；后端对 P0-8b 之前的账本行给 `null` + `shadow_value_status=not_computed`，界面显示 `Not computed` | — | 否 |
| F-P09-10 | 1.2 / 计划 S1：`RunContextBar.tsx:27`、`Value101Learn.tsx:124` 改用共享格式化 | 未改，列入 `toLocaleString` 白名单 | 两处都是整数周期数，不存在缺失变 0；`RunContextBar` 属 X0 S12（并行 lane 在改），避免冲突 | 否 |
| F-P09-11 | 5：`Mark as lost` 二次确认 | 浏览器 `prompt`，用户须输入精确 run ID（与 Delete 相同），前端只把用户输入的 ID 作为 `confirm_run_id` 发给 API 的确认门；输入不符时不发请求（评审后修改，原实现是确认框 + 自动带上 ID） | 规格只要求二次确认；P0-3 S4 的精确 ID 门不能由前端代填；API 的安静期门仍由后端执行，拒绝时显示错误码 | 否 |
| F-P09-12 | 5：`Backend offline` 在连续失败 3 次后 | 实现如此；第一次失败即显示 `Backend degraded` 与 Retry，轮询 2 s 起翻倍至 30 s。`e2e/happy-path.spec.ts` 的离线断言改为匹配 `Backend (degraded|offline)`（该 spec 需真实服务，本次未运行） | 规格 | 否 |
| F-P09-13 | 9.8：375 px 不引起页面级横向滚动 | 只断言新组件自身不横向溢出（窗口卡、隔离面板）；旧布局（252 px 侧栏网格）在 375 px 的页面级溢出不在本轮 | 做法一不改旧元素样式 | 是 |
| F-P09-14 | 6：Disable 确认 | 使用浏览器确认框（文案与规格逐字一致），未用 `<dialog>` | 规格第 6 节未指定对话框形式（`<dialog>` 是第 7 节迁移确认的要求） | 否 |
| F-P09-15 | 10：截图用 PNG | 用 JPEG（质量 55，整页），共 14 张约 2.7 MB，放在 `docs/dev/p0-ui-screens/` | 控制仓库体积；来源是 scratch 实例（端口 18966/18967）上真实的 VALUE 101 day Run | 否 |

### 设计方裁决：M2 界面审查遗留的小问题（2026-10-05，Claude）——在 M7「P0-9 收口」中实现

1. **单位成本标签**：按 `system_cost_definition_id` 选择标签。
   - CEM 账本口径：`£X/MWh served`；
   - 遗留口径（`total_system_cost / total_energy_generated`）：`£X/MWh generated`；
   - 口径未知：`£X/MWh (basis not recorded)`。
2. **「Withheld」只用于 Q14**（论文复现口径未通过验证而按规则不发布）。其余情形各用各的词：
   - 部分年份：`Partial year · {coverage}%`（琥珀色）；
   - 进行中：`Running`（蓝色）；
   - 已取消或已停止：`Stopped · {coverage}%`（琥珀色）。

   规格 1.1 的词表据此新增 `stopped`。
3. **已归档、原状态为 cancelled、缺少声明年份的 Run**：判为 `unavailable`（灰色），reason code 为 `cancelled_before_year_complete`，不判 `invalid`。红框只留给真正自相矛盾的结果。
4. **折线中的孤立数据点**（两侧都缺失，或只有一个桶）：渲染为半径 2.5px 的实心圆点，颜色与该序列一致；不画成零长度折线。只有一个桶的视图，例如 VALUE 101 的日视图，要能看到这个点。
5. **没有事件的事件组**（`affected_periods == 0`）：显示 `No events recorded`。不显示「Peak event 0 MWh」和时间戳。
6. **窗口摘要网格**：1280px 下末行不留空白填充格，可用 `grid-auto-flow: dense`，或让最后一项占满整行。`server.py` 的空行按 PEP 8 修正。

## X0 S12 / P0-9 S11（第 2、7 节：Run 上下文条口径与验证、Study 口径选择与迁移确认；M2b）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-S12-1 | 2.3 规则 1：`energy_balance=failed` **且口径为 corrected** 时显示 danger Callout | 条件为 `failed` 且口径**不是 doctoral**：corrected、修复前（`methodology.status=not_recorded`）、无法解析的口径都显示规则 1；doctoral 的失败由规则 2（withheld）表达 | 修复前的旧 Run（如 Release R2）由读取时 oracle 判为 failed，若严格按 corrected 判断，红色 Callout 不出现，只剩琥珀色的「Produced before…」，弱化了失败（原则 3「不确定就降级，不要美化」）；状态条的 Energy balance 字段在任何口径下都是红色 ● Failed | 是 |
| F-S12-2 | 2.2 只列出 corrected、doctoral、缺失（修复前）三种徽章 | 另有三种降级：后端没有 `methodology` 字段（旧后端）→ `Methodology not recorded`（muted，提示服务未报告）；`methodology.status=unresolved`（记录了本目录无法解析的 id）→ `Methodology not recorded`（muted，不称作修复前）；目录外的已知 id → muted，显示其 label | 原则 3：不猜；`unresolved` 不是修复前的 Run，不能套用 pre-2026-10 文案 | 否 |
| F-S12-3 | 2.3：Contract check、Scientific validation 字段保留原样 | 两字段值为 `superseded_pre_fix` 时显示琥珀色 ● Superseded（悬停给出原记录值）；为 `reproduction_with_declared_deviations` 时显示琥珀色 ● Declared deviations；其余值文字不变 | 验收清单第 4 条：修复前的旧 Run 不得显示绿色 passed；原样显示 `superseded pre fix` 不可读 | 否 |
| F-S12-4 | 2.3 规则 2 动作 `Export ledger` | 打开 Inspect 的 Artifacts 标签（账本与审计包导出所在处），不直接下载 | 前端没有单独的「导出账本」接口；导出入口在 Artifacts 标签与 Runs 页的 `Prepare audit bundle` | 否 |
| F-S12-5 | 2.3 规则 4 动作 `Show stress events` 跳到 4.4 的列表 | 跳到 Market replay（窗口卡已显示 Shortfall 与 stress period，F-P09-4） | 4.4 的 stress event 列表随 M4（A2 的期别字段）落地；届时改为跳到该列表 | 是（M4 后改目标） |
| F-S12-6 | 2.3 规则 3 `View advisories (n)` 点开为列表 | 在同一个 Callout 内展开列表（标题、一句话说明、受影响指标）；Run 列表行只有 `advisory_summary.count`，详情未到时显示 “The advisory details are loading with this Run’s record.” | 不新增弹层；列表行按 `compact_validation_fields` 只带计数 | 否 |
| F-S12-7 | 7：迁移对话框只列 diff | 修订前 Study 首次写入口径（后端返回 `profile_choices`，F-X0-2）时，对话框内加与 StudyComposer 文案相同的 `Methodology` 单选组：只有 `supported` 的口径可选，不可选的附原因；默认选中与 Study 参考预设相符的口径；切换时重新 GET 该口径的 diff，加载完成前「Review and save as new revision」不可点；POST 带 `{diff_sha256, profile_id}` | 回应 F-X0-2（设计方尚未补充该细节）；避免论文复现 Study 一次确认就静默改为 corrected | 是（F-X0-2 的展示） |
| F-S12-8 | 7：Doctoral 选中时「不在白名单内的模块和数据包选项显示为禁用」 | 数据包与扩展按目录（`/api/methodology/profiles`）的白名单 id 预先禁用并附原因；模块按 draft resolution 给每个选项的 `methodology_supported`/`methodology_reason` 禁用；已选中的项不被禁用（以免用户无法看到当前值），由服务端的 draft 校验与预检报错 | 白名单的唯一判定在服务端（C16：一处 whitelist 检查）；前端只预先禁用目录已明确排除的项；pinned 内容哈希检查只在服务端 | 否 |
| F-S12-9 | 7：方法变化的对话框在用户点 Run 或 Preflight 时弹出 | Preflight 报告 `checks.project_revision.classification` 需确认、或启动 Run 被 409 拒绝且带 `revision_migration` 时弹出；声明的修订哈希与当前 Study 不一致（Study 已被换掉）时不弹出 | 只对用户正在操作的那个 Study 修订弹窗 | 否 |
| F-S12-10 | 9.8：375 px 不引起页面级横向滚动 | 新组件（口径徽章、状态字段、Callout、单选组、对话框）自身不横向溢出；截图 `s12-composer-methodology-375.jpg` 中右侧裁切来自旧的 composer 网格布局，与 F-P09-13 相同，不在本轮 | 做法一不改旧元素样式 | 否（同 F-P09-13） |
| F-S12-11 | P0-9 S11：比较页「警示」 | 比较页的 Run 选择列表在每行写出口径徽章文字；比较结果 `attribution_status=needs_review` 时显示 caution Callout `This comparison needs review`，逐条列出 `attribution_review_reasons`（advisory、验证失败、能量平衡失败、withheld、口径不同） | 规格第 2 节没有比较页的线框；按计划 P0-9 S11「比较页警示」的最小实现 | 是（文案） |

## P0-5a S10（CSV 映射声明 EUR；M3）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-P05A-1 | 计划 4.5 S10 列出 `CsvMappingEditor.tsx`（映射界面可声明 EUR、汇率与来源） | 只做了后端：映射目录的价格角色带 `fx_required_for` 与 `requires_fx` 的换算对，预览请求可带 `fx: {eur_per_gbp, fx_basis[, price_year]}`，缺汇率时报 `GF_MAPPING_FX`；界面未改，现有界面选不到 EUR，行为与改动前相同（只能映射 GBP） | 设计规格没有这一处的设计，按约定不即兴实现 | 是（需要设计方补 EUR/汇率输入的界面） |

## P0-4 S7（验证门控与已声明偏差；M4，后端已就绪，前端未改，待设计方裁决）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-P04-1 | 2.3 Stress events、3.1 窗口卡 `Shortfall` | 后端给出 `shortfall_basis`（`exact` 或 `lower_bound`）与 `shortfall_upper_mwh`。状态条的 `stressField` 在 `lower_bound` 时只在悬停提示中说明是下界；Market replay 窗口卡直接显示数值，不加任何限定。新 Run 都是 `exact`，只有 P0-4 S5 之前的旧 Run 是 `lower_bound`（例如 r2：下界 570.5 MWh，上界 1015.5 MWh） | 规格没有区分下界与精确值；按“不确定就降级”的原则，应当在数值前加 `≥` 或显式标注 basis，但这是展示决定，需要设计方确认 | 是（下界显示为 `≥ 570.5 MWh`，还是加 basis 提示） |
| F-P04-2 | 2.3 Energy balance 字段的取值表 | 后端新值 `reproduction_conformant`（doctoral 口径下能量平衡账闭合）落到 `energyBalanceField` 的默认分支，显示为灰色文字 “reproduction conformant” | 规格只给出 `reproduction_with_declared_deviations`（琥珀 Declared deviations），没有 `reproduction_conformant` | 是（建议 teal ● Conformant） |
| F-P04-3 | 2.3 状态条字段 | 新增的 gate `storage_invariant_status`（以及 `storage_invariants`、`validation_gate`、`declared_deviations`）目前不显示。production 口径下储能不变量失败会使 Scientific validation 变为 failed，但状态条上的 Energy balance 仍可能是 Passed | 规格没有储能不变量的字段和 Callout；不臆造 | 是（是否增加 `Storage limits` 字段，或让 Callout 1 覆盖 `validation_gate.status=failed`） |
| F-P04-4 | 2.3 规则 1 只看 `energy_balance=failed` | production 口径的 gate 失败（任一 gate）时，后端把 `scientific_validation_status` 置为 failed、`annual_economics_eligible=false`，`results` 为空并写 `publication_blocked.reason_code=GF_VALIDATION_GATE_FAILED`；前端目前不读 `publication_blocked`，年度结果区只显示没有结果 | 计划 4.4 第 6 点“生产口径 gate 失败阻止年度结果发布”；规格只为 doctoral 的 withheld 写了文案（且文案专指 reproduction run），不能套用 | 是（corrected Run 被门控时的文案） |
| F-P04-5 | 2.3 Callout 4 与决策 A2 | 决策 A2 下，能量平衡 gate 是“缺口记为缺电量”之后的账；单纯的缺电（stress）不再使 corrected Run 的 Energy balance 显示 Failed，只出现 Callout 4（不阻断）。原始边界残差的判定在 `energy_balance.raw_boundary_status` 中，前端没有显示 | 与规格中 Callout 1/4 的分工一致（stress 不阻断）；是否在 Inspect 中展示原始残差，由设计方决定 | 否（如需展示 raw 判定再补） |

### 设计方裁决：F-P04-1…5、F-P09-5…7、F-P05A-1（2026-10-06，Claude）——在 M7「P0-9 收口」中实现

- **F-P04-1：** `shortfall_basis='lower_bound'` 时，状态条和 Market replay 窗口卡都显示 `≥ 570.5 MWh`（数值前加 ≥）。悬停提示为：`Lower bound: this Run predates exact stress accounting (upper bound 1,015.5 MWh)`。`exact` 时不加限定。
- **F-P04-2：** `reproduction_conformant` 显示为 teal `● Conformant`。悬停提示为：`The doctoral reproduction ledger closes. This does not certify the method as physically validated.`
- **F-P04-3：** 不新增状态条字段。Callout 1 的触发条件推广为 `validation_gate.status = failed`（任一 gate，包括 storage limits）。
  - 标题：`Validation gate failed: {gate names}`
  - 正文逐条列出失败的 gate，每条一句话说明。
  - 只有能量平衡失败时，沿用原有文案。
- **F-P04-4：** corrected Run 被 `publication_blocked`（`GF_VALIDATION_GATE_FAILED`）时，年度结果区显示 danger Callout：
  - 标题：`Annual results not published`
  - 正文：`This Run failed {n} validation gate(s): {list}. Results are withheld until the cause is fixed. The full ledger remains available.`
  - 动作：`Open in Inspect` · `Export ledger`

  年度合计不显示。
- **F-P04-5：** 原始边界残差只在 Inspect 的残差面板中显示：一张小表，列为 boundary、raw status、max residual、periods，不进入状态条。
- **F-P09-5：** 批准（旧后端没有 coverage 时，标签降级为 `Coverage not recorded`，数值照常显示）。
- **F-P09-6：** Withheld 的触发读取 `publication_blocked`：口径为 doctoral，且 `reason_code` 表示原始不变量未通过（以 X0/M4 实际实现的码为准，实现者在代码中查明后写入 reasonCodes 表）。不得臆造新字段。
- **F-P09-7：** memo 行接 P0-7 实际输出的兼容资本字段，即成本账 v2 中单列的 `existing_stock_compatibility.annualised_capital`，或 P0-7 报告中的实际键名。文案为 `Memo: run-of-river hydro compatibility capital (excluded from headline)`。
- **F-P05A-1：CSV 映射的 EUR/汇率输入**
  1. 价格列映射行增加 `Currency` 下拉框（GBP | EUR），默认 GBP。
  2. 选 EUR 后，同一行下方展开三个必填项：
     - `EUR per GBP`：数字输入，> 0，保留 4 位小数；
     - `FX basis`：下拉框，选项为 annual average / monthly average / fixed rate；
     - `Price year`：整数，1990–2100。
  3. 缺任一项或值不合法时，在字段下方显示 `GF_MAPPING_FX` 对应的错误文案，并禁用“预览”。
  4. 预览表中，原值列和换算后的 £/MWh 列并排显示，表头注明 `converted at {rate} EUR/GBP ({basis}, {year})`。

  沿用现有表单样式，新增元素遵守规格 1.3。

## M7「P0-9 收口」（实现 M2 界面审查小问题 1–6、F-P04-1…5、F-P09-5…7、F-P05A-1；stress event 界面；P0-6/P0-7/P0-8b 语义适配）

先前待定条目的处理：

- **已消解**：F-P04-1…5、F-P09-6、F-P09-7、F-P05A-1 按 2026-10-06 裁决实现；F-P08-1、F-P09-8（运行期 fallback 审计 Callout）已实现；F-S12-5（`Show stress events` 的目标）改为跳到 Market replay 中的全年 stress event 列表（见 F-M7-4）；F-P09-4 的旧 Run 下界按 F-P04-1 显示 `≥`。
- **M2 界面审查小问题 1–6**：全部按裁决实现。实现中与裁决字面不完全一致之处见下表 F-M7-2、F-M7-3。

| # | 规格 / 裁决 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-M7-1 | F-P09-6：Withheld 读取 `publication_blocked`，reason code 以 X0/M4 实际实现为准 | 代码中 Q14 的判定字段是 `result_publication`（`status='withheld'`，`reason_code` 为 `GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED` 或 `GF_RESULTS_WITHHELD_RAW_INVARIANTS_NOT_EVALUATED`，见 `gridform_core/result_advisories.py`）；`publication_blocked` 只用于 production 口径的 gate 失败（`GF_VALIDATION_GATE_FAILED`，F-P04-4）。界面按此读取，四个码都写入 `reasonCodes.ts`，并导出 `Q14_WITHHELD_REASON_CODES` | 裁决要求“以实际实现为准”，不臆造字段；两种“不发布”分别是 Q14（琥珀 Withheld）与 gate 失败（红色 Annual results not published） | 否 |
| F-M7-2 | 小问题 3：归档、原状态 cancelled、缺少声明年份 → `unavailable` + `cancelled_before_year_complete` | 同时覆盖原状态 failed：`unavailable` + `failed_before_year_complete` | 失败中止的 Run 缺年份同样不是“自相矛盾”；红框只留给 completed 却缺年份的情形（测试保留该 invalid 用例） | 否 |
| F-M7-3 | 小问题 4：孤立点画成半径 2.5px 的实心圆点，颜色与序列一致 | `<circle r=1.25>` 加 2.5px 描边（沿用该序列线条的 `stroke` 颜色），视觉上是半径 2.5px 的实心点 | 新样式表只能用已有 token（CSS guard）；序列颜色是旧的十六进制值，用描边继承即可不复制颜色 | 否 |
| F-M7-4 | 4.4：一个列表同时列出 `stress (supply < demand)` 与 `lost load (network)` | stress event 列表放在 **Market replay**（所有 Run，读新接口 `GET /api/runs/<id>/market/stress-events`，全年分页 50 条、按 start_period 数值排序、每条 Replay →）；Network & redispatch 的可靠性列表仍只列 `lost load (network)`，并加一行说明和跳到 Market replay 列表的按钮 | stress event 来自市场账本 `stress_event` 表，对铜板 Run 也存在，而网络页只对分区 Run 存在；两张表分属不同读模型，合并分页需要跨表排序，超出本轮“只改读模型”的范围 | 是（列表位置） |
| F-M7-5 | 2.3 规则 4 动作 `Show stress events` 跳到 4.4 列表 | 打开 Market replay 并滚动、聚焦到该列表（一次性，不影响之后的导航） | 回应 F-S12-5 | 否 |
| F-M7-6 | F-P04-3：`validation_gate.status = failed` 时显示 Callout 1 | 对任何口径都生效（doctoral 的 gate 只有在失败不符合已声明偏差时才是 failed，属于真实缺陷）；没有 `validation_gate` 记录的旧 Run 仍按 F-S12-1（`energy_balance=failed` 且非 doctoral） | 裁决原文未限定口径；doctoral 的已声明偏差不会触发 | 否 |
| F-M7-7 | F-P04-3：标题 `Validation gate failed: {gate names}`，正文逐条一句话 | gate 名称：Run invariants / Energy balance / Storage limits；每条一句话说明为本实现的文案（`runValidation.ts` 的 `GATE_TEXT`）；列表后一句 `Treat results from this Run as unverified.`，动作 `Open residuals in Inspect` | 裁决只给了标题格式 | 是（逐条文案） |
| F-M7-8 | F-P04-4：corrected Run 被 gate 门控时的 Callout | 已实现并有 SSR 测试；scratch 实例中没有真实的 gate 失败 corrected Run，因此没有截图 | 当前修正口径的 VALUE 101 Run 全部通过 gate | 否 |
| F-M7-9 | F-P05A-1：预览表原值列与换算后列并排 | 后端审阅报告新增只读字段 `source_sample_rows`（同一批样例行中被映射来源列的原始值）与 `fx`（所用汇率）；界面并排显示，不在前端反算 EUR。字段错误文案以 `GF_MAPPING_FX：` 开头，语言与该编辑器现有文案（中文）一致；字段标签按裁决用英文 | 原则 9：前端不做推算；编辑器原有文案为中文 | 否 |
| F-M7-10 | C20（计划 4.9 集成修订）：VRE 事件增加第三种 basis `corrected_unused_vre` | corrected 规则集（账本声明 `curtailment_semantics = vre_available_minus_gross_output`）下：`event_basis=corrected_unused_vre`，只显示 Unused VRE 一组（`excess + curtailment` 在该口径下是“非 VRE spill + VRE 弃电”，不是 VRE 事件口径）；KPI 与定义改称 `Non-VRE spill`、`VRE curtailment`、`Accepted VRE (gross output)`。doctoral 账本不变 | 按 P0-6 声明的列语义读取，不写死 | 是（文案） |
| F-M7-11 | C30：成本注释读取 `physical_operating_cost_detail_gbp.blackout_reliability` | model_runner 按年读取该明细：native PSM 的 `generation_import_and_reliability` 自 P0-6 S4 起包含“记录缺电 × VoLL”，因此铜板 native Run 现在显示 `includes VoLL`（M2 时显示 excludes，已过时）；悬停提示给出 VoLL 部分的金额与单价（新指标 `operating_cost_voll_gbp`、`voll_gbp_per_mwh`） | 适配 P0-6 的成本口径 | 否 |
| F-M7-12 | 4.6：fallback 审计 caution Callout 文案 | 标题 `Spatially indicative network results`，逐条列出规格句式 `Spatially indicative: {x}% of {tech} capacity fell back to {zone}.`（多年时句末加年份），另加一句说明与 `Open in Inspect` | 规格只给了句式；按原则 5 给出下一步 | 是（标题与说明句） |
| F-M7-13 | 9.8：375 px 不引起页面级横向滚动 | 新组件自身不溢出；375 px 下页面级溢出仍来自旧布局（与 F-P09-13 相同） | 做法一不改旧元素样式 | 否（同 F-P09-13） |
| F-M7-14 | 10：截图 | JPEG（质量 55，整页），来源为 scratch 实例（API 18966、UI 18967）上的真实 Run：修正口径 VALUE 101（一日与两年）、复现口径 VALUE 101（一日与两年，Q14 withheld）、Release R2 预测数据的修正口径新 Run（48 个 stress 时段，exact）、复制的修复前 Release R2 Run（下界）、VALUE 101 网络教学 Run | 控制仓库体积 | 否 |

## 修复轮 F-D2（第 11.5 节：一日范围与扩展；FX2）

| 编号 | 规格 | 实现 | 理由 | 需设计方复核 |
|---|---|---|---|---|
| F-FX2-1 | 11.5 只规定预检、范围下拉框和比较页；任务另要求修正 Inspect 的原因文案 | Inspect 的扩展结果面板遇到后端 reason `extensions_not_executed_in_scope` 时，显示 `Extensions did not run in this scope.` 加后端原文（`The one-day lesson runs the market step only, so the recorded extension(s) {ids} did not execute in this Run. Re-run with two-period or a longer scope to obtain extension results.`），不再显示 `year_results_missing` | 四类用户测试报告 4.2 的修复建议；文案沿用 11.5 预检句式 | 是（文案） |
| F-FX2-2 | 11.5 预检句中的 `{names}` | 填扩展 id（如 `value-toy-audit-extension`），逗号分隔 | 预检阶段扩展清单以 id 为准，名称可能缺失 | 否 |

## 修复轮 FX3（第 11.1、11.2、11.3、11.4、11.6、11.7 节）

| 编号 | 规格 | 实现 | 理由 | 需设计方复核 |
|---|---|---|---|---|
| F-FX3-1 | 11.1 第 6 组“环境类问题” | 组名 `Environment and setup`：除 errors 和数据类（plausibility、chronology、其他数据警告、适配器 unit not declared）之外的所有 warning 都归入此组，包括 project（如 UNSAVED_REVISION）、modules（如 QUARANTINE_PRESENT、STAGED_DWELL、MODULE_SOURCE_CHANGED）和 recovery 类 | 规格只列了六组，未说明非数据、非环境的 warning 放哪里；放进最后一组不丢信息 | 是（组名与归类） |
| F-FX3-2 | 11.1 组内去重“同一 code 只显示一次” | 去重键为 code + 去掉对象前缀后的消息正文。同一 code 但正文不同（如 `canonical role expects MW` 与 `expects GBP/MWh`）分成两行，各带 `×n`，悬停列出全部对象 | 只按 code 合并会把不同含义的提示藏到悬停里 | 是 |
| F-FX3-3 | 11.1 组头 tone | errors 组用红色 pill，其余五组都用琥珀色 pill；行内另显示对象（第一个对象 + `and n more`） | 规格写“琥珀色或红色” | 否 |
| F-FX3-4 | 11.7 预检琥珀色 warning | 后端 warning `GF_PREFLIGHT_MODULE_SOURCE_CHANGED`（消息为规格原句）；Readiness 卡片在分组上方另显示一个 caution Callout（标题 `Module source changed since install`），同一条也留在 `Environment and setup` 组里 | 该组默认折叠，单靠分组看不到 | 是（Callout 标题） |
| F-FX3-5 | 11.4 预检报告缺 `project_revision_sha256` | 只有 `accepted=false` 且带 errors 的报告才能在缺 revision 时匹配（Study、数据包、范围仍须一致）；Run 按钮旁文案 `Readiness found {n} error(s). Fix it/them, then check readiness again.` | 已通过的报告仍必须核对 revision（P0 身份规则不放松） | 是（按钮旁文案） |
| F-FX3-6 | 11.4 `Remove` | 新端点 `POST /api/{modules,extensions}/<id>/remove`：把安装目录和清单移到 `modules/disabled-manifests/removed/<kind>s/<id>/<时间戳>/`，不删除文件；已启用且正常的条目须先停用（`*_REMOVE_ENABLED`）；被保存的 Study、活动 Run（扩展另含保留的运行记录）引用时拒绝（`*_IN_USE`）。确认对话框文案见 `disabledEntries.ts` | 保守：不做永久删除，不破坏历史 Run 的可读性 | 是（拒绝条件与文案） |
| F-FX3-7 | 11.4 隔离条目的三个按钮 | 隔离但仍处于启用状态的条目，`Enable` 按钮禁用并提示 `Fix the source, then Rescan`；`Rescan`、`Remove` 可用 | 已启用的条目没有“启用”可做 | 否 |
| F-FX3-8 | 11.4 Enable 失败提示 | 后端在 Enable 前清除所有记住的导入失败（等同一次 Rescan），失败信息留在该行，附 `Rescan`；Rescan 成功后清空这些行内错误。四类用户测试中“缓存旧错误”的确切复现路径在测试 harness 中未能重现，单元测试改为断言 Enable 前调用了 `clear_negative_caches` 且报告的是新错误 | 保证“显示最新一次扫描的错误” | 否 |
| F-FX3-9 | 11.2 “每个数据包一张” | Data 页一次只显示当前输入上下文的一个数据包，面板随之切换（按 pack id 重挂载）；数据来自 `/api/data-packs/<id>/validation?extensions=…`，加载完成前用列表的 `plausibility_status` 缓存 | Data 页现有布局只有一个当前包 | 否 |
| F-FX3-10 | 11.2 配色与文字 | 层：无发现 teal `Passed`；有发现且不阻断任何口径为琥珀色 `{n} warning(s)`；有发现阻断某个口径为红色 `Failed`（悬停：`{n} findings; blocks {口径}`）；结构层无效为红色 `Failed`，有结构 warning 为琥珀色。口径：`Eligible` teal（有 warning 时悬停列出 code）；不可用为琥珀色 `Not eligible — blocked by {codes}` 或 `— structural validation failed`。规格示例中的 “not a thesis-era pack” 后端没有对应判定，不自造原因 | 原则 3：不确定就不猜 | 是（不可用的颜色与原因文案） |
| F-FX3-11 | 11.2 最差状态文案 | `validation failed / passed with warnings / passed / not evaluated`；原 `25/25` 数字保留在原位置，其后的说明改为 `inputs present · validation {最差状态}`（沿用旧元素字号，未改旧样式） | 做法一不改旧元素样式 | 否 |
| F-FX3-12 | 11.3 Callout 句式 | 每个失败的原始不变量一句：首句 `Annual results withheld: raw invariant "{名称}" failed ({n} rows).`，其余 `Raw invariant "{名称}" failed (…).`；能量平衡账户类失败用 `periods`；各自后接 `Matches declared deviation {ID}: {一句话}.` 或 `No declared deviation explains it.`；最后 `The full ledger remains available.`。没有失败明细时：未评估写 `the raw invariants of this Run were not evaluated`，否则 `a raw invariant failed. No declared deviation explains it.`。“一句话”取声明偏差目录 description 的第一句 | 规格只给单个失败的句式 | 是 |
| F-FX3-13 | 11.3 不变量名称 | 后端读模型新增 `raw_invariant_failures`（gate、check、名称、行数或时段数、命中的声明偏差及一句话），名称表在 `result_advisories.RAW_INVARIANT_CHECK_NAMES`（如 `storage.single_direction` → `Storage single direction`） | 由后端给出原因，前端不拼 | 是（名称用词） |
| F-FX3-14 | 11.6 时间戳检查结果 | 预览请求可带 `timestamp: {column, time_zone}`；时间轴层逐行检查（不可读、与第 k 行重复、早于上一行、缺口、步长不规则），任何问题都使审阅 `valid=false`、不能提交；逐行表最多列 50 行并注明总数。提交后 binding 记录 `timestamp_column`、`timestamp_time_zone`、`timestamp_uri`（保留的映射源文件）和 `timestamp_check`，数据包时间轴层从该源文件复查；冻结快照里该源文件不在时，以记录的 passed 检查为准 | 规范文件只含 value 列，时间戳必须留在源文件 | 是（阻断提交） |
| F-FX3-15 | 11.6 下拉框位置与文案 | `Timestamp column (optional)` 字段组放在列映射下方，只对半小时或小时序列角色出现；未选列时 Time zone 禁用；说明句为中文（与编辑器现有文案一致）；EUR 提示为行内琥珀色条（`role="status"`），放在 Currency 下方 | 编辑器现有文案为中文 | 否 |
| F-FX3-16 | 10：截图 | `docs/dev/p0-ui-screens/fx3-*.jpg`（元素截图，JPEG 质量 80，1280 与 375 各一张）。映射编辑器两组截图来自与 harness 测试相同的独立渲染（模拟映射 API），其余来自 scratch 实例（API 18930、UI 18931）上的真实数据与真实 Run | 映射编辑器在应用中只出现在换数据引导里，需要整套独立数据包流程 | 否 |

### 设计方裁决：F-FX3-1…16（2026-10-06，Claude）

**全部批准。** 说明如下：

- **F-FX3-1** 组名 `Environment and setup`，按实现归类，可以。
- **F-FX3-2** 去重键用 code 加正文，比只用 code 更好。
- **F-FX3-4** Callout 标题 `Module source changed since install` 批准。
- **F-FX3-5** 按钮旁的文案批准。已通过的报告仍要核对 revision，这一点正确。
- **F-FX3-6** Remove 实现为移入 `removed/` 而不删除；拒绝条件为“启用中”和“被引用”。文案批准。
- **F-FX3-10** 规格示例中的 “not a thesis-era pack” 取消，改为后端实际给出的阻断码，符合原则 3。配色批准：不可用为琥珀色，结构层失败为红色。
- **F-FX3-12、F-FX3-13** 多条失败时的句式和名称表批准。名称用 Title case，与现有界面一致。
- **F-FX3-14** 时间戳有问题时阻断提交，批准。用户已明确声明了时间戳列，就必须保证它可信。

## FX9（四类用户复测的中等问题：N-1、M-D1 界面）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-FX9-1 | 11.2 `Doctoral reproduction ● Not eligible — not a thesis-era pack`（F-FX3-10 裁决时因后端无此判定而取消） | 后端 `profile_eligibility` 现在调用与 Study 编辑器、preflight 相同的白名单检查（`methodology.data_pack_violation`），口径行新增 `pack_supported` / `pack_support_reason`，并把 `VALUE_PROFILE_COMBINATION_UNSUPPORTED` 记入 blocking codes。前端在 `pack_supported === false` 时显示 `Not eligible — not a thesis-era pack`（琥珀色，与 F-FX3-10 的配色一致），优先于结构层和发现层的原因；该码不对应任何发现，所以三层的颜色不受影响 | 复测 N-1：面板说 Eligible、编辑器却拒绝。后端已有判定，恢复规格原文案 | 是（原因的优先顺序） |
| F-FX9-2 | 3.4 Merit order 表的 Accepted 列（规格未涉及储能逐条接受量） | 储能报价有 `storage_orders` 账本行时，Accepted 显示该条报价自己的 MWh（Evidence 列为 `storage offer ledger`），悬停显示 `Storage offer ledger: {status} ({reason})`；不再显示 `(asset total)`。表下方加一行 12px、`--muted` 的说明：`Storage offers show the MWh each offer delivered (storage offer ledger, gross). Where a battery buys energy back in the same period, its net dispatch in the orders ledger is lower.`。没有账本行的旧 Run 保持原来的 `(asset total)` / `Not separately recorded` | 复测 M-D1 界面残留与 M2-N5（修正口径按毛值记，同时段买回不在表中扣减） | 是（说明文案） |
| F-FX9-3 | 11.6 时间戳检查（规格只要求单调、缺口和重复） | 映射审阅的 Timestamps 一行在原文之后追加 ` · first {first_utc} · last {last_utc}`（沿用该行原样式）。后端在首个时间戳不在 1 月 1 日 00:00（与模型时钟原点相差 `origin_offset_minutes` 分钟）时，在审阅的 warnings 中加 `GF_DATA_TIMESTAMP_ORIGIN: the first timestamp … is {n} minutes after/before 1 January 00:00; …`，**不阻断提交**；年份不同（例如 2023 年的参考数据）只显示，不判定 | 复测 N-3：整体错位 30 分钟能通过全部检查。规格没有要求，所以只提示不阻断 | 是（是否改为阻断） |

## R1-5（四类用户测试剩余界面缺陷；DECISIONS A21）

规格第 11 节没有覆盖这些低等级问题。以下实现都沿用第 0 节原则和第 1.3 节样式约定（新元素 ≥12px、只用已有 token），每条都需要设计方复核文案或做法。截图：`docs/dev/p0-ui-screens/r1-*.jpg`（scratch 实例 API 18950 / UI 18951，真实 VALUE 101 Run，元素截图 1280 与 375 各一张；页头 pill 在 375 下被折叠进菜单、模块安装框只截了 1280）。

| # | 缺陷 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-R15-1 | R-D2 | Run history 下拉项为 `{范围} · {状态} · {创建时间} · {ID 后缀}`，悬停显示完整 ID；创建时间取 `created_at` 的本地钟点原文（不做时区换算），旧记录从 Run ID 中的时间戳取。有 Run 时占位项改为禁用的 `Choose a Run (n)`，`No runs yet for this Study` 只在没有 Run 时出现；未选 Run 时结果区写 `{n} Runs for this Study`，启动中写 `Starting the Run…` | 同一 Study 的两个 Run 原来标签完全相同 | 是（标签格式） |
| F-R15-2 | S-D12、M2-N1 | `Check for` 在用户未手动选择范围前跟随所选 Run 的范围；“has started” 提示跟随该 Run，结束后改为 `The {范围} Run {后缀} has completed. / failed ({error_code}). / was cancelled.` | 重新加载后 Check for 回到 Two-period；失败原因在当前视口看不到 | 是（提示文案） |
| F-R15-3 | S-D10、O-1 | 启动中在 Run 按钮下显示一句说明（首次在新数据目录归档 Python 运行环境约 3 分钟，之后不到 1 分钟；可以离开本页，结束后不会被拉回）；`snapshotting` 状态行附一句同义说明。启动返回时若用户已切到别的页面，不再自动切回 Runs，也不改选 Run | POST 要等快照归档结束（P1-11 / F5-08 未改） | 是（说明文案） |
| F-R15-4 | R-D4 | 冻结输入核对与创建进行中，面板内显示状态行（中文，与该面板现有文案一致），创建一行提醒关闭页面后服务端仍会完成、不要重复创建 | 原来只禁用按钮 | 否 |
| F-R15-5 | M2-N3 | 预检有 errors 而物理输入 ready 时，Physical system preview 的徽章改为琥珀色 `inputs ready · Run blocked`（悬停说明 Run 不能启动） | 原来是 teal 的 `ready` | 是（徽章文字） |
| F-R15-6 | S-D13 | Run 上下文条与冻结 readiness 证据中，`Data pack manifest SHA-256` 改为 `Frozen data pack manifest SHA-256`，并加一句：冻结会改写文件路径并记录快照，所以与 Data 页的源 manifest SHA 不同，按角色比较文件 SHA | 两个 SHA 都正确，缺的是标注 | 是（说明句） |
| F-R15-7 | R-D6、S-D11、M-D9 | 输入快照（project.json、snapshot.json）每个 Run 只在离开 queued/snapshotting 后读一次；`resource-readiness.json` 只在 snapshot.json 记录 `resource_readiness_path` 时才读。一日课程的 Inspect 默认打开 Market，Planning 标签显示 `No planning record in this scope` 并说明原因，不请求 planning 接口 | 每次轮询都重复请求，404 刷屏 | 否 |
| F-R15-8 | R-D3 | 非年度 Run 的 stress 列表：标题 `Stress events — {year} (non-annual run)`；空列表 `No stress events in the {n} periods of {year} this non-annual Run computed.`（n 取 Run 的每年时段数，缺失时不写数字）；记录了 stress 但为 0 时，标题右侧写 `None`（规格 2.3），不再是 `—`。网络页可靠性列表的空句同样处理 | “0% of 2025” 把非年度 Run 说成没算 | 是（文案） |
| F-R15-9 | R-D5 | 没有 balancing 模块的 Run（一个全国市场）归为 copperplate：网络页写 `This run cleared one national (copperplate) market and selected no network balancing module…`，附 `Open Market replay →`；市场账本有分区表但没有分区行时，不再请求 annual brief，所以 doctoral Run 不会把 withheld 原因拼到“没有分区账本”后面；已完成 Run 的页头不再写 `network evidence pending` | 原来修正口径铜板 Run 显示完整分区工作区和 pending，doctoral 拼两个原因 | 是（文案与归类） |
| F-R15-10 | R-D7、S-D9、F-D5 | Compare 的 Changed dimensions 每行为“标签 + differs at {路径}”（来自后端 `changed_dimension_details`），模块选择写 `id 版本 → id 版本`；原始 JSON 收进折叠的 `Recorded values (JSON)`。身份核对卡片在 changed 时先显示 `Differs at: …`，原始值同样折叠 | 原来是数 KB 的单行 JSON | 是（行格式） |
| F-R15-11 | R-D11 | 只要有 advisory 且没有 pre-fix 通知，上下文条下方显示折叠的 `{n} advisories apply to this Run · 7 high, 3 medium, 1 info`（摘要琥珀色），展开为已有的 advisory 列表；列表每条加严重度；Run 详情未加载时用列表行的计数 | doctoral Run 的 10–11 条 advisory 只在比较页出现 | 是（位置与配色） |
| F-R15-12 | R-D11、F-D6、N-6 | 编辑已保存 Study 时标题为 `Edit study · {名称}`；已保存 Study 列表加 `data {pack}`，哈希上方注明 `Model graph SHA-256 (modules and extensions; not the data pack)` 或 `Revision SHA-256` | 两个数据包不同的 Study 显示同一哈希，看似缺陷 | 是（标注文字） |
| F-R15-13 | M2-N4、M-D2 | 已安装模块卡片：`Source SHA-256 at install`、`Conformance at install`，新增 `State`（Enabled / Disabled / Quarantined）。停用或隔离时卡片不再给出自己的 Enable/Disable，改为 `Open Disabled and quarantined`（由该区负责 Enable、Rescan、Remove）。原地改源码时卡片显示琥珀色 `Source changed since install (old8… → new8…). Runs record the new source hash.`；数据来自后端新字段 `GET /api/workspace` 的 `module_source_changes`（与 preflight 同一只读字节比较） | 卡片与停用区、隔离面板不一致；卡片看不到源码已变 | 是（卡片不再提供开关） |
| F-R15-14 | M-D9、F-D6 | 模块和扩展安装成功后，原生文件输入框随之重置（`files.length` 为 0） | 原来只修了显示 | 否 |
| F-R15-15 | S-D8、N-6、N-5、F2-N3 | 映射提交后，引导数据编辑器在该角色下保留确认句（编辑器因 manifest 变化重挂载，原消息丢失）；映射绑定的角色卡显示 `时间戳列 {列} · {时区} · 已核对 {n} 行`；引导数据上下文写入 URL（`journeyRevision`、`journeyPack`，仅 `dataContext=journey` 时，revision 须为 SHA-256），重新加载与前进后退可恢复；页头 pill 改为 `{n} of {m} base inputs ready`（悬停说明扩展角色在 Data 页输入合同中计数） | 复测的低级问题 | 是（URL 参数名、pill 文案） |
| F-R15-16 | R-D8 | 新样式表 `app/features/shared/narrow-layout.css`：仅在 760 px 以下，给 `.project-grid`、`.audit-stack`、composer 各步骤的子元素加 `min-width: 0`，composer 两列字段改为 `minmax(0, 1fr)`，composer 输入框与 `.inline-select` 限宽 100%。实测 375 px 下 13 个视图和 composer 五步的 scrollWidth 都是 375（Inspect 原 866、Studies 原 488、Market replay 原 391） | A21 要求修理剩余问题；只改最小宽度，不改颜色、字号和桌面布局 | **是**：这是对旧元素布局的窄屏修改，与“做法一不改旧元素样式”（F-P09-13、F-M7-13）不同，请设计方确认是否接受 |
| F-R15-17 | R-D12 | 已结束 Run 的模块证据：有调用记录写调用次数；一日课程中 PSM 以外的槽位写 `Not called in this scope`；其他范围没有记录写 `No calls recorded`；`Evidence pending` 只用于进行中的 Run | 已完成的 Run 写 pending 不准确 | 是（文案） |

未实现（理由见 `docs/dev/p0-reports/R1-5-ui-defects.md` 第 2 节）：F-D6 草稿只在内存中（整页刷新丢失，需要决定存放位置，属于设计问题）；N-4（快照期间 clone 被 `STUDY_LIFECYCLE_LOCK` 阻塞，后端 P1-11）；R-D9、R-D10、O-3（信息级，后端或负责人决定）。

## R2-2（R1 复测遗留的界面与文档项；DECISIONS A23）

规格没有覆盖这些项。以下实现沿用第 0 节原则和第 1.3 节样式约定（新元素 ≥12px、只用已有 token），需要设计方复核文案或做法。截图：`docs/dev/p0-ui-screens/r2-*.jpg`（scratch 实例 API 18960 / UI 18961；模块安装、隔离和页头 pill 是真实实例，比较页、停用卡片、Enable 失败、研究引导和 Learn 的启动等待用 Playwright 拦截 `/api/workspace` 和被测请求，比较响应由后端 `compare_run_summaries` 实际生成）。

| # | 缺陷 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-R22-1 | AF3-1 | 年度差值按后端 `metric_delta_gates[指标].allowed` 逐指标显示。被扣发的指标在数值下方加一行 12px、`--muted`：`Delta withheld: {reason}`（后端给的英文句子；没有句子时写 reason_code）。年份列表上方的总括改为 `info-box`：标题 `Deltas withheld`，正文 `Deltas are withheld for {n} of {m} metrics ({名称}); each states its reason below. The other metrics show their deltas.`，全部扣发时写 `Annual deltas are withheld for every metric; each metric states its reason below.`。原来的红框中文句子删除。没有 `metric_delta_gates` 的旧响应仍按 `metric_deltas_allowed` 全有或全无，总括用英文的原句意 | A23 裁决：只扣发依赖弃电证据的指标，并注明原因。红框按规格第 4 节只用于 invalid，扣发不是 invalid | 是（总括与逐指标文案、改用 info-box） |
| F-R22-2 | AF3-2、R3M-7 | 比较页的身份核对块改为英文：标题 `Identity check before comparison`；五行标签 `Base and network data`、`Model method (modules, extension selection, methodology)`、`Parameters and extension settings`、`Execution years`、`Run scope`；状态 `Same` / `Changed` / `Cannot verify`；说明句与加载提示、响应不一致的错误也改为英文 | 比较页其余部分都是英文；“扩展的选择属于方法、扩展的参数属于配置”是后端原设计，标签把这一点写明，避免“配置一致”被读成扩展没变 | 是（标签文字） |
| F-R22-3 | R3M-7（范围） | 只改英文界面中夹杂的中文：比较页身份块、方法对照 Study 保存后的提示（`Method-comparison Study saved. Data and all other settings are unchanged; no Run has started.`）。Read me 对话框的“正在读取使用说明…”保留中文（对话框内容是中文 README），但只在读取中出现，关闭或空闲时不再常驻 `role=status` | 研究引导页（含“选择基线 Study / 核对新研究”）、Read me、数据映射编辑器、冻结输入恢复面板整页都是中文，逐页翻译不是“小改动”，也涉及界面语言策略 | **是**：界面是否统一为一种语言，由设计方决定 |
| F-R22-4 | R3-N3 | Run 上下文条的 “Open in Inspect” 不带标签时不再强制 Planning，由 Inspect 按范围选默认标签（一日课程为 Market）；侧栏导航、Runs 页的链接和网络页的 “Open in Inspect” 都会清除之前请求的标签 | 原来写死 `tab ?? "planning"`，且请求的标签不清除 | 否 |
| F-R22-5 | R3M-2 | 页头 pill 只在工作区本身读不到时写 `Inputs not loaded`；`/api/health` 为 degraded（例如一个模块被隔离）时照常显示 `{n} of {m} base inputs ready`。侧栏的 `● Backend degraded` 不变 | 工作区已正常读取，pill 的计数仍然有效 | 否 |
| F-R22-6 | R3-N4 | 研究引导创建 Study 成功后，基线下拉框保持原基线，名称框清空；输入的名称与已有 Study 重名（忽略大小写和首尾空格）时，在名称框下显示琥珀色提示 `已有同名 Study。名称可以重复，但列表和比较页中容易混淆，建议换一个名称。`，**不阻止**创建（后端允许重名） | 原来创建后下拉框落到新建的复现 Study，再点一次得到“复现的复现”，且同名 | **是**：重名是否应阻止创建 |
| F-R22-7 | R3M-3 | Enable 失败后的说明按该条目能否 Enable 区分：能 Enable 时写 `Fix the cause, then press Enable again (Enable scans afresh; Rescan alone leaves a disabled entry disabled).`；不能时保留 `Fix the cause, then Rescan.` | 照原提示 Rescan 后模块仍是 Disabled | 是（文案） |
| F-R22-8 | R3M-4 | 已安装模块卡片的引用说明按状态区分：Enabled 时保留 `Used by n saved Studies; disable is blocked until those configurations are migrated.`；Disabled 或 Quarantined 时写 `Used by n saved Studies; they cannot run until this module is enabled again (隔离时为 repaired), or they select another module.`。`USER_GUIDE` 中英文同步写明隔离面板可以停用仍被引用的模块 | 卡片已是 Disabled 却说“停用被阻止” | 是（文案） |
| F-R22-9 | R3M-5 | Readiness 中模块源码变更的 warning 只在琥珀色 Callout 中出现一次，不再计入 `Environment and setup`（errors 从不排除）；已隔离模块的卡片写 `… It is quarantined, so no Run can start; once it is repaired, Runs record the new source hash.`（与后端 d1ad608 同义） | 同一警告出现两次；隔离时承诺“记录新哈希”不成立 | 否 |
| F-R22-10 | L-4 | Learn 页启动 Run 期间，在课程标题下显示一行 `run-launch-note`（与 Runs 页同样式）：`Starting the Run: VALUE is freezing the Study's inputs and execution environment first, so the lesson buttons stay disabled until the Run is listed. The first Run in a new data folder also archives the Python runtime once (about 3 minutes); later Runs take under a minute. If you stay on this page, the Run opens when it is listed.` | 原来按钮全部禁用但没有说明；POST 阻塞本身属于 P1-11 / F5-08，未改 | 是（位置与文案） |
| F-R22-11 | L-6 | 映射审阅中 “完整文件校验报告” 在报告为空时写 `尚未运行：先修正上面列出的映射或换算错误，整份文件的校验才会运行。`（12px、`--muted`），不再显示 `null` | 原样显示 `null` | 是（文案） |

未实现：R3-N3 的截图（需要带 Callout 的真实 Run，改动由源码契约测试 `r2-ui-low-items` 覆盖）；L-6 的截图（需要真实换算失败的映射，未做）。

### 设计方裁决：F-R22-1…11（2026-10-07，Claude）

- **F-R22-3（界面语言）：** 本轮只改英文界面中夹杂的中文，范围批准。**统一界面语言（i18n，中英可切换）放进做法二（前端整体翻新）**，与第 1.3 节的样式体系一起设计，这一轮不逐页翻译。
- **F-R22-6（重名 Study）：** 批准。只给琥珀色提示，不阻止创建，与后端允许重名一致。
- **其余 F-R22 项：** 按实现批准。
- **p06 advisory 的严重度：** 维持 high。它只影响显示顺序，而且该提示涉及论文口径下调记账的已知局限，宁可醒目。

## R3-4（Run 异步启动；DECISIONS A24-5：O-1、N-4、L-4、F5-08、P1-11）

后端改为：启动请求只做准入和 preflight，建好 `snapshotting` 状态的 Run 后立即答复 202；冻结在后台进行，进度写在 `status.json` 的 `preparation`（阶段、第几步、已用时间）。规格第 5 节只规定了 worker 状态与年度进度，没有准备阶段的显示，以下按第 0 节原则和第 1.3 节样式（新元素 ≥12px、只用已有 token）实现，需设计方复核。

| # | 缺陷 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-R34-1 | O-1、F5-08 | Runs 页所选 Run 处于准备中时，状态行下加一行 `run-preparation-progress`（13px、600、`--ink`，`role=status`）：`Preparing · step {i} of {n}: {阶段} · {已用时间} elapsed`，阶段为 `Recording and archiving the execution environment` / `Freezing the Study's inputs` / `Checking disk space and reserving output space` / `Starting the model worker`，时间格式 `42 s`、`1 min 05 s`、`1 h 02 min`（随每 2 s 的轮询更新，取服务器时间）。其下保留原 `SNAPSHOTTING_NOTE`（首次归档约 3 分钟） | 规格要求显示阶段与用时；原来只有一句固定说明 | 是（文案与位置） |
| F-R34-2 | O-1、S-D10 | 取代 F-R15-3 的启动说明：启动请求进行中（通常约 1 s）Run 按钮下改为 `VALUE is checking the Study's readiness and creating the Run. The Run is listed at once; its inputs and execution environment are then frozen in the background, and other pages stay usable.`；结果区空状态改为 `VALUE is checking the Study's readiness. The Run appears in Run history as soon as it is created; its inputs are then frozen in the background.` | 启动不再等快照归档，原文“列出前要冻结”不再成立 | 是（文案） |
| F-R34-3 | L-4 | 取代 F-R22-10 的 Learn 文案：`Starting the Run: VALUE checks the Study's readiness and lists the Run, then freezes its inputs in the background. If you stay on this page, the Run opens when it is listed; its preparation is also shown here.`。另外，课程的 Run（一日、两年、网络练习的两个 Run）处于准备中时，在课程标题下显示 `learn-run-preparation` 块：每个 Run 一行 `{One-day Run / Two-year Run / Copperplate Run / Constrained Run}: {与 F-R34-1 相同的进度句}`，块末附 `SNAPSHOTTING_NOTE` | 读者从 Runs 返回 Learn 时也能看到准备进度 | 是（位置与标签） |
| F-R34-4 | O-1 | `snapshotting` 的 Run 也显示 `Request safe cancellation`（原来只有 queued、running）。准备线程在每个阶段开始前读取取消请求，取消后 Run 记为 cancelled（`GF_RUN_CANCELLED_BEFORE_WORKER`），不启动 worker；准备中取消时进度句末尾加 `Cancellation requested: the Run stops before its model worker starts.` | 准备首次可达 3 分钟，原来无法中止 | 是（是否提供该按钮） |

后端出错的显示沿用已有的失败 Run 呈现：准备失败为 `GF_RUN_PREPARATION_FAILED`（`current_stage` 为 `Run preparation failed`，`preparation.failed_stage` 记失败阶段），后端在准备途中停止为 `GF_RUN_PREPARATION_INTERRUPTED`（`Run preparation interrupted`）；磁盘与预留的拒绝保持原错误码，但现在是已建 Run 的 failed 状态，而不是启动请求的 503/507。


## R4-2（复现角色的中低缺陷；DECISIONS A27）

以下按规格现有组件、token 与文案风格实现；规格没有覆盖的地方取最保守的做法，需设计方复核。

| # | 缺陷 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-R42-1 | R-低4 | 规格第 0 节第 5 条和 4.2 节把动作写作 `Export ledger`，但这个动作只是打开 Inspect 的产物列表，并不下载文件。按钮和 Run 上下文条的动作统一改名为 `Open ledger files`，行为不变 | 动作名与行为一致；真正的打包下载已有 Inspect 的 `Prepare audit bundle` | 是（规格中的动作名） |
| F-R42-2 | R-中2 | 比较页原来的 `Teaching boundary` 信息框改为按后端 `annual_withholding` 生成：教学课仍写 `Teaching boundary` 原文；Q14 扣留写 `Annual results withheld`，每个被扣留的 Run 一行（`{run} is a reproduction Run whose annual results are withheld (Q14): raw invariant {check} ({n} rows) failed. Its full ledger stays available in Inspect.`），末行说明导出里有哪些已发布 Run 的年度值、没有差值。沿用原 `info-box`，不并排显示已发布 Run 的年度值（只进导出） | 原文案与事实不符；并排显示需要新的表格布局，规格未覆盖 | 是（是否在页面上并排显示已发布 Run 的年度值） |
| F-R42-3 | R-低2 | 未完成 Run 的提示摘要末尾加 ` · provisional: re-evaluated against this Run's frozen fleet and modules when it completes`；冻结输入之前不列出按资产筛选的提示 | 提示条数在完成前后变化，且列出了与本数据包无关的提示 | 是（文案） |
| F-R42-4 | R-低3 | “has started” 提示只在发起它的 Study 的 Runs 页显示；换页或换 Study 时不显示，回到原处仍显示。后台运行按钮不变 | 提示跟着用户到了无关页面 | 否 |
| F-R42-5 | R-低5、S-低7(c)、T-低1 | 新建 `app/features/shared/labels.ts` 作为指标名、状态词和阶段名的唯一标签表（如 `CEM system cost per MWh served (GBP/MWh)`、`Reproduction with declared deviations`、`Application submitted`），未知代码按首字母大写的短语显示。Runs 的校验条改为首字母大写的状态词，准备期间 Execution 写 `Preparing`；Run 上下文条沿用小写风格，准备期间写 `preparing` | 原来直接由字段名拼出标题，同一阶段两种写法 | 是（个别标签的措辞） |
| F-R42-6 | R-低1 | Inspect 规划表标题改为 `{n} project-year records`，下面一行说明 `One row per project and model year: …`，第一列加 `Year` | 表格行实为“项目×年份” | 否 |
| F-R42-7 | R-低7 | Composer 第 2 步中，当前口径不接受的计算域卡片徽章写 `not available with this methodology`（warn 色），与第 1 步数据包的禁用写法一致 | 原来同时显示绿色 `ready` 和“不属于论文谱系” | 否 |
| F-R42-8 | R-低8 | Readiness 运行时间：没有可比的已完成 Run 时写 `estimated {a} min to {b} min (no comparable completed Run yet)`；有实测时写 `estimated about {n} min`（90 分钟以上用小时、一位小数） | 首次估算单点值与实际相差约 6 倍 | 是（文案） |
| F-R42-9 | R-低9 | Market replay 导出面板控件下加一行 12px `--muted` 说明（`.replay-export-note`），解释 `physical_resource_cost_gbp` 与年度成本账的口径差别 | 用户对不上两个合计 | 是（文案与位置） |
| F-R42-10 | R-低10 | 年度结果被扣留的 Run 打开 VRE 页时不再请求年度 VRE 摘要，改为 `Withheld` 状态 pill 加 `info-box`：`Annual VRE results withheld` 与去向说明 | 原来请求得到 409，控制台记为错误 | 否 |

## R4-3（换数据角色的中低缺陷；DECISIONS A27）

以下按规格现有组件、token 与文案风格实现；规格没有覆盖的地方取最保守的做法，需设计方复核。

| # | 缺陷 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-R43-1 | S-中1 | **取代 F-P09-3。** 模型时钟统一按一条规则显示：UTC、固定 365 天年（闰年没有 2 月 29 日）、不做夏令时。回放窗口行写 `{start} → {end} (UTC model time)`，时间去掉秒和 `Z`（`2025-07-01 16:00`）；规格 3.1 原写 `(UTC)`，本实现多“model time”两词，提示这是模型时钟。旧 Run 的账本标签为 Europe/London 时，后端按 UTC 报告并给出 `clock_note`，窗口行下方用 12px `--muted` 显示这句说明。Stress 事件表和网络可靠性事件表表头改为 `Start (model date & time, UTC)`；VRE 峰值事件时间后加 ` UTC`。前端统一用 `app/features/shared/modelClock.ts` | 账本时钟一直是 UTC，原标签 Europe/London 让夏令时期间的时间看起来早 1 小时（S-中1） | 是（标签措辞） |
| F-R43-2 | S-中3 | 映射编辑器 `Timestamp column (optional)` 框内新增 `Date order` 下拉框：`Auto-detect (DD/MM/YYYY unless a row shows MM/DD/YYYY)` / `DD/MM/YYYY (day first)` / `MM/DD/YYYY (month first)`，未选时间戳列时禁用，与 `Time zone` 相同。审阅报告的时间戳段落下加一行 13px 文字：`covers {n} days · data year {y} · dates read as DD/MM/YYYY ({依据})`；缺口多为约一个月时列出提示 | 英国常用的日/月/年被按月/日读出，报 154 条误导性缺口 | 是（选项文案） |
| F-R43-3 | S-低3 | 时间戳问题表的 `Row` 列拆为 `Data row` 与 `CSV line` 两列（与单元格错误 `Row 51 (CSV line 52)` 同一对编号）；“重复”问题写 `duplicate of data row {n} (CSV line {m})` | 同一面板中 Row 含义不一致 | 否 |
| F-R43-4 | S-低2 | 序列不满一个模型年（会从开头重复补齐）时，审阅报告给出警告，并在原确认框下多一个确认框：`{覆盖说明} 我知道模型会这样补齐，仍要提交。`；两个都勾选后提交按钮才可用，后端也要求 `acknowledged` | 原来只有泛泛的“循环重复”，可以直接提交 | 是（文案） |
| F-R43-5 | S-低5 | 换数据角色卡片在时间戳声明下加一行（与时间戳同样的 12px `--muted`）：`原币种 EUR · 汇率 {r} EUR/GBP · 汇率口径 {b} · 价格年份 {y}`；时间戳行在有日月顺序时加 ` · DD/MM/YYYY`。包只读时角色下拉框仍可选择，用于浏览各角色当时的导入方式；上传与映射仍禁用 | 提交后看不到汇率；只读时无法浏览角色 | 否 |
| F-R43-6 | S-低7(b) | 比较页年度指标中，三个依赖 VRE 弃电证据的指标缺值时写 `Unavailable`（与 Runs 页相同），其他缺值仍写 `Not evaluated` | 同一缺项两页用词不同 | 否 |

## R4-4（改函数、加功能角色的中低缺陷；DECISIONS A27）

以下按规格现有组件、token 与文案风格实现；规格没有覆盖的地方取最保守的做法，需设计方复核。

| # | 缺陷 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-R44-1 | M-中1 | Runs 页模块证据中，storage cost 槽位在市场账本记录了储能成本模块时写 `Called inside the PSM: the market ledger records its storage offers ({n} storage asset-periods)`；模块对象报告的 id 与清单 id 不同时，句末加 `; its object reports id {id}`。其他槽位不变 | 由 PSM 内部调用的槽位没有阶段事件，原来写 “Not called in this scope” | 是（文案） |
| F-R44-2 | F-中2 | 扩展目录卡片在已安装扩展原地改源后，footer 上方显示与模块卡片相同样式的 `installed-module-note caution`：`Source changed since install ({模块} {旧哈希8位}… → {新哈希8位}…). Results may change; Runs record the new source hash.`。Studies 卡片对 `source-reidentify` 修订写 `Updated to code identity {12位} (installed local code was edited in place; results may differ)` | 原来扩展改源没有任何提示，修订还写“no change expected” | 否 |
| F-R44-3 | M-中3 | 派生成功后的页面提示（Modules 页和研究引导）在原句后追加：先为来源 Study 追加的代码级修订（`The source Study was first re-identified as revision {n} (…).`），以及来源模块图已变化的说明（`The source's module code changed since its revision was saved (…). For a one-change comparison, compare with a new Run of the source Study.`） | 后端改为自动追加代码级修订、按当前模块图派生，用户需要知道 | 是（文案） |
| F-R44-4 | F-中4 | 扩展编写台的 “Open independent Study draft” 复制当前选中的已保存 Study（年份、模块、扩展、确认、市场与求解器设置、参数和运行选项），草稿名 `{Study} · extension study`；提示写 `Independent Study draft opened as a copy of {Study} (revision {n}): its years, modules, parameters and run options are kept. …`。没有选中 Study 时保持原行为并说明 | 原草稿沿用编辑器当前内容，丢参数，无法做单变量对照 | 否 |
| F-R44-5 | M-低2 | Check readiness 报告中有安装环境错误（scope `environment`，如 kernel 未封存）时，不弹出方法升级确认框，直接显示报告，提示 `Fix the installation errors listed under readiness first. …`；确认框确认或取消后自动重跑 readiness（取消后不再弹框，报告中显示需要确认的错误） | 原来先确认、写入修订，之后才看到封存错误；确认后 readiness 区为空 | 是（流程） |
| F-R44-6 | M-低4、F-低2 | 隔离面板每行在错误行下加 12px `--muted` 一行 `Manifest file: modules/{file}`（新 class `.quarantine-manifest`），同一 ID 多份清单时追加 ` · another manifest uses the same ID; keep one and Rescan`；面板标题按条目类型写 module / extension / modules and extensions，句子按数量写 it / them。停用区条目标签写 `{名称} · {ID} {版本}`（名称与 ID 相同时只写 ID），隔离条目列出清单文件 | 两行完全相同无法区分；横幅单数不对；同名扩展无法区分 | 否 |
| F-R44-7 | F-低4 | Run 上下文条（Runs、Inspect 和结果页的头部）在方法学 pill 旁为每个所选扩展加一个 `StatusPill`：未声明 ready 的写 `Experimental extension: {id} {version}`（caution），ready 的写 `Extension: {id} {version}`（muted）；`.run-context-profile` 加 `gap: 4px 6px` | 原来全页找不到实验性扩展的标记 | 是（位置） |
| F-R44-8 | F-低5 | 有 Run 未结束时的生命周期确认框文案按对象写 `Change the installed extensions anyway?` 或 `… modules anyway?`（后端消息同样区分）；冲突检查先于确认 | 原来扩展也说 modules，且确认后才知道包会被拒 | 否 |
| F-R44-9 | F-中3 | Rescan 成功后的提示改为 `Rescan complete: modules and extension hooks were imported again; none is quarantined.`，否则 `… some modules or extensions are quarantined; see the panel.` | Rescan 现在也导入扩展钩子 | 否 |

## R5-1（换数据角色最终验收的缺陷；DECISIONS A28）

以下按规格现有组件、token 与文案风格实现；规格没有覆盖的地方取最保守的做法，需设计方复核。

| # | 缺陷 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-R51-1 | S-F-高1 | 换数据角色卡片中，旧标签需求文件（VALUE 101 的两份需求文件：表头 `mwh`、包内标签 `MWh/period`、实际按 MW 读取）在原文件和目标文件下各加一行，样式与时间戳、汇率行相同（12px `--muted`，新 class `.journey-data-unit`）：`单位：按 MW 读取（每半小时平均功率）。文件表头写作 mwh、包内标签为 MWh/period，这是已知误标；…映射中请选择 MW。`。映射编辑器需求说明下用已有的 `.csv-mapping-hint`（amber 左边框）重复这句。后端在工作区数据包的绑定上给出 `runtime_unit_interpretation`（登记表重标，文件字节和 manifest 不变） | 用户按基线标签换算会把需求放大一倍，界面原来没有任何提示 | 是（文案、提示色） |
| F-R51-2 | S-F-高1、S-F-中2 | 比较页年度指标新增 `Annual demand (MWh)`、`Demand served (MWh)`、`Unserved energy recorded by the PSM (MWh)`；原 `Unserved energy (MWh)` 改为 `Unserved energy incl. stress shortfall (MWh)`（A2 账：PSM 记录的缺电加 stress 缺口），沿用现有指标卡片。Runs 页年度卡片 `Unserved demand` 改显示同一 A2 总量，下方用卡片已有的 `small` 样式写 `incl. stress shortfall · {x} MWh recorded by the PSM`；没有 A2 数值的旧 Run 仍显示 PSM 记录值，不加说明。前端不做减法，两个数都来自后端 | 顶部横幅说缺口记为未供电量，卡片和比较却只显示 PSM 记录的小数 | 是（标签措辞） |
| F-R51-3 | S-F-低5 | 比较页年度表格上方加一行（`.comparison-reference`，正文样式）：`Deltas (+ and %) are measured against {Study 名} ({run id}), the first Run ticked. To measure against another Run, clear the selection and tick that Run first.`。参照仍是第一个勾选的 Run，不新增选择控件 | 原来不说明参照；新增选择控件超出规格 | 是（是否要参照选择器） |
| F-R51-4 | S-F-低1、S-F-低6、S-F-低3 | 映射审阅中 `映射 SHA` 改为 `列与单位映射 SHA`，下方 `small` 一行说明时间戳声明不在此 SHA 内、记录在时间戳报告和绑定中；审阅有效期显示为本地时间到分钟（`2026-10-08 00:50 local time`）；包只读时映射编辑器不再显示“正在核对当前包的映射目录…”，改为“当前不能映射 CSV，原因见下方。” | 同一文件两种日期读法得到同一 SHA 易误解；原始 ISO 串带微秒；只读时像在加载 | 否 |
| F-R51-5 | S-F-中3 | 映射编辑器需求说明句末加：`逐时数据（8,760 或 8,784 行，或时间戳间隔 60 分钟）的每个小时用于两个半小时，MWh/period 按每小时电量换算。` 审阅报告的警告列表中出现 `GF_MAPPING_HOURLY_DEMAND` 一条 | 需求原来不接受逐时数据，报告互相矛盾 | 否 |

## R5-2（复现角色最终验收的缺陷；DECISIONS A28）

以下按规格现有组件、token 与文案风格实现；规格没有覆盖的地方取最保守的做法，需设计方复核。

| # | 缺陷 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-R52-1 | R-中1 | 研究路径第 2 步“核对新研究”的 `dl` 中新增一项 `方法学口径`：口径名（Studies 编辑器单选项的同一文案 `Corrected (default)` / `Doctoral reproduction`）、下一行 profile id（`code`），再下一行 12px `--muted` 说明：`沿用基线 Study 的口径。要换用另一口径，请选一项该口径的基线，或在创建后到 Studies 编辑器的 Methodology 中更改并保存新版本。`。Runs 页 “What will run” 的 `project-summary` 在 Data pack 后新增 `Methodology` 一格（同一文案，悬停为 profile id）。研究路径**不加**口径选择控件 | 原来创建前、启动前都看不到口径；规格第 7 节把口径选择放在 StudyComposer，研究路径另加选择会绕过编辑器的白名单检查 | 是（是否要在研究路径中直接选择口径） |
| F-R52-2 | R-中2 | Runs 年度卡片 `result-domain-grid` 在 `Storage charge / discharge` 后新增 `Unused VRE (PSM boundary)`：`{x} MWh · {y}% of available`（与 VRE 页同一定义：各时段 max(可用 VRE − 接受 VRE, 0) 之和）；旧 Run 无此字段时写 `Not recorded`。比较页年度指标新增 `Unused VRE at the PSM boundary (MWh)` 与 `Unused VRE share of available VRE (%)`（沿用现有指标卡片），不受弃电归因证据门控。原三项 v2 归因指标保持 `Unavailable` | 比较页和卡片原来没有可用的物理弃电量，两口径最大的差异看不到 | 是（标签措辞） |
| F-R52-3 | R-低2 | 论文复现口径的 Run 未结束时：上下文条 `Raw invariants` 写 `Pending`（muted，悬停说明）；Callout 改为 info 色 `Annual results pending the raw-invariant check`，正文 `This reproduction Run is still running. …`，无按钮；年度结果区 pill 写 `Pending`，状态词用 `in_progress`；VRE 页 pill 与信息框写 `Pending` / `Annual VRE results pending`；结果查询面板的状态词为 `Running`（info）。后端 `result_publication` 仍为 `withheld`（年度资源照旧门控），`raw_invariants_status: "pending"`、`reason_code: GF_RESULTS_PENDING_RAW_INVARIANTS` | 准备阶段原来写“raw invariants were not evaluated”和 Withheld，像是结论 | 否 |
| F-R52-4 | R-低3 | Run 处于 queued / snapshotting / running / cancel_requested 时，Runs 页不显示“历史复现条件检查”和“从此 Run 的冻结输入创建独立 Study”两块面板（原来只是禁用） | 两块面板只对已结束的 Run 有意义 | 否 |
| F-R52-5 | R-低1 | Market replay、VRE、Network & redispatch、Network & water 页按 Run 的 id、状态和已完成年数重新加载证据，不再随每次轮询重载；Run 尚在冻结输入（queued / snapshotting）时，Market replay 显示 `The Run is still preparing` 空状态，Inspect 的 planning / market 页签显示同义 info-box，均不发请求 | 准备期间每 2 s 一个 404 | 否 |
| F-R52-6 | R-低4 | 年度卡片 Planning evolution 的 `Active` 改为 `Active before admission`，其后新增 `Admitted this year: {n}`；整行悬停说明 Inspect 的年末 Active = 两者之和 | 卡片与 Inspect 的 Active 口径不同（规划步骤后 vs 年末），原来没有说明 | 是（标签措辞） |
| F-R52-7 | R-低6 | Inspect 规划表的 Project 列在名称等于 ID 时只显示一次；生命周期事件表在本页没有任何阶段转换记录时（v2 项目索引不记录 from/to）不显示 Transition 列 | 同一 ID 显示两次；整列 “- -> -” | 否 |
| F-R52-8 | R-低7 | Artifacts 页签中，未选择任何扩展的 Run 只显示一句 `This Run selected no optional extensions, so it has no extension results.`，不再列出 “Not recorded” 的身份格；VRE 页 v2 归因查询面板在结果 `unavailable` 或 Run 未结束时不显示来源身份格，只显示状态说明 | 原来把“没有扩展/没有归因来源”显示成证据缺失 | 否 |
| F-R52-9 | R-低10 | Market replay 窗口卡的 `Accepted supply` 数值下加一行（沿用 `.window-clock-note`）：修正口径 `Full node: covers demand plus storage charge, exports and flexible load.`，论文口径 `Source-classified node: storage charged from pre-balancing surplus is outside this figure.`，未知 `Balance boundary not recorded.`；悬停为边界公式。后端 dispatch timeline 新增 `accepted_supply_boundary` | 同一标签在两口径下统计边界不同，原来没有说明 | 是（文案） |
| F-R52-10 | R-低11 | 研究路径创建按钮因名称为空而禁用时，按钮下方加一行 13px `--muted`：`先在第 {n} 步填写新 Study 名称，才能创建。`（按钮 `aria-describedby` 指向它）；不自动填默认名称 | 按钮变灰没有原因 | 否 |
| F-R52-11 | R-低13 | Runs 空状态正文改为 `Choose a scope under Check for, check readiness, then run it. Wiring checks are quick; full scopes compute every model year.` | 原文“start with two full years”与默认 scope 不符 | 否 |
| F-R52-12 | R-中2 复审 | 比较页标签表新增 `pre_balancing_excess_mwh`：`Pre-balancing excess, reported separately (MWh)`；该指标无值时写 `Not applicable`（只有论文口径账本有独立的预平衡阶段）。跨口径比较时 unused VRE 两项与该项的差值不显示，沿用现有 `comparison-metric-withheld` 段落写后端给出的原因（`Delta withheld: Unused VRE is measured at different PSM boundaries (...); the doctoral pre-balancing excess is reported separately.`）。无新组件 | 复审指出两种口径在不同边界测 accepted VRE，差值不是同一量 | 否 |

## R5-3（改函数角色最终验收的缺陷；DECISIONS A28）

以下按规格现有组件、token 与文案风格实现；规格没有覆盖的地方取最保守的做法，需设计方复核。

| # | 缺陷 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-R53-1 | 中2 | 隔离面板 Disable 后的提示条在原句后加一句：`Its other manifest was moved out of the scanned folder: modules/disabled-manifests/modules/{文件}.`（多份时用复数）。面板、按钮、确认框不变；后端在停用时把同一 ID 的其他清单移到 `disabled-manifests/modules/` | 原来点副本行的 Disable 会留下副本，界面无法恢复 | 否 |
| F-R53-2 | 低1 | 方法升级确认保存后，“Saved as a new revision (revision N)…” 提示不再被随后的 readiness 复查清掉；readiness 的修复建议改为 `Press Check readiness again: VALUE lists the changes for your confirmation and saves them as a new revision of this Study.`，不再给出 API 路径 | 原建议指向不存在的入口，确认后看不到已保存修订 | 否 |
| F-R53-3 | 低2 | 起止年份相同的 Study，Runs 页 Check for 下拉框不列出 `Two-year hand-off check` 与 `Two full model years`（冻结恢复要求的范围除外） | 选了必然被 readiness 拒绝 | 否 |
| F-R53-4 | 低6 | Modules 页标题徽标改为 `{ready} of {total} ready · {n} experimental`（有实验性模块时） | 实验性模块计入分母却从不算 ready，原来没有说明 | 是（措辞） |

## R5-4（加功能角色最终验收的缺陷；DECISIONS A28）

以下按规格现有组件、token 与文案风格实现；规格没有覆盖的地方取最保守的做法，需设计方复核。

| # | 缺陷 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-R54-1 | F-中2 | Modules 的 “Open independent Study draft” 生成默认名称时，若 `{来源 Study 名} · extension study` 推导出的 Study ID 已被占用，依次加 ` 2`、` 3`…（ID 推导与后端 `slug` 一致，超长名称先截短再加序号）。名称输入框不变，用户仍可改名。后端对“无基修订、ID 已存在”的保存改报 409 `GF_STUDY_ID_EXISTS`：`A Study with ID … already exists (…). Give this Study another name to save it as a new Study, or open the existing Study and use Edit as new revision.`，页面照原样在提示条显示 | 原来重名时报 “revision conflict… reload”，按提示重载会丢掉草稿 | 否 |
| F-R54-2 | F-低4 | Data 页在 “Current unsaved Study draft” 语境（且不是在编辑已保存 Study）时，顶部语境条显示与 Studies 页相同的 `Independent Study draft · {名称} · Review and save to create a new Study.`，不再显示 “Selected saved Study … Editing is saved as a new revision.”。“Input contract for” 下拉框仍列出全部 Study（它是选择器） | 草稿状态下被误认为在修改来源 Study | 否 |
| F-R54-3 | F-低1 | 隔离面板 Disable 确认框对扩展改为 `Disable {id}? Studies that select this extension cannot run until it is enabled again or they deselect it (saved as a new revision).`（模块不变）；readiness 对停用/隔离的扩展建议 `deselect the extension in the Study (saved as a new revision)`，模块与扩展混合时两者都写 | 扩展不能被“换成另一个 module” | 否 |
| F-R54-4 | F-低3 | 扩展卡片被 Study 引用时的说明改为 `Referenced by N saved Studies; disabling here is blocked. If it is quarantined, Disabled and quarantined can still disable it so the Studies can be repaired.`；两处规则本身不变 | 两处规则不同但卡片没有说明 | 是（措辞） |
| F-R54-5 | F-中3 | 扩展编写台高级清单说明末尾加一句 `A Run records the initialize state and the after_psm artifacts only; see the README for the other hooks.` | 手册与界面未说明哪些钩子输出会被记录 | 否 |
