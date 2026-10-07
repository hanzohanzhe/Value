# R1-handoff-update：R1 轮之后的三份交接文档（工作报告）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `1eec6e6`。
- 授权：DECISIONS A21（交接文档照常交给 methodology 编辑员和网页上传员阅读，文档顶部标明本轮状态），A19–A22a 的内容，A17（网站上传等前端翻新）。
- 性质：只改文档，不改代码、参数表和 golden。
- 提交：`a05ce5d` docs(handoff)：R1 reading banners and R1 content in the three hand-offs (A19-A22a)；本报告单独提交。

## 1 完成的步骤

1. 读取 DECISIONS A19–A22a、R1-1 至 R1-5 的工作报告、FX9 报告、`FOUR_ROLE_TEST_REPORT.md` 第 10 节（R1 轮复测）、r12 草稿、CHANGELOG 的 R1 两节、参考统计表第 4 节与 4.8 节，并核对 p06 草稿规则表、r12/p06 两条 advisory 的目录文字、模型卡与数学参考中的现状。
2. 三份交接文档顶部的 2026-10-07 阅读提示全部换成 R1 轮的新提示，写明哪些可以定稿、哪些仍待定。
3. 按 R1 轮的实际内容改正文（见第 2 节）。
4. `docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md` 4.8 节：第 5 条（A22a）改为“已确认”，第 3 条注明 A22 原式已由 A22a 更正。
5. 三份文档复制到 worktree 根目录的 `VALUE_model_changes_brief_2026-10-04.md`、`VALUE_handoff_methodology_editor_2026-10-04.md`、`VALUE_handoff_website_uploader_2026-10-04.md`（被 exclude，不入库），已用 `cmp` 核对与仓库副本逐字节相同。

## 2 改动内容

**新阅读提示（三份共同的口径）**

- 已定稿：
  - 修正口径的经济下调顺序（C28，`r12.economic-downward-order`，PSM 6.5.0）：重启成本取值已由 A22 认可，停机段公式 a = c − S/(m·H) 已由 A22a 确认；
  - 按类型的电池上限（A20，R1-3）；
  - 参考统计表第 1–3 节（A21）与第 4 节（A22）全部作者已审核；
  - R1-4、R1-5 的缺陷修复，不改数值。
- 仍待定：
  - 参数表 `value_thermal_restart_v1.json` 的说明文字仍写 c − S/H，要随一次修正族 golden 修订改正，只变 `restart_table_sha256`；
  - 重启成本的价格基年（4.8 节第 4 条）；
  - 分区再调度的下调次序是否也按 A19 处理（作者决定）；
  - R1 轮复测剩余问题（R3-N1 中等必修、R3-N2 advisory 措辞等），放在下一轮小修复；
  - 网站上传与发布按 A17 等前端翻新，界面字符串届时重新核对。

**`MODEL_CHANGES_BRIEF.md`（给作者）**

- 文件头：依据补到 A22a、FX9、R1 报告、第 10 节复测；新增“R1 更新”条。
- 第 1 节：新增 R1 轮一段，写两段下调规则和取值，以及两套参考运行上的作用。“仍需你审核的数据”一句按 A21 改写。
- 2.3 节：FX9 已修 N-1、N-2、F2-N1；新增 R1-4、R1-5 一段，并写明 R3-N1。
- 3.2 节：版本补到 6.5.0；C10 加注，说明燃气、生物质部分由 C28 取代。
- 新增 3.6 节（C28）：规则、H 的取法、取值、H\*、A22a、成本账不变、身份与确认、论文口径、VALUE 101 与 GBP1 数字、为什么影响小、golden、仍待处理。
- 4.2 节：“先弃风”写成论文设定，不写成缺陷。
- 第 5 节：
  - 5.1 节新增三行：A21、A22、A22a；
  - 5.2 节：原 DUKES 列、薄弱来源、回退值、水电归一化都标为已审核；剩下价格基年，以及施工选择（含 R1-2 的施工选择）供过目；
  - 5.3 节：N-1 已修；新增 R1 待决事项，即网络 dec 次序、价格基年、R3-N2、R3-N7、AF3-1。
- 6.1 节措辞改写；6.2 节新增说明 6（R1-2 的 +£10.4）；6.6 节注明 R1-2 之后逐位不变。

**`METHODOLOGY_EDITOR_HANDOFF.md`**

- 文件头与第 0 节：
  - 依据补到 A22a、FX9、R1；新增“R1 轮更新”条，并列出 R1-4 改过名称的开发者文档；
  - 草稿数改为 11 份（补 fx8、r12）；
  - 第 9 节改为 14 条。
- 2.2 节补 6.5.0；2.4 节术语表新增 8 个术语（经济下调顺序、不停机段、停机段、重启成本、净节省、最小稳定出力、最短停机时间、H、H\*）。
- 3.2 节：“先弃风”写成论文设定。3.3 节：C8–C16 一行加注；新增 C28 一行。
- 第 4 章正文清单：
  - K-3：注明 staged 的 dec 次序与 A19 的关系待作者定；
  - N-8：补一句；
  - N-9：分两层写，新增经济下调顺序的公式、推导、取值、数字和 advisory 提示；
  - W-4：DUKES 列已审核。
- 第 5 节参考文档：
  - M-1 改为 6.5.0 并补 C28；
  - 新增 MC-7（模型卡还没有写 C28）；
  - 新增 VC-9（r12、r13 测试及其边界）；
  - V-4 补 C28。
- 第 6 节：
  - p06 行补“规则表下调一行的旧式 `c - S(H)/H`”；
  - p05b 行改为 DUKES 已审核；
  - 新增 fx8、r12 两行（r12 草稿中的 “author confirmation pending” 和内部路径）。
- 7.2 节 `scope_changes` 补 A19–A20。
- 8.2 节：数值核对补 R1 的取值与数字；第 5 条改为不带 PENDING。
- 第 9 节：
  - 第 5 条已解决；第 7 条补重启成本的价格基年；
  - 新增第 12 条（网络 dec 次序与 A19）、第 13 条（R3-N2）、第 14 条（R3-N7）。

**`WEBSITE_UPLOADER_HANDOFF.md`**

- 文件头：依据补到 A22a 和第 10 节；新增“R1 轮更新”条，FX9 一并补记。
- 第 0 节：不得上传项中，“待审核的参考统计”改为“参考统计表（已审核但属内部文档）”。
- 2.2 节：储能逐条接受量已在界面显示（FX9）。
- 2.3 节：新增 R1-2 一条，写明网站可以怎样写、不得怎样写；电池上限一条原已有。
- 2.6 节：复测状态改为 FX9 已修 N-1、N-2、F2-N1，R1 复测剩 R3-N1。
- 2.7 节：新增经济下调顺序的声明边界。
- 2.9 节：
  - N-1、N-2 两行改为已修；
  - 新增 9 行：R1-2 方法升级与 advisory、FX9 储能报价、FX9 扩展结果、R1-4 预检、Modules、Runs、结果/网络/比较、Studies/Data/窄屏；
  - 表后注意事项补 R1-4 的文档改名与 CHANGELOG 现状。
- 第 5 节：参考统计表与复测报告、界面字符串来源已更新。第 6 节第 3 条改写。第 7 节第 8 条补充，新增第 9 条。
- 附录 A.1：修正口径说明补下调顺序与按类型上限。附录 A.2：四类用户一行改为 R1 复测结果，只留 R3-N1，并注明修复后删去。

## 3 测试与检查

- `vpy -m unittest tests.test_fx7_gbp1_public2 tests.test_documentation_consistency`：26 个测试，2 failures、6 errors、1 skipped。全部是既有问题：
  - errors：缺少 `publication/prompt107*`、`prompt108*` 文件；
  - failures：user guide 求解控制段、market-ledger v7/v8 字段字典。
  
  这些都与本单元改的文件无关，属于 ratchet 基线内。参考统计表相关断言（test_fx7）通过。
- `refresh_source_release_manifest.py --index --check`：`stale: false`（`docs/handoff`、`docs/dev` 不在发布清单内）。
- `scripts/p0_gate.py quick`（暂存状态下）：`status: passed`，16 个步骤全部通过，没有豁免，用时 145.66 s。

## 4 采用的决定

- A21：交接文档照常给两位读者阅读，顶部标明本轮状态。
- A19、A22、A22a：经济下调顺序按实现和作者确认的修正式写。
- A20：电池上限按类型。
- A17：网站上传等前端翻新。
- Q1：论文复现口径不变；A19 之后，“先弃风”写成论文设定。

## 5 偏差

1. **“重启成本数据待作者审核”与 DECISIONS 不符，按 DECISIONS 写。**
   - 任务文字要求阅读提示写“restart-cost data pending author review”。DECISIONS A22 已写明“认可参考统计表第 4 节的建议值”，A22a 已标“作者 2026-10-07 已确认”，参考统计表第 4 节状态也是“作者已审核 (A22)”。
   - DECISIONS 的权威最高，所以三份提示都写“取值已认可、公式已确认”。真正未决的重启成本事项列为待定：参数表说明文字与 golden 修订、价格基年、网络 dec 次序是否按 A19。
2. **顺带改了参考统计表 4.8 节。**
   - 改的是 4.8 节第 3、5 两条，它们仍写“A22a 待作者确认”。这与 DECISIONS 矛盾，而且是交接文档引用的审核文件，只改状态文字。
   - r12 草稿 §2 的 “author confirmation pending”，以及 p06 草稿规则表中的旧式 `c - S(H)/H`，**没有改**：草稿由 methodology 编辑员维护，交接文档第 6 节已列为待改项。
3. **FX9 补记。**
   - FX9（N-1、N-2、N-3、F2-N1、M-D1 界面）在上一版交接文档中没有体现，网站与简报仍把 N-1、N-2、F2-N1 写成未修。
   - 本次按 FX9 报告和 R1 复测一并改正。

## 6 未决事项（交负责人与作者）

1. 参数表 `value_thermal_restart_v1.json` 的 `rule.shutdown_segment` 说明文字改为修正式，并做一次修正族 golden 修订（C1–C6、C9，只变 `restart_table_sha256`）。R1-2 报告中已有补丁。
2. 下一轮小修复（建议 R2）：
   - R3-N1（中，必修）；
   - R3-N2（p06 advisory 措辞，改前已在 methodology 交接第 9 节第 13 条告知编辑员）；
   - R3M-1 及 10.7 中的低项。
3. 作者决定：
   - 重启成本的价格基年；
   - 网络 dec 次序是否按 A19；
   - AF3-1、R3-N7、O-3、R-D10。
4. CHANGELOG 与用户指南仍缺 FX1–FX3、FX9、R1-5 的界面变化，网站阶段 2 之前须补齐。
5. 前端整体翻新之后，网站交接 2.9 节与附录 A.3、A.6 的界面字符串要逐条重新核对。

## 7 安全核对

- INSTALLED：
  - `find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`，即现网 supervisor 在本轮之前创建的锁文件，以往报告已记录；
  - `diagnose-value --prefix …/installed` 退出码 0，输出 “Installation integrity and runtime checks passed.”。中途那行 vinext “Premature close” 提示与以往相同。
- 本单元没有启动服务，没有连接 8766/8800，没有向任何进程发信号，没有写 SRC 或 INSTALLED，没有 push。
- Python 全部通过 `vpy` 调用，INTEG 中没有 `__pycache__`。scratch 中只新增 `build/r1h/`（门禁输出，约 10 KB）和两个编辑脚本。
