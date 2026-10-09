"""Fail when a public PSM identity can denote more than one execution route."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.v2.module_manifest import workspace_registry  # noqa: E402


CANONICAL = (
    "gridform_core.builtin.scheme_c_1000twh.scheme_c_native_psm:"
    "SchemeCNativePSM"
)
PRODUCTION_ROOTS = (ROOT / "gridform_core", ROOT / "backend")
NON_PRODUCTION = {
    "gridform_core/reference_comparison.py",
    "gridform_core/builtin/scheme_c_1000twh/modular_run.py",
    "gridform_core/builtin/scheme_c_1000twh/scheme_c_modules.py",
    "gridform_core/builtin/scheme_c_1000twh/reference/__init__.py",
    "gridform_core/builtin/scheme_c_1000twh/reference/replay.py",
    "gridform_core/builtin/scheme_c_1000twh/factory.py",
    "gridform_core/builtin/scheme_c_1000twh/psm.py",
}
FORBIDDEN_IMPORT_FRAGMENTS = (
    "scheme_c_1000twh.factory",
    "scheme_c_1000twh.psm",
    "SchemeCReplayData",
    "run_modular_scheme_c",
)


def _literal_psm_ids(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return rows
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if not isinstance(value, ast.Constant) or value.value != "value-bid-at-cost-psm":
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "id":
                rows.append({"path": path.relative_to(ROOT).as_posix(), "line": node.lineno})
    return rows


def build_report() -> dict[str, object]:
    registry = workspace_registry(strict=True)
    psm_manifests = [item for item in registry.manifests().values() if item.slot == "psm"]
    duplicate_ids = sorted({item.id for item in psm_manifests if sum(x.id == item.id for x in psm_manifests) > 1})
    canonical = registry.manifest("value-bid-at-cost-psm", expected_slot="psm")
    literal_ids: list[dict[str, object]] = []
    route_findings: list[dict[str, object]] = []
    for root in PRODUCTION_ROOTS:
        for path in root.rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            if relative in NON_PRODUCTION or "/runtime_compat/" in f"/{relative}":
                continue
            literal_ids.extend(_literal_psm_ids(path))
            text = path.read_text(encoding="utf-8")
            matched = [token for token in FORBIDDEN_IMPORT_FRAGMENTS if token in text]
            if matched:
                route_findings.append({"path": relative, "tokens": matched})
    passed = (
        not duplicate_ids
        and canonical.implementation == CANONICAL
        and canonical.execution_kind == "live_module"
        and len(literal_ids) == 1
        and literal_ids[0]["path"]
        == "gridform_core/builtin/scheme_c_1000twh/scheme_c_native_psm.py"
        and not route_findings
    )
    return {
        "schema_version": "value.psm-entrypoint-scan/v1",
        "canonical_module_id": canonical.id,
        "canonical_entry_point": canonical.implementation,
        "canonical_version": canonical.version,
        "canonical_execution_kind": canonical.execution_kind,
        "registered_psm_ids": sorted(item.id for item in psm_manifests),
        "duplicate_ids": duplicate_ids,
        "literal_public_id_implementations": literal_ids,
        "normal_route_findings": route_findings,
        "explicit_reference_identity": "doctoral-reproduction-comparison",
        "passed": passed,
    }


def main() -> None:
    report = build_report()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
