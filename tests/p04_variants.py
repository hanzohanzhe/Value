"""Derived VALUE 101 fixtures for the P0-4 energy-balance oracle (plan 4.4 S1).

Each variant is the frozen VALUE 101 baseline study (``tests/golden/projects/C3.json``,
course default modules, ``value_101_day``) run against a copy of
``data-packs/value-101-baseline-v1`` with a small, documented data change.
The copies are written to a caller-supplied scratch directory with the
manifest binding hashes recomputed; the repository pack is never modified.

Variants (what each one exercises in the HEAD default PSM kernel):

* ``baseline``           – unchanged pack.  VRE pre-balancing excess charges the
  battery outside the retained boundary (periods 20-24).
* ``overshoot``          – day-ahead forecast fixed at 120 MW (60 MWh/period),
  the release-r2 configuration: every period takes the curtailment branch and
  the demand-serving generation is missing from the final dispatch (P3-01,
  P7-10).  Period 0 has a full-node residual of -18.829 MWh.
* ``export``             – the France interconnector profile is negative
  (12 MW export capability) so surplus is sold abroad.
* ``export_electrolyser``– 2 MW France export capability plus a 6 MW electrolyser.
* ``nuclear_curtail``    – a 30 MW must-run ``Nuclear`` unit and a forecast
  1 MW (0.5 MWh) above real demand wherever that stays within the nuclear
  capacity, so the in-dispatch nuclear surplus is handled in the curtailment
  branch.
* ``nuclear_balancing``  – the review's pack_nucbal: a 29 MW ``Nuclear`` unit
  (14.5 MWh per period) and a forecast 6 MW (3.0 MWh) below real demand, so
  every period takes the balancing branch, where the balancing volume is added
  to the in-dispatch nuclear output again (DEV-BAL-04): nuclear is recorded as
  17.5 MWh instead of 14.5 and the full-node residual exceeds the unused excess
  by +3.000 MWh (plan 4.4, P7-10 test matrix).
* ``multi_battery``      – a second battery (``0.5c_battery``, pool limit 5).

Market rule set (P0-6): the fixtures were built to exercise the 0.6.0-alpha.2
default-PSM kernel, so by default a variant runs the doctoral market rule set
(``native-doctoral-thesis-v1``, boundary ``default_psm_surplus_node_v1``)
whatever the Study's profile; ``rule_set="profile"`` runs the rule set of the
Study's methodology profile (the corrected rule set for the C3 Study).

CLI (one variant per process; the legacy kernel keeps a process-global weather
cache, P7-02)::

    python -B tests/p04_variants.py build NAME DEST
    python -B tests/p04_variants.py run NAME OUTPUT_DIR [--mode value_101_day] [--rule-set doctoral|profile]
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
BASE_PACK = ROOT / "data-packs" / "value-101-baseline-v1"
BASE_PROJECT = ROOT / "tests" / "golden" / "projects" / "C3.json"
DEFAULT_MODE = "value_101_day"
RULE_SETS = ("doctoral", "profile")


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _binding_file(pack: Path, manifest: Mapping, role: str) -> Path:
    return pack / str(manifest["bindings"][role]["uri"])


def _map_series(pack: Path, manifest: Mapping, role: str, transform: Callable[[int, float], float]) -> None:
    """Rewrite a one-column numeric CSV, keeping its header (if any)."""

    path = _binding_file(pack, manifest, role)
    lines = _read_lines(path)
    out: list[str] = []
    index = 0
    for line in lines:
        text = line.strip()
        try:
            value = float(text)
        except ValueError:
            out.append(line)
            continue
        out.append(repr(float(transform(index, value))))
        index += 1
    _write_lines(path, out)


def _edit_fleet(pack: Path, manifest: Mapping, edit: Callable[[dict], None]) -> None:
    path = _binding_file(pack, manifest, "fleet.generators")
    fleet = json.loads(path.read_text(encoding="utf-8"))
    edit(fleet)
    path.write_text(json.dumps(fleet, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _nuclear(capacity_mw: float) -> dict:
    return {
        "name": "Nuclear",
        "gen_cost": 0.0,
        "curtail_cost": 0.0,
        "carbon_emission": 0.0,
        "capacity_limit": float(capacity_mw),
        "alter_limit": 0.0,
        "startup_cost": 0.0,
        "capital_cost": 0.0,
        "unit_time_cost": 0.0,
    }


def _add_nuclear(pack: Path, manifest: Mapping, capacity_mw: float) -> None:
    """Add a must-run ``Nuclear`` unit (kernel class NuclearGenerator).

    The canonical asset builder needs a CAPEX basis for every fleet
    technology, so a nominal one is added to ``costs.capital``; value_101_day
    runs no investment stage, so it does not affect the fixture.
    """

    def edit(fleet: dict) -> None:
        fleet["generators"]["Nuclear"] = _nuclear(capacity_mw)

    _edit_fleet(pack, manifest, edit)
    costs_path = _binding_file(pack, manifest, "costs.capital")
    costs = json.loads(costs_path.read_text(encoding="utf-8"))
    costs["capital_costs_per_mw"]["Nuclear"] = 5_000_000.0
    costs_path.write_text(json.dumps(costs, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _variant_baseline(pack: Path, manifest: Mapping) -> None:
    return None


def _variant_overshoot(pack: Path, manifest: Mapping) -> None:
    _map_series(pack, manifest, "demand.forecast", lambda _i, _v: 120.0)


def _variant_export(pack: Path, manifest: Mapping) -> None:
    _map_series(pack, manifest, "market.france.profile", lambda _i, _v: -12.0)


def _variant_export_electrolyser(pack: Path, manifest: Mapping) -> None:
    # A smaller export capability (2 MW) leaves surplus for the electrolyser.
    _map_series(pack, manifest, "market.france.profile", lambda _i, _v: -2.0)

    def edit(fleet: dict) -> None:
        fleet["electrolyzer"]["capacity_limit"] = 6.0
        fleet["electrolyzer"]["rampup_rate"] = 6.0

    _edit_fleet(pack, manifest, edit)


NUCLEAR_CURTAIL_MW = 30.0


def _real_demand(pack: Path, manifest: Mapping) -> list[float]:
    return [
        float(line)
        for line in _read_lines(_binding_file(pack, manifest, "demand.real"))
        if _is_number(line)
    ]


def _variant_nuclear_curtail(pack: Path, manifest: Mapping) -> None:
    _add_nuclear(pack, manifest, NUCLEAR_CURTAIL_MW)
    real = _real_demand(pack, manifest)
    _map_series(
        pack, manifest, "demand.forecast",
        lambda i, value: real[i] + 1.0 if real[i] + 1.0 <= NUCLEAR_CURTAIL_MW else value,
    )


NUCLEAR_BALANCING_MW = 29.0
NUCLEAR_BALANCING_GAP_MW = 6.0


def _variant_nuclear_balancing(pack: Path, manifest: Mapping) -> None:
    _add_nuclear(pack, manifest, NUCLEAR_BALANCING_MW)
    real = _real_demand(pack, manifest)
    _map_series(
        pack, manifest, "demand.forecast",
        lambda i, _v: max(real[i] - NUCLEAR_BALANCING_GAP_MW, 0.0),
    )


def _variant_multi_battery(pack: Path, manifest: Mapping) -> None:
    def edit(fleet: dict) -> None:
        # Battery ids must be storage-catalogue ids (canonical_psm_data).
        second = copy.deepcopy(fleet["batteries"]["1c_battery"])
        second.update({"name": "0.5c_battery", "battery_type": "0.5c", "pool_limit": 5.0, "per_pool_limit": 5.0})
        fleet["batteries"]["0.5c_battery"] = second

    _edit_fleet(pack, manifest, edit)


def _is_number(text: str) -> bool:
    try:
        float(text.strip())
    except ValueError:
        return False
    return True


VARIANTS: dict[str, Callable[[Path, Mapping], None]] = {
    "baseline": _variant_baseline,
    "overshoot": _variant_overshoot,
    "export": _variant_export,
    "export_electrolyser": _variant_export_electrolyser,
    "nuclear_curtail": _variant_nuclear_curtail,
    "nuclear_balancing": _variant_nuclear_balancing,
    "multi_battery": _variant_multi_battery,
}


def build_variant_pack(name: str, destination: Path) -> Path:
    """Copy the baseline pack to ``destination`` and apply variant ``name``.

    Binding ``sha256``/``bytes`` are recomputed for every file so the derived
    pack is internally consistent; the pack id is kept (the study refers to it
    by id) and the variant is named in ``manifest.name``.
    """

    if name not in VARIANTS:
        raise KeyError(f"unknown P0-4 variant {name!r}; known: {sorted(VARIANTS)}")
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    shutil.copytree(BASE_PACK, destination)
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    VARIANTS[name](destination, manifest)
    for binding in manifest["bindings"].values():
        payload = (destination / str(binding["uri"])).read_bytes()
        binding["sha256"] = hashlib.sha256(payload).hexdigest()
        binding["bytes"] = len(payload)
    manifest["name"] = f"{manifest['name']} (P0-4 fixture: {name})"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def variant_project() -> dict:
    project = json.loads(BASE_PROJECT.read_text(encoding="utf-8"))
    project["id"] = "golden-study"
    return project


@contextlib.contextmanager
def _market_rule_set(rule_set: str):
    """Pin the doctoral market rule set (default) or keep the profile's (P0-6)."""

    if rule_set not in RULE_SETS:
        raise ValueError(f"rule_set must be one of {RULE_SETS}, not {rule_set!r}")
    if rule_set == "profile":
        yield
        return
    from unittest import mock

    from gridform_core.builtin.scheme_c_1000twh import scheme_c_native_psm
    from gridform_core.builtin.scheme_c_1000twh.native_market_rules import DOCTORAL

    with mock.patch.object(scheme_c_native_psm, "rules_for_methodology", lambda _methodology: DOCTORAL):
        yield


def run_variant_in_process(name: str, output_dir: Path, *, mode: str = DEFAULT_MODE,
                           rule_set: str = "doctoral") -> Path:
    """Build the variant pack in a temporary directory and run it here.

    Callers should use :func:`run_variant` (separate process) unless they own
    the process.
    """

    from gridform_core.application import run_project_application

    output_dir = Path(output_dir).resolve()
    with tempfile.TemporaryDirectory(prefix=f"value-p04-{name}-") as scratch, _market_rule_set(rule_set):
        pack = build_variant_pack(name, Path(scratch) / "pack")
        log = Path(scratch) / "run.log"
        try:
            with log.open("w", encoding="utf-8") as handle, contextlib.redirect_stdout(handle), contextlib.redirect_stderr(handle):
                run_project_application(
                    variant_project(),
                    run_id=f"p04-{name}",
                    pack_root=pack,
                    output_dir=output_dir,
                    mode=mode,
                )
        except BaseException:
            sys.stderr.write(log.read_text(encoding="utf-8", errors="replace")[-6000:])
            raise
    return output_dir


def run_variant(name: str, output_dir: Path, *, mode: str = DEFAULT_MODE, python: str | None = None,
                timeout: float = 900.0, rule_set: str = "doctoral") -> Path:
    """Run variant ``name`` in a fresh interpreter (P7-02) and return the output dir."""

    command = [python or sys.executable, "-B", str(Path(__file__).resolve()), "run", name, str(output_dir),
               "--mode", mode, "--rule-set", rule_set]
    completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(
            f"P0-4 variant {name} failed (exit {completed.returncode}):\n{completed.stderr[-4000:]}"
        )
    return Path(output_dir)


P04_LEDGER_TABLES = (
    "storage_energy_audit", "storage_year_boundary", "surplus_routing",
    "balance_boundary_period", "stress_event",
)


def downgrade_to_pre_p04_ledger(database: Path) -> None:
    """Rewrite a fresh default-PSM ledger into the pre-P0-4 S4 form.

    For tests that need a legacy (release-r2 type) ledger from a current run:
    drop the P0-4 S4-S6 tables and boundary metadata, and restore the HEAD
    self-report (raw on retained_demand_serving_v1, adjustment -raw whenever
    |raw| > 1e-9, adjusted residual 0).  Dispatch columns are untouched.
    """

    import sqlite3

    from gridform_core import energy_balance_contract as contract

    connection = sqlite3.connect(database)
    try:
        for table in P04_LEDGER_TABLES:
            connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.execute(
            "DELETE FROM metadata WHERE key IN (?, ?)",
            (contract.METADATA_BOUNDARY_KEY, contract.METADATA_RULE_SET_KEY),
        )
        rows = connection.execute(
            "SELECT year, period, stage, accepted_supply_mwh, blackout_mwh, real_demand_mwh, "
            "storage_charge_mwh, forecast_demand_mwh FROM period_summary"
        ).fetchall()
        for year, period, stage, supply, blackout, demand, charge, forecast in rows:
            flows = contract.PeriodFlows(
                year, period, supply, blackout, demand, charge, 0.0, 0.0, forecast_demand_mwh=forecast,
            )
            raw = contract.retained_residual(flows)
            adjustment = -raw if abs(raw) > 1e-9 else 0.0
            connection.execute(
                "UPDATE period_summary SET raw_energy_balance_residual_mwh=?, compatibility_adjustment_mwh=?, "
                "energy_balance_residual_mwh=? WHERE year=? AND period=? AND stage=?",
                (raw, adjustment, raw + adjustment, year, period, stage),
            )
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("name", choices=sorted(VARIANTS))
    build.add_argument("destination", type=Path)
    run = sub.add_parser("run")
    run.add_argument("name", choices=sorted(VARIANTS))
    run.add_argument("output", type=Path)
    run.add_argument("--mode", default=DEFAULT_MODE)
    run.add_argument("--rule-set", default="doctoral", choices=RULE_SETS)
    arguments = parser.parse_args(argv)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if arguments.command == "build":
        print(build_variant_pack(arguments.name, arguments.destination))
    else:
        print(run_variant_in_process(arguments.name, arguments.output, mode=arguments.mode,
                                     rule_set=arguments.rule_set))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
