# VALUE macOS 完整离线安装包

macOS 15 或更新版本；选择与 Intel / Apple Silicon 对应的归档。本包未签名、未公证，尚未完成 macOS 实机验证；系统可能要求在隐私与安全设置中允许打开。

包内包含私有 Python 3.10、完整科学依赖、Node 和四角色应用；安装与内置教学无需联网或系统 Python、Node。完整解压后保留 runtime 目录；不允许 --python/--node 外部覆盖。

1. 完整解压后运行 `Install VALUE.command`。默认安装到 `~/VALUE-four-role`，目标必须为空。
2. 在安装后的目录运行 `Start VALUE.command`。
3. 需要检查时，在安装目录运行 `Diagnose VALUE.command`。

指定新目录示例：

```
./"Install VALUE.command" --prefix "$HOME/VALUE-new"
```

首页建议按四角色顺序使用：复现已有教学 Study → 用自己的数据建立独立 Study → 修改模块建立方法 Study → 安装扩展并检查结果与来源。内置 value-101-baseline-v1 / value-101-network-v1 数据包支持离线教学。

启动保持前台；看到就绪提示后打开 http://127.0.0.1:8800/ 。按 Ctrl+C 停止本次服务。状态在安装目录的 state，日志在 logs；端口 8766、8800 须空闲。

升级须安装到另一个空目录；当前不支持状态自动迁移或覆盖已有安装。失败只清理本次临时目录。安装完成后可删除解压源目录。运行时哈希或版本变化需重新旁路安装。

双击运行时保留窗口供阅读路径或错误；命令行传入参数时不会等待关闭。
