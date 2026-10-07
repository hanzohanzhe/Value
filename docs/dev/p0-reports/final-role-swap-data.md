# 最终构建验收：换数据（add your new data）角色

- 被测构建：`fix/review-2026-10-04` @ `c204aac`（`git archive HEAD` 到 scratch，`vinext build` 重新构建）。
- 环境：API 18882、UI 网关 18883，`VALUE_DATA_HOME=scratchpad/build/final_roles/swap-data/state`（全新数据目录）；Playwright headless（chromium 1243）加 API 核对。
- 依据：DECISIONS A27（作者：“除了这些，四角色测试的中低缺陷你也可以一起修好”）；本单元只做验收，不改代码。

## 结论：通过但有问题

完整路径能走通：新用户安装 VALUE 101 教学包，创建基线 Study 并完成两年 Run；复制独立 BASE 包，用映射编辑器导入 4 个 CSV（逐时、闰年、日/月/年、GW、MWh/period、EUR 与汇率、Europe/London 夏令时），查看校验面板，派生新 Study，完成两年 Run，查看结果、回放时间和比较。数值抽查与输入一致。

有 1 个高等缺陷（基线需求文件标为 MWh/period，模型却按 MW 读，换数据后的比较差一倍）、3 个中等缺陷、6 个低等缺陷。

## 1 能用的部分（证据）

| 环节 | 结果 |
|---|---|
| 新数据目录首次启动 | VALUE 101 页面提示教学包未安装，并给出 `install_synthetic_pack.py --value-101-only` 命令；运行后 25/25 输入就绪 |
| 基线 | “Create baseline Study” 创建修订 1；“Run complete two-year model” 约 5 分钟完成（含首次归档运行环境），状态 passed |
| 复制包 | 引导第 2 步复制出独立包 `my-swap-data-pack-…`；基线包文件哈希不变（前后都是 `88ca2112…`） |
| 逐时 EUR 价格（Belgium，8760 行，ISO，UTC） | 选 EUR 后出现 `EUR per GBP`、`FX basis`、`Price year`，未填时预览按钮禁用；列名提示 “Column name suggests EUR”；报告写明 “each hour is used for two half-hour periods”；样例 90.00 EUR → 76.923 £（1.17）；角色卡显示 `原币种 EUR · 汇率 1.17 EUR/GBP · 汇率口径 annual average · 价格年份 2025` |
| 日/月/年、GW（demand.forecast，17520 行） | 自动识别为 DD/MM/YYYY，并写明依据 “CSV line 578 has a first field above 12”；0.063614 GW → 63.614 MW；Run 中第 0 期预测需求 31.807 MWh，与文件一致 |
| 闰年半小时（demand.real，2024 年 17568 行，MW） | 报告写明删去 2 月 29 日并按年电量重新缩放；数据年份 2024 与 Study 首年 2025 不同时给出 `GF_DATA_TIMESTAMP_YEAR`。Run 中第 0、2783、2784、2832（3 月 1 日 00:00）、17519 期的需求都等于 文件值 × 0.5 × 1.0030462（按删去 2 月 29 日后的电量算出的系数），对齐正确 |
| Europe/London 当地时间（France profile，MWh/period） | 夏令时文件 0 个问题；把 48 期/日的“天真”当地时间文件逐行报出 2 个不存在的春季时刻和 2 个无法定位的秋季重复时刻 |
| 美式日期 | 自动识别 MM/DD/YYYY（“CSV line 290 has a second field above 12”）；声明为 DD/MM/YYYY 时报 5436 个问题，并提示 “132 gaps last about a month: the dates may be in MM/DD/YYYY order” |
| 其它校验 | 分号文件在暂存时拒绝，并说明另存为逗号分隔；重复与缺口逐行列出 Data row / CSV line；半年序列须另勾确认框，两项都勾后提交按钮才可用；价格年份 2023 给出 `GF_MAPPING_PRICE_YEAR` |
| 提交 | 每次提交后 “SHA 改变” 计数加 1，角色卡显示映射文件、原始文件、规则哈希和时间戳列 |
| 校验面板 | 25/25，Structural 12 warnings、Chronology/Plausibility Passed、Corrected Eligible、Doctoral “Not eligible — not a thesis-era pack”；展开后逐角色列出警告 |
| 派生 Study 与 Run | 引导第 3 步显示基线、年份、修订哈希、原包和新包；创建后转到 Runs，Check readiness 为 Ready（约 2 分钟，35,040 期）；两年 Run 约 2.5 分钟 passed，契约、科学校验、能量平衡均 passed |
| 被引用的包变只读 | 新 Study 保存后，再改该包时提示 “该数据包已被保存的 Study 引用。请再次复制后编辑” |
| 回放时间 | 窗口行 `2025-01-01 00:00 → 2025-01-02 00:00 (UTC model time)`；stress 表表头 `Start (model date & time, UTC)`；API 返回 `timezone: UTC`、`calendar: fixed_365_day_utc_periods`；点 stress 事件的 “Replay →” 会跳到对应窗口（period 33 → 窗口 29–76） |
| 比较 | 勾选两个 Run 后，身份检查只有 “Base and network data: Changed”，列出 4 个改动的角色；按年列出 9 个指标，VRE 三项写明缺值原因；CSV 导出正常 |

## 2 当前缺陷

### 高

**S-F-高1 基线需求文件写的是 MWh/period，模型按 MW 读；照着基线单位换数据，需求会多一倍，比较也差一倍。**

- 现象：VALUE 101 的 `demand.real`、`demand.forecast` 绑定单位是 `MWh/period`，文件表头是 `mwh`。但 `data_pack_validation.LEGACY_DEMAND_MW_SHA256` 把这两个文件列为“按 MW 读的旧文件”，所以基线第 0 期需求是 13.83 MWh（= 27.66 × 0.5），基线两年需求合计 467,740 MWh，正好是文件“MWh 值”的一年总和。
- 新用户按基线文件的单位理解数据：我想把需求提高 15%，把 27.66 MWh/period 换算成 63.6 MW 上传（映射编辑器明确要求 MWh/period 先换成 MW，这一步本身是对的）。结果 Run 的需求是基线的 2.31 倍（539,540 对 233,870 MWh/年），出现 6,035 个 stress 期、51.2 GWh 缺口；比较页显示 CEM 系统成本 +174%、碳排放 +213%，但没有任何地方提示需求单位的口径不同。
- 唯一的线索是复制包校验面板里 14 条结构警告中的两条（两个需求角色各一条 “Legacy demand label MWh/period is interpreted as raw MW”），角色卡、映射编辑器的需求说明和比较页都没有提到。
- 复现：新数据目录 → VALUE 101 创建基线并运行两年 → 引导复制包 → 用 `demand.real` 映射上传一份 `MWh/period` 值为基线 1.15 倍的半小时 CSV（单位选 MWh/period，或先换成 MW 再选 MW）→ 派生 Study 并运行 → 比较。新 Run 的 `energy_balance.sum_demand_mwh` 是基线的 2.3 倍，而不是 1.15 倍。
- 建议：把 VALUE 101 教学包的需求文件改标为 MW（新包修订），或者至少在角色卡和映射编辑器中写明 “基线文件按 MW 读（表头写作 mwh）”；比较页可增加 “年需求（MWh）” 一行，让量级变化一眼可见。

### 中

**S-F-中1 有 Run 在后台运行时，映射编辑器无法使用：暂存的 CSV 在 0.3–2 秒后被清空。**

- 复现：启动任一 Run（例如基线两年 Run），在 Data 页（引导中的独立包）选择角色，上传 CSV。`POST …/csv-mapping/stages` 返回 201，编辑器显示原文件 SHA 和列选择；下一次约 2 秒一次的轮询（`GET workspace` → `POST projects/resolve-draft` → `GET …/catalog`）之后，列选择全部消失，回到 “选择含标题行的 CSV”。Run 结束后同样操作正常（连续 12 次采样都保持暂存状态）。
- 原因（代码阅读）：`page.tsx` 中 `savedDataResolution` 以 `dataContextProject` 的对象身份作键；轮询刷新工作区后得到新对象，`dataContextResolution` 暂时为 null，`readOnlyReason` 变成 “正在解析基线方法所需的数据角色…”；`JourneyDataEditor` 的 `mappingContext`（含 `readOnlyReason`）变化，`CsvMappingEditor` 以新 key 重新挂载，暂存、映射和审阅状态全部丢失。R4-3 报告观察到的 “映射目录与当前目标包版本不一致” 偶发提示可能也与此有关。
- 影响：完整研究可能要运行数小时，期间无法准备下一份数据；用户看不到任何报错，只看到文件“没上传上去”。

**S-F-中2 stress 缺口与 “Unserved demand” 两个口径并列，比较和单位成本只用后者。**

- 现象：同一 Run 顶部写 “Total shortfall 51.2 GWh … the shortfall is recorded as unserved energy”，年度卡片却写 “Unserved demand 363.64 MWh”（2026）；比较页和 CSV 导出的 `unserved_energy_mwh` 也是 417.64 / 363.64 MWh，没有 stress 缺口这一项。`cem_system_cost_gbp_per_mwh_served` 的分母 539,121 MWh 是需求减去 417.64 MWh，而 stress 账目算出 2025 年少供 28,167 MWh，所以 “每 MWh 供电成本” 把未供的 27.7 GWh 也算作已供。
- 复现：任何出现 stress 事件的 Run（如上面的换数据 Run）→ Runs 页对比顶部横幅与年度卡片 → 比较页展开 2025。
- 建议：年度卡片和比较中把 stress 缺口与按 VoLL 记录的未供电量分开写明，或说明 “Unserved demand” 只含模型记录的部分；单位成本的分母说明口径。

**S-F-中3 逐时需求无法导入，报告还给出互相矛盾的说明。**

- 复现：`demand.real` 映射上传 2024 年逐时 8784 行（ISO、UTC、MW）并选时间戳列。报告同时出现：
  - `demand contains 8784 numeric periods; at least 17520 are required`；
  - 8783 行 “gap of 60 minutes … (expected 30)”；
  - `GF_DATA_TIMESTAMP_COVERAGE: … (365.98 days), less than a model year … the last 8,736 periods (182.0 days) are filled by repeating the series from its start. Confirm this below before committing.`
- 同一套映射对价格角色接受逐时数据并说明 “each hour is used for two half-hour periods”，对需求却不支持，也没有告诉用户怎么做。编辑器只有一句 “不会推断或重采样时长”。
- 建议：需求角色遇到 60 分钟步长时直接说明 “需求只接受半小时数据，请先换成 17,520（或闰年 17,568）个半小时”，不要再输出 “用重复补齐” 和 “请确认” 这类不适用的句子。

### 低

1. **S-F-低1 “映射 SHA” 不含时间戳声明。** 同一文件分别按 Auto（读作 MM/DD）和 DD/MM/YYYY 预览，映射 SHA 都是 `0244d0b9…`；时区、日期顺序、时间戳列只记在审阅和绑定里，不进 `spec_sha256`（`backend/data_mapping.py` 第 562 行只对 `spec.to_dict()` 求哈希）。界面上称为 “映射 SHA”，用户比较两次映射时会误以为相同。
2. **S-F-低2 校验详情的 `clock_adapter` 与实际读法不一致。** 8760 行逐时价格显示 `cyclic_repeat`（实际是逐时加倍）；17568 行闰年需求显示 `take_first_required_periods`（实际是删去 2 月 29 日并缩放）；正好 17520 行的 France 曲线也显示 `cyclic_repeat`。同一报告下方的 `clock_alignment` 是对的。
3. **S-F-低3 只读时映射编辑器一直显示 “正在核对当前包的映射目录…”。** 包被 Study 引用后，`CsvMappingEditor` 不再请求目录，但文字仍是 “正在核对”，看起来像在加载。
4. **S-F-低4 覆盖说明的措辞。** 只缺 1 期的文件写成 “(365.0 days), less than a model year … the last 1 periods (0.0 days)”。建议按期数写，例如 “缺 1 个半小时（30 分钟）”，并用单数。
5. **S-F-低5 比较的参照 Run 不明确。** 增量以先列出的 Run（这里是换数据 Run）为 “+0 · 0%”，基线显示为 −63.55%；界面没有说明哪个是参照，也不能选择。换数据比较通常以基线为参照。
6. **S-F-低6 审阅有效期显示原始 ISO 串。** 例如 `2026-10-07T22:05:02.444364+00:00`（带微秒，UTC）。页面其它位置用本地时间，建议统一格式并写明时区。

### 观察（不计缺陷）

- 映射成功提交后，编辑器回到空白，只靠计数 “SHA 改变 n” 和角色卡变化来确认，没有一句 “已提交”。
- Runs 页首次进入时 “Check for” 默认是 “Two-period wiring check”，而空状态文字写 “start with two full years”。
- 本次 Belgium 价格的改动对结果没有影响：VALUE 101 的 Belgium 互联线可用容量为 0。这是测试数据设计造成的，不是缺陷。

## 3 测试数据

`scratchpad/build/final_roles/swap-data/csv/`（共 11 个文件，由 `gen.py` 和内联脚本生成）：逐时闰年需求（ISO、MW）、半小时闰年需求、半小时 DD/MM/YYYY 需求（GW）、逐时 EUR 价格、Europe/London 夏令时曲线（MWh/period），以及负面用例：美式日期、分号文件、重复与缺口、半年序列、天真当地时间、2023 价格年份。Playwright 脚本在 `…/swap-data/pw/`，保留 9 张截图在 `…/swap-data/shots/`。

## 4 环境核对

- 两个服务都按记录的 PID 停止（API 1508152、UI 1508154），端口 18882/18883 已释放；两个 Run 的 worker 都已退出；没有连接 8766/8800，没有使用按模式匹配的 kill。
- 删除了 scratch 中的源码副本、数据目录（约 750 MB）和浏览器配置，`final_roles/swap-data` 剩 6 MB。
- INSTALLED：`find … -newer install-receipt.json -type f ! -path '*/state/*' ! -path '*/logs/*'` 只列出 `.supervisor.lock`（作者实例的锁文件，以往报告已说明），没有 `.pyc`；`diagnose-value --prefix …` 输出 “Installation integrity and runtime checks passed.”（过程中有一行 vinext 静态文件流的 “Premature close” 日志，不影响结果）。
- Python 全部通过 `vpy` 调用。本单元只新增这份报告；它是纯文档提交，没有运行 `p0_gate.py quick`（没有代码或清单变化）。
