"""Explicit live freshness audit for registered official data sources.

This command discovers metadata only. It does not download source objects,
compile data packs, or alter an installed benchmark.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from gridform_core.data_workbench.discovery import (
    UrllibDiscoveryTransport,
    discover_source_safe,
)
from gridform_core.data_workbench.registry import JsonSourceRegistry, package_registry_root
from gridform_core.data_workbench.reporting import render_discovery_reports


def _installed_revisions(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    revisions = payload.get("installed_revisions", payload)
    if not isinstance(revisions, dict):
        raise ValueError("Installed revision file must contain a JSON object")
    return {str(key): str(value) for key, value in revisions.items()}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="uk-network")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--installed-revisions", type=Path)
    args = parser.parse_args(argv)

    registry = JsonSourceRegistry(package_registry_root(args.registry))
    installed = _installed_revisions(args.installed_revisions)
    transport = UrllibDiscoveryTransport()
    sources = {item.source_id: item for item in registry.list_sources()}
    revisions = {
        source_id: discover_source_safe(
            source,
            transport,
            installed.get(source_id),
        )
        for source_id, source in sources.items()
    }
    reports = render_discovery_reports(
        revisions,
        args.output,
        source_definitions=sources,
    )
    print(json.dumps(reports, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
