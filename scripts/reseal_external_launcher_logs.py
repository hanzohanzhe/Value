"""Exclude external launcher logs and reseal a completed VALUE bundle.

The command changes only artifact-index.json and provenance.json. It refuses to
run if the existing bundle has any validation error unrelated to a recognized
external supervisor log, or if any scientific artifact changes during resealing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.bundle_validator import validate_run_bundle
from gridform_core.provenance import (
    _artifact_index,
    _is_external_launcher_log,
    _write_artifact_index,
    sha256_file,
)


MUTABLE_SEAL_FILES = {"artifact-index.json", "provenance.json"}


def scientific_hashes(run_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name in MUTABLE_SEAL_FILES:
            continue
        if _is_external_launcher_log(path) or path.suffix.lower() in {".tmp", ".wal", ".shm"}:
            continue
        hashes[path.relative_to(run_dir).as_posix()] = sha256_file(path)
    return hashes


def reseal(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    provenance_path = run_dir / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance.get("completion", {}).get("status") != "completed":
        raise RuntimeError("Only a completed run bundle can be resealed")

    before_validation = validate_run_bundle(run_dir)
    unrelated = [
        error
        for error in before_validation.get("errors", [])
        if not _is_external_launcher_log(Path(str(error.get("artifact_id", ""))))
    ]
    if unrelated:
        raise RuntimeError(
            "Refusing to reseal because the bundle has non-launcher errors: "
            + json.dumps(unrelated, ensure_ascii=False)
        )

    before_science = scientific_hashes(run_dir)
    excluded = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file() and _is_external_launcher_log(path):
            excluded.append(
                {
                    "artifact_id": path.relative_to(run_dir).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )

    artifact_index = run_dir / "artifact-index.json"
    old_index_hash = sha256_file(artifact_index)
    old_provenance_hash = sha256_file(provenance_path)
    _write_artifact_index(run_dir, run_dir)
    provenance["artifacts"] = _artifact_index(run_dir, run_dir)
    temporary = provenance_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(provenance_path)

    after_science = scientific_hashes(run_dir)
    if before_science != after_science:
        raise RuntimeError("A scientific artifact changed while resealing")
    after_validation = validate_run_bundle(run_dir)
    if not after_validation.get("valid"):
        raise RuntimeError(
            "Resealed bundle is invalid: "
            + json.dumps(after_validation.get("errors"), ensure_ascii=False)
        )
    return {
        "schema_version": "value.external-launcher-log-reseal/v1",
        "passed": True,
        "run_dir": str(run_dir),
        "reason": "external supervisor log changed after model provenance closed",
        "before_validation": before_validation,
        "excluded_external_logs": excluded,
        "scientific_artifacts_checked": len(before_science),
        "scientific_artifact_hashes_unchanged": True,
        "seal_changes": {
            "artifact_index_sha256_before": old_index_hash,
            "artifact_index_sha256_after": sha256_file(artifact_index),
            "provenance_sha256_before": old_provenance_hash,
            "provenance_sha256_after": sha256_file(provenance_path),
        },
        "after_validation": after_validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    report = reseal(args.run_dir)
    output = args.audit.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"passed": True, "audit": str(output)}, indent=2))


if __name__ == "__main__":
    main()
