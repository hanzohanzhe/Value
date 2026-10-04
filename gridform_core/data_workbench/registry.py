"""Validated package-resource registry for official data sources."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from .contracts import SourceDefinition


OFFICIAL_AUTHORITIES = {
    "DESNZ",
    "NESO",
    "Ofgem",
    "ONS",
    "Official interconnector operator",
}


def package_registry_root(registry_id: str) -> Path:
    if not registry_id or any(part in registry_id for part in ("/", "\\", "..")):
        raise ValueError("Registry ID must be one safe path segment")
    return Path(__file__).resolve().parent / "sources" / registry_id


def _domain_allowed(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain.lower() or host.endswith("." + domain.lower()) for domain in domains)


class JsonSourceRegistry:
    def __init__(self, root: Path) -> None:
        root = Path(root)
        sources: dict[str, SourceDefinition] = {}
        for path in sorted(root.glob("*.source.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            source = SourceDefinition.from_dict(payload)
            self._validate(source)
            if source.source_id in sources:
                raise ValueError(f"Registry contains duplicate source ID {source.source_id}")
            sources[source.source_id] = source
        if not sources:
            raise ValueError(f"Source registry is empty: {root}")
        self._sources = sources

    @staticmethod
    def _validate(source: SourceDefinition) -> None:
        if source.authority not in OFFICIAL_AUTHORITIES:
            raise ValueError(f"Source {source.source_id} does not declare an official authority")
        if not source.landing_page.startswith("https://"):
            raise ValueError(f"Source {source.source_id} must use an HTTPS landing page")
        domains = tuple(source.allowed_domains)
        if not domains or not _domain_allowed(source.landing_page, domains):
            raise ValueError(f"Source {source.source_id} landing page is not allowlisted")
        if not source.licence_expected.strip() or not source.candidate_uses:
            raise ValueError(f"Source {source.source_id} lacks rights or purpose metadata")

    def list_sources(self) -> tuple[SourceDefinition, ...]:
        return tuple(self._sources[key] for key in sorted(self._sources))

    def get_source(self, source_id: str) -> SourceDefinition:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise KeyError(f"Unknown official source {source_id}") from exc

