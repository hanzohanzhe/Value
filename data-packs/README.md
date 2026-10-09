# 数据 / Data packs

软件使用 Apache-2.0；数据按每个包和对象的许可使用，软件许可不代替来源数据条款。许可范围见 [DATA-LICENSING.json](../DATA-LICENSING.json)。

| 本仓库包含的包 | 用途 | 许可 |
| --- | --- | --- |
| [value-101-baseline-v1](value-101-baseline-v1/) | 基础教学与输入映射 | CC0-1.0 |
| [value-101-network-v1](value-101-network-v1/) | 合成三分区网络教学 | CC0-1.0 |
| [value-synthetic-contract-pack-v1](value-synthetic-contract-pack-v1/) | 非英国合成契约夹具 | CC0-1.0 |

三个合成包保留原 ID、哈希与生成关系，不代表真实英国观测。Full 内置前两个；源码使用 `python scripts/install_synthetic_pack.py --value-101-only` 安装教学包。

真实研究输入从数据 Release 下载。VALUE 0.7.0 中：修正口径（默认）的全国研究使用 [value-data-2026-10-09](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-09) 中的 R029 public2 或 GBP1 public2（data bundle，Data → Install a VALUE data pack）；23 区网络研究使用同一发行中的 GBP1 public2 研究套件 `VALUE-UK-GBP1-23zone-research-suite-public2-2026-10-09.zip`（Data → Install the VALUE-UK research suite）；论文复现口径使用 [value-data-2026-10-04](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-04) 中的 GBP1 public1，见[实物清单](../docs/release/public-data-assets.json)。value-data-2026-10-04 中的 GBP1 public1 研究套件只适用于 0.6.0-alpha.2；23 区独立网络组件在 0.7.0 中经由 public2 研究套件接入；11 区 family 先解压选择组件，按包内 Python 安装指引接入，不能将整个 family 当 national 数据包上传。

`public1` 修订单位标签、路径和分发元数据，保留全部数值绑定原字节。GBP1 与 R029 保留原 pack ID，实际 manifest SHA 另行记录。GBP1 的原核政策已在实际短运行中确认；R029 public1 与 0.6.0-alpha.2 的普通 VALUE 链兼容（0.7.0 的修正口径改用 R029 public2），不用于论文复现口径。11 区仅发布获准的计算网络组件，未公开原 CP30 轮廓、原 workbook 或完整年度重放目录。详见[发布计划](../docs/PUBLICATION_PLAN.md)。

需求、互联线、天气、REPD 等来源对象保留 NESO、CC BY、OGL 等许可与署名。运行参数编译来源见 [runtime parameter notices](../publication/RUNTIME_PARAMETER_NOTICES.md)。每个包都有 RIGHTS、ATTRIBUTION 或明确来源说明；短任务检查不代替科学验证。
