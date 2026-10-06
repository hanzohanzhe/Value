# 基于 FORCE 构建你自己的电力系统模型 101

[English version](BUILD_YOUR_OWN_MODEL_101.md)

这是一份从“我有自己的数据或方法”走到“我有一个可运行、可审计、可复现的
FORCE 衍生模型”的总教程。它面向研究者和模型开发者，不要求先理解 Scheme C
的私有实现。

如果你只想写一个具体 module，请继续阅读
[`MODULE_DEVELOPER_101_ZH.md`](MODULE_DEVELOPER_101_ZH.md)。本教程负责决定该换
数据、参数、module，还是升级平台；Module 101 负责 `module.zip` 的代码、manifest
和测试细节。

## 1. 先理解：FORCE 模型不是一个 Python 文件

一次可复现的 FORCE 研究由五部分共同定义：

```text
模型身份
  = FORCE 平台与 contract 版本
  + data-pack revision 与每个对象的 SHA-256
  + Study 年份、科学参数与 revision
  + 七个 slot 的 module ID、版本与源码哈希
  + （如有）经过版本化的平台 contract 扩展
```

前端不是另一个简化模型。网页与命令行把同一个冻结的 Study 交给同一个
application service、module registry 和年度 orchestrator。Study 是把数据、参数和
module 组装起来的运行配方；它不会拥有或修改原始数据库，也不会把 module 源码
复制进 Scheme C。

## 2. 一套数据底座，加三种深度的替换/升级

在 FORCE 上构建自己的模型时，先连接数据；随后按研究变化的深度选择下面三种
机制。不要把所有改动都写成 module。

| 层级 | 适用变化 | 是否写 Python | 是否改变生命周期或输入维度 |
| --- | --- | ---: | ---: |
| 数据底座：换 data pack | 同一种语义，换国家、年份或数据库 | adapter 可能需要 | 否 |
| 方式一：换 Study 参数 | 算法不变，只换已注册的科学假设 | 否 | 否 |
| 方式二：换现有 slot 的 module | 生命周期位置不变，替换该段算法 | 是 | 否 |
| 方式三：升级平台 contract | 新数据维度、新状态或新生命周期阶段 | 是 | 是 |

最短判断规则：

```text
同一字段，换数值或来源？       -> data pack
同一算法，换已注册假设？       -> Study parameter
同一生命周期位置，换计算方法？ -> module
需要新的输入维度、状态或阶段？ -> platform contract upgrade
```

### 例子

| 研究需求 | 正确入口 |
| --- | --- |
| 换成德国的半小时 demand、天气和电站表 | data pack / adapter |
| 换一个给定的 demand profile | data pack；必要时写 adapter |
| 调整 VOLL、折现率、规划成功率或随机种子 | Study parameter |
| 换储能报价函数 | `storage_cost` module |
| 换竞价、出清或 UC 算法 | `psm` module |
| 换投资 agent、项目管线或年度状态转移 | 对应 CEM module |
| 七段算法全部换掉，但仍使用现有年度链和 typed contracts | 同时安装并选择七个 module |
| 给需求增加价格弹性，但仍在 PSM 内联合求解 | 完整 `psm`；若需新输入字段，先升级 contract |
| 增加 bus、line、nodal demand 和 DC/AC 潮流 | 先升级网络 data roles/PSM contract，再接网络 PSM |
| 增加内生输电投资、审批和投产 | 平台升级；还需网络资产、投资、pipeline 和 transition 契约 |
| 换整个碳核算方法 | 当前没有 carbon-ledger slot，需要平台升级 |

## 3. 数据底座：用自己的数据库替换现有数据

### 3.1 Data pack 管什么

Data pack 是有版本、可校验的数据清单。它把来源专用文件映射到稳定的 semantic
role，而不是让模型代码依赖某个人桌面上的绝对路径。当前 v2 有 25 个必需角色：

- PSM：现有发电机组、预测/实际需求、风/光天气，以及法国、比利时、荷兰、
  挪威和爱尔兰的互联线可用量（正值为进口容量，负值为出口能力）与价格；
- CEM：太阳能、陆上风、海上风 profile，标准化和原始 REPD 项目，资本成本、
  policy/support、规划时间、规划成功率和模型参数。

权威角色、允许格式和单位定义在 `gridform_core/dataset_slots.py` 的 `DATASET_SLOTS`（`gridform_core/catalog.py` 原样转出），
前端 **Data** 页面由同一清单生成。不要只根据文件名猜用途。

### 3.2 每个 binding 至少应声明

- semantic role；
- data-pack 内的相对 URI；
- CSV、Parquet、NetCDF、Zarr、JSON、XLSX 等允许格式；
- 单位、时区、时间分辨率、货币基年和技术代码映射；
- 来源机构、下载日期、许可、attribution 与转换说明；
- 文件或规范化对象的 SHA-256。

### 3.3 换数据的标准流程

1. 复制合成 data pack 模板或建立新的 manifest，使用新的 pack ID 和 revision。
2. 保留原始文件；在 adapter 边界完成重命名、单位和技术分类转换。
3. 把输出绑定到 25 个稳定 role，使用 pack 内相对路径。
4. 验证时序长度、唯一键、缺失值、单位、容量非负、年份覆盖和 checksum。
5. 在 **Data** 页面确认 `25/25 inputs ready`。
6. 新建 Study 并选择该 pack；不要回写旧 Study revision。
7. 依次运行两期 wiring、两年 smoke 和完整年度测试。

CSV/SQL/API 只是来源格式。PSM/CEM 接收的是 adapter 规范化后的对象；不要把
数据库连接、作者电脑路径或来源专用列名写进科学 module。

### 3.4 数据替换的边界

更换值和来源不等于增加新输入维度。当前 25 个角色没有 buses、branches、
transformers、asset-to-bus mapping 或 nodal demand。即使把这些文件放进 pack，
当前 canonical adapter 也不会把它们传给 `PSMInput`。这种需求必须走方式三，先
增加正式 data roles 和 typed contract。

## 4. 方式一：在 Study 中替换参数和情景假设

这种方式适合算法完全不变的敏感性分析。用户在 **Studies** 中选择 data pack、
年份和 module，然后在基础或 Advanced settings 中修改已经注册的科学参数。

适合的例子包括：

- VOLL、折现率和成本基年；
- planning success mode、随机种子、僵尸项目过滤、最小项目规模；
- expansion headroom、储能利用率 floor 或平滑窗口；
- terminal policy、碳因子情景和输出粒度。

原则：

1. 只有参数 registry 中的键才能作为可信 Study override；不要用隐藏环境变量。
2. 单位、默认值、范围和科学含义必须登记并在运行前解析。
3. 每次保存生成 append-only Study revision；旧 revision 不被覆盖。
4. 运行冻结最终有效值和每个值的来源，便于 A/B 比较。
5. 如果一个“参数”改变了输入结构、返回结构或调用顺序，它其实是 module 或
   platform upgrade。

这一路径不需要 `module.zip`。复制一个 Study，修改一个变量，保持其余身份相同，
是最清楚的敏感性实验方式。

## 5. 方式二：替换年度链中已有的 module

### 5.1 七个公开 slot

```text
YearState(y)
  -> pipeline.advance_year
  -> psm.run
  -> vre_cap.evaluate + storage_cap.evaluate
  -> investment.decide
  -> pipeline.admit_projects
  -> transition.apply
  -> YearState(y+1)
```

| Slot | 用途 |
| --- | --- |
| `psm` | 需求与资源的逐期出清、报价、储能状态和可靠性 |
| `storage_cost` | offer-based PSM 使用的年度储能成本/报价函数 |
| `vre_cap` | 风光年度扩张空间 |
| `storage_cap` | 储能年度扩张空间 |
| `investment` | economic owner 的投资提案逻辑 |
| `pipeline` | 项目进入、成功、失败、延期与投产 |
| `transition` | 退出、结转和下一年系统状态 |

这不是只允许改 agent 策略的“装饰性插件”。研究者可以只换一个 slot，也可以在
同一个 Study 中把七个 slot 全部换成自己的实现。只要返回值遵守 typed contract，
下一段就会收到前一段的真实结果。

但“七个都可替换”仍有明确边界：年度调用顺序、现有输入维度、共享状态、成本/
碳账本和结果契约仍由平台定义。全替换得到的是“在 FORCE 生命周期内的全新模型”，
不是允许任意函数签名和任意生命周期的通用脚本启动器。

### 5.2 `module.zip` 是什么

它是一个 `force.module-bundle/v1` 安装包，至少包括：

```text
my-module.zip
  bundle.json              # 精确文件清单和每个文件的 SHA-256
  module/
    module.json            # gridform.module/v2 manifest
    LICENSE
    METHOD.md              # 推荐：方程、假设和验证边界
    my_package/
      __init__.py
      implementation.py    # manifest 指向的入口类
```

安装器验证路径、哈希、manifest、入口、slot/contract 和 callable conformance，
然后原子安装到本地 module registry。它不执行 `pip`，不下载依赖，也不接受 native
binary。外部代码仍在 FORCE Python 进程内运行；conformance 证明接线正确，不证明
科学方法正确。

精确字段、七类入口模板、打包命令和测试示例见
[`MODULE_DEVELOPER_101_ZH.md`](MODULE_DEVELOPER_101_ZH.md)。

### 5.3 用户操作

1. 开发者给 module 新的稳定 ID、semantic/scientific version 和 package 名。
2. 完成 unit、contract 和 deterministic fixture 测试。
3. 在 **Modules → Install a model module** 上传并审查 ZIP。
4. 在 **Studies** 复制一个 Study revision，在对应下拉框选择新 module。
5. 先运行 two-period wiring；再运行 two-year smoke、完整年度和所需的多年测试。
6. 在 **Runs** 比较旧/新 Study；在 **Inspect** 检查逐期出清、弃电和 planning。

## 6. 方式三：升级平台 contract 或生命周期

当研究方法需要现有 contracts 没有的数据、状态或阶段时，不应把新内容塞进
`extensions`、全局变量或其他 slot。应该把它作为一个显式、版本化的平台升级。

### 6.1 什么时候必须升级平台

- 新输入维度：bus、branch、nodal load、reserve zone、fuel network；
- 新跨年状态：输电资产、退役队列、政策义务、燃料库存；
- 新生命周期阶段：输电扩张、容量市场、独立需求响应、碳市场；
- 新公共输出：节点电价、线路潮流、无功、约束影子价；
- 现有 typed output 无法无损表达科学结果。

### 6.2 正确的升级顺序

1. 写 extension proposal：科学问题、方程、输入、输出、状态所有权和兼容边界。
2. 为新数据定义 semantic roles、schema、单位、时间/空间索引和 provenance。
3. 新建版本化 contract，例如 `gridform.network-psm/v1`，不要静默改写 v2 含义。
4. 修改 canonical adapter，使新输入被验证、冻结并传入 module。
5. 声明 module capability 与兼容规则；不兼容的 Study 在 preflight 失败。
6. 如有新阶段，更新 orchestrator、checkpoint、state transition 和 module registry。
7. 扩展结果 schema、SQLite/JSON 工件、Inspect 页面和比较器。
8. 提供旧 Study migration 或明确保持旧 contract 可运行。
9. 通过旧模型回归、新 contract conformance、分析算例和多年状态测试。
10. 发布新的平台版本；从此后，同一 contract 下的算法才可以用普通 module ZIP
    丝滑替换。

### 6.3 DC/AC transmission 的具体路线

英国基线仍是单节点模型，但 0.6 扩展线已经并行提供 solver-neutral network
contract。它以条件角色加入 buses、branches、asset-to-bus mapping 和 nodal demand，
不会迁移旧 Study。因此：

```text
只做带线路约束的逐期出清
  = network data roles + typed network PSM contract + canonical adapter
  + DC 或 AC PSM module + 网络结果/验证

还要让 CEM 投资输电
  = 上述全部
  + 网络资产 YearState
  + 带位置的 InvestmentProposal
  + network planning / expansion policy
  + commissioning 和 transition
```

当前 reference contract 已提供：

- `force.network.buses`、`force.network.branches`；
- `force.network.asset-map`、`force.network.nodal-demand`；
- DC 的角度、线路限额、KCL/KVL、拥塞和节点价格输出；
- AC 的电压、无功、损耗、tap 和收敛状态；
- `network.single-node`、`network.dc/v1`、`network.ac/v1` capability。

reference DC 模块已经通过 2/3-bus、24/168 小时、随机、孤岛和故障注入测试。
实验性 AC 模块只检查给定有功计划的局部可行性，不是 AC OPF。替换求解器仍须
给出自己的独立验证；现有单节点 Study 继续使用旧 contract，不能因网络升级而
改变历史结果。

## 7. 四种典型衍生模型怎么组装

### A. 换一个国家，但继续做单节点模型

```text
新 data pack + adapter
  -> 现有 modules
  -> 新 Study parameters
  -> wiring -> annual -> multi-year
```

### B. 保留 PSM，研究新的投资理论

```text
现有或新 data pack
  -> 新 investment.zip
  -> 必要时新 pipeline.zip
  -> 新 Study revision
  -> 两年状态注入测试 -> 多年路径
```

### C. 在现有年度框架内全方位替换

```text
自己的 data pack
  + psm/storage_cost/vre_cap/storage_cap/investment/pipeline/transition modules
  + 自己的 Study 参数
  -> FORCE orchestrator、账本、checkpoint、比较和 Inspect
```

这是一套真正不同的模型，但它主动复用了 FORCE 的生命周期和公共契约。

### D. 建立带 transmission expansion 的网络模型

```text
force-network-contract-extension
  + 网络 data pack roles
  + 替换型或 reference network PSM module
  + 可选 force-network-expansion-extension
  + network-expansion module
  + 网络结果页面与验证套件
```

0.6 扩展线已经发布 solver-neutral network contract。这里仍然是两类安装包：
`force.extension-bundle/v1` 声明数据角色和 capability，
`force.module-bundle/v1` 提供求解器或生命周期实现。一个普通 module ZIP 不能
暗中发明数据角色或改写核心 contract。

## 8. 推荐的衍生研究项目目录

不要把所有内容混成一个不透明 ZIP。推荐把来源、可执行代码和研究配方分开：

```text
my-force-model/
  MODEL_CARD.md
  CITATION.cff
  LICENSES/
  data-pack/
    manifest.json
    SOURCE_REGISTER.md
  modules/
    my-psm-1.0.0.zip
    my-investment-1.0.0.zip
  studies/
    baseline.study.json
    sensitivity.study.json
  validation/
    fixtures/
    expected-results/
    TEST_REPORT.md
```

data pack、module 和 Study 分别安装/导入，最后由 Study 组合。这样用户可以只升级
一个部件，审稿人也能分辨“换了数据”还是“换了算法”。

## 9. 与改动深度匹配的测试门槛

| 改动 | 最低测试 |
| --- | --- |
| data pack | schema、单位、checksum、年份覆盖、时序对齐、两期 wiring |
| Study parameter | 类型/范围、effective value/source、单变量 A/B |
| module | unit、contract conformance、wiring、年度；涉及状态时至少两年 |
| 七 module 全替换 | 全链 integration、账本、checkpoint/replay、年度和多年 |
| platform contract | 旧 contract 回归、migration、能力协商、分析算例、故障注入 |

运行层级不要混淆：

- two-period verification 只证明接线和工件；
- two-year smoke 只证明跨年调用，不代表年度经济学；
- full annual 才能评价 17,520 个半小时的年度结果；
- multi-year 才能评价 CEM 路径和状态继承；
- 新算法还需要独立 benchmark、解析解或外部 solver oracle。

## 10. 版本、审计与发布

每个结果至少应冻结并保存：

- FORCE 平台、API 和 contract schema 版本；
- Study ID、revision、年份和 effective parameters；
- data-pack ID/revision、binding 和对象 SHA-256；
- module ID、version、scientific version、source SHA-256 和 capability；
- resolved module graph、初始状态和逐年 state hash；
- 成本/碳定义、terminal policy、随机种子和 solver 身份；
- validation report、运行工件和许可证。

发布衍生模型时，提供 `MODEL_CARD.md`，明确写出：研究问题、相对 FORCE 基线改了
哪一层、哪些能力未实现、数据再分发权、测试范围和允许的科学结论。不能用 smoke
test 宣称完成年度验证，也不能把“安装成功”写成“科学正确”。

## 11. 最终发布检查表

- [ ] 我能用一句话说明这次变化属于 data、parameter、module 还是 platform。
- [ ] 数据使用相对路径，来源、许可、转换和 SHA-256 齐全。
- [ ] 没有直接修改 Scheme C compatibility kernel 或覆盖内置 module ID。
- [ ] 每个新 module 都有 manifest、LICENSE、方法说明和 conformance 结果。
- [ ] Study revision 冻结了有效参数、module graph 和数据身份。
- [ ] 涉及跨年状态的变化至少通过两年测试。
- [ ] 年度或多年科学结论来自相应长度的完整运行。
- [ ] 新输入维度/阶段使用版本化 contract，而不是隐藏字段或全局变量。
- [ ] 旧 contract 与旧 Study 的兼容或 migration 行为已有测试。
- [ ] 模型卡准确区分软件可运行、数值验证和科学基线。

## 12. 下一步阅读

- 具体 module 代码、manifest、ZIP 和测试：
  [`MODULE_DEVELOPER_101_ZH.md`](MODULE_DEVELOPER_101_ZH.md)
- 前端每个栏目和运行方法：[`USER_GUIDE_ZH.md`](USER_GUIDE_ZH.md)
- 当前方程与不支持范围：[`MATHEMATICAL_REFERENCE.md`](MATHEMATICAL_REFERENCE.md)
- 安装：[`INSTALLATION.md`](INSTALLATION.md)
- 验证与可声明结论：[`VALIDATION_AND_CLAIMS.md`](VALIDATION_AND_CLAIMS.md)
