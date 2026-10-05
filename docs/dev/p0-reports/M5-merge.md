# M5 集成报告：m5-data、m5-inv 合入 `fix/review-2026-10-04`

- 集成分支：`fix/review-2026-10-04`（INTEG worktree）。合并前 tip 为 `d788a37`（M4-P0-4-S7-S8 报告），两条 lane 都从这里分叉。
- 合并方式：按任务顺序 m5-data → m5-inv，都用 `git merge --no-ff`。lane 提交原样保留，没有 squash，也没有改写历史。
- 解释器一律经 `build/bin/vpy`，node 经 `build/bin/vnode`（`VALUE_NODE`）。`TMPDIR` 与 `VALUE_DATA_HOME` 设在 `build/m5merge/` 下。
- 用户本轮要求“不要搞无止境的测试，一切基本顺利之后就迅速推进”。因此每次合并只跑受影响模块和 `p0_gate quick`；golden 只在需要追加修订或核对的 case 上运行（合计覆盖全部 12 个 case，见第 2 节），没有跑 `p0_gate full/nightly`。

## 1 合并提交

| 合并提交 | lane（tip，提交数） | 内容 | 冲突与处理 |
|---|---|---|---|
| `54fe0ed` | m5-data（`b1a5206`，3 个） | P0-5b S5–S8、S11、S12：修正口径天气 v2、风光文献损耗系数（不标定）、核电/径流水电可用率机制（参考值待作者审核）、内核站点注入、天气缓存按文件作键（P7-02，两轨通用）、GBP1 public2 本地构建器与边界潮流符号审计、方法学草稿与参考统计表 | 无冲突。lane 的分叉点就是集成 tip，合并结果的树与 lane tip 逐字节相同（`git diff --cached <lane>` 为空） |
| `dfe1823` | m5-inv（`50fc6bd`，6 个） | P0-7 S2–S4、S6–S8、S9 部分：火电净收入（A4，两口径）、corrected 储能余量与功率电池共用池（P5-01、P5-02）、成本账 v2（P4-03 兼容资本 memo、A7 风光储 FOM memo）、PF 的 FOM 键修正、P4-02 移出范围（A6）、方法学草稿 | 文本冲突 9 个文件：`tests/golden/corrected/C1–C8.json` 与 `source-release-manifest.json`，见 1.1 |
| 本报告提交 | — | `docs/dev/p0-reports/M5-merge.md` | — |

两个合并提交的正文都按 P0_CONVENTIONS 第 1 节写了 Findings / Track / Correction ids / Golden / Delta / Tests 六个小节，末尾带 Co-Authored-By。`git branch --merged` 确认两个 lane 分支都已包含在集成分支中。

### 1.1 m5-inv 的冲突处理

**corrected 族 golden（C1–C8）。** 两条 lane 在同一个基点上各自追加了修订：

- m5-data：每个 case 追加 1 个修订（`p05.weather-time-convention` + `p05.vre-loss-factors`）；
- m5-inv：C1–C7 追加 3 个修订（A4 火电净收入；储能余量与功率电池池；成本账 v2），C8 追加 2 个（没有储能余量那一个）。这些修订是在 P0-5b 之前的代码上采集的，digest 里没有 P0-5b 的天气变化。

两边的修订不能简单拼接：m5-inv 修订里的 digest 对合并后的代码不成立。处理方法如下：

1. 取 m5-data 一侧的文件（`git checkout --ours`）。它在基点处的修订是结果的严格前缀，append-only 规则成立。
2. 在合并后的代码上用 `capture.py revise` 为每个 case 追加**一个**修订：
   - C1–C7：correction ids 为 `p07.thermal-net-revenue`、`p07.storage-leftover-headroom`、`p07.power-battery-pool`、`p07.cost-ledger-v2`、`p07.compatibility-capital-out-of-headline`，finding 为 `P4-01-thermal`；
   - C8：不含两条储能 id，因为 staged PSM 不发布 leftover 序列，lane 也没有为 C8 记储能修订。
   - reason 写明这是合并修订，以及 lane 原来的修订划分。
3. 核对合并修订没有带进无法解释的列：对每个 case，合并修订中门控列（trajectory + accounting）的集合，与 m5-inv 在该 case 上全部 P0-7 修订的门控列并集**完全相同**。C1–C8 都是 0 个多出、0 个缺少（C3、C6、C7 的基点修订数与其他 case 不同，已按各自的基点计算）。也就是说，P0-5b 与 P0-7 叠加后，变化的列仍然只是 P0-7 本来就会改变的那些；P0-5b 改过而 P0-7 没改的列，在合并修订中没有再变化。
4. 合并修订的列数（门控/identity）：C1、C2、C4 为 38/10；C3 为 10/5；C5 为 537/29；C6 为 543/29；C7 为 36/38；C8 为 8/39。

**doctoral 族 golden（D1–D4）。** 只有 m5-inv 改过（A4 的 D4 trajectory 重基线和 `tests/golden/reports/D4-r9.json`，以及 D1–D4 的 accounting 修订），自动合并取 m5-inv 一侧。m5-data 的改动只在修正口径下生效，`p05.weather-cache-key` 不改数值。在合并后的代码上用 `capture.py check --cases D1 D2 D3 D4`（exact）核对，4 个 case 门控差异都为 0，各有 1 项 identity 差异（代码身份哈希）。`capture.py validate` 通过，D4-r9 报告仍然和修订 9 绑定。

**`source-release-manifest.json`。** 按 C25 处理：任取一侧，golden 修订完成后用 `refresh_source_release_manifest.py --index` 刷新，再用 `--index --check` 确认不过期。

**自动合并的交叠文件。** 下列文件逐一审阅过，没有发现问题：

- `scheme_c_native_psm.py`：P0-5b 的 `_kernel_site_inputs` / `kernel_site_inputs`，与 P0-7 的 `agent_cashflow`、`capital_cost_components_gbp`、`storage_headroom_inputs` 扩展互不相交。A4 的运行成本分项取自 `config.generators` 的 `gen_cost` 等字段，P0-5b 的内核注入只改逐期容量上限，不改这些字段。CRLF 行尾保持不变：合并前后都只有 8 行是 LF，与两侧一致。
- `CHANGELOG.md`、`docs/SCHEME_C_MODEL_CARD.md`：两段都保留。
- `tests/test_methodology_static_scan.py`：两侧的夹具复制都保留。

## 2 每次合并后的验证

门禁报告在 `build/m5merge/gate-*.json`。“passed”指 `status: passed`，waivers 为空。

| 合并 | 受影响测试 | 其他检查 | `p0_gate quick` |
|---|---|---|---|
| m5-data | 合并树与 lane tip 相同。lane 提交前已跑 quick 与 golden nightly | — | passed（132 s）：棘轮 2240 个 id，157 个失败，基线 110，new 0，fixed 0，forbidden ports 0；node_tests、http_harness、typecheck_frontend、eslint_ratchet 都通过 |
| m5-inv | 15 个模块共 203 个 id，new 0。7 个失败都在基线中；2 个 skip 是需要 `VALUE_P0_5_PACKS` 的 GBP1 用例。模块包括 test_p05b_*、test_p07_*、static scan、advisories、application_service、prompt101 staged、runtime_overlay_seal、version_ledger、ui_contract_fixtures | golden：C1–C8 在合并代码上 revise（见 1.1）；D1–D4 用 check exact 核对，门控差异 0；`capture.py validate` 通过；`generate_reference_tables --check` 通过；`check_version_ledger` 通过；发布清单 `--index --check` 不过期；UI 契约夹具无需重新生成（`test_ui_contract_fixtures` 通过，夹具中没有投资和成本账字段） | passed（132 s）：棘轮 2264 个 id，157 个失败，基线 110，new 0，fixed 0，flaky 0，forbidden ports 0；其余步骤全部通过 |

12 个 golden case 都在合并后的代码上至少跑过一次：C1–C8 在 revise 时运行，D1–D4 在 check 时运行（D4 用 141 s）。

## 3 应用的决策

- **DECISIONS 1(c) / A4**：火电净收入在两个口径中恢复，D4 的 trajectory 重基线只有 lane 中那一次（`P4-01-thermal`）。合并没有再动 doctoral trajectory。
- **DECISIONS 4 / Q15 / A1**：风光只加文献损耗系数，不做标定，doctoral 不变（D1–D4 门控差异为 0）。
- **DECISIONS 5**：核电/水电机制合入，参考值保持 PENDING AUTHOR REVIEW。
- **DECISIONS 3 / A6**：P4-02 不实现，不引入 NPV。
- **Q12 / append-only**：corrected 族只追加修订，不改写已有修订；doctoral trajectory 没有新增例外。
- **C25**：发布清单用工具刷新，没有手工编辑 JSON。
- **C20**：储能余量按规则集声明的列语义读取。合并后 corrected 的余量建立在 P0-5b 之后的过剩/弃电量上，这是预期的叠加结果。
- D0-1：只在本地 `fix/review-2026-10-04` 上提交，没有 push，没有改 remote，lane 分支全部保留。

## 4 偏差

1. **corrected 族的 P0-7 修订在集成分支上合并成一个修订**（第 1.1 节）。lane 的三个分步修订是在 P0-5b 之前的代码上采集的，在合并后的代码上无法复现。逐步重放需要构造并运行若干中间合并状态，用户要求迅速推进，所以没有这样做。分步的修订和 delta 仍保存在 lane 分支 `fix/review-2026-10-04--m5-inv` 的历史中。合并修订的门控列集合已经核对过，与分步修订的并集相同。
2. **没有跑 `p0_gate full/nightly`**（用户要求）。全部 12 个 golden case 已在合并代码上运行（第 2 节），里程碑门禁留给 lead 视需要再跑。
3. **`tests/baselines/milestone.txt` 仍为 M0**。沿用 M0、M2 集成者的做法，推进留给 lead。

## 5 需要 lead 注意的事项

1. 合并修订中，C5、C6 的 trajectory 变化列数分别为 456、462。这与 m5-inv 在 lane 中的变化列集合相同（主要来自 A4：CCGT 不再按毛收入扩容）。但数值建立在 P0-5b 的风光出力之上，与 lane 报告中的数值不完全相同。如需要数值报告，可以用 `capture.py dump` 比较 `54fe0ed` 与 `dfe1823`。
2. 两条 lane 都已经评审通过（approved）。合并只带来第 1.1 节的 golden 处理，没有改任何生产代码或测试。

## 6 环境与安全核对

- `find <INSTALLED> -newer <INSTALLED>/install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*' -print` 在合并前和 diagnose 之后都只列出 `<INSTALLED>/.supervisor.lock`。这是现网 supervisor 早先留下的 0 字节锁文件，mtime 为 2026-10-03 12:41:26，早于本轮工作，前几轮报告已经说明。app/、runtime/、installer/ 下没有新文件。两次门禁的 `guard` 与 `installed_inventory` 都通过。
- `<INSTALLED>/diagnose-value --prefix <INSTALLED>`：退出码 0，输出 “Installation integrity and runtime checks passed.”。输出中有两行 vinext 静态文件流 “Premature close”，与以前相同。diagnose 自行启动并关闭了一个 127.0.0.1:8800 的检查实例。开始前和结束后，8766/8800/18800/18766 都没有监听。
- 现网 VALUE：本轮开始时 8766/8800 没有监听，PID 2949415/2949416 不存在（只用 `ps -p` 和 `ss` 只读查看）。没有向任何进程发信号，没有使用 pkill/killall，没有连接 8766/8800。本轮只启动过自己的两个后台 golden 进程（PID 1421325 revise、1421988 check），两个都已正常退出。
- 本轮没有启动任何服务器，HTTP 测试由测试框架绑定随机端口。
- 集成 worktree 中没有 `.pyc` 或 `__pycache__`。SRC 主工作树没有改动，SRC 的 `node_modules` 仍为 387 项。

## 7 清理

- 两个 lane worktree（`build/wt/m5-data` 117 MB、`build/wt/m5-inv` 126 MB）已用 `git worktree remove` 删除。删除前确认 `git status --porcelain` 为空（只有被忽略的 `node_modules` 符号链接），并先单独 unlink 了指向 SRC 的 `node_modules` 符号链接。
- lane 分支 `fix/review-2026-10-04--m5-data`、`fix/review-2026-10-04--m5-inv` 保留。
- 本轮 scratch 用量很小（`build/m5merge/`，只有门禁报告、日志与临时目录）。

## 8 遗留问题（从两条 lane 原样带过来）

- 作者审阅：`value_uk_vre_loss_factors_v1.json`（海上合计损耗约 18.5%）与 `value_uk_firm_availability_v1.json`；提供 `boundary_flow_reference_2022.json`；决定 public2 是否登记、是否进入 `NUCLEAR_POLICY_PACK_IDS`。
- AC PSM 与 doctoral-national PSM 没有发布 agent_cashflow。staged、PF、DC 没有发布 leftover 序列，所以 corrected 下这些 PSM 的储能扩容仍关闭，并记录原因。
- market 结果自身的 `total_levelized_capital_cost_gbp` 仍为 PSM 原值，账本头条已改。
- 储能 ROI 判定（A8(3)）留待 S10 的 VALUE-101 two_year 验收复核。
- 投资侧 CSV 资源曲线与调度侧天气不一致（Q15 披露项）。
- 方法学 0.4 草稿（`p05b_corrected_data.md`、`p07_investment.md`）待并入 core.md。
