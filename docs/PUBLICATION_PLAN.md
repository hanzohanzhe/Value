# VALUE 发布与上传计划

本计划执行日期为 2026-10-04。发行对象是 VALUE 电力系统运行与年度投资模型：软件 Apache-2.0，作者文档 CC BY 4.0，三个合成包 CC0，研究数据逐对象保留条款。原有私有研究引擎、混合方法学与旧 Git 历史不进入公开发行。

## 入口与实物

[value.ac](https://value.ac) 提供开始使用、安装、数据、方法学和开发指引；模型在用户本机运行。公开源码与大文件使用同一 [GitHub VALUE 项目](https://github.com/hanzohanzhe/Value)。旧仓库和网站项目留作私有归档，新项目从受审 VALUE 快照建立公开历史。

| 发行 | 交付内容 | 身份 |
| --- | --- | --- |
| [源码](https://github.com/hanzohanzhe/Value/releases/tag/source-2026-10-04) | 前后端、模型、SDK、三个合成包、参数与文档/官网源稿 | `source-2026-10-04` |
| [Full 安装包](https://github.com/hanzohanzhe/Value/releases/tag/value-2026-10-03-rc1) | Linux、Windows、macOS Intel/Apple Silicon，Python/Node/科学依赖内置 | `2026-10-03-rc1` prerelease |
| [方法学](https://github.com/hanzohanzhe/Value/releases/tag/methodology-0.3-2026-10-04) | 双语各九章，Word、PDF、离线 HTML 共六份 | `0.3`，修订 2026-10-04，科学依据 2026-10-02 |
| [研究输入](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-04) | GBP1 基础、23 区网络与套件，R029 数据，11 区网络组件与获准需求资料 | `public1` 元数据修订，原数值输入不变 |

应用继承元数据仍为 npm `0.6.0-alpha.2`、Python `0.6.0a2`；它们不代替源码、Full、数据与方法学的各自身份。每个 Release 提供实际文件、SHA256 与说明，不靠修改同一个版本号掩盖对象差异。

## 已执行的施工与检查

1. 将方法学集中到 `docs/methodology/zh` 和 `en`，网页与六份文件共用正文，保留公式、数值与单位。50 页中文和 46 页英文全部审阅。
2. 从白名单准备干净源码，不继承旧 Git 历史。找回原科学目录的权利账本，补齐九个缺失参数；全部十三个碳/储能/数值契约对象保留原字节，来源与边界记录在 `publication/runtime-parameter-rights.json`。
3. 核对四个 Full 的 2030 文件应用身份、运行源码、参数与第三方运行时通知。保留已验包的字节，单独记录文档、发布脚本与 doctoral package-data 修补，不冒称新文档树的精确重建。
4. 在独立源码环境安装锁定依赖、构建前端、构建含十三参数对象的 wheel，并完成一个一天教学任务。沿用 unchanged Full 的 Linux 离线安装与四角色结果，不重复全年或十年研究。
5. 逐对象审核数据、补齐间接依赖，形成合法完整的输入组件。修订错误单位标签和本机路径等元数据，保留数值绑定原字节。公开 GBP1/R029 的 pack ID 保持原身份，避免改变按 ID 选择的科学政策。
6. 上传真实资产，核对 GitHub 返回的大小与 digest，再启用官网链接。只对全新干净网站开放公开访问；旧网站及其混合历史继续私有。value.ac 绑定使用新网站的域名验证记录。

四类路径保持 `reproduce from existing data`、`add your new data`、`Edit module`、`add new function to VALUE`。操作与测试清单随 Full Release 提供，入口保持简明。

## 数据的准确边界

| 对象 | 发行与实际使用方式 | 实际检查与限制 |
| --- | --- | --- |
| GBP1 基础 | national data bundle，在 Data 导入 | 原需求数字实际为 MW；修正旧 MWh/period 标签。原 pack ID 保留；实际两期运行确认五核站 5958 MW 与禁止内生投资政策生效。 |
| GBP1 23 区套件 | research-suite，可从既有套件入口导入 | 基础、网络与两个模板实际 Full 导入通过；不称年度网络科学验收。独立网络包按包内 Python 安装方法使用。 |
| R029 | 保留历史输入字节的独立 data bundle | 当前 national 数据导入与普通 VALUE 链短任务可用。博士冻结链初始化存在核投资资格不兼容，未通过精确历史重现验收；不交付失败博士模板。 |
| 11 区网络 family | 解压后选取 33 个完整的网络组件之一，按 README 使用 Python 安装 API | 去除来源未明确授权的 CP30 轮廓，其他数值/计算字段保持原值，typed model 比较通过；代表组件安装通过。它不是完整的原年度研究套件，不能把 family ZIP 上传到 national Data 入口。 |
| 11 区需求资料 | 获准的独立需求来源组件与获取说明 | 补充资料，不是可直接导入的 data bundle。原 CP30 形状、原 ETYS workbook 和图像不随组件公开。 |

研究数字、计算政策和数据许可不是同一层要求。数据来源许可与编译对象署名随包保留；原始源出版物与原研究目录不一并公开。11 区原完整研究重放和 R029 博士冻结链修复属于后续科学兼容工作，不能用输入导入成功代替。

## 发行限制与后续维护

Linux Full 的离线安装、移动目录后启动/停止及四类短任务已有通过记录。Windows/macOS 只完成归档/架构/依赖检查，原生安装验收、签名与公证待完成，因此作为实验候选发布。所有短任务科学验证状态均为 `not_evaluated`。

公开前运行源码与 publication scope 扫描、官网构建/链接检查，核对实际远端资产 SHA、公开仓库和网站权限。后续仅在程序、输入、平台或声明变化影响结论时重做相关检查。方法学修改按同一源稿同步全部格式；实物状态见[发行映射](release/release-map.json)。
