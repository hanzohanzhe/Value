from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from gridform_core.data_workbench.contracts import SourceDefinition
from gridform_core.data_workbench.discovery import (
    UrllibDiscoveryTransport,
    discover_source,
    discover_source_safe,
)
from gridform_core.data_workbench.reporting import render_discovery_reports


class FixtureTransport:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.payload = payload

    def get_json(self, url: str, *, allowed_domains: tuple[str, ...]) -> Mapping[str, object]:
        assert url == "https://api.neso.energy/dataset/example"
        assert allowed_domains == ("api.neso.energy",)
        return self.payload

    def get_text(self, url: str, *, allowed_domains: tuple[str, ...]) -> str:
        raise AssertionError("text discovery was not requested")


def source() -> SourceDefinition:
    return SourceDefinition(
        source_id="neso.example",
        authority="NESO",
        semantic_role="example",
        landing_page="https://api.neso.energy/dataset/example",
        discovery_adapter="neso_catalogue_resource",
        allowed_domains=("api.neso.energy",),
        licence_expected="NESO Open Data Licence",
        candidate_uses=("network validation",),
        discovery_config={"resource_name_contains": "GeoJSON"},
    )


def catalogue_payload() -> Mapping[str, object]:
    fixture = Path(__file__).parent / "fixtures" / "discovery" / "neso-catalogue.json"
    return json.loads(fixture.read_text(encoding="utf-8"))


class OfflineTransport(FixtureTransport):
    def get_json(self, url: str, *, allowed_domains: tuple[str, ...]) -> Mapping[str, object]:
        raise OSError("fixture portal is offline")


class FakeResponse:
    def __init__(self, body: bytes, final_url: str) -> None:
        self.body = body
        self.final_url = final_url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body

    def geturl(self) -> str:
        return self.final_url


class FakeOpener:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def open(self, request: object, timeout: float) -> FakeResponse:
        return self.response


def test_catalogue_discovery_marks_latest_and_superseded_revisions() -> None:
    revisions = discover_source(source(), FixtureTransport(catalogue_payload()), None)

    assert [(item.revision_id, item.status) for item in revisions] == [
        ("revision-2020", "superseded"),
        ("revision-2024", "new"),
    ]
    assert revisions[-1].publication_date == "2024-05-03"
    assert revisions[-1].media_type == "application/geo+json"


def test_installed_latest_revision_is_unchanged() -> None:
    revisions = discover_source(
        source(), FixtureTransport(catalogue_payload()), "revision-2024"
    )

    assert revisions[-1].status == "unchanged"


def test_portal_outage_is_recorded_without_mutating_installed_revision() -> None:
    revisions = discover_source_safe(
        source(), OfflineTransport({}), "revision-2024"
    )

    assert len(revisions) == 1
    assert revisions[0].status == "unavailable"
    assert revisions[0].revision_id == "revision-2024"
    assert revisions[0].object_key is None
    assert revisions[0].catalogue_metadata["installed_revision_id"] == "revision-2024"
    assert "offline" in str(revisions[0].catalogue_metadata["discovery_error"])


def test_live_transport_rejects_redirect_outside_official_allowlist() -> None:
    transport = UrllibDiscoveryTransport(
        opener=FakeOpener(FakeResponse(b"{}", "https://mirror.example/catalogue"))
    )

    try:
        transport.get_json(
            "https://api.neso.energy/catalogue",
            allowed_domains=("api.neso.energy",),
        )
    except ValueError as exc:
        assert "redirected outside" in str(exc)
    else:
        raise AssertionError("An off-domain redirect was accepted")


def test_changed_catalogue_licence_is_not_silently_accepted() -> None:
    payload = dict(catalogue_payload())
    resources = [dict(item) for item in payload["resources"]]  # type: ignore[index]
    resources[-1]["licence"] = "Unknown replacement terms"
    payload["resources"] = resources

    try:
        discover_source(source(), FixtureTransport(payload), None)
    except ValueError as exc:
        assert "licence" in str(exc).lower()
    else:
        raise AssertionError("A changed licence was silently accepted")


def test_discovery_reports_explain_candidate_uses(tmp_path: Path) -> None:
    revisions = discover_source(source(), FixtureTransport(catalogue_payload()), None)

    result = render_discovery_reports(
        {source().source_id: revisions},
        tmp_path,
        source_definitions={source().source_id: source()},
    )

    machine = json.loads((tmp_path / "source_discovery_report.json").read_text("utf-8"))
    assert machine["candidate_inventory"][0]["usable_for"] == ["network validation"]
    assert machine["candidate_inventory"][0]["status"] == "superseded"
    assert result["machine_report"] == "source_discovery_report.json"
    assert (tmp_path / "source_discovery_report.md").is_file()
