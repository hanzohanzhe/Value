# VALUE macOS local installation candidate / 本地安装候选

This archive contains the four-role frontend, local backend and existing production UI. It requires external runtimes: **macOS Python 3.10** with numpy, pandas, scipy, xarray, netCDF4 and pyproj already installed, and **Node >=22.13**. Python and Node must use the same architecture: Intel x64 or Apple Silicon arm64. Architecture support describes runtime checks; no native macOS binary or macOS device validation is claimed. The archive and `.command` scripts are unsigned and unnotarized. No runtime download, pip operation or administrator access occurs.

本包包含四角色前端、本地后端与已有生产构建。须自行提供已安装科学依赖的 macOS Python 3.10 与 Node >=22.13，二者架构一致。Intel / Apple Silicon 为外部运行时检查支持，尚未在 mac 实机验收；本包未签名、未公证。安装不会下载依赖或请求 sudo。

Extract the archive. In Terminal, run from the extracted directory (quote paths containing spaces):

```sh
./"Install VALUE.command" --prefix "$HOME/Applications/VALUE four role" \
  --python /absolute/path/to/python3.10 --node /absolute/path/to/node
"$HOME/Applications/VALUE four role/Start VALUE.command"
"$HOME/Applications/VALUE four role/Diagnose VALUE.command"
```

The installer accepts only a new or empty directory and preserves existing installations/state. The default prefix is reported by the installer; use the reported start entry. `VALUE_PYTHON=/absolute/path/to/python` chooses the Python that runs the controller; `--python` chooses the application's Python runtime. Finder launch searches typical Homebrew and Python 3.10 framework locations. Terminal arguments are recommended when choosing runtime paths or an installation path. Official runtime downloads: [Python](https://www.python.org/downloads/) and [Node.js](https://nodejs.org/en/download).

安装目录必须全新或为空；已有目录与数据不会覆盖。安装成功后按输出中的路径启动。需要自定义路径时使用上述 Terminal 命令。`VALUE_PYTHON` 控制安装器 Python，`--python` 指定应用运行时。

Start keeps the terminal open while supervising API/UI. Open http://127.0.0.1:8800; the API uses 127.0.0.1:8766. An occupied port causes failure without stopping existing applications. Press **Ctrl+C in the start terminal** to stop this instance's API/UI. Detached scientific Runs are separate and are not cancelled by stopping the frontend. State is retained. Diagnose reports local installation/runtime information; it is not scientific validation.

启动终端须保持打开；Ctrl+C 停止本次 API/UI 并保留数据。停止前端不取消独立模型 Run。端口被占用时拒绝启动，不终止其他应用。

The previously verified Linux execution-archive restoration workflow is Linux-only; a historical Linux archive is not portable to macOS through this installer. Scientific acceptance and numerical equivalence remain separate release gates.

此前已验 Linux 历史执行归档恢复仅适用于其 Linux 平台；本安装器不提供跨系统历史复算保证。

关闭 VALUE 时，正在运行的 Run 会在后台继续，停止提示会列出它们；下次启动时 VALUE 通过各 Run 的租约（worker.lock）重新接管监督。同一个状态目录只能由一个 VALUE 后端使用，第二个后端会以退出码 3 停止且不改动任何内容。若诊断报告安装目录的 `__pycache__` 中有多余字节码（stray bytecode），VALUE 不会读取它们；运行 `Diagnose VALUE.command --repair-bytecode` 可把它们移入 state/quarantine，只读安装会保留原位。
