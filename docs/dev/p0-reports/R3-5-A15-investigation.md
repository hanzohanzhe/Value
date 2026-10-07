# R3-5 工作报告：GBP1 论文复现口径 surplus conservation 失败的调查（A15、A24）

工作位置：`value-fix-review-2026-10-04`（分支 `fix/review-2026-10-04`，起点 f7a5f7a）。本单元只调查、只写报告：没有改校验、偏差目录、内核、数据或界面；没有 correction id，没有 golden 修订。

## 1 做了什么

1. 在 f7a5f7a 上跑 golden case D5（GBP1 public1，2025 年，`doctoral-lineage-0.6.0a2`，`mode=full`），保留输出。
2. 用 `git archive 1e61e5e` 跑同一个冻结项目。1e61e5e 的轨迹与 35aadb3 逐位相同，而且已经写 surplus routing，用来代表 35aadb3。
3. 用当前分支的能量平衡 oracle 只读评估两个账本，再直接读账本表，逐行重算 surplus conservation 缺口并分类。
4. 在 scratch 中给 `store_service_three` 套只记录、不改值的包装，跑完整一年，记录每次下调前后各机组的出力。包装后的 golden 摘要与正常运行逐列相同（2076 列）。另外单独截取第 301 期，记录完整的下调顺序。
5. 对照跑 VALUE-101 的 D3、D4（D2 的 smoke 账本没有 routing，评估结果为 not_evaluated）。
6. 写出调查报告 `docs/dev/GBP1_SURPLUS_CONSERVATION_INVESTIGATION.md`（中文）。

## 2 主要发现

- 失败的原因是**论文内核的真实能量不平衡**，不是记账边界问题，也与核电 must-run 盈余无关。`store_service_three` 中非 VRE 下调的 `>=` 分支在 `break` 前没有把 `need_curtailed_energy` 清零（当前文件第 1168、1283 行；35aadb3 第 1019、1126 行）。外层循环于是从后续报价（通常是风电）再削一次同样的量。GBP1 的 `Hydro_natural_flow` 下调价为 0，排在风电前面，所以会触发。
- 修复后：surplus conservation 失败 **563 行**，全部是 `in_dispatch`、削减分支、负缺口，合计 217,140 MWh，最大 991.33 MWh；其中 562 行实际下调正好是记账量的 2 倍。35aadb3 轨迹：737 行，274,187 MWh。
- 此前报告中的 “471 个时段、最大 991 MWh” 是**包络下界越界**的统计。471 个时段全部包含在 563 个 conservation 失败时段里。
- 563 个时段都是 stress 时段。A2 账已把多削量记为未供电量（每个时段的缺口都不小于多削量，`balance_account` 通过）。多削量占全年 A2 缺口的 72%。
- D3、D4（VALUE-101）的 surplus conservation 通过。修正口径的下调用 `downward_stack`，不会重复扣减。
- 草拟的签名（DEV-BAL-05）在修复后的 563 行和 35aadb3 轨迹的 737 行上全部匹配，没有例外。
- Q14：即使登记声明偏差或修复内核，GBP1 复现运行的年度结果仍会隐藏，因为储能门已经是 `reproduction_with_declared_deviations`（DEV-STO-01），而 Q14 把它计为未通过。

## 3 建议（待作者决定）

- A（建议）：登记论文复现口径的声明偏差 DEV-BAL-05，实现匹配器，并在方法学中披露（报告第 9 节有中文说明和目录条目草案）。
- B：不建议做“记账修复”，因为这里没有记错账。
- C：是否在论文复现口径中也修复内核（两处加 `need_curtailed_energy = 0`），属于通用修正，D5 需要重基线一次，交作者决定。

## 4 文件

- 新增 `docs/dev/GBP1_SURPLUS_CONSERVATION_INVESTIGATION.md`
- 新增 `docs/dev/p0-reports/R3-5-A15-investigation.md`（本报告）

## 5 测试与检查

- D5 完整运行（f7a5f7a）：完成，约 6 分钟；oracle：failed（envelope 471、boundary_residual 890、surplus_conservation 563；balance_account 通过）。
- 1e61e5e 上的 D5 项目运行：完成；oracle：failed（envelope 621、boundary_residual 848、surplus_conservation 737；balance_account 通过）。
- 加只读包装的 D5 运行：golden 摘要与正常运行逐列相同；记录到的 “实际下调 > 记账下调” 时段与 routing 失败行逐一对应（563 = 563）。
- D3、D4：oracle 全部通过。
- 本单元只改文档。提交前跑了 `scripts/p0_gate.py quick --changed-since HEAD`：passed（前端 typecheck 与 eslint 因 app/ 未改动而跳过）。

## 6 偏差

- 任务描述沿用了 “surplus conservation 失败 471 个时段（最大 991 MWh）” 的说法。实测 471/991 是包络越界的数字，surplus conservation 的失败行数是 563（最大 991.33 MWh）。报告按实测口径书写，并明确指出了这一更正。
- 35aadb3 本身的账本没有 routing 表，无法直接评估 surplus conservation。这里用轨迹逐位相同的 1e61e5e 来代表它，与 `GBP1_DOCTORAL_BEFORE_AFTER.md` 的做法一致。

## 7 收尾检查

- p0_gate quick：passed（见第 5 节）。
- INSTALLED 未被写入：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（现网 supervisor 在 2026-10-03 创建的 0 字节锁文件，早于本单元，以往报告已说明）；`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”
- 没有启动服务器；scratch 中的运行输出已清理，只保留小的 JSON 证据文件。
