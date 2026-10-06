# FX8 交接文档 A18 更新报告

- 分支：`fix/review-2026-10-04`（INTEG）。开始时的基点为 `dca470e`（FX9 之后）。
- 授权：DECISIONS A18（作者选择“开局即在运”）与“收尾交付”第 1、2、4 项。本单元只改文档。
- 提交：
  - `45cebd3` docs(handoff): A18 in the brief, methodology and website hand-offs; four-role note
  - 本报告单独提交（docs(p0)）

## 1 起点

`6631fc1`（FX8）已经把 A18 写进了三份交接文档和 `GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` 第 10 节。本单元逐份核对，补上缺的内容，并改掉残留的旧说法（“当前 6.3.0”“要等 A18”“若 A18 已实施”）。四角色报告此前没有提到 A18。

## 2 补测：A18 在 VALUE 101 上的作用

任务要求简报写出 A18 在 GBP1 和 VALUE 101 上的实测作用。GBP1 的数字取自第 10 节。VALUE 101 方面，FX8 只对 fast tier（C1–C4、C7、C8、D1–D3）做了检查，两年算例 C5、C6 没有重跑，所以本单元补测一次：

- 命令：`capture.py check --cases C5 C6 --jobs 2`，在 HEAD `dca470e` 上运行。用 `vpy` 调用，`TMPDIR` 和 `VALUE_DATA_HOME` 都指向 scratch。
- C5 的最新修订是 11，C6 是 9，都来自 FX5（`c9954ff`），早于 A18。
- 结果：两个 case 都是 gated 0，identity 差异各 15 列，`passed: true`，各用时约 130 s。
- 结论：A18 在 VALUE 101 two_year 上的数值作用为 0。原因是 101 没有核电，`initial_running_rows` 为空。
- HEAD 同时包含 FX9。gated 0 说明 FX9 在这两个 case 上的数值作用也是 0。

## 3 改了什么

| 文件 | 改动 |
|---|---|
| `docs/handoff/MODEL_CHANGES_BRIEF.md` | 3.5 节新增“VALUE 101（实测）”一行，即第 2 节的补测；头部 FX8 一条与第 1 节第二段注明 101 不变；3.2 节标题和模块版本历史加 6.4.0；6.1 节 GBP1 一条改为 A18 之后的实测方向；6.2 节说明 5 加 A18；依据列表改为 FX1–FX8。其余内容不变 |
| `docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md` | N-7 新增三条：①修正口径调度规则的正文写法（报价式不变，只改年初接受集合 \(\mathcal A_{-1}\)；重启与物理启动项；可用率为 0 与新投运机组；没有停运日历）；②论文复现口径路径依赖的披露要点，包括读取时的 high 级 advisory，正文不写 id 和哈希；③VALUE 101 作用为 0。另把 Native 行与 M-1 的版本改为 6.4.0，f2 草稿一行和 `scope_changes` 去掉“要等 A18”“若 A18 已实施”，依据列表改为 FX1–FX8 |
| `docs/handoff/WEBSITE_UPLOADER_HANDOFF.md` | A18 对用户可见，只通过已有机制：头部新增 FX8 一条；2.9 节标题改为 FX1–FX8；“Study 迁移”一行改为 6.4.0；新增 advisory 一行，标题按原文照抄，并写明哪些 Run 的 `needs_review` 会变（见第 4 节第 2 条）；CHANGELOG 已有 FX8 一节 |
| `docs/handoff/FOUR_ROLE_TEST_REPORT.md` | 头部加一条指引；新增 9.10 节：A18 在复测（HEAD `cd2d72c`）之后落地，没有改动 `app/`，四个角色没有重测，VALUE 101 不受影响（补测结果），GBP1 数字的出处；另注明 FX9 的结果见 FX9 报告 |
| `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` | 10.4 节加一条补测记录 |

复制（worktree 根目录的本地副本，被 git exclude，不入库）：

- `VALUE_model_changes_brief_2026-10-04.md`
- `VALUE_handoff_methodology_editor_2026-10-04.md`
- `VALUE_handoff_website_uploader_2026-10-04.md`
- `VALUE_four_role_test_report_2026-10-04.md`
- `VALUE_GBP1_corrected_acceptance_2026-10-06.md`（新文件，来自 `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md`）

上述五份都用 `cmp` 核对过，与仓库中的版本逐字节相同。

## 4 核对过的事实

1. FX8 的代码提交 `7bf170e` 没有改动 `app/`，只更新了 UI 合同夹具 `value-101-day.capabilities.json` 中的模块版本和规则集 sha。所以四角色报告写的是“不改界面”。
2. `result_advisories.evaluate_advisories` 对每个没有应用 `fx8.nuclear-in-service-at-start`、且使用 `value-bid-at-cost-psm` 的 Run 列出这条 advisory（high）。判断只看模块，所以没有核电的 VALUE 101 Run 也会列出它。
   - 论文复现口径 Run 本来就有其他 high 级 advisory（`p06.*`），所以 `needs_review` 不变。
   - 只缺这一条的修正口径 Run（本分支上 FX8 之前跑的）会变为 `needs_review`。
   - 结果是否发布不受影响（Q14 只看 raw invariants）。
   - 网站交接文档按这些情况写。
3. 方法学交接中的公式和说法都与草稿 `fx8_nuclear_in_service.md` 及 FX8 报告的偏差 4、6 一致。

## 5 测试与门禁

- `capture.py check --cases C5 C6`：passed（第 2 节）。
- `scripts/p0_gate.py quick`：提交前 passed，共 16 步，无豁免，backend_ratchet 没有新失败。
- 本单元只改文档，没有新增测试。

## 6 采用的决定与偏差

采用的决定：A18、A15、Q13、Q14、A16-7（public2 只在本地，网站不得引用其数字）。

偏差：

1. 任务要求在简报中写出 VALUE 101 的“实测”作用，但现有记录只有 fast tier 的检查。为此我补跑了 C5、C6，没有只凭“101 没有核电”下结论。
2. `VALUE_GBP1_corrected_acceptance_2026-10-06.md` 是新文件，没有列入 git exclude（exclude 文件在 SRC 的 `.git/info/exclude`，我没有改它）。所以它在 INTEG 的 `git status` 中显示为未跟踪文件。是否把它加入 exclude，由负责人决定。

## 7 遗留问题

1. FX9 已修复 N-1、N-2、N-3、F2-N1 和 M-D1 界面，但网站交接 2.9 节仍把 N-1、N-2 写成“已知问题”，简报 5.3 节第 3 条仍写“建议在发布前修 N-1”。这些不属于 A18，本单元没有改。建议由 FX9 的交接更新处理。
2. 读取时的 advisory 只按模块判断，所以没有核电的数据包也会列出 A18 advisory，这会误导用户。是否给 `fx8.nuclear-in-service-at-start` 的 `applies_when` 加数据包条件，由负责人决定。改了会影响 advisory 列表，属于代码改动。
3. 生物质几乎不运行（0.01 TWh）的问题仍待判断，与之前相同。

## 8 环境与安装目录

- 只启动了一个后台进程：golden check，PID 2963146。它自己结束，我只用 `kill -0` 检查过它，没有发送任何信号。没有启动 HTTP 服务，没有连接 8766 或 8800，没有使用 pkill、killall 或按模式的 kill。
- scratch：`…/scratchpad/hof-a18/`，约 20 KB；临时数据目录已删除。
- INSTALLED 检查：
  - `find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`。它是安装时就有的锁文件，以往的报告都记录过。
  - `diagnose-value --prefix …/installed` 退出码 0，输出 “Installation integrity and runtime checks passed.”。中间有一行 vinext 的 “Premature close” 提示，来自诊断探针本身，不影响结论。
- 没有改动 SRC 工作树，没有 push，没有下载文件。Python 都通过 `vpy` 调用。
