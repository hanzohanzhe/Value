from __future__ import annotations

import json
from pathlib import Path

import pytest

from gridform_core.data_workbench.registry import JsonSourceRegistry, package_registry_root


EXPECTED_SOURCE_IDS = {
    "desnz.postcode-electricity-consumption",
    "neso.dno-license-areas",
    "neso.etys-boundary-gis",
    "neso.etys-capabilities",
    "neso.fes-gsp-regional-demand",
    "neso.interconnector-register",
    "ons.postcode-directory",
}


def test_packaged_uk_network_registry_contains_required_official_sources() -> None:
    registry = JsonSourceRegistry(package_registry_root("uk-network"))

    assert {item.source_id for item in registry.list_sources()} == EXPECTED_SOURCE_IDS
    assert all(item.landing_page.startswith("https://") for item in registry.list_sources())
    assert all(item.candidate_uses for item in registry.list_sources())


def test_neso_api_resources_allow_only_the_observed_official_r2_object_host() -> None:
    registry = JsonSourceRegistry(package_registry_root("uk-network"))
    by_id = {item.source_id: item for item in registry.list_sources()}
    object_host = "83025b28472d6aa2bf5ae59f3724aa78.eu.r2.cloudflarestorage.com"

    for source_id in (
        "neso.dno-license-areas",
        "neso.etys-boundary-gis",
        "neso.fes-gsp-regional-demand",
        "neso.interconnector-register",
    ):
        assert object_host in by_id[source_id].allowed_domains


def test_missing_prompt98_sources_are_pinned_to_versioned_official_objects() -> None:
    registry = JsonSourceRegistry(package_registry_root("uk-network"))
    by_id = {item.source_id: item for item in registry.list_sources()}

    desnz = by_id["desnz.postcode-electricity-consumption"]
    assert desnz.discovery_config["revision_id"] == "DESNZ-postcode-electricity-2024"
    assert desnz.discovery_config["publication_date"] == "2025-12-18"
    assert desnz.discovery_config["download_url"] == (
        "https://assets.publishing.service.gov.uk/media/694282a1fdbd8404f9e1f1da/"
        "Postcode_level_all_meters_electricity_2024.csv"
    )
    assert "assets.publishing.service.gov.uk" in desnz.allowed_domains

    onspd = by_id["ons.postcode-directory"]
    assert onspd.discovery_config["revision_id"] == "ONSPD-May-2026-corrected-2026-06-04"
    assert onspd.discovery_config["publication_date"] == "2026-06-04"
    assert onspd.discovery_config["download_url"] == (
        "https://www.arcgis.com/sharing/rest/content/items/"
        "6fff67d204fd4f339591ed667a6e3642/data"
    )
    assert "arcgis.com" in onspd.allowed_domains

    interconnector = by_id["neso.interconnector-register"]
    assert interconnector.discovery_config["revision_id"] == (
        "NESO-interconnector-register-2026-08-18"
    )
    assert interconnector.discovery_config["publication_date"] == "2026-08-18"
    assert interconnector.discovery_config["download_url"] == (
        "https://api.neso.energy/dataset/a7cca714-9dbb-42b1-99c8-4bc7211605a8/"
        "resource/64f7908f-f787-4977-93e1-5342a5f1357f/download/"
        "interconnector-register-18-august-2026.csv"
    )


def test_prompt98_sources_record_conservative_object_level_redistribution_policy() -> None:
    registry = JsonSourceRegistry(package_registry_root("uk-network"))
    by_id = {item.source_id: item for item in registry.list_sources()}

    assert by_id["desnz.postcode-electricity-consumption"].redistribution_policy == "redistributable"
    assert by_id["ons.postcode-directory"].redistribution_policy == "local-use-only"
    assert by_id["neso.etys-capabilities"].redistribution_policy == "pointer-only"
    for source_id in (
        "neso.dno-license-areas",
        "neso.etys-boundary-gis",
        "neso.fes-gsp-regional-demand",
        "neso.interconnector-register",
    ):
        assert by_id[source_id].redistribution_policy == "redistributable"


def test_registry_rejects_duplicate_ids_and_unofficial_domains(tmp_path: Path) -> None:
    valid = {
        "schema_version": "value.data-source-definition/v1",
        "source_id": "neso.example",
        "authority": "NESO",
        "semantic_role": "example",
        "landing_page": "https://www.neso.energy/example",
        "discovery_adapter": "official_static_resource",
        "allowed_domains": ["neso.energy"],
        "licence_expected": "NESO Open Data Licence",
        "candidate_uses": ["test evidence"],
        "discovery_config": {"download_url": "https://www.neso.energy/example.csv"},
    }
    (tmp_path / "a.source.json").write_text(json.dumps(valid), encoding="utf-8")
    invalid = dict(valid)
    invalid["landing_page"] = "https://example.com/not-official"
    (tmp_path / "b.source.json").write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate|allowlisted"):
        JsonSourceRegistry(tmp_path)


def test_source_definitions_are_packaged_in_python_distributions() -> None:
    root = Path(__file__).resolve().parents[2]
    project = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert '"data_workbench/sources/**/*.json"' in project
