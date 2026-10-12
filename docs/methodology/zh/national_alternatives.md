# 全国市场出清

全国市场在每个半小时先出清预测需求，再按实际需求完成平衡。默认模块 `value-bid-at-cost-psm` 采用 `native-corrected-v1`：发电和进口报出可用功率，储能报出满足条件的库存批次，最终调度更新下一期的物理状态。

## 输入、代理与可用出力

调度量以 MW 表示，`period_hours = 0.5`。变量 `forecast_demand`、`real_demand`、`capacity_limit`、`real_gen_energy` 和 `alter_limit` 分别表示预测需求、实际需求、可用出力、实际出力和每期爬坡额度；机组下标为 \(i\)，时段下标为 \(t\)，其他资产下标在相应计算处定义。UTC 模型年含 17,520 期。Native 内核读取以 MW 表示的需求，在电量输出和结算时将接纳功率乘 `period_hours`。`canonical_psm_data.py` 的 chronology 接口按第 2 章规则向分阶段与优化模块提供期间 MWh。

发电报价由运行费用和取决于上期接纳集合的启动加价构成。燃气和生物质采用 `gen_cost + fuel_cost + carbon_price + unit_time_cost`；核电、风光和天然水电采用 `gen_cost + unit_time_cost`。输入行的费用相加后写入运行对象的 `gen_cost`，单位为 GBP/MWh；`carbon_price` 已表示每 MWh 发电的费用。设报价倍率为 \(\mathrm{bidding\_factor}\)、综合运行费用为 \(\mathrm{gen\_cost}_i\)、启动加价为 \(\mathrm{startup\_cost}_i\)，则

$$
\begin{aligned}
\mathrm{price}_{i,t}={}&\mathrm{bidding\_factor}\cdot \mathrm{gen\_cost}_{i}\\
&+\mathrm{startup\_cost}_{i}\cdot
\mathbf1[i\notin\mathrm{accepted\_bids\_name}_{t-1}].
\end{aligned}
$$

报价倍率默认取 1，水电与风光的启动加价为零。GB 输入行中，生物质综合费用为 0.2 + 80 + 4.8 = 85 GBP/MWh，启动加价为 83 GBP/MWh；CCGT 和 OCGT 的综合费用分别为 55.07 和 74.92 GBP/MWh。生物质收入按市场结算计量。

年度适配器先按名称、再按技术与标准化区域，将在运和当年投运资产映射到市场代理。多个候选依次采用已映射容量、构造器容量或等份作为权重。`weights` 与 `total_weight` 将资产的 `capacity_mw` 分配至 `generator_sources`，这些容量均以 MW 计量，其中 \(j\) 表示市场代理，\(a\) 表示资产。`_allocate_runtime_income` 再按分配容量，将 `raw_income` 分到资产账户 `allocated`，二者均以 GBP 计量：

$$
\begin{aligned}
\mathrm{generator\_sources}_{j,a}
&=\mathrm{capacity\_mw}_a\cdot \mathrm{weights}_j/\mathrm{total\_weight},\\
\mathrm{capacity}_j&=\sum_a\mathrm{generator\_sources}_{j,a},\\
\mathrm{allocated}_a&=\sum_j\mathrm{raw\_income}_j\cdot
\frac{\mathrm{generator\_sources}_{j,a}}{\mathrm{capacity}_j}.
\end{aligned}
$$

风电采用 20 MW 参考机组和 \(\mathrm{capacity\_mw}_j/20\) 倍率，光伏采用 1 MW 参考机组和 \(\mathrm{capacity\_mw}_j\) 倍率，储能功率与能量按技术聚合。`scheme_c_native_psm.py` 每年建立代理，并恢复上一年售电量及按售电量加权的持有时间，用于计算报价。每年创建的储能代理采用空的 `stored_energy`；上一年期末库存作为丢弃电量记入 `storage_year_boundary`。

风光可用出力采用与标准输入适配器相同的逐期数组。`site_weather.site_cf_by_source` 执行第 3 章的天气、损耗及组件平面辐照换算，`kernel_injection.KernelSiteInputs` 将容量因子 \(\mathrm{cf}_{j,t}\) 传入内核：

$$
\mathrm{capacity\_limit}_{j,t}=\mathrm{capacity\_mw}_j\cdot \mathrm{cf}_{j,t}.
$$

核电可用率在换算模型容量时保留各站 PRIS 参考出力。`nuclear_load_factor` 读取 `pris_load_factor`、`pris_reference_mw` 和 `capacity_mw`；`generation_end_period` 给出宣布停发月份后第一期 `end`，全年可用的电站在各期保留该负荷率。以 \(n\) 为电站下标，`asset_availability` 生成各站数组 `values`，`kernel_availability` 按容量合并：

$$
\begin{aligned}
\mathrm{factor}_n&=\min\left(1,
\frac{\mathrm{pris\_load\_factor}_n\cdot \mathrm{pris\_reference\_mw}_n}
{\mathrm{capacity\_mw}_n}\right),\\
\mathrm{values}_{n,t}&=\mathrm{factor}_n\cdot \mathbf1[t<\mathrm{end}_n],\\
\mathrm{weighted}_{\mathrm{Nuclear},t}
&=\sum_n\mathrm{capacity\_mw}_n\cdot \mathrm{values}_{n,t},\\
\mathrm{kernel\_availability}_{\mathrm{Nuclear},t}
&=\frac{\mathrm{weighted}_{\mathrm{Nuclear},t}}{\sum_n\mathrm{capacity\_mw}_n}.
\end{aligned}
$$

2019–2024 年固定平均负荷率为 Heysham 1 的 0.668、Hartlepool 的 0.689、Heysham 2 的 0.752、Torness 的 0.792 和 Sizewell B 的 0.801。具有电站政策的输入将四座 AGR 的可用率从 2030 年第 4,320 期，即 4 月 1 日 00:00 UTC 起设为零；Sizewell B 在声明的退役年之前保持全年覆盖。回退负荷率分别为新建 PWR/EPR 的 0.801、未指定 AGR 的 0.727、全国合并核电资产的 0.723。GBP1 public2 采用 VALUE-UK 核电电站政策（`value_uk_nuclear_policy_v1.json`：五座 EDF 电站及其宣布的停发时间），其机组输入表只有一行合并核电；R029 保留全国合并资产，在全国调度中采用 0.723。参数由 `value_uk_firm_availability_v1.json` 与 `firm_availability.py` 提供。

径流水电采用 DUKES 6.3 平均年负荷率，并结合 Energy Trends 季度数据形成的月度形状：

$$
\mathrm{values}_t=0.3487\cdot \mathrm{monthly\_shape}_{\mathrm{month\_of\_period}(t)},
$$

$$
\begin{aligned}
\mathrm{monthly\_shape}=[&1.3851,1.3851,1.3851,0.6582,0.6582,0.6582,\\
&0.6776,0.6776,0.6776,1.2791,1.2791,1.2791].
\end{aligned}
$$

形状的月度算术均值为 1，按 365 天加权的均值为 0.99883，对应模型年可用率 0.3483。核电与水电在各模型年采用这些固定曲线。

核电在年初设为在运，属于 \(\mathrm{accepted\_bids\_name}_{-1}\)；燃气与生物质位于该集合之外。机组参数行给出初始 `real_gen_energy`，核电将其设为 `capacity_limit`。水电与生物质的 `have_gen_energy` 初始化为各自的 `real_gen_energy`，随后每期将 `add_energy` 加入 `energy_limit`，按剩余预算接纳发电，并将下调量返回预算。预算量采用 MW·时段，乘 `period_hours` 后得到 MWh。

## 储能报价与期间头寸

储能代理将各充电期的内部 MWh 记入以充电期 \(k\) 为索引的 `stored_energy`，\(t\) 表示当前期。`Battery.charge` 根据 `power_capacity_mw`、`energy_capacity_mwh`、充电效率 `n_1` 和本期已有充电后的剩余功率限制输入。对各储能，计算为

$$
\begin{aligned}
\mathrm{stored\_total}&=\sum_k\mathrm{stored\_energy}_{k},\\
\mathrm{remaining\_input\_power}
&=\max\left(\frac{\mathrm{energy\_capacity\_mwh}-\mathrm{stored\_total}}
{\mathrm{n\_1}\cdot \mathrm{period\_hours}},0\right),\\
\mathrm{already\_charged\_power}
&=\frac{\mathrm{stored\_energy}_{t}}{\mathrm{n\_1}\cdot \mathrm{period\_hours}},\\
\mathrm{period\_power\_headroom}
&=\max(\mathrm{power\_capacity\_mw}-\mathrm{already\_charged\_power},0),\\
\mathrm{input\_power}&=\min(\max(\mathrm{available\_input\_power\_mw},0),\\
&\qquad\mathrm{remaining\_input\_power},\mathrm{period\_power\_headroom}),\\
\mathrm{stored\_energy}_t&\leftarrow\mathrm{stored\_energy}_t
+\mathrm{input\_power}\cdot \mathrm{n\_1}\cdot \mathrm{period\_hours}.
\end{aligned}
$$

`Battery.discharge` 从指定批次扣除 `output_power * period_hours / n_2` MWh，其中 `n_2` 为放电效率。全部批次及各阶段共享额定功率，日前采用已有批次，上调采用年龄至少两期的批次。期间账户中的 `discharged_mw`、`charged_mw` 及 `stored_energy` 合计满足

$$
\begin{aligned}
0&\le\mathrm{discharged\_mw}\le\mathrm{power\_capacity\_mw},\\
0&\le\mathrm{charged\_mw}\le\mathrm{power\_capacity\_mw},\\
\mathrm{discharged\_mw}\cdot \mathrm{charged\_mw}&=0,\\
0&\le\mathrm{stored\_total}\le\mathrm{energy\_capacity\_mwh}.
\end{aligned}
$$

吸收盈余时，储能先回购本期放电，并将撤回的电量返回原批次；剩余放电降至零后，继续到达的盈余才能充电。本期已经充电的储能在后续阶段提供零放电。盈余吸收先处理预测差额盈余，再处理其他可用盈余，并按时段结束时的净头寸记录售电。被回购的出力保留日前储能报酬。

自放电在每期将库存乘 \(1-\mathrm{decay\_rate}\)。电池及其他默认类型的 \(\mathrm{decay\_rate}\) 为 0.000021，抽蓄为 0.000001，氢储能为 0.000005。小于 0.001 MWh 的批次被移除，并进入库存核对。

默认动态储能成本模块按循环折旧报价。电池报价为 \(\mathrm{bidding\_factor}\cdot\mathrm{cycle\_depreciation\_gbp\_per\_mwh}_b\)，抽蓄和氢储能报价为零，最老批次先行报价：

$$
\begin{aligned}
\mathrm{price}=\mathrm{bidding\_factor}\times
\begin{cases}
\mathrm{cycle\_depreciation\_gbp\_per\_mwh},&\mathrm{battery},\\
0,&\mathrm{pumped\ hydro\ or\ hydrogen}.
\end{cases}
\end{aligned}
$$

第 4 章定义储能状态与报价费用的计算。年度送出 MWh 和售电量加权持有时间进入下一年的定价输入，其年度费用处理见第 6 章。

## 预测出清与平衡

市场按稳定排序键排列发电、进口和储能批次报价。同一 0.01 £/MWh 档内，发电和进口位于储能之前，再按未取整价格和输入顺序处理并列：

$$
\mathrm{merit\_key}(\mathrm{offer})=
(\operatorname{round}(\mathrm{price},2),
\mathbf1[\mathrm{is\_storage\_offer}(\mathrm{offer})],\ \mathrm{price}).
$$

普通机组满足剩余预测需求，其出力上限为

$$
\min(\mathrm{real\_gen\_energy}_{i,t-1}+\mathrm{alter\_limit}_i,
\mathrm{capacity\_limit}_{i,t}).
$$

水电与生物质还受剩余累计预算 \(\mathrm{energy\_limit}_i-\mathrm{have\_gen\_energy}_i\) 约束，该预算以 MW·时段表示，乘 \(\mathrm{period\_hours}\) 后转为 MWh。核电接纳量可高于剩余需求 \(\mathrm{forecast\_demand}\)：当其上限高于 \(\mathrm{forecast\_demand}\) 时，供应 \(\max(\mathrm{real\_gen\_energy}_{i,t-1}-\mathrm{alter\_limit}_i,\mathrm{forecast\_demand})\)，超出部分成为已经发出的刚性盈余。风光高于需求接纳量的可用出力保留为可用盈余。

互联线以对侧价格乘 \(\mathrm{bidding\_factor}\) 报出正的可用进口容量，参与日前出清。进口报价受容量约束，爬坡和启动加价均为零。平衡阶段仅报出 \(\max(\mathrm{transfer\_constraint}_{k,t}-\mathrm{accepted\_mw}_{k,t},0)\)。负的传输容量表示出口能力，在对侧价格为正时接纳出口。

日前结束后，以可用量减接纳量重建风光盈余，并先使用已经发出的核电盈余。风光盈余被储能、出口或柔性需求使用时，计入风光毛发电量。因此，`vre_accepted` 表示风光毛出力，`curtailed` 表示可用风光减毛出力，`excess` 表示非风光溢出。已进入日前供给与结算的核电盈余在平衡阶段仅分配一次；在平衡阶段进入供给的风光盈余接受平衡结算。

日前出清依次接纳报价，在剩余预测需求降为零或全部报价耗尽时结束。日前阶段没有核电机组被接纳时，核电的 `real_gen_energy` 在平衡前乘 0.99。实际调度结束后，最终出力为零的机组将 `real_gen_energy` 设为零，其余机组将最终出力传入下一期。

实时阶段按实际需求与预测需求的比较选择分支。实际需求较低时，执行盈余吸收和下调；较高或相等时，执行上调平衡。日前供给低于预测需求时，仍采用这一比较规则：较低实际需求的分支继续要求下调 \(\mathrm{forecast\_demand}_t-\mathrm{real\_demand}_t\)，留下的需求缺口进入下文电量账户。

```text
accepted_bids = initial_running_rows(generators)
for period in range(periods):
    Read availability, forecast_demands[period], real_demands[period]
    Read period external_price and transfer_constraint
    ahead_market_bidding(...):
        Add add_energy to each hydro/biomass energy_limit
        Apply storage self-discharge; construct offers
        Sort by merit_key; accept forecast demand subject to physical bounds
        rebuild_surplus(...); uniform_income(...)
    realise_period(...):
        if real_demand < forecast_demand:
            curtailment_market_bidding(...):
                Buy back discharge, charge, export, supply electrolysis
                economic_downward_stack(...): reduce remaining output
        else:
            balancing_market_bidding(...):
                Use surplus; buy back discharge and charge
                Offer eligible batches, generation and residual imports
                Export remaining surplus and supply electrolysis
                Clear upward demand; record remaining blackout
        Set real_gen_energy to zero for generators with zero final output
    battery.close_period(period) for each battery
    physical_cost_terms(...): record period expenditure components
return period dispatch, prices, income, inventory and annual totals
```

低需求分支按 `storage_fee`、`per_storage_fee`、`n_1 * n_2` 的升序依次处理储能，上调平衡按储能输入顺序处理。每项储能先回购本期放电，再接纳充电。正价格出口在低需求分支按对侧价格降序接纳，在上调平衡按对侧价格升序接纳，各自受负 `transfer_constraint` 的绝对值限制。

上调出清从最后一台日前接纳机组开始，加入后续发电报价、年龄至少两期的储能批次和剩余进口容量。对这台边际机组，`valid_energy` 为当前受爬坡约束的出力上限减日前已接纳 MW；后续机组采用完整的受爬坡约束上限。水电和生物质还遵循剩余预算。每次接纳量减少初值为 `real_demand - forecast_demand` 的 `energy_provided`，该量降为零或全部报价耗尽时结束，剩余量记为 `blackout`。

公共电解槽作为柔性需求吸收盈余。源参数为 10 MW 容量、每期 0.125 MW 爬坡和 0.65 转换效率，选定数值由数据包参数行提供。可用风光先进入市场出清，再按盈余分配顺序供应储能、出口和电解。本期电解槽限额为 `energy_cell = min(real_energy + rampup_rate, capacity_limit)`，单位 MW。接纳量 `min_value` 取该限额与剩余盈余的较小值：低需求分支采用 `excess_energy + need_curtailed_energy`，上调平衡采用 `excess_energy`；随后更新 `real_energy = min_value` 和 `green_hy = min_value * energy_efficiency`。

## 经济下调顺序

在储能、出口和柔性需求吸收盈余后，比较下调能够避免的运行支出。`ramp_floor_mw` 取零与上期 `real_gen_energy` 减 `alter_limit` 的较大值，风光和进口的下限为零。`avoided_cost` 读取综合 `gen_cost`，核电扣除 `NUCLEAR_DEC_PREMIUM_GBP_PER_MWH = 100`，进口采用 `external_price`。普通报价行按保留两位小数的避免费用降序排列。

燃气与生物质将当期日前接纳出力 \(\mathrm{power}_k\) 拆为不停机段与停机段。在此排序规则中，\(\mathrm{power}_k\) 代表聚合机组在线容量，\(\mathrm{min\_stable\_fraction}_k\) 为最小稳定出力比例：

$$
\begin{aligned}
\mathrm{stable}&=\mathrm{min\_stable\_fraction}\cdot \mathrm{power},\\
\mathrm{running}&=\max(\mathrm{power}-\max(\mathrm{floor},\mathrm{stable}),0),\\
\mathrm{shutdown}&=\max(\mathrm{power}-\mathrm{floor},0)-\mathrm{running}.
\end{aligned}
$$

不停机段每 MWh 避免 \(\mathrm{cost}_k\) 英镑费用；停机段将预计停机时长 \(\mathrm{horizon\_h}\) 内的节省与重启费用 \(\mathrm{restart\_cost}(\mathrm{horizon\_h})\) 比较，后者按每 MW 装机每次启动计量：

$$
\begin{aligned}
\mathrm{net\_saving}(\mathrm{cost},\mathrm{horizon\_h})
&=\mathrm{cost}-\frac{\mathrm{restart\_cost}(\mathrm{horizon\_h})}
{\mathrm{min\_stable\_fraction}\cdot \mathrm{horizon\_h}},\\
\mathrm{horizon\_h}&=(1+\mathrm{run\_after}_t)\cdot \mathrm{period\_hours}.
\end{aligned}
$$

`SurplusOutlook.run_after` 统计当前期之后连续满足“预测需求不高于预测风光加核电可用量”的期数，当前下调期另计一期。缺少注入可用率数组时，`horizon_h = 0.5` h。在稳定出力比例处减少 1 MW，需要停运 `1 / min_stable_fraction` MW 装机；重启比较因此将费用除以该比例及预计停机时长。

当 \(\mathrm{horizon\_h}\ge \mathrm{min\_down\_time\_h}_k\) 时，停机段与其他资源按净节省降序排列。\(\mathrm{saving}_k\) 为正时排在零成本风光之前；为零或负时排在风光之后，取整后同值也按风光在前处理。当 \(\mathrm{horizon\_h}<\mathrm{min\_down\_time\_h}_k\) 时，该段排在其他全部可下调资源之后。这些量共同定义连续出力的排序规则；物理费用账户采用前文启动报价加价 \(\mathrm{startup\_cost}_i\)。

|技术|热／温／冷重启费用，2025 年 GBP/MW|最小稳定出力比例|最短停机时间，h|
|---|---:|---:|---:|
|CCGT|113.7 / 134.4 / 155.0|0.50|6|
|OCGT|175.7 / 175.7 / 175.7|0.50|0.5|
|生物质|129.2 / 129.2 / 129.2|0.35|6|

CCGT 在 \(\mathrm{horizon\_h}<12\) h 时采用热启动值，\(12\le \mathrm{horizon\_h}\le48\) h 时采用温启动值，\(\mathrm{horizon\_h}>48\) h 时采用冷启动值。`value_thermal_restart_v1.json` 综合 [Kumar 等（2012）](https://docs.nrel.gov/docs/fy12osti/55433.pdf) 的循环磨损估计与 [Staffell 和 Green（2016）](https://doi.org/10.1109/TPWRS.2015.2407613) 的 GB 启动燃料和碳费用估计。最小出力和停机时间参考 Elexon 申报值及参数表记录的技术资料。参数表以 [ONS CPI D7BT](https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7bt/mm23) 的 \(138.4/133.9\) 将选定的 2024 年英镑值换算为 2025 年英镑，并将重启费用保留一位小数；记录的换算系数为 1.0336。

`RestartParameters.break_even_hours` 将重启费用除以 `min_stable_fraction` 与避免费用的乘积。按 GB 运行费用，热启动 CCGT、OCGT、生物质的盈亏平衡时长分别为 4.13 h、4.69 h、4.34 h。因此，满足 6 h 条件的 CCGT 和生物质停机段具有正净节省，OCGT 在半小时时钟上从 5 h 开始取得正净节省。CCGT 六小时停机对应的费用边界为 113.7 / (0.5 × 6) = 37.9 £/MWh。

相同的取整净节省依次采用类别值：火电 0、进口 0.5、水电与生物质 1、风光 2、停机段 2.5、核电 3，再按名称和输入顺序排列。每次接纳的下调量消耗一次剩余需求：

$$
\begin{aligned}
\mathrm{take}&=\min(\mathrm{limit},\mathrm{item}[2],\mathrm{remaining}),\\
\mathrm{item}[2]&\leftarrow\mathrm{item}[2]-\mathrm{take},\\
\mathrm{remaining}&\leftarrow\mathrm{remaining}-\mathrm{take}.
\end{aligned}
$$

`limit` 为报价段可下调 MW，`item[2]` 为该行剩余接纳出力，`remaining` 为尚需下调的量。水电与生物质将下调量返回累计预算，受爬坡下限保留的出力记为调度内溢出。`native_corrected.economic_downward_stack` 执行这些下调。下调在 `remaining` 至多为 \(10^{-9}\) MW 或所有可下调段耗尽时结束。

## 结算、显示价格与物理费用

市场对各阶段全部接纳供给采用统一边际价。日前取包含进口与储能在内的最高接纳报价，`uniform_income` 将接纳 `power_mw` 乘时段长度及阶段 `price_gbp_per_mwh`；平衡价格同样包含接纳进口报价。`income` 为 GBP，`power_mw` 为 MW，价格为 GBP/MWh；空接纳类别向最大值计算提供零：

$$
\mathrm{income}_{i,t}=\mathrm{power\_mw}_{i,t}\cdot
\mathrm{period\_hours}\cdot \mathrm{price\_gbp\_per\_mwh}_t,
$$

$$
\mathrm{price\_gbp\_per\_mwh}^{\mathrm{balancing}}_t
=\max(\mathrm{max\_gen\_price}_t,\mathrm{max\_bat\_price}_t,
\max_{k\in\mathrm{imports}}\mathrm{price}_{k,t}).
$$

储能费用在本期内结算。被回购的储能出力保留日前报酬，物理调度及年度送出电量采用期末净头寸。

市场显示价格的标签为“Average period cost (£/MWh demand)”，即每 MWh 需求的时段平均费用。设 \(\mathrm{total\_gen\_cost}_t\) 为接纳报价、储能、下调及上调费用的累加器，其单位为 GBP/小时。价格单位为 GBP/MWh，对应期间费用为 GBP：

$$
\begin{aligned}
\mathrm{avg\_price}_t&=\begin{cases}
\mathrm{total\_gen\_cost}_t/\mathrm{real\_demand}_t,&\mathrm{real\_demand}_t>0,\\
0,&\mathrm{real\_demand}_t=0,
\end{cases}\\
\mathrm{retained\_period\_cost\_gbp}_t
&=\mathrm{period\_hours}\cdot \mathrm{total\_gen\_cost}_t.
\end{aligned}
$$

这一统计量描述实际需求的每 MWh 费用；发电与储能收入根据前述结算账户计算。\(\mathrm{total\_gen\_cost}_t\) 仅包含本期储能费用。最终边界供给进入年度发电量统计，储能放电量另行报告。

物理运营费用按综合 `gen_cost` 计量实际发电、按 `external_price` 计量进口，并以 `startup_cost` 乘启动期发电 MWh 计量启动加价。`physical_cost_terms` 返回各期的 `generation_variable_gbp`、`import_variable_gbp` 和 `startup_adder_gbp`。第 6 章将这些分项与储能折旧、缺电估值和年度资本费用合并。

## 电量平衡与年度输出

期间电量平衡边界包含接纳毛供给、充电、出口、柔性需求和非风光溢出。本节各量均以 MWh 表示。设接纳供给为 \(\mathrm{accepted\_supply\_mwh}_t\)、记录切负荷为 \(\mathrm{blackout\_mwh}_t\)、实际需求为 \(\mathrm{real\_demand\_mwh}_t\)、储能充电为 \(\mathrm{storage\_charge\_mwh}_t\)、出口为 \(\mathrm{export\_mwh}_t\)、柔性需求为 \(\mathrm{flexible\_demand\_mwh}_t\)、非风光溢出为 \(\mathrm{non\_vre\_spill\_mwh}_t\)，则期间残差为

$$
\begin{aligned}
\mathrm{residual\_mwh}_t={}&\mathrm{accepted\_supply\_mwh}_t
+\mathrm{blackout\_mwh}_t-\mathrm{real\_demand\_mwh}_t\\
&-\mathrm{storage\_charge\_mwh}_t-\mathrm{export\_mwh}_t\\
&-\mathrm{flexible\_demand\_mwh}_t-\mathrm{non\_vre\_spill\_mwh}_t.
\end{aligned}
$$

电量账户通过 `compatibility_adjustment_mwh` 吸收浮点运算的小幅残差，该数值项仅在期间容差以内生效：

$$
\begin{aligned}
\mathrm{tolerance\_mwh}_t=\max\bigl(&10^{-6},\\
&10^{-9}\max(\mathrm{real\_demand\_mwh}_t,\mathrm{accepted\_supply\_mwh}_t)\bigr),\\
\mathrm{compatibility\_adjustment\_mwh}_t
&=\begin{cases}
-\mathrm{residual\_mwh}_t,&10^{-9}<|\mathrm{residual\_mwh}_t|\le\mathrm{tolerance\_mwh}_t,\\
0,&\mathrm{otherwise}.
\end{cases}
\end{aligned}
$$

电量账户根据物理残差和调度分支记录的缺电量，计算全部未满足需求：

$$
\begin{aligned}
\mathrm{unserved\_mwh}_t&=\max(0,-(\mathrm{residual\_mwh}_t-\mathrm{blackout\_mwh}_t)),\\
\mathrm{closing\_residual\_mwh}_t&=\mathrm{residual\_mwh}_t
-\mathrm{blackout\_mwh}_t+\mathrm{unserved\_mwh}_t.
\end{aligned}
$$

仅含未满足需求的时段以 \(\mathrm{closing\_residual\_mwh}_t=0\) 闭合。同一年内连续出现缺口的时段构成一次事件。年度输出包含事件数、时段数和未满足 MWh；第 6 章将各缺口分项各扣除一次，得到已服务需求。

年度输出合计机组与进口 MWh、储能充放电、风光弃电、非风光溢出、出口、柔性需求、期间价格、资产收入和未满足电量。期间状态将实际出力与储能批次传入下一期，年度模型随后执行第 6 章的核算与投资规则。
