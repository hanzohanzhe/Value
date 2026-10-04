# 博士原模型对标修复（保留核电与固定分区）Implementation Plan

> **For agentic workers:** Continue with the selected execution method: executing-plans
> for inline work, or subagent-driven-development when delegation is permitted and useful.
> Honor existing user choices and AGENTS.md. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 除用户允许不迁入的电解槽直接负荷外，按现有审计逐项恢复博士原模型的物理、结算、投资和项目演化规则；保留已批准核电政策、固定分区网络框架及月度存档。
**Architecture:** 独立原件参考R0 → 仅应用批准例外的测试参考R1 → 对标全国核心C → 固定分区最终物理执行Z。采用明确的政策/状态/物理意图接口和单次状态提交，不让真实信息泄漏进日前预测计划。
**Tech Stack:** 现有Python3.10、numpy/pandas/netCDF4/scipy、unittest、SQLite；不新增求解器、服务或监控。
**Spec:** [范围、例外与验收合同](C:/Users/86150/Documents/Codex/VALUE-1.1/docs/superpowers/specs/2026-09-06-doctoral-alignment-exceptions.md)
**Status:** CORE_IMPLEMENTATION_APPROVED / D1_APPROVED / ZONAL_ADAPTATION_DEFERRED；2026-09-06。任务状态不代表已实施或已通过。

## 2026-09-06 第一批执行结果（优先于下方历史任务状态）

### 2026-09-08 最新更新：按 final9.6 继续施工

本节中的 2026-09-06 数字和状态为历史快照。用户已更正论文基准为桌面 `PhD_thesis_final9.6.docx`。本轮完成了 9.6 独立利润/风光 cap/政策分配组件、规划零概率与经济量缩放修复、年度引擎切换、磁盘 checkpoint、显式 experimental 全国 PSM 入口和严格验收保护。当前博士相关 266 项通过；全库 1,196 项仍有 58 失败、63 错误、21 跳过，相对施工前没有新增失败节点。

**当前状态是 PARTIAL_THESIS96_REPAIRS_VERIFIED / ANNUAL_CEM_NOT_READY。** 年度 CEM、储能逐期价格和 12% cap、融资、owner/投产/退出及完整双成本/碳账仍未闭环。没有正式年度/多年运行、监测或旧 checkpoint 续跑。以[9.6 施工与重新审计报告](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-thesis96-alignment-20260908/report.md)及[当前 F01–F26 状态](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-thesis96-alignment-20260908/findings-status.json)为最新进展；下方历史任务步骤不因此自动打勾。

**后续更新：D3 已获用户批准并完成组件级实现。** 采用权威分站台账→唯一全国 `Nuclear` 调度/现金流视图；登记和管线身份绑定恢复输入，逐站网络适配仍延期。最新博士相关 224 项及既有回归 57 项通过，详见[D3实施与验证](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-core-restoration-20260906/nuclear-aggregation.md)。下文“D3待决”仅为第一批历史交付状态，不再要求确认。正式年度主流程及新核心磁盘月度恢复仍待集成，不能据此宣布整模型可运行。

当前状态为 PARTIAL_COMPONENTS_VERIFIED / PUBLIC_INTEGRATION_PENDING，不能重启正式模型。已落地全国源内核、单期事务引擎、状态/账本、严格输入分支及规划投资组件；博士相关 203 项、既有月度/分区/核电回归 57 项通过。不代表年度主流程已经接通或整模型一致。

完整逐项状态、保护文件哈希和未完成项见[本批实施报告](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-core-restoration-20260906/report.md)及[机器证据](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-core-restoration-20260906/evidence.json)。coverage JSON 已更新为组件级进度；T08 仍延期，T10 磁盘集成和 T11 正式发布门槛尚未完成，T12 仅小例证据。

新增 D3 待决：原单一全国 Nuclear 调度对象与现行按站核电政策的表示关系。建议以站点时间表汇总容量、仍按全国对象调度；不得将全国爬坡/启动/CAPEX 参数逐站复制。核电政策数据本批未改。

## 执行修订：先修复全国原版本，分区延期

用户已批准修复原实现自身缺陷；要求先完成全国/铜板版本，再考虑分区适配。当前执行T01–T07、T09–T11的全国部分及T12有界验证与诚实交付；T08和分区新目标/phase/版本/诊断修改延期，不修改现有分区方法。

当前依赖改为T04→T09，T02+T06+T09→T10；T08不再阻塞全国账本或月度checkpoint。当前T10测试使用candidate全国引擎，分区拥塞和新增phase测试保留为后续设计，不列为本次已完成项。T11/T12明确记录zonal_adaptation_deferred；不要求全国结果等于分区结果。D1已批准，D2不再反复询问。

本次只实施并进行有界测试，不启动正式年度/十年运行、监测、旧checkpoint续跑。下文最初方案中有关“本轮只计划”及D2待决的描述是历史阶段说明，由本节覆盖。

## Global Constraints

已获全国核心修复与有界验证授权；正式模型运行和分区改造不在当前阶段。执行时必须同时遵守[完整合同](C:/Users/86150/Documents/Codex/VALUE-1.1/docs/superpowers/specs/2026-09-06-doctoral-alignment-exceptions.md)。
- 不迁入两类电解槽直接负荷，但不误删独立氢储能。
- 核电保持5958MW基线、禁止内生新增、现役退出/HPC外生投产/Sizewell C管线规则；不重新改工期或研究EDF数据。
- 固定分区、线路/断面限制和同价比例规则保留；D2确认前不改数学目标。新目标不得沿用v2身份冒充方法未变。
- 原代表点天气和项目映射修复保留，无平均曲线回退；需求及17520×0.5h时钟保持原执行口径。
- 历史输出、原件及checkpoint只读；新方法缺失新状态的旧JSON不得伪造兼容。
- 现有月度存档保留并升级完整状态；月末不做年度投资。最多一个回放worker，BelowNormal，六数值线程变量为1，不设监听。
- 脏工作区原有修改归用户。不能重置、覆盖未提交天气修复或把整个工作区无差别提交。
- 单元测试和有限验证与长期模型运行分开；此计划不代表任何模型已启动。GitHub发布不在本任务内。

## 当前证据与待决边界

- [26项审计报告](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-model-difference-audit-20260906/report.md)
- [结构化发现](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-model-difference-audit-20260906/findings.json)
- [源码证据](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-model-difference-audit-20260906/evidence.json)
- [本计划覆盖映射](C:/Users/86150/Documents/Codex/VALUE-1.1/docs/superpowers/plans/2026-09-06-doctoral-alignment-coverage.json)

D1建议：修复原负容量项目丢弃、负新增被正新增缩放覆盖、跨年批次年龄错误；保留原行为记录，不声称逐行完全相同。不同意时采用原执行行为，但不能称为修复。

D2建议：保留固定分区和重调度框架，允许显式升级目标优先级以恢复原可行充电顺序。建议版新增最小未供电阶段，不把它误称为v2原有层级；这也是本次待批准的方法变化。原v2即使无拥塞也可能因正价出口选择不充电；若原数学目标完全冻结，就必须把F02/F03的分区残余列为保留方法差异。

**D1获批；D2延期。当前直接实施全国核心，不实施分区方法变化。**

## 交付分层与依赖

| 阶段 | 任务 | 可验收结果 |
| --- | --- | --- |
| 冻结参考 | T01 | 原件oracle、批准例外、拒绝身份漂移 |
| 物理行为 | T02–T03 | SOC/批次/机组约束、充电出口顺序、出价恢复 |
| 钱与项目 | T04–T07 | 净利润→agent→投资→投产闭环可逐笔对照 |
| 分区接入 | T08 | 不污染日前信息，网络最终执行后只提交一次 |
| 账本与恢复 | T09–T10 | 双口径成本/碳、完整月度/年度续跑状态 |
| 发布验证 | T11–T12 | 局部→整年→跨年→十年分级证据，未评估不算通过 |

主依赖：T01→T02→T03→T04；T01→T05→T06；T04+T06→T07；T03+T04+D2→T08；T04+T08→T09；T02+T06+T08+T09→T10；T07+T09+T10→T11→T12。

可并行：参考证据/夹具准备、T05纯预处理实现与T02–T04主体。**共享canonical_psm_data.py、v2_module_definitions.py、staged_psm.py、contracts.py的集成由同一责任人串行完成**；不派多个agent同时改这些文件。T05独立doctoral_planning.py；T04/T07使用doctoral_policy.py，避免创建/编辑冲突。

## 公共接口与测试观察合同

以下名称是拟新增接口，不宣称当前仓库已实现。保持现有JsonContract序列化方式。
- `StorageBatch`：asset_id、batch_id、charged_absolute_period、stored_energy_mwh、source_cost_gbp；输入/输出能量与损耗单独记录，批次年龄不以每年重置的局部period相减。
- `DoctoralRuntimeState`：model_year、next_period、next_absolute_period、storage_batches_by_asset、generator_memory_by_asset、source_rule_hash。Generator memory逐项映射原机组类会被下一期读取的状态：前期出力/启停、自然能源剩余额度等；必须由源函数读写清单校验，不用泛空字典替代。
- `NationalPhysicalIntent`：run_id、model_year、period_index、ahead_result_hash、realised_input_hash、source_rule_hash、desired_generation_mwh_by_asset、desired_charge_mwh_by_asset、desired_discharge_mwh_by_asset、desired_export_mwh_by_asset、priority_groups。出口使用互联线资产ID，由网络映射取得landing。priority_groups为有序组，每组包含order、action（charge/discharge/export）、resource_class、asset_ids（源顺序）；与网络同价比例冲突时按D2声明处理，不允许任意再分配。建议schema=`value.national-physical-intent/v1`；设备约束仍来自BalancingInput，不在意图里放松约束。
- `AgentAccount`输出字段：market_income_gbp、balancing_income_gbp、redispatch_income_gbp、cm_income_gbp、decarb_income_gbp、operating_cost_gbp、net_profit_gbp，均说明是增量还是总额。只有不同收入来源才相加，不能把已含平衡收入的总额再加一次；CAPEX/折旧按原投资判断处处理，不随意重复扣除。
- 测试统一调用`run_case(case_id, engine=..., overrides=...)`，从冻结输入运行对应真实原函数/候选函数；下方flat观察字段只由真实结果计算，不是预置返回预期值。
- fixture保存source路径/语句、输入、R0预期、R1批准调整、单位、误差阈值。连续恢复比较只允许去掉run-instance ID、路径、墙钟时间，不去掉源规则/数据/方法哈希或资金字段。

数值门槛见合同：离散事件完全相等；普通功率/能量逐值误差≤1e-7+1e-10×|参考值|，现金逐行≤0.0001GBP、年度累计≤0.01GBP。分区求解使用其已认证容限并报告目标/守恒残差。若实现表达式精度确实需要不同门槛，必须在回放前提出依据并冻结，不能根据失败结果放宽。

## 每个任务的统一执行约定

下方测试代码为最低起步覆盖，执行者应放入该任务指定的新测试文件。所有`run_case`必须经真实调用路径，不能用mock固定通过核心数学行为。
先添加夹具和测试并记录red，再实现最小变更、跑green及相关旧回归。缺新API引起的red只是接口起点；还须用当前行为呈现被审计的数值差异，不能把ImportError当科学修复证据。
以下PowerShell命令均在 `C:/Users/86150/Documents/Codex/VALUE-1.1` 下执行；测试模块路径为Python导入名而非相对文件交付链接。

## T01｜冻结参考、例外和独立测试工具

覆盖：F01、F04、F26。前置：无。

### 文件与职责

- Create：[gridform_core/doctoral_alignment.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/doctoral_alignment.py)
- Create：[gridform_core/data/doctoral_alignment/profile-v1.json](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/data/doctoral_alignment/profile-v1.json)
- Create：[tests/doctoral_reference_harness.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/doctoral_reference_harness.py)
- Create：[tests/test_doctoral_alignment_profile.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_alignment_profile.py)
- Create：[tests/fixtures/doctoral_alignment/manifest.json](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/fixtures/doctoral_alignment/manifest.json)

**接口：** 测试唯一入口 run_case(case_id: str, *, engine: str, overrides: dict[str, object] | None = None) -> dict[str, object]，engine仅reference/candidate/zonal_v2/zonal_aligned。结果为任务内明确列出的观察字段。生产load_alignment_profile(path: Path) -> dict[str, object]检查例外、哈希与D1/D2状态。

**确定性夹具：** manifest保存source文件哈希、来源函数/语句、case_id、输入、原始预期、例外调整预期、单位/容差。profile_guard使用复制的manifest，分别篡改weather_sha256、nuclear_policy_sha256；electrolysis_disabled原侧/候选侧均关闭两类直接负荷，独立氢储能power/energy不变。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class ProfileTests(TestCase):
    def test_exceptions_are_explicit_and_do_not_delete_hydrogen_storage(self):
        x = run_case("electrolysis_disabled", engine="candidate")
        self.assertEqual(x["electrolysis_load_mwh"], 0.0)
        self.assertEqual(x["hydrogen_storage_mw_after"], x["hydrogen_storage_mw_before"])
        self.assertEqual(x["hydrogen_storage_mwh_after"], x["hydrogen_storage_mwh_before"])

    def test_input_mutation_is_rejected(self):
        for key in ("weather_sha256", "nuclear_policy_sha256"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "identity"):
                    run_case("profile_guard", engine="candidate", overrides={key: "0" * 64})
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_alignment_profile -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. 先记录git status、未提交差异和审计源码哈希；保留用户未提交工作。需要隔离时按using-git-worktrees在执行阶段创建工作区，不能只从HEAD漏掉未提交的天气修复。
  2. 从C:/Users/86150/Desktop/Dr.seal/能源投资/invest!/人人如龙/人人谦让/newpredictedVRE0.03 - sum - seperate prediction - 0.2c43_REPD2025_physical_income_fixed/decarbonization_cost_research/simulation_model.py提取Generator/Battery等必要类及decay_func、acm_income、acm_income_balance、store_service_three、ahead_market_bidding、curtailment_market_bidding、balancing_market_bidding。通过AST节点白名单+依赖闭包载入测试命名空间；禁止直接import原main，禁止导入绘图/Excel保存/长跑顶层语句。未解析名字直接失败，不能用candidate函数填充reference。
  3. 原年度参考从原run_investment_analysis.py与case3源语句提取；涉及共享全局时使用冻结config对象和独立TemporaryDirectory。完整回放使用独立受控子进程，先校验全部源码/数据，不在T01启动。
  4. 例外只进入测试适配层和新profile；原文件字节保持不变。D1、D2未确认的profile不得启动生产运行。保留R0原始案例与R1例外调整后的期望，两者不能互相覆盖。
  5. 对oracle自身做资格测试：原source income两类边际价、原200期VRE阈值、原负容量丢弃均能呈现；不满足即oracle_unqualified，不能生成黄金基线。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- 测试参考从原件而非候选取得；原件哈希不变；不导入原main；D1/D2未确认拒绝生产启动。

## T02｜恢复储能批次、初始值和跨年机组状态

覆盖：F05、F06。前置：T01、D1。

### 文件与职责

- Create：[gridform_core/builtin/scheme_c_1000twh/doctoral_state.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/doctoral_state.py)
- Modify：[gridform_core/canonical_psm_data.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/canonical_psm_data.py)
- Modify：[gridform_core/v2/orchestrator.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/v2/orchestrator.py)
- Modify：[gridform_core/builtin/scheme_c_1000twh/psm_runtime_state.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/psm_runtime_state.py)
- Test：[tests/test_doctoral_state_alignment.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_state_alignment.py)

**接口：** 新增StorageBatch与DoctoralRuntimeState(JsonContract)，字段见公共接口节；initialise_doctoral_state(state: YearState) -> DoctoralRuntimeState；年度state序列化携带同一批次/机组历史，非从容量推SOC。

**确定性夹具：** soc_year_boundary：100 MWh池，年末10 MWh，进入下一年无充放电；first_year_empty：相同池首次为0。batch_decay：普通电池100 MWh、一周期衰减0.000021；age_cross_year：最后一个周期充电，跨年年龄增加而非归零（仅D1修正版）。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class StateTests(TestCase):
    def test_opening_soc_is_not_half_capacity(self):
        self.assertEqual(run_case("first_year_empty", engine="candidate")["soc_mwh"], 0.0)
        self.assertEqual(run_case("soc_year_boundary", engine="candidate")["opening_soc_mwh"], 10.0)

    def test_batch_survives_json_and_decays(self):
        x = run_case("batch_decay", engine="candidate")
        self.assertAlmostEqual(x["soc_mwh"], 99.9979, places=8)
        self.assertEqual(x["state_before_json"], x["state_after_json"])
        y = run_case("age_cross_year", engine="candidate")
        self.assertEqual(y["age_after"], y["age_before"] + 1)
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_state_alignment -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. 去掉energy*0.5作为生产默认。初年空池；新增储能初始能量0；已有资产只取已验证期末状态。恢复缺字段时拒绝，不按50%补齐。
  2. 保存每批次charged_absolute_period、stored_energy_mwh和其资产；恢复原每期衰减、持有费用和放电年龄资格。按原实际MW量纲计算的内部语句只在边界转换一次MWh。
  3. 原Gas/Biomass/Water跨期字段逐一映射到generator_memory，包含上一期出力、启动状态、天然能量预算与补充状态；字段由源类与各执行分支的读写集合验证，不能只保存SOC。
  4. 年度transition写入期末物理状态；成本观察和物理状态分别传递，不用市场summary替代可恢复状态。D1批准时采用全局单调period索引；严格分支保留旧年龄行为并明确标记。
  5. 储能扩容只扩大功率/能量上限，不凭空加电；缩容/退休需要记录剩余电量处置及能量守恒，不得静默clip。若原语义导致非法状态，作为D1具名缺陷记录，不能自动选择新物理政策。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- 首次0、跨年10→10、批次年龄、衰减、成本年龄、JSON完整；核电policy未改。

## T03｜恢复全国日前及真实平衡的原调度顺序

覆盖：F01、F02、F03、F07、F08。前置：T02。

### 文件与职责

- Create：[gridform_core/builtin/scheme_c_1000twh/doctoral_market.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/doctoral_market.py)
- Modify：[gridform_core/builtin/scheme_c_1000twh/staged_psm.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/staged_psm.py)
- Modify：[gridform_core/builtin/scheme_c_1000twh/copperplate_balancing.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/copperplate_balancing.py)
- Modify：[gridform_core/staged_market_contracts.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/staged_market_contracts.py)
- Modify：[gridform_core/canonical_psm_data.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/canonical_psm_data.py)
- Test：[tests/test_doctoral_market_alignment.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_market_alignment.py)

**接口：** clear_doctoral_ahead(ahead_input: AheadMarketInput, state: DoctoralRuntimeState) -> AheadMarketResult；build_doctoral_intent(balancing_input: BalancingInput, state: DoctoralRuntimeState) -> NationalPhysicalIntent。NationalPhysicalIntent仅记录目标动作，不修改运行state。

**确定性夹具：** excess_equal_demand：0.5h、VRE100MW、预测=实际50MW、空储能可充50MW/25MWh、效率1、无出口/电解，预期充25。storage_before_export：多排5MWh、储能/出口均可5、出口£50，预期充5/出口0。water_budget_empty：水电20MW、预算0，预期出力0。ramp_limited与startup_cost从源GasGenerator执行语句取得两期参考。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class MarketTests(TestCase):
    def test_unaccepted_vre_can_charge(self):
        x = run_case("excess_equal_demand", engine="candidate")
        self.assertEqual(x["storage_charge_mwh"], 25.0)
        self.assertEqual(x["blackout_mwh"], 0.0)

    def test_storage_precedes_export(self):
        x = run_case("storage_before_export", engine="candidate")
        self.assertEqual((x["storage_charge_mwh"], x["export_mwh"]), (5.0, 0.0))

    def test_source_constraints_match(self):
        for name in ("water_budget_empty", "ramp_limited", "startup_cost", "curtailment_cost"):
            self.assertEqual(run_case(name, engine="candidate")["decision_trace"],
                             run_case(name, engine="reference")["decision_trace"])
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_market_alignment -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. 按原ahead_market_bidding/curtailment_market_bidding/balancing_market_bidding和store_service_three移植执行语句到无I/O核心；adapter负责现有输入/输出与单位，不重写成另一套简化LP。固定电解关闭的唯一分支排除。
  2. 保留available、ahead accepted、realised accepted、charged、exported、curtailed分别的量，不把未接受VRE从后续流程抹掉；先储能、再出口、剩余弃电。
  3. 将curtail_cost、unit_time_cost、startup/ramp、天然能量状态接入报价与可行域。边界进口保留原时序容量/价格；费用、容量、效率都经source-to-contract表验证单位。
  4. 日前函数不能读取实际需求或实际平衡结果；NationalPhysicalIntent在实际阶段由原规则生成，旁路保存其来源ahead/realised哈希。
  5. 不把单一clearing_price作为两类原结算的唯一来源。旧公共字段若无法准确表达，增加显式组件字段/合同版本；旧字段标诊断而非权威，禁止悄悄改变旧schema含义。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- 全部解析反例通过；两个不同actual输入保持同一ahead哈希；风光、电量与功率单位守恒。

## T04｜恢复结算、运营成本和政策资金进入agent

覆盖：F09、F10、F11。前置：T03。

### 文件与职责

- Create：[gridform_core/builtin/scheme_c_1000twh/doctoral_policy.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/doctoral_policy.py)
- Modify：[gridform_core/cem_market_adapter.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/cem_market_adapter.py)
- Modify：[gridform_core/builtin/scheme_c_1000twh/staged_psm.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/staged_psm.py)
- Modify：[gridform_core/builtin/scheme_c_1000twh/v2_module_definitions.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/v2_module_definitions.py)
- Modify：[gridform_core/v2/contracts.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/v2/contracts.py)
- Test：[tests/test_doctoral_agent_cashflow.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_agent_cashflow.py)

**接口：** build_agent_accounts(market: MarketYearResult, state: YearState, policy: dict[str, object]) -> dict[str, dict[str, float]]；逐owner字段见公共接口。投资读取该年度具名账户，不从资产静态extensions读取缺省0。

**确定性夹具：** loss_not_profit：收入10m、实际运营成本12m，预期净利润−2m；separate_prices：50MWh发电报价20、50MWh储能报价100、效率1，原收入1000/5000；policy_basic为CM/decarb都0；policy_decarb与policy_cm按原分配函数对资格资产生成资金。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class CashflowTests(TestCase):
    def test_actual_cost_reaches_investment(self):
        x = run_case("loss_not_profit", engine="candidate")
        self.assertEqual(x["net_profit_gbp"], -2_000_000.0)
        self.assertNotEqual(x["recommendation"], "Invest_High")

    def test_original_settlement_and_policy(self):
        x = run_case("separate_prices", engine="candidate")
        self.assertEqual((x["generator_income_gbp"], x["storage_income_gbp"]), (1000.0, 5000.0))
        for case in ("policy_basic", "policy_decarb", "policy_cm"):
            self.assertEqual(run_case(case, engine="candidate")["accounts"],
                             run_case(case, engine="reference")["accounts"])
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_agent_cashflow -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. 按原acm_income/acm_income_balance及case3年度income归一化语句还原生成/储能结算，保留日前、真实平衡、分区额外调整及政策转移独立子账户。
  2. 把实际dispatch成本/运营gen_cost沿逐资产轨迹聚合给owner；系统资源成本保留但不能替代agent费用。缺少所需成本字段直接失败，不容许annual_operational_cost_gbp默认为0。
  3. 净利润必须等于各收入项之和减原公式规定的运营成本；资本回收/固定OPEX是否另扣依原公式，禁止现代成本账本又扣一次CAPEX。
  4. 移植原decarb/CfD相关资金可投资部分及CM分配函数，分别验证basic/with_cm/decarb。资格、容量权重、收入注入时点按原件，不能政策金额直接变MW。
  5. 分区额外结算沿保留方法单列，到账owner与物理资产mapping一致；原结算与分区现金流重复计入检测必须失败。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- −2m不是+10m；原两类结算可复现；basic政策为0；分账合计与owner净利润一致。

## T05｜恢复REPD筛选、成功率与工期

覆盖：F18、F19、F20。前置：T01。

### 文件与职责

- Modify：[gridform_core/canonical_psm_data.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/canonical_psm_data.py)
- Create：[gridform_core/builtin/scheme_c_1000twh/doctoral_planning.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/doctoral_planning.py)
- Modify：[gridform_core/planning_ledger.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/planning_ledger.py)
- Modify：[gridform_core/data/cem/planning_preprocessing_contract.json](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/data/cem/planning_preprocessing_contract.json)
- Test：[tests/test_doctoral_planning_alignment.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_planning_alignment.py)

**接口：** preprocess_doctoral_projects(rows: list[dict[str, object]], context: dict[str, object]) -> tuple[PlanningProject, ...]，context含冻结status开关、时间统计、成功率表、seed和start_year；保存每个原始row的保留/排除理由与日期推算。

**确定性夹具：** probability_by_status：Granted和Submitted各100MW，地域率0.6；原前者100后者60。missing_probability：技术均值或0.75。zombie_granted：旧进度停滞的获批项目应按源筛除。timeline_milestones与spread_start_year_only分别验证不用预测Operational代替原里程碑和仅指定项目延期散布。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class PlanningTests(TestCase):
    def test_success_gate_uses_original_status(self):
        x = run_case("probability_by_status", engine="candidate")
        self.assertEqual(x["capacity_by_project_mw"], {"granted": 100.0, "submitted": 60.0})

    def test_project_events_match_source(self):
        for case in ("missing_probability", "zombie_granted",
                     "timeline_milestones", "spread_start_year_only"):
            self.assertEqual(run_case(case, engine="candidate")["project_events"],
                             run_case(case, engine="reference")["project_events"])
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_planning_alignment -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. 直接移植原状态适用开关、技术/地区缺省概率、historical milestone计算、stagnant/overdue筛选及散布适用范围，保留确定性seed/散列语义。
  2. 真实全REPD先生成逐row对照：输入ID、原容量、保留理由、成功率、有效容量、完成年、映射依据；同一ID/技术/容量发生差异立即定位，不只比年度总MW。
  3. 原03/05环境覆盖写进各测试manifest，不把config默认False和native默认True直接当历史运行差异；政策分支与uncertain设置互不隐式改写。
  4. 核电来源项目不参与普通REPD概率/僵尸筛选重复投产，按已冻结核电policy独立注入；原输出与规范化事件均保存。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- 每项目保留/年份/概率/容量与原参考相同；核电无重复项目；坏字段明确失败不套默认平均天气。

## T06｜恢复项目财务owner、抽蓄外生表并锁住核电

覆盖：F21、F22。前置：T05。

### 文件与职责

- Modify：[gridform_core/asset_economics.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/asset_economics.py)
- Modify：[gridform_core/builtin/scheme_c_1000twh/v2_module_definitions.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/v2_module_definitions.py)
- Modify：[gridform_core/doctoral_weather_mapping.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/doctoral_weather_mapping.py)
- Modify：[gridform_core/canonical_psm_data.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/canonical_psm_data.py)
- Create：[gridform_core/data/doctoral_alignment/pumped_hydro_schedule.json](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/data/doctoral_alignment/pumped_hydro_schedule.json)
- Test：[tests/test_doctoral_commissioning_alignment.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_commissioning_alignment.py)
- Modify：[tests/test_doctoral_project_weather.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_project_weather.py)

**接口：** commissioned资产保留physical asset ID/source_project_id/weather lineage；economic owner按原assigned_generator或原比例归属。多owner项目拆为可追溯子资产，不将一个复合物理资产全部归给单一owner。年度账户按原agent聚合，不能因新asset ID/region多算主体。

**确定性夹具：** owner_commissioning：原A/B各100MW，映射A新增20，未定位再新增80，按原同年顺序分配后owner总容量与资本等于参考；pumped_schedule逐年2025–2034；nuclear_lock核电投资0、2025总5958、HPC2031/2032、SizewellC2034前pipeline且generation0。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class CommissioningTests(TestCase):
    def test_physics_and_financial_ownership_both_match(self):
        x = run_case("owner_commissioning", engine="candidate")
        y = run_case("owner_commissioning", engine="reference")
        self.assertEqual(x["owner_accounts"], y["owner_accounts"])
        self.assertAlmostEqual(x["total_commissioned_mw"], 100.0)
        self.assertEqual(x["unowned_operating_vre"], [])

    def test_exogenous_fleets_are_not_replaced(self):
        x = run_case("pumped_schedule", engine="candidate")
        self.assertEqual(x["year_2034"], {"power_mw": 5687.9, "energy_mwh": 70800.0})
        y = run_case("nuclear_lock", engine="candidate")
        self.assertEqual(y["endogenous_nuclear_mw"], 0.0)
        self.assertEqual(y["sizewell_c_generation_before_2035_mwh"], 0.0)
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_commissioning_alignment -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. 采用原同年“已定位项目先计入、未定位项目再比例分配”的顺序，同时对天气与财务权重核对；避免只修weather不修owner。
  2. 保留资本、利润、源项目、原agent和physical asset多层映射，所有经营风光都有可追溯owner。多个物理子资产到原agent汇总后CAPEX、运营成本、收入与原主体相同。
  3. 更新此前天气专项测试里assertIsNone(owner)/“不改财务归属”的旧范围假设；改成weather不变且owner正确，不能删除对应测试来掩盖冲突。重新执行天气全部专项测试。
  4. 原抽蓄年度功率/能量/CAPEX表逐行提取为JSON并保存源行/哈希，每年一次应用，普通pipeline和内生投资不得重复加抽蓄。
  5. 保持核电policy字节/哈希不变；通过相同核电注入给reference/candidate隔离批准场景变更，不把原5883或自由核电投资恢复进来。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- 天气与owner同时相符；抽蓄各年不重复；核电锁定；资本与容量合计守恒。

## T07｜恢复四档投资、风光/储能cap及退出

覆盖：F12、F13、F14、F15、F16、F17、F23。前置：T04、T06、D1。

### 文件与职责

- Modify：[gridform_core/builtin/scheme_c_1000twh/doctoral_policy.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/doctoral_policy.py)
- Modify：[gridform_core/builtin/scheme_c_1000twh/v2_module_definitions.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/v2_module_definitions.py)
- Modify：[gridform_core/cem_investment_policy.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/cem_investment_policy.py)
- Modify：[gridform_core/canonical_psm_data.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/canonical_psm_data.py)
- Modify：[gridform_core/builtin/scheme_c_1000twh/storage/storage_expansion_cap.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/storage/storage_expansion_cap.py)
- Test：[tests/test_doctoral_investment_alignment.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_investment_alignment.py)

**接口：** decide_doctoral_investment(run: ResolvedRun, state: YearState, market: MarketYearResult, headroom: ExpansionHeadroom, accounts: dict[str, dict[str, float]]) -> InvestmentDecision。保留原agent顺序与技术汇总后比例缩放，不能按owner字典序抢额度。

**确定性夹具：** vre_cap_200：200点(50,1)另100点(100,0.1)，原cap≈10；owner_cap：80/80申请、100总额→50/50；thermal_high：100MW、利润可10→新增1；storage_high：利润10/cap20→20；storage_profit：利润10/cap5→10；storage_credit：available100,demand60,charge30,accepted90,leftover10→使用10；bio_payback：22年且非High→Do_Nothing。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class InvestmentTests(TestCase):
    def test_caps_and_scale_are_original_rules(self):
        self.assertAlmostEqual(run_case("vre_cap_200", engine="candidate")["cap_mw"], 10.0, places=5)
        self.assertEqual(run_case("owner_cap", engine="candidate")["accepted_mw"], {"A": 50.0, "B": 50.0})
        self.assertEqual(run_case("thermal_high", engine="candidate")["addition_mw"], 1.0)

    def test_storage_and_biomass_rules(self):
        self.assertEqual(run_case("storage_high", engine="candidate")["addition_mw"], 20.0)
        self.assertEqual(run_case("storage_profit", engine="candidate")["addition_mw"], 10.0)
        self.assertEqual(run_case("storage_credit", engine="candidate")["excess_input_mwh"], 10.0)
        self.assertEqual(run_case("bio_payback", engine="candidate")["recommendation"], "Do_Nothing")
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_investment_alignment -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. 恢复原负残余需求至少200期的二分容量算法及真实0.20系数，不使用峰值替代；输入时序长度/单位明确，原total cap与incremental headroom不能混名。
  2. 原四档判级、原火电High×1.01、原生物质20年目标逐句恢复；经济寿命与投资回收目标为两个字段。
  3. 先计算所有agent提案，再按原同技术比例缩放；储能High利润底线、Profit不受相同High cap夹限必须单独分支，不能套通用min(requested,cap)。
  4. 储能cap核心函数保留，修正调用的charge、剩余excess和discharge来源；对虚拟池谱的完整输出逐值比较，不只验证一个cap数字。
  5. D1修正版中保留原退出公式，但让负容量事件下一年真实落地、独立于正投资缩放；批准的行政核电退役优先，不重复经济退出。D1严格分支的缺陷案例以原实际输出为参考且明确标记。
  6. 使用最终分区运行的owner收入/实际运营成本决定分区投资，不把全国反事实收入拿来驱动分区资产。每年记录推荐档、净利润、原申请、cap、缩放因子、接受量和退出量。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- 全部标量和分类反例通过；原cap谱逐值相同；owner重命名不改变经济额度；核电禁投；退出选择与D1一致。

## T08｜保留固定分区框架，接入明确版本的全国物理意图

覆盖：F02、F03。前置：T03、T04、D2。

### 文件与职责

- Modify：[gridform_core/staged_market_contracts.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/staged_market_contracts.py)
- Modify：[gridform_core/zonal_redispatch.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/zonal_redispatch.py)
- Modify：[gridform_core/zonal_solver_contract.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/zonal_solver_contract.py)
- Modify：[gridform_core/market_ledger.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/market_ledger.py)
- Modify：[gridform_core/data/contracts/solver-validation-registry-v1.json](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/data/contracts/solver-validation-registry-v1.json)
- Modify：[gridform_core/builtin/scheme_c_1000twh/staged_psm.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/staged_psm.py)
- Modify：[gridform_core/manifests/value-zonal-redispatch-balancing.json](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/manifests/value-zonal-redispatch-balancing.json)
- Modify：[gridform_core/runtime_capabilities.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/runtime_capabilities.py)
- Test：[tests/test_doctoral_zonal_alignment.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_zonal_alignment.py)

**接口：** NationalPhysicalIntent为新不可变JsonContract，字段见公共接口。resolve_doctoral_zonal(input: BalancingInput, intent: NationalPhysicalIntent) -> BalancingResult。原AheadMarketResult及其哈希仍表示预测信息集，不得替换为实际平衡后的基线。

**确定性夹具：** 使用相同天气、核电、全国需求和机组输入；无拥塞案例excess_equal_demand与storage_before_export复用T03。binding_line用1h的独立求解器单元测试：北10MWh原计划、南10MWh负荷、线路4MW、北减发价0、南增发价100；这不改变年度模型0.5h时钟。equal_price_down为两个各10MWh的同价机组，需总减10MWh。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class ZonalAlignmentTests(TestCase):
    def test_source_charge_priority_when_network_unconstrained(self):
        x = run_case("storage_before_export", engine="zonal_aligned")
        self.assertAlmostEqual(x["charge_mwh"], 5.0)
        self.assertAlmostEqual(x["export_mwh"], 0.0)

    def test_binding_line_preserves_network_and_balances(self):
        x = run_case("binding_line", engine="zonal_aligned")
        for key, value in {"north_mwh": 4, "south_mwh": 6, "flow_mwh": 4,
                           "blackout_mwh": 0, "redispatch_cost_gbp": 600}.items():
            self.assertAlmostEqual(x[key], value)
        self.assertEqual(x["ahead_hash_before"], x["ahead_hash_after"])

    def test_equal_price_pro_rata_is_retained(self):
        x = run_case("equal_price_down", engine="zonal_aligned")
        self.assertEqual(x["down_mwh_by_asset"], {"A": 5.0, "B": 5.0})

    def test_phase_evidence_cannot_be_silently_downgraded(self):
        for corruption in ("missing_phase", "wrong_order", "wrong_unit", "lock_degraded"):
            with self.subTest(corruption=corruption):
                with self.assertRaisesRegex(ValueError, "solver_evidence"):
                    run_case("new_phase_ledger", engine="zonal_aligned",
                             overrides={"corruption": corruption})
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_zonal_alignment -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. D2采用推荐边界后，保留固定zone、线路/cutset限制、供需守恒、分区调整及同价按比例规则；不引入DC/AC潮流，不改网络数据和容量。
  2. 从T03产生实际阶段的NationalPhysicalIntent，不改预测AheadMarketResult，不伪造network_effect_id、价格或ahead哈希来使旧solver接受新优先级。
  3. 显式新增最小未供电量阶段并固定其最优值（v2当前是含VoLL的报价成本首目标，并无独立可靠性层级；新增阶段属于D2待批变化），再按原storage类别顺序逐层最小化可行物理动作对charge/discharge意图的偏离，再处理逐互联线export意图，之后保留经济成本、计划偏离、throughput、稳定排序层级。逐层锁定最优值，不用任意巨大权重。物理不可行或增加未供电的充电意图允许被网络约束削减并记录原因。
  4. 该目标变化采用新显式求解策略标识（建议value.zonal-lexicographic/v3）、模块主版本（建议3.0.0）与能力声明；执行时校验版本注册未冲突。原v2夹具作为历史基线保留，不能改预期冒充旧v2完全不变。同步修改market_ledger.py的phase白名单、阶段计数及完整性检查，以及zonal_solver_contract.py的阶段/单位硬编码。版本化策略声明各phase ID、顺序、单位、容限和必需证据；旧v2保持三阶段要求，新策略保留全部新增阶段的锁定证据，不得降级成三条诊断。
  5. 存储状态只能按分区最终物理结果提交一次；全国意图和中间求解阶段均不得改SOC、批次、机组预算或到账收益。网络调整后的真实收益用于后续投资。
  6. 若D2选择冻结v2数学目标，本任务只增加独立对照及诊断，不改v2目标；F02/F03在分区端保留明确方法差异，修改coverage/profile为有条件保留，不得签发“已全部恢复”。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- 无拥塞下无退化的单资产案例匹配原物理意图；拥塞案例守恒且不越界。
- 同价分摊导致的逐资产差异明确归入保留网络方法，不能宣称逐资产全同。
- Ahead预测隔离、单次状态提交、solver/module/runtime新身份均有负向测试。

## T09｜分开恢复博士成本/碳口径与现行物理账本

覆盖：F24、F25。前置：T04、T08。

### 文件与职责

- Create：[gridform_core/doctoral_ledgers.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/doctoral_ledgers.py)
- Modify：[gridform_core/cost_ledger.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/cost_ledger.py)
- Modify：[gridform_core/carbon_ledger.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/carbon_ledger.py)
- Modify：[gridform_core/application.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/application.py)
- Test：[tests/test_doctoral_ledgers.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_ledgers.py)

**接口：** build_doctoral_ledgers(market: MarketYearResult, state: YearState, profile: dict[str, object]) -> dict[str, object]返回doctoral_reproduction与physical_accounting两套命名空间，各自带numerator、denominator、unit、boundary、status和source_rule_hash。不能反向用报表资源成本覆盖T04现金流。

**确定性夹具：** 同一成本分子900GBP、总发电150MWh、供给需求100MWh：博士发电分母口径6GBP/MWh，供需口径9GBP/MWh，字段名称不能混同。storage_carbon单元例为充100MWh、输入2kg/MWh、效率1、放40MWh，剩余归属碳120kg；不把放电再次记成新产生的排放。原始系数单位未核实不得转成tCO2。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class LedgerTests(TestCase):
    def test_denominators_are_separate(self):
        x = run_case("cost_denominators", engine="candidate")
        self.assertEqual(x["doctoral_gbp_per_generated_mwh"], 6.0)
        self.assertEqual(x["physical_gbp_per_served_mwh"], 9.0)

    def test_storage_trace_and_units_are_not_invented(self):
        x = run_case("storage_carbon", engine="candidate")
        self.assertAlmostEqual(x["remaining_carbon_kg"], 120.0)
        self.assertAlmostEqual(x["new_emissions_from_discharge_kg"], 0.0)
        with self.assertRaisesRegex(ValueError, "storage_trace"):
            run_case("storage_carbon", engine="candidate", overrides={"storage_trace": None})
        y = run_case("unverified_carbon_unit", engine="candidate")
        self.assertIsNone(y["tonnes_co2"])
        self.assertEqual(y["status"], "unit_unverified")
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_ledgers -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. 逐项抄录原后处理的CAPEX、OPEX、进出口、缺电、机制支出及发电分母公式；分开资金转移/资源成本，不把原口径“优化”为另一个口径。
  2. 分别追踪原8000缺电报告系数与当前17000等调度/报告用途；不能因报告差异就把全部市场VOLL设成8000。每个出现点标明出处、单位、用途，按各自源语句恢复。
  3. 恢复原碳公式的原始数值口径并保留原单位标签；独立保留现行有来源的运营碳/总体碳字段。单位不明时原始指数可对照，tCO2为null并明确未核实，不估算单位填数。
  4. 在实际调用链传入逐期storage_trace和电量来源，验证残余储碳及损耗归属。账本构造缺必需追踪直接报错；兼容只读历史报告可标not_evaluated，但不能判passed。
  5. 输出中用博士复刻/当前物理核算命名空间明确解释成本差异，保留年度agent资金桥接表，不能将补贴/CM多次累计。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- 公式、分母、系数和单位逐项有源语句。
- 碳追踪函数不仅存在，而且年度生产调用路径实际传入完整追踪。
- 两套成本/碳不得同名混用，不因有报告文件就判复刻成立。

## T10｜为完整新状态升级月度与年度checkpoint

覆盖：F05、F06。前置：T02、T06、T08、T09。

### 文件与职责

- Modify：[gridform_core/builtin/scheme_c_1000twh/psm_runtime_state.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/builtin/scheme_c_1000twh/psm_runtime_state.py)
- Modify：[gridform_core/subannual_checkpoint.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/subannual_checkpoint.py)
- Modify：[gridform_core/recovery_capability.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/recovery_capability.py)
- Modify：[gridform_core/runtime_capabilities.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/runtime_capabilities.py)
- Modify：[gridform_core/v2/orchestrator.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/v2/orchestrator.py)
- Test：[tests/test_doctoral_checkpoint_alignment.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_checkpoint_alignment.py)
- Modify：[tests/test_zonal_subannual_resume.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_zonal_subannual_resume.py)

**接口：** 沿用既有checkpoint发布/恢复API，运行态使用新显式schema（建议value.staged-psm-runtime-state/v2）；增加DoctoralRuntimeState、双账本前缀和策略身份的序列化与验证。旧格式可只读审计，生产恢复不得默认补零或人工改hash。

**确定性夹具：** 连续三段：全国意图充电→线路约束削减充电→下一期放电，在测试月份边界保存再恢复；scientific_state为完整规范化结果，剔除字段仅run-instance ID、路径、墙钟时间，保留全部方法/数据哈希。cross_year在12月末后跨年；old_runtime_missing_batches缺少批次/机组记忆。另测period=1487后首月发布、每月一次和保留最近2点。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class CheckpointTests(TestCase):
    def test_month_resume_is_identical_without_double_commit(self):
        a = run_case("month_resume", engine="zonal_aligned", overrides={"resume": False})
        b = run_case("month_resume", engine="zonal_aligned", overrides={"resume": True})
        self.assertEqual(a["scientific_state"], b["scientific_state"])
        self.assertEqual(b["commits_per_period"], [1, 1, 1])

    def test_old_incomplete_state_is_not_relabelled(self):
        with self.assertRaisesRegex(ValueError, "incompatible"):
            run_case("old_runtime_missing_batches", engine="candidate")

    def test_month_publication_is_not_annual_investment(self):
        x = run_case("first_month_publication", engine="candidate")
        self.assertEqual(x["last_committed_period"], 1487)
        self.assertEqual(x["investment_calls"], 0)
        self.assertEqual(x["retained_recovery_points"], 2)

    def test_checkpoint_requires_all_solver_phase_evidence(self):
        with self.assertRaisesRegex(ValueError, "solver_evidence"):
            run_case("new_phase_checkpoint", engine="zonal_aligned",
                     overrides={"corruption": "missing_phase"})
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_checkpoint_alignment -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. 新增状态字段逐一列出读写点：SOC/批次年龄/批次成本、机组前期出力与启停状态、年度水/生物质剩余额度、所有收入与成本累计、储碳追踪、下一期绝对时钟。缺字段不允许假设可恢复。
  2. 发布顺序维持物理结果与账本提交成功→完整runtime snapshot→manifest原子发布，月末发布不得调用年度投资/投产；滚动保留沿用既有安全规则，旧正式成果不删除。
  3. 更新能力注册白名单识别明确的新solver/module/runtime组合，不放宽成任意版本；运行身份同时包含天气、mapping、核电政策、原语义profile、新数据、方法版本及有序phase合同哈希。账本前缀复核按该合同核验全部阶段证据，缺阶段/错序/单位错误/目标退化均拒绝续跑。
  4. 旧年度JSON缺失新状态且代码/天气/方法身份不同，拒绝续跑。无可证明完整转换时重新生成2025基线；不能通过手改2028JSON、替换hash来继续旧轨迹。
  5. 加入月中故障、未发布manifest、内容破损、账本前缀不匹配、重复提交、年度转场后恢复的负向测试。按D1明确跨年年龄规则，新投资进入/退役离开后的状态变化只发生一次。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- 连续与续跑的完整科学状态/收益/投资输入相同，不只比较期数和SOC。
- 首月发布1487与全年17520连续性分别证明；一个月成功不代表年度闭环成功。
- 保留月度机制且不存在跨新旧方法/天气断点混用。

## T11｜把未评估与通过彻底分开，形成自动验收入口

覆盖：F26。前置：T07、T09、T10。

### 文件与职责

- Modify：[gridform_core/parity.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/parity.py)
- Modify：[gridform_core/scientific_validation.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/scientific_validation.py)
- Modify：[gridform_core/application.py](C:/Users/86150/Documents/Codex/VALUE-1.1/gridform_core/application.py)
- Create：[scripts/verify_doctoral_alignment.py](C:/Users/86150/Documents/Codex/VALUE-1.1/scripts/verify_doctoral_alignment.py)
- Test：[tests/test_doctoral_release_gates.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_release_gates.py)
- Modify：[tests/test_release_parity.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_release_parity.py)
- Modify：[tests/test_scientific_validation.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_scientific_validation.py)

**接口：** validate_alignment_evidence(evidence: dict[str, object]) -> dict[str, object]只能在必需范围全部有证据且通过时返回passed。新命令接口见验证阶梯；这是有限的一次性验证工具，不是常驻监控程序。

**确定性夹具：** all_required包含T01–T10、天气、nuclear_exception、network_exception逐项状态。将annual_dispatch替换为not_evaluated，或把F12加入例外却未获授权，release均不得passed。legacy_bug_exception只可接受D1明确列出的项。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class ReleaseGateTests(TestCase):
    def test_not_evaluated_never_counts_as_pass(self):
        x = run_case("release_gate", engine="candidate",
                     overrides={"annual_dispatch": "not_evaluated"})
        self.assertNotEqual(x["release_status"], "passed")
        self.assertIn("annual_dispatch", x["blocking_checks"])

    def test_new_undeclared_exception_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "undeclared_exception"):
            run_case("release_gate", engine="candidate",
                     overrides={"new_exception": "F12"})
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_release_gates -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. 修复all/empty/default逻辑：缺少数值比较、单位未核实、缺年度资金链、缺原oracle，均不得归入passed。单独提供engineering_tests_passed、scoped_parity_passed、annual_verified、multiyear_verified。
  2. 提供一次性CLI参数：--tier small|month|year|two-year|ten-year，--engine reference|candidate|zonal-aligned，--manifest <绝对JSON路径>，--output <新独立目录>，--serial。生产源码原件只能通过已资格认证的隔离参考适配层执行。
  3. 修订测试预期时，每项必须关联审计F编号或批准例外；不能为了绿色结果删除预测隔离、同价分摊、核电、天气、checkpoint身份等断言。
  4. 先运行现有全部测试记录基线，再运行新测试；原先已有失败单列、按相关性调查，不把基线失败转为本次通过。涉及本次调用链的问题必须处理；无关问题明确列出而非藏进“全通过”。
  5. 验证脚本写出原始差值、状态、未评估清单和允许例外，不生成覆盖旧运行名称的结果。整个路径保持BelowNormal、数值线程1、单worker串行。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- 缺证据、数值不一致和未获批准差异均能阻断对应等级发布。
- 保留原始差值，不仅输出布尔值；不能把不同方法的数值差异藏进总量容差。

## T12｜逐级串行验证、差异归因和最终交付

覆盖：F01、F02、F03、F05、F06、F07、F08、F09、F10、F11、F12、F13、F14、F15、F16、F17、F18、F19、F20、F21、F22、F23、F24、F25、F26。前置：T11。

### 文件与职责

- Create：[publication/doctoral-alignment-restoration/verification-manifest.json](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-alignment-restoration/verification-manifest.json)
- Create：[publication/doctoral-alignment-restoration/report.md](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-alignment-restoration/report.md)
- Create：[publication/doctoral-alignment-restoration/findings-status.json](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-alignment-restoration/findings-status.json)
- Create：[publication/doctoral-alignment-restoration/execution-handoff.md](C:/Users/86150/Documents/Codex/VALUE-1.1/publication/doctoral-alignment-restoration/execution-handoff.md)
- Test：[tests/test_doctoral_handoff.py](C:/Users/86150/Documents/Codex/VALUE-1.1/tests/test_doctoral_handoff.py)

**接口：** verification-manifest连接输入/源码/例外profile哈希与各tier输出。findings-status按F01–F26列before、after、evidence、residual、approval；F04始终excluded_by_user，不伪装implemented。

**确定性夹具：** 同一冻结输入：R0=原实现；R1=原实现的批准例外测试适配；C=候选全国；Z=候选固定分区。初始basic作为低耦合样本，decarb与with_cm单独检查；不将一个情景通过推广全部。所有整年为17520个半小时，不自行插入闰日。

### 施工步骤

- [ ] 1. 建立上述夹具，添加下列测试；核实参考预期有原语句/解析依据。

```python
from unittest import TestCase
from tests.doctoral_reference_harness import run_case

class HandoffTests(TestCase):
    def test_manifest_has_honest_scope(self):
        x = run_case("handoff_manifest", engine="candidate")
        self.assertEqual(set(x["findings"]), {f"F{i:02d}" for i in range(1, 27)})
        self.assertEqual(x["findings"]["F04"]["status"], "excluded_by_user")
        if not x["ten_year_verified"]:
            self.assertNotEqual(x["release_status"], "full_multiyear_verified")
```

- [ ] 2. 执行聚焦测试记录失败原因（以下为待执行命令，不是已运行结果）。

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_handoff -v
```

- [ ] 3. 按以下边界实现，并逐项保留源语句到候选函数映射。

  1. 验证顺序：小案例与源函数对照→月边界/短跨年→一个完整17520期年度→两个连续年度含投资/投产/SOC延续→2025–2034完整序列。上一级失败不启动下一级，不自动重启失败任务。
  2. 同一阶段R1、C、Z串行，不同时跑多个大型模型。先检查可用内存/页文件/磁盘并记录，不承诺运行时间；仅在已获执行授权覆盖该验证阶段时运行。本轮仅制定计划，不启动任何模型。
  3. 每年比对逐期物理量、批次/预算、两套价格、收入成本、agent类型/投资量、REPD投产/退役、核电计划与分区线路。R0→R1差异必须逐笔归属于批准例外，R1→C不得出现未声明差异，C→Z只保留解释得出的网络方法影响。
  4. 漂移排查固定为首个差异期→首个不同字段→上游输入/状态→对应源语句；不能仅调整年度聚合使总量接近。保存最小复现供修复后重跑该级验证。
  5. 出具修改文件清单、测试命令/时间/结果、每个F关闭依据、仍存差异及生产启动交接。未做多年验证则状态为代码/局部验证完成，多年待验证，不称整模型已一比一。

- [ ] 4. 重跑该任务测试及直接依赖的回归；检查当前git diff仅含登记范围，没有覆盖用户原修改。
- [ ] 5. 保存本任务的red/green、首个差异、源/候选哈希与修改清单。必要时只提交本任务已审阅文件，不自动发布、不暂存整棵脏目录。

**验收：**

- 最终产物逐项覆盖26个发现和三个保留边界；所有差异有证据或明确待决状态。
- 原代码、历史运行、旧checkpoint完整保留，发布不含自动监听或GitHub推送。

## 验证命令与原有回归保护

执行阶段先运行现有suite作为基线，不将基线失败谎报通过：

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest discover -s tests -p 'test_*.py'
```

聚焦回归最低包含以下现有模块（逐个或按组串行）：

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 -m unittest tests.test_doctoral_project_weather tests.test_subannual_checkpoint tests.test_zonal_subannual_resume tests.test_zonal_solver_contract tests.test_prompt99_zonal_redispatch tests.test_carbon_ledger tests.test_release_parity tests.test_scientific_validation -v
```

此前天气局部55项验证只说明当时对应天气代码；这次涉及owner、canonical接入、checkpoint和版本，必须重新跑受影响的天气/地点/身份测试，不能据旧55项宣布新全模型对标完成。

新脚本在T11完成且执行授权覆盖时，按以下形式逐级运行；目录示例为新隔离验证输出，不覆盖历史模型：

```powershell
& 'C:/Users/86150/Documents/Codex/2026-07-22/yue-d/.gridform/p64-clean-venv/Scripts/python.exe' -X utf8 'C:/Users/86150/Documents/Codex/VALUE-1.1/scripts/verify_doctoral_alignment.py' --tier small --engine candidate --manifest 'C:/Users/86150/Documents/Codex/VALUE-1.1/tests/fixtures/doctoral_alignment/manifest.json' --output 'C:/Users/86150/Documents/Codex/VALUE-1.1/outputs/doctoral-alignment-validation/small-candidate' --serial
```

同一命令依次选择month、year、two-year、ten-year，每级按reference→candidate→zonal-aligned串行；参数名是本计划定义的新CLI，不可在T11实现前误认为仓库已有命令。输出目录必须新建或严格验证为同次验证的续跑目录。

## 风险、失败处理和停止条件

1. 原oracle若加载了自动主循环或依赖闭包不完整：停止该参考执行，修复隔离载入；不得拿候选代码补原实现。
2. 原件已知缺陷与对标冲突：只按D1批准清单修正；新发现的源缺陷先记录对照，不能额外当作已批准科学改动。
3. D2若不允许目标变更：分区保持v2，F02/F03明示未消除；这不是以铜板替代分区。
4. 历史存档不含批次/预算/资金状态：拒绝恢复，并解释缺字段；不“迁移”成零值，不从旧2028JSON强行接续。
5. 原成本/碳单位不明：保留原始量与unknown状态，对相关tCO2/GBP指标不签通过；物理核算另列。
6. 新时期的第一分歧保留原始trace与输入，不反复换参数试图匹配年度总量。
7. 机器资源不足：保留验证日志、停止启动后续验证；不抢占其他任务、不擅自终止用户进程。
8. 计划获批后的范围内测试/修复直接推进，不为常规阶段反复索要审批；新的科学选择、范围变化和未包含在授权内的长期运行才需要用户决定。

## 交付与完成等级

- 代码层：新测试及相关回归通过，所有生产调用链确实使用新状态/现金流/ledger，不只是孤立helper通过。
- 年度层：17520期物理与财务链条完整，明确核电/电解例外和分区效果。
- 跨年层：年末投资、投产、退役、SOC/批次/预算延续与checkpoint恢复已证实。
- 全周期层：2025–2034验证完成才标full_multiyear_verified。任何未运行级别保留not_evaluated，不以代码测试替代。
- 最终报告必须逐条回应F01–F26；F04注明用户排除，核电/分区/月度checkpoint列为保留边界。列出D1批准修正与D2数学差异，绝不写成“逐行原样模型”。
- 本轮交付仅为本计划、范围合同和覆盖映射。模型代码未因该计划而改变，也没有启动/恢复/监测任务。

## 计划自审清单

- [ ] D1/D2获明确决定后写入profile（本轮保持pending）。
- [x] 26项审计发现均有处理或明确排除；不漏天气回归/核电保护。
- [x] 原始参考、例外参考、全国候选、固定分区四层不混淆。
- [x] 列出实际修改文件、新文件、接口、起步测试、依赖和验收级别。
- [x] 共享文件串行集成，不让并行agent互相覆盖。
- [x] 没有把现有v2目标不变与原充电优先同时作为无条件承诺。
- [x] 没有把未完成的年度/全周期数值验证写成已通过。
