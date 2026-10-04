"""Fail closed if a public UK pack includes unresolved or corrupted objects."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACK = ROOT / "data-packs" / "value-uk-open-data-pack-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(pack: Path) -> dict[str, object]:
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    for role, binding in manifest.get("bindings", {}).items():
        redistribution = str(binding.get("redistribution_class") or "")
        if not redistribution.startswith(("redistributable_", "owner_licensed_")):
            errors.append(f"{role}: unresolved redistribution class {redistribution}")
        if not binding.get("licence") or not binding.get("attribution"):
            errors.append(f"{role}: missing licence or attribution")
        path = (pack / str(binding["uri"])).resolve()
        try:
            path.relative_to(pack.resolve())
        except ValueError:
            errors.append(f"{role}: path escapes pack")
            continue
        if not path.is_file() or sha256(path) != binding.get("sha256"):
            errors.append(f"{role}: missing or hash mismatch")
    return {
        "schema_version": "value.public-pack-scan/v1",
        "pack_id": manifest.get("id"), "roles": len(manifest.get("bindings", {})),
        "forbidden_or_corrupt_objects": len(errors), "errors": errors,
        "decision": "GO" if not errors else "NO-GO",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "publication" / "value-uk-open-data-pack" / "public-artifact-scan.json",
    )
    arguments = parser.parse_args()
    result = verify(arguments.pack.resolve())
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["decision"] == "GO" else 1)


if __name__ == "__main__":
    main()
