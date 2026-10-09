# 全国调度算法

默认全国电力系统模型 Native（`value-bid-at-cost-psm`）每半小时在全国单节点上出清。方法学口径决定市场规则集：默认修正口径采用 `native-corrected-v1`，论文复现口径采用 `native-doctoral-thesis-v1`。实验性全国路径（`value-doctoral-national-psm`）具有独立的调度引擎和输入约定。第 6 章介绍与其相关的实验年度账户。

## 输入、代理与可用出力

调度量以 MW 表示，`period_hours = 0.5`。变量 `forecast_demand`、`real_demand`、`capacity_limit`、`real_gen_energy` 和 `alter_limit` 分别表示预测需求、实际需求、可用出力、实际出力和每期爬坡额度；资产与时段下标用于索引这些量。UTC 模型年含 17,520 期。`canonical_psm_data.py` 按第 2 章读取规则，将 MW 需求乘 `period_hours` 换成期间 MWh。

发电报价由运行费用和取决于上期接纳集合的启动加价构成。燃气和生物质采用 `gen_cost + fuel_cost + carbon_price + unit_time_cost`；核电、风光和天然水电采用 `gen_cost + unit_time_cost`。输入行的费用相加后写入运行对象的 `gen_cost`，单位为 GBP/MWh；`carbon_price` 已表示每 MWh 发电的费用。设报价倍率为 \(\mathrm{bidding\_factor}\)、综合运行费用为 \(\mathrm{gen\_cost}_i\)、启动加价为 \(\mathrm{startup\_cost}_i\)，则

$$
\begin{aligned}
\mathrm{price}_{i,t}={}&\mathrm{bidding\_factor}\cdot \mathrm{gen\_cost}_{i}\\
&+\mathrm{startup\_cost}_{i}\cdot
\mathbf1[i\notin\mathrm{accepted\_bids\_name}_{t-1}].
\end{aligned}
$$

倍率默认取 1，水电与风光的启动加价为零，物理运营费用直接采用 \(\mathrm{gen\_cost}_i\)。随模型提供的 GB 参数中，生物质 费用为 0.2 + 80 + 4.8 = 85 £/MWh，启动加价为 £83/MWh；CCGT、OCGT 的综合费用分别为 £55.07/MWh、£74.92/MWh。生物质收入按市场结算计量，CfD 和 ROC 补贴属于该收入设定之外的政策机制。在这些费用下，GBP1 public2 和 R029 public2 的修正口径计算中，4,762 MW 生物质在 2025 年约发电 0.01 TWh。两个修订数据包随 VALUE 0.7.0-alpha.1 提供（[数据下载](https://value.ac/zh/data/)）。

Native 先按名称、再按技术与标准化区域，将在运和当年投运资产映射到市场代理。多个候选依次采用已映射容量、构造器容量或等份作为权重。`weights` 与 `total_weight` 将资产的 `capacity_mw` 分配至 `generator_sources`，这些容量均以 MW 计量。`_allocate_runtime_income` 再按分配容量，将 `raw_income` 分到资产账户 `allocated`，二者均以 GBP 计量：

$$
\begin{aligned}
\mathrm{generator\_sources}_{j,a}
&=\mathrm{capacity\_mw}_a\cdot \mathrm{weights}_j/\mathrm{total\_weight},\\
\mathrm{capacity}_j&=\sum_a\mathrm{generator\_sources}_{j,a},\\
\mathrm{allocated}_a&=\sum_j\mathrm{raw\_income}_j\cdot
\frac{\mathrm{generator\_sources}_{j,a}}{\mathrm{capacity}_j}.
\end{aligned}
$$

风电采用 20 MW 参考机组和 \(\mathrm{capacity\_mw}_j/20\) 倍率，光伏采用 1 MW 参考机组和 \(\mathrm{capacity\_mw}_j\) 倍率，储能功率与能量按技术聚合。`scheme_c_native_psm.py` 每年建立代理，并恢复上一年售电量及按售电量加权的持有时间，用于计算报价。物理库存采用新代理的初始状态；上一年对象的期末库存作为丢弃电量记入 `storage_year_boundary`。

修正口径的可用出力采用与标准输入适配器相同的逐期数组。`site_weather.site_cf_by_source` 执行第 3 章的天气、损耗及组件平面辐照换算，`kernel_injection.KernelSiteInputs` 将容量因子 \(\mathrm{cf}_{j,t}\) 传入内核：

$$
\mathrm{capacity\_limit}_{j,t}=\mathrm{capacity\_mw}_j\cdot \mathrm{cf}_{j,t}.
$$

论文复现口径采用冻结的天气时钟与第 3 章风光曲线，每个小时值用于两个半小时。两个口径均按对应模型时段读取互联线价格与可用传输容量。

修正口径的核电可用率在换算模型容量时保留各站 PRIS 参考出力。`nuclear_load_factor` 读取 `pris_load_factor`、`pris_reference_mw` 和 `capacity_mw`；`generation_end_period` 给出宣布停发月份后第一期 `end`，全年可用的电站在各期保留该负荷率。`asset_availability` 生成各站数组 `values`，`kernel_availability` 按容量合并：

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

2019–2024 年固定平均负荷率为 Heysham 1 的 0.668、Hartlepool 的 0.689、Heysham 2 的 0.752、Torness 的 0.792 和 Sizewell B 的 0.801。具有电站政策的输入将四座 AGR 的可用率从 2030 年第 4,320 期，即 4 月 1 日 00:00 UTC 起设为零；Sizewell B 在声明的退役年之前保持全年覆盖。回退负荷率分别为新建 PWR/EPR 的 0.801、未指定 AGR 的 0.727、全国合并核电资产的 0.723。GBP1 public2 采用 VALUE-UK 核电电站政策（`value_uk_nuclear_policy_v1.json`：五座 EDF 电站及其宣布的停发时间），其机组输入表只有一行合并核电；R029 保留全国合并资产，在修正 Native 调度中采用 0.723。参数由 `value_uk_firm_availability_v1.json` 与 `firm_availability.py` 提供。

修正口径的径流水电采用 DUKES 6.3 平均年负荷率，并结合 Energy Trends 季度数据形成的月度形状：

$$
\mathrm{values}_t=0.3487\cdot \mathrm{monthly\_shape}_{\mathrm{month\_of\_period}(t)},
$$

$$
\begin{aligned}
\mathrm{monthly\_shape}=[&1.3851,1.3851,1.3851,0.6582,0.6582,0.6582,\\
&0.6776,0.6776,0.6776,1.2791,1.2791,1.2791].
\end{aligned}
$$

形状的月度算术均值为 1，按 365 天加权的均值为 0.99883，对应模型年可用率 0.3483。核电与水电在各模型年采用这些固定曲线。论文复现口径中，两者可用率为 1。

修正 Native 调度将核电设为每个模型年开局在运，因此核电属于 \(\mathrm{accepted\_bids\_name}_{-1}\)。某期离开接纳集合后，重新被接纳的启动期计入启动加价；燃气与生物质开局位于接纳集合之外。论文复现口径采用 \(\mathrm{accepted\_bids\_name}_{-1}=\varnothing\)：GBP1 核电初始报价为 £500/MWh，被接纳后降为运行费用。GBP1 参数中的每期 500 MW 爬坡额度使其在后续低需求时段保留出力；未被接纳时，记忆出力每期乘 0.99。因此，年度核电量取决于当年首次进入接纳集合的时间。

## Native 储能批次与净头寸

Native 将各充电期的内部 MWh 记入 `stored_energy`。`Battery.charge` 根据 `power_capacity_mw`、`energy_capacity_mwh`、充电效率 `n_1` 和本期已有充电后的剩余功率限制输入。对各储能，计算为

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

批次`Battery.discharge` 从指定批次扣除 `output_power * period_hours / n_2` MWh，其中 `n_2` 为放电效率。全部批次及各阶段共享额定功率，日前采用已有批次，上调采用年龄至少两期的批次。期间账户中的 `discharged_mw`、`charged_mw` 及 `stored_energy` 合计满足

$$
\begin{aligned}
0&\le\mathrm{discharged\_mw}\le\mathrm{power\_capacity\_mw},\\
0&\le\mathrm{charged\_mw}\le\mathrm{power\_capacity\_mw},\\
\mathrm{discharged\_mw}\cdot \mathrm{charged\_mw}&=0,\\
0&\le\mathrm{stored\_total}\le\mathrm{energy\_capacity\_mwh}.
\end{aligned}
$$

吸收盈余时，储能先回购本期放电，并将撤回的电量返回原批次；剩余放电降至零后，继续到达的盈余才能充电。本期已经充电的储能在后续阶段提供零放电。两个口径均先处理预测差额盈余，再处理其他可用盈余，并按时段结束时的净头寸记录售电。被回购的出力保留日前储能报酬。

自放电在每期将库存乘 \(1-\mathrm{decay\_rate}\)。电池及其他默认类型的 \(\mathrm{decay\_rate}\) 为 0.000021，抽蓄为 0.000001，氢储能为 0.000005。小于 0.001 MWh 的批次被移除，并进入库存核对。

默认动态储能成本模块在修正口径中按循环折旧报价。电池报价为 \(\mathrm{bidding\_factor}\cdot\mathrm{cycle\_depreciation\_gbp\_per\_mwh}_b\)，抽蓄和氢储能报价为零，最老批次先行报价：

$$
\begin{aligned}
\mathrm{price}=\mathrm{bidding\_factor}\times
\begin{cases}
\mathrm{cycle\_depreciation\_gbp\_per\_mwh},&\mathrm{battery},\\
0,&\mathrm{pumped\ hydro\ or\ hydrogen}.
\end{cases}
\end{aligned}
$$

模块根据第 4 章年度成本回收输入计算循环折旧。历史电价、用户公式和外部储能成本模块分别提供自身报价函数。论文复现口径保留所选模块随批次年龄变化的报价；历史电价形式为

$$
\begin{aligned}
\mathrm{price}=\mathrm{bidding\_factor}\cdot\bigl(&\mathrm{storage\_fee\_gbp\_per\_mwh}\\
&+(t-k)\cdot \mathrm{holding\_fee\_gbp\_per\_mwh\_period}\bigr).
\end{aligned}
$$

正持有费使新批次更便宜，同价时保持批次顺序。年度观测保留送出 MWh 及 MWh 与年龄的乘积，供下一年定价使用。

## Native 预测出清与平衡

修正 Native 按稳定排序键排列发电、进口和储能批次报价。同一 0.01 £/MWh 档内，发电和进口位于储能之前，再按未取整价格和输入顺序处理并列：

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

修正口径的互联线以对侧价格乘 \(\mathrm{bidding\_factor}\) 报出正的可用进口容量，参与日前出清。进口报价受容量约束，爬坡和启动加价均为零。平衡阶段仅报出 \(\max(\mathrm{transfer\_constraint}_{k,t}-\mathrm{accepted\_mw}_{k,t},0)\)。负的传输容量表示出口能力，在对侧价格为正时接纳出口。论文复现口径的进口仅进入上调平衡分支，满足实际需求高于预测需求的剩余部分。

修正口径在日前结束后，以可用量减接纳量重建风光盈余，并先使用已经发出的核电盈余。风光盈余被储能、出口或柔性需求使用时，计入风光毛发电量。因此，`vre_accepted` 表示风光毛出力，`curtailed` 表示可用风光减毛出力，`excess` 表示非风光溢出。已进入日前供给与结算的核电盈余在平衡阶段仅分配一次；在平衡阶段进入供给的风光盈余接受平衡结算。

实时阶段按实际需求与预测需求的比较选择分支。实际需求较低时，执行盈余吸收和下调；较高或相等时，执行上调平衡。日前供给低于预测需求时，仍采用这一比较规则：较低实际需求的分支继续要求下调 \(\mathrm{forecast\_demand}_t-\mathrm{real\_demand}_t\)，由此留下的需求缺口进入下文的 stress 事件账户。

```text
for each half-hour:
    Read availability, demand and boundary inputs
    Update budgets and self-discharge
    Form generator, import and eligible storage-batch offers
    ahead_market_bidding(...): clear forecast demand in merit order
    rebuild_surplus(...): reconstruct renewable and already-generated surplus
    if actual demand < forecast demand:
        Buy back storage discharge using forecast surplus, then existing surplus
        Charge storage after its net discharge reaches zero
        Accept positive-price exports in descending external-price order
        Supply flexible electrolysis
        economic_downward_stack(...): reduce remaining output
    else:
        Use existing surplus for demand and offer the remainder to storage
        Merge remaining generation, eligible batches and residual imports
        balancing_market_bidding(...): serve upward demand; record blackout
    close_battery_period(...); uniform_income(...); physical_cost_terms(...)
```

公共电解槽作为柔性需求，原始默认值为 10 MW、每期爬坡 0.125 MW、效率 0.65，数据包可替换这些参数。修正路径将可用风光依次送入出清和后续盈余分配。论文复现口径在出清前，为每个风光代理分流 \(\min(\mathrm{real\_energy}+\mathrm{rampup\_rate},\mathrm{electrolyzer\_limit})\) 至直接电解，并分别记录分流量及其超出可用风光的部分。该口径还采用未取整价格的稳定排序和盈余节点平衡边界。

## 经济下调顺序

修正口径在储能、出口和柔性需求吸收盈余后，比较下调能够避免的运行支出。`ramp_floor_mw` 取零与上期 `real_gen_energy` 减 `alter_limit` 的较大值，风光和进口的下限为零。`avoided_cost` 读取综合 `gen_cost`，核电扣除 `NUCLEAR_DEC_PREMIUM_GBP_PER_MWH = 100`，进口采用 `external_price`。普通报价行按保留两位小数的避免费用降序排列。

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

`limit` 为报价段可下调 MW，`item[2]` 为该行剩余接纳出力，`remaining` 为尚需下调的量。水电与生物质将下调量返回累计预算，受爬坡下限保留的出力记为调度内溢出。`native_corrected.economic_downward_stack` 执行这些下调。

论文复现口径按 `curtail_cost` 升序下调，零成本风电位于燃气之前，水电下调量返回其预算。两个口径均在剩余下调需求降为零时结束下调。

## 结算、显示价格与物理费用

修正 Native 对各阶段全部接纳供给采用统一边际价。日前取包含进口与储能在内的最高接纳报价，`uniform_income` 将接纳 `power_mw` 乘时段长度及阶段 `price_gbp_per_mwh`；平衡价格同样包含接纳进口报价：

$$
\mathrm{income}_{i,t}=\mathrm{power\_mw}_{i,t}\cdot
\mathrm{period\_hours}\cdot \mathrm{price\_gbp\_per\_mwh}_t,
$$

$$
\mathrm{price\_gbp\_per\_mwh}^{\mathrm{balancing}}_t
=\max(\mathrm{max\_gen\_price}_t,\mathrm{max\_bat\_price}_t,
\max_{k\in\mathrm{imports}}\mathrm{price}_{k,t}).
$$

储能费用在本期结算。论文复现口径分别以发电、储能的最高接纳报价定价；接纳发电机集合为空时，收入映射为空，包括由储能独自供给的时段。该口径还将最后一个平衡时段的储能费用计入后续下调时段费用。

Native 显示价格的标签为“Average period cost (£/MWh demand)”，即每 MWh 需求的时段平均费用。设 \(\mathrm{total\_gen\_cost}_t\) 为接纳报价、储能、下调及上调费用的累加器，则价格和对应期间费用为

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

这一统计量描述实际需求的每 MWh 费用；发电与储能收入根据前述结算账户计算。修正口径的 \(\mathrm{total\_gen\_cost}_t\) 仅包含本期储能费用。最终边界供给进入年度发电量统计，Native 另行报告储能放电量。

物理运营费用按综合 `gen_cost` 计量实际发电，按 `external_price` 计量进口，按 `startup_cost` 乘发电 MWh 计量符合条件的启动。`physical_cost_terms` 返回 `generation_variable_gbp`、`import_variable_gbp` 和 `startup_adder_gbp`，年度账户再加记录切负荷费用及当年储能循环折旧。年份索引为 \(y\)，`operating` 与 `cycle_wear` 为实现中的年度合计，单位 GBP：

$$
\begin{aligned}
\mathrm{operating}_y={}&
\sum_t(\mathrm{generation\_variable\_gbp}_t
+\mathrm{import\_variable\_gbp}_t\\
&\qquad+\mathrm{startup\_adder\_gbp}_t)\\
&+\mathrm{voll\_gbp\_per\_mwh}\cdot\sum_t\mathrm{blackout\_mwh}_t
+\mathrm{cycle\_wear}_y.
\end{aligned}
$$

\(\mathrm{import\_mwh}_{k,t}\) 为进口 MWh，\(\mathrm{blackout\_mwh}_t\) 为记录的切负荷 MWh，\(\mathrm{cycle\_wear}_y\) 为各储能资产 `current_cycle_depreciation_gbp` 的合计。市场结算转移与这些资源费用分项分别报告。费用账户采用 \(\mathrm{voll\_gbp\_per\_mwh}=17{,}000\) £/MWh，等价于每 MW·半小时 £8,500。修正 Native 读取 `market.voll_gbp_per_mwh`，可设范围为 0–1,000,000；论文复现规则集采用常数 17,000。在 Native 中，该参数用于费用账户对记录切负荷的估值。Stress 缺口单列，并从第 4 章采用的已供电量分母中扣除。

## 能量平衡与结果资格

修正 Native 的平衡边界包含接纳毛供给、充电、出口、柔性需求和非风光溢出。本节各量均以 MWh 表示。设接纳供给为 \(\mathrm{accepted\_supply\_mwh}_t\)、记录切负荷为 \(\mathrm{blackout\_mwh}_t\)、实际需求为 \(\mathrm{real\_demand\_mwh}_t\)、储能充电为 \(\mathrm{storage\_charge\_mwh}_t\)、出口为 \(\mathrm{export\_mwh}_t\)、柔性需求为 \(\mathrm{flexible\_demand\_mwh}_t\)、非风光溢出为 \(\mathrm{non\_vre\_spill\_mwh}_t\)，则 `native_corrected_full_node_v1` 残差为

$$
\begin{aligned}
\mathrm{residual\_mwh}_t={}&\mathrm{accepted\_supply\_mwh}_t
+\mathrm{blackout\_mwh}_t-\mathrm{real\_demand\_mwh}_t\\
&-\mathrm{storage\_charge\_mwh}_t-\mathrm{export\_mwh}_t\\
&-\mathrm{flexible\_demand\_mwh}_t-\mathrm{non\_vre\_spill\_mwh}_t.
\end{aligned}
$$

论文复现口径采用 `default_psm_surplus_node_v1`。其中，位于调度外并供给储能、出口或电解的风光盈余为 \(\mathrm{u\_out\_mwh}_t\)，已经接纳但最终溢出的盈余为 \(\mathrm{w\_in\_mwh}_t\)：

$$
\begin{aligned}
\mathrm{residual\_mwh}_t={}&\mathrm{accepted\_supply\_mwh}_t
+\mathrm{blackout\_mwh}_t\\
&+\mathrm{u\_out\_mwh}_t-\mathrm{w\_in\_mwh}_t\\
&-\mathrm{real\_demand\_mwh}_t-\mathrm{storage\_charge\_mwh}_t\\
&-\mathrm{export\_mwh}_t-\mathrm{flexible\_demand\_mwh}_t.
\end{aligned}
$$

兼容调整在声明容差内吸收数值噪声。Native 采用

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

LP 对应的容差系数为 \(10^{-5}\) 和 \(10^{-7}\)，超过容差的残差保留在物理平衡中。`native_balance_audit.py`、`energy_balance_contract.py` 与 `energy_balance_oracle.py` 将账本供给边界与这些核对连接。

能量账户先计算全部未满足需求，再区分记录切负荷和额外 stress 缺口：

$$
\begin{aligned}
\mathrm{unserved\_mwh}_t&=\max(0,-(\mathrm{residual\_mwh}_t-\mathrm{blackout\_mwh}_t)),\\
\mathrm{closing\_residual\_mwh}_t&=\mathrm{residual\_mwh}_t
-\mathrm{blackout\_mwh}_t+\mathrm{unserved\_mwh}_t.
\end{aligned}
$$

唯一不平衡为需求缺口的时段以 \(\mathrm{closing\_residual\_mwh}_t=0\) 闭合，记为 stress 时段。同一年内连续 stress 时段构成一个事件，年度报告给出事件数、时段数和缺口 MWh。与记录切负荷并列的额外 stress 量遵循账户的分项定义，第 4 章从需求中分别扣除每个未供需求分项一次。

年度资格核对包括三组：运行不变量；能量平衡与账本一致性，包括盈余守恒和 \(\sum_t|\mathrm{compatibility\_adjustment\_mwh}_t|/\sum_t\mathrm{real\_demand\_mwh}_t\le10^{-6}\)；储能吞吐、库存边界及批次平衡。修正口径的年度经济结果要求三组均通过，论文复现口径的结果页要求全部原始不变量通过。Stress 事件作为可靠性结果报告。年度状态记录另保留 Native 库存重置和各口径盈余边界的定义。

## 实验路径输入

实验性全国路径在两个方法学口径下均采用冻结的 v1 天气、核电与径流水电的单位可用率，以及原始边界价格。天气转换采用原始辐照约定和单位损耗因子。`doctoral_market_factory.py` 根据完整参数行构造代理，参数包含费用、效率、爬坡、初始出力、下调价格及天然资源预算。新资产可通过 `doctoral_parameter_source_id` 引用参数行，并保留该行的爬坡与预算值。此路径的直接风光电解和公共电解容量均为零。

该模块支持固定年度调度和实验年度现金账户，记录 `scientific_release_eligible=false` 与 `doctoral_annual_cem_ready=false`。与 `agent-investment` 连接时，具备决策资格的火电需要 `value.agent-cashflow/v1` 账户合同；实验 PSM 当前发布 `doctoral_cashflow_inputs`，因此该组合会在投资账户要求处停止。以下方程描述现行逐期引擎。

## 实验路径批次库存

实验内核在 `stored_energy` 中以功率等价值记录各批次，乘 `period_hours = 0.5` 后为内部 MWh。`pool_limit` 限制这些原始量的合计，`per_pool_limit` 为送出 MW，`n_1`、`n_2` 为充放电效率。自放电采用前述参数。于 `charge_period` 充电的批次在 `period` 的报价为

$$
\begin{aligned}
\mathrm{price}=\mathrm{bidding\_factor}\cdot\bigl(&\mathrm{storage\_fee}\\
&+(\mathrm{period}-\mathrm{charge\_period})\cdot \mathrm{per\_storage\_fee}\bigr).
\end{aligned}
$$

原型参数由 `config.py` 提供，`doctoral_market_factory.py` 为每次运行绑定完整参数行：

|原型技术|`n_1`|`n_2`|`storage_fee`|`per_storage_fee`|
|---|---:|---:|---:|---:|
|抽水蓄能|0.87|0.87|0|1.1008|
|1C 电池|0.81|0.81|0|1.0558|
|0.25C 电池|0.81|0.81|0|0.7369|
|0.5C 电池|0.98|0.98|135.26|0.1736|
|氢储能|0.57|0.57|884.4|0.0055|

全部批次及两阶段出清共享储能送出功率限额。日前从 `gen_list` 读取已有送出 MW `delivered`，再以剩余功率除 `n_2` 限制批次报价原始量 `item[3]`；剩余 `forecast_demand` 较小时，提取该需求除 `n_2` 的原始量。平衡阶段对 `energy_provided` 采用同一规则。日前采用全部已有批次，平衡采用年龄至少两期的批次。小于 0.001 的原始余额被移除，每批对应至多 0.0005 MWh。

充电按 `storage_fee`、`per_storage_fee` 和 `n_1 * n_2` 升序排列储能。`store_service_three` 对各储能先吸收预测盈余 `need_curtailed_energy`，再处理其他 `excess_energy`。第一轮采用

$$
\begin{aligned}
\mathrm{limit}&=\max(0,\mathrm{per\_pool\_limit}-\mathrm{stored\_energy}_t/\mathrm{n\_1}),\\
\mathrm{energy}&=\min(\mathrm{limit},\mathrm{need\_curtailed\_energy},
\mathrm{pool\_limit}-\sum_k\mathrm{stored\_energy}_k),\\
\mathrm{stored\_energy}_t&\leftarrow\mathrm{stored\_energy}_t+\mathrm{n\_1}\cdot \mathrm{energy}.
\end{aligned}
$$

第二轮将预测盈余替换为 `excess_energy`，原始库存空间直接限制电网侧充电功率。0.5C 原型持有四期后的报价为 135.26 + 4 × 0.1736 = 135.9544 GBP/MWh。10 MWh 批次的原始量为 20，在 0.5 h 内送出 10 MW，提取内部电量 5 / 0.98 = 5.1020408 MWh，以该价结算的收入为 £679.772。原始支出诊断采用原始提取量乘报价，现金结算采用送出 MWh。

## 实验路径计划与实时执行

`DoctoralPeriodEngine` 在期初物理状态副本上形成日前计划，更新天然预算和自放电后调用 `ahead_market_bidding`。发电与储能按价格稳定排序，常规机组受爬坡约束，水电和生物质还受剩余预算约束。核电上期 `real_gen_energy` 减 `alter_limit` 高于剩余预测需求时，保留这一出力；未获接纳的核电记忆出力每期乘 0.99。引擎分别记录未接纳风光可用量和已发出的核电盈余。

实时执行比较实际需求与扣除日前非风光盈余后的计划供应。`realise_period` 中，`actual` 与 `scheduled_load` 均为 MW：

$$
\mathrm{scheduled\_load}
=\sum_{(\mathrm{generator},\mathrm{amount})\in\mathrm{ahead}[10]}
\mathrm{amount}-\mathrm{already\_generated\_surplus}.
$$

当 `actual < scheduled_load` 时，差额进入 `curtailment_market_bidding`，依次充电、处理已有盈余、按价格降序接纳正价出口，再按配置的下调价格削减发电。`_curtail_thermal_bid` 采用接纳 MW `bid[2]`、上期 `previous_energy` 和 `generator.alter_limit` 限制下调量：

```text
if bid[2] - previous_energy == generator.alter_limit:
    max_curtail_energy = min(2 * generator.alter_limit, bid[2])
elif previous_energy >= generator.alter_limit:
    max_curtail_energy = bid[2] - (previous_energy - generator.alter_limit)
else:
    max_curtail_energy = bid[2]
curtailed = min(need_curtailed_energy,
                max(0, min(bid[2], max_curtail_energy)))
bid[2] -= curtailed
```

水电与生物质将削减量返回已用预算，上期出力按发电机对象身份读取。爬坡约束保留的非风光出力记为 `non_vre_spill`。

当 `actual >= scheduled_load` 时，`balancing_market_bidding` 先使用已有盈余，并向储能提供剩余部分，随后合并日前最后接纳机组及其后的机组、合格储能批次和进口。日前机组集合为空时，从第一条报价开始。边际机组的 `valid_energy` 为受爬坡限制的可用出力减日前接纳 MW，后续机组提供其全部爬坡可用量；水电与生物质继续受预算约束。进口采用 `external_price`，此分支按价格升序接纳正价出口，剩余需求形成切负荷。

引擎在推进状态前核对最终物理平衡。这里 `total`、`actual`、`charge`、`exported`、`non_vre_spill` 和 `blackout` 为 MW，`residual` 为 MWh：

$$
\begin{aligned}
\mathrm{missing}&=\mathrm{actual}+\mathrm{charge}+\mathrm{exported}
+\mathrm{non\_vre\_spill}-\mathrm{total},\\
\mathrm{blackout}&=\max(0,\mathrm{missing}),\\
\mathrm{residual}&=0.5(\mathrm{total}+\mathrm{blackout}-\mathrm{actual}
-\mathrm{charge}-\mathrm{exported}-\mathrm{non\_vre\_spill}).
\end{aligned}
$$

状态推进要求 `residual` 绝对值至多为 \(10^{-7}\) MWh，发电量非负，风光出力位于可用量以内。储能另核对期初 `opening`、电网侧 `charged` 与 `delivered`、自放电 `decay`、转换损失 `conversion` 和微小批次移除 `discard`，均以 MWh 计：

$$
\begin{aligned}
&\mathrm{conversion}=\mathrm{charged}\cdot(1-\mathrm{n\_1})
+\mathrm{delivered}\cdot(1/\mathrm{n\_2}-1),\\
&\mathrm{next\_state.storage\_energy\_mwh}(\mathrm{battery.name})\\
&\quad=\mathrm{opening}+\mathrm{charged}-\mathrm{delivered}\\
&\qquad-\mathrm{decay}-\mathrm{conversion}-\mathrm{discard}.
\end{aligned}
$$

`commit_period` 将期末储能批次、机组记忆和接纳机组集合传入下一期。进入储能和出口的风光发电量归属至相应来源。

## 实验路径结算与年度费用

实验引擎在日前和上调市场分别按发电与储能的最高接纳报价结算。`acm_income` 在下调改变出力前记录日前现金，将接纳 MW 乘 `period_hours` 及对应 `max_gen_price` 或 `max_bat_price`。储能独自供给时获得储能结算，`acm_income_balance` 对上调供应采用相同类别价格。

下调现金保留配置价格的符号。各接纳动作中，`quantity` 为 MW，`price` 为 GBP/MWh。引擎计算 `raw_gbp = quantity * 0.5 * price`，火电、生物质及水电计入 `down_cash`；核电、风光与储能计入 `legacy_down` 作为诊断。每项资产的 `income_balance` 为 `income_up` 加 `down_cash`，`income_ahead` 单列。

变量运营支出按 `gen_cost` 计量最终发电，按 `external_price` 计量进口，储能变量运营支出为零。燃料、碳价和其他费用构成总量的分项，出口收入与进口采购保留各自现金方向。

年度系统费用合计变量支出、显式固定费用、年化资本和缺电估值。`DoctoralNationalPSM` 从资产记录与期间合计取得 `variable`、`fixed` 和 `capital`：

$$
\mathrm{total\_system\_cost\_gbp}
=\mathrm{variable}+\mathrm{fixed}+\mathrm{capital}
+\mathrm{blackout\_mwh}\cdot \mathrm{voll\_gbp\_per\_mwh}.
$$

固定费用和资本费用进入完整 17,520 期年度汇总，较短诊断运行中两者均为零。年度发电包含储能放电与边界供给。显示的“Ahead settlement price”采用日前发电价格，可靠性系数读取 `market.voll_gbp_per_mwh`，默认 £17,000/MWh。第 6 章介绍读取这些完整实验现金记录的年度账户与投资辅助函数。
