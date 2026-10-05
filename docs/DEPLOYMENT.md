# 安装与部署 / Installation and deployment

## 普通用户

从 [value.ac](https://value.ac) 进入，选择[完整安装包](https://github.com/hanzohanzhe/Value/releases/tag/value-2026-10-03-rc1)，核对同一 Release 的 SHA256SUMS，解压并运行安装器。Full 自带 Python 3.10、Node、科学依赖和两个 CC0 教学包；用户无需预装这些环境。模型在本机运行，官网负责说明和下载。

| 平台 | 最低平台要求 | 解压后安装 | 安装后启动 |
| --- | --- | --- | --- |
| Linux x64 | glibc 2.28+、kernel 4.18+ | `./install-value` | `~/VALUE-four-role/start-value` |
| Windows x64 | Windows 10+ | `install-value.cmd` | `%USERPROFILE%\VALUE-four-role\start-value.cmd` |
| macOS Apple Silicon / Intel | macOS 15+ | `Install VALUE.command` | `~/VALUE-four-role/Start VALUE.command` |

启动后打开本机浏览器，进入 **Learn → VALUE 101**，创建 Study，先运行一天，再查看 Results。四类使用路径为 `reproduce from existing data`、`add your new data`、`Edit module`、`add new function to VALUE`。

Linux 候选已通过离线安装、移动安装目录后的启动/停止和四类短任务验收。Windows/macOS 为实验候选，目前仅完成归档、架构和依赖检查；原生安装验收、签名与公证待完成。操作系统可能要求确认下载程序的来源。这些检查不构成科学结果验证。

Download the platform Full archive, extract it, run its installer, then start VALUE locally. Python and Node are bundled. Linux offline installation and bounded role tasks passed; Windows/macOS are experimental candidates awaiting native acceptance and signing/notarisation.

真实研究输入从[数据 Release](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-04)独立下载，在 **Data** 导入相应 bundle 或 research suite，并阅读其 RIGHTS、ATTRIBUTION 和版本说明。原始来源文件与可直接运行的输入不是同一对象。软件许可为 Apache-2.0，研究数据保留各自条款。

## 开发者：从源码运行

目标环境为 Python 3.10、Node ≥22.13.0、npm 11.16.0。新建环境并安装锁定依赖：

```sh
python3.10 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements/value-all-py310.lock
python -m pip install -e .
python scripts/install_synthetic_pack.py --value-101-only
npm ci --ignore-scripts
npm run build
```

Windows 激活环境使用 `.venv\Scripts\activate`，并用已安装的 Python 3.10 创建环境。准备完成后，在两个终端分别启动后台与前端：

```sh
python -m backend.server
```

```sh
npm run start
```

打开 <http://127.0.0.1:8800>。后台仅绑定本机，默认端口 8766；前端默认端口 8800。浏览器只访问前端；前端网关（`scripts/value-ui-gateway.mjs`）把 `/api` 连同后台写在 `<VALUE_DATA_HOME>/runtime/api-session-8766.json` 的会话一起转发给后台，因此两个终端必须使用同一个 `VALUE_DATA_HOME`（都不设也可以）。后台不是 8766 时，用 `node scripts/serve-value-ui.mjs --host 127.0.0.1 --port 8800 --api-origin http://127.0.0.1:<端口>` 启动前端。开发服务器 `npm run dev` 挂载同一个网关（`VALUE_API_ORIGIN` 可指定后台）。脚本直接调用后台时用 `backend.api_session.authorized_headers()` 取会话，见 [SECURITY.md](../SECURITY.md)。教学包安装器保留已有用户修改，源码调试可用 `VALUE_DATA_HOME` 指定独立的绝对状态目录。程序不会因只安装 Python 基础包就自动获得全部科学依赖或研究数据。

公开源码补齐了原字节碳参数、储能技术目录及作者选定的数值契约；其来源见 [runtime parameter notices](../publication/RUNTIME_PARAMETER_NOTICES.md)。源码的干净依赖安装、前端构建、wheel 参数成员与一个短教学任务按本次发布记录验证；未重复旧四角色验收或全年研究。原始论文和第三方源出版物不随软件提供。

## 官网的静态部署

只需 Python 3.12+ 标准库，从根目录运行：

```sh
python3 website/build.py
python3 website/check_site.py
python3 -m http.server 8770 --bind 127.0.0.1 --directory website/dist
```

打开 <http://127.0.0.1:8770/zh/> 或 <http://127.0.0.1:8770/en/>。将 `website/dist/` 部署到域名根目录即可；官网不承担模型求解。正式入口为 value.ac，大型安装包与数据托管 GitHub Releases。方法学 0.3 的网页、Word、PDF、离线 HTML 共用 VALUE 正文，科学依据日期为 2026-10-02。

模型环境 Python 3.10 与官网构建 Python 3.12+ 服务于不同任务。普通 Full 用户无需构建官网。详情见 [website/README.md](../website/README.md)、[发行映射](release/release-map.json)和[发布计划](PUBLICATION_PLAN.md)。
