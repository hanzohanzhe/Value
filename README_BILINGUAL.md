# VALUE bilingual project guide

> **当前发行 / Current release:** 源码 `source-2026-10-04`，Full 批次 `2026-10-03-rc1`。下文包含历史安装与科学记录；以[当前部署说明](docs/DEPLOYMENT.md)及[发行映射](docs/release/release-map.json)识别实际发行和验收范围。
> This source-review snapshot is not a verified complete installer. Historical guides below retain their context; real UK data and several research parameter objects are omitted.
> 四角色 / Four workflows: `reproduce from existing data`、`add your new data`、`Edit module`、`add new function to VALUE`.

[中文快速演示](#1-明早给-stuart-的演示顺序--tomorrows-demo-sequence) · [核心名词](#2-forcegridform-和几个核心对象--force-gridform-and-the-core-objects) · [Data 25项接口](#5-data每一项上传什么--what-each-data-interface-requires) · [Modules](#6-modules每一个模块做什么--what-each-module-does) · [Studies](#7-studies所有选项说明--every-study-option) · [Runs](#8-runs如何运行和比较--running-and-comparing-studies) · [Inspect](#9-inspect查看什么--what-inspect-shows) · [Add data](#10-add-data目前能做什么--what-add-data-currently-does) · [Complete English reference](#17-complete-english-reference-for-stuart)

---

## 0. 一句话说明 | One-sentence explanation

**中文：** VALUE（**V**ariable renewable electricity **A**llocation, **L**oad-enabled excess-generation **U**tilisation, and system **E**volution）是电力系统与容量扩张建模框架。本仓库保留单节点基线，并增加带独立成熟度标记的网络研究模块。数据、模块、年份和参数先保存为一个 Study，再由 Runs 调用真实 Python 模块逐年执行 PSM → 投资 → 规划 → 下一年状态。

**English:** VALUE is the scientific power-system and capacity-expansion framework: Variable renewable electricity Allocation, Load-enabled excess-generation Utilisation, and system Evolution. This repository preserves the single-node baseline and adds network research modules with separate maturity labels. A Study fixes data, executable modules, years and assumptions; Runs executes the real Python PSM-CEM chain year by year.

**当前扩展前端 / Current expanded workflow:** Studies 现在采用五步 composer：
Identity → System domain → Optional domains → Model chain → Review。Data 会按当前
Study 动态显示 Network、AC feasibility、Hydrology 和 Network expansion 条件角色；
Modules 分开安装 `value.module-bundle/v1` 与 `value.extension-bundle/v1`；
Network & water 只读取完成运行的 typed artifacts。英国默认数据包仍是单节点，
目前没有已经验收的真实英国 network/hydrology 或全国输电扩容基线。

---

## 1. 历史研究工作区演示顺序 | Historical research-workspace demonstration

### 1.1 历史源码工作区准备（自行配置环境） | Historical source setup (developer environment)

1. 双击根目录的 [`start-value.cmd`](start-value.cmd)。第一次使用这台电脑时先运行 [`install-value.cmd`](install-value.cmd)。
   Double-click `start-value.cmd`. Run `install-value.cmd` first only if this installation has not been prepared.
2. 等待命令窗口显示：`VALUE started: http://127.0.0.1:8800`。启动脚本也会自动打开浏览器。
   Wait for the launcher to confirm that VALUE has started.
3. 如果浏览器没有自动打开，手动输入：**http://127.0.0.1:8800**。不要用 3000；3000 是开发地址，不是当前打包前端地址。
   If necessary, enter `http://127.0.0.1:8800` manually. Port 3000 is a development address.
4. 在右上角选择 **VALUE UK — 1000 TWh verified data**，确认显示 **25 of 25 inputs ready**。
   Select the verified 1000 TWh pack and confirm that all 25 inputs are ready.
5. 不需要互联网。网页和 API 都只绑定在这台电脑的 `127.0.0.1`。
   No internet connection is required; both services are loopback-only.

如果启动失败，在 PowerShell 中运行：

```powershell
py -3.10 scripts\doctor.py --capability value-native
```

### 1.2 建议的 8–10 分钟演示 | Recommended 8–10 minute walkthrough

| 顺序 | 打开什么 | 讲什么 | 不要误讲什么 |
|---:|---|---|---|
| 1 | **Home** | VALUE 是单节点、bid-at-cost PSM 与逐年 CEM；投资改变下一年实际机组状态。 | 不要说当前版本有英国内部输电约束、AC/DC 潮流或完整 unit commitment。 |
| 2 | **Data** | 选择 1000 TWh pack，展示 25/25；文件按语义角色绑定并留存 SHA-256。 | 不要选择 `VALUE UK research data` 后说模型坏了；它本来就是空白导入工作区。 |
| 3 | **Modules** | 展示每个 Study 选择的是真实 Python implementation；重点讲两个 PSM 和三个储能定价模块。 | 不要把保留的 VALUE 整体 kernel 说成前端可选 PSM；它只是单独的比较证据。 |
| 4 | **Studies** | 解释 Study = 数据包 + 年份 + 模块链 + 参数的版本化配方。展示 dynamic 与 legacy 两个储能情景。 | 右侧 Saved studies 是配置，不等于每一个都已有可信结果。 |
| 5 | **Runs** | 打开已完成的 dynamic 与 legacy 十年 full run，展示成本、容量、规划和跨情景比较。 | 现场不要重跑十年。Two-period 只验证接线，不能解释年成本。 |
| 6 | **Inspect → Planning** | 搜索项目，展示阶段、地区、MW、预计完成年、失败/过滤原因和生命周期事件。 | 不要把 expected capacity 当作确定会建成的实体项目。 |
| 7 | **Inspect → Market** | 展示逐期需求、接受供给、出清价、能量残差；full trace 才能查看逐笔 bid/order。 | Summary trace 没有逐笔订单不等于模型没竞价。 |
| 8 | **Inspect → Artifacts & provenance** | 展示 resolved execution identity、输入哈希、模块版本和可下载审计文件。 | 不要把 VALUE 说成另一个求解器。 |

**可直接对 Stuart 说：**

> VALUE is the model and local research workbench. The data pack, executable modules and assumptions are frozen into a versioned Study. The run then clears the selected PSM, applies investment and planning decisions, commissions assets into the following year's fleet, and records the market and planning evidence needed for audit.

---

## 2. VALUE、VALUE 和几个核心对象 | VALUE, VALUE and the core objects

| 名称 | 中文解释 | English explanation |
|---|---|---|
| **VALUE** | 科学模型与模块契约：PSM、储能定价、扩张上限、投资 agent、planning pipeline 和状态转移。 | The scientific framework and executable contracts: PSM, storage pricing, expansion caps, investment agents, planning and state transition. |
| **VALUE** | 本地网页、API、模块注册表和研究工作区管理层。它负责组织输入和运行，不是第三个科学模型，也不是独立求解器。 | The local web UI, API, module registry and study/run manager. It is not a third scientific model or a solver. |
| **Data pack** | 一组版本化数据绑定。每个文件被绑定到稳定语义角色，如 `demand.real` 或 `projects.repd`。 | A versioned set of bindings from local files to stable semantic roles. |
| **Module** | 一个有 manifest、版本、输入输出和 Python entry point 的真实可执行实现。 | A real executable implementation with a manifest, version, I/O contract and Python entry point. |
| **Study** | 可复现的研究配方：数据包、年份、模块选择、科学参数和运行输出设置。保存会生成 revision 与哈希。 | A reproducible research recipe containing the data pack, years, modules, scientific parameters and runtime/output settings. |
| **Run** | Study 的一次冻结执行。启动时复制/冻结输入、参数、模块版本和实现哈希，之后生成 checkpoint 与结果证据。 | One immutable execution of a Study, with frozen inputs, parameters, module identities, checkpoints and evidence. |
| **Adapter** | 把外部数据库的字段、单位、技术名称和时间轴转换为 VALUE 标准角色的边界程序。 | A boundary transformation that maps a foreign database into VALUE fields, units, technology codes and chronology. |
| **`.gridform`** | 当前源码安装使用的本地状态目录，内含 data packs、studies、runs、archives 和 trash。它是历史命名的工作区目录，不是模型名称。 | The current source installation's local state directory. The historical folder name does not denote a separate model. |

### 年度执行顺序 | Annual execution order

```text
规划项目推进与到期投产 / advance planning and commission due projects
    → 选定 PSM 出清 / selected PSM clearing
    → 风光和储能扩张上限 / VRE and storage headroom
    → 投资 agents 提案与退役 / investment proposals and retirements
    → 规划准入、延期或失败 / planning admission, deferment or failure
    → 冻结下一年资产、项目、所有者和储能状态 / next-year checkpoint
```

---

## 3. “Research data”和“1000 TWh data”的区别 | Difference between the two data packs

| 前端名称 | 当前状态 | 实际用途 | 是否现在能运行 |
|---|---:|---|---:|
| **VALUE UK research data** (`uk-scheme-c`) | 0/25 | 空白导入工作区。用于把另一套已经标准化的数据逐项接入 25 个语义接口。它不是另一套已经准备好的英国数据库。 | **不能**；必须先填满并通过校验。 |
| **VALUE UK — 1000 TWh verified data** (`value-uk-1000twh-reproduction`) | 25/25 | 当前英国研究情景的完整、哈希化、已验证数据包；现有 UK Studies 和长跑证据使用它。`1000 TWh` 是该研究情景/储能扩张设定的标签，不是通用 VALUE 数据标准。 | **能**；是明早演示应选的数据包。 |

**English summary:** `VALUE UK research data` is an empty import workspace, not a second completed dataset. `VALUE UK — 1000 TWh verified data` is the populated, scenario-specific UK pack used by the current studies and tests.

选择右上角的 data pack 只改变当前浏览的数据包。真正运行哪个数据包由保存后的 Study 决定。
The top-right selector changes the pack being inspected; a run uses the pack frozen in the saved Study.

---

## 4. 七个栏目分别做什么 | What the seven pages do

| 栏目 | 作用 | 典型操作 |
|---|---|---|
| **Home** | 总览数据就绪、模块运行环境、年度因果链和当前科学边界。 | 演示模型范围；确认 Python/服务在线。 |
| **Data** | 显示 25 个语义输入、允许格式、当前文件、大小和哈希；可替换已标准化文件。 | 检查 25/25；上传或替换某个绑定。 |
| **Modules** | 显示注册表中所有真实可执行模块、版本、contract、输入输出与就绪状态。 | 解释某个 Study 选择了哪套 PSM/CEM 方法。 |
| **Studies** | 创建和保存研究配置，选择数据、年份、模块链与参数。 | 建 dynamic/legacy/perfect-foresight 等可比较情景。 |
| **Runs** | 做 preflight、启动、取消、恢复、归档、导出、删除和跨情景比较。 | 先 Check readiness，再跑；查看年度结果。 |
| **Inspect** | 按需读取详细 planning、market、artifacts 和 provenance。 | 审核某项目为什么失败；查看某期 bid/order；下载证据。 |
| **Add data** | 说明外部数据库如何通过 adapter 接到语义角色。 | 查看适配器步骤和 manifest 示例；目前不是完整无代码导入向导。 |

---

## 5. Data：每一项上传什么 | What each Data interface requires

### 5.1 先读这条格式说明 | Read this format rule first

Data 页的 **Accepted formats** 是接口层允许上传的扩展名；当前内置 VALUE/VALUE-derived 读取器并没有对每种扩展名都提供自动转换。为了确保现有内置链能运行，请使用下表的 **内置链推荐格式**。如果使用其他扩展名，先在 Add data 所述的 adapter 中转换，或提供能读取该格式的新模块。

The UI lists contract-level upload extensions. The current built-in readers do not automatically convert every listed format. Use the **recommended built-in format** below unless a reviewed adapter or replacement module handles the alternative.

当前 25 项全部标记为 required；需求尚未按所选 PSM 动态裁剪。因此即使 perfect-foresight PSM 不直接使用全部天气文件，preflight 目前仍要求完整 data pack。
All 25 roles are currently globally required; requirements are not yet reduced according to the selected PSM.

### 5.2 PSM：市场与系统数据（15项） | PSM market and system inputs (15)

| # | 前端名称 / Role | 上传内容 | UI 接受 | 内置链推荐 | 最低结构、单位和时间要求 | 当前 1000 TWh 示例 |
|---:|---|---|---|---|---|---|
| 1 | Existing generator fleet<br>`fleet.generators` | 现有火电、核电、水电、储能、连接与位置 | JSON | **JSON** | 根对象至少含 `generators`, `batteries`, `connections`；技术、容量和成本字段应沿用示例 schema。 | `fleet.json` |
| 2 | Forecast demand profile<br>`demand.forecast` | 日前/预测需求逐期序列 | CSV, Parquet | **CSV** | 至少 17,520 个有限非负数；`MWh/period`；一个数值列，允许一个表头。 | `2022fd.csv` |
| 3 | Real demand profile<br>`demand.real` | 实际/平衡阶段需求逐期序列 | CSV, Parquet | **CSV** | 同上；当前正常时段为半小时。 | `2022reald.csv` |
| 4 | Wind weather field<br>`weather.wind` | 用机组位置生成风电可用率的格点天气 | NetCDF, Zarr | **NetCDF (.nc)** | 坐标 `longitude`, `latitude`；变量为 `wind_speed`，或同时有 `u100` 与 `v100`；时间可为 time×lat×lon 或 lat×lon×day×hour。 | `average_annual_wind_profile.nc` |
| 5 | Solar weather field<br>`weather.solar` | 用机组位置生成光伏可用率的格点辐照数据 | NetCDF, Zarr | **NetCDF (.nc)** | 坐标 `longitude`, `latitude`；辐照变量 `ssrd`；支持 time×lat×lon 或 lat×lon×day×hour。 | `average_annual_solar_profile.nc` |
| 6 | France import availability<br>`market.france.profile` | 法国边界进口可用电量/流量序列 | CSV | **CSV** | 一个主要数值列，建议表头 `availability_mwh`；`MWh/period`；短序列会循环重复，科学运行建议 17,520 期。 | `France_profile.csv` |
| 7 | France external price<br>`market.france.price` | 法国进口报价/外部价格序列 | CSV | **CSV** | 一个主要数值列；`GBP/MWh`；与 availability 同时间轴。 | `France.csv` |
| 8 | Belgium import availability<br>`market.belgium.profile` | 比利时边界进口可用量 | CSV | **CSV** | 同 France profile。 | `belgium_profile.csv` |
| 9 | Belgium external price<br>`market.belgium.price` | 比利时进口价格 | CSV | **CSV** | 同 France price；如果原始数据是 EUR/MWh，应在 adapter 边界先统一为 GBP/MWh。 | `Belgium_price.csv` |
| 10 | Netherlands import availability<br>`market.netherlands.profile` | 荷兰边界进口可用量 | CSV | **CSV** | 同 France profile。 | `nehtheralnd_profile.csv` |
| 11 | Netherlands external price<br>`market.netherlands.price` | 荷兰进口价格 | CSV | **CSV** | 同 France price。 | `Netherlands.csv` |
| 12 | Norway import availability<br>`market.norway.profile` | 挪威边界进口可用量 | CSV | **CSV** | 同 France profile。 | `Norway_profile.csv` |
| 13 | Norway external price<br>`market.norway.price` | 挪威进口价格 | CSV | **CSV** | 同 France price。 | `Norway.csv` |
| 14 | Ireland import availability<br>`market.ireland.profile` | 爱尔兰边界进口可用量 | CSV | **CSV** | 同 France profile。 | `Ireland_profile.csv` |
| 15 | Ireland external price<br>`market.ireland.price` | 爱尔兰进口价格 | CSV | **CSV** | 同 France price。 | `Ireland.csv` |

这些 interconnector 文件代表**模型边界外的进口供给报价**，不是英国内部输电线路。正流量被解释为可进口供给；当前模型没有内部线路容量、潮流或节点约束。
These interconnector series are external boundary offers, not internal GB transmission branches.

### 5.3 CEM：投资与规划数据（10项） | CEM investment and planning inputs (10)

| # | 前端名称 / Role | 上传内容 | UI 接受 | 内置链推荐 | 最低结构、单位和要求 | 当前 1000 TWh 示例 |
|---:|---|---|---|---|---|---|
| 16 | System-average solar profile<br>`profiles.vre_solar` | 太阳能系统平均容量因子 | CSV | **CSV** | 无表头单数值列最稳妥；所有值在 0–1；至少 8,760 个小时值，内置 adapter 可复制为半小时。 | `sa.csv` |
| 17 | System-average onshore profile<br>`profiles.vre_onshore` | 陆上风系统平均容量因子 | CSV | **CSV** | 同上。 | `wa.csv` |
| 18 | System-average offshore profile<br>`profiles.vre_offshore` | 海上风系统平均容量因子 | CSV | **CSV** | 同上。 | `we.csv` |
| 19 | Normalized planning projects<br>`projects.repd` | 已标准化的规划项目表，供 pipeline 使用 | CSV, Parquet | **CSV** | 必须有 `project_id`, `technology`, `capacity_mw`, `development_status`, `region`；ID 唯一；容量有限且非负。建议另有 `site_name`, country、各阶段日期和坐标。 | `repd_projects_normalized.csv` |
| 20 | Raw UK REPD source<br>`source.repd_raw` | 未改写的 REPD 源表，用于初始运营资产、重申请/替代关系和来源审计 | CSV | **CSV** | 至少有 `Ref ID`, `Site Name`, `Technology Type`, `Installed Capacity (MWelec)`, `Development Status`；保留原始列名。 | `repd-q2-jul-2025.csv` |
| 21 | Technology capital costs<br>`costs.capital` | 各技术 CAPEX 与相关资本成本资料 | CSV, JSON | **JSON** | 当前内置读取器要求根键 `capital_costs_per_mw`；其下按标准技术名称给出 `GBP/MW`。可保留 `active_profile` 与来源字段。 | `capital_costs.json` |
| 22 | Policy and support mechanisms<br>`policy.support` | 容量市场、安全/平衡与脱碳政策预算时间序列 | CSV, JSON, XLSX | **XLSX** | 当前内置读取器读取 `Sheet1`，至少包含 `Delivery Year`, `Security Budget (£mn)`, `Decarbonization Budget (£mn)`；其他明细列可保留。 | `mechansim cost.xlsx` |
| 23 | Planning stage timelines<br>`planning.timelines` | 各技术从规划阶段到建设/投产的时长 | CSV, JSON | **JSON** | 至少含 `development_stage_timelines`；当前 native initial-state 也读取 `development_timelines`，因此应按示例同时提供两者及状态映射；月份为主。 | `planning_timelines.json` |
| 24 | Regional technology success rates<br>`planning.success_rates` | 技术×地区的项目成功概率 | CSV, JSON | **CSV** | 必须有 `Technology`, `Region`, `Success_Rate`；成功率建议 0–1；额外项目数/成功失败统计列允许保留。 | `regional_technology_success_rates.csv` |
| 25 | VALUE investment and policy parameters<br>`config.model_parameters` | 投资、过滤、扩张和兼容参数的结构化配置 | JSON | **JSON** | 根对象至少含 `simulation_parameters` 与 `investment_parameters`；推荐沿用示例中的 `repd_filtering`, `storage_cap_fraction` 等命名。 | `model_parameters.json` |

当前示例文件可在本地数据包的 `files/<role>` 子目录查看。不要把本地 UK pack 直接提交到公开 GitHub；数据再分发权限与软件 Apache-2.0 许可是两回事。
The current samples live under the local pack's `files/<role>` directories. Do not assume that the installed UK pack may be redistributed with the Apache-2.0 software.

### 5.4 点击 Choose file / Replace 时发生什么 | What upload and replacement do

1. 浏览器把文件发送到本机 API；单文件上限 2 GiB，并要求上传后仍保留至少 1 GiB 磁盘余量。
   The local API enforces a 2 GiB file limit and a 1 GiB free-space floor.
2. 系统检查扩展名和对应 role 的结构要求，计算 SHA-256，并复制到内容寻址目录。原始桌面文件不会被模型直接依赖。
   The file is validated, hashed and copied into content-addressed local storage.
3. 校验失败时，新候选文件被丢弃，上一版有效 binding 保持不变。
   Failed candidates are rolled back; the previous valid binding remains active.
4. 校验成功只说明**该 role 的基础契约通过**。它不会自动猜测陌生字段、货币、技术名称或时间转换。
   Passing validation does not infer foreign columns, currencies, technology labels or chronology.
5. 替换数据后，应保存一个新的 Study revision，再启动新 run。已完成 run 的冻结输入和结果不会改变。
   Save a new Study revision after replacing data. Completed run snapshots remain unchanged.

---

## 6. Modules：每一个模块做什么 | What each module does

Modules 页不是代码展示截图：每张卡片对应模块注册表中的一个 Python entry point。Study 保存的是 module ID；run 启动时会解析并记录该实现文件的 SHA-256。当前内置注册表有 13 个模块。

Each card resolves to a real Python implementation. The selected module ID and implementation hash are frozen into the run.

### 6.1 当前模块目录 | Current module catalogue

| Study 槽位 | 当前模块 | 它实际做什么 | 可替换成什么 |
|---|---|---|---|
| **PSM** | `value-bid-at-cost-psm` v5.1.0<br>VALUE live bid-at-cost PSM | 单节点日前与平衡市场；VRE、火电、外部进口和储能报价共同竞争；使用选定 storage-cost 模块；没有机组启停、爬坡或内部输电约束。 | 可直接换成符合 `value.psm/v2` 的完整 UC、其他单节点出清或 ABM。网络 PSM 组合已发布的 network contract extension。 |
| **PSM** | `value-perfect-foresight-lp` v1.0.0<br>Perfect-foresight co-optimization | SciPy/HiGHS 单节点时序 LP；中央联合优化发电与储能 SOC、功率、能量和效率。它回答“完美预见最优调度”问题。 | 其他符合现有 contract 的 LP/MILP；若中央联合优化储能，应声明 `storage.central-cooptimization`。 |
| **PSM** | `value-reference-dc-network` v1.0.0 | 线性时序 DC network PSM：节点平衡、角度、线路容量、拥塞、节点价格、储能 SOC；仅在声明的 reference scope 为 ready。 | 组合 `value-network-contract-extension` 的其他 `value.psm/v2` network solver。 |
| **PSM** | `value-reference-ac-feasibility` v0.1.0 | 对给定有功计划作局部 AC 可行性检查；含 P/Q、电压与损耗；实验性，**不是 AC OPF**。 | 另一个明确声明收敛/最优性边界的 PSM；不得把 feasibility 冒充经济最优出清。 |
| **Network expansion** | `reference-transmission-expansion` v1.0.0 | 实验性 candidate → proposal → planning → commissioned/failed/retired 生命周期，并将投产线路注入下一年 DC 出清。 | 其他符合 `value.network-expansion/v1` 的扩容/规划规则。 |
| **Storage cost** | `dynamic-annual-storage-cost` v1.0.0 | 第一年度按满负荷设计售电量初始化；以后用上一年售电量和售电加权 dwell time 分摊年化项目回收；循环折旧只作用于电池。 | 其他公开的储能 offer cost、成本回收或退化定价方法，符合 `value.storage-cost/v1`。 |
| **Storage cost** | `value-legacy-storage-tariff` v1.0.0 | 保留 VALUE 的固定分量 + 储存时长分量，用于历史复现和基准比较。 | 仅适合 legacy comparison；不应被表述成新的通用科学推荐。 |
| **Storage cost** | `user-formula-storage-cost` v1.0.0 | 用户在批准变量上写算术表达式；禁止任意 Python。默认式为循环折旧 + dwell periods × holding recovery。 | 在同一安全表达式边界内替换为用户公式；更复杂逻辑应作为新审核模块发布。 |
| **Pipeline** | `planning-pipeline` v2.2.0 | 推进既有/新建项目，应用时间线与成功规则，记录 active、deferred、failed、filtered、commissioned 及原因；投产资产写入下一年 fleet。 | 其他国家的许可阶段、随机成功模型、排队/并网逻辑或选址水文规则，符合 `value.planning/v2`。 |
| **VRE cap** | `vre-expansion-cap` v2.0.0 | 根据需求、VRE profile 和本年 PSM 结果计算太阳能、陆风、海风年度共享扩张 headroom。 | 土地/供应链/并网/政府目标约束，或地区/技术分层的扩张上限，符合 `value.expansion-policy/v2`。 |
| **Storage cap** | `value-storage-expansion-policy` v4.0.0 | 从所选 PSM 的物理调度与系统 excess trace 估算储能投资上限；当前为 VALUE aligned-utilisation 方法。 | 可靠性、容量信用、ELCC、市场收入或规划约束驱动的储能 headroom 模块。 |
| **Investment** | `agent-investment` v2.2.0 | 按经济所有者、技术和地区汇总收入/成本，执行四层投资与退役判断，并共享技术年度预算，避免一个 owner 因多行机组重复投资。 | 其他 agent 决策、风险偏好、融资约束、企业异质性或中央规划投资模块，符合 `value.investment/v2`。 |
| **Transition** | `value-annual-state-transition` v2.1.0 | 接受 planning admission 和 retirement，把资产、经济属性、owner、项目和储能状态带入下一年。 | 其他退役、寿命延长、退化、政策状态或跨年 checkpoint 规则，符合 `value.state-transition/v2`。 |

### 6.2 两种合法 PSM 组合 | Two valid PSM combinations

```text
A. VALUE offer-based market
value-bid-at-cost-psm
    + exactly one storage_cost module
    + pipeline + vre_cap + storage_cap + investment + transition

B. Perfect-foresight LP
value-perfect-foresight-lp
    + NO storage_cost module
    + pipeline + vre_cap + storage_cap + investment + transition
```

选择 perfect-foresight LP 后，Storage Cost 下拉框会消失，这是正确行为：储能已由 LP 中央联合优化，不能再叠加一套储能 bid tariff。
The Storage Cost selector disappears under perfect foresight because storage is centrally co-optimized; adding a separate offer rule would be internally inconsistent.

### 6.3 如何安装替换模块 | How replacement modules are installed

普通用户不再需要手工复制 Python 文件。开发者先把实现、manifest、许可证和说明构建为一个 `value.module-bundle/v1` ZIP；使用者再打开 **Modules → Install a model module**：

1. 选择 `.zip` 模块包（上限 25 MiB）；
2. 阅读并勾选“这是可信来源的可执行 Python”确认；
3. 点击 **Install and validate module**；
4. 等待文件清单、SHA-256、路径安全、manifest、entry point 和 conformance 检查；
5. 成功后转到 **Studies**，在对应槽位选择新模块并保存新的 Study revision；
6. 先跑 two-period wiring check，再决定是否进行完整年度研究。

Non-programming users now install a modeller-prepared ZIP from **Modules**. VALUE verifies the bundle inventory, hashes, path safety, manifest, entry point and public callable contract before adding it to the Study selectors. A successful conformance check proves wiring and callable shape; it does not prove the scientific method.

开发者可以复制 [`examples/external_module_bundle`](examples/external_module_bundle/README.md)，然后运行：

```powershell
py -3.10 scripts\build_module_bundle.py `
  --manifest my-module\value-module.json `
  --source-root my-module\src `
  --license my-module\LICENSE `
  --readme my-module\README.md `
  --output my-module.zip
```

第一版安装器只接受自包含 Python 源码，不联网下载依赖、不运行 `pip`、不接受原生二进制，也不覆盖内置 VALUE ID。安装包按模块 ID/版本隔离存放，但代码仍在本地 VALUE Python 进程内执行；它不是操作系统安全沙箱。已被 Saved Study 引用的模块不能直接禁用。底层手工安装路径仍保留给开发调试，详见 [`examples/external_modules`](examples/external_modules/README.md)。

The first installer is deliberately offline and self-contained: it does not run `pip`, download dependencies, accept native binaries or shadow built-in IDs. Packages are version-scoped on disk but execute in the VALUE Python process; this is not an operating-system sandbox.

---

## 7. Studies：所有选项说明 | Every Study option

### 7.1 Study details | 基本信息

| 字段 | 作用 | 使用建议 |
|---|---|---|
| **Name** | 人类可读名称；系统另生成稳定 project ID。 | 名称写清实验变量，如 `Dynamic storage recovery 2025–2034`。 |
| **First model year** | 第一个执行年份。 | 当前 UK baseline 从 2025 开始。 |
| **Final model year** | 最后一个执行年份；包含该年。 | 2025–2034 表示十个完整年份。 |
| **Data pack** | 该 Study 绑定的数据清单。 | 明早选择 `VALUE UK — 1000 TWh verified data`。空白 research pack 不能运行。 |

### 7.2 Model chain 下拉框 | Model-chain selectors

| 下拉框 | 当前可选项 | 应如何选择 |
|---|---|---|
| **Psm** | `VALUE live bid-at-cost PSM · 5.1.0`；`Perfect-foresight co-optimization · 1.0.0` | 研究 agent bid-at-cost 与储能竞争用前者；研究中央最优调度 benchmark 用后者。二者不是同一种信息结构。 |
| **Storage Cost** | Dynamic annual-average；VALUE retained tariff；User arithmetic formula | 只在 `value-bid-at-cost-psm` 下出现。dynamic 是论文型研究情景；legacy 用于历史复现；user formula 用于受限自定义敏感性。 |
| **Pipeline** | `Planning pipeline · 2.2.0` | 当前仅一项。它不是写死在 PSM 中，而是当前唯一已安装、通过测试的 planning implementation。 |
| **Vre Cap** | `Solar / wind expansion policy · 2.0.0` | 控制 annual VRE headroom；可由同 contract 的地区/供应链模块替换。 |
| **Storage Cap** | `Storage expansion policy — VALUE · 4.0.0` | 控制 annual storage headroom；不是储能 bid price。 |
| **Investment** | `Agent investment logic · 2.2.0` | 决定经济所有者是否投资/退役；与 planning 是否最终成功是两个阶段。 |
| **Transition** | `VALUE annual state transition · 2.1.0` | 把本年投产、退役和储能状态可靠注入下一年。 |

分区再调度还会出现一个必选的 **Demand authority / 需求权威**：

- `scenario_scaled_zonal_shares`（推荐）：全国实际与预测需求来自研究数据包，
  已签名网络包只提供每期分区份额。只有这种模式可与同输入铜板 run 做受控的
  network-cost attribution。
- `network_pack_absolute_demand`：分区和全国需求都来自网络包，是独立区域需求
  研究。界面仍可并排比较，但不会把它相对情景需求铜板 run 的全部差异称为
  “网络成本”。

The current GB benchmark freezes 2024 DESNZ postcode-derived zonal weights.
Future packs may provide time- or year-varying shares, but must keep exact period
alignment, declared units and per-period national reconciliation. An old saved
zonal Study with no declared mode is intentionally blocked until the user saves
a new explicit revision.

每个模型年的实际顺序是：

```text
planning advance / 本年到期项目投产
    → selected PSM 使用本年 operating fleet 出清
    → VRE 与 storage expansion headroom
    → agent investment
    → planning admission / failure / deferral
    → annual state transition 形成下一年状态
```

The planning step before the PSM commissions projects already due in the current year. New investment proposals created after that year's PSM enter the pipeline and can affect only a later operating fleet; they are not retroactively dispatched in the year in which they were proposed.

**重要：** 当前某些槽位只有一个下拉选项，表示“目前只安装了一项合格实现”，不表示架构不能替换。
A single visible option means that only one conforming implementation is currently installed; the slot itself remains replaceable.

### 7.3 Advanced assumptions：界面中每个可编辑项 | Every visible advanced setting

点击 **Advanced assumptions** 展开。点击 **Check effective values** 后，右侧 badge 会说明值来自 Module default、Data Pack-derived、Runtime default 还是 Overridden。只修改与实验问题有关的项；无关模块拥有的参数保持默认。

#### Planning

| 参数 | 默认/可选 | 实际含义 |
|---|---|---|
| `planning.success_mode` | `expected`; 可选 `stochastic`, `expected_capacity`, `seeded_stochastic` | `expected`/`expected_capacity` 用成功率形成预期容量；`stochastic`/`seeded_stochastic` 用种子抽样项目成败。两个后缀值是兼容别名。 |
| `planning.random_seed` | 0；0–2,147,483,647 | 随机规划成功的可复现种子；expected 模式下不驱动抽样。 |
| `planning.include_uncertain_projects` | true | 是否保留完成时间不确定的 REPD 项目。 |
| `planning.zombie_filter_enabled` | true；可由 data pack 提供 | 是否过滤终止、长期停滞或严重超过计划的项目。 |
| `planning.zombie_status_stale_year` | 2015；1990–2100 | 项目最后状态更新早于该阈值时可能被判为 stale。 |
| `planning.construction_grace_years` | 2；0–20年 | 超过计划建设时长后额外允许的宽限年数。 |
| `planning.minimum_project_size_mw` | 1 MW；0–10,000 | 小于该规模的 REPD 项目不进入规划池。 |
| `planning.max_completion_year` | 2040；2025–2200 | 晚于该年的源项目不进入当前研究范围。 |
| `planning.timeline_statistic` | `median`; 可选 `mean` | 使用平均还是中位规划/建设时间。 |
| `planning.defer_spread_years` | 3；0–20年 | 对起始年被延期的项目确定性分散到多少年。 |
| `planning.repd_battery_assignment` | `scheme_c_proportional_split` | 当 REPD 只写 Battery、没有时长时，按比例分给固定 C-rate；也可全部分到 `1c`, `0.5c`, `0.25c`，或 `exclude_untyped`。 |

#### Expansion

| 参数 | 默认/可选 | 实际含义 |
|---|---|---|
| `expansion.vre_cap_fraction` | 0.20；0–1 | 每年允许 agents 使用的太阳能/风电计算 headroom 比例。 |
| `expansion.storage_cap_fraction` | 0.20；0–1；可由 data pack 提供 | 每年允许使用的储能计算 headroom 比例。 |
| `expansion.storage_credit_method` | 仅 `scheme_c` | 当前储能 capacity-credit 处理方式；因尚无第二个经过验证的实现，改变它没有其他合法值。 |

#### Storage cost

| 参数 | 默认/可选 | 实际含义 |
|---|---|---|
| `storage.cost.discount_rate` | 0.05；0–1 | dynamic/user-formula 方法将 CAPEX 年化时采用的实际贴现率。只对相关 storage-cost 模块生效。 |
| `storage.cost.utilisation_floor_fraction` | 0；0–1 | 后续年度分母相对“满负荷设计售电量”的下限。第一年总是按满负荷初始化；0 表示不加额外 floor。 |
| `storage.cost.custom_formula` | `cycle_depreciation_gbp_per_mwh + dwell_periods * holding_recovery_gbp_per_mwh_period` | 仅 `user-formula-storage-cost` 生效。只允许批准变量和算术，不运行任意代码。 |

#### Market experiment

| 参数 | 默认/可选 | 实际含义 |
|---|---|---|
| `market.bid_multiplier` | 1.0；0.01–10 | `value-bid-at-cost-psm` 的成本报价乘数。只有 1.0 才是严格 bid-at-cost；其他值是明确的实验性 markup/markdown。 |
| `market.perfect_foresight_terminal_soc_rule` | `cyclic`; 可选 `fixed`, `free` | 只对 perfect-foresight LP 生效。`cyclic` 使终点 SOC 回到初点；`fixed` 使用声明终值；`free` 不强制终点。 |
| `market.voll_gbp_per_mwh` | 10,000 GBP/MWh；0–1,000,000 | perfect-foresight LP 对未服务需求采用的 Value of Lost Load。 |

#### Output/runtime

这些设置控制文件和运行方式，正常情况下不改变科学情景，但会显著改变磁盘占用。

| 参数 | 默认/可选 | 实际含义 |
|---|---|---|
| `runtime.checkpoint_enabled` | true | 每年保存可验证恢复点。建议长跑保持开启。 |
| `runtime.market_trace_level` | `summary`; `off/summary/full` | `full` 才保存每期每笔 bid/order；文件最大。`summary` 保存逐期汇总；`off` 最小。 |
| `runtime.market_balance_diagnostic` | false | 输出冗长的逐期平衡组成诊断；只在排错时开启。 |
| `runtime.market_export_format` | `sqlite`; `sqlite/parquet` | SQLite 是规范账本；Parquet 是可选 post-run 导出。 |
| `runtime.generation_trace_level` | `off`; `off/summary/full` | 控制机组发电轨迹输出量。 |
| `runtime.console_verbosity` | `normal`; `quiet/normal/debug` | 只控制日志详细程度。 |
| `runtime.artifact_batch_size` | 500；1–100,000 rows | SQLite/证据写入批大小；过小变慢，过大增加内存。当前长跑曾使用 2,000。 |
| `runtime.ensemble_max_parallel_children` | 1；1–16 | 显式 ensemble 的最大并行子运行数；普通单情景不受影响。 |

### 7.4 注册表中存在、但当前 Studies 页面没有暴露的设置 | Registered but not currently exposed in Studies

这是当前前端缺口，手册不把它们冒充成可点击下拉框：

| 参数 | 当前默认 | 说明 |
|---|---|---|
| `scenario.id` | `existing_decarb_base` | 另有 `subsidy_as_usual`, `government_target`，但当前页面没有 Scenario selector。旧项目 JSON 可以已经保存该值。 |
| `carbon.factor_scenario` | `value_current_authoritative_v1` | 另有 `scheme_c_reproduction_2026_07_18`；当前页面没有 carbon scenario selector。 |
| `terminal.policy` | `report_only` | Advanced Review 可选 `pipeline_tail` 或 `full_extension`，并由 preflight 冻结。 |
| `fleet.valuation_discount_rate` | 0.05 | 只影响信息性剩余资本价值，不进入 dispatch 或 system cost；当前页面没有该输入。 |

在明早演示中可以说这些已进入 typed registry，但仍需在前端补齐显式控件。不要现场手改 `project.json`。
These values exist in the typed registry but still need explicit UI controls. Do not edit project JSON by hand during the demonstration.

### 7.5 固定且不可编辑的模型身份 | Fixed model-card assumptions

- 单一 GB node；无英国内部传输约束。
  One GB node with no internal transmission constraints.
- interconnectors 是边界进口 offers。
  Interconnectors are boundary import offers.
- 正常 period = 0.5 h；完整年 = 17,520 periods。
  Normal period length is 0.5 h; a full year contains 17,520 periods.
- `value-bid-at-cost-psm` 是 continuous bid-at-cost，不含 commitment、ramp、minimum output。
  Continuous bid-at-cost dispatch without commitment, ramping or minimum output.
- virtual storage pool 的 1e9 MW / 1e9 MWh 是非约束诊断 sentinel，不代表英国真实储能容量。
  The 1e9 MW/MWh virtual pool is a non-binding diagnostic sentinel.
- 历史科学数值记录使用 Python 3.10；当前 Full 使用包内私有解释器。
  Historical scientific records use Python 3.10; Full uses its private interpreter.

### 7.6 右侧 Saved studies 是什么 | What the Saved studies list means

Saved study 是配置，不是数据库管理器，也不保证已经有科学可用的完成结果。点击一项会去 Runs 查看与它相关的运行。

| 当前名称 | 用途 | 明早是否建议展示 |
|---|---|---:|
| **Dynamic storage recovery 2025–2034** | 1000 TWh pack + bid-at-cost PSM + dynamic storage recovery 的十年情景。 | **是**；与 legacy 对照。 |
| **VALUE legacy storage tariff 2025–2034** | 同一数据/年份/非储能模块，只把 storage pricing 换成 legacy tariff。 | **是**；受控对照。 |
| **VALUE one-year full test** | 一年完整运行回归配置。 | 可简要说明；不是主结果。 |
| **VALUE ten-year full test** | 早期通用十年配置。 | 不如上述两个命名明确。 |
| **VALUE UK transition** | 通用 UK 2025–2034 配置。 | 可用于讲模块链，不作为特定结论名称。 |
| **VALUE UK 1000TWh verified** | 早期数据包验证配置。 | 可说明 provenance；不必当主情景。 |
| **Prompt 08 audit fixture** | 开发测试 fixture，开启 full market trace。 | **不建议**作为科学演示情景。 |

---

## 8. Runs：如何运行和比较 | Running and comparing studies

### 8.1 正确的运行顺序 | Correct launch sequence

1. 在 **Study** 下拉框选择已保存配置。先核对年份、data pack 和 annual sequence。
   Select a saved Study and verify its years, data pack and annual sequence.
2. 在 **Check for** 选择准备运行的规模，然后点 **Check readiness**。preflight 会检查 Python、模块组合、25 项数据、参数、磁盘空间和输出规模。
   Choose the intended scale and run **Check readiness** first.
3. 只有 preflight 显示 **Ready** 后再启动。长跑时保持命令窗口打开；关闭浏览器页面不会停止后台模型。
   Start only after a Ready result. Closing the browser does not stop the background process.

### 8.2 四种运行规模 | Four run modes

| 前端选项 | 实际工作量 | 用途 | 能否解释年度成本/投资 |
|---|---:|---|---:|
| **Two-period wiring check** | 一个模型年、2 个半小时 period | 检查 data → PSM → CEM 的函数调用和基本守恒。 | **不能** |
| **Two-year hand-off check** | 两个模型年、每年 2 个 period | 检查第一年 PSM 后的投资、pipeline、state transition 是否进入第二年。 | **不能** |
| **Two full model years** | 2025、2026 各 17,520 periods | 第一项能检验完整年度经济与跨年资产注入的实用测试。 | **能**，通过账本审计后 |
| **Complete study** | Study 中每年 17,520 periods | 正式一年至十年研究运行。 | **能**，通过账本与科学门槛后 |

Smoke results deliberately withhold annual economics. Two periods can prove wiring and conservation, but cannot estimate an annual load factor, project recovery or system cost.

### 8.3 运行中的按钮 | Run lifecycle controls

| 按钮 | 作用 | 注意 |
|---|---|---|
| **Request safe cancellation** | 请求在下一个安全边界停止。 | 不是强杀进程；已经完成的年度 checkpoint 会保留。 |
| **Resume from verified annual checkpoint** | 从身份、hash 和状态都通过校验的最近年度断点恢复。 | 只对 failed/cancelled run 出现；不会从半写入状态恢复。 |
| **Archive** / **Restore archive** | 把不常用 run 移到归档状态，或恢复到原状态。 | 不删除结果。 |
| **Prepare audit bundle** | 生成带 manifest、hash 和结果工件的可移植 ZIP。 | 用于交给导师、审稿或另一台受信任电脑验证。 |
| **Move to trash** | 输入完整 run ID 后移入可恢复的本地 trash。 | 不是立即永久删除。 |

### 8.4 年度结果怎么读 | Reading annual results

| 指标 | VALUE 中的口径 |
|---|---|
| **Total system cost** | `value.cem-system-resource-cost/v1`：投产 fleet 的年化 CAPEX/FOM + 物理 operating cost。market settlement、policy transfer、未投产 pipeline commitment 和信息性 residual value 均不计入，避免把转移支付重复算成资源成本。 |
| **Average system cost** | 上述年度 system cost ÷ 实际 served demand，单位 GBP/MWh served。 |
| **Annualised capital** | 投产资产按 CAPEX、经济寿命与折现参数年化后的资源成本，不是当年现金购买额。 |
| **Operating cost** | 实际发电、进口及模型声明的可变运行成本；只看两期 smoke 时不应把缩放显示当年度科学结果。 |
| **Unserved demand** | 未满足需求，MWh；其惩罚取决于相关 PSM/VOLL 口径。 |
| **Imports** | 五个边界市场被接受的进口电量，不是英国内部线路流量。 |
| **Storage charge / discharge** | 本年储能实际充、放电能量；同时展开 capacity 可看 MW 与 MWh。 |
| **VRE curtailment** | 可用但未被系统接受的 VRE 电量。 |
| **Total carbon** | 只有选定 factor scenario 的边界、单位和账本都可对齐时才给 tCO2e；否则应显示 **Not evaluated**，不能把未知值显示成 0。 |
| **Planning pipeline** | active、commissioned、failed、filtered、deferred 项目数量与 MW；进一步原因在 Inspect。 |

Dashboard 另列 **Capacity mechanism** 和 **Decarbonisation policy**，用于查看机制/政策账户；它们不是 headline CEM resource-cost 的额外加数。需要解释消费者支付或政策预算时，应引用相应独立 ledger，而不是把它们手工加回 Total system cost。

### 8.5 跨情景比较 | Scenario comparison

- 只能选择 **2–6 个已完成的年度 run**；smoke 被有意排除。
  Select two to six completed annual runs; smoke diagnostics are excluded.
- 页面会列出 changed dimensions。只有数据、年份、非目标模块和定义一致时，dynamic 与 legacy 的差值才可解释为干净的 storage-pricing 对照。
  Review changed dimensions before making a causal claim.
- 如果 system-cost 或 carbon 的 definition ID、单位、分母不同，VALUE 会阻止或不标注数值 delta。
  Deltas are withheld when metric identities differ.
- 可导出 CSV 或 JSON；导出的是比较结果，不会修改原 run。
  Comparison exports never mutate the underlying runs.

### 8.6 Market replay：竞价和最终发电时序 | Bids and final dispatch

先在 **Runs** 选中一个 run，再打开左栏 **Market replay**。上半页读取
`market.sqlite` 的最终物理层，把每一期真正送入系统的风、光、核电、火电、
水电、边界进口和储能放电按技术拼成连续发电图；需求以线显示。它不会把
ahead、curtailment、balancing 三个阶段的 accepted orders 相加，因为那会重复
计算同一度电。

Select a run in **Runs**, then open **Market replay**. The chronological chart
uses the final physical-dispatch table, not a sum of stage transactions. Choose
daily or weekly overview, or load a bounded half-hour slice. Click a bar or enter
its period number to inspect that period.

如果该 run 是 `full` trace，页面下半部会读取**出清前声明的输入**与对应 outcome，
按实际的“报价升序、同价保持输入顺序”画 merit order，并列出 offered/accepted MWh、
报价、asset 和证据粒度。储能有多个 tranche 而 outcome 只给 asset 合计时，页面会
明确写 `asset aggregate`，不会把合计量随意分配到某个 tranche。`summary` trace
仍可看最终发电时序，但没有逐单 replay；perfect-foresight LP 只显示调度与 dual
price，不伪造 sequential auction。

### 8.7 VRE & curtailment：到底弃了多少电 | How much renewable energy was unused

左栏 **VRE & curtailment** 给出每年的：

- `Available VRE`：该期天气与装机允许产生的 VRE；
- `Accepted VRE`：被 PSM 接受的 VRE；
- `Unused VRE = Available − Accepted`：共同物理边界上的中性弃电总量；
- `Pre-balancing excess`：实时平衡前已经形成的过剩。VALUE 中它可能还含核电或
  径流水电，所以界面写 `inflexible mixed`，不会冒充纯 VRE；
- `Balancing curtailment`：预测与实际需求偏差后，在储能、出口和灵活负荷之后仍被
  削减的量；
- `Marginal curtailment`：新增一小单位容量的边际实验。普通年度 run 没有这种工件时
  必须显示 `Not evaluated`。

The annual bars follow the thesis accounting logic: available VRE is split into
accepted and neutral unused VRE. Pre-balancing excess is shown alongside that
identity when it has mixed inflexible composition; it is not added to unused VRE
a second time. The selected-year timeline, affected periods, longest event and
peak event all come from the same half-hour ledger. Storage charging, exports and
flexible demand are shown as simultaneous system flows unless the ledger proves
their source MWh.

两期 smoke 只能检查接线，页面会标成 `Diagnostic chronology`，不得把两期数值称为
年度弃电率。

---

## 9. Inspect：查看什么 | What Inspect shows

先在 Runs 选择一个 run，再进入 Inspect。这里采用按需加载，避免把数十万行账本一次塞进主运行页面。

### 9.1 Planning

- **Planning projects**：按名称、ID、技术、地区搜索，并按 active、commissioned、failed planning、filtered、outside scope 筛选。
  Search durable projects and filter by outcome.
- 每行显示 project ID/name、technology、development stage、region、capacity MW、expected completion year、outcome 与 reason code。
  Each row preserves capacity, expected completion and exclusion/failure reason.
- **Lifecycle events** 按 sequence 显示某项目在哪一年从哪个阶段变到哪个阶段，以及触发原因。
  Lifecycle events explain how and why the pipeline evolved.

因此 Planning 不是一张装饰图，而是回答“多少项目仍在规划、在哪里、何时预计投产、多少失败、为什么失败”的审计入口。

### 9.2 Market

- 默认每页读取 50 个 clearing periods；每期显示 real demand、accepted supply、clearing price 和 energy-balance residual。
  The period ledger is paged in blocks of 50.
- 如果复制的 VALUE settlement 没把某些 secondary allocations 暴露成 asset dispatch row，页面会把 **raw residual** 与 **compatibility adjustment** 分开显示，不会把差额伪装成发电或 blackout。
  Compatibility adjustments remain explicitly labelled.
- 只有 Study 中 `runtime.market_trace_level = full` 时，才能看到逐 asset 的 side、offer price、offered MWh、accepted MWh、status 和 reason code。
  Individual orders require full trace.
- `summary` 下看不到 individual orders，只表示当次没有保存明细，**不表示市场没有 bidding**。
  Missing order rows under summary trace do not mean that no bidding occurred.

### 9.3 Artifacts & provenance

- **Artifacts**：下载年度结果、cost/carbon ledgers、planning index、market SQLite/Parquet、checkpoints、validation 和其他本地证据。
  Download the files produced by the selected run.
- **Provenance**：查看 run ID、Study revision/hash、data-pack identity、module identities/hashes、Python/runtime 与其他 resolved execution identity。
  Provenance records exactly which inputs and executable implementations ran.

---

## 10. Add data：目前能做什么 | What Add data currently does

### 10.1 它是什么 | What it is

Add data 是**适配器开发指南**，说明把某个外部数据库转换到 25 个稳定 semantic roles 的四个步骤：描述 pack、映射 role、统一单位/时间、验证 contract。它不是已经完成的无代码 ETL 向导。

Add data is an adapter guide, not a complete no-code importer. The current page documents the boundary between source-specific data and stable VALUE contracts.

### 10.2 目前两条可用路径 | Two practical paths today

**路径 A：数据已经符合第 5 节 schema。** 在 Data 页选择空的 **VALUE UK research data** pack，逐项 Choose file/Replace，直到 25/25，再保存 Study revision。
**Path A:** Upload already-canonical files through Data and save a new Study revision.

**路径 B：原始数据库列名、单位或技术编码不同。** 先使用 `value.data-adapter/v1` 适配器或外部预处理脚本，将源文件变成第 5 节的 canonical files，再导入。当前内置适配器只提供明确的 **CSV → CSV** 列映射、已声明单位换算、技术映射和 timezone metadata；Excel、NetCDF API、SQL 或任意 Parquet/Zarr 转换仍需专用 adapter。
**Path B:** Normalize the source with a reviewed adapter before upload. The built-in executable adapter is currently limited to explicit CSV-to-CSV normalization.

### 10.3 新国家/新数据库的最小 manifest | Minimal pack identity

```yaml
data_pack: my-country-2030
country: XX
timezone: Region/City
licence: state-the-source-licence
bindings:
  demand.real:
    source: demand.csv
    column: observed_mwh
    unit: MWh/period
  projects.repd:
    source: projects.csv
    mapping:
      project_id: source_id
      capacity_mw: size_mw
      technology: tech_code
```

真正接入时还必须为所有当前 required roles 提供 binding、来源版本、SHA-256、转换代码版本、单位、时区和再分发类别。manifest 只描述数据身份；它不会执行隐式转换。

A manifest records identity and lineage. It does not perform hidden conversion.

---

## 11. VALUE 到底是什么 | What VALUE actually is

**VALUE 不是第三套电力模型，也不是一个“调用旧脚本”的假前端。** 它是 VALUE 的本地工作台和应用服务层，负责五件事：

1. 注册 data packs、modules 和 typed parameters；
2. 把数据、模块、年份和参数冻结成版本化 Study revision；
3. 做 preflight，并调用同一套 Python application service 启动真实 PSM–CEM chain；
4. 管理后台 run、checkpoint、archive、trash 和 exports；
5. 通过浏览器读取年度结果与细粒度审计证据。

VALUE is the local workbench and application-service layer around VALUE. It registers inputs and modules, freezes reproducible Study revisions, launches the real annual model chain, manages run lifecycle and exposes audit evidence.

### 11.1 Study 是否“管理”导入的数据和模块 | Does a Study own the imported data and modules?

不是。三个对象是分开的：

```text
Data pack ── files + role bindings + hashes + provenance
Module registry ── executable IDs + versions + contracts + hashes
Study revision ── references one data pack and one module per slot
                         + years + parameter overrides
                                      │
                                      ▼
Run ── frozen resolved snapshot + outputs + checkpoints + audit files
```

- **Data pack** 管文件和来源；同一个 pack 可被多个 Studies 使用。
  A data pack owns file bindings and provenance and can be reused.
- **Module registry** 管可执行实现；Study 只选择 module ID，不复制其源码。
  The registry owns executable identities; the Study selects them.
- **Study revision** 管“这一次研究问题的组合”，不搬运或改写数据库。修改数据、模块、年份或参数后应保存新 revision。
  A Study revision freezes a configuration, not the source files themselves.
- **Run** 再把已解析的 data/module hashes 和结果一起冻结，保证以后知道“当时究竟跑了什么”。
  A Run freezes the resolved execution identity and evidence.

### 11.2 本地文件保存在哪里 | Where local state is stored

| 环境 | 默认位置 | 主要内容 |
|---|---|---|
| 当前源码工作区 | 项目根目录的 `.gridform/` | `data-packs`, `projects`, `runs`, `modules`, archives/trash 与 registry state |
| 以后干净安装 | `%LOCALAPPDATA%\VALUE` | 与上面相同的用户本地状态，不与程序安装目录混在一起 |
| 自定义 | 环境变量 `VALUE_DATA_HOME` 指向的绝对路径 | 便于把大数据和长跑结果放到容量更大的磁盘 |

这些目录是本地模型状态，不应整目录提交 Git。公开源码、可再分发 synthetic pack 和受权利约束的 UK data pack 应作为不同发布产品管理。

---

## 12. 四个常用工作流 | Four common workflows

### 12.1 新建一个可运行研究 | Create a runnable Study

1. 在 Data 选择 **VALUE UK — 1000 TWh verified data**，确认 25/25。
2. 在 Modules 先确认所有选中实现为 Ready。
3. 在 Studies 输入名称和年份；选择 PSM、storage pricing、pipeline、caps、investment、transition。
4. 只修改与研究问题有关的 Advanced assumptions，点 **Check effective values**。
5. 点 **Save study and continue to runs**。这会创建不可混淆的 revision。
6. 在 Runs 做相应规模的 **Check readiness**，再启动。

### 12.2 动态储能成本与 legacy tariff 做受控比较 | Controlled storage-pricing comparison

1. 选择同一 data pack、年份和 `value-bid-at-cost-psm`。
2. 建立 Study A，Storage Cost 选 `dynamic-annual-storage-cost`。
3. 在 Runs 展开 **Clone a storage-pricing experiment**，克隆成 Study B，只改为 `value-legacy-storage-tariff`。
4. 两个 Study 采用相同非储能模块和相同参数分别运行。
5. 在 Scenario comparison 同时勾选二者；确认 `clean_storage_policy_comparison=true` 或页面未报告其他 changed dimensions，再解释差异。

This workflow changes one causal dimension only: the storage offer-cost rule.

### 12.3 用 perfect-foresight LP 做调度基准 | Use the perfect-foresight dispatch benchmark

1. 克隆 Study，并把 PSM 改为 `value-perfect-foresight-lp`。
2. Storage Cost 槽位会自动消失。不要把这称为另一种 storage tariff；它是信息结构不同的中央联合优化。
3. 根据研究问题选择 terminal SOC rule，并做 24/168 小时或完整年度测试。
4. 比较时明确：VALUE bid-at-cost agents 与 perfect foresight LP 的差异可能来自信息结构，不一定是程序错误。

### 12.4 接入新的数据库或模块 | Connect new data or a new module

完整路线见 [`基于 VALUE 构建你自己的模型 101`](docs/BUILD_YOUR_OWN_MODEL_101_ZH.md)
和 [`English guide`](docs/BUILD_YOUR_OWN_MODEL_101.md)。总结构是一套数据底座加三种
不同深度的替换/升级：

- **换数据底座：** 把源表通过 adapter 映射到第 5 节 role；校验后保存新 Study revision。
- **方式一——Study parameter：** 算法不变，只改变已注册的数值假设。
- **方式二——module：** 在七个现有 slot 内替换算法；可以换一个，也可以全部换掉。
- **方式三——platform contract：** 新增网络维度、跨年状态或生命周期阶段；先版本化升级 contract，再让该类算法成为可安装 module。

先稳定 adapter 输出，再单独验证参数或 module。不要让 source-specific 字段进入
PSM/CEM 内部，也不要把新维度藏在不相关的 slot 中。

The stable integration point is the public data/module contract, not a particular UK filename or retained VALUE global variable.

---

## 13. 当前版本能说什么、不能说什么 | Current claims and limits

### 13.1 可以如实说明 | Supported statements

- 当前版本是 **local, bounded research beta**；真实模块链已经通过完整一年、两年和成对十年运行，energy balance、cost ledger、checkpoint 与独立 PSM oracle 有现有测试证据。
  The local bounded beta has annual, two-year and paired ten-year execution evidence.
- `value-bid-at-cost-psm` 在声明的连续、无启停/爬坡约束条件下实行 bid-at-cost 资源竞争；储能、VRE、火电和边界进口在同一市场链中处理。
  The offer-based PSM implements competition under its declared simplified assumptions.
- CEM 的投资、caps、planning pipeline 和 next-year transition 是实际执行模块，不是前端静态数字。
  CEM stages are executable modules in the live annual chain.
- dynamic storage recovery 是已声明的研究方法；legacy tariff 是历史对照；perfect foresight LP 是另一种 dispatch formulation。
  These are distinct, selectable scientific formulations.

### 13.2 不能夸大 | Unsupported claims

- 默认英国基线没有内部节点/线路；interconnectors 只是边界进口。可选 reference
  DC 只代表合成/声明范围，不等于真实 GB network baseline。
- 实验性 AC 只检查给定计划的局部可行性，不是 AC OPF 或全局最优 dispatch。
- 当前 `value-bid-at-cost-psm` 没有完整 unit commitment、minimum up/down、ramping 或 reserves。
- agent-based multi-year CEM 没有被证明是全局最优容量扩张。
- VALUE-CEM 是 VALUE-derived 的公开模块化 formulation，不是保留 kernel 的逐行等同副本。保留 kernel 只用于单独 comparison command，不能在 Study 中选择。
- dynamic storage pricing 是可发表/研究的情景，不是已证明对所有系统唯一最优的默认方法。
- 本节历史科学运行记录来自 64-bit Windows + Python 3.10；当前 Full 的安装/短任务验收另见发行目标，不能由历史记录推导所有平台的科学复现。

### 13.3 前端仍有的具体缺口 | Remaining UI gaps

1. 条件 Data roles 已按 Study 动态显示，但真实 GB network/hydrology 数据包尚未验收。
2. natural-flow hydrology 的解析/科学 fixture 已存在；普通年度运行尚未稳定写出供
   Network & water 查询的 typed hydrology result index，因此该工作流为 `NO_GO`。
3. AC feasibility 与 transmission expansion 在 UI 可组合，但科学成熟度仍是
   `EXPERIMENTAL`，没有完整年度或十年英国网络基线。
4. Add data 仍是 adapter guide，不是任意来源的一键 no-code pack builder。
5. Data 页会区分 manifest 可接受格式与当前真正有 parser 的格式；没有 parser 的
   格式不会被显示为可运行。
6. Modules 页只安装经过 manifest、哈希、路径和 conformance 检查的 ZIP；它不会把
   任意上传文件直接当作代码执行，也不是操作系统安全沙箱。
7. DC/AC/perfect-foresight 需要可选 SciPy solver capability；历史源码默认单节点安装可能不含 SciPy；当前 Full 已包含锁定依赖，
   选择模块仍须通过 preflight。

### 13.4 许可边界 | Licence boundary

- 模型代码：Apache-2.0，允许科研、教学、商用及政府用途、修改和再分发；按许可保留适用声明并标明修改。
- 文档：CC BY 4.0。
- 三个已发布 synthetic example data 包：继续采用 CC0-1.0。
- 其他作者自有且有权授权的数据：按具体数据许可发布；包内许可和第三方条款优先。
- 本地 UK research data：按各原始来源的许可与再分发状态分别处理，软件换许可不会授予第三方数据的再分发权，也不撤销既有有效 Apache/CC0 授权。

详见 [`LICENSING.md`](LICENSING.md)、[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) 和 [`docs/VALIDATION_AND_CLAIMS.md`](docs/VALIDATION_AND_CLAIMS.md)。

---

## 14. 常见问题排查 | Troubleshooting

Full 用户先运行安装目录内的 diagnose 入口；下表 `py`/源码 doctor 命令只适用于自行配置环境的源码工作区。Full 环境有问题时采用新的空目录旁路安装，不覆盖旧安装或承诺自动迁移。
For Full, use the installed diagnostic launcher and a separate empty directory for reinstallation. Source doctor commands below require a developer environment.

| 现象 | 原因 | 处理 |
|---|---|---|
| `127.0.0.1 refused to connect` | 本地服务没启动、启动失败，或打开了错误端口。 | 双击 `start-value.cmd`；等待成功提示；打开 `http://127.0.0.1:8800`。仍失败时运行 `py -3.10 scripts\doctor.py --capability value-native`。 |
| 打开 `127.0.0.1:3000` 失败 | 3000 是开发地址；当前打包演示使用 8800。 | 改用 8800。 |
| 左下角显示 Python incompatible | 当前解释器不是被验证的 Python 3.10，或依赖缺失。 | Full 使用安装目录的 diagnose；需重装时旁路安装到新空目录。源码开发检查 doctor；不要强迫 Python 3.12 跑 retained comparison。 |
| **VALUE UK research data** 显示 0/25 | 这是空的导入工作区，不是坏掉的 1000 TWh pack。 | 演示请选择 verified pack；建新 pack 时按第 5 节导入全部接口。 |
| 上传后仍未 ready | 扩展名、必需列/JSON key、长度、NaN、范围或单位不符合 contract。 | 阅读该 role 的错误信息；对照第 5 节和 verified sample 修正；旧 binding 不会被失败上传覆盖。 |
| Storage Cost 下拉框消失 | 选择了 perfect-foresight LP；其储能由中央联合优化。 | 这是正确组合。若要比较 tariff，改回 `value-bid-at-cost-psm`。 |
| smoke 页面出现 `£0bn` operational cost 或奇怪的 GBP/MWh | 两期诊断没有年度经济资格，旧界面/旧 run 可能仍显示缩放卡片。 | 不解释该值；用新版诊断说明，正式经济结果至少跑完整一年。 |
| Inspect/Market 看不到逐 bid | `runtime.market_trace_level` 是 `summary` 或 `off`。 | 克隆 Study，把 trace level 改为 `full` 后重跑；会显著增加磁盘占用。 |
| 页面关了但模型还在跑 | run 是本机后台进程。 | 回到 Runs 查看；需要停止时用 safe cancellation，不要直接删目录。 |
| run 中断 | 断电、进程错误或手动取消。 | 若已完成一个年度，选择 **Resume from verified annual checkpoint**；先阅读 error code。 |
| Total carbon 显示 Not evaluated | 所选 factor scenario 中有边界/单位无法物理对齐，尤其 legacy storage scalar。 | 查看 carbon ledger 和 reason code；不要把 null 改成 0。 |
| Compare 不给 delta | 两个 run 的 cost/carbon definition、分母或其他关键维度不同。 | 查看 changed dimensions；建立真正的一变量克隆实验。 |

停止整个本地工作台可双击 [`stop-value.cmd`](stop-value.cmd)。它只停止本次 VALUE 安装记录的服务，不会删除数据或 run。

---

## 15. 明早可直接照读的英文介绍 | A short script for Stuart

> VALUE stands for Variable renewable electricity Allocation, Load-enabled excess-generation Utilisation, and system Evolution. The same local application combines executable PSM and CEM modules with the browser workbench that manages data packs, module selection, Study revisions, runs and audit evidence.
>
> A data pack maps local files to 25 stable interfaces. The verified 1000 TWh pack is the current runnable UK research scenario; the similarly named research pack is deliberately empty and is used as an import workspace. A Study does not copy those files. It freezes references to one data pack, one compatible module in each slot, the model years and explicit parameter overrides.
>
> The offer-based PSM clears VRE, thermal generation, storage and boundary imports through bid-at-cost competition. It is a single-node continuous formulation, so it does not claim internal GB transmission or full unit commitment. The CEM then applies investment, expansion caps and the planning pipeline, commissions eligible projects and injects them into the next year's fleet.
>
> Storage pricing is a replaceable component. The dynamic annual-recovery method and the retained legacy tariff can be compared while keeping all other dimensions fixed. A perfect-foresight LP is also available, but it is a different dispatch information structure rather than another tariff.
>
> Runs are auditable. We can inspect every planning project's stage and reason code, period-level market clearing, cost and carbon ledgers, module and data hashes, and verified checkpoints. The current build is a local bounded research beta. The main publication work left is fresh-clone reproducibility and the rights-governed distribution of UK data.

建议现场只展示三个证据：
Show only three pieces of evidence during the live demonstration:

1. Data 页 verified pack 的 **25/25**；
2. Studies 中 dynamic 与 legacy 的单变量差异；
3. 已完成十年 run 的年度结果，并在 Inspect 打开一个 planning project 和一个 market period。

不要在导师面前临时启动十年长跑；直接使用已有 completed run。若要证明前端真能执行，运行 **Two-period wiring check** 即可，并明确它不是年度科学结果。

---

## 16. 进一步阅读与技术依据 | Further reading

- [`README.md`](README.md)：版本状态、安装和最短启动说明。
- [`docs/BUILD_YOUR_OWN_MODEL_101_ZH.md`](docs/BUILD_YOUR_OWN_MODEL_101_ZH.md) /
  [`docs/BUILD_YOUR_OWN_MODEL_101.md`](docs/BUILD_YOUR_OWN_MODEL_101.md)：从换数据、
  参数、module 到平台 contract 升级的总教程。
- [`docs/MODULE_DEVELOPER_101_ZH.md`](docs/MODULE_DEVELOPER_101_ZH.md) /
  [`docs/MODULE_DEVELOPER_101.md`](docs/MODULE_DEVELOPER_101.md)：具体 module 的
  manifest、代码、ZIP 和测试流程。
- [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) / [`docs/USER_GUIDE_ZH.md`](docs/USER_GUIDE_ZH.md)：原有英文/中文技术使用指南。
- [`docs/MATHEMATICAL_REFERENCE.md`](docs/MATHEMATICAL_REFERENCE.md)：PSM、CEM、储能与账本数学定义。
- [`docs/generated/MODULES.md`](docs/generated/MODULES.md)：由 module manifests 生成的模块目录。
- [`docs/generated/PARAMETERS.md`](docs/generated/PARAMETERS.md)：typed parameter registry。
- [`docs/SCHEME_C_MODEL_CARD.md`](docs/SCHEME_C_MODEL_CARD.md)：系统边界与固定假设。
- [`docs/VALIDATION_AND_CLAIMS.md`](docs/VALIDATION_AND_CLAIMS.md)：哪些结论已有证据、哪些尚未验证。
- [`publication/prompt52-final-test-report.md`](publication/prompt52-final-test-report.md)：当前完整测试与十年运行报告。
- [`examples/external_modules/README.md`](examples/external_modules/README.md)：外部模块示例。
- [`docs/INSTALLATION.md`](docs/INSTALLATION.md)：安装、路径、Python/Node 与 clean-environment 说明。

如果界面和本手册有冲突，以 module manifest、typed parameter registry、data contract validator 和当前 run provenance 为最终事实来源；不要以截图或旧 run 名称猜测。

If the UI and this guide ever diverge, treat the executable manifests, typed registry, validators and run provenance as the source of truth.

---

## 17. Complete English reference for Stuart

This appendix restates the operational tables in English so that the guide can be read without the Chinese text.

### 17.1 All 25 Data interfaces

Use the **built-in format** column for the current shipped modules. Other extensions shown by the UI require a compatible adapter or replacement reader.

| # | Semantic role | What to provide | UI extensions | Built-in format and minimum contract |
|---:|---|---|---|---|
| 1 | `fleet.generators` | Existing generators, storage, interconnectors and locations | JSON | JSON with root keys `generators`, `batteries`, `connections`; use the verified fleet schema for technology, MW/MWh and economic fields. |
| 2 | `demand.forecast` | Forecast demand by market period | CSV, Parquet | CSV; at least 17,520 finite non-negative values; MWh/period; one header is allowed. |
| 3 | `demand.real` | Real/balancing demand by market period | CSV, Parquet | CSV; same chronology and unit as forecast demand. |
| 4 | `weather.wind` | Gridded wind used at asset locations | NetCDF, Zarr | NetCDF with `longitude`, `latitude` and either `wind_speed` or both `u100`, `v100`; supported 3-D or day/hour 4-D structure. |
| 5 | `weather.solar` | Gridded solar irradiation used at asset locations | NetCDF, Zarr | NetCDF with `longitude`, `latitude`, `ssrd`; supported 3-D or day/hour 4-D structure. |
| 6 | `market.france.profile` | Available imports from France | CSV | CSV, MWh/period; 17,520 values recommended. Short cyclic profiles repeat. |
| 7 | `market.france.price` | French boundary offer price | CSV | CSV, GBP/MWh, aligned with the availability profile. |
| 8 | `market.belgium.profile` | Available imports from Belgium | CSV | CSV, MWh/period; 17,520 values recommended. |
| 9 | `market.belgium.price` | Belgian boundary offer price | CSV | CSV, GBP/MWh; convert EUR at the adapter boundary. |
| 10 | `market.netherlands.profile` | Available imports from the Netherlands | CSV | CSV, MWh/period; 17,520 values recommended. |
| 11 | `market.netherlands.price` | Dutch boundary offer price | CSV | CSV, GBP/MWh. |
| 12 | `market.norway.profile` | Available imports from Norway | CSV | CSV, MWh/period; 17,520 values recommended. |
| 13 | `market.norway.price` | Norwegian boundary offer price | CSV | CSV, GBP/MWh. |
| 14 | `market.ireland.profile` | Available imports from Ireland | CSV | CSV, MWh/period; 17,520 values recommended. |
| 15 | `market.ireland.price` | Irish boundary offer price | CSV | CSV, GBP/MWh. |
| 16 | `profiles.vre_solar` | System-average solar capacity factor | CSV | CSV; one numeric column; all values 0–1; at least 8,760 hourly values. |
| 17 | `profiles.vre_onshore` | System-average onshore-wind capacity factor | CSV | CSV; one numeric column; all values 0–1; at least 8,760 hourly values. |
| 18 | `profiles.vre_offshore` | System-average offshore-wind capacity factor | CSV | CSV; one numeric column; all values 0–1; at least 8,760 hourly values. |
| 19 | `projects.repd` | Normalized planning pipeline | CSV, Parquet | CSV with unique `project_id` plus `technology`, `capacity_mw`, `development_status`, `region`; capacity finite and non-negative. |
| 20 | `source.repd_raw` | Unaltered UK REPD evidence | CSV | CSV retaining at least `Ref ID`, `Site Name`, `Technology Type`, `Installed Capacity (MWelec)`, `Development Status`. |
| 21 | `costs.capital` | Technology CAPEX and capital assumptions | CSV, JSON | JSON with root key `capital_costs_per_mw`; values on a declared GBP/MW and currency-year basis. |
| 22 | `policy.support` | Capacity/security/balancing and decarbonisation budgets | CSV, JSON, XLSX | XLSX `Sheet1` with `Delivery Year`, `Security Budget (£mn)`, `Decarbonization Budget (£mn)`; additional breakdown columns may remain. |
| 23 | `planning.timelines` | Technology and development-stage duration evidence | CSV, JSON | JSON with `development_stage_timelines`; follow the verified example for `development_timelines`, status mapping and month units. |
| 24 | `planning.success_rates` | Technology-by-region project success rates | CSV, JSON | CSV with `Technology`, `Region`, `Success_Rate`; use probabilities from 0 to 1. |
| 25 | `config.model_parameters` | Structured simulation, investment and compatibility parameters | JSON | JSON with root keys `simulation_parameters`, `investment_parameters`; retain documented nested names such as `repd_filtering`. |

The five interconnector profile/price pairs are external boundary offers. They are not internal transmission lines. Upload validation hashes and copies a candidate into local managed storage; a failed candidate does not replace the previous valid binding.

### 17.2 All currently shipped Modules

| Slot | Module ID and version | Scientific purpose | Valid replacement class |
|---|---|---|---|
| PSM | `value-bid-at-cost-psm` 5.1.0 | Single-node continuous bid-at-cost competition between VRE, thermal generation, boundary imports and storage offers. No commitment, ramping or internal network. | Any `value.psm/v2` implementation: DC/AC network, UC/MILP, alternative clearing or ABM, provided it emits the standard annual and period results. |
| PSM | `value-perfect-foresight-lp` 1.0.0 | Single-node chronological SciPy/HiGHS LP with central storage SOC, power, energy and efficiency co-optimization. | Another LP/MILP/network optimizer conforming to `value.psm/v2`; declare central storage co-optimization where applicable. |
| PSM | `value-reference-dc-network` 1.0.0 | Chronological linear DC network PSM with nodal balance, angles, finite branch ratings, congestion, nodal prices and storage. Ready only in its declared reference scope. | Another `value.psm/v2` network solver composed with the network-contract extension. |
| PSM | `value-reference-ac-feasibility` 0.1.0 | Experimental local AC feasibility of a declared active schedule, including P/Q, voltage and real losses. It is not AC OPF. | Another PSM with explicit convergence and optimality claims; feasibility must not be presented as economic optimality. |
| Network expansion | `reference-transmission-expansion` 1.0.0 | Experimental candidate-to-commissioning lifecycle with causal next-year injection into DC clearing. | Another `value.network-expansion/v1` policy/lifecycle module. |
| Storage cost | `dynamic-annual-storage-cost` 1.0.0 | Full-utilization first-year recovery; later years allocate annualized project recovery using prior-year sold energy and sales-weighted dwell. Cycle depreciation applies to batteries only. | Another transparent offer-cost, recovery or degradation rule under `value.storage-cost/v1`. |
| Storage cost | `value-legacy-storage-tariff` 1.0.0 | Retains the fixed plus dwell-dependent VALUE tariff for historical comparison. | A different documented legacy/reproduction tariff; not a general default without evidence. |
| Storage cost | `user-formula-storage-cost` 1.0.0 | Evaluates safe arithmetic over approved cost variables; it does not execute arbitrary Python. | Another approved expression, or a reviewed module for more complex logic. |
| Pipeline | `planning-pipeline` 2.2.0 | Advances, defers, filters, fails and commissions projects using declared timelines, probabilities and reasons. | Country-specific permitting, connection queue, hydrology/site or stochastic planning under `value.planning/v2`. |
| VRE cap | `vre-expansion-cap` 2.0.0 | Sets shared annual solar/onshore/offshore expansion headroom. | Land, supply-chain, connection, target or regional expansion policies under `value.expansion-policy/v2`. |
| Storage cap | `value-storage-expansion-policy` 4.0.0 | Uses physical dispatch and excess-energy evidence to set annual storage investment headroom. | ELCC, adequacy, revenue or planning-constraint storage headroom logic. |
| Investment | `agent-investment` 2.2.0 | Aggregates economics once per owner/technology/region, then applies investment and retirement logic under shared budgets. | Alternative agent finance, risk, ownership heterogeneity or central-planning investment under `value.investment/v2`. |
| Transition | `value-annual-state-transition` 2.1.0 | Carries commissioned/retired assets, economic identity and storage state into the next model year. | Alternative retirement, degradation, lifetime-extension or cross-year state logic under `value.state-transition/v2`. |

A replacement is installed as an importable Python implementation plus a `value.module/v2` manifest, must pass conformance, and appears in the browser only after registration and restart. The browser intentionally refuses arbitrary executable uploads.

### 17.3 The seven navigation pages in English

| Page | Purpose |
|---|---|
| **Home** | Read the declared annual chain, selected data readiness, installed module status and fixed model boundary before configuring a study. |
| **Data** | Bind, validate and replace the 25 PSM/CEM input roles in the selected data pack. It manages inputs, not model logic. |
| **Modules** | Inspect each registered executable implementation, version, public contract, inputs, outputs and readiness. |
| **Studies** | Save a versioned combination of data pack, module choices, years and parameter overrides. A Study is a configuration, not a completed result. |
| **Runs** | Preflight, start, monitor, safely cancel, resume, archive, export, trash and compare model runs. |
| **Inspect** | Query project-level planning evidence, period/order-level market evidence and downloadable artifacts/provenance for the selected run. |
| **Add data** | Read the adapter boundary and manifest example. It is currently guidance, not a finished no-code data-pack builder. |

VALUE is the application implementing these pages and the scientific framework executed behind them. Historical `VALUE` and `VALUE` identifiers remain only where compatibility requires them.

### 17.4 Every selectable Study field in English

#### Study details and module chain

| Field | Meaning and choice |
|---|---|
| **Name** | Human-readable experiment name. The service generates a stable ID and an append-only revision identity. |
| **First model year** | First included year; the current UK baseline normally starts in 2025. |
| **Final model year** | Last included year; 2025–2034 means ten full model years. |
| **Data pack** | Frozen input-pack reference for the Study. Use the verified 1000 TWh pack for the current UK case. |
| **Psm** | Choose `value-bid-at-cost-psm` for offer-based bid-at-cost competition or `value-perfect-foresight-lp` for centrally optimized dispatch. |
| **Storage Cost** | Under the offer-based PSM choose dynamic annual recovery, legacy tariff or safe user formula. The field is correctly removed under perfect foresight. |
| **Pipeline** | Selects the planning-stage, success, deferral, failure and commissioning implementation. One option currently means one conforming module is installed. |
| **Vre Cap** | Selects the annual solar/wind investment-headroom policy. |
| **Storage Cap** | Selects annual storage investment headroom; this is not storage bidding cost. |
| **Investment** | Selects the owner-level proposal and retirement decision logic. |
| **Transition** | Selects how admitted, commissioned and retired state is carried into the following year. |

The actual annual order is planning advance/commissioning → selected PSM → expansion headroom → investment → planning admission/failure/deferral → state transition.

#### Planning settings

| Parameter | Default / choices | Effect |
|---|---|---|
| `planning.success_mode` | `expected`; `stochastic`, `expected_capacity`, `seeded_stochastic` | Uses probability-weighted expected capacity or reproducible project-level random success. The paired names are compatibility aliases. |
| `planning.random_seed` | 0 | Seed for stochastic planning success; irrelevant to expected mode. |
| `planning.include_uncertain_projects` | true | Retains projects whose completion timing is uncertain. |
| `planning.zombie_filter_enabled` | true | Applies declared stale/terminated/overdue project filters. |
| `planning.zombie_status_stale_year` | 2015 | Treats sufficiently old last-status evidence as stale under the filter. |
| `planning.construction_grace_years` | 2 years | Adds limited grace beyond the declared construction timeline. |
| `planning.minimum_project_size_mw` | 1 MW | Excludes source projects below the threshold. |
| `planning.max_completion_year` | 2040 | Excludes source projects outside the planning horizon. |
| `planning.timeline_statistic` | `median`; `mean` | Chooses the statistic used for planning/construction duration. |
| `planning.defer_spread_years` | 3 years | Deterministically spreads projects deferred from the initial year. |
| `planning.repd_battery_assignment` | proportional split; all 1C/0.5C/0.25C; exclude | Maps untyped REPD battery projects to fixed-duration technologies or excludes them. |

#### Expansion and storage-cost settings

| Parameter | Default / choices | Effect |
|---|---|---|
| `expansion.vre_cap_fraction` | 0.20 | Fraction of calculated annual solar/wind expansion headroom made available to agents. |
| `expansion.storage_cap_fraction` | 0.20 | Fraction of calculated annual storage headroom made available to agents. |
| `expansion.storage_credit_method` | `scheme_c` only | Current storage-capacity-credit rule; no second validated implementation is installed. |
| `storage.cost.discount_rate` | 0.05 | Real discount rate used by compatible dynamic/user-formula project annualization. |
| `storage.cost.utilisation_floor_fraction` | 0 | Lower bound on later-year sales denominators relative to full-utilization design sales. The first year always uses full utilization. |
| `storage.cost.custom_formula` | approved default arithmetic | Formula used only by `user-formula-storage-cost`; approved variables and arithmetic only. |

#### Market settings

| Parameter | Default / choices | Effect |
|---|---|---|
| `market.bid_multiplier` | 1.0 | Multiplies cost offers under `value-bid-at-cost-psm`. Only 1.0 is strict bid-at-cost; other values are explicit markup/markdown experiments. |
| `market.perfect_foresight_terminal_soc_rule` | `cyclic`; `fixed`, `free` | Sets terminal storage SOC only for the perfect-foresight LP. |
| `market.voll_gbp_per_mwh` | 10,000 GBP/MWh | Value of lost load used by the perfect-foresight LP for unserved demand. |

#### Output and runtime settings

| Parameter | Default / choices | Effect |
|---|---|---|
| `runtime.checkpoint_enabled` | true | Writes identity-verified annual recovery points; keep enabled for long runs. |
| `runtime.market_trace_level` | `summary`; `off`, `full` | Controls market evidence. `full` stores every order and is much larger. |
| `runtime.market_balance_diagnostic` | false | Writes verbose period balance diagnostics for debugging. |
| `runtime.market_export_format` | `sqlite`; `parquet` | Selects the primary fast market ledger/export representation. |
| `runtime.generation_trace_level` | `off`; `summary`, `full` | Controls asset-generation trace volume. |
| `runtime.console_verbosity` | `normal`; `quiet`, `debug` | Controls console logs only. |
| `runtime.artifact_batch_size` | 500 rows | Controls batched evidence writes; long runs currently use a larger resolved value where declared. |
| `runtime.ensemble_max_parallel_children` | 1 | Maximum explicit ensemble children; it does not parallelize an ordinary single Study. |

#### Registered base parameters in Advanced Review

| Parameter | Current default | Status |
|---|---|---|
| `scenario.id` | `existing_decarb_base` | Selectable from the registry-backed Advanced panel; alternatives include `subsidy_as_usual` and `government_target`. |
| `carbon.factor_scenario` | `value_current_authoritative_v1` | Advanced panel also exposes the bounded VALUE reproduction factor set. |
| `terminal.policy` | `report_only` | Advanced panel exposes `pipeline_tail` and `full_extension`; preflight applies the selected policy. |
| `fleet.valuation_discount_rate` | 0.05 | Advanced parameter for informational residual-value reporting; it does not change dispatch or headline system cost. |

Do not edit a saved Study JSON manually during a demonstration. Use Advanced
Review so the effective values and sources are frozen in the revision.

### 17.5 English run and troubleshooting quick reference

- Always run **Check readiness** for the intended scale before launch.
- A two-period wiring check and two-year hand-off smoke test are diagnostics; neither is eligible for annual economics.
- **Two full model years** executes 35,040 half-hour periods and tests next-year asset injection. **Complete study** executes every configured full year.
- Closing the browser does not stop the background run. Use safe cancellation and verified checkpoint resume.
- Use port **8800**, not 3000. The API on 8766 is not the user interface.
- A 0/25 research pack is an empty import workspace. Select the verified 25/25 pack for the UK demonstration.
- If Storage Cost disappears, the Study uses centrally co-optimized perfect foresight; this is correct.
- Individual orders require `runtime.market_trace_level = full`; summary-only evidence does not mean that no bids were processed.
- `Not evaluated` carbon is an intentional scientific status when factor boundaries or units do not reconcile. Never replace it with zero.
- The headline CEM resource cost is annualized commissioned-fleet capital/FOM plus physical operating resource cost. Settlement and policy-transfer accounts are not added again.


VALUE software is licensed under Apache-2.0. The private Electrace differential optimisation engine, previously labelled VALUE-single, is a separate product and is excluded from VALUE and this licence grant. It is not distributed in this source release. VALUE national single-node calculations are a model configuration and do not refer to that private engine.
