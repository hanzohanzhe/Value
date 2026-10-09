"""Count zonal v4 lock violations and repairs over a run of gb_chain periods.

``python -B scripts/p08_zonal_lock_repair_scan.py [--periods 336] [--scarce-every 3]``

Clears periods 0..N-1 of the synthetic 23-zone ``gb_chain`` fixture
(tests/network_toys.py; every k-th period scarce) with the production
zonal redispatch module and reports, as JSON:

* ``violations``: locks found violated after a phase (each one triggers a
  repair attempt through ``_tighten_violated_objective_cap``);
* ``repairs`` / ``repair_failures``: repair attempts that returned / raised;
* ``hard_failures``: periods whose clearing raised (with the error class);
* ``worst_primary_degradation_over_tolerance``: max over periods of the
  final primary bid-cost degradation divided by its computed tolerance.

This is the reproducible form of the 336-period (168 h) count in the
M2-P0-8a report (plan 4.8 risk: record repair counts on a GB-scale
fixture).  It is a synthetic fixture, not a real GB year: the real
full-year count remains an open item for M5/M6.  Read-only; writes nothing.
"""

from __future__ import annotations

# P0 rule (P0_CONVENTIONS section 2): never write bytecode, even when started
# without -B; the managed install's runtime is read-only and must stay
# byte-identical.
import os as _os
import sys as _sys

_sys.dont_write_bytecode = True
_os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import argparse
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))


def scan(periods: int = 336, scarce_every: int = 3) -> dict[str, Any]:
    import gridform_core.zonal_redispatch as zonal_redispatch
    from gridform_validation.zonal_case_generator import bind_production_input
    from tests.network_toys import gb_chain_declaration

    if periods < 1 or scarce_every < 1:
        raise ValueError("periods and scarce_every must be positive")
    stats: dict[str, Any] = {
        "fixture": "tests/network_toys.py::gb_chain_declaration (23 zones, synthetic)",
        "periods_requested": periods,
        "scarce_every": scarce_every,
        "periods_cleared": 0,
        "scarce_periods": 0,
        "violations": 0,
        "repairs": 0,
        "repair_failures": 0,
        "hard_failures": 0,
        "hard_failure_periods": [],
        "worst_primary_degradation_over_tolerance": 0.0,
    }
    real_tighten = zonal_redispatch._tighten_violated_objective_cap

    def counted_tighten(*args: Any, **kwargs: Any) -> Any:
        stats["violations"] += 1
        try:
            result = real_tighten(*args, **kwargs)
        except Exception:
            stats["repair_failures"] += 1
            raise
        stats["repairs"] += 1
        return result

    started = time.perf_counter()
    with patch.object(zonal_redispatch, "_tighten_violated_objective_cap", counted_tighten):
        for period in range(periods):
            scarce = period % scarce_every == 0
            model_input, module = bind_production_input(gb_chain_declaration(period, scarce=scarce))
            try:
                result = module.clear(model_input)
            except Exception as exc:  # noqa: BLE001 - counted and reported, not hidden
                stats["hard_failures"] += 1
                stats["hard_failure_periods"].append(
                    {"period": period, "error": type(exc).__name__, "message": str(exc)[:200]}
                )
                continue
            stats["periods_cleared"] += 1
            stats["scarce_periods"] += int(scarce)
            for row in result.extensions["network_solver_diagnostics"]:
                if row["phase_id"] == "primary_bid_cost" and float(row["computed_tolerance"]) > 0:
                    stats["worst_primary_degradation_over_tolerance"] = max(
                        stats["worst_primary_degradation_over_tolerance"],
                        float(row["degradation"]) / float(row["computed_tolerance"]),
                    )
    stats["seconds"] = round(time.perf_counter() - started, 1)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--periods", type=int, default=336)
    parser.add_argument("--scarce-every", type=int, default=3)
    arguments = parser.parse_args(argv)
    stats = scan(arguments.periods, arguments.scarce_every)
    print(json.dumps(stats, indent=1))
    return 1 if stats["hard_failures"] or stats["repair_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
