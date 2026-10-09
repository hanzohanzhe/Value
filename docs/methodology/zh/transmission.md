# 传输与网络约束

## 分区再调度的空间表示

分区再调度在全国日前计划上加入空间约束。每个半小时接纳上调与下调报价，使最终注入满足分区需求、走廊容量和地理边界限额。无损运输表示通过守恒与容量约束确定流量。23 区配置与 11 区实验采用这一表示，直流调度与交流可行性采用下述独立方法。网络模块在修正口径下使用具备相应资格的数据包。

需求按案例指定的空间规则分配。`align_zonal_demand` 在 23 区研究中保留网络包的分区份额，并缩放至全国情景需求。数组 `aligned`、`output_real`、`network_demand_mwh_by_zone` 和 `network_national_mwh` 均为 MWh，区域和时段下标为 \(z,t\)：

$$
\begin{aligned}
\mathrm{scale}_t&=\frac{\mathrm{output\_real}_t}{\mathrm{network\_national\_mwh}_t},\\
\mathrm{aligned}_{z,t}&=\mathrm{network\_demand\_mwh\_by\_zone}_{z,t}\cdot \mathrm{scale}_t.
\end{aligned}
$$

最后一个分区取全国需求减去前面各区已分配量，以保持总量守恒。11 区实验采用网络数据的绝对需求，并保留基础序列的预测需求与实际需求之比：

$$
\begin{aligned}
\mathrm{output\_real}_t&=\mathrm{network\_national\_mwh}_t,\\
\mathrm{output\_forecast}_t&=\mathrm{output\_real}_t\cdot
\frac{\mathrm{research\_forecast\_mwh}_t}{\mathrm{research\_real\_mwh}_t}.
\end{aligned}
$$

分母为零而目标需求为正时，输入检查报错。输出 `demand_mwh_by_zone` 与资产位置、实际可用率、互联线进出口限额一起进入 `build_single_period_problem`。

## 调整目标与运行约束

再调度依次求解四个线性目标：包含缺电费用的报价支出、调整电量、加权物理吞吐和固定变量顺序。`SinglePeriodProblem` 将目标系数数组记为 `primary_objective`、`secondary_objective`、`physical_tie_objective` 和 `stable_tie_objective`。各目标值为对应数组与期间决策向量 `values` 的内积，后者由 `solve_lexicographic` 返回。

决策向量采用实现中的变量标签。`bid:<bid_id>` 为非负接纳报价电量，`flow:<corridor_id>` 为带方向走廊电量，`load-shedding:<zone_id>` 为未满足需求，`storage-charge:<asset_id>` 与 `storage-discharge:<asset_id>` 为电网侧充放电量，`absolute-flow:<corridor_id>` 限制走廊绝对流量，单位均为 MWh。公式的数组下标保留这些已有标识。

第一目标按报价方向计算支出。上调量乘 `price_gbp_per_mwh`，下调量取该乘积的相反数；缺电量乘 `voll_gbp_per_mwh`，默认值为 17,000 GBP/MWh：

$$
\begin{aligned}
\mathrm{primary\_objective}^{\mathsf T}\cdot\mathrm{values}={}&
\sum_{k:\mathrm{direction}=\mathrm{up}}
\mathrm{price\_gbp\_per\_mwh}_k\cdot \mathrm{values}_{\mathrm{bid}:k}\\
&-\sum_{k:\mathrm{direction}=\mathrm{down}}
\mathrm{price\_gbp\_per\_mwh}_k\cdot \mathrm{values}_{\mathrm{bid}:k}\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot
\sum_z\mathrm{values}_{\mathrm{load\mbox{-}shedding}:z}.
\end{aligned}
$$

第二目标合计接纳报价电量与缺电量。第三目标对充电、放电和走廊绝对电量赋权 1，再加非储能下调报价的类别权重。`physical_dec_weight` 提供下表权重，`bid_dec_rank` 选择类别：

|下调类别|权重|
|---|---:|
|燃料机组不停机段|0|
|进口|0.5|
|径流水电|2|
|风电和光伏|3|
|燃料机组停机段|3.5|
|核电|4|
|短于最小停机时间的燃料机组停机段|5|

同一区域内，第一目标价格完全相同时，储能充电先于径流水电、风光及核电下调；燃料机组停机段位于风光之后、核电之前。跨区时，类别权重同时与走廊流量竞争。第一目标采用原始价格，无网络平衡按 0.01 GBP/MWh 分档排列下调价格。第四目标按报价、走廊、区域和储能标识的固定顺序，依次给变量赋权 1、2、……。

资产最终注入等于日前计划加接纳的带方向调整。`final_dispatch_mwh_by_asset` 与 `schedule_mwh_by_asset` 均为 MWh。索引 \(k\) 表示报价，其 `asset_id` 指定资产 \(a\)，`asset_zone_id_by_asset` 指定分区 \(z\)：

$$
\begin{aligned}
\mathrm{final\_dispatch\_mwh\_by\_asset}_a={}&
\mathrm{schedule\_mwh\_by\_asset}_a\\
&+\sum_{k:\mathrm{asset\_id}_k=a,\ \mathrm{direction}=\mathrm{up}}\mathrm{values}_{\mathrm{bid}:k}\\
&-\sum_{k:\mathrm{asset\_id}_k=a,\ \mathrm{direction}=\mathrm{down}}\mathrm{values}_{\mathrm{bid}:k}.
\end{aligned}
$$

分区守恒要求最终供给和流入满足需求及流出。走廊方向由 `from_zone_id` 与 `to_zone_id` 定义：

$$
\begin{aligned}
&\sum_{a:\mathrm{asset\_zone\_id\_by\_asset}_a=z}\mathrm{final\_dispatch\_mwh\_by\_asset}_a
+\mathrm{values}_{\mathrm{load\mbox{-}shedding}:z}\\
&\quad+\sum_{l:\mathrm{to\_zone\_id}=z}\mathrm{values}_{\mathrm{flow}:l}
=\mathrm{demand\_mwh\_by\_zone}_z
+\sum_{l:\mathrm{from\_zone\_id}=z}\mathrm{values}_{\mathrm{flow}:l}.
\end{aligned}
$$

报价接纳量位于零与 `bid_capacity` 之间，MW 报价乘 `period_hours = 0.5` 后成为期间电量。缺电量介于零与分区需求之间。发电注入介于零与 `realised_availability_mw_by_asset` 乘时段长度之间；互联线注入介于负的 `export_capacity_mwh` 与正的 `import_capacity_mwh` 之间。

同价非储能报价按可自由接纳量比例分配。上调分组采用相同区域、方向、网络作用和价格，下调还要求类别相同。`_forced_down_by_bid` 先分出实际可用率或互联线限额要求的强制下调量。对组内某报价及该组第一报价，实现采用

$$
\begin{aligned}
\mathrm{free}&=\mathrm{bid\_capacity}_{k}-\mathrm{forced},\\
\mathrm{first\_free}&=\mathrm{bid\_capacity}_{k_0}-\mathrm{first\_forced},\\
(\mathrm{values}_{\mathrm{bid}:k}-\mathrm{forced})\cdot \mathrm{first\_free}
&=(\mathrm{values}_{\mathrm{bid}:k_0}-\mathrm{first\_forced})\cdot \mathrm{free}.
\end{aligned}
$$

每个地理边界限制其成员走廊的带方向合计流量。`coefficient` 为成员方向系数，`forward_capacity` 与 `reverse_capacity` 为将 MW 输入换算后的期间 MWh：

$$
-\mathrm{reverse\_capacity}_b
\le\sum_{l\in b}\mathrm{coefficient}_{b,l}\cdot \mathrm{values}_{\mathrm{flow}:l}
\le\mathrm{forward\_capacity}_b.
$$

各边界同时约束流量。单独声明的走廊限额进一步限制该走廊，`absolute-flow` 至少等于正、负两个方向的流量值。因此，B6 的 6,700 MW 在每半小时对应 3,350 MWh，Western Link 的 2,200 MW 对应 1,100 MWh。缺少自身限额的走廊仍受分区守恒和所属边界约束。

储能再调度以实际充放电更新内部库存。`opening` 取自 `initial_soc_mwh_by_asset`，`capacity` 取自 `energy_capacity_mwh`。各储能满足

$$
\begin{aligned}
\mathrm{values}_{\mathrm{storage\mbox{-}discharge}:s}
-\mathrm{values}_{\mathrm{storage\mbox{-}charge}:s}
&=\mathrm{final\_dispatch\_mwh\_by\_asset}_s,\\
\mathrm{final\_soc\_mwh\_by\_asset}_s={}&\mathrm{opening}_s\\
&+\mathrm{charge\_efficiency}_s\cdot
\mathrm{values}_{\mathrm{storage\mbox{-}charge}:s}\\
&-\mathrm{values}_{\mathrm{storage\mbox{-}discharge}:s}/
\mathrm{discharge\_efficiency}_s.
\end{aligned}
$$

充放电分别介于零与对应功率乘 `period_hours` 之间，期末库存介于零与 `capacity` 之间。储能报价采用 `convex_net_power_v1`，每个方向至多一条，下调价格至多为上调价格加 \(10^{-8}\) GBP/MWh。最终同时充放电量至多为 \(10^{-8}\) MWh。期末库存传入下一期，全国计划与提交报价提供当前决策中的跨期价值。

物理资源支出与报价支付分别核算。`resource_cost_gbp_per_mwh_by_asset` 乘资产正的最终注入，缺电按 VoLL 计价：

$$
\begin{aligned}
\mathrm{physical\_resource\_cost\_gbp}={}&
\sum_a\max(\mathrm{final\_dispatch\_mwh\_by\_asset}_a,0)\\
&\qquad\cdot\mathrm{resource\_cost\_gbp\_per\_mwh\_by\_asset}_a\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot
\sum_z\mathrm{values}_{\mathrm{load\mbox{-}shedding}:z}.
\end{aligned}
$$

网络约束费用将该结果与合并为单节点、移除走廊和边界后的同一线性规划比较。`solve_network_free_counterfactual` 保留报价、出口套利、进出口限额、储能物理约束、缺电估值和求解设置。两种情况共用逐期单位费用表：优先取给定的时变资源费用，其余采用年度边际费用、储能循环折旧及零出口资源费用。负进口价格可使期间资源支出为负。

第一目标的差额单独记为 `network_constraint_bid_objective_gbp`。预测误差归因比较实际预测和完全预测的无网络结果。每次比较仅改变所声明的空间或预测输入，并保留相同优化方法。

## 数值求解与边界边际价值

求解器先固定第一目标最优解的缺电总量，再限制其中的报价费用。`lock_primary_shedding` 在第一阶段缺电总量为零时将各区缺电固定为零，其余情况以上一最优解的缺电合计作为上界。`bid_cost_coefficients` 提供下一条约束使用的纯报价费用系数。

目标约束采用随数值尺度变化的浮点容差。`compute_lock_tolerance` 读取目标系数 `coefficients`、前次最优解 `optimum`、下限 `unit_floor` 和有效 `solver_tolerance`，计算

$$
\begin{aligned}
\mathrm{absolute\_term\_scale}&=\sum_i|
\mathrm{coefficients}_i\cdot \mathrm{optimum}_i|,\\
\mathrm{coefficient\_one\_norm}&=\sum_i|\mathrm{coefficients}_i|,\\
\mathrm{gamma\_n}&=\frac{\mathrm{nonzero\_terms}\cdot \mathrm{epsilon}}
{1-\mathrm{nonzero\_terms}\cdot \mathrm{epsilon}},\\
\mathrm{tolerance}=\max\bigl\{&\mathrm{unit\_floor},\\
&\mathrm{solver\_tolerance}\cdot\max(1,\mathrm{absolute\_term\_scale}),\\
&\mathrm{gamma\_n}\cdot \mathrm{absolute\_term\_scale},\\
&\mathrm{coefficient\_one\_norm}\cdot \mathrm{solver\_tolerance}\bigr\}.
\end{aligned}
$$

`nonzero_terms` 为非零系数数目，`epsilon` 为机器精度。有效容差取适用求解容差与边界归整容差的较大值。报价费用约束的下限为 \(10^{-8}\) GBP，默认求解容差为 \(10^{-9}\)；MWh 目标的下限为 \(10^{-9}\) MWh，求解容差下限为 \(10^{-8}\)。报价费用接纳上限为每期 1 GBP。后续求解保留前面目标的上界。HiGHS 对偶单纯形法启用预求解，原始与对偶容差均为 \(10^{-9}\)，最终等式、不等式及变量界偏差至多为 \(10^{-7}\)。

```text
for period in the half-hour chronology:
    align_zonal_demand(...): obtain zonal demand
    build_single_period_problem(...): build bids and physical constraints
    solve_lexicographic(problem):
        minimise primary_objective; retain primary boundary marginals
        lock_primary_shedding(...); bound bid_cost_coefficients(problem)
        minimise secondary_objective; retain its objective bound
        minimise physical_tie_objective; retain its objective bound
        minimise stable_tie_objective; validate_solution(...)
    solve_network_free_counterfactual(...): compute matched comparison
    return actual injections, storage inventory, flows, shortage and costs
    pass final_soc_mwh_by_asset to the next period
```

边界边际价值表示第一目标对传输容量的响应。`boundary_marginal_values` 在增加目标约束前读取正、反向容量行的对偶值：

$$
\mathrm{value\_gbp\_per\_mwh}_b
=\mathrm{marginals}_{\mathrm{reverse\_row}_b}
-\mathrm{marginals}_{\mathrm{forward\_row}_b}.
$$

正值对应正向限额生效，负值对应反向限额生效。状态为 `computed`、限额生效但对偶值为零时的 `degenerate_dual`，或多个生效边界共享走廊、对偶分配具有多解时的 `shared_member`。年度合计的“边界价值乘传输量绝对值”作为拥塞诊断，与区域价格、现金流和系统费用分别报告。缺少该计算的账本显示“Not computed”。

## 两个分区案例

英国 23 区网络研究采用随 VALUE 0.7.0-alpha.1 提供的 GBP1 public2 研究套件 `value-uk-research-suite-v1-public2`，下载见[数据页](https://value.ac/zh/data/)。网络包含 22 条计算走廊以及 B6、B7a 两个边界，双向容量分别为 6,700 MW 和 9,400 MW。2025–2034 年研究设计保持网络容量固定，年度需求与资产可以变化。

23 区包按站点分配风电和光伏位置，CCGT、OCGT、生物质、径流水电、核电、储能和进口均放入 `ENGLAND_FALLBACK`。public2 核电政策在运行时形成的逐站资产采用该默认分区，包括位于 B6 以北的 Torness。进口资源名称为 `import:<country>`，登陆点表名称为 `interconnector:<line>`，两者对应关系缺失，进口也进入默认分区。`runtime_fallback_audit` 记录这些分配，分区结果的空间分布具有指示意义。

分段与分区运行的账本声明 `full_node_v1` 平衡边界，因此能够评估能量平衡。独立检查 `generation_cross_path` 与 `demand_input_reconciliation` 的状态仍为 `not_evaluated`。默认 `summary` 轨迹省略逐时段求解诊断，结果页相应显示“未记录”。

11 区试验使用 T1–T11 表示英国区域，并在固定资产下运行单年传输比较。区域依次为苏格兰北部、苏格兰南部、英格兰北部、北威尔士／默西河／亨伯河、英格兰中部、英格兰中部偏南、东英吉利、南威尔士／塞文河、英格兰西南部、英格兰南部和英格兰东南部。时间序列采用 2022 年负荷与天气，共 17,520 个半小时，模型背景年为 2025。该试验的容量保持固定，年度投资模块留在试验之外。

11 区网络由 13 条交流资产类别的计算走廊及 Western Link 组成。普通走廊连接 1–2、2–3、3–4、4–5、5–6、5–8、6–7、6–8、6–11、8–9、8–10、9–10、10–11；Western Link 连接 T2→T4。下表列出地理边界及另设的 Western Link 限额。2029 容量作为独立敏感性输入，基础案例使用 2025 容量。

| 边界 | 2025 正反向容量 MW | 2029 敏感性容量 MW | 正向成员 |
|---|---:|---:|---|
| B4 | 4,002 | 4,923 | f12 |
| B6 | 6,700 | 11,456 | f23 + fWL |
| B7a | 9,400 | 10,609 | f34 + fWL |
| B8 | 11,000 | 14,005 | f45 |
| B9 | 11,500 | 12,900 | f56 + f58 |
| EC5 | 3,300 | 5,925 | −f67 |
| LE1 | 11,223 | 13,917 | f6,11 + f10,11 |
| B13 | 3,500 | 6,575 | −f89 + f9,10 |
| Western Link | 2,200 | 2,200 | fWL |

Western Link 的传输同时占用 B6 与 B7a 的既定容量。8 个地理边界的反向能力采用正向能力的对称假设，Western Link 输入采用双向额定值。基础约简网络对 T6、T8、T10 的边界成员定义相同，三者之间的模型传输能力缺少有限上界。其 14 维走廊空间中，节点关联矩阵秩为 10，地理边界矩阵秩为 8，加入 HVDC 限额后秩为 9；5 维约束零空间含 3 维循环流和 2 维节点净传输方向。

热容量敏感性为南部 8 条走廊补充单独限额，同时保留地理边界。构造方法将区内已知变电站收缩为区域节点，保留未知中间节点，排除其他已知区，再以线路网络的最大流／最小割计算走廊容量。并联线路容量相加，串联路径受其瓶颈控制；MVA 按功率因数 1 换算为 MW。普通夏季与冬季输入如下，另设的上界敏感性使用各自输入文件。

| 走廊 | 夏季 MW | 冬季 MW |
|---|---:|---:|
| T5–T6 | 19,086 | 21,052 |
| T5–T8 | 3,424 | 3,934 |
| T6–T8 | 4,436 | 5,558 |
| T6–T11 | 16,684 | 19,849 |
| T8–T9 | 8,088 | 9,217 |
| T8–T10 | 6,470 | 7,834 |
| T9–T10 | 4,434 | 5,558 |
| T10–T11 | 6,587 | 7,500 |

## 直流网络调度

直流网络模块在完整时序上联合选择发电、储能运行和节点电压相角。`ReferenceDCNetworkPSM` 在 `layout` 中建立 `generation`、`charge`、`discharge`、`soc`、`blackout`、`angle` 和 `flow` 变量块，公式沿用这些名称表示其解值。前五项为 MWh，`angle` 为弧度，`flow` 为 MW。资源、储能、节点、支路和时段索引为 \(i,s,n,l,t\)。`marginal_costs`、`variable_degradation_gbp_per_mwh_discharged` 和 `voll_gbp_per_mwh` 的单位为 GBP/MWh。固定装机下的运行支出为

$$
\begin{aligned}
\min\quad&\sum_{i,t}\mathrm{marginal\_costs}_{i,t}\cdot \mathrm{generation}_{i,t}\\
&+\sum_{s,t}\mathrm{variable\_degradation\_gbp\_per\_mwh\_discharged}_s\cdot
\mathrm{discharge}_{s,t}\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot\sum_{n,t}\mathrm{blackout}_{n,t}.
\end{aligned}
$$

跨节点资产通过 `expand_share_mappings` 拆为各位置独立的资源单元。每项资产的映射字段 `share` 合计为 1，按份额缩放发电装机、储能充放电功率、电量容量和期初库存。求解器在指定节点调度这些单元，再按原资产汇总。VoLL 读取 `market.voll_gbp_per_mwh`，默认 17,000 GBP/MWh。

节点守恒用 `period_hours` 将支路功率换为电量。对节点 \(n\) 上的单元，

$$
\begin{aligned}
&\sum_{i\in n}\mathrm{generation}_{i,t}
+\sum_{s\in n}(\mathrm{discharge}_{s,t}-\mathrm{charge}_{s,t})
+\mathrm{blackout}_{n,t}\\
&\quad+\mathrm{period\_hours}\cdot\sum_{l:\mathrm{to\_bus}=n}\mathrm{flow}_{l,t}
=\mathrm{demand\_mwh\_by\_bus}_{n,t}
+\mathrm{period\_hours}\cdot\sum_{l:\mathrm{from\_bus}=n}\mathrm{flow}_{l,t}.
\end{aligned}
$$

资源上界为 `capacity_mw`、`share`、`availability` 与 `period_hours` 的乘积。储能按相同映射份额采用第 8 章的充放电和库存约束，库存更新为

$$
\begin{aligned}
\mathrm{soc}_{s,t}={}&\mathrm{soc}_{s,t-1}
+\mathrm{charge\_efficiency}_s\cdot \mathrm{charge}_{s,t}\\
&-\mathrm{discharge}_{s,t}/\mathrm{discharge\_efficiency}_s.
\end{aligned}
$$

期末规则可以为自由、等于期初库存的循环规则，或固定目标。启用 `allow_blackout` 时，缺电介于零与节点需求之间，其余情况固定为零。资源可用率位于 \([0,1]\)，边际费用非负。

交流线路与变压器采用声明的等效电抗及相角差。`base_mva` 默认 100 MVA，`tap` 默认 1，`phase` 将 `phase_shift_degrees` 换为弧度：

$$
\begin{aligned}
\mathrm{susceptance}_l&=\frac{\mathrm{base\_mva}}
{\mathrm{reactance\_pu}_l\cdot \mathrm{tap}_l},\\
\mathrm{flow}_{l,t}&=\mathrm{susceptance}_l\cdot
(\mathrm{angle}_{\mathrm{from\_bus},t}
-\mathrm{angle}_{\mathrm{to\_bus},t}-\mathrm{phase}_l),\\
|\mathrm{flow}_{l,t}|&\le\mathrm{thermal\_rating\_mw}_l\cdot \mathrm{circuits}_l.
\end{aligned}
$$

回路数缩放热容量，声明的等效电抗进入相角方程。每个电气孤岛有一个零相角参考节点，其余相角位于 \([-\pi,\pi]\)。停运支路流量为零，直流联络线以声明范围内的可控流量进入节点平衡。

HiGHS 在一次线性规划中求解全部时段，原始与对偶容差为 \(10^{-8}\)，等式残差上限为 \(10^{-7}\)。节点电量平衡的对偶值给出 GBP/MWh 边际运行价格，系统显示价格按需求加权。该完整时域比较由固定资产、连续调度、储能与线性网络共同定义。

## 交流可行性计算

交流模块计算给定有功计划下的稳态潮流。输入包含有功与无功需求、发电机有功和无功限额、电压设定、支路阻抗与充电电纳、固定变比及相移、电压范围和 MVA 额定值。每个电气孤岛有一个平衡资产，PV 和平衡节点配置发电机，同一节点的发电机采用共同电压设定。储能按给定的有功充放电计划运行。

节点复功率由求得的电压及节点导纳矩阵计算。`vm` 为标幺电压幅值，`theta` 为弧度，`voltage` 为复数标幺电压，`injection` 的实部和虚部分别为 MW、Mvar。`ybus` 为 `base_mva` 基准下的标幺导纳，\(j^2=-1\)：

$$
\begin{aligned}
\mathrm{voltage}_n&=\mathrm{vm}_n\cdot e^{j\cdot\mathrm{theta}_n},\\
\mathrm{injection}_n&=\mathrm{base\_mva}\cdot \mathrm{voltage}_n\cdot
\overline{\sum_m\mathrm{ybus}_{nm}\cdot \mathrm{voltage}_m}.
\end{aligned}
$$

支路采用 π 型阻抗表示。`_ybus` 将 `resistance_pu` 加 \(j\) 倍 `reactance_pu` 后取倒数得到 `series`；`charging` 为虚数充电电纳的一半；`tap` 为变比乘复数相移因子。两端导纳为

$$
\begin{aligned}
\mathrm{yff}&=(\mathrm{series}+\mathrm{charging})/|\mathrm{tap}|^2,\\
\mathrm{yft}&=-\mathrm{series}/\overline{\mathrm{tap}},\qquad
\mathrm{ytf}=-\mathrm{series}/\mathrm{tap},\\
\mathrm{ytt}&=\mathrm{series}+\mathrm{charging}.
\end{aligned}
$$

求解器拟合非平衡节点有功平衡与 PQ 节点无功平衡，固定 PV 和平衡节点电压幅值。平衡资产提供剩余有功和网损，节点无功发电受该节点发电机合计限额约束。两端复功率 `s_from` 与 `s_to` 包含 MW 与 Mvar，`losses` 的单位为 MW；它们采用声明的端点 \(f,t\)：

$$
\begin{aligned}
\mathrm{s\_from}&=\mathrm{base\_mva}\cdot \mathrm{voltage}_f\cdot
\overline{\mathrm{yff}\cdot \mathrm{voltage}_f+\mathrm{yft}\cdot \mathrm{voltage}_t},\\
\mathrm{s\_to}&=\mathrm{base\_mva}\cdot\mathrm{voltage}_t\cdot
\overline{\mathrm{ytf}\cdot\mathrm{voltage}_f+\mathrm{ytt}\cdot\mathrm{voltage}_t},\\
\mathrm{losses}_l&=\operatorname{Re}(\mathrm{s\_from}+\mathrm{s\_to}).
\end{aligned}
$$

两端视在功率均受 `apparent_power_rating_mva` 乘 `circuits` 约束。在役支路按声明阻抗进入导纳矩阵，拓扑和设备设定保持固定。

非线性最小二乘从多个初始电压条件求解。收敛解先核对一致性，再检查发电有功与无功边界、节点电压、支路额定值，以及供给、充电、需求和损失之间的系统平衡。`ReferenceACFeasibilityPSM` 返回该计划对应的局部稳态轨迹和可行性检查。

## 可选线路扩建

线路扩建根据观测拥塞和声明年度收益筛选外部候选。候选记录包含端点、回路数、支路参数及限额、建设费用、固定运维、寿命、折现率、建设期、延误、规划成功率和预算组。`ReferenceTransmissionExpansion.propose` 计算峰值利用率 `utilisation`、年费用 `annual_cost` 和效益费用比 `ratio`：

$$
\begin{aligned}
\mathrm{utilisation}&=\max_{t,l\in\mathrm{trigger\_branch\_ids}}
\frac{|\mathrm{branch\_flow\_mw}_{l,t}|}{\mathrm{trigger\_branch\_rating\_mw}},\\
\mathrm{annual\_cost}&=\operatorname{\_crf}(\mathrm{discount\_rate},\mathrm{economic\_life\_years})\\
&\qquad\cdot\mathrm{total\_capex\_gbp\_per\_build}
+\mathrm{annual\_fixed\_opex\_gbp\_per\_build},\\
\mathrm{ratio}&=\mathrm{declared\_annual\_benefit\_gbp}/\mathrm{annual\_cost}.
\end{aligned}
$$

资本回收函数 `_crf` 使用参数 `rate` 与 `life`：

$$
\operatorname{\_crf}(\mathrm{rate},\mathrm{life})=
\begin{cases}
1/\mathrm{life},&\mathrm{rate}=0,\\
\dfrac{\mathrm{rate}\cdot(1+\mathrm{rate})^{\mathrm{life}}}
{(1+\mathrm{rate})^{\mathrm{life}}-1},&\mathrm{rate}>0.
\end{cases}
$$

候选按 `ratio` 降序和标识升序排列，最早决策年、最低触发利用率、最低效益费用比、总预算与预算组额度共同决定准入。年费用为零时比率为无穷大。注册参数默认年度总资金为 0 GBP，每组额度为 \(10^{13}\) GBP。每个接纳提案扣除完整建设费用，预计投运年为决策年加 `lead_time_years` 和 `delay_years`。

规划成功由可重复的均匀抽样值与 `success_probability` 比较决定。默认种子为 0，提案标识包含运行标识，两者共同确定抽样。年初将已完成项目投运；线路按投运年加 `economic_life_years` 向上取整的年份退役。`apply_commissioned_network_assets` 将投运支路接入年度网络。23 区和 11 区案例保持固定网络，线路扩建属于单独选择的方法。

## 数据与实现对应

分区数据由 `zones`、`corridors`、`cutsets`、`asset-map`、`demand`、`ratings` 和 `interconnector-landings` 输入组成。`align_zonal_demand` 执行两种需求规则，`build_single_period_problem` 建立再调度约束，`solve_lexicographic` 依次求解 4 个目标，`ZonalRedispatchBalancing` 返回实际注入、库存及费用。11 区研究采用外部研究脚本 `build_network_data.py` 和 `fixed_fleet_runner.py`，容量情景由 `cutsets_2025.json`、`cutsets_2029.json` 及夏冬热容量文件定义。这些脚本属于上文的独立固定资产实验，随模型提供的英国网络研究采用 23 区套件。

`network_method_rules.py` 定义 `network-economic-v2`。无网络参照使用 `value.network-free-lp/v1` 标识，`zonal_results.py` 汇总分区结果。各年度在 `extensions.downward_restart_economics` 中记录下调报价假设，采用 `value.network-downward-restart-economics/v1` 结构；缺失输入及回退依据记入计算记录。

独立电网模块使用节点、支路、资产到节点映射及逐期需求。`ReferenceDCNetworkPSM` 和 `validate_dc_solution` 对应线性调度及其物理检查；`load_ac_data_from_pack`、`ReferenceACFeasibilityPSM` 和 `validate_ac_result` 对应交流输入、潮流及可行性检查。`ReferenceTransmissionExpansion` 读取候选与预算并更新建设状态，`apply_commissioned_network_assets` 将在役新增线路接入网络。
