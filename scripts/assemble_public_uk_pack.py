"""Assemble the 25-role UK pack from an authorised local source without mutation.

The default materialisation uses hard links so the local release candidate does
not consume another ~0.85 GB. Use --copy for a portable independent directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.catalog import DATASET_SLOTS  # noqa: E402
from gridform_core.data_pack_validation import validate_data_pack  # noqa: E402

from audit_local_uk_data_pack import build_inventory  # noqa: E402


DEFAULT_SOURCE = ROOT / ".gridform" / "data-packs" / "value-uk-1000twh-reproduction"
DEFAULT_DESTINATION = ROOT / "data-packs" / "value-uk-open-data-pack-v1"
PLAN = ROOT / "publication" / "uk-source-plan.json"
ALLOWED_PREFIXES = ("redistributable_", "owner_licensed_")


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assemble(source: Path, destination: Path, *, copy_files: bool) -> dict[str, object]:
    source = source.resolve()
    destination = destination.resolve()
    inventory = build_inventory(source, verify_files=True)
    blockers = [
        row for row in inventory["objects"]
        if not str(row["redistribution_class"]).startswith(ALLOWED_PREFIXES)
        or not row.get("exact_licence")
    ]
    if inventory["errors"] or blockers:
        raise RuntimeError(
            "Public assembly refused: unresolved local integrity or rights decisions: "
            + ", ".join(str(row["canonical_role"]) for row in blockers)
        )
    if destination.exists():
        existing = destination / "manifest.json"
        if existing.is_file():
            payload = json.loads(existing.read_text(encoding="utf-8"))
            if payload.get("source_manifest_sha256") == inventory["local_manifest_sha256"]:
                return {"destination": str(destination), "status": "already_assembled"}
        raise FileExistsError(f"Refusing to replace existing destination {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=destination.name + "-", dir=destination.parent))
    try:
        source_manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8-sig"))
        bindings: dict[str, object] = {}
        for row in inventory["objects"]:
            role = str(row["canonical_role"])
            uri = str(row["local_uri"])
            source_file = (source / uri).resolve()
            target_file = (staging / uri).resolve()
            target_file.parent.mkdir(parents=True, exist_ok=True)
            if copy_files:
                shutil.copy2(source_file, target_file)
            else:
                os.link(source_file, target_file)
            if sha256(target_file) != row["sha256"]:
                raise RuntimeError(f"Post-materialisation hash mismatch for {role}")
            original = dict(source_manifest["bindings"][role])
            original.update({
                "source_id": row["source_id"],
                "source_url": row["source_url"],
                "source_version": row["source_version"],
                "licence": row["exact_licence"],
                "attribution": row["attribution"],
                "redistribution_class": row["redistribution_class"],
                "transformation": row["transformation"],
            })
            bindings[role] = original

        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        manifest = {
            "schema_version": "value.data-pack/v1",
            "id": destination.name,
            "name": "VALUE UK open research data pack v1",
            "country": "GB",
            "timezone": source_manifest["timezone"],
            "period_hours": source_manifest["period_hours"],
            "publication_status": "redistributable_per_object",
            "pack_licence": "mixed open licences; see each binding and RIGHTS.json",
            "source_manifest_sha256": inventory["local_manifest_sha256"],
            "source_plan_version": plan["version"],
            "materialisation": "independent_copy" if copy_files else "local_hardlink_release_candidate",
            "bindings": bindings,
        }
        (staging / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        rights = {
            "schema_version": "value.public-data-rights/v1",
            "decision": "GO_PER_OBJECT_WITH_ATTRIBUTION",
            "not_legal_advice": True,
            "objects": [
                {
                    "role": row["canonical_role"], "decision": "GO",
                    "licence": row["exact_licence"], "source_url": row["source_url"],
                    "attribution": row["attribution"],
                    "redistribution_class": row["redistribution_class"],
                }
                for row in inventory["objects"]
            ],
            "policy_science_caveat": "policy.support contains approximate historical cells and scenario projections; see publication/value-uk-open-data-pack/policy-provenance.json",
        }
        (staging / "RIGHTS.json").write_text(canonical_json(rights), encoding="utf-8")
        report = validate_data_pack(staging, manifest, DATASET_SLOTS)
        if not report["valid"]:
            raise RuntimeError("Assembled public pack failed semantic validation: " + repr(report["errors"]))
        (staging / "semantic-preflight.json").write_text(
            canonical_json(report), encoding="utf-8"
        )
        staging.replace(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "destination": str(destination), "status": "assembled",
        "roles": len(bindings), "materialisation": manifest["materialisation"],
        "semantic_valid": report["valid"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pack", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--copy", action="store_true", dest="copy_files")
    arguments = parser.parse_args()
    print(canonical_json(assemble(
        arguments.source_pack, arguments.destination, copy_files=arguments.copy_files
    )))


if __name__ == "__main__":
    main()
