"""Run the canonical semantic gate for the installed local UK research pack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.catalog import DATASET_SLOTS  # noqa: E402
from gridform_core.data_pack_validation import validate_data_pack  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pack-root",
        type=Path,
        default=ROOT / ".gridform" / "data-packs" / "value-uk-1000twh-reproduction",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "publication" / "value-uk-open-data-pack" / "semantic-preflight.json",
    )
    parser.add_argument("--verify-hashes-below-bytes", type=int, default=2**63 - 1)
    args = parser.parse_args()

    pack_root = args.pack_root.resolve()
    manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8-sig"))
    report = validate_data_pack(
        pack_root,
        manifest,
        DATASET_SLOTS,
        verify_hashes_below_bytes=args.verify_hashes_below_bytes,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="",
    )
    print(json.dumps({
        "valid": report["valid"],
        "summary": report["summary"],
        "warnings": len(report["warnings"]),
        "output": str(args.output),
    }, indent=2))
    raise SystemExit(0 if report["valid"] else 1)


if __name__ == "__main__":
    main()
