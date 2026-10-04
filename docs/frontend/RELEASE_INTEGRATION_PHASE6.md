# VALUE 第六阶段：GBP1 基线集成施工记录

日期：2026-10-02。本记录说明 GBP1 集成与 Linux 本地候选发行的已完成验收。Windows 和科学正式发布仍不在本次已验收范围。

## 集成范围

科学源码来自 `2026-09-27/new-chat/work/zonal-gbp1-policy-20261001/source`，原补丁位于同项目的 `outputs/Value_GBP1_Policy_2026-10-01`。16 个 GBP1 核心文件按原补丁 SHA-256 核验后集入前端工作副本，保留科学契约、快照身份及数值政策。

前端没有整页覆盖科学副本的 `app/page.tsx`。手工合并 `networkRedispatch.ts`、`solverContract.ts`、`SolverSettingsEditor.tsx` 和 `StudyComposer.tsx`，保留已交付的研究引导、模块与扩展作者流程。

新 Study 使用 `value.network-solver-contract/v3` 与 `value.zonal-lexicographic-gbp1/v3`。主目标锁定误差固定为每个求解半小时总竞价成本 GBP 1，验证阈值与执行上限均为 GBP 1；自定义设置确认绑定 `value-zonal-redispatch-balancing@3.0.0`。

历史 v2 契约及验证摘要继续按其记录版本读取。加载旧 v2 草稿不会自动升级：编辑器展示原政策，并提供明确的 “Use current £1 policy” 按钮。选择升级才替换草稿契约、清除两版旧确认并重新检查；保存产生新 Study 修订，原修订与历史 Run 保留原身份。界面说明跨政策结果包含方法变化，不能当作方法相同的比较。自定义设置改回默认值时，派生状态标记按实际值重新计算。

## 已确认验证

- 真实历史 Run `value-101-netwo-20260928-024214-32ad4169` 通过新 API 成功读取 capabilities、annual 和 solver 结果；记录的 `solver_contract_version` 仍为 v2。
- 26 个 contract 与 snapshot 定向测试首轮有一个 Linux 权限 fixture 错误：Windows 风格的 `chmod(S_IWRITE)` 使测试文件在 Linux 不可读。修正 fixture 的读写权限后，该失败项单独通过；不将首轮记录写成全部通过。
- 3 个 GBP1 边界算例通过。
- 7 个相关 UI 契约测试通过，覆盖新旧版本读取、混合版本拒绝、GBP 1 固定、显式升级保留原草稿、确认清理及自定义设置回到默认。
- 前端 typecheck、改动范围 lint 和生产 build 通过。

日志保留在本任务父目录 `work/phase6-*.log`，包括 contract/snapshot 首轮、权限 fixture 修复、GBP1 边界、UI 契约、typecheck、lint 与 build 的真实记录。

## 安装验收中发现并修复的问题

首轮本地安装成功后，端口预检把 TCP TIME_WAIT 当成正在监听的程序。启动器已改为 SO_REUSEADDR 后 bind/listen，仍拒绝真实监听者。UI 端口只开放 API 已允许的 8800 或 18800，避免可配置端口与浏览器跨源策略不一致。

第二轮安装已完成教学 Study 创建、独立数据包复制及 CSV 上传。实际网络 two_year_smoke Run `value-101-netwo-20261002-045212-db08da7b` 完成 2025 年后，在 2026 年首时段发现既有状态索引问题：覆盖包的全局时钟索引被写入年度运行状态。原科学源与前端基线均有同一写法；这不是 GBP1 目标阈值变化。修复只将消费记录的索引改为 BalancingInput.period，网络数据读取仍使用全局索引。失败记录保留，修复后以新安装和新 Run 验收，不恢复失败 Run 冒充同一执行源码。

第二轮安装的独立数据包复制与原始 `demand.forecast` CSV 上传已通过，上传 SHA-256 前缀为 `62b59aa0`，baseline 数据包 manifest 未变。第三轮安装的浏览器已在 8800 端口看到 Read me 的四条路径名称。

第三轮安装 Run `value-101-netwo-20261002-045702-dc6ce397` 成功写入 2025 年两个时段，2026 年又暴露一个跨年身份冲突：`orders.order_id` 是全 Run 主键，ahead/balancing 的原始生成 ID 只包含年内 period 和 asset，重复年份触发主键冲突。修复已对七处原始 ID 生成加入 year，使声明、接受记录与账本保持同一身份；不使用 `INSERT IGNORE`，也不通过改变 trace profile 避开冲突。定向回归和最终新安装 Run 已通过，证据见下文。

## 发行范围与科学边界

Linux x86-64 本地候选已在独立用户目录安装并完成必要验收；需要已有 Python 3.10 与 Node >=22.13，未捆绑完整离线 runtime。Windows 未构建。

科学基线状态仍为 `ten_year_study_pending`。工程集成与短边界算例通过不等于十年科学研究完成，也不构成科学发布结论。完整历史环境恢复和第二阶段数据增强仍按施工状态继续推进。

## 定向修复验证补充

年内 runtime 索引与导出/恢复相关 9 项通过（0.054 秒）。订单身份修复后的同一 Run、同一 SQLite、跨两年 full-trace 算例和现有恢复一致性用例共 2 项通过（0.851 秒）；两年订单均保留、ID 唯一、结算与真实声明/接受结果可关联。扩充测试时曾错误假定另一组表必有记录，首轮测试失败日志保留；最终断言使用实际 clear 输入/输出。

安装器停止、立即重启、重复启动与诊断均通过，原研究配置和状态哈希未变。失败 Run 的浏览器页面已显示 failed、诊断代码与 verified annual checkpoint 恢复入口；未在源码变化后恢复旧 Run。SmokeDiagnostics 的说明已改为配置范围，避免在失败时声称已完成全部时段，并完成最终前端生产构建。

## 最终安装验收与交付

最终候选 archive SHA-256：`29da290b924681faea722dd22d7aa71a8c3b11206329e032c8a2f30a7eec0385`，包含 2004 个清单文件；原始总大小 38,060,730 bytes。此包为 `9f7df4e5dabe37dfbe323abad145ec57ba08ff0f` 之上的本批工作区快照，逐文件哈希定义其精确来源。包含两套 CC0 教学数据、预构建 UI、Python 源码和五个 Node 运行包，不含个人研究状态或私有研究数据。包内施工记录为构建前快照，本记录及独立验收证据补充其后实际验收。

实际安装路径为本任务 `work/phase6-installed-r4`。Python 3.10.21、Node 24.19.0；状态独立存于该目录的 state。创建 VALUE 101 基础研究、网络对照研究和独立数据副本均未自动启动 Run。数据接入已在同版数据服务的 r2 安装验收中完成：上传 demand.forecast CSV 后原始字节哈希一致，原基础包 manifest 未变；后续修改限于启动器、跨年执行身份和诊断文案。

显式运行 `value-101-netwo-20261002-050310-ec6d6085`（two_year_smoke）完成 2025、2026 各两个半小时时段，总计 4 个时段：execution=passed，contract=passed，scientific_validation=not_evaluated。新 API 的 capabilities、annual 和分页 solver 查询均成功；两个年度各有 2 条时段覆盖，solver policy 为 `value.zonal-lexicographic-gbp1/v3`。浏览器实际看到运行通过、四条路径、简明 Read me、网络结果与未通过科学验证的真实标签；GBP1 numerical warnings 原样保留，没有隐藏或改为 validated。

原日常工作区的 18 个 Study/修订 JSON 哈希保持不变。失败 r2/r3 Run、定向回归首轮失败日志均保留，未覆盖为成功。未启动完整年度或十年研究。完整收据位于 `work/phase6-installed-acceptance.json`，启动恢复收据位于 `work/phase6-control-recovery.json`，截图交付于 outputs。

## 后续收口

本记录中的 archive 与 r4 是 GBP1 初次集成的历史验收。包含后续数据映射、冻结输入恢复和归档工作区的新发行已完成，见 `FINAL_DELIVERY_PHASE6.md`；最新下载和 SHA 以 `VALUE_final_delivery.json` 为准。
