# Corrected-profile weather, VRE losses and firm availability (P0-5b draft for methodology 0.4)

Status: draft written with the P0-5b construction (2026-10-06); to be merged into
`core_weather.md`, `datasets.md` and `national_alternatives.md` (en, zh) when the
0.4 edition is generated. Every numeric reference value named here is
**PENDING AUTHOR REVIEW** (`docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md`).

The doctoral reproduction profile (`doctoral-lineage-0.6.0a2`) is unchanged by
everything below except the weather-cache key, which is a pure software fix.

## 1 One conversion for both dispatch paths (S5)

`gridform_core/site_weather.py::site_cf_by_source` converts the NetCDF weather of
each representative site (the fleet's `solar_<city>`, `onshore_<city>`,
`offshore<N>` generators) into a per-period capacity factor. The canonical
adapter (`doctoral_weather.site_weather_profiles`) and the retained kernel use
the same arrays: under the corrected profile `SchemeCNativePSM` passes them to
the kernel (`kernel_injection.KernelSiteInputs`), which sets
`capacity_limit = capacity_multiplier x unit x cf[p]` every period (unit 20 MW
per wind multiplier, 1 for solar) instead of re-reading the files on its own
`IterLimit` clock. The same injection carries the nuclear and natural-flow hydro
availability of section 4. Interconnector offers of the canonical adapter keep
negative source prices under the corrected profile (`p05.raw-boundary-price`).

The kernel's process weather cache is keyed by the real paths, sizes and
modification times of its two weather files (`p05.weather-cache-key`, finding
P7-02), so a second run in one process on other weather never reuses the first
run's arrays. This applies to both profiles.

## 2 Weather time conventions, weather v2 (S6, finding P6-06)

ERA5 accumulated fields (`ssrd`, GRIB `stepType = accum`) are stamped at the end
of the hour they accumulate. The 0.6.0-alpha.2 clock served source hour `t // 2`
to the half-hour period `t`, i.e. the irradiance of the hour ending at `h` to the
hour starting at `h`: solar output was about one hour late. Weather v2
(`p05.weather-time-convention`, corrected profile only):

| Field | Convention | Source hour of period `t` |
|---|---|---|
| accumulated (`stepType = accum`, or binding `time_convention: accumulation_end_of_hour`) | end of hour | `t // 2 + 1` |
| instantaneous (`u100`, `v100`, `wind_speed`, synthetic samples; or `time_convention: instantaneous`) | at the stamp | `(t + 1) // 2` (stamp nearest the period midpoint) |
| doctoral v1 (frozen) | - | `t // 2` |

A binding may declare `time_convention`; otherwise the GRIB step type decides
and a variable without one is instantaneous. Result on GBP1 (London site):
solar centroid 12.97 UTC (v1) -> 11.97 UTC (v2); on 21 December the first
nonzero half-hour starts at 08:00 UTC (v1: 09:00) and the last ends at 16:00.
VALUE 101 (synthetic hourly samples): centroid 12.50 -> 12.00.

## 3 Literature loss factors, no statistical calibration (S7, finding P6-08, decisions Q15/A1)

> Updated by F2 (`f2_solar_poa_firm_cf_disclosure.md`): the author accepted the
> loss factors including the offshore total of about 18.5 % (A9); solar PR now
> multiplies plane-of-array irradiance (A13), GBP1 corrected solar CF 0.1065;
> the DUKES comparison is in the results summary and in that draft (A9).

The single-turbine power curve on ERA5 100 m wind and `ssrd / 3.6e6` (GHI against
1 kW m-2) are free-stream / horizontal-plane quantities. The corrected profile
multiplies them by literature loss factors (`p05.vre-loss-factors`,
`gridform_core/data/weather/value_uk_vre_loss_factors_v1.json`):

| Technology | Wake | Availability (energy) | Electrical | Multiplier | Sources |
|---|---|---|---|---|---|
| Onshore | 0.95 | 0.97 | 0.98 | 0.90307 | Simley et al. 2025; Conroy et al. 2011; Colmenar-Santos et al. 2014; Lee & Fields 2021 |
| Offshore | 0.88 | 0.945 | 0.98 | 0.814968 | Barthelmie et al. 2009; Warder & Piggott 2025; SPARTA 2017/18; Colmenar-Santos et al. 2014 |
| Solar | performance ratio 0.83 | | | 0.83 | Taylor et al. 2015; Dhimish 2020; Dhimish et al. 2021; Leloux et al. 2012 |

There is **no fitting to statistical load factors** (Q15): the per-period shape
stays ERA5, curtailment stays a market outcome, and the resulting capacity
factors are reported, not tuned. Two disclosures: (i) the offshore total loss
(about 18.5 %) exceeds the "about 10-15 %" of Q15; the author decides between
keeping it and lowering offshore wake to about 8 %; (ii) the PV performance
ratio is defined on plane-of-array irradiance, VALUE uses horizontal GHI, so the
tilt gain is missing and solar output is probably low. ERA5's own wind bias is
not a loss and is not removed.

Resulting annual capacity factors (unweighted mean of the representative sites,
17,520 periods, before curtailment):

| Pack | Method | Onshore | Offshore | Solar |
|---|---|---|---|---|
| GBP1 public1 (ERA5 2020-2024 climatology) | doctoral v1 | 0.4458 | 0.6028 | 0.1201 |
| GBP1 public1 | corrected (v2 + losses) | 0.4026 | 0.4913 | 0.0997 |
| VALUE 101 baseline (synthetic) | doctoral v1 | 0.4132 | 0.3270 | 0.2500 |
| VALUE 101 baseline (synthetic) | corrected (v2 + losses) | 0.3731 | 0.2665 | 0.2075 |

For comparison only (not a target): DESNZ DUKES 6.3 load factors for recent years
are lower for onshore and offshore wind; the author reads the values from the
DUKES 6.3 workbook. The investment side still uses the technology CSV resource
curves (`profiles.vre_*`), whose shape and level differ from the dispatch
weather; this inconsistency is disclosed and is to be unified in the next round.

## 4 Nuclear and natural-flow hydro availability (S8, findings P5-09, P5-10, P6-10)

> Updated by F2 (`f2_solar_poa_firm_cf_disclosure.md`): the author approved the
> nuclear values (A14); Heysham 2 and Torness also retire in March 2030 (A10);
> natural-flow hydro is 0.3487 x a quarterly-derived seasonal shape (A14).

`gridform_core/firm_availability.py` with
`gridform_core/data/nuclear/value_uk_firm_availability_v1.json`
(`p05.firm-availability`, corrected profile only; acceptance deferred to the author):

* **Nuclear.** Station load factor = PRIS 2019-2024 mean (Heysham 1 0.668,
  Hartlepool 0.689, Heysham 2 0.752, Torness 0.792, Sizewell B 0.801 on PRIS
  reference power), rescaled to the model's EDF capacity so the energy is kept
  (`lf x PRIS MW / model MW`), applied as a constant derate (no outage calendar
  in P0). A planned PWR/EPR project uses 0.801; an undifferentiated `Nuclear`
  asset the DESNZ fleet value 0.723. In the year of a station's announced
  `YYYY-MM` generation end the availability is zero from the first period of the
  next month (Heysham 1, 2030-03: zero from period 4320).
* **Natural-flow hydro.** Annual load factor 0.334 (2023, secondary source) x a
  monthly shape (flat placeholder: no monthly statistic was readable).
* The kernel's single `Nuclear` / `Hydro_natural_flow` agents receive the
  capacity-weighted availability of their member assets; the canonical
  resources carry the per-asset arrays.

Acceptance targets of the plan (nuclear within +-10 % of Energy Trends 5.1 on
the *supplied* basis, hydro within +-15 % of DUKES) are evaluated by the author.

## 5 GBP1 public2 (S11)

`scripts/build_value_uk_pack_revision.py` builds `value-uk-open-data-pack-public2`
locally: GBP1 public1 objects byte-identical except demand and the ten
interconnector roles, which are re-bound to the raw bytes of the author-approved
R029 objects (UTC demand pair, approved R03 interconnector chronology) with
declared columns, `interval_minutes` 30, `currency` GBP (fixed 1.1 EUR/GBP basis
recorded) and the ERA5 `time_convention`s. `flow_sign` stays
`declared_unverified` unless `scripts/audit_boundary_flow_sign.py` verifies every
country's annual net flow against an author-supplied reference
(`boundary_flow_reference_2022.json`). `--check` rebuilds and compares the
deterministic manifest. Nothing is uploaded; publishing needs the author's consent.

## 6 Edits for the 0.4 edition

`datasets.md` (en line 34 and 229, zh line 34 and 229) still names the removed
readers `doctoral_demand` and `doctoral_interconnectors`; the 0.4 edition names
the shared declarative reader `data_method.read_role` / `data_method.read_boundary`
instead. The 0.3 sources are left untouched here because the published 0.3
docx/pdf (`docs/methodology/artifacts.json`) were rendered from them.

## 7 Historical runs

Runs without these corrections (all runs before P0-5b and every doctoral run) on
the ERA5 research packs carry read-time advisories: solar about one hour late
(P6-06), wind and solar without losses (P6-08), nuclear and natural-flow hydro
always available (P5-09/P5-10).

---

# 修正口径的天气、风光损耗与稳定电源可用率（P0-5b，方法学 0.4 草稿）

状态：随 P0-5b 施工写成（2026-10-06），0.4 版生成时并入 `core_weather.md`、`datasets.md`、`national_alternatives.md`（中英）。文中所有参考数值均为 **PENDING AUTHOR REVIEW**（见 `docs/dev/REFERENCE_STATISTICS_FOR_AUTHOR_REVIEW.md`）。除天气缓存键（纯软件修复）外，论文复现口径不受影响。

1. **两条调度路径共用一次换算（S5）。** `site_weather.site_cf_by_source` 把各代表站点的 NetCDF 天气换算为逐期容量因子；canonical 适配器与遗留内核使用同一组数组。修正口径下，内核每期按 `capacity_multiplier × 单位 × cf[p]` 设定出力上限（风电单位 20 MW，光伏 1），不再用自己的 `IterLimit` 时钟重读文件；核电与径流水电的可用率经同一注入传入。canonical 的互联线报价在修正口径下保留负价。内核的进程级天气缓存按两个天气文件的真实路径、大小和修改时间作键（P7-02），两个口径都适用。
2. **天气 v2 时间约定（S6，P6-06）。** ERA5 累积量（`ssrd`，GRIB `stepType = accum`）标在所累积小时的末尾。旧时钟把第 `t//2` 小时给第 `t` 个半小时，光伏整体滞后约 1 小时。v2：累积量取 `t//2+1`；瞬时量（风速、合成样本）取离时段中点最近的时间戳 `(t+1)//2`；binding 可声明 `time_convention`。GBP1 伦敦站光伏质心由 12.97 变为 11.97 UTC；12 月 21 日首个非零时段从 09:00 提前到 08:00 UTC，最后一个在 16:00 结束。
3. **文献损耗系数，不做统计标定（S7，P6-08，Q15/A1）。**（F2 更新：作者已在 A9 认可损耗系数和海上约 18.5% 的合计损耗；光伏性能比改乘倾斜面辐照（A13），GBP1 修正口径光伏 CF 为 0.1065；DUKES 并列披露见 `f2_solar_poa_firm_cf_disclosure.md`。） 陆上 0.95×0.97×0.98 = 0.90307；海上 0.88×0.945×0.98 = 0.814968；光伏性能比 0.83。出处见参数表 `value_uk_vre_loss_factors_v1.json`。逐期形状仍来自 ERA5，弃电仍由出清决定，所得容量因子只报告、不拟合。GBP1：陆上 0.4458→0.4026，海上 0.6028→0.4913，光伏 0.1201→0.0997；VALUE 101：陆上 0.4132→0.3731，海上 0.3270→0.2665，光伏 0.2500→0.2075。披露：海上合计损耗约 18.5%，超出 Q15 所说的约 10–15%，由作者决定；性能比按组件平面辐照度定义，而 VALUE 用水平面 GHI，缺少倾角增益，光伏可能偏低；投资侧仍用技术 CSV 资源曲线，与调度侧不一致，下一轮统一。
4. **核电与径流水电可用率（S8，P5-09、P5-10、P6-10）。**（F2 更新：核电数值已获作者认可（A14）；Heysham 2、Torness 也在 2030 年 3 月停发（A10）；径流水电改为 0.3487 × 季度推出的季节形状（A14）。） 核电按站取 PRIS 2019–2024 平均负荷率，并按 EDF 容量折算以保持电量；在建 PWR/EPR 取 0.801，未分站的 `Nuclear` 取 DESNZ 全国值 0.723；宣布在某年某月停发的站，从下个月第一期起为 0（Heysham 1，2030-03 → 第 4320 期起为 0）。径流水电取年负荷率 0.334 × 月度形状（暂为平直占位）。验收（核电对 Energy Trends 5.1 净发电量 ±10%，水电对 DUKES ±15%）由作者审核后进行。
5. **GBP1 public2（S11）。** 本地构建 `value-uk-open-data-pack-public2`：需求与十条互联线改绑 R029 已批准对象的原始字节，并声明列名、30 分钟间隔、GBP 币种（记录 1.1 EUR/GBP 汇率依据）和 ERA5 时间约定；`flow_sign` 只有在 `audit_boundary_flow_sign.py` 用作者提供的参考表核实后才标为 verified。不上传，发布须经作者同意。
6. **0.4 版需改的文字。** `datasets.md`（中英第 34、229 行）仍提到已删除的 `doctoral_demand`、`doctoral_interconnectors`，0.4 版改为共用读取器 `data_method.read_role` / `read_boundary`；0.3 的源文件不动，因为已发布的 0.3 docx/pdf 由它们渲染。
7. **历史运行公告。** 未应用上述修正的运行（P0-5b 之前的全部运行和所有论文复现运行），在 ERA5 研究数据包上读取时附公告：光伏滞后约 1 小时、风光无损耗、核电与径流水电恒可用。
