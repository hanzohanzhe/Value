# VALUE 101 中文教学手册

## 在 VALUE 中建立第一个模型

VALUE 101 是一个用于学习真实 VALUE 工作流程的合成电力系统。它调用正式的数据契约、模块注册表、PSM、CEM 年度状态转换和结果工件，不是另写的演示内核，也不读取预先计算好的答案。

教学包提供两条运行路线：48 个半小时的单日 PSM 用来学习逐期竞价与调度；完整两年路线则对 2025 和 2026 各运行 17,520 期，并执行年度 CEM 链。合成数据不是英国电力系统证据。

合成系统包括太阳能、陆上风电、海上风电、CCGT、进口电、电池储能和 planning pipeline。它借用了英国电力系统常见的资源类型，但所有数值都是教学数据，采用 CC0-1.0。

## 五个基本概念

Data 是模型收到的需求、天气、机组、成本、政策和规划记录。Data Pack 把这些记录绑定到命名接口，使 VALUE 不依赖某个固定文件名或电脑目录。

Study 是保存下来的研究配置，记录年份、一个 Data Pack、所选 Modules、参数和运行设置。每次保存都会产生不可变的版本。

Modules 是可执行的模型部分。基线链路会进行市场出清、储能定价、投资判断、planning pipeline 推进、扩建上限处理，并生成下一年的初始状态。

Run 是对某一个确定 Study 版本的执行。创建 Study 不会自动运行。Run 接收保存后的模型图，并写出自己的状态和证据。

Results 是 Run 保存的结果工件，包括竞价、接受发电量、储能流量、未利用 VRE、成本和碳账本、规划事件、哈希与 provenance。浏览器读取这些工件，不会重新计算竞价，也不会把短时序结果年化。

## What Check readiness resolves（Check readiness 会解析什么）

`Check readiness` 是保存 Study 之后、启动 Run 之前的 preflight。它验证所选的不可变 Study revision，解析准确的已安装 Module 版本，检查所有必需 data role、单位和时间顺序，核对 Data Pack 与 Module 的身份和哈希，估算 periods、磁盘、峰值内存和运行时间，并在执行前冻结 declared input snapshot。任何必需输入无法解析时，VALUE 都会 fail closed，并给出缺失或不兼容的 role 以及修正办法。

对于 **single node** Study，保存的 revision 已明确记录 `data_pack_id`。Preflight 不会另行搜索 Network Pack；它只验证并冻结已声明的 Data Pack、Modules、参数和 run clock。互联线仍是基础 Data Pack 中的边界报价，不会引入内部输电网络数据集。

对于 **zonal** Study，保存的 revision 记录基础 Data Pack、zonal System domain、network extension 和 `zonal_demand_mode`。Preflight 会解析一个兼容的已安装 Network Pack，并验证准确的 pack ID、manifest/hash、zones、cutsets、时变 ratings、zonal demand、空间映射和模型 clock。它还会明确全国需求是由基础研究包控制、Network Pack 只提供分区权重，还是由 Network Pack 提供绝对分区需求。冻结后的 input snapshot 必须保留准确的 Network Pack ID 和 hash。VALUE 不得静默选择任意 pack，也不得自动退回铜板模型。

检查前，`Network pack: Check readiness to confirm` 表示身份尚未确认。检查成功后显示 `Network pack: <pack-id> · verified`。检查失败时，界面必须指出缺失或不兼容的 role 以及 corrective action。**resolved during preflight** 的意思是“尚未确认”，不是缺失、随机选择，也不是在 Run 期间下载。

```text
Single node:
Saved Study → declared Data Pack → validate and freeze

Zonal:
Saved Study → declared base Data Pack
            → resolve compatible Network Pack
            → validate alignment
            → freeze both identities
```

## 安装并打开 VALUE

1. 在 Windows 10 或 11 中双击 `VALUE-Setup.exe`。
2. 安装窗口会显示文件解压、程序设置和本地服务启动的进度。进度完成前不要关闭窗口。安装器只使用当前 Windows 账户，不申请管理员权限。
3. 等进度条达到 100%，并让浏览器打开 [http://127.0.0.1:8800](http://127.0.0.1:8800)。如果浏览器仍未打开，双击桌面或开始菜单中的 `VALUE`。
4. 查看左下角服务状态，应显示 Python 3.10 和本地模型服务 ready。

请把 VALUE 安装在自己的电脑上。VALUE 假定一台电脑只有一个使用者：不支持共用机房电脑或远程桌面服务器，因为同一台机器上的其他用户可能访问到你的本地 VALUE（见 `SECURITY.md`）。

下载包已经包含 Python、Node、锁定依赖、应用程序、两个合成数据包和英文指南。下载完成后，不需要 Git、命令行、外部 Python 或 Node、管理员权限，也不需要联网。

应用状态保存在 `%LOCALAPPDATA%\VALUE\state`。关闭浏览器不会停止本地服务。使用完毕后，在 Windows 开始菜单选择 `Stop VALUE`。`Uninstall VALUE` 会删除此 VALUE 安装及其应用状态。旧的 `%LOCALAPPDATA%\VALUE-101` 试用版是独立的可选安装，不会迁移，且可以继续保留。

## 运行基线

进入 `Learn`，点击 `Meet the five building blocks`。Read 按钮会在 VALUE 内部打开课程内容。阅读完成后再建立模型。

点击 `Create baseline Study`。VALUE 会保存一个普通 Study：

| 字段 | 保存值 |
| --- | --- |
| Name | `VALUE 101 baseline` |
| Years | 2025 到 2026 |
| Data Pack | `value-101-baseline-v1` |
| Market | 全国单节点 |
| Period length | 30 分钟 |
| Full model year | 17,520 期 |

点击 `Run one market day` 时，VALUE 只读取 2025 年前 48 个半小时并调用一次正式 PSM。该路线记录完整竞价、接受电量、储能流量和未利用 VRE，不运行年度投资、扩建上限、规划准入或状态转换。

点击 `Run complete two-year model` 时，VALUE 先出清 2025 年全部 17,520 期，再执行扩建余量、投资、规划推进与准入并写出 2026 年初始状态；随后出清 2026 年全部 17,520 期并执行 2026 年 CEM。只有这条路线可以用于查看年度收入、成本回收、投资和规划结果。

两年路线保存紧凑的逐期汇总、物理调度、储能和未利用 VRE；需要完整 auction-level bidding 时使用单日路线。

## 基线模块链

Study 以 ID 记录每个执行模块：

| Study 位置 | Module ID | 本练习中的作用 |
| --- | --- | --- |
| PSM | `value-bid-at-cost-psm` | 逐半小时执行 bid-at-cost 市场出清 |
| Storage cost | `dynamic-annual-storage-cost` | 用动态年平均项目成本回收方法形成储能报价 |
| Investment | `agent-investment` | PSM 年度结束后按业主判断投资项目 |
| Pipeline | `planning-pipeline` | 推进项目规划阶段并记录结果 |
| VRE cap | `vre-expansion-cap` | 应用太阳能与风电扩建限制 |
| Storage cap | `value-storage-expansion-policy` | 应用储能扩建限制 |
| Transition | `value-annual-state-transition` | 生成下一模型年的初始状态 |

这些是普通 VALUE Study 使用的公开模块契约。教学路线不会绕过它们。

## 25 项 Data Pack 契约

`value-101-baseline-v1` 绑定 25 个必需角色。运行前，VALUE 会检查角色、格式、哈希、许可和 provenance。教学包中的角色如下：

| 角色 | 格式 | 内容 |
| --- | --- | --- |
| `config.model_parameters` | JSON | 模型参数 |
| `costs.capital` | JSON | 资本成本假设 |
| `demand.forecast` | CSV | 每期预测需求，单位 MWh/period |
| `demand.real` | CSV | 每期实际需求，单位 MWh/period |
| `fleet.generators` | JSON | 发电、储能和进口资产 |
| `market.belgium.price` | CSV | 比利时进口价格 |
| `market.belgium.profile` | CSV | 比利时进口可用量 |
| `market.france.price` | CSV | 法国进口价格 |
| `market.france.profile` | CSV | 法国进口可用量 |
| `market.ireland.price` | CSV | 爱尔兰进口价格 |
| `market.ireland.profile` | CSV | 爱尔兰进口可用量 |
| `market.netherlands.price` | CSV | 荷兰进口价格 |
| `market.netherlands.profile` | CSV | 荷兰进口可用量 |
| `market.norway.price` | CSV | 挪威进口价格 |
| `market.norway.profile` | CSV | 挪威进口可用量 |
| `planning.success_rates` | CSV | 规划成功率输入 |
| `planning.timelines` | JSON | 规划阶段时间输入 |
| `policy.support` | JSON | 政策支持输入 |
| `profiles.vre_offshore` | CSV | 海上风电可用率 |
| `profiles.vre_onshore` | CSV | 陆上风电可用率 |
| `profiles.vre_solar` | CSV | 太阳能可用率 |
| `projects.repd` | CSV | 整理后的规划项目记录 |
| `source.repd_raw` | CSV | 为 provenance 保留的源规划记录 |
| `weather.solar` | NetCDF | 太阳能天气场 |
| `weather.wind` | NetCDF | 风电天气场 |

在 `Data` 页面可以查看接口绑定和源文件。完整 Data Pack 是一个科学输入，不是一堆互不关联的上传文件。

## 建立真实研究模型

VALUE 101 不提供点击按钮即替换研究数据或科学方法的情景玩具。真实修改通过正式契约进入：在 `Data` 中查看 25 项角色、单位和时钟，用 manifest 或 adapter 把自己的数据库映射为完整 Data Pack；在 `Modules` 中查看 slot 和 contract，用包含 `value-module.json` 与可导入 Python package 的 bundle 安装兼容实现；新增研究领域时，用 extension 声明条件数据角色、生命周期 hook、状态与结果工件。

安装完成后，在普通 `Studies` composer 的 `Advanced` 模式中选择新的 Data Pack、Module 或 extension，并保存成新的不可变 Study revision。

## 查看逐期市场与规划证据

在 `Market replay` 中查看每个半小时的报价、接受电量和出清结果。储能充电与放电是两种独立的物理流量。

在 `VRE & curtailment` 中查看可用、接受和未利用的可再生能源。单日路线只有 48 期；完整两年路线每年有 17,520 期。

在 `Inspect` 中查看 planning events 和 provenance。Run 会记录模块 ID、数据包 ID、工件路径和哈希。需要简短备案时，可以导出 completion report。

## Build from VALUE 101

点击 `Build from VALUE 101`。VALUE 会把教学配置复制到普通 Study composer，形成一份尚未保存的草稿。此时不会创建或运行模型。

普通 composer 允许建模者修改以下层次：

- 选择完整 Data Pack，或者安装适配其他数据库的 adapter；
- 在保持上下游契约的条件下替换一个兼容 Module；
- 修改年份和公开参数；
- 添加经过审核、带有条件数据角色和测试的 extension。

保存后，它就是普通的版本化 Study，不再依赖教学进度。拥有完整英国数据的建模者可以把数据映射到 25 项角色，并继续使用同一套 VALUE 模块。VALUE 101 本身不包含英国 research data 或 1000 TWh reproduction data。

`docs/MODEL_BUILDER_101.md` 说明三种开发路线：替换数据，替换一个或多个兼容模块，或者通过 extension 增加模型领域。

## 可选的 Network constraints & redispatch

该课程使用 `value-101-network-v1`，建立一对相互匹配的铜板 Study 和固定三区 Study。全国需求、机组、天气、bid-at-cost ahead market 与模型年份都保持不变。

两个 Study 都完整运行 2025–2026：每年 17,520 个半小时，随后执行相同的投资、扩建、planning 和年度 transition。CSV 文件出现 17,521 行时，其中一行是表头，实际仍是 17,520 个数值期，并不是少了一期或多了一期。

网络情景对 North、Central 和 South 应用无损 zonal transport 限制，再执行 pay-as-bid redispatch。结果记录走廊利用率、向上与向下 redispatch、网络增加及避免的弃电、load shedding、redispatch resource cost、结算和成本账本。

这是 zonal transport 与 redispatch 练习。它不是 DC 潮流、AC 潮流或 N-1 安全分析，也不包含输电扩建实现。它是可选的方法教学，不是经过验证的英国网络结果。

## 合成教学数据与英国研究数据

试用安装包只提供两个 VALUE 101 数据包：年度单节点基线，以及使用同一组全国输入的固定三区网络练习。它们是采用 CC0-1.0 的确定性合成数据，适合教学与自动测试。

英国 research pack 和 1000 TWh reproduction pack 使用本地保存、受数据权利约束的源数据与完整研究时序，因此不会进入这个安装包。它们的结果和科学主张必须与 VALUE 101 分开审核。

## 无法启动时

先使用 `Stop VALUE`，再启动一次 `VALUE`。不要从另一个文件夹同时启动第二套程序。

如果页面显示 **Open VALUE from its launcher**，说明它不是经 VALUE 自己的快捷方式打开的（例如旧书签或其他地址）：关闭页面，从桌面或开始菜单启动 `VALUE`。

如果显示 missing pack，重新运行 `VALUE-Setup.exe`。重复安装采用事务式替换，并保留 `%LOCALAPPDATA%\VALUE\state` 中的应用状态。

如果显示 occupied port，关闭占用 8800 或 8766 的其他程序。VALUE 不会终止不属于自己的进程。

安装与启动诊断日志位于 `%LOCALAPPDATA%\VALUE\diagnostics`。Run 证据与教学状态位于 `%LOCALAPPDATA%\VALUE\state`。

## 许可与署名

VALUE 源代码采用 Apache-2.0。文档采用 CC BY 4.0。两个合成教学包采用 CC0-1.0。每个 manifest 都记录 ID、哈希、来源说明和转换版本。
