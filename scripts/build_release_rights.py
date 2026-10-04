"""Build the authoritative VALUE release-rights ledger and its projections."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = "publication/release-rights-ledger.json"
UK_RIGHTS = ROOT / "data-packs" / "value-uk-open-data-pack-v1" / "RIGHTS.json"
UK_BILL = ROOT / "publication" / "value-uk-open-data-pack" / "bill-of-data.json"
SOURCE_PLAN = ROOT / "publication" / "uk-source-plan.json"
INVENTORY = ROOT / "publication" / "rights-inventory.json"
CARBON_ROOT = ROOT / "gridform_core" / "data" / "carbon"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_ledger() -> dict[str, Any]:
    rights = _read_json(UK_RIGHTS)
    bill = _read_json(UK_BILL)
    rights_by_role = {str(row["role"]): row for row in rights.get("objects", [])}
    bill_by_role = {
        str(row["canonical_role"]): row for row in bill.get("objects", [])
    }
    if len(rights_by_role) != 25 or set(rights_by_role) != set(bill_by_role):
        raise ValueError("UK rights and bill-of-data must describe the same 25 roles")
    uk_objects: list[dict[str, Any]] = []
    for role in sorted(rights_by_role):
        decision = rights_by_role[role]
        evidence = bill_by_role[role]
        if decision.get("decision") != "GO":
            raise ValueError(f"UK object is not cleared for the release asset: {role}")
        uk_objects.append(
            {
                "object_id": f"uk-role:{role}",
                "path": (
                    "data-packs/value-uk-open-data-pack-v1/"
                    + str(evidence["local_uri"])
                ),
                "canonical_role": role,
                "bytes": evidence["bytes"],
                "sha256": evidence["sha256"],
                "decision": "GO_WITH_ATTRIBUTION",
                "licence": decision["licence"],
                "redistribution_class": decision["redistribution_class"],
                "source_url": decision.get("source_url"),
                "attribution": decision["attribution"],
                "transformation": evidence.get("transformation"),
                "scientific_caveat": (
                    "Contains approximate historical cells and model projections; "
                    "redistribution approval is not a claim of observational authority."
                    if role == "policy.support"
                    else None
                ),
            }
        )

    carbon_objects: list[dict[str, Any]] = []
    for path in sorted(item for item in CARBON_ROOT.rglob("*") if item.is_file()):
        relative = path.relative_to(ROOT).as_posix()
        carbon_objects.append(
            {
                "object_id": f"carbon:{path.relative_to(CARBON_ROOT).as_posix()}",
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "decision": "GO_IN_VALUE_CODE_PACKAGE_WITH_CITATIONS",
                "licence": (
                    "Apache-2.0 for the VALUE schema, scenario configuration, "
                    "compilation and reproducibility snapshot"
                ),
                "redistribution_class": (
                    "owner_authored_model_parameter_compilation; cited factual values "
                    "retain source attribution; source publications are not redistributed"
                ),
                "source_register": "gridform_core/data/carbon/sources.csv",
            }
        )

    return {
        "schema_version": "value.release-rights-ledger/v2",
        "ledger_id": "force-release-rights-2026-08-19",
        "audit_date": "2026-08-19",
        "not_legal_advice": True,
        "authority": {
            "path": AUTHORITY,
            "precedence": (
                "This ledger is authoritative. RIGHTS.json, bill-of-data, source-plan "
                "and THIRD_PARTY_NOTICES are checked projections and must not override it."
            ),
        },
        "owner_attribution": {
            "copyright_holder": "Hanzhe Xing",
            "contributing_supervisors_and_advisors": ["Stuart Scott", "John Miles"],
        },
        "products": [
            {
                "product_id": "force-source-and-python",
                "decision": "GO_PRIVATE_COLLABORATION_AND_PUBLIC_SOURCE",
                "licence": "Apache-2.0",
                "includes": "VALUE code and owner-authored VALUE software copy",
                "excludes": "UK data payload, local state, run outputs and source publications",
            },
            {
                "product_id": "force-documentation",
                "decision": "GO_WITH_ATTRIBUTION",
                "licence": "CC-BY-4.0",
                "includes": "Repository-authored documentation",
                "excludes": "The private thesis document and third-party publications",
            },
            {
                "product_id": "value-synthetic-contract-pack-v1",
                "decision": "GO",
                "licence": "CC0-1.0",
                "includes": "Deterministic synthetic tutorial and CI data only",
            },
            {
                "product_id": "value-uk-benchmark-2025-v1",
                "decision": "GO_AS_SEPARATE_RIGHTS_GOVERNED_DATA_BUNDLE",
                "licence": "per-object",
                "objects": 25,
                "required_attribution": True,
                "ordinary_git_history": False,
            },
            {
                "product_id": "force-carbon-model-parameters",
                "decision": "GO_IN_VALUE_CODE_PACKAGE_WITH_CITATIONS",
                "licence": (
                    "Apache-2.0 for the VALUE compilation/schema; cited sources retain terms"
                ),
                "source_documents_included": False,
                "scientific_boundary": (
                    "Reproduction snapshots remain literal and disputed units/citations are "
                    "flagged; the reference catalogue is not automatically active."
                ),
            },
        ],
        "uk_data_objects": uk_objects,
        "carbon_objects": carbon_objects,
        "release_boundaries": {
            "source_archive": [
                "force-source-and-python",
                "force-documentation",
                "value-synthetic-contract-pack-v1",
                "force-carbon-model-parameters",
            ],
            "python_wheel": ["force-source-and-python", "force-carbon-model-parameters"],
            "separate_data_asset": ["value-uk-benchmark-2025-v1"],
            "never_distributed": [
                "private thesis document",
                "local .gridform state",
                "historical run directories",
                "cited source PDFs and reports",
            ],
        },
    }


def _project_existing_files(ledger: dict[str, Any]) -> None:
    inventory = _read_json(INVENTORY)
    inventory["schema_version"] = "value.release-rights-inventory/v2"
    inventory["audit_date"] = ledger["audit_date"]
    inventory["authority"] = AUTHORITY
    inventory["public_release_status"] = (
        "CODE_DOCS_SYNTHETIC_CARBON_GO; UK_DATA_GO_AS_SEPARATE_PER_OBJECT_ASSET"
    )
    for item in inventory.get("items", []):
        if item.get("id") == "installed-uk-pack":
            item["redistribution_class"] = (
                "separate_rights_governed_asset_go_per_object_with_attribution"
            )
            item["evidence"] = (
                "publication/release-rights-ledger.json; "
                "data-packs/value-uk-open-data-pack-v1/RIGHTS.json"
            )
            item["note"] = (
                "The UK payload remains separate from source/wheel and is installed "
                "transactionally from value.data-bundle/v1."
            )
        if item.get("id") == "carbon-catalogue":
            item["licence"] = (
                "Apache-2.0 for VALUE schema/configuration/compilation; cited sources retain terms"
            )
            item["redistribution_class"] = (
                "included_in_code_package_with_source_citations_no_source_documents"
            )
            item["evidence"] = AUTHORITY
    inventory["remaining_release_actions"] = [
        "Keep UK payload separate from ordinary source and wheel products.",
        "Regenerate and validate the rights ledger when any data or carbon object changes.",
        "Do not describe the policy workbook's projected/approximate cells as authority observations.",
    ]
    _write_json(INVENTORY, inventory)

    source_plan = _read_json(SOURCE_PLAN)
    source_plan["version"] = "1.0.0-rights-ledger-aligned"
    source_plan["audit_date"] = ledger["audit_date"]
    source_plan["default_status"] = "go_per_object_with_attribution_as_separate_asset"
    source_plan["authority"] = AUTHORITY
    _write_json(SOURCE_PLAN, source_plan)

    bill = _read_json(UK_BILL)
    bill["version"] = "1.0.0-rights-ledger-aligned"
    bill["authority"] = AUTHORITY
    bill["publication_status"] = "PUBLIC_REDISTRIBUTION_GO_PER_OBJECT_WITH_ATTRIBUTION"
    for row in bill.get("objects", []):
        row["included_in_public_archive"] = True
        row["public_release_product"] = "value-uk-benchmark-2025-v1"
    _write_json(UK_BILL, bill)


def _notice(ledger: dict[str, Any]) -> str:
    uk_sources: dict[str, str] = {}
    for row in ledger["uk_data_objects"]:
        key = str(row["licence"])
        uk_sources.setdefault(key, str(row["attribution"]))
    rows = [
        "# Third-party and data notices",
        "",
        "This file is a checked human-readable projection of",
        "`publication/release-rights-ledger.json`. The machine-readable ledger",
        "takes precedence if this text is stale.",
        "",
        "## Release products",
        "",
        "- VALUE software, including the owner-authored VALUE software copy: Apache-2.0.",
        "- Repository-authored documentation: CC BY 4.0.",
        "- Synthetic contract data pack: CC0 1.0.",
        "- UK benchmark data: separate per-object rights-governed asset; not in the wheel/source ZIP.",
        "- VALUE carbon parameter compilation/schema: Apache-2.0, with cited source terms retained.",
        "",
        "## UK benchmark attribution",
        "",
    ]
    for licence, attribution in sorted(uk_sources.items()):
        rows.append(f"- **{licence}:** {attribution}")
    rows.extend(
        [
            "",
            "The policy-support workbook contains owner-authored aggregation, approximate",
            "historical entries and forward model projections. Permission to redistribute",
            "does not make those cells official observations.",
            "",
            "## Carbon source boundary",
            "",
            "VALUE distributes its schema, scenarios, compilation and reproducibility rows,",
            "not copies of the cited thesis, reports, papers or environmental statements.",
            "`gridform_core/data/carbon/sources.csv` supplies citations and boundary notes.",
            "The VALUE and Chapter 4 snapshots are not silently corrected.",
            "",
            "## Attribution",
            "",
            "Copyright © Hanzhe Xing. Stuart Scott and John Miles are acknowledged",
            "contributing supervisors and advisors.",
            "",
        ]
    )
    return "\n".join(rows)


def validate_ledger(
    ledger: dict[str, Any], *, require_uk_payload: bool = True
) -> list[str]:
    """Validate the rights authority.

    Release assembly keeps ``require_uk_payload=True`` and therefore fails
    closed unless every separately distributed UK object is present.  A clean
    source checkout may set it to false to validate the checked-in authority,
    its decisions and all source-distributed carbon objects without pretending
    that the UK payload belongs in ordinary Git history.
    """
    errors: list[str] = []
    if ledger.get("schema_version") != "value.release-rights-ledger/v2":
        errors.append("invalid authority schema")
    uk = ledger.get("uk_data_objects") or []
    if len(uk) != 25 or len({row.get("canonical_role") for row in uk}) != 25:
        errors.append("authority must contain 25 unique UK roles")
    for row in [*uk, *(ledger.get("carbon_objects") or [])]:
        path = ROOT / str(row.get("path") or "")
        is_uk_payload = str(row.get("object_id") or "").startswith("uk-role:")
        if is_uk_payload and not require_uk_payload:
            if not row.get("sha256") or not row.get("bytes"):
                errors.append(f"missing UK evidence: {row.get('canonical_role')}")
            if not row.get("decision") or not row.get("licence"):
                errors.append(
                    f"missing decision/licence: {row.get('canonical_role')}"
                )
            continue
        if not path.is_file():
            errors.append(f"missing release object: {row.get('path')}")
            continue
        if row.get("sha256") != _sha256(path):
            errors.append(f"hash mismatch: {row.get('path')}")
        if not row.get("decision") or not row.get("licence"):
            errors.append(f"missing decision/licence: {row.get('path')}")
    return errors


def main() -> None:
    ledger = build_ledger()
    errors = validate_ledger(ledger)
    if errors:
        raise SystemExit("RIGHTS LEDGER FAILED\n" + "\n".join(errors))
    _write_json(ROOT / AUTHORITY, ledger)
    _project_existing_files(ledger)
    (ROOT / "THIRD_PARTY_NOTICES.md").write_text(_notice(ledger), encoding="utf-8")
    print(
        "RIGHTS LEDGER PASSED: "
        f"{len(ledger['uk_data_objects'])} UK and "
        f"{len(ledger['carbon_objects'])} carbon objects"
    )


if __name__ == "__main__":
    main()
