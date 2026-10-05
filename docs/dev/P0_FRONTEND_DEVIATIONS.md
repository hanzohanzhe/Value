# P0 前端实现与设计规格的偏差记录（P0_FRONTEND_DEVIATIONS）

依据：`docs/dev/P0_FRONTEND_DESIGN_SPEC.md`。每条写明规格条目、实际实现、原因与是否需要设计方确认。没有偏差的条目不列出。

## P0-1（第 8 节：安全相关的前端改动）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-P01-1 | 网关返回 403 或 421（令牌缺失、Host 错误）时显示整页说明 | 触发条件为：421；403 且错误码属于网关/会话类（`GF_GATEWAY_CROSS_SITE`、`GF_GATEWAY_ORIGIN_REJECTED`、`GF_BROWSER_ORIGIN_REJECTED`、`GF_SESSION_*`）；**以及 502 且错误码为 `GF_GATEWAY_SESSION_UNAVAILABLE` / `GF_GATEWAY_SESSION_MISMATCH`**。其他 403/502（例如业务 403、后端未启动的 `GF_GATEWAY_UPSTREAM_UNAVAILABLE`）不触发整页，仍走原有的 “Model service offline” 侧栏状态 | 网关设计（计划 4.1 方案第 1 点）把“令牌缺失/不匹配”表达为 502 `GF_GATEWAY_SESSION_*`，不是 403；若只按 403 判断，规格想覆盖的“未经启动器打开”场景反而显示不出来。判定集中在 `app/features/shared/api.ts` 的 `isLauncherAccessFailure` | 是（触发集合） |
| F-P01-2 | 整页说明由网页显示 | Host 错误（421）时浏览器根本拿不到 VALUE 页面，因此网关对**页面请求**的 421 直接返回同文案的静态 HTML（标题与正文逐字相同，内联样式，CSP `default-src 'none'`）；对 `/api` 请求仍返回 JSON。页面内的整页组件 `OpenFromLauncher` 用于页面已加载、但 API 被拒的情形 | 421 发生在页面加载之前，React 组件无法渲染 | 否（文案与规格一致） |
| F-P01-3 | 整页说明仅在初次加载时出现？（规格未写明） | 只在 `refresh()`（加载/重试 workspace）收到上述响应时切换为整页；其他请求（如单个 Run 详情）不切换 | 避免一次偶发失败把整个工作台替换掉；workspace 是每个视图的前提 | 是 |
