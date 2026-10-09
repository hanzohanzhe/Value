# 天气与可用出力

VALUE 用资产容量和代表点天气计算各资产逐时段可用的风光电量。调度字段 `available_mw` 和 `available_mwh` 分别表示可用功率（MW）和时段电量（MWh）；`capacity_mw` 为装机功率，`availability` 为天气决定的无量纲出力系数，`period_hours` 为时段长度。对每个资产和时段，

$$
\begin{aligned}
\mathtt{available\_mw}&=\mathtt{capacity\_mw}\times\mathtt{availability},\\
\mathtt{available\_mwh}&=\mathtt{available\_mw}\times\mathtt{period\_hours},\\
\mathtt{period\_hours}&=0.5\ \mathrm{h}.
\end{aligned}
$$

市场出清在上述可用电量范围内接纳发电。年度扩张采用下文的技术平均投资曲线，或实验性物理可用出力规则。

## 天气序列与代表点采样

R029 将 2020–2024 年 ERA5 小时观测按月、日、小时取算术平均，形成各模型年复用的 365 日气候态。原始序列包含 43,848 小时。删除两次 2 月 29 日的 48 小时后，每个保留的日历小时有五个观测，平均后得到 8,760 小时。

风速在原始小时尺度先由 100 m 风矢量求模，再作日历平均：`wind_speed` 等于 `u100` 的平方与 `v100` 的平方之和的平方根。文件保留三个字段。`hourly_unit_cf` 优先读取 `wind_speed`；输入只有 `u100` 和 `v100` 时，在输入时刻计算矢量模长。

气候态保留英国及附近海域的 0.25° 网格。太阳文件以 `ssrd` 表示向下太阳辐射，风文件提供 100 m 风信息；数组的空间与时间尺寸如下。

| 输入 | 纬度范围 | 经度范围 | 纬度 × 经度 × 日 × 小时 |
|---|---|---|---|
| 太阳辐射 | 45°–65°N | 14°W–4°E | 81 × 73 × 365 × 24 |
| 100 m 风 | 46°–65°N | 14°W–5°E | 77 × 77 × 365 × 24 |

每个代表点采用天气网格中最近的纬度和经度。`point_series` 从坐标数组 `lats`、`lons` 中选择 `lat_index`、`lon_index`，站点坐标 `latitude`、`longitude` 以度表示：

$$
\begin{aligned}
\mathtt{lat\_index}&=\operatorname*{arg\,min}_{j}|\mathtt{lats}[j]-\mathtt{latitude}|,\\
\mathtt{lon\_index}&=\operatorname*{arg\,min}_{k}|\mathtt{lons}[k]-\mathtt{longitude}|.
\end{aligned}
$$

`point_series` 接受“纬度—经度—日—小时”和“时间—纬度—经度”数组，将选定格点展平为小时序列。修正口径读取 `time_convention`；标记为 `GRIB_stepType=accum` 的场采用小时区间末累计值，缺少两项声明的场采用瞬时值约定。`hour_index` 按从零开始的半小时编号 `t` 和源小时数 `hours` 生成 `index`：

$$
\mathtt{index}[t]=\begin{cases}
(\lfloor t/2\rfloor+1)\bmod\mathtt{hours},&\text{accumulation\_end\_of\_hour},\\
\lfloor(t+1)/2\rfloor\bmod\mathtt{hours},&\text{instantaneous}.
\end{cases}
$$

累计值约定将截至 01:00 的小时辐射量赋给始于 00:00 和 00:30 的两个时段，太阳几何位置按接收时段的中点计算。瞬时值约定将 00:00 的样本赋给 00:00 时段，将 01:00 的样本赋给 00:30 和 01:00 时段。

论文复现口径采用 `index = (t // 2) % hours`，每个源小时值连续用于两个半小时。原始 GBP1 天气按年内日序号形成 366 日、8,784 小时序列，使用其中前 8,760 小时。R029 的 8,760 小时日历气候态在当前元数据中采用瞬时值约定。实验性 R029 调度路径保留逐小时重复时钟及原始发电曲线。

## 风电转换与损失

风电可用系数采用切入、立方增长、额定和切出四段关系。`wind_unit_output` 用 20 单位标度表达功率曲线，`hourly_unit_cf` 将结果除以 20，得到无量纲小时系数 `hourly`。风速 `speed`、额定风速 `rated` 和切出风速 `cut_out` 均以 m/s 表示：

$$
\mathtt{wind\_unit\_output}(\mathtt{speed})=\begin{cases}
0,&\mathtt{speed}<3\ \text{or}\ \mathtt{speed}>\mathtt{cut\_out},\\
20\dfrac{\mathtt{speed}^3-27}{\mathtt{rated}^3-27},&3\le\mathtt{speed}<\mathtt{rated},\\
20,&\mathtt{rated}\le\mathtt{speed}\le\mathtt{cut\_out}.
\end{cases}
$$

陆风采用 `rated = 9.7`、`cut_out = 25`，海风采用 `rated = 10.5`、`cut_out = 30`。修正口径将 `hourly[index]` 乘以 `multiplier`，其数值为 `value_uk_vre_loss_factors_v1.json` 中尾流、能量可用率和电气系数的乘积。

| 技术 | 尾流系数 | 能量可用率系数 | 电气系数 | `multiplier` |
|---|---|---|---|---|
| 陆上风电 | 0.95 | 0.97 | 0.98 | 0.90307 |
| 海上风电 | 0.88 | 0.945 | 0.98 | 0.814968 |

风速为 8 m/s 时，陆风原始系数为 0.5476061707，修正后约为 0.49453，因此 100 MW 资产的可用功率约为 49.453 MW。论文复现口径采用原始曲线，损失乘数为 1；独立的 R029 实验路径也保留原始曲线。

## 太阳辐射与阵列平面转换

修正口径将 ERA5 水平累计辐射转换为朝南倾斜面的辐照度，再应用 0.83 的性能比和 1 的出力系数上限。`hourly_unit_cf` 将 `ssrd` 读入 `raw`，单位为 J/m²，并将各值转换为以 kW/m² 表示的 `hourly`：

$$
\mathtt{hourly}=\begin{cases}
\mathtt{raw}/3{,}600{,}000,&3{,}600<\mathtt{raw}\le36{,}000{,}000,\\
0,&\text{otherwise}.
\end{cases}
$$

阵列倾角由纬度决定。`optimal_tilt_jacobson_jadhav` 中的 `phi` 为北纬度数，该函数采用 [Jacobson 和 Jadhav（2018），Solar Energy 169，55–66](https://web.stanford.edu/group/efmh/jacobson/Articles/I/TiltAngles.pdf) 的 0°–65°N 拟合式。返回值在 `plane_of_array` 中记为 `tilt`，单位为度：

$$
\mathtt{tilt}=1.3793+\mathtt{phi}\times\bigl[1.2011+\mathtt{phi}\times(-0.014404+0.000080509\mathtt{phi})\bigr].
$$

太阳几何位置按半小时时段中点计算。`period_clock` 由从零开始的时段编号 `t` 生成 `day_of_year` 和 `utc_hours`，`day_angle` 给出年角 `g`。`declination`、`equation_of_time_minutes` 和 `eccentricity_factor` 采用以下实现系数，输出依次为以弧度表示的赤纬 `decl`、以分钟表示的时差和无量纲轨道距离系数：

$$
\begin{aligned}
\mathtt{day\_of\_year}&=(\lfloor t/48\rfloor\bmod365)+1,\\
\mathtt{utc\_hours}&=(t\bmod48)/2+0.25,\\
\mathtt{g}&=2\pi(\mathtt{day\_of\_year}-1)/365.
\end{aligned}
$$

$$
\begin{aligned}
\mathtt{decl}={}&0.006918-0.399912\cos\mathtt{g}+0.070257\sin\mathtt{g}\\
&-0.006758\cos2\mathtt{g}+0.000907\sin2\mathtt{g}\\
&-0.002697\cos3\mathtt{g}+0.00148\sin3\mathtt{g}.
\end{aligned}
$$

$$
\begin{aligned}
\mathtt{equation\_of\_time\_minutes}({}&\mathtt{day\_of\_year})=\\
229.18\bigl(&0.000075+0.001868\cos\mathtt{g}-0.032077\sin\mathtt{g}\\
&-0.014615\cos2\mathtt{g}-0.04089\sin2\mathtt{g}\bigr).
\end{aligned}
$$

$$
\begin{aligned}
\mathtt{eccentricity\_factor}({}&\mathtt{day\_of\_year})=\\
&1.000110+0.034221\cos\mathtt{g}+0.001280\sin\mathtt{g}\\
&+0.000719\cos2\mathtt{g}+0.000077\sin2\mathtt{g}.
\end{aligned}
$$

经度与时差决定当地太阳时 `solar_time` 和小时角 `omega`。`incidence_cosines` 将纬度、倾角转换为以弧度表示的 `phi`、`beta`；返回值分别记为 `cos_z` 和 `cos_theta`，表示天顶角与入射角的余弦：

$$
\begin{aligned}
\mathtt{solar\_time}={}&\mathtt{utc\_hours}+\mathtt{longitude\_deg}/15\\
&+\mathtt{equation\_of\_time\_minutes}(\mathtt{day\_of\_year})/60,\\
\mathtt{omega}={}&\pi(\mathtt{solar\_time}-12)/12,\\
\mathtt{cos\_z}={}&\sin(\mathtt{phi})\times\sin(\mathtt{decl})\\
&+\cos(\mathtt{phi})\times\cos(\mathtt{decl})\times\cos(\mathtt{omega}),\\
\mathtt{cos\_theta}={}&\sin(\mathtt{phi}-\mathtt{beta})\times\sin(\mathtt{decl})\\
&+\cos(\mathtt{phi}-\mathtt{beta})\times\cos(\mathtt{decl})\times\cos(\mathtt{omega}).
\end{aligned}
$$

水平辐照度 `ghi` 采用 [Erbs、Klein 和 Duffie（1982），Solar Energy 28(4)，293–302](https://www.sciencedirect.com/science/article/pii/0038092X82903024) 的小时关系分解为直射和散射分量。`extraterrestrial_normal` 等于 1.361 kW/m² 乘以 `eccentricity_factor(day_of_year)`。当 `ghi` 为正且天顶角小于 87° 时，晴朗指数 `kt` 与散射比例 `kd` 为

$$
\mathtt{kt}=\min\left(1,\max\left(0,\frac{\mathtt{ghi}}{\mathtt{extraterrestrial\_normal}\times\mathtt{cos\_z}}\right)\right),
$$

$$
\begin{aligned}
\mathtt{middle}={}&0.9511-0.1604\mathtt{kt}+4.388\mathtt{kt}^2\\
&-16.638\mathtt{kt}^3+12.336\mathtt{kt}^4,\\
\mathtt{kd}={}&\begin{cases}
1-0.09\mathtt{kt},&\mathtt{kt}\le0.22,\\
\mathtt{middle},&0.22<\mathtt{kt}\le0.80,\\
0.165,&\mathtt{kt}>0.80.
\end{cases}
\end{aligned}
$$

[Hay–Davies（1980）倾斜面转换](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.irradiance.haydavies.html) 汇总直射、各向异性天空散射及地面反射。`dhi`、`bhi`、`dni` 分别表示水平散射、水平直射和法向直射辐照度，单位为 kW/m²；`anisotropy`、`beam_ratio`、`sky_view`、`ground_view` 均为无量纲系数。采用 `albedo = 0.2` 时，阵列平面辐照度 `poa` 为

$$
\begin{aligned}
\mathtt{dhi}&=\mathtt{kd}\times\mathtt{ghi},\qquad \mathtt{bhi}=\mathtt{ghi}-\mathtt{dhi},\\
\mathtt{dni}&=\mathtt{bhi}/\mathtt{cos\_z},\\
\mathtt{anisotropy}&=\min(1,\max(0,\mathtt{dni}/\mathtt{extraterrestrial\_normal})),\\
\mathtt{beam\_ratio}&=\max(\mathtt{cos\_theta},0)/\mathtt{cos\_z},\\
\mathtt{sky\_view}&=(1+\cos\mathtt{beta})/2,\\
\mathtt{ground\_view}&=(1-\cos\mathtt{beta})/2,\\
\mathtt{beam}&=\mathtt{bhi}\times\mathtt{beam\_ratio},\\
\mathtt{sky\_diffuse}&=\mathtt{dhi}\times\bigl[\mathtt{anisotropy}\times\mathtt{beam\_ratio}\\
&\qquad +(1-\mathtt{anisotropy})\times\mathtt{sky\_view}\bigr],\\
\mathtt{ground}&=\mathtt{ghi}\times\mathtt{albedo}\times\mathtt{ground\_view},\\
\mathtt{poa}&=\mathtt{beam}+\mathtt{sky\_diffuse}+\mathtt{ground}.
\end{aligned}
$$

天顶角达到或超过 87°，或 `ghi` 为零时，计算设定 `kd = 1`、`dhi = ghi`、`bhi = 0`、`dni = 0`、`anisotropy = 0`、`beam_ratio = 0`。同一阵列平面求和式保留散射和地面反射。对于修正口径的累计输入，`site_cf_by_source` 将 `poa` 转换为出力系数 `values`：

$$
\mathtt{values}=\min(0.83\mathtt{poa},1).
$$

累计输入约定采用阵列平面转换。修正口径的瞬时输入，包括当前 R029 日历气候态和 VALUE 101 合成输入，直接将水平辐照度乘以 0.83。论文复现口径和实验性 R029 路径保留水平转换，乘数为 1。以下伪代码采用实现中的函数名和变量名：

```text
hourly, evidence = hourly_unit_cf(ds, technology, latitude, longitude, binding)
index = hour_index(periods, len(hourly), method.clock, evidence["time_convention"])
values = hourly[index]
poa_applied = False
if technology == "solar" and method.plane_of_array:
    poa_applied, reason = plane_of_array_applies(method, evidence["time_convention"])
    if poa_applied:
        values, poa_evidence = plane_of_array(values, latitude_deg=latitude,
            longitude_deg=longitude, parameters=plane_of_array_parameters())
multiplier = method.multiplier(technology)
values = values * multiplier
if poa_applied:
    values = minimum(values, 1.0)
return values
```

## 与观测负荷率的比较

GBP1 代表点天气计算可与 [DUKES 表 6.3](https://www.gov.uk/government/statistics/renewable-sources-of-energy-chapter-6-digest-of-united-kingdom-energy-statistics-dukes) 的全国负荷率比较。下表模型值为各代表点在 17,520 个半小时时段内、弃电前可用出力系数的非加权均值。DUKES 以全国发电量除以年初和年末装机容量的均值及全年小时数；两项定义共同确定比较范围。

| 技术 | GBP1 修正口径 | DUKES 2019–2024 均值 | DUKES 2020–2024 均值 | 修正值 / 2020–2024 均值 | GBP1 论文复现口径 |
|---|---|---|---|---|---|
| 陆上风电 | 0.4026 | 0.2593 | 0.2582 | 1.56 | 0.4458 |
| 海上风电 | 0.4913 | 0.4016 | 0.4009 | 1.23 | 0.6028 |
| 光伏 | 0.1065 | 0.1033 | 0.1025 | 1.04 | 0.1201 |

修正口径的风电值仍高于全国观测均值。计算采用原始 ERA5 风速、各风电技术的一条功率曲线及固定损失乘数；DUKES 则记录实际机组组合的发电量，包含调度和机组构成的影响。该表为上述参数设定提供外部比较。

光伏计算对气候态辐射序列执行非线性分解和倾斜面转换。GBP1 代表点得到的散射比例约为 0.63–0.75，阵列平面与水平面辐射量之比约为 1.05–1.10。这些量对应所采用的气候态及转换，特定年份的模拟需要相应年份的天气输入。

## 项目位置、资产聚合与分区

风光项目通过同技术代表点建立空间天气对应。英国初始模板包含 11 个光伏和 11 个陆风代表点，以及 21 个海风代表点名称；R029 的 2025 年初始设定包含 11 个光伏、11 个陆风和 18 个海风正容量资产。代表点位置由 `fleet.locations` 和机组名称共同给出。

具有明确坐标的项目采用同技术的最近代表点。`nearest_site` 将项目纬度、经度转换为以弧度表示的 `lat1`、`lon1`，候选点坐标记为 `lat2`、`lon2`，球面距离为

$$
\begin{aligned}
\mathtt{a}&=\sin^2\frac{\mathtt{lat2}-\mathtt{lat1}}{2}\\
&\quad+\cos(\mathtt{lat1})\times\cos(\mathtt{lat2})\times\sin^2\frac{\mathtt{lon2}-\mathtt{lon1}}{2},\\
\mathtt{distance}&=2\arcsin\sqrt{\mathtt{a}}\times6{,}371\ \mathrm{km}.
\end{aligned}
$$

距离相同时，映射保留候选表中先出现的点。缺少明确位置的光伏和陆风项目先按 REPD 地区映射至下表代表点。

| REPD 地区 | 代表点 |
|---|---|
| East Midlands | Nottingham |
| Eastern | Ipswich |
| London | London |
| North East | Newcastle |
| North West | Manchester |
| Scotland | Edinburgh |
| South East | Portsmouth |
| South West | Bournemouth |
| Wales | Cardiff |
| West Midlands | Birmingham |
| Yorkshire and Humber | Sheffield |

其余未定位项目按同技术既有容量分配。`commissioned_project_weather` 中的 `stock[name]` 为代表点运营容量，`total_stock` 为该技术各点之和；同年投运且位置明确的项目先计入容量。其余各点获得 `total_new * stock[name] / total_stock` MW，最后一点接收余量。总容量为零时选择第一个代表点；分配量小于或等于 0.000001 MW 时，该份额的天气权重为零。

资产沿用投运时确定的 `weather_source_weights`。`source_weights` 提供映射 `weights`，`_map_lineages` 按各来源曲线 `values` 及其 `weight` 求和，得到无量纲曲线 `combined`：

$$
\mathtt{combined}[t]=\sum_{\mathtt{name}}\mathtt{weights}[\mathtt{name}]\times\mathtt{values}_{\mathtt{name}}[t].
$$

天气读取器检查来源技术及权重的有限性、非负性。权重之和为 1，并保留 0.000001 MW 分配规则产生的有界缺口。后续容量变化沿用这些权重。

当前全国市场将年度资产映射到固定的市场主体与代表天气拓扑。映射优先采用相同资产编号，其次选择同技术且地区匹配的主体，并按已有映射容量分配；容量为零时依次采用模板容量和等权分配。每个市场主体的最终容量等于归属于它的年度资产容量之和。

分区运行按 `zone_share` 划分资产容量，保留其天气曲线和经济所有者。`StagedBidAtCostPSM` 将各区资源的 `capacity_mw` 设为原 `resource.capacity_mw` 乘以 `share`，各份额之和为 1。储能的 `charge_power_mw`、`discharge_power_mw`、`energy_capacity_mwh`、`initial_soc_mwh` 采用相同乘法，保持全国总量。

独立聚合接口 `REPDERA5AggregatedWeather.build` 在同一所有者、技术和分区内，合并预先计算的项目曲线。分配记录集合记为 `rows`，其 `capacity_mw` 之和为 `total`，单位为 MW；各来源曲线记为 `values`，组合曲线 `weighted` 为

$$
\begin{aligned}
\mathtt{total}&=\sum_{\mathtt{row}\in\mathtt{rows}}\mathtt{row.capacity\_mw},\\
\mathtt{weighted}[t]&=\sum_{\mathtt{row}\in\mathtt{rows}}\mathtt{values}_{\mathtt{row}}[t]\times\frac{\mathtt{row.capacity\_mw}}{\mathtt{total}}.
\end{aligned}
$$

聚合接口接受同长度、有限且位于 [0,1] 的曲线及正总容量，项目曲线由调用方提供。当前分区执行路径将代表点曲线复制到资产的各区域份额。

## 年度风光容量上限

通用投资规则按峰值需求与各技术 CSV 曲线的峰值计算可新增容量空间。`canonical_psm_data` 中，`demand` 为时段电量（MWh），`period_hours` 为 0.5 h，`availability` 为无量纲技术曲线，`capacity_by_technology` 为运营容量（MW）。`vre-expansion-cap` 模块将所得 `headroom` 乘以 `expansion.vre_cap_fraction`，该比例记为 `fraction`，得到以 MW 表示的年度上限 `limits`：

$$
\begin{aligned}
\mathtt{peak}&=\max_t\mathtt{availability}[t],\\
\mathtt{headroom}[\mathtt{technology}]&=\max\left(0,\frac{\max_t\mathtt{demand}[t]}{\mathtt{period\_hours}\times\max(\mathtt{peak},10^{-12})}\right.\\
&\qquad\left.-\mathtt{capacity\_by\_technology}[\mathtt{technology}]\right),\\
\mathtt{limits}[\mathtt{technology}]&=\mathtt{fraction}\times\mathtt{headroom}[\mathtt{technology}],\\
\mathtt{fraction}&=0.20.
\end{aligned}
$$

技术平均投资曲线由 2022 年 ERA5 资料结合机组和项目假设构成。原始光伏 `sa.csv` 含 8,761 行，最后一行为 `2023-01-01T00:00:00` 的零值；陆风 `wa.csv` 和海风 `we.csv` 各含 8,760 行。Public2 删除光伏末行并声明 `interval_minutes=60`，将剩余各值重复用于两个半小时时段后，与原年度截取所得数值一致。投资读取器沿用 CSV 行序和 ERA5 区间末时间戳；这些曲线直接用于投资计算，调度则采用上文的天气时钟、损失及太阳倾斜面转换。

峰值需求为 1,000 MW、`peak = 0.8`、运营容量为 300 MW 时，`headroom` 为 950 MW，年度上限为 190 MW。曲线峰值为零时，分母下界为 0.000000000001。

实验函数 `thesis96_vre_annual_expansion_cap` 按负净需求时段数确定年度新增容量上限。其三个全年输入为：实际需求时段电量 `demand_mwh`，全部运营风光资产的物理可用电量 `operational_vre_available_mwh`，以及待扩张技术每 MW 可用电量 `generation_per_mw_mwh`。前两者单位为 MWh/时段，第三者为 MWh/MW/时段。技术曲线由该技术运营资产的可用电量除以其总 MW 容量得到；技术容量为零时曲线为零。

函数从需求中扣除风光可用电量得到 `net`，并将 `net < 0` 的时段数记为 `already_negative`。默认 `negative_threshold = 200` 个半小时时段，对应 100 小时。达到该时段数时新增上限为零；其余情况下，每个合格时段产生容量临界值 `net / profile`，其中 `profile` 为输入的 `generation_per_mw_mwh`。算法取指定的顺序统计量，乘以 `cap_fraction = 0.20`：

```text
demand = demand_mwh
available = operational_vre_available_mwh
profile = generation_per_mw_mwh
net = demand - available
already_negative = count_nonzero(net < 0)
if already_negative >= negative_threshold:
    return 0.0
transitions = net[(net >= 0) & (profile > 0)] / profile[(net >= 0) & (profile > 0)]
needed = negative_threshold - already_negative
if len(transitions) < needed:
    return 0.0
critical = partition(transitions, needed - 1)[needed - 1]
return cap_fraction * critical
```

`critical` 为第 `needed` 小的容量临界值，单位为 MW。新增容量等于某个临界值时，对应净需求恰为零；继续增加容量后，该时段进入负净需求。合格临界值数量不足时，函数按既定规则返回零。随 VALUE 0.7.0-alpha.1 发布的 R029 public2 包提供构造这些输入所需的需求、资产和天气。第 6 章说明实验路径的执行覆盖范围。

## 数据与实现对应

`calendar_mean_solar_2020_2024.nc` 和 `calendar_mean_wind_2020_2024.nc` 提供 R029 日历气候态。`site_weather` 读取代表点序列并应用所选时钟与转换，`solar_irradiance` 计算阵列平面辐射。`value_uk_vre_loss_factors_v1.json` 提供转换参数，`value_uk_vre_cf_disclosure_v1.json` 记录负荷率比较。`doctoral_weather` 为实验路径提供固定转换，`doctoral_weather_mapping` 管理项目位置和混合天气权重。

`scheme_c_native_psm` 将容量聚合到全国市场主体，`staged_psm` 按区域划分容量。年度上限的通用峰值规则由 `canonical_psm_data` 和 `v2_module_definitions` 提供。实验性净需求阈值函数 `thesis96_vre_annual_expansion_cap` 定义于 `doctoral_policy`。
