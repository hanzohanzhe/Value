from __future__ import annotations

import pytest

from gridform_core.data_workbench.compilers.demand import (
    compile_base_demand_weights,
    evolve_demand_weights,
    normalize_postcode,
    spatialize_national_demand,
)


ZONES = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"zone_id": "north"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 1], [2, 1], [2, 2], [0, 2], [0, 1]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"zone_id": "south"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [2, 0], [2, 1], [0, 1], [0, 0]]],
            },
        },
    ],
}


def test_postcode_normalisation_and_measured_energy_reconciliation() -> None:
    domestic = [
        {"postcode": "ab1 2cd", "consumption_mwh": 30},
        {"postcode": "EF34GH", "consumption_mwh": 20},
    ]
    non_domestic = [
        {"postcode": "AB12CD", "consumption_mwh": 10},
        {"postcode": "ZZ9 9ZZ", "consumption_mwh": 5},
    ]
    directory = [
        {"postcode": "AB1 2CD", "longitude": 1, "latitude": 1.5, "status": "live", "country": "England"},
        {"postcode": "EF3 4GH", "longitude": 1, "latitude": 0.5, "status": "live", "country": "England"},
    ]

    result = compile_base_demand_weights(domestic, non_domestic, directory, ZONES)

    assert normalize_postcode(" ab1-2cd ") == "AB12CD"
    assert result["energy_mwh_by_zone"] == {"north": 40.0, "south": 20.0}
    assert result["weights"] == pytest.approx({"north": 2 / 3, "south": 1 / 3})
    assert result["coverage"]["unmatched_postcodes"] == ["ZZ99ZZ"]
    assert result["reconciliation"]["included_mwh"] == 60.0
    assert result["reconciliation"]["unmatched_mwh"] == 5.0


def test_duplicate_terminated_non_gb_and_boundary_points_are_visible() -> None:
    demand = [
        {"postcode": "A1 1AA", "consumption_mwh": 1},
        {"postcode": "A11AA", "consumption_mwh": 2},
        {"postcode": "T1 1AA", "consumption_mwh": 3},
        {"postcode": "N1 1AA", "consumption_mwh": 4},
        {"postcode": "B1 1AA", "consumption_mwh": 5},
    ]
    directory = [
        {"postcode": "A1 1AA", "longitude": 0.5, "latitude": 1.5, "status": "live", "country": "England"},
        {"postcode": "T1 1AA", "longitude": 0.5, "latitude": 1.5, "status": "terminated", "country": "England"},
        {"postcode": "N1 1AA", "longitude": 0.5, "latitude": 1.5, "status": "live", "country": "Northern Ireland"},
        {"postcode": "B1 1AA", "longitude": 1.0, "latitude": 1.0, "status": "live", "country": "England"},
    ]

    result = compile_base_demand_weights(demand, [], directory, ZONES)

    assert result["coverage"]["duplicate_postcodes"] == ["A11AA"]
    assert result["coverage"]["terminated_postcodes"] == ["T11AA"]
    assert result["coverage"]["non_gb_postcodes"] == ["N11AA"]
    assert result["coverage"]["boundary_assignments"] == [
        {"postcode": "B11AA", "candidate_zone_ids": ["north", "south"], "selected_zone_id": "north"}
    ]


def test_fes_relative_evolution_normalises_each_year_and_marks_fallback() -> None:
    result = evolve_demand_weights(
        {"north": 0.6, "south": 0.4, "island": 0.0},
        [
            {"year": 2030, "zone_id": "north", "relative_factor": 1.0},
            {"year": 2030, "zone_id": "south", "relative_factor": 2.0},
        ],
        years=[2025, 2030],
    )

    assert sum(result["weights_by_year"]["2025"].values()) == pytest.approx(1.0)
    assert result["weights_by_year"]["2030"] == pytest.approx(
        {"north": 3 / 7, "south": 4 / 7, "island": 0.0}
    )
    assert result["method_by_zone_year"]["2030"]["island"] == "static_share_fallback"
    assert "demand.island.static_share_fallback" in result["requested_waivers"]


def test_spatialisation_preserves_each_national_period_to_1e_8() -> None:
    result = spatialize_national_demand(
        [
            {"period_id": "p0", "national_demand_mwh": 100.0},
            {"period_id": "p1", "national_demand_mwh": 123.456789},
        ],
        {"north": 1 / 3, "south": 2 / 3},
    )

    for index, national in enumerate(result["national_demand_mwh"]):
        assert sum(values[index] for values in result["demand_mwh_by_zone"].values()) == pytest.approx(
            national, abs=1e-8
        )
    assert all(abs(item["post_residual_mwh"]) <= 1e-8 for item in result["residual_audit"])
    scaled = spatialize_national_demand(
        [{"period_id": "p0", "national_demand_mwh": 200.0}],
        {"north": 1 / 3, "south": 2 / 3},
    )
    assert scaled["weight_method"] == result["weight_method"]
