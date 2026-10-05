# P0 前端实现与设计规格的偏差记录（P0_FRONTEND_DEVIATIONS）

依据：`docs/dev/P0_FRONTEND_DESIGN_SPEC.md`。每条写明规格条目、实际实现、原因与是否需要设计方确认。没有偏差的条目不列出。

## P0-1（第 8 节：安全相关的前端改动）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-P01-1 | 网关返回 403 或 421（令牌缺失、Host 错误）时显示整页说明 | 触发条件为：421；403 且错误码属于网关/会话类（`GF_GATEWAY_CROSS_SITE`、`GF_GATEWAY_ORIGIN_REJECTED`、`GF_BROWSER_ORIGIN_REJECTED`、`GF_SESSION_*`）；**以及 502 且错误码为 `GF_GATEWAY_SESSION_MISMATCH`**（网关读到的令牌被 API 拒绝）。502 `GF_GATEWAY_SESSION_UNAVAILABLE`（会话文件不存在）**不**触发整页：它通常表示引擎还在启动或已停止，侧栏显示原有的 “Model service offline” 与 Retry；`GF_GATEWAY_UPSTREAM_UNAVAILABLE` 与业务 403 同样不触发 | 网关设计（计划 4.1 方案第 1 点）把“令牌不匹配”表达为 502 `GF_GATEWAY_SESSION_MISMATCH`，不是 403；若只按 403 判断，规格想覆盖的“未经启动器打开”场景显示不出来。会话文件缺失若也触发整页，后端启动稍慢时页面会卡在整页说明（e2e happy-path 实测），因此排除。判定集中在 `app/features/shared/api.ts` 的 `isLauncherAccessFailure` | 是（触发集合） |
| F-P01-2 | 整页说明由网页显示 | Host 错误（421）时浏览器根本拿不到 VALUE 页面，因此网关对**页面请求**的 421 直接返回同文案的静态 HTML（标题与正文逐字相同，内联样式，CSP `default-src 'none'`）；对 `/api` 请求仍返回 JSON。页面内的整页组件 `OpenFromLauncher` 用于页面已加载、但 API 被拒的情形 | 421 发生在页面加载之前，React 组件无法渲染 | 否（文案与规格一致） |
| F-P01-3 | 整页说明仅在初次加载时出现？（规格未写明） | 只在 `refresh()`（加载/重试 workspace）收到上述响应时切换为整页；其他请求（如单个 Run 详情）不切换 | 避免一次偶发失败把整个工作台替换掉；workspace 是每个视图的前提 | 是 |

## P0-8a（第 4.6 节：网络页；M2 lane m2-net）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-P08-1 | 4.6 网络页：可靠性数值用统一格式化（<0.01 MWh 不显示为 0）、运行期 fallback 审计超阈值时顶部 caution Callout `Spatially indicative: {x}% of {tech} capacity fell back to {zone}.` | 本 lane 只交付后端字段与 TS 类型：`known_defects`、`load_shedding_reporting_threshold_mwh`、`numerical_residual_unserved_mwh`（年度简报）、`runtime_fallback_audit`（能力接口，含 `spatially_indicative_technologies` 的 year/technology/fraction/zone，足以拼出规格文案），`networkRedispatch.ts` 增加对应可选类型。`NetworkRedispatchView.tsx` 未改 | 冲突热点 C11 规定 P0-8 的网络页改动放在 P0-9 S6 之后；`Callout` 与 `format.ts` 由并行的 P0-9 lane 新建，本分支上尚不存在，自行实现会与设计方的组件重复 | 是：集成者在 P0-9 S6 合入后补一个提交，用 `Callout`（caution）与 `formatEnergy` 渲染上述字段 |
| F-P08-2 | 规格未覆盖 SolverSettingsEditor | 历史合同（v2、v3）显示 `Historical {v2 / v3 GBP 1 lock} policy` 徽章；升级说明框里新增一张只读对照表（Setting / Recorded / Current v4），按钮文案改为 `Use current v4 policy`；当前合同徽章改为 `Built-in v4 default settings` / `Custom v4 settings`。只用已有的 `Badge`、`info-box` 样式，没有新增颜色或字号 | P0-8 S5 要求升级前预览差异（Q13 method_upgrade_required）；原文案写死 “£1 policy”，在 v4 下会误导 | 是：文案与表格样式 |
