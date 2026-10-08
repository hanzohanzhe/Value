**复现角色验收报告（最终构建 `fix/review-2026-10-04` @ c204aac）**

## 结论：通过但有问题

整条复现路径都能走通：
- 从 Home 进入，建 VALUE 101 基线 Study，再建修正口径和论文复现口径两个 Study；
- 在 UI 中启动 Run，查看结果页，比较两个 Run，导出 CSV 和 JSON，生成 replay 导出和审计包；
- 两个口径各重跑一次，年度结果完全一致。

没有发现高等缺陷。有 2 项中等缺陷和 12 项低等缺陷，都不影响数值结果，主要涉及显示和使用说明。

## 环境

- 源码：`git archive HEAD` 解到 `scratchpad/build/final_roles/reproduce/src`，vinext 构建成功。
- 服务：API 端口 18880（PID 1508457），UI 网关端口 18881（PID 1508811），`VALUE_DATA_HOME=.../final_roles/reproduce/state`。
- 教学数据：这是源码检出，按页面提示运行 `install_synthetic_pack.py --value-101-only` 装入两个 VALUE 101 教学包，用时 0.6 s。
- 测试方式：Playwright headless（chromium 1243）加 API。

## 可用部分与证据

1. **Home 到 Research guide 到 VALUE 101**
   - 教学包未装时，页面明确提示安装方法和命令。
   - 装好后点 “Create baseline Study”，得到 revision 1，页面写明 “Run started: no”。
2. **复现路径**
   - 选择基线，填写名称，“创建复现 Study”后跳到 Runs 页，提示还没有启动 Run。
   - 以论文口径 Study 为基线再走一次，新 Study 正确继承 `methodology.profile=doctoral-lineage-0.6.0a2` 和对应的碳因子参数。
3. **论文复现口径**
   - 在 Studies 编辑器中选择 “Doctoral reproduction”。不兼容的数据包会标出 “not available with this methodology” 并说明原因。
   - Review 一步显示方法学和图 SHA；保存成功。
4. **首次在 UI 启动 Run，进度和响应**
   - Check readiness 给出 35,040 个时段，估计 3–18 min。
   - 点击后页面立即显示 “Preparing · step 1 of 4…”，并有 elapsed 计时和 “1 Run running in background” 徽标。
   - 第二个 Run 启动后正确排队（Waiting for the model process to start），然后进入 Computing year 2026、Finishing outputs，最后 completed。
   - 首次快照约 3 min，计算约 2 min；重跑时 Check readiness 的估计改为 “about 2 min”。
   - 运行期间切换 Market replay、VRE、Inspect、Runs，每次 45–96 ms；rAF 2–11 ms；页面没有卡顿。
5. **结果**
   - 修正口径：
     - 状态：Execution、Contract、Scientific 均为 passed，Energy balance Passed，Stress events None。
     - 2025 年 £14.70m（£62.85/MWh），2026 年 £14.425m（£61.68/MWh）。
     - 碳排放 2025 年 46,239 t，2026 年 38,635 t。
     - 弃电比例 2025 年 3.1%，2026 年 14.6%。
   - 论文复现口径：
     - Raw invariants Passed，年度结果已发布（`raw_invariants_must_pass`）。
     - 2025 年 £14.458m，2026 年 £14.23m。
     - 碳排放标为 not physically interpretable，有 9 条 advisory。
   - Market replay 显示 shortfall 和 Stress events（A2）。Network 页正确说明这是 copperplate Run。Inspect 能看到规划项目和生命周期事件。
6. **比较与导出**
   - 修正口径与论文口径比较：列出方法学差异和每条 advisory，4/9 个指标的差值按原因扣发；导出 CSV（5.9 KB）和 JSON（169 KB）成功。
   - Replay 有界 CSV（168 h，336 行）后台任务完成，可以下载。
   - “Prepare audit bundle” 7.6 s 完成，zip 有 43 个文件，校验完好。
   - “核对冻结输入与执行身份” 22 s 完成，输入完整性 verified，25 个规范角色。
7. **重跑可重复性**
   - 两个口径的重跑与首跑相比，年度结果和投资决策都完全相同。
   - `market/market.sqlite` 逐字节相同；碳账本在去掉 run id 后相同。
   - UI 比较显示 identity 各维度都是 Same，各指标 “+0 · 0%”。
8. 手机宽度 390 px 下，run、journey、projects 三个页面都没有横向滚动。

## 当前缺陷

### 中等

- **R-中1：复现路径和 Runs 启动前都看不到方法学口径。**
  - 复现路径第 2 步只显示基线、年份、保存版本、数据包和模块。
  - Runs 页的 “What will run” 和 preflight 卡片也不显示口径。
  - 复现路径不能选择论文复现口径，只能静默继承基线。用户要到 Studies 编辑器才能看到或选择口径。
  - 复现步骤：Home → reproduce → 选择 “Repro doctoral” 或 “VALUE 101 baseline” 作为基线 → 第 2 步没有 Methodology 字段 → 进入 Runs 页，同样没有。
- **R-中2：两个口径之间最明显的弃电差异，在比较和 Run 卡片上都看不到。**
  - VRE 页显示：修正口径未用 VRE 3.1%/14.6%，论文口径 <0.1%。
  - Runs 卡片上的 “Final VRE curtailment” 却写 “Unavailable — module does not provide counterfactual snapshot”。
  - 比较页和导出 CSV 里，三个弃电指标全部为空或被扣发。
  - 按 v2 归因定义这可能是设计行为，但比较中缺少可用的物理未用 VRE 指标。
  - 复现步骤：比较两个 repro Run，看 VRE curtailment 行；再对照 VRE 页和 metrics 中的 `curtailment_mwh`（4,003 和 25,026 MWh）。

### 低等

- **R-低1：** Run 还在准备时，Market replay 每次轮询都重新请求 `/market/capabilities`，每次都是 404，30 s 内控制台约 15 条错误；VRE 页和 Inspect 页也有 404。
  - 原因：`app/page.tsx:225` 的 effect 依赖 `run` 对象，而它每次轮询都会被替换。
- **R-低2：** 论文口径 Run 在准备阶段就显示 “Annual results withheld… raw invariants were not evaluated” 和 Withheld 卡片，应该显示为“待评估”。
- **R-低3：** 正在 snapshotting 或 running 的 Run 也会显示 “历史复现条件检查 / 从此 Run 的冻结输入创建独立 Study” 面板。
- **R-低4：** 年度卡片 Planning evolution 显示 “Active: 0”，而 Inspect 中 2026 年有 2 条 Active 记录（2027 年完工）。这是 R4-2 §8 已提出的遗留，仍未统一。
- **R-低5：** advisory `p07.compatibility-capital-out-of-headline`（high）的 `applies_when` 为 `{}`，附在没有径流水电的 VALUE 101 论文 Run 上，比较页的警告里也出现。其他 advisory 已按资产存在与否筛选，这一条没有。
- **R-低6：** Inspect 规划表的 Project 列把同一个 ID 显示两次（名称等于 ID）；生命周期事件的 Transition 列全是 “- -> -”。
- **R-低7：** 没有扩展的 Run 打开 Artifacts 页签，显示 “Extension results unavailable: frozen_extension_graph_missing”、“Frozen module graph Not recorded”、“Year-results SHA-256 Not recorded”。实际上 `module-resolution.json` 和 `year-results-v2.json` 都存在，Study 也有 graph SHA。VRE 页的 “Module graph SHA-256” 同样显示 Not recorded。
- **R-低8：** 两次逐位一致的重跑，2026 年的 `annual_input_state_sha256` 不同（修正口径 de94… 对 2934…，论文口径 39fb… 对 f945…），因为带 run id 前缀的项目 ID 进入了状态。这个哈希因此不能用来核对可重复性。
- **R-低9：** Replay CSV 导出没有 `shortfall_mwh` 和 stress 相关列，而 API 和 UI 都有。价格列名为 `clearing_price_gbp_per_mwh`，UI 上标为 “Demand-weighted average period cost”，与 Q6 按口径命名不一致。
- **R-低10：** 同一个 “Accepted supply” 标签在两个口径下统计边界不同，UI 没有说明。
  - 2025-01-01 窗口：修正口径 787.02 MWh（等于需求加充电），论文口径 775.49 MWh（等于需求，充电来自 pre-balancing excess）。
  - 年度 `total_energy_generated` 的口径也不同：论文口径中 gen + discharge = served。
- **R-低11：** 复现路径的名称为空时，“创建复现 Study”按钮是灰的，但没有说明原因，只有 placeholder，也没有默认名称。
- **R-低12：** 比较 CSV 中被扣发的指标值留空，没有原因列；UI 上是有原因说明的。
- **R-低13：** Runs 页默认的 scope 是 “Two-period wiring check”，但空状态文案写 “start with two full years”。

## 清理与核对

- 只按记录的 PID 停止了自己启动的 API（1508457）和 UI（1508811），没有遗留进程；没有连接 8766/8800 端口。
- 已删除 src、state（约 950 MB）、浏览器 profile 和审计 zip。scratch 只剩约 2.7 MB。
- 保留 10 张截图，在 `.../scratchpad/build/final_roles/reproduce/shots/`，包括 01-home、03-value101、07-preflight-corrected、08-run-progress、09-composer-doctoral-review、11-runs-doc、12-Marketreplay-corr、12-VRE-corr、13-compare、15-rerun-compare。
- INSTALLED：
  - `find … -newer install-receipt.json …` 只列出 `.supervisor.lock`，是作者实例的 0 字节锁文件，早已知道。
  - `diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”。输出中另有一行 vinext 静态文件 “Premature close”，出现在诊断探测时，没有影响结论。
- 没有改动 INTEG 工作树，`git status` 干净；没有提交，也没有 push。