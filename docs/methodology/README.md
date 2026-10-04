# VALUE 方法学

修订版 **0.3，2026 年 10 月 4 日**。模型实现与数据依据为 **2026 年 10 月 2 日**。

本目录保存 VALUE 中英文方法学的权威源稿。正文说明模型设定、方程、算法和输入数据；函数与数据文件名紧接其对应计算步骤。两版章序相同，网页、Word、PDF 和离线 HTML 使用同一套正文。

| 章节 | 中文 | English |
| --- | --- | --- |
| 1 | [模型框架](zh/introduction.md) | [Model framework](en/introduction.md) |
| 2 | [初始数据与输入处理](zh/datasets.md) | [Initial data and input processing](en/datasets.md) |
| 3 | [天气与可用出力](zh/core_weather.md) | [Weather and available generation](en/core_weather.md) |
| 4 | [运行与年度反馈](zh/core.md) | [Operation and annual feedback](en/core.md) |
| 5 | [全国调度算法](zh/national_alternatives.md) | [National dispatch algorithms](en/national_alternatives.md) |
| 6 | [年度投资与资产演化](zh/r029_cem.md) | [Annual investment and fleet evolution](en/r029_cem.md) |
| 7 | [传输与网络约束](zh/transmission.md) | [Transmission and network constraints](en/transmission.md) |
| 8 | [完全预见调度与自然水文](zh/optional_modules.md) | [Perfect foresight and hydrology](en/optional_modules.md) |
| 9 | [碳排放核算参数](zh/appendix.md) | [Carbon accounting parameters](en/appendix.md) |

下载：[中文 PDF](../../website/static/assets/methodology/VALUE_模型方法学_2026-10-04.pdf) · [中文 Word](../../website/static/assets/methodology/VALUE_模型方法学_2026-10-04.docx) · [中文离线 HTML](../../website/static/assets/methodology/VALUE_methodology_ZH_2026-10-04.html) · [English PDF](../../website/static/assets/methodology/VALUE_Model_Methodology_EN_2026-10-04.pdf) · [English Word](../../website/static/assets/methodology/VALUE_Model_Methodology_EN_2026-10-04.docx) · [English offline HTML](../../website/static/assets/methodology/VALUE_methodology_EN_2026-10-04.html)。

## 维护

先修改 `zh/` 和 `en/` 中相应章节，在 `edition.json` 更新编辑版本。依照[生成说明](../../scripts/methodology/README.md)重建全部格式、检查排版，再同步网站。`artifacts.json` 记录六个受审文件，`generation.json` 记录内容和生成关系；这些工程记录独立于正文。

作者文档采用 CC BY 4.0，见 [文档许可](../LICENSE.md)。运行接口概览保留在 [VALUE_METHODOLOGY.md](VALUE_METHODOLOGY.md)，用于查阅工作区和契约实现；完整数学方法以本目录的中英文章节为准。
