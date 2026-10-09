# VALUE 发布与上传计划

发布版本：VALUE 0.7.0-alpha.1，2026-10-09。

[value.ac](https://value.ac) 提供安装、数据、方法学与开发入口。模型在用户自己的计算机上运行；[GitHub VALUE 项目](https://github.com/hanzohanzhe/Value) 托管源码、完整安装包和研究数据。

| 内容 | 版本 | 获取入口 |
| --- | --- | --- |
| 源码、SDK、教学数据和官网源稿 | source-2026-10-09 | [源码发行](https://github.com/hanzohanzhe/Value/releases/tag/source-2026-10-09) |
| Linux、Windows、macOS Intel、macOS Apple Silicon 完整安装包 | Full 2026-10-09-a1 | [软件发行](https://github.com/hanzohanzhe/Value/releases/tag/value-2026-10-09-a1) |
| 中英文九章方法学，Word、PDF、离线 HTML | 0.4.1，2026-10-09 | [方法学](https://value.ac/zh/methodology/) |
| GBP1 public2、R029 public2、GBP1 public2 23 区研究套件 | value-data-2026-10-09 | [新数据发行](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-09) |
| GBP1 public1，供论文复现口径使用 | value-data-2026-10-04 | [数据归档](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-04) |

## 安装与数据选择

Full 随附 Python、Node、科学依赖和两个 VALUE 101 教学数据包。安装到新的空目录，启动后先完成 VALUE 101。平台验收记录以[软件发行](https://github.com/hanzohanzhe/Value/releases/tag/value-2026-10-09-a1)为准；Windows 与 macOS 为实验性版本，原生验收、签名与公证列入后续发布。

修正口径是默认选择。全国研究通过 Data → Install a VALUE data pack 导入 GBP1 public2 或 R029 public2；23 区网络研究通过 Data → Install the VALUE-UK research suite 导入 public2 套件。论文复现口径使用 GBP1 public1。网络模块在修正口径下运行。

public2 互联线潮流符号为 declared_unverified。23 区套件把火电、核电、水电、储能和进口放入 ENGLAND_FALLBACK，分区结果的空间分布只具指示意义。研究结论按实际配置、输入和时间范围进一步验证。

## 发布流程

1. 接入方法学 0.4.1，冻结模型和用户文档，按发布白名单导出干净源码。
2. 上传新数据与方法学文件，核对远端下载文件。
3. 从冻结的干净源码重建应用和四平台 Full，记录构建来源；完成 Linux 空目录断网安装、VALUE 101 与停止检查。
4. 把实际下载信息和平台验收结果写入官网，更新四类任务指引、数据选择、版本与引用。
5. 同步最终官网源码并生成完整公开源码快照；核对冻结的运行文件未变，发布源码标签和网站。

四类路径为 Reproduce from existing data、Add your new data、Edit a module、Add a new function to VALUE。对应关系见[发行映射](release/release-map.json)。软件 Apache-2.0，作者文档 CC BY 4.0，合成教学数据 CC0；研究数据保留各自许可与署名。
