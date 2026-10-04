# VALUE 前端施工记录 · Phase 1

日期：2026-10-01。依据《Value 前端设计书 v1.1》实现第一批可运行改造。

## 已实现

- 首页按用户指定的四个任务命名：`reproduce from existing data`、`add your new data`、`Edit module`、`add new function to VALUE`。分别接入教学/已有 Study、数据工作台、模块安装、扩展安装；工作页可切换任务。
- 顶部提供 Read me，正文统一读取 `public/README.md`。支持键盘关闭、焦点返回、加载失败重试与移动端阅读。
- 导航按开始、研究、结果、指南分组；首页增加继续已有 Study。移动端保留文字导航，触点至少 44px。
- 结果页显示只读 Run 上下文：冻结 Study 版本、数据包、网络覆盖包及哈希；执行、契约、科学验证三个状态分别显示。缺失或不一致的来源明确标记，不用当前草稿代替。
- URL 保存视图、任务路径、Study、Run、Data 输入上下文。刷新和浏览器返回恢复选择；明确指定但不存在的 Run/Study 不会默默转到其他结果。未保存表单内容仍未持久化。
- 从历史 Run 创建 Full replay 版本时，只使用对应冻结 Study。数据解析和预览绑定其来源，阻止切换任务或返回时串用上一项研究的数据。
- 没有云端 hosting 配置的源码包可直接构建本地 Node 版本；有配置的项目保留原有构建路径。

## 验证

| 检查 | 结果 |
| --- | --- |
| `npm run typecheck:frontend` | 通过，覆盖 app 下的 TS/TSX |
| `npm run lint` | 0 错误；Value101Learn 有 3 条既有 no-unused-expressions 警告 |
| `npm run build` | 通过，本地生产构建 |
| `node --test --test-isolation=none tests/*.test.mjs` | 37/37 通过，含 SSR、来源身份、链接恢复与既有前端检查 |
| `BASE_URL=http://127.0.0.1:18800 npx playwright test --config playwright.workspace.config.ts` | 11/11 通过；API 使用 fixtures，未启动模型计算 |
| 320/390px 人工截图复核 | 四入口、Data、Runs、Read me 无全页横向溢出；导航和说明可读 |
| 真实 API 联通 | 读取已有教学状态与历史 Run；Run 冻结包为 network-v1，与首页草稿 baseline 包区分 |

前端类型检查不等于全仓库类型检查。全仓库 `tsc --noEmit` 仍有旧 Cloudflare 环境类型与旧 E2E 的 Playwright 类型冲突；本次未改 worker/db。未执行新的全年计算，以上验证不代表模型科学验收。Sites/Cloudflare 部署分支尚未部署验证。

## 本地运行

需要 Node >=22.13、锁定的 npm 11.16.0，以及已有 VALUE Python 环境。依赖锁文件未改变。

```sh
npm ci
npm run build
npm start -- --port 18800
```

另一个终端用项目原有 Python 环境启动 `python -m backend.server --host 127.0.0.1 --port 8766`。如使用独立测试数据，将 `VALUE_DATA_HOME` 设为对应状态目录。浏览器打开 `http://127.0.0.1:18800/`。后端已允许 18800、8800、3000；其他前端端口需要匹配服务端来源配置。

浏览器测试复用已启动的前端，通过 mock 拦截模型 API；先按项目现有方式安装 Playwright Chromium，再执行上表命令。

## 集成范围

本次在独立源码副本实现，基于原 `Value_GoogleCloud_Release/frontend-model` 0.6.0-alpha.2。交付为前端增量文件和补丁，不包含 backend、gridform_core、科学数据、运行状态、node_modules 或部署凭据。应用到其他正在开发的版本前，检查清单中的基线哈希；不同基线按补丁合并并重跑验证。

## 后续设计项

本批完成工作区入口、说明和来源身份基础。完整的四条引导流程、紧凑结果查询适配层、模块作者的测试/差异工作台、扩展脚手架和长周期大结果性能验证仍需后续实现。模型核心的结构优化应配套契约与数值回归单独实施。
