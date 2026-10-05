# M2 集成报告：三条 lane 合入 `fix/review-2026-10-04`

- 集成分支：`fix/review-2026-10-04`（INTEG worktree）。合并前 tip 为 `21f9a9d`（DECISIONS A8）。
- 合并方式：按任务指定的顺序 m2-profile → m2-net → m2-ui，每条都用 `git merge --no-ff`。lane 的提交原样保留，没有 squash，也没有改写历史。三条 lane 的分叉点都是 `f80edd2`。分叉之后集成分支只改了文档（DECISIONS A7/A8、P0-1 设计方裁决、P0-7 S1 lead 裁定）。
- 合并结束后、本报告提交之前，另一个会话在集成分支上提交了只改文档的 `bd619b9`（设计方对 M2 界面审查遗留小问题的裁决，留到 M7 实现）。本报告提交在它之后。
- 解释器一律经 `build/bin/vpy`，node 经 `build/bin/vnode`（`VALUE_NODE`）。`TMPDIR` 与 `VALUE_DATA_HOME` 都设在 `build/m2merge/` 下。
- 合并带来的数值变化只有 m2-net 已经登记的 C8 修订 1、2（`p08.zonal-solver-v4`、S12 审计产物）。doctoral 族 golden 没有任何修订。集成者自己的修正只涉及 Study 修订身份与台账文字，不改变任何 trajectory 或 accounting 列。

## 1 合并提交

| 合并提交 | lane（tip，提交数） | 内容 | 冲突与处理 |
|---|---|---|---|
| `46e142b` | m2-profile（`e91b506`，23 个） | X0 S8–S11：口径目录与组合白名单、运行入口与每个 PSM.run 的口径激活、读时 advisory 与状态词汇、Q14 年度结果发布门控、Study 修订迁移（方法变化须确认）。**lane 状态 unapproved**，见第 5 节 | 只有 `docs/dev/P0_FRONTEND_DEVIATIONS.md` 冲突：集成分支加了 P0-1 设计方裁决，lane 加了 X0 S10b 一节。两侧都保留，裁决在前。发布清单自动合并，`--index --check` 不过期 |
| `5e5f502` | m2-net（`1e3434c`，29 个） | P0-8a S1–S6、S11、S12：资产母线份额（DC 1.1.0 展开—求解—聚合）、zonal solver contract v4（先锁切负荷，再对 bid 项加数值锁；zonal 4.0.0）、历史合同只读与显式升级、统一的切负荷报告阈值、割集分类、运行期 fallback 审计 | 文本冲突 4 处，见 1.1。**另有一处语义冲突（C24），已在合并提交中修正**，见 1.2 |
| `44fb566` | m2-ui（`9584823`，18 个） | P0-9 S1、S3–S10（格式化层、价格口径、dispatch timeline v2、统一覆盖率规则、网络页覆盖率与可靠性列表、归因 unavailable/invalid、VRE KPI、年度成本构成、zonal 能力探针）；P0-3 S8 降级/离线状态；P0-2 S9 隔离面板 | 文本冲突 4 处，见 1.3。合并后 UI 契约夹具 `--check` 无差异，不需要重新生成 |
| 本报告提交 | — | `docs/dev/p0-reports/M2-merge.md` | — |

三个合并提交的正文都按 P0_CONVENTIONS 第 1 节写了 Findings / Track / Correction ids / Golden / Delta / Tests 六个小节，末尾带 Co-Authored-By。`git branch --merged` 确认三个 lane 分支都已包含在集成分支中。更正：m2-ui 合并提交的说明写的是 “17 commits”，实际为 18 个（`defd001`…`9584823`）。提交尚未推送，但为了不改动已跑过门禁的提交，我没有 amend，以本报告为准。

### 1.1 m2-net 的文本冲突

| 文件 | 处理 |
|---|---|
| `docs/dev/P0_FRONTEND_DEVIATIONS.md` | 全部保留，顺序为：P0-1 裁决、X0 S10b（F-X0-1/2）、P0-8a（F-P08-1/2） |
| `tests/test_golden_digest.py` | `test_cases_run_from_frozen_projects_not_the_live_template` 两侧合并：先按 X0 S8 检查 doctoral case 钉住 `REFERENCE_PROFILE_ID`、corrected case 不带口径；再按 P0-8 忽略运行时重新推导的两个键（`maturity_acknowledgements`、`solver_contract`），其余必须与冻结项目逐项相同 |
| `docs/generated/MODULES.md` | 任取一侧后用 `scripts/generate_reference_tables.py` 重新生成。生成器写出的是 LF，仓库中的这个文件是 CRLF，因此把 MODULES.md 转回 CRLF；生成器顺带改写的 PARAMETERS.md 只差行尾，已还原。之后 `--check` 通过 |
| `source-release-manifest.json` | 按 C25 处理：任取一侧，暂存全部解决结果后用 `refresh_source_release_manifest.py --index` 刷新，再 `--check` 确认不过期 |

### 1.2 m2-net 的语义冲突（C24：X0 S11 × P0-8 S5），已在合并提交中修正

合并后 `test_project_revision_migration` 有 3 个新失败。原因是两条 lane 各自都正确，但合在一起出现了缺口：

- P0-8 S5 让 `validate_solver_settings` 只接受 v4，v2/v3 抛 `GF_SOLVER_CONTRACT_UPGRADE_REQUIRED`。`canonical_project_payload` 经 `validate_project_solver_contract` 调用它，因此 v3 合同再也无法规范化。
- X0 S11 的 `_reconstructed_basis` 为 S11 之前保存的 Study 重建 35aadb3 basis 时，也要调用 `canonical_project_payload`。35aadb3 时代的 zonal Study 记录的都是 v3 合同，于是重建一律抛错，被 `except (KeyError, ValueError)` 吞掉。结果是：**每个 35aadb3 时代的 zonal Study 都会被判为 `unverifiable`，确认对话框里没有可审的差异**，而不是 `method_upgrade_required` 加逐项差异。lane 的测试 `test_pre_profile_extension_study_is_reconstructed_from_its_stored_graph` 正好覆盖这个场景，合并后它在夹具这一步就抛错。

修正（只用于身份重建，不放宽执行）：

1. `gridform_core/project_revision.py`：`canonical_project_payload` 新增关键字参数 `recorded_solver_contract=False`。为 True 且所存合同属于 v2/v3 时，用 `validate_recorded_solver_settings`（P0-8 提供的只读校验）按记录原样取合同，不经过当前的 v4 校验。docstring 写明这样得到的 payload 只是身份记录，既不保存也不执行。文件是 CRLF/LF 混合行尾，编辑时逐行保留了原行尾。
2. `gridform_core/revision_migration.py`：只有 `_reconstructed_basis` 传入 `recorded_solver_contract=True`。合同升级仍由 `_solver_contract_upgrade` 单独列出一行（`method_upgrade_required`、`GF_SOLVER_CONTRACT_UPGRADE_REQUIRED`）。确认后由 `migration_candidate` 换成安装版的 v4 默认合同，这与 P0-8 “不静默改写，显式升级”的规则一致。
3. `tests/test_project_revision_migration.py`：
   - 夹具 `zonal_study_with_superseded_contract` 改为先用安装版 v4 默认合同保存（v3 快照已经无法保存），再把记录改写为真实的 v3 身份 `V3_SOLVER_CONTRACT_VERSION`。原夹具用的是虚构的 `value.zonal-lexicographic-gbp1/v2`。
   - 重建测试改用 `recorded_solver_contract=True` 构造 35aadb3 payload，并新增断言：差异中有一行 `contract_version`，为 v3 → v4、`method_upgrade_required`。
   - 有效性：把第 2 条的参数临时去掉后，该测试失败（`basis_source == 'none'`）；恢复后 23/23 通过。
4. `docs/release/VERSION_LEDGER.json` 中 DC 1.0.0→1.1.0 的 reason 原来写 “The flag is declarative until X0 S11 …(open item for X0 S11)”。S11 合入后这句话不再成立：`revision_migration._module_change_kind` 会读取 `requires_user_opt_in`。reason 已改为说明该标志现在生效。`tests/test_p08_network_shares.DCVersionLedgerTests` 原来断言旧措辞，现在改为断言实际行为：`_module_change_kind('value-reference-dc-network','1.0.0','1.1.0')` 返回 `method_upgrade_required`，并带 `p08.network-share-expansion`。`check_version_ledger.py` 通过。

以上修改都放在 m2-net 的合并提交里，不单独成提交。原因是在修正之前提交合并会留下新失败的测试，而规则要求不得提交新失败的测试。合并提交的正文逐条列出了这些修改。

其他自动合并的交叠文件逐一核对过，没有发现问题：`backend/server.py`、`frozen_input_recovery.py`、`frozen_run_recovery.py`、`application.py`、`staged_psm.py`、`network_dc.py`、`network_ac.py`、`run_snapshot.py`、`results_summary.py`、`frontend_contract.py`、`P0_CONVENTIONS.md`。检查方式：
- `test_methodology_activation` 的内省测试确认，DC/AC/staged PSM 的 `@methodology_scoped` 都还在；
- doctoral 白名单不含 zonal/DC/AC（Q3），P0-8 的升版不影响 `DOCTORAL_DEFINITION_SHA256`；
- golden fast 中 C8 在口径激活下仍等于修订 2，没有门控差异。

### 1.3 m2-ui 的文本冲突

| 文件 | 处理 |
|---|---|
| `backend/result_queries.py` | 两侧的 import 都保留（Q14 的 `withheld_annual_result` 与 P0-9 的 `result_coverage` 等）。逻辑上，年度 withheld 检查在任何覆盖率判定之前，这是自动合并的结果，已核对 |
| `backend/server.py`（`market/vre-summary`） | 先做 Q14 检查（withheld 时照旧返回 409），再返回 P0-9 的 summary 和 coverage 块。其余受 Q14 门控的资源（`network-redispatch/annual`、`planning/summary`、`domains/*/summary`）是自动合并的，已核对 withheld 检查仍在 coverage 之前。Run 详情的 `result_coverage` 只给年份与时段边界，不含年度数值，对 withheld 的 Run 不构成泄漏 |
| `docs/dev/P0_FRONTEND_DEVIATIONS.md` | 全部保留，P0-9 一节（F-P09-1..15）放在最后 |
| `source-release-manifest.json` | 同 C25 |

UI 契约夹具（P0_CONVENTIONS 第 11 节）：两条线都没有让对方的夹具过期。合并结果上 `tests/ui_contract_fixtures.py --check` 为 0 处差异，共 202,069 字节（预算 256 KB），因此没有重新生成。

## 2 每次合并后的验证

所有门禁报告写在 `build/m2merge/gate-*.json`。“passed”均指 `status: passed`，waivers 为空。

| 合并 | 受影响测试（`run_backend_tests.py --modules …`） | 其他检查 | `p0_gate quick` |
|---|---|---|---|
| m2-profile | 18 个模块，193 个 id，new 0（7 个失败都在基线中） | 发布清单 `--index --check` 不过期 | passed（113 s）：棘轮 1938 个 id、161 个失败、new 0、fixed 0；`methodology_catalog` 由跳过变为运行并通过 |
| m2-net | 修正前：46 个模块中 `test_project_revision_migration` 有 3 个新失败（见 1.2）。修正后：46 个模块，524 个 id，new 0 | golden `capture.py check --tier fast` passed：9 个 case 门控差异均为 0（C8 为修订 2，其余为修订 0）；`ui_contract_fixtures --check` 0 差异；`check_version_ledger` 通过；`generate_reference_tables --check` 通过 | passed（115 s）：2008 个 id、157 个失败、new 0、fixed 0 |
| m2-ui | 三条线合计 53 个模块，593 个 id，new 0 | golden fast passed（同上，门控差异 0）；`ui_contract_fixtures --check` 0 差异 | passed（118 s）：2033 个 id、157 个失败、new 0、fixed 0；node_tests（含 ui-unit、ui-render 新组）、typecheck_frontend、eslint_ratchet 通过 |

基线规模由 114 降到 110：m2-net 删去了 4 条已修好的基线条目（prompt103 3 条、prompt101 1 条），lane 已在棘轮中处理。

### 里程碑门禁（nightly，包含 full 的全部步骤）

nightly 在 `44fb566` 上启动，**status passed，waivers 为空**，耗时 1373 s。运行期间，另一个会话在集成分支上提交了 `bd619b9`（设计方对 M2 界面审查遗留小问题的裁决），它只改 `docs/dev/P0_FRONTEND_DEVIATIONS.md`。门禁报告结束时记录的提交就是它（dirty=false）。这个文件在发布排除目录中，不影响任何测试，所以本结果对 `44fb566` 与 `bd619b9` 同样成立。

| 步骤 | 结果 |
|---|---|
| guard、release_manifest、release_path_hygiene、methodology_catalog、runtime_overlay、version_ledger、golden_bookkeeping、append_only | passed |
| backend_ratchet | passed：2033 个 id、157 个失败（基线 110 + 隔离区）、new_failures []、fixed_but_listed []、flaky []、expired_quarantine []、forbidden_port_attempts [] |
| node_tests、http_harness、typecheck_frontend、eslint_ratchet | passed |
| golden_full | passed：D4、C5 在精确模式下没有门控差异（各约 125 s），identity 差异各 8 项 |
| reference_tables、publication_scope | passed（publication_scope 只忽略了与源码无关的 `website/dist` 缺失） |
| e2e_offline（强制步骤） | passed：33 通过、5 个已登记失败、4 个 skip（castle-101 在 UI-only 下）、0 个新失败。各 spec：market-visibility 2/2，network-redispatch 22 通过、3 个已登记，expanded-workflows 1 通过、2 个已登记，result-queries 2/2，comparison-review 1/1，evidence-isolation 1/1，service-status 4/4。与 m2-ui lane 评审后的结果一致 |
| golden_nightly | passed：C6 在精确模式下没有门控差异（1004 s） |
| network_guard、installed_inventory | passed（installed_inventory 22,509 项，增 0、删 0、改 0） |
| pytest_ratchet、energy_balance、validation_oracles、golden_sensitivity | 非强制步骤，按设计 skip，原因分别是：没有 pytest（139 个 pytest 风格 id 未运行）；corrected 能量平衡不变量随 P0-4 到来；独立 oracle 运行在 X0 S6/P0-4 之后接入；敏感性检查虽然已有口径目录，但脚本还没接入（门禁文案仍写 “needs the methodology profiles (X0 S8)”，属于门禁自身的待办） |

e2e 服务使用固定端口 18800/18766，由门禁自己启动和关闭。运行前后这两个端口都没有监听。

## 3 应用的决策

- D0-1：只在本地 `fix/review-2026-10-04` 上提交，没有 push，没有改 remote。lane 分支全部保留。
- Q1/Q12：doctoral 族 golden 没有修订，D1–D3（fast）与 D4（full）门控差异都为 0。C8 的两次修订来自 m2-net lane，集成时没有再修订。
- Q3：doctoral 白名单拒绝 zonal/DC/AC，因此 P0-8a 全部是两轨通用修正，不经口径开关；合并后 `methodology_catalog` 的静态扫描通过（无口径 id 字面量比较，C15）。
- Q13/C24：v3 zonal Study 与 DC 1.0.0 Study 的升级都是 `method_upgrade_required`，须用户确认；只有纯代码身份变化自动追加修订。1.2 的修正保证 35aadb3 时代的 zonal Study 能重建 basis，让确认对话框有逐项差异可审。
- Q14：P0-9 新加的 coverage 块都放在 withheld 检查之后，withheld 的 Run 仍然不出年度数。
- C25：发布清单冲突三次都按“任取一侧、工具刷新”处理，没有手工编辑 JSON。
- P0_CONVENTIONS 第 11 节：合并后在合并结果上检查 UI 契约夹具，0 差异。e2e 只在 nightly 中运行一次，运行前确认 18800/18766 空闲。

## 4 偏差

1. **合并提交中包含集成修正**（1.2）。修正与合并放在同一个提交里，因为不这样做就会提交新失败的测试。修正范围很小（2 个生产文件、2 个测试文件、台账的一句 reason），合并提交正文逐条列出。lead 可用 `git show --remerge-diff 5e5f502` 只看合并提交相对自动合并结果的改动（9 个文件：冲突解决 4 个、上述修正 5 个）。
2. **改了 m2-net 的一条测试断言与台账文字**（DC opt-in 的 “declarative until X0 S11”）。原断言针对 S11 落地之前的事实，合并后不再成立。改为断言实际行为，没有删除这条测试。
3. **`tests/baselines/milestone.txt` 仍为 M0**，没有推进到 M2。M0 集成者把推进留给 lead 验收（M0 报告第 5 节第 5 条），M1 也没有推进。推进本身不影响门禁：隔离区的条目都是 `expires=M7` 或 `host`。我沿用保守做法，留给 lead 一并推进。
4. 合并提交 `44fb566` 正文中的 lane 提交数写成了 17，实际为 18（见第 1 节）。

## 5 需要 lead 注意的事项

1. **m2-profile 以 unapproved 状态合入。** 任务说明把 M2-X0-S8-S11 标为 unapproved：第三轮审查回应（`21865c1`、`179e2b8`、`20f3a78`、`e91b506`）之后没有新的审查结论。我按任务给定的顺序合入，合并后它的全部测试与门禁都通过。**请 lead 复审第三轮回应**，重点是 doctoral 冻结副本按“记录 + 一致性核验”认定源 manifest（偏差 19）。若不通过，请在集成分支上追加修正提交。不要回退合并提交，否则以后再次合并会丢掉这些改动。
2. **DC 1.1.0 与 zonal 4.0.0 的 opt-in 现在都生效。** 已保存的、选择 DC 模块的 Study（包括单母线 Study），下次运行前都要确认一次修订迁移。已保存的 zonal Study 还要同时确认 v3→v4 合同升级。这是 m2-net 选择的保守取值，作者可以裁定只对含拆分映射的 DC Study 要求确认（M2-P0-8a 报告第 6 节）。
3. **v3 zonal Study 启动 Run 时，409 响应不带 `revision_migration`。** start-run 先执行 P0-8 的 `validate_project`，对历史合同直接返回 409 `GF_SOLVER_CONTRACT_UPGRADE_REQUIRED`，附 `validation`。S11 的分类在它之后，所以这一路径拿不到分类结果。用户目前有两种升级方式：编辑器里的 “Use current v4 policy”（P0-8，已有界面），或 `GET/POST /api/projects/<id>/revision-migration`（S11，已经能正确分类，见 1.2）。设计规格第 7 节的迁移确认对话框还没有实现，实现时可以让这条 409 也带上分类。本次不改，没有消费方。

## 6 环境与安全核对

- `find <INSTALLED> -newer <INSTALLED>/install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*' -print` 在合并前、diagnose 之前和之后都只列出 `<INSTALLED>/.supervisor.lock`。这是一个 0 字节文件，mtime 为 2026-10-03 12:41:26，比 receipt 晚 17 s，是现网 supervisor 启动时留下的锁（P0_CONVENTIONS 第 2 节将其排除在外），早于本次工作。app/、runtime/、installer/ 下没有新文件。每次门禁的 `guard` 与 `installed_inventory` 都通过。
- `<INSTALLED>/diagnose-value --prefix <INSTALLED>`：退出码 0，输出 “Installation integrity and runtime checks passed.”。输出中有两行 vinext 静态文件流 “Premature close”，与前几轮报告中的情况相同。diagnose 会自行启动并关闭一个 127.0.0.1:8800 的检查实例；结束后 8766/8800/18800/18766 都没有监听。
- 现网 VALUE：本次开始时（18:14）8766/8800 已经没有监听，PID 2949415/2949416 也不存在（只用 `ps -p` 和 `ss` 只读查看过）。我没有向任何进程发送信号，没有使用 pkill/killall，没有连接 8766/8800。
- 本次没有手动启动任何服务器。HTTP 测试经 `start_local_api` 绑定随机端口；e2e 服务由门禁启动和关闭。
- 集成 worktree 中没有 `.pyc` 或 `__pycache__`。SRC 主工作树 `git status` 干净，SRC 的 `node_modules` 仍为 387 项。
- 所有 Python 都经 `build/bin/vpy` 调用。有一次误把一段空的 heredoc 交给了系统 `python3`，只是空输入，没有执行任何项目代码，也没有读写文件。

## 7 清理

- 三个 lane worktree（`build/wt/m2-profile`、`m2-net`、`m2-ui`，每个约 76–82 MB）已用 `git worktree remove` 删除。删除前确认它们的 `git status --porcelain` 为空（只有被忽略的 `.next/`、`dist/` 和 `node_modules` 符号链接），并先单独 unlink 了指向 SRC 的 `node_modules` 符号链接。SRC 的 `node_modules` 未受影响。
- lane 分支 `fix/review-2026-10-04--m2-{profile,net,ui}` 全部保留。
- 本次 scratch 用量约 18 MB（`build/m2merge/`，门禁报告、日志与临时目录）。整个 `build/` 目录现为约 206 MB。

## 8 遗留问题（交给 lead 或后续里程碑）

- 第 5 节第 1 条：m2-profile 第三轮回应的复审。
- 前端待办（都需要设计方补充或确认，本次集成没有改界面）：
  - **F-P08-1**：网络页渲染，包括可靠性数值格式、v3 缺陷提示、fallback 审计 Callout。m2-net 报告把它交给“P0-9 S6 合入之后”，现在 P0-9 S6 已合入，后端字段与 TS 类型都已就位。这需要一个前端单元按规格 4.6 实现并补 e2e，不宜在合并中顺手做。
  - **F-X0-1**：VRE 页与网络页对 409 withheld 改显示 Withheld Callout，目前显示的是错误框。
  - **F-X0-2**：迁移对话框中的口径单选。
  - **F-P09-6**：年度卡片 Withheld pill。X0 的 `result_publication` 字段已经有了，可以接到 `coveragePill(…, { withheld: true })`。
  - 设计规格第 7 节：迁移确认对话框整体。
- `tests/baselines/milestone.txt` 推进（第 4 节第 3 条）。
- 其他沿用的未决事项：
  - S12 的 10% fallback 阈值待作者确认；
  - 真实 GB 全年的锁越界与 repair 计数（M5/M6）；
  - `value-uk-1000twh-reproduction` 的 manifest sha 未钉住（X0 偏差 17）；
  - gate venv、pytest 仍未安装（X0 偏差 1）。
- 负载下偶发的计时测试失败（`test_lifecycle_primitives…test_import_is_fast_and_never_loads_numpy`、`test_prompt121…ownership`），已有多条 lane 报告记录。本次集成的门禁没有遇到。
