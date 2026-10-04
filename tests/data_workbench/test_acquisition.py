from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import pytest

from gridform_core.data_workbench.acquisition import (
    FetchLimits,
    MediaTypeMismatch,
    UrllibFetchTransport,
    fetch_revision,
)
from gridform_core.data_workbench.contracts import SourceDefinition, SourceRevision
from gridform_core.data_workbench.object_store import LocalObjectStore


def definition(*, policy: str = "verify_each_revision") -> SourceDefinition:
    return SourceDefinition(
        source_id="neso.test",
        authority="NESO",
        semantic_role="fixture",
        landing_page="https://api.neso.energy/catalogue",
        discovery_adapter="official_static_resource",
        allowed_domains=("api.neso.energy",),
        licence_expected="NESO Open Data Licence",
        candidate_uses=("fixture compilation",),
        expected_media_types=("text/csv",),
        redistribution_policy=policy,
    )


def revision(revision_id: str = "r1") -> SourceRevision:
    return SourceRevision(
        source_id="neso.test",
        revision_id=revision_id,
        publication_date="2026-08-01",
        landing_page="https://api.neso.energy/catalogue",
        download_url="https://api.neso.energy/data.csv",
        media_type="text/csv",
        reported_licence="NESO Open Data Licence",
        discovered_at="2026-08-21T09:00:00+00:00",
        status="new",
    )


@dataclass
class FixtureResponse:
    blocks: Iterable[bytes]
    final_url: str = "https://api.neso.energy/data.csv"
    status: int = 200
    headers: Mapping[str, str] = None  # type: ignore[assignment]
    media_type: str = "text/csv"

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {"ETag": '"abc"'}

    def iter_bytes(self, chunk_size: int) -> Iterable[bytes]:
        return self.blocks


class FixtureTransport:
    def __init__(self, response: FixtureResponse) -> None:
        self.response = response

    def open(self, url: str, *, timeout_seconds: float) -> FixtureResponse:
        assert url == "https://api.neso.energy/data.csv"
        assert timeout_seconds > 0
        return self.response


class FakeHttpResponse:
    status = 200
    headers = {"Content-Type": "text/csv; charset=utf-8", "ETag": '"fixture"'}

    def __init__(self) -> None:
        self._blocks = iter((b"a,b\n", b"1,2\n", b""))

    def geturl(self) -> str:
        return "https://api.neso.energy/data.csv"

    def read(self, chunk_size: int) -> bytes:
        return next(self._blocks)

    def close(self) -> None:
        return None


class FakeOpener:
    def open(self, request: object, timeout: float) -> FakeHttpResponse:
        assert timeout == 2.0
        return FakeHttpResponse()


def test_fetch_emits_relative_receipt_and_reuses_bytes_across_revisions(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    transport = FixtureTransport(FixtureResponse([b"a,b\n", b"1,2\n"]))

    first = fetch_revision(
        definition(policy="redistributable"),
        revision("r1"),
        transport,
        store,
        limits=FetchLimits(max_bytes=1024, timeout_seconds=3.0),
        retrieved_at="2026-08-21T09:00:00+00:00",
    )
    second = fetch_revision(
        definition(policy="redistributable"),
        revision("r2"),
        transport,
        store,
        limits=FetchLimits(max_bytes=1024, timeout_seconds=3.0),
        retrieved_at="2026-08-21T09:01:00+00:00",
    )

    assert first.object_key == second.object_key
    assert first.revision_id != second.revision_id
    assert first.redistribution_decision == "redistributable"
    assert not Path(first.object_key).is_absolute()


def test_fetch_rejects_off_domain_redirect_and_media_mismatch(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    off_domain = FixtureTransport(
        FixtureResponse([b"x"], final_url="https://mirror.example/data.csv")
    )
    with pytest.raises(ValueError, match="redirect"):
        fetch_revision(definition(), revision(), off_domain, store)

    wrong_media = FixtureTransport(
        FixtureResponse([b"x"], media_type="application/pdf")
    )
    with pytest.raises(MediaTypeMismatch):
        fetch_revision(definition(), revision(), wrong_media, store)


def test_generic_binary_header_is_accepted_only_when_bytes_match_the_declared_type(
    tmp_path: Path,
) -> None:
    store = LocalObjectStore(tmp_path)
    generic_csv = FixtureTransport(
        FixtureResponse([b"period_id,value\n", b"p0,1\n"], media_type="application/octet-stream")
    )

    receipt = fetch_revision(definition(), revision(), generic_csv, store)

    assert receipt.media_type == "text/csv"
    with pytest.raises(MediaTypeMismatch, match="content signature"):
        fetch_revision(
            definition(),
            revision("bad-binary"),
            FixtureTransport(
                FixtureResponse([b"\x00\x01\x02\x03"], media_type="application/octet-stream")
            ),
            store,
        )


def test_unknown_rights_are_explicit_and_blocking(tmp_path: Path) -> None:
    receipt = fetch_revision(
        definition(),
        revision(),
        FixtureTransport(FixtureResponse([b"x"])),
        LocalObjectStore(tmp_path),
    )

    assert receipt.redistribution_decision == "needs_rights_review"


def test_urllib_transport_streams_in_chunks_without_extracting_content() -> None:
    response = UrllibFetchTransport(opener=FakeOpener()).open(
        "https://api.neso.energy/data.csv", timeout_seconds=2.0
    )

    assert response.media_type == "text/csv"
    assert list(response.iter_bytes(4)) == [b"a,b\n", b"1,2\n"]
