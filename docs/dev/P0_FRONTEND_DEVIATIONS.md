# P0 前端实现与设计规格的偏差记录（P0_FRONTEND_DEVIATIONS）

依据：`docs/dev/P0_FRONTEND_DESIGN_SPEC.md`。每条写明规格条目、实际实现、原因与是否需要设计方确认。没有偏差的条目不列出。

## P0-1（第 8 节：安全相关的前端改动）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-P01-1 | 网关返回 403 或 421（令牌缺失、Host 错误）时显示整页说明 | 触发条件为：421；403 且错误码属于网关/会话类（`GF_GATEWAY_CROSS_SITE`、`GF_GATEWAY_ORIGIN_REJECTED`、`GF_BROWSER_ORIGIN_REJECTED`、`GF_SESSION_*`）；**以及 502 且错误码为 `GF_GATEWAY_SESSION_MISMATCH`**（网关读到的令牌被 API 拒绝）。502 `GF_GATEWAY_SESSION_UNAVAILABLE`（会话文件不存在）**不**触发整页：它通常表示引擎还在启动或已停止，侧栏显示原有的 “Model service offline” 与 Retry；`GF_GATEWAY_UPSTREAM_UNAVAILABLE` 与业务 403 同样不触发 | 网关设计（计划 4.1 方案第 1 点）把“令牌不匹配”表达为 502 `GF_GATEWAY_SESSION_MISMATCH`，不是 403；若只按 403 判断，规格想覆盖的“未经启动器打开”场景显示不出来。会话文件缺失若也触发整页，后端启动稍慢时页面会卡在整页说明（e2e happy-path 实测），因此排除。判定集中在 `app/features/shared/api.ts` 的 `isLauncherAccessFailure` | 是（触发集合） |
| F-P01-2 | 整页说明由网页显示 | Host 错误（421）时浏览器根本拿不到 VALUE 页面，因此网关对**页面请求**的 421 直接返回同文案的静态 HTML（标题与正文逐字相同，内联样式，CSP `default-src 'none'`）；对 `/api` 请求仍返回 JSON。页面内的整页组件 `OpenFromLauncher` 用于页面已加载、但 API 被拒的情形 | 421 发生在页面加载之前，React 组件无法渲染 | 否（文案与规格一致） |
| F-P01-3 | 整页说明仅在初次加载时出现？（规格未写明） | 只在 `refresh()`（加载/重试 workspace）收到上述响应时切换为整页；其他请求（如单个 Run 详情）不切换 | 避免一次偶发失败把整个工作台替换掉；workspace 是每个视图的前提 | 是 |

## X0 S10b（Q14 年度结果门控；交给 m2-ui 线）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-X0-1 | 4.2 只给年度卡片加 `Withheld` pill；4.5 VRE 页、4.6 网络页没有 Q14 门控 | 门控在服务端：withheld 的 Run 请求 `market/vre-summary`、`planning/summary`、`domains/network/summary`、`domains/expansion/summary`、`network-redispatch/annual` 得到 409 `{status:'withheld', reason_code, error, available_in}`；`results/vre-curtailment?resolution=annual` 得到 200 `status:'withheld'`、`items:[]`。现有页面因此显示错误框（文案为 `error`），不显示年度数 | 只按规格在卡片上门控，VRE 页与网络页仍会显示 doctoral 年度数，违反 Q14（复审意见）。m2-ui 线应在这些页面识别 `status==='withheld'`（或 409 体中的 `status`），改用 4.2 的 `Withheld` Callout（文案与 4.2 相同，附 Inspect/导出入口），而不是错误框 | 是（4.5/4.6 的 Withheld 展示需设计方补充） |
