# VALUE 0.7.0-alpha.1 四角色用户验收汇总报告

- 日期：2026-10-06。
- 被测版本：分支 `fix/review-2026-10-04`，HEAD `a987ca450e3c819ce900a2d5c71d2f8152d92986`。四个角色都用 `git archive HEAD` 导出到 scratch 测试，没有改动集成工作树。
- 四个角色（按首页路径命名）：
  1. **复现**：reproduce from existing data；
  2. **换数据**：add your new data；
  3. **改函数**：edit a module；
  4. **加功能**：add new function to VALUE。
- 本文合并四份角色报告，并独立复核了所有标为“高”的缺陷（第 4 节）。“中-高”的 S-D2 也一并复核。
- 角色报告原本要写到 `…/build/roles/<role>/REPORT.md`，但运行环境不允许子代理写报告文件，所以四份原文只存在于工作流输出中。本文是这四份报告唯一入库的记录，因此每个缺陷都保留了描述和复现方法。
- 缺陷编号：在角色报告原编号前加角色前缀。R = 复现，S = 换数据，M = 改函数，F = 加功能。例如 F-D1 就是加功能报告的 D1。
- 复核状态分三种：
  - **已独立复现**：本次在 scratch 中重新跑出了问题；
  - **代码核对确认**：读代码确认了问题的成因，没有重跑；
  - **未复核**：只有测试员的证据。

## 1 结论

| 角色 | 结论 | 主路径 | 测试员报的高缺陷 | 复核后 |
|---|---|---|---|---|
| 复现 | 可用，但有问题 | 全部走通。两个口径的 48 时段运行都与 golden C3、D3 逐列一致（只有 run_id、result_id 不同）；重跑哈希相同；doctoral 年度结果按 Q14 扣发 | 无（最高为中：R-D1） | — |
| 换数据 | 可用，但有问题 | 全部走通。身份链从原文件、映射、规范文件、包 manifest 一直对到 Run 快照；单位只换算一次；汇率随快照冻结 | S-D1（高）、S-D2（中-高） | **都已确认** |
| 改函数 | 可用，但有问题 | 全部走通：模板、构建、安装、48 时段、方法身份变化、迁移确认对话框、坏模块隔离、禁用和修复。所有拒绝都是 fail-closed | 无（4 个中） | — |
| 加功能 | 可用，但有问题 | 2 时段和两年 smoke 走通，扩展的输出与核心结果隔离，命名空间冲突处理正确，G4-01 已修复。48 时段只证明了扩展**没有执行** | F-D1（高）、F-D2（高） | **都已确认，F-D1 比报告的范围更大** |

**一句话结论：** 主路径在四个角色中都能走通，没有出现静默的错误数值，INSTALLED 也保持完好。但有三项已确认的缺陷，建议对外发布前修复，三项都是小改动：

- **F-D1**：只要 Study 选了任何扩展，Run 都会被判为科学验证失败。在修正口径下，按代码路径推断，17520 时段 Run 的年度经济结果会因此被拦下。
- **F-D2**：唯一的 48 时段范围静默跳过扩展，但 Run 的身份记录里仍然写着选了这个扩展。
- **S-D1**：Readiness 卡片只显示前 6 条问题，数据合理性警告被藏在后面。

另有一项需要设计决定：S-D2，UI 中看不到数据包三层校验的结果。

## 2 测试方法与共同条件

| 角色 | 实例端口（API/UI） | 数据 | 驱动方式 |
|---|---|---|---|
| 复现 | 18810 / 18811 | `value-101-baseline-v1`、`value-101-network-v1` | Playwright headless（chromium 1243）。API 只用来轮询状态和读取证据；用 `gridform_validation.golden` 与 golden 对照 |
| 换数据 | 18812 / 18813 | 以上两个包，加 `value-synthetic-contract-pack-v1` | Playwright 操作 UI。负向用例和账本核对直接调 API，请求头用 `authorized_headers()` |
| 改函数 | 18814 / 18815 | 以上两个 VALUE 101 包 | Playwright 操作 UI。API 只用来读运行记录和做负向测试 |
| 加功能 | 18816 / 18817 | 以上两个 VALUE 101 包 | Playwright 操作 UI。UI 没有入口的操作才调 API |

共同条件与偏差：

1. **没有走桌面安装器。** 安装器要求空的 prefix 和完整的发行包，所以四个角色都改用安装器内部的同一个装包脚本（`scripts/install_synthetic_pack.py --value-101-only`），以及同一组启动命令（`python -m backend.server --port …`、`scripts/serve-value-ui.mjs`）。每个实例有自己的 `VALUE_DATA_HOME`。
2. **`vinext build`** 用时 4.7–4.8 s，四次都成功。
3. **范围限制：** 只跑了 48 时段和 2 时段级别的范围，没有跑 17520 时段的整年。年度 Withheld pill（规格 4.2）、doctoral 下禁用外部模块、G4-07（多个扩展共享载荷）、G4-05（结果超过 16 MiB）都没有实测。
4. **清理：** 四个角色都只按自己记录的 PID 停止进程，没有连接 8766/8800。state 和 src 都已删除（每个角色约 560–570 MB，其中执行归档约 500–520 MB）。截图和证据保留，合计约 12 MB。

## 3 各角色结果

### 3.1 复现角色（reproduce from existing data）

**测了什么：**

1. 从首页进入复现路径，创建教学基线，再创建独立的复现 Study。`derivation` 记录了 intent、来源 Study、来源修订、数据包和模块图 sha。
2. Check readiness 后启动 corrected 口径的 48 时段 Run，然后查看结果。
3. 新建 Study，在编辑中改选 Doctoral reproduction 口径：
   - 白名单预设自动生效，包括 `value-legacy-storage-tariff`、`methodology.profile=doctoral-lineage-0.6.0a2`、`carbon.factor_scenario=doctoral_reproduction_2026_07_18`；
   - 三区网络包被禁用，并给出原因。
4. 两个口径各重跑一次。
5. 比较：复现 Run 对基线 Run；corrected 对 doctoral。
6. 用 strict 模式从冻结输入复现。
7. 确认原 Study 没有被改动：基线 Study 仍是 rev 1，只有 1 份修订。

**关键证据：**

- **与 golden 对照：** 用 `digest_run` 和 `compare_digests` 做 exact 比较。

  | UI Run | 参考 | 列数 | trajectory/accounting 差异 | identity 差异 |
  |---|---|---|---|---|
  | corrected 首跑、重跑 | C3（12 个修订） | 875 / 875 | 只有 `run_id`、`result_id` | 无 |
  | doctoral 首跑、重跑、冻结恢复 Run | D3（11 个修订） | 913 / 913 | 只有 `run_id`、`result_id` | `runtime_kernel_tree_sha256`：参考 `a8bddbc1…`，当前 `872700d1…`。属于 identity 区，只报告，不设门 |

- **重跑可重复：**
  - market.sqlite：corrected 为 `f52058725bac95afeccc…`，doctoral 为 `db1efd2638b1f4dc…cdc4038`。首跑、重跑、基线 Run、冻结恢复 Run 各自相同。
  - 以下文件逐字节相同：`energy-balance-oracle.json`、`run-invariants.json`、`scientific-validation.json`、`market/index.json`、`stage-parity.json`。
- **窗口卡数值（MWh）：**
  - corrected：需求 775.49，Accepted supply 787.02，Shortfall 0，充电 11.53，放电 9.34，价格 £37.06/MWh；
  - doctoral：775.49 / 780.49 / 0 / 48.34 / 39.15，价格 £36.48/MWh；
  - 价格按口径标注，没有出现 “Clearing price”。
- **doctoral 结果按 Q14 扣发：**
  - `result_publication.status=withheld`，`reason=GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED`；
  - Inspect 和导出仍可用：60 个产物，下载的 market.sqlite 哈希与磁盘文件一致；
  - 原始不变量失败的是储能 `storage.single_direction`，共 10 行，对应 DEV-STO-01。
- **冻结输入复现（strict）：** 核对约 22 s，结果 allowed，25 个规范角色，执行身份前后相同；创建约 21 s。由此得到的 Run 的 market.sqlite 与原 Run 字节相同。
- **上轮问题：** R1 的 “参数与扩展配置 `[null, null]`” 已修复。
- **截图：** `$ROLES/reproduce/shots/` 下 9 张（01-home、04-reproduce-review、06-corrected-run-completed、07-doctoral-methodology-selected、11-doctoral-run-withheld、12-doctoral-market-replay、14-compare-reproduce-vs-baseline、15-compare-corrected-vs-doctoral、16-doctoral-context-1280）。

**缺陷：**

| ID | 严重度 | 描述与复现 | 复核状态 |
|---|---|---|---|
| R-D1 | 中 | doctoral Run 的 Withheld Callout 说原因是没有通过 “physical energy-balance check”，但同一状态条上能量平衡显示绿色 “● Conformant”（后端值 `reproduction_conformant`，能量平衡检查 passed）。真正失败的是储能单向性（DEV-STO-01，10 行）。状态条、Inspect、结果页都没有显示储能不变量的状态或命中的声明偏差。另外，规格 2.3 的映射表里没有 `reproduction_conformant`，实现把它画成了 teal。复现：doctoral Run → 任一结果视图的状态条，再对照 `GET /api/runs/<id>` 中的 `raw_invariants` 和 `declared_deviations.matched` | 未复核 |
| R-D2 | 低-中 | Runs 页的 “Selected run” 下拉框：已有 Run 时仍保留 “No runs yet for this Study” 选项；同一 Study 的多次 Run 标签完全相同（`project_name · mode · status`），没有时间或 id，无法区分；点 Run 后约 4 s 内，Run history 仍显示 “No runs yet” | 代码核对确认（`RunWorkspace.tsx:97`） |
| R-D3 | 低 | 48 时段 Run 的 stress 区显示 “Stress events — full year 2025 / —” 和 “No stress events in the 0% of 2025 that has been computed.”。覆盖率按年度计算，所以非年度 Run 被说成 0% | 未复核 |
| R-D4 | 低 | 冻结输入的核对和创建各需约 21–22 s，期间只禁用按钮，没有进度文字。创建过程中关闭页面，服务端仍会完成，但用户拿不到回执，容易重复创建（本次因此多出 `recovered-6350cde8333745d4`） | 未复核 |
| R-D5 | 低 | Network & redispatch 页：doctoral 铜板 Run 把“没有分区证据”和 withheld 两个原因拼成一句（API 返回 409）；corrected 铜板 Run 已完成，却显示 “network evidence pending” | 未复核 |
| R-D6 | 低 | 每个 Run 视图都有控制台 404：`resource-readiness.json`。一日 Run 的 `planning/events`、`planning/projects` 也是 404。PSM-only Run 的 Inspect 默认打开空的 Planning 标签 | 未复核（四个角色都看到了这个 404，见第 5 节） |
| R-D7 | 低 | Compare 页把 `identity.method`、`identity.config` 显示成数千字符的单行原始 JSON；口径变化没有作为单独的维度点名 | 未复核 |
| R-D8 | 低 | 375 px 宽度下页面整体横向滚动（391 > 375），与已登记的 F-M7-13 相同 | 未复核 |
| R-D9 | 信息 | `one-day-market-result.json` 含本机绝对路径（`market_ledger.uri`）；相同输入重跑时，`psm_input_sha256` 会变 | 未复核 |
| R-D10 | 信息 | golden D3 记录的 identity 值（kernel tree sha）落后于当前代码；C3 已同步。不设门 | 未复核 |
| R-D11 | 低 | 编辑已有 Study 时，卡片标题仍是 “New study”。doctoral Run 有 9 条 advisories（其中 6 条 high），状态条和 Callout 都没有显示 | 未复核 |
| R-D12 | 信息 | 已完成的 PSM-only Run 中，没有调用的 6 个模块显示 “Evidence pending”，更准确的说法是“本范围未调用” | 未复核 |

### 3.2 换数据角色（add your new data）

**测了什么：**

1. 复制出独立的 BASE 包，在 CSV 映射编辑器里从同一个 CSV 映射 4 列：
   - 需求两列：MWh/period 转为 MW；
   - 法国容量：MW；
   - 法国价格：EUR/MWh，填写汇率 1.15 / annual average / 2025 后转为 GBP/MWh。
2. 创建换数据 Study，Check readiness，再明确启动 48 时段 Run。
3. 查看市场回放，并与基线 Run 做身份比较。
4. 在单独复制的包上，通过 API 做 8 类负向用例。

**关键证据：**

- **身份链：**
  - 原文件 SHA `932cc43b…` → 映射 SHA `2d75e7df…` → 规范文件 SHA `a4e767b3…` → 包 manifest → Run 冻结快照（需求文件 `a4e767b3…`，价格文件 `27f6c3e3…`）；
  - 汇率字段（source_currency、eur_per_gbp、fx_basis、price_year）也冻结在快照里。
- **单位只换算一次：**
  - 第 0 时段 requirement 为 14.94 MWh，等于 CSV 中的 14.935404 MWh/period；
  - 全天需求 775.49 → 837.53 MWh（×1.080，与构造一致）；
  - CCGT 428.13 → 489.72 MWh；能量平衡残差 1.8e-15。
- **汇率：** 103.5 → 90、92 → 80，换算正确。汇率字段为空、rate=0、year=1890 时都报 `GF_MAPPING_FX`，预览按钮禁用。
- **比较页：** 只有“基础与网络数据”一个维度变化。
- **被引用即只读：** 包一旦被 Study 引用就变为只读（`GF_DATA_PACK_REFERENCED`）。
- **负向用例：**

  | 用例 | 结果 |
  |---|---|
  | 非数值、空单元格、负需求 | 拒绝 |
  | 17,568 行 | 接受，并警告只取前 17520 行 |
  | EUR 价格不填汇率、对 GBP 列填汇率、rate=0 | 400 `GF_MAPPING_FX` |
  | 价格单位映射到需求角色 | 400 `GF_MAPPING_UNITS` |
  | **时间戳错位或重复** | **接受**（S-D4） |
  | **名为 EUR 的列按 GBP 映射、不填汇率** | **接受**（S-D5） |

- **文件：** 截图在 `$ROLES/swap-data/shots/`（10 张，含 `17-readiness-neg-truncated.png`、`16-data-neg-pack-no-layers.png`）；证据在 `$ROLES/swap-data/evidence/`（runs.json、mapped-bindings.json、pack-validation-*.json、auction-p0-*.json、new-run-energy-balance-oracle.json、neg-tests.txt）。

**缺陷：**

| ID | 严重度 | 描述与复现 | 复核状态 |
|---|---|---|---|
| S-D1 | **高** | Readiness 卡片只显示 `[...errors, ...warnings]` 的前 6 条，也没有“还有 N 条”的提示。VALUE 101 派生包本身就带十几条 “unit is not declared” 适配器警告，plausibility 发现排在最后，用户看不到。详见 4.3 节 | **已独立复现** |
| S-D2 | 中-高 | UI 中没有任何地方显示数据包的三层校验结果（structural / chronology / plausibility）和口径资格（profile eligibility）。后端已有 `/api/data-packs/<id>/validation` 和 `plausibility_status`，前端没有使用。负向包在 Data 页仍显示 “25/25 required inputs ready”。详见 4.4 节 | **代码核对确认** |
| S-D3 | 中（科学语义，需作者确认） | 法国 “import availability” 填正值时，当前 PSM 不产生进口：两次 Run 的 import_mwh 都是 0，回放中也没有互联线报价。所以替换法国容量和 EUR 价格，在 48 时段结果里看不出效果，只能从输入身份证明它们被冻结进了 Run。角色标签 “import availability” 和 VALUE 101 中 “imports” 的说法会误导用户 | 未复核。顺带看了代码：保留内核的 `ahead_market_bidding(generators, batterys, …)` 不接收 connections，只有 `transfer_constraint < 0` 的连接进入外售和弃电环节（`modular_simulation_model.py:1082、1335、1813、2082`），与测试员的观察一致。是否属于设计行为，需作者判断（见第 6 节） |
| S-D4 | 中 | 映射编辑器只映射 `value` 列，CSV 的时间戳列被静默丢弃，时间轴校验只看位置和长度。后端其实支持 `timestamp_column` 校验（`data_validation_layers.py:146-155`），但映射请求没有办法声明它。时间错位或有重复时间戳的文件能通过全部三层校验 | 未复核 |
| S-D5 | 中 | Currency 默认是 GBP；列名含 “eur” 却选 GBP/MWh 时，没有任何提示。原有的 P6-02 币种检查（`GF_DATA_PRICE_CURRENCY`）在这里失效，因为映射后的规范文件表头固定为 `value` | 未复核 |
| S-D6 | 低 | FX 换算的浮点尾差（如 `90.00000000000001`）原样写进规范文件和审阅表 | 未复核 |
| S-D7 | 低 | 结构错误直接显示 Python 异常文本，没有行号和列名，而且只报第一处 | 未复核 |
| S-D8 | 低 | 点“确认提交”后编辑器里没有成功提示：提交改变了 manifest SHA，编辑器上下文随之重置，提示消息被丢弃 | 未复核 |
| S-D9 | 低 | 比较页把 identity.data 显示为 25 个角色的完整 JSON 大块，没有按角色列出差异。说明文字写的是 “storage-policy causal effect”。做过单位或汇率转换的角色，transformation_id 仍是 `identity/v1` | 未复核 |
| S-D10 | 低 | 新数据目录中的第一次 Run 会在 snapshotting 停留 2 分 51 秒（要归档 521 MB 的 Python 环境），期间没有进度说明；启动完成后，页面会把已经切到别处的用户强制拉回 Runs | 未复核 |
| S-D11 | 低 | 每次加载一日 Run 的页面，`resource-readiness.json` 都会反复 404，约 15 次 | 未复核 |
| S-D12 | 低 | 过期或不一致的状态提示：Run 完成后仍显示 “lesson has started”；Runs 页残留旧的数据包提示；重新加载后 Check for 回到 Two-period，而所选 Run 是一日 Run；Run history 写 “No runs yet”，下面却列着 Run | 未复核 |
| S-D13 | 低 | Run 面板中的 “Data pack manifest SHA”（`e9426fc2…`）既不同于映射编辑器显示的值，也不同于 live 文件的 SHA（`4785fa5d…`），用户无法对上号。逐角色 SHA 是一致的 | 未复核 |

### 3.3 改函数角色（edit a module）

**测了什么：**

1. 按 MODULE_DEVELOPER_101，给 `storage_cost` 槽位新建模块 `uat-scaled-storage-cost`：
   - 报价从 42.0 改为 73.0；
   - 用 `scripts/build_module_bundle.py` 构建两次，字节相同（`fdf6300c…`）；
   - UI 安装时 conformance 为 passed；
   - 从工作台派生 Study 并运行 48 时段。
2. 改内置模块的公式（cycle_only 报价加 25）：
   - 先测不升版本的情况；
   - 再按规则做方法升级：版本升到 2.1.0，在 VERSION_LEDGER 追加记录，执行 `seal_runtime_overlay.py --correction`；
   - 检查迁移确认对话框和各种负向路径。
3. 坏模块的处理：
   - 安装时导入即 `SystemExit` 的包；
   - 已装模块被改坏（导入即 `RuntimeError`、`SyntaxError`）；
   - 隔离、Rescan、Disable、Enable；
   - 离线救援工具 `gridform_core.module_recovery`。

**关键证据：**

- **方法身份变化（基线 → flat73）：**

  | 项目 | 基线 | flat73 |
  |---|---|---|
  | graph | `844fd4f2…` | `915f2d4b…` |
  | execution identity | `12f7384b…` | `36502bd4…` |
  | 电池报价 | 18.5185 | 73.0 |
  | 电池放电 / CCGT 发电（MWh） | 9.339 / 428.13 | 0 / 437.05 |

  Compare 页显示 “模块方法 已改变 / Only the storage-cost module differs”，年度差值按规则扣留。
- **不升版本静默改公式：** readiness 显示 READY，Run 在快照之后 fail-closed，报 `GF_COMPATIBILITY_001 … reseal with --correction <id>`。拦截正确，但时机太晚，见 M-D6。
- **方法升级：**
  - 分类为 `method_upgrade_required`，`confirmable=true`；
  - 对话框正常弹出；
  - 负向路径全部按预期拒绝：Esc 取消、取消后再点 Run、API 直接启动（409 `GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED`）、迁移请求不带 diff 或带错误 diff；
  - 确认后生成 rev 2，报价 43.5185，P30–P32 清算价相应上升；
  - 不使用该模块的 Study 不受影响。
- **坏模块：**
  - 安装时拒绝，后端存活；
  - 已装模块被改坏后，启动为 degraded，Modules 页出现隔离面板；
  - 只拒绝选用它的 Study（`GF_STUDY_MODULE_QUARANTINED`），VALUE 101 基线照常运行；
  - Rescan 和 Disable 两条修复路径都能恢复（Disable 路径有 M-D4 的问题）。
- **截图：** `$ROLES/edit-module/shots/` 下 10 张（01-edit-module-workbench、03-workbench-candidate-vs-reference、04-run-compare-baseline-vs-flat73、05-method-change-dialog、06-after-confirm-run、07-quarantine-panel、08-quarantined-study-refused、09-after-fix-rescan、10-after-disable、11-compare-inplace-edit-73-vs-99）。

**缺陷：**

| ID | 严重度 | 描述与复现 | 复核状态 |
|---|---|---|---|
| M-D1 | 中 | order 账本里储能报价恒为 0.0：储能出清行以 `supplemental` / `accepted_non_generator_offer` 写入，价格写死为 0.0，offered 等于 accepted；未被接受的储能报价完全不写入（`runtime_compat/modular_simulation_model.py:3451-3461`）。真实报价只出现在 `clearing_inputs.payload_json`。复现：`select offer_price_gbp_per_mwh from orders where asset_type='Battery'`，再对照 clearing_inputs | 未复核 |
| M-D2 | 中 | 已安装的外部模块在原地改源码（同 ID、同版本）会被静默接受：Rescan 返回 ok，修订分类为 `none`，没有迁移对话框，运行直接用新代码（73 → 99）。这与 MODULE_DEVELOPER_101 §2 “refuses a silent source update under an installed ID” 不符。已有的缓解：run 记录了新的 source_sha256（`836d9086…`，安装时为 `bdfb9ab4…`），Compare 页显示“模块方法 已改变”；但 preflight 和运行都没有警告，scientific_version 也没变 | 未复核 |
| M-D3 | 中 | Study 选用了被隔离或被禁用的模块时，Check readiness 显示 “Preflight identity changed. Refresh the saved Study and check it again.”，Run 按钮仍可点。原因：preflight 返回的 `project_revision_sha256` 为 null，`preflightMatches` 失败后整份报告被丢弃（`app/page.tsx:1235`、`app/features/workspace/preflightIdentity.ts:9-15`）。API 实际返回了正确的 `GF_PREFLIGHT_MODULE_QUARANTINED` 和修复指引 | 未复核 |
| M-D4 | 中 | 禁用隔离模块、修好源码后，在 UI 里 Enable 一直报缓存的旧错误 `GF_MODULE_REGISTRY_CONFLICT … SyntaxError`。Rescan 按钮只在隔离面板里，模块禁用后面板消失，所以 UI 里没有出路，只能调 `POST /api/modules/rescan` 或重启 | 未复核 |
| M-D5 | 低-中 | Rescan 不会重新校验已经导入的模块：已加载的模块被改成 SyntaxError 后，Rescan 仍报 “no module is quarantined”，要等到运行时 fail-closed 或重启才暴露 | 未复核 |
| M-D6 | 低 | preflight 不校验 runtime overlay 封印：未封印的内核改动在 readiness 显示 READY，运行要等快照做完才失败。MODULE_DEVELOPER_101 也没有写内置模块的方法升级流程（版本号、VERSION_LEDGER、`seal_runtime_overlay.py --correction`） | 未复核 |
| M-D7 | 低 | 文档与模板不一致：storage-cost 模板 import 了 `gridform_core.builtin.scheme_c_1000twh.compat.storage_cost`，违反指南“不要依赖 compat 内部实现”；指南 §7/§8 仍写 `force-module.json`、`gridform.module/v2`、`FORCE_DATA_HOME`，实际是 `value-module.json`、`value.module/v2`、`VALUE_DATA_HOME` | 未复核 |
| M-D8 | 低 | 从工作台派生的 Study 原样继承了 `extensions.value_101`（`variant_kind: baseline`、`parent_project_id: null`），谱系元数据不对 | 未复核 |
| M-D9 | 低 | 安装成功后，文件框仍显示上一个文件名；源码实例的 Learn 页提示 “Run the standard VALUE installer”，应提示 `install_synthetic_pack.py --value-101-only`；`resource-readiness.json` 404 | 未复核 |
| M-D10 | 观察 | 内置模块的 `source_sha256` 记录的是转发文件 `gridform_core/builtin/value_modules.py` 的哈希，所有内置模块都是 `09f66c1e…`。run 级的执行身份和 runtime_compat 封印可以兜底，但模块级身份察觉不到 runtime_compat 以外的内置实现改动 | 未复核 |

### 3.4 加功能角色（add new function to VALUE）

**测了什么：**

1. 在网页生成器中写提案并 Validate，下载 ZIP（SHA 与 UI 显示一致）。
2. 本地修改 `after_psm` 和 artifact schema，3 个 unittest 通过；用 `scripts/build_extension_bundle.py` 重新打包。
3. 在 UI 安装扩展，草稿中启用，复制数据包，绑定 audit CSV（26/26 就绪），勾选实验性确认后保存。
4. 跑三种 Run 并与对照 Study 比较：
   - 2 时段 smoke；
   - 48 时段 one-day；
   - two_year_smoke。
5. 命名空间冲突序列，以及冲突后重启。

**关键证据：**

- **输出隔离（2 时段，带扩展对比对照）：**
  - cost ledger、carbon ledger、energy-balance-oracle 逐字节一致；
  - `market.sqlite` 所有表的内容哈希相同；
  - `year-results-v2.json` 有 10 处差异，全部能解释（run_id、ledger URI、写入耗时、新增的 `extension_state` 和 `extension_artifacts`、`annual_input_state_sha256`）。
- **身份：** 冻结的 hook `source_sha256` 为 `7f1abcac…`，与作者本地修改后的 `hooks.py`、已安装的 `hooks.py` 三者一致；`observed_run_id` 等于本次 Run 的 ID。
- **命名空间冲突：**
  - 安装或启用同命名空间的扩展，都返回 409 `GF_EXTENSION_NAMESPACE_COLLISION`，并指向占用者；
  - `modules/` 树摘要前后不变（`ce6154e0…`、`a3efebc6…`）；
  - 重启后 health 为 ok，新 Run 正常完成。G4-01（冲突写盘后后端起不来、Run 永远 queued）已修复；
  - 网页生成器在 Validate 阶段就拒绝冲突命名空间。
- **被引用即保护：** A 被 2 个 Study 引用，UI 拒绝停用，提示正确。
- **文件：** 截图在 `$ROLES/add-feature/shots/`（10 张），日志、API 响应和对比在 `$ROLES/add-feature/ev/`，作者包在 `$ROLES/add-feature/author/`。

**缺陷：**

| ID | 严重度 | 描述与复现 | 复核状态 |
|---|---|---|---|
| F-D1 | **高** | 带扩展的 Run 中，`run.state_chain` 不变量失败，结果页显示 “Scientific validation failed / Treat results as unverified”。测试员认为是 initialize hook 引起的；复核发现，**只要 Study 选了任何扩展**都会失败。在修正口径下，按代码路径推断，这还会拦下整年 Run 的年度经济结果。详见 4.1 节 | **已独立复现，范围比报告的大** |
| F-D2 | **高** | UI 里唯一的 48 时段范围 `value_101_day` 走纯 PSM 路径，不执行扩展。Run 显示 completed，但没有任何扩展输出；Inspect 只给出 `year_results_missing`，会误导用户；预检也没有警告。另一个 48 时段范围 `validation_24h` 被教学包拒绝（`GF_PREFLIGHT_TEACHING_RUN_MODE`）。详见 4.2 节 | **已独立复现** |
| F-D3 | 中 | 在 UI 中停用扩展后，它的卡片从列表里消失，全站找不到 Enable 控件（`app/page.tsx:1516` 只遍历已启用的 `workspace.extensions`）。只能调 API `POST /api/extensions/<id>/enable` 重新启用 | 未复核 |
| F-D4 | 中 | 在 Data 页改选另一个已有的草稿数据包后，草稿不会重新解析：上下文显示 “Not evaluated”，Review 显示 “0 of 0 required roles ready”，Graph SHA 显示 not resolved，实验性确认框消失，网络里也没有新的 `resolve-draft` 请求。绕行办法：改动任意一个字段，或者一开始就在 Identity 步骤选好数据包。用“复制”生成的新包不受影响 | 未复核 |
| F-D5 | 低 | 两个一日 Run 唯一的差别是加了扩展，比较结果却显示“模块方法已改变”，“参数与扩展配置”反而显示一致；说明文字写的是 “storage-policy causal effect”；变化详情是数 KB 的原始 JSON。（复核 F-D2 时发现：一日 Run 的 `module-resolution.json` 记录了扩展图，但扩展并没有执行。这条比较结果实际上是把“记录了但没执行”的扩展算成了方法变化） | 未复核（成因见 4.2） |
| F-D6 | 低 | 独立 Study 草稿只保存在内存里，整页刷新后丢失；编辑已有 Study 时标题仍是 “New study”；`resource-readiness.json` 404；扩展安装成功后，文件框仍保留上次的文件名 | 未复核 |
| 观察 | — | ① 新数据目录中的第一个 Run，snapshotting 用了 171 s，之后约 35 s（归档 521 MB 运行时）。② `source_inputs_sha256` 是对含 `run_id` 和 `extension_state` 的 PSM 输入求的哈希，同一修订跑两次也会不同，不能跨 Run 比较 | — |

## 4 高严重度缺陷的独立复核

复核时 INTEG 只读：`PYTHONPATH` 指向 INTEG，Python 一律通过 `vpy` 包装器调用（不写 .pyc）。数据包复制到 scratch 后再改；`HOME`、`TMPDIR`、`VALUE_DATA_HOME` 都指向 `$ROLES/consolidate/`。没有启动 HTTP 服务。脚本和输出见附录 A。

### 4.1 F-D1：选了扩展的 Run 必然 `run.state_chain` 失败（已复现，范围更大）

**方法：** 与现有测试 `tests/test_prompt65_extension_framework.py:172` 走同一条路径：`run_project_application`，数据用 `value-synthetic-contract-pack-v1`，扩展用内置的 `value-toy-audit-extension`（带 initialize 和 after_psm 两个 hook）。三个变体：

- A：选该扩展；
- B：对照，不选扩展；
- C：选该扩展，但让 initialize 不返回任何输出（相当于没有 initialize hook 的扩展）。

**结果：**

| 变体 | 范围 | run invariants | 失败的链接 | scientific_validation_status | validation_gate（production，value-corrected） |
|---|---|---|---|---|---|
| A | smoke | failed（`run.state_chain`） | 2025 年 `previous_state_is_annual_input`：actual `8f4a6915…`，expected `a0fbd278…` | **failed** | **failed**（`run_invariants: failed`） |
| B | smoke | passed | — | not_evaluated | not_evaluated |
| C | smoke | **failed**（`run.state_chain`） | 2025 年同一链接：actual `c628fd31…`，expected `a0fbd278…` | **failed** | **failed** |
| A | two_year_smoke | failed | 只有 2025 年这一条；2026 年的链接正常 | — | — |
| B | two_year_smoke | passed | — | — | — |

**根因（代码核对）：**

- `gridform_core/v2/orchestrator.py:314-332`：只要 `extension_runtime` 存在，就把 `extension_state` 键写进初始状态，即使 initialize 没有输出、写进去的只是 `{}`。
- `orchestrator.py:355` 用写入后的状态计算 `annual_input_state_sha256`。
- `gridform_core/application.py:2162` 传给 `run_invariants` 的 `initial_state_sha256` 是写入前的 `contract_hash(source_initial_state)`。
- 因此第一年的链接必然不等。

**影响（比测试员报告的大）：**

1. **影响范围：** 不只是带 initialize 的扩展，任何被选中的扩展都会让 Run 被判为科学验证失败。加功能角色的每一个 Run 都会显示 “Treat results as unverified”。
2. **修正口径的整年 Run：**
   - `scientific_validation.py:560-564`：production gate 失败 → `annual_economics_eligible=False`；
   - `backend/model_runner.py:765-780`：于是 `results=[]`，并标记 `publication_blocked`（`GF_VALIDATION_GATE_FAILED`）；
   - 结论：17520 时段的 two_year / full Run 只要带扩展，年度经济结果就**不会发布**。
   - 这一点是按代码路径推断的，本次没有跑 17520 时段的整年 Run。
3. **doctoral 口径：** 原始不变量失败时按 Q14 扣发，推断结果相同，没有实测。
4. **测试缺口：** 现有的 toy 扩展两年测试只断言 bundle validation，不检查 run invariants，所以这个问题没有被发现。

**修复建议（小改动）：**

- 让状态链的起点使用扩展 initialize 之后的状态。`provenance.py:383-387` 已经区分 `source_initial_state_sha256` 和 `effective_initial_state_sha256`，可以直接复用；
- 或者由 orchestrator 记录一个 `extension.initialize` 阶段事件，状态链按 source → initialize → annual input 校验；
- 两种做法都要在 `test_toy_extension_runs_two_years_through_normal_application_path` 中补上 `run-invariants.json` 为 passed 的断言，并补一个 C 类（initialize 无输出）的用例。
- golden 案例都不带扩展，所以 doctoral 的 trajectory 不受影响。

**判定：** 高，**确认，建议作为发布阻断项**。

### 4.2 F-D2：48 时段一日范围静默跳过扩展（已复现）

**方法：** 用 golden C3 项目（修正口径，`value_101_day`）。数据用 scratch 中复制的 `value-101-baseline-v1`，并绑定 toy 扩展的角色；Study 选 `value-toy-audit-extension`；以 `mode=value_101_day` 调用 `run_project_application`。

**结果：**

- `execution_engine` 为 `value-psm-only/v1`；
- `orchestrator-events.jsonl` 中只有 `psm.run` 一个阶段；
- 没有 `year-results-v2.json`，也没有任何扩展产物；`one-day-market-result.json` 中没有 `extension_artifacts`；
- 但是 `module-resolution.json` 的 `extension_graph` 列出了 `value-toy-audit-extension`。也就是说，Run 的身份记录声明了一个实际没有执行的扩展。

**代码核对：**

- `gridform_core/application.py:1874-1984` 是一日课程的纯 PSM 分支，在第 2018-2022 行创建 `ExtensionRuntime` 之前就返回了。
- `gridform_core/preflight.py` 没有检查“所选范围是否会执行所选扩展”。
- `app/features/workspace/runScope.ts:17-18` 只要 Study 来自 VALUE 101，就开放 One-day 范围，不看是否选了扩展。

**影响：**

- 加功能用户只用随附数据包时，没有任何 48 时段范围会执行扩展，而 UI 给出的是 “completed”。
- Run 身份中记录了扩展，所以比较页把这两个 Run 归为“模块方法已改变”（F-D5），实际上两者的计算完全相同。

**修复建议：**

- 最小改动：选了扩展时，预检对纯 PSM 范围给出阻断错误或明确警告，UI 不再为这类 Study 提供 One-day；同时把 Inspect 的原因改为“本范围不执行扩展”。
- 另一种做法是让一日路径也调用 initialize 和 after_psm。这会改变方法语义，由作者决定（见第 6 节）。

**判定：** 高，**确认**。最小改动可以在发布前完成。

### 4.3 S-D1：Readiness 卡片截断，plausibility 警告看不到（已复现）

**方法：** 直接调用 `run_preflight`，与 `POST /api/projects/<id>/preflight`（`backend/server.py:3987`）是同一个调用。项目用 C3（`value_101_day`），数据用 scratch 中复制的两个 VALUE 101 包：

- 一个保持原样；
- 一个把 `france-price.csv` 首行改为 6087、`france-profile.csv` 首行改为 500，并同步更新 manifest 中的 sha256 和 bytes。

**结果：**

| 包 | errors | warnings | UI 显示的前 6 条 | 被藏起来的 plausibility 发现 |
|---|---|---|---|---|
| 原样副本 | 2 | 15 | OUTPUT_PERMISSION、DISK_SPACE、UNSAVED_REVISION、3 条 DATA_WARNING | — |
| 改值副本 | 2 | 17 | 同上 | 第 18 条 `GF_DATA_PLAUSIBILITY_PRICE`（“france price range [82, 6087] outside [-500, 5000] GBP/MWh”）、第 19 条 `GF_DATA_PLAUSIBILITY_FLOW`（“france \|flow\| 500 MW exceeds 58.62 MW”） |

- 那 2 条 error 来自复核环境本身（没有创建输出目录、磁盘余量不足），把列表又往后推了两位。测试员的实例里共 14 条，plausibility 排在第 13、14 条。
- 不论哪种环境，排在 plausibility 前面的都是 VALUE 101 包自带的十几条 “unit is not declared; canonical role expects …” 适配器警告。

**代码核对：**

- `app/features/runs/RunWorkspace.tsx:88`：`[...preflight.errors, ...preflight.warnings].slice(0, 6)`，没有“还有 N 条”的提示。
- `gridform_core/data_validation_layers.py:315-327`：teaching 和 user_workspace 包的 plausibility 发现只记为 warning，不会阻断 Run。

所以这些发现本来就不阻断运行，唯一能看到它们的地方又被截掉了；再加上 S-D2，plausibility 这一层在 UI 中完全看不到。

**修复建议：**

- 显示全部问题（可以折叠），或者显示“还有 N 条”；
- 把 data、plausibility 类的发现排在适配器提示之前；
- 补一个前端测试：preflight 有 14 条问题时，最后一条必须能看到。

**判定：** 高（对换数据角色而言），**确认**。改动很小，建议发布前修复。

### 4.4 S-D2：UI 中看不到三层校验结果（代码核对确认）

**核对：**

- 在 `app/` 中搜索，没有任何代码调用 `/api/data-packs/<id>/validation`（`backend/server.py:1808`），也没有读取 `plausibility_status`（`backend/server.py:989`）。
- `docs/dev/P0_FRONTEND_DESIGN_SPEC.md` 中没有校验层视图。施工计划把 S9 定为只改 API（`P0_CONSTRUCTION_PLAN.md:1002`：“validate 端点支持 `?profile=`；`list_packs` 新增 `plausibility_status`”）。

所以这不是实现偏离规格，而是**规格缺口**：后端已经提供了这些数据，前端没有设计对应的视图。

**判定：** 中-高，**确认**。

- 修好 S-D1 后，plausibility 警告至少能在 readiness 中看到，缺口可以缓解一部分。
- 要在 Data 页显示三层状态和口径资格，需要先由 lead 补设计，再实现。

## 5 跨角色的共性问题（合并去重）

| 主题 | 涉及缺陷 | 说明与建议 |
|---|---|---|
| 校验结论在 UI 中看不到，或原因说错 | R-D1、R-D11、S-D1、S-D2、M-D3、F-D1、F-D2 | 后端证据完整，但到界面时被截断、被丢弃，或说错了原因。建议把 readiness、状态条、Inspect 的“原因”统一由后端的 reason_code 和 advisories 驱动，不要在前端拼文案 |
| 停用后无法在 UI 中恢复 | M-D4、F-D3 | 模块和扩展停用后，UI 都没有 Enable 或 Rescan 的入口。建议在 Modules 页常驻停用列表，并提供 Rescan 按钮 |
| 比较页难读，或分类不对 | R-D7、S-D9、F-D5 | identity 差异直接显示成原始 JSON；说明文字固定为 storage-policy；扩展和数据变化的分类不准。建议按角色和槽位列出差异，说明文字按变化的维度生成 |
| `resource-readiness.json` 404 | R-D6、S-D11、M-D9、F-D6 | 四个角色都遇到，不影响功能。PSM-only Run 不生成这个文件，前端应该把它当作可选文件 |
| Runs 页状态过期 | R-D2、S-D12 | 占位文字 “No runs yet” 一直保留，多次 Run 标签无法区分，Check for 范围会被重置 |
| 编辑时标题仍是 “New study”，文件框残留上次的文件名 | R-D11、F-D6、M-D9 | 界面细节 |
| 第一次 Run 很慢，且没有说明 | S-D10、M（性能观察）、F（观察） | 新数据目录的第一次 snapshotting 需要约 3 分钟（归档约 500 MB 运行时），之后约 20–35 s。建议在 snapshotting 阶段显示“首次归档运行环境”的说明，并且不要把用户强制拉回 Runs |
| 文档与实际不一致 | M-D2、M-D6、M-D7、M-D9 | MODULE_DEVELOPER_101 仍有 force/gridform 时代的名称，缺少内置模块的方法升级流程；Learn 页的安装提示不适用于源码实例 |

## 6 需要作者决定的事项

1. **S-D3：互联线“进口”的语义。** 保留内核的日前出清不接收 connections，正的 transfer_constraint 不会产生进口。
   - 如果这是论文设定：doctoral 保持不变，修正口径和 UI 文案改为“外售可用容量”，VALUE 101 中关于 imports 的说法也要改。
   - 如果需要进口：这属于修正口径的方法改动，按 Q13 需要显式确认。
2. **F-D2：选了扩展时一日范围怎么处理。** 二选一：(a) 预检阻断，这是建议的最小方案；(b) 让一日路径也执行扩展 hook。
3. **M-D2：已安装模块原地改源码。** 二选一：按文档拒绝（Rescan 时比对安装时的 source_sha256，不一致就隔离）；或者修改文档，接受现在的“记录新哈希、Compare 显示已改变”的做法。
4. **R-D1：doctoral 扣发的说明文字。** 建议直接写出失败的原始不变量（储能单向性，DEV-STO-01），并在状态条上加一项储能不变量；同时在规格 2.3 中补上 `reproduction_conformant` 的配色（由 lead 设计）。
5. **R-D10：golden D3 的 identity 区。** `runtime_kernel_tree_sha256` 落后于当前代码，是否随下一次 identity 刷新一起同步？这不影响 trajectory 和 accounting。

## 7 建议

**发布前必须修（已确认，改动都不大）：**

1. **F-D1：** 修正状态链的起点，并补回归测试（见 4.1）。
2. **F-D2：** 至少加上预检阻断或警告，并修正 UI 范围选项和 Inspect 的原因文案（见 4.2）。
3. **S-D1：** Readiness 显示全部问题，或显示“还有 N 条”，并调整排序（见 4.3）。

**强烈建议同批修复：**

- S-D4、S-D5：时间戳列和币种防错，否则错位或误标的数据会静默进入模型；
- M-D3、M-D4、F-D3：隔离和停用后在 UI 中的出路；
- R-D1：说清扣发的真实原因；
- S-D2：先补设计，再实现；
- M-D1：order 账本中的储能报价写为 0.0，模块作者没法核对自己的报价公式。动这里之前，先确认这一行属于账本记录，不在 doctoral 轨迹的冻结范围内。

**可以延后：** 其余低等级和信息类问题，以及第 5 节的界面细节。

**整体判断：** 四个角色的主路径都能走通。所有拒绝都是 fail-closed，没有静默写错数值，与 golden 逐列一致，重跑可重复，安装保持完好。修复上面三项后，分支可以作为 0.7.0-alpha.1 的发布候选再做一次快速回归：只需重跑加功能角色的 2 时段和两年 smoke，以及换数据角色的 readiness 截图。

## 8 安全与环境核对

- **四个角色：**
  - 都只按自己记录的 PID 停止进程，端口 18810–18817 和 18819 都已释放，没有向 8766/8800 发请求或信号；
  - 本次复核时再次确认，各角色记录的 PID（4187319、4189847、185702、4187497）都已不存在。
- **本次复核：**
  - 没有启动任何服务；Python 全部通过 `vpy` 调用；
  - INTEG 中 `git status --short` 为空，没有新的 `__pycache__`；
  - scratch 产物在 `$ROLES/consolidate/` 下，合计约 8 MB。
- **INSTALLED（本次复核结束时执行）：**
  - `find <INSTALLED> -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`。它是 0 字节文件，mtime 为 2026-10-03 05:41:26，比 receipt 晚 17 s，是安装后首次启动时生成的，不是本轮写入；
  - `diagnose-value --prefix <INSTALLED>` 退出码为 0，输出 “Installation integrity and runtime checks passed.”。运行中打印过一行 vinext 的 “Static file stream error … Premature close”，那是诊断探针中断静态文件流时的日志，不影响结论。
  - 四个角色各自结束时做的同样两项检查，结果相同。

## 附录 A 复核脚本与输出

`$ROLES` = `/tmp/claude-1000/-home-deepseek--config-Claude-scratch-workspaces-236b67cc-cc11-47c6-901f-9efac7ff2b1f-954fe4c9-9c87-4a98-b62f-216510b0e0f0-scratch-2026-10-04-a946e8/fd56b27b-0c52-4166-89c3-a4a8b5e4ea96/scratchpad/build/roles`。这是会话的 scratch 目录，可能被清理；需要长期保留的证据，请在清理前另行归档。

| 脚本 | 复核项 | 调用方式 |
|---|---|---|
| `$ROLES/consolidate/repro_af_d1.py` | F-D1（变体 A/B/C；smoke、two_year_smoke） | `PYTHONPATH=<INTEG> vpy repro_af_d1.py <INTEG> <out> smoke` |
| `$ROLES/consolidate/repro_af_d2.py` | F-D2（C3 一日 + toy 扩展） | `PYTHONPATH=<INTEG> vpy repro_af_d2.py <INTEG> <out>` |
| `$ROLES/consolidate/repro_sd_d1.py` | S-D1（preflight 问题数量与位置） | `PYTHONPATH=<INTEG> vpy repro_sd_d1.py <INTEG> <out>`，输出在 `sd-d1.json` |
| `$ROLES/consolidate/diagnose.txt` | INSTALLED 诊断输出 | — |

## 附录 B 角色证据位置

| 角色 | 目录 | 内容 |
|---|---|---|
| 复现 | `$ROLES/reproduce/` | `shots/`（9 张）、api.log、ui.log、build.log、pids.txt、runs-final.txt |
| 换数据 | `$ROLES/swap-data/` | `shots/`（10 张）、`evidence/`、`input/my_gb_data_48rows.csv`、api.py、驱动客户端 `d`、日志 |
| 改函数 | `$ROLES/edit-module/` | `shots/`（10 张）、`scripts/`（Playwright 脚本）、restart.sh、api.log、ui.log |
| 加功能 | `$ROLES/add-feature/` | `shots/`（10 张）、`ev/`（日志、API 响应、对比、diagnose.txt）、`author/`（作者包和测试） |
