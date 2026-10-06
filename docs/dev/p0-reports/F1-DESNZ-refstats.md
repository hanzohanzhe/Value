# F1-DESNZ-refstats：用 DESNZ xlsx 补齐参考统计表（DECISIONS A11）

分支：`fix/review-2026-10-04`（INTEG 工作树）。日期：2026-10-06。

## 1 做了什么

1. 从 4 个 gov.uk 统计页面的 HTML 中取得附件链接，只下载 A11 授权的 6 个 DESNZ xlsx：DUKES 2026 表 5.6、5.10、6.2、6.3，Energy Trends 2026 年 9 月版表 5.1、6.1。文件放在施工临时目录 `scratchpad/build/desnz/`，未入库。URL、字节数、sha256、访问时间（2026-10-06T02:54:09Z）写在参考统计表第 6 节。
2. 用运行时 Python（vpy 包装器）和自带的 openpyxl 读取单元格。读取与计算脚本在 scratchpad `refstats/`（`dump.py`、`q51.py`、`qdump.py`、`hq.py`、`calc.py`），未入库。
3. 更新 `docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md`，新增核实等级 [X]（直接读自 DESNZ xlsx 单元格），全文保持 PENDING AUTHOR REVIEW：
   - 1.1 节：新增来源 X1–X3。
   - 1.2 节：核电全国值改为 DESNZ 官方值。DUKES 5.10.B 负荷率 2019–2024 年为 62.90 / 57.19 / 56.82 / 72.15 / 72.37 / 72.26%；DUKES 5.6 给出毛发电量、厂用电、supplied；ET 5.1 给出逐季度 generated 与 supplied。另附第一轮数字与 [X] 的对照，并解释 2019–2021 年全国值偏低的原因（已退役电站的容量仍在分母中）。
   - 1.4a 节（新增，A10 所需）：各站 2019–2024 年平均负荷率表（PRIS 参考功率口径），含逐年值、算术均值、电量加权均值、最小/最大和 EDF 容量下的等电量值。DESNZ 不公布逐站数据，所以逐站值仍来自 PRIS。PRIS 逐堆合计与 DUKES 5.6.E 全国 supplied 每年相差都在 0.9% 以内。算术均值为 Heysham 1 66.80%、Hartlepool 68.86%、Heysham 2 75.17%、Torness 79.20%、Sizewell B 80.09%，与仓库参数表一致。
   - 1.7 节：补充验收比较基准（ET 5.1c supplied）。
   - 2.1–2.4 节：水电。DUKES 6.2 给出装机与发电量（合计、小型、大型），DUKES 6.3 给出标准口径与不变配置口径两种负荷率。2019–2024 年均值分别为 34.87% 和 34.59%，逐年标准口径为 36.05 / 41.59 / 32.77 / 30.60 / 33.82 / 34.41%。ET 6.1 给出逐季度发电量与负荷率，由此推出 2019–2024 年季度形状系数 1.386 / 0.659 / 0.678 / 1.280，以及满足 `firm_availability.py` 检查（12 个月算术均值为 1）的月度阶梯形状。第一轮倒推的 2022 年约 5.6 TWh 与官方值 5.07 TWh 不符，已作废并说明。
   - 3.4 节（新增，A9 披露用）：DUKES 6.3 陆上风电、海上风电、光伏 2019–2024 年负荷率（两种口径），以及模型 CF 与 DUKES 并列的披露表。修正口径 CF 与 DUKES 2020–2024 均值之比为陆上 1.56、海上 1.23、光伏 0.97。
   - 第 4 节更新待办，第 5 节补充第二轮过程，新增第 6 节下载清单。

## 2 文件

- 修改：`docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md`
- 新增：`docs/dev/p0-reports/F1-DESNZ-refstats.md`（本报告）
- 未入库：6 个 xlsx（约 1.26 MB）和读取脚本，都在 scratchpad。

## 3 测试

本单元只改文档，没有新增代码测试。

- 数值自检（scratchpad 脚本）：
  - DUKES 6.3 标准口径用 DUKES 6.2 复算：陆上、海上、光伏、水电合计相差都不超过 0.3 pp。
  - ET 6.1 和 ET 5.1 的四季度合计等于 DUKES 6.2 / 5.6 的年值。
  - PRIS 合计与 DUKES 5.6.E 的相对差在 −0.89% 到 +0.02% 之间。
  - 月度形状 12 个值之和为 12.0000。
- `scripts/refresh_source_release_manifest.py --check`：未过期（`docs/dev` 不在发布清单中）。
- `scripts/p0_gate.py quick`：结果见第 7 节。

## 4 采用的决定

- A11：只下载授权的 6 个 DESNZ xlsx，只放在临时目录，记录 URL、文件名、sha256、访问日期。补齐后的表仍为 PENDING AUTHOR REVIEW，交作者再审。
- A10：逐站 2019–2024 年平均负荷率表采用 PRIS 参考功率口径（1.4a 节）。
- A9：DUKES 对照列只作披露，不做标定。并列表写明两者口径不同的原因。

## 5 偏差

- **没有改参数表** `gridform_core/data/nuclear/value_uk_firm_availability_v1.json`。任务只要求更新文档；而且替换水电值（0.334 → 0.3487，平直形状 → 阶梯形状）会改变修正口径的 golden，属于模型方法变更，应在作者审核本表后另做。核电各站值与新表一致，不需要修改。
- **月度水电形状仍为 [NV]**：授权的 6 个文件只有年度和季度数据。本单元给出由季度推出的阶梯形状（[D]），没有下载其他文件。
- 下载的是当前最新版（DUKES 2026、ET 2026 年 9 月）。第一轮引用的 DUKES 2025 正文数字与新版有小幅修订，文中逐项列出对照。

## 6 遗留问题（交作者）

1. 审核第二轮补齐的数值（A11 要求）。
2. 决定水电年负荷率用标准口径 0.3487 还是不变配置口径 0.3459，以及是否采用阶梯月度形状。决定后由施工方修改参数表，并做一次修正口径 golden 修订。
3. DESNZ 原表的两处疑点：DUKES 6.3 风电合计行 2020、2021 年标准口径值与分项不符；大型水电 2023、2024 年标准口径值无法复算。两处都不影响建议取值。
4. 第一轮遗留且不在 A11 范围内的项目：海上电气损耗、光伏倾角增益、AGR 换料方式的逐站现状、Dungeness B 的 PRIS 数据。

## 7 门禁与安装目录检查

- `scripts/p0_gate.py quick`（提交前，工作树含本单元两个文档改动）：passed，耗时 137.65 s，15 步全部通过（guard、release_manifest、release_path_hygiene、methodology_catalog、runtime_overlay、version_ledger、golden_bookkeeping、append_only、backend_ratchet、node_tests、http_harness、typecheck_frontend、eslint_ratchet、network_guard、installed_inventory），无豁免。
- 安装目录 `find ... -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'`：只列出 `.supervisor.lock`。这是作者在运行的 VALUE 监督进程的锁文件，修改时间为 2026-10-03 05:41:26，比 receipt 晚 17 秒，早于本单元开始，以往报告也记录过。本单元没有写入安装目录。
- `diagnose-value --prefix <INSTALLED>`："Installation integrity and runtime checks passed."
- 本单元没有启动服务器，也没有向任何进程发信号。
