# VALUE 四角色 Windows 安装包

适用于 Windows x64。本包保留四角色前端源码及生产构建、模型源码和两套教学数据；Python、Node.js 和科学依赖由本机提供，安装器不会下载或安装运行时。

准备 Python 3.10 x64（Windows Python Launcher 的 `py -3.10` 可用）、Node.js 22.13.0 或更新版本 x64，以及 Python 环境中的 numpy、pandas、scipy、xarray、netCDF4、pyproj。运行时和科学依赖版本会记录在安装收据中；运行时更新后需重新安装到新的空目录。

1. 完整解压 ZIP，在解压目录运行 `install-value.cmd`。默认安装到用户目录的 `VALUE-four-role`；目标必须为空，已有状态不会被覆盖。
2. 到安装后的目录运行 `start-value.cmd`。看到就绪提示后，自行打开 <http://127.0.0.1:8800/>。
3. 保持启动窗口打开。按 Ctrl+C 停止本次启动的前端和 API。独立运行的模型任务不会被该控制器主动取消。
4. 在安装后的目录运行 `diagnose-value.cmd`，只读检查文件、运行时和日志。日志保存在 `logs`，本地工作状态保存在 `state`。

指定路径时可在命令提示符中使用（路径带空格时保留引号）：

```bat
install-value.cmd --prefix "D:\VALUE 四角色" --python "C:\Python310\python.exe" --node "C:\Program Files\nodejs\node.exe"
start-value.cmd --prefix "D:\VALUE 四角色"
diagnose-value.cmd --prefix "D:\VALUE 四角色"
```

端口 8766、8800 被其他服务占用时启动会拒绝；安装器不会停止占用端口的服务。此包使用前台进程，不注册后台服务。安装前验证清单和文件 SHA-256；这些校验用于发现损坏，不代表发行者数字签名。

本包在 Linux 上组装，尚未在 Windows 实机验证；交付形式是未签名脚本 ZIP，非 EXE 安装器。
