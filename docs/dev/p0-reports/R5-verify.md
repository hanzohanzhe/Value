# R5 定向验证报告（DECISIONS A28）

- 被测构建：`fix/review-2026-10-04` @ `cbdb69a`（`git archive` 到 `scratchpad/build/r5verify/src`，vinext 重新构建）。
- 实例：API 18870（PID 2741800）、UI 网关 18871（PID 2741801），`VALUE_DATA_HOME=scratchpad/build/r5verify/state`（全新目录，`install_synthetic_pack.py --value-101-only`）。Playwright headless（chromium 1243）+ API。
- 范围（A28）：只重跑 `scratchpad/build/r5/*.md` 中每个高、中缺陷的复现步骤，以及 R5 标为已修、影响结果的项；另跑 VALUE 101 修正口径和论文口径两年 Run 各一次作冒烟检查。不做新的探索性测试，不改代码。

## 1 缺陷对照表

| 缺陷 | 结论 | 证据 |
|---|---|---|
| S-F-高1 需求标签 MWh/period、实际按 MW 读 | 已修 | 工作区绑定带 `runtime_unit_interpretation`（declared MWh/period → runtime MW）；角色卡与映射编辑器显示“按 MW 读取…已知误标…请选择 MW”；上传基线 ×1.15 的 MWh/period 文件，审阅给出 `GF_DATA_DEMAND_SCALE … 537,902 MWh … 2.30 times … (about 233,870 MWh per year)`；复制包校验对 demand.real、demand.forecast 各给一条 2.30 倍告警；比较页有 `Annual demand (MWh)`：233,870.27 对 537,901.63（+130%） |
| S-F-中1 Run 运行时映射编辑器被清空 | 已修 | 有 Run 在 queued/snapshotting 时暂存 CSV，20 s 内工作区轮询 11 次，`resolve-draft` 与映射目录请求 0 次，列选择 10 次采样都保留；随后预览、提交成功 |
| S-F-中2 单位成本把 stress 缺口算作已供电 | 已修 | 2.3 倍需求 Run：2025 年 A2 缺口 28,333.03 MWh（PSM 记录 2,736.46，隐藏 25,596.57）。`demand_served_mwh` 509,568.60 = 537,901.63 − 28,333.03；每 MWh 成本 79,806,844.69 / 509,568.60 = 156.62 GBP/MWh；碳强度 144,583.9 t / 509,568.6 MWh = 283.74 kg/MWh。年度卡片（2026）`Unserved demand 23,325.39 MWh · incl. stress shortfall · 2,411.73 MWh recorded by the PSM`；比较页两行分列（28,333.03 与 2,736.46 MWh） |
| S-F-中3 逐时需求无法导入、说明矛盾 | 已修 | 2024 逐时 8,784 行（ISO、UTC、MW）带时间戳列：完整校验通过，只有一条 `GF_MAPPING_HOURLY_DEMAND … 17,568 half-hour periods`，没有“至少 17520 期”“60 分钟缺口”“重复补齐/请确认”；提交成功；规范文件 17,568 行，每小时值重复两次（63.7691、63.7691、63.9805、63.9805…，末行 61.6480×2） |
| R-中1 创建前、启动前看不到方法学口径 | 已修 | 复现路径第 2 步：`方法学口径 Doctoral reproduction` / `Corrected (default)`；Runs 页 What will run：`Methodology Doctoral reproduction` / `Corrected (default)` |
| R-中2 比较页和 Run 卡片看不到弃电差异 | 已修 | 修正口径卡片 `Unused VRE (PSM boundary) 25,026.5 MWh · 14.6% of available`，论文口径 `2 MWh · <0.1%`；比较页 `Unused VRE at the PSM boundary (MWh)` 两个值都给出，差值按 0e1cb2e 规则扣发并写明原因（两口径 PSM 边界不同）；比较 CSV 中 4 个值都有 |
| E-中1 储能 tranche 记录无界增长 | 已修 | flat-73 模块（ID `hx-flat-offer-73`）、full 追踪、两整年：readiness 给出 `GF_PREFLIGHT_ESTIMATE_STORAGE_MODULE`；计算 6.8 min（与另两个 Run 并行），输出 1.6 GB（market.sqlite 1.56 GB）；`clearing_inputs` 70,080 行，单行最大 26,823 B、平均 12,349 B，67,482 行为压缩表示（`stored_tranche_count` 129…）。2025 CEM 成本 14,789,538.15，与 R4 报告逐位相同（结果未变） |
| E-中2 同 ID 两份清单 | 已修 | 复制清单后 Rescan：两行隔离 `GF_MODULE_ID_DUPLICATE`；界面在副本行点 Disable：提示写出 `modules/disabled-manifests/modules/hx-dup-demo-copy.….json`，面板消失，health ok。旧坏状态（停用安装 + 残留副本）下 Enable 返回 409 `GF_MODULE_ID_COLLISION` 并写出副本文件名；再 Disable 移走副本（`parked_manifests`），Enable 200，health ok |
| F-中1 原地改源的扩展停用后无法启用 | 部分修复（行为按 R5-4 保留，待作者决定） | 原地改 hooks.py → Rescan → Disable → Enable：仍 400 `GF_EXTENSION_SOURCE_CHANGED`，但信息写明改动的钩子模块和两条出路（恢复原文件，或改版本号与包名重建后安装）；恢复原文件后 Enable 200 |
| F-中2 第二个草稿重名报 revision conflict | 已修 | API 第二次以相同名称新建：409 `GF_STUDY_ID_EXISTS`，提示改名；界面第二个独立草稿默认名 `VALUE 101 baseline · extension study 2` |
| F-中3 非 after_psm 钩子的产物被静默丢弃 | 已修 | 扩展加 after_cem 钩子返回带 `artifact_type` 的产物：Run 失败，diagnostics/error.json 写明 “VALUE records extension artifacts only from after_psm … Return the artifact from after_psm” |
| R-低5 径流水电 advisory 不按资产筛选（影响结果标注） | 已修 | VALUE 101 论文口径 Run 的 advisory 为 8 条，不再含 `p07.compatibility-capital-out-of-headline` |
| R-低9 Replay CSV 缺 stress 列（导出内容） | 已修 | 两口径 24 h 导出都有 `clearing_price_basis`、`period_shortfall_mwh`、`period_stress`、`shortfall_basis` |

## 2 冒烟 Run（两整年，35,040 时段）

| | 修正口径（value-101-baseline） | 论文口径（repro-doctoral） |
|---|---|---|
| 状态 | completed；execution、scientific passed；能量平衡 passed；无 stress；已发布 | completed；execution passed、scientific reproduction_conformant；raw invariants passed，已发布 |
| 2025 系统成本 | £14,699,553（£62.85/MWh） | £14,458,446（£61.82/MWh） |
| 2026 系统成本 | £14,424,989（£61.68/MWh） | £14,230,219（£60.85/MWh） |
| 碳排放 2025 / 2026 | 46,239 / 38,635 tCO2e | 不给数值（论文口径标为不可物理解释） |
| 未用 VRE 2025 / 2026 | 4,002.9 / 25,026.5 MWh（3.1% / 14.6%） | 2.0 / 2.0 MWh |
| 年需求 / 已供电 | 233,870.27 / 233,870.27 MWh | 233,870.27 / 233,870.27 MWh |
| advisory | 0 | 8 |

两个口径的数值与 R4 验收报告一致。

## 3 观察（不在本轮范围，不阻塞）

1. 在有 Run 排队时改模块（确认框写 “would start with the changed code”），排队的 Run 实际以 `GF_CONTRACT_001`（“A selected module did not satisfy its declared contract”）失败，日志原因是 “Execution source or runtime changed after enqueue”。安全地失败，不产生错误结果，但确认框文案与错误码有误导。
2. F-中3 的具体原因只在 diagnostics/error.json，Runs 页只显示通用的 `GF_CONTRACT_001`。

## 4 环境与清理

- 两个服务按记录的 PID 停止，端口 18870/18871 已释放；没有连接 8766/8800，没有按模式 kill。
- 删除了 src、state（约 1.8 GB，含 flat-73 Run）、浏览器配置；`scratchpad/build/r5verify` 剩 3.7 MB（脚本、15 张截图）。
- INSTALLED：`find … -newer install-receipt.json …` 只列出 `.supervisor.lock`（作者实例的锁文件）；`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”（有一行已知的 vinext “Premature close” 日志）。
- Python 全部经 `vpy` 调用；本单元不改代码，只提交本报告。
