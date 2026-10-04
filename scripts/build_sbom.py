"""Build bounded CycloneDX-style dependency inventories from committed locks."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")
PYTHON_LOCKS = (
    "value-all-py310.lock",
    "value-perfect-foresight-py310.lock",
    "value-validation-py310.lock",
    "value-ci-tools-py310.lock",
)


def python_components(path: Path, seen: set[Path] | None = None) -> list[dict[str, str]]:
    seen = seen or set()
    path = path.resolve()
    if path in seen:
        return []
    seen.add(path)
    rows: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("-r "):
            rows.extend(python_components(path.parent / line[3:].strip(), seen))
        elif match := PIN.fullmatch(line):
            rows.append({"type": "library", "name": match.group(1), "version": match.group(2), "purl": f"pkg:pypi/{match.group(1)}@{match.group(2)}"})
    return rows


def scoped_python_components() -> list[dict[str, object]]:
    components: dict[tuple[str, str], dict[str, object]] = {}
    for lock_name in PYTHON_LOCKS:
        scope = lock_name.removesuffix(".lock")
        for row in python_components(ROOT / "requirements" / lock_name):
            key = (row["name"].lower().replace("_", "-"), row["version"])
            component = components.setdefault(key, {**row, "lock_scopes": []})
            scopes = component["lock_scopes"]
            assert isinstance(scopes, list)
            if scope not in scopes:
                scopes.append(scope)
    for component in components.values():
        scopes = component.pop("lock_scopes")
        component["properties"] = [{
            "name": "force:lock-scopes",
            "value": ",".join(sorted(str(value) for value in scopes)),
        }]
    return sorted(components.values(), key=lambda row: (str(row["name"]).lower(), str(row["version"])))


def main() -> None:
    destination = ROOT / "publication" / "sbom"
    destination.mkdir(parents=True, exist_ok=True)
    python = scoped_python_components()
    package_lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    node = []
    for package_path, metadata in package_lock.get("packages", {}).items():
        if not package_path.startswith("node_modules/") or not metadata.get("version"):
            continue
        name = package_path.removeprefix("node_modules/")
        version = str(metadata["version"])
        node.append({"type": "library", "name": name, "version": version, "purl": f"pkg:npm/{name}@{version}"})
    base = {"bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1}
    (destination / "python.cdx.json").write_text(json.dumps({**base, "components": python}, indent=2), encoding="utf-8")
    (destination / "node.cdx.json").write_text(json.dumps({**base, "components": sorted(node, key=lambda row: row["name"].lower())}, indent=2), encoding="utf-8")
    print(f"SBOM: {len(python)} Python and {len(node)} Node components")


if __name__ == "__main__":
    main()
