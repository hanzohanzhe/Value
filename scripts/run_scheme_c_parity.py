"""Run the packaged authoritative VALUE kernel and compare retained fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.builtin.scheme_c_1000twh.exact_run import (  # noqa: E402
    ExactRunRequest,
    run_exact_scheme_c,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, default=ROOT / ".gridform" / "data-packs" / "value-uk-1000twh-reproduction")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-year", type=int, default=2025)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--periods", type=int, default=17_520)
    args = parser.parse_args()
    result = run_exact_scheme_c(ExactRunRequest(
        pack_root=args.pack.resolve(),
        output_dir=args.output.resolve(),
        start_year=args.start_year,
        end_year=args.end_year,
        periods=args.periods,
    ))
    print(json.dumps({
        "output": str(args.output.resolve()),
        "years": [int(row["Year"]) for row in result["system_cost_history"]],
        "status": "completed",
    }, indent=2))


if __name__ == "__main__":
    main()
