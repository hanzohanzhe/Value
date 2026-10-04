"""Sign an owner-approved Prompt 98 candidate and install it locally."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.gb_zonal_pack_builder import (  # noqa: E402
    canonical_json,
    sign_and_install_candidate,
)
from gridform_core.v2.module_manifest import workspace_registry  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_root", type=Path)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approved-at", required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    args = parser.parse_args()
    slots = workspace_registry(
        args.state_root / "missing-local-modules"
    ).extension_registry.conditional_dataset_slots(
        ("value-zonal-redispatch-extension",)
    )
    result = sign_and_install_candidate(
        args.candidate_root,
        state_root=args.state_root,
        dataset_slots=slots,
        approved_by=args.approved_by,
        approved_at=args.approved_at,
        expected_candidate_scientific_sha256=args.expected_candidate_sha256,
    )
    print(canonical_json(result), end="")


if __name__ == "__main__":
    main()
