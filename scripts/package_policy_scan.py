"""Fail when a built distribution contains local research state or UK data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.path_hygiene import find_absolute_paths


FORBIDDEN_NAMES = (".gridform/", "value-uk-1000twh-reproduction", "run_logs/", "input-snapshot/")
RIGHTS_LEDGER = ROOT / "publication" / "release-rights-ledger.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _carbon_rights() -> dict[str, dict[str, object]]:
    payload = json.loads(RIGHTS_LEDGER.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "value.release-rights-ledger/v2":
        raise ValueError("Unsupported release-rights authority")
    return {str(row["path"]): row for row in payload.get("carbon_objects", [])}


def _inspect_member(name: str, data: bytes, issues: list[str], archive_name: str) -> None:
    normalized = name.replace("\\", "/")
    if any(value in normalized for value in FORBIDDEN_NAMES):
        issues.append(f"{archive_name}: prohibited path: {normalized}")
    suffix = Path(normalized).suffix.lower()
    if suffix in {".py", ".json", ".toml", ".txt", ".md", ".ps1", ".cmd"}:
        for finding in find_absolute_paths(data, suffix):
            issues.append(
                f"{archive_name}: absolute path in {normalized}:{finding.line}: "
                f"{finding.kind}: {finding.value}"
            )


def scan_dist(dist_dir: Path) -> tuple[list[str], Path, Path]:
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if not wheels:
        raise SystemExit(f"PACKAGE POLICY FAILED: no wheel found in {dist_dir}")
    if not sdists:
        raise SystemExit(f"PACKAGE POLICY FAILED: no source distribution found in {dist_dir}")
    issues: list[str] = []
    rights = _carbon_rights()
    seen_carbon: set[str] = set()
    with zipfile.ZipFile(wheels[-1]) as archive:
        for name in archive.namelist():
            data = archive.read(name)
            _inspect_member(name, data, issues, wheels[-1].name)
            marker = "gridform_core/data/carbon/"
            if marker in name:
                relative = name[name.index(marker):]
                seen_carbon.add(relative)
                row = rights.get(relative)
                if row is None:
                    issues.append(f"{wheels[-1].name}: carbon object has no rights decision: {relative}")
                elif row.get("decision") != "GO_IN_VALUE_CODE_PACKAGE_WITH_CITATIONS":
                    issues.append(f"{wheels[-1].name}: carbon object is not cleared: {relative}")
                elif row.get("sha256") != _sha256(data):
                    issues.append(f"{wheels[-1].name}: carbon rights hash mismatch: {relative}")
    with tarfile.open(sdists[-1], "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            handle = archive.extractfile(member)
            if handle is not None:
                _inspect_member(member.name, handle.read(), issues, sdists[-1].name)
    expected_carbon = set(rights)
    if seen_carbon != expected_carbon:
        missing = sorted(expected_carbon - seen_carbon)
        extra = sorted(seen_carbon - expected_carbon)
        if missing:
            issues.append("wheel omits cleared carbon objects: " + ", ".join(missing))
        if extra:
            issues.append("wheel includes undeclared carbon objects: " + ", ".join(extra))
    return issues, wheels[-1], sdists[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    dist_dir = args.dist_dir.resolve()
    issues, wheel, sdist = scan_dist(dist_dir)
    if issues:
        raise SystemExit("PACKAGE POLICY FAILED\n" + "\n".join(issues))
    print(f"PACKAGE POLICY PASSED: {wheel.name}, {sdist.name}")


if __name__ == "__main__":
    main()
