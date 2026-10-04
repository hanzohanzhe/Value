# 第二阶段：CSV 列映射与独立网络覆盖包

2026-10-02。本批延续 `DATA_COPY_PHASE2.md`，补齐受支持 CSV 的显式列映射和网络覆盖包编辑。保持四条社区入口、原 Study、原数据包和历史 Run 的身份。保存数据或 Study 都不会启动计算。

## 用户流程

在 **add your new data** 复制 BASE 包，进入 Data，选择语义角色。标准文件仍可直接上传；外部 CSV 可选择来源列与来源单位，查看规范样例和完整文件校验，确认后提交。仅提供运行时已有解析器和明确列契约的角色，不推断时区、重采样或缺失列。已被当前 Study、历史修订或 Trash 引用的副本不能继续覆盖。

在 **Data Workbench → Network overlay editor** 选择已安装覆盖包（含没有 installation.json 的 VALUE 101 本地包），复制为新 ID。选择角色，下载当前文件，编辑后上传同一契约格式，执行全包检查，由用户审阅并安装。随后在 **Studies → Model chain → Network overlay** 选择新覆盖包。BASE 与网络产品分别选择。

## 实现与边界

CSV 服务为 stage → preview → commit 三步；每次审阅绑定原始字节、规则、规范字节及目标 manifest 的 SHA-256，有效期 30 分钟，上传上限 32 MiB。完整检查 UTF-8、标题唯一性、每行宽度及角色数据契约；样例最多 20 行。提交持共享 Study 生命周期锁，再核对身份、引用和转换结果。原 CSV、规则与审阅保存在包内 provenance，规范绑定不带 executable adapter，后续 snapshot 不会二次转换。

网络编辑使用服务端 UUID 目录及候选内容身份。源包只读，编辑不覆盖已安装包，失效候选不能通过旧报告安装。下载、上传与安装都核对当前候选；上传尚未应用时禁止批准。安装复用已有 bundle 安装器，并记录本地命名审阅回执。版本是 approval release version；未更改已审阅的候选内容。它不是密码学签名。独立网络候选不会进入旧编译候选的审阅列表；旧服务入口也拒绝混用。

网络检查调用真实 `validate_data_pack` 与 `load_zonal_network_pack`，检查角色绑定、拓扑引用、时钟及现有对账契约，不能由客户端声明“拓扑通过”。副本清除当前科学基线资格与认可，原资格仅保留为来源历史。机械检查通过不代表新增网络已科学验证。新上传文件使用 local-upload 来源及未声明的许可记录，原生成器、作者及源权利文件只保留为历史；本地安装确认不会自动产生再分发许可。

前端请求绑定角色、包和 manifest；换文件、映射、上下文时清除旧报告与确认，忽略迟到响应。Study 覆盖包选择器同样绑定请求上下文。Read me 已同步简短操作步骤。

## 必要验收

- CSV 后端 5 项定向测试通过：真实 demand.forecast 和 projects.repd（kW → MW），无 adapter 二次转换；末行无效、身份/有效期漂移、引用保护和失败不改 manifest。
- 网络编辑后端 3 项定向测试通过：独立下载/编辑/安装，坏跨角色引用阻止安装，旧 hash/越界/上传限制，以及不继承科学资格。Python 3.10，约 19 秒，未执行模型。
- Chromium 组件测试通过：确认后提交并刷新、映射修改清除报告、迟到响应不能跨上下文复活。
- 真实 HTTP 在独立验收 state 完成 BASE 复制、17,520 行外部 CSV 上传/映射/提交；重复提交返回 409，原 manifest 不变，Run 数仍为 0。
- 真实浏览器完成 VALUE 101 网络复制、角色下载、待上传阻止批准、替换、全包检查、安装 `phase2-browser-network-v1`、在独立 Study 选择并保存新覆盖包。原 Study 修订不变，Run 数为 0，无页面异常。
- 完整 CSV 页面另行走通 17,520 行文件选择、来源列选择、审阅、明确提交及目标包刷新；新规范文件 SHA 为 `33f8d2fe6fe98888d92a2f2781ca6541a08befd7fb005c62ca49afc6e36eb482`。
- 前端类型检查、改动文件 lint、生产构建及最终页面视觉检查通过。没有跑全年或十年模型。

主要证据位于工作区 `work/phase2-data-enhancement/`：`http-acceptance.json`、`browser-acceptance.json`、`final-browser-check.json`、`final-api-check.json` 和页面截图；另有 `phase2-csv-mapping-tests-final.log`、`csv-mapping-component-tests.log`、`phase2-data-enhancement-typecheck.log`、`phase2-data-enhancement-lint.log`、`phase2-data-enhancement-build.log`。浏览器验收 API 使用独立 18876 端口，经测试浏览器转发；未向日常工作区写入验收研究。

## 剩余工作

本批完成列映射和独立网络覆盖包编辑。下一批继续冻结规范输入恢复为独立研究，并通过普通 preflight/worker 创建新 Run。严格同记录方法/环境与按当前方法迁移必须分开；历史缺失源码或环境不能补造为已恢复。只读完整性 helper 正在独立施工，未接入运行链路时不计为该功能完成。
