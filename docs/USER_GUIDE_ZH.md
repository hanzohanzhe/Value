# VALUE Network Extensions 本地测试手册

本手册对应 VALUE Network Extensions 0.6.0-alpha.2。VALUE 的全称是 Variable renewable electricity Allocation, Load-enabled excess-generation Utilisation, and system Evolution。本地网页、API 与命令行使用同一个应用服务。

VALUE 把一次研究保存为一个可复现的 Research project。项目记录数据包、模型模块、年份、科学参数和输出设置。运行时，后端按项目中选定的模块执行真实 PSM 和 CEM，不会调用一个与界面选择无关的固定脚本。

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

公开 CEM 保留兼容 ID `force-cem-v1`。它是从 Scheme C 研究代码提炼出的模块化实现，保留 agent 投资和 planning pipeline 的研究结构，但不是 Scheme C 历史内核的逐数值复刻。保留的 Scheme C 代码只用于对照，不能在 Research project 中作为 PSM 选择。

当前版本不包含 AC 最优潮流、完整机组组合或爬坡约束，也不声称 CEM 是全局最优的多年扩张模型。DC 验证不能被外推为 AC 或输电扩张模块已经成为科学基线。

## 2. 安装要求

已验证的环境是：

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
py -3.10 scripts\doctor.py --capability force-native
```

检查结果会明确指出 Python、Node.js、依赖、端口、磁盘或数据目录中的问题。更完整的安装说明见 [INSTALLATION.md](INSTALLATION.md)。

## 3. Castle 101：前半小时怎么学

第一次接触 VALUE 时，先不要导入研究数据。Castle 是随软件提供的 CC0-1.0
合成教学系统，但它走的是正常运行路径：保存不可变 Study、冻结输入、调用所选
PSM 与 CEM、写市场和规划结果，再把系统推进到下一年。网页不会读取一份事先
准备好的结果冒充模型运行。

1. 汇报前先双击 [check-castle-demo.cmd](../check-castle-demo.cmd)，看到最后一行
   `READY` 再继续。
2. 双击 [start-value.cmd](../start-value.cmd)，在
   `http://127.0.0.1:8800` 选择 **Learn: Castle 101**。
3. 阅读系统卡片，点击 **Load Castle Study**，进入 **Review**，保存页面显示的
   精确 Study revision。
4. 点击 **Run Castle tutorial**。查看各期报价和出清、未利用 VRE、储能行为，
   以及 2026 年合成光伏项目的投产事件。
5. 回到 Learn，点击 **Create legacy-tariff Study**。运行这个 Study，在比较面板
   勾选两次教学运行，然后导出 JSON。

正确情况下只有 `module.storage_cost` 发生变化。Castle 每个模型年只有 48 个
半小时，因此它用来讲时序、PSM–CEM 交接和可审计结果，不用来估算英国全年
成本或碳排放。比较页面会保留模块身份，但主动隐藏年度成本和碳差值，避免把
短教学时钟包装成年度结果。

配套材料包括[中文教学手册](tutorial/CASTLE_101_ZH.md)、
[英文教学手册](tutorial/CASTLE_101.md)、
[一页检查卡](tutorial/CASTLE_101_QUICK_CARD.md)、
[Stuart 演示提纲](tutorial/STUART_DEMO_RUNBOOK.md)和
[六页打印版 PDF](../output/pdf/VALUE_Castle_101_guide.pdf)。完成 Castle 后，再按
下文接入真实研究数据。

## 4. 数据存放位置

源代码目录中的既有安装默认继续使用 `.gridform`。全新安装默认把本地状态放在 `%LOCALAPPDATA%\FORCE`。也可以在启动前设置 `FORCE_DATA_HOME`：

```powershell
$env:FORCE_DATA_HOME = "D:\FORCE-Research"
.\scripts\start-local.ps1
```

该目录保存：

- `data-packs`：数据包 manifest 和已导入对象
- `objects/sha256`：按内容哈希保存的输入对象
- `projects`：Research project 及其不可变 revisions
- `runs`：运行状态、checkpoint 和结果
- `archives`：已归档运行的完整审计包
- `trash`：可恢复删除区

不要把个人研究数据放入 Python package，也不要把本地英国数据包直接提交到 Git。

## 5. 第一次研究运行

如果还没有本地数据包，可先安装 CC0 合成示例：

```powershell
py -3.10 scripts\install_synthetic_pack.py
```

也可以打开 **Data** 页面，在 **Install a FORCE data pack** 中选择数据维护者
提供的 `force.data-bundle/v1` ZIP，阅读并确认其中的许可与署名记录后安装。
浏览器只把文件流式传给本地服务；后端在同一磁盘的临时目录检查安全路径、
解压上限、逐对象 SHA-256、manifest、权利记录和 25 个语义接口，全部通过后
才原子写入。上传阶段取消或任一检查失败，都不会改变已有数据包，临时文件会
被清理。安装后不再保留 ZIP 的第二份副本；不同内容必须使用新的版本化 pack ID。

然后按以下顺序操作：

1. 在 Data interfaces 选择数据包，确认所有 required inputs 已就绪。
2. 在 Model modules 查看可执行模块及其输入、输出和契约版本。
3. 在 Studies 的第一步填写名称、研究目的、年份和数据包。
4. 在 **System domain** 选择单节点、reference DC 或实验性 AC feasibility；
   必需的 contract extension 由后端解析。
5. 在 **Optional domains** 按需加入 hydrology 或 transmission expansion，
   并对每个实验版本作明确确认。
6. 在 **Model chain** 核对或替换兼容的 PSM/CEM 实现。
7. 在 **Review** 核对条件数据、有效参数和 graph SHA-256，再保存不可变 revision。
8. 进入 Run centre，先执行 Check readiness。
9. 新数据或新模块先运行 Two-period wiring check，再运行 Two-year smoke test。
10. 接线检查通过后，运行两个完整年度。完整十年研究应在年度投资与下一年注入审计通过后再开始。

合成数据只能验证接口、安装和运行链路，不能支持英国电网科学结论。

## 6. 各页面分别管理什么

### Overview

Overview 显示所选数据包、可用模块、Python runtime 和年度 PSM/CEM 链。这里也列出当前模型支持的科学范围。

### Data interfaces

一个数据包将来源不同的文件映射到稳定的语义角色。PSM 角色包括需求、天气、机组、VRE profile 和进口报价。CEM 角色包括 REPD 项目、CAPEX/FOM、policy cost、planning success 和技术寿命。页面会根据当前 draft 或已保存 Study，动态增加 Network、AC feasibility、Hydrology 和 Network expansion 分组；模板与预览调用的也是 preflight 使用的 canonical adapter。页面顶部可以安装完整的非可执行数据包，并显示文件大小、上传进度、验证阶段和精确错误代码。

上传 Replace 只会创建新的本地数据对象和 binding revision，不会修改原始文件。每个 binding 记录相对 URI、格式、单位或映射、SHA-256 和来源信息。运行开始时会冻结这些信息。

### Model modules

该页面显示模块 registry 中真正可以执行的 Python 实现。当前公开 slot 是：

- `psm`
- `storage_cost`，只适用于报价型 PSM
- `pipeline`
- `vre_cap`
- `storage_cap`
- `investment`
- `transition`
- `network_expansion`（可选）

模块卡片中的 ID、版本、contract、输入和输出会进入运行身份。模块 ZIP 与 extension ZIP 使用两套独立的事务式安装流程；extension 安装成功不等于已在 Study 中启用。外部模块只有通过 conformance 检查后才会出现在这里。

#### 安装别人编写的模块

打开 **Modules** 页面顶部的 **Install a model module**：选择建模者提供的 `force.module-bundle/v1` ZIP，勾选可执行代码信任确认，再点击安装。FORCE 会在临时目录检查文件清单与 SHA-256、路径穿越、manifest、Python entry point、槽位/contract、必需方法和最小 conformance fixture；全部通过后才原子写入模块目录并立即刷新 Studies 下拉框。

安装成功不代表科学方法已经验证。先建立新的 Study revision，运行 two-period wiring check，再做完整年度测试。内置模块不能被覆盖或禁用；已被 Saved Study 引用的外部模块也不能直接禁用。外部源码按模块/版本分目录保存，但仍在 FORCE Python 进程内运行。安装器不联网、不运行 `pip`、不接受原生二进制。

开发者从 `examples/external_module_bundle` 复制模板，并用 `scripts/build_module_bundle.py` 构建确定性的 ZIP。每个包必须包含 `force-bundle.json`、`force-module.json`、`src/`、`LICENSE`，可选 `README.md`。

### Research projects

Research project 管理研究的组成和科学身份，不管理任意桌面绝对路径。保存项目会创建 append-only revision。修改显示名称不会改变科学身份；修改数据、模块、年份或参数会创建新的 revision 和 SHA-256。

### Run centre

Run centre 负责 preflight、物理域输入预览、启动、进度、结果、checkpoint 恢复、取消、归档、导出和情景比较。关闭网页不会停止后台模型。

### Audit

Audit 页面按需读取 planning project、commissioning event、市场周期、成本账本、碳账本和 provenance。大表保存在 SQLite、JSONL 或 NPZ 中，不会全部塞入主运行页面。

### Network & water

该页面只读取完成运行中已有的 typed artifact，显示 DC 节点平衡、节点价格、
支路流量与拥塞、AC feasibility 状态，以及输电扩容事件链。它不会在 React 中
重新求解。若普通年度路径没有写出可索引的 natural-flow hydrology artifact，
水文结果会明确显示 `not_evaluated`，不会由前端猜一个数。

## 7. 运行模式

| 模式 | 实际执行 | 适合用途 | 可以解释年度经济性吗 |
| --- | --- | --- | --- |
| Two-period wiring check | 一个年份的两个半小时 | 数据和模块接线 | 不可以 |
| Two-year smoke test | 两个年份，每年两个半小时 | PSM 到 CEM 再到下一年的状态传递 | 不可以 |
| Run two full years | 两年各 17,520 个半小时 | 年度成本、投资、投产和下一年注入 | 可以 |
| Run complete study | 项目配置的全部年份 | 正式研究情景 | 可以，但仍受模型范围限制 |

Preflight 会检查 Python capability、模块兼容性、25 个数据接口、参数、输出目录、磁盘余量和预计运行规模。不要在 preflight 有 error 时强行启动。

## 8. PSM 和储能定价选择

### Scheme C derived bid-at-cost PSM

`scheme-c-psm` 是当前 FORCE bid-at-cost 市场。选择该 PSM 时必须选择一个 `storage_cost` 模块。

`dynamic-annual-storage-cost` 在第一年按技术能够满负荷运行的设计利用率初始化。后续年份把年化项目成本按上一年实际售电量和售电加权储存时间回收。循环折旧只作用于 battery，pumped hydro 和 hydrogen 没有该分量。`storage.cost.utilisation_floor_fraction=0` 保留论文中的精确零下限解释。研究者可以另外建立带利用率下限或平滑分母的敏感性情景。

`scheme-c-legacy-storage-tariff` 使用历史 Scheme C tariff 公式。它用于受控对比，不代表整个模块化模型能够逐数值复刻保留内核。

`user-formula-storage-cost` 允许用户用批准变量编写受限算术公式。公式不执行任意 Python 代码。

Run centre 的 Clone a storage-pricing experiment 会复制项目，只替换储能定价模块。数据、年份和其他模块保持不变，适合做可解释的政策对比。

### Perfect foresight LP

`force-perfect-foresight-lp` 是另一种 PSM。它使用 SciPy/HiGHS 集中联合优化发电和储能，不使用 storage offer cost 模块。该模块需要 solver capability。它与 bid-at-cost agent pricing 回答不同研究问题，不应把两者当作同一个 tariff 的两个参数值。

独立 PuLP/CBC oracle 已在 24 小时、168 小时和随机凸算例上验证 perfect foresight LP，也验证故意破坏能量平衡、效率、SOC、终端状态和进口约束时测试会失败。该验证不把 FORCE 的顺序性市场规则重新定义成一个全局 LP。

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

主系统成本使用 `force.cem-system-resource-cost/v1`：

```text
投产资产的年化 CAPEX 和 FOM + 物理运行资源成本
```

GBP/MWh 使用 served demand 作为分母。市场结算、政策转移、储能 bid recovery、未投产 pipeline commitments 和期末残值是独立账目，不会再次计入 system resource cost。

运行页面显示适合快速阅读的年度汇总。详细 cost ledger 保存在 `ledgers/annual-cost-ledger.json`。operational cost 为 0 只能在确实没有物理运行成本且账本可对账时出现。完整英国年度运行若显示 0，应视为错误并检查运行模式、成本 activity 和 ledger status。

## 11. 碳结果

每个原生年度运行固定使用一个 carbon factor scenario：

- `force_current_authoritative_v1`
- `scheme_c_reproduction_2026_07_18`

碳账本可以包括火电直接排放、进口电、当地新增设备隐含排放和储能生命周期排放。只有 activity 和 factor 都存在时才计算。缺少证据时状态是 `not_evaluated`，不会静默写成 0。

JSON 和 SQLite 碳账本必须逐年一致。详细结果位于 `ledgers/annual-carbon-ledger.json` 和 `ledgers/annual-carbon-ledger.sqlite`。

Scheme C reproduction 情景有不同边界。历史 storage scalars 40/50 没有已确认的物理单位，因此 FORCE 返回 null total、`not_physically_interpretable` 和 `legacy_storage_scalars_have_no_declared_physical_unit`。系统不会把该历史数值改名为 tCO2e，也不会显示成 0。

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

## 13. 取消、恢复、归档和删除

- Request safe cancellation 写入取消请求。原生运行在下一个完整年度 checkpoint 边界停止。
- Resume from verified annual checkpoint 只对 failed 或 cancelled 运行开放。数据、项目 revision、参数、模块和实现哈希必须与 checkpoint 一致。
- Archive 先生成并验证 complete audit ZIP，再把运行标记为 archived。
- Restore archive 会验证 ZIP 后恢复运行记录。
- Prepare audit bundle 生成可下载的审计包。
- Move to trash 要求输入完整 run ID。它把目录移入可恢复 trash，不会立即永久删除。

每个 Run 的模型 worker 持有 `<run>/worker.lock` 租约。关闭 VALUE 不会停止正在运行的 worker：停止提示会列出仍在后台运行的 Run，下次启动时 VALUE 通过租约接管监督。worker 退出或消失时，Run 会在几秒内（或在下次启动时）转为 failed（若已请求取消则为 cancelled），错误码为 `GF_WORKER_EXITED` 或 `GF_WORKER_LOST`，之后可以 Resume 或移入回收站。旧版 VALUE 启动的 Run 不一定能确认存活（`worker_liveness: unverifiable`）；Mark lost 需要输入完整 run ID，并且只有在 Run 目录 15 分钟内没有任何变化时才会接受。同一个数据目录只能有一个 VALUE 后端，第二个会以退出码 3 停止，不改动任何内容。

Move to trash 先移动目录，再只在回收站中的副本里记录 `deleting`；移动失败时 Run 保持原状。磁盘预留只由活动 Run 持有，且只计尚未写出的输出；已结束的 Run 按实际字节计（硬链接只计一次）。移入回收站会释放配额，归档不会。

不要手工复制某一个 checkpoint 到另一个情景。即使年份相同，科学身份不一致也必须拒绝恢复。

## 14. 情景比较

Run centre 可以选择 2 到 6 个完成的年度运行，并导出 JSON 或 CSV。接线检查和 smoke run 会被排除。

比较器先检查年份、数据、非储能模块、成本定义、碳因子、终端政策和 denominator。只有定义一致时才显示无标签数值差。动态储能和 legacy tariff 的受控克隆可以直接比较。模块化 FORCE 与保留 Scheme C 使用不同 system-cost 定义时，只能做带标签的描述性比较。

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

25 个内置角色和格式见 Data interfaces 页面。外部 adapter 示例位于 [examples/external_modules/README.md](../examples/external_modules/README.md)。

## 16. 接入新模型模块

先用总教程
[`BUILD_YOUR_OWN_MODEL_101_ZH.md`](BUILD_YOUR_OWN_MODEL_101_ZH.md)
判断应当替换 data pack、Study parameter、现有 module，还是升级平台 contract。
从零编写、打包和测试一个具体 module 的逐步教程见
[`MODULE_DEVELOPER_101_ZH.md`](MODULE_DEVELOPER_101_ZH.md)。其中包含
data/parameter/module/架构的选择方法、七个可替换 slot、module 替代原理、
`module.zip` 的准确格式、manifest、入口模板和从单元测试到多年运行的分层门槛。

外部模块是安装好的 Python package，包含 `gridform.module/v2` manifest。manifest 至少声明：

- 稳定 module ID、slot 和 semantic version
- contract version
- typed inputs 和 outputs
- state read/write sets
- parameters、capabilities 和 determinism
- 生成的 artifacts

外生 demand profile 通常应进入 data pack/adapter；storage-cost、扩张、投资、
planning 和 transition 算法使用对应 slot。DC/AC 的求解算法属于完整 PSM；
0.6 版本已经提供 solver-neutral network contract、拓扑/节点需求条件角色、
reference DC PSM 和实验性 AC-feasibility data contract。替换型 network PSM 应
声明并组合这些 capability/extension。当前没有对应 slot 的新生命周期阶段仍然
需要显式 extension 和平台级验证，不能
伪装成其他 module。不要在 Scheme C compatibility 代码里增加隐藏开关。外部模块
必须先安装并通过 conformance tests。

## 17. 命令行运行

Research project JSON 也可以通过公开 application service 运行：

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

- Research project JSON 和 revision SHA-256
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

### 浏览器显示 connection refused

确认地址是 `http://127.0.0.1:8800`，然后运行 `start-value.cmd`。若仍失败，运行 environment doctor，并检查 `.gridform/frontend-error.log` 或 `%LOCALAPPDATA%\FORCE\frontend-error.log`。

### 页面显示 Open VALUE from its launcher

页面不是经启动器打开的：用了其他主机名、另一份安装的书签，或网页服务读取的数据目录与 API 不同（HTTP 421/403 也是同一原因）。停止 VALUE，再用启动器启动。`python -B scripts/verify_local_security_boundary.py` 可检查正在运行的安装：所有跨站、DNS rebinding 和无会话探测都被拒绝时输出 PASS。

### 页面显示 Python 3.12 不兼容

停止旧服务后重新运行 `start-value.cmd`。启动器优先使用项目 `.venv`，其次使用 Python 3.10。VALUE 目前不接受未经验证的 Python 3.12 科学运行。

### 25 个接口齐全但 preflight 失败

接口数量只表示文件已绑定。preflight 还会检查单位、时间范围、checksum、模块 capability、参数和磁盘。按错误中的 corrective action 修正，不要把 warning 或 error 改写成成功。

### 长跑中断

不要删除输出目录。先确认 `checkpoints-v2` 中最后一个 `state-YYYY.json` 完整，再从 Run centre 的 Resume 按钮恢复。恢复会重算尚未提交的当前年度，但不会重算已经 checkpoint 的年份。

### 诊断报告 stray bytecode

这是安装目录 `__pycache__` 中的 Python 字节码。VALUE 不会读取它们（每个解释器都使用新建的空 `pycache_prefix`）。运行 `diagnose-value --repair-bytecode` 可把它们移入 `state/quarantine/`；安装目录可写时，启动也会自动这样做。

### 结果与保留 Scheme C 不同

先确认比较的是同一数据、年份、碳因子、储能政策和 system-cost 定义。FORCE-CEM v1 有已声明的结构修正，因此 legacy tariff 只复刻储能报价公式，不保证完整轨迹相同。

### 运行很慢

完整英国年度有 17,520 个半小时，资产和 planning components 会逐年增加。先关闭详细 generation trace，检查 `performance.json`，并用 preflight 估计磁盘和时间。不要用 two-period smoke 的耗时外推十年结果。

## 20. 科学解释边界

FORCE 可以支持以下表述：模型按照记录的 bid-at-cost 和 planning 规则执行；能量、成本、碳和项目账本通过相应审计；新增资产通过 CEM 投产并进入后续实际 PSM；指定情景的结果可以在固定定义下比较。

当前证据不支持以下表述：模型包含英国境内输电约束；模型执行完整 unit commitment；agent market 是全局最优 dispatch；CEM 是完美预见的全局最优扩张；legacy tariff 情景精确复刻 Scheme C；任何本地英国数据都可以随软件一起再分发。

详细数学定义和证据边界见 [MATHEMATICAL_REFERENCE.md](MATHEMATICAL_REFERENCE.md) 与 [VALIDATION_AND_CLAIMS.md](VALIDATION_AND_CLAIMS.md)。
