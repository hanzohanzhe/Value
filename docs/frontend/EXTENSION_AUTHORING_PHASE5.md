# VALUE 第五阶段：扩展作者流程与冻结结果

日期：2026-10-02。基线：`40813da`。本批完成第五阶段限定示范闭环，继续保留第二阶段历史恢复和第六阶段发行集成的未完成项。

## 用户流程

`add new function to VALUE` 现在打开扩展作者工作台。填写研究问题、版本、命名空间、验证计划和迁移说明后，服务器生成完整声明并校验。高级编辑可以检查数据 roles、参数、模块组合、生命周期、状态所有权、结果 schema 和摘要字段。修改任何字段都会取消旧请求、撤销旧报告；下载必须匹配已审核的包 SHA-256。

下载 ZIP 包含声明、独立 Python 包、样例 CSV、结果 schema、提案、许可证及说明。作者可以在本地实现新功能，再运行 `scripts/build_extension_bundle.py` 重建精确文件清单。安装复用本地扩展安装入口，明确可信 Python 执行边界。依赖模块必须先安装；不自动执行依赖安装或迁移。

安装后打开独立 Study 草稿，在 Advanced → Optional domains 启用扩展。Data 以该草稿作为上下文显示条件输入；先复制数据包并绑定角色，再保存 Study。保存不启动 Run，原 Study 保留。实验性扩展必须明确确认。完成短运行后，在 Inspect → Artifacts & provenance 查看按扩展和年份筛选的摘要。

## 实现与边界

- 当前网页生成器只提供真实实现的 audit observer：初始化扩展自有状态，after_psm 输出年份和 PSM 输入哈希。不计算新物理算法，不消费样例 CSV 的值，不允许通过高级声明虚构其他已实现能力。
- 源码 ZIP 使用一个独立顶层包，校验路径、文件清单、哈希、包冲突和 hook callable；安装失败回滚。重新启用校验原 hook 身份。安装报告绑定声明哈希，变更声明后旧通过报告不再适用。
- Run 冻结完整扩展声明和 hook 入口文件哈希；图输出经过 JSON 规范化，确保年度检查点读写身份一致。这里没有宣称捕获完整 Python 环境和全部间接依赖源码。
- `value.extension-results/v1` 只读取 Run 的冻结文件，按扩展、年份和分页返回声明的标量摘要。文件大小和读前后身份受限；失败/未完成 Run 不展示产物，旧 Run 缺少声明明确 unavailable，不替换为当前 registry。
- period、zone、technology 不在本结果族的维度范围。迁移说明不是已执行迁移；扩展科学成熟度仍为 experimental。

## 必要验收

相关作者、源码安装、冻结结果及 JSON/checkpoint 往返用例通过；前端类型、相关 lint 和生产构建通过。浏览器检查了提案校验、编辑及改回原文后禁止旧报告下载、实验确认、独立 Study 保存、年份筛选和结果版面。浏览器显示下载就绪；自动化下载事件未捕获，后续通过同一模板 API 获取并核对界面审核过的 ZIP 哈希后安装。

真实验收使用独立数据包 `phase-5-extension-audit-data-8fa68925d7e1`、独立 Study `phase-5-extension-audit-study`、扩展 `phase5-audit-observer@0.1.0`。原 Study 不变，保存时 Run 数未增加。显式执行 `two_year_smoke`（2025、2026，每年 2 个时段）。

首次运行 `phase-5-extensi-20261002-042739-33b3460a` 暴露嵌套 tuple/list 的检查点身份差异。修复图的 JSON 输出后，必要重跑 `phase-5-extensi-20261002-042959-68104a50` 完成。未修改数值算法，未重跑年度模型。两个年度产物输入哈希与各自 PSM 事件一致，状态 owner/schema/初始化年份跨年保留，年度检查点回读通过。失败 Run 保留并被结果查询正确 withheld。

详细记录：交付包 evidence 中的 `phase5-live-validation.json` 及各定向检查日志。示范模型执行通过不代表新科学方法验证通过。
