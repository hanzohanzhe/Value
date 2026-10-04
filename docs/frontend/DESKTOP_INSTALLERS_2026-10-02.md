# 三平台本地安装包交付

2026-10-02。使用 `scripts/build_desktop_installers.py` 从验收包 SHA-256 `4bc7781a4741556adeece3b0ce49b8f4e972f14ac38390445a314550cb292e32` 构建三个独立安装包。共同应用 2,028 文件不变；新增 `packaging/desktop-local` 前台监督式安装器，外部 Python 3.10 / Node >=22.13，无依赖下载或系统服务。Windows ZIP、macOS ZIP、Linux tar.gz 的内容及权限清单均已验证；Linux 实际安装与启停通过，Windows/macOS 原生执行未验证。运行时调用保留 venv 启动路径。原日常服务已恢复，18份Study/revision和142份冻结输入哈希不变。

交付与说明：[VALUE-desktop-installers-2026-10-02]([LOCAL_PATH_REDACTED])；[平台验证记录]([LOCAL_PATH_REDACTED])。

打包未运行模型，未改变已有四角色验收结论。源与归档快照通过SHA核对，不以Git tracked列表收集，以保留尚未提交的四角色修复。
