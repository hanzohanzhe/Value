# 最终构建验收：改函数（编辑模块）角色

- 构建：`fix/review-2026-10-04` HEAD `c204aac`（git archive 到 scratch，`vinext build` 重新构建）
- 实例：API 18884、UI 网关 18885，`VALUE_DATA_HOME=scratchpad/build/final_roles/edit-module/state`，只装 VALUE 101 教学包；Playwright headless（chromium 1243）+ API
- 路径：按 MODULE_DEVELOPER_101 第 2、7、9、12、12.1 节，从新用户开始

## 结论：通过但有问题

主路径都能走通：构建并安装改过的模块，派生只改一个槽位的对照 Study，检查 readiness，运行，再比较。就地改源码、隔离、停用、启用、移除、离线恢复和内置模块方法升级确认也都能走通，结果符合手册。发现 2 个中等缺陷、6 个低缺陷，没有高缺陷。

## 已验证可用（证据）

1. **构建**：示例改为 73 GBP/MWh，ID `hx-flat-offer-73`、版本 1.1.0、包 `hx_flat_offer_73`。连续构建两次，SHA-256 都是 `2ff84a0f…`，结果相同。
2. **安装**（Modules 页）：显示 “passed structural conformance”。以下错误情形都被拒绝，信息正确：
   - 再次安装同一 ID：`GF_MODULE_ID_COLLISION`
   - 使用 `gridform.storage-cost/v1`：`GF_MODULE_CONTRACT_MISMATCH`，保留手册引用的句子
   - 使用内置 ID：`GF_MODULE_BUILTIN_COLLISION`
   - 顶层包同名：`GF_MODULE_PACKAGE_COLLISION`
3. **检视**：身份、契约和源码 SHA 都显示出来，可以查看已记录的源码，也能和参考模块对比 manifest 差异。
4. **派生**：“Create an independent Study with one method change” 只改 `storage_cost` 一个槽位。实验性模块必须勾选确认（`GF_EXPERIMENTAL_ACK_REQUIRED`）；保存后 Runs 页显示 A/B 标题。
5. **两时段运行**：Ready，运行完成。storage cost 槽位显示 “Called inside the PSM: the market ledger records its storage offers (2 storage asset-periods)”。
6. **两整年运行与比较**：基线修订 2 用 3.7 分钟完成；派生 Study 用 31 分钟完成。比较时身份检查只有 “Model method … Changed (modules.storage_cost)”。2025 年结果如下，VRE 弃电三项不给差值，并写明原因：

   | 指标 | 基线 | flat-73 |
   | --- | --- | --- |
   | CEM 系统成本 | 14,699,553.28 | 14,789,538.15（差 0.61%） |
   | 碳排放（tCO2e） | 46,239.27 | 46,977.72 |

   年度存储报告中 `fixed_offer_gbp_per_mwh=73`、`current_year_sold_mwh=0`。Market replay 能打开 20 GB 的这个 Run。
7. **就地改源（73→31）**：readiness 出现琥珀色警告 “Module source changed since install (7cb4350d… → 11377575…)”，新的 Run 冻结了新哈希。`/api/comparisons` 在 `identity.method` 下按 `source_sha256` 标出差异。
8. **隔离**（插入错误 import 后点 Rescan）：
   - `/api/health` 为 `degraded`（`GF_MODULE_IMPORT_FAILED`），面板列出原因和清单文件。
   - 选了该模块的 Study 报 `GF_PREFLIGHT_MODULE_QUARANTINED`，Run 按钮禁用。
   - 没选它的 Study 为 Ready，只有 `GF_PREFLIGHT_MODULE_QUARANTINE_PRESENT` 环境提示。
9. **停用、移除、启用**：
   - 在隔离面板点 Disable（有确认框），health 回到 ok；卡片显示 “Used by 2 saved Studies”；readiness 报 `GF_PREFLIGHT_MODULE_DISABLED`。
   - 被引用时 Remove 被拒绝（`GF_MODULE_IN_USE`，列出两个 Study）。
   - 源码未修好就 Enable，报出新的导入错误；修好后 Enable 成功，health 为 ok，readiness 为 Ready。
   - 被引用时，卡片上的 Disable 按钮不可点。
   - 未被引用的模块：Disable → Remove → 文件移到 `disabled-manifests/removed/…` → 同 ID 可以重新安装。
10. **同 ID 两份清单**：Rescan 后两行都被隔离（`GF_MODULE_ID_DUPLICATE`），分别显示各自的清单文件。
11. **离线恢复**：`module_recovery list` 和 `verify` 正常；VALUE 运行时 `disable` 被拒绝；停机后 `park-manifest` 能恢复。
12. **内置方法升级（12.1）**：改 `runtime_compat/storage_cost.py`（2.0.0→2.1.0，利用率下限 0→0.01），同步 manifest、VERSION_LEDGER（`requires_user_opt_in=true`）和 CHANGELOG 中的 id。
    - correction id 拼错时，`check_version_ledger` 失败，`seal_runtime_overlay` 也拒绝。
    - 未封存时，readiness 报 `GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED` 和 `METHOD_UPGRADE_REQUIRED`，不弹确认框。
    - 封存后弹出 “This Study needs your confirmation…”，列出 2.0.0→2.1.0（`uat.method-upgrade-test`）。
    - 取消后被阻断，Run 按钮禁用；再点 Check readiness 会再次弹框。
    - 确认后生成修订 3（`method-upgrade-confirmed`）并变为 Ready；新 Run 记录的版本为 `dynamic-storage-recovery-2026.10.uat`。
    - 不用该模块的 Study 不受影响。
    - 对旧 Run 做严格复现核对，结果为 “当前方式存在阻断”，并列出 2.0.0 对 2.1.0。
13. **模板**：可以下载可编辑源码模板，构建后能安装并通过一致性检查。

## 当前缺陷

### 中1 存储分批（tranche）记录无界增长：磁盘和耗时都远超估计

- **复现**：VALUE 101 两年 Study，选 `hx-flat-offer-73`，Full market replay，运行 Two full model years。
- **现象**：

  | | 磁盘 | 耗时 |
  | --- | --- | --- |
  | readiness 估计 | 约 1.06 GB | 3–18 分钟 |
  | 实际 | 20 GB | 31 分钟 |
  | 同配置基线 | 1.4 GB | 3.7 分钟 |

  每 Run 配额是 21.47 GB，这次已接近上限。
- **原因**：
  - 73 GBP/MWh 的报价高于市场价，电池一直满电、不放电，每时段只补充约 0.0002 MWh。
  - `Battery.stored_energy` 每次补充都按充电时段新开一个 tranche，从不合并；到 2026 年第 14000 时段已有 4435 个。
  - `runtime_compat/modular_simulation_model.py:149-166` 的 `_storage_pre_state` 每个时段、每个阶段都把全部 tranche 写进 `clearing_inputs.payload_json`，单行最大 536 KB（基线约 2.5 KB），总量随时段数平方增长。
- **影响**：年数更多、少放电的储能或报价实验都可能超配额。超配额时会发生什么没有测。

### 中2 同 ID 两份清单时，点隔离行的 Disable 会陷入界面无法恢复的状态

- **复现**：
  1. 安装模块 X，把 `modules/X.json` 复制成 `modules/X-copy.json`，点 Rescan。此时两行都被隔离，这一步正确。
  2. 在显示 “Manifest file: modules/X-copy.json” 的那一行点 Disable。
- **现象**：
  - 服务器按 ID 停用了安装，删掉的是另一份 `modules/X.json`；被点的 `X-copy.json` 留了下来，被报成误导性的 `GF_MODULE_IMPORT_FAILED`（No module named …）。
  - 之后 Enable 报 `GF_MODULE_REGISTRY_CONFLICT`（“did not register”）。
  - Remove 提示 “was removed” 成功，但 `X-copy.json` 仍在，health 一直是 degraded。
  - 再点 Remove 或 Disable，都报 `GF_MODULE_NOT_INSTALLED`。
  - 只有停机后用 `module_recovery park-manifest` 才能恢复；`module_recovery list` 也没有标出这份孤立清单。
- **代码位置**：`gridform_core/module_installation.py` 的 `_set_module_enabled` 固定使用 `root / f"{module_id}.json"`（约第 403 行），没有用行上显示的清单文件。

### 低1 方法升级的修复建议指错入口

- readiness 写的是 “Open the Study and confirm the listed changes (POST /api/projects/<id>/revision-migration)”，但 Studies 卡片和菜单里没有确认入口。
- 实际入口是再点一次 Check readiness 弹出的确认框；建议文字还把原始 API 路径直接给了用户。
- 确认后没有提示 “已保存修订 3”。

### 低2 一年期 Study 列出了跑不了的范围

- 用 VALUE 101 包、2025–2025 的 Study，下拉框里有 “Two full model years”，选了之后 readiness 报 `GF_PREFLIGHT_PARAMETERS`（“requires a project covering at least two years”）。
- 这个包没有单年完整运行的范围。空状态文字写 “start with two full years”，用户只能回去把年份改长。

### 低3 模板名称与实际行为不符

- 从 `dynamic-annual-storage-cost` 下载的模板实际是固定 42 GBP/MWh 的示例，但 manifest 名称是 “Draft Dynamic annual-average storage cost recovery”，安装后的卡片也显示这个名字。

### 低4 用户指南仍用旧产品名

- `docs/USER_GUIDE.md` 第 97、434 行写的是 “Install a FORCE data pack”“FORCE then checks…”，界面上实际是 “Install a VALUE data pack”。
- 故障排查写 “Start GridForm”；`USER_GUIDE_ZH.md` 第 113、166 行同样写 FORCE。

### 低5 比较没有选择基准的地方

- 比较的基准是先勾选的那个 Run，而不是来源或基线 Study。先勾 flat-73 时显示 “hx-flat-offer-73 → dynamic”，差值也以 flat 为基准。
- 页面上没有地方选基准。

### 低6 模块计数不说明实验性模块

- Modules 页显示 “13 of 18/19/20 ready”：已安装、已启用、通过一致性检查的实验性模块算进分母，但从不算 ready，页面也没有说明。

## 环境与清理

- UI 驱动端口用 18984：原计划的 18886 被另一个代理占用。
- API、UI 网关和驱动都按记录的 PID 停止，端口已释放。scratch 中所有 Run 和 trash 已删除（包括那个 20 GB 的 Run），现在约 692 MB；截图保留 10 张，在 `final_roles/edit-module/shots/`。
- INSTALLED 检查：
  - `find … -newer install-receipt.json`（排除 state 和 logs）只列出 `.supervisor.lock`，0 字节，2026-10-03 05:41:26，安装时就有。
  - `diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”
- 没有接触 8766/8800，没有修改 INTEG 或 SRC。内置模块方法升级只改在 scratch 归档副本里。
