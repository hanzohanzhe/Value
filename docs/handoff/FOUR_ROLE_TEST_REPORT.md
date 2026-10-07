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
- **修复轮之后的状态见第 9 节“修复轮复测（2026-10-06）”**（被测 HEAD `cd2d72c`）。第 1–8 节保留首轮（HEAD `a987ca4`）的原始记录，没有改写。
- **复测之后落地的 A18（修正口径核电开局在运，FX8）见第 9.10 节**：不改界面，四个角色没有为它重测。
- **R1 轮（A19–A22a，R1-1 至 R1-5）之后的复测见第 10 节“R1 轮复测（2026-10-07）”**（被测 HEAD `e0ec659`）：四个角色都通过，没有高缺陷，新增 1 项中等缺陷 R3-N1；仍未关闭的项汇总在第 10.7 节。第 9 节保留修复轮的原始记录，没有改写。
- **R2 轮（DECISIONS A23，单元 R2-1、R2-2）之后只做了定向复核，见第 11 节“R2 定向复核（2026-10-07）”**（代码状态 HEAD `71cd564`）：按作者“不要无止境测试”的要求和 A23，没有做四角色全量复测；A23 列出的各项都已处理，逐项写明状态与证据。第 10 节保留 R1 复测的原始记录，没有改写。

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

## 9 修复轮复测（2026-10-06）

- **被测版本：** 分支 `fix/review-2026-10-04`，HEAD `cd2d72c2a3e9988e526192ca743bb99b70a2bf93`，即 A16 修复轮（FX1–FX7）全部提交之后。四个角色仍用 `git archive HEAD` 导出到 scratch，没有改动 INTEG。
- **修复范围（DECISIONS A16-1）：** 必须修 F-D1、F-D2、S-D1；同批修 S-D4、S-D5、M-D3、M-D4、F-D3、R-D1、M-D1、S-D2。另有 A16-2（修正口径日前进口，对应 S-D3）、A16-3（F-D2 的处理方式）、A16-4（M-D2 接受并记录）、A16-5（VoLL 17,000 £/MWh）。不在范围内的缺陷没有修，复测中仍存在属于预期。
- **方法：** 与首轮相同，每个角色起自己的 API 和 UI 网关，用 Playwright headless（chromium 1243）操作界面，API 只用来读证据或做负向用例。四份复测报告的原文同样只存在于工作流输出中，本节是它们唯一入库的记录。

| 角色 | 实例端口（API/UI） | 主要证据目录 |
|---|---|---|
| 复现 | 18830 / 18831 | `$ROLES2/reproduce/`（`shots/` 32 张、`golden-cmp.txt`、`corrected-run.json`、`doctoral-run.json`） |
| 换数据 | 18832 / 18833（驱动 18839） | `$ROLES2/swap-data/`（`shots/`、`evidence/`、`input/`） |
| 改函数 | 18834 / 18835 | `$ROLES2/edit-module/`（`shots/` 21 张、`evidence/md1-reconcile.txt`、`author/`） |
| 加功能 | 18836 / 18837 | `$ROLES2/add-feature/`（`shots/` 38 张、`ev/`、`pw/`） |

`$ROLES2` = `…/scratchpad/build/roles2`，完整路径见附录 A。

### 9.1 结论

| 角色 | 复测结论 | 本轮范围内的缺陷 | 首轮的高缺陷 | 新发现的最高严重度 |
|---|---|---|---|---|
| 复现 | **通过** | R-D1 已修复 | 无 | 信息（O-1～O-3） |
| 换数据 | **通过，带两项中等新问题** | S-D1、S-D2、S-D5 已修复；S-D3 在修正口径下已生效；S-D4 大部分修复 | S-D1 已修复 | 中（N-1、N-2） |
| 改函数 | **通过** | M-D2、M-D3、M-D4 已修复；M-D1 账本已修复，界面仍看不到逐条接受量 | 无 | 低 |
| 加功能 | **通过** | F-D1、F-D2、F-D3 已修复 | F-D1、F-D2 已修复 | 中（F2-N1，即 G4-05 实测出现） |

**一句话结论：** 首轮的三项高缺陷 F-D1、F-D2、S-D1 都已在真实实例中验证修复；A16-1 同批修复的 8 项中，6 项已修复（S-D2、S-D5、M-D3、M-D4、F-D3、R-D1），S-D4 大部分修复（残留 N-2、N-3），M-D1 只修好了账本、界面仍有残留。复测**没有发现新的高缺陷**，所以本轮没有需要独立复核的高缺陷。不过三项中等新问题 N-1、N-2、F2-N1，本轮另做了代码核对或独立复现（见 9.6）。主路径在四个角色中都能走通；golden 对照、重跑可重复和 INSTALLED 完好这三点都保持不变。

### 9.2 复现角色

**过程：** 在全新的数据目录中走完整条复现路径：装包 → 建基线 → 建复现 Study → corrected 一日 Run → doctoral Study 和 Run → 各重跑一次 → 两组比较 → strict 冻结输入复现 → Market replay、Inspect、Network 页 → 375 px 宽度。

**关键证据：**

- **R-D1 已修复。**
  - doctoral Run 状态条上，`Energy balance ● Conformant` 为 teal；新增字段 `Raw invariants ● 1 failed` 为琥珀色，悬停显示 “Storage single direction”。这个字段只在 doctoral Run 上出现。
  - Callout 标题为 “Annual results withheld for this reproduction run”，正文写明失败的原始不变量（Storage single direction，10 行）和命中的声明偏差 DEV-STO-01，下方有 “Open in Inspect” 和 “Export ledger”。
  - 与 API 一致：`raw_invariant_failures=[{check: storage.single_direction, count: 10, deviation_ids: [DEV-STO-01]}]`，`unexplained_checks=[]`，`result_publication=withheld`（`GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED`）。
  - 冻结恢复的 Run 同样被扣发，失败项相同。375 px 下状态条和 Callout 显示正常。截图：`17-doctoral-run-selected.jpg`、`18-doctoral-context-bar.jpg`、`25-doctoral-context-375.jpg`。
- **VoLL 17,000（A16-5）两个口径都已生效：**

  | 位置 | corrected | doctoral |
  |---|---|---|
  | `market_rule_set.voll_gbp_per_mwh` | 17000.0 | 17000.0 |
  | `rules.reliability_voll` | `chronology_parameter` | `constant_17000` |
  | Study `market_configuration.voll_gbp_per_mwh` | 17000.0 | 17000 |

  参数注册表默认值为 17000.0，说明中写有 “decision A16-5”。这一天没有切负荷（`blackout_mwh=0`），所以 VoLL 不改变任何成本数字。一日 Run 不显示成本构成，界面上看不到 VoLL。
- **与 golden 对照**（exact 模式）：

  | UI Run | 参考 | 列数 | trajectory / accounting 差异 | identity 差异 |
  |---|---|---|---|---|
  | corrected 首跑、重跑 | C3（15 个修订） | 894 / 894 | 只有 `run_id`、`result_id` | 0 |
  | doctoral 首跑、重跑、冻结恢复 Run | D3（13 个修订） | 932 / 932 | 只有 `run_id`、`result_id` | 13 列（见 R-D10） |

- **重跑可重复：** market.sqlite（sha256 前 16 位）corrected 三个 Run 都是 `c2152bcd7eef62aa`，doctoral 三个 Run 都是 `5755489c2733fa0f`；`energy-balance-oracle.json`、`run-invariants.json`、`scientific-validation.json`、`market/index.json`、`stage-parity.json` 同口径逐字节相同。
- **窗口卡数值与首轮完全相同**：corrected 需求 775.49 / Accepted supply 787.02 / Shortfall 0 / 充电 11.53 / 放电 9.34 MWh，£37.06/MWh；doctoral 775.49 / 780.49 / 0 / 48.34 / 39.15，£36.48/MWh。
- **比较页：** 复现 Run 对基线 Run，五个维度全部一致；corrected 对 doctoral，显示 “This comparison needs review”，并点名 “The Runs use different methodologies”。
- **原 Study 未被改动：** `value-101-baseline` 仍为 rev 1，只有 1 份修订。

**首轮缺陷逐条状态：**

| ID | 状态 | 本轮证据 |
|---|---|---|
| R-D1 | **已修复** | 见上。规格 2.3 中 `reproduction_conformant` 的配色属于设计文档，FX3 列为遗留，本轮没有核对文档 |
| R-D2 | 仍在 | 同一 Study 两个 Run 的下拉标签仍完全相同，且保留 “No runs yet for this Study” 选项。点 Run 后 POST 要 36–45 s 才返回（新 Study 首次为 2 min 51 s），这期间 Run history 一直显示 “No runs yet” |
| R-D3 | 仍在 | Market replay 仍显示 “No stress events in the 0% of 2025 that has been computed.”（`coverage_percent=0.0`、`annual_status=non_annual`）；状态条上的 Stress events 字段正确显示 “None” |
| R-D4 | 仍在 | 冻结输入核对 21.0–21.6 s、创建 21.5 s，期间只有 `aria-busy` 和禁用的按钮 |
| R-D5 | 仍在 | doctoral Network 页仍把两个原因拼成一句（API 409）；corrected 铜板 Run 仍显示 “network evidence pending” |
| R-D6 | 仍在 | `resource-readiness.json` 每页 404 2–4 次，`planning/events`、`planning/projects` 404，Inspect 默认打开空的 Planning 标签。新现象：Run 在快照阶段时，前端轮询 `input-snapshot/project.json`、`snapshot.json`，也返回 404 |
| R-D7 | 部分改善 | 口径变化已在 needs-review 原因中点名；Changed dimensions 仍是原始 JSON（`identity.method` 4485 字符，`identity.config` 5323 字符） |
| R-D8 | 部分改善 | Run、Market replay、首页在 375 px 下不再横向滚动；Inspect（scrollWidth 866，来自 Planning projects 筛选表单）和 Studies（488，来自 `composer-panel`）仍横向滚动 |
| R-D9 | 仍在 | `market_ledger.uri` 仍是本机绝对路径；四个 Run 的 `psm_input_sha256` 各不相同，market.sqlite 相同，只是身份记录问题 |
| R-D10 | 仍在，差异变大 | 首轮差 1 列，本轮差 13 列（`psm_module_version`，当前为 6.3.0；`rule_set_sha256`、`rules`、`switch_corrections`、`runtime_kernel_tree_sha256`、`source_artifact_sha256` 等）。原因：D3 的最后一次修订 r12 来自 FX5（base `b591059`），之后 FX6 把 PSM 升到 6.3.0，C3 已同步而 D3 没有。按 A16-8 由负责人决定，不设门 |
| R-D11 | 仍在 | 编辑已有 Study 时标题仍为 “New study”。doctoral Run 的 10 条 advisory（6 high、3 medium、1 info）只在比较页的 review 原因中出现，状态条、Callout、Market replay、Inspect 都不显示；`AdvisoryList` 只挂在 `pre_fix` 通知上 |
| R-D12 | 仍在 | 6 个没有调用的模块仍显示 “Evidence pending” |

**新观察（信息级）：**

- **O-1：** 新数据目录中第一次 Run 的快照阶段 2 min 51 s，之后 35–45 s；POST 要等快照结束才返回，界面只显示 “Starting…”。与 R-D2、R-D4、S-D10 同类。
- **O-2：** 6 个一日 Run 加一次冻结核对后，`state/execution-archives` 为 500 MB，`runs/` 只有 50 MB。
- **O-3：** VoLL 的修正 id 没有写进 Run 的方法学记录：doctoral Run 的 `applied_correction_ids` 共 10 个，其中没有 `fx5.voll-17000`；`switch_corrections.reliability_voll` 写的是 `p06.voll-chronology-parameter`，而规则值是 `constant_17000`。FX5 报告偏差 5 已说明通用核算修正不写入修正目录，所以不算缺陷，但从 Run 记录看不出 8000 改为 17000。是否在 Run 的来源记录中点名，由负责人决定。

### 9.3 换数据角色

**过程：** 教学基线 → 复制 BASE 包 → 在 Data 页通过 UI 映射 4 个角色（都声明了时间戳列）→ 创建换数据 Study → 一日 Run。另做一个负向包（法国价格首行 6087、流量首行 500）和多组时间戳负向文件。

**关键证据：**

- **S-D1 已修复。** 负向包的 Readiness 卡片按组显示：
  1. `Data plausibility · 2`：默认展开，两条完整显示；
  2. `Other data warnings · 4`：折叠；
  3. `Adapter: unit not declared · 8`：折叠。

  同一 code 合并为一行，悬停列出全部对象；375 px 下没有横向滚动。截图 `27-readiness-neg-plausibility.png`、`30-readiness-neg-mobile.png`。
- **S-D2 已实现。** Data 页每个包有校验面板：`Validation`（Structural / Chronology / Plausibility）、`Methodology use`（Corrected / Doctoral reproduction）和 `Show details`；状态随数据变化（映射后 Structural warnings 从 14 降到 10，负向包显示 `Plausibility ● 2 warnings`）。但 Methodology use 一行有 N-1 的矛盾。
- **S-D3 在修正口径下已生效（A16-2）。** 法国价格设为 40 / 30 £/MWh（46 / 34.5 EUR 换算），低于 CCGT 的 66.5 £/MWh：

  | | 基线 | 换数据（本轮） | 换数据（首轮，无日前进口） |
  |---|---:|---:|---:|
  | 需求（MWh） | 775.49 | 837.53 | 837.53 |
  | 法国进口（MWh） | 0 | **282.55** | 0 |
  | CCGT（MWh） | 428.13 | **207.17** | 489.72 |
  | 运行成本（£） | 28,643.41 | 23,820.77 | — |
  | 能量平衡最大残差（MWh） | — | 1.8e-15 | 1.8e-15 |

  - `orders` 中 48 条法国 `ahead_offer`（35 条 accepted、6 条 partial、7 条 rejected），accepted 合计 282.547 MWh，与 `physical_dispatch` 和 `import_mwh` 完全一致（`evidence/import-orders.txt`）。
  - Market replay 第 0 期报价栈中有 `Interconnect_France · boundary import · £40/MWh · 7.5 / 7.5 MWh`，CCGT £66.5 为边际报价；角色标签已改为 “France interconnector availability (+ import / - export)”。
  - 进口按统一边际价结算（收入 £18,137.41，约 £64.2/MWh），与 FX6 报告偏差 2 一致。
  - doctoral 一侧无法从这个角色验证，因为 doctoral 不接受用户数据包。
- **S-D4 大部分修复。** 映射编辑器新增 `Timestamp column` 和 `Time zone`（UTC / Europe/London），预览逐行列出问题，有问题时不能提交。17,520 行文件实测：重复、缺口、倒序、乱码都被拒绝并给出行号；正确的 London 本地钟点（含春秋换时）通过；列名错误、时区不支持、与数值列相同都返回 400 `GF_MAPPING_TIMESTAMP`。提交后的绑定记录了 `timestamp_column`、`timestamp_time_zone`、`timestamp_uri`、`timestamp_check`（`evidence/mapped-bindings.json`）。残留 N-2、N-3。
- **S-D5 已修复（UI 层）。** 列名含 eur 且 Currency 为 GBP 时，出现琥珀色行内提示 “Column name suggests EUR — confirm the currency.”，不阻断（截图 `18-eur-hint-gbp-selected.png`）。按设计只在前端提示，API 预览和审阅报告仍没有 warning。

**首轮缺陷逐条状态：**

| ID | 状态 | 本轮证据 |
|---|---|---|
| S-D1 | **已修复** | 见上 |
| S-D2 | **已修复**（新增 N-1） | 见上 |
| S-D3 | **已修复（修正口径）** | 见上 |
| S-D4 | **大部分修复**（残留 N-2、N-3） | 见上 |
| S-D5 | **已修复（UI 层）** | 见上 |
| S-D6 | 仍在 | 审阅表、规范文件和 `orders.offer_price_gbp_per_mwh` 中有 `40.00000000000001`、`30.000000000000004` |
| S-D7 | 仍在 | 仍显示 `could not convert string to float: 'n/a'`，没有行号和列名，只报第一处 |
| S-D8 | 仍在 | 提交后编辑器回到初始状态，没有成功提示 |
| S-D9 | 仍在 | 比较页仍是 25 个角色的整块 JSON，说明文字仍为 “storage-policy causal effect”，转换过的角色仍是 `identity/v1` |
| S-D10 | 部分仍在 | 首次 snapshotting 3 分 15 秒，第二次 59 s，期间只显示 “Freezing immutable run inputs”；强制拉回 Runs 页本轮没有复现 |
| S-D11 | 仍在 | `resource-readiness.json` 反复 404（第二次 Run 期间 14 次）；首次 snapshotting 期间 `snapshot.json`、`project.json` 约 1.5 分钟内 404 共 89 次 |
| S-D12 | 仍在 | Run 完成后仍显示 “lesson has started”；“No runs yet for this Study” 下方列着 Run；重新加载后 Check for 回到 Two-period |
| S-D13 | 仍在 | Run 面板的 manifest SHA `5e78afac…`（`snapshot.pack_manifest_sha256`）与数据包列表的 `f8e4bc94…`（`snapshot_source_manifest.file_sha256`）不同，界面没有说明两者关系 |

**新发现：**

| ID | 严重度 | 描述 | 本轮复核 |
|---|---|---|---|
| N-1 | 中 | 校验面板和 `GET /api/data-packs/<id>/validation` 对用户数据包（以及 `value-101-network-v1`）给出 doctoral `eligible: true`、`blocking_codes: []`，但 Studies 编辑器选 Doctoral reproduction 后，同一个包被标为 “not available with this methodology”，Review 报 `VALUE_PROFILE_COMBINATION_UNSUPPORTED … is not a thesis-era pack`。证据 `evidence/profile-eligibility.txt`、`shots/26-doctoral-study-review.png` | **代码核对确认**，见 9.6 |
| N-2 | 中 | Europe/London 下，不带偏移的时间戳如果秋季重复的一小时只出现一次，映射预览返回 HTTP 500 `GF_RUNTIME_001`（“Model execution failed…”），没有行号。fail-closed，但文案误导 | **已独立复现**，见 9.6 |
| N-3 | 中低 | 时间轴层不比较首个时间戳与模型时钟或年份：整体错位 30 分钟、年份写成 2023 都能通过；后端已算出 `first_utc`，界面不显示。规格 11.6 只要求单调、缺口和重复，属于规格缺口 | 未复核 |
| N-4 | 低-中 | 首次 snapshotting 时，启动 Run 的 POST 阻塞 2 分 52 秒，同期发出的 clone 也等到它结束才返回；引导页按钮全部禁用，文字为 “正在创建 Study…”，与复制动作不符 | 未复核 |
| N-5 | 低 | 带 `dataContext=journey` 的 Data 页重新加载后显示“引导上下文已失效”，目标包变为“尚未选择” | 未复核 |
| N-6 | 低 | 春季不存在的本地时刻被报为 “unreadable timestamp”；角色卡片不显示时间戳声明；Studies 列表中两个数据包不同的 Study 显示同一个未标注的哈希 `f0acc24c…` | 未复核 |

### 9.4 改函数角色

**过程：** 按 MODULE_DEVELOPER_101 从示例复制 storage_cost 模块 `uat2-flat73-storage-offer`（固定报价 73.0），构建两次（ZIP 字节相同，`ce64ec1c…`），UI 安装（structural conformance passed），派生 Study 并跑修正口径一日 Run；然后原地改源码、改坏、隔离、停用、恢复。

**本轮范围内四项：**

- **M-D1：账本已修复，界面仍有残留（低-中）。**
  - 新的核算表 `storage_orders` 写入真实报价，被接受和未被接受的都写：基线 40 行，价格全部 18.5185（不是 0.0），14 条接受、1 条部分接受、25 条未接受；flat73 170 行全部为 73.0；原地改为 99 后全部为 99.0。
  - 与 `clearing_inputs` 按 (year, period, offer_id) 一一对应（基线 40/40、flat73 170/170，价格差异 0）；基线 P29、P31、P32 各时段接受量之和与 `orders` 电池行相等（`evidence/md1-reconcile.txt`）。
  - `orders` 电池行价格仍为 0.0（`accepted_non_generator_offer`），这是 FX4 记录的偏差 1：`orders` 属于 doctoral 冻结的轨迹列，有意不改。
  - **界面残留：** Market replay 的单时段报价表能看到报价价格，但每条报价的接受量仍显示 “2.5 MWh (asset total)”，而账本中 P29 四条报价分别是 0.75、1.26、0.49、0。`app/` 和 `backend/` 都没有读 `storage_orders`，没有对应的 API；Inspect 仍只读 `orders`。与 FX4 第 8 节的遗留一致。
- **M-D2：已修复，符合 A16-4 和设计规格 11.7。**
  - 把已安装的 `plugin.py` 中 73.0 改为 99.0 后，Readiness 为 Ready，并显示琥珀色提示 “Module uat2-flat73-storage-offer source changed since install (1f4fee48… → a88500a2…). Results will record the new source hash.”（截图 `05`）。
  - 新 Run 的报价为 99.0，新哈希记录在 `module-resolution.json` 和 `input-snapshot/snapshot.json`，执行包哈希 `c52f088b…` → `364e26c8…`，`preflight.json` 的 `checks.module_source_changes` 同时列出新旧哈希。
  - 比较页（73 对 99）只有“模块方法 已改变”；开发者文档已改为允许原地修改并记录。
  - 小问题（低）：`project-snapshot.json` 和 Modules 卡片仍显示安装时的哈希，卡片没有提示源码已变。
- **M-D3：已修复。**
  - 隔离时 Readiness 显示 “Needs attention / Errors · 3”，第一条是 `GF_PREFLIGHT_MODULE_QUARANTINED`，带修复指引；另两条 `MODULE_SELECTION`、`PROJECT_REVISION` 是 FX3 已登记的派生错误。Run 按钮不可点（截图 `13*`）。
  - 停用时显示 “Errors · 2”，Run 不可点；旧的 “Preflight identity changed…” 不再出现（截图 `16*`）。
- **M-D4：已修复。**
  - Modules 页常驻 “Disabled and quarantined” 区，每项有 Enable、Rescan、Remove，页头有全局 “Rescan modules”。
  - 停用时的错误是 SyntaxError；把源码改成导入即 `RuntimeError` 后点 Enable，返回 409 并显示**本次**扫描的 RuntimeError，没有再报缓存的 SyntaxError（截图 `17`）。修好后 Enable 成功，health 恢复 ok（截图 `18`）。
  - 隔离后修好源码再点该行的 Rescan，隔离解除（截图 `20`）；Remove 先二次确认，再因 Study 仍在用而返回 409 `GF_MODULE_IN_USE`（截图 `19`）。
  - 恢复后 Run `…154933-7e4b975d` 完成，报价 99.0。

**首轮其余缺陷：**

| ID | 状态 | 本轮证据 |
|---|---|---|
| M-D5 | 仍在（不在范围） | 已加载的模块被改成 SyntaxError 后，全局 Rescan 仍报 “no module is quarantined”，Readiness 为 Ready；Run 在运行时 fail-closed（`GF_MODULE_IMPORT_FAILED`），要重启 API 才进入隔离 |
| M-D6 | 仍在 | 在 `runtime_compat/storage_cost.py` 末尾加注释（未封印），Readiness 仍为 Ready，Run 在快照后报 `GF_COMPATIBILITY_001`（测完已还原）。开发者文档仍没有内置模块的方法升级流程 |
| M-D7 | 仍在 | 示例模块仍 import `…compat.storage_cost`；指南标题仍为 “FORCE…”，仍写 `gridform.module/v2`、`FORCE_DATA_HOME`、`force-module.json`，与第 9 节的 `value-module.json` 前后不一致；安装目录仍生成 `force-bundle.json` |
| M-D8 | 仍在 | 派生 Study 的 `extensions.value_101` 仍是 `variant_kind: baseline`、`parent_project_id: null`；新的 `derivation` 字段正确 |
| M-D9 | 仍在 | 安装后文件框仍保留 `flat73-1.zip`；每个 Run 有 14 次 `resource-readiness.json` 404；`gridform_core/value_101.py:92` 的安装提示仍是 “Run the standard VALUE installer…” |
| M-D10 | 仍在（观察） | 所有内置模块的 `source_sha256` 仍是 `09f66c1e…` |

**新发现（都是低或观察）：**

| ID | 严重度 | 描述 |
|---|---|---|
| M2-N1 | 低 | 一日 Run 完成或失败后，状态条仍显示 “lesson has started”（同 S-D12）；失败的 Run 在当前视口看不到失败原因 |
| M2-N2 | 低 | 模块被停用时，预检只写 “Module is not registered”，没有专门的错误码，也没有“去 Enable”的指引 |
| M2-N3 | 低 | 预检有错误时，下方 Physical system preview 仍显示 teal 的 READY |
| M2-N4 | 低 | 隔离或停用期间，模块卡片（仍显示 “Conformance passed”，按钮状态不一致）与停用区、隔离面板对不上 |
| M2-N5 | 观察 | 修正口径下 `storage_orders` 记毛接受量：P30 四条报价记为接受、合计 5 MWh，但该时段同时买回，实际放电约为 0；表中没有字段标出买回 |

### 9.5 加功能角色

**过程：** 用首轮作者改过的 `uat-af-observer-a-0.1.0-local.zip`（initialize 和 after_psm 两个 hook，一个必填数据角色），在 UI 中安装、绑定数据、保存带扩展的 Study 和不带扩展的对照 Study；两个 Study 都存 revision 2（最终年份 2026）用于两年范围。

**关键证据：**

- **F-D1 已修复，包括整年范围。**

  | Run | Study | 范围 | scientific_validation_status | gate | 用时 |
  |---|---|---|---|---|---|
  | …151857-063514de | observer A | smoke | not_evaluated | passed | 3 分 17 秒（首次快照） |
  | …152235-692ef3e5 | 对照 | smoke | not_evaluated | passed | 1 分 01 秒 |
  | …152542-153686c2 | observer A | two_year_smoke | not_evaluated | passed | 1 分 02 秒 |
  | …152723-8de7d9ca | observer A | **two_year（35,040 时段）** | **passed** | **passed** | 2 分 58 秒 |
  | …153806-652f6773 | 对照 | two_year | passed | passed | 2 分 50 秒 |

  - `run.state_chain` 的 `failed_links` 全部为空；带扩展的 Run 比对照多一条链接，就是新的 initialize 链接（只有 2025 年带 `extensions.extension_initialize`）。
  - two_year 结果页四项都是 Passed，年度结果已发布（2026 年 £14.425m，£61.68/MWh；2025 年 £14.70m；碳排放 38,634.86 tCO₂e，Reconciled），不再出现 “Treat results as unverified”（截图 27）。首轮按代码推断的“带扩展的 17520 时段 Run 扣发年度结果”，本轮在真实两年 Run 中确认不再发生。
  - 输出隔离：two_year 两个 Run 规范化 run_id 和路径、剔除扩展键后，`year-results-v2.json`、cost ledger、carbon ledger、energy-balance-oracle 没有差异，`market.sqlite` 的 23 张表全部相同。
  - 54 个相关单元测试在导出副本中全部通过（`test_prompt65_extension_framework`、`test_run_invariants`、`test_preflight_scope_extensions`、`test_module_disabled_exits_api`、`test_extension_results`）。
- **F-D2 已修复（A16-3）。** 带扩展的一日 Study：范围选项显示 “One-day market lesson (extensions do not run)”；Readiness 以 `GF_PREFLIGHT_SCOPE_SKIPS_EXTENSIONS` 阻断，文案与规格一致，Run 按钮禁用；直接调 `POST /api/projects/<id>/runs {"mode":"value_101_day"}` 返回同一个 error_code，不创建 Run（`ev/api-start-oneday-ext.json`）。不带扩展的一日 Study 不受影响（截图 16、17）。
- **F-D3 已修复。** 停用后 Modules 页出现 “Disabled and quarantined” 区，Enable 返回 200 并回到列表；Remove 有确认框，文件移到 `modules/disabled-manifests/removed/`，不删除；被 2 个 Study 引用的扩展 Disable 按钮禁用并列出 Study 名称（截图 20–22）。
- **G4-01 回归：** 同命名空间安装仍返回 409 `GF_EXTENSION_NAMESPACE_COLLISION`，`modules/` 摘要前后都是 `72e80e3de1c604dd`，health 为 ok。

**首轮其余缺陷：**

| ID | 状态 | 本轮证据 |
|---|---|---|
| F-D4 | **按原步骤未复现**，不算已修复 | 改选数据包后立即发出 `resolve-draft`，显示 26/26，Graph SHA 已解析，确认框也在（截图 24、25）。`a987ca4..HEAD` 之间没有针对它的提交 |
| F-D5 | 部分修复 | 成因（一日 Run 记录了扩展却没执行）已被预检挡住。比较两个真正执行了扩展的两年 Run 时，说明文字仍为 “storage-policy causal effect”，变化详情仍是约 6.9 KB 原始 JSON，年度差值被扣发，而 observer 扩展的数值其实相同（截图 28） |
| F-D6 | 基本仍在 | 草稿刷新后丢失（截图 30）；编辑时标题仍为 “New study”（截图 10）；`resource-readiness.json` 404；文件框只修了显示，`<input>` 中仍留着上次的文件（`files.length=1`） |

**新发现：**

| ID | 严重度 | 描述 | 本轮复核 |
|---|---|---|---|
| F2-N1 | 中 | **G4-05 实测出现。** two_year Run 的 `year-results-v2.json` 为 34.5 MB，超过 `backend/extension_results.py` 中 16 MiB 的上限，Inspect 扩展面板显示 “Extension results unavailable: year_results_size_limit”（截图 27）；smoke 下正常（截图 32）。数据完整，可从 Artifacts 下载。G4-05 不在 P0 计划和 A16 范围内 | **代码核对确认**，见 9.6 |
| F2-N2 | 低 | two_year 的 readiness 估算 “35,040 periods · estimated 3.4 hours”，实际约 3 分钟 | 未复核 |
| F2-N3 | 低 | Study 带扩展角色时，Data 和 Modules 页头 pill 显示 “25 of 25 inputs ready”，同页的 Input contract 却是 26/26 | 未复核 |
| F2-N4 | 观察 | 两个 smoke Run 的 `annual-carbon-ledger.json` 中 `direct_operational`、`asset_embodied` 两个键顺序不同，数值相同；首轮是逐字节一致 | 未复核 |

### 9.6 本轮的独立复核

复测没有报告任何高缺陷，所以没有必须复核的项。三项中等新问题由汇总人另行核对，INTEG 只读，Python 经 `vpy` 调用，没有启动服务：

- **N-2：已独立复现。**
  - 脚本 `$ROLES2/consolidate/repro_n2.py`：生成 17,520 行、从 `2025-01-01 00:00:00` 起按 30 分钟连续、不带偏移的时间戳文件，以 Europe/London 调用。
  - `parse_declared_timestamps` 和 `timestamp_row_problems` 都抛出 `pytz.exceptions.AmbiguousTimeError: 2025-10-26 01:00:00`（pandas 2.3.2）。
  - 根因：`gridform_core/data_validation_layers.py:397-400` 先用 `ambiguous="infer"` 本地化，失败时回退到 `ambiguous="NaT"`，但只捕获 `(ValueError, TypeError)`；`pytz.AmbiguousTimeError` 不是 `ValueError` 的子类，所以回退不生效，异常一直冒到 API，变成 `GF_RUNTIME_001`。
  - 修复建议（小改动）：在回退分支同时捕获 pytz 的 `InvalidTimeError`（或直接 `Exception`），让无法推断的重复时刻变为 NaT，再由逐行报告列出这一行；补一条单元测试。
- **N-1：代码核对确认。**
  - `profile_eligibility`（`data_validation_layers.py:346-362`）只看结构层是否通过，以及 chronology / plausibility 发现按口径策略算出的严重度，不检查数据包是否在该口径的白名单中。
  - Studies 编辑器走的是 `methodology.py` 中的组合检查：`_pack_supported`（第 662-673 行）按 `supported_data_packs` 的 id、pack_class 和 manifest sha 比对，不符合就产生 “is not a thesis-era pack” 违规（第 765 行）。
  - 两条路径对 doctoral 的资格判断不一致。修复建议：`profile_eligibility` 同时调用 `_pack_supported`（或其公开封装），把不在白名单中的情况记为 blocking code，面板显示 “Not eligible: not a thesis-era pack”。
- **F2-N1：代码核对确认。** `backend/extension_results.py:16` 的 `LIMITS["year_results"] = 16 * 1024 * 1024`，与测试员观察到的原因码 `year_results_size_limit` 对应。两年 Run 的 `year-results-v2.json`（34.5 MB）必然超限，全年及以上范围都会如此。属于已登记的 G4-05，建议列入下一轮：扩展结果改为按扩展产物单独读取，不经过整份 year-results。

### 9.7 跨角色的共性问题：修复轮之后

| 主题（对应第 5 节） | 状态 |
|---|---|
| 校验结论在 UI 中看不到或原因说错 | **大部分解决**：R-D1、S-D1、S-D2、M-D3、F-D1、F-D2 已修复。剩 R-D11（doctoral advisories 只在比较页出现）和 N-1（校验面板的 doctoral 资格与编辑器矛盾） |
| 停用后无法在 UI 中恢复 | **已解决**（M-D4、F-D3）。小问题：停用时预检没有专门的错误码和“去 Enable”指引（M2-N2），卡片状态与停用区不一致（M2-N4） |
| 比较页难读或分类不对 | **部分改善**：口径变化已点名；F-D5 的错误分类成因已消除。原始 JSON 和固定的 storage-policy 说明文字仍在（R-D7、S-D9、F-D5） |
| `resource-readiness.json` 404 | **未修**，四个角色仍然都看到；另外快照阶段 `snapshot.json`、`project.json` 也会 404 |
| Runs 页状态过期 | **未修**（R-D2、S-D12、M2-N1） |
| 编辑时标题仍是 “New study”、文件框残留 | **未修**（R-D11、F-D6、M-D9）；扩展的文件框只修了显示 |
| 第一次 Run 很慢且没有说明 | **未修**，并发现 POST 会一直阻塞到快照结束（O-1、N-4）。新数据目录首次快照 2 min 51 s–3 min 17 s，之后 35–60 s；执行归档每个实例约 500 MB |
| 文档与实际不一致 | **部分改善**：M-D2 的文档已改为允许原地修改；M-D6、M-D7、M-D9 仍在 |

### 9.8 建议

**本轮修复范围基本达成：** A16-1 的 11 项中，9 项已在真实实例中验证修复；S-D4 大部分修复（残留 N-2、N-3）；M-D1 只修好了账本（界面残留为低-中）。另外 S-D3 按 A16-2 在修正口径下生效，M-D2 按 A16-4 处理到位。首轮三项发布阻断项全部解决。从四类用户的角度，没有剩余的高缺陷阻止分支作为 0.7.0-alpha.1 发布候选。

**建议在发布前顺手修的小改动：**

1. **N-2：** 时间戳本地化回退要捕获 pytz 异常（一行改动加一条测试），否则用户上传一份常见格式的文件就会看到 “Model execution failed”。
2. **N-1：** 校验面板的 doctoral 资格要与编辑器的白名单检查一致，否则面板上的 “Eligible” 是错误的承诺。

**下一轮：**

- F2-N1（G4-05）：全年范围下 Inspect 看不到扩展结果；
- M-D1 界面：Market replay / Inspect 读取 `storage_orders`，显示逐条报价的接受量，并标出同时段买回（M2-N5）；
- 第 9.7 节中“未修”的界面细节，以及 N-3（时间轴与模型时钟对齐）、F2-N2（运行时间估算）。

**需要负责人决定：**

- R-D10：golden D3 的 identity 区已落后 13 列（A16-8，不设门）；
- O-3：是否在 Run 的来源记录中点名 `fx5.voll-17000`。

### 9.9 安全与环境核对（复测）

- **进程：** 四个角色都只按自己记录的 PID 停止进程。

  | 角色 | 停止的 PID |
  |---|---|
  | 复现 | API 2040961、UI 2041337 |
  | 换数据 | API 2041859、UI 2041860、驱动 2043320（SIGTERM 后仍在监听，对同一 PID 补发 SIGKILL） |
  | 改函数 | API 2042083、2216269、2271321（为 M-D5 重启过两次），UI 2042275 |
  | 加功能 | API 2042518、UI 2042738 |

  端口 18830–18837、18839 都已释放。没有连接 8766/8800，没有使用 pkill、killall 或按模式的 kill。
- **INTEG：** 四个角色都没有改动，`git status` 为空，没有 `__pycache__`；Python 都通过 `vpy` 调用。
- **磁盘：** 各角色已删除 `state/`（约 540–570 MB，其中执行归档约 500 MB）和 `src/`；保留的截图与证据每个角色 4–12 MB。
- **INSTALLED：** 四个角色结束时，以及本次汇总结束时，都执行了同样两项检查：
  - `find <INSTALLED> -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出安装时就有的 `.supervisor.lock`（0 字节，mtime 2026-10-03 05:41:26）；
  - `diagnose-value --prefix <INSTALLED>` 退出码 0，输出 “Installation integrity and runtime checks passed.”（中途的 vinext “Static file stream error … Premature close” 来自诊断探针本身）。

### 9.10 复测之后落地的 A18（2026-10-07 补记）

- **时间顺序：** 复测的被测 HEAD 是 `cd2d72c`。作者在复测之后决定 A18（`6cf98b6`），由 FX8 实施（代码 `7bf170e`，方法学与验收 `6631fc1`，报告 `9af15b8`）。所以第 9 节的结论**不覆盖** A18，四个角色没有为它重测。
- **改了什么：** 只改修正口径。每个模型年开始前核电视为在运，第一期报价不加启动成本，按各站可用率作基荷；某期未被接受后重启时收取一次启动成本。correction id `fx8.nuclear-in-service-at-start`，value-bid-at-cost-psm 6.3.0 → 6.4.0（`requires_user_opt_in`）。论文复现口径不变（D1–D3 gated 0）。
- **界面：** 没有改动 `app/`，没有新的界面字符串或组件，只有 UI 合同夹具中的模块版本与规则集 sha 随之更新。用户能看到的差别都走已有机制：
  - 修正口径 Study 的方法升级确认（Q13，FX5、FX6 升 6.2.0、6.3.0 时已有的同一界面）现在升级到 6.4.0，升级内容多一条 correction；
  - 没有应用 A18 的默认 PSM Run（论文复现口径 Run 与 FX8 之前的修正口径 Run）在 advisory 列表中多一条 high 级 advisory “Nuclear started the year off and paid its start-up cost to enter”。
- **对四个角色的数值影响：** 复测用的 VALUE 101 包没有核电。补测：HEAD `dca470e` 上 `capture.py check --cases C5 C6`（两年算例，对 A18 之前的最新修订）gated 0，只有 identity 差异；FX8 的 fast tier 检查中 C1–C4、C7、C8、D1–D3 也是 gated 0。所以复现角色的 golden 对照和重跑结论不变，只是 identity 区的落后列数（R-D10）会再多几列。
- **数值作用在 GBP1 上：** GBP1 public2 修正口径第一年（本地，未发布）核电 2.02 → 38.26 TWh，对 Energy Trends 5.1 +2.5%，通过；见 `docs/dev/GBP1_CORRECTED_LOCAL_ACCEPTANCE.md` 第 10 节。四个角色都没有用 GBP1 public2，不受影响。
- 复测之后另有 FX9（N-1、N-2、N-3、F2-N1、M-D1 界面），记录在 `docs/dev/p0-reports/FX9-retest-mediums.md`；本节只记 A18。

## 10 R1 轮复测（2026-10-07）

- **被测版本：** 分支 `fix/review-2026-10-04`，HEAD `e0ec659432818ec64798ddfb23178f86ba79708a`，即 R1 轮（R1-1 至 R1-5）全部提交之后。R1 之前还落地了 FX8（A18）和 FX9（N-1、N-2、N-3、F2-N1、M-D1 界面）。四个角色仍用 `git archive HEAD` 导出到 scratch，INTEG 没有改动。
- **R1 轮范围（DECISIONS A19–A22a）：**
  - R1-1：重启成本参考数据（A19、A22）；
  - R1-2：修正口径按经济顺序下调（A19、A22、A22a）；
  - R1-3：电池按类型分别设扩容上限（A20）；
  - R1-4、R1-5：四类用户测试中仍未解决的后端与界面问题（A21：medium 及以上必修，low 改动小时顺带修）。
- **方法：** 与前两轮相同，每个角色起自己的 API 和 UI 网关，用 Playwright headless（chromium 1243）操作界面，数据包用 `install_synthetic_pack.py --value-101-only` 安装，`vinext build` 4.8–4.9 s。运行环境仍不允许子代理写 `REPORT.md`，四份报告原文只存在于工作流输出中，本节是它们唯一入库的记录。

| 角色 | 实例端口（API/UI） | 主要证据目录 |
|---|---|---|
| 复现 | 18850 / 18851 | `$ROLES3/reproduce/`（`shots/` 32 张、`golden-cmp.txt`、`golden_cmp.py`、`repro-correcte-run.json`、`repro-doctoral-run.json`、`pw/runmod.log`） |
| 换数据 | 18852 / 18853（驱动 18859） | `$ROLES3/swap-data/`（`shots/` 43 张、`evidence/`、`input/`） |
| 改函数 | 18854 / 18855 | `$ROLES3/edit-module/`（`shots/` 38 张、`evidence/`、`author*/`、`scripts/pill.mjs`） |
| 加功能 | 18856 / 18857 | `$ROLES3/add-feature/`（`shots/`、`ev/`、`author/`、`pw/`） |

`$ROLES3` = `…/scratchpad/build/roles3`，完整路径见附录 A。

### 10.1 结论

| 角色 | 结论 | 以往缺陷 | 新发现的最高严重度 |
|---|---|---|---|
| 复现 | **通过，有问题** | R-D2、R-D3、R-D4（界面）、R-D5、R-D7、R-D8、R-D11、R-D12 已修复；R-D6 大部分修复（残留 N3）；R-D9、R-D10 保留 | **中**（R3-N1） |
| 换数据 | **通过，有若干低等级问题** | 19 项中 15 项已修复，S-D5、S-D7、S-D10 部分修复（残留都为低），N-4 仍在（已转 P1） | 低（L-1～L-6） |
| 改函数 | **通过，有问题** | M-D1～M-D6、M-D8、M-D9、M2-N1～M2-N4 已修复；M-D7 部分修复（R3M-1）；M-D10、M2-N5 观察保留 | 低-中（R3M-1，文档） |
| 加功能 | **通过，有问题** | F-D1～F-D4、F2-N1～F2-N4、G4-01 已修复或未复现；F-D5、F-D6 部分修复 | 低-中（4.1，既有） |

**一句话结论：** 四个角色的主路径都走通；没有高缺陷，所以本轮没有必须独立复核的高缺陷。R1-4、R1-5 处理的界面和后端缺陷绝大多数已在真实实例中确认修复。新出现 1 项中等缺陷 R3-N1（原样保存 Study 后，比较页报告不存在的 VoLL 变化），按 A21 属于必修。R1-2、R1-3、A18 的方法改动对 VALUE 101 一日和两年数值没有影响，与 R1 各报告的结论一致。golden 对照、重跑可重复、INSTALLED 完好这三点保持不变。

另有两项需要 methodology 编辑员注意：R3-N2（p06 的 advisory 仍把“先弃风电”写成缺陷，与 A19 矛盾）和 R3-N7（advisory 不按 Run 中是否有相关资产筛选）。

### 10.2 复现角色

**过程：** 首页 → 复现路径 → VALUE 101 基线 → 复现 Study → corrected 一日 Run、重跑、基线 Run → 在编辑中改为 doctoral 口径，跑一日 Run 并重跑 → 两组比较 → strict 冻结输入复现，并运行复现出的 Study → Market replay、Inspect、Network 页 → 375 px。

**关键证据：**

- **与 golden 对照**（exact 模式，比较各 Run 的 `model-output/`）：

  | UI Run | 参考 | 列数 | trajectory 差异 | identity 差异 |
  |---|---|---|---|---|
  | corrected：首跑 8b30d021、重跑 c172207b、基线 01b806b4、原样保存后的 3c12f82f | C3（16 个修订） | 905 / 905 | 只有 `run_id`、`result_id` | 1 列 `market_rule_set.runtime_kernel_tree_sha256`（R3-N6） |
  | doctoral：首跑 2d58b65a、重跑 5afca2de、冻结恢复 3ee29b93 | D3（13 个修订） | 932 / 932 | 只有 `run_id`、`result_id` | 13 列，同上轮（R-D10） |

- **重跑可重复：** 同口径 market.sqlite 逐字节相同（corrected 4 个 Run `dffb19034337aace`，doctoral 3 个 Run `7ff0796424d56bcf`），energy-balance-oracle、run-invariants、scientific-validation、stage-parity、market/index 同口径也逐字节相同。market.sqlite 哈希与上轮不同（上轮 `c2152bcd…`、`5755489c…`），差异只在 identity 区（`metadata.value`）和 R1-2 新增的 extension 列，数值列不变。Inspect › Artifacts 下载的 market.sqlite 与磁盘文件哈希一致。
- **窗口卡数值与前两轮完全相同：** corrected 需求 775.49 / Accepted supply 787.02 / Shortfall 0 / 充电 11.53 / 放电 9.34 MWh，£37.06/MWh；doctoral 775.49 / 780.49 / 0 / 48.34 / 39.15，£36.48/MWh。价格标签为 “Demand-weighted average period cost”。
- **doctoral 年度结果扣发：** 状态条 `Energy balance ● Conformant`、`Raw invariants ● 1 failed`（Storage single direction）、`Stress events None`；Callout 写明 10 行失败、命中 DEV-STO-01；状态条下方新增可展开的 “11 advisories apply to this Run · 7 high, 3 medium, 1 info”。API `result_publication.status=withheld`（`GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED`）；冻结恢复的 Run 同样扣发。
- **修正 id：** corrected Run 的 `applied_correction_ids` 共 37 个，含 `r12.economic-downward-order`、`r13.per-type-battery-caps`、`fx8.nuclear-in-service-at-start`；doctoral Run 共 10 个，不含这三个，符合 Q1。
- **派生与冻结复现：** `derivation` 记录 intent、来源 Study 与修订、数据包和模块图 sha；基线 Study 仍是 rev 1。strict 冻结输入核对 21.7 s，verified，25 个规范角色；由此创建的 Study 跑出的 Run 与原 Run 字节相同。
- VALUE 101 没有核电，也没有带价的停机段，所以 R1-2、R1-3、A18 不改变一日课程的数值。

**以往缺陷逐条状态：**

| ID | 状态 | 本轮证据 |
|---|---|---|
| R-D1 | 保持修复 | 见上 |
| R-D2 | **已修复** | 下拉项为 `One-day market lesson · completed · 2026-10-07 01:05 · 8b30d021`，悬停显示完整 ID；有 Run 时不再出现 “No runs yet”；启动中显示 “Starting the Run… VALUE is freezing the Study's inputs…” |
| R-D3 | **已修复** | 标题 “Stress events — 2025 (non-annual run) / None”；空列表写 “No stress events in the 48 periods of 2025 this non-annual Run computed.” |
| R-D4 | **已修复（界面部分）** | 核对时显示 “通常需要约 20 秒”、`aria-busy=true`；创建时提示关闭页面后服务端仍会完成、不要再次创建。实测关闭页面后只产生 1 个 recovered Study。后端持锁部分转 P1（R1-4） |
| R-D5 | **已修复** | 两个口径都只显示一个原因 “This run cleared one national (copperplate) market…”，并有 “Open Market replay →”；没有 409，也没有 “evidence pending” |
| R-D6 | **大部分修复** | 一次完整 Run 以及 Market、Inspect、Network 页，HTTP ≥400 为 0 次（`pw/runmod.log`）；从导航进入 Inspect 默认打开 Market，Planning 标签说明本范围没有规划记录。残留 R3-N3 |
| R-D7 | **已修复** | 变化维度按“标签 + 路径”列出，例如 `module · storage cost: dynamic-annual-storage-cost 2.0.0 → value-legacy-storage-tariff 1.0.0`；原始 JSON 默认折叠 |
| R-D8 | **已修复** | 375 px 下 7 个视图 scrollWidth 都是 375，没有文字被裁掉 |
| R-D9 | 仍在（R1-4 保留，信息级） | `market_ledger.uri` 仍是本机绝对路径；8 个 Run 的 `psm_input_sha256` 各不相同 |
| R-D10 | 仍在（负责人决定，不设门） | D3 的 identity 区落后 13 列 |
| R-D11 | **已修复** | 编辑时标题 “Edit study · Repro doctoral R3”；advisory 在状态条下方的折叠区列出，每条带严重度 |
| R-D12 | **已修复** | PSM 以外的 6 个槽位显示 “Not called in this scope” |
| O-1 | 部分修复 | 新数据目录第一次 Run 的 POST 仍阻塞 173 s，之后约 36 s；界面已有说明。后端部分转 P1（P1-11 / F5-08） |
| O-2 | 仍在 | 8 个一日 Run 加 1 次冻结核对后 state 588 MB，其中执行归档 500 MB |
| O-3 | 仍在（负责人决定） | doctoral Run 的 10 个 `applied_correction_ids` 中没有 VoLL 相关 id |

**新发现：**

| ID | 严重度 | 描述 | 本轮复核 |
|---|---|---|---|
| R3-N1 | **中** | 原样保存 Study（Edit as new revision，不改任何字段）后，`market_configuration.voll_gbp_per_mwh` 从 `17000.0` 变成 `17000`，并生成 rev 2（sha `8c51c919…` → `d6c76a59…`，`change_summary=[]`）。复现 Run 对基线 Run 比较时，页面写 “Recorded Configuration Changed — Only the parameters and extension configuration (market_configuration.voll_gbp_per_mwh) differ…”，而两个 Run 的 market.sqlite 字节相同（`dffb1903…`）；corrected 对 doctoral 的比较中 `differs at` 也列出这个不存在的差异。比较页是复现路径上最关键的核对，所以记为中。截图 `shots/23-compare-noop-edit-vs-baseline.jpg` | **代码核对确认**，见 10.6 |
| R3-N2 | 低-中 | doctoral Run 上的 advisory `p06.avoided-cost-downward-order`（high，“Down regulation in curtail-cost order”）正文把 “ascending curtail_cost (VRE first)” 当作缺陷，与 A19 撤回的判断矛盾；同一 Run 上 `r12.economic-downward-order`（medium，“Down regulation without restart economics”）表述准确。两条讲同一件事，严重度不同、结论相反。文字来源 `gridform_core/data/methodology/corrections/p06.json:91-93`（截图 `shots/14-doctoral-advisories.jpg`）。**methodology 编辑员需要知道** | **代码核对确认**：`p06.json` 第 93 行 summary 仍写 “ascending curtail_cost (VRE first)” |
| R3-N3 | 低 | R-D6 残留：从 Callout 或状态条点 “Open in Inspect” 打开空的 Planning 标签，之后从导航进入 Inspect 也停在 Planning。根因 `app/page.tsx:1432` 中 `setInspectTarget({ tab: tab ?? "planning", … })` 写死默认标签，且 `inspectTarget` 不清除（截图 `shots/29-open-in-inspect-from-callout.jpg`） | **代码核对确认**（第 1432 行如述） |
| R3-N4 | 低 | 在复现路径创建 Study 后，来源下拉框默认选中刚创建的复现 Study；再点一次“创建复现 Study”得到“复现的复现”，且 Study 允许重名（实例：`repro-corrected-r3-8209b52903` 的来源是 `repro-corrected-r3-0fbaf920cf`，两者都叫 “Repro corrected R3”） | 未复核 |
| R3-N5 | 信息 | 同一个 Run 在比较选择器中显示完成时间（01:08:25），在 Run history 中显示创建时间（01:05） | 未复核 |
| R3-N6 | 信息 | golden C3 的 identity 区落后 1 列（`runtime_kernel_tree_sha256`）：C3 最后一次修订是 R1-2 写入的 revision 15（基于 `c9c1cc1`），之后 A22a 改了 `net_saving`。与 R-D10 同类，不设门 | 未复核 |
| R3-N7 | 信息 | advisory 不按 Run 中是否有相关资产筛选：VALUE 101 没有核电，doctoral Run 仍列出 high 级 “Nuclear started the year off…”，正文自己写着 “Runs without nuclear units are not affected”，high 因此由 6 条变为 7 条。**methodology 编辑员需要知道** | 未复核 |
| R3-N8 | 观察，未确认 | 冻结恢复的 Study 只有一个范围，readiness 卡片仍显示 “Checking…” 时点 Run，Run 也正常启动并完成。是否允许在核对完成前启动，未进一步确认 | 未复核 |

### 10.3 换数据角色

**过程：** VALUE 101 基线 → 一日 Run → 复制 BASE 包 → 在界面中映射 4 个角色（demand.real、demand.forecast、market.france.profile、EUR 计价的 market.france.price，都声明 UTC 时间戳列）→ 创建换数据 Study → Check readiness → 一日 Run → Market replay → 比较 → 身份详情。另做负向包（价格 6087、流量 500）和多组负向文件。

**关键证据：**

- **数值与第 2 轮逐项相同：**

  | 指标 | 基线 | 换数据 |
  |---|---:|---:|
  | 需求（MWh） | 775.49 | 837.53 |
  | 法国进口（MWh） | 0 | 282.547 |
  | CCGT（MWh） | 428.13 | 207.17 |
  | 运行成本（£） | 28,643.41 | 23,820.77 |
  | 能量平衡最大残差（MWh） | 1.8e-15 | 1.8e-15 |

  结算分项也相同。R1-2 新增的 `downward_restart_economics` 账本已出现：只有 1 个时段走 thermal_running_range，减出力 1.48 MWh。
- **身份链：** 原文件 `f4e5ba90…` → demand.real 映射 `2d75e7df…` → 规范文件 `a4e767b3…` → Run 快照。快照中 4 个 `mapped.csv` 的 sha256（`a4e767b3…`、`ae94ebed…`、`b4aeba7d…`、`df711c46…`）与绑定记录逐一相同；时间戳声明和 FX 字段（`source_currency=EUR`、`eur_per_gbp=1.15`、annual average、2025）都冻结进了快照。
- **单位与汇率：** 需求 14.935404 MWh/period → 29.870808 MW；价格 46 / 34.5 EUR → 40.0 / 30.0 £，规范文件、审阅表和 `orders.offer_price_gbp_per_mwh` 中都没有浮点尾差了。
- **进口与回放：** 法国报价 48 条（35 accepted、6 partially_accepted、7 rejected）；第 0 期回放中有 `Interconnect_France · boundary import · £40/MWh · 7.5/7.5 MWh`，CCGT £66.5 为边际报价；Shortfall 0 MWh，stress 列表为非年度措辞。
- **其他：** 比较页只有“基础与网络数据”为“已改变”，4 条路径逐条列出，原始 JSON 折叠；被 Study 引用的包返回 409 `GF_DATA_PACK_REFERENCED`；两次 Run 和回放全程网络 4xx/5xx 为 0 次，控制台错误为 0 条。
- **负向用例全部符合预期：** 不填汇率、rate=0、对 GBP 列填汇率返回 400 `GF_MAPPING_FX`；单位错配 400 `GF_MAPPING_UNITS`；负需求拒绝；17,568 行给 warning 只取前 17,520 行；17,568 行加时间戳 48 处问题拒绝；375 px 下 Data、Runs（含 readiness）、引导页 scrollWidth 都是 375。

**以往缺陷逐条状态：**

| ID | 原严重度 | 状态 | 本轮证据 |
|---|---|---|---|
| S-D1 | 高 | 已修复 | 负向包 readiness 中 `Data plausibility · 2` 默认展开，两条完整显示；其余组折叠（shots/25） |
| S-D2 | 中-高 | 已修复 | 校验面板显示 Structural（映射后 warning 14 → 10）、Chronology、Plausibility、Methodology use（shots/17） |
| S-D3 | 中 | 已修复（修正口径） | 进口 282.547 MWh 与 orders 一致；角色标签 “(+ import / - export)” |
| S-D4 | 中 | 已修复 | 重复、缺口、错位逐行拒绝；London 本地时间（含换时）通过；列名错误、时区不支持返回 400 `GF_MAPPING_TIMESTAMP` |
| S-D5 | 中 | UI 层已修复 | “Column name suggests EUR — confirm the currency.”；按设计 API 和审阅报告仍没有 warning |
| S-D6 | 低 | 已修复 | 规范文件、审阅表、orders 中都是 40.0、30.0 |
| S-D7 | 低 | 大部分修复 | 坏单元格按 “Row 6 (CSV line 7), column …: 'n/a' is not a number” 一次列出；残留 L-1、L-2、L-3 |
| S-D8 | 低 | 已修复 | 提交后角色卡显示 “已提交 demand.real 的映射：规范文件 SHA a4e767b33894…” |
| S-D9 | 低 | 界面已修复 | 变化维度按路径列出；`transformation_id` 按 R1-4 保留 |
| S-D10 | 低 | 部分修复 | Runs 页显示冻结说明，不再拉回 Runs；首次快照约 2 分 50 秒，第二次 39 s；残留 L-4 |
| S-D11 | 低 | 已修复 | 全程 404 为 0 次 |
| S-D12 | 低 | 已修复 | 完成后显示 “…Run 4acee21b has completed”；下拉项带状态和短 ID；Check for 跟随所选 Run |
| S-D13 | 低 | 已修复 | 标为 “Frozen data pack manifest SHA-256” 并附说明（shots/24） |
| N-1 | 中 | 已修复（FX9） | 面板写 “Not eligible — not a thesis-era pack”，API `pack_supported=false`，与 Studies 编辑器一致（shots/28） |
| N-2 | 中 | 已修复（FX9） | 不带偏移的连续 London 文件不再报 500，逐行列出 4228、4229 行 non-existent，14308、14309 行 ambiguous |
| N-3 | 中低 | 已修复（只提示，FX9） | 错位 30 分钟出现 warning `GF_DATA_TIMESTAMP_ORIGIN`；2023 年数据只显示首末时间戳（按设计） |
| N-4 | 低-中 | 仍在（转 P1） | 第二次 Run 冻结期间发出的 clone 阻塞 33.3 s（P1-11 / F5-08） |
| N-5 | 低 | 已修复 | 引导 Data 页重新加载后上下文保留（shots/10） |
| N-6 | 低 | 已修复 | 春季不存在时刻有专门文案；角色卡显示时间戳声明；Studies 列表的哈希标为 “Model graph SHA-256 (… not the data pack)” |

**新发现（全部为低或观察）：**

| ID | 严重度 | 描述 |
|---|---|---|
| L-1 | 低 | 同一文件既有 `'n/a'`、`'abc'` 又有空单元格、且需要单位换算时，清单漏掉空单元格那一行（第 101 行）：`data_adapters._convert` 把空值当 None 放行，有换算错误时整文件校验不运行，用户要修两轮才看全（`evidence/neg-api.txt`） |
| L-2 | 低 | 不换算的序列（法国容量 MW）含空值、NaN、inf 时，计数写 “1 non-numeric or missing”，逐行清单却列 3 行；另有误导性 warning “17519 numeric periods … repeats it cyclically”（`evidence/neg-api-blank.txt`） |
| L-3 | 低 | 负需求只报 “demand contains a negative or non-finite value”，没有行号和列名（S-D7 残留） |
| L-4 | 低 | 在 Learn 页点 “Run one market day” 后 POST 阻塞约 3 分钟，按钮全部禁用但没有说明；冻结说明只在 Runs 页显示（S-D10 残留，shots/05、05b，对照 06） |
| L-5 | 低 | API 与 UI 的 FX 规则不一致：界面要求 price_year 在 1990–2100、fx_basis 三选一；API 中 price_year 可省略或为任意整数，fx_basis 可为任意文本，实测 `price_year=1890` 返回 200 valid（`backend/data_mapping.py:55-68`） |
| L-6 | 低 | 换算失败时，审阅区“完整文件校验报告”下原样显示 `null`（shots/26-ui-badcells） |
| O-1 | 观察 | 价格 6087 £/MWh 在映射审阅和提交时没有 plausibility 提示，只在提交后的校验面板和 readiness 中出现（符合设计） |
| O-2 | 观察 | 用负向包跑完的 Run，状态条看不出冻结输入带有 plausibility 发现（shots/31） |

附注：`period_summary.clearing_price_gbp_per_mwh` 第 0 期为 32.91，低于当期被接受的报价（£40、£66.5）。它的含义是需求加权的平均时段成本，界面已按 Q6 正确标注，不是回归；只是直接读 sqlite 时列名容易误导。

### 10.4 改函数角色

**过程：**

1. 按指南第 9 节从 `examples/external_module_bundle` 复制 `uat3-flat73-storage-offer`（报价 42 → 73），构建两次 ZIP 字节相同（`21c776e0…`），示例源码已不再 import `compat`；
2. UI 安装（conformance passed，State Enabled，安装后文件框清空、信任勾选复位）；
3. 派生 Study “UAT3 flat73”（`parent_project_id=value-101-baseline`、`changed_dimensions=["modules.storage_cost"]`、`derivation_intent=edit_module`）；
4. 修正口径一日 Run：基线 `e0c446c4` 报价 18.5185（14 接受、1 部分、25 未接受），flat73 `929bf99f` 报价 73.0（170 条全部未接受）；`storage_orders` 与 `clearing_inputs` 一一对应（40/40、170/170），价格差异 0；
5. Market replay 基线 P29：四条电池报价 Accepted 列为 0.75、1.26、0.49、0 MWh，与账本一致，Evidence 列为 “storage offer ledger”；
6. Compare 基线对 flat73：`dynamic-annual-storage-cost 2.0.0 → uat3-flat73-storage-offer 1.0.0`；
7. 原地改源码 73 → 99：卡片显示 “Source changed since install (66bbf1bf… → 98f06a6c…)”，Readiness Ready 带琥珀提示，Run `c39e4659` 报价 99.0，新哈希写入 `module-resolution.json`、`snapshot.json` 和 `preflight.checks.module_source_changes`；
8. 坏模块与恢复：SyntaxError 后全局 Rescan 立即隔离、health degraded；Readiness 第一条 `GF_PREFLIGHT_MODULE_QUARANTINED`，徽章 “INPUTS READY · RUN BLOCKED”；Disable 后第一条 `GF_PREFLIGHT_MODULE_DISABLED` 带 Enable 指引；RuntimeError 时 Enable 返回 409 并显示本次扫描的错误；修好后恢复；Remove 二次确认后 409 `GF_MODULE_IN_USE`；
9. 导入即 `SystemExit` 的包安装返回 400 `GF_MODULE_RESOLUTION`，后端存活；
10. 未封印的内核改动：Readiness 报 `GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED`（error），Run 不可点；
11. 按指南 12.1 做一次内置模块方法升级（cycle_only 报价 +25，2.0.0 → 2.1.0，VERSION_LEDGER `requires_user_opt_in: true`，`seal --correction uat3.cycle-plus-25` 后 `--verify` 通过）：重启后基线 Study 弹出确认框；直接调 API 返回 409 `GF_PREFLIGHT_METHOD_UPGRADE_REQUIRED`；确认后 rev 2 的 Run `212083c3` 报价 18.5185 → 43.5185；还原四个文件后确认框显示 “2.1.0 → 2.0.0 moved backwards”，确认后恢复；
12. 375 px 下 Modules、Runs 页没有页面级横向滚动。

**以往缺陷逐条状态：**

| ID | 状态 | 本轮证据 |
|---|---|---|
| M-D1 | 已修复 | 第 4、5 步。`orders` 电池行价格仍为 0.0，按 FX4 偏差 1 有意不改 |
| M-D2（含卡片小问题） | 已修复 | 第 7 步 |
| M-D3 | 已修复 | 截图 `13`、`17` |
| M-D4 | 已修复 | 截图 `18`、`20`；措辞问题见 R3M-3 |
| M-D5 | 已修复 | 截图 `11`：全局 Rescan 立即隔离已加载的坏模块 |
| M-D6 | 已修复 | 截图 `24`；指南 12.1 实际走通 |
| M-D7 | **部分修复** | 见 R3M-1 |
| M-D8 | 已修复 | `variant_kind` 仍为 `baseline`，R1-4 说明是有意保留 |
| M-D9 | 已修复 | 安装后文件框清空；4 个 Run 期间没有 `resource-readiness.json` 404；源码检出的安装提示只做了代码核对（`value_101.py:92-94`） |
| M-D10 | 观察保留 | 7 个内置模块的 `source_sha256` 都是 `09f66c1e…` |
| M2-N1 | 已修复 | 结束后显示 “Run e0c446c4 has completed” |
| M2-N2 | 已修复 | `GF_PREFLIGHT_MODULE_DISABLED`，带 Enable 指引 |
| M2-N3 | 已修复 | 徽章 “INPUTS READY · RUN BLOCKED” |
| M2-N4 | 已修复 | 卡片 State 正确；文字残留见 R3M-4 |
| M2-N5 | 观察保留 | 已有说明句 |

**新发现：**

| ID | 严重度 | 描述 | 本轮复核 |
|---|---|---|---|
| R3M-1 | **低-中**（文档，M-D7 残留） | MODULE_DEVELOPER_101 EN/ZH 三处写 `gridform.*` contract ID：第 4 节 slot 表（`gridform.psm/v2`、`gridform.storage-cost/v1` 等，EN:94-98、ZH:104-108）；第 8 节 manifest 示例 `"contract_version": "gridform.investment/v2"`（EN:322、ZH:343）；第 7 节说 “`gridform.storage-cost/v1` 这类 contract ID 保留”（EN:300、ZH:317）。安装器只接受 `value.*`，按文档写的包安装返回 400 “uses gridform.storage-cost/v1; expected value.storage-cost/v1”（`author-gf/gf.zip`）。另有 EN:213 写 `force.vre-counterfactual-snapshot/v1`；`USER_GUIDE_ZH.md:170` 仍写 `force-module.json` 和 “FORCE Python 进程” | **代码核对确认**：文档行号如述；`gridform_core/v2/module_manifest.py:42` 的期望值为 `value.storage-cost/v1` |
| R3M-2 | 低 | 只要有一个模块被隔离（health degraded），所有页面顶部徽章都显示 “Inputs not loaded”，数据包下拉框也被禁用；恢复后显示 “25 of 25”。`app/page.tsx:1426` 在 `connectionState !== "online"` 时显示这句，而 `serviceState`（`app/features/shared/api.ts:88`）把 degraded 也算非 online（复现脚本 `scripts/pill.mjs`） | **代码核对确认**（两处代码如述） |
| R3M-3 | 低 | 停用模块点 Enable 失败后提示 “Fix the cause, then Rescan.”；照做后模块仍是 Disabled（“no module is quarantined”），还要再点 Enable（截图 `19`） | 未复核 |
| R3M-4 | 低 | 经隔离面板停用一个仍被 Study 使用的模块后，卡片 State 为 Disabled，却仍写 “disable is blocked until those configurations are migrated”（截图 `16`）；`USER_GUIDE.md:434` 的说法同样矛盾 | 未复核 |
| R3M-5 | 低/观察 | 原地改源码的警告出现两次（琥珀提示一次，又计入 “Environment and setup · 1”，`readinessGroups.ts` 的 issueGroup 没有排除这个 code）；模块已隔离时提示仍写 “Results will record the new source hash” | 未复核 |
| R3M-6 | 低 | 比较同一 Study 原地修改前后的两个 Run（73 对 99，ID 和版本相同）：只写 “differs at modules.storage_cost”，没点出变的是 `source_sha256`；句子 “Only the model method (…) (modules.storage_cost) differ” 别扭；结论写 “not a controlled storage-cost experiment”，换模块时却写 “controlled teaching diagnostic”（`results_summary.py:606/627`，截图 `10`） | 未复核 |
| R3M-7 | 低（35aadb3 就有，首轮未登记） | 英文界面硬编码中文：“方法对照 Study 已保存…”（`page.tsx:1577`）；Compare 页身份核对块 “比较前身份核对 / 一致 / 已改变”；“正在读取使用说明…”（`ReadMePanel.tsx:162`，常驻 role=status）；Read me 中 “选择基线 Study / 核对新研究” | 未复核 |
| 观察 | — | 方法升级确认框只显示 correction id，不显示 VERSION_LEDGER 的 `reason` 文字 | — |

### 10.5 加功能角色

**过程（全部在 UI 中完成）：** 生成器生成 `uat3-af-observer`（命名空间 `local.uat3-af`，ZIP `00badd88…2c2705` 与页面 Package identity 一致）→ 作者本地加 `observed_run_id` 字段并改 schema，本地 4 个 unittest 通过，重新打包 `f43f61b8…` → UI 安装 201，文件框清空 → 扩展 Study `uat3-add-feature-observer`（2025–2026，输入合同 26/26）和对照 Study `uat3-add-feature-control`（25/25）→ 四个 Run：

| Run | Study | 范围 | 结果 | 用时 |
|---|---|---|---|---|
| `…010633-9263c8b6` | 扩展 | smoke | completed / not_evaluated | 3 分 17 秒（首次快照） |
| `…011012-6de13778` | 扩展 | **two_year（35,040 时段）** | completed / **passed** | 2 分 59 秒 |
| `…011332-c01615ad` | 对照 | two_year | completed / passed | 2 分 51 秒 |
| `…012630-d22b484a` | 扩展 | two_year_smoke（API 重启后） | completed / not_evaluated | 1 分 02 秒 |

**关键证据：**

- 扩展 two_year 的 `run.state_chain` 通过，`failed_links=[]`（扩展 9 条链，对照 8 条，多出 initialize）。三项检查 Passed，年度结果已发布：2026 年 £14.425m、£61.68/MWh；2025 年 £14.70m；碳排放 38,634.86 tCO₂e，Reconciled；Unserved 0 MWh。数值与第 2 轮完全相同，R1-2、R1-3 对这个教学包没有数值影响。
- 每年 1 个扩展 artifact，`observed_run_id` 等于本次 Run ID；`source_inputs_sha256` 逐年等于同一 Run 中 `psm.run` 的 `input_state_sha256`（2025 `4d00a0b9…`，2026 `5b59d6d9…`）；hook 的 `source_sha256` `5e1ea51a…` 与本地、已安装的 `hooks.py` 三者一致。
- 输出隔离：两个 two_year Run 规范化 run_id 和路径、剔除扩展键后，`year-results-v2.json`、cost ledger、carbon ledger、energy-balance-oracle 0 处差异，`market.sqlite` 23 张表全部相同。
- 压力事件：`status.json` 有 `stress` 区（`shortfall_mwh=0`、`stress_periods=0`，按年分列）；Market replay “No stress events recorded”；Inspect 状态条 “Stress events: None”。
- 单元测试：相关 91 个，90 个通过；唯一的 error `test_carbon_ledger.test_legacy_storage_scalar_is_not_relabelled` 已登记在 `tests/baselines/known-failures-linux-py310.txt`，是既有失败。

**以往缺陷逐条状态：**

| ID | 状态 | 本轮证据 |
|---|---|---|
| F-D1 | 已修复 | 真实 two_year Run 中确认，见上 |
| F-D2 | 已修复 | 扩展 Study 的范围下拉没有一日选项；API 预检 `value_101_day` 返回 `GF_PREFLIGHT_SCOPE_SKIPS_EXTENSIONS`，`POST …/runs` 返回 400 同一错误码、不创建 Run；`validation_24h` 返回 `GF_PREFLIGHT_TEACHING_RUN_MODE` |
| F-D3 | 回归通过 | 被引用的扩展不能停用（“Referenced by 1 saved Study; disabling is blocked”）；未被引用的 `uat3-af-nsb` Disable 200 进入 “Disabled and quarantined” 区，Enable 200 回到列表 |
| F-D4 | 未复现 | 改选数据包后立即 resolve-draft，26/26，Graph SHA 已解析，实验性确认框在 |
| F-D5 | 部分修复 | 说明文字不再写 storage-policy，变化按路径列出，原始 JSON 默认折叠；残留 AF3-1、AF3-2 |
| F-D6 | 大部分修复 | 编辑时标题 “Edit study · …”；文件框已清空；没有 `resource-readiness.json`、`snapshot.json`、`project.json` 404；草稿刷新后丢失仍在（AF3-3） |
| F2-N1 | 已修复（FX9） | 34.5 MB 的两年 year-results，Inspect 扩展面板列出 2025、2026 两条（“Artifacts 1–2 of 2”） |
| F2-N2 | 已修复（R1-4） | two_year 估算 0.3 h，实际约 3 分钟 |
| F2-N3 | 已修复 | 页头 “25 of 25 base inputs ready”，输入合同 26/26 |
| F2-N4 | 已修复 | 两个 two_year Run 的碳账规范化后逐字节相同，键顺序固定 |
| G4-01 | 回归通过 | 生成器在 Validate 阶段拒绝冲突命名空间；手工冲突包安装 409 `GF_EXTENSION_NAMESPACE_COLLISION`，modules 摘要前后都是 `6ceb2b9f…`；重启 API 后 health ok，新 Run 正常完成 |

**剩余问题（测试员报告第 4 节；本节编号 AF3-1～AF3-3）：**

| ID | 严重度 | 描述 | 本轮复核 |
|---|---|---|---|
| AF3-1 | **低-中**（既有，F-D5 残留，需负责人决定） | 比较两个 two_year Run 时只显示 “所需的定义、范围或归因证据不完整。VALUE 暂不展示未获支持的差值。”，2025、2026 都没有差值，尽管两个 Run 的成本和碳完全相同。API：`comparison_review.status=verified`、`annual_metrics_withheld=false`，但 `metric_deltas_allowed=false`，`curtailment_comparison.reason_code=module_does_not_provide_counterfactual_snapshot`。根因：`results_summary.py` 把弃电归因是否可比当成所有成本和碳差值的前提，而内置 copperplate 组合不提供反事实快照，所以**任何 VALUE 101 年度对照都看不到差值**；`ComparisonWorkspace.tsx:110` 只显示通用文案，不用已返回的 reason_code。二选一：只扣发弃电相关指标、成本和碳差值照常显示；或者保留保守设计，但在界面上写明原因 | **代码核对确认**：`gridform_core/results_summary.py:560-564` 中 `deltas_allowed` 要求 `curtailment_comparison["metric_deltas_allowed"]` 为真；`ComparisonWorkspace.tsx` 只对 network_comparison 显示 reason_code |
| AF3-2 | 低 | 扩展的差异归在“模块方法：已改变”下，同时“参数与扩展配置”显示“一致”，容易让人以为扩展没变；说明文字重复 “Only the model method (modules, extensions, methodology) (extensions) differ”；同一区块中英混排（与 R3M-6、R3M-7 同源） | 未复核 |
| AF3-3 | 低（R1-5 已转 P1） | 独立草稿填写 Name、Purpose 后整页刷新，Name 回到默认 “VALUE UK transition”，Purpose 变空，没有任何提示 | 未复核 |
| 观察 | — | 首次快照仍慢（3 分 17 秒，之后约 1 分钟，P1-11 / F5-08，启动时已有说明）；生成第二个扩展时 `POST /api/extensions/authoring/template 200` 后紧跟一条 `GET …/template 404`，下载本身成功，首次生成时没有出现，可能是浏览器下载行为引起，建议顺手查看 | — |

### 10.6 本轮的独立复核

四个角色都没有报告高缺陷，所以没有必须独立复核的项。唯一的中等新缺陷 R3-N1 和几项低-中问题由汇总人做了代码核对。INTEG 只读，Python 经 `vpy` 调用，没有启动服务。

- **R3-N1：代码核对确认，并用最小输入复现了比较逻辑。**
  - `gridform_core/results_summary.py:407-416` 的 `_differing_paths` 用 `json.dumps(child, sort_keys=True, default=str)` 判断两侧是否不同；同文件第 467–477 行的维度判定也用 `json.dumps`。`json.dumps(17000.0)` 为 `"17000.0"`，`json.dumps(17000)` 为 `"17000"`，所以数值相同、类型不同的 VoLL 被判为不同。
  - 直接调用：`_differing_paths([{'market_configuration': {'voll_gbp_per_mwh': 17000.0}}, {'market_configuration': {'voll_gbp_per_mwh': 17000}}], 2)` 返回 `['market_configuration.voll_gbp_per_mwh']`。
  - 问题有两层：编辑器原样保存时把 float 写回成 int（并因此生成一份 `change_summary=[]` 的新修订）；比较和身份哈希不做数值规范化。修复建议：保存时在 `study_market_config` 中把 `voll_gbp_per_mwh`（以及其他浮点参数）统一为 float，**并且**比较前做数值规范化（整数值的 float 与 int 视为相同），避免以后其他参数出同样的问题；无改动的保存最好不产生新修订。补一条单元测试。
- **R3-N2：代码核对确认。** `gridform_core/data/methodology/corrections/p06.json` 第 91–93 行仍为 high、标题 “Down regulation in curtail-cost order”，summary 以 “ascending curtail_cost (VRE first)” 开头；`r12` 的 advisory（medium，“Down regulation without restart economics”）是按 A19 写的。p06 这条应只保留另外三项（爬坡历史按位置匹配、断开后保留旧要求、预算只返还水电），去掉 “VRE first” 并重新评估严重度，或交负责人决定。属于方法学措辞，修改前应让 methodology 编辑员知道。
- **R3M-1：代码核对确认。** 文档行号如测试员所述；`gridform_core/v2/module_manifest.py:42` 期望 `value.storage-cost/v1`。按文档写的包必然安装失败，对改函数用户是实际阻碍，建议下一轮修（纯文档改动）。
- **AF3-1：代码核对确认。** `results_summary.py:560-564` 的 `deltas_allowed` 同时要求 `curtailment_comparison["metric_deltas_allowed"]`；内置 copperplate 组合没有反事实快照，所以 VALUE 101 年度对照一律没有差值。这是设计选择还是过严，需要负责人决定；无论哪种，界面都应显示原因。
- **R3-N3、R3M-2：代码核对确认**（`app/page.tsx:1432` 写死 `tab ?? "planning"`；`app/page.tsx:1426` 与 `app/features/shared/api.ts:88` 如述）。

### 10.7 缺陷总表：R1 之后仍未关闭的项

按 A21（medium 及以上必修，low 改动小时顺带修）分组：

| 组 | 项目 | 说明 |
|---|---|---|
| **必修（中）** | R3-N1 | 原样保存后比较页报告不存在的 VoLL 变化 |
| **建议本轮修（低-中，改动小）** | R3M-1、R3-N2 | 开发者文档的 contract ID；p06 advisory 与 A19 矛盾（需 methodology 编辑员知晓） |
| **需负责人决定** | AF3-1、R-D10、R3-N6、O-3、R3-N7 | 年度差值是否因弃电证据缺失而全部扣发；golden D3/C3 identity 区落后（不设门）；VoLL 修正 id 是否写进 Run 记录；advisory 是否按资产筛选 |
| **顺带修（低，改动小）** | R3-N3、R3-N4、R3M-2、R3M-3、R3M-4、R3M-5、R3M-6、R3M-7、AF3-2、L-1、L-2、L-3、L-5、L-6 | 多为一处判断或一段文案 |
| **已转 P1** | O-1、R-D4（后端）、S-D10 / L-4、N-4、AF3-3、首次快照慢、O-2（执行归档体积） | 都与 `STUDY_LIFECYCLE_LOCK` 持锁或草稿持久化有关（P1-11 / F5-08） |
| **保留（信息/观察）** | R-D9、M-D10、M2-N5、R3-N5、R3-N8、O-1/O-2（换数据）、生成器的一次 404 | 不影响结论 |

### 10.8 建议

1. **下一轮小修复（建议命名 R2）：** 必修 R3-N1（含单元测试）；同批修 R3M-1、R3-N2（改 p06 文字前先告知 methodology 编辑员）以及 10.7 中“顺带修”的低项。这些都是局部改动，不涉及方法与 golden。
2. **复测范围收窄：** 按“不要搞无止境的测试”的要求，R2 之后不再做四角色全量复测；只由对应角色复核 R3-N1（复现路径原样保存 → 比较）和 R3M-1（按文档写的包能装上），其余低项以单元测试和截图核对为准。
3. **交接：** R1 的方法改动（A19/A22/A22a 经济下调顺序、A20 分类型电池上限）已在 VALUE 101 上验证没有数值副作用，交接文档可以照常给 methodology 编辑员和网页上传员阅读；需要他们注意的只有 R3-N2、R3-N7 两条 advisory 措辞。按 A17，网站上传与发布仍等前端翻新之后。
4. **负责人决定项** 见 10.7，其中 AF3-1 影响所有 VALUE 101 年度对照的可读性，建议优先决定。

### 10.9 安全与环境核对（R1 复测）

- **进程：** 四个角色都只按自己记录的 PID 停止进程。

  | 角色 | 停止的 PID |
  |---|---|
  | 复现 | API 902751、UI 903189 |
  | 换数据 | API 903022、UI 903220、驱动 903761（SIGTERM 后仍在监听，对同一 PID 补发 SIGKILL，无子进程） |
  | 改函数 | API 902633、1065284、1088858（两次 `restart-api.sh` 中按 PID 停止），UI 902635 |
  | 加功能 | API 902791、917669、1093664，UI 902793、917671 |

  端口 18850–18857、18859 都已释放，没有残留 worker。没有连接 8766/8800，没有使用 pkill、killall 或按模式的 kill。
- **INTEG：** 四个角色都没有改动，`git status` 为空；Python 都通过 `vpy` 调用。改函数角色在导出副本中改过的四个文件已还原到与 HEAD 逐字节相同后再删除。
- **磁盘：** 各角色已删除 `state/`（556–750 MB，其中执行归档约 500 MB）和 `src/`（152 MB）；保留的截图与证据每个角色 5–23 MB。
- **INSTALLED：** 四个角色结束时，以及本次汇总结束时，都执行了两项检查：
  - `find <INSTALLED> -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出安装时就有的 `.supervisor.lock`（0 字节，mtime 2026-10-03 05:41:26）；
  - `diagnose-value --prefix <INSTALLED>` 退出码 0，输出 “Installation integrity and runtime checks passed.”（中途的 vinext “Premature close” 来自诊断探针本身）。

## 11 R2 定向复核（2026-10-07）

- **范围：** DECISIONS A23（负责人对 R1 复测遗留项的裁决）列出的各项，以及第 10.7 节“顺带修”的低项。A23 写明“本轮之后只做定向复核，不做四角色全量复测”，作者也要求“不要无止境测试”，所以本节**没有**重新起四个角色，也没有在真实实例上重跑 Run。
- **代码状态：** 分支 `fix/review-2026-10-04`，HEAD `71cd564`（R2-1 提交 `16b9ef2`…`a89b1f4`、报告 `d6046df`；R2-2 提交 `7d7cd57`…`431af90`、报告 `71cd564`）。
- **证据来源：**
  1. R2 收尾时在 INTEG 上重跑的单元测试（经 `vpy`，`unittest`）：`tests.test_r2_numeric_identity`、`tests.test_r2_methodology_record`、`tests.test_r2_advisory_assets`、`tests.test_r2_developer_guide_contracts` 共 18 个，全部通过；`tests.test_results_summary`、`tests.test_comparison_identity`、`tests.test_module_source_changed` 共 46 个，全部通过；
  2. R2 收尾时的直接核对：第 10.6 节复现 R3-N1 的原始调用；p06 advisory 的目录文字；重启成本参数表的规则文字与 sha256；`methodology.UNIVERSAL_ACCOUNTING_CORRECTIONS` 的内容；
  3. R2-1、R2-2 两份工作报告（`docs/dev/p0-reports/R2-1-backend.md`、`R2-2-ui-docs.md`）中的测试、golden 检查和截图（`docs/dev/p0-ui-screens/r2-*.jpg`，20 张；其中模块安装、隔离和页头 pill 来自 scratch 真实实例，其余由 Playwright 拦截请求生成，比较响应由后端 `compare_run_summaries` 实际生成）。
- 第 10.8 节第 2 条原建议由对应角色复核 R3-N1 和 R3M-1。本轮改用单元测试复核：R3-N1 的测试经本地 API 原样保存两次（第二次 VoLL 为 int），只生成 1 个修订，比较结果为 same；R3M-1 的测试按指南表中的 contract ID 构建并安装示例包。R2-2 另在 scratch 实例中按指南命令构建并经 Modules 页安装成功。两项都没有由角色测试员在界面上重走一遍。

### 11.1 A23 各项的状态

| 项目 | A23 裁决 | 状态 | 提交 | 证据 |
|---|---|---|---|---|
| R3-N1（中，必修） | 保存时数值规范化，比较时按数值比较 | **已修，已复核** | `16b9ef2` | 第 10.6 节的原始调用 `_differing_paths([{… 17000.0}], [{… 17000}])` 修复前返回 `['market_configuration.voll_gbp_per_mwh']`，R2 收尾时重跑返回 `[]`。原样保存不再生成新修订（哈希相同时返回原记录），修订哈希算法不变。`tests/test_r2_numeric_identity.py` 7 个通过，其中包括经本地 API 保存两次只有 1 个修订文件、identity 审查为 same、真实数值变化仍会报告 |
| AF3-1（低-中） | 年度差值按指标门控，只扣发依赖弃电证据的指标，注明原因 | **已修，已复核** | `0d0bc98`（后端）、`cbfca6a`（界面） | 后端新增 `metric_delta_gates`（每个指标 `allowed`、`reason_code`、`reason`）与 `withheld_metric_deltas`；`metric_deltas_allowed` 含义不变（全部指标可比时才为真）。界面逐指标显示差值，被扣发的指标写 `Delta withheld: {reason}`，总括用 info-box `Deltas withheld`。VALUE 101 无反事实快照时，成本和碳显示差值，三个弃电指标扣发并写原因。`tests/test_results_summary.py` 通过；截图 `r2-compare-per-metric-deltas`、`r2-compare-withheld-summary`；离线 e2e `comparison-review.spec.ts` 2 个通过（R2-2 报告） |
| R-D10（信息） | golden D3/C3 identity 区本轮同步 | **已修** | `a89b1f4` | D3 revision 13（只有 identity 13 列）；C3 revision 16 同时同步 identity 1 列。`capture.py check --tier fast` 之后 C3、D3 identity 差异为 0（R2-1 报告第 3 节）。D1、D2、C8 的 identity 区不在 A23 范围内，仍落后（不设门） |
| R3-N6 / O-3（信息） | Run 记录写入实际生效的 correction id，含 `fx5.voll-17000` | **已修，已复核** | `3609f06` | 方法记录（status.json、resolved-run.json、provenance 共用）新增 `universal_accounting_correction_ids` 与 `correction_ids_in_force`。R2 收尾时核对 `UNIVERSAL_ACCOUNTING_CORRECTIONS` 共 9 项，含 `fx5.voll-17000`。方法身份 `applied_corrections_sha256` 不变，已保存的 Study 不需要确认。`tests/test_r2_methodology_record.py` 3 个通过 |
| R3-N7（信息） | advisory 按资产是否存在筛选 | **已修，已复核** | `fad02ae` | 修正目录 `applies_when.assets_any`（展示字段，不进方法身份），按 Run 冻结输入中的机组判断，读不到机组时保留 advisory。VALUE 101 的 doctoral Run 不再列出核电 advisory（high 由 7 条回到 6 条）；GBP1 有核电与径流水电，不受影响。`tests/test_r2_advisory_assets.py` 3 个通过 |
| R3M-1（低-中） | 本轮修 | **已修，已复核** | `7d7cd57` | `MODULE_DEVELOPER_101.md` / `_ZH.md` 的 slot 表、第 7 节说明与第 8 节 manifest 示例都改为安装器接受的 `value.*` ID（`value.psm/v2`、`value.storage-cost/v1`、`value.investment/v2` 等，与 `gridform_core/v2/module_manifest.py` 的 `SUPPORTED_CONTRACTS` 一致），并引用安装器拒绝 `gridform.*` 的原文。`tests/test_r2_developer_guide_contracts.py` 5 个通过（按指南 ID 构建的包安装成功，`gridform.storage-cost/v1` 的包按引用原文被拒绝）。R2-2 在 scratch 实例中经 Modules 页安装成功（截图 `r2-guide-module-installed`、`r2-guide-gridform-refused`） |
| R3-N2（低-中） | p06 advisory 与 A19 冲突的措辞改掉，并告知 methodology 编辑员 | **已修（措辞），已复核** | `e05bea3` | R2 收尾时读取目录：标题为 “Down regulation bookkeeping (ramp history, breaks, budgets)”，正文只讲三项记账缺陷，并写明先弃风是论文规则、不是缺陷（A19）。严重度仍为 high（R2-1 偏差 3：A23 只要求改措辞，是否降级由负责人定）。`docs/generated/METHODOLOGY_PROFILES.md` 已重新生成；methodology 交接文档已同步（第 0 节阅读提示、N-9、第 9 节第 13 条） |
| A22a 收尾 | 取值表公式文字改为 a = c − S/(m·H)，修正族 golden 修订一次 | **已修，已复核** | `a89b1f4` | R2 收尾时读取 `gridform_core/data/thermal/value_thermal_restart_v1.json`：`rule.shutdown_segment` 为 “… net saving per MWh a(H) = c - S(H) / (m H) (DECISIONS A22a)”，sha256 `446b1df5…`（原 `d4a5695a…`），取值不变。C1–C6、C9 各修订一次，只有 `restart_table_sha256` 一列变化，数值列全部不变。0.4 草稿 `p06_default_psm_clearing.md` 的旧式一并改正 |

### 11.2 第 10.7 节“顺带修”低项的状态

| 项目 | 状态 | 提交 | 证据 / 说明 |
|---|---|---|---|
| R3-N3 | 已修 | `fe87166` | “Open in Inspect” 不再写死 Planning，导航清除之前请求的标签；源码契约测试 `r2-ui-low-items` 覆盖（需要带 Callout 的真实 Run 才能截图，没有截图） |
| R3-N4 | 已修（重名只提示） | `fe87166` | 创建后基线不变、名称清空；重名给琥珀色提示，不阻止（F-R22-6，待设计方定）。截图 `r2-journey-duplicate-name` |
| R3M-2 | 已修 | `fe87166` | health degraded 时页头 pill 照常显示计数（真实实例截图 `r2-pill-degraded-health`） |
| R3M-3 | 已修 | `930faf0` | Enable 失败后提示修好后再点 Enable（截图 `r2-enable-failure-hint`） |
| R3M-4 | 已修 | `930faf0` | 卡片引用说明按状态区分；用户指南中英文同步（截图 `r2-disabled-card-usage-note`） |
| R3M-5 | 已修 | `d1ad608`（后端）、`930faf0`（界面） | 已隔离模块不再承诺记录新哈希；readiness 不再重复计数（真实实例截图 `r2-quarantined-card-source-change`） |
| R3M-6 | 已修 | `c2ed529` | 原地改源码的模块按字段点名（`modules.storage_cost.source_sha256`），教学范围与年度范围结论一致 |
| R3M-7 | 部分修 | `cbfca6a`、`fe87166` | 英文界面中夹杂的中文已改；研究引导页、Read me、映射编辑器、冻结输入恢复面板整页中文未翻译（F-R22-3，界面语言策略交设计方） |
| AF3-2 | 已修 | `c2ed529`、`cbfca6a` | 去掉双重括号；身份块标签写明扩展的选择属于方法维度 |
| L-1、L-2、L-3 | 已修 | `a27e1b6` | 坏单元格一次列全（空值、非有限值、负需求），`tests/test_data_mapping.py` 新增用例 |
| L-5 | 部分修 | `a27e1b6` | API 的 `price_year` 若给出须在 1990–2100；`price_year` 仍可省略、`fx_basis` 仍为自由文本（R2-1 偏差 4，不改 API 合同） |
| L-4 | 界面已修 | `fe87166`、`431af90` | Learn 页说明启动等待（截图 `r2-learn-launch-note`）；POST 持锁归档仍属 P1-11 / F5-08 |
| L-6 | 已修 | `fe87166` | 报告为空时不再显示 `null`（没有截图） |

### 11.3 测试与门禁（R2 两个单元的记录）

- R2-1：每个提交前跑相关模块的后端测试（`scripts/run_backend_tests.py --modules …`），全部 `new_failures: []`；`p0_gate.py quick` passed；A22a 提交之后 `capture.py check --tier fast` passed，C1–C4、C7、C8、D1–D3 gated 差异为 0。
- R2-2：每个提交前 `p0_gate.py quick` passed（16 步，无豁免）；UI unit 163、render 67、source-contracts 66 全部通过；离线 e2e 39 passed、5 个已登记的已知失败、0 个新失败。
- R2 收尾：见本节开头的单元测试与直接核对；交接文档更新后 `p0_gate.py quick` 一次，结果见收尾报告 `docs/dev/p0-reports/R2-handoff-update.md`。

### 11.4 仍未关闭、但不阻塞本轮的项

| 项目 | 去向 |
|---|---|
| R3-N2 的严重度（仍为 high） | 负责人决定是否降为 medium |
| F-R22-3（界面是否统一为一种语言）、F-R22-6（Study 重名是否阻止），以及 F-R22-1…11 的文案 | 设计方复核；按 A17 前端整体翻新时一并处理 |
| L-4 后端部分、O-1、R-D4（后端）、S-D10、N-4、AF3-3、O-2 | 已转 P1（`STUDY_LIFECYCLE_LOCK` 持锁与草稿持久化，P1-11 / F5-08） |
| D1、D2、C8 的 golden identity 区落后 | 不设门，A23 只要求 D3/C3 |
| 重启成本的价格基年；分区再调度的下调次序是否按 A19 处理 | 作者决定（`MODEL_CHANGES_BRIEF.md` 5.3 节） |
| 指南第 13 节“只有七个 slot 可替换”与 `SUPPORTED_CONTRACTS` 另外三个 slot 的关系 | 未核对，留 P1（R2-2 报告第 6 节） |

**结论：** A23 列出的各项都已处理；必修项 R3-N1 已修并经单元测试复核。没有新发现的中等及以上缺陷。R2 没有改变任何模型数值：修正族 golden 只有 `restart_table_sha256` 一列变化，论文族只同步了 D3 的 identity 区。按 A23，R2 之后不再做四角色全量复测。

## 附录 A 复核脚本与输出

`$ROLES` = `/tmp/claude-1000/-home-deepseek--config-Claude-scratch-workspaces-236b67cc-cc11-47c6-901f-9efac7ff2b1f-954fe4c9-9c87-4a98-b62f-216510b0e0f0-scratch-2026-10-04-a946e8/fd56b27b-0c52-4166-89c3-a4a8b5e4ea96/scratchpad/build/roles`。这是会话的 scratch 目录，可能被清理；需要长期保留的证据，请在清理前另行归档。

| 脚本 | 复核项 | 调用方式 |
|---|---|---|
| `$ROLES/consolidate/repro_af_d1.py` | F-D1（变体 A/B/C；smoke、two_year_smoke） | `PYTHONPATH=<INTEG> vpy repro_af_d1.py <INTEG> <out> smoke` |
| `$ROLES/consolidate/repro_af_d2.py` | F-D2（C3 一日 + toy 扩展） | `PYTHONPATH=<INTEG> vpy repro_af_d2.py <INTEG> <out>` |
| `$ROLES/consolidate/repro_sd_d1.py` | S-D1（preflight 问题数量与位置） | `PYTHONPATH=<INTEG> vpy repro_sd_d1.py <INTEG> <out>`，输出在 `sd-d1.json` |
| `$ROLES/consolidate/diagnose.txt` | INSTALLED 诊断输出 | — |
| `$ROLES2/consolidate/repro_n2.py` | 第 9.6 节 N-2（London 秋季重复时刻只出现一次） | `PYTHONPATH=<INTEG> vpy repro_n2.py <out>`，生成 `n2_naive_london.csv` |

`$ROLES2` = `$ROLES` 的同级目录 `…/scratchpad/build/roles2`，存放修复轮复测的四个角色目录（`reproduce/`、`swap-data/`、`edit-module/`、`add-feature/`）和汇总复核目录 `consolidate/`。同样可能被清理。

`$ROLES3` = `$ROLES` 的同级目录 `…/scratchpad/build/roles3`，存放 R1 轮复测的四个角色目录（`reproduce/`、`swap-data/`、`edit-module/`、`add-feature/`）。第 10.6 节的复核只读代码，另用一行 `vpy -c` 调用 `_differing_paths` 复现 R3-N1 的比较逻辑，没有单独的脚本。同样可能被清理。

## 附录 B 角色证据位置

| 角色 | 目录 | 内容 |
|---|---|---|
| 复现 | `$ROLES/reproduce/` | `shots/`（9 张）、api.log、ui.log、build.log、pids.txt、runs-final.txt |
| 换数据 | `$ROLES/swap-data/` | `shots/`（10 张）、`evidence/`、`input/my_gb_data_48rows.csv`、api.py、驱动客户端 `d`、日志 |
| 改函数 | `$ROLES/edit-module/` | `shots/`（10 张）、`scripts/`（Playwright 脚本）、restart.sh、api.log、ui.log |
| 加功能 | `$ROLES/add-feature/` | `shots/`（10 张）、`ev/`（日志、API 响应、对比、diagnose.txt）、`author/`（作者包和测试） |
