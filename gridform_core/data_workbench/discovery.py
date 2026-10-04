"""Deterministic source-revision discovery without downloading resource bytes."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Mapping, Protocol
from urllib.parse import urlparse
from urllib.request import OpenerDirector, Request, build_opener

from .contracts import SourceDefinition, SourceRevision


class DiscoveryTransport(Protocol):
    def get_json(self, url: str, *, allowed_domains: tuple[str, ...]) -> Mapping[str, object]: ...

    def get_text(self, url: str, *, allowed_domains: tuple[str, ...]) -> str: ...


class UrllibDiscoveryTransport:
    """Small HTTPS transport used only by an explicit freshness audit."""

    def __init__(
        self,
        *,
        opener: OpenerDirector | object | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._opener = opener or build_opener()
        self._timeout_seconds = timeout_seconds

    def _read(self, url: str, allowed_domains: tuple[str, ...]) -> str:
        if not url.startswith("https://") or not _allowed(url, allowed_domains):
            raise ValueError("Discovery URL is outside the official allowlist")
        request = Request(url, headers={"User-Agent": "VALUE-Data-Workbench/1"})
        with self._opener.open(request, timeout=self._timeout_seconds) as response:  # type: ignore[attr-defined]
            final_url = str(response.geturl())
            if not final_url.startswith("https://") or not _allowed(final_url, allowed_domains):
                raise ValueError("Discovery request redirected outside the official allowlist")
            return response.read().decode("utf-8-sig")

    def get_json(
        self, url: str, *, allowed_domains: tuple[str, ...]
    ) -> Mapping[str, object]:
        payload = json.loads(self._read(url, allowed_domains))
        if not isinstance(payload, Mapping):
            raise ValueError("Discovery response is not a JSON object")
        return payload

    def get_text(self, url: str, *, allowed_domains: tuple[str, ...]) -> str:
        return self._read(url, allowed_domains)


_MEDIA_TYPES = {
    "csv": "text/csv",
    "geojson": "application/geo+json",
    "gpkg": "application/geopackage+sqlite3",
    "json": "application/json",
    "pdf": "application/pdf",
    "shp": "application/zip",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
}


def _allowed(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == item.lower() or host.endswith("." + item.lower()) for item in domains)


def _media_type(value: object) -> str:
    text = str(value or "").strip().lower().lstrip(".")
    return _MEDIA_TYPES.get(text, text or "application/octet-stream")


def _catalogue_revisions(
    source: SourceDefinition,
    payload: Mapping[str, object],
    installed_revision_id: str | None,
) -> tuple[SourceRevision, ...]:
    raw_resources = payload.get("resources")
    if not isinstance(raw_resources, list):
        raise ValueError(f"Catalogue for {source.source_id} has no resource list")
    name_filter = str(source.discovery_config.get("resource_name_contains") or "").lower()
    rows: list[Mapping[str, object]] = []
    for raw in raw_resources:
        if not isinstance(raw, Mapping):
            continue
        if name_filter and name_filter not in str(raw.get("name") or "").lower():
            continue
        url = str(raw.get("url") or "")
        if not url.startswith("https://") or not _allowed(url, tuple(source.allowed_domains)):
            raise ValueError(f"Discovered resource URL for {source.source_id} is not allowlisted")
        rows.append(raw)
    if not rows:
        raise ValueError(f"No matching resources discovered for {source.source_id}")
    rows.sort(key=lambda row: (str(row.get("last_modified") or ""), str(row.get("id") or "")))
    observed = str(payload.get("observed_at") or datetime.now(timezone.utc).isoformat())
    revisions: list[SourceRevision] = []
    for index, row in enumerate(rows):
        reported_licence = str(row.get("licence") or source.licence_expected).strip()
        if reported_licence.casefold() != source.licence_expected.strip().casefold():
            raise ValueError(
                f"Discovered licence for {source.source_id} changed from the reviewed expectation"
            )
        revision_id = str(row.get("id") or row.get("last_modified") or "")
        latest = index == len(rows) - 1
        status = "superseded"
        if latest:
            status = "unchanged" if revision_id == installed_revision_id else "new"
        revisions.append(
            SourceRevision(
                source_id=source.source_id,
                revision_id=revision_id,
                publication_date=str(row.get("last_modified") or ""),
                landing_page=source.landing_page,
                download_url=str(row.get("url") or ""),
                media_type=_media_type(row.get("format")),
                reported_licence=reported_licence,
                discovered_at=observed,
                status=status,
                catalogue_metadata={
                    "name": str(row.get("name") or ""),
                    "catalogue_id": revision_id,
                },
            )
        )
    return tuple(revisions)


def _static_revision(
    source: SourceDefinition, installed_revision_id: str | None
) -> tuple[SourceRevision, ...]:
    config = source.discovery_config
    revision_id = str(config.get("revision_id") or config.get("publication_date") or "current")
    url = str(config.get("download_url") or "")
    if not url.startswith("https://") or not _allowed(url, tuple(source.allowed_domains)):
        raise ValueError(f"Static resource URL for {source.source_id} is not allowlisted")
    return (
        SourceRevision(
            source_id=source.source_id,
            revision_id=revision_id,
            publication_date=str(config.get("publication_date") or ""),
            landing_page=source.landing_page,
            download_url=url,
            media_type=_media_type(config.get("format")),
            reported_licence=source.licence_expected,
            discovered_at=datetime.now(timezone.utc).isoformat(),
            status="unchanged" if revision_id == installed_revision_id else "new",
        ),
    )


def discover_source(
    source: SourceDefinition,
    transport: DiscoveryTransport,
    installed_revision_id: str | None,
) -> tuple[SourceRevision, ...]:
    if source.discovery_adapter == "neso_catalogue_resource":
        payload = transport.get_json(
            source.landing_page, allowed_domains=tuple(source.allowed_domains)
        )
        return _catalogue_revisions(source, payload, installed_revision_id)
    if source.discovery_adapter == "official_static_resource":
        return _static_revision(source, installed_revision_id)
    raise ValueError(f"Unknown discovery adapter {source.discovery_adapter}")


def discover_source_safe(
    source: SourceDefinition,
    transport: DiscoveryTransport,
    installed_revision_id: str | None,
) -> tuple[SourceRevision, ...]:
    """Discover a source while preserving an auditable outage record.

    Discovery never fetches resource bytes or changes an installed bundle.  A
    network/parser failure is therefore evidence about the observation attempt,
    not a reason to invalidate the last installed revision.
    """

    try:
        return discover_source(source, transport, installed_revision_id)
    except (OSError, TimeoutError, ValueError) as exc:
        media_type = (
            str(source.expected_media_types[0])
            if source.expected_media_types
            else "application/octet-stream"
        )
        return (
            SourceRevision(
                source_id=source.source_id,
                revision_id=installed_revision_id or "unresolved",
                publication_date="",
                landing_page=source.landing_page,
                download_url=source.landing_page,
                media_type=media_type,
                reported_licence=source.licence_expected,
                discovered_at=datetime.now(timezone.utc).isoformat(),
                status="unavailable",
                catalogue_metadata={
                    "installed_revision_id": installed_revision_id or "",
                    "discovery_error": f"{type(exc).__name__}: {exc}",
                },
            ),
        )
