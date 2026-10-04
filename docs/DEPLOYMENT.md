# 安装与部署 / Installation and deployment

## 普通用户

从 [value.ac](https://value.ac) 进入，选择[完整安装包](https://github.com/hanzohanzhe/Value/releases/tag/value-2026-10-03-rc1)，按平台文件名下载，解压并运行安装器。Full 自带 Python 3.10、Node、科学依赖和两个 CC0 教学包，解压后可按平台步骤安装。模型在本机运行，官网负责说明和下载。

| 平台 | 最低平台要求 | 解压后安装 | 安装后启动 |
| --- | --- | --- | --- |
| Linux x64 | glibc 2.28+、kernel 4.18+ | `./install-value` | `~/VALUE-four-role/start-value` |
| Windows x64 | Windows 10+ | `install-value.cmd` | `%USERPROFILE%\VALUE-four-role\start-value.cmd` |
| macOS Apple Silicon / Intel | macOS 15+ | `Install VALUE.command` | `~/VALUE-four-role/Start VALUE.command` |

启动后打开本机浏览器，进入 **Learn → VALUE 101**，创建 Study，先运行一天，再查看 Results。四类使用路径为 `reproduce from existing data`、`add your new data`、`Edit module`、`add new function to VALUE`。

Linux 候选已通过离线安装、移动安装目录后的启动/停止和四类短任务验收。Windows/macOS 为实验候选，已完成归档、架构和依赖检查；原生安装验收、签名与公证待完成。操作系统可能要求确认下载程序的来源。这些检查覆盖安装与短任务运行；科学结果按具体研究配置和时间范围进一步验证。

Download the platform Full archive, extract it, run its installer, then start VALUE locally. Python and Node are bundled. Linux offline installation and bounded role tasks passed; Windows/macOS are experimental candidates awaiting native acceptance and signing/notarisation.

真实研究输入从[数据 Release](https://github.com/hanzohanzhe/Value/releases/tag/value-data-2026-10-04)独立下载，在 **Data** 导入相应 bundle 或 research suite，并阅读其 RIGHTS、ATTRIBUTION 和版本说明。按包内说明区分原始资料、可导入输入与安装组件。软件许可为 Apache-2.0，研究数据保留各自条款。

GBP1 全国数据从 Data 导入；23 区研究套件使用研究套件入口，独立网络组件按包内 Python 安装说明接入。R029 用于普通全国数据输入，博士冻结复跑路径仍待验证。11 区集合先解压，选择包内 33 个网络组件之一，再按 README 使用 Python 安装；全国需求补充资料按包内说明加入相应输入。

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

打开 <http://127.0.0.1:8800>。后台绑定本机，默认端口 8766；前端默认端口 8800。教学包安装器保留已有用户修改，源码调试可用 `VALUE_DATA_HOME` 指定独立的绝对状态目录。以上锁定依赖命令安装完整科学环境；真实研究数据从对应数据发行下载。

公开源码补齐了原字节碳参数、储能技术目录及作者选定的数值契约；其来源见 [runtime parameter notices](../publication/RUNTIME_PARAMETER_NOTICES.md)。源码版本 source-2026-10-04 已完成依赖安装、前端构建与一天教学任务检查。Full 的短任务记录对应安装候选 2026-10-03-rc1；全年研究按各自配置另行验证。原始论文与第三方源出版物从相应出版来源获取。

## 官网的静态部署

使用 Python 3.12+ 标准库，从根目录运行：

```sh
python3 website/build.py
python3 website/check_site.py
python3 -m http.server 8770 --bind 127.0.0.1 --directory website/dist
```

打开 <http://127.0.0.1:8770/zh/> 或 <http://127.0.0.1:8770/en/>。将 `website/dist/` 部署到域名根目录即可；模型求解在用户计算机上运行。正式入口为 value.ac，大型安装包与数据托管 GitHub Releases。方法学 0.3 的网页、Word、PDF、离线 HTML 共用 VALUE 正文，科学依据日期为 2026-10-02。

模型环境 Python 3.10 与官网构建 Python 3.12+ 服务于不同任务。Full 用户按本页安装步骤启动本机应用。详情见 [website/README.md](../website/README.md)、[发行映射](release/release-map.json)和[发布计划](PUBLICATION_PLAN.md)。
