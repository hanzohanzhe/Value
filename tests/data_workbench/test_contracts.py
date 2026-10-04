from __future__ import annotations

from dataclasses import replace

import pytest

from gridform_core.data_workbench.contracts import (
    CandidatePack,
    SourceDefinition,
    SourceRevision,
    candidate_id,
    canonical_payload,
)


def source_definition() -> SourceDefinition:
    return SourceDefinition(
        source_id="neso.dno-license-areas",
        authority="NESO",
        semantic_role="dso_zone_geometry",
        landing_page="https://www.neso.energy/data-portal/gis-boundaries-gb-dno-license-areas",
        discovery_adapter="neso_catalogue_resource",
        allowed_domains=("neso.energy", "api.neso.energy"),
        licence_expected="NESO Open Data Licence",
        candidate_uses=("DSO zone construction",),
    )


def source_revision(*, object_key: str = "raw/sha256/abc") -> SourceRevision:
    return SourceRevision(
        source_id="neso.dno-license-areas",
        revision_id="2024-05-03",
        publication_date="2024-05-03",
        landing_page=source_definition().landing_page,
        download_url="https://api.neso.energy/example.geojson",
        media_type="application/geo+json",
        reported_licence="NESO Open Data Licence",
        discovered_at="2026-08-21T10:00:00Z",
        status="new",
        object_key=object_key,
    )


def candidate(*, observed_at: str) -> CandidatePack:
    return CandidatePack(
        build_manifest_hash="1" * 64,
        artifact_hashes={"zones": "2" * 64},
        source_revisions=(source_revision(),),
        validation_status="pending",
        candidate_inventory=(),
        requested_waivers=(),
        report_refs={},
        observed_at=observed_at,
    )


def test_candidate_identity_excludes_observation_timestamps() -> None:
    first = candidate(observed_at="2026-08-21T10:00:00Z")
    later = replace(first, observed_at="2026-08-21T11:00:00Z")

    assert candidate_id(first) == candidate_id(later)


def test_public_contract_rejects_absolute_paths() -> None:
    revision = source_revision(object_key=r"C:\private\source.csv")

    with pytest.raises(ValueError, match="absolute path"):
        canonical_payload(revision)


def test_unknown_contract_schema_is_rejected() -> None:
    payload = source_definition().to_dict()
    payload["schema_version"] = "value.unknown/v9"

    with pytest.raises(ValueError, match="schema_version"):
        SourceDefinition.from_dict(payload)


def test_source_definition_round_trips_without_type_loss() -> None:
    source = source_definition()

    assert SourceDefinition.from_dict(source.to_dict()) == source

