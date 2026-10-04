from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from gridform_core.data_workbench.compilers.dso_etys import (
    compile_dso_geojson,
    compile_etys_capabilities,
    read_etys_workbook,
    reconcile_boundary_evidence,
)


def feature(zone_id: str, coordinates: object, *, geometry_type: str = "Polygon") -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {
            "zone_id": zone_id,
            "display_name": zone_id.title(),
            "dso_owner": f"DSO {zone_id}",
            "nation": "England",
        },
        "geometry": {"type": geometry_type, "coordinates": coordinates},
    }


def test_dso_compiler_repairs_invalid_geometry_and_orders_multipolygons() -> None:
    bow_tie = [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]]
    multi = [
        [[[4, 0], [5, 0], [5, 1], [4, 1], [4, 0]]],
        [[[3, 0], [3.5, 0], [3.5, 1], [3, 1], [3, 0]]],
    ]
    payload = {
        "type": "FeatureCollection",
        "features": [
            feature("z-b", multi, geometry_type="MultiPolygon"),
            feature("z-a", bow_tie),
        ],
    }

    result = compile_dso_geojson(payload, source_crs="EPSG:4326")

    assert [zone["zone_id"] for zone in result["resource_zones"]] == ["z-a", "z-b"]
    assert result["source_crs"] == "EPSG:4326"
    assert result["display_crs"] == "EPSG:4326"
    assert result["repairs"][0]["zone_id"] == "z-a"
    assert result["scientific_sha256"] == compile_dso_geojson(
        deepcopy(payload), source_crs="EPSG:4326"
    )["scientific_sha256"]


def test_dso_compiler_rejects_duplicate_ids_and_positive_area_overlap() -> None:
    square = [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]
    overlapping = [[[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]]]
    duplicate = {"type": "FeatureCollection", "features": [feature("z", square), feature("z", overlapping)]}
    with pytest.raises(ValueError, match="duplicate"):
        compile_dso_geojson(duplicate, source_crs="EPSG:4326")

    overlap = {"type": "FeatureCollection", "features": [feature("a", square), feature("b", overlapping)]}
    with pytest.raises(ValueError, match="overlap"):
        compile_dso_geojson(overlap, source_crs="EPSG:4326")


def test_dso_compiler_converts_declared_source_crs_to_display_crs() -> None:
    metres = [[[0, 0], [1000, 0], [1000, 1000], [0, 1000], [0, 0]]]
    result = compile_dso_geojson(
        {"type": "FeatureCollection", "features": [feature("projected", metres)]},
        source_crs="EPSG:3857",
    )

    coordinates = result["display_geojson"]["features"][0]["geometry"]["coordinates"][0]
    assert 0 < coordinates[1][0] < 1


def test_etys_compiler_uses_capability_not_fes_percentile_and_names_reverse_waiver() -> None:
    rows = [
        {
            "Boundary": "B6",
            "Year": 2025,
            "Direction": "north_to_south",
            "Category": "Capability",
            "Value MW": 6400,
            "publication_date": "2025-01-01",
        },
        {
            "Boundary": "B6",
            "Year": 2025,
            "Direction": "north_to_south",
            "Category": "FES 95th percentile flow",
            "Value MW": 9000,
            "publication_date": "2025-01-01",
        },
    ]

    result = compile_etys_capabilities(rows)

    assert result["boundaries"][0]["forward_limit_mw"] == 6400.0
    assert result["boundaries"][0]["reverse_limit_mw"] == 6400.0
    assert result["boundaries"][0]["reverse_limit_method"] == "symmetric_forward_fallback"
    assert result["requested_waivers"] == ["etys.B6.symmetric_forward_fallback"]
    assert result["ignored_rows"][0]["category"] == "FES 95th percentile flow"


@pytest.mark.parametrize("value", [-1, "not-a-number"])
def test_etys_compiler_rejects_invalid_capability(value: object) -> None:
    with pytest.raises(ValueError, match="Capability"):
        compile_etys_capabilities(
            [{"Boundary": "B1", "Year": 2025, "Direction": "forward", "Category": "Capability", "Value MW": value}]
        )


def test_reconciliation_fills_missing_fields_and_keeps_newer_conflict_diff() -> None:
    workbook = {"B1": {"publication_date": "2025-01-01", "forward_limit_mw": 100}}
    gis = {"B1": {"publication_date": "2024-01-01", "geometry_id": "gis-b1", "forward_limit_mw": 90}}

    result = reconcile_boundary_evidence(workbook, gis)

    assert result["resolved"]["B1"]["forward_limit_mw"] == 100
    assert result["resolved"]["B1"]["geometry_id"] == "gis-b1"
    assert result["conflicts"][0]["selected_value"] == 100
    assert result["inventory"][0]["boundary_id"] == "B1"


def test_data_workbench_extra_declares_build_only_gis_dependencies() -> None:
    project = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    lock = (
        Path(__file__).resolve().parents[2]
        / "requirements"
        / "value-data-workbench-py310.lock"
    ).read_text(encoding="utf-8")
    assert "data-workbench = [" in project
    assert '"shapely==2.1.1"' in project
    assert '"pyproj==3.7.1"' in project
    assert '"openpyxl==3.1.0"' in project
    assert '"pyshp==3.1.6"' in project
    assert "pyshp==3.1.6" in lock


def test_etys_workbook_reader_preserves_headers_and_rows(tmp_path: Path) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Boundary capabilities"
    sheet.append(["Boundary", "Year", "Direction", "Category", "Value MW"])
    sheet.append(["B6", 2025, "north_to_south", "Capability", 6400])
    path = tmp_path / "etys.xlsx"
    workbook.save(path)

    rows = read_etys_workbook(path, sheet_name="Boundary capabilities")

    assert rows == [
        {
            "Boundary": "B6",
            "Year": 2025,
            "Direction": "north_to_south",
            "Category": "Capability",
            "Value MW": 6400,
        }
    ]
