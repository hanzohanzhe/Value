"""Validate an unsigned Prompt 98 candidate without signing or installing it."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.gb_zonal_pack_builder import canonical_json, sha256_file  # noqa: E402
from gridform_core.weather_spatialization import ZonalAvailabilityBundle  # noqa: E402
from gridform_core.zonal_contracts import ZonalNetworkPack  # noqa: E402


def validate(candidate_root: Path) -> dict[str, object]:
    candidate_root = candidate_root.resolve()
    if (candidate_root / "manifest.json").exists():
        raise ValueError("Unsigned candidate must not contain an installable manifest.json")
    path = candidate_root / "candidate-manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "awaiting_owner_signoff":
        raise ValueError("Prompt 98 candidate is not at the owner-signoff gate")
    if payload.get("final_network_pack_id") is not None or payload.get("installed") is not False:
        raise ValueError("Unsigned candidate has been assigned or installed prematurely")
    if payload.get("owner_signoff", {}).get("status") != "pending":
        raise ValueError("Candidate owner signoff must remain pending")
    if re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", path.read_text(encoding="utf-8")):
        raise ValueError("Candidate manifest contains an absolute local path")

    pack = ZonalNetworkPack.from_dict(payload["zonal_network_pack"])
    pack.validate()
    checked = 0
    for relative, expected in payload.get("scientific_file_sha256", {}).items():
        artifact = (candidate_root / relative).resolve()
        try:
            artifact.relative_to(candidate_root)
        except ValueError as exc:
            raise ValueError("Candidate artifact escapes its root") from exc
        if not artifact.is_file() or sha256_file(artifact) != expected:
            raise ValueError(f"Candidate artifact identity failed: {relative}")
        checked += 1
    for role, binding in payload.get("bindings", {}).items():
        relative = str(binding.get("uri") or "")
        artifact = (candidate_root / relative).resolve()
        try:
            artifact.relative_to(candidate_root)
        except ValueError as exc:
            raise ValueError("Candidate binding escapes its root") from exc
        actual = sha256_file(artifact) if artifact.is_file() else None
        declared = str(binding.get("sha256") or "")
        pack_identity = str(pack.spatial_audit.source_sha256_by_role.get(role) or "")
        if actual != declared or declared != pack_identity:
            raise ValueError(f"Candidate binding identity failed: {role}")
    for relative in payload.get("weather_artifacts", []):
        bundle = ZonalAvailabilityBundle.from_dict(
            json.loads((candidate_root / relative).read_text(encoding="utf-8"))
        )
        bundle.validate()
    review = candidate_root / "review" / "reconciliation-and-rights.json"
    map_path = candidate_root / "review" / "zone-map.svg"
    if not review.is_file() or not map_path.is_file():
        raise ValueError("Candidate is missing its mandatory human review package")
    return {
        "schema_version": "value.gb-zonal-candidate-validation/v1",
        "status": "passed_unsigned_candidate_validation",
        "candidate_scientific_sha256": pack.scientific_sha256,
        "scientific_artifacts_checked": checked,
        "owner_signoff": "pending",
        "installed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_root", type=Path)
    args = parser.parse_args()
    print(canonical_json(validate(args.candidate_root)), end="")


if __name__ == "__main__":
    main()
