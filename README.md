# VALUE

VALUE (Variable renewable electricity Allocation, Load-enabled excess-generation Utilisation, and system Evolution)：可变可再生电力的分配、通过负荷利用富余发电，以及电力系统演化。

VALUE 连接电力系统的半小时运行与年度投资，研究发电、储能、网络和资产演化。Power-system operation and annual investment in one modelling workspace.

**从 [value.ac](https://value.ac) 开始，或直接下载 [完整安装包](https://github.com/hanzohanzhe/Value/releases/tag/value-2026-10-09-a1)。** 模型在自己的计算机上运行；Full 自带 Python、Node、科学依赖和两个 VALUE 101 教学包。

1. 选择 Windows、macOS 或 Linux 包，解压后运行包内安装器。
2. 启动 VALUE，在 **Learn → VALUE 101** 创建 Study，先运行一天教学任务。
3. 根据目标选择下面的导引。安装入口和平台要求见[安装说明](docs/DEPLOYMENT.md)。

| 你要做什么 | 从哪里开始 |
| --- | --- |
| Reproduce from existing data | [VALUE 101 教学与数据导引](docs/tutorial/VALUE_101_TO_VALUE_UK.md) |
| Add your new data | [数据包](data-packs/README.md)与[自建模型导引](docs/BUILD_YOUR_OWN_MODEL_101_ZH.md) |
| Edit a module | [模块开发导引](docs/MODULE_DEVELOPER_101_ZH.md) |
| Add a new function to VALUE | [扩展与项目结构](docs/REPOSITORY_STRUCTURE.md) |

源码 0.7.0-alpha.1 的界面已整体翻新：每个页面有独立地址，侧栏分 Start、Work、Results 三组，界面可在英文与中文之间切换（默认英文）。

各平台的实际验收记录见[下载页](https://value.ac/zh/releases/)。Windows/macOS 为实验性版本，原生安装验收、签名与公证列入后续发布。科学结论结合具体配置、输入与研究时间范围判断。

[中英文方法学](docs/methodology/README.md)为 **0.4.1（2026-10-09）**，对应 VALUE 0.7.0-alpha.1，数据与实现依据日期为 **2026-10-09**；网页、Word、PDF、离线 HTML 从同一套 VALUE 正文生成。真实研究输入由[独立数据发行](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-04)提供，按包内来源和许可使用。R029 public2 与 GBP1 public2 随 0.7.0 在[数据发行 value-data-2026-10-09](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-09) 发布，只用于修正口径（默认），不适用于论文复现口径。23 区网络研究在 0.7.0 中使用同一数据发行中以 GBP1 public2 为底包的研究套件 `VALUE-UK-GBP1-23zone-research-suite-public2-2026-10-09.zip`。论文复现口径使用 value-data-2026-10-04 中的 GBP1 public1。

应用版本为 **0.7.0-alpha.1**（Python `0.7.0a1`），Full 批次为 **2026-10-09-a1**。修正口径是默认选择，论文复现口径保留相应历史设定；具体区别见 [CHANGELOG](CHANGELOG.md)。Application version 0.7.0-alpha.1; Full installers include the application, Python, Node and VALUE 101 inputs.

开发者查看[源码启动与网站部署](docs/DEPLOYMENT.md)、[项目结构](docs/REPOSITORY_STRUCTURE.md)和[发布计划](docs/PUBLICATION_PLAN.md)。源码版本 `source-2026-10-09` 与 Full 批次 `2026-10-09-a1` 分别识别，对应关系见[发行映射](docs/release/release-map.json)。

**许可**：软件 Apache-2.0，作者文档 CC BY 4.0，三个合成数据包 CC0；第三方数据保留具体条款。科研、教学和商用均可按软件许可开展，论文引用属于建议。详见 [LICENSING.md](LICENSING.md)。本仓库仅发布 VALUE。
