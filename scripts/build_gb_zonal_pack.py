"""Build an unsigned Prompt 98 GB zonal candidate from a complete local inventory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.gb_zonal_pack_builder import build_candidate, canonical_json  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(canonical_json(build_candidate(args.inventory, args.output)), end="")


if __name__ == "__main__":
    main()
