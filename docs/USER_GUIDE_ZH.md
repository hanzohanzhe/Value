# VALUE Network Extensions 本地测试手册

本手册对应 VALUE Network Extensions 0.7.0-alpha.1。VALUE 的全称是 Variable renewable electricity Allocation, Load-enabled excess-generation Utilisation, and system Evolution。本地网页、API 与命令行使用同一个应用服务。

VALUE 把一次研究保存为一个可复现的 Study。Study 记录数据包、模型模块、年份、科学参数和输出设置。运行时，后端按项目中选定的模块执行真实 PSM 和 CEM，不会调用一个与界面选择无关的固定脚本。

## 1. 模型范围

已接受的内置英国基线采用单节点电力系统，没有英国境内输电约束。互联线路是外部进口报价，不是内部输电线路。快速按成本排序 PSM、完美预见 LP 与外部用户模块都是可替换实现；任何单一出清算法都不是 VALUE 的科学定义。VRE 可以主动弃电，不会预先从需求中扣除。

本仓库还提供可选网络能力。逐时序 DC 网络出清已经过解析、随机、24 小时和 168 小时独立检查；AC 目前只是实验性可行性检查器，不是 AC 最优潮流；输电扩张是实验性的因果生命周期，尚未形成经过验证的英国全年或十年路径。选择网络模块时必须提供兼容的拓扑与线路数据，运行身份会记录该能力的成熟度。

每个模型年的顺序是：

1. 推进 planning pipeline，并将当年到期项目投产。
2. 使用投产后的资产清除当年 PSM。
3. 计算风光和储能的年度扩张余量。
4. 投资 agents 根据当年市场结果提出项目。
5. planning pipeline 决定项目的接收、延迟、失败和后续阶段。
6. 保存下一年的资产、项目、投资者和储能状态。

公开 CEM 是 `value-cem-v1`（VALUE Capacity Expansion Model v1）。它是从博士论文 Scheme C 研究代码提炼出的模块化实现，保留 agent 投资和 planning pipeline 的研究结构，但不是 Scheme C 历史内核的逐数值复刻。保留的 Scheme C 代码只用于对照，不能在 Study 中作为 PSM 选择。

每个 Study 和 Run 记录两种方法学口径之一：**修正口径（默认）**（`value-corrected`）或**论文复现口径**（`doctoral-lineage-0.6.0a2`）。各口径适用哪些修正见 [CHANGELOG](../CHANGELOG.md) 与 `docs/generated/METHODOLOGY_PROFILES.md`。

当前版本不包含 AC 最优潮流、完整机组组合或爬坡约束，也不声称 CEM 是全局最优的多年扩张模型。DC 验证不能被外推为 AC 或输电扩张模块已经成为科学基线。

## 2. 安装要求

Linux、Windows、macOS 的 Full 安装包自带 Python 3.10、Node.js 和科学依赖，平台要求见 [DEPLOYMENT.md](DEPLOYMENT.md)。本节其余内容针对 Windows 源码检出，已验证的环境是：

- 64 位 Windows 10 或 Windows 11
- 64 位 CPython 3.10
- Node.js 22 或更高版本
- 安装和短测试至少保留 2 GiB 可用磁盘空间

首次安装时双击 [install-value.cmd](../install-value.cmd)。安装完成后双击 [start-value.cmd](../start-value.cmd)。浏览器地址是：

```text
http://127.0.0.1:8800
```

API 地址是 `http://127.0.0.1:8766`。两个服务都只监听本机回环地址。网页打不开时，不要改用 `127.0.0.1:3000`，除非你正在运行前端开发服务器。

浏览器只与 `http://127.0.0.1:8800`（或 `http://localhost:8800`）通信。网页服务把 `/api` 请求连同只有它和 API 知道的会话一起转发给本地 API；API 拒绝来自网页的直接请求和不带会话的请求。若页面显示 **Open VALUE from its launcher**，说明它是用其他地址打开的，或网页服务与 API 使用了不同的数据目录：关闭页面，用启动器重新启动 VALUE。VALUE 假定一台电脑只有一个使用者；不要安装在共用机房电脑或远程桌面服务器上（见 [SECURITY.md](../SECURITY.md)）。

停止服务时双击 [stop-value.cmd](../stop-value.cmd)。启动脚本只管理本次 VALUE 安装记录的进程，不会停止占用相同端口的其他程序。

如果安装或启动失败，在项目目录运行：

```powershell
py -3.10 scripts\doctor.py --capability value-native
```

检查结果会明确指出 Python、Node.js、依赖、端口、磁盘或数据目录中的问题。更完整的安装说明见 [INSTALLATION.md](INSTALLATION.md)。

## 3. VALUE 101：前半小时怎么学

第一次接触 VALUE 时，先不要导入研究数据。VALUE 101 是随软件提供的 CC0 合成
教学系统，安装为数据包 `value-101-baseline-v1`（可选的分区网络练习另用
`value-101-network-v1`）。它走正常运行路径：保存不可变 Study、冻结输入、调用
所选 PSM 与 CEM、写市场和规划结果，再把系统推进到下一年。网页不会读取一份
事先准备好的结果冒充模型运行。

1. Windows 源码检出先双击 [check-value-101.cmd](../check-value-101.cmd)，看到
   最后一行 `READY` 再继续。
2. 启动 VALUE，在侧栏打开 **Learn**（学习，`/learn`）。
3. 点击 **Create baseline Study**（创建基线 Study）。VALUE 保存 Study
   `VALUE 101 baseline`（2025 至 2026 年，数据包 `value-101-baseline-v1`，全国
   单节点）。创建 Study 不会运行模型。
4. 点击 **Run one market day**（运行一个市场日）。它只用所选 PSM 出清 2025 年
   前 48 个半小时，不调用任何 CEM 阶段。打开 **Market replay**（市场回放）和
   **VRE & curtailment**（VRE 与弃电）查看报价、调度、储能和未利用 VRE。
5. 需要年度结果时点击 **Run complete two-year model**（运行完整的两年模型）：
   2025 和 2026 年各出清 17,520 个半小时，中间完成投资、规划和年度状态传递。
   这是较长的本地计算。

数值是合成的，不代表英国电力系统。[VALUE 101 中文教程](tutorial/VALUE_101_ZH.md)、
[英文教程](tutorial/VALUE_101.md)和[一页检查卡](tutorial/VALUE_101_QUICK_CARD.md)
描述的是同一条路径。完成后再按下文接入真实研究数据。

## 4. 数据存放位置

源代码目录中的既有安装默认继续使用 `.gridform`。全新安装默认把本地状态放在 `%LOCALAPPDATA%\VALUE`。也可以在启动前设置 `VALUE_DATA_HOME`：

```powershell
$env:VALUE_DATA_HOME = "D:\VALUE-Research"
.\scripts\start-local.ps1
```

该目录保存：

- `data-packs`：数据包 manifest 和已导入对象
- `objects/sha256`：按内容哈希保存的输入对象
- `projects`：Study 及其不可变 revisions
- `runs`：运行状态、checkpoint 和结果
- `archives`：已归档运行的完整审计包
- `trash`：本机回收目录（Study 可以从回收区恢复；Run 移出工作区后 VALUE 不提供恢复）

不要把个人研究数据放入 Python package，也不要把本地英国数据包直接提交到 Git。

## 5. 第一次研究运行

如果还没有本地数据包，可先安装 CC0 合成示例：

```powershell
py -3.10 scripts\install_synthetic_pack.py
```

也可以打开 **Data** 页面，在 **Install a VALUE data pack** 中选择数据维护者
提供的 `value.data-bundle/v1` ZIP，阅读并确认其中的许可与署名记录后安装。
浏览器只把文件流式传给本地服务；后端在同一磁盘的临时目录检查安全路径、
解压上限、逐对象 SHA-256、manifest、权利记录和 25 个语义接口，全部通过后
才原子写入。上传阶段取消或任一检查失败，都不会改变已有数据包，临时文件会
被清理。安装后不再保留 ZIP 的第二份副本；不同内容必须使用新的版本化 pack ID。

然后按以下顺序操作：

1. 打开 **Data**（数据）选择数据包，确认所有 required inputs 已就绪。
2. 在 **Modules**（模块）查看可执行模块及其输入、输出和契约版本。
3. 打开 **Studies** 新建 Study，在第一步 **Identity**（基本信息）填写名称、研究
   目的、年份和数据包，并保留或更改方法学口径（默认 **Corrected methodology
   (default)**，中文界面为“修正口径（默认）”）。
4. 在 **System domain** 选择单节点、reference DC 或实验性 AC feasibility；
   必需的 contract extension 由后端解析。
5. 在 **Optional domains** 按需加入 hydrology 或 transmission expansion，
   并对每个实验版本作明确确认。
6. 在 **Model chain** 核对或替换兼容的 PSM/CEM 实现。
7. 在 **Review** 核对条件数据、有效参数和 graph SHA-256，再保存不可变 revision。
8. 打开 **Runs**（Run 中心），选择 Study 和运行范围，先点 **Check readiness**（检查就绪情况）。
9. 新数据或新模块先运行 Two-period wiring check（两时段连接检查），再运行 Two-year hand-off check（两年交接检查）。
10. 接线检查通过后，运行两个完整模型年。完整十年研究应在年度投资与下一年注入审计通过后再开始。

编辑中的 Study 草稿会保存在本浏览器里；回到 Studies 页时会提示 **Restore unsaved draft**（恢复未保存的草稿）或 **Discard draft**（丢弃草稿）。

合成数据只能验证接口、安装和运行链路，不能支持英国电网科学结论。

## 6. 各页面分别管理什么

侧栏分三组：**Start**（开始：Home、Learn、Research guide）、**Work**（工作：Studies、Data、Modules、Extensions）、**Results**（结果：Runs、Compare、Inspect）。侧栏底部在任何宽度下都显示本地服务状态（服务没有应答时有 **Retry** 重试按钮）、语言切换（English / 中文）和版本号。界面默认英文；选择保存在浏览器 cookie `value_locale` 中，不按浏览器语言自动切换。模型时间在两种语言下都按 UTC 标注。宽度小于 1200 px 时侧栏收成图标栏，小于 900 px 时变为抽屉。

每个页面都有自己的地址，链接或书签可直接打开：

| 地址 | 页面 |
| --- | --- |
| `/` | Home（首页）：四条研究路径、服务与输入状态、最近的 Run |
| `/learn` | VALUE 101 |
| `/journey` | Research guide（研究路径），用于复现与换数据两条路径 |
| `/studies`、`/studies/<study>` | Study 列表；编辑一个 Study |
| `/data` | 数据包、CSV 映射编辑器、Data Workbench |
| `/modules` | Catalog、Disabled & quarantined、Author a module |
| `/extensions` | 扩展目录、安装与编写 |
| `/runs` | Run 中心 |
| `/runs/<run>` | 一个 Run 的年度结果（`?year=`） |
| `/runs/<run>/replay`、`/vre`、`/network`、`/systems` | 市场回放、VRE 与弃电、网络与再调度、网络与水系统 |
| `/compare` | 比较 Run（`?runs=a,b&ref=a`） |
| `/inspect` | 检查（`?tab=&q=`） |

旧链接 `/?view=<页面>` 会转到对应地址，其他参数保留。浏览器的后退、前进会恢复所选 Study 和 Run。若页面与本地服务报告的界面契约版本不同，页面会提示重启 VALUE。

Home 有四条路径：**Reproduce from existing data** 与 **Add your new data** 打开研究路径页；**Edit a module** 打开 Modules 页的模块编写工具；**Add a new function to VALUE** 打开 Extensions 页的扩展编写工具。

### Data

一个数据包将来源不同的文件映射到稳定的语义角色。PSM 角色包括需求、天气、机组、VRE profile 和进口报价。CEM 角色包括 REPD 项目、CAPEX/FOM、policy cost、planning success 和技术寿命。页面会根据当前 draft 或已保存 Study，动态增加 Network、AC feasibility、Hydrology 和 Network expansion 分组；模板与预览调用的也是 preflight 使用的 canonical adapter。页面顶部可以安装完整的非可执行数据包，并显示文件大小、上传进度、验证阶段和精确错误代码。

上传 Replace 只会创建新的本地数据对象和 binding revision，不会修改原始文件。每个 binding 记录相对 URI、格式、单位或映射、SHA-256 和来源信息。运行开始时会冻结这些信息。

### Modules

该页面显示模块 registry 中真正可以执行的 Python 实现。当前公开 slot 是：

- `psm`
- `storage_cost`，只适用于报价型 PSM
- `pipeline`
- `vre_cap`
- `storage_cap`
- `investment`
- `transition`
- `network_expansion`（可选）

模块卡片中的 ID、版本、contract、输入和输出会进入运行身份。模块 ZIP 在 Modules 页安装，extension ZIP 在 Extensions 页安装，两套事务式安装流程彼此独立；extension 安装成功不等于已在 Study 中启用。外部模块只有通过 conformance 检查后才会出现在这里。

#### 安装别人编写的模块

打开 **Modules** 页面顶部的 **Install a model module**：选择建模者提供的 `value.module-bundle/v1` ZIP，勾选可执行代码信任确认，再点击安装。VALUE 会在临时目录检查文件清单与 SHA-256、路径穿越、manifest、Python entry point、槽位/contract、必需方法和最小 conformance fixture；全部通过后才原子写入模块目录并立即刷新 Studies 下拉框。

安装成功不代表科学方法已经验证。先建立新的 Study revision，运行 two-period wiring check，再做完整年度测试。内置模块不能被覆盖或禁用；已被 Saved Study 引用的外部模块不能在模块卡片上直接停用。已隔离的模块可以在隔离面板中停用，即使仍有 Study 引用它；此后这些 Study 在模块修好并重新启用、或改选其他模块之前不能运行。外部源码按模块/版本分目录保存，但仍在 VALUE Python 进程内运行。安装器不联网、不运行 `pip`、不接受原生二进制。

开发者从 `examples/external_module_bundle` 复制模板，并用 `scripts/build_module_bundle.py` 构建确定性的 ZIP。每个包必须包含 `force-bundle.json`、`value-module.json`、`src/`、`LICENSE`，可选 `README.md`。描述文件 `force-bundle.json` 由构建脚本写入，文件名是改名前留下的兼容名称；`value-module.json` 中的 `contract_version` 必须是 `value.*` 形式（例如 `value.storage-cost/v1`），见 `MODULE_DEVELOPER_101_ZH.md` 第 4 节。

### Studies

Study 管理研究的组成和科学身份，不管理任意桌面绝对路径。保存项目会创建 append-only revision。修改显示名称不会改变科学身份；修改数据、模块、年份或参数会创建新的 revision 和 SHA-256。

### Runs（Run 中心）

Run 中心（`/runs`）负责 preflight、物理域输入预览、启动、checkpoint 恢复、取消、归档和导出，并列出每个 Run 的状态词、进度、错误码和诊断首行。关闭网页不会停止后台模型。每个 Run 有自己的页面（`/runs/<run>` 及其下的回放、VRE、网络页），页面顶部是 Run 上下文条。情景比较在 Compare 页（见第 14 节）。

### Inspect

Inspect（检查）页面按需读取 planning project、生命周期事件、市场周期和结果文件及 provenance。大表保存在 SQLite、JSONL 或 NPZ 中，不会全部塞入主运行页面。按 Enter 或点击 **Apply filters** 后才搜索。

### Network & water

该页面只读取完成运行中已有的 typed artifact，显示 DC 节点平衡、节点价格、
支路流量与拥塞、AC feasibility 状态，以及输电扩容事件链。它不会在 React 中
重新求解。若普通年度路径没有写出可索引的 natural-flow hydrology artifact，
水文结果会明确显示 `not_evaluated`，不会由前端猜一个数。

## 7. 运行模式

| 范围 | 实际执行 | 适合用途 | 可以解释年度经济性吗 |
| --- | --- | --- | --- |
| Two-period wiring check（两时段连接检查） | 一个年份的两个半小时 | 数据和模块接线 | 不可以 |
| Two-year hand-off check（两年交接检查） | 两个年份，每年两个半小时 | PSM 到 CEM 再到下一年的状态传递 | 不可以 |
| One-day market lesson（一天市场课程） | 48 个半小时，只运行 PSM（VALUE 101） | 教学 | 不可以 |
| Two full model years（两个完整模型年） | 两年各 17,520 个半小时 | 年度成本、投资、投产和下一年注入 | 可以 |
| Complete study（完整研究） | Study 配置的全部年份 | 正式研究情景 | 可以，但仍受模型范围限制 |

Run 中心只提供该 Study 数据包允许的范围；就绪检查和 **Run selected scope**（运行所选范围）使用同一个范围。

Preflight 会检查 Python capability、模块兼容性、25 个数据接口、参数、输出目录、磁盘余量和预计运行规模。不要在 preflight 有 error 时强行启动。

## 8. PSM 和储能定价选择

### 默认 bid-at-cost PSM

`value-bid-at-cost-psm` 是默认 PSM，即 VALUE 的 bid-at-cost 市场。选择该 PSM 时必须选择一个 `storage_cost` 模块。

`dynamic-annual-storage-cost` 在第一年按技术能够满负荷运行的设计利用率初始化。后续年份把年化项目成本按上一年实际售电量和售电加权储存时间回收。循环折旧只作用于 battery，pumped hydro 和 hydrogen 没有该分量。`storage.cost.utilisation_floor_fraction=0` 保留论文中的精确零下限解释。研究者可以另外建立带利用率下限或平滑分母的敏感性情景。

`value-legacy-storage-tariff` 使用历史 Scheme C tariff 公式。它用于受控对比，不代表整个模块化模型能够逐数值复刻保留内核。

`user-formula-storage-cost` 允许用户用批准变量编写受限算术公式。公式不执行任意 Python 代码。

`scheme-c-psm` 不是 Study 可选的模块：它是保留内核对照桥（只由显式的保留内核对照命令使用）记录的 PSM ID，也是 `value-bid-at-cost-psm` 所继承的内部类的标识。

Run 中心的 **Clone a storage-pricing experiment**（复制一个储能定价实验）会复制 Study，只替换储能定价模块。数据、年份和其他模块保持不变，适合做可解释的政策对比。

### Perfect foresight LP

`value-perfect-foresight-lp` 是另一种 PSM。它使用 SciPy/HiGHS 集中联合优化发电和储能，不使用 storage offer cost 模块。该模块需要 solver capability。它与 bid-at-cost agent pricing 回答不同研究问题，不应把两者当作同一个 tariff 的两个参数值。

独立 PuLP/CBC oracle 已在 24 小时、168 小时和随机凸算例上验证 perfect foresight LP，也验证故意破坏能量平衡、效率、SOC、终端状态和进口约束时测试会失败。该验证不把 VALUE 的顺序性市场规则重新定义成一个全局 LP。

## 9. Planning pipeline 和新增资产

Planning pipeline 记录每个项目的来源、技术、地区、容量、阶段、成功、失败、延迟和投产年份。项目当年投产后，会在同年 PSM 开始前进入实际资产集合。新增资产继承：

- 稳定的 physical asset ID 和 investment owner ID
- MW 和 MWh 容量
- CAPEX、FOM 和经济寿命
- 技术、地区和数据来源

投资按 economic owner、technology 和 region 聚合，commissioned children 不会复制投资 agent。风、光和储能使用技术级共享年度扩张余量，不会按现有机组行数重复放大。

英国 REPD 中没有明确 duration 的 generic battery 默认按 `scheme_c_proportional_split` 拆分到四种 battery 技术。这个映射是可见的兼容假设，不是原始 REPD 事实。expected-capacity 模式会用同一个成功概率同时缩放 MW、MWh、CAPEX 和 FOM，并排除已被新申请替代的 superseded applications。

现有 natural-flow hydro 可以运行。新水电必须提供场址、水文和 new-build CAPEX 证据，不能继承现有水电的兼容账面值。pumped hydro 是已有独立储能技术，不会作为普通库容水电重复建设。

## 10. 成本结果

主系统成本使用 `value.cem-system-resource-cost/v1`：

```text
投产资产的年化 CAPEX 和 FOM + 物理运行资源成本
```

GBP/MWh 使用 served demand 作为分母。市场结算、政策转移、储能 bid recovery、未投产 pipeline commitments 和期末残值是独立账目，不会再次计入 system resource cost。

运行页面显示适合快速阅读的年度汇总。详细 cost ledger 保存在 `ledgers/annual-cost-ledger.json`。operational cost 为 0 只能在确实没有物理运行成本且账本可对账时出现。完整英国年度运行若显示 0，应视为错误并检查运行模式、成本 activity 和 ledger status。

## 11. 碳结果

每个原生年度运行固定使用一个 carbon factor scenario：

- `value_current_authoritative_v1`
- `doctoral_reproduction_2026_07_18`

碳账本可以包括火电直接排放、进口电、当地新增设备隐含排放和储能生命周期排放。只有 activity 和 factor 都存在时才计算。缺少证据时状态是 `not_evaluated`，不会静默写成 0。

JSON 和 SQLite 碳账本必须逐年一致。详细结果位于 `ledgers/annual-carbon-ledger.json` 和 `ledgers/annual-carbon-ledger.sqlite`。

Scheme C reproduction 情景有不同边界。历史 storage scalars 40/50 没有已确认的物理单位，因此 VALUE 返回 null total、`not_physically_interpretable` 和 `legacy_storage_scalars_have_no_declared_physical_unit`。系统不会把该历史数值改名为 tCO2e，也不会显示成 0。

## 12. 结果文件

一个完成的原生运行通常包含：

| 文件或目录 | 内容 |
| --- | --- |
| `resolved-run.json` | 冻结后的项目、数据、模块和参数身份 |
| `preflight.json` | 启动前检查和规模估计 |
| `year-results-v2.json` | 年度 PSM、投资、planning 和 next-state 结果 |
| `checkpoints-v2/state-YYYY.json` | 通过身份校验的年度原子 checkpoint |
| `market/market.sqlite` | 快速写入的分期市场结果 |
| `planning/project-index.sqlite` | 项目、阶段和投产索引 |
| `planning/summary.json` | planning 汇总 |
| `ledgers/annual-cost-ledger.json` | 可对账成本账本 |
| `ledgers/annual-carbon-ledger.*` | JSON 和 SQLite 碳账本 |
| `terminal/fleet-vintage.json` | 期末机组寿命和残值信息 |
| `artifact-index.json` | bundle 文件、哈希和角色索引 |
| `provenance.json` | 输入、代码和运行来源 |
| `performance.json` | 各模块和年份耗时 |

可以在项目根目录验证一个结果目录：

```powershell
py -3.10 -m gridform_core.bundle_validator <run-directory>
```

验证只读取结果，不会重新运行模型。

### 结果状态词

各结果视图使用同一组状态词（P0-9），只有 `invalid` 用红框显示：

| 状态 | 含义 | 怎么办 |
| --- | --- | --- |
| `reconciled` | 记录的数值通过了恒等式和身份核对 | 正常阅读 |
| `unavailable` | 没有记录这类证据（例如铜板 Run 没有弃电归因表） | 不是错误；需要时改用会记录它的方法 |
| `Partial year · n%` / `Running` / `Stopped · n%` / `Non-annual run` | Run 只覆盖了年份的一部分（仍在运行、已取消或失败，或者是短运行模式），因此不显示年度合计 | 到 Inspect 查看分时段账本 |
| `Withheld` | 只用于一条规则（Q14）：论文复现口径的 Run 原始不变量没有全部通过时，年度结果不在结果页发布 | 到 Inspect 查看，或导出账本 |
| `invalid` | 记录的证据自相矛盾（身份或年份集合对不上） | 把该 Run 的结果视为未经核实，检查账本 |
| `Not modelled` / `Not computed` / `Not recorded` | 该方法不建模此项 / 实现尚未计算 / 旧 Run 没有记录 | 都不等于 0 |

其他标签都写明口径。平均系统成本：CEM 资源成本账写作 `/MWh served`，遗留口径的总成本写作 `/MWh generated`，口径未知时写作 `(basis not recorded)`。成本构成旁的注记说明头条是否包含失负荷价值（VoLL），悬停可看到记录的 VoLL 金额。修正口径下，VRE 页把账本两列称为 `Non-VRE spill`（非 VRE 弃置）和 `VRE curtailment`（VRE 弃电），只显示一组事件（`Unused VRE`，口径 `corrected_unused_vre`）；没有受影响时段的事件组显示 `No events recorded`。映射以欧元计价的价格 CSV 时，须填写币种、EUR per GBP 汇率、汇率口径和价格年份，预览中原始欧元值与换算后的 £/MWh 并排显示。

### 科学验证、能量平衡与 stress event

`validation/scientific-validation.json`（v2）中的每个状态都由本次运行实际执行的检查重算，不再有写死的 “passed”。以下三组检查是 gate：

- **run 不变量**：时段覆盖、需求输入对账、发电跨路径核对、年度状态链。
- **能量平衡**：只读 oracle 按 PSM 在账本中声明的边界逐期重算。缺口（接纳供给没有满足的需求）记为缺电量，并作为 **stress event** 报告，不判能量平衡失败；记入缺口之后仍不闭合的残差（记录的供给超过全部用途）才判失败。
- **储能不变量**：充放电不超过额定功率、同一时段不对同一储能既充又放、荷电状态不超出容量，以及逐储能的能量审计恒等式。

默认（corrected）口径下，任一 gate 失败，科学验证即为 `failed`，年度经济结果不发布。论文复现（doctoral）口径保留论文行为：符合已声明偏差的失败（例如必发盈余的重复计入、每个出清阶段重置储能功率上限）显示为 `reproduction_with_declared_deviations`，没有失败显示为 `reproduction_conformant`，其他情况显示为 `failed`。复现口径的年度结果只有在原始不变量全部通过时才在结果页发布，否则只在 Inspect 和导出中提供。市场账本中“调整后残差”一列不能作为能量平衡的证据。任何 Run（包括旧 Run）都可以只读复核：

```powershell
py -3.10 -B -m gridform_core.energy_balance_oracle <run-directory>
```

退出码 0 为通过，1 为失败，2 为未评估。这些检查出现之前产生的 Run 在读取时复核，原来的 `passed` 显示为 superseded。

在浏览器中的位置：

- Run 上下文条显示 **Energy balance**（蓝绿色 `● Conformant` 表示论文复现账本闭合，不代表物理验证通过）和 **Stress events**（`None`，或 `● {n} periods · {缺口}`）。精确 stress 记账之前产生的 Run 把缺口显示为下界 `≥ x MWh`，悬停可看到上界。
- 任一 gate 失败时，红色提示 `Validation gate failed: {gate 名称}` 逐条列出失败的 gate；修正口径下 Runs 页不显示年度合计，改为显示 `Annual results not published`，并给出 Inspect 和导出账本的入口。
- **Show stress events** 打开 Market replay 中的 **Stress events — full year {year}** 列表：开始时间、时段数、缺口、类型 `stress (supply < demand)`，以及跳到对应窗口的 Replay。窗口卡显示 `Shortfall` 与 stress 时段数，图上用细的琥珀色带标出 stress 时段。分区网络内的失负荷仍在 Network & redispatch 页（类型 `lost load (network)`）。
- Inspect › Market 显示原始边界检查（边界、原始判定、最大残差、时段数），即缺口记为缺电量之前的证据。

## 13. 取消、恢复、归档和删除

- Request safe cancellation 写入取消请求。原生运行在下一个完整年度 checkpoint 边界停止。
- Resume from verified annual checkpoint 只对 failed 或 cancelled 运行开放。数据、项目 revision、参数、模块和实现哈希必须与 checkpoint 一致。
- Archive 先生成并验证 complete audit ZIP，再把运行标记为 archived。
- Restore archive 会验证 ZIP 后恢复运行记录。
- Prepare audit bundle 生成可下载的审计包。
- **Remove from workspace**（移出工作区）要求输入完整 run ID。它把 Run 目录移到本机回收目录，不会立即永久删除；VALUE 不提供 Run 的恢复功能，要找回只能手动把目录移回。移入回收区的 Study 可以恢复。

每个 Run 的模型 worker 持有 `<run>/worker.lock` 租约。关闭 VALUE 不会停止正在运行的 worker：停止提示会列出仍在后台运行的 Run，下次启动时 VALUE 通过租约接管监督。worker 退出或消失时，Run 会在几秒内（或在下次启动时）转为 failed（若已请求取消则为 cancelled），错误码为 `GF_WORKER_EXITED` 或 `GF_WORKER_LOST`，之后可以 Resume 或移出工作区。旧版 VALUE 启动的 Run 不一定能确认存活（`worker_liveness: unverifiable`）；**Mark as lost**（标记为丢失）需要输入完整 run ID，并且只有在 Run 目录 15 分钟内没有任何变化时才会接受。同一个数据目录只能有一个 VALUE 后端，第二个会以退出码 3 停止，不改动任何内容。

移出 Run 时先移动目录，再只在回收目录中的副本里记录 `deleting`；移动失败时 Run 保持原状。磁盘预留只由活动 Run 持有，且只计尚未写出的输出；已结束的 Run 按实际字节计（硬链接只计一次）。移出工作区会释放配额，归档不会。

不要手工复制某一个 checkpoint 到另一个情景。即使年份相同，科学身份不一致也必须拒绝恢复。

## 14. 情景比较

打开 **Compare**（比较，`/compare`），勾选同一范围的 2 到 6 个已完成 Run，并选择 **Reference Run**（参照 Run）。默认参照是最早创建的基线 Run（派生 Study 的来源），否则是最早创建的 Run。所有差值（+ 和 %）都相对参照 Run 计算，页面写明参照是谁；地址以 `?runs=a,b&ref=a` 保存所选。导出 CSV 或 JSON 的按钮在页头；CSV 在 `schema_version` 之后有一行 `reference_run_id` 写明参照。

表格上方的 **Identity check before comparison**（比较前的身份核对）逐维列出数据、方法、年份、成本与碳定义、denominator 和终端政策是 Same 还是 Changed。只有某项指标背后的定义一致时才显示该指标的数值差，否则写明原因并不显示。两时段等诊断范围不产生年度指标。动态储能和 legacy tariff 的受控克隆使用同一个 VALUE 成本定义，可以直接比较。模块化 VALUE 与保留 Scheme C 使用不同 system-cost 定义时，只能做带标签的描述性比较。

## 15. 接入新数据库

新数据源应在 adapter 边界转换，而不是把来源专用路径或列名写进 PSM/CEM。建议流程是：

1. 为数据源建立新的 data-pack manifest revision。
2. 使用 CSV、Parquet、NetCDF、SQL 或 API adapter 读取原始数据。
3. 统一技术代码、单位、货币年份、时区和半小时时序。
4. 映射到稳定的 semantic roles。
5. 保存来源、license、attribution、checksum 和转换说明。
6. 运行结构和语义验证。
7. 用合成或小规模数据完成 wiring、two-year smoke 和 full annual gate。

weather 和 demand 文件使用数据包内相对路径。运行时通过 workspace registry 解析到本地对象，不能依赖作者桌面上的绝对路径。

25 个内置角色和格式见 Data 页面。外部 adapter 示例位于 [examples/external_modules/README.md](../examples/external_modules/README.md)。

## 16. 接入新模型模块

先用总教程
[`BUILD_YOUR_OWN_MODEL_101_ZH.md`](BUILD_YOUR_OWN_MODEL_101_ZH.md)
判断应当替换 data pack、Study parameter、现有 module，还是升级平台 contract。
从零编写、打包和测试一个具体 module 的逐步教程见
[`MODULE_DEVELOPER_101_ZH.md`](MODULE_DEVELOPER_101_ZH.md)。其中包含
data/parameter/module/架构的选择方法、七个可替换 slot、module 替代原理、
`module.zip` 的准确格式、manifest、入口模板和从单元测试到多年运行的分层门槛。

外部模块是安装好的 Python package，包含 `value.module/v2` manifest。manifest 至少声明：

- 稳定 module ID、slot 和 semantic version
- contract version
- typed inputs 和 outputs
- state read/write sets
- parameters、capabilities 和 determinism
- 生成的 artifacts

外生 demand profile 通常应进入 data pack/adapter；storage-cost、扩张、投资、
planning 和 transition 算法使用对应 slot。DC/AC 的求解算法属于完整 PSM；
VALUE 已经提供 solver-neutral network contract、拓扑/节点需求条件角色、
reference DC PSM 和实验性 AC-feasibility data contract。替换型 network PSM 应
声明并组合这些 capability/extension。当前没有对应 slot 的新生命周期阶段仍然
需要显式 extension 和平台级验证，不能
伪装成其他 module。不要在 Scheme C compatibility 代码里增加隐藏开关。外部模块
必须先安装并通过 conformance tests。

## 17. 命令行运行

Study JSON 也可以通过公开 application service 运行：

```powershell
py -3.10 -m gridform_core.application `
  --project examples\release-dynamic-storage-2025-2034.scenario.json `
  --pack .gridform\data-packs\uk-scheme-c-1000twh `
  --output outputs\my-dynamic-run `
  --run-id my-dynamic-run `
  --mode full
```

命令行和网页使用同一个 orchestrator、module registry、参数解析和结果契约。长跑建议开启 `runtime.checkpoint_enabled=true`，并使用 `runtime.generation_trace_level=off` 或 `summary` 控制大体量 generation trace。关闭详细 generation trace 不会删掉公开 period summary、年度总量、投资或 storage observation。

脚本直接调用正在运行的本地 API 时需要它的会话：从 API 的数据目录读取，并作为请求头发送；不要发送 `Origin` 头。

```python
import json, urllib.request
from backend.api_session import authorized_headers  # 在 VALUE 源码或安装目录的 app 中运行

headers = authorized_headers(r"C:\Users\me\AppData\Local\VALUE\state", 8766, json_body=True)
request = urllib.request.Request("http://127.0.0.1:8766/api/projects/validate",
                                 data=json.dumps({"name": "check"}).encode(), headers=headers, method="POST")
print(urllib.request.urlopen(request).status)
```

没有会话时只有精简的 `GET /api/health` 会应答。请求体必须带明确的 `Content-Type`（例如 `application/json`）；表单和 `text/plain` 请求体会以 415 拒绝。

## 18. 可复现研究清单

发布或引用一个结果前，至少保存：

- Study JSON 和 revision SHA-256
- data-pack manifest、各对象 SHA-256、来源和许可
- module manifests 和 implementation hashes
- Python 与依赖版本
- random seed 和 planning uncertainty mode
- carbon factor scenario
- storage pricing policy 及其参数
- preflight、bundle validation 和 scientific validation
- 完整 cost、carbon、market 和 planning 账本

运行 bundle 是结果证据，不是英国数据再分发许可。软件采用 Apache-2.0，仓库文档采用 CC BY 4.0，合成数据采用 CC0-1.0。英国数据对象仍受各自上游条款控制。

## 19. 常见问题

### 页面提示“界面与本地服务的版本不一致。请重启 VALUE。”

页面加载时会核对本地服务的 `frontend_contract_version`。停止 VALUE，再用启动器启动，让页面与服务来自同一个安装。

### 浏览器显示 connection refused

确认地址是 `http://127.0.0.1:8800`，然后运行 `start-value.cmd`。若仍失败，运行 environment doctor，并检查 `.gridform/frontend-error.log` 或 `%LOCALAPPDATA%\VALUE\frontend-error.log`。

### 页面显示 Open VALUE from its launcher

页面不是经启动器打开的：用了其他主机名、另一份安装的书签，或网页服务读取的数据目录与 API 不同（HTTP 421/403 也是同一原因）。停止 VALUE，再用启动器启动。`python -B scripts/verify_local_security_boundary.py` 可检查正在运行的安装：所有跨站、DNS rebinding 和无会话探测都被拒绝时输出 PASS。

### 页面显示 Python 3.12 不兼容

停止旧服务后重新运行 `start-value.cmd`。启动器优先使用项目 `.venv`，其次使用 Python 3.10。VALUE 目前不接受未经验证的 Python 3.12 科学运行。

### 25 个接口齐全但 preflight 失败

接口数量只表示文件已绑定。preflight 还会检查单位、时间范围、checksum、模块 capability、参数和磁盘。按错误中的 corrective action 修正，不要把 warning 或 error 改写成成功。

### 长跑中断

不要删除输出目录。先确认 `checkpoints-v2` 中最后一个 `state-YYYY.json` 完整，再从 Run 中心的 Resume 按钮恢复。恢复会重算尚未提交的当前年度，但不会重算已经 checkpoint 的年份。

### 诊断报告 stray bytecode

这是安装目录 `__pycache__` 中的 Python 字节码。VALUE 不会读取它们（每个解释器都使用新建的空 `pycache_prefix`）。运行 `diagnose-value --repair-bytecode` 可把它们移入 `state/quarantine/`；安装目录可写时，启动也会自动这样做。

### 本地模块或扩展被隔离（health 显示 degraded）

VALUE 继续运行，只有选中该条目的 Study 会被拒绝，并给出 `GF_STUDY_MODULE_QUARANTINED` 或 `GF_PREFLIGHT_MODULE_QUARANTINED`。在 Modules 页停用它；或修好后用新 ID 安装，再点 **Rescan**。若 VALUE 走不到这一步，或所有 Run 都因 `GF_EXECUTION_ARCHIVE_MODULE_RECORD` 被拒绝，先停止 VALUE，再按下一节离线自救。

有排队或运行中的 Run 时变更模块或扩展需要显式确认。Run 在排队时记录已安装的代码，绝不会用别的代码启动，所以尚未开始的 Run 会以 `GF_RUN_EXECUTION_IDENTITY_CHANGED` 停止；Runs 页提供 **Resubmit with current code**，用同一 Study 和范围新建一个 Run。已在运行的 Run 保持原代码，但变更后无法再 Resume。

### 离线模块自救（Offline module recovery）

`module_recovery` 只读写、移动安装器的文件，不导入任何已安装代码。先停止 VALUE：VALUE 占用数据目录时该工具拒绝执行。安装版 VALUE 要用自带的 Python 和安装目录下的数据目录运行（`<prefix>` 为安装目录；用 `--python` 安装的版本改用当时指定的解释器）：

```bash
# Linux 与 macOS
PYTHONPATH="<prefix>/app" "<prefix>/runtime/python/bin/python3.10" -B -s \
  -m gridform_core.module_recovery --modules-root "<prefix>/state/modules" list
```

```bat
rem Windows（命令提示符）
set PYTHONPATH=<prefix>\app
"<prefix>\runtime\python\python.exe" -B -s -m gridform_core.module_recovery --modules-root "<prefix>\state\modules" list
```

`-B` 保证不往安装目录写字节码。在源码检出中运行时，`python -B -m gridform_core.module_recovery list` 使用 `$VALUE_DATA_HOME/modules`。把 `list` 换成：

| 命令 | 用途 |
| --- | --- |
| `list` | 列出所有已安装条目、可见问题和 `fix:` 提示 |
| `disable module <id>`、`disable extension <id>` | 与 Modules 页的停用相同 |
| `park-manifest module\|extension <file.json>` | 把读不了的活动清单移开 |
| `park-installation module\|extension <id> [<version>]` | 把安装记录损坏（`GF_MODULE_INSTALL_RECORD_INVALID`）的整个安装目录移开；没有剩余启用版本时连同活动清单一起移开 |

移开的文件放在 VALUE 从不扫描的 `modules/disabled-manifests/`。被移开的模块 ID 与停用的一样仍被占用。

### 结果与保留 Scheme C 不同

先确认比较的是同一数据、年份、碳因子、储能政策和 system-cost 定义。VALUE 的 CEM（`value-cem-v1`）有已声明的结构修正，因此 legacy tariff 只复刻储能报价公式，不保证完整轨迹相同。

### 运行很慢

完整英国年度有 17,520 个半小时，资产和 planning components 会逐年增加。先关闭详细 generation trace，检查 `performance.json`，并用 preflight 估计磁盘和时间。不要用 two-period smoke 的耗时外推十年结果。

## 20. 科学解释边界

VALUE 可以支持以下表述：模型按照记录的 bid-at-cost 和 planning 规则执行；能量、成本、碳和项目账本通过相应审计；新增资产通过 CEM 投产并进入后续实际 PSM；指定情景的结果可以在固定定义下比较。

当前证据不支持以下表述：模型包含英国境内输电约束；模型执行完整 unit commitment；agent market 是全局最优 dispatch；CEM 是完美预见的全局最优扩张；legacy tariff 情景精确复刻 Scheme C；任何本地英国数据都可以随软件一起再分发。

详细数学定义和证据边界见 [MATHEMATICAL_REFERENCE.md](MATHEMATICAL_REFERENCE.md) 与 [VALIDATION_AND_CLAIMS.md](VALIDATION_AND_CLAIMS.md)。
