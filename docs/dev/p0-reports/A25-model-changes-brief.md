# A25 工作报告：模型实质设定改动简报按最终状态重写

- 分支：`fix/review-2026-10-04`（INTEG），代码状态 `fab9ec2`（之后只有其他交付文档的提交）。
- 授权：DECISIONS A25（简报、四角色报告和两份交接文档按当前最终状态从头重写，不写已经发现有错并改过的内容、被推翻的旧做法或逐轮历史）；作者本轮原话“这一轮记得四个新文件都重新生成，不要把之前已经发现有错并且改过的东西给我”。
- 性质：只改文档，不改代码、参数表或 golden。

## 1 完成的步骤

1. 从头重写 `docs/handoff/MODEL_CHANGES_BRIEF.md`，按任务要求的七部分组织：一段话总结；两个口径都改的修正（U1–U13，每项写改了什么、一句话原因、VALUE 101 与 GBP1 的实测作用）；只改修正口径的修正（数据与可用出力、默认 PSM 出清与储能、火电下调经济次序、投资与成本账、网络模块、模块版本与确认）；明确没有改的论文设定；数据来源与审核状态；仍需作者决定的事项；预期结果变化与实测数字。
2. 去掉了阅读提示横幅、各轮更新条、删除线条目、已修复问题的叙述和被推翻的做法（先降火电的旧顺序、电池共用池、旧公式 a = c − S/H、2024 年英镑的重启成本取值作为现行值）。按 DECISIONS 后出条目优先：下调次序只写 A19/A22/A22a/A24-3/A24-4 的最终规则；电池上限只写 A20 的按类型上限（论文设计，修正口径照用）。历史只用一句话指向 git 与 `docs/dev/p0-reports/`。
3. 复制到 worktree 根目录 `VALUE_model_changes_brief_2026-10-04.md`（被 exclude，不入库），用 `cmp` 核对与仓库副本逐字节相同。

## 2 核对依据

- **重跑（VALUE 101 两年算例，scratch，各自独立的 HOME/TMPDIR/VALUE_DATA_HOME，Python 全部经 vpy）：**
  - HEAD `fab9ec2`：`run_case.py` D4、C5、C6。golden 摘要与最新修订（D4 r11、C5 r15、C6 r13）的 trajectory/accounting 区逐列一致；D4 只有 identity 区 16 列不同（代码哈希）。
  - 35aadb3：`git archive 35aadb3` 上用冻结项目 D4、C6 调用 `run_project_application(mode="two_year")`。
  - 分解用中间状态：3537374（C6）、5014b7b（C6、D4）、54fe0ed（C6）、7e07437（C6、D4），摘要与对应修订（C6 r3、r6、r7，D4 r8、r9）逐列一致。
  - 汇总脚本只读 `year-results-v2.json`、成本账、`market.sqlite`，排放用当前代码的 `build_operational_carbon_ledger`（权威因子 `value_current_authoritative_v1`）。脚本在 scratch，没有入库。
- **代码与参数表（只读）：** 方法学目录（口径、修正、声明偏差、advisory 文本）、版本台账、重启参数表（2025 年英镑值、`price_base`、规则文字）、`native_corrected.py`（分段、类别次序、H、最后手段、核电溢价）、`network_method_rules`/R3-2 报告（网络模型类别与权重）、损耗系数表、firm availability 表、CF 披露表（VALUE 101 与 GBP1 的模型 CF）、`v2_module_definitions.py`（四档投资规则、A4 噪声阈值）、`known_data_objects_v1.json`（DST 行号、EUR/GBP 1.1）、`interconnector_identity.py`、`audit_boundary_flow_sign.py`、`store_service_three` 的行号。
- **GBP1 与 R029 数字：** 取自 `GBP1_DOCTORAL_BEFORE_AFTER.md`、`GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` 第 10 节、`GBP1_SURPLUS_CONSERVATION_INVESTIGATION.md`、FX6 与 R3-1/R3-2/R3-3 报告。它们对当前代码仍成立的依据是 golden 修订记录：C9 在核电开局在运之后只修订过下调记录列、储能余量证据列和重启参数表哈希，在 `@v3` 数据包上复跑 gated 0；C10 只修订过参数表哈希；D5 在重基线之后只修订过 VoLL 两列。没有重跑这三个研究包算例（需要本地重建数据包，每个约 6–9 分钟）。

## 3 主要实测数字（写进简报第 7 节）

- 论文口径（D4）：两年系统成本 29,570,717 → 28,930,311 £（−2.17%），A4 −508,406，A7 −132,000；出力、价格、储能、排放与 35aadb3 相同；原始不变量 failed（DEV-STO-01），结果页扣发。
- 修正口径（C6）：29,737,943 → 29,124,542 £（−2.06%）；CCGT 198,410 → 197,191 MWh，排放 78,174 → 77,693 t；电池放电 0.36 → 5,208 MWh；提案 21.96 → 9.49 MW（无 CCGT）。分解：U10 −19、市场规则 −1,445,951、天气与损耗 +1,480,346、投资与成本账及其余 −647,776。
- 修正口径（C5，legacy 储能）：29,570,717 → 29,025,978 £（−1.84%）。

## 4 测试与门禁

- 本单元只改文档，没有新增测试。
- `scripts/refresh_source_release_manifest.py --index`，然后 `--index --check`：结果见提交说明（`docs/handoff/`、`docs/dev/` 都在发布排除清单中）。
- `scripts/p0_gate.py quick --changed-since HEAD`：结果见提交说明。

## 5 采用的决策与偏差

- 采用：A25、A2、A4、A6–A10、A13–A24（各项）、Q1、Q3、Q6、Q7、Q8、Q12、Q13、Q14、Q15。
- 偏差与说明：
  1. 第 6.1 节保留一句“A15 中的 471 个时段是包络检查的计数”。DECISIONS A15 原文写 471，作者读到 563 时需要知道两者的关系；这不是历史叙述。`CHANGELOG.md` Known issues 仍写 471，属于其他文档的待补项，本单元没有改。
  2. 3.2 节 C17、C18 的 GBP1 作用是“单独测量”的数值（核电开局在运对照论文的核电起始规则；日前进口在 C17 之前的代码上测得），只说明测量条件，没有描述被推翻的做法。
  3. 7.3 节的分解把“投资与成本账”和之后各项（含下调经济次序的约 +£10）合成一行，因为中间那个状态的下调次序已被 A19 推翻，不单列。
  4. VALUE 101 的“风光可用电量”一行只给修正口径：论文口径账本不记录未被接受的 VRE 可用量，无法从运行输出得出。

## 6 安全核对

- 没有启动服务，没有连接 8766/8800，没有向任何进程发信号（重跑进程都是我启动、自行结束的）。
- INSTALLED 核对结果见提交后的最终报告。
