# Shipped module catalogue

Generated from `gridform_core/manifests/*.json` by `scripts/generate_reference_tables.py`; do not edit by hand.

| ID | Slot | Version | Contract | Solver contract | Status | Required selection | Implementation source | Source SHA-256 |
|---|---|---|---|---|---|---:|---|---|
| value-copperplate-balancing | balancing | 1.0.0 | value.balancing-module/v1 | — | ready | false | gridform_core/builtin/value_modules.py | 20ca4cf9d2e7f33d316859c8e3131275f38f0fc0324818a09124c7ee30684bd4 |
| value-zonal-redispatch-balancing | balancing | 4.0.0 | value.balancing-module/v1 | value.zonal-lexicographic-shed-lock/v4 | experimental | false | gridform_core/zonal_redispatch.py | f5295cfcb03895ec18e42022712bbcc6942b83e32b7b373bb0e799f28e0a4f9e |
| agent-investment | investment | 2.2.0 | value.investment/v2 | — | ready | true | gridform_core/builtin/value_modules.py | 20ca4cf9d2e7f33d316859c8e3131275f38f0fc0324818a09124c7ee30684bd4 |
| reference-transmission-expansion | network_expansion | 1.0.0 | value.network-expansion/v1 | — | experimental | false | gridform_core/network_expansion.py | 38a808faca5d35436a03680dab8696f1ff3c3673b29733bce291addc7a006ffb |
| planning-pipeline | pipeline | 2.2.0 | value.planning/v2 | — | ready | true | gridform_core/builtin/value_modules.py | 20ca4cf9d2e7f33d316859c8e3131275f38f0fc0324818a09124c7ee30684bd4 |
| value-bid-at-cost-psm | psm | 5.1.0 | value.psm/v2 | — | ready | true | gridform_core/builtin/value_modules.py | 20ca4cf9d2e7f33d316859c8e3131275f38f0fc0324818a09124c7ee30684bd4 |
| value-doctoral-national-psm | psm | 0.2.0 | value.psm/v2 | — | experimental | false | gridform_core/builtin/scheme_c_1000twh/doctoral_national_psm.py | 0dec2ec1747428a0e2add835e9f9faae83c142cc9e8075b5d5854633569700c6 |
| value-perfect-foresight-lp | psm | 1.0.0 | value.psm/v2 | — | ready | false | gridform_core/perfect_foresight_psm.py | 48c4d0d20ad189e5011c19807c1f8e0ce39ccb24efdbac02b1fbd7947ff240da |
| value-reference-dc-network | psm | 1.1.0 | value.psm/v2 | — | ready | false | gridform_core/network_dc.py | 10fbf1a7794dc9ad6c457b7862b5b7363bfde2a92889257877b109b40ee169e1 |
| value-staged-bid-at-cost-psm | psm | 1.1.0 | value.psm/v2 | — | ready | false | gridform_core/builtin/value_modules.py | 20ca4cf9d2e7f33d316859c8e3131275f38f0fc0324818a09124c7ee30684bd4 |
| value-storage-expansion-policy | storage_cap | 4.0.0 | value.expansion-policy/v2 | — | ready | true | gridform_core/builtin/value_modules.py | 20ca4cf9d2e7f33d316859c8e3131275f38f0fc0324818a09124c7ee30684bd4 |
| dynamic-annual-storage-cost | storage_cost | 1.0.0 | value.storage-cost/v1 | — | ready | false | gridform_core/builtin/value_modules.py | 20ca4cf9d2e7f33d316859c8e3131275f38f0fc0324818a09124c7ee30684bd4 |
| user-formula-storage-cost | storage_cost | 1.0.0 | value.storage-cost/v1 | — | ready | false | gridform_core/builtin/value_modules.py | 20ca4cf9d2e7f33d316859c8e3131275f38f0fc0324818a09124c7ee30684bd4 |
| value-legacy-storage-tariff | storage_cost | 1.0.0 | value.storage-cost/v1 | — | ready | false | gridform_core/builtin/value_modules.py | 20ca4cf9d2e7f33d316859c8e3131275f38f0fc0324818a09124c7ee30684bd4 |
| value-annual-state-transition | transition | 2.1.0 | value.state-transition/v2 | — | ready | false | gridform_core/builtin/value_modules.py | 20ca4cf9d2e7f33d316859c8e3131275f38f0fc0324818a09124c7ee30684bd4 |
| vre-expansion-cap | vre_cap | 2.0.0 | value.expansion-policy/v2 | — | ready | true | gridform_core/builtin/value_modules.py | 20ca4cf9d2e7f33d316859c8e3131275f38f0fc0324818a09124c7ee30684bd4 |
| value-repd-era5-aggregated-weather | weather_spatializer | 1.0.0 | value.weather-spatializer/v1 | — | experimental | false | gridform_core/weather_spatialization.py | 4d9efe1f822f02e62dd0d3206ac800044ec7184992054de3afaab6baa30f7609 |
| value-representative-point-weather | weather_spatializer | 1.0.0 | value.weather-spatializer/v1 | — | experimental | false | gridform_core/weather_spatialization.py | 4d9efe1f822f02e62dd0d3206ac800044ec7184992054de3afaab6baa30f7609 |

Shipped manifest count: **18**.
