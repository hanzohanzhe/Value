"""Profile a completed VALUE run without changing or replaying it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.performance_profile import write_performance_profile  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path, help="Run root or model-output directory")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = write_performance_profile(args.run, args.report)
    print(json.dumps({
        "schema_version": report["schema_version"],
        "run": report["run"],
        "measurements": report["measurements"],
        "causal_classification": report["causal_analysis"]["classification"],
        "report": str(args.report.resolve()),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
