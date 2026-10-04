# VALUE 归档方法独立工作区验收

日期：2026-10-02。承接冻结输入恢复，补齐历史源码与 Python 在独立目录实际执行的用户路径。目标为同一 Linux x86-64 宿主；不把源文件展开称为已经运行，也不宣称完整操作系统隔离。

## 用户路径与实现

在历史 Run 的 **Run with the archived method** 折叠区查看命令。`scripts/prepare_archived_workspace.py review` 只读核对终态 Run、冻结输入、方法声明、执行记录引用、CAS 对象及宿主兼容性，返回 `review_sha256`。`prepare` 必须传入此哈希和 `--acknowledge-code`，才执行可信归档代码；源身份变化需重新审阅。

准备命令只在新目录复制独立源码、Python、规范输入和必要归档对象。复制前、复制后与原来源再次审阅的身份必须一致；错误只清理本次创建的目录。它在归档 Python 中调用归档后端已有的 strict review/publish 服务，创建独立 Study，不启动服务或 Run。旧后端缺少所需契约时拒绝，不换用当前后端。

生成的 `start-archived-value`、`diagnose-archived-value`、`stop-archived-value` 使用独立目录及进程归属记录。启动检查物化字节、当前执行身份、独立输入、宿主依赖和计算进程参数，复用归档 `backend.server` 及普通 `backend.model_runner`。API 仍为 8766，UI 为 8800；端口被占用时拒绝，不停止现有程序。互斥锁串行化启动、诊断和停止。当前发行 UI 和外部 Node 只提供操作界面，科学源码来自归档。

## 实际证据

- 原 Run：`recovered-8d057-20261002-060823-10508dd0`；原快照：`40f7a6c2d6bd1376a6457f75e02fcd32cf54b036ee90c6ef641c992c8e68c859`。
- 最终独立工作区：本任务 `work/phase2-archive-execution/prepared-workspace-final`，独立 Study：`recovered-49b654d8c5554ad5`。
- 准备与启动均未创建新 Run。显式 readiness/launch 后，新 Run `recovered-49b65-20261002-064123-b837a39e` 完成 2025 年两个时段，execution=passed、contract=passed、scientific_validation=not_evaluated。
- 新 Run 的执行身份与原归档相同：`33edc206ccef2e19b6155cd29e0a8b1f8ff6b6d5f29f8d68aa1a7bf9c1c7a27e`。现场 `/proc` 记录证明 worker 的实际可执行文件、工作目录、命令均来自独立目录；Python prefix、导入模块与 HiGHS 路径也已核对。
- 普通网络 capabilities、annual 和分页 solver 查询成功；浏览器显示独立 Study、锁定范围、完成状态及真实科学验证标签，无控制台错误。
- 真实端口占用拒绝保留日常服务的 9 个 Studies / 6 个 Runs；停止、立即重启、诊断与再次停止通过，独立 Study 字节不变。原源码、原 Python 和原 GBP1 科学任务均未移动或替换。

准备和启动器仅做身份、事务清理、环境传递、进程归属等必要定向检查；前端类型检查、生产构建和一条实际页面链路通过。本批实跑限定两个时段，未运行全年或十年模型。实际日志、审阅报告、进程证明与截图位于 `work/phase2-archive-execution`，发行收据保留其文件哈希。

## 准确边界

初次独立 Python probe 发现原归档没有记录宿主 locale/gconv 文件。此缺口没有回填进旧证据。新准备过程明确固定本次宿主 locale 配置和资源，核对已记录的宿主 ELF；仍标记 `same_host=true`、`fully_isolated=false`。同一归档身份不等于跨系统可运行、位级数值一致或科学验证通过。没有历史归档的旧 Run 仍须显式迁移，不能凭现存数据补造历史方法。

最终发行刷新及完整阶段核对见 `CONSTRUCTION_STATUS.md` 和 `FINAL_DELIVERY_PHASE6.md`。
