# Data reading and validation (P0-5a draft for methodology 0.4)

Status: draft written with the P0-5a construction (2026-10-06); to be merged into
`datasets.md` / `core_weather.md` (en, zh) when the 0.4 edition is generated.

## One declarative reader

Every chronological role (demand, forecast, VRE profiles, interconnector flows and
prices) is read by one reader (`gridform_core/series_reader.py`, through
`gridform_core/data_method.py`) in the canonical adapter, the retained kernel's
boundary input and the data-pack validator. A binding may declare `csv_column`,
`csv_header`, `unit`, `currency`, `eur_per_gbp`, `fx_basis`, `interval_minutes`,
`source_periods`, `cyclic`, `leap_policy`, `timestamp_column` and related fields.

* The doctoral reproduction profile reads with the 0.6.0-alpha.2 rules
  (`legacy-v1`), the corrected profile with `declared-v2` (undeclared headers are
  inferred, several numeric columns are ambiguous, the clock honours the declared
  resolution).
* In both profiles a declared `csv_column` is read (finding P6-01), and an
  implicitly selected integer index column is refused (`GF_DATA_INDEX_COLUMN`).

## Universal reading corrections (decisions A3/Q9 and A5)

These apply to both profiles. They act on released objects identified by their
sha256 in the truth registry `gridform_core/data/validation/known_data_objects_v1.json`.

| Correction | Finding | Rule |
|---|---|---|
| `p05.belgium-price-currency` | P6-02 | GBP1 public1 `Belgium_price.csv` is hourly EUR/MWh. It is read from `Price (EUR/MWhe)`, divided by the fixed 1.1 EUR/GBP of the R029 approved_r03 interconnector manifest ("Ember 2022 except Ireland 2021; approved fixed EUR/GBP 1.1"), and each UTC hour is used for two half-hours. The result equals the R029 Belgium series to 6e-14 GBP/MWh. |
| `p05.boundary-identity` | P6-03 | Interconnector flow files are assigned by NESO line identity (`NEMO_FLOW` = Belgium, `BRITNED_FLOW` = Netherlands, `NSL_FLOW` = Norway ...). The retained kernel feeds every Connection its own country's series. |
| `p05.demand-utc-clock` | P6-04 | GBP1 public1 demand and forecast rows are put on the UTC clock with the R029 audit rule: the duplicated 2022-10-30 settlement periods 2 and 3 keep the later publication, and the four missing periods (09:00, 09:30, 23:00, 23:30 UTC) are linearly interpolated. The doctoral forecast keeps its one-period lead (P6-05 is corrected only). |
| `p05.interconnector-clock` | P6-24 | The retained kernel receives the interconnector series period by period on the run clock (`src[p]`), not each row twice (`src[p // 2]`). |

## Validation layers

`validate_data_pack` reports a structural layer (it alone decides `valid`, so a
pack with known defects can still be installed), a chronology layer (line
identity, price currency, untimestamped local-time demand, registry-identified row
order defects, forecast/real lag, declared timestamps) and a plausibility layer
(ranges in `gridform_core/data/validation/value_data_plausibility_v1.json`).
`profile_eligibility` says which findings block which profile: under the corrected
profile, chronology findings of non-workspace packs and plausibility failures of
scientific reference packs are preflight errors; under the doctoral profile they
are warnings. GBP1 public1 is therefore refused by the corrected preflight
(identity, currency, time) and runs, repaired, under the doctoral profile.
`profile_eligibility` also applies the profile's data-pack whitelist, the same
check (`methodology.data_pack_violation`) as Study resolution and preflight: a pack
the doctoral profile does not name (any user workspace pack, the VALUE 101 network
overlay) is not eligible for it, with the blocking code
`VALUE_PROFILE_COMBINATION_UNSUPPORTED` and the reason "not a thesis-era pack".
