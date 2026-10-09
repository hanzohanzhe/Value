# VALUE bilingual project guide

> **版本 / Version:** 源码应用 VALUE **0.7.0-alpha.1**（Python `0.7.0a1`）；方法学 **0.4.1（2026-10-09）**。安装包、数据发行与源码的对应关系见[部署说明](docs/DEPLOYMENT.md)和[发行映射](docs/release/release-map.json)。
> Source application VALUE 0.7.0-alpha.1; methodology edition 0.4.1 (2026-10-09). See the deployment guide and the release map for installers and data releases.

[一句话说明](#0-一句话说明--one-sentence-explanation) · [核心对象](#1-核心对象--core-objects) · [界面](#2-界面与地址--interface-and-addresses) · [四条路径](#3-四条研究路径--the-four-research-paths) · [运行与比较](#4-运行比较与检查--runs-comparison-and-inspect) · [边界](#5-能说什么不能说什么--claims-and-limits) · [详细文档](#7-详细文档--detailed-guides)

---

## 0. 一句话说明 | One-sentence explanation

**中文：** VALUE（**V**ariable renewable electricity **A**llocation, **L**oad-enabled excess-generation **U**tilisation, and system **E**volution）是电力系统运行与容量扩张建模框架。数据、模块、年份和参数先保存为一个 Study，再由 Run 调用真实 Python 模块逐年执行 PSM → 投资 → 规划 → 下一年状态。英国基线是单节点模型；网络研究模块各自带成熟度标记。

**English:** VALUE is a power-system operation and capacity-expansion framework. A Study fixes the data pack, executable modules, years and assumptions; a Run executes the real Python PSM–CEM chain year by year. The GB baseline is single-node; network research modules carry their own maturity labels.

---

## 1. 核心对象 | Core objects

| 名称 | 中文解释 | English explanation |
|---|---|---|
| **Data pack** | 一组版本化数据绑定。每个文件绑定到稳定语义角色（如 `demand.real`、`projects.repd`），记录单位、时钟、来源和 SHA-256。 | A versioned set of bindings from files to stable semantic roles, with units, clock, provenance and SHA-256. |
| **Module** | 有 manifest、版本、输入输出契约和 Python 入口的可执行实现，占用一个 slot（`psm`、`storage_cost`、`pipeline`、`vre_cap`、`storage_cap`、`investment`、`transition`，可选 `network_expansion`）。 | An executable implementation with a manifest, version, I/O contract and Python entry point, filling one slot. |
| **Extension** | 增加数据角色、参数、生命周期钩子或新模型领域的扩展包；不悄悄替换模块。 | Adds data roles, parameters, lifecycle hooks or a model domain; never silently replaces a module. |
| **Study** | 可复现的研究配方：数据包、年份、方法学口径、每个 slot 的模块、科学参数和输出设置。每次保存生成不可变 revision 与哈希。 | A reproducible recipe: data pack, years, methodology profile, one module per slot, parameters and output settings. Every save is an immutable revision. |
| **Run** | Study 某个 revision 的一次执行。排队时记录执行身份（已安装代码和输入），之后生成 checkpoint 与结果证据。 | One execution of a Study revision. It records its execution identity when queued and writes checkpoints and evidence. |
| **Methodology profile** | **修正口径（默认）**（`value-corrected`）或**论文复现口径**（`doctoral-lineage-0.6.0a2`）。两者共享一组通用修正；修正口径另有方法修正。 | **Corrected methodology (default)** or **Doctoral reproduction**. Both share the universal corrections; the corrected profile adds method corrections. |

年度执行顺序 | Annual order:

```text
规划项目推进与到期投产 / advance planning and commission due projects
    → 选定 PSM 出清 / selected PSM clearing
    → 风光和储能扩张上限 / VRE and storage headroom
    → 投资 agents 提案与退役 / investment proposals and retirements
    → 规划准入、延期或失败 / planning admission, deferment or failure
    → 冻结下一年资产、项目、所有者和储能状态 / next-year checkpoint
```

本地状态默认在 `%LOCALAPPDATA%\VALUE`（Windows）或 `~/.local/share/value`（其他系统）；设置 `VALUE_DATA_HOME` 可改到别处。Local state defaults to `%LOCALAPPDATA%\VALUE` on Windows and `~/.local/share/value` elsewhere; `VALUE_DATA_HOME` overrides it.

---

## 2. 界面与地址 | Interface and addresses

侧栏分三组 | The sidebar has three groups:

| 组 / Group | 页面 / Pages |
|---|---|
| **Start**（开始） | Home、Learn（VALUE 101）、Research guide（研究路径） |
| **Work**（工作） | Studies、Data、Modules、Extensions |
| **Results**（结果） | Runs（Run 中心）、Compare、Inspect |

- 侧栏底部始终显示服务状态（无应答时有 **Retry**）、语言切换和版本号。界面默认英文，可切换为中文；选择保存在 cookie `value_locale`。模型时间一律按 UTC 标注。
  The sidebar footer always shows service status (with **Retry**), the language switch and the version. English is the default; the choice is kept in the cookie `value_locale`. Model times are labelled UTC.
- 每个页面有自己的地址：`/`、`/learn`、`/journey`、`/studies`、`/studies/<study>`、`/data`、`/modules`、`/extensions`、`/runs`、`/runs/<run>`（`?year=`）、`/runs/<run>/replay`、`/runs/<run>/vre`、`/runs/<run>/network`、`/runs/<run>/systems`、`/compare`（`?runs=a,b&ref=a`）、`/inspect`。旧链接 `/?view=…` 自动转到对应地址。
  Every page has its own address; old `/?view=…` links are forwarded.
- 一个 Run 的页面（`/runs/<run>/…`）顶部有 Run 上下文条：方法学口径、验证状态、能量平衡和 stress 事件。
  A Run's own pages show the Run context bar: methodology, validation, energy balance and stress events.

---

## 3. 四条研究路径 | The four research paths

Home 上的四张卡片对应四条路径 | Home offers four paths:

### 3.1 Reproduce from existing data

1. Home → **Reproduce from existing data** 打开研究路径页（`/journey`）。没有 Study 时先在 **Learn** 点 **Create baseline Study**。
2. 选择基线 Study；页面用它当前保存的 revision、模块和数据包。
3. 填写新 Study 名称，点 **Create the reproduction Study**。创建只保存 Study，不启动 Run。
4. 在 **Runs** 选择范围，点 **Check readiness**，再点 **Run selected scope**。
5. 完成后在 **Compare** 勾选基线 Run 和新 Run，基线 Run 作为参照 Run。

Choose a baseline Study, create an independent reproduction Study from its current revision, check readiness and run it in **Runs**, then compare it with the baseline Run on **Compare**.

### 3.2 Add your new data

1. Home → **Add your new data**（`/journey`），选择基线 Study。
2. **Copy the baseline BASE pack and add my files** 复制出独立的数据包；或选择一个已安装的其他数据包。
3. 在 **Data** 为每个文件选择语义角色并替换；CSV 映射编辑器核对列、单位（需求按 MW 读）、时钟和欧元汇率，校验后写入新绑定。也可以在 **Data → Install a VALUE data pack** 安装完整的 `value.data-bundle/v1` 数据包。
4. 回到研究路径页，点 **Create the new-data Study**，再在 **Runs** 检查就绪并运行，最后在 **Compare** 与基线比较。

Copy the baseline pack (or choose another installed pack), map your files to the semantic roles in **Data**, create the new-data Study, run it and compare it with the baseline.

### 3.3 Edit a module

1. Home → **Edit a module** 打开 **Modules** 页的模块编写工具（Author a module）。
2. 选择 slot 和模块，查看契约、入口、源码哈希；**Download editable source template** 下载可编辑模板，在本地用新的模块 ID 和包名实现并测试，用 `scripts/build_module_bundle.py` 打包。
3. **Modules → Install a model module** 安装 `value.module-bundle/v1` ZIP（需确认信任可执行代码）。
4. **Create Study with this module** 从已保存的 Study 派生一个只改这一个 slot 的独立 Study；运行后在 **Compare** 比较。

Inspect a module, implement a separate one locally from the template, install the bundle on **Modules**, derive a Study that changes only that slot, run and compare. Details: [Module Developer 101](docs/MODULE_DEVELOPER_101.md) ([中文](docs/MODULE_DEVELOPER_101_ZH.md)).

### 3.4 Add a new function to VALUE

1. Home → **Add a new function to VALUE** 打开 **Extensions** 页的扩展编写工具。
2. 填写扩展提案（ID、命名空间、研究问题、验证计划），**Validate extension proposal**，再下载审阅后的扩展 ZIP；新的科学逻辑在本地开发和验证。
3. **Extensions → Install a model extension** 安装 `value.extension-bundle/v1` ZIP；安装不等于启用。
4. 在 Study 的 **Optional domains** 中选用该扩展（Advanced 级别显示已安装的扩展契约），保存新 revision 后运行。

Define and validate an extension proposal on **Extensions**, develop it locally, install the bundle, then select it in a Study's **Optional domains** (Advanced shows installed extension contracts). Details: [Build your own model 101](docs/BUILD_YOUR_OWN_MODEL_101.md) ([中文](docs/BUILD_YOUR_OWN_MODEL_101_ZH.md)).

---

## 4. 运行、比较与检查 | Runs, comparison and Inspect

| 范围 / Scope | 工作量 / Work | 年度经济性 / Annual economics |
|---|---|---|
| Two-period wiring check（两时段连接检查） | 一年 2 个半小时 | 不可解释 / not allowed |
| Two-year hand-off check（两年交接检查） | 两年各 2 个半小时 | 不可解释 / not allowed |
| One-day market lesson（一天市场课程） | 48 个半小时，只运行 PSM | 不可解释 / not allowed |
| Two full model years（两个完整模型年） | 两年各 17,520 个半小时 | 可以 / allowed |
| Complete study（完整研究） | Study 的全部年份 | 可以 / allowed |

- **Runs（Run 中心）**：就绪检查、启动、进度、错误码与诊断首行、checkpoint 恢复、安全取消、归档、审计包。有 Run 排队时变更模块或扩展，尚未开始的 Run 以 `GF_RUN_EXECUTION_IDENTITY_CHANGED` 停止，用 **Resubmit with current code** 重新提交。**Remove from workspace** 把 Run 目录移到本机回收目录，VALUE 不提供 Run 的恢复。
  The Run centre checks readiness, starts and follows Runs, shows each error code with the first diagnostic line, resumes checkpoints, cancels safely and archives. Queued Runs stopped by a module change are resubmitted with **Resubmit with current code**. Removing a Run cannot be undone in VALUE.
- **Compare**：勾选同一范围的 2–6 个已完成 Run，选择参照 Run（默认是最早创建的基线 Run）；所有差值相对参照 Run 计算，CSV 带 `reference_run_id`。定义不一致的指标不显示差值并写明原因。
  Tick two to six completed Runs of one scope and choose the reference Run; every delta is measured against it, and the CSV records `reference_run_id`. Deltas whose definitions differ are withheld with a reason.
- **Inspect**：按需读取 planning 项目、生命周期事件、市场时段与报价、结果文件与 provenance；按 Enter 或 **Apply filters** 搜索。
  Planning projects, lifecycle events, market periods and orders, artifacts and provenance, loaded on request.
- 状态词：`reconciled`、`unavailable`、`Partial year`、`Withheld`（只用于论文复现口径原始不变量未全部通过）、`invalid`、`Not modelled` / `Not computed` / `Not recorded`。缺失的值从不显示为 0。
  State words never turn missing evidence into zero.

---

## 5. 能说什么、不能说什么 | Claims and limits

可以说明 | Supported:

- 模型按记录的 bid-at-cost、投资和规划规则执行；能量、成本、碳和项目账本通过各自审计；新增资产经 CEM 投产后进入后续年份的 PSM。
  Execution under the declared bid-at-cost, investment and planning rules, with energy, cost, carbon and project ledgers audited.
- 修正口径下，验证 gate 失败时不发布年度经济结果；供给不足的时段作为 stress 事件记录，缺口记为未供电量。
  Under the corrected profile a failed validation gate withholds annual economics; supply shortfalls are recorded as stress events.

不能夸大 | Not supported:

- 英国境内输电约束、完整机组组合、AC 最优潮流、agent 调度或 CEM 的全局最优、对保留 Scheme C 内核的逐数值复刻。
  Internal GB transmission, full unit commitment, AC OPF, global optimality of agent dispatch or CEM expansion, exact retained-kernel reproduction.
- 两时段或一天教学运行的年度结论；VALUE 101 是合成数据，不代表英国。
  Annual conclusions from short scopes; VALUE 101 data are synthetic.

---

## 6. 许可 | Licence

软件 Apache-2.0，作者文档 CC BY 4.0，合成数据包 CC0；第三方数据保留各自条款，结果包不构成英国数据的再分发许可。详见 [LICENSING.md](LICENSING.md)。
Software Apache-2.0, author documentation CC BY 4.0, synthetic packs CC0; third-party data keep their own terms.

---

## 7. 详细文档 | Detailed guides

| 内容 / Topic | 中文 | English |
|---|---|---|
| 用户手册 / User guide | [USER_GUIDE_ZH.md](docs/USER_GUIDE_ZH.md) | [USER_GUIDE.md](docs/USER_GUIDE.md) |
| VALUE 101 | [VALUE_101_ZH.md](docs/tutorial/VALUE_101_ZH.md) | [VALUE_101.md](docs/tutorial/VALUE_101.md) |
| 自建模型 / Build your own model | [BUILD_YOUR_OWN_MODEL_101_ZH.md](docs/BUILD_YOUR_OWN_MODEL_101_ZH.md) | [BUILD_YOUR_OWN_MODEL_101.md](docs/BUILD_YOUR_OWN_MODEL_101.md) |
| 模块开发 / Module development | [MODULE_DEVELOPER_101_ZH.md](docs/MODULE_DEVELOPER_101_ZH.md) | [MODULE_DEVELOPER_101.md](docs/MODULE_DEVELOPER_101.md) |
| 方法学 / Methodology | [docs/methodology/README.md](docs/methodology/README.md) | [docs/methodology/README.md](docs/methodology/README.md) |
| 参数与模块目录 / Parameters and modules | [PARAMETERS.md](docs/generated/PARAMETERS.md)、[MODULES.md](docs/generated/MODULES.md) | same |
| 变更记录 / Changes | [CHANGELOG.md](CHANGELOG.md) | [CHANGELOG.md](CHANGELOG.md) |
