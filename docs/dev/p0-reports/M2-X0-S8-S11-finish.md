# M2-X0-S8-S11-finish 工作报告：X0 S8–S11 第五轮复审的处理

- 施工单元：VALUE P0 `M2-X0-S8-S11-finish`
- 分支与 worktree：`fix/review-2026-10-04`（INTEG，`value-fix-review-2026-10-04`），在 `15b6aaa` 之上追加提交
- 完整的 X0 S8–S11 报告见 `docs/dev/p0-reports/M2-X0-S8-S11.md`；该报告第 12 节简要记录本轮，并指向本文件
- 日期：2026-10-05

## 1 进度概要

X0 S8–S11 已于 `46e142b` 合入 `fix/review-2026-10-04`。合入时第四轮复审的结论仍是 changes_required。之后 `821a02e`、`2ed4cca`、`15b6aaa` 处理了第四轮的意见。随后的复审（本文称“第五轮”）确认第四轮的 4 项都已修好，但提出了 1 个 major、2 个 minor：major 由 `2ed4cca` 新开的 doctoral 恢复路径引入。本轮全部接受，没有驳回项。追加 3 个代码提交，另有本报告提交：

| 提交 | 对应意见 |
|---|---|
| `5708563` | major：模型按包 id 决定行为的包，不经恢复认定为源包 |
| `dc6773a` | minor 1：修订迁移的口径选择与预检使用同样的白名单输入 |
| `7484a0b` | minor 2：测试辅助函数与文件摘要函数的代码质量 |
| 本报告提交 | 报告与提交正文约定 |

每个代码提交前都做了以下事情：刷新 `source-release-manifest.json`；`p0_gate quick` 的结果为 `status: passed`（15/15，棘轮无新失败）；`scripts/golden/capture.py check --tier fast` 通过，0 gated differences。三个代码提交的正文都包含 Findings、Track、Correction ids、Golden、Delta、Tests 六个字段和 Co-Authored-By 行。

## 2 Review response

### 2.1 major：恢复认定与按包 id 决定的模型行为

**问题**（接受，已复现）：`recovered_source` 按内容把 `recovered-base-<suffix>` 认定为源包，doctoral 白名单随之放行。但对 GBP1 public1 而言，包 id 本身决定模型行为：
- `nuclear_policy.applies_to_data_pack` 只在 id 为 `value-uk-open-data-pack-v1` 时启用 VALUE-UK 核电机组口径（按 EDF 电站拆分、`model_unavailable_from_year`、不允许内生投资）；
- `doctoral_weather.uses_doctoral_weather` 按两个 VALUE-UK id 选择 doctoral 站点天气适配器。

换了 id 的恢复包会以聚合的 Nuclear 资产运行，轨迹不同，却标为 doctoral 加 GBP1，违反 Q1/Q3。第四轮报告 11.3、`pack_source_identity` 的文档字符串和 P0_CONVENTIONS 第 10 节中“数据字节和语义元数据完全相同”的说法不成立，已更正。

**做法**（复审推荐的保守方案）：
- 在 `gridform_core/pack_source_identity.py` 中定义唯一的清单 `ID_KEYED_PACK_IDS = NUCLEAR_POLICY_PACK_IDS | DOCTORAL_WEATHER_PACK_IDS`。
- `nuclear_policy.applies_to_data_pack` 改为引用 `NUCLEAR_POLICY_PACK_IDS`。原常量 `nuclear_policy.VALUE_UK_OPEN_DATA_PACK_ID` 没有任何引用方，已移到 `pack_source_identity`。
- `doctoral_weather.py` **没有改**（见偏差 24）。它的字节属于调度天气身份 `weather_execution_identity`。我试过改它，结果 S11 的 35aadb3 修订重建测试（D1、C1、C7、HTTP 迁移、口径选择）全部变成 unverifiable，等于让所有带站点天气的已保存 Study 都需要用户重新确认。因此改为加一条绊线测试：用 AST 断言 `uses_doctoral_weather` 中的字面集合等于 `DOCTORAL_WEATHER_PACK_IDS`，并断言 `gridform_core` 与 `backend` 中只有 4 个允许的文件出现这些 id 的字面量（清单本身、doctoral 天气集合、pack_class 登记表，以及 server 两个参考路由的默认包 id）。今后若新增按包 id 改变行为的代码，绊线会失败。
- `recovered_source` 拆为两步：`_recovered_content_source`（原有的内容核验）和 `recovered_source`（内容核验通过，且源 id 不在清单中）。`resolve_pack_identity` 遇到“内容相同但 id 决定行为”的恢复包时返回 `unverified='recovery_id_keyed'`，白名单违规说明为 “… model behaviour keys on the pack id, so the recovered copy under a new id does not behave as that pack”。
- `review_frozen_recovery` 因此会在审查阶段阻断 doctoral GBP1 Run 的恢复：`methodology_violations` 的 sub_reason 为 data_pack，阻断原因以 `VALUE_PROFILE_COMBINATION_UNSUPPORTED:` 开头。
- 不钉住包的口径（value-corrected）照常允许恢复，但审查报告的 `limitations` 会写明：恢复包的新 id 会失去按 id 选择的行为，重算结果可能与源 Run 不同。这个问题早于本轮，记为遗留，不阻断。

**测试**：
- `tests/test_pack_source_identity.py` 新增 `IdKeyedRecoveryTests`，共 4 个测试：
  - 清单与 `applies_to_data_pack`、`uses_doctoral_weather` 实际按 id 判定的结果逐 id 一致；
  - 没有其他模块比较这些 id；
  - GBP1 id 替身（VALUE 101 的副本，id 改为 GBP1，按它的两个 sha 钉住 doctoral 的 GBP1 条目）：源包与冻结副本无违规，恢复包被拒且说明含 “model behaviour keys on the pack id”；`applies_to_data_pack` 对源包、冻结副本、恢复包分别为 True、True、False，正是被拒的原因；
  - 对照：同样内容在 VALUE 101 id 下仍被认定，说明规则针对的是 id，而不是内容。
- `tests/test_doctoral_run_worker_path.py`：
  - 新增：GBP1 替身上的 doctoral Run 经真实 API 与 worker 完成，恢复审查返回 `allowed=false`、`methodology_violations` 和口径错误码。把 `ID_KEYED_PACK_IDS` 置空后，该测试在 `allowed` 断言处失败（审查放行）。
  - 新增：value-corrected 的 GBP1 替身 Run，恢复审查允许，`limitations` 中写明失去的行为。
  - 加强 `test_a_doctoral_run_is_recovered_into_a_doctoral_study_that_runs`：恢复后重跑的 `model-output/year-results-v2.json` 的全部数值叶子（键名含 `seconds` 的计时字段除外，超过 100 个）与源 Run 完全相同，用“行为相同”支撑“认定为源包”。

### 2.2 minor 1：迁移口径选择的白名单输入

**问题**（接受，已复现）：`_profile_choices` 调用白名单时传的是 revision manifest，不带文件字节。对 zonal Study，这个 manifest 还是合并后的 base 加 overlay manifest。只按文件 sha 钉住时，Study 解析、预检和 worker 都接受，迁移却把 doctoral 判为不支持。

**做法**（复审的首选方案）：
- `classify_revision_mismatch`、`migrate_project_revision` 新增关键字参数 `whitelist_packs`（`methodology.pack_entry` 行：base 包与 zonal Network Pack，含 manifest 文件字节），并传给口径选择。
- 服务端新增 `_study_whitelist_packs`，构造方式与 Study 解析 `resolve_project_draft` 相同，用于 GET/POST `revision-migration`。启动 Run 时由 pack root 与 zonal 选择构造；预检直接传入它本来就在检查的那些行。
- Study 派生与研究套件重装只读取分类种类。默认口径接受任何包，所以种类不受影响，这两处保留回退（只有规范 sha）。P0_CONVENTIONS 第 10 节写明了这一点，并保留“新增钉住应同时列出两个 sha”的建议。

**测试**（`tests/test_project_revision_migration.py`，新增 2 个）：
- 只按文件 sha 钉住时，带 `whitelist_packs` 的分类把 doctoral 列为 supported 且符合参考预设，可选择并迁移成功；不带时仍为 unsupported（data_pack），保留这条断言用来说明差异。
- 经真实 HTTP 接口：GET `?profile_id=doctoral…` 显示 supported，POST 确认后 Study 记录 doctoral。把 `_study_whitelist_packs` 换成返回空列表后，该测试失败（409 `VALUE_PROFILE_COMBINATION_UNSUPPORTED`）。

### 2.3 minor 2：代码质量

- `tests/test_frozen_input_integrity.py` 新增模块级函数 `rehash_snapshot_identity(root)`；`FrozenInputIntegrityTests.rehash` 改为调用它，原有调用方不变。`test_doctoral_run_worker_path.rehash_snapshot` 也改为调用它，不再以 `self=None` 调用另一个测试类的实例方法。
- `PACK_ID`、`PACK_ROOT` 移到 `ROOT` 旁边，函数前后的空行符合 PEP 8。
- `backend/frozen_input_recovery._digest` 更名为公开的 `file_sha256`（流式读取）。`frozen_run_recovery` 删除重复的 `_file_sha256`，另外两处内联的 `hashlib.sha256(path.read_bytes())` 也改用它。

### 2.4 提交正文约定

本轮 3 个代码提交和本报告提交的正文都包含 Findings、Track、Correction ids、Golden、Delta、Tests 六个字段；今后的提交照此执行。第四轮之前的提交已在 M2-X0-S8-S11.md 11.4 节补记，历史不改写。

### 2.5 附带观察（复审未列为问题）

复审指出，冻结副本中经适配器变换的 binding，其数据字节不与源包绑定。当前钉住的包都没有适配器 binding，所以现在无法利用；而且恢复认定本来就不认定适配器 binding。记为遗留：将来若有钉住的包使用适配器，需要为冻结副本补核验。

## 3 测试与门禁

- 最终合跑 22 个相关模块，共 225 个测试：口径目录、激活、身份与静态扫描，包身份，doctoral worker 路径，冻结输入完整性与恢复，冻结 Run 恢复，Run 输入快照，doctoral 天气与核电，修订迁移，P0-8 求解合同升级，预检，P0-5 基线，研究套件与 Study 派生。唯一失败是 M0 基线中已有的 `test_run_input_snapshot…test_zonal_overlay_is_frozen_and_verified_separately`；跳过 3 个，均为环境缺少研究包或可选依赖。归档工作区相关的 3 个模块共 12 个测试通过。
- 新增 8 个测试：包身份 4 个、worker 路径 2 个、修订迁移 2 个；加强 1 个（恢复后重跑的数值等价）。两个关键新测试都做了反向验证：把修复置空后它们失败（见 2.1、2.2）。
- 三个代码提交前，`p0_gate quick` 均为 `status: passed`（15/15，`backend_ratchet` 与 `eslint_ratchet` 均通过，无新失败）。
- `scripts/golden/capture.py check --tier fast` 在 `5708563` 与 `dc6773a` 之前均通过，0 gated differences，两族 golden 都没有修订。`7484a0b` 只改测试辅助函数和摘要函数，不触及模型代码。
- 行尾：`backend/server.py`、`gridform_core/preflight.py` 中被修改的区域保持原有的 LF/CRLF；`backend/frozen_run_recovery.py` 中唯一的 CR 行没有触及。

## 4 应用的决策

- Q1/Q3：doctoral 口径严格冻结到论文时代的包。凡模型行为依赖包 id 的包，换 id 的副本一律不视为同一个包。
- Q13：修订迁移的口径选择与 Study 解析、预检、worker 使用同一白名单输入。
- 保守原则：按复审推荐，选择不改变任何 Run 轨迹的方案（阻断，而不是让行为改按解析后的 id 判定）。

## 5 偏差

- 偏差 24：复审建议让 `doctoral_weather` 引用同一个常量，但没有改 `doctoral_weather.py`，理由见 2.1（其字节属于调度天气身份，改动会让所有带站点天气的 35aadb3 Study 无法重建修订 basis）。改为保留字面集合，并用 AST 绊线测试保证它与 `DOCTORAL_WEATHER_PACK_IDS` 一致。行为上与“引用同一个常量”等价，只是单一来源由测试保证，而不是由 import 保证。
- 偏差 25：value-corrected 口径下恢复 GBP1 Run 不阻断，只在审查的 `limitations` 中说明失去的行为。复审把这一点列为遗留，而改变恢复后的行为需要修正 id 和作者决定。

## 6 遗留问题

- value-corrected 口径下恢复 GBP1 Run 会失去 VALUE-UK 核电口径（偏差 25）。若要保留，需要让 `applies_to_data_pack` 按 `resolve_pack_identity(...).manifest['id']` 判定。这会改变所有口径下恢复 Run 的轨迹，需要修正 id，并由主管或作者决定。
- 冻结副本中适配器 binding 的数据字节与源包的绑定（2.5）。
- 沿用：doctoral Run 能否恢复到 value-corrected 口径，待作者决定；`value-uk-1000twh-reproduction` 仍未钉住（偏差 17）。

## 7 INSTALLED 与进程

- `find <INSTALLED> -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*' -print` 只列出现网 supervisor 的顶层 `.supervisor.lock`（mtime 2026-10-03 12:41，早于本轮）。按 P0_CONVENTIONS 第 2 节，它属于现网，不在只读范围内，也不是本线写入的。
- `diagnose-value --prefix <INSTALLED>` 输出 “Installation integrity and runtime checks passed.”。
- 没有启动独立服务：HTTP 测试经 `start_local_api` 绑定 0 端口，没有连接 8766/8800，没有向任何进程发送信号。
- worktree 中没有 .pyc。分支没有 upstream，`origin/main` 仍为 35aadb3，没有 push。
- 本轮写入 scratch 的只有几个小脚本和日志。
