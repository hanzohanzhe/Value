"""Build a lock-derived dependency licence inventory without network access."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

from build_sbom import scoped_python_components


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _python_licence(name: str, expected_version: str) -> dict[str, object]:
    try:
        metadata = importlib.metadata.metadata(name)
        installed_version = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return {"license": "NOASSERTION", "source": "distribution_not_installed"}
    expression = str(metadata.get("License-Expression") or "").strip()
    legacy = str(metadata.get("License") or "").strip()
    classifiers = [
        value for value in metadata.get_all("Classifier", [])
        if value.startswith("License ::")
    ]
    return {
        "license": expression or legacy or ("; ".join(classifiers) if classifiers else "NOASSERTION"),
        "source": "installed_distribution_metadata",
        "metadata_distribution_version": installed_version,
        "metadata_version_matches_lock": installed_version == expected_version,
        "classifiers": classifiers,
    }


def build_inventory() -> dict[str, object]:
    package_lock = ROOT / "package-lock.json"
    python = []
    for row in scoped_python_components():
        python.append({**row, **_python_licence(str(row["name"]), str(row["version"]))})
    lock = json.loads(package_lock.read_text(encoding="utf-8"))
    node = []
    for path, metadata in sorted(lock.get("packages", {}).items()):
        if not path.startswith("node_modules/") or not isinstance(metadata, dict) or not metadata.get("version"):
            continue
        node.append({
            "path": path,
            "name": path.removeprefix("node_modules/"),
            "version": str(metadata["version"]),
            "license": str(metadata.get("license") or "NOASSERTION"),
            "integrity": metadata.get("integrity"),
            "dev": bool(metadata.get("dev")),
            "optional": bool(metadata.get("optional")),
        })
    return {
        "schema_version": "value.dependency-licences/v1",
        "source_locks": {
            "python": [
                {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
                for path in sorted((ROOT / "requirements").glob("force-*-py310.lock"))
            ],
            "node": {"path": str(package_lock.relative_to(ROOT)), "sha256": _sha256(package_lock)},
        },
        "summary": {
            "python": len(python),
            "python_noassertion": sum(row["license"] == "NOASSERTION" for row in python),
            "node": len(node),
            "node_noassertion": sum(row["license"] == "NOASSERTION" for row in node),
        },
        "python": python,
        "node": node,
    }


def main() -> None:
    output = ROOT / "publication" / "dependency-licenses.json"
    report = build_inventory()
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
