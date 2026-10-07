# R4-1 golden 重基线：数值前后对比（DECISIONS A26）

三项论文内核错误作为通用修正（`r41.down-regulation-taken-once`、`r41.must-run-surplus-counted-once`、`p06.storage-net-per-period` 改为通用）后，论文族 golden 重基线一次：

| case | 修订 | 内容 | 逐列数值报告（与修订绑定） |
|---|---|---|---|
| D1 | r11 | 只有核算区：验证报告列出的已声明偏差从 5 条变为 3 条 | 无（没有轨迹变化） |
| D2 | r11 | 同 D1 | 无 |
| D3 | r14 | 轨迹 48 列、核算 138 列 | `tests/golden/reports/D3-r14.json` |
| D4 | r12 | 轨迹 110 列、核算 162 列 | `tests/golden/reports/D4-r12.json` |
| D5 | r3 | 轨迹 99 列、核算 360 列 | `tests/golden/reports/D5-r3.json` |

修复前（before）是父提交 6fecfc6 的 `git archive` 运行，修复后（after）是 R4-1 工作树运行，均用 `scripts/golden/run_case.py --keep-output`。父提交的输出在轨迹区、核算区与上一修订逐位相同，只在身份区有 16–17 列不同（R1-2、R3-3 等单元之后的模块版本和来源哈希），所以逐列报告按 R1-2 的先例直接用 `gridform_validation.golden.build_numeric_report` 生成，报告中 `parent_reproduction` 一栏列出这些身份列。

本目录的文件：

| 文件 | 内容 |
|---|---|
| `D3-market-before-after.json`、`D4-…`、`D5-…` | 年度市场合计（需求、接纳供给、储能充放、弃电、excess、进出口、A2 缺口、stress、逐技术出力）、验证状态、能量平衡与储能检查；由 `market_metrics.py` 从两份运行输出只读生成 |
| `D5-gbp1-summary-before-after.json` | `scripts/gbp1_doctoral_before_after.py summarise` 的输出（成本账、排放、投资、市场） |
| `market_metrics.py` | 上述年度合计的生成脚本（只读，`python -B market_metrics.py before <dir> after <dir>`） |

主要数字：

| 指标 | D5（GBP1 2025）修复前 → 修复后 | D4（VALUE 101 两年）修复前 → 修复后 |
|---|---|---|
| surplus conservation | 失败 563 行 → 通过 | 通过 → 通过 |
| 储能门 | 带声明偏差（单向 15,653 行，超额定 448 行）→ 通过 | 带声明偏差（单向 9,343 行）→ 通过 |
| 原始不变量（Q14） | failed（隐藏）→ passed（发布） | failed → passed |
| A2 缺口 | 300,855 → 78,810 MWh | 0 → 0 |
| stress 时段 / 事件 | 890 / 157 → 487 / 74 | 0 → 0 |
| 储能充电 / 放电 | 5.05 / 3.66 → 2.42 / 1.75 TWh | 2025：14.33 / 11.61 → 3.09 / 2.50 GWh |
| 头条运营成本 | £4,317.5 m → £4,287.0 m | 2025：£7.17 m → £7.06 m（物理资源成本） |
| VRE 接纳 | 137.49 → 137.71 TWh | 2025：114.52 → 125.16 GWh |

D3（VALUE 101 一天）：储能门由带声明偏差（单向 10 行）变为通过；接纳供给 780.5 → 775.5 MWh（等于需求），VRE 接纳 315.9 → 347.0 MWh，储能充放 48.3 / 39.2 → 11.1 / 9.0 MWh。

修正族 C1–C8 在门控区不变（`capture.py check`，R4-1 工作树）；C9、C10 需要本地构建的 GBP1 public2 与 R029 public2，本单元没有重建，修正口径的代码路径未改。
