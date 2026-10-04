# VALUE Linux local installation candidate / 本地安装候选

This archive contains the four-role frontend, local backend and existing production UI. Supply external **Linux x64 Python 3.10** with numpy, pandas, scipy, xarray, netCDF4 and pyproj installed, and **Linux x64 Node >=22.13**. No runtime/dependency download, pip operation, sudo or system service is performed. Official runtimes: [Python](https://www.python.org/downloads/) and [Node.js](https://nodejs.org/en/download).

本包包含四角色前端、本地后端与已有生产构建；须提供 Linux x64 Python 3.10 及科学依赖、Node >=22.13。安装不下载依赖、不运行 pip、不请求 sudo。

Extract the archive and install into a new or empty user directory:

```sh
./install-value --prefix "$HOME/.local/VALUE four role" \
  --python /absolute/path/to/python3.10 --node /absolute/path/to/node
"$HOME/.local/VALUE four role/start-value"
"$HOME/.local/VALUE four role/diagnose-value"
```

Installation reports its prefix and start entry; existing installations/state are refused and preserved. `VALUE_PYTHON` may select the controller's Python executable (3.10 or newer); `--python` selects the application's Python 3.10 runtime. Keep supplied runtimes at their recorded paths.

安装目录须全新或为空；已有安装与数据不覆盖。`VALUE_PYTHON` 可指定安装器 Python（>=3.10），`--python` 指定应用 Python 3.10。

Start supervises API/UI in the foreground: keep its terminal open. The UI is http://127.0.0.1:8800 and API is 127.0.0.1:8766. Occupied ports cause failure without stopping other processes. Press **Ctrl+C in the start terminal** to stop this instance's API/UI and preserve state. Detached scientific Runs are not cancelled. Diagnose reports installation/runtime information; it does not certify scientific equivalence.

启动终端须保持打开；Ctrl+C 停止本次 API/UI 并保留数据，不取消独立科学 Run。端口占用时拒绝启动，不终止其他应用。

Previously verified execution-archive restoration is scoped to its matching Linux host and dependencies. This frontend installation is not a cross-platform scientific restoration or scientific release acceptance claim.

此前已验历史执行归档恢复仅适用于匹配的 Linux 宿主与依赖；本安装包不代表跨平台复算或科学发布验收通过。
