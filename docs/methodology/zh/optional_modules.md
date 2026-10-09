# 完全预见调度与天然水文

## 完全预见单节点调度

完全预见模块在固定装机下，联合安排完整输入时序中的发电、进口和储能。`PerfectForesightPSM.run` 读取 `PSMInput.chronology`，年度外层模型提供投资及其形成的装机。各期输入包括需求、资源可用率和边际费用；储能输入包括功率、电量容量、效率和期初库存。

目标函数最小化资源运行支出、储能衰减费用和缺电费用。公式保留实现名称：`resource_period`、`charge_period`、`discharge_period`、`soc_period` 和 `blackout` 均为 MWh 数组，下标 \(i\)、\(s\)、\(t\) 分别对应资源、储能和时段。`resource_marginal_costs` 与 `variable_degradation_gbp_per_mwh_discharged` 的单位为 GBP/MWh，`voll_gbp_per_mwh` 为缺电估值。目标为

$$
\begin{aligned}
\min\quad&\sum_{i,t}\mathrm{resource\_marginal\_costs}_{i,t}\cdot
\mathrm{resource\_period}_{i,t}\\
&+\sum_{s,t}\mathrm{variable\_degradation\_gbp\_per\_mwh\_discharged}_{s}\cdot
\mathrm{discharge\_period}_{s,t}\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot\sum_t\mathrm{blackout}_{t}.
\end{aligned}
$$

单节点平衡以资源供给、储能放电和记录缺电满足需求及充电：

$$
\begin{aligned}
&\sum_i\mathrm{resource\_period}_{i,t}
+\sum_s\mathrm{discharge\_period}_{s,t}+\mathrm{blackout}_{t}\\
&\qquad=\mathrm{demand\_mwh}_{t}+\sum_s\mathrm{charge\_period}_{s,t}.
\end{aligned}
$$

储能库存表示内部电量。电网侧充电量乘 `charge_efficiency` 后进入库存，送出电量除以 `discharge_efficiency` 后从库存扣除：

$$
\begin{aligned}
\mathrm{soc\_period}_{s,t}={}&\mathrm{soc\_period}_{s,t-1}
+\mathrm{charge\_efficiency}_s\cdot \mathrm{charge\_period}_{s,t}\\
&-\mathrm{discharge\_period}_{s,t}/\mathrm{discharge\_efficiency}_s.
\end{aligned}
$$

容量约束通过 `period_hours` 将 MW 换为期间 MWh：

$$
\begin{aligned}
0&\le\mathrm{resource\_period}_{i,t}
\le\mathrm{capacity\_mw}_{i}\cdot \mathrm{availability}_{i,t}\cdot \mathrm{period\_hours},\\
0&\le\mathrm{charge\_period}_{s,t}
\le\mathrm{charge\_power\_mw}_{s}\cdot \mathrm{period\_hours},\\
0&\le\mathrm{discharge\_period}_{s,t}
\le\mathrm{discharge\_power\_mw}_{s}\cdot \mathrm{period\_hours},\\
0&\le\mathrm{soc\_period}_{s,t}\le\mathrm{energy\_capacity\_mwh}_{s}.
\end{aligned}
$$

期初与期末库存决定储能在整个时域内的净电量交换。第一期从 `initial_soc_mwh` 开始；默认 `terminal_soc_rule = cyclic` 要求期末等于期初，`fixed` 采用 `terminal_soc_mwh_by_asset`，`free` 允许期末库存位于容量界内。启用 `allow_blackout` 时，缺电量介于零与 `demand_mwh` 之间，其余情况的上界为零。默认 `period_hours = 0.5`、`voll_gbp_per_mwh = 17000`，衰减费用为零。Study 参数 `market.voll_gbp_per_mwh` 接受 0–1,000,000 GBP/MWh，并进入调度目标。

第二次线性规划在第一次解的费用容差内最小化储能吞吐。`primary.fun` 为第一次求解的最小费用，单位 GBP；第二次保留全部物理约束，并增加

$$
\begin{aligned}
\mathrm{primary\_tolerance}&=\max(10^{-7},10^{-10}|\mathrm{primary.fun}|),\\
\mathrm{objective}^{\mathsf T}\cdot\mathrm{solution}
&\le\mathrm{primary.fun}+\mathrm{primary\_tolerance},\\
\min\quad&\sum_{s,t}(\mathrm{charge\_period}_{s,t}+\mathrm{discharge\_period}_{s,t}).
\end{aligned}
$$

两次求解均采用 HiGHS，原始与对偶可行性容差为 \(10^{-8}\)。返回的物理轨迹为 `secondary.x`，最大同时充放电量 `simultaneous` 须小于等于 \(10^{-6}\) MWh。未使用的风光电量为可用量减已接纳资源供给。

页面显示的“Balance shadow price”为第一阶段需求的边际运行费用。资源收入为需求平衡对偶值与接纳 MWh 的乘积，储能收入为该对偶值乘放电减充电，消费者支付采用已供应需求。系统费用在变量支出、衰减和缺电费用上，加年化资本及非风、非光、非储能资产的固定运维。固定费用输入为 `annual_fixed_opex_gbp`；风、光和储能的固定运维按第 4 章作为备查分项。

```text
PerfectForesightPSM.run(model_input):
    data = model_input.chronology
    validate_chronology(data, model_input.period_hours)
    _availability(...) and _marginal_costs(...): expand inputs to every period
    _layout(data): allocate resource, charge, discharge, soc and blackout
    assemble objective, throughput_objective, equality, rhs and bounds
    primary = linprog(objective, A_eq=equality, b_eq=rhs,
                      bounds=bounds, method="highs")
    primary_tolerance = max(1e-7, abs(primary.fun) * 1e-10)
    secondary = linprog(
        throughput_objective, A_ub=objective.reshape(1, -1),
        b_ub=[primary.fun + primary_tolerance], A_eq=equality, b_eq=rhs,
        bounds=bounds, method="highs")
    extract resource_period, charge_period and discharge_period
    extract soc_period and blackout
    check balance and simultaneous storage operation
    return costs and demand duals
```

资源可用率接受单元素序列或完整时序，数值须有限且位于 \([0,1]\)。边际费用接受标量、单元素序列或完整时序，数值须有限且非负。适配器核对时序长度，并要求充电、放电效率位于 \((0,1]\)。该输入中的水电作为具有给定电力可用率的资源。下述水文函数从来水构造可用电量，或优化常规水库运行。

## 径流式水电可用电量

天然水文方法根据来水时序和站点参数计算可用电量。`run_of_river_dispatch` 读取 `HydroSite` 与 `CanonicalInflow`；默认全国 PSM 采用第 5 章的统计负荷率和季节曲线。

归一化电力可用率按时段长度缩放装机功率。输入为 `inflow.unit = p.u.` 时，`inflow.values` 位于 \([0,1]\)，`capacity_mw` 单位为 MW，`interval_hours` 单位为小时：

$$
\begin{aligned}
\mathrm{maximum}&=\mathrm{capacity\_mw}\cdot \mathrm{interval\_hours},\\
\mathrm{available}_t&=\mathrm{maximum}\cdot \mathrm{inflow.values}_t.
\end{aligned}
$$

水量输入乘站点水电转换系数和涡轮效率，再受发电功率约束：

$$
\begin{aligned}
\mathrm{available}_t=\min\bigl(&\mathrm{maximum},\\
&\mathrm{inflow.values}_t\cdot \mathrm{conversion\_mwh\_per\_water\_unit}\cdot
\mathrm{turbine\_efficiency}\bigr).
\end{aligned}
$$

接纳发电量介于零与 `available` 之间，默认接纳全部可用电量，`curtailed` 记录剩余电力潜力。返回结果中，三个数组分别记为 `available_energy_mwh`、`accepted_generation_mwh` 和 `curtailed_energy_mwh`。10 MW 电站在 0.5 h 时段内采用可用率 \([0,0.5,1]\)，得到 \([0,2.5,5]\) MWh。各期独立计算。

## 常规水库调度

常规水库在完整来水与电力价值时序上分配水量，以最大化发电价值。`reservoir_dispatch` 的四类期间变量为涡轮放水 `q`、生态旁路 `bypass`、弃水 `spill` 和期末库存 `storage`，均采用声明的水量单位，前三项表示期间水量。电量转换为

$$
\mathrm{conversion}=\mathrm{conversion\_mwh\_per\_water\_unit}\cdot
\mathrm{turbine\_efficiency},\qquad
\mathrm{generation}_t=\mathrm{q}_t\cdot \mathrm{conversion}.
$$

线性规划最小化发电价值的相反数与小额弃水惩罚之和。`energy_value_gbp_per_mwh` 为外部给定的电力价值时序：

$$
\begin{aligned}
\min\quad&-\sum_t\mathrm{energy\_value\_gbp\_per\_mwh}_t\cdot
\mathrm{conversion}\cdot \mathrm{q}_t+10^{-9}\sum_t\mathrm{spill}_t.
\end{aligned}
$$

水量连续性连接相邻库存与来水，第一期从 `initial_volume` 开始：

$$
\begin{aligned}
\mathrm{storage}_t={}&\mathrm{storage}_{t-1}+\mathrm{inflow.values}_t
-\mathrm{q}_t-\mathrm{bypass}_t-\mathrm{spill}_t,\\
\mathrm{min\_volume}&\le\mathrm{storage}_t\le\mathrm{max\_volume}.
\end{aligned}
$$

涡轮、普通放水及生态要求共同限制水量分配：

$$
\begin{aligned}
0&\le\mathrm{q}_t\le\mathrm{max\_turbine\_release\_per\_period},\\
0&\le\mathrm{bypass}_t\le\mathrm{max\_total\_release\_per\_period},\qquad
\mathrm{spill}_t\ge0,\\
\mathrm{minimum\_environmental\_release\_per\_period}
&\le\mathrm{q}_t+\mathrm{bypass}_t
\le\mathrm{max\_total\_release\_per\_period}.
\end{aligned}
$$

普通放水上限和生态下限同时约束涡轮放水加旁路，弃水单独进入水量平衡。给定 `terminal_volume` 时，期末库存固定为该值。参数检查要求普通放水上限至少等于涡轮放水上限，最大涡轮放水转换的电量至多为 `turbine_capacity_mw` 乘 `interval_hours`，容差为 \(10^{-9}\) MWh。

求解器读取完整来水与价值序列，调用一次 SciPy/HiGHS 线性规划，返回水量轨迹、发电量和守恒残差。`objective_gbp` 包含小额弃水惩罚。输入标签 `myopic`、`rolling_horizon` 和 `perfect_foresight` 均调用这一完整时域算法，并作为元数据返回。

```text
reservoir_dispatch(parameters, inflow, energy_value_gbp_per_mwh):
    inflow.validate(); parameters.validate(inflow.interval_hours)
    conversion = (parameters.conversion_mwh_per_water_unit
                  * parameters.turbine_efficiency)
    allocate q, bypass, spill and storage for every period
    assemble objective, water equalities, release inequalities and bounds
    use parameters.terminal_volume as the final storage bound when supplied
    solved = linprog(objective, A_ub=inequalities, b_ub=upper,
                     A_eq=equalities, b_eq=rhs, bounds=bounds, method="highs")
    generation = q * conversion
    check previous + inflow.values[period] - q - bypass - spill - storage
    return generation, water trajectories and residuals
```

## 水文输入与模块连接

天然水文输入包括站点表、资产到站点映射、径流式水电来水、水库来水和水库参数。站点声明技术、装机、涡轮效率、节点、来源及许可；抽蓄采用电储能模型。每项资产分配至一个站点，映射份额位于 \((0,1]\)，同一资产份额合计至多为 1。

来水 CSV 提供带时区的时间戳、时段长度、站点标识、数值及水量或电力可用率单位。适配器要求数值有限且非负、时间戳唯一、单位一致；给定预期时序时逐期核对。站点、映射及参数表接受 JSON 或 CSV，缺失值处理声明为 `none`。

输入与运行函数可独立调用。`load_hydrology_inputs_from_pack` 汇集输入，`adapt_hydrology_csv` 读取来水，`validate_site_mapping` 核对映射，`run_of_river_dispatch` 计算径流式水电，`reservoir_dispatch` 优化水库放水。年度市场应用需要适配器连接这些输入、输出与调度流程，并提供相应站点、来水、取水、转换、库存及期末参数。
