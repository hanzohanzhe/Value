# 天气与可用出力

风光资产的可用出力由装机容量和其代表位置的天气共同计算。`capacity_mw` 为装机 MW，`availability` 为无量纲天气转换系数，`available_mw` 为可用功率，`available_mwh` 为单个运行时段的可用电量：

$$
\begin{aligned}
\mathtt{available\_mw}&=\mathtt{capacity\_mw}\times\mathtt{availability},\\
\mathtt{available\_mwh}&=\mathtt{available\_mw}\times\mathtt{period\_hours},\\
\mathtt{period\_hours}&=0.5\ \mathrm{h}.
\end{aligned}
$$

天气计算为市场出清提供供给上限，第 4、5、7 章的调度算法确定实际接纳电量。年度投资使用本章末尾的技术平均曲线和第 6 章的容量上限。

## 天气输入与空间采样

R029 以 2020–2024 年 ERA5 中相同月、日、小时的平均值表示各日历小时。源序列包含 43,848 个小时，移除两个闰日的 48 小时后，8,760 个保留日历小时各有五个观测值。取算术平均得到的全年序列用于各模型年。

风速先由每个源小时的矢量分量求模，再作日历平均。预处理先计算 `u100` 平方与 `v100` 平方之和的平方根，其日历均值记为 `wind_speed`，同时保留 `u100` 和 `v100`。太阳文件保存向下水平累计辐射 `ssrd`；R029 的两个文件分别为 `calendar_mean_wind_2020_2024.nc` 和 `calendar_mean_solar_2020_2024.nc`。

天气网格以 0.25° 分辨率覆盖英国及邻近海域。文件的坐标范围与数组大小为

| 输入 | 纬度范围 | 经度范围 | 纬度 × 经度 × 日 × 小时 |
|---|---|---|---|
| 太阳辐射 | 45°–65°N | 14°W–4°E | 81 × 73 × 365 × 24 |
| 100 m 风 | 46°–65°N | 14°W–5°E | 77 × 77 × 365 × 24 |

各代表点采用最近的网格纬度和经度。`point_series` 中，站点 `latitude`、`longitude` 与网格数组 `lats`、`lons` 均以度表示；`lat_index`、`lon_index` 分别选择坐标绝对差最小的位置，等距时取网格数组中的第一项：

$$
\begin{aligned}
\mathtt{lat\_index}&=\operatorname*{arg\,min}_{j}|\mathtt{lats}[j]-\mathtt{latitude}|,\\
\mathtt{lon\_index}&=\operatorname*{arg\,min}_{k}|\mathtt{lons}[k]-\mathtt{longitude}|.
\end{aligned}
$$

空间抽取接受纬度—经度—日—小时数组和时间—纬度—经度数组，将选定点按源顺序展平为逐时序列。空序列、掩码缺失值、非有限值或其他数组布局会终止天气载入。各站点的 `lat`、`lon` 由 `fleet.locations` 提供，`representative_sites` 将这些位置与 `fleet.json` 的机组名称对应。

## 逐时天气与半小时调度

天气值按时间戳的物理含义分配至调度时段。默认天气方法采用 `clock="v2"`，绑定中的 `time_convention` 优先；其余情况下，`GRIB_stepType="accum"` 表示截至该时间戳的逐时累计值，其他场采用瞬时约定。`hour_index` 将从零开始的半小时编号 `t` 映射为源索引 `index`，并在 `hours` 个源值后循环：

$$
\mathtt{index}[t]=\begin{cases}
(\lfloor t/2\rfloor+1)\bmod\mathtt{hours},&\text{accumulation\_end\_of\_hour},\\
\lfloor(t+1)/2\rfloor\bmod\mathtt{hours},&\text{instantaneous}.
\end{cases}
$$

截至 01:00 的小时累计量分配给从 00:00 和 00:30 开始的两个时段。瞬时规则将 00:00 样本分配给从 00:00 开始的时段，将 01:00 样本分配给从 00:30 和 01:00 开始的时段。太阳几何在每个接收时段的中点计算。

R029 日历平均文件声明瞬时输入，因此采用索引公式第二行。受支持的 `clock="v1"` 设置采用 `index = (t // 2) % hours`，每个源值用于连续两个半小时。这些索引规则作用于声明的源顺序，并包含从最后一小时至第一小时的循环。

## 风电曲线与损耗

风电可用系数由 3 m/s 切入、立方增长、恒定额定出力和切出上限组成。`hourly_unit_cf` 在输入提供 `wind_speed` 时读取该变量，其余情况下由 `u100`、`v100` 求矢量模。`wind_unit_output` 采用 20 单位出力尺度，结果除以 20 后得到无量纲小时系数 `hourly`。风速 `speed`、额定风速 `rated`、切出风速 `cut_out` 均以 m/s 表示：

$$
\mathtt{wind\_unit\_output}(\mathtt{speed})=\begin{cases}
0,&\mathtt{speed}<3\ \text{or}\ \mathtt{speed}>\mathtt{cut\_out},\\
20\dfrac{\mathtt{speed}^3-27}{\mathtt{rated}^3-27},&3\le\mathtt{speed}<\mathtt{rated},\\
20,&\mathtt{rated}\le\mathtt{speed}\le\mathtt{cut\_out}.
\end{cases}
$$

陆风采用 `rated=9.7`、`cut_out=25`，海风采用 `rated=10.5`、`cut_out=30`。恰好达到切出风速时维持额定出力，高于该值时出力为零。立方增长段先限定在 0–20，再转换为 `hourly`。

送出风电系数由已分配的 `hourly[index]` 乘以尾流、能量可用率和电气系数的乘积得到。默认 `loss_factors=true` 时，`method.multiplier(technology)` 从 `value_uk_vre_loss_factors_v1.json` 读取下列数值：

| 技术 | 尾流系数 | 能量可用率系数 | 电气系数 | `multiplier` |
|---|---|---|---|---|
| 陆上风电 | 0.95 | 0.97 | 0.98 | 0.90307 |
| 海上风电 | 0.88 | 0.945 | 0.98 | 0.814968 |

风速为 8 m/s 时，陆风曲线给出 0.5476061707，乘以 0.90307 得约 0.49453，对应 100 MW 装机的可用功率约为 49.453 MW。受支持的 `loss_factors=false` 设置取 `multiplier=1.0`，直接使用曲线出力。

## 水平辐射与光伏转换

光伏计算先将源小时辐射量表示为辐照度。`hourly_unit_cf` 将 `ssrd` 读为 J/m² 的 `raw`，返回 kW/m² 的 `hourly`，输入筛选和单位换算为

$$
\mathtt{hourly}=\begin{cases}
\mathtt{raw}/3{,}600{,}000,&3{,}600<\mathtt{raw}\le36{,}000{,}000,\\
0,&\text{otherwise}.
\end{cases}
$$

默认光伏方法采用 `plane_of_array=true` 和 0.83 的性能比。`clock="v2"` 且 `time_convention="accumulation_end_of_hour"` 时，在每个半小时中点将水平辐照度转换到朝南倾斜平面。R029 和 VALUE 101 等瞬时来源将水平辐照度直接乘以 0.83；`plane_of_array=false` 时，全部来源采用这一水平计算。`loss_factors=false` 将性能比设为 1.0。

阵列倾角由站点纬度确定。默认 `tilt_rule="jacobson-jadhav-2018"` 采用 [Jacobson 和 Jadhav（2018），Solar Energy 169，55–66](https://web.stanford.edu/group/efmh/jacobson/Articles/I/TiltAngles.pdf) 的 0°–65°N 多项式。在 `optimal_tilt_jacobson_jadhav` 中，`phi` 为北纬度数，函数返回的度数在 `plane_of_array` 中记为 `tilt`：

$$
\mathtt{tilt}=1.3793+\mathtt{phi}\times\bigl[1.2011+\mathtt{phi}\times(-0.014404+0.000080509\mathtt{phi})\bigr].
$$

倾角参数还支持 `tilt_rule="site_latitude"`，取纬度绝对值，以及 `tilt_rule="fixed"`，取 [0,90] 度内的 `fixed_tilt_deg`。三种规则均采用朝南平面。`PlaneOfArrayParameters` 给定 `albedo=0.2`、`solar_constant_w_m2=1361`、`max_zenith_deg=87`；允许的反照率范围为 [0,1]，太阳常数范围为 1,300–1,400 W/m²，天顶角阈值范围为 [80,90) 度。

## 太阳几何

太阳几何采用运行时段的 UTC 中点。`period_clock` 返回年内日 `day_of_year` 和小时 `utc_hours`，`day_angle` 计算以弧度表示的年角 `g`。对从零开始的时段 `t`，

$$
\begin{aligned}
\mathtt{day\_of\_year}&=(\lfloor t/48\rfloor\bmod365)+1,\\
\mathtt{utc\_hours}&=(t\bmod48)/2+0.25,\\
\mathtt{g}&=2\pi(\mathtt{day\_of\_year}-1)/365.
\end{aligned}
$$

赤纬和轨道修正由 `declination`、`equation_of_time_minutes`、`eccentricity_factor` 的下列系数计算。所得 `decl` 以弧度表示，时差以分钟表示，轨道距离因子为无量纲：

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

经度和时差确定当地太阳时及小时角。`longitude_deg` 以东经为正，`solar_time` 以小时表示，`omega` 以弧度表示。`incidence_cosines` 将纬度和倾角转换为弧度量 `phi`、`beta`，返回天顶角和入射角的余弦 `cos_z`、`cos_theta`：

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

## 散射分解与阵列平面辐照度

水平辐照度被分解为散射与直射分量。`plane_of_array` 将 `ghi_kw_m2` 的非负部分记为 kW/m² 的 `ghi`，`extraterrestrial_normal` 等于 `parameters.solar_constant_w_m2 / 1000.0 * eccentricity_factor(day_of_year)`，默认乘数为 1.361 kW/m²。`ghi` 为正且天顶角小于 87° 时，晴朗指数为

$$
\mathtt{kt}=\min\left(1,\max\left(0,\frac{\mathtt{ghi}}{\mathtt{extraterrestrial\_normal}\times\mathtt{cos\_z}}\right)\right),
$$

散射比例采用 [Erbs、Klein 和 Duffie（1982），Solar Energy 28(4)，293–302](https://www.sciencedirect.com/science/article/pii/0038092X82903024) 的逐时关系。`kd` 取决于无量纲晴朗指数 `kt`，`middle` 为中间区间的多项式值：

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

[Hay–Davies（1980）转换](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.irradiance.haydavies.html) 将直射、天空散射和地面反射辐照度合并。`dhi`、`bhi`、`dni` 分别为水平散射、水平直射和法向直射辐照度，单位为 kW/m²；`anisotropy`、`beam_ratio`、`sky_view`、`ground_view` 为无量纲，默认 `albedo` 为 0.2。阵列平面辐照度 `poa` 为

$$
\begin{aligned}
\mathtt{dhi}&=\mathtt{kd}\times\mathtt{ghi},\qquad \mathtt{bhi}=\mathtt{ghi}-\mathtt{dhi},\\
\mathtt{dni}&=\mathtt{bhi}/\mathtt{cos\_z},\\
\mathtt{anisotropy}&=\min(1,\max(0,\mathtt{dni}/\mathtt{extraterrestrial\_normal})),\\
\mathtt{beam\_ratio}&=\max(\mathtt{cos\_theta},0)/\mathtt{cos\_z},\\
\mathtt{cos\_beta}&=\cos(\pi\mathtt{tilt}/180),\\
\mathtt{sky\_view}&=(1+\mathtt{cos\_beta})/2,\\
\mathtt{ground\_view}&=(1-\mathtt{cos\_beta})/2,\\
\mathtt{beam}&=\mathtt{bhi}\times\mathtt{beam\_ratio},\\
\mathtt{sky\_diffuse}&=\mathtt{dhi}\times\bigl[\mathtt{anisotropy}\times\mathtt{beam\_ratio}\\
&\qquad +(1-\mathtt{anisotropy})\times\mathtt{sky\_view}\bigr],\\
\mathtt{ground}&=\mathtt{ghi}\times\mathtt{albedo}\times\mathtt{ground\_view},\\
\mathtt{poa}&=\mathtt{beam}+\mathtt{sky\_diffuse}+\mathtt{ground}.
\end{aligned}
$$

天顶角达到或超过 87° 或 `ghi` 为零时，取 `kt=0`、`kd=1`、`dhi=ghi`、`bhi=0`、`dni=0`、`anisotropy=0`、`beam_ratio=0`，所得 `poa` 保留散射和地面反射分量。调整参数后，条件中的 87° 改用选定的 `max_zenith_deg`。

阵列平面辐照度经性能比转换为出力系数，再取上限 1。默认参数下，`site_cf_by_source` 返回的无量纲系数 `values` 为

$$
\mathtt{values}=\min(0.83\mathtt{poa},1).
$$

出力系数上限在阵列平面转换之后施加。水平转换将性能比直接作用于 `hourly[index]`。以下算法覆盖风电、瞬时光伏和累计光伏输入：`ds` 为已打开的 NetCDF，`binding` 声明时间约定，`periods` 为所需半小时数，`method` 包含 `clock`、`loss_factors`、`plane_of_array`。

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
    values = np.minimum(values, 1.0)
return values
```

## 项目位置与天气混合

资产按技术和位置取得代表天气。英国模板列出 11 个光伏、11 个陆风代表点及 21 个海风代表点名称；R029 的 2025 年装机中，正容量资产分别为 11、11、18 个。运行资产在第 2 章的初始筛选时完成映射，规划项目在投运前获得代表点。

规划项目的显式位置优先。`attach_project_weather` 先读取项目的 `latitude`、`longitude`，再按 `physical_project_id` 查找原始 REPD 行，坐标仍缺失时按站名查找。有限坐标被分配至同技术最近的代表点。`nearest_site` 将项目坐标转为弧度量 `lat1`、`lon1`，将代表点坐标转为 `lat2`、`lon2`，以 km 表示的距离为

$$
\begin{aligned}
\mathtt{a}&=\sin^2\frac{\mathtt{lat2}-\mathtt{lat1}}{2}\\
&\quad+\cos(\mathtt{lat1})\times\cos(\mathtt{lat2})\times\sin^2\frac{\mathtt{lon2}-\mathtt{lon1}}{2},\\
\mathtt{distance}&=2\arcsin\sqrt{\mathtt{a}}\times6{,}371\ \mathrm{km}.
\end{aligned}
$$

等距时选择声明顺序中的第一个代表点。缺少坐标的规划光伏、陆风项目采用 REPD 地区与下表的城市映射。初始运行资产读取也使用该表，在初始步骤中地区优先于坐标。

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

位置缺失的项目在投运时获得按容量加权的天气组合。`commissioned_project_weather` 先将代表点运行容量累加为 `stock[name]`，再加入当年到期、具有显式位置的全部项目，随后按技术汇总其余项目。`total_stock` 为相应运行 MW，`total_new` 为新增 MW，`names` 为该技术的代表点列表：

```text
total_stock = sum(stock[name] for name in names)
total_new = sum(p.capacity_mw for p in projects)
if total_new <= 0 or total_stock <= 0:
    weights = {names[0]: 1.0}
else:
    names.sort()
    remaining, weights = total_new, {}
    for i, name in enumerate(names):
        amount = remaining if i == len(names) - 1 else total_new * stock[name] / total_stock
        remaining -= amount
        weights[name] = amount / total_new if amount > 1e-6 else 0.0
```

同组位置缺失的项目获得相同的 `weights`。分配量超过 0.000001 MW 时，天气权重取 `amount / total_new`；较小分配量取零权重。字母排序和最后一点的余量确定浮点分配顺序，总运行容量为零时将第一代表点的权重设为 1。

投运后，资产保留其 `weather_source_weights`。`source_weights` 优先读取这一显式映射，再读取单一 `weather_source_asset_id`，随后依次按资产、指定机组、投资所有者、源代理和基础资产标识匹配。来源名称须对应同技术代表点，权重须为有限非负值，其和至多为 1 加 0.000000000001。若 `deficit = 1.0 - sum(weights.values())` 超过该容差，`cohort` 取正的有限 `weather_allocation_cohort_mw`，`skipped` 计数零权重；接收条件为 `deficit <= skipped * 1e-6 / cohort + 1e-12`。

资产可用系数为各来源曲线的加权和。`_map_lineages` 对每个来源的 `values` 应用 `weights`；下标 `name` 用于选择对应来源数组，所得 `combined` 为

$$
\mathtt{combined}[t]=\sum_{\mathtt{name}}\mathtt{weights}[\mathtt{name}]\times\mathtt{values}_{\mathtt{name}}[t].
$$

分区分配在保留天气曲线的同时拆分资产物理容量。`StagedBidAtCostPSM` 将 `capacity_mw` 乘以各区 `share`，份额之和为 1；储能的 `charge_power_mw`、`discharge_power_mw`、`energy_capacity_mwh`、`initial_soc_mwh` 也乘以同一份额。第 7 章定义资产至区域的映射与网络约束。

可选接口 `REPDERA5AggregatedWeather.build` 在各所有者—技术—区域组内合并调用方提供的项目曲线。对分配记录 `rows`，`total` 为总 MW，`values` 为项目无量纲曲线，`weighted` 为该组曲线：

$$
\begin{aligned}
\mathtt{total}&=\sum_{\mathtt{row}\in\mathtt{rows}}\mathtt{row.capacity\_mw},\\
\mathtt{weighted}[t]&=\sum_{\mathtt{row}\in\mathtt{rows}}\mathtt{values}_{\mathtt{row}}[t]\times\frac{\mathtt{row.capacity\_mw}}{\mathtt{total}}.
\end{aligned}
$$

这一聚合要求项目曲线等长、全部有限且位于 [0,1]，并要求 `total` 为正。`weighted` 乘以总 MW 等于各项目可用功率之和。分区调度接口也可将代表曲线直接用于资产各区分配部分。

## 技术平均投资曲线

年度扩张为光伏、陆风和海风各使用一条技术平均曲线。输入将 2022 年 ERA5 数据与 `sa.csv`、`wa.csv`、`we.csv` 中的机组及项目设定结合；每个 public2 文件包含 8,760 个小时值，声明 `interval_minutes=60`，各值按源行序用于连续两个半小时。

得到的 `availability` 为无量纲量，用于第 6 章的 `peak` 和年度容量余量计算。投资规则直接使用这些曲线，调度可用出力则采用上文的站点采样、时间分配、转换与损耗步骤。
