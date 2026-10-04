"""Build a metadata-only provenance index for the installed UK research pack.

The command never copies, edits or republishes the installed source objects. It
records relative URIs and hashes so local scientific runs and publication-rights
decisions can be audited separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.catalog import DATASET_SLOTS  # noqa: E402


DEFAULT_PACK = ROOT / ".gridform" / "data-packs" / "value-uk-1000twh-reproduction"
PLAN = ROOT / "publication" / "uk-source-plan.json"
OUTPUT = ROOT / "publication" / "value-uk-open-data-pack"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def contained_path(root: Path, uri: str) -> Path:
    candidate = (root / uri).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Binding escapes the pack root: {uri}") from exc
    return candidate


def build_inventory(pack_root: Path, *, verify_files: bool) -> dict[str, object]:
    manifest_path = pack_root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    sources = plan["source_catalog"]
    rules = plan["role_rules"]
    objects: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []

    for slot in DATASET_SLOTS:
        role = str(slot["role"])
        binding = manifest.get("bindings", {}).get(role)
        rule = rules.get(role)
        if binding is None or rule is None:
            errors.append({"role": role, "error": "missing_binding_or_source_rule"})
            continue
        source = sources[str(rule["source_id"])]
        uri = str(binding["uri"])
        local_file = contained_path(pack_root, uri)
        size_matches = local_file.is_file() and local_file.stat().st_size == int(binding["bytes"])
        hash_matches: bool | None = None
        if verify_files and local_file.is_file():
            hash_matches = file_sha256(local_file) == str(binding["sha256"])
        if not local_file.is_file() or not size_matches or hash_matches is False:
            errors.append({
                "role": role,
                "error": "local_object_integrity_failed",
                "exists": local_file.is_file(),
                "size_matches": size_matches,
                "hash_matches": hash_matches,
            })
        redistribution = rule.get(
            "redistribution_class",
            "conditional_exact_source_and_licence_review",
        )
        objects.append({
            "canonical_role": role,
            "required": bool(slot.get("required")),
            "downstream_module_use": slot["group"],
            "local_pack_id": manifest["id"],
            "local_uri": uri,
            "filename": binding.get("filename"),
            "format": binding.get("format"),
            "unit": binding.get("unit", slot.get("unit")),
            "bytes": binding.get("bytes"),
            "sha256": binding.get("sha256"),
            "source_release_recorded_by_local_pack": binding.get("source_release"),
            "source_id": rule["source_id"],
            "source_publisher": source["publisher"],
            "source_title": source["title"],
            "source_url": source.get("source_url"),
            "source_version": source.get("source_version"),
            "doi": source.get("doi"),
            "exact_licence": source.get("exact_licence"),
            "licence_evidence_url": source.get("licence_evidence_url"),
            "attribution": source.get("attribution"),
            "evidence_basis": source.get("evidence_basis"),
            "transformation": rule.get("transformation", binding.get("transform")),
            "redistribution_class": redistribution,
            "included_in_public_archive": False,
            "local_integrity": {
                "size_matches": size_matches,
                "hash_verified": hash_matches,
            },
        })

    identified = sum(bool(row.get("source_id")) for row in objects)
    licence_pinned = sum(bool(row.get("exact_licence")) for row in objects)
    rights_ready = all(
        str(row.get("redistribution_class") or "").startswith(
            ("redistributable_", "owner_licensed_")
        )
        and bool(row.get("exact_licence"))
        and bool(row.get("attribution"))
        for row in objects
    )
    inventory = {
        "schema_version": "value.local-data-source-inventory/v1",
        "audit_date": plan["audit_date"],
        "local_pack_id": manifest["id"],
        "local_pack_root": f"force-data://{manifest['id']}",
        "local_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "policy": "Metadata index only: source files remain unchanged in the installed local pack.",
        "publication_status": (
            "PUBLIC_REDISTRIBUTION_GO_PER_OBJECT_WITH_ATTRIBUTION"
            if rights_ready else
            "LOCAL_RUNTIME_COMPLETE_PUBLIC_REDISTRIBUTION_CONDITIONAL"
        ),
        "roles_expected": len(DATASET_SLOTS),
        "roles_locally_available": len(objects),
        "roles_source_identified": identified,
        "roles_with_licence_label": licence_pinned,
        "roles_in_public_archive": 0,
        "file_integrity_verified": verify_files,
        "errors": errors,
        "objects": objects,
    }
    return inventory


def write_outputs(inventory: dict[str, object]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "local-source-inventory.json").write_text(
        canonical_json(inventory), encoding="utf-8", newline=""
    )
    classes = {"redistributable": 0, "conditional": 0, "local_use": 0, "excluded": 0}
    for row in inventory["objects"]:
        value = str(row.get("redistribution_class") or "")
        if value.startswith(("redistributable", "owner_licensed")):
            classes["redistributable"] += 1
        elif value.startswith("excluded"):
            classes["excluded"] += 1
        elif value.startswith("local_only"):
            classes["local_use"] += 1
        else:
            classes["conditional"] += 1
    bill = {
        "schema_version": "value.bill-of-data/v1",
        "pack_id": "value-uk-open-data-pack",
        "local_pack_id": inventory["local_pack_id"],
        "version": "0.2.0-local-source-audit",
        "publication_status": inventory["publication_status"],
        "roles_expected": inventory["roles_expected"],
        "roles_locally_available": inventory["roles_locally_available"],
        "roles_source_identified": inventory["roles_source_identified"],
        "roles_with_licence_label": inventory["roles_with_licence_label"],
        "rights_class_counts": classes,
        "roles_redistributable": classes["redistributable"],
        "archive_created": (
            ROOT / "data-packs" / "value-uk-open-data-pack-v1" / "manifest.json"
        ).is_file(),
        "blocking_reason": (
            None if classes["conditional"] == classes["local_use"] == classes["excluded"] == 0
            else "Conditional, local-only or excluded objects must remain pointers."
        ),
        "objects": inventory["objects"],
    }
    (OUTPUT / "bill-of-data.json").write_text(
        canonical_json(bill), encoding="utf-8", newline=""
    )
    pointer = {
        "schema_version": "value.local-data-pack-pointer/v1",
        "pack_id": inventory["local_pack_id"],
        "pack_root": inventory["local_pack_root"],
        "manifest_sha256": inventory["local_manifest_sha256"],
        "roles": inventory["roles_locally_available"],
        "materialization": "existing_atomic_install_no_data_bytes_duplicated",
        "source_inventory": "local-source-inventory.json",
        "public_redistribution": (
            "go_per_object_with_attribution"
            if inventory["publication_status"].startswith("PUBLIC_REDISTRIBUTION_GO")
            else "not_authorized_as_one_combined_archive"
        ),
    }
    (OUTPUT / "local-pack-pointer.json").write_text(
        canonical_json(pointer), encoding="utf-8", newline=""
    )

    lines = [
        "# UK local data source register",
        "",
        "This register describes the installed 25-role VALUE data pack without copying or modifying it. "
        "A local file is usable by the model but is not automatically approved for public redistribution.",
        "",
        f"- Local pack: `{inventory['local_pack_id']}`",
        f"- Manifest SHA-256: `{inventory['local_manifest_sha256']}`",
        f"- Roles present: {inventory['roles_locally_available']}/{inventory['roles_expected']}",
        f"- Sources identified: {inventory['roles_source_identified']}/{inventory['roles_expected']}",
        f"- Objects included in a public archive: {inventory['roles_in_public_archive']}",
        "",
        "| Role | Local file | Source | Licence label | Public treatment |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in inventory["objects"]:
        licence = row.get("exact_licence") or "exact terms not pinned"
        lines.append(
            f"| `{row['canonical_role']}` | `{row['local_uri']}` | "
            f"{row['source_publisher']} — {row['source_title']} | {licence} | "
            f"{row['redistribution_class']} |"
        )
    lines.extend([
        "",
        "## Provenance rules",
        "",
        "- The existing installed pack remains the runtime source of truth; this audit writes only publication metadata.",
        "- DESNZ REPD derivatives retain OGL attribution, and the raw table is not placed in a public archive before excluded-rights and personal-data review.",
        "- NESO licensing is checked per dataset; the portal-level licence page alone is not treated as proof for every acquired object.",
        "- ERA5 adaptations retain DOI, product, variables, year and adaptation wording.",
        "- Ember wholesale-price inputs are CC-BY-4.0 with attribution. The policy workbook is an owner-authored CC-BY-4.0 research input; its approximate and projected cells remain scientifically qualified in policy-provenance.json.",
        "- Apache-2.0 for VALUE software does not relicense upstream data.",
        "",
        "See `local-source-inventory.json` for hashes, transformation notes, source URLs and attribution text.",
    ])
    (OUTPUT / "SOURCE_REGISTER.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")

    attributions: list[str] = []
    seen: set[str] = set()
    for row in inventory["objects"]:
        value = row.get("attribution")
        if value and value not in seen:
            attributions.append(f"- {value}")
            seen.add(str(value))
    text = "# Attribution register\n\n" + "\n".join(attributions) + "\n"
    (OUTPUT / "ATTRIBUTION.md").write_text(text, encoding="utf-8", newline="")

    local_install = """# Local UK data pack

The complete 25-role UK research pack is already installed atomically at the
path recorded in `local-pack-pointer.json`. The pointer, manifest hash and
per-object hashes make that installation reproducible without copying roughly
one gigabyte of data into a second folder.

Use this pack locally as `value-uk-1000twh-reproduction`. `SOURCE_REGISTER.md` explains
where every object came from and `bill-of-data.json` separates local use from
public redistribution. The separable public candidate is assembled at
`data-packs/value-uk-open-data-pack-v1`; its manifest keeps the licence,
attribution and transformation decision on every object. The default local
assembly uses hard links and must be treated as read-only. Use
`scripts/assemble_public_uk_pack.py --copy` for an independent portable copy.
"""
    (OUTPUT / "LOCAL_INSTALL.md").write_text(
        local_install, encoding="utf-8", newline=""
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-root", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--verify-files", action="store_true")
    args = parser.parse_args()
    inventory = build_inventory(args.pack_root, verify_files=args.verify_files)
    write_outputs(inventory)
    print(canonical_json({
        "local_pack_id": inventory["local_pack_id"],
        "roles": inventory["roles_locally_available"],
        "errors": len(inventory["errors"]),
        "file_integrity_verified": inventory["file_integrity_verified"],
        "output": "publication/value-uk-open-data-pack/local-source-inventory.json",
    }))
    raise SystemExit(1 if inventory["errors"] else 0)


if __name__ == "__main__":
    main()
