"""Verify the frozen VALUE-UK suite and its retained read-only sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.data_bundle import validate_data_bundle  # noqa: E402
from gridform_core.research_suite import (  # noqa: E402
    BASE_MEMBER,
    NETWORK_MEMBER,
    validate_research_suite,
)
from scripts.build_value_uk_research_suite import _tree_sha256  # noqa: E402


TEXT_SUFFIXES = {".json", ".md", ".txt", ".yml", ".yaml"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_value_only(archive: zipfile.ZipFile, label: str) -> None:
    for name in archive.namelist():
        if "force" in name.lower():
            raise ValueError(f"Legacy product identity remains in {label} member name: {name}")
        if Path(name).suffix.lower() in TEXT_SUFFIXES:
            text = archive.read(name).decode("utf-8")
            if "force" in text.lower():
                raise ValueError(f"Legacy product identity remains in {label} text: {name}")


def verify(
    *,
    suite_path: Path,
    receipt_path: Path,
    base_source: Path,
    network_source: Path,
    report_path: Path,
) -> dict[str, object]:
    suite_path = Path(suite_path).resolve()
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    source_hashes = [_tree_sha256(Path(base_source).resolve()), _tree_sha256(Path(network_source).resolve())]
    if source_hashes != receipt.get("source_tree_sha256"):
        raise ValueError("A retained source tree changed after the VALUE-UK build")
    if _sha256(suite_path) != receipt.get("sha256"):
        raise ValueError("VALUE-UK suite hash does not match its build receipt")
    validated = validate_research_suite(suite_path)
    component_reports: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="value-uk-verify-") as folder:
        temporary = Path(folder)
        with zipfile.ZipFile(suite_path) as suite:
            _assert_value_only(suite, "research suite")
            for index, member in enumerate((BASE_MEMBER, NETWORK_MEMBER)):
                target = temporary / f"component-{index}.zip"
                with suite.open(member) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                component = validate_data_bundle(target)
                with zipfile.ZipFile(target) as bundle:
                    _assert_value_only(bundle, member)
                component_reports.append({
                    "member": member,
                    "pack_id": component.descriptor["pack_id"],
                    "bundle_sha256": component.bundle_sha256,
                    "members": len(component.members),
                })
    report = {
        "schema_version": "value.research-suite-verification/v1",
        "passed": True,
        "suite_id": validated.descriptor["suite_id"],
        "suite_sha256": validated.suite_sha256,
        "suite_bytes": validated.suite_bytes,
        "source_tree_sha256": source_hashes,
        "source_trees_unchanged": True,
        "legacy_public_identity_absent": True,
        "components": component_reports,
    }
    report_path = Path(report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--base-source", required=True, type=Path)
    parser.add_argument("--network-source", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(verify(
        suite_path=arguments.suite,
        receipt_path=arguments.receipt,
        base_source=arguments.base_source,
        network_source=arguments.network_source,
        report_path=arguments.report,
    ), indent=2))


if __name__ == "__main__":
    main()
