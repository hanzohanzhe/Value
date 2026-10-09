# 安装与部署 / Installation and deployment

## 普通用户

从 [value.ac](https://value.ac) 进入，选择[完整安装包](https://github.com/hanzohanzhe/Value/releases/tag/value-2026-10-09-a1)，按平台文件名下载，解压并运行安装器。Full 自带 Python 3.10、Node、科学依赖和两个 CC0 教学包，解压后可按平台步骤安装。模型在本机运行，官网负责说明和下载。

| 平台 | 最低平台要求 | 解压后安装 | 安装后启动 |
| --- | --- | --- | --- |
| Linux x64 | glibc 2.28+、kernel 4.18+ | `./install-value` | `~/VALUE-four-role/start-value` |
| Windows x64 | Windows 10+ | `install-value.cmd` | `%USERPROFILE%\VALUE-four-role\start-value.cmd` |
| macOS Apple Silicon / Intel | macOS 15+ | `Install VALUE.command` | `~/VALUE-four-role/Start VALUE.command` |

启动后打开本机浏览器，进入 **Learn → VALUE 101**，创建 Study，先运行一天，再查看 Results。首页的四条路径为 **Reproduce from existing data**、**Add your new data**、**Edit a module**、**Add a new function to VALUE**。界面默认英文，可在侧栏底部切换为中文。

安装到不存在或为空的目录。各平台的实际验收记录见[下载页](https://value.ac/zh/releases/)。Windows/macOS 为实验性版本，原生安装验收、签名与公证列入后续发布。一台电脑一个使用者，共用电脑与远程桌面服务器的部署需要额外隔离。

Download the platform Full archive, extract it and install into a new, empty directory. Start VALUE and open the printed local address, normally http://127.0.0.1:8800. Python and Node are bundled. Read the platform acceptance record on the download page; Windows and macOS are experimental.


真实研究输入从数据 Release 独立下载，在 **Data** 导入，并阅读其 RIGHTS、ATTRIBUTION 和版本说明。VALUE 0.7.0 按方法学口径选择数据：修正口径（默认）的全国研究使用随 0.7.0 发布的 R029 public2 或 GBP1 public2（[数据发行 value-data-2026-10-09](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-09)，`value-uk-calendar-vx-trade001-public2-2026-10-09.zip`、`value-uk-open-data-pack-public2-2026-10-09.zip`），在 **Data** 的“Install a VALUE data pack”导入；论文复现口径使用 [value-data-2026-10-04](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-04) 中的 GBP1 public1。public2 两包不适用于论文复现口径，public1 两包在修正口径下运行时报 `GF_DATA_SHORT_SERIES`。public2 的互联线潮流符号已声明、未对照来源核实。软件许可为 Apache-2.0，研究数据保留各自条款。

23 区网络研究使用同一数据发行中的 GBP1 public2 研究套件 `VALUE-UK-GBP1-23zone-research-suite-public2-2026-10-09.zip`，在 **Data** 的“Install the VALUE-UK research suite”导入：它原样包含 GBP1 public2 与 23 区网络包 `value-gb-zonal-network-v1-c9e841112c40`，并创建两个未运行的 Study（`value-uk-copperplate-2025-2034-public2`、`value-uk-zonal-2025-2034-public2`，修正口径）。该网络包把火电、核电（包括 B6 以北的 Torness）、径流水电、储能和进口都放在 `ENGLAND_FALLBACK` 区；分区潮流与阻塞结果的空间分布只具指示意义，详见方法学的网络章节。

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

打开 <http://127.0.0.1:8800>。后台绑定本机，默认端口 8766；前端默认端口 8800。浏览器只访问前端；前端网关（`scripts/value-ui-gateway.mjs`）把 `/api` 连同后台写在 `<VALUE_DATA_HOME>/runtime/api-session-8766.json` 的会话一起转发给后台，因此两个终端必须使用同一个 `VALUE_DATA_HOME`（都不设也可以）。后台不是 8766 时，用 `node scripts/serve-value-ui.mjs --host 127.0.0.1 --port 8800 --api-origin http://127.0.0.1:<端口>` 启动前端。开发服务器 `npm run dev` 挂载同一个网关（`VALUE_API_ORIGIN` 可指定后台）。脚本直接调用后台时用 `backend.api_session.authorized_headers()` 取会话，见 [SECURITY.md](../SECURITY.md)。教学包安装器保留已有用户修改，源码调试可用 `VALUE_DATA_HOME` 指定独立的绝对状态目录。以上锁定依赖命令安装完整科学环境；真实研究数据从对应数据发行下载。

公开源码补齐了原字节碳参数、储能技术目录及作者选定的数值契约；其来源见 [runtime parameter notices](../publication/RUNTIME_PARAMETER_NOTICES.md)。源码版本为 source-2026-10-09，Full 批次为 2026-10-09-a1。构建来源与验收记录见[发行映射](release/release-map.json)和软件发行页。原始论文与第三方源出版物从相应出版来源获取。

## 官网的静态部署

使用 Python 3.12+ 标准库，从根目录运行：

```sh
python3 website/build.py
python3 website/check_site.py
python3 -m http.server 8770 --bind 127.0.0.1 --directory website/dist
```

打开 <http://127.0.0.1:8770/zh/> 或 <http://127.0.0.1:8770/en/>。将 `website/dist/` 部署到域名根目录即可；模型求解在用户计算机上运行。正式入口为 value.ac，大型安装包与数据托管 GitHub Releases。方法学 0.4.1 的网页、Word、PDF、离线 HTML 共用 VALUE 正文，对应 VALUE 0.7.0-alpha.1，模型与数据依据日期为 2026-10-09。

模型环境 Python 3.10 与官网构建 Python 3.12+ 服务于不同任务。Full 用户按本页安装步骤启动本机应用。详情见 [website/README.md](../website/README.md)、[发行映射](release/release-map.json)和[发布计划](PUBLICATION_PLAN.md)。
