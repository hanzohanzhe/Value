# VALUE 通用 Module 开发与替换 101

[English version](MODULE_DEVELOPER_101.md)

如果你还没有确定应当换 data pack、Study parameter、module，还是平台 contract，
先读总教程 [`BUILD_YOUR_OWN_MODEL_101_ZH.md`](BUILD_YOUR_OWN_MODEL_101_ZH.md)。

这份手册对应当前仓库真实运行的 `value.module/v2` 与年度
orchestrator。它适用于 PSM、储能成本、扩张上限、投资、规划管线和年度
状态转移，而不是只针对竞价。

本手册只说明如何使用现有模块架构，不要求修改 Scheme C，也不把尚未存在
的扩展点描述成已经可用。

## 1. 最重要的判断：你要改的是数据、参数、module，还是架构？

开始写代码前先做这个判断：

| 研究需求 | 正确入口 | 例子 |
| --- | --- | --- |
| 换一套原始数据或字段映射 | Data pack / data adapter | 新国家天气、需求曲线、成本表、项目库 |
| 改一个已有、已注册的数值假设 | Study parameter | VOLL、随机种子、扩张比例、折现率 |
| 替换年度链中已有的一段算法 | Module | PSM、投资逻辑、planning pipeline、扩张规则 |
| 只改变展示、导出或图表 | 结果转换或前端 | 新 dashboard、CSV、图形 |
| 增加当前年度链中不存在的新阶段 | 架构扩展 | 独立 demand-response 阶段、网络建设阶段、政策市场阶段 |

几个容易混淆的例子：

- **换一个给定的 demand profile**：通常是 data pack/adapter，不是 module。
- **让需求随价格内生响应**：当前没有独立 demand module；应由完整 PSM
  处理，或未来新增正式 contract。
- **增加 DC/AC 潮流约束**：算法属于完整 `psm`，但当前 v2 输入没有 bus、line
  和 nodal demand。必须先增加网络 data roles 与版本化 PSM contract，再把网络
  求解器做成可替换 `psm`；仅上传一个现有 contract 的 ZIP 不够。
- **换碳排放因子**：属于 data pack/科学参数；如果要更换整套碳核算算法，
  当前七个 slot 中没有 carbon-ledger slot，需要单独扩展架构。
- **只改变储能成本回收/报价函数**：使用 `storage_cost`。
- **改变项目成功率、开发阶段与投产规则**：使用 `pipeline`。
- **改变 agent 投资判断**：使用 `investment`。

原则是：**数据进 data pack，数值进 parameter，算法进已有 slot；新阶段不能
伪装成别的 slot。**

## 2. Module 替代的真实原理

VALUE 不是把用户代码复制进 Scheme C，也不是修改原始函数。替代过程是：

```text
module.zip
  -> 安装器验证文件、manifest、入口和契约
  -> 原子安装到用户 VALUE_DATA_HOME/modules
  -> workspace registry 同时加载内置与外部 module
  -> Study 在每个 slot 保存一个 module ID
  -> 启动运行时冻结 module ID、version、contract 和源码 SHA-256
  -> registry 实例化 Study 选中的入口类
  -> orchestrator 在固定生命周期位置调用它
  -> 返回 typed result，进入下一阶段
```

因此“替换”准确地说是：**在一个新 Study revision 中，为某个 slot 选择另一个
实现。**它不会覆盖内置文件，也不会删除旧 module。旧 Study 仍保留原 ID、
版本、参数和哈希，可以回滚或做 A/B 比较。

当前安装器不允许外部包覆盖内置 ID。对已安装 module 原地修改源码（同 ID、
同版本）是允许的，会被记录而不是被拒绝（DECISIONS A16-4）：Check readiness
显示琥珀色警告 `GF_PREFLIGHT_MODULE_SOURCE_CHANGED`，列出安装时和当前的源码
SHA-256；每个 Run 冻结新的源码哈希；Compare 把该 module 的方法标为已改变。
安装记录和 scientific version 不会随之更新，所以打算发布或作为方法对照的修改，
仍应使用新的 module version（或新 ID）、scientific version 和 Python package
名，并以 bundle 安装。

## 3. 年度模型链与调用位置

每个模型年按下面的顺序执行：

```text
YearState(y)
  -> pipeline.advance_year
     投产/失败/延期，形成 OperatingState(y)
  -> psm.run
     形成 MarketYearResult(y)
  -> vre_cap.evaluate + storage_cap.evaluate
     形成 ExpansionHeadroom(y)
  -> investment.decide
     形成 InvestmentDecision(y)
  -> pipeline.admit_projects
     把投资提案放入规划管线
  -> transition.apply
     处理退出与状态结转，形成 YearState(y+1)
```

`storage_cost` 不是额外年度阶段。它只在所选 PSM 声明需要
`storage.bid-cost-function` 时，被注入 offer-based PSM。集中协同优化储能的
PSM 通常声明 `storage.central-cooptimization`，此时不能同时选择 storage-cost
报价 module。

orchestrator 拥有年份循环。第三方 module 只实现自己的阶段，不应自己再循环
十年，也不应启动另一个隐藏脚本。

## 4. 当前七个可替换 slot

| Slot | Contract | 必须提供的方法 | 接收 | 返回 |
| --- | --- | --- | --- | --- |
| `psm` | `value.psm/v2` | `run(model_input)` | `PSMInput` | `MarketYearResult` |
| `storage_cost` | `value.storage-cost/v1` | `create(**parameters)` | 技术和运行参数 | 年度储能报价对象 |
| `vre_cap` | `value.expansion-policy/v2` | `evaluate(run, state, market)` | 运行、在运系统、市场结果 | `ExpansionHeadroom` |
| `storage_cap` | `value.expansion-policy/v2` | `evaluate(run, state, market)` | 同上 | `ExpansionHeadroom` |
| `investment` | `value.investment/v2` | `decide(run, state, market, headroom)` | 市场收入、资产、扩张空间 | `InvestmentDecision` |
| `pipeline` | `value.planning/v2` | `advance_year(...)`, `admit_projects(...)` | 年度状态和投资提案 | `PlanningAdvanceResult`、`PlanningAdmissionResult` |
| `transition` | `value.state-transition/v2` | `apply(run, current_state, planning, investment)` | 本年资产、规划和退出 | 下一年 `YearState` |

`value-module.json` 中的 `contract_version` 必须与上表完全一致。安装器按
`gridform_core/v2/module_manifest.py` 的 `SUPPORTED_CONTRACTS` 核对，其他写法一律拒绝，
包括改名之前的 `gridform.*` 写法；错误代码为 `GF_MODULE_CONTRACT_MISMATCH`，信息例如：
`Module my-module in slot storage_cost uses gridform.storage-cost/v1; expected value.storage-cost/v1`。

权威接口定义：

- `gridform_core/v2/interfaces.py`
- `gridform_core/v2/contracts.py`
- `gridform_core/v2/orchestrator.py`
- `docs/generated/MODULES.md`

不要根据界面标签猜字段，也不要依赖
`gridform_core/builtin/scheme_c_1000twh/compat` 中的私有实现细节。

## 5. 每类 module 可以改什么

### 5.1 `psm`

适合 bid-at-cost、策略报价、unit commitment、economic dispatch、
perfect foresight、储能 SOC、内生需求响应、进口边界和可靠性处理。当前 v2
contract 可直接支持铜板模型；分区/DC/AC 模型在完成总教程所述的网络 contract
升级后，再由完整 `psm` 实现。

```python
class MyPSM:
    id = "my-psm"
    version = "1.0.0"

    def run(self, model_input):
        # PSMInput -> MarketYearResult
        ...
```

必须处理或明确拒绝输入中的需求、资源、储能、blackout 和 terminal-SOC。
返回年份和 `module_id` 必须与输入及入口类一致。

### 5.2 `storage_cost`

适合动态年平均回收、legacy tariff、其他论文报价函数，以及不同技术的循环
折旧、持有成本和利用率假设。

```python
class MyStorageCostDefinition:
    id = "my-storage-cost"
    version = "1.0.0"

    def create(self, **parameters):
        return MyAnnualStorageOffer(**parameters)


class MyAnnualStorageOffer:
    # 构造时初始化；真实 Battery 在 prepare_year 前读取此属性。
    prepared_year = None
    cycle_depreciation_gbp_per_mwh = 0.0
    holding_recovery_gbp_per_mwh_period = 0.0

    def prepare_year(self, year, *, capital_cost_gbp, power_capacity_mw,
                     energy_capacity_mwh, discharge_efficiency):
        ...  # 同年幂等；跨年 previous <- current，current 重置，prepared_year 更新

    def bid_price_gbp_per_mwh(self, dwell_periods):
        ...  # 有限、非负 GBP/MWh

    def record_sale(self, delivered_mwh, dwell_periods):
        ...  # 累计真实送出 MWh 及 MWh*period dwell 观测

    def report(self):
        ...  # 返回可更新的 dict，准确声明 method/prepared_year 和实际年度观测
```

`create()` 收到 `battery_type`、`period_hours` 和 legacy 兼容参数。年度报告
至少包含 `method`、`prepared_year`、`cycle_depreciation_gbp_per_mwh`、
`previous_year_sold_mwh`、`current_year_sold_mwh` 和
`current_year_average_dwell_periods`；两项费用属性必须是有限非负数。
`previous` 观测对象支持 `year`、`sold_energy_mwh` 和
`dwell_weighted_sold_mwh_periods`，供年度 checkpoint 恢复。

完整可执行实现见 `examples/external_module_bundle/src/value_example_flat_offer/plugin.py`。
下载模板仅需把构造参数默认值 `42.0` 改为 `73.0`，同步 manifest 与定义类的
id/version/scientific_version 为新身份，按打包命令生成 ZIP，再安装并在派生 Study
选择新模块。保留全部生命周期方法。报告的 `fixed_offer_gbp_per_mwh` 会显示 73，
`method=experimental_fixed_offer`；零循环/持有兼容字段不代表科学成本分解。
安装检查使用真实 Battery 的准备、报价、非零放电、报告、同年与下一年状态链；
通过只证明运行接线，不证明科学有效性。

### 5.3 `vre_cap` 与 `storage_cap`

适合技术潜力、供应链速度、政策上限，以及基于弃电或利用率的扩张空间。

```python
class MyExpansionPolicy:
    id = "my-expansion-policy"
    version = "1.0.0"

    def evaluate(self, run, state, market):
        return ExpansionHeadroom(
            headroom_id=f"{run.run_id}:{self.id}:{market.year}",
            year=market.year,
            module_id=self.id,
            allowed_additions_mw={"solar": 1000.0},
        )
```

返回值必须是非负、有限 MW。多个 incumbent asset 不能让同一技术年度预算被
重复乘算。

### 5.4 `investment`

适合 NPV、IRR、payback、real options、异质 agent、风险偏好、资本约束、
投资和退出判断。

```python
class MyInvestment:
    id = "my-investment"
    version = "1.0.0"

    def decide(self, run, state, market, headroom):
        return InvestmentDecision(
            decision_id=f"{run.run_id}:investment:{market.year}",
            year=market.year,
            module_id=self.id,
            proposals=(),
            retirements_mw={},
        )
```

proposal 应包含技术、MW、地区、owner/agent、预计投产年，以及让后续 pipeline
建立 CAPEX、FOM、寿命和效率记录的经济信息。

### 5.5 `pipeline`

适合项目阶段、工期、成功率、外部项目库合并、投产/失败/延期，以及
commissioned asset 身份生成。它必须实现两个阶段：

```python
class MyPipeline:
    id = "my-pipeline"
    version = "1.0.0"

    def advance_year(self, run, state):
        # 年初推进旧项目，形成当年 OperatingState
        ...

    def admit_projects(self, run, state, proposals):
        # 年末接受或拒绝本年 investment proposals
        ...
```

不要重复应用成功概率，也不要让投产资产丢失 CAPEX、FOM、寿命、效率、owner
或来源记录。

### 5.6 `transition`

适合退休、容量衰减、残值、累计指标和年界状态结转。

```python
class MyTransition:
    id = "my-transition"
    version = "1.0.0"

    def apply(self, run, current_state, planning, investment):
        return YearState(
            year=current_state.year + 1,
            assets=current_state.assets,
            planning_projects=planning.next_pipeline,
        )
```

年份必须恰好加一，容量不能为负，经济记录应与物理容量同步缩放。

## 6. Module 之间如何连接

连接依靠三层约束：

1. **slot/contract**：module 只能填入 manifest 声明的 slot；
2. **typed result**：上一阶段返回的 dataclass 是下一阶段输入；
3. **capability**：`provides_capabilities` 与 `requires_capabilities` 必须闭合。

```text
PSM provides market.year-result
  -> expansion policies require market.year-result
expansion policies provide expansion.headroom
  -> investment requires expansion.headroom
investment provides investment.proposals
  -> pipeline requires investment.proposals
pipeline provides planning.admission
  -> transition requires planning.admission
```

capability 只证明形式兼容，不证明科学兼容。具体 module 组合仍要做集成测试。

## 7. `module.zip` 的准确格式

它是确定性的 `value.module-bundle/v1`，不是任意 ZIP，也不是 wheel：

```text
my-module.zip
├── force-bundle.json       # 构建器生成的描述文件；不要手写
├── value-module.json       # value.module/v2 manifest
├── LICENSE                 # 必需
├── README.md               # 可选，建议包含方法与引用
└── src/
    └── my_unique_package/
        ├── __init__.py
        └── plugin.py
```

描述文件名 `force-bundle.json` 是 VALUE 改名之前留下的兼容名称（见
[`BRAND_AND_VARIANTS.md`](BRAND_AND_VARIANTS.md)），其 schema 是
`value.module-bundle/v1`；manifest 文件是 `value-module.json`。slot 的 contract ID
**没有**沿用旧名：请使用第 4 节表中的 `value.*` ID（例如 `value.storage-cost/v1`），
写成 `gridform.*` 的包在安装时会被拒绝。

硬性限制：

- 压缩后最多 25 MiB；解压后最多 100 MiB；最多 1,000 个文件；
- 禁止绝对路径、`..`、重复名称、加密文件和符号链接；
- `src/` 至少一个 `.py`；
- 允许 `.py/.pyi/.json/.csv/.txt/.md/.toml/.yaml/.yml`；
- 禁止 `.exe/.dll/.pyd/.so/.bat/.cmd` 等可执行或原生文件；
- 安装器离线运行，不执行 `pip`，不下载依赖；
- 顶层包名不能是 `backend`、`examples`、`gridform_core`、
  `gridform_validation`、`scripts`、`tests`；
- 外部 Python 在 VALUE 进程内执行，没有 OS 沙箱，只安装可信代码。

## 8. `value-module.json` 怎么写

```json
{
  "schema_version": "value.module/v2",
  "id": "my-research-module",
  "name": "My research module",
  "version": "1.0.0",
  "scientific_version": "paper-method-2026-01",
  "slot": "investment",
  "implementation": "my_unique_package.plugin:MyInvestment",
  "contract_version": "value.investment/v2",
  "inputs": ["market.year-result", "expansion.headroom"],
  "outputs": ["investment.proposals", "investment.retirements"],
  "parameters": [],
  "state_reads": ["operating.assets"],
  "state_writes": [],
  "determinism": "deterministic",
  "artifacts": ["investment/decisions.json"],
  "description": "State the method, scope and important assumptions.",
  "status": "ready",
  "selection_required": false,
  "provides_capabilities": ["investment.proposals"],
  "requires_capabilities": ["market.year-result", "expansion.headroom"],
  "units": {
    "market.year-result": "GBP, MWh",
    "expansion.headroom": "MW",
    "investment.proposals": "MW"
  },
  "execution_kind": "live_module"
}
```

字段规则：

- `id`：3–64 位小写字母、数字和连字符，以字母开头；
- `version`：semantic version，例如 `1.2.0`；
- `scientific_version`：论文方法/算法版本；
- `slot` 与 `contract_version` 必须匹配；
- `implementation` 必须是 `src/` 中真实存在的 `package.module:ClassName`；
- `parameters` 只能声明 VALUE 参数注册表中已存在的 ID；
- `units` 的 key 必须已在 inputs、outputs 或 parameters；
- `determinism` 只能是 `deterministic`、`seeded` 或 `stochastic`；
- 外部包必须 `status: ready`、`execution_kind: live_module`。

当前 beta 不能根据第三方 manifest 自动生成新的 Advanced Settings 参数控件。
新参数若要出现在界面，应单独进入参数注册表和前端，不能让 module 偷读本地 JSON。

## 9. 从零编写的标准流程

1. **界定 slot**：写清“只替代哪一阶段、读什么、返回什么、不改变什么”。
2. **复制参考**：`external_module_bundle` 是 storage-cost 示例，
   `external_psm_bundle` 是 PSM 示例，`external_modules` 是其余 slot 的测试夹具。
3. **全部更名**：ID、package、类、version、scientific version 和说明。
4. **只依赖公开 contract**：优先导入 `gridform_core.v2.contracts/interfaces`。
5. **先写最小 fixture**：手算输入输出，验证 ID、year、单位和边界。
6. **填写 manifest/README**：记录方法、数学式、输入输出、随机性、来源和限制。
7. **构建确定性 ZIP**：使用官方 builder。
8. **安装与校验**：在 Modules 页面安装，不覆盖旧 module。
9. **克隆基线 Study**：只更换目标 slot，形成新 revision。
10. **从短到长测试**：前一层未通过时不跑下一层。

构建命令：

```powershell
py -3.10 scripts\build_module_bundle.py `
  --manifest path\to\value-module.json `
  --source-root path\to\src `
  --license path\to\LICENSE `
  --readme path\to\README.md `
  --output work\my-module.zip
```

## 10. 通用测试流程

### Level 0：源码和包结构

- 语法/import/类型检查；manifest schema、semver、slot/contract、units；
- ZIP 路径、类型、哈希、大小；两次构建产生相同 bytes。

### Level 1：contract 单元测试

- 必需方法存在；最小 typed fixture 返回正确 dataclass；
- module ID/version/year 一致；输入不被意外修改；结果可序列化和哈希。

安装成功主要证明接线，不证明科学正确。

### Level 2：边界与失败测试

覆盖零值、空列表、极小/极大值、未知技术、缺字段、NaN、负值、重复 ID 和
不兼容 capability。人为破坏核心约束时，测试必须失败。

### Level 3：跨 module 兼容测试

- 上下游 contract 与 capability 闭合；缺能力时 fail closed；
- 其余 slot 仍为 Study 声明实现；resolution graph/stage events 记录真实 hash；
- 不读取未声明的全局 config 或绝对路径。

### Level 4：两期 wiring smoke

- 真实新 module 被调用，无 fallback；
- 年度链走到下一年 state；结果工件/checkpoint 能生成；
- 只证明接线，不解释年度经济学。

### Level 5：领域短测试

| Slot | 最低领域测试 |
| --- | --- |
| `psm` | 手算 merit order；24h/168h；供需平衡；弃电；进口；blackout；SOC/效率/MW/MWh/terminal；成本与支付分账 |
| `storage_cost` | 首年初始化；上一年零/低/正常售电；dwell；battery 循环折旧；pumped hydro 无循环折旧；非法值拒绝 |
| `vre_cap` / `storage_cap` | 非负有限 headroom；技术映射；多资产不重复放大预算；零 dispatch/excess |
| `investment` | 多资产同 owner；多个 owner 共用 cap；利润/退出边界；proposal 携带 CAPEX/FOM/寿命/owner |
| `pipeline` | seed 重放；概率只应用一次；commission/fail/defer；投产资产身份完整 |
| `transition` | 年份加一；无负容量；retirement 同步缩放经济记录；pipeline/累计状态不丢失 |

### Level 6：一年 full run

17,520 个半小时 period；检查物理、成本、碳、规划账本、目标行为、性能、内存、
磁盘和结果规模。

### Level 7：两年 CEM–PSM 耦合

验证投资提案进入 pipeline、到期项目投产、新资产的容量/CAPEX/FOM/寿命/owner
进入第二年，以及 retirement、storage observations、checkpoint 正确结转。

### Level 8：多年与十年

只在 module 影响跨年状态时必需。比较逐年容量、成本、碳、弃电、blackout、
pipeline、seed 重放、振荡/fallback/数值爆炸和 checkpoint 恢复一致性。

### Level 9：独立验证和发布审计

若声称最优、等价或论文复现，增加独立实现/oracle，并保存 ZIP/hash、manifest、
license、fixture、报告、data revision、Study、参数、seed、Python/依赖和已知限制。

## 11. 所有 module 的统一通过门槛

- 不修改 Scheme C retained source；
- 不依赖作者电脑绝对路径或隐藏 fallback；
- 不产生 NaN、无穷、非法负值；
- 随机方法可按 seed 重放；
- contract、manifest、代码和输出单位一致；
- 报告实际 ID/version/source hash；
- 新 Study 可与旧 Study 做单变量 A/B 并随时回滚；
- 失败时给出可操作错误，不静默改变科学假设。

PSM 必须区分：

```text
offer price       -> 市场行为
market payment    -> 结算与 agent 收入
physical cost     -> 燃料、VOM、退化和可靠性成本
capital + FOM     -> 已投产资产年度资源成本
```

若输出 `physical_operating_cost_components_gbp`，分项必须对上 typed operational
total。Inspect 若要逐笔重放，还需兼容的出清前 inputs、outcomes 和 orders；只有
period summary 时不能声称完整 auction replay。

## 12. 安装、替换与回滚

### 安装

ZIP 在 staging 中通过验证后，才原子保存 module/version、安装记录、bundle hash
和 source hash。

### 替换

1. 新实现使用新 ID/version；
2. 安装新 ZIP；
3. 克隆基线 Study；
4. 只替换目标 slot；
5. 逐层测试并比较 provenance。

### 回滚

运行旧 Study revision，或重新选择旧 module。不要覆盖源码来“回滚”。

### 禁用

启用/禁用只影响 registry 可见性，不会自动修改 Study。存在 Study 引用时不应
禁用；禁用也不应删除历史源码和运行记录。

### 隔离

内置 module 出错仍然直接失败（fail-closed）。本地清单读不了、实现导入时抛出
任何异常（包括 `SystemExit`）、本地条目之间 ID 或命名空间重复时，该条目被隔离：
不注册，`/api/health` 变为 `degraded`，只有选中它的 Study 会被拒绝。互相冲突的
本地条目全部隔离，不设隐式赢家；与内置 ID 或命名空间冲突时只隔离本地那一条。
被 Study 引用的隔离条目也可以停用，只有引用它的活动 Run 会阻止停用。

### 安装与启用后的校验

冲突在写盘前就被拒绝；写盘后先在进程内、再在一个与 worker 启动方式相同的新
Python 进程中重建注册表，任一层拒绝都会逐字节回滚。导入失败的结果会被记住，
点 **Rescan**（Modules 页顶部，以及每个停用或隔离条目上都有）才会重试；
**Enable** 会先清除记住的失败，所以它报告的总是一次新扫描的结果。**Rescan**
还会重新导入所有已安装的 module 和每个已启用扩展的钩子，所以原地修改把一个已加载的
module 或扩展钩子改坏时，它会立即被隔离，而不是等到下一次 Check readiness、Run 或重启。

扩展在 Run 中被记录的输出只有两类：`initialize` 返回的状态（存放在扩展命名空间下）和
`after_psm` 返回的产物（每个模型年一组，在 Inspect 中显示）。`preflight`、`before_psm`、
`before_cem`、`after_cem`、`transition`、`finalize` 照常在各自位置运行，但返回值不记录；
从这些钩子返回声明过的产物（带 `artifact_type`）会使 Run 报错并指明钩子，而不是被静默丢弃。

### 停用与隔离区

Modules 页在 module 列表下方列出所有停用或隔离的本地 module 和扩展，每项都有
**Enable**、**Rescan** 和 **Remove**。选用了其中某项的 Study 做 Check readiness 时，
会显示阻断错误并禁用 Run 按钮。**Remove** 经确认后，把安装目录和清单移到
`modules/disabled-manifests/removed/<modules|extensions>/<id>/`，不删除任何文件。
已启用且正常的条目要先停用才能移除；被保存的 Study、活动 Run 或（扩展的）
保留运行记录引用的条目不能移除。

同一 ID 安装期间一直被占用（即使已停用）。修好源码后可以原地修复再 Enable 或
Rescan（按第 2 节记录），也可以先 Remove 再安装修好的 bundle；要发布的方法改动
应使用新版本。

### 离线自救

`module_recovery list`、`disable module|extension <id>`、
`park-manifest module|extension <file>`、`park-installation module|extension <id> [<version>]`
（安装记录损坏时）只读写安装器的文件，不导入任何已安装代码；`verify` 按新 worker
的方式构建注册表。VALUE 正在使用该数据目录时，这些命令会拒绝执行（`--force` 可
覆盖），请改用 Modules 页。源码检出中运行 `python -B -m gridform_core.module_recovery ...`；
安装版须用自带解释器，命令见用户指南“离线模块自救（Offline module recovery）”。

### 修改内置 module（方法升级）

内置 module 在 VALUE 源码树中（`gridform_core/`；保留的 Scheme C 内核在
`gridform_core/builtin/scheme_c_1000twh/runtime_compat/`）。改变内置 module 的计算
方式属于方法改动，不能原地静默修改：

1. 修改代码。只应在一个方法学口径中生效的改动，要在
   `gridform_core/data/methodology/corrections/` 中用 correction id 开关；
   不得修改保留的 `compat/` 目录。
2. 同时提高 manifest（`gridform_core/manifests/<id>.json`）和实现类中的版本号。
3. 在 `docs/release/VERSION_LEDGER.json` 追加一条 bump（`from`、`to`、`package`、
   `correction_ids`、`reason`、`requires_user_opt_in`）。`true` 表示已保存的 Study
   运行前要在界面中明确确认方法升级，`false` 只用于纯代码改动。每个 correction id
   都必须已登记：在 `gridform_core/data/methodology/corrections/` 中，或列在
   `CHANGELOG.md` 的 “Correction ids” 表中。用
   `python -B scripts/check_version_ledger.py` 检查；未登记（例如拼错）的 id 会报错，
   因为它会原样出现在用户看到的确认框里。
4. 改动 `runtime_compat/` 之后必须登记：
   `python -B scripts/seal_runtime_overlay.py --correction <id>`（使用该 bump 的 id；
   未登记的 id 会被拒绝）。登记之前，
   Check readiness 以 `GF_PREFLIGHT_RUNTIME_OVERLAY_UNSEALED` 拒绝所有 Run；
   经 API 启动的 Run 会以 `GF_COMPATIBILITY_001` 停止。
5. 重新生成 `docs/generated/` 并运行测试；数值变化要在同一 correction id 下修订
   golden。

## 13. 常见失败

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| implementation module is missing | ZIP 多一层或 entry point 错 | 对照 `package.module:Class` |
| built-in/package collision | 内置 ID 或保留包名 | 换新 ID/package |
| undeclared parameter IDs | 参数未注册 | 注册参数或改用 data role |
| missing capability | 上下游能力不闭合 | 检查 provides/requires |
| Study 没有 module | 安装失败、disabled、非 ready 或 slot 错 | 看安装报告 |
| wrong year/module | 返回 ID/year 不一致 | 修正 typed result |
| cost ledger failed | 成本分项与 total 不符 | 分开物理成本和结算 |
| 新资产第二年未进入 PSM | pipeline/transition 丢资产 | 查两年 coupling |
| 新资产缺 CAPEX/FOM | proposal/pipeline 丢经济身份 | 查 commissioned record |
| 能跑但方法没变化 | Study 仍选旧 ID 或 fallback | 查 resolution/events |
| Inspect 缺细节 | module 未输出 artifact | 实现格式或诚实声明缺失 |

## 14. 当前架构的明确限制

1. 只支持本手册列出的七个 slot；新生命周期阶段仍需修改核心架构。
2. 当前没有独立 `bid_strategy`、`demand_profile`、`carbon_accounting` 或
   `network_expansion` slot。
3. 第三方 manifest 不能自动注册新的 Advanced Settings 参数。
4. 安装器不执行 `pip`；只能用已有依赖或随包纯源码。
5. 外部代码同进程执行，没有安全沙箱。
6. conformance 不证明科学正确。
7. contract 兼容不代表所有 module 组合科学兼容。

这些限制说明哪些扩展已能即插即用，哪些仍需正式架构设计。

## 15. 作者发布前一页清单

- [ ] 选择正确 slot；没有合适 slot 时没有伪装到别处。
- [ ] 未修改 Scheme C，未依赖私有 compatibility 全局变量。
- [ ] ID、package、version、scientific version 新且稳定。
- [ ] 只使用公开 typed contract，单位清楚。
- [ ] manifest 与代码的 inputs/outputs/parameters/units/capabilities 一致。
- [ ] README 说明方法、数据、假设、随机性、限制、license 和引用。
- [ ] ZIP 由 builder 生成，两次构建相同。
- [ ] 最小、失败和跨 module fixture 通过。
- [ ] 两期 wiring 证明真实入口被调用，无 fallback。
- [ ] 按 slot 完成短期、一年、两年或十年测试。
- [ ] 账本、checkpoint、module/source/data hashes 可审计。
- [ ] 新 Study 与基线只改变目标变量，并且可回滚。

最终用户不需要会编程即可安装、选择、运行和比较已经打包好的 module；但编写
新的科学 module 本身仍是 Python 软件开发和领域验证工作。
