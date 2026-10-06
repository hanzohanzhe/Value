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
| F-P09-3 | 3.1：窗口行写 `(UTC)` | 写作 `({timezone} model time)`，取自读模型的 `timezone`（当前为 Europe/London）；网络页事件列表表头为 `Start (model date & time)` | 账本时间戳是固定 365 天日历上的本地模型时间，不是 UTC；标成 UTC 会误导 | 是 |
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
