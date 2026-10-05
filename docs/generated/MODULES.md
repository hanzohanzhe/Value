# Shipped module catalogue

Generated from `gridform_core/manifests/*.json` by `scripts/generate_reference_tables.py`; do not edit by hand.

| ID | Slot | Version | Contract | Solver contract | Status | Required selection | Implementation source | Source SHA-256 |
|---|---|---|---|---|---|---:|---|---|
| value-copperplate-balancing | balancing | 1.0.0 | value.balancing-module/v1 | — | ready | false | gridform_core/builtin/value_modules.py | 09f66c1e745bbdc4d94bc58a06ee73b4080513d08c1bd716c0633e9925f35ac6 |
| value-zonal-redispatch-balancing | balancing | 4.0.0 | value.balancing-module/v1 | value.zonal-lexicographic-shed-lock/v4 | experimental | false | gridform_core/zonal_redispatch.py | 113af854e200fd920ea000130f4ff29914f82090798a3422705a30168acf7372 |
| agent-investment | investment | 3.0.0 | value.investment/v2 | — | ready | true | gridform_core/builtin/value_modules.py | 09f66c1e745bbdc4d94bc58a06ee73b4080513d08c1bd716c0633e9925f35ac6 |
| reference-transmission-expansion | network_expansion | 1.0.0 | value.network-expansion/v1 | — | experimental | false | gridform_core/network_expansion.py | 38a808faca5d35436a03680dab8696f1ff3c3673b29733bce291addc7a006ffb |
| planning-pipeline | pipeline | 2.2.0 | value.planning/v2 | — | ready | true | gridform_core/builtin/value_modules.py | 09f66c1e745bbdc4d94bc58a06ee73b4080513d08c1bd716c0633e9925f35ac6 |
| value-bid-at-cost-psm | psm | 6.0.0 | value.psm/v2 | — | ready | true | gridform_core/builtin/value_modules.py | 09f66c1e745bbdc4d94bc58a06ee73b4080513d08c1bd716c0633e9925f35ac6 |
| value-doctoral-national-psm | psm | 0.2.0 | value.psm/v2 | — | experimental | false | gridform_core/builtin/scheme_c_1000twh/doctoral_national_psm.py | eda4f33edf9bc0577dc5ab77a99c14e380ce1a5dbdb6266d8199351423cf98d7 |
| value-perfect-foresight-lp | psm | 1.0.0 | value.psm/v2 | — | ready | false | gridform_core/perfect_foresight_psm.py | 7762ee22a6a79fb087b27890bd822b06f9c6f55053ef07af04be953da388334b |
| value-reference-dc-network | psm | 1.1.0 | value.psm/v2 | — | ready | false | gridform_core/network_dc.py | 045634ab0057cb4f085930e056de666fb7e589bc3d6aca1de2af7a43519f3634 |
| value-staged-bid-at-cost-psm | psm | 1.2.0 | value.psm/v2 | — | ready | false | gridform_core/builtin/value_modules.py | 09f66c1e745bbdc4d94bc58a06ee73b4080513d08c1bd716c0633e9925f35ac6 |
| value-storage-expansion-policy | storage_cap | 5.0.0 | value.expansion-policy/v2 | — | ready | true | gridform_core/builtin/value_modules.py | 09f66c1e745bbdc4d94bc58a06ee73b4080513d08c1bd716c0633e9925f35ac6 |
| dynamic-annual-storage-cost | storage_cost | 2.0.0 | value.storage-cost/v1 | — | ready | false | gridform_core/builtin/value_modules.py | 09f66c1e745bbdc4d94bc58a06ee73b4080513d08c1bd716c0633e9925f35ac6 |
| user-formula-storage-cost | storage_cost | 1.0.0 | value.storage-cost/v1 | — | ready | false | gridform_core/builtin/value_modules.py | 09f66c1e745bbdc4d94bc58a06ee73b4080513d08c1bd716c0633e9925f35ac6 |
| value-legacy-storage-tariff | storage_cost | 1.0.0 | value.storage-cost/v1 | — | ready | false | gridform_core/builtin/value_modules.py | 09f66c1e745bbdc4d94bc58a06ee73b4080513d08c1bd716c0633e9925f35ac6 |
| value-annual-state-transition | transition | 2.1.0 | value.state-transition/v2 | — | ready | false | gridform_core/builtin/value_modules.py | 09f66c1e745bbdc4d94bc58a06ee73b4080513d08c1bd716c0633e9925f35ac6 |
| vre-expansion-cap | vre_cap | 2.0.0 | value.expansion-policy/v2 | — | ready | true | gridform_core/builtin/value_modules.py | 09f66c1e745bbdc4d94bc58a06ee73b4080513d08c1bd716c0633e9925f35ac6 |
| value-repd-era5-aggregated-weather | weather_spatializer | 1.0.0 | value.weather-spatializer/v1 | — | experimental | false | gridform_core/weather_spatialization.py | 4d9efe1f822f02e62dd0d3206ac800044ec7184992054de3afaab6baa30f7609 |
| value-representative-point-weather | weather_spatializer | 1.0.0 | value.weather-spatializer/v1 | — | experimental | false | gridform_core/weather_spatialization.py | 4d9efe1f822f02e62dd0d3206ac800044ec7184992054de3afaab6baa30f7609 |

Shipped manifest count: **18**.
