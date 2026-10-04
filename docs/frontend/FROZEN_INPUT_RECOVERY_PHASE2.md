# VALUE 第二阶段：冻结输入创建独立 Study

日期：2026-10-02。本批补齐历史 Run 冻结规范数据的审阅、独立 Study 创建与执行接纳。本批冻结输入新 Run 链路已完成实际两时段验收；不据此宣称全部建设计划完成或完整历史环境恢复。

## 用户流程与科学边界

在 Runs 选择历史 Run，核对冻结输入完整性，审阅已记录与当前执行身份的差异，再明确选择 strict 或 migration。strict 核对当前本地源码、环境与已归档执行身份；migration 保留冻结规范数据，按当前方法重新计算，并明确展示政策和方法变化。两种方式均只创建独立 Study，不启动 Run，也不恢复旧检查点。

保存后的 Study 保留 source_run lineage、快照、已接受执行身份及锁定范围。用户仍须在普通 Runs 核对范围、Check readiness，再明确启动。数据包允许范围与来源锁定范围取交集；没有可用范围时不能检查或启动。24h/168h 等已记录范围提供对应执行入口。冻结输入 Study 不加载为可编辑科学草稿；后端拒绝改变受保护科学配置或运行范围。

界面按需读取报告，显示范围、求解政策及模块版本摘要；完整身份与差异记录默认折叠。缺失证据、阻断条件及限制持续可见。切换 Run 或方式会清除审阅和确认，晚到响应不能复活旧报告；创建回执核对来源 Run、快照、范围与保存未启动标记。

## 已确认验收

- 真实旧 v2 生产 Run 的冻结数据审阅完整，包含 66 项绑定及规范文件证据。该旧快照包含双 product 的重复角色；按 BASE/network 分离后的新快照为 33 项（25 BASE、8 network），不是 66 个不同科学角色。strict 因缺少执行归档拒绝；migration 明确展示旧 v2 到 GBP1 v3 的求解政策变化。
- 保存创建了新的独立 Study，没有创建 Run。改变来源范围为 full，以及修改受保护科学配置，均返回 409。
- 临时移走隔离测试目录中的历史 Run 后，新 Study 的 readiness 仍 accepted，说明新 Study 不依赖该历史 Run 目录继续存在；这不等于历史执行环境已恢复。
- 定向检查：冻结输入暂存 4 项、既有纯完整性 8 项、服务与执行接纳 10 项、执行归档 3 项、浏览器组件 1 项通过。前端组件测试覆盖跨 Run/方式的晚响应隔离与明确保存不运行。
- 最终 Run `recovered-8d057-20261002-060823-10508dd0` 完成 smoke 范围：2025 年、2 时段。execution 与 contract 均 passed，science 为 `not_evaluated`。更早的 A Run 也通过两时段检查；执行加载器的变量记录修订后，旧身份被强制判定 stale，最终 B Run 验证修订后的身份。
- 最终 B Run 的 strict 浏览器审阅无差异并通过；旧 Run 的 strict 仍明确阻断。确认保存新 Study `recovered-d937708e35004118` 后没有启动 Run，页面自动选择新 Study，范围唯一为 smoke，Check readiness 显示 Ready，未出现 pageerrors。截图为 `work/phase2-frozen-recovery/browser-strict-study.png`；真实 JSON 记录为同目录的 `final-run-acceptance` 与 `http-acceptance`。
- 两份真实原冻结 Run 的所有原字节 SHA 均未改变。两次实际执行各为 2 时段必要检查，没有运行年度或十年模型。

测试使用隔离目录 `work/phase2-frozen-recovery`。来源日常工作区的 9 个 Study、6 个 Run 未作修改；不将隔离验收写入来源研究记录。

## 执行身份与归档边界

新增源码与环境 CAS 证据，以实际文件全字节 SHA-256 绑定身份。最终执行包身份为 `33edc206ccef2e19b6155cd29e0a8b1f8ff6b6d5f29f8d68aa1a7bf9c1c7a27e`，包含 311 个源码文件及 12,086 个环境文件；`identity_complete`、`native_closure_complete`、`archive_complete` 均为 true，limitations 为空。实际 environment ZIP artifact 为 218,763,699 bytes，并按内容身份去重。`identity_complete`、`native_closure_complete` 与 `archive_complete` 分开记录：身份可完整核对，并不表示原生依赖闭包完整，也不表示归档具备独立执行资格。

同一本地兼容环境可进行严格身份核对，报告须如实保留原生闭包或归档限制。归档在独立安装前缀执行、Windows 与完整离线环境尚未验证，不能写为可独立重建或已恢复。科学基线仍为 `ten_year_study_pending`；短运行接纳和工程检查不构成科学发布。

## 剩余边界

本批冻结输入新 Run、浏览器保存/readiness 与原冻结输入哈希闭环已验收。来源日常工作区的 18 个 Study/修订文件已逐一核对 SHA-256，全部保持不变；原 9 个 Study、6 个 Run 未修改。独立历史源码/环境归档执行与最终发行刷新仍须另行验收，不以本批本地输入迁移或严格身份核对替代。

执行身份不完整的当前环境会阻断 strict 与 migration 审阅；新增的一项定向接纳检查通过。迁移不能绕过未知源码或运行路径。

## 后续收口

后续归档方法在同宿主独立目录的实际运行已通过，见 `ARCHIVED_WORKSPACE_PHASE2.md`；最终发行及全部阶段状态见 `FINAL_DELIVERY_PHASE6.md`。本记录上文的未验事项为该批交付时状态。
