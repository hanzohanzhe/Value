# M0 集成报告：五条 lane 合入 `fix/review-2026-10-04`

- 集成分支：`fix/review-2026-10-04`（INTEG worktree），合并前 tip 为 `bce7102`（M0-X0 第三轮报告）。
- 合并方式：按任务指定的顺序 m0-p04 → m0-p06 → m0-p07 → m0-p05 → m0-p09，每条都用 `git merge --no-ff`。lane 的提交原样保留，没有 squash，也没有改写历史。
- 解释器：一律经 `build/bin/vpy`（`-B`、`PYTHONDONTWRITEBYTECODE=1`、`PYTHONPYCACHEPREFIX` 指向 scratch）；node 经 `build/bin/vnode`（`VALUE_NODE`）。`TMPDIR` 与 `VALUE_DATA_HOME` 都设在 `build/m0merge/` 下。
- 本次集成**没有任何数值行为改变**。五条 lane 都只做 HEAD 采集或测试基础设施，两族 golden 文件都没有动。

## 1 合并提交

| 合并提交 | lane（tip） | 内容 | 冲突与处理 |
|---|---|---|---|
| `749b6b6` | m0-p04（`04a89a3`，4 个提交） | P0-4 S1：能量平衡契约、只出报告的只读 oracle、派生夹具与逐表 HEAD golden、`test_release_members_cover_imports` | 无冲突。发布清单自动合并，`refresh_source_release_manifest.py --index --check` 确认不过期 |
| `89c400f` | m0-p06（`08cb5b1`，16 个提交） | P0-6 S1：96 期合成默认 PSM golden（带 HEAD 源码 sha 校验，frozen 与 live 两条循环）、48 期 value_101_day e2e 基线、native reproduction harness 与采集工具 | 只有 `source-release-manifest.json` 冲突（两侧都新增条目）。按 C25 处理：取本侧，重跑 `--index` 刷新（补入 P0-6 的 6 个路径），`--check` 不过期 |
| `4f7f126` | m0-p07（`ecc39c5`，17 个提交） | P0-7 S1：投资判据纯函数模块 `investment_accounts.py`（未接入任何生产路径）、HEAD decide() 记录（10 个情形）、仓内源规则 oracle | 只有发布清单冲突，处理同上（补入 6 个路径）。**lane 状态为 unapproved**，见第 5 节 |
| `9bb9a83` | m0-p05（`3e593f9`，2 个提交） | P0-5 S0：VALUE 101、GBP1 public1、R029 public1 的 HEAD 数据读取基线与声明覆盖矩阵 | 只有发布清单冲突，处理同上（补入 5 个路径） |
| `b07eb6a` | m0-p09（`c1ceed0`，16 个提交） | P0-9 S0：离线 e2e 服务、`--offline` 子集与棘轮、UI 测试分组、SSR 助手、`.ts` 导入后缀；`p0_gate` 的 `e2e_offline` 成为 full/nightly 强制步骤；P0-9 S2 的 UI 契约夹具生成器；P0_CONVENTIONS 第 2 节强制步骤表与新增第 11 节 | 无冲突。清单自动合并后 `--check` 不过期；UI 契约夹具在合并结果上 `--check` 0 处差异，无需重新生成 |
| 本报告提交 | — | `docs/dev/p0-reports/M0-merge.md` | — |

每个合并提交的正文都按 P0_CONVENTIONS 第 1 节写了 Findings / Track / Correction ids / Golden / Delta / Tests 六个小节，末尾带 Co-Authored-By。`git branch --merged` 确认五个 lane 分支都已包含在集成分支中。

### 关于冲突热点（第 5 章）

五条 lane 改动的文件除发布清单外互不重叠：p04、p05、p06、p07 只新增文件；p09 修改 `scripts/p0_gate.py`、`docs/dev/P0_CONVENTIONS.md`、`tests/test_p0_gate.py`、e2e 与前端测试文件、`package.json`、`tsconfig.json`、`playwright.config.ts`，这些文件在 `bce7102` 之后的集成分支上没有其他改动。因此唯一实际出现的热点是 **C25（发布清单）**，三次都按“任取一侧，再用工具刷新”处理，没有手工编辑 JSON。

以下热点经核对，本次合并不涉及：C17（各包 golden 复用 `golden.py`：p04 的逐表 golden 与 p06 的合成 golden 都复用了 `gridform_validation.golden` 与 `zones.json`，本次没有改 zones.json）；C18/C19（本次没有任何 `runtime_compat/` 改动，`runtime_overlay` 步骤每次都通过；`BOUNDARY_REGISTRY` 只有 p04 一份，P0-6 的 `native_corrected_full_node_v1` 留待 M3）；C13（p09 S0 已按计划放在 M0）；C22/C23/C29（没有包修改 `staged_psm.py`、模块版本或 `application.py`）。p07 回退了它对 `canonical_psm_data.py` 的改动，该文件与 35aadb3 逐字节相同，doctoral 天气身份哈希不变。

## 2 每次合并后的验证

所有门禁都写报告到 `build/m0merge/gate-*.json`，“passed”均指 `status: passed`、无豁免（waivers 为空）。

| 合并 | 受影响测试 | 结果 | `p0_gate quick` |
|---|---|---|---|
| m0-p04 | `test_energy_balance_oracle`、`test_p04_variant_fixtures`、`test_release_members_cover_imports`；`p04_capture_trajectory_golden.py check` | 35 个测试 OK；7 个变体在精确模式下全部无差异 | passed（84 s），ratchet 1484 个 id、164 个失败、new 0、fixed_but_listed 0、禁用端口 0 |
| m0-p06 | `test_native_reproduction_golden`；`capture_native_reproduction_golden.py check` 与 `check-e2e` | 33 个测试 OK（提交后）；frozen 与 live 两条循环 0 差异；e2e 基线在 trajectory/accounting 区一致 | passed（86 s），ratchet 1517 / 164，new 0、fixed 0 |
| m0-p07 | `test_p07_investment_accounts`、`test_p07_head_decide_record`、`test_p07_doctoral_source_oracle`；`p07_record_head_decide.py --check` | 67 个测试 OK；HEAD decide 记录可复现 | passed（86 s），ratchet 1584 / 164，new 0、fixed 0 |
| m0-p05 | `test_p0_5_baseline`（设置 `VALUE_P0_5_PACKS` 指向 staging 中的 gbp1-national 与 r029-public1）；`capture_p0_5_baseline.py check` | 11 个测试 OK（含研究包回放，约 67 s）；4 个包无差异。两个研究包目录在运行前后的文件清单（路径、大小、mtime）哈希相同 | passed（87 s），ratchet 1595 / 164，new 0、fixed 0 |
| m0-p09 | `test_ui_contract_fixtures`、`test_p0_gate`；`ui_contract_fixtures.py --check`；`scripts/run-ui-tests.mjs harness`（缓存的 chromium_headless_shell-1243） | 47 个测试 OK；夹具 28 个、0 处差异、193,585 字节、7 项不变式通过；harness 2/2 | passed（88 s），ratchet 1613 / 164，new 0、fixed 0；node_tests 已包含新加入的 unit 与 render 组 |

说明：m0-p06 的 `test_fixtures_were_captured_clean_from_committed_tooling` 在合并尚未提交时失败，另有一个用例 skip。这两个用例都要求 lane 的工具提交能从 HEAD 到达（`git rev-list HEAD`、`git show HEAD:...`），合并进行中 HEAD 仍是合并前的提交，所以不满足。提交合并后重跑，33/33 通过，没有 skip。lane worktree 中原本也是全部通过。

### 合并完成后的里程碑门禁（nightly，包含 full 的全部步骤）

在 `b07eb6a` 上运行 `p0_gate nightly`：**status passed，waivers 为空**，总耗时 1366 s。

| 步骤 | 结果 |
|---|---|
| guard、release_manifest、release_path_hygiene、runtime_overlay、version_ledger、golden_bookkeeping、append_only | passed |
| backend_ratchet | passed：1613 个 id、164 个失败（基线 117 + 隔离区）、new_failures []、fixed_but_listed []、flaky []、forbidden_port_attempts [] |
| node_tests、http_harness、typecheck_frontend、eslint_ratchet | passed |
| golden_full | passed：D4、C5 在精确模式下没有任何 gated 差异，identity 区差异也为 0 |
| reference_tables、publication_scope | passed（publication_scope 只忽略了与源码无关的 `website/dist` 缺失） |
| e2e_offline（强制步骤） | passed：自动选中 chromium_headless_shell-1243，24 通过、6 个已登记失败、4 个 skip（castle-101 在 UI-only 下）、0 个新失败。market-visibility 0/1（只有 R3-01 的登记失败），network-redispatch 19 通过、3 个已登记，expanded-workflows 1 通过、2 个已登记，result-queries 2/2，comparison-review 1/1，evidence-isolation 1/1 |
| golden_nightly | passed：C6 在精确模式下没有差异（1019 s） |
| network_guard、installed_inventory | passed |
| methodology_catalog、pytest_ratchet、energy_balance、validation_oracles、golden_sensitivity | 非强制步骤按设计 skip，原因分别是：口径目录由 X0 S8 提供；gate venv 未批准，pytest 不可用，139 个 pytest 风格 id 未运行；corrected 能量平衡不变量脚本属于 P0-4 后续步骤，不在 S1；独立 oracle 运行要等 X0 S6/P0-4 接入；敏感性检查需要口径机制（X0 S8） |

e2e 服务使用固定端口 18800/18766，由门禁自己启动和关闭。运行结束后这两个端口没有监听，临时状态目录也已删除。整个过程没有连接 8766/8800。

## 3 M0 准入/验收门槛对照（计划 2.1）

| # | 门槛 | 状态 |
|---|---|---|
| ① | `p0_gate quick` 全绿；基线两次采集一致；test_preflight 不受磁盘影响 | 满足。每次合并后 quick 都通过，合并完成后 nightly 也通过；后两项由 X0 完成。gate venv 未建（X0 偏差 1，等作者决定） |
| ② | 两族 golden 在 `git archive 35aadb3` 副本中复核一致 | X0 已复核；本次合并没有改动任何 golden，golden_full 与 golden_nightly 精确一致 |
| ③ | P0-6 采集脚本的 HEAD 源码 sha 校验通过 | 满足（合并后 `check` 的 frozen 与 live 两条循环都是 0 差异） |
| ④ | P0-4 oracle：overshoot、nuclear_balancing 判 failed；baseline、export、nuclear_curtail 判 not_evaluated；market.sqlite 的 sha256 不变 | 满足（`test_p04_variant_fixtures` 在合并结果上通过） |
| ⑤ | test_path_hygiene 中的 overlay 测试转为通过 | X0 已满足，棘轮中没有回退 |
| ⑥ | CLI 跑 value_101_day 退出码为 0 | X0 的 `test_application_cli` 在棘轮中通过 |
| ⑦ | 离线 e2e 基线：market-visibility 1/1，network-redispatch ≥16/19 | **部分满足**：network-redispatch 19 通过（该文件现有 22 个测试，min_passed 设为 19）；market-visibility 为 0/1，失败只有 R3-01 的价格断言，已登记，owner 为 P0-9 S3（M2）。这是 P0-9 S0 的偏差 1：spec 改成真实字段后不再“假绿”，见第 5 节 |
| ⑧ | INSTALLED 的 mtime 与文件清单不变；SRC 中没有新增 .pyc | 满足，见第 6 节 |
| ⑨ | 作者已答复 Q1、Q2、Q3 | 满足（P0_DECISIONS） |

## 4 应用的决策

- D0-1：只在本地 `fix/review-2026-10-04` 上提交，没有 push，没有改 remote，lane 分支保留。
- Q1/Q12：本次合并没有修订任何 golden，doctoral 族 trajectory 区与 accounting 区都不变（golden_full、golden_nightly 精确一致）。
- A2：P0-4 的 oracle 与 P0-6 的采集都只把 stress/缺口作为报告量，不改调度。
- A4/A6：P0-7 S1 的 A4 净收入只对火电扣减，风光与储能毛收入即利润；没有引入 NPV（lane 有测试断言）。
- A5/Q9：P0-5 S0 的基线把 P6-02/03/04、P6-24 标为两轨 expected_change，本次不改读取行为。
- C25：发布清单冲突按“任取一侧、工具刷新”处理。
- P0_CONVENTIONS 第 11 节：合并后在合并结果上检查 UI 契约夹具（0 处差异，不需要重新生成）；e2e 跨 lane 串行（本次运行时 18800/18766 空闲）。

## 5 偏差与集成者裁定

1. **m0-p07 以 unapproved 状态合入。** 任务说明把该 lane 的状态标为 unapproved：第三轮审查回应（`4b0d918`、`fdef258`、`ea0ecf0`、`ecc39c5`）之后没有找到新的审查结论。按任务给定的合并顺序，本次仍然合入，理由是：内容全部是新增文件，`investment_accounts.py` 没有被任何生产代码导入（已 grep 核对）；decide() 的源文件和 `canonical_psm_data.py` 与 35aadb3 逐字节相同；67 个测试与记录 `--check` 都通过，门禁全绿。**请 lead 在 P0-7 S2 及之后的步骤以它为基础之前，复审第三轮回应。** 如果复审不通过，可以在集成分支上追加修正提交；不要回退合并提交，因为回退后再次合并会丢掉改动。
2. **P0-9 偏差 7（夹具预算 200 KB → 256 KB）由集成者批准。** 夹具是真实 C3 Run 对 UI 实际请求返回的原样载荷，削减会让夹具不再等于 API 实际发送的内容；S3/S4 预计还要增加 3–9 KB，200 KB 在 M2 必然超出。新常量由测试钉住，再提高必须改测试。lead 若不同意，按 P0-9 报告第 4 节第 7 条改回 200,000 即可。
3. **M0 验收门槛 ⑦ 中 market-visibility 为 0/1 而不是 1/1。** 沿用 P0-9 的处理：该失败已在 `e2e/offline-subset.json` 登记，失败形态由 `error_must_match` 钉死（必须显示 `Price£0/MWh`）。P0-9 S3 修好 R3-01 后，棘轮会要求删除这条登记。
4. **m0-p06 有几个第二轮提交的提交说明缺少约定的小节。** lane 想用 filter-branch 补写，被权限系统拒绝；应补的内容写在 M0-P0-6-S1 报告的 9.5 节。这些提交现已进入集成分支历史，改写就等于改写集成分支，因此**不补写**，以 lane 报告为准。fixture 的 provenance 按内容核对，不受影响。
5. **里程碑文件 `tests/baselines/milestone.txt` 仍为 M0，没有推进到 M1。** P0_CONVENTIONS 规定由集成者在里程碑结束时推进。但 M0 还有两项待 lead 确认：上面的第 1 条和第 3 条。因此保守处理，推进留到 lead 验收 M0 时进行。推进本身没有副作用：隔离区中带里程碑期限的 6 条都是 `expires=M7`，其余为 `host`，推进到 M1 不会让任何条目过期。
6. 任务要求“每次合并后跑 quick”，本次照做。另外，在全部合并完成后加跑了一次 nightly（包含 full 的全部步骤），对应计划 5.1-5 中“合入前跑 full、里程碑结束跑 nightly”的要求。

## 6 环境与安全核对

- `find <INSTALLED> -newer <INSTALLED>/install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*' -print` 在 diagnose 之前和之后都只列出 `<INSTALLED>/.supervisor.lock`。这是一个 0 字节文件，mtime 为 2026-10-03 12:41:26，比 receipt 晚 17 s，是现网 supervisor 启动时留下的锁（P0_CONVENTIONS 第 2 节将其排除在外），早于本次工作。runtime/ 与 app/ 下没有比 receipt 新的 `.pyc`。门禁的 `installed_inventory` 每次都通过。
- `<INSTALLED>/diagnose-value --prefix <INSTALLED>`：退出码 0，输出 “Installation integrity and runtime checks passed.”。输出中有两行 vinext 静态文件流 “Premature close”，来自 diagnose 自身的探测请求，与前几轮 lane 报告中的情况相同，不影响结论。
- 本次没有手动启动任何服务器。门禁的 e2e_offline 在 18800/18766 上启动的服务由 Playwright 自己关闭，结束后无监听。没有向任何进程发送信号，也没有使用 pkill/killall。现网 8766/8800（PID 2949415/2949416）没有被触碰。
- 集成 worktree 中没有 `.pyc` 或 `__pycache__`。SRC 主工作树 `git status` 干净；其中原有 79 个 `.pyc`，没有比本轮施工文档更新的。
- 研究包 `data-audit/staging/{gbp1-national,r029-public1}` 只读使用，运行前后的文件清单哈希相同。

## 7 清理

- 五个 lane worktree（`build/wt/m0-p04`、`m0-p05`、`m0-p06`、`m0-p07`、`m0-p09`）已用 `git worktree remove` 删除，每个约 73–76 MB。删除前确认它们都是干净的（`git status --porcelain` 为空），并先单独删除了各自指向 SRC 的 `node_modules` 符号链接；SRC 的 `node_modules` 未受影响（仍有 387 项）。
- lane 分支 `fix/review-2026-10-04--m0-p0{4,5,6,7,9}` 全部保留。
- 本次 scratch 用量约 21 MB（`build/m0merge/`，门禁报告与临时目录）。

## 8 遗留问题（交给 lead 或后续里程碑）

- P0-7 S1 的复审（第 5 节第 1 条）。
- 推进 `tests/baselines/milestone.txt` 到 M1（第 5 节第 5 条）。
- gate venv、pytest、pypdf 仍未安装（X0 偏差 1）。在作者批准离线安装之前，139 个 pytest 风格测试不运行，隔离区中 6 条 `expires=M7`。
- 研究包不在仓库内，门禁默认跳过 P0-5 的研究包回放。后续 P0-5 步骤需要设置 `VALUE_P0_5_PACKS`（见 M0-P0-5-S0 报告第 7 节）。
- P0-6 的 48 期 e2e 基线会在 D3/C3 第一次出现修订时自动退役，不再采集 v2（P0-6 报告 8.1，需 lead 确认是否偏离计划 M3）。
- P0-5 S0 偏差 4：P6-03 中内核 Connection 错位是否属于 A5 的两轨修复，DECISIONS 没有明说，留给 S4/S5 负责人决定并记录。
- 计划实测数字勘误（P0-4 报告第 5 节）：overshoot 的 Σ|adj| 为 810.546，不是 819.40；nuclear_balancing 为 35/48 期，不是 21/48。S8 写勘误时以 oracle 输出为准。
