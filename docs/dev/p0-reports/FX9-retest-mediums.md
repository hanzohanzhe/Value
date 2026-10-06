# FX9 复测中等问题：N-1、N-2、F2-N1，以及 S-D4 余项 N-3 和 M-D1 界面

分支 `fix/review-2026-10-04`（INTEG）。范围来自 `docs/handoff/FOUR_ROLE_TEST_REPORT.md` 第 9 节（9.3–9.6、9.8）。
作者授权见 DECISIONS A16（“必须修 + 强烈建议一起修”）。

## 1 做了什么

| 提交 | 问题 | 改动 |
|---|---|---|
| `4bc2a71` | N-2 | `gridform_core/data_validation_layers.py`：pandas 抛出的是 pytz 的 `AmbiguousTimeError`，它不是 `ValueError` 的子类，所以 `ambiguous="NaT"` 的回退分支从来没有执行，映射预览变成 HTTP 500 `GF_RUNTIME_001`。现在回退分支同时捕获 pytz 的 `InvalidTimeError`。新增内部函数 `_parse_declared`，逐行给出无法定位的原因：秋季重复的一小时按行序推断不出时，报 `ambiguous local time (a repeated autumn hour that the row order cannot place; give this row an explicit UTC offset)`；春季不存在的时刻报 `non-existent local time (skipped by the spring clock change)`。原来两种情况都只报 “unreadable timestamp”，后者顺带改善了 N-6 的第一点。时间轴层 `timestamp_findings` 在发现中写明其中有几行是秋季的歧义时刻。`parse_declared_timestamps` 的接口不变。 |
| `cb8ca25` | N-1 | 新增公开函数 `methodology.data_pack_violation(profile, manifest, manifest_bytes)`，它是唯一的数据包白名单检查。`combination_violations`（Study 解析、preflight、Run 入口）和 `data_validation_layers.profile_eligibility`（Data 页校验面板、`GET /api/data-packs/<id>/validation`）都调用它。口径行新增 `pack_supported`、`pack_support_reason`，不在白名单中时 `eligible=false`，blocking code 为 `VALUE_PROFILE_COMBINATION_UNSUPPORTED`。`validate_data_pack` 传入 manifest 文件字节（只在传入的 manifest 就是该文件内容时），所以按文件 sha 钉住的包也能正确匹配。列表缓存升到 `value.data-validation-cache/v2`，旧的 v1 摘要按 not evaluated 处理，避免继续显示过期的 “Eligible”。前端 `methodologyUse` 在 `pack_supported === false` 时显示 `Not eligible — not a thesis-era pack`（规格 11.2 原文）。方法学草稿 `p05a_data_reading.md` 和 `METHODOLOGY_EDITOR_HANDOFF.md` 各补一段。 |
| `69c982c` | F2-N1（G4-05） | `backend/extension_results.py`：`year-results-v2.json` 不超过 16 MiB 时仍整份解析（行为不变）；超过时不再直接放弃，而是按唯一写入方（`application.py` 的 `json.dumps(..., indent=2)`）的版式逐行读取。读取时对每个字节做 sha256，只取每年的 `schema_version`、`year` 和 `market.extensions.extension_artifacts`。JSON 字符串中不能有裸换行，所以结构行没有歧义。上限：artifacts 合计 2 MiB（超出报 `extension_artifacts_size_limit`），文件 4 GiB。结果按文件身份（路径、inode、大小、mtime、ctime）缓存 4 份。版式不符的文件仍报原来的 `year_results_size_limit`。之后的扩展清单、产物契约和摘要字段校验与原来完全相同。 |
| `3609bcd` | M-D1 界面 | `gridform_core/market_replay.query_auction_view` 按 clearing offer id 关联 FX4 的 `storage_orders` 账本（accounting 区）。每条储能报价带上自己的 `accepted_mwh`、`offer_status`、`offer_reason_code`，`acceptance_granularity` 为 `storage_offer_ledger`，并计入 complete coverage。前端新增纯逻辑模块 `app/features/market/auctionOffers.ts`：Accepted 列显示该条报价的 MWh，悬停显示 `Storage offer ledger: {status} ({reason})`；表下方加一行 12px、`--muted` 色的说明，写明按毛值记、同时段买回会使 orders 账本中的净调度更低（对应 M2-N5）。没有账本行的旧 Run 仍按原来的 `(asset total)` 显示。UI 合同夹具已重新生成，只多了两个键，数值无变化。 |
| `18f34c1` | N-3（S-D4 余项） | `timestamp_row_problems` 新增 `last_utc` 和 `origin_offset_minutes`（距最近的 1 月 1 日 00:00 UTC 的分钟数；1 月份伦敦时间与 UTC 相同）。偏移不为 0 时，映射审阅加一条**不阻断**的 warning `GF_DATA_TIMESTAMP_ORIGIN`。年份不同（如 2023 年的参考数据）只显示，不判定。映射审阅的 Timestamps 一行追加首、末时间戳。 |

## 2 测试

新增或修改的测试：

- `tests/test_data_mapping.py`
  - `test_london_autumn_hour_seen_once_is_a_row_finding_not_a_runtime_error`（N-2）：17,520 行、不带偏移、连续半小时的 2025 年文件，按 Europe/London 解析。预览不再抛异常，`valid=false`，`problem_count=4`：第 4228、4229 行为春季不存在的时刻，第 14308、14309 行为秋季歧义时刻。提交被拒；时间轴层返回一条 `GF_DATA_TIMESTAMPS` 发现，写明有 2 行歧义；带偏移的秋季时间戳为 0 个问题。修复前，这个文件在 `timestamp_row_problems` 就抛出 `pytz.AmbiguousTimeError`（已在本地复现）。
  - `test_series_shifted_against_the_model_clock_is_warned_not_blocked`（N-3）：对齐时偏移为 0、没有 warning；+30、−30 分钟时各有一条 warning，审阅仍然有效；2023 年数据偏移为 0。
- `tests/test_data_validation_layers.py`
  - `WhitelistEligibilityTests`（N-1）：
    - 用户副本在结构上有效，但对 doctoral 不可用，原因 “not a thesis-era pack”、blocking code 都正确，`combination_violations` 给出同样的结论；
    - 对仓库中的每个数据包、每个口径，面板的 `pack_supported` 都与编辑器的检查一致；`value-101-network-v1` 对 doctoral 不可用。
  - `ListPacksTests`：v1 缓存不再被采用。
- `tests/frontend/unit/data-pack-validation.test.mjs`：新增 N-1 用例（药丸文案；三层颜色不受影响）。
- `tests/test_extension_results.py::test_year_results_above_16_mib_are_read_line_by_line`（F2-N1）：
  - 按写入方版式生成 >16 MiB 的合成文件，带每年 60,000 条 period summary、嵌套的同名键和含引号与括号的字符串。查询返回 3 条产物，sha256 等于整份文件的 sha256，未声明字段不外泄。
  - 第二次查询走缓存。
  - 改字节后出现非有限数，报 `year_results_invalid_json`。
  - 版式不符时报 `year_results_size_limit`；artifacts 超限时报 `extension_artifacts_size_limit`。
- `tests/test_market_replay.py::test_storage_offer_ledger_gives_each_storage_offer_its_accepted_mwh`（M-D1）：
  - 两条电池报价分别得到 0.5 和 0 MWh；
  - 状态和原因码正确；
  - outcome 的资产合计仍保留；
  - coverage 为 complete。
- `tests/frontend/unit/auction-offers.test.mjs`（新）：单元格和说明文字的 3 个用例。

另做了一次真实文件核对（只读）：本机所有 21 份已有的 `year-results-v2.json`（含 INSTALLED state 和其他工作区的 Run，最大 61.8 MB，用时约 1 s），逐行读取的结果和 sha256 与整份解析完全相同，其中 8 份带扩展产物。

运行结果：

- `vpy -m unittest tests.test_data_mapping tests.test_data_validation_layers tests.test_methodology_profiles tests.test_extension_results tests.test_market_replay`：80 个，OK（skipped=1：`EligibilityTests` 因缺少 GBP1 包，按原样跳过）。
- `vnode --test` 两个前端单元文件：OK。
- `tests/ui_contract_fixtures.py --write`，随后在门禁中 `--check`：通过。
- 每个提交前都先运行 `refresh_source_release_manifest.py --index`，再运行 `scripts/p0_gate.py quick`：5 个代码提交和本报告提交前共 7 次，全部为 `status: passed`，16 个步骤都通过，没有豁免，backend ratchet 无新失败。每次约 140 s。

## 3 采用的决策

- **A16-1、A16 后续**：N-2、N-1 为“发布前顺手修”；F2-N1、M-D1 界面、N-3 为“下一轮”，按任务一并处理。
- **Q12**：M-D1 只读 accounting 表 `storage_orders`，`orders` 和其他 trajectory 列不动；没有 golden 修订。
- **规格 1.3**：新增文字 ≥12px，只用 `--muted` 等已有 token；旧元素样式不改。
- **原则 3（不确定就不猜）**：N-3 只提示，不阻断；年份不判定。

## 4 偏差

1. **F-FX9-1（N-1 文案）**：设计方在 F-FX3-10 中取消了 “not a thesis-era pack”，原因是当时后端没有这项判定。现在后端有了，所以恢复规格 11.2 的原文，并让这个原因优先于结构层和发现层的原因。已记入 `P0_FRONTEND_DEVIATIONS.md`，待设计方确认。
2. **F-FX9-2（M-D1 界面）**：规格 3.4 没有写储能逐条接受量的显示方式，悬停文字和表下说明是本单元加的，已记录待确认。复测建议中的“标出同时段买回”只做成一句说明，没有加列（界面保持最小改动）。
3. **F-FX9-3（N-3）**：规格 11.6 只要求检查单调、缺口和重复，所以错位只提示、不阻断，已记录待确认（是否改为阻断）。同一检查**没有**加到数据包时间轴层（`timestamp_findings`），因为对非工作区包，时间轴发现在修正口径下是 error，新增发现码会改变已有包的资格。
4. **F2-N1 的做法**：评审报告 G4-05 建议在写入端加一个旁路文件 `extensions/artifacts-v1.json`，并给旧 Run 提供重建流程。本单元采用任务允许的另一种做法：在读取端按写入方的固定版式流式读取。这样旧 Run 不用重建也能显示，写入端和冻结的 Run 目录都不变。代价是依赖 `indent=2` 版式；版式一变，就退回原来的 `year_results_size_limit`，fail closed。
5. **CRLF**：`backend/server.py`、`gridform_core/data_pack_validation.py`、`gridform_core/market_replay.py`、`app/page.tsx`、`tests/test_market_replay.py` 都是 CRLF 和 LF 混用。编辑后已按 HEAD 逐行恢复原来的行尾，diff 中只有实际改动的行。

## 5 未决与提示

- 设计方需要确认 F-FX9-1、F-FX9-2、F-FX9-3。
- C3 一日教学 Run 的 UI 合同夹具，在各阶段的第一个时段都没有储能报价，所以夹具里的 `storage_offer_ledger` 路径没有实例。这条路径由单元测试覆盖。
- N-6 的其余两点（角色卡片不显示时间戳声明；两个 Study 显示同一个未标注的哈希）不在本单元范围内。
- `diagnose-value` 的输出中有一行 vinext 的 “Static file stream error … Premature close”，但它最终报告检查通过，退出码为 0。这一行来自它自己的探测请求，与本单元无关。

## 6 安全核对

- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`。这是现网 supervisor 的文件，FX4、M8 报告中也有同样记录，不在 app/runtime/installer 之下。`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”，退出码为 0。门禁的 `installed_inventory` 步骤每次都通过。
- 对 INSTALLED state 中的 `year-results-v2.json` 只做了读取，没有写入。
- 没有启动任何服务，没有连接 8766/8800 端口，没有向任何进程发信号。18xxx 端口上没有监听。
- INTEG 中没有 `__pycache__` 或 `.pyc`，Python 全部通过 `vpy` 调用。scratch 中本单元的临时文件约 0.5 MB。
