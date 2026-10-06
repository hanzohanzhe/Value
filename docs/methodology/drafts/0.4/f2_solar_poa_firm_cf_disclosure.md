# Solar plane-of-array irradiance, nuclear end month, natural-flow hydro and the CF disclosure (F2 draft for methodology 0.4)

Status: draft written with construction unit F2 (2026-10-06), following decisions
A9, A10, A13 and A14 of `docs/dev/P0_DECISIONS.md`. It supersedes the solar,
nuclear and hydro statements of `p05b_corrected_data.md` sections 3 and 4 where
they differ. To be merged into `core_weather.md`, `datasets.md` and
`national_alternatives.md` (en, zh) when the 0.4 edition is generated.
Everything below applies to the corrected profile (`value-corrected`) only; the
doctoral reproduction profile (`doctoral-lineage-0.6.0a2`) is unchanged.

## 1 Solar: horizontal irradiance to the module plane (A13, `p05.solar-plane-of-array`)

The PV performance ratio (PR 0.83, A9) is defined on plane-of-array (POA)
irradiance. Before A13 the corrected profile multiplied it by horizontal
irradiance (ERA5 `ssrd / 3.6e6`, GHI in kW m-2), which omits the gain of a tilted
module. The corrected profile now computes, for every half-hour period:

| Step | Model | Parameters | Source |
|---|---|---|---|
| Solar geometry | Spencer (1971) declination, equation of time and eccentricity factor; hour angle from local solar time = UTC + longitude / 15 h + equation of time; incidence angle on an equator-facing plane | geometry at the **period midpoint** of a 365-day UTC model year (period `t`: day `t // 48 + 1`, UTC hour `(t mod 48) / 2 + 0.25`); site latitude and longitude of the representative site | Spencer 1971; Iqbal 1983; Duffie & Beckman 2013 eqs 1.6.5, 1.6.7 |
| Decomposition | Erbs, Klein & Duffie (1982) hourly diffuse fraction `kd(kt)`, `kt = GHI / (I0n cos z)` clipped to [0, 1] | solar constant 1361 W m-2 x eccentricity factor | Erbs et al. 1982; Kopp & Lean 2011 |
| Transposition | Hay & Davies (1980): beam x `Rb` + diffuse x (`Ai Rb + (1 - Ai)(1 + cos tilt)/2`), `Ai = DNI / I0n`; ground reflection `GHI x albedo x (1 - cos tilt)/2` | albedo 0.2; south-facing | Hay & Davies 1980; Duffie & Beckman 2013; Loutzenhiser et al. 2007 |
| Tilt | annual-optimal fixed tilt for the site latitude, northern-hemisphere fit `tilt = 1.3793 + lat (1.2011 + lat (-0.014404 + lat 0.000080509))` | about 35.7-37.7 deg for the GBP1 sites (50.7-56.0 N) | Jacobson & Jadhav 2018 |
| Low sun | zenith above 87 deg or GHI = 0: no beam; the GHI is treated as isotropic diffuse | - | - |
| Capacity factor | `min(POA x PR, 1)` | PR 0.83 | A9 (Taylor et al. 2015 and others) |

Clock. Under weather v2 (`p05.weather-time-convention`) the ERA5 accumulation
served to period `t` is the one stamped `t // 2 + 1`, i.e. the hour that
contains the period. The geometry is evaluated at the period midpoint, which
lies inside that accumulation hour; both half-hours of an hour share the hourly
GHI but have their own sun position. With a horizontal plane (tilt 0) the
procedure returns GHI exactly for every period (tested), so the transposition
redistributes energy by angle and never invents it.

Scope. The transposition is applied to an ERA5 hourly **accumulation** on the v2
clock (GRIB `stepType = accum` or a declared `time_convention:
accumulation_end_of_hour`). A solar source without that convention keeps the
horizontal ratio, and the site evidence says why:

* VALUE 101 (synthetic teaching samples, about 1 kW m-2 at a December noon at
  52 N, which no physical sky produces) - not transposed;
* R029 public1 (`calendar_mean_solar_2020_2024.nc`): its `ssrd` carries neither
  a GRIB step type nor a declared convention, so P0-5b already reads it as
  instantaneous and it is not transposed either. GBP1 public2 declares the ERA5
  convention.

Parameters and citations are in
`gridform_core/data/weather/value_uk_vre_loss_factors_v1.json`
(`solar_plane_of_array`; PENDING AUTHOR REVIEW for the model choices, the PR
itself was accepted in A9). Code: `gridform_core/solar_irradiance.py`,
`site_weather.site_cf_by_source`.

Result on GBP1 public1 (ERA5 2020-2024 climatology, 11 solar sites): annual GHI
about 1,080 kWh m-2 at London; POA/GHI 1.05-1.10 by site; annual diffuse
fraction 0.63-0.75; representative-site mean CF **0.0997 -> 0.1065** (+6.9 %).
Sensitivity (not used): a tilt equal to the site latitude (the other rule A13
allows) gives 0.1012, because a 51-56 deg plane loses more sky diffuse than it
gains beam in the diffuse-rich UK climate.

Disclosure. GBP1 weather is a multi-year average climatology (finding P6-09).
Averaging smooths the hourly clearness index (London: energy-weighted mean kt
0.47, maximum 0.73, no clear-sky hours), so the Erbs correlation assigns a
larger diffuse share than single-year hourly ERA5 would, and the tilt gain is
smaller than in a real year. With the same code a synthetic clear-sky year at
51.5 N (kt 0.65 in every daylight period, diffuse fraction 0.34) gains 33 % at
the same tilt (tested within 15-35 %). This is reported, not corrected.

## 2 Nuclear: retirement by month for every station (A10, `p05.nuclear-generation-end-month`)

Station load factors are unchanged and were approved by the author (A14): PRIS
2019-2024 means Heysham 1 66.8 %, Hartlepool 68.9 %, Heysham 2 75.2 %, Torness
79.2 %, Sizewell B 80.1 %, rescaled from PRIS reference power to the model's
EDF capacity, applied as a constant derate. A station whose announced
generation end has a month is zero from the first period of the next month in
that year. The station policy file gives only "2030" for Heysham 2 and Torness,
so the corrected profile takes the month from `generation_end_month_overrides`
of `gridform_core/data/nuclear/value_uk_firm_availability_v1.json` (2030-03,
reference statistics 1.6): all four AGR stations are zero from period 4,320 of
2030 (1 April 00:00 UTC). Sizewell B ("2055", no month) runs the whole year.

## 3 Natural-flow hydro: DUKES load factor and seasonal shape (A14, `p05.hydro-dukes-load-factor`)

Availability = 0.3487 (DUKES 2026 table 6.3, natural-flow hydro, standard basis,
2019-2024 mean) x a stepped monthly shape derived from the Energy Trends 6.1
quarterly load factors 2019-2024: January-March 1.3851, April-June 0.6582,
July-September 0.6776, October-December 1.2791 (arithmetic mean of the 12
months = 1, as A14 specifies). On the 365-day calendar the period-weighted mean
of the shape is 0.99883, so the modelled annual load factor is 0.3483. GBP1
carries 2,000 MW: 6.10 TWh per year against the DUKES 6.2 2019-2024 mean of
5.77 TWh (+5.8 %, inside the +-15 % acceptance of A14). Runs recorded without
this correction used the provisional P0-5b values (0.334, flat), which the
table keeps as `p05b_values`.

## 4 Wind and solar capacity factors next to DUKES (A9 disclosure)

The corrected wind CF stays above the DESNZ load factors after the literature
losses; A9 keeps it without calibration and requires the comparison and its
reasons in the results and here. The run results summary
(`GET /api/runs/{run}/summary`, field `vre_capacity_factor_disclosure`) carries
the same table for the Run's weather and weather method
(`gridform_core/vre_cf_disclosure.py`, values in
`gridform_core/data/weather/value_uk_vre_cf_disclosure_v1.json`, computed and
checked by `scripts/vre_cf_disclosure.py`).

Model CF: unweighted mean of the representative sites, 17,520 half-hour
periods, before curtailment. DUKES: table 6.3 standard basis, actual generation
of the GB fleet.

| Technology | GBP1 doctoral v1 | GBP1 P0-5b (v2 + losses) | **GBP1 corrected (v2 + losses + POA)** | DUKES 2019-2024 | DUKES 2020-2024 | corrected / DUKES 2020-2024 |
|---|---|---|---|---|---|---|
| Onshore wind | 0.4458 | 0.4026 | **0.4026** | 0.2593 | 0.2582 | 1.56 |
| Offshore wind | 0.6028 | 0.4913 | **0.4913** | 0.4016 | 0.4009 | 1.23 |
| Solar PV | 0.1201 | 0.0997 | **0.1065** | 0.1033 | 0.1025 | 1.04 |

VALUE 101 (synthetic, not comparable with DUKES): doctoral 0.4132 / 0.3270 /
0.2500; corrected 0.3731 / 0.2665 / 0.2075 (solar not transposed, section 1).
R029 public1: corrected 0.4022 / 0.4913 / 0.0996.

Why the model CF differs from DUKES (stated in every disclosure):

1. ERA5 100 m wind speeds are not bias-corrected; uncorrected reanalysis
   overstates north-west European wind output (Staffell & Pfenninger 2016). The
   literature loss factors do not remove this bias (A9).
2. One free-stream single-turbine power curve per site, no farm-level
   smoothing; wake, availability and electrical losses enter as literature
   factors only (A9).
3. The model CF is available output before curtailment; DUKES is generation
   after curtailment and constraint actions.
4. The model CF is an unweighted mean of a few representative sites, not the
   capacity-weighted GB fleet.
5. GBP1 weather is a 2020-2024 average climatology (P6-09); for solar it shrinks
   the plane-of-array gain (section 1).
6. DUKES solar generation of small installations is estimated with a typical
   load factor (DUKES 6.2 note 8).

## 5 References

Spencer J.W. (1971) Fourier series representation of the position of the sun.
Search 2(5):172. - Iqbal M. (1983) An Introduction to Solar Radiation. Academic
Press. - Duffie J.A., Beckman W.A. (2013) Solar Engineering of Thermal
Processes, 4th ed. Wiley. - Erbs D.G., Klein S.A., Duffie J.A. (1982) Solar
Energy 28(4):293-302. - Hay J.E., Davies J.A. (1980) Proc. First Canadian Solar
Radiation Data Workshop, 59-72. - Loutzenhiser P.G. et al. (2007) Solar Energy
81(2):254-267. - Kopp G., Lean J.L. (2011) Geophys. Res. Lett. 38, L01706. -
Jacobson M.Z., Jadhav V. (2018) Solar Energy 169:55-66. - Staffell I.,
Pfenninger S. (2016) Energy 114:1224-1239. - DESNZ, DUKES 2026 tables 6.2, 6.3;
Energy Trends September 2026 table 6.1. The bibliographic details of the
solar-model references were written from the literature and not re-checked
online in F2.

---

# 光伏倾斜面辐照、核电停发月份、径流水电与容量因子披露（F2，方法学 0.4 草稿）

状态：随施工单元 F2 写成（2026-10-06），依据 DECISIONS A9、A10、A13、A14。与 `p05b_corrected_data.md` 第 3、4 节不一致处以本文为准。0.4 版生成时并入 `core_weather.md`、`datasets.md`、`national_alternatives.md`（中英）。以下只适用于修正口径，论文复现口径不变。

1. **光伏倾斜面换算（A13，`p05.solar-plane-of-array`）。** 性能比 PR 0.83 按组件平面辐照度定义，此前乘在水平面 GHI 上。现在逐个半小时时段计算：Spencer（1971）赤纬、时差与日地距离修正，按时段**中点**（365 天 UTC 年，第 `t` 期为第 `t//48+1` 天、UTC `(t mod 48)/2+0.25` 时）和站点经纬度求太阳位置；Erbs 等（1982）由晴空指数 `kt` 分解散射比例；Hay–Davies（1980）换算到朝南倾斜面，地面反照率 0.2；倾角取 Jacobson & Jadhav（2018）按纬度拟合的年最优倾角（GBP1 各站约 35.7–37.7°）；天顶角大于 87° 或 GHI 为 0 时无直射、按各向同性散射处理；CF = min(POA × 0.83, 1)。天气 v2 下第 `t` 期取包含该时段的累积小时（`t//2+1`），时段中点落在该小时内。倾角为 0 时逐期精确返回 GHI（已测试）。只对 v2 时钟下的 ERA5 逐时累积量换算：VALUE 101 合成数据（52°N 十二月正午约 1 kW/m²，非物理值）和 R029 public1（`ssrd` 无 GRIB step type、未声明约定）不换算，证据中写明原因。GBP1 结果：伦敦年 GHI 约 1080 kWh/m²，各站 POA/GHI 1.05–1.10，年散射比例 0.63–0.75，代表站点平均 CF **0.0997 → 0.1065**（+6.9%）。敏感性（未采用）：倾角取纬度时为 0.1012。披露：GBP1 天气是 2020–2024 多年平均气候态（P6-09），平均后晴空指数被抹平（伦敦能量加权 kt 0.47、最大 0.73），散射比例偏高、倾斜增益偏小；同一代码在合成晴空年（51.5°N，所有白天时段 kt 0.65，散射比例 0.34）下增益为 33%（测试区间 15–35%）。只报告，不校正。参数与出处见 `value_uk_vre_loss_factors_v1.json` 的 `solar_plane_of_array`（模型选择待作者审核）。
2. **核电按月退役（A10，`p05.nuclear-generation-end-month`）。** 各站负荷率不变（A14 已认可）。站点政策文件中 Heysham 2、Torness 只写 “2030”，修正口径从参数表 `generation_end_month_overrides` 取 2030-03（参考统计表 1.6 节），因此四座 AGR 都在 2030 年第 4320 期（4 月 1 日 00:00 UTC）起为 0；Sizewell B（“2055”，无月份）全年运行。
3. **径流水电（A14，`p05.hydro-dukes-load-factor`）。** 可用率 = 0.3487（DUKES 6.3 标准口径 2019–2024 均值）× 由 Energy Trends 6.1 季度数据推出的阶梯月度形状（1–3 月 1.3851，4–6 月 0.6582，7–9 月 0.6776，10–12 月 1.2791；12 个月算术均值为 1）。按 365 天日历的时段加权均值为 0.99883，模型年负荷率为 0.3483。GBP1 的 2000 MW 年发电 6.10 TWh，比 DUKES 6.2 2019–2024 均值 5.77 TWh 高 5.8%，在 A14 的 ±15% 以内。未应用本修正的运行使用 P0-5b 临时值（0.334、平直），参数表以 `p05b_values` 保留。
4. **风光容量因子与 DUKES 并列披露（A9）。** 运行结果摘要（`GET /api/runs/{run}/summary` 的 `vre_capacity_factor_disclosure` 字段）给出该运行天气与天气方法下的模型弃电前 CF、DUKES 负荷率、比值和原因。GBP1 修正口径：陆上 0.4026（DUKES 2020–2024 均值 0.2582，比值 1.56），海上 0.4913（0.4009，1.23），光伏 0.1065（0.1025，1.04）。偏差原因：ERA5 100 m 风速未做偏差校正（Staffell & Pfenninger 2016）；每站一条单机自由流功率曲线；模型 CF 为弃电前可用出力，DUKES 为扣除弃电和约束调度后的实际发电；代表站点等权平均而非全国装机加权；GBP1 为多年平均气候态；DUKES 小型光伏发电量为估算值。只披露，不标定。
