from __future__ import annotations

import json
from pathlib import Path

import gridform_core.data_workbench.local_service as local_service_module
from gridform_core.data_workbench.local_service import LocalDataWorkbenchService


def test_revisions_attach_the_pinned_object_receipt(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    freshness = state_root / "reports" / "freshness"
    freshness.mkdir(parents=True)
    revision = {
        "schema_version": "value.data-source-revision/v1",
        "source_id": "neso.test",
        "revision_id": "2026-08-21",
        "publication_date": "2026-08-21",
        "landing_page": "https://example.test/catalogue",
        "download_url": "https://example.test/data.csv",
        "media_type": "text/csv",
        "reported_licence": "Open Government Licence v3.0",
        "discovered_at": "2026-08-21T00:00:00Z",
        "status": "new",
        "catalogue_metadata": {},
        "object_key": None,
    }
    (freshness / "source_discovery_report.json").write_text(
        json.dumps({"revisions": [revision]}), encoding="utf-8"
    )
    receipts = state_root / "receipts" / "neso.test"
    receipts.mkdir(parents=True)
    (receipts / "2026-08-21.json").write_text(
        json.dumps(
            {
                "schema_version": "value.data-raw-object-receipt/v1",
                "source_id": "neso.test",
                "revision_id": "2026-08-21",
                "object_key": "sha256/ab/test.csv",
                "redistribution_decision": "needs_rights_review",
            }
        ),
        encoding="utf-8",
    )

    response = LocalDataWorkbenchService(state_root).revisions()

    assert response["revisions"][0]["object_key"] == "sha256/ab/test.csv"
    assert response["revisions"][0]["redistribution_decision"] == "needs_rights_review"


def test_prompt98_build_is_exposed_as_a_review_candidate_without_false_installability(
    tmp_path: Path, monkeypatch
) -> None:
    state_root = tmp_path / "state"
    inventories = state_root / "inventories"
    inventories.mkdir(parents=True)
    (inventories / "official.json").write_text("{}", encoding="utf-8")

    def fake_build(_inventory: Path, output: Path) -> dict[str, object]:
        output.mkdir(parents=True)
        (output / "review").mkdir()
        (output / "review" / "zone-map.svg").write_text("<svg/>", encoding="utf-8")
        (output / "review" / "reconciliation-and-rights.json").write_text(
            json.dumps(
                {
                    "source_rights": [
                        {
                            "source_id": "neso.fixture",
                            "redistribution_decision": "redistributable",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (output / "candidate-manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "value.gb-zonal-network-candidate/v1",
                    "candidate_scientific_sha256": "a" * 64,
                    "bindings": {"value.zonal.zones": {"sha256": "b" * 64}},
                }
            ),
            encoding="utf-8",
        )
        return {
            "schema_version": "value.gb-zonal-candidate-build-result/v1",
            "status": "awaiting_owner_signoff",
            "maximum_demand_residual_mwh": 0.0,
            "assumed_symmetric_boundaries": ["B6"],
        }

    monkeypatch.setattr(local_service_module, "build_candidate", fake_build)
    service = LocalDataWorkbenchService(state_root)

    result = service.compile(
        {
            "schema_version": "value.data-compile-request/v1",
            "recipe_id": "prompt98-gb-zonal",
            "inventory_key": "official.json",
            "candidate_name": "official-a",
        }
    )

    assert result["workbench_candidate_id"].startswith("candidate-")
    candidates = service.candidates()["candidates"]
    assert candidates[0]["candidate_id"] == result["workbench_candidate_id"]
    validation = service.validate(result["workbench_candidate_id"])
    assert any(issue["code"] == "DW-PACK-001" for issue in validation["issues"])
    report = service.report(result["workbench_candidate_id"])
    assert report["audit_map_svg"] == "<svg/>"


def test_fetch_rejects_an_unsafe_revision_id_before_network_access(
    tmp_path: Path, monkeypatch
) -> None:
    called = False

    def forbidden_fetch(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network path must not run")

    monkeypatch.setattr(local_service_module, "fetch_revision", forbidden_fetch)
    service = LocalDataWorkbenchService(tmp_path / "state")
    request = {
        "schema_version": "value.data-fetch-request/v1",
        "revision": {
            "schema_version": "value.data-source-revision/v1",
            "source_id": "neso.dno-license-areas",
            "revision_id": "../../escape",
            "publication_date": "2024-05-03",
            "landing_page": "https://www.neso.energy/data-portal/gis-boundaries-gb-dno-license-areas",
            "download_url": "https://api.neso.energy/example.geojson",
            "media_type": "application/geo+json",
            "reported_licence": "NESO Open Data Licence",
            "discovered_at": "2026-08-21T00:00:00Z",
            "status": "new",
        },
    }

    try:
        service.fetch(request)
    except ValueError as exc:
        assert "safe path segment" in str(exc)
    else:
        raise AssertionError("unsafe revision ID was accepted")
    assert called is False


def test_revision_listing_does_not_follow_an_unsafe_receipt_path(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    freshness = state_root / "reports" / "freshness"
    freshness.mkdir(parents=True)
    (freshness / "source_discovery_report.json").write_text(
        json.dumps(
            {
                "revisions": [
                    {
                        "source_id": "neso.test",
                        "revision_id": "../escape",
                        "status": "new",
                        "object_key": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    escaped = state_root / "receipts" / "escape.json"
    escaped.parent.mkdir(parents=True)
    escaped.write_text(json.dumps({"object_key": "leaked"}), encoding="utf-8")

    response = LocalDataWorkbenchService(state_root).revisions()

    assert response["revisions"][0]["object_key"] is None
