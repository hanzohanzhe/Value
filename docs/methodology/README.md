# VALUE 方法学

修订版 **0.5，2026 年 10 月 12 日**。模型实现为 **VALUE 0.7.0-alpha.1**，数据与实现依据日期为 **2026 年 10 月 9 日**。

本目录保存 VALUE 中英文方法学的权威源稿。正文说明模型设定、方程、算法和输入数据；函数与数据文件名紧接其对应计算步骤。两版章序相同，网页、Word、PDF 和离线 HTML 使用同一套正文。

| 章节 | 中文 | English |
| --- | --- | --- |
| 1 | [模型框架](zh/introduction.md) | [Model framework](en/introduction.md) |
| 2 | [初始数据与输入处理](zh/datasets.md) | [Initial data and input processing](en/datasets.md) |
| 3 | [天气与可用出力](zh/core_weather.md) | [Weather and available generation](en/core_weather.md) |
| 4 | [运行与储能](zh/core.md) | [Operation and storage](en/core.md) |
| 5 | [全国市场出清](zh/national_alternatives.md) | [National market clearing](en/national_alternatives.md) |
| 6 | [年度核算与投资](zh/r029_cem.md) | [Annual accounting and investment](en/r029_cem.md) |
| 7 | [传输与网络约束](zh/transmission.md) | [Transmission and network constraints](en/transmission.md) |
| 8 | [完全预见调度与天然水文](zh/optional_modules.md) | [Perfect-foresight dispatch and natural hydrology](en/optional_modules.md) |
| 9 | [碳排放核算参数](zh/appendix.md) | [Carbon accounting parameters](en/appendix.md) |

下载：[中文 PDF](../../website/static/assets/methodology/VALUE_模型方法学_2026-10-12.pdf) · [中文 Word](../../website/static/assets/methodology/VALUE_模型方法学_2026-10-12.docx) · [中文离线 HTML](../../website/static/assets/methodology/VALUE_methodology_ZH_2026-10-12.html) · [English PDF](../../website/static/assets/methodology/VALUE_Model_Methodology_EN_2026-10-12.pdf) · [English Word](../../website/static/assets/methodology/VALUE_Model_Methodology_EN_2026-10-12.docx) · [English offline HTML](../../website/static/assets/methodology/VALUE_methodology_EN_2026-10-12.html)。

## 维护

先修改 `zh/` 和 `en/` 中相应章节，在 `edition.json` 更新编辑版本。依照[生成说明](../../scripts/methodology/README.md)重建全部格式、检查排版，再同步网站。`artifacts.json` 记录六个受审文件，`generation.json` 记录内容和生成关系；这些工程记录独立于正文。

0.5 版按输入、运行、年度核算与投资重新组织正文，补齐初始化、数值约束和状态更新，公式与伪代码沿用实现中的变量名。

作者文档采用 CC BY 4.0，见 [文档许可](../LICENSE.md)。运行接口概览保留在 [VALUE_METHODOLOGY.md](VALUE_METHODOLOGY.md)，用于查阅工作区和契约实现；完整数学方法以本目录的中英文章节为准。
