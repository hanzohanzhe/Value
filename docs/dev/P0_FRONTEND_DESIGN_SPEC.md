# VALUE P0 前端设计规格（做法一）

- 作者：Claude（前端设计）
- 实现：Sonnet 代理，按本规格编码
- 日期：2026-10-04
- 依据：
  - `VALUE_fix_decisions_2026-10-04.md`（决策记录，优先级最高）
  - `VALUE_fix_plan_P0_2026-10-04.md` 第 4.9 节（P0-9）、X0 S12、P0-2 S9、P0-3 S8、P0-1 S9
  - 对本机 0.6.0-alpha.2 界面的实测

> **范围红线（做法一）**
> 本轮只修「让读者读错结果」的地方，并加入新机制需要的最小界面，包括口径、验证、stress event、隔离、生命周期和迁移确认。
> 不重做视觉体系，不拆分 page.tsx 的整体结构，不加 i18n 框架，不调整全局字号。这些属于做法二，须等作者下令。
>
> 新增元素必须遵守本规格的样式约定（第 1.3 节），但不得顺手改动旧元素的样式。
> 如果实现中发现规格无法满足，停下来写进 `docs/dev/P0_FRONTEND_DEVIATIONS.md`，由设计方裁决，不要自行发挥。

---

## 0. 设计原则

1. **一个数字只能是真值或状态，二者择一。** 界面上的每个数值槽位，要么显示后端记录的真实值并标明口径，要么显示一个**明确的状态词**（见 1.1）。不允许出现由缺失值、未建模或字段名不匹配造成的 0。
2. **口径永远可见。** 凡是显示 Run 结果的视图，顶部 RunContextBar 都必须显示方法学口径徽章和验证状态。用户不需要点开详情，就能知道自己看的是「修正口径」还是「论文复现口径」，以及结果是否通过能量平衡验证。
3. **不确定就降级，不要美化。** 后端没有给出口径字段时（旧后端或旧 Run），显示 `basis not recorded`，不要猜。
4. **严重程度只用三种颜色，语义固定：**
   - 红（`--red`）：结果无效或验证失败；
   - 琥珀（`--amber`）：需要注意，包括部分覆盖、复现口径、已知偏差、stress event、旧版结果；
   - 蓝绿（`--teal`）：通过。
   - 蓝色只用于中性信息和链接。不得新增其他强调色。
5. **文案用短句和动词，说明「这意味着什么」和「下一步去哪」。** 每个阻断或降级状态都要给出一个可点击的下一步，例如「Open in Inspect」「Export ledger」「Review changes」。

---

## 1. 共享基础（所有包都依赖，最先实现）

### 1.1 状态词表（`app/features/shared/valueStates.ts`，新文件）

用一个 TS 联合类型统一定义，组件只能从这里取文案：

| key | 显示文本（en） | 何时使用 | tone |
|---|---|---|---|
| `missing` | `—` | 字段缺失，没有更多信息 | muted |
| `not_recorded` | `Not recorded` | 旧 Run 没有记录该字段 | muted |
| `not_modelled` | `Not modelled` | 该口径或模块不建模此项，例如 native 路径的容量机制成本 | muted |
| `not_evaluated` | `Not evaluated` | 可以计算，但本 Run 没有计算，例如单位成本的分母缺失 | muted |
| `not_computed` | `Not computed` | 实现尚未提供，例如 P0-8b 之前的边界影子价格 | muted |
| `partial_year` | `Partial year · {coverage}%` | 年度覆盖不完整 | amber |
| `non_annual` | `Non-annual run` | 非年度模式，如 smoke、101_day、validation_24h | amber |
| `in_progress` | `Running` | 进行中 | blue |
| `unavailable` | `Unavailable` | 证据表为空，但结果本身不是 invalid | muted |
| `invalid` | `Invalid` | 结果自相矛盾或年份集合不符 | red |
| `withheld` | `Withheld` | 按规则不在结果页发布，例如复现口径未通过验证 | amber |
| `basis_not_recorded` | `basis not recorded` | 价格或成本的口径未知 | muted |

- 每个状态词都可以带 `title`（悬停提示），一句话说明原因，由后端的 reason code 映射得到。
- muted 文本用 `var(--muted)`，**不加删除线，不加斜体**。

### 1.2 统一格式化层（`app/features/shared/format.ts`，新文件；对应计划 P0-9 S1）

- `formatNumber(value, opts)`：
  - `value` 为 `null` 或 `undefined` 时**返回 `null`**，由调用方渲染状态词。禁止 `value ?? 0`。
  - 去掉负零。
  - 非零小值不得被四舍五入成 0：|x| 小于显示精度时，显示 `<0.01` 或 `>-0.01`。
- `formatEnergy(mwh)`：按数值自适应单位。
  - |x| < 1 MWh 显示 kWh，< 1e3 显示 MWh，< 1e6 显示 GWh，否则显示 TWh。
  - 3 位有效数字。
  - **同一张表或同一组 KPI 统一用该组最大值的单位**（提供 `formatEnergyGroup(values[])`）。
- `formatPower(mw)`：规则同上，使用 MW 和 GW。
- `formatMoney(gbp)`：先按目标精度四舍五入，再决定进位，因此 999,999.9 显示为 £1.00m。其余沿用 £k、£m、£bn。
- `formatPrice(gbpPerMwh, basis)`：返回 `{ value, label }`，label 见 3.2。
- 旧的 `presentation.tsx` 中的 `formatNumber` 和 `formatMoney` 改为转调 `format.ts`，保持导出签名，避免大面积改动；但 `?? 0` 行为必须移除。
- `frontend-guards.test.mjs`：扫描 `app/` 下 `?? 0)` 出现在格式化调用中的写法，以及 `/ 1e6` 加字面量 `"TWh"` 的写法，出现即失败。

### 1.3 新元素的样式约定（只适用于本轮新增的元素）

- 字号：正文不小于 13px，辅助说明不小于 12px。**不得使用 7–11px。**
- 颜色只用 `:root` 中已有的 token：
  - `--red` / `--red-soft`、`--amber` / `--amber-soft`、`--teal` / `--teal-soft`、`--blue` / `--blue-soft`；
  - `--ink`、`--muted`、`--line`、`--panel`。
- 新组件 `Callout`（`app/features/shared/Callout.tsx` 和 `callout.css`）：

  ```
  ┌─▌───────────────────────────────────────────────┐
  │ ▌ [icon] Title (14px, 600)                      │
  │ ▌ One or two sentences (13px, --ink)            │
  │ ▌ [Primary action]  [Secondary link]            │
  └─▌───────────────────────────────────────────────┘
  ```

  - 左侧 4px 色条，取 tone 主色；背景用 tone 的 soft 色；圆角 8px；内边距 12px 16px；
  - tone 取值：`danger` | `caution` | `ok` | `info`；
  - danger 和 caution 设 `role="alert"`（只在新出现时朗读），ok 和 info 设 `role="status"`；
  - 图标用纯 CSS 或内联 SVG（!、i、✓），不引入图标库。
- 新组件 `StatusPill`：高 22px，圆角 11px，12px 字，600 字重，内边距 0 9px；颜色同 tone。用于徽章和表格单元。**与旧的 `.badge` 并存，不替换旧 badge。**
- 所有新的交互元素都要有 `:focus-visible` 样式：`outline: 2px solid var(--blue); outline-offset: 2px`。

---

## 2. Run 上下文条：口径与验证（X0 S12 + P0-9 S11）

改造现有的 `RunContextBar.tsx`，不新建页面级结构。

### 2.1 线框

```
Selected Run · read-only source
Release R2 new forecast   release-r2-new--20261003-…
[Corrected (default)] or [Doctoral reproduction · 0.6.0-alpha.2]   ← StatusPill
Execution  passed │ Contract check  passed │ Energy balance  ● Failed  │ Stress events  ● 48 periods · 570.5 MWh
──────────────────────────────────────────────────────────
(Callout, conditional; see 2.3)
Run scope …（原样保留）
Frozen Study revision … (原样)
▸ Source identity details  (保留；在 dl 中新增两行：Methodology profile id、Profile catalogue SHA-256)
```

### 2.2 口径徽章（Q2）

| 后端 `methodology.profile_id` | 徽章文案 | tone | 悬停说明 |
|---|---|---|---|
| `value-corrected-*`（默认口径，具体 id 以 X0 目录为准） | `Corrected methodology (default)` | info | `Current default methodology with review fixes of 2026-10. Profile {id}.` |
| `doctoral-lineage-0.6.0a2` | `Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)` | caution | `Reproduces the thesis behaviour as implemented in VALUE 0.6.0-alpha.2, including declared deviations. Not an exact reproduction of the 2026-07-18 retained trajectory.` |
| 缺失（修复前的 Run） | `Methodology not recorded (pre-2026-10 run)` | muted | `This Run was produced before methodology profiles existed. See advisories.` |

- 徽章在窄屏（<600px）下换行，不截断。完整 id 放在 Source identity details 里。

### 2.3 验证状态与 Callout 规则（P0-4、Q14、A2）

状态条新增两个字段：

| 字段 | 值 → 显示 |
|---|---|
| Energy balance | `passed` 显示 ● Passed（teal）；`failed` 显示 ● Failed（red）；`report_only` 显示 ● Reported（amber，悬停提示「Residuals are reported, not yet enforced」）；`reproduction_with_declared_deviations` 显示 ● Declared deviations（amber）；`not_evaluated` 显示 Not evaluated（muted）；`superseded_pre_fix` 显示 ● Superseded（amber） |
| Stress events | 0 时显示 `None`（muted，**不能是绿色**，因为「没有压力事件」不等于验证通过）；大于 0 时显示 ● `{n} periods · {shortfall}`，amber，shortfall 用 formatEnergy；缺失时显示 Not recorded |

> 原有的 `Scientific validation` 字段**保留**。它与 Energy balance 是两件事：前者是总体结论，后者是独立对账。

Callout 规则如下。按优先级只显示一个；其余在条内用文字提示「+N more notices」，点开后展开列表。

1. **`energy_balance=failed` 且口径为 corrected**，tone=danger
   - 标题：`Energy balance check failed`
   - 正文：`The independent ledger check found {k} periods where supply and use do not reconcile (largest residual {x}). Treat results from this Run as unverified.`
   - 动作：`Open residuals in Inspect`
2. **口径为 doctoral，且年度结果被 withheld（Q14）**，tone=caution
   - 标题：`Annual results withheld for this reproduction run`
   - 正文：`Doctoral reproduction runs keep the thesis behaviour, including declared deviations, so they do not pass the physical energy-balance check. Annual results are therefore not published on result pages. The full ledger remains available.`
   - 动作：`Open in Inspect` · `Export ledger`
3. **`superseded_pre_fix`（修复前的旧 Run）**，tone=caution
   - 标题：`Produced before the 2026-10 review fixes`
   - 正文：`This Run's original validation status was "{original}". It was produced by a version with known issues; see the advisories that apply to it.`
   - 动作：`View advisories (n)`。点开后是一个列表，每条显示 advisory 标题、一句话说明和受影响的指标。
4. **stress event 大于 0**，tone=caution（不阻断）
   - 标题：`Supply fell short of demand in {n} periods`
   - 正文：`Total shortfall {mwh}. These are stress events: demand exceeded accepted supply. Dispatch was not altered; the shortfall is recorded as unserved energy.`
   - 动作：`Show stress events`，跳到 4.4 节的列表

- 修复前的旧 Run，不得把旧的 `passed` 显示成绿色。

---

## 3. Market replay（P0-9 S3–S4、Q6、A2）

### 3.1 窗口摘要卡（现有 Window/Demand/Physical supply/Storage charge/Price 一组）

新的顺序与文案：

```
Window              2025-01-01 00:00 → 2025-01-02 00:00 (UTC)
Demand              775.49 MWh
Accepted supply     204.94 MWh
Shortfall           570.55 MWh   ● 48 stress periods        ← 新增，>0 时 amber
Storage charge      240 MWh
Storage discharge   0 MWh                                    ← 新增（已有字段）
{price label}       £xx.x/MWh  (demand-weighted)             ← 见 3.2
```

- `Shortfall = max(0, demand − accepted supply − storage discharge + storage charge…)`。**前端不计算**，只显示后端 A2 新增的 `shortfall_mwh` 和 `stress_periods`；字段缺失时显示 `Not recorded`。不要用前端减法凑数。
- 「Physical supply」改名为「Accepted supply」，与后端口径一致。

### 3.2 价格标签（Q6）

| 后端 `price_basis` | 标签 | 悬停说明 |
|---|---|---|
| `average_period_cost` | `Average period cost` 后缀 `(£/MWh demand)` | `Total period cost divided by demand. Not a marginal clearing price.` |
| `national_ahead_clearing_price` | `National ahead clearing price` | `Uniform price set by the last accepted offer in the ahead stage.` |
| `balance_shadow_price` | `Balance shadow price` | `Dual value of the energy-balance constraint.` |
| `ahead_settlement_price` | `Ahead settlement price` | — |
| `not_declared` 或缺失 | `Price (basis not recorded)` | `This ledger does not declare what the price represents.` |

- 窗口级聚合时，标签前加 `Demand-weighted`。
- 选中时段的 merit order 图下方已有 `Marginal accepted offer £66.5/MWh`，**保留**。它和价格是两件事，不要合并。

### 3.3 调度堆叠图（R3-02、A2）

- 按后端 `role` 字段着色和堆叠：只有 `role=supply` 的流量进入堆叠。旧后端没有 role 时，使用前端兜底映射，规则写在 `dispatchView.ts` 中。
- **stress 标记**：stress period 在图上方画一条 4px 高的 amber 细带，与时段对齐。图例增加 `Stress event (shortfall)`。不画「缺电」柱，因为缺电不是一种供给。
- 需求线保持现状。堆叠顶部与需求线之间的差距，就是 stress 的可视化证据，不另加阴影。
- 空图时显示：`No supply flows recorded for this window` 加原因（reason code），不得留白。

### 3.4 Merit order 表

- 修改 `Technology` 列：显示后端规范技术名，例如 `offshore wind`。原始类名 `ExpensiverenewableGenerator` 移到悬停说明里，不再作为第二行灰字显示。
- 「Offer」列在 `price_basis` 为 average_period_cost 的 Run 中照常显示报价，这一点不受影响。

---

## 4. Runs 结果页、VRE、网络、可靠性

### 4.1 KPI 组（R3-21）

- 8 个 KPI 一律经 `formatEnergyGroup` 统一单位，不再写死 TWh。
- 每个 KPI 卡下方一行 12px 说明，写明覆盖范围：`{year}` 或 `{n} periods · non-annual`。

### 4.2 年度结果门控（F3-02、G1-10、Q14）

年度卡片头部用一个 StatusPill 显示覆盖状态：`Complete year`（teal）、`Partial year · 16.6%`（amber）、`Non-annual run`（amber）、`Withheld`（amber）。

- 非 Complete 时，**年度合计数字不显示**，替换为状态词，并给出一行解释和动作（Open in Inspect）。不能把部分年份的合计当作年度值展示。

### 4.3 成本构成（F3-04、P4-03）

- native 口径：只堆两段（operating 和 capital），标题旁注明 `includes VoLL` 或 `excludes VoLL`，以后端字段为准。
- 容量机制、脱碳机制：在构成表中显示 `Not modelled`，不画进堆叠条。
- 修正口径下径流水电的兼容资本（约 £10.96bn）不计入头条，在构成表末尾单列一行 `Memo: run-of-river hydro compatibility capital (excluded from headline)`。
- **堆叠条总长必须等于头条总成本**，由测试断言。
- 必须有图例。图例和条形用同一组颜色，从现有图表的颜色里选，不新增色板。

### 4.4 可靠性与 stress event（F3-07、A2）

- 列表改为**全年分页**，每页 50 条，按 `start_period` 数值排序。列：
  - `Start (date & time, UTC)`
  - `Periods`
  - `Shortfall`
  - `Type`：`stress (supply < demand)` 或 `lost load (network)`
  - `Replay →`，跳到 Market replay 的对应窗口
- 文案：
  - 标题：`Stress events and lost load — full year {year}`；
  - 空状态：`No stress events recorded in {year}.`，仅在覆盖为 Complete year 时允许出现这句；
  - 覆盖不完整时显示：`No stress events in the {coverage}% of {year} that has been computed.`
  - 删除「全年无失负荷」这类无条件表述。

### 4.5 VRE 页（R3-21、G1-08）

- 单位自适应。
- 事件分两组显示：`Unused VRE`，以及 `Excess + curtailment`，后者带 event_basis 说明。
- 缺失值处折线断开，不连到 0。

### 4.6 网络页（F3-05、R3-16、G1-07、P0-8a）

- 「Diagnostic marginal value」列：P0-8b 之前，后端给 `null` 加 `not_computed`，界面显示 `Not computed`。P0-8b 之后，显示对偶值，表头改为 `Boundary marginal value (£/MWh)`。
- 页面顶部加覆盖率横幅（复用 4.2 的 pill 和规则）。
- 结果查询区分 `Invalid`（红框）和 `Unavailable`（灰色说明）。红框只用于 invalid。
- 「Network & water」对分区 Run 不再说 `valid single-node`。按 Run 类型显示：`This Run uses the zonal network model. Open Network & redispatch →`。
- 运行期 fallback 审计（P0-8 S12）：fallback 占比超过阈值时，网络页顶部显示 caution Callout：`Spatially indicative: {x}% of {tech} capacity fell back to {zone}.`

---

## 5. 运行生命周期与后台状态（P0-3 S8、Q4）

- **后端 degraded**（`/api/health` 返回 degraded，或轮询失败）：
  - 侧栏底部的服务状态改为 `● Backend degraded`（amber），或 `● Backend offline`（red，连续失败 3 次后）。
  - 轮询按指数退避，最长 30 s。
  - 页面内容**保持可读**，不整页切换成离线页。
- **Run 状态新增：**
  - `worker exited`：`Run stopped unexpectedly (worker exited). You can resume from the last annual checkpoint.`，动作 `Resume`。若 resume 预检不可用，显示原因。
  - `worker lost`：`VALUE lost contact with this Run's worker (for example after a restart).`，动作 `Mark as lost`，需二次确认。
- **后台运行提示（Q4）**：顶栏在有 Run 运行时显示 `● {n} Run(s) running in background`，点击跳到 Runs。启动器关闭时的提示在启动器里实现，不在网页中。
- 进度：保留现有年度进度条。没有时段级进度时，文案从 `preparing the next annual state` 改为 `Computing year {y} (period-level progress not reported by this model)`。时段级进度条属于 P1，本轮不做。

---

## 6. 模块隔离（P0-2 S9）

Modules 页顶部，仅在有隔离项时显示，使用 caution Callout：

```
▌ ⚠ 1 external module quarantined
▌ VALUE started without it. Runs that need it cannot start until it is fixed or disabled.
▌ ┌──────────────────────────────────────────────────────────┐
▌ │ my-storage-module 1.2.0   Import failed: ModuleNotFoundError: …   [Disable] [Rescan] │
▌ └──────────────────────────────────────────────────────────┘
```

- 错误信息只显示首行，完整 traceback 折叠在 `details` 里，并且**不得显示绝对路径**：后端已做脱敏，前端再次检查不出现 `/home/`。
- `Disable` 需要确认。确认文案：`Disable {module}? Studies that use it will need another module before they can run.`

---

## 7. Study 迁移确认（X0 S11、Q13）

- **纯代码身份变化**：Study 卡片上显示一行 info 提示 `Updated to code identity {short} (no change to methods or results expected)`，不打断用户。
- **方法或数值变化**：用户点击 Run 或 Preflight 时，弹出模态对话框：
  - 标题：`This Study needs your confirmation before it runs`
  - 正文：`VALUE {version} changes how this Study is computed:`，后接 diff 列表，每行写明维度、旧值 → 新值，以及一句话说明影响。
  - 按钮：`Review and save as new revision`（主按钮）、`Cancel`
  - 对话框用原生 `<dialog>`，打开时焦点落在标题上，Esc 关闭；未确认时 Run 不启动。
- **StudyComposer 中的口径选择（Q3）**：在 Study 配置区加一个单选组 `Methodology`，两个选项：
  - `Corrected (default)`；
  - `Doctoral reproduction`，说明 `Locks thesis-era reference settings: legacy storage tariff, doctoral carbon factors, thesis-era modules and data packs only. External code is not allowed.`
  - 选中 Doctoral 时，不在白名单内的模块和数据包选项显示为禁用，并附原因。

---

## 8. 安全相关的前端改动（P0-1）

- 所有请求走同源 `/api/...`，删除 `apiOrigin` 属性链。这一步放在 M7 集成阶段，不在本节设计范围内。
- 网关返回 403 或 421（令牌缺失、Host 错误）时，显示整页说明，这是本轮唯一允许的整页错误：
  - 标题：`Open VALUE from its launcher`
  - 正文：`This page was not opened through the VALUE launcher, so it cannot talk to the local engine. Close it and start VALUE again with start-value (or the desktop shortcut).`
- 界面上任何地方都不得出现令牌字符串。

---

## 9. 验收清单（设计方验收，Sonnet 实现时逐条自测）

1. 以下任一视图中都搜不到 `£0/MWh`、`0 TWh`、`valid single-node`、`Result invalid`（适用于证据缺失的情形）、`Clearing price`（适用于 average_period_cost 的情形）：Market replay、VRE、Network & redispatch、Network & water、Runs、Inspect、Compare。
2. Release R2 这类缺电 Run 在 Market replay 的窗口卡中显示 `Shortfall` 和 stress period 数，状态条显示 Stress events，图上有 amber 细带。
3. doctoral 口径且被 withheld 的 Run：结果页出现 Withheld Callout，年度合计不出现，Inspect 和导出可用。
4. 修复前的旧 Run：显示 `Methodology not recorded` 和 `Superseded`，不显示绿色的 passed。
5. 6 个结果视图都能看到口径徽章（SSR 测试加 e2e）。
6. 新增元素没有小于 12px 的字号（CSS guard 测试只扫描新文件）。
7. 新组件可以用键盘操作，并有 focus-visible 样式；Callout 和 dialog 通过 axe 的 critical 和 serious 检查（只扫描新组件）。
8. 375px 宽度下，新组件不引起页面级横向滚动。
9. 前端不做任何物理量的减法或推算来「补」缺失值，测试 grep 守卫。

## 10. 交付给设计方复核的材料

- 每个视图在 1280px 和 375px 宽度下的截图，放在 `docs/dev/p0-ui-screens/`，使用 scratch 实例和 VALUE 101 Run。
- `docs/dev/P0_FRONTEND_DEVIATIONS.md`：记录与本规格不一致的地方，没有就写「无」。

---

## 11. 修复轮设计（四类用户测试后，2026-10-06，Claude）

继续遵守第 1.3 节的样式约定，以及第 0 节的原则。

### 11.1 Readiness 卡片（S-D1）
- **不再截断。** 问题按以下优先级分组：
  1. errors：始终展开；
  2. 数据 plausibility；
  3. 时间轴（chronology）；
  4. 其他数据警告；
  5. 适配器的 “unit is not declared”；
  6. 环境类问题。
- **组头：** `{组名} · {n}`，琥珀色或红色 StatusPill。errors 组和 plausibility 组默认展开，其余组默认折叠，展开按钮写 `Show {n}`。
- **组内去重：** 同一 code 只显示一次，并在后面注明 `×{n}`，悬停时列出全部对象。

### 11.2 数据包校验面板（S-D2，Data 页，每个数据包一张）
```
Validation        Structural ● Passed   Chronology ● 2 warnings   Plausibility ● 1 warning
Methodology use   Corrected ● Eligible   Doctoral reproduction ● Not eligible — not a thesis-era pack
[Show details ▾]   (逐层列出发现：code、对象、一句话说明)
```
- **配色：** Passed 为 teal；有 warning 为琥珀色；Failed 为红色；未评估为 muted 色、文字 `Not evaluated`。
- **替换旧文案：** 原来的 `25/25 required inputs ready` 改为 `25/25 inputs present · validation {最差状态}`。
- **数据来源：** `/api/data-packs/<id>/validation` 和 `plausibility_status`。

### 11.3 论文复现口径扣发的说明（R-D1）
- **Callout 正文写明真正失败的原始不变量：** `Annual results withheld: raw invariant "{名称}" failed ({n} rows).` 其后另起一句：
  - 命中声明偏差：`Matches declared deviation {DEV-ID}: {一句话}.`
  - 未命中：`No declared deviation explains it.`
- **状态条：** 仅在 doctoral 口径下增加字段 `Raw invariants`。全部通过显示 teal `● Passed`；有失败显示琥珀色 `● {k} failed`，悬停列出名称。`Energy balance` 字段保持不变。
- **`reproduction_conformant`：** 维持 teal `● Conformant`（第 2.3 节补入该值）。悬停说明强调“账闭合 ≠ 物理验证通过”。

### 11.4 隔离和停用后的出路（M-D3、M-D4、F-D3）
- **预检结果（M-D3）：** 预检报告即使缺少 `project_revision_sha256`，也必须显示后端返回的 errors，包括 `GF_PREFLIGHT_MODULE_QUARANTINED` 及其修复指引。有 errors 时 Run 按钮禁用，旁边注明原因。
- **停用项入口（M-D4、F-D3）：** Modules 页在列表下方始终保留 `Disabled and quarantined` 区，只要存在停用或隔离的模块或扩展就显示。每项提供 `Enable`、`Rescan`、`Remove` 三个按钮，`Remove` 需要二次确认。页头另有全局 `Rescan modules` 按钮。
- **Enable 失败时的提示：** 显示最新一次扫描的错误，不显示缓存的旧错误，并附 `Rescan` 按钮。

### 11.5 一日范围与扩展（F-D2）
- **预检：** 阻断级 error：`The one-day lesson runs the market step only, so the selected extension(s) {names} would not execute. Choose two-period or a longer scope, or deselect the extension(s).`
- **范围下拉框：** 选中扩展时，在一日选项后附注 `(extensions do not run)`。
- **比较页：** 不把这种情况判为方法改变。

### 11.6 映射编辑器防错（S-D4、S-D5）
- **时间戳列（S-D4）：** 新增可选的 `Timestamp column` 下拉框和 `Time zone` 下拉框（UTC / Europe/London）。选定后声明 `timestamp_column`，由时间轴层校验单调性、缺口和重复，错误逐行显示。
- **币种提示（S-D5）：** 列名含 `eur` 或 `€`，而 Currency 选的是 GBP 时，显示琥珀色行内提示 `Column name suggests EUR — confirm the currency.`。该提示不阻断。

### 11.7 原地修改模块源码（M-D2，作者决定：接受并记录）
- **预检：** 显示琥珀色 warning：`Module {id} source changed since install ({old8}… → {new8}…). Results will record the new source hash.`
- **比较页：** 沿用现有的“方法已改变”标记。
