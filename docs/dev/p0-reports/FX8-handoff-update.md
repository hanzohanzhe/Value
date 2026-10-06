# FX8：修复轮之后更新三份交接文档（DECISIONS A16）

分支 `fix/review-2026-10-04`（INTEG），起点 `be30884`。授权见 A16（“必须修 + 强烈建议一起修”）与收尾交付第 1、2、4 项。

## 1 做了什么

只改文档，没有改代码、数据或方法学源稿。提交 `c74c2ad`。

| 文件 | 改动要点 |
|---|---|
| `docs/handoff/MODEL_CHANGES_BRIEF.md` | 结构不变，只在各节中加内容并标“修复轮”。依据改为 A1–A18，加入 FX 报告、`GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` 与复测报告。第 1 节加修复轮总结一段。2.2 节新增 U12（`fx4.storage-offer-ledger`，`storage_orders` 核算表）和 U13（`fx5.voll-17000`，两个口径 17,000；五个模块升版本；VALUE 101 与 GBP1 头条为 0 的原因）。2.3 节加 F-D1、F-D2、M-D2、设计规格第 11 节界面变化与复测结论。3.1 节 C4 改为 FX7 实测，新增 C26（`p05.nuclear-stations-public2`）。3.2 节标题与 C25 补版本和论文口径进口语义。新增 3.5 节：A18 已决定、未实施，附 FX7 敏感性数字（注明不是 A18 本身）。4.2 节补核电路径依赖机制与修正口径同样存在、进口只在平衡环节。5.1 节加 A13（A16-6 认可）、VoLL、dec premium 与汇率（A16-6 维持）。5.3 节改为 FX7 已完成，新列四个数据问题（R029/GBP1 public1 光伏严格读取、生物质、N-1、O-3）。6.1、6.2（说明 5）、6.5 更新，新增 6.6 节 GBP1 public2 修正口径第一年 |
| `docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md` | 依据与第 0 节：修复轮五处影响清单；草稿 9 份；须确认事项改为十一条。2.2 节模块版本（6.3.0、1.4.0、0.3.0）。3.2 节加“进口只在平衡分支”。3.3 节加 U12、U13、C26、（C27）A18 待实施，以及 F-D1、F-D2、M-D2 三行。**VoLL**：R-4 与 O-2 更正（完全预见 LP 默认已是 17,000，原文“10,000 不改”过时）。**进口语义**：DS-7 第 158 行补句、N-8 展开两个口径的语义与行号、N-9 补不乘乘数与无爬坡、N-10 补进口按统一价。**核电路径依赖**：N-7 补报价侧机制、FX7 实测、A18 决定与 0.4 的两步写法；N-4 改数据包限制与验收结果。**光伏模型**：W-3、MC-3、VC-6 改为作者认可。另加 DS-1、DS-8（资格两道检查、验证层漏检）、DS-8b（时间戳列）、R-1（R029 严格读取）、N-15、MC-5、MC-6、VC-8、第 6 节草稿表、7.2 scope_changes、8.2 数值、第 9 节第 6 条更新与第 10、11 条 |
| `docs/handoff/WEBSITE_UPLOADER_HANDOFF.md` | 依据与修复轮说明；第 0 节加 A17 推送时机与修复轮变化一项。2.2 加 VoLL 与储能报价账本；2.3 加日前进口、A13 已认可、修正口径核电已知问题；2.4 加 R-D1 扣发说明与 Raw invariants、F-D1；2.6 表格三行补修复轮变化，复测报告已有及其边界；2.7 改写 GBP1 修正口径、R029、VoLL、进口、复测范围的声明边界；新增 2.9 节（界面字符串表，并指出 CHANGELOG 与用户指南尚未覆盖 FX1–FX3 界面变化）。第 3 节阶段 1 加 A17；4.1 S-6、4.2 C-9 与 C-11、4.3 J-3 与 J-7 更新；第 5 节来源表、第 6 节 public2、第 7 节新增 6–8 条；附录 A.1、A.2（四角色一行与 VoLL 写法）、A.3 更新，新增 A.6 三条 FAQ |

三份文件已复制为 worktree 根目录的 `VALUE_model_changes_brief_2026-10-04.md`、`VALUE_handoff_methodology_editor_2026-10-04.md`、`VALUE_handoff_website_uploader_2026-10-04.md`（git exclude，未提交），与仓库副本逐字节相同（`cmp`）。

## 2 核对

- 数字都取自 FX1–FX7 报告、`GBP1_CORRECTED_LOCAL_ACCEPTANCE.md`、`fx5`/`fx6` 草稿和 `FOUR_ROLE_TEST_REPORT.md` 第 9 节；模块版本对照 `docs/generated/MODULES.md`；引用的测试文件逐个确认存在。
- 核对了 A18 的状态：`be30884` 之前只有 DECISIONS 提交（`6cf98b6`），修正目录与代码中没有对应改动，所以三份文档都写“已决定、尚未实施”，没有预写规则集版本或 correction id。
- 确认状态链检查（`run_invariants.py`）是本分支新增的（35aadb3 中没有），所以网站交接中写明 F-D1 不涉及 rc1。
- `git diff 35aadb3 -- website/` 仍为空。
- 用脚本检查三份文档中所有表格的列数一致（转义竖线与反引号内容除外）：无不一致。

## 3 测试与门禁

| 命令 | 结果 |
|---|---|
| `scripts/p0_gate.py quick`（vpy，PYTHONPATH=INTEG，TMPDIR、VALUE_DATA_HOME 在 scratch） | passed，143.9 s，16 步全部 passed，无豁免 |

`docs/handoff/` 在发布排除清单中，不进入 `source-release-manifest.json`，所以不需要刷新清单。

## 4 采用的决策

A16-1 至 A16-8、A17、A18（只作为“已决定、未实施”记录）、A15（论文口径核电路径依赖必写）、Q12、Q13、Q14。

## 5 偏差

1. A18 是在修复轮之后决定的，任务没有点名，但 A18 本身要求“更新简报和交接文档”。我只写了决定内容和 FX7 的诊断性数字，明确标注未实施；实施后需要再更新一次（第 6 节）。
2. 网站交接第 2.9 节中的界面字符串取自设计规格第 11 节与 FX3 报告（内部文档），因为 `CHANGELOG.md` 与用户指南还没有覆盖 FX1–FX3 的界面变化。我没有改 CHANGELOG 或用户指南（不在任务范围），在网站交接第 7 节第 7 条列为待办。
3. FX5 报告第 3 节的 VALUE 101 头条数比简报 6.2 节多 66,000 £/年（取了 A7 之前的成本字段）。不影响“VoLL 变化为 0”的结论；在简报 6.2 节说明 5 中注明，没有改 FX5 报告。

## 6 遗留

- A18 实施并重跑 GBP1 public2 之后：更新简报 3.5、6.6 节，方法学交接 N-4、N-7 与第 9 节第 6 条，网站交接 2.3、2.7 节。
- `CHANGELOG.md` 与 `docs/USER_GUIDE*.md` 补 FX1–FX3 界面变化（代码负责人）。
- 前端整体翻新（A17，做法二）之后，网站交接 2.9 节与附录 A.3、A.6 的界面字符串要重新核对。

## 7 环境与安全核对

- INSTALLED：`find …/installed -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（作者在运行的 supervisor 的锁文件，早于本轮，以往报告已说明）。`diagnose-value --prefix …/installed` 输出 “Installation integrity and runtime checks passed.”（前面有一行 vinext 静态文件流 “Premature close” 的消息，是诊断探测关闭连接时打印的，结论行仍为通过）。
- 没有启动任何服务，没有连接 8766/8800，没有向任何进程发信号；没有 push。
- Python 只经 vpy 调用；INTEG 中没有 `__pycache__`。scratch 中门禁的临时目录与数据目录已删除，只留门禁日志。
