# R5-3 改函数角色最终验收缺陷修复（DECISIONS A28）

- 缺陷来源：R4 最终构建验收报告“改函数（编辑模块）角色”（构建 c204aac），2 个中、6 个低，没有高。
- 通过规则（A28）：中缺陷和任何影响模型运行结果的问题必须修并配测试；只涉及显示/措辞的低缺陷能便宜修就修，否则列入 backlog。
- 提交：
  - `d63921a` fix(psm,modules): edit-module defects - bounded storage state record, duplicate manifests (A28)
  - `4505472` fix(ui,docs): edit-module defects - scopes, revision notice, module badge, guide names (A28)
  - 本报告提交

## 1 缺陷处理表

| 缺陷 | 结论 | 提交 | 说明 |
|---|---|---|---|
| 中1 储能 tranche 记录无界增长 | 已修 | d63921a | 见第 2 节。调度不变；两年 flat-73 全追踪由 20 GB / 31 分钟降到 1.6 GB / 6.4 分钟 |
| 中1 附带：估计在出现该增长模式时给警告 | 已修（保守实现） | d63921a | readiness 新增 `GF_PREFLIGHT_ESTIMATE_STORAGE_MODULE` 警告，见偏差 1 |
| 中2 同 ID 两份清单时 Disable 进入不可恢复状态 | 已修 | d63921a、4505472 | 见第 3 节 |
| 低1 方法升级修复建议指错入口、确认后看不到修订号 | 已修 | d63921a、4505472 | 建议改为 “Press Check readiness again…”，不再给 API 路径；“Saved as a new revision (revision N)” 提示不再被随后的 readiness 复查清掉（原因：复查开头 `setNotice("")`） |
| 低2 一年期 Study 列出跑不了的两年范围 | 已修 | 4505472 | 起止年份相同的 Study 不再列出 `Two-year hand-off check` 和 `Two full model years`（冻结恢复要求的范围除外）。报告里提到的空状态文字 “start with two full years” 已由 R5-2（F-R52-11）改掉 |
| 低3 模板名称与实际行为不符 | 已修 | d63921a | storage_cost 槽位的模板名改为 “Draft fixed-offer storage example (GBP 42/MWh)” |
| 低4 用户指南仍用旧产品名 | 已修（报告点名的行） | 4505472 | EN 第 97–99 行（含 `value.data-bundle/v1`）、434、469 行；ZH 第 113–114、166 行。指南中其他 FORCE 字样未改，列 backlog |
| 低5 比较没有选择基准的地方 | backlog（需设计决定） | — | R5-1 已加参照说明（F-R51-3，“Deltas … are measured against … the first Run ticked”），是否增加参照选择控件在 F-R51-3 中待设计方确认；本轮不新增控件 |
| 低6 模块计数不说明实验性模块 | 已修 | 4505472 | 徽标改为 `13 of 18 ready · 5 experimental` |

## 2 中1：声明的储能状态有界

原因（核对属实）：flat-73 报价高于市场价，电池常满不放电；每个时段自放电后补充约 0.0002 MWh，`Battery.charge` 按充电时段新开一个 tranche，年内只在放电时清理，所以年内 tranche 数一直增长（本次实测最大 5,435 个）。`_storage_pre_state` 在每个时段每个阶段把全部 tranche 写进 `clearing_inputs` / `clearing_outcomes` 的 JSON，总量随时段数平方增长。

做法（`runtime_compat/modular_simulation_model.py`）：

- 一个储能的 tranche 不超过 `STORAGE_STATE_TRANCHE_RECORD_LIMIT = 128` 时，记录格式与以前逐字节相同。
- 超过时，`stored_tranches_mwh` 只列出本阶段报价用到的 tranche（ahead 和 balancing 把已声明的 offers 传进来），其余合并为一项 `stored_tranches_aggregate`（个数、MWh、最早和最晚充电时段），并标注 `stored_tranche_representation = value.storage-tranches-offered-plus-aggregate/v1`、`stored_tranche_count`。`state_of_charge_mwh` 仍是全部 tranche 之和。独立出清 oracle 的逐 tranche 报价上限检查对象正是报价用到的 tranche，所以检查不变。
- 只有 full 追踪的账本会记录声明状态，summary 追踪不再构建它（以前构建后丢弃）。
- 只记录，不参与调度：函数只读 `stored_energy`，不改顺序。

为什么没有合并 tranche 本身：内置动态储能成本按 dwell（当前时段减充电时段）报价和记账，下一年的持有成本系数也由销售的平均 dwell 算出；第三方模块的报价是否与 dwell 无关无法判断。合并 tranche 会改变 dwell 记账和 0.001 MWh 尾量核销，可能改变结果。只压缩记录在构造上不改变任何结果，是最保守的做法。

证明：

- golden 对比（`CompactedDeclarationGoldenTests`）：C3（full 追踪，48 时段）用默认上限运行一次，再把上限设为 -1（每个声明状态都压缩，239 个）运行一次。除 `clearing_inputs`、`clearing_outcomes` 外，24 张市场表逐行相同；`validate_declared_database` 两次结论相同（96 行，LP 通过 95、失败 0；1 行 storage transition 失败是两次都有的既有情况）。输出目录的其他差异只有数据库字节数、哈希和含输出路径的 context 哈希。
- `capture.py check --cases D1 D2 D3 C1 C2 C3 C4 C7 C8`：全部 passed，没有门控区差异；只有身份区 1 列（内核 overlay 哈希）。所有 golden 案例都达不到 128 个 tranche，所以 golden 不需要修订。
- 复现场景实测（scratch，直接调用 `run_project_application`）：VALUE 101 两年（C6 冻结项目）+ 固定 73 GBP/MWh 外部模块 + full 追踪：

  | | 修复前（R4 报告） | 修复后 |
  | --- | --- | --- |
  | 耗时 | 31 分钟 | 6.4 分钟（383.8 s） |
  | 输出 | 20 GB | 1.63 GB（market.sqlite 1.5 GB） |
  | 单行最大 payload | 536 KB | 26.8 KB（平均 12.3 KB） |
  | 最大 tranche 数 / 被压缩的状态 | 4,435（报告时点） | 5,435 / 168,702 |

  同配置的内置模块基线是 1.4 GB、3.7 分钟；剩余差别来自每时段的报价行和内存中的 tranche 遍历，不再随时段数平方增长。

估计警告：readiness 在 full 追踪且选了非内置 storage_cost 模块时给出警告 `GF_PREFLIGHT_ESTIMATE_STORAGE_MODULE`：估计是在内置储能模块上校准的，很少放电的储能会每个充电时段留一条记录，full 回放可能比估计慢、比估计大；建议先跑短范围对照，或长运行改用 Summary。

修正 id：`r53.bounded-storage-state-record`（CHANGELOG 修正表，通用，只涉及 full 追踪的出清声明，不在方法身份内）；runtime overlay 用它重新封存。没有升级 PSM 版本：这是只影响记录的改动，按 Q13 属代码身份变化，已保存 Study 自动追加代码修订。

## 3 中2：同 ID 两份清单

原因（核对属实）：`_set_module_enabled` 停用时只删除 `modules/<id>.json`。点在 `X-copy.json` 行上的 Disable 停用了安装、删掉了另一份清单，副本留在扫描目录中；因为安装已停用、源码不再激活，副本被报成误导性的 `GF_MODULE_IMPORT_FAILED`，之后 Enable、Remove 都不能恢复。

做法：

- `gridform_core/module_recovery.py`：新增 `active_manifests_declaring`（只读原始 JSON，不导入代码）和 `park_other_manifests`（把同 ID 的其他活动清单移到 `disabled-manifests/modules/`，与 `park-manifest` 同一目录，VALUE 不扫描）。离线 `disable` 同样移走副本；`remove_installation` 把同 ID 的所有活动清单一起移走；`list` 对“安装已停用但仍有活动清单”的条目标出问题和 `park-manifest module <file>` 修复命令。
- `gridform_core/module_installation.py`：Disable 停用安装并移走副本（失败时副本按原名回滚）；结果带 `parked_manifests`。Enable 在仍有副本时拒绝，`GF_MODULE_ID_COLLISION`，消息写出副本文件名并说明在隔离面板点它那一行的 Disable。
- 已经处在旧坏状态（安装停用、副本残留）的用户：副本行仍有 Disable 按钮，现在点它会移走副本，health 回到 ok。
- 前端：隔离面板 Disable 后的提示条写出被移走的文件（F-R53-1）。

隔离面板仍按 ID 停用（两行的 Disable 都停用这个模块并移走副本），没有改成“只停用某一份清单”：那需要新的 API 参数和界面语义，超出规格；按 ID 停用后再 Enable 即可回到单份清单的正常状态。

## 4 测试

- 新增 `tests/test_r5_edit_module_defects.py`（13 个，全部通过）：小状态格式不变；大状态只列报价 tranche 加汇总、SOC 和总量守恒、行大小有界、只读、summary 不构建；oracle 对压缩状态仍逐 tranche 检查（越界仍报 `storage_tranche_energy`）；C3 压缩前后 golden 对比；估计警告的触发与不触发；同 ID 两份清单的隔离、Disable 移走副本并清除隔离、Enable 恢复、有副本时 Enable 拒绝、旧坏状态的离线 list/disable/Remove；方法升级建议措辞；模板名称。
- 新增 `tests/frontend/unit/r5-edit-module-defects.test.mjs`（6 个）：一年期范围过滤、两年和未知年份不过滤、冻结恢复范围保留、修订提示保留、徽标、隔离 Disable 提示。UI unit 套件 210 个全部通过。
- golden：`capture.py check` D1–D3、C1–C4、C7、C8 passed（见第 2 节）。
- Playwright headless（chromium 1243），scratch 实例 API 18893、UI 网关 18894，`VALUE_DATA_HOME=scratchpad/build/r5ui/r53/data`，vinext 重新构建，预置一个外部模块和它的副本清单，全部 PASS：徽标 `13 of 18 ready · 5 experimental`；隔离面板两行；在副本行点 Disable 后提示写出 `modules/disabled-manifests/modules/hx-dup-demo-copy.….json`，面板消失，`/api/health` 为 ok；一年期 Study 的 Check for 只列 `Two-period wiring check`；两年 VALUE 101 Study 仍列 `Two full model years`。
- `scripts/p0_gate.py quick`（`VALUE_GATE_VENV=scratchpad/build/gate-venv`，两个代码提交的全部改动暂存状态）：status `passed`，16 步全部通过，没有豁免；`backend_ratchet` 2,719 个 id、失败 147 个全部在基线内，new_failures 0；typecheck、eslint ratchet、network_guard、installed_inventory 通过。之后只把同一批文件分成两个提交，并各自用 `refresh_source_release_manifest.py --index` 刷新清单。

## 5 偏差

1. “估计在检测到增长模式时警告”：运行前无法从估计本身检测增长（它取决于运行中的调度），所以实现为：full 追踪且选了非内置储能成本模块时，readiness 给出警告。运行中不另加状态警告；声明状态中的 `stored_tranche_representation` / `stored_tranche_count` 记录了实际发生的压缩。
2. 中1 采用“限制记录”而不是“合并 tranche”，理由见第 2 节；任务允许两者之一（“cap with aggregation”）。
3. 中2 不新增“只停用某一份清单”的接口，理由见第 3 节。
4. 低4 只改报告点名的行，没有全文替换 FORCE（全文替换涉及大量历史说明，属于文档统一工作）。

## 6 Backlog（一行一条）

- 低5：比较页是否需要参照 Run 选择控件，等设计方对 F-R51-3 的决定。
- 低4 延伸：`docs/USER_GUIDE.md` / `USER_GUIDE_ZH.md` 中其余 FORCE 产品名统一改为 VALUE。
- 中1 延伸：常满储能每时段仍新增一个内存中的 tranche（年末合并为一项）；若以后需要进一步降低报价行数和运行时间，需由作者决定 dwell 记账是否允许合并同价 tranche。

## 7 环境与清理

- 停止了自己启动的 API（PID 2501237）和 UI 网关（PID 2501238），按 PID；端口 18893/18894 已释放。没有连接 8766/8800，没有按模式 kill。
- scratch 中的运行输出（两次 C3、flat-73 两年 1.6 GB）、数据目录和浏览器配置已删除。
- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（作者实例的 0 字节锁，以往报告已说明），没有 `.pyc`；`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”（过程中的 vinext “Premature close” 日志以往已说明，不影响结果）。
- Python 全部经 `vpy` 调用，INTEG 中没有 `__pycache__`；`dist/`（gitignored）已用 vinext 重新构建；没有 push，没有改 remote。
