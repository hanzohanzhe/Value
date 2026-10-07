# Energy balance, stress events and validation gates (P0-4 draft for methodology 0.4)

Status: draft written with the P0-4 S7-S8 construction (2026-10-06); the gate
reading of the doctoral profile updated for R4-1 (DECISIONS A26, 2026-10-08).  It replaces
the passage "Native retains both raw supply-demand residuals and compatibility
adjustments ..." of `national_alternatives.md` (en: the paragraph with
\(r_t^{raw}\) and \(a_t^{compat}\); zh: the paragraph starting
"Native 同时保存原始供需差额和兼容调整量") when the 0.4 edition is generated.
The 0.3 edition stays frozen (C26).  An English text and a Chinese text with
the same content follow.

## English

### What the 0.3 text got wrong

The 0.3 text defines the raw residual on the retained demand-serving boundary
\(r_t^{raw}=G_t+U_t-d_t-c_t^{accounted}\) and a compatibility adjustment
\(a_t^{compat}=-r_t^{raw}\) whenever \(|r_t^{raw}|>10^{-9}\) MWh.  The reported
residual \(r_t^{raw}+a_t^{compat}\) is therefore zero by construction and is no
evidence of an energy balance.  The adjustment had no cap, and the official
validator checked only completeness.  The retained boundary also leaves out
surplus that left the node outside the accepted supply (VRE surplus charged
into storage, exported or sent to electrolysis), so a non-zero raw residual
mixes four things: out-of-dispatch surplus, in-dispatch surplus spilled, a
hidden shortfall (P3-01) and a double count of must-run surplus in the
balancing stage of the thesis kernel (DEV-BAL-04, corrected in both profiles
by R4-1).

### Declared boundary and the raw residual

From P0-4 S6 the default PSM declares its balance boundary in the ledger
(`energy_balance_boundary`).  The doctoral rule set declares
`default_psm_surplus_node_v1`:

$$
r_t = S_t + B_t + U^{out}_t - W^{in}_t - D_t - C_t - E_t - X_t ,
$$

with accepted supply \(S_t\), recorded blackout \(B_t\), out-of-dispatch VRE
surplus routed to storage, export or electrolysis \(U^{out}_t\), in-dispatch
surplus finally spilled \(W^{in}_t\) (non-VRE spill, decision Q7), real demand
\(D_t\), storage charge \(C_t\), export \(E_t\) and flexible demand \(X_t\).  The
corrected rule set declares `native_corrected_full_node_v1`:
\(r_t = S_t + B_t - D_t - C_t - E_t - X_t - XS_t\) with the non-VRE spill
\(XS_t\).  Surplus routing is recorded per source class in `surplus_routing`.
The compatibility adjustment now absorbs numerical noise only:
\(a_t=-r_t\) when \(10^{-9}<|r_t|\le\tau_t\), otherwise 0, with
\(\tau_t=\max(10^{-6},10^{-9}\max(D_t,S_t))\) MWh for exact arithmetic
(\(10^{-5}\) and \(10^{-7}\) for LP solvers).  A physical imbalance stays
visible in \(r_t\).

### Stress events and the energy-balance account (decision A2)

Dispatch is not changed when the ahead stage cannot meet the forecast
(P3-01).  Instead, both profiles book the shortfall
\(u_t=\max(0,-(r_t-B_t))\) as unserved energy:

$$
\text{closing}_t = r_t - B_t + u_t .
$$

A period whose only defect is unmet demand closes (\(\text{closing}_t=0\)) and
is a **stress period**; contiguous stress periods of one year form a stress
event, and the annual summary reports the event count, stress periods and the
total shortfall.  A positive closing residual (supply recorded beyond every
use, such as a double count) remains an open period.

### Validation gates (P0-4 S7)

The scientific-validation report (v2) recomputes every status from executed
checks.  Three groups are gates:

* run invariants (period coverage, demand input reconciliation, generation
  cross-path, state chain);
* the energy balance: the account above plus ledger integrity (self-report
  consistency, surplus conservation, the annual adjustment share
  \(\sum|a_t|/\sum D_t\le10^{-6}\));
* storage throughput (after P0-6 S8): grid-side charge and discharge within
  rated power times the period length, no period that both charges and
  discharges a store, state of charge within \([0,E]\), and the audit identity
  of each store.

Under the default (corrected) profile any failed gate makes scientific
validation `failed` and annual economics are not published.  A stress period
is reported but is not a gate failure.

The frozen doctoral reproduction profile keeps the thesis settings.  Its
remaining declared deviations
(`gridform_core/data/methodology/declared_deviations.json`) are a definition
and evidence; none of them explains a gate failure:

| Deviation | Behaviour kept | Role |
|---|---|---|
| DEV-BAL-02 (P3-01) | hidden shortfall | evidence only (stress events, booked as unserved) |
| DEV-BAL-03 | stored energy discarded at a year end | evidence only (`storage_year_boundary`) |
| DEV-BAL-01 | thesis column semantics | definition of the surplus-node boundary |

The two thesis-kernel behaviours that used to explain gate failures were
implementation errors and are corrected in both profiles (R4-1, DECISIONS
A26; see `r41_kernel_corrections.md`): must-run nuclear surplus is no longer
counted twice in the balancing stage (`r41.must-run-surplus-counted-once`,
formerly DEV-BAL-04), and a store keeps one net position per period with its
rated power shared by the clearing stages (`p06.storage-net-per-period`,
formerly DEV-STO-01).  The thesis curtailment branch also no longer takes the
same down regulation twice (`r41.down-regulation-taken-once`), which
surplus conservation used to report as a failure on GBP1.

A gate that passes is `reproduction_conformant`; a failed gate is `failed`,
as is every failed run invariant (`reproduction_with_declared_deviations`
remains readable on reports written before R4-1).  Annual results of a
doctoral run appear on result pages only when all raw invariants pass
(decision Q14); otherwise they stay in Inspect and exports.

## 中文

### 0.3 版本的表述错在哪里

0.3 版本在保留的需求服务边界上定义原始残差 \(r_t^{raw}=G_t+U_t-d_t-c_t^{accounted}\)，并且只要 \(|r_t^{raw}|>10^{-9}\) MWh 就令兼容调整 \(a_t^{compat}=-r_t^{raw}\)。因此调整后的残差 \(r_t^{raw}+a_t^{compat}\) 按构造恒为 0，不能作为能量平衡的证据；调整量没有上限，官方校验器也只检查完整性。保留边界还漏掉了在接纳供给之外离开节点的盈余（VRE 盈余充入储能、出口或电解），所以非零的原始残差混合了四类量：调度外盈余、调度内盈余的弃置、被隐藏的缺电（P3-01），以及论文内核在平衡阶段对必发盈余的重复计入（DEV-BAL-04，R4-1 已在两个口径中修正）。

### 声明边界与原始残差

自 P0-4 S6 起，默认 PSM 在账本中声明平衡边界（`energy_balance_boundary`）。doctoral 规则集声明 `default_psm_surplus_node_v1`：

$$
r_t = S_t + B_t + U^{out}_t - W^{in}_t - D_t - C_t - E_t - X_t ,
$$

其中 \(S_t\) 为接纳供给，\(B_t\) 为记录的缺电，\(U^{out}_t\) 为调度外 VRE 盈余中流向储能、出口、电解的部分，\(W^{in}_t\) 为最终弃置的调度内盈余（非 VRE spill，决策 Q7），\(D_t\) 为真实需求，\(C_t\)、\(E_t\)、\(X_t\) 分别为储能充电、出口和柔性负荷。corrected 规则集声明 `native_corrected_full_node_v1`：\(r_t = S_t + B_t - D_t - C_t - E_t - X_t - XS_t\)，\(XS_t\) 为非 VRE spill。盈余按来源类别逐期记入 `surplus_routing`。兼容调整只吸收数值噪声：\(10^{-9}<|r_t|\le\tau_t\) 时 \(a_t=-r_t\)，否则为 0；精确算术的 \(\tau_t=\max(10^{-6},10^{-9}\max(D_t,S_t))\) MWh（LP 求解器为 \(10^{-5}\) 与 \(10^{-7}\)）。物理不平衡在 \(r_t\) 中保持可见。

### stress event 与能量平衡账（决策 A2）

日前阶段满足不了预测时（P3-01），调度不变。两个口径都把缺口 \(u_t=\max(0,-(r_t-B_t))\) 记为缺电量：

$$
\text{closing}_t = r_t - B_t + u_t .
$$

只有需求未满足这一种缺陷的时段闭合（\(\text{closing}_t=0\)），记为 **stress 时段**；同一年内连续的 stress 时段构成一个 stress event，年度汇总给出事件数、stress 时段数和总缺口。closing 为正（记录的供给超过全部用途，例如重复计入）的时段仍是未闭合时段。

### 验证门控（P0-4 S7）

科学验证报告（v2）的每个状态都由实际执行的检查重算。以下三组是 gate：

* run 不变量（时段覆盖、需求输入对账、发电跨路径核对、状态链）；
* 能量平衡：上述能量平衡账，加上账本完整性（自报一致、盈余守恒、年度调整量占比 \(\sum|a_t|/\sum D_t\le10^{-6}\)）；
* 储能吞吐（P0-6 S8 之后）：网侧充放电不超过额定功率乘时段长度、同一时段不对同一储能既充又放、荷电状态在 \([0,E]\) 内、每个储能的审计恒等式。

默认（corrected）口径下，任一 gate 失败，科学验证即为 `failed`，年度经济结果不发布。stress 时段只报告，不算 gate 失败。

冻结的 doctoral 复现口径保留论文设定。它剩下的已声明偏差（`gridform_core/data/methodology/declared_deviations.json`）只是定义和证据，都不解释 gate 失败：

| 偏差 | 保留的行为 | 作用 |
|---|---|---|
| DEV-BAL-02（P3-01） | 被隐藏的缺电 | 只作证据（stress event，记为缺电量） |
| DEV-BAL-03 | 年末丢弃储能存量 | 只作证据（`storage_year_boundary`） |
| DEV-BAL-01 | 论文的列语义 | surplus-node 边界的定义 |

过去用来解释 gate 失败的两项论文内核行为是实现错误，已在两个口径中修正（R4-1，决策 A26，见 `r41_kernel_corrections.md`）：平衡阶段不再把必发核电盈余计两次（`r41.must-run-surplus-counted-once`，原 DEV-BAL-04）；每个储能每个时段只有一个净头寸，各出清阶段共用额定功率（`p06.storage-net-per-period`，原 DEV-STO-01）。论文削减分支也不再把同一笔下调削两次（`r41.down-regulation-taken-once`），这一行为过去在 GBP1 上表现为盈余守恒失败。

gate 通过记为 `reproduction_conformant`；gate 失败记为 `failed`，任何 run 不变量失败也记为 `failed`（R4-1 之前写出的报告中的 `reproduction_with_declared_deviations` 仍可读）。doctoral 运行的年度结果只有在原始不变量全部通过时才在结果页发布（决策 Q14），否则只在 Inspect 和导出中提供。
