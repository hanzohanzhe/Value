# A28 工作报告：模型实质设定改动简报按最终状态重写

- 分支：`fix/review-2026-10-04`（INTEG），代码状态 `6560189`（之后只有交付文档的提交）。
- 授权：DECISIONS A25（交付文档按当前最终状态从头重写，不写已修过的问题、被推翻的做法或逐轮历史）、A26（网站方法学描述网上发布的新模型；论文复现口径是兼容口径，保留论文期设定并接受通用修正）、A28（缺陷修完后一次性重写四份文件）。
- 性质：只改文档，不改代码、参数表或 golden。

## 1 完成的步骤

1. 从头重写 `docs/handoff/MODEL_CHANGES_BRIEF.md`，七部分：一段话总结；两个口径都改的修正 U1–U18（含 A26 的三项内核修正 U7–U9、`r5.served-energy-net-of-stress-shortfall`、`r43.model-clock-utc-label`），每项写改了什么、一句话原因、VALUE 101 与 GBP1 的实测作用；只改修正口径的修正 C1–C26（数据与可用出力、默认 PSM 出清与储能、火电下调经济次序、投资与成本账、网络模块、模块版本与 Study 确认）；明确没有改的论文期设定（作为设定描述）；数据来源与审核状态；仍未解决的事项；预期结果变化与实测数字。
2. 按 A26 改写定位：修正口径是网上发布的新模型，网站方法学描述它；论文复现口径是兼容口径。只写最终规则：下调次序只写 a = c − S(H)/(m·H)；电池上限只写按类型上限；声明偏差只列现存的 DEV-BAL-01/02/03；论文复现参考运行（D3、D4、D5）原始不变量通过、年度结果发布。历史只用一句话指向 git 与 `docs/dev/p0-reports/`。
3. 复制到 worktree 根目录 `VALUE_model_changes_brief_2026-10-04.md`（被 exclude，不入库），`cmp` 逐字节相同。

## 2 核对依据

- **重跑（VALUE 101 两年，scratch，独立 HOME/TMPDIR/VALUE_DATA_HOME，Python 全部经 vpy）：** `git archive 6560189` 上 `run_case.py` D4、C5、C6（各约 3 分钟）。与最新修订 D4 r13、C5 r16、C6 r14 比较：trajectory 与 accounting 区逐列一致，只有 identity 区 1 列（`market_rule_set.runtime_kernel_tree_sha256`）不同。
- **D4 新数字：** 两年系统成本 28,688,666 £（35aadb3 29,570,717，−2.98%）；A26 一步 −241,645 £（相对 D4 r11 的 28,930,311）；运营 12,823,845 £；CCGT 192,839 MWh；排放 75,979 t；储能充 / 放 7,298 / 5,910 MWh；提案 8.00 MW；`reproduction_conformant`，原始不变量 passed。与 R5 定向验证的论文口径冒烟 Run 分年成本（14,458,446 / 14,230,219 £）一致。
- **C5、C6：** 与上一版简报使用的数字逐位相同（修正口径调度在 A26 下不变）。
- **35aadb3 与分解中间状态：** 沿用对固定提交的既有运行摘要（scratch `build/brief/`）。
- **GBP1：** D5 HEAD 数字取自 `docs/dev/p0-reports/r41-golden/D5-gbp1-summary-before-after.json`（after-r41）与 R5-1 的已供电量修订（单位成本 116.828773 £/MWh）；35aadb3 取自 `GBP1_DOCTORAL_BEFORE_AFTER.md`。C9、C10 取自 `GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` 第 10 节与 R3-1 报告；golden 修订记录显示其后只有记录列、参数表哈希和时钟标签变化，R5-1 用本地重建的研究包复核全部 15 个 golden 时 C9、C10 一致。
- **代码与目录（只读）：** `native_market_rules.py`（两个规则集的字段）、方法学目录（`track`、advisory 文本、声明偏差与 withdrawn 列表）、`methodology.UNIVERSAL_ACCOUNTING_CORRECTIONS`、版本台账（`value-bid-at-cost-psm` 6.7.0）、重启参数表 `price_base`、损耗系数表、`voll.py`、`known_data_objects_v1.json`、CHANGELOG correction id 表。

## 3 测试与门禁

- 只改文档，没有新增测试。
- `scripts/refresh_source_release_manifest.py --check`：`stale: false`（`docs/handoff/`、`docs/dev/` 在发布排除清单中）。
- `scripts/p0_gate.py quick --changed-since HEAD`（gate venv）：`status: passed`，15 步通过，前端 typecheck 与 eslint 因 app/ 未改动按规则跳过；backend_ratchet 无新增失败。

## 4 采用的决策与偏差

- 采用：A25、A26、A28；A2、A4、A6–A10、A13–A24、Q1、Q3、Q6、Q7、Q8、Q12、Q13、Q14、Q15。
- 说明：
  1. 第 6.1 节第 4 项列出论文内核中 A26 没有列入、仍由 advisory 披露的几处实现（储能费结转、出清前 VRE 分流电解、储能扩容余量为 0、下调记账三处），请作者判断是否也属真错误。本单元没有测量它们的影响。
  2. 7.3 节修正口径分解沿用既有的逐步运行；中间状态的下调次序与最终规则在 VALUE 101 上只差 2025 年 1 个时段（约 +£10），计入最后一行，表中只写最终规则。
  3. 同一 worktree 中其他交付文档单元在并行工作（网站上传员、methodology 编辑员交接文档），本单元只按路径提交自己的两个文件，没有动它们的改动。

## 5 安全核对

- 没有启动服务，没有连接 8766/8800，没有向任何进程发信号；三个重跑进程都是本单元启动、自行结束的。scratch 中旧的 `build/brief2` 运行输出（约 0.8 GB，上一轮未完成的重写留下）已删除，本单元的运行输出用后删除。
- INSTALLED 核对结果见最终报告。
