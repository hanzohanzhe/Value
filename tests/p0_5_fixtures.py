"""Shared fixtures for the P0-5 data-reading work (plan 4.5).

S0 adds them; later P0-5 steps reuse them to show what changed:

* :func:`capture_module` - ``scripts/capture_p0_5_baseline.py`` (reader
  captures, the kernel-input oracle and the stored baseline);
* :func:`research_pack_roots` - GBP1/R029 pack directories supplied through
  ``VALUE_P0_5_PACKS`` (they are not in the repository);
* :func:`nonconstant_boundary_pack` - a copy of the VALUE 101 baseline pack
  whose ten interconnector series are non-constant and distinct per country,
  so a clock stretch or a mis-wired connection becomes visible (the shipped
  101 market series are constant and cannot show either);
* :class:`KernelBoundaryRecorder` - records what the retained kernel hands
  to ``ahead_market_bidding`` in every period (connection limits and prices,
  forecast demand, VRE capacity limits) while the real kernel runs;
* :func:`run_value_101_day` - runs the frozen golden D3 project
  (``value_101_day``, 48 periods, the retained kernel) on a given pack.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_SCRIPT = ROOT / "scripts" / "capture_p0_5_baseline.py"
RUN_CASE_SCRIPT = ROOT / "scripts" / "golden" / "run_case.py"
VALUE_101_BASELINE = ROOT / "data-packs" / "value-101-baseline-v1"
KERNEL_MODULE = "gridform_core.builtin.scheme_c_1000twh.runtime_compat.modular_simulation_model"
# Baseline labels of the released public1 research packs (see
# capture_p0_5_baseline.RESEARCH_PACKS: the release keeps the original pack
# ids, the manifest sha256 identifies the public1 revision).
GBP1_PUBLIC1 = "gbp1-public1"
R029_PUBLIC1 = "r029-public1"
TOY_COUNTRY_INDEX = {"france": 1, "belgium": 2, "netherlands": 3, "norway": 4, "ireland": 5}
TOY_ROWS = 17_520


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_CAPTURE = None


def capture_module():
    global _CAPTURE
    if _CAPTURE is None:
        _CAPTURE = _load("capture_p0_5_baseline", CAPTURE_SCRIPT)
    return _CAPTURE


def research_pack_roots() -> dict[str, Path]:
    """Label -> directory for the released research packs listed in VALUE_P0_5_PACKS.

    A directory is taken only when its manifest sha256 is the released
    public1 manifest; other revisions of the same pack id are ignored.
    """

    capture = capture_module()
    wanted = {entry["manifest_sha256"]: label for label, entry in capture.RESEARCH_PACKS.items()}
    found: dict[str, Path] = {}
    for item in os.environ.get(capture.PACKS_ENVIRONMENT, "").split(os.pathsep):
        if not item.strip():
            continue
        root = Path(item)
        manifest = root / "manifest.json"
        if manifest.is_file():
            label = wanted.get(capture.file_sha256(manifest))
            if label:
                found[label] = root
    return found


# ------------------------------------------------------------- toy pack

def toy_profile(country: str, row: int) -> float:
    """Signed flow in MW: country offset plus a ramp that differs in every row of a day."""

    return round(0.5 * TOY_COUNTRY_INDEX[country] + 0.001 * (row % 1000), 6)


def toy_price(country: str, row: int) -> float:
    return round(40.0 + 10.0 * TOY_COUNTRY_INDEX[country] + 0.01 * (row % 1000), 6)


def nonconstant_boundary_pack(destination: Path) -> Path:
    """Copy the 101 baseline pack and replace its ten market series.

    Layout is kept (profile: header ``mwh`` + 17520 rows; price: 17520 rows,
    no header), only the values change, and the manifest hashes/bytes are
    updated so the pack stays internally consistent.
    """

    pack = destination / "value-101-baseline-v1"
    shutil.copytree(VALUE_101_BASELINE, pack)
    manifest_path = pack / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for country in TOY_COUNTRY_INDEX:
        for kind in ("profile", "price"):
            role = f"market.{country}.{kind}"
            binding = manifest["bindings"][role]
            target = pack / binding["uri"]
            if kind == "profile":
                lines = ["mwh", *(repr(toy_profile(country, row)) for row in range(TOY_ROWS))]
            else:
                lines = [repr(toy_price(country, row)) for row in range(TOY_ROWS)]
            data = ("\n".join(lines) + "\n").encode("utf-8")
            target.write_bytes(data)
            binding["sha256"] = hashlib.sha256(data).hexdigest()
            binding["bytes"] = len(data)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return pack


# ------------------------------------------------------- kernel recorder

class KernelBoundaryRecorder:
    """Record the kernel's per-period inputs at each ``ahead_market_bidding`` call.

    ``run_simulation`` is wrapped to keep its ``connections``, forecast and
    real demand arguments; ``ahead_market_bidding`` is wrapped to read, before
    delegating to the real function, every connection's ``transfer_constraint``
    and ``external_price`` and every VRE generator's ``capacity_limit`` (with
    its ``capacity_multiplier``) as the input block has just assigned them.
    Dispatch is the real kernel's; nothing is changed.
    """

    def __init__(self) -> None:
        self.forecast_arguments: list[Any] = []
        self.real_demands: list[float] = []
        self.forecast_demands: list[float] = []
        self.connections: dict[str, dict[str, list[Any]]] = {}
        self.vre_capacity_limit: dict[str, list[float]] = {}
        self.vre_limits: dict[str, list[tuple[float, float]]] = {}
        self.periods: list[int] = []

    @contextlib.contextmanager
    def patched(self) -> Iterator["KernelBoundaryRecorder"]:
        import importlib

        kernel = importlib.import_module(KERNEL_MODULE)
        real_run, real_ahead = kernel.run_simulation, kernel.ahead_market_bidding
        state: dict[str, Any] = {}

        def run_simulation(periods, generators, batterys, forecast_demands, real_demands, connections, electrolyzer):
            state["connections"] = list(connections)
            self.forecast_demands = [float(value) for value in list(forecast_demands)[:periods]]
            self.real_demands = [float(value) for value in list(real_demands)[:periods]]
            return real_run(periods, generators, batterys, forecast_demands, real_demands, connections, electrolyzer)

        def ahead_market_bidding(generators, batterys, forecast_demand, period, *arguments, **keywords):
            self.periods.append(int(period))
            self.forecast_arguments.append(forecast_demand)
            for connection in state.get("connections", ()):
                entry = self.connections.setdefault(connection.name, {"transfer_constraint": [], "external_price": []})
                entry["transfer_constraint"].append(connection.transfer_constraint)
                entry["external_price"].append(connection.external_price)
            for generator in generators:
                if type(generator) is kernel.ExpensiverenewableGenerator:
                    self.vre_capacity_limit.setdefault(generator.name, []).append(float(generator.capacity_limit))
                    self.vre_limits.setdefault(generator.name, []).append(
                        (float(generator.capacity_limit), float(generator.capacity_multiplier)))
            return real_ahead(generators, batterys, forecast_demand, period, *arguments, **keywords)

        previous_cache = kernel._WEATHER_LIMIT_CACHE
        kernel.run_simulation, kernel.ahead_market_bidding = run_simulation, ahead_market_bidding
        # The weather cache is process-global and unkeyed (P7-02); start clean.
        kernel._WEATHER_LIMIT_CACHE = None
        try:
            yield self
        finally:
            kernel.run_simulation, kernel.ahead_market_bidding = real_run, real_ahead
            kernel._WEATHER_LIMIT_CACHE = previous_cache


def run_value_101_day(pack_root: Path, recorder: KernelBoundaryRecorder) -> None:
    """Run the frozen golden D3 project (value_101_day, retained kernel) on ``pack_root``."""

    from unittest.mock import patch

    from gridform_core import methodology
    from gridform_core.application import run_project_application

    run_case = _load("p0_5_run_case", RUN_CASE_SCRIPT)
    cases = run_case.load_cases()
    project = run_case.build_project(dict(cases["D3"], id="D3"))
    output = Path(tempfile.mkdtemp(prefix="value-p0-5-kernel-"))
    # D3 runs under the frozen doctoral profile, whose whitelist pins the
    # VALUE 101 manifest sha; an edited copy (nonconstant_boundary_pack) is
    # therefore refused at the run entry.  This instrumented test is about the
    # kernel boundary, not the whitelist, so only this pack directory is
    # admitted (the whitelist itself is tested in test_methodology_profiles).
    real_pack_supported = methodology._pack_supported
    edited_manifest = methodology.read_pack_manifest(pack_root)[0]

    def pack_supported(profile, manifest, shas):
        return manifest == edited_manifest or real_pack_supported(profile, manifest, shas)

    try:
        with open(os.devnull, "w", encoding="utf-8") as sink, contextlib.redirect_stdout(sink), \
                contextlib.redirect_stderr(sink), recorder.patched(), \
                patch.object(methodology, "_pack_supported", pack_supported):
            run_project_application(
                project,
                run_id="p0-5-kernel-boundary",
                pack_root=pack_root.resolve(),
                output_dir=output / "output",
                mode="value_101_day",
            )
    finally:
        shutil.rmtree(output, ignore_errors=True)
