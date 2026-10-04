"""Install one verified value.data-bundle/v1 ZIP into a local VALUE data root."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.catalog import DATASET_SLOTS  # noqa: E402
from gridform_core.data_bundle import install_data_bundle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify and atomically install a VALUE data bundle")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--packs-root", type=Path, required=True)
    parser.add_argument(
        "--acknowledge-rights",
        action="store_true",
        help="Confirm that the bundle licence and attribution records were reviewed",
    )
    arguments = parser.parse_args()
    result = install_data_bundle(
        arguments.bundle,
        packs_root=arguments.packs_root,
        dataset_slots=DATASET_SLOTS,
        rights_acknowledged=arguments.acknowledge_rights,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
