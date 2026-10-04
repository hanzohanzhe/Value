"""Fail when package-lock install scripts differ from the reviewed allowlist."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "package-lock.json"
DEFAULT_ALLOWLIST = ROOT / "publication" / "dependency-install-script-allowlist.json"
DEFAULT_PACKAGE = ROOT / "package.json"


def verify_install_scripts(
    lock_path: Path,
    allowlist_path: Path,
    *,
    package_path: Path | None = None,
    today: date | None = None,
) -> dict[str, object]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    policy = json.loads(allowlist_path.read_text(encoding="utf-8"))
    today = today or date.today()
    review_by = date.fromisoformat(str(policy.get("review_by") or ""))
    actual = {
        path: {
            "path": path,
            "package": path.split("node_modules/")[-1],
            "version": str(metadata.get("version") or ""),
        }
        for path, metadata in lock.get("packages", {}).items()
        if isinstance(metadata, dict) and metadata.get("hasInstallScript")
    }
    allowed_rows = policy.get("entries")
    if not isinstance(allowed_rows, list):
        raise ValueError("Install-script allowlist has no entries")
    allowed = {str(row.get("path")): row for row in allowed_rows if isinstance(row, dict)}
    errors: list[str] = []
    if review_by < today:
        errors.append(f"install-script review expired on {review_by.isoformat()}")
    for path in sorted(set(actual).difference(allowed)):
        errors.append(f"undeclared install script: {path}@{actual[path]['version']}")
    for path in sorted(set(allowed).difference(actual)):
        errors.append(f"stale allowlist entry: {path}@{allowed[path].get('version')}")
    for path in sorted(set(actual).intersection(allowed)):
        row = allowed[path]
        if row.get("package") != actual[path]["package"] or str(row.get("version")) != actual[path]["version"]:
            errors.append(
                f"install-script identity changed: {path}; expected {row.get('package')}@{row.get('version')}, "
                f"found {actual[path]['package']}@{actual[path]['version']}"
            )
        for field in ("reachability", "reason", "disposition"):
            if not str(row.get(field) or "").strip():
                errors.append(f"allowlist entry lacks {field}: {path}")
    native_policy: dict[str, bool] | None = None
    if package_path is not None:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        raw_native = package.get("allowScripts")
        if not isinstance(raw_native, dict):
            errors.append("package.json has no npm allowScripts policy")
            native_policy = {}
        else:
            native_policy = {
                str(key): bool(value) for key, value in raw_native.items()
            }
        expected_native = {
            f"{row['package']}@{row['version']}"
            for row in allowed.values()
            if row.get("package") and row.get("version")
        }
        approved_native = {
            key for key, approved in (native_policy or {}).items() if approved
        }
        for key in sorted(expected_native.difference(approved_native)):
            errors.append(f"npm allowScripts approval missing: {key}")
        for key in sorted(approved_native.difference(expected_native)):
            errors.append(f"npm allowScripts approval is not in reviewed ledger: {key}")
    return {
        "schema_version": "value.install-script-verification/v1",
        "passed": not errors,
        "lock": str(lock_path.resolve()),
        "allowlist": str(allowlist_path.resolve()),
        "package": str(package_path.resolve()) if package_path is not None else None,
        "review_by": review_by.isoformat(),
        "install_scripts": [actual[path] for path in sorted(actual)],
        "npm_allow_scripts": native_policy,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--json-output", type=Path)
    arguments = parser.parse_args()
    report = verify_install_scripts(
        arguments.lock,
        arguments.allowlist,
        package_path=arguments.package,
    )
    if arguments.json_output:
        arguments.json_output.parent.mkdir(parents=True, exist_ok=True)
        arguments.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
