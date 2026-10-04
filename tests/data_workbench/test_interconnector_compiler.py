from __future__ import annotations

import pytest

from gridform_core.data_workbench.compilers.interconnectors import (
    allocate_country_profile,
    compile_interconnector_landings,
)


ZONES = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"zone_id": "south", "nation": "England"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-2, 49], [2, 49], [2, 53], [-2, 53], [-2, 49]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"zone_id": "north", "nation": "Scotland"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-5, 53], [1, 53], [1, 59], [-5, 59], [-5, 53]]],
            },
        },
    ],
}


def assets() -> list[dict[str, object]]:
    return [
        {
            "interconnector_id": "ifa",
            "counterparty_country": "France",
            "connection_site": "Sellindge",
            "import_capacity_mw": 2000,
            "export_capacity_mw": 2000,
            "status": "operational",
            "effective_date": "1986-01-01",
            "host_transmission_owner": "NGET",
        },
        {
            "interconnector_id": "eleclink",
            "counterparty_country": "France",
            "connection_site": "Folkestone",
            "import_capacity_mw": 1000,
            "export_capacity_mw": 500,
            "status": "operational",
            "effective_date": "2022-01-01",
            "host_transmission_owner": "NGET",
        },
    ]


def test_known_connection_sites_map_to_physical_gb_zone() -> None:
    result = compile_interconnector_landings(
        assets(),
        {
            "Sellindge": {"longitude": 1.1, "latitude": 51.1, "evidence": "official_substation"},
            "Folkestone": {"longitude": 1.2, "latitude": 51.0, "evidence": "operator_connection"},
        },
        ZONES,
        coast_candidates=[],
    )

    assert [row["zone_id"] for row in result["assets"]] == ["south", "south"]
    methods = {row["interconnector_id"]: row["landing_method"] for row in result["assets"]}
    assert methods == {"ifa": "official_substation", "eleclink": "operator_connection"}
    assert result["requested_waivers"] == []
    assert all(row["asset_scope"] == "external_to_gb_internal_fleet" for row in result["assets"])


def test_nearest_coast_fallback_is_deterministic_and_requests_waiver() -> None:
    single = [
        {
            **assets()[0],
            "interconnector_id": "unknown-link",
            "connection_site": "Unknown",
            "fallback_longitude": -1.0,
            "fallback_latitude": 55.0,
        }
    ]
    result = compile_interconnector_landings(
        single,
        {},
        ZONES,
        coast_candidates=[
            {"coast_id": "south-coast", "zone_id": "south", "longitude": 0.0, "latitude": 50.0},
            {"coast_id": "north-coast", "zone_id": "north", "longitude": -1.1, "latitude": 55.1},
        ],
    )

    assert result["assets"][0]["zone_id"] == "north"
    assert result["assets"][0]["landing_method"] == "nearest_coast_dso_inference"
    assert result["assets"][0]["distance_km"] > 0
    assert result["requested_waivers"] == ["interconnector.unknown-link.nearest_coast_dso_inference"]


def test_country_profile_split_conserves_positive_and_negative_periods() -> None:
    compiled = compile_interconnector_landings(
        assets(),
        {
            "Sellindge": {"longitude": 1.1, "latitude": 51.1, "evidence": "official_substation"},
            "Folkestone": {"longitude": 1.2, "latitude": 51.0, "evidence": "official_substation"},
        },
        ZONES,
        coast_candidates=[],
    )
    split = allocate_country_profile(
        [
            {"period_id": "p0", "timestamp": "2025-01-01T00:00:00Z", "country": "France", "exchange_mw": 1500},
            {"period_id": "p1", "timestamp": "2025-01-01T00:30:00Z", "country": "France", "exchange_mw": -1000},
        ],
        compiled["assets"],
    )

    for period_id, expected in (("p0", 1500), ("p1", -1000)):
        rows = [row for row in split["allocations"] if row["period_id"] == period_id]
        assert sum(row["exchange_mw"] for row in rows) == pytest.approx(expected)
    positive = {
        row["interconnector_id"]: row["exchange_mw"]
        for row in split["allocations"] if row["period_id"] == "p0"
    }
    negative = {
        row["interconnector_id"]: row["exchange_mw"]
        for row in split["allocations"] if row["period_id"] == "p1"
    }
    assert positive == pytest.approx({"ifa": 1000, "eleclink": 500})
    assert negative == pytest.approx({"ifa": -800, "eleclink": -200})
    assert split["allocation_method"] == "capacity_weighted_country_split"


def test_invalid_identity_unknown_zone_and_envelope_overflow_are_rejected() -> None:
    duplicate = assets() + [dict(assets()[0])]
    with pytest.raises(ValueError, match="duplicate"):
        compile_interconnector_landings(duplicate, {}, ZONES, coast_candidates=[])

    with pytest.raises(ValueError, match="envelope"):
        allocate_country_profile(
            [{"period_id": "p0", "timestamp": "2025-01-01", "country": "France", "exchange_mw": 4000}],
            [
                {**assets()[0], "zone_id": "south"},
                {**assets()[1], "zone_id": "south"},
            ],
        )


def test_irish_exchange_does_not_create_northern_ireland_internal_zone() -> None:
    ireland = [{**assets()[0], "interconnector_id": "moyle", "counterparty_country": "Ireland"}]
    result = compile_interconnector_landings(
        ireland,
        {"Sellindge": {"longitude": 1.1, "latitude": 51.1, "evidence": "fixture"}},
        ZONES,
        coast_candidates=[],
    )

    assert result["assets"][0]["zone_id"] == "south"
    assert all(row["zone_id"] != "northern-ireland" for row in result["assets"])
