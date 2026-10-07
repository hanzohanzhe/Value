# GBP1 论文复现口径：surplus conservation 失败的调查（DECISIONS A15、A24）

日期：2026-10-07。分支 `fix/review-2026-10-04` @ f7a5f7a。对应 golden case：`D5`（GBP1 public1，2025 年，`doctoral-lineage-0.6.0a2`）。

本调查只读：没有改校验、偏差目录、内核或任何模型代码。为了逐步看清内核行为，在 scratch 里给内核函数 `store_service_three` 套了一层只记录不改值的包装。包装后的运行与正常运行的 golden 摘要逐列相同（2076 列，sha256 全部一致）。

## 1 结论

- **这是真实的能量不平衡，原因在论文内核本身，不是记账边界问题，也与核电 must-run 盈余无关。** 失败的 surplus routing 行有一个共同点：削减阶段从已接受供给 S 中实际拿走的电量，比内核记下的削减量多。多拿走的电没有任何去处，相应的需求就没有被满足。
- **机制。** `store_service_three` 中非 VRE 机组的下调分支有一个缺陷：`max_curtail_energy >= need_curtailed_energy` 时只 `break` 了内层循环，没有把 `need_curtailed_energy` 清零（当前文件第 1168、1283 行；35aadb3 第 1019、1126 行，代码相同）。外层循环于是继续往下走，又从风电里削掉同样的量。GBP1 的 `Hydro_natural_flow` 下调价为 0，排在所有风电之前，所以经常是先削水电、再把同样的量从海上风电削一遍。2025 年这样的时段有 563 个，其中 562 个实际下调量正好是记账量的 2 倍。
- **数字口径需要更正。** 此前报告里写的 “471 个时段、最大 991 MWh” 是 **包络（`period.envelope`）下界越界** 的统计，不是 surplus conservation 的统计。能量平衡门实际失败的检查是 `period.surplus_conservation`：修复后 **563 行**（全部为 `in_dispatch`），最大缺口 991.33 MWh，合计 217,140 MWh。471 个包络越界时段都在这 563 个时段之内，是同一个缺陷在包络检查下的表现。
- **35aadb3 同样如此。** 35aadb3 的账本没有 surplus routing 表，所以用轨迹与它逐位相同的 1e61e5e 复跑（见 `GBP1_DOCTORAL_BEFORE_AFTER.md` 第 4 节）：737 行失败，合计 274,187 MWh，其中包络越界 621 个时段。机制和分类与修复后完全相同。
- **这些时段已经计入 A2 缺电账。** 563 个时段全部是 stress 时段，A2 账已把多削的量记为未供电量，`period.balance_account` 通过。多削量占全年 A2 缺口（300,855 MWh）的 72%，占全年需求的 0.093%。因为 blackout 一直记为 0，内核自己的输出看不出这部分缺电。
- **影响范围。** 只影响论文复现口径，而且要求机组中有下调价为 0（或低于风电）的非 VRE 机组排在 VRE 前面。VALUE-101 数据包的 doctoral case D3、D4 在 surplus conservation 上通过。修正口径的下调改用 `downward_stack`，一次扣减、不会重复，也不使用这套 routing 边界。
- **建议**（第 8 节）：(A) 登记一条论文复现口径的声明偏差（暂定 DEV-BAL-05），配机器签名，并在方法学的论文复现部分披露；(B) 不做“记账修复”，因为这里没有记错账；(C) 是否在论文复现口径中修复内核，由作者决定，这会改变冻结轨迹，属于通用修正。无论选哪一项，GBP1 复现运行的年度结果按 Q14 都仍然隐藏，因为储能门本身就是 “reproduction_with_declared_deviations”（DEV-STO-01），而 Q14 只在所有原始不变量都通过时才发布。

## 2 两个检查与两组数字

| 检查 | 定义 | 修复后（f7a5f7a） | 35aadb3 轨迹（1e61e5e 复跑） | 是否属于能量平衡门 |
|---|---|---:|---:|---|
| `period.surplus_conservation` | 每行 routing：`available − (to_storage + to_export + to_flexible) − spilled − to_dispatch − curtailed − unrealised = 0`（容差 `max(1e-6, 1e-9·available)`） | **563 行失败**，全部为负，最大 −991.33 MWh，合计 −217,140.07 MWh | 737 行，最大 −999.84，合计 −274,187.28 MWh | 是（`ENERGY_BALANCE_GATE_CHECKS`） |
| `period.envelope` | 声明边界 `default_psm_surplus_node_v1` 的必要条件 | **471 个时段下界越界**，最大 991.16 MWh，合计 186,074.68 MWh；上界越界 0 | 621 个时段，最大 991.16，合计 237,351.25 | 否（只作证据） |
| `period.boundary_residual` | `S + B + U_out − W_in − D − C − E − X` | 890 个时段超出容差（即全部 stress 时段） | 848 | 否（A2 后只作证据） |
| `period.balance_account` | A2 账：缺口记为未供电量后的闭合残差 | 通过（最大 1.5e−11 MWh） | 通过 | 是 |

- 471 个包络越界时段全部包含在 563 个 conservation 失败时段里。剩下 92 个时段的多削量较小，还在包络的松弛范围内，所以包络没有报出来。
- 这次运行的 `scientific-validation.json` 中：`energy_balance.status = failed`，`declared_deviations.unexplained_checks = ["period.surplus_conservation"]`，`storage_invariants.status = reproduction_with_declared_deviations`，`raw_invariants.status = failed`。

## 3 方法

| 步骤 | 内容 |
|---|---|
| 修复后运行 | `scripts/golden/run_case.py D5 --keep-output …`，f7a5f7a，GBP1 public1（manifest sha256 `17a68154…0025`），`mode=full`，用时约 6 分钟 |
| 35aadb3 轨迹 | `git archive 1e61e5e`，以它为 `PYTHONPATH`，在同一个冻结项目 `tests/golden/projects/D5.json`（加 D5 覆盖项）上调用 `run_project_application`。1e61e5e 已经写 surplus routing，轨迹与 35aadb3 逐位相同 |
| 独立核验 | 用当前分支的 `python -m gridform_core.energy_balance_oracle` 只读评估两个账本 |
| 分类 | 直接读 `surplus_routing`、`period_summary`、`balance_boundary_period`、`stress_event` 表，逐行重算缺口，并按来源类别、所在分支（F>R 为削减分支）、符号、下调倍数、包络与 stress 归属分类 |
| 机制确认 | 在 scratch 中给 `store_service_three` 套只读包装，记录调用前后 `gen_list` 中每台机组的出力和内核记账的削减量。全年调用中，“实际拿走 > 记账量” 的时段正好是那 563 个，与 routing 表逐一对应。另外单独截取第 301 期，记录完整的下调顺序 |
| 对照 | VALUE-101 的 D3（`value_101_day`）和 D4（两年）也用同样的核验跑了一遍 |

## 4 分类与量化（修复后；括号内为 35aadb3 轨迹）

### 4.1 失败行的分布

| 维度 | 结果 |
|---|---|
| 来源类别 | `in_dispatch` 563（737）；`out_of_dispatch` 0（0） |
| 所在分支 | 全部在削减分支（实际需求 < 预测需求）。该分支全年共 8,393 个时段，受影响的约占 6.7% |
| 缺口符号 | 全部为负：路由出去的比可用的多 |
| `spilled + unrealised` | 全部为 0（内核声称的弃电为负，被截成 0） |
| 缺口与削减量的关系 | 缺口 = 记账削减量 − 实际从 S 拿走的量，最大误差 4.5e−13 MWh |
| 实际下调 / 记账下调 | 2.00：562 个时段；1.15：1 个时段（35aadb3 轨迹：2.00 有 699 个，1.01–1.33 有 38 个） |
| routing 中的 `available` | 等于 (F − R)·h，最大误差 0。盈余来源只有预测减实际的部分，不含任何核电盈余 |
| 日前盈余的来源类别 | `out_of_dispatch`（未接受的 VRE）500 个时段；没有日前盈余 63 个时段；`in_dispatch`（核电）0 个 |
| 被重复削减的机组 | 562 个时段：先削 `Hydro_natural_flow`，再削同样的量的海上风电（offshore10 169、offshore1 119、offshore12 119、offshore11 103、offshore13 50、offshore15 2、offshore16 1，按最后一台被部分削减的风电计）。第 301 期：重复削减的是 CCGT（见 5.3） |
| 子分支 | 削减分支有 “有可出口线路” 与 “无可出口线路” 两个子分支（第 1283、1168 行），下调代码相同，两处都会触发 |

### 4.2 多削量的大小

| 单个时段的多削量（MWh） | 时段数 |
|---|---:|
| < 1 | 2 |
| 1–10 | 7 |
| 10–100 | 84 |
| 100–500 | 291 |
| ≥ 500 | 179 |

按月：1 月 24、2 月 130、3 月 53、4 月 11、5 月 18、6 月 12、7 月 2、8 月 21、9 月 2、10 月 93、11 月 57、12 月 140。集中在风大、需求预测偏高、水电在日前排满的月份。

### 4.3 与 A2 缺电账的关系

| 项 | 修复后 | 35aadb3 轨迹 |
|---|---:|---:|
| 全年 stress 时段 / 事件 | 890 / 157 | 848 / 168 |
| 其中受本缺陷影响的时段 | 563（全部是 stress 时段） | 737 |
| 含受影响时段的 stress 事件 | 133 | 164 |
| 这些时段的 A2 缺口合计 | 247,283.6 MWh | 280,464.8 MWh |
| 其中多削量 | 217,140.1 MWh（全年缺口的 72.2%） | 274,187.3 MWh（90.7%） |
| 缺口恰好等于多削量的时段 | 371 | 588 |
| 缺口大于多削量的时段（另有其他缺口，如日前预测高于可用供给，DEV-BAL-02） | 192 | 149 |
| 缺口小于多削量的时段 | 0 | 0 |
| 内核记录的 blackout | 0 | 0 |
| 多削量占全年需求 | 0.093% | 0.118% |

所以 A2 记账已经把这部分电量作为未供电量完整记入：每个受影响时段的缺口都不小于多削量，`balance_account` 闭合。

## 5 机制

### 5.1 代码路径

削减分支（`realise_period` 中 `real_demand < forecast_demand`）调用 `curtailment_market_bidding` → `store_service_three`。需要削减的量 `need_curtailed_energy = F − R`，依次被储能、出口、柔性负荷吸收，剩下的部分由下调消化。下调按 `accepted_bids.sort(key=lambda x: x[3])`（下调价，第 1941 行）的顺序进行：

```python
for item in accepted_bids:                       # 外层：按下调价
    if need_curtailed_energy != 0:
        if type(item[0]) == ExpensiverenewableGenerator:
            ...                                  # VRE：削够后 need = 0; break
        else:
            for index, item in enumerate(accepted_bids):   # 内层：扫描全部非 VRE
                if type(item[0]) != ExpensiverenewableGenerator:
                    ...
                    if max_curtail_energy >= need_curtailed_energy:
                        item[2] = item[2] - need_curtailed_energy   # 削掉 need
                        ... gen[1] = item[2] ...
                        break                     # 只跳出内层，need 没有清零
                    else:
                        need_curtailed_energy -= max_curtail_energy
                        ...
```

VRE 分支削够后会执行 `need_curtailed_energy = 0` 再 `break`，非 VRE 的 `>=` 分支没有这一步。外层循环接着处理下一个已接受报价时，`need_curtailed_energy` 仍是刚刚削过的值，于是同样的量又被削一次，通常是从排在后面的风电削。记账用的 `curtailed_energy` 是进入下调前的 `need_curtailed_energy`，所以只记了一次。

审查报告在 P3-03 的复核意见中已经指出过这一点（`VALUE_review_2026-10-04.md` 第 2692 行：`>=` 分支在 break 前没有清零，会重复削减风电，留下未记录的缺口）。这次调查在 GBP1 上量化了它，并确认它就是 surplus conservation 失败的唯一来源。

### 5.2 典型时段：第 17184 期（最大缺口）

- 预测 10,680 MWh，实际 9,688.5 MWh，`need` = 991.5 MWh。储能吸收 0.17，剩下 991.33 MWh 需要下调。日前盈余（未接受的风电）另有 1,053.5 MWh 出口。
- 已接受报价按下调价排序，第一个是 `Hydro_natural_flow`（下调价 0，日前出力 2,000 MW，即 1,000 MWh），后面是 offshore1、offshore10 等风电（下调价同为 0）。
- 内层循环：水电可下调量 ≥ need，水电被削 991.33 MWh，`break`，need 没有清零。
- 外层循环继续：offshore1 的出力小于 need，被全部削掉；接着 offshore10、offshore11、offshore12 也被全部削掉，最后 offshore13 被部分削减，凑满 991.33 MWh。
- 合计从 S 中拿走 1,982.66 MWh，记账 991.33 MWh。S = 8,697.34 MWh，而实际需求是 9,688.5 MWh，缺口 991.33 MWh，blackout 记 0。

### 5.3 非 2 倍的时段：第 301 期

- 需要下调 2,349.68 MW（以内核的 MW 计）。内层循环先把水电削到 0（2,000 MW，走 `else` 分支，need 降到 349.68），再继续扫到 CCGT（第 30 位）：CCGT 可下调量 ≥ 349.68，于是削 349.68 并 `break`，need 没有清零。
- 外层循环继续：offshore1 被削 323.3，offshore10 被削 26.38。
- 结果多削的是最后那一笔 349.68 MW（174.8 MWh），比值为 1.15。规律相同：**多削量等于内层 `>=` 分支最后削掉的那一笔。**

### 5.4 为什么是 GBP1，而不是 VALUE-101

- 要触发这个缺陷，需要一台非 VRE 机组排在 VRE 前面（或与 VRE 同价而排在前面），并且它能一次削够剩余的 need。GBP1 public1 的 `Hydro_natural_flow` 下调价为 0，可下调 2,000 MW，正好满足条件。VALUE-101 机组组合中的非 VRE 只有 CCGT 等，下调价为正，排在 VRE 之后，外层循环在 VRE 处已经削够，不会进入非 VRE 分支。
- 实测：D3（VALUE-101 一日）和 D4（VALUE-101 两年，35,040 个时段）的 surplus conservation、包络、边界残差、A2 账全部通过。

## 6 被排除的解释

| 候选原因 | 结论 | 依据 |
|---|---|---|
| 记账边界问题（routing 漏记或归错类） | 排除 | routing 行如实记录了内核从 S 中拿走的量（`curtailed_mwh` = 下调前后 `gen_list` 之差）和内核记账的削减量；两者之差就是缺口，误差 < 1e−12 MWh。只读包装独立测得的“拿走 − 记账”与 routing 逐期一致。电确实离开了 S，而且没有去向 |
| 核电 must-run 盈余 | 排除 | 失败行的 `available` 都恰好等于 (F−R)·h；日前盈余类别没有一个是 `in_dispatch`。修复后核电全年没有被接受，失败依然存在；35aadb3 轨迹（12 月有核电）也是同样的机制 |
| 数值误差 | 排除 | 最小缺口 0.33 MWh，远大于 1e−6 的容差；比值集中在 2.00 |
| P3-01 隐藏缺电（日前预测高于可用供给） | 不是同一机制，但会在同一时段叠加 | P3-01 的缺口来自日前排程不足，体现在 A2 的 `forecast_above_supply` 时段（DEV-BAL-02）。本缺陷来自削减分支多削。192 个时段两者叠加，所以缺口大于多削量 |
| storage 跨阶段功率重置（DEV-STO-01） | 无关 | 失败行中储能吸收量正常（如 0.17 MWh），缺口与储能无关 |

## 7 对结果的影响（论文复现口径，GBP1 2025）

- **可靠性：** 内核报 0 blackout，但有 217,140 MWh 的需求实际没有得到供给，占全年 A2 缺口的 72%，分布在 563 个半小时和 133 个 stress 事件里。按 A2，这些已经作为 stress 事件对外报告。
- **削减记录：** `period_summary.curtailed_mwh` 只记了一次下调。实际从 S 中拿走的量比它多 217,140 MWh：562 个时段多拿的是水电与风电各削一次中的一次，1 个时段（第 301 期）是 CCGT。
- **其他结果**（逐资产出力、收入、时段价格）都按内核实际的 S 计算，已经包含这一行为，也已包含在 A15 认可的修复前后对比里。本调查没有单独拆分它对成本和价格的影响。

## 8 选项与建议

| 选项 | 做法 | 对冻结轨迹 | 对校验结论 | 对 Q14 发布 | 评价 |
|---|---|---|---|---|---|
| **A 声明偏差（建议）** | 在 `declared_deviations.json` 中为 `doctoral-lineage-0.6.0a2` 增加 DEV-BAL-05，配机器签名（见第 9 节），检查项为 `period.surplus_conservation`；`match_declared_deviations` 增加对应的匹配器；方法学的论文复现部分加一段披露 | 不变 | 能量平衡门由 `failed` 变为 `reproduction_with_declared_deviations`；只有每一行失败都符合签名时才成立，不符合的行仍然失败 | 不变：年度结果仍隐藏（Q14 把 “with declared deviations” 计为未通过，储能门已是这一状态） | 如实说明这是论文内核的已知行为，同时保留严格校验。需要改校验代码，属于下一个施工单元，须作者先认可 |
| B 记账修复 | 例如给 routing 加一个 “over_curtailed” 项，让守恒式闭合 | 不变 | 守恒式会通过，但这样只是把真实缺陷藏进记账 | 不变 | **不建议**：这里没有记错账，电确实少了。最多可以作为透明度补充（单独一列显示多削量），不能代替 A |
| C 修复内核 | 在非 VRE 的 `>=` 分支 `break` 前加 `need_curtailed_energy = 0`（两处），作为两个口径共用的通用修正 | **改变**：D5 需要按通用修正规则重基线一次，并附数值报告；D1–D4 预计不受影响（D3、D4 本次实测不触发） | 预计 surplus conservation 通过，全年 A2 缺口约减少 217 GWh | 仍隐藏（储能门 DEV-STO-01 仍是 “with declared deviations”） | 这会使论文复现结果偏离论文原始代码。是否把它视为与 A3/A5 同类的“读取/实现错误”，需要作者判断 |

建议：**先做 A**，在方法学中写明这一行为及其规模；**C 交作者决定**。如果作者选 C，A 就不需要了，但方法学仍应说明论文原始结果含这部分隐藏缺电。修正口径已经没有这个问题，无需改动。

## 9 声明偏差草案（DEV-BAL-05，待作者认可）

**中文说明（方法学用）：**

> 论文原始内核在削减阶段处理非 VRE 机组下调时，一台机组一次削够剩余需求后没有把剩余需求清零，外层循环会从后续报价（通常是风电）再削一次同样的量。被多削的电量没有记为缺电，内核报告的 blackout 为 0。论文复现口径保留这一行为，以便逐位复现原始轨迹。VALUE 的能量平衡账（A2）把多削的电量记为未供电量，并作为 stress 事件报告。只有当机组中有下调价不高于 VRE 的非 VRE 机组排在 VRE 前面时才会触发。以 GBP1 public1 的 2025 年为例：563 个半小时受影响（`Hydro_natural_flow` 下调价为 0），多削合计 217 GWh，占全年需求的 0.09%，占 A2 缺口的 72%。修正口径的下调采用一次扣减的成本排序，不存在这一行为。

**目录条目草案（英文，供 `declared_deviations.json`）：**

```json
{
  "id": "DEV-BAL-05",
  "profiles": ["doctoral-lineage-0.6.0a2"],
  "title": "Curtailment-branch down regulation taken twice after a non-VRE unit meets the remaining need",
  "signature": {
    "matcher": "down_regulation_double_take",
    "checks": ["period.surplus_conservation"],
    "relation": "surplus_routing row with source_class in_dispatch in a curtailment-branch period (real < forecast demand), spilled_mwh = unrealised_mwh = 0, conservation gap g < 0 with |g| <= curtailed_mwh / 2 + tolerance, and A2 shortfall of the period >= |g| - tolerance"
  }
}
```

签名的依据：两次削减量相等时 |g| = curtailed/2；第 301 期这类情形 |g| 更小，所以用 ≤。“缺口 ≥ |g|” 保证多削量已在 A2 账中记为未供电量。按本次数据，修复后的 563 行和 35aadb3 轨迹的 737 行全部满足这一签名，没有例外。

## 10 待作者决定

1. 是否采纳 A（登记 DEV-BAL-05 并实现匹配器、在方法学中披露）。
2. 是否采纳 C（在论文复现口径中也修复内核，作为通用修正，D5 重基线一次）。
3. 本报告更正了此前文档中 “surplus conservation 471 个时段” 的说法：471 是包络越界时段数，surplus conservation 的失败行数是 563。`GBP1_DOCTORAL_BEFORE_AFTER.md` 和交接文档在 A25 重写时应采用本报告的口径。

## 11 复现

```sh
export VALUE_P0_5_PACKS=<GBP1 public1 目录>
python -B scripts/golden/run_case.py D5 --keep-output <OUT>
python -B -m gridform_core.energy_balance_oracle <OUT> --output oracle.json
# 失败行：surplus_routing 中
#   available - to_storage - to_export - to_flexible - spilled - to_dispatch - curtailed - unrealised
# 的绝对值大于 max(1e-6, 1e-9*available) 的行；与 period_summary 关联后，
# routing.curtailed_mwh / period_summary.curtailed_mwh 即实际/记账下调比。
```

35aadb3 轨迹：`git archive 1e61e5e` 解到临时目录，以它为 `PYTHONPATH`，用当前分支的 `tests/golden/projects/D5.json` 加 `cases.json` 中的 D5 覆盖项调用 `run_project_application(mode="full")`，再用当前分支的 oracle 评估。
