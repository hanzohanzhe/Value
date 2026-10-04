# 四角色修复循环验收报告

日期：2026-10-02。**四项预定任务修复后全部通过。** 主控完成浏览器操作与最终审核，GPT‑6.1‑sol 分担修复、作者文件准备及只读检查。

## 原验收标准与边界

沿用仓库 docs/frontend/FOUR_ROLE_USABILITY_TEST_2026-10-02.md 的预定任务和验收清单，不降低标准：R1 要取得独立复现 Study、明确 Run 与完整身份比较；R2 要完成独立包、显式映射、保留原方法及可读的正确需求结果；R3 要从下载示例本地改价、安装新身份、只替换 storage_cost、实际运行并核对报价；R4 要完成提案、安装、独立 Study/包、扩展角色绑定、明确 Run 和 Inspect 摘要。

业务复验由主控通过 CUA 操作前端。启动隔离安装、准备 CSV、依据下载说明在本地编辑作者包和保存证据属于记录过的依赖。修复发生在工程工作区，随后重新构建/安装复验；本轮是修复后的协助复验，不回写首轮的 R1 部分通过、R2 未通过、R3 阻塞及 R4 限定任务通过结论。保存 Study、运行前检查、启动 Run 仍为不同动作。

复验限定界面可用的短范围，验证用户操作与运行接线，不验证全年经济结论或模型科学正确性。各次修复构建有单独包记录，本报告不声称以下所有 Run 均来自最终同一安装包。

## 最终结论与运行登记

| 角色 | 当前复验结论 | Study / Run 与证据 |
| --- | --- | --- |
| R1 复现 | **通过**：五维身份一致，正确显示教学比较边界 | Study `uat-loop-r1-reproduce-a165fe977c`；Run `uat-loop-r1-rep-20261002-124953-43229b7d`；对照基线 Run `value-101-basel-20261002-124843-9d102e95`；[最终身份比较]([LOCAL_PATH_REDACTED])、[截图]([LOCAL_PATH_REDACTED]) |
| R2 换数据 | **通过**：60 MWh 映射与实际结果一致，仅数据维度改变 | Study `uat-loop-r2-forecast-60-mwh-f702fd756b`；包 `uat-loop-r2-60-mwh-forecast-08f3d96511f2`；Run `uat-loop-r2-for-20261002-125224-8368527c`；[映射预览]([LOCAL_PATH_REDACTED])、[最终市场回放]([LOCAL_PATH_REDACTED])、[最终比较]([LOCAL_PATH_REDACTED]) |
| R3 改模块 | **通过**：独立模块和方法 Study 的真实报价为 £73/MWh | Study `uat-loop-r3-storage-offer-73-3181966938`；模块 `uat-loop-fixed-storage-73`；Run `uat-loop-r3-sto-20261002-125821-73614405`；[最终报价文本]([LOCAL_PATH_REDACTED])、[截图]([LOCAL_PATH_REDACTED])、[下载作者 README]([LOCAL_PATH_REDACTED])、[安装作者包]([LOCAL_PATH_REDACTED]) |
| R4 加功能 | **通过（observer 任务）**：26/26 自动校验、两时段运行、Inspect 年份与输入身份摘要 | Study `uat-loop-r4-year-input-observer`；包 `uat-loop-r4-observer-inputs-d2d308b322d0`；扩展 `uat-loop-year-observer@0.1.0`；Run `uat-loop-r4-yea-20261002-131104-42dfd0de`；[Data ready]([LOCAL_PATH_REDACTED])、[Review ready]([LOCAL_PATH_REDACTED])、[范围不一致现场和修复说明]([LOCAL_PATH_REDACTED]) |

## 修复和已取得的用户证据

### R1：配置身份与教学分类

一日教学分支补齐比较所需的有效配置身份。R1 与基线比较显示基础/网络数据、模块、参数与扩展、年份、范围五项一致，不再以缺失配置推断多个维度变化。现有记录中没有储能方法变化，界面解释为 recorded configuration matches。

循环中另发现身份已经完整时，旧解释仍把教学差值限制描述为证据不完整，保留了[修正前现场]([LOCAL_PATH_REDACTED])。随后纠正比较说明和 `value_101_day` 分类，并保留已有 Run 数据。一次直接替换安装文件被完整性检查拒绝启动；已恢复原文件，之后均重建完整包，再将停服测试状态逐字节复制到新安装，未绕过完整性检查；过程见 [comparison-hotfix.json]([LOCAL_PATH_REDACTED])、[r2 迁移记录]([LOCAL_PATH_REDACTED]) 和 [r4 迁移记录]([LOCAL_PATH_REDACTED])。最终 UI 显示 `matching teaching configuration`，五维均一致。教学 Run 只核对模型身份，年度成本和碳差值仍不作为科学情景比较；不把教学限制写成身份缺失。

### R2：输入单位只转换一次

标准需求列使用每半小时平均功率 MW。复验以 17,520 行恒定 60 MWh/period CSV，在映射界面明确选择来源 MWh/period、目标 MW，预览规范值为 `120.0`。映射过程为 60 MWh ÷ 0.5 h = 120 MW；实际 Run 的半小时回放 Requirement 为 **60 MWh**，对应 120 MW × 0.5 h。

比较显示基础数据已改变，模块、参数与扩展、年份和范围一致。旧标签兼容警告明确历史数据仍按原 MW 行为解释，旧字节不改；此警告不是新上传可以推断单位的许可，也不修写首轮错误 Run。界面证据与截图见 [r2-mapping-preview.txt]([LOCAL_PATH_REDACTED])、[r2-market-60mwh.png]([LOCAL_PATH_REDACTED])。

### R3：模板实际生命周期与报价

新版示例补齐真实储能消费所需的生命周期与状态协议，作者说明补齐改价、独立身份和验证层级。按下载 README 本地改为 73 并打包，安装新模块后创建独立方法 Study；真实 48-period 教学 Run 完成，市场回放的 Battery 行显示 **£73/MWh**。

该报价证据说明新实现被真实运行消费，不能据此宣称年度收益合理或科学验证通过。截图中报价行的 accepted 为 0 MWh，也不声称本轮 UI Run 已完成非零成交的全链路验证；非零销售、报告、跨年重置由必要协议回归承担，19 项必要协议回归已通过，主控审阅后确认。首轮失败 Run 继续保留。

### R4：数据到草稿、范围和真实扩展输出全部通过

Data 的 Current unsaved Study draft 内增加基础包选择、命名复制及 Return to Study Review。复制自动用于同一草稿，保留扩展和方法；已保存 Study 引用的包禁止直接覆盖。包 manifest 更新会清旧草稿校验并重新解析，解析过程中阻止保存。CUA 已确认 audit CSV 绑定后自动到 **26/26 required roles ready**，直接回 Review，未通过切换无关 acknowledgement 触发刷新。

但从 R3 one-day 切换至 R4 普通 Study 的实测仍复现范围错配：下拉显示 Two-period，readiness 却为 48 periods，按钮后缀为 value_101_day。**本次未在这个不一致状态启动 R4 Run。** 根因是 canRunMode 仅按包允许范围判断，而 select 对非教学 Study 另行隐藏 one-day，使合法的受控值没有对应选项。先前显式转交 effective mode 只统一了请求，漏掉了可见选项的资格差异。

二次修复将选项、有效选择、检查和启动统一到共享 runScope 资格函数：普通 Study 去掉 one-day，旧 one-day 状态回退 smoke，旧 day 预检不匹配；教学和历史恢复锁定范围保留其资格。按钮后缀使用与选项相同的人类可读名称。主控已在最终安装通过 CUA 显式选择 R3 One-day，再切至 R4，未手改范围；下拉与按钮均显示 Two-period，第一次检查为 Ready 2 periods，见 [r4-scope-fixed.txt]([LOCAL_PATH_REDACTED]) 与 [截图]([LOCAL_PATH_REDACTED])。之后明确点击 Run selected scope，Run `uat-loop-r4-yea-20261002-131104-42dfd0de` 完成，执行与契约均 passed；在 Inspect → Artifacts & provenance 读到 `uat-loop-year-observer@0.1.0`、`year=2025` 和 `source_inputs_sha256=35165a93570fd321df72a125ef9867637d198ccd2a3b430d8cf6e83df9a67585`。UI 摘要与前端下载的 year-results 一致，随后只读审计确认其匹配同 Run 的 `psm.run` 输入身份事件。见 [最终 Inspect 文本]([LOCAL_PATH_REDACTED])、[结果截图]([LOCAL_PATH_REDACTED])、[UI 下载记录]([LOCAL_PATH_REDACTED]) 和 [运行/身份终核]([LOCAL_PATH_REDACTED])。

observer 只记录已执行年份与冻结 PSM 输入身份；声明 audit 数据角色与成功绑定不表示 CSV 值被用于新科学计算。此功能不新增物理算法，更不代表任意新功能或科学验证已通过。

## 工程检查与证据分类

| 类别 | 已确认结果 |
| --- | --- |
| 前端静态检查 | scope 修复后的 frontend typecheck 通过。 |
| 范围和旧证据回归 | `tests/run-scope.test.mjs` 与 `tests/preflight-identity.test.mjs` 共 4/4 通过；覆盖普通 Study + 包允许 one-day + retained one-day、标签对应、旧 day 预检失效、教学/恢复资格及锁定冲突。 |
| 后端需求单位、配置身份与模板协议 | 施工阶段定向检查已通过：需求契约/映射 7 项（root）、模板生命周期 conformance 与 authoring 19 项（repair_module）、配置产物 1 项与比较身份 11 项（repair_reproduction）。结果依据主控工具及 agent 回报核验；没有持久日志，不编造日志引用。 |
| 浏览器夹具检查 | 子任务尝试的 CSV mapping Playwright 测试因默认 Chromium executable 缺失未执行；不计通过。实际用户操作由上述主控 CUA 证据支持。 |
| 最终交付构建 | [build-final.log]([LOCAL_PATH_REDACTED])、[package-r4.json]([LOCAL_PATH_REDACTED]) 保留最终构建与包身份；主控已完成最终安装的范围、真实 Run 和 Inspect 验收；最终查询版本又读取 R1/R2 比较、R2 60 MWh 和 R3 £73/MWh，全部符合原任务标准。 |

## 原对象及首轮证据保护

[final-preservation.json]([LOCAL_PATH_REDACTED]) 于 2026-10-02T05:09:32Z 记录只读核对：原 Study/修订 18/18、原冻结输入 142/142、首轮验收证据 151/151 全部哈希一致，总计 311。核对对象来自已记录列表，不等于检查工作区所有文件。所有修复复验均在独立状态目录进行。当前循环基线只有 revision 1，project 文件与该修订及 r1 安装中的原始副本字节相同；文件 SHA-256 为 `d127f7bec12c82816d8416a1a392f7e10ae4f7cbf0c83849383498222cb8e3b5`，语义修订身份另为 `592cd3bce5e1730c804c164ae9fbe72bacb2886fd7c06845e5c252fd46da25e0`，两者不可混为一谈。

## 原清单逐项验收

| 验收项 | reproduce from existing data | add your new data | Edit module | add new function to VALUE |
|---|---|---|---|---|
| 入口与说明可找到 | 通过 | 通过 | 通过 | 通过 |
| 按说明准备输入与作者文件 | 通过 | 通过：显式单位 | 通过：下载 README 后本地编辑 | 通过：生成 observer 示例 |
| 独立 Study，保存不运行 | 通过 | 通过 | 通过 | 通过 |
| 预检后明确启动 | 通过：48 时段 | 通过：48 时段 | 通过：48 时段 | 通过：2 时段 |
| 取得指定结果与身份 | 通过：五维一致 | 通过：60 MWh | 通过：£73/MWh | 通过：2025 与输入 SHA |
| 原配置与历史证据保留 | 通过 | 通过 | 通过 | 通过 |

本循环共新增 **5 个实际 Run，全部 completed**：教学基线和 R1/R2/R3 各一个 48 时段 Run，R4 一个两时段 Run。未重复全年或十年模型；后续比较说明和范围修复不改变已完成模型输出，因此最终在 UI 重读相关结果，没有为只读展示改动重复求解。

修复与读取分别发生在 r1、r2、r4 独立安装；最终执行代码、查询代码与 UI 的包身份见 package-r4.json。测试状态保留于 `work/uat-loop-fixed-r4-installed/state`。交付包只包含程序与教学数据，不包含这批测试研究。

内置简明 Read me 已通过 UI 核对，补齐显式单位、选择/检查/启动同一范围以及扩展复制数据、自动校验、返回 Review、查看摘要步骤，见 [最终 Read me 文本]([LOCAL_PATH_REDACTED])。本次关闭的是四项指定用户任务的缺陷；任意新物理算法、全年科学正确性、Windows 和完整离线运行仍属于另行验证范围。

## 交付与日常环境恢复

日常 API 8766 / UI 18800 已恢复最新实现；通过 CUA 刷新用户原有页面，确认 VALUE native ready、原 fixed-three-zone Study revision 1 和四角色首页均正常。测试安装已停止，测试状态、首轮失败记录和全部本次证据保留，测试标签已关闭。最终交付包为 `outputs/VALUE-Linux-four-role-accepted-2026-10-02.tar.gz`；仅在已验 r4 程序包基础上补充最终验收与施工状态文档，程序及前端构建字节另行核对一致，见 `delivery-package-equivalence.json`。仍需既有外部 Python 3.10 与 Node 运行环境。
