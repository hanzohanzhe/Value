"""Fail closed when public-release rights or repository hygiene are unresolved."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.path_hygiene import scan_path
from scripts.verify_public_uk_pack import verify as verify_public_uk_pack


PROHIBITED_ROOTS = {
    ".gridform", ".superpowers", ".venv", "outputs", "work", "node_modules", "dist", "build",
    "playwright-report", "test-results", ".git", ".next",
}
RUNTIME_ROOTS = {"backend", "gridform_core", "app", "scripts"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".ps1", ".cmd", ".json", ".toml"}
SECRET = re.compile(rb"(?:AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
SEPARATE_RELEASE_ASSET_ROOTS = {
    ("data-packs", "value-uk-open-data-pack-v1"),
}


def scan() -> dict[str, object]:
    inventory = json.loads((ROOT / "publication" / "rights-inventory.json").read_text(encoding="utf-8"))
    issues = []
    reference_findings = []
    non_runtime_findings = []
    separate_release_assets = []
    for parts in sorted(SEPARATE_RELEASE_ASSET_ROOTS):
        asset_root = ROOT.joinpath(*parts)
        relative_asset = asset_root.relative_to(ROOT).as_posix()
        if not (asset_root / "manifest.json").is_file():
            separate_release_assets.append({
                "path": relative_asset,
                "repository_treatment": "gitignored_separate_release_asset",
                "installed": False,
                "status": "NOT_INSTALLED_SEPARATE_ASSET",
                "verification": None,
            })
            continue
        verification = verify_public_uk_pack(asset_root)
        separate_release_assets.append({
            "path": relative_asset,
            "repository_treatment": "gitignored_separate_release_asset",
            "installed": True,
            "status": verification["decision"],
            "verification": verification,
        })
        if verification["decision"] != "GO":
            issues.append({
                "code": "GF_RELEASE_SEPARATE_ASSET_INVALID",
                "path": relative_asset,
                "errors": verification["errors"],
            })
    for row in inventory["items"]:
        if row["redistribution_class"] in {"blocked_owner_decision", "prohibited_until_confirmed"}:
            issues.append({"code": "GF_RELEASE_RIGHTS_UNRESOLVED", "item_id": row["id"]})
    for path in ROOT.rglob("*"):
        if not path.is_file() or set(path.relative_to(ROOT).parts).intersection(PROHIBITED_ROOTS) or ".git" in path.parts:
            continue
        relative = path.relative_to(ROOT).as_posix()
        relative_parts = path.relative_to(ROOT).parts
        if any(relative_parts[: len(parts)] == parts for parts in SEPARATE_RELEASE_ASSET_ROOTS):
            # These objects are not Git/package inputs.  They remain fail-closed
            # through the per-object public-pack verification above.
            continue
        if "__pycache__" in path.parts or path.suffix.lower() in {".pyc", ".pyo"}:
            # Interpreter caches are never release inputs; scanning embedded
            # bytecode strings would duplicate the source finding many times.
            continue
        if path.stat().st_size > 20 * 1024 * 1024:
            issues.append({"code": "GF_RELEASE_OVERSIZED_FILE", "path": relative, "bytes": path.stat().st_size}); continue
        data = path.read_bytes()
        if SECRET.search(data):
            issues.append({"code": "GF_RELEASE_SECRET_PATTERN", "path": relative})
        if path.suffix.lower() not in TEXT_SUFFIXES or path.name.startswith("redraw_"):
            continue
        for finding in scan_path(path):
            row = {
                "path": relative,
                "line": finding.line,
                "kind": finding.kind,
                "value": finding.value,
            }
            if relative.startswith("gridform_core/builtin/scheme_c_1000twh/compat/"):
                reference_findings.append(
                    {"code": "GF_RELEASE_RETAINED_REFERENCE_ABSOLUTE_PATH", **row}
                )
            elif path.relative_to(ROOT).parts[0] not in RUNTIME_ROOTS:
                non_runtime_findings.append(
                    {"code": "GF_RELEASE_NON_RUNTIME_ABSOLUTE_PATH", **row}
                )
            else:
                issues.append({"code": "GF_RELEASE_RUNTIME_ABSOLUTE_PATH", **row})
    return {
        "schema_version": "value.release-scan/v2",
        "go": not issues,
        "issues": issues,
        "reference_findings": reference_findings,
        "non_runtime_findings": non_runtime_findings,
        "separate_release_assets": separate_release_assets,
    }


def main() -> None:
    report = scan()
    output = ROOT / "publication" / "release-scan.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"go": report["go"], "issues": len(report["issues"])}, indent=2))
    raise SystemExit(0 if report["go"] else 1)


if __name__ == "__main__":
    main()
