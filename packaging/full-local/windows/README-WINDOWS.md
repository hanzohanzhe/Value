# VALUE Windows x64 完整离线安装包

Windows 10 或更新版本 x64。本包未签名，尚未完成 Windows 实机验证。

包内包含私有 Python 3.10、完整科学依赖、Node 和四角色应用；安装与内置教学无需联网或系统 Python、Node。完整解压后保留 runtime 目录；不允许 --python/--node 外部覆盖。

1. 完整解压后运行 `install-value.cmd`。默认安装到 `%USERPROFILE%\VALUE-four-role`，目标必须为空。
2. 在安装后的目录运行 `start-value.cmd`。
3. 需要检查时，在安装目录运行 `diagnose-value.cmd`。

指定新目录示例：

```
install-value.cmd --prefix "D:\VALUE-new"
```

首页建议按四角色顺序使用：复现已有教学 Study → 用自己的数据建立独立 Study → 修改模块建立方法 Study → 安装扩展并检查结果与来源。内置 value-101-baseline-v1 / value-101-network-v1 数据包支持离线教学。

启动保持前台；看到就绪提示后打开 http://127.0.0.1:8800/ 。按 Ctrl+C 停止本次服务。状态在安装目录的 state，日志在 logs；端口 8766、8800 须空闲。

升级须安装到另一个空目录；当前不支持状态自动迁移或覆盖已有安装。失败只清理本次临时目录。安装完成后可删除解压源目录。运行时哈希或版本变化需重新旁路安装。

双击运行时保留窗口供阅读路径或错误；命令行传入参数时不会等待关闭。

关闭 VALUE 时，正在运行的 Run 会在后台继续，停止提示会列出它们；下次启动时 VALUE 通过各 Run 的租约（worker.lock）重新接管监督。同一个状态目录只能由一个 VALUE 后端使用，第二个后端会以退出码 3 停止且不改动任何内容。若诊断报告安装目录的 `__pycache__` 中有多余字节码（stray bytecode），VALUE 不会读取它们；运行 `diagnose-value.cmd --repair-bytecode` 可把它们移入 state/quarantine，只读安装会保留原位。
