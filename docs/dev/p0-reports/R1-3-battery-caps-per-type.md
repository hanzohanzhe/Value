# R1-3-battery-caps-per-type：修正口径的电池扩容上限按类型分别设定（DECISIONS A20）

- 分支：`fix/review-2026-10-04`（INTEG），起点 `1c9176a`。
- 授权：A20（撤回 P5-02 的“三种电池共用一个功率池”；0.25C、0.5C、1C 各自给 `expansion.storage_cap_fraction × power_room`（0.2）是论文的有意设计，比例本身已经削弱过；修正口径恢复为按类型分别设上限，比例维持 0.2；P5-01 的修复保留；属于方法改动（Q13），修正族 golden 修订一次）。论文复现口径不变（Q1）。
- 提交：
  - `6fa1690` feat(invest): per-type power-battery caps in the corrected profile (A20)（代码、目录、版本、测试、golden、生成表、CHANGELOG、发布清单）
  - `19d5eac` docs: per-type battery caps in the methodology draft, model card and hand-offs (A20)
  - 本报告单独提交（docs(p0)）

## 1 改了什么

1. **规则**：修正口径的储能余量（P5-01，剩余盈余 → aligned-utilisation 谱）不变。功率电池上限从“三种电池共用一个池 `f·B(365)`”改回“每种电池各自 `f·B(365)`”，f 默认 0.2，三者合计最多 `3f·B(365)`。氢储仍是 `f·` 季节段。投资步（agent-investment）对每种电池分别扣减自己的上限；同一种电池有多个 owner 时按 owner 顺序贪心分配，与 35aadb3 相同。
2. **开关**：新增 profile_gated 修正 `r13.per-type-battery-caps`（`gridform_core/data/methodology/corrections/r13.json`，scope `expansion_headroom`，affects trajectory，advisory 为 null，trigger fixture `tests.test_r13_per_type_battery_caps.PerTypeBatteryCapTests`）。代码中只有一个判断函数 `v2_module_definitions.power_battery_pool_in_force(methodology)`：`enabled("p07.power-battery-pool") and not enabled("r13.per-type-battery-caps")`。修正口径两条都应用，所以不再共用池；论文复现口径两条都不应用，仍按类型（Q1，走原来的 35aadb3 分支）。
3. **旧条目保留**：`p07.power-battery-pool` 留在目录中（与 R1-2 保留 `p06.avoided-cost-downward-order`、在其上叠加 r12 的做法一致），只是：
   - advisory 改为 null。按类型的上限是论文设计，不再算偏差，所以论文复现 Run 和 0.6.0 旧 Run 不再显示 medium 级 “Power-battery cap counted three times”。advisory 文字不属于方法身份（`semantic_identity` 只含 id/track/scope/affects），所以论文复现口径的 applied-corrections 哈希不变；
   - description 写明已被 A20 撤回、由 r13 取代、保留只为 P0-7 到 R1-3 之间产生的 Run 的身份可读。
   共用池的代码路径（`allocate_capped_requests`、`headroom_pools`）保留，只在“应用 p07 池而不应用 r13”的方法学下可达（目前没有任何目录口径如此；测试用它复现 R1-3 之前的修正口径）。按类型的 Run 收到声明了共用池的余量行时报错，不静默改读。
4. **输出**：修正口径的余量行
   - `extensions.headroom_semantics` = `corrected_leftover_per_type_caps_v1`（共用池时仍为 `corrected_leftover_power_pool_v1`）；
   - 新增 `extensions.power_battery_cap_rule`（说明文字）；`pooled_power_batteries` = false；不再有 `extensions.pools`；
   - evidence 中 `power_pool_cap_mw` 改名为 `power_cap_mw_per_technology`（值相同，都是 f·B(365)）。
   投资结果不再有 `extensions.power_battery_pool`。
5. **版本（Q13）**：`value-storage-expansion-policy` 5.0.0 → 5.1.0（manifest 与 `SchemeCStorageExpansionPolicyDefinition`），VERSION_LEDGER 包 R1-3，correction_ids `r13.per-type-battery-caps`，`requires_user_opt_in = true`。修正口径的 applied-corrections 集合多了 r13，所以 R1-3 之前保存的修正口径 Study 在迁移分类中是 `method_upgrade_required`（有测试）。agent-investment 不升版本：它对同样的输入行为不变，变的是余量行不再声明池。

## 2 文件

| 位置 | 改动 |
|---|---|
| `gridform_core/builtin/scheme_c_1000twh/storage_headroom.py` | 模块说明改写（A20）；新常量 `HEADROOM_SEMANTICS_PER_TYPE`、`POWER_BATTERY_CAP_RULE_*`；按 `pooled` 写语义、规则与 evidence 键 |
| `gridform_core/builtin/scheme_c_1000twh/v2_module_definitions.py` | 新函数 `power_battery_pool_in_force`；余量与 decide 两处改用它；`storage-expansion-scheme-c` 5.1.0；注释。文件是 CRLF/LF 混合，按字节编辑，保持原行尾 |
| `gridform_core/data/methodology/corrections/r13.json`（新） | `r13.per-type-battery-caps` |
| `gridform_core/data/methodology/corrections/p07.json` | `p07.power-battery-pool` 的 advisory 改为 null、description 改写；notes 加一条 |
| `gridform_core/manifests/value-storage-expansion-policy.json`、`docs/release/VERSION_LEDGER.json` | 5.1.0，R1-3 升级条目（opt-in） |
| `docs/generated/METHODOLOGY_PROFILES.md`、`MODULES.md` | 重新生成（修正口径应用的修正 36 → 37） |
| `tests/golden/corrected/C1、C2、C4、C5、C6、C7、C9.json` | 各追加一次修订（见第 4 节） |
| `docs/release/P0_GOLDEN_DELTA.md`、`source-release-manifest.json` | 重新生成 / 刷新 |
| `tests/test_r13_per_type_battery_caps.py`（新） | 见第 3 节 |
| `tests/test_p07_investment_corrections.py` | 修正口径余量断言改为按类型；共用池测试改在“R1-3 之前的修正口径”（`pre_a20_corrected()`，从修正口径的应用集合中去掉 r13 后激活）下运行 |
| `tests/test_result_advisories.py` | 修复前 Run 的 advisory 列表去掉 `p07.power-battery-pool` |
| `tests/test_application_service.py` | 版本 5.1.0 |
| `docs/methodology/drafts/0.4/p07_investment.md` | 储能余量一节：按类型上限、A20 的理由、撤回池的说明 |
| `docs/SCHEME_C_MODEL_CARD.md` | 投资规则一句 |
| `CHANGELOG.md`（随第一个提交） | 论文复现口径描述、correction id 表 R1-3 行、golden 摘要、P0-7 一节加注、新小节 “Per-type power-battery expansion caps” |
| `docs/handoff/METHODOLOGY_EDITOR_HANDOFF.md`、`MODEL_CHANGES_BRIEF.md`、`WEBSITE_UPLOADER_HANDOFF.md`（及 worktree 根目录的三份副本，内容相同，被 exclude 不入库） | 见第 5 节 |

## 3 测试

新增 `tests/test_r13_per_type_battery_caps.py`（8 个）：

- `PerTypeBatteryCapTests`（trigger fixture）：
  - 17520 期方波（power_room = 2000 MW）下修正口径每种电池上限 400 MW，不声明池，语义、规则与 evidence 键为新值；R1-3 之前的修正口径给出同样的上限并声明 400 MW 池；
  - 请求 300/200/100 MW（合计 600，超过原来的 400 MW 池，但每种都在 400 以内）：修正口径全部接受；R1-3 之前的修正口径为 200/133.33/66.67；
  - 请求 500/450/100：1C、0.5C 各被截到 400，0.25C 接受 100，剩余上限按类型扣减，合计不超过 3×400；
  - 修正口径的 Run 收到声明了共用池的余量行时报错；
  - 论文复现口径：r13 与 p07 池都不应用，余量为 0，无池。
- `MethodChangeTests`：目录（r13 为 gated、无 advisory；p07 池仍在、无 advisory；修正口径两条都应用但池不生效）；VERSION_LEDGER 5.0.0 → 5.1.0、R1-3、opt-in，manifest 与类版本一致；去掉 r13 的已存修正口径 Study 分类为 `method_upgrade_required`，r13 在 numeric 列表中。

运行结果：见第 6 节。

## 4 golden

- **论文族**：`capture.py check --tier fast`，D1–D3 gated 0（只有 identity）。D4、D5 没有跑：论文复现口径不应用 `p07.storage-leftover-headroom`，走原来的 35aadb3 分支；decide 中 `power_battery_pool_in_force` 在论文口径下先判 `enabled("p07.power-battery-pool")` 为假，与改动前同值，所以代码路径不变。
- **修正族**：`capture.py revise --cases C1 C2 C4 C5 C6 C7 C9 --correction-id r13.per-type-battery-caps --finding A20 --finding P5-02`，各追加一次修订（C1 r14、C2、C4、C7、C5 r13、C6 r11、C9 r3）。变化的 gated 列全部在 trajectory 区，而且只是记录性的扩展列：
  - C1、C2、C4、C7（smoke，不满一年，余量为 0 并记原因）：4 列，即 `headroom_semantics`、`pooled_power_batteries` 改值，`pools.power_battery_pool` 删除，`power_battery_cap_rule` 新增；
  - C5（VALUE 101 legacy two_year）：6 列，另加 evidence `power_pool_cap_mw` → `power_cap_mw_per_technology` 改名；
  - C6（dynamic two_year）、C9（GBP1 public2 2025）：12 列，另加投资结果 `extensions.power_battery_pool.*` 六列删除。
  - 提案、装机、`initial/remaining_headroom_mw_by_technology` 等列都没有出现在 delta 中，所以撤回池对这三个全年算例的投资轨迹为 0：池在这些算例中从未被用满（例如 101 中 2026 年电池提案 0.418 MW，上限 4.065 MW；GBP1 第一年请求合计约 104 MW，上限约 360 MW）。
  - C3、C8 不变。
- C9 用本地构建的 public2：`build_value_uk_pack_revision.py --link hardlink`，manifest sha `f43e0e46…1439`，与 C9 钉住的值一致；构建前后两个来源目录（`data-audit/staging/gbp1-national`、`r029-public1`）的文件清单（路径、大小、mtime）哈希相同；临时包用后已删除，没有上传。
- 没有生成数值报告：修订只涉及记录性扩展列，没有数值列变化，revision 自带的 delta 已经完整说明（修正族也不要求数值报告）。
- `delta_report.py --write`，`--check`：0 条无法归因；`capture.py validate`：passed。

## 5 交接文档与方法学草稿

- 方法学交接：顶部阅读提示中 A20 一条标为“已实施（R1-3），可以定稿”；术语表、3.2 节冻结行为（“各拿一份上限”不再写成偏差）、C18 行、K-9（论文口径补句；修正口径改为按类型上限公式 ΔP_k ≤ H^bat，三者合计最多 3H^bat，说明 P0-7 至 R1-3 的共用池已撤回、正文不要写池公式）、V-7、M-5（5.1.0）。
- 模型改动简报：C17（版本、上限数字）、C18 整行改写、4.2 节冻结行为、6 节表中 P0-7 一行加注。
- 网站交接：2.3 节修正口径设定列表一行；2.9 节新增一行（Study 迁移确认 5.1.0；advisory 少一条 medium；没有新界面字符串；不要写“共用一个功率池”）。顶部阅读提示中 A19 一条不属于本单元，没有改。
- 草稿 `p07_investment.md`、`SCHEME_C_MODEL_CARD.md` 见第 2 节。

## 6 测试与门禁结果

- `vpy -m unittest`：test_r13_per_type_battery_caps、test_p07_investment_corrections、test_p07_investment_accounts、test_p07_s10_acceptance、test_p07_head_decide_record、test_p07_cost_ledger_v2、test_methodology_static_scan、test_methodology_profiles、test_methodology_identity、test_methodology_activation、test_result_advisories、test_version_ledger、test_ui_contract_fixtures、test_catalog_lazy、test_r12_economic_downward_order、test_project_revision_migration：236 个，OK。
- `check_methodology_catalog.py`：passed；`check_version_ledger.py`：passed；`generate_reference_tables.py --check`：重新生成后通过；`refresh_source_release_manifest.py --index --check`：两个提交前都 not stale。
- `scripts/p0_gate.py quick`（gate venv，独立的 TMPDIR 与 VALUE_DATA_HOME，在包含全部代码和文档改动的工作树上运行）：status passed，145 s，16 步全部通过，没有豁免；backend ratchet 2508 个 id，147 个失败，基线 106，new 0，flaky 0，forbidden ports 0。
- 安装目录：`find …/installed -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*' -print` 只列出 `.supervisor.lock`（作者现网 supervisor 在 2026-10-03 05:41 创建的锁文件，早于本轮，以往报告已说明）；`diagnose-value --prefix …/installed`："Installation integrity and runtime checks passed."。本单元没有启动服务，没有接触 8766/8800，没有向安装目录写入。

## 7 采用的决定与偏差

采用：A20（按类型上限，比例 0.2，保留 P5-01）、Q13（新 correction 改变修正口径的 applied-corrections 哈希；策略模块 5.1.0 标 opt-in）、Q1（论文复现口径逐位不变）、A16-7（public2 只在本地，用后删除）。

偏差与说明：

1. **撤回的实现方式**：没有从目录中删除 `p07.power-battery-pool`，而是新增 `r13.per-type-battery-caps` 并让它优先（同 R1-2 在 `p06.avoided-cost-downward-order` 上叠加 r12 的做法）。理由：P0-7 到 R1-3 之间的修正口径 Run 记录了这条 id，保留它让这些 Run 的身份与迁移分类仍可读；共用池的代码保留但没有任何目录口径会走到。若作者希望目录更干净，可以在发布前删除该条与池代码（会再改变一次修正口径的身份）。
2. **advisory**：`p07.power-battery-pool` 的 advisory 改为 null，r13 也不设 advisory。后果：P0-7 到 R1-3 之间用共用池跑出的修正口径 Run 不会显示“本 Run 用了共用池”的提示。目录的 `applies_when` 不能按口径区分，若给 r13 设 advisory，所有论文复现 Run 都会显示一条不成立的提示，所以没有设。这些 Run 只存在于本分支的本地测试中，且在已知算例上池从未被用满。
3. **evidence 键改名**：`power_pool_cap_mw` 在按类型时改为 `power_cap_mw_per_technology`（数值相同），避免“pool”一词继续出现在修正口径的输出里。前端与导出没有读取这个键（已 grep `app/`）。
4. **没有数值报告**：见第 4 节。
5. **agent-investment 不升版本**：它对同样输入的行为不变。

## 8 遗留问题

- 方法学交接与网站交接顶部的阅读提示中，A19（弃电顺序）一条仍写“待改”。那是 R1-2 的范围，本单元没有改。
- 网站交接 2.9 节的 Study 迁移一行仍写“默认 PSM 升到 6.4.0”，没有包含 R1-2 的 6.5.0；同样不属于本单元，留给交接文档的统一更新。
