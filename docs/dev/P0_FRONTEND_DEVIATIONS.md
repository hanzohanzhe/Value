# P0 前端实现与设计规格的偏差记录（P0_FRONTEND_DEVIATIONS）

依据：`docs/dev/P0_FRONTEND_DESIGN_SPEC.md`。每条写明规格条目、实际实现、原因与是否需要设计方确认。没有偏差的条目不列出。

## P0-1（第 8 节：安全相关的前端改动）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-P01-1 | 网关返回 403 或 421（令牌缺失、Host 错误）时显示整页说明 | 触发条件为：421；403 且错误码属于网关/会话类（`GF_GATEWAY_CROSS_SITE`、`GF_GATEWAY_ORIGIN_REJECTED`、`GF_BROWSER_ORIGIN_REJECTED`、`GF_SESSION_*`）；**以及 502 且错误码为 `GF_GATEWAY_SESSION_MISMATCH`**（网关读到的令牌被 API 拒绝）。502 `GF_GATEWAY_SESSION_UNAVAILABLE`（会话文件不存在）**不**触发整页：它通常表示引擎还在启动或已停止，侧栏显示原有的 “Model service offline” 与 Retry；`GF_GATEWAY_UPSTREAM_UNAVAILABLE` 与业务 403 同样不触发 | 网关设计（计划 4.1 方案第 1 点）把“令牌不匹配”表达为 502 `GF_GATEWAY_SESSION_MISMATCH`，不是 403；若只按 403 判断，规格想覆盖的“未经启动器打开”场景显示不出来。会话文件缺失若也触发整页，后端启动稍慢时页面会卡在整页说明（e2e happy-path 实测），因此排除。判定集中在 `app/features/shared/api.ts` 的 `isLauncherAccessFailure` | 是（触发集合） |
| F-P01-2 | 整页说明由网页显示 | Host 错误（421）时浏览器根本拿不到 VALUE 页面，因此网关对**页面请求**的 421 直接返回同文案的静态 HTML（标题与正文逐字相同，内联样式，CSP `default-src 'none'`）；对 `/api` 请求仍返回 JSON。页面内的整页组件 `OpenFromLauncher` 用于页面已加载、但 API 被拒的情形 | 421 发生在页面加载之前，React 组件无法渲染 | 否（文案与规格一致） |
| F-P01-3 | 整页说明仅在初次加载时出现？（规格未写明） | 只在 `refresh()`（加载/重试 workspace）收到上述响应时切换为整页；其他请求（如单个 Run 详情）不切换 | 避免一次偶发失败把整个工作台替换掉；workspace 是每个视图的前提 | 是 |

## P0-9 / P0-2 S9 / P0-3 S8（M2-P0-9：第 1、3–6 节）

| # | 规格 | 实现 | 原因 | 待确认 |
|---|---|---|---|---|
| F-P09-1 | 1.2：`formatNumber` 缺失时返回 `null` | `shared/format.ts` 的 `formatNumber` 返回 `null`；保留签名的 `presentation.tsx` 版本对缺失返回状态词 `—`（`VALUE_STATES.missing`） | 规格要求旧签名不变，旧调用方需要字符串；计划 6.9 的测试写的是 `formatNumber(undefined)='—'`，两者在不同层同时满足 | 否 |
| F-P09-2 | 1.2：非零小值显示 `<0.01` / `>-0.01`；`formatMoney(999999.9)` 显示 `£1.00m` | 按规格实现（`formatNumber(-0.001)` 为 `>-0.01`，金额 k/m/bn 段保留 2–3 位小数：`£1.00m`、`£12.346bn`、`£1.234k`）。负数写作 `-£1.234k`，亚便士写作 `<£0.01` | 计划 6.9 的手算表写的是 `formatNumber(-0.001)='0'`、`formatMoney(999999.9)='£1m'`，与规格冲突；按规格（设计方）执行 | 是（计划测试表需同步） |
| F-P09-3 | 3.1：窗口行写 `(UTC)` | 写作 `({timezone} model time)`，取自读模型的 `timezone`（当前为 Europe/London）；网络页事件列表表头为 `Start (model date & time)` | 账本时间戳是固定 365 天日历上的本地模型时间，不是 UTC；标成 UTC 会误导 | 是 |
| F-P09-4 | 3.1/3.3/4.4：shortfall、stress period、stress band、`stress (supply < demand)` 类型 | 窗口卡显示 `Shortfall: Not recorded`；`shortfall_mwh`/`stress_periods` 字段一到即显示数值与 amber pill，图上画 4px amber 带并加图例；可靠性列表目前只有 `lost load (network)` 一类 | A2 的后端字段在 M4 落地（任务说明：缺失时显示 Not recorded）；前端不做减法 | 否（M4 接入后复核） |
| F-P09-5 | 4.2：非 Complete 时不显示年度合计 | 后端给出 coverage 时严格执行；**后端没有给出 coverage（旧后端）时**，合计照常显示，pill 为 `Coverage not recorded`（muted） | 原则 3「不确定就降级」：降级的是标签而不是隐藏数值；同时保持旧 mock 的 e2e 不被整体改写 | 是 |
| F-P09-6 | 4.2：`Withheld` pill（复现口径未通过不变量，Q14） | `coveragePill(…, { withheld: true })` 已就绪，但当前没有后端字段可读，界面不会出现 Withheld | 复现口径的发布判定由 X0/M4 提供字段；不臆造字段名 | 是（需约定字段） |
| F-P09-7 | 4.3：修正口径径流水电兼容资本的 memo 行 | 当 Run 指标中有 `ror_hydro_compatibility_capital_gbp` 时在构成表末尾列出（不计入头条、不画进条形）；当前后端没有该字段 | 该数值属于修正口径（P0-7/X0），字段名先按此约定，需对方实现时采用 | 是（字段名） |
| F-P09-8 | 4.6：运行期 fallback 审计 Callout | 未实现 | 依赖 P0-8 S12 的后端字段，接口未定 | 是（P0-8 交付后补） |
| F-P09-9 | 4.6：P0-8b 后表头改为 `Boundary marginal value (£/MWh)` | 仍为 `Diagnostic marginal value`；值为 null 时显示 `Not computed` | P0-8b 尚未合入 | 否 |
| F-P09-10 | 1.2 / 计划 S1：`RunContextBar.tsx:27`、`Value101Learn.tsx:124` 改用共享格式化 | 未改，列入 `toLocaleString` 白名单 | 两处都是整数周期数，不存在缺失变 0；`RunContextBar` 属 X0 S12（并行 lane 在改），避免冲突 | 否 |
| F-P09-11 | 5：`Mark as lost` 二次确认 | 浏览器确认框 + 前端自动带上精确 run ID（API 的确认门） | 规格只要求二次确认；API 的安静期门仍由后端执行，拒绝时显示错误码 | 否 |
| F-P09-12 | 5：`Backend offline` 在连续失败 3 次后 | 实现如此；第一次失败即显示 `Backend degraded` 与 Retry，轮询 2 s 起翻倍至 30 s。`e2e/happy-path.spec.ts` 的离线断言改为匹配 `Backend (degraded|offline)`（该 spec 需真实服务，本次未运行） | 规格 | 否 |
| F-P09-13 | 9.8：375 px 不引起页面级横向滚动 | 只断言新组件自身不横向溢出（窗口卡、隔离面板）；旧布局（252 px 侧栏网格）在 375 px 的页面级溢出不在本轮 | 做法一不改旧元素样式 | 是 |
| F-P09-14 | 6：Disable 确认 | 使用浏览器确认框（文案与规格逐字一致），未用 `<dialog>` | 规格第 6 节未指定对话框形式（`<dialog>` 是第 7 节迁移确认的要求） | 否 |
| F-P09-15 | 10：截图用 PNG | 用 JPEG（质量 55，整页），共 14 张约 2.7 MB，放在 `docs/dev/p0-ui-screens/` | 控制仓库体积；来源是 scratch 实例（端口 18966/18967）上真实的 VALUE 101 day Run | 否 |
