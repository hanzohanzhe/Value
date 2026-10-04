from __future__ import annotations

from gridform_core import gb_zonal_pack_builder
from gridform_core.data_workbench.compilers.network_candidate import (
    compile_review_candidate,
)


def zone(zone_id: str, x0: float, x1: float, parent: str) -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {
            "zone_id": zone_id,
            "dso_parent_zone_id": parent,
            "display_name": zone_id.upper(),
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[x0, 0], [x1, 0], [x1, 1], [x0, 1], [x0, 0]]],
        },
    }


def zones() -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [zone("a", 0, 1, "dso-west"), zone("b", 1, 2, "dso-centre"), zone("c", 2, 3, "dso-east")],
    }


def test_one_cut_has_hand_authored_signed_incidence_and_review_record() -> None:
    result = compile_review_candidate(
        zones(),
        [
            {
                "boundary_id": "B_AB",
                "positive_zone_ids": ["a"],
                "negative_zone_ids": ["b", "c"],
            }
        ],
        {
            "schema_version": "value.network-review-overrides/v1",
            "decisions": [
                {
                    "boundary_id": "B_AB",
                    "decision": "accepted",
                    "approved_by": "fixture-reviewer",
                    "expected_members": [{"corridor_id": "corridor:a--b", "coefficient": 1}],
                }
            ],
        },
    )

    assert [row["corridor_id"] for row in result["corridors"]] == [
        "corridor:a--b",
        "corridor:b--c",
    ]
    assert result["accepted_cutsets"][0]["members"] == [
        {"corridor_id": "corridor:a--b", "coefficient": 1}
    ]
    assert result["accepted_cutsets"][0]["approval"]["approved_by"] == "fixture-reviewer"
    assert result["blocking_reasons"] == []


def test_overlapping_cuts_and_unreviewed_membership_remain_visible() -> None:
    result = compile_review_candidate(
        zones(),
        [
            {"boundary_id": "B_W", "positive_zone_ids": ["a"], "negative_zone_ids": ["b", "c"]},
            {"boundary_id": "B_E", "positive_zone_ids": ["a", "b"], "negative_zone_ids": ["c"]},
        ],
        {
            "schema_version": "value.network-review-overrides/v1",
            "decisions": [
                {"boundary_id": "B_W", "decision": "accepted", "approved_by": "reviewer"}
            ],
        },
    )

    assert result["accepted_cutsets"][0]["members"] == [
        {"corridor_id": "corridor:a--b", "coefficient": 1}
    ]
    assert result["unresolved_cutsets"][0]["boundary_id"] == "B_E"
    assert result["unresolved_cutsets"][0]["status"] == "needs_mapping"
    assert result["blocking_reasons"] == ["cutset.B_E.needs_mapping"]


def test_zone_parents_corridor_endpoints_and_map_ids_reconcile() -> None:
    result = compile_review_candidate(
        zones(),
        [],
        {"schema_version": "value.network-review-overrides/v1", "decisions": []},
    )

    assert all(row["dso_parent_zone_id"] for row in result["network_zones"])
    zone_ids = {row["zone_id"] for row in result["network_zones"]}
    assert all(
        row["from_zone_id"] in zone_ids and row["to_zone_id"] in zone_ids
        for row in result["corridors"]
    )
    assert set(result["map_ids"]) == {
        "zone:a", "zone:b", "zone:c", "corridor:corridor:a--b", "corridor:corridor:b--c"
    }
    assert all(f'data-map-id="{map_id}"' in result["audit_svg"] for map_id in result["map_ids"])


def test_disconnected_official_polygons_get_a_visible_minimum_gap_bridge() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [zone("a", 0, 1, "dso-west"), zone("b", 2, 3, "dso-east")],
    }

    result = compile_review_candidate(
        payload,
        [],
        {"schema_version": "value.network-review-overrides/v1", "decisions": []},
    )

    assert result["corridors"] == [
        {
            "corridor_id": "corridor:a--b",
            "from_zone_id": "a",
            "to_zone_id": "b",
            "positive_direction": "from_to_positive",
            "purpose": "computational_routing",
            "connection_method": "nearest_geometry_gap_bridge",
        }
    ]
    assert result["inferred_gap_bridges"] == ["corridor:a--b"]


def test_prompt98_public_builder_is_a_compatibility_facade() -> None:
    assert gb_zonal_pack_builder.COMPATIBILITY_FACADE_TARGET == (
        "gridform_core.data_workbench.compilers.network_candidate.build_prompt98_candidate"
    )
