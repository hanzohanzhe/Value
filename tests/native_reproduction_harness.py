"""96-period synthetic reproduction harness for the default PSM kernel (P0-6 S1).

The default PSM (``value-bid-at-cost-psm``) runs the copied Scheme C period
loop ``run_simulation`` in
``gridform_core/builtin/scheme_c_1000twh/runtime_compat/modular_simulation_model.py``.
That loop reads netCDF weather and interconnector CSV files by hard-coded asset
names, so it cannot be driven with small, exact synthetic inputs.  This harness
therefore runs a *frozen verbatim copy* of the 35aadb3 loop
(``tests/fixtures/native_psm/head_run_simulation_35aadb3.py``) in which only the
weather/interconnector loading and the per-period weather assignment are
replaced by exact synthetic inputs.  Every other line -- accumulator
initialisation (``total_storage_fee_balance`` at 2274), the forecast-based
branch at 2734, the storage-fee carry at 2768/2815, the ledger boundary at
2857-2956 and the return tuple -- is the HEAD text.

Source identity is built in:

* ``HEAD_KERNEL_SHA256`` pins the whole 35aadb3 kernel file;
* ``HEAD_SEGMENTS`` pins the SHA-256 of every copied line range;
* :func:`render_head_copy` regenerates the copy file from the pinned source and
  :func:`verify_head_copy` checks the committed copy is exactly that rendering
  (segment hashes, whole-file re-rendering from the verified segments and the
  pinned ``HEAD_COPY_SHA256``); :func:`compile_head_loop` calls it.

The market functions that the frozen loop calls (``ahead_market_bidding``,
``curtailment_market_bidding``, ``balancing_market_bidding`` ...) are resolved
from the *current* kernel module, so later rule-set work (P0-6 S2+) is checked
against the golden ``tests/fixtures/native_psm/doctoral_reproduction_golden_v1.json``
through the same loop.

Because the frozen copy also freezes the HEAD ledger boundary (2857-3002), its
accounting columns are HEAD-boundary values.  :func:`render_live_loop` applies
the same two input replacements to the *current* kernel text (located by
anchors), so ``loop="live"`` runs the current boundary and market functions;
at 35aadb3 it is byte-identical to the frozen copy.  Accounting revisions are
captured through the live loop, and :func:`gated_zones` says which zones a
loop is checked in.  Another replacement loop (for example a P0-6 S3
``realise_period`` driver, once the anchors no longer apply) can be passed to
:func:`run_case` as a callable ``loop=``; it must have ``run_simulation``'s
signature, must call
``driver.begin_period(period, generators, batterys, connections, electrolyzer)``
where HEAD assigned weather and interconnector inputs, and must not read
weather files.  It reaches the driver through the module global
``__p06_synthetic_driver__``, as the frozen copy does; :func:`run_case` sets
that global in the callable's ``__globals__`` only for the run and restores
the previous state afterwards.  Ledger writers the loop calls must exist on
:class:`RecordingLedger` (unknown ``record_*``/``declare_*`` writers raise
``NotImplementedError``).

Golden values are compared exactly (bit-identical doubles).  Every column has a
zone (trajectory / accounting / identity, decision Q12): the doctoral
trajectory zone is frozen; accounting columns may only change through an
appended revision carrying a universal correction id
(``scripts/capture_native_reproduction_golden.py revise``).
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import fnmatch
import functools
import hashlib
import json
import math
import os
import random
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from gridform_validation.golden import ZONE_STRENGTH, ZoneRules

ROOT = Path(__file__).resolve().parents[1]
KERNEL_RELPATH = "gridform_core/builtin/scheme_c_1000twh/runtime_compat/modular_simulation_model.py"
KERNEL_MODULE = "gridform_core.builtin.scheme_c_1000twh.runtime_compat.modular_simulation_model"
HEAD_COMMIT = "35aadb3"
HEAD_KERNEL_SHA256 = "dc4f8164ed2c74187fa9bf954bb12d9dced57fb35ee98f8891233d52683b9e5a"
# name, first line, last line (1-based, inclusive), SHA-256 of the UTF-8 text.
HEAD_SEGMENTS = (
    ("A", 2252, 2364, "c86aae704644a4bdec66372f67b3fde6e218aab026abfab6d8f9ffca21109b65"),
    ("C", 2592, 2599, "47c4e6888b40cb808abfa1a6f1bf00f7ea30891116795f5b332e237e109d9e0b"),
    ("E", 2691, 3125, "d1f37e6869e6640dcc6602825899a4b162292d5afeb948e80a5ad35baf48d020"),
)
REPLACED_RANGES = {
    "B": (2365, 2591, "weather netCDF and interconnector CSV loading"),
    "D": (2600, 2690, "per-period VRE availability and interconnector assignment"),
}
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "native_psm"
HEAD_COPY_PATH = FIXTURE_DIR / "head_run_simulation_35aadb3.py"
# SHA-256 of the whole committed copy (header, markers, replacements, segments).
HEAD_COPY_SHA256 = "07ad59660191a3c840bd3f48783589e9f959cea1271f4f1141d2b0583e00e3a8"
GOLDEN_PATH = FIXTURE_DIR / "doctoral_reproduction_golden_v1.json"
E2E_BASELINE_PATH = FIXTURE_DIR / "value101_baseline_48p_head_v1.json"
ZONES_PATH = ROOT / "tests" / "golden" / "zones.json"

GOLDEN_SCHEMA = "value.native-reproduction-golden/v1"
SCENARIO_SCHEMA = "value.native-synthetic-scenario/v1"
SCENARIO_ID = "p06-s1-synthetic-96"
PERIODS = 96
SEGMENT_LENGTH = 8
SIMULATION_YEAR = 2030
PERIOD_HOURS = 0.5
CORRECTION_ID_PATTERN = r"^[a-z0-9]+(\.[a-z0-9-]+)+$"
# Size budgets (plan 4.6 S1: "fixture < 300 KB" is the acceptance limit of the
# capture, i.e. revision 0 with the scenario and the cases).  Every appended
# accounting revision has its own budget: a revision that rewrites every numeric
# accounting column of both variants measures about 47 KB today, so 160 KiB leaves
# room for the planned P0-4 S4/S6, A2 and P0-6 S4/S10 revisions.  A revision
# above it is refused (split it, or raise the budget in the same commit with
# a reason).
REVISION_ZERO_BUDGET_BYTES = 300 * 1024
APPENDED_REVISION_BUDGET_BYTES = 160 * 1024
SHORT_HASH = 12

# Environment of the frozen loop: half-hour periods, no CSV trace files (the
# HEAD default would write market_trace_outputs/ into the source tree), no
# plot-only tranche history, no balance diagnostic file, quiet market stdout.
LOOP_ENVIRONMENT = {
    "PHYSICAL_PERIOD_HOURS": "0.5",
    "SIMULATION_YEAR": str(SIMULATION_YEAR),
    "SAVE_MARKET_TRACE": "0",
    "SAVE_GENERATION_TRACE": "0",
    "MARKET_BALANCE_DIAGNOSTIC": "0",
    "DECARB_SCENARIO": SCENARIO_ID,
    "SIM_DEBUG_MARKET": "0",
}

HEADER = """# Frozen verbatim copy of the 35aadb3 default-PSM period loop (P0-6 S1).
#
# Source: gridform_core/builtin/scheme_c_1000twh/runtime_compat/
#         modular_simulation_model.py at commit 35aadb3, function run_simulation.
# The VERBATIM segments below are byte-identical copies of the named source
# lines; tests/native_reproduction_harness.py pins the SHA-256 of every
# segment and of the whole source file and refuses to run if either differs.
# Only the two HARNESS REPLACEMENT blocks are authored: they replace the
# netCDF weather / interconnector CSV loading (35aadb3:2365-2591) and the
# per-period weather and interconnector assignment (35aadb3:2600-2690) with
# exact synthetic per-period inputs. Everything else -- accumulator
# initialisation (including total_storage_fee_balance at 2274), the
# forecast-based branch at 2734, the storage-fee carry at 2768/2815, the
# ledger boundary at 2857-2956 and the return tuple -- is the HEAD text.
#
# This file is never imported. The harness compiles it into a namespace
# copied from the *current* kernel module, so the market functions it calls
# (ahead_market_bidding, curtailment_market_bidding, balancing_market_bidding,
# ...) are the live ones; the loop around them is frozen HEAD.
# Do not edit. Regenerate only with
# scripts/capture_native_reproduction_golden.py write-head-copy (refuses to
# run unless the source equals the pinned 35aadb3 bytes).

"""

RETURN_NAMES = (
    "avg_electricity_prices", "storage_fees", "store_electricity", "generation_costs",
    "storage_pool", "total_storage_pool", "storage_pools_composition",
    "usage_storage_pool_composition", "avg_gen_fees", "avg_curtailment_fees",
    "avg_balancing_fees", "avg_storage_fees", "ahead_renewables", "ahead_other",
    "ahead_traditional", "ahead_nuclear", "balance_renewables", "balance_other",
    "balance_traditional", "balance_nuclear", "gen_list_composition",
    "curtailed_electricity", "excess_electricity", "total_annual_cost",
    "total_annual_demand", "carbon_emission", "sold_fees", "purchase_fees",
    "traditional_gen", "total_green_hy", "total_renew_capacity", "renew_capacity",
    "total_annual_energycell", "total_income_dict", "excess_energy_dict",
    "excess_energy_final_dict", "curtailed_energy_dict", "renewable_hy_dict",
    "flexible_demand_list", "interconnector_exports_list", "blackout_periods",
)

# Harness-local zone rules, evaluated before tests/golden/zones.json (first
# match wins; unmatched keys fall through to zones.json, whose default is
# trajectory).  tests/golden/zones.json is the single zone authority
# (P0_CONVENTIONS section 2): these rules only cover keys that exist nowhere
# but in this harness ('kernel/*' columns and the per-asset storage_state
# split) and never override zones.json for a real market.sqlite column.
# Cost, fee, income and attribution columns are accounting (Q12); prices,
# dispatch, flows, SoC, asset state and the declared clearing inputs and
# outcomes stay trajectory, as their market.sqlite tables
# (clearing_inputs / clearing_outcomes) are in zones.json and in the X0
# goldens.  Each rule is (pattern, zone, why).
LOCAL_ZONE_RULES = (
    ("kernel/run_simulation::storage_fees", "accounting", "Q12 cost ledger"),
    ("kernel/run_simulation::generation_costs", "accounting", "Q12 cost ledger"),
    ("kernel/run_simulation::avg_gen_fees", "accounting", "Q12 cost ledger"),
    ("kernel/run_simulation::avg_curtailment_fees", "accounting", "Q12 cost ledger"),
    ("kernel/run_simulation::avg_balancing_fees", "accounting", "Q12 cost ledger"),
    ("kernel/run_simulation::avg_storage_fees", "accounting", "Q12 cost ledger"),
    ("kernel/run_simulation::total_annual_cost", "accounting", "Q12 cost ledger"),
    ("kernel/run_simulation::sold_fees", "accounting", "Q12 cost ledger"),
    ("kernel/run_simulation::purchase_fees", "accounting", "Q12 cost ledger"),
    ("kernel/run_simulation::total_income_dict*", "accounting", "Q12 income ledger"),
    ("kernel/run_simulation::ahead_*", "accounting", "Q12 attribution: category cost shares of real demand (HEAD 1449/1695/2827)"),
    ("kernel/run_simulation::balance_*", "accounting", "Q12 attribution: category cost shares of real demand"),
    # P3-14: StorageStateRow.charge_mwh is the literal 0.0 at HEAD (kernel
    # 2997); DECISIONS override (d) lists charge accounting as a universal
    # accounting-zone correction (P0-4 S4).  The per-asset split
    # 'storage_state.<asset>.charge_mwh' exists only in this harness.  The
    # real table column 'storage_state.charge_mwh' is left to zones.json
    # (trajectory today, as pinned by the X0 goldens) until the lead decides
    # the X0 P3-14 zone question.  Not '*charge_mwh', which would also catch
    # discharge_mwh (trajectory).
    ("market/market.sqlite::storage_state.*.charge_mwh", "accounting",
     "harness-only per-asset key; Q12 audit table, P3-14 charge accounting (decision (d)); HEAD literal 0.0, P0-4 S4"),
    # Order ledger: the cost and settlement fields (zones.json already classes
    # orders.physical_resource_cost_gbp / market_payment_gbp as accounting;
    # P5-06, P0-6 S4) are hashed separately from the bid/acceptance fields
    # into this harness-only column.
    ("market/market.sqlite::orders.accounting_row_sha", "accounting",
     "harness-only key: orders.physical_resource_cost_gbp and market_payment_gbp (zones.json accounting; P5-06, P0-6 S4)"),
    # Battery.storage_cost_report(): cost-recovery report (annualised capital,
    # fixed opex, recovery adequacy); recovery_adequacy v2 lands in P0-6 S10.
    # Bid effects of its parameters show up in the trajectory columns.
    ("kernel/storage_cost_report*", "accounting",
     "Q12 cost ledger / validation report: storage cost-recovery report (P0-6 S10)"),
)


# ---------------------------------------------------------------------------
# Source identity
# ---------------------------------------------------------------------------


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def kernel_path(root: Path = ROOT) -> Path:
    return root / KERNEL_RELPATH


def segment_text(source: str, first: int, last: int) -> str:
    lines = source.splitlines(keepends=True)
    return "".join(lines[first - 1:last])


def verify_head_source(source: str) -> None:
    """Raise unless ``source`` is the pinned 35aadb3 kernel text."""

    actual = sha256_text(source)
    if actual != HEAD_KERNEL_SHA256:
        raise ValueError(
            f"kernel source is not the pinned {HEAD_COMMIT} text: expected sha256 "
            f"{HEAD_KERNEL_SHA256}, got {actual}"
        )
    for name, first, last, expected in HEAD_SEGMENTS:
        got = sha256_text(segment_text(source, first, last))
        if got != expected:
            raise ValueError(f"segment {name} {first}-{last}: expected {expected}, got {got}")


def _render(segments: Mapping[str, str], ranges: Mapping[str, tuple[int, int]], label: str, header: str) -> str:
    """Assemble a loop file from the A/C/E segment texts and the two replacements."""

    out = [header]

    def verbatim(name: str) -> None:
        first, last = ranges[name]
        out.append(f"# >>> VERBATIM {name} {label}:{first}-{last}\n")
        out.append(segments[name])
        out.append(f"# <<< VERBATIM {name}\n")

    verbatim("A")
    first, last, what = REPLACED_RANGES["B"]
    out.append(f"    # >>> HARNESS REPLACEMENT B for {HEAD_COMMIT}:{first}-{last} ({what})\n")
    out.append("    _p06_driver = __p06_synthetic_driver__\n")
    out.append("    # <<< HARNESS REPLACEMENT B\n\n")
    verbatim("C")
    first, last, what = REPLACED_RANGES["D"]
    out.append(f"        # >>> HARNESS REPLACEMENT D for {HEAD_COMMIT}:{first}-{last} ({what})\n")
    out.append("        _p06_driver.begin_period(period, generators, batterys, connections, electrolyzer)\n")
    out.append("        # <<< HARNESS REPLACEMENT D\n")
    verbatim("E")
    return "".join(out)


def _head_ranges() -> dict[str, tuple[int, int]]:
    return {name: (first, last) for name, first, last, _ in HEAD_SEGMENTS}


def render_head_copy(source: str) -> str:
    """The frozen copy file, rendered from the pinned 35aadb3 kernel source."""

    verify_head_source(source)
    ranges = _head_ranges()
    segments = {name: segment_text(source, first, last) for name, (first, last) in ranges.items()}
    return _render(segments, ranges, HEAD_COMMIT, HEADER)


def copied_segments(copy_text: str) -> dict[str, str]:
    """Extract the VERBATIM segments from the committed copy file."""

    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in copy_text.splitlines(keepends=True):
        if line.startswith("# >>> VERBATIM "):
            current = line.split()[3]
            found[current] = []
            continue
        if line.startswith("# <<< VERBATIM "):
            current = None
            continue
        if current is not None:
            found[current].append(line)
    return {name: "".join(lines) for name, lines in found.items()}


def verify_head_copy(copy_text: str | None = None) -> dict[str, Any]:
    """Check the committed copy: pinned segment hashes and the whole file.

    This does not need the 35aadb3 source: the per-segment SHA-256 values are
    the hashes of the HEAD lines, so a byte change anywhere in a VERBATIM block
    is detected even after the live kernel diverges.  Text outside the VERBATIM
    blocks (header, markers, the two replacements) is checked by re-rendering
    the whole file from the verified segments and by the pinned
    ``HEAD_COPY_SHA256``, so an injected line anywhere is rejected.
    """

    text = HEAD_COPY_PATH.read_text(encoding="utf-8") if copy_text is None else copy_text
    segments = copied_segments(text)
    expected_names = [name for name, *_ in HEAD_SEGMENTS]
    if sorted(segments) != sorted(expected_names):
        raise ValueError(f"head copy has segments {sorted(segments)}, expected {expected_names}")
    for name, first, last, expected in HEAD_SEGMENTS:
        got = sha256_text(segments[name])
        if got != expected:
            raise ValueError(f"head copy segment {name} ({HEAD_COMMIT}:{first}-{last}) was edited: {got}")
    if _render(segments, _head_ranges(), HEAD_COMMIT, HEADER) != text:
        raise ValueError("head copy differs from the rendering of its verified segments (text outside VERBATIM blocks was edited)")
    copy_sha = sha256_text(text)
    if copy_sha != HEAD_COPY_SHA256:
        raise ValueError(f"head copy sha256 {copy_sha} is not the pinned {HEAD_COPY_SHA256}")
    return {
        "head_commit": HEAD_COMMIT,
        "kernel": KERNEL_RELPATH,
        "kernel_sha256": HEAD_KERNEL_SHA256,
        "segments": {name: {"lines": [first, last], "sha256": sha} for name, first, last, sha in HEAD_SEGMENTS},
        "replaced": {name: {"lines": [first, last], "what": what} for name, (first, last, what) in REPLACED_RANGES.items()},
        "copy_sha256": copy_sha,
    }


# Anchors that locate the same A/B/C/D/E split in the *current* kernel text.
LIVE_ANCHORS = {
    "function": "def run_simulation(",
    "B": "    # This part was moved from the if __name__",
    "C": "    for period in range(periods):",
    "D": "        solar_Nottingham.capacity_limit",
    "E": "        # chosen generation in wholesale",
}
LIVE_LABEL = "live"
LIVE_HEADER = """# Live default-PSM period loop rendered by tests/native_reproduction_harness.py
# (render_live_loop) from the current kernel text with the same two synthetic
# input replacements as the frozen 35aadb3 copy.  Generated in memory only.

"""


def live_loop_ranges(source: str) -> dict[str, tuple[int, int]]:
    """1-based A/C/E line ranges of ``run_simulation`` in ``source``, found by anchors.

    A runs from ``def run_simulation(`` to the line before the weather-loading
    block, C from ``for period in range(periods):`` to the line before the
    per-period weather assignment, E from the blank lines before the first
    clearing comment to the last non-blank line of the function (the next
    column-0 line ends it).  Raises ``LookupError`` when an anchor is missing,
    e.g. after P0-6 S3 moves the period body into ``realise_period``; such a
    step must update these anchors or pass its own ``loop=``.
    """

    lines = source.splitlines(keepends=True)

    def find(prefix: str, after: int) -> int:
        for index in range(after, len(lines)):
            if lines[index].startswith(prefix):
                return index
        raise LookupError(f"live kernel has no line starting with {prefix!r} after line {after + 1}")

    function = find(LIVE_ANCHORS["function"], 0)
    b_start = find(LIVE_ANCHORS["B"], function + 1)
    c_start = find(LIVE_ANCHORS["C"], b_start + 1)
    d_start = find(LIVE_ANCHORS["D"], c_start + 1)
    e_anchor = find(LIVE_ANCHORS["E"], d_start + 1)
    e_start = e_anchor
    while e_start - 1 > d_start and not lines[e_start - 1].strip():
        e_start -= 1
    end = len(lines)
    for index in range(e_anchor + 1, len(lines)):
        if lines[index][:1] not in ("", " ", "\t", "\n", "\r"):
            end = index
            break
    while end - 1 > e_anchor and not lines[end - 1].strip():
        end -= 1
    return {"A": (function + 1, b_start), "C": (c_start + 1, d_start), "E": (e_start + 1, end)}


def render_live_loop(source: str, *, label: str = LIVE_LABEL, header: str = LIVE_HEADER) -> str:
    """The current kernel loop with the same B/D input replacements as the frozen copy.

    At 35aadb3, ``render_live_loop(source, label=HEAD_COMMIT, header=HEADER)``
    is byte-identical to the committed frozen copy (tested).  Unlike the
    frozen copy it carries the *current* ledger boundary, so universal
    accounting corrections made in the loop (P0-4 S4-S6, P0-6 S4, A2 stress
    events) reach the golden only through this loop.
    """

    ranges = live_loop_ranges(source)
    segments = {name: segment_text(source, first, last) for name, (first, last) in ranges.items()}
    return _render(segments, ranges, label, header)


def live_kernel_is_head(root: Path = ROOT) -> bool:
    return sha256_text(kernel_path(root).read_text(encoding="utf-8")) == HEAD_KERNEL_SHA256


def tree_sha256(directory: Path) -> str:
    """Content hash of every file below ``directory`` (``__pycache__`` ignored)."""

    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(path.relative_to(directory).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii") + b"\n")
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Synthetic scenario
# ---------------------------------------------------------------------------

# Small fleet with the thesis cost structure (config.py) at toy scale.  Units:
# power in MW per half-hour period, exactly as the kernel uses them.
FLEET = {
    "generators": [
        {"kind": "NuclearGenerator", "args": {
            "name": "Nuclear", "gen_cost": 0, "curtail_cost": 91430, "carbon_emission": 0,
            "capacity_limit": 40, "alter_limit": 5, "startup_cost": 500,
            "capital_cost": 3_200_000, "unit_time_cost": 0}},
        {"kind": "WaterGenerator", "args": {
            "name": "Hydro_natural_flow", "gen_cost": 0, "curtail_cost": 0, "carbon_emission": 0,
            "capacity_limit": 10, "alter_limit": 10, "energy_limit": 10, "add_energy": 6,
            "capital_cost": 1_000_000_000, "real_gen_energy": 0, "unit_time_cost": 0}},
        {"kind": "BiomassGenerator", "args": {
            "name": "bio_and_waste", "gen_cost": 0.2, "curtail_cost": 3, "carbon_emission": 0,
            "capacity_limit": 8, "alter_limit": 2, "startup_cost": 83, "energy_limit": 30,
            "add_energy": 3, "carbon_intensity": 120, "capital_cost": 16_000_000,
            "carbon_price": 4.8, "fuel_cost": 80, "real_gen_energy": 0, "unit_time_cost": 0}},
        {"kind": "GasGenerator", "args": {
            "name": "CCGT", "gen_cost": 0.1, "curtail_cost": 48.04, "carbon_emission": 0,
            "capacity_limit": 60, "alter_limit": 30, "startup_cost": 50, "carbon_intensity": 394,
            "capital_cost": 96_000_000, "carbon_price": 15.76, "fuel_cost": 39.21,
            "real_gen_energy": 0, "unit_time_cost": 0}},
        {"kind": "GasGenerator", "args": {
            "name": "OCGT", "gen_cost": 0.1, "curtail_cost": 81.95, "carbon_emission": 0,
            "capacity_limit": 25, "alter_limit": 25, "startup_cost": 30, "carbon_intensity": 651,
            "capital_cost": 17_500_000, "carbon_price": 26.04, "fuel_cost": 48.78,
            "real_gen_energy": 0, "unit_time_cost": 0}},
        {"kind": "ExpensiverenewableGenerator", "args": {
            "name": "offshore1", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0,
            "capital_cost": 111_000_000, "real_gen_energy": 0, "unit_time_cost": 0,
            "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1,
            "rampup_rate": 0.125, "capacity_multiplier": 1.5}},
        {"kind": "ExpensiverenewableGenerator", "args": {
            "name": "onshore_Edinburgh", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0,
            "capital_cost": 36_600_000, "real_gen_energy": 0, "unit_time_cost": 0,
            "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 1,
            "rampup_rate": 0.125, "capacity_multiplier": 1.5}},
        {"kind": "ExpensiverenewableGenerator", "args": {
            "name": "solar_London", "gen_cost": 0.0001, "curtail_cost": 0, "carbon_emission": 0,
            "capital_cost": 15_000_000, "real_gen_energy": 0, "unit_time_cost": 0,
            "electrolyzer_cost": 15000, "energy_efficiency": 0.65, "electrolyzer_limit": 0,
            "rampup_rate": 0.125, "capacity_multiplier": 20}},
    ],
    "batteries": [
        {"name": "li_battery", "pool_limit": 40, "per_pool_limit": 20, "storage_fee": 135.26,
         "per_storage_fee": 0.1736, "n_1": 0.98, "n_2": 0.98, "carbon_emission": 50,
         "capital_cost": 7_260_000, "battery_type": "0.5c"},
        {"name": "pumpedhydro_battery", "pool_limit": 60, "per_pool_limit": 15, "storage_fee": 0,
         "per_storage_fee": 1.1008, "n_1": 0.87, "n_2": 0.87, "carbon_emission": 40,
         "capital_cost": 5_400_000, "battery_type": "pumped_hydro"},
        {"name": "thermal_battery", "pool_limit": 10, "per_pool_limit": 5, "storage_fee": 0,
         "per_storage_fee": 1.0558, "n_1": 0.81, "n_2": 0.81, "carbon_emission": 50,
         "capital_cost": 3_300_000, "battery_type": "1c"},
    ],
    "connections": [
        {"name": "Interconnect_France", "capital_cost": 394_400_000, "carbon_emission": 0, "carbon_intensity": 53},
        {"name": "Interconnect_Norway", "capital_cost": 276_080_000, "carbon_emission": 0, "carbon_intensity": 100},
    ],
    "electrolyzer": {
        "name": "electrolyzer", "capital_cost": 1_500_000, "operational_cost": 30000,
        "energy_efficiency": 0.65, "cycle_life": 50000, "capacity_limit": 6,
        "rampup_rate": 2, "body_emission": 0,
    },
}

VRE_NAMES = ("offshore1", "onshore_Edinburgh", "solar_London")
CONNECTION_NAMES = ("Interconnect_France", "Interconnect_Norway")

# Twelve 8-period segments.  Each row: forecast F, real R, VRE availability
# (offshore, onshore, solar) and interconnector (transfer MW, price GBP/MWh) for
# France and Norway; positive transfer = import capability, negative = export.
# "purpose" names the HEAD behaviour the segment is built to exercise; the
# coverage_facts observed from the run (not the inputs) are what the tests
# require.  The nuclear-surplus segment follows the VRE-surplus segment so that
# storage is full and cannot absorb the nuclear surplus before the exports.
SEGMENTS: tuple[dict[str, Any], ...] = (
    {"purpose": "warm-up: forecast met by VRE and thermal, realised slightly above forecast (balancing with VRE excess)",
     "rows": [
        (90, 93, (20, 12, 0), (0, 60), (0, 55)),
        (92, 95, (22, 12, 0), (0, 60), (0, 55)),
        (95, 97, (24, 10, 0), (0, 60), (0, 55)),
        (98, 101, (24, 10, 2), (0, 60), (0, 55)),
        (100, 104, (26, 12, 6), (0, 60), (0, 55)),
        (104, 106, (28, 12, 10), (0, 60), (0, 55)),
        (106, 106, (30, 14, 14), (0, 60), (0, 55)),
        (108, 112, (30, 14, 18), (0, 60), (0, 55)),
     ]},
    {"purpose": "forecast above available supply (commits nuclear); realised far above (imports, unserved deficit) and far below (P3-01 toy F120/R28)",
     "rows": [
        (150, 160, (4, 2, 0), (10, 95), (5, 110)),
        (180, 190, (2, 2, 0), (10, 95), (5, 110)),
        (200, 260, (2, 0, 0), (0, 95), (0, 110)),
        (120, 28, (0, 0, 0), (0, 95), (0, 110)),
        (200, 250, (0, 0, 0), (20, 95), (10, 110)),
        (120, 28, (0, 0, 0), (0, 95), (0, 110)),
        (160, 150, (6, 4, 0), (0, 95), (0, 110)),
        (140, 145, (8, 4, 0), (10, 95), (5, 110)),
     ]},
    {"purpose": "nuclear blocking: forecast below the nuclear ramp floor, VRE not accepted and not recorded (HEAD 1463); nuclear surplus re-booked in balancing (DEV-BAL-04)",
     "rows": [
        (34, 36, (30, 20, 10), (0, 50), (0, 45)),
        (30, 37, (32, 20, 12), (0, 50), (0, 45)),
        (26, 24, (35, 20, 14), (0, 50), (0, 45)),
        (22, 27, (35, 22, 16), (0, 50), (0, 45)),
        (18, 15, (38, 22, 16), (-8, 50), (0, 45)),
        (16, 21, (40, 24, 14), (0, 50), (0, 45)),
        (14, 14, (40, 24, 12), (0, 50), (0, 45)),
        (12, 16, (38, 22, 10), (0, 50), (0, 45)),
     ]},
    {"purpose": "VRE surplus with realised below forecast: curtailment branch charges storage from need and excess, exports, electrolysis",
     "rows": [
        (100, 92, (60, 30, 30), (-15, 40), (0, 30)),
        (100, 90, (70, 30, 32), (-15, 40), (-10, 25)),
        (98, 86, (75, 35, 34), (-15, 40), (-10, 25)),
        (96, 80, (80, 35, 34), (-15, 40), (-10, 25)),
        (94, 85, (80, 40, 30), (-15, 40), (-10, -5)),
        (92, 88, (70, 40, 26), (0, 40), (-10, -5)),
        (92, 84, (65, 35, 22), (0, 40), (0, 25)),
        (90, 85, (60, 30, 18), (0, 40), (0, 25)),
     ]},
    {"purpose": ("nuclear surplus with storage full after the VRE-surplus segment: the nuclear ramp floor stays above "
                 "the forecast and the non-VRE surplus is exported in the curtailment branch (Q7 non_vre_spill "
                 "path), the rest goes to electrolysis and down-regulation; zero and negative export prices "
                 "refuse the export"),
     "rows": [
        (10, 6, (10, 6, 0), (-6, 35), (-4, 20)),
        (10, 5, (12, 6, 0), (-6, 35), (-4, 0)),
        (12, 7, (12, 8, 0), (-3, 35), (-6, 20)),
        (14, 8, (14, 8, 0), (-6, -2), (-6, 20)),
        (16, 12, (14, 8, 0), (-6, 35), (0, 20)),
        (20, 17, (12, 6, 0), (0, 35), (-6, 20)),
        (26, 24, (10, 6, 0), (-6, 35), (-6, 20)),
        (32, 31, (8, 4, 0), (0, 35), (0, 20)),
     ]},
    {"purpose": "balancing periods with storage discharge followed by curtailment periods (storage-fee carry, HEAD 2274/2768/2815)",
     "rows": [
        (100, 115, (20, 10, 0), (0, 80), (0, 90)),
        (100, 90, (40, 20, 0), (-10, 30), (0, 90)),
        (100, 118, (20, 10, 0), (0, 80), (0, 90)),
        (100, 92, (45, 20, 0), (-10, 30), (0, 90)),
        (105, 122, (15, 10, 0), (0, 80), (0, 90)),
        (105, 99, (50, 25, 0), (0, 30), (0, 90)),
        (110, 126, (10, 8, 0), (0, 80), (0, 90)),
        (110, 104, (55, 25, 0), (-10, 30), (0, 90)),
     ]},
    {"purpose": "storage arbitrage: low forecast with high VRE charges storage, evening peak discharges it in the ahead stage",
     "rows": [
        (60, 55, (60, 30, 0), (0, 40), (0, 40)),
        (60, 54, (65, 30, 0), (0, 40), (0, 40)),
        (62, 58, (65, 32, 0), (0, 40), (0, 40)),
        (64, 60, (60, 30, 0), (0, 40), (0, 40)),
        (130, 132, (10, 4, 0), (0, 120), (0, 120)),
        (140, 143, (8, 4, 0), (0, 120), (0, 120)),
        (145, 150, (6, 2, 0), (0, 120), (0, 120)),
        (135, 138, (6, 2, 0), (0, 120), (0, 120)),
     ]},
    {"purpose": "thermal down-regulation with ramp limits (curtail-cost order, hydro/biomass budgets, HEAD 985-1052)",
     "rows": [
        (120, 118, (0, 0, 0), (0, 70), (0, 70)),
        (125, 124, (0, 0, 0), (0, 70), (0, 70)),
        (125, 95, (0, 0, 0), (0, 70), (0, 70)),
        (120, 70, (0, 0, 0), (0, 70), (0, 70)),
        (110, 105, (0, 0, 0), (0, 70), (0, 70)),
        (115, 60, (0, 0, 0), (0, 70), (0, 70)),
        (118, 117, (0, 0, 0), (0, 70), (0, 70)),
        (118, 80, (0, 0, 0), (0, 70), (0, 70)),
     ]},
    {"purpose": "large upward balancing served by imports at different prices",
     "rows": [
        (80, 110, (10, 5, 0), (25, 52), (15, 58)),
        (80, 115, (10, 5, 0), (25, 52), (15, 58)),
        (85, 120, (8, 5, 0), (25, 70), (15, 58)),
        (85, 118, (8, 5, 0), (5, 52), (5, 58)),
        (90, 125, (6, 4, 0), (25, 52), (15, 58)),
        (90, 100, (6, 4, 0), (25, 52), (15, 58)),
        (92, 130, (4, 2, 0), (25, 120), (15, 130)),
        (95, 100, (4, 2, 0), (25, 52), (15, 58)),
     ]},
    {"purpose": "VRE availability below the pre-clearing electrolysis skim (HEAD 1173 leak) and exact VRE fills",
     "rows": [
        (70, 72, (0.05, 0.6, 0), (0, 60), (0, 60)),
        (70, 69, (0.5, 0.05, 0), (0, 60), (0, 60)),
        (70, 70, (1.0, 1.125, 0), (0, 60), (0, 60)),
        (40, 41, (25, 15, 0), (0, 60), (0, 60)),
        (40, 39, (25.0, 15.0, 0), (0, 60), (0, 60)),
        (70, 75, (0.2, 0.2, 0.2), (0, 60), (0, 60)),
        (70, 66, (2, 2, 2), (0, 60), (0, 60)),
        (72, 74, (3, 3, 3), (0, 60), (0, 60)),
     ]},
    {"purpose": "edge periods: realised equal to forecast, zero forecast, zero realised demand",
     "rows": [
        (80, 80, (20, 10, 5), (0, 60), (0, 60)),
        (0, 20, (20, 10, 5), (0, 60), (0, 60)),
        (60, 0, (20, 10, 5), (-10, 40), (0, 60)),
        (80, 80, (0, 0, 0), (0, 60), (0, 60)),
        (0, 0, (5, 5, 5), (0, 60), (0, 60)),
        (75, 76, (10, 10, 10), (0, 60), (0, 60)),
        (75, 75, (10, 10, 10), (-5, 40), (5, 60)),
        (78, 70, (10, 10, 10), (-5, 40), (5, 60)),
     ]},
)
RANDOM_SEGMENT_PURPOSE = "seeded random mix (random.Random(606)) for broad branch coverage"
RANDOM_SEED = 606


def _random_rows(count: int) -> list[tuple]:
    rng = random.Random(RANDOM_SEED)
    rows = []
    for _ in range(count):
        forecast = rng.randint(30, 180)
        real = max(forecast + rng.randint(-40, 40), 0)
        vre = (rng.randint(0, 70), rng.randint(0, 40), rng.randint(0, 30))
        france = (rng.choice((-15, -5, 0, 10, 20)), rng.choice((-3, 0, 35, 60, 95)))
        norway = (rng.choice((-10, 0, 5, 15)), rng.choice((0, 25, 58, 110)))
        rows.append((forecast, real, vre, france, norway))
    return rows


def build_scenario() -> dict[str, Any]:
    """The deterministic 96-period synthetic scenario (inputs only)."""

    rows: list[tuple] = []
    purposes = []
    for segment in SEGMENTS:
        purposes.append({"first_period": len(rows), "periods": len(segment["rows"]), "purpose": segment["purpose"]})
        rows.extend(segment["rows"])
    purposes.append({"first_period": len(rows), "periods": PERIODS - len(rows), "purpose": RANDOM_SEGMENT_PURPOSE})
    rows.extend(_random_rows(PERIODS - len(rows)))
    if len(rows) != PERIODS:
        raise AssertionError(f"scenario has {len(rows)} periods, expected {PERIODS}")
    scenario = {
        "schema_version": SCENARIO_SCHEMA,
        "id": SCENARIO_ID,
        "periods": PERIODS,
        "period_hours": PERIOD_HOURS,
        "simulation_year": SIMULATION_YEAR,
        "bidding_factor": 1.0,
        "fleet": copy.deepcopy(FLEET),
        "segments": purposes,
        "forecast_mw": [float(row[0]) for row in rows],
        "real_mw": [float(row[1]) for row in rows],
        "vre_availability_mw": {
            name: [float(row[2][index]) for row in rows] for index, name in enumerate(VRE_NAMES)
        },
        "interconnectors": {
            name: {
                "transfer_constraint_mw": [float(row[3 + index][0]) for row in rows],
                "external_price_gbp_per_mwh": [float(row[3 + index][1]) for row in rows],
            }
            for index, name in enumerate(CONNECTION_NAMES)
        },
    }
    return scenario


# Storage-cost variants.  "dynamic" is the default PSM storage module
# (dynamic-annual-storage-cost); "legacy_tariff" is the doctoral reference
# configuration (decision Q3: value-legacy-storage-tariff).
VARIANTS = ("dynamic", "legacy_tariff")


def _storage_definition(variant: str):
    from gridform_core.builtin.scheme_c_1000twh.runtime_compat import storage_cost

    if variant == "dynamic":
        return storage_cost.DynamicStorageCostDefinition(None, {})
    if variant == "legacy_tariff":
        return storage_cost.SchemeCLegacyStorageCostDefinition(None, {})
    raise ValueError(f"unknown storage variant {variant!r}")


# ---------------------------------------------------------------------------
# Recording ledger and driver
# ---------------------------------------------------------------------------


def _short(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:SHORT_HASH]


class RecordingLedger:
    """In-memory full-trace market ledger capturing what the loop records."""

    trace_level = "full"
    schema_version = "p06-recording"

    def __init__(self) -> None:
        self.periods: list[dict[str, Any]] = []
        self.orders: list[list[dict[str, Any]]] = []
        self.storage: list[dict[str, Any]] = []
        self.declared: list[dict[str, Any]] = []
        self.storage_audit: list[dict[str, Any]] = []
        self.surplus_routing: list[dict[str, Any]] = []

    def record_period(self, row) -> None:
        self.periods.append(dataclasses.asdict(row))

    def record_orders(self, rows) -> None:
        self.orders.append([dataclasses.asdict(row) for row in rows])

    def record_storage(self, rows) -> None:
        self.storage.extend(dataclasses.asdict(row) for row in rows)

    def record_storage_audit(self, rows) -> None:
        # P0-4 S4: per-asset storage energy audit (accounting, zones.json).
        self.storage_audit.extend(dataclasses.asdict(row) for row in rows)

    def record_surplus_routing(self, rows) -> None:
        # P0-4 S5: source-classified surplus routing (accounting, zones.json).
        self.surplus_routing.extend(dataclasses.asdict(row) for row in rows)

    def record_clearing_input(self, row) -> None:
        self.declared.append({
            "kind": "input", "period": int(row.period), "stage": str(row.stage),
            "input_sha256": str(row.input_sha256), "payload": _short(str(row.payload_json)),
        })

    def record_clearing_outcome(self, row) -> None:
        outcome = json.loads(str(row.outcome_json))
        accepted = outcome.get("accepted", []) if isinstance(outcome, Mapping) else []
        self.declared.append({
            "kind": "outcome", "input_sha256": str(row.input_sha256),
            "payload": _short(str(row.outcome_json)),
            "unserved_target_mw": float(outcome.get("unserved_target_power_mw", 0.0)) if isinstance(outcome, Mapping) else 0.0,
            "storage_accepted_mw": float(sum(
                float(item.get("accepted_power_mw", 0.0))
                for item in accepted if item.get("asset_type") == "Battery"
            )),
        })

    def __getattr__(self, name: str):
        # Fail closed: a ledger writer this harness does not know is an error,
        # also for hasattr()/getattr(..., None) probes (hasattr only swallows
        # AttributeError).  Writers that later steps add to the loop must be
        # added here: P0-4 S4 (storage energy audit), P0-4 S5 (surplus
        # routing), P0-4 S6 (declare_balance_boundary, compatibility
        # adjustment metadata) and the A2 stress-event writers.
        if name.startswith(("record_", "declare_")):
            raise NotImplementedError(
                f"RecordingLedger has no {name}(): the loop called a ledger writer that "
                "tests/native_reproduction_harness.py does not record; add it to RecordingLedger "
                "and to columns_from_run (with a zone rule) in the same commit"
            )
        raise AttributeError(name)

    def close(self) -> dict[str, object]:
        return {"trace_level": self.trace_level}


def _asset_state(asset) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for attribute in (
        "real_gen_energy", "capacity_limit", "run_time", "have_gen_energy", "energy_limit",
        "real_energy", "if_curtail", "sold_energy", "transfer_constraint", "external_price",
    ):
        if hasattr(asset, attribute):
            state[attribute] = getattr(asset, attribute)
    stored = getattr(asset, "stored_energy", None)
    if isinstance(stored, dict) and hasattr(asset, "cost_recovery"):
        state["stored_energy_total"] = sum(float(value) for value in stored.values())
        state["stored_tranches"] = len(stored)
        state["stored_tranche_sha"] = _short(json.dumps(
            [[int(key), float(value)] for key, value in stored.items()]
        ))
    recovery = getattr(asset, "cost_recovery", None)
    if recovery is not None:
        current = getattr(recovery, "current", None)
        if current is not None:
            state["recovery_sold_energy_mwh"] = float(current.sold_energy_mwh)
            state["recovery_dwell_weighted_mwh_periods"] = float(current.dwell_weighted_sold_mwh_periods)
    return state


class SyntheticDriver:
    """Supplies exact per-period inputs and snapshots end-of-period state."""

    def __init__(self, scenario: Mapping[str, Any]) -> None:
        self.scenario = scenario
        self.snapshots: list[dict[str, dict[str, Any]]] = []
        self._previous: int | None = None

    @staticmethod
    def _snapshot(generators, batterys, connections, electrolyzer) -> dict[str, dict[str, Any]]:
        snapshot = {}
        for asset in list(generators) + list(batterys) + list(connections):
            snapshot[str(asset.name)] = _asset_state(asset)
        snapshot["electrolyzer"] = _asset_state(electrolyzer)
        return snapshot

    def begin_period(self, period, generators, batterys, connections, electrolyzer) -> None:
        period = int(period)
        expected = 0 if self._previous is None else self._previous + 1
        if period != expected:
            raise AssertionError(f"driver saw period {period}, expected {expected}")
        if self._previous is not None:
            self.snapshots.append(self._snapshot(generators, batterys, connections, electrolyzer))
        self._previous = period
        by_name = {str(asset.name): asset for asset in generators}
        for name, series in self.scenario["vre_availability_mw"].items():
            by_name[name].capacity_limit = series[period]
        connection_by_name = {str(asset.name): asset for asset in connections}
        for name, series in self.scenario["interconnectors"].items():
            connection_by_name[name].transfer_constraint = series["transfer_constraint_mw"][period]
            connection_by_name[name].external_price = series["external_price_gbp_per_mwh"][period]

    def finish(self, generators, batterys, connections, electrolyzer) -> None:
        self.snapshots.append(self._snapshot(generators, batterys, connections, electrolyzer))


@contextlib.contextmanager
def _loop_environment(kernel, variant: str, bidding_factor: float,
                      runtime_attributes: Mapping[str, Any] | None = None) -> Iterator[None]:
    from gridform_core import market_ledger as ledger_module
    from gridform_core.builtin.scheme_c_1000twh.runtime_compat import module_context

    saved_environment = {key: os.environ.get(key) for key in LOOP_ENVIRONMENT}
    saved_bidding = kernel.config.simulation_parameters.get("bidding_factor")
    saved_runtime = module_context._runtime
    saved_ledger = ledger_module._ACTIVE_LEDGER
    try:
        os.environ.update(LOOP_ENVIRONMENT)
        kernel.config.simulation_parameters["bidding_factor"] = bidding_factor
        # HEAD's loop only reads ``storage_cost`` from the module runtime.  From
        # P0-6 S2 on the live kernel refuses a configured runtime without
        # ``market_rules``; the golden is the doctoral rule set's oracle, so it
        # is the default here (callers may override through runtime_attributes).
        from gridform_core.builtin.scheme_c_1000twh.native_market_rules import DOCTORAL

        attributes = {"market_rules": DOCTORAL, **dict(runtime_attributes or {})}
        module_context._runtime = SimpleNamespace(
            storage_cost=_storage_definition(variant), **attributes
        )
        yield
    finally:
        for key, value in saved_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        kernel.config.simulation_parameters["bidding_factor"] = saved_bidding
        module_context._runtime = saved_runtime
        ledger_module._ACTIVE_LEDGER = saved_ledger


def kernel_module():
    import importlib

    return importlib.import_module(KERNEL_MODULE)


def _compile_loop(text: str, filename: str, kernel) -> tuple[Callable[..., Any], dict[str, Any]]:
    namespace = dict(vars(kernel))
    namespace["__name__"] = "p06_synthetic_loop"
    code = compile(text, filename, "exec")
    exec(code, namespace)  # noqa: S102 - hash-verified frozen copy or anchored live kernel text
    return namespace["run_simulation"], namespace


def compile_head_loop(kernel=None) -> tuple[Callable[..., Any], dict[str, Any]]:
    """Compile the frozen copy into a namespace cloned from the live kernel."""

    kernel = kernel or kernel_module()
    verify_head_copy()
    return _compile_loop(HEAD_COPY_PATH.read_text(encoding="utf-8"), str(HEAD_COPY_PATH), kernel)


def compile_live_loop(kernel=None) -> tuple[Callable[..., Any], dict[str, Any]]:
    """Compile :func:`render_live_loop` of the current kernel file (live ledger boundary)."""

    kernel = kernel or kernel_module()
    source = kernel_path().read_text(encoding="utf-8")
    return _compile_loop(render_live_loop(source), f"<live {KERNEL_RELPATH}>", kernel)


# Module global through which a loop reaches the SyntheticDriver.
DRIVER_GLOBAL = "__p06_synthetic_driver__"

# Loop drivers.  "frozen": the verbatim 35aadb3 loop (HEAD ledger boundary,
# live market functions); "live": the current kernel loop with the same input
# replacements (current ledger boundary and market functions).
LOOPS = ("frozen", "live")


def resolve_loop(loop, kernel=None) -> tuple[Callable[..., Any], dict[str, Any]]:
    if loop is None or loop == "frozen":
        return compile_head_loop(kernel)
    if loop == "live":
        return compile_live_loop(kernel)
    if callable(loop):
        return loop, getattr(loop, "__globals__", {})
    raise ValueError(f"unknown loop {loop!r}; expected one of {LOOPS} or a callable")


def build_assets(kernel, scenario: Mapping[str, Any]):
    fleet = scenario["fleet"]
    generators = [getattr(kernel, item["kind"])(**item["args"]) for item in fleet["generators"]]
    batteries = [kernel.Battery(**item) for item in fleet["batteries"]]
    connections = [kernel.Connection(**item) for item in fleet["connections"]]
    electrolyzer = kernel.Electrolyzer(**fleet["electrolyzer"])
    for battery in batteries:
        battery.prepare_operating_year(int(scenario["simulation_year"]))
    return generators, batteries, connections, electrolyzer


def run_case(variant: str, scenario: Mapping[str, Any] | None = None, *, loop=None,
             runtime_attributes: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Run one storage variant of the synthetic scenario; return raw results.

    ``loop`` is ``"frozen"`` (default, the verbatim 35aadb3 loop), ``"live"``
    (:func:`compile_live_loop`) or a callable with ``run_simulation``'s
    signature.

    ``runtime_attributes`` are added to the module runtime next to
    ``storage_cost`` (for example the doctoral ``market_rules`` of P0-6 S2);
    the HEAD capture passes none.
    """

    from gridform_core import market_ledger as ledger_module
    import numpy as np

    scenario = scenario or build_scenario()
    kernel = kernel_module()
    driver = SyntheticDriver(scenario)
    loop, namespace = resolve_loop(loop, kernel)
    ledger = RecordingLedger()
    # A callable loop may live in a real module (for example a P0-6 S3
    # realise_period driver in the kernel): its globals get the driver only
    # for the duration of the run.
    missing = object()
    saved_driver = namespace.get(DRIVER_GLOBAL, missing)
    try:
        with _loop_environment(kernel, variant, float(scenario["bidding_factor"]), runtime_attributes):
            namespace[DRIVER_GLOBAL] = driver
            generators, batteries, connections, electrolyzer = build_assets(kernel, scenario)
            ledger_module.set_active_market_ledger(ledger)
            raw = loop(
                int(scenario["periods"]), generators, batteries,
                np.asarray(scenario["forecast_mw"], dtype=float),
                np.asarray(scenario["real_mw"], dtype=float),
                connections, electrolyzer,
            )
            driver.finish(generators, batteries, connections, electrolyzer)
            storage_reports = {str(battery.name): battery.storage_cost_report() for battery in batteries}
    finally:
        if saved_driver is missing:
            namespace.pop(DRIVER_GLOBAL, None)
        else:
            namespace[DRIVER_GLOBAL] = saved_driver
    if len(raw) != len(RETURN_NAMES):
        raise AssertionError(f"loop returned {len(raw)} values, expected {len(RETURN_NAMES)}")
    return {
        "raw": dict(zip(RETURN_NAMES, raw)),
        "ledger": ledger,
        "snapshots": driver.snapshots,
        "storage_reports": storage_reports,
    }


# ---------------------------------------------------------------------------
# Canonical golden columns
# ---------------------------------------------------------------------------


def canonical(value: Any) -> Any:
    """JSON-ready, order-preserving representation; assets become names."""

    import numpy as np

    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value)
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, np.ndarray):
        return [canonical(item) for item in value.tolist()]
    if isinstance(value, Mapping):
        return {_key(key): canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    if hasattr(value, "name"):
        return f"<{value.__class__.__name__}:{value.name}>"
    return f"<{value.__class__.__name__}>"


def _key(key: Any) -> str:
    if hasattr(key, "name") and not isinstance(key, str):
        return f"<{key.__class__.__name__}:{key.name}>"
    return str(canonical(key))


def _per_period(values: Sequence[Any], periods: int, name: str) -> list[Any]:
    values = list(values)
    if len(values) != periods:
        raise AssertionError(f"{name}: {len(values)} values for {periods} periods")
    return values


ORDER_TRAJECTORY_FIELDS = (
    "order_id", "year", "period", "stage", "asset_id", "asset_type", "side",
    "offer_price_gbp_per_mwh", "offered_mwh", "accepted_mwh", "status", "reason_code",
)
ORDER_ACCOUNTING_FIELDS = ("physical_resource_cost_gbp", "market_payment_gbp")


def columns_from_run(result: Mapping[str, Any], periods: int = PERIODS) -> dict[str, Any]:
    """Column-oriented canonical view of one run (key -> per-period list or value)."""

    raw = result["raw"]
    ledger: RecordingLedger = result["ledger"]
    columns: dict[str, Any] = {}

    # Market ledger rows recorded by the HEAD boundary (2857-2956).
    if len(ledger.periods) != periods:
        raise AssertionError(f"ledger recorded {len(ledger.periods)} periods")
    for field in ledger.periods[0]:
        columns[f"market/market.sqlite::period_summary.{field}"] = [canonical(row[field]) for row in ledger.periods]
    storage_by_asset: dict[str, list[dict[str, Any]]] = {}
    for row in ledger.storage:
        storage_by_asset.setdefault(str(row["asset_id"]), []).append(row)
    for asset, rows in storage_by_asset.items():
        for field in ("state_of_charge_mwh", "charge_mwh", "discharge_mwh", "power_capacity_mw", "energy_capacity_mwh"):
            columns[f"market/market.sqlite::storage_state.{asset}.{field}"] = _per_period(
                [canonical(row[field]) for row in rows], periods, f"storage {asset}")
    # P0-4 S4 storage energy audit (accounting via tests/golden/zones.json).
    audit_by_asset: dict[str, list[dict[str, Any]]] = {}
    for row in ledger.storage_audit:
        audit_by_asset.setdefault(str(row["asset_id"]), []).append(row)
    for asset, rows in audit_by_asset.items():
        for field in rows[0]:
            if field in ("year", "period", "asset_id"):
                continue
            columns[f"market/market.sqlite::storage_energy_audit.{asset}.{field}"] = _per_period(
                [canonical(row[field]) for row in rows], periods, f"storage audit {asset}")
    # P0-4 S5 surplus routing: per source class, one value per period (0 when
    # the class had no surplus in that period).
    routing_fields = [field for field in (ledger.surplus_routing[0] if ledger.surplus_routing else {})
                      if field not in ("year", "period", "source_class")]
    for source_class in ("in_dispatch", "out_of_dispatch"):
        by_period = {int(row["period"]): row for row in ledger.surplus_routing if row["source_class"] == source_class}
        for field in routing_fields:
            columns[f"market/market.sqlite::surplus_routing.{source_class}.{field}"] = [
                canonical(by_period[period][field]) if period in by_period else 0.0 for period in range(periods)
            ]
    if len(ledger.orders) != periods:
        raise AssertionError(f"ledger recorded orders for {len(ledger.orders)} periods")
    columns["market/market.sqlite::orders.#rows"] = [len(rows) for rows in ledger.orders]
    # Bid and acceptance fields (trajectory) and cost/settlement fields
    # (accounting, P5-06) are hashed separately so an accounting correction
    # never moves a trajectory column.
    for name, fields in (("trajectory_row_sha", ORDER_TRAJECTORY_FIELDS), ("accounting_row_sha", ORDER_ACCOUNTING_FIELDS)):
        columns[f"market/market.sqlite::orders.{name}"] = [
            _short(json.dumps([{field: canonical(row[field]) for field in fields} for row in rows], sort_keys=True))
            for rows in ledger.orders
        ]
    for rows in ledger.orders:
        for row in rows:
            unknown = set(row) - set(ORDER_TRAJECTORY_FIELDS) - set(ORDER_ACCOUNTING_FIELDS)
            if unknown:
                raise AssertionError(f"OrderLedgerRow has unclassified fields {sorted(unknown)}")
    for stage in ("ahead", "curtailment", "balancing"):
        inputs = [row for row in ledger.declared if row["kind"] == "input" and row["stage"] == stage]
        by_input = {row["input_sha256"]: row for row in ledger.declared if row["kind"] == "outcome"}
        columns[f"kernel/declared::{stage}.periods"] = [row["period"] for row in inputs]
        columns[f"kernel/declared::{stage}.input_payload_sha"] = [row["payload"] for row in inputs]
        columns[f"kernel/declared::{stage}.outcome_payload_sha"] = [
            by_input[row["input_sha256"]]["payload"] if row["input_sha256"] in by_input else None
            for row in inputs
        ]
        if stage != "curtailment":
            columns[f"kernel/declared::{stage}.unserved_target_mw"] = [
                by_input[row["input_sha256"]]["unserved_target_mw"] if row["input_sha256"] in by_input else None
                for row in inputs
            ]
            columns[f"kernel/declared::{stage}.storage_accepted_mw"] = [
                by_input[row["input_sha256"]]["storage_accepted_mw"] if row["input_sha256"] in by_input else None
                for row in inputs
            ]

    # Final physical composition per asset (result_list, HEAD 2803-2813).
    composition = _per_period(raw["gen_list_composition"], periods, "gen_list_composition")
    assets = []
    for rows in composition:
        for asset, _ in rows:
            name = canonical(asset)
            if name not in assets:
                assets.append(name)
    for name in assets:
        columns[f"kernel/dispatch::{name}"] = [
            sum(float(energy) for asset, energy in rows if canonical(asset) == name) for rows in composition
        ]
    # Order of the final composition (first-dispatch order) as a per-period hash.
    columns["kernel/dispatch::composition_order_sha"] = [
        _short(json.dumps([canonical(asset) for asset, _ in rows])) for rows in composition
    ]

    per_period_series = (
        "avg_electricity_prices", "storage_fees", "store_electricity", "generation_costs",
        "avg_gen_fees", "avg_curtailment_fees", "avg_balancing_fees", "avg_storage_fees",
        "ahead_renewables", "ahead_other", "ahead_traditional", "ahead_nuclear",
        "balance_renewables", "balance_other", "balance_traditional", "balance_nuclear",
        "curtailed_electricity", "excess_electricity", "total_annual_cost", "total_annual_demand",
        "carbon_emission", "sold_fees", "purchase_fees", "total_green_hy", "total_annual_energycell",
        "flexible_demand_list", "interconnector_exports_list", "blackout_periods",
    )
    for name in per_period_series:
        series = raw[name]
        if name in {"avg_gen_fees", "avg_curtailment_fees", "avg_balancing_fees", "avg_storage_fees"}:
            columns[f"kernel/run_simulation::{name}"] = canonical(list(series))
        else:
            columns[f"kernel/run_simulation::{name}"] = _per_period(canonical(list(series)), periods, name)
    # Plot-only storage composition helpers: exact per-period hashes keep the
    # fixture small; their physical content is in the storage_state columns.
    for name in ("storage_pools_composition", "usage_storage_pool_composition"):
        columns[f"kernel/run_simulation::{name}.sha"] = [
            _short(json.dumps(canonical(rows))) for rows in raw[name]
        ]
    columns["kernel/run_simulation::storage_pool.#entries"] = len(raw["storage_pool"])
    columns["kernel/run_simulation::total_storage_pool.#entries"] = len(raw["total_storage_pool"])
    columns["kernel/run_simulation::traditional_gen"] = canonical(raw["traditional_gen"])
    columns["kernel/run_simulation::total_renew_capacity"] = canonical(raw["total_renew_capacity"])
    columns["kernel/run_simulation::renew_capacity"] = canonical(raw["renew_capacity"])
    columns["kernel/run_simulation::total_income_dict"] = canonical(raw["total_income_dict"])
    for name in ("excess_energy_dict", "excess_energy_final_dict", "curtailed_energy_dict"):
        mapping = raw[name]
        columns[f"kernel/run_simulation::{name}"] = [canonical(mapping.get(period)) for period in range(periods)]
    # Pre-clearing electrolysis skim [generator, cost, hydrogen]; the skimmed
    # power itself is in the kernel/state::<vre>.real_energy columns.
    columns["kernel/run_simulation::renewable_hy_dict.sha"] = [
        _short(json.dumps(canonical(raw["renewable_hy_dict"].get(period)))) for period in range(periods)
    ]

    snapshots = result["snapshots"]
    if len(snapshots) != periods:
        raise AssertionError(f"driver captured {len(snapshots)} end-of-period states")
    for asset in snapshots[0]:
        for attribute in snapshots[0][asset]:
            columns[f"kernel/state::{asset}.{attribute}"] = [
                canonical(snapshot[asset].get(attribute)) for snapshot in snapshots
            ]
    columns["kernel/storage_cost_report"] = canonical(result["storage_reports"])
    return columns


# ---------------------------------------------------------------------------
# Zones, comparison and revisions
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _zones_json() -> ZoneRules:
    return ZoneRules.load(ZONES_PATH)


def zone_of(key: str) -> str:
    """Zone of a golden key: harness-local rules, then tests/golden/zones.json."""

    for pattern, zone, _ in LOCAL_ZONE_RULES:
        if fnmatch.fnmatchcase(key, pattern):
            return zone
    return _zones_json().zone(key)


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, float) and isinstance(actual, float):
        if math.isnan(expected) and math.isnan(actual):
            return True
        return expected == actual and math.copysign(1.0, expected) == math.copysign(1.0, actual)
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return type(expected) is type(actual) and expected == actual
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(_same(a, b) for a, b in zip(expected, actual))
    if isinstance(expected, dict) and isinstance(actual, dict):
        return list(expected) == list(actual) and all(_same(expected[k], actual[k]) for k in expected)
    return type(expected) is type(actual) and expected == actual


def _first_difference(expected: Any, actual: Any, path: str = "") -> tuple[str, Any, Any] | None:
    if _same(expected, actual):
        return None
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        for index, (left, right) in enumerate(zip(expected, actual)):
            found = _first_difference(left, right, f"{path}[{index}]")
            if found:
                return found
    if isinstance(expected, dict) and isinstance(actual, dict) and list(expected) == list(actual):
        for key in expected:
            found = _first_difference(expected[key], actual[key], f"{path}.{key}")
            if found:
                return found
    return path or "<value>", expected, actual


@dataclasses.dataclass(frozen=True)
class ColumnDifference:
    case: str
    key: str
    zone: str
    kind: str  # changed | added | removed
    where: str = ""
    expected: Any = None
    actual: Any = None

    def describe(self) -> str:
        if self.kind == "changed":
            return f"[{self.zone}] {self.case} {self.key}{self.where}: expected {self.expected!r}, got {self.actual!r}"
        return f"[{self.zone}] {self.case} {self.key}: column {self.kind}"


def compare_columns(case: str, expected: Mapping[str, Any], actual: Mapping[str, Any], pinned: Mapping[str, str]) -> list[ColumnDifference]:
    differences = []
    for key in expected:
        zone = pinned.get(key, zone_of(key))
        if key not in actual:
            differences.append(ColumnDifference(case, key, zone, "removed"))
            continue
        found = _first_difference(expected[key], actual[key])
        if found:
            where, left, right = found
            differences.append(ColumnDifference(case, key, zone, "changed", where if where != "<value>" else "", left, right))
    for key in actual:
        if key not in expected:
            differences.append(ColumnDifference(case, key, zone_of(key), "added"))
    return differences


def load_golden(path: Path = GOLDEN_PATH) -> dict[str, Any]:
    golden = json.loads(path.read_text(encoding="utf-8"))
    if golden.get("schema_version") != GOLDEN_SCHEMA:
        raise ValueError(f"{path}: unexpected schema {golden.get('schema_version')!r}")
    return golden


def latest_columns(golden: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Revision 0 columns with every later revision's patch applied in order."""

    cases = {case: dict(payload["columns"]) for case, payload in golden["cases"].items()}
    for revision in golden.get("revisions", [])[1:]:
        for case, patch in revision.get("patch", {}).items():
            for key, value in patch.items():
                if value is None:
                    cases[case].pop(key, None)
                else:
                    cases[case][key] = value
    return cases


def pinned_zones(golden: Mapping[str, Any]) -> dict[str, str]:
    zones = dict(golden.get("zones", {}))
    for revision in golden.get("revisions", [])[1:]:
        for key, zone in revision.get("zones", {}).items():
            previous = zones.get(key)
            if previous is None or ZONE_STRENGTH[zone] >= ZONE_STRENGTH[previous]:
                zones[key] = zone
    return zones


def observe(variants: Iterable[str] = VARIANTS, *, loop=None,
            runtime_attributes: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    scenario = build_scenario()
    function, _ = resolve_loop(loop)
    return {
        variant: columns_from_run(run_case(variant, scenario, loop=function, runtime_attributes=runtime_attributes))
        for variant in variants
    }


def compare_with_golden(golden: Mapping[str, Any], observed: Mapping[str, Mapping[str, Any]]) -> list[ColumnDifference]:
    expected = latest_columns(golden)
    zones = pinned_zones(golden)
    differences: list[ColumnDifference] = []
    for case in expected:
        if case not in observed:
            differences.append(ColumnDifference(case, "<case>", "trajectory", "removed"))
            continue
        differences.extend(compare_columns(case, expected[case], observed[case], zones))
    for case in observed:
        if case not in expected:
            differences.append(ColumnDifference(case, "<case>", "trajectory", "added"))
    return differences


def gated_zones(golden: Mapping[str, Any], loop: str) -> tuple[str, ...]:
    """Zones in which a difference from the latest golden revision fails a check.

    The live loop carries the current ledger boundary and is gated in the
    trajectory and accounting zones.  The frozen loop keeps the 35aadb3 ledger
    boundary (2857-3002), so its accounting columns are HEAD-boundary values:
    they are gated only while the golden has no accounting revision; after one,
    the frozen loop is gated in the trajectory zone only and its accounting
    differences are informational (the live loop gates them).
    """

    if loop == "live":
        return ("trajectory", "accounting")
    if loop == "frozen":
        return ("trajectory", "accounting") if len(golden.get("revisions", [])) <= 1 else ("trajectory",)
    raise ValueError(f"unknown loop {loop!r}")


def new_golden(observed: Mapping[str, Mapping[str, Any]], *, base_commit: str, source: Mapping[str, Any]) -> dict[str, Any]:
    scenario = build_scenario()
    zones: dict[str, str] = {}
    for columns in observed.values():
        for key in columns:
            zones[key] = zone_of(key)
    return {
        "schema_version": GOLDEN_SCHEMA,
        "id": "doctoral_reproduction_golden_v1",
        "notes": [
            "P0-6 S1: 96-period synthetic golden of the default PSM loop, captured at HEAD with the frozen verbatim 35aadb3 loop (tests/fixtures/native_psm/head_run_simulation_35aadb3.py) and the live market functions.",
            "Values are exact doubles. Zones follow decision Q12 (tests/golden/zones.json plus harness-local rules in tests/native_reproduction_harness.py); the trajectory zone of this doctoral golden is frozen, accounting columns change only through an appended revision with a universal correction id (capture script 'revise').",
            "Revision 0 is written once; it is never rewritten. At capture the frozen loop and the live loop (render_live_loop of the HEAD kernel) are byte-identical and give identical columns.",
            "Accounting revisions are captured through the live loop: the frozen loop keeps the 35aadb3 ledger boundary, so its accounting columns stay HEAD-boundary values (gated_zones).",
        ],
        "source": dict(source),
        "scenario_sha256": sha256_text(json.dumps(scenario, sort_keys=True)),
        "scenario": scenario,
        "variants": {
            "dynamic": "dynamic-annual-storage-cost (default PSM storage module)",
            "legacy_tariff": "value-legacy-storage-tariff (doctoral reference configuration, decision Q3)",
        },
        "loop_environment": dict(LOOP_ENVIRONMENT),
        "zones": zones,
        "cases": {case: {"columns": dict(columns)} for case, columns in observed.items()},
        "revisions": [{"index": 0, "base_commit": base_commit, "reason": "P0-6 S1 HEAD capture", "correction_ids": [],
                       "loop": "frozen (identical to live at capture)"}],
    }


def append_revision(golden: dict[str, Any], observed: Mapping[str, Mapping[str, Any]], *, reason: str,
                    correction_ids: Sequence[str], base_commit: str, loop: str = "live") -> dict[str, Any]:
    """Append an accounting-only revision; trajectory changes are refused.

    ``observed`` must come from the live loop (or a replacement driver of the
    current kernel, recorded as ``loop``); the frozen loop cannot carry a
    correction of the ledger boundary.
    """

    import re

    if loop == "frozen":
        raise ValueError("revisions are captured through the live loop; the frozen loop keeps the 35aadb3 ledger boundary")

    if not correction_ids or not all(re.match(CORRECTION_ID_PATTERN, item) for item in correction_ids):
        raise ValueError("a revision needs at least one correction id matching " + CORRECTION_ID_PATTERN)
    if not reason.strip():
        raise ValueError("a revision needs a reason")
    differences = compare_with_golden(golden, observed)
    if not differences:
        raise ValueError("no differences: nothing to revise")
    frozen = [item for item in differences if item.zone == "trajectory"]
    if frozen:
        raise ValueError(
            "doctoral trajectory columns are frozen (decision Q1/Q12); synthetic inputs bypass the data readers, "
            "so no approved universal correction can change them:\n  "
            + "\n  ".join(item.describe() for item in frozen[:20])
        )
    if any(item.key == "<case>" for item in differences):
        raise ValueError("cases cannot be added or removed by a revision")
    patch: dict[str, dict[str, Any]] = {}
    zones: dict[str, str] = {}
    for item in differences:
        patch.setdefault(item.case, {})[item.key] = None if item.kind == "removed" else observed[item.case][item.key]
        if item.kind == "added":
            zones[item.key] = item.zone
    revision: dict[str, Any] = {
        "index": len(golden["revisions"]),
        "base_commit": base_commit,
        "reason": reason,
        "correction_ids": list(correction_ids),
        "loop": loop,
        "delta": sorted({f"{item.case}:{item.key}:{item.kind}" for item in differences}),
        "zones": zones,
        "patch": patch,
    }
    size = revision_bytes(revision)
    if size > APPENDED_REVISION_BUDGET_BYTES:
        raise ValueError(
            f"revision {revision['index']} is {size} bytes, above the appended-revision budget of "
            f"{APPENDED_REVISION_BUDGET_BYTES} bytes (APPENDED_REVISION_BUDGET_BYTES)"
        )
    revised = copy.deepcopy(golden)
    revised["revisions"].append(revision)
    return revised


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _dump_columns(columns: Mapping[str, Any], indent: str) -> list[str]:
    keys = list(columns)
    return [f"{indent}{_dumps(key)}: {_dumps(columns[key])}{',' if index < len(keys) - 1 else ''}"
            for index, key in enumerate(keys)]


def _dump_revision(revision: Mapping[str, Any], comma: str) -> list[str]:
    """One revision: metadata one key per line, ``delta`` one entry per line
    and ``patch`` one column per line (as in ``cases``)."""

    if "patch" not in revision and "delta" not in revision:
        return [f"  {json.dumps(revision, ensure_ascii=False)}{comma}"]
    lines = ["  {"]
    keys = list(revision)
    for index, key in enumerate(keys):
        key_comma = "," if index < len(keys) - 1 else ""
        value = revision[key]
        if key == "patch" and isinstance(value, Mapping):
            lines.append(f"   {_dumps(key)}: {{")
            cases = list(value)
            for case_index, case in enumerate(cases):
                lines.append(f"    {_dumps(case)}: {{")
                lines.extend(_dump_columns(value[case], "     "))
                lines.append("    }" + ("," if case_index < len(cases) - 1 else ""))
            lines.append("   }" + key_comma)
        elif key == "delta" and isinstance(value, list) and value:
            lines.append(f"   {_dumps(key)}: [")
            lines.extend(f"    {_dumps(item)}{',' if item_index < len(value) - 1 else ''}"
                         for item_index, item in enumerate(value))
            lines.append("   ]" + key_comma)
        else:
            lines.append(f"   {_dumps(key)}: {json.dumps(value, ensure_ascii=False)}{key_comma}")
    lines.append("  }" + comma)
    return lines


def dump_golden(golden: Mapping[str, Any]) -> str:
    """Stable text: one column per line (in ``cases`` and in every revision
    ``patch``) so reviews show the changed columns."""

    lines = ["{"]
    keys = list(golden)
    for index, key in enumerate(keys):
        comma = "," if index < len(keys) - 1 else ""
        value = golden[key]
        if key == "cases":
            lines.append(' "cases": {')
            case_names = list(value)
            for case_index, case in enumerate(case_names):
                lines.append(f'  {_dumps(case)}: {{"columns": {{')
                lines.extend(_dump_columns(value[case]["columns"], "   "))
                case_comma = "," if case_index < len(case_names) - 1 else ""
                lines.append(f"  }}}}{case_comma}")
            lines.append(f" }}{comma}")
        elif key == "revisions":
            lines.append(' "revisions": [')
            for revision_index, revision in enumerate(value):
                lines.extend(_dump_revision(revision, "," if revision_index < len(value) - 1 else ""))
            lines.append(f" ]{comma}")
        else:
            lines.append(f" {_dumps(key)}: {json.dumps(value, ensure_ascii=False, sort_keys=False)}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def revision_zero_bytes(golden: Mapping[str, Any]) -> int:
    """Size of the golden as captured (scenario, cases, revision 0 only)."""

    base = dict(golden)
    base["revisions"] = list(golden["revisions"][:1])
    return len(dump_golden(base).encode("utf-8"))


def revision_bytes(revision: Mapping[str, Any]) -> int:
    """Size of one appended revision as :func:`dump_golden` writes it."""

    return len("\n".join(_dump_revision(revision, ",")).encode("utf-8"))


# ---------------------------------------------------------------------------
# Coverage facts used by the tests (documenting what the scenario exercises)
# ---------------------------------------------------------------------------


def coverage_facts(columns: Mapping[str, Any], scenario: Mapping[str, Any] | None = None) -> dict[str, list[int]]:
    """Periods in which each HEAD behaviour named by plan 4.6 S1 occurs."""

    scenario = scenario or build_scenario()
    periods = int(scenario["periods"])
    forecast = scenario["forecast_mw"]
    real = scenario["real_mw"]
    summary = "market/market.sqlite::period_summary."
    excess_lists = columns["kernel/run_simulation::excess_energy_dict"]
    blackout = columns["kernel/run_simulation::blackout_periods"]
    curtailed = columns["kernel/run_simulation::curtailed_electricity"]
    sold = columns["kernel/run_simulation::interconnector_exports_list"]
    nuclear = columns.get("kernel/dispatch::<NuclearGenerator:Nuclear>", [0.0] * periods)
    vre_dispatch = [
        sum(columns.get(f"kernel/dispatch::<ExpensiverenewableGenerator:{name}>", [0.0] * periods)[p] for name in VRE_NAMES)
        for p in range(periods)
    ]
    vre_available = [sum(scenario["vre_availability_mw"][name][p] for name in VRE_NAMES) for p in range(periods)]
    curtailment_branch = [p for p in range(periods) if real[p] < forecast[p]]
    balancing_branch = [p for p in range(periods) if real[p] >= forecast[p]]
    ahead_unserved = dict(zip(columns["kernel/declared::ahead.periods"], columns["kernel/declared::ahead.unserved_target_mw"]))
    ahead_storage = dict(zip(columns["kernel/declared::ahead.periods"], columns["kernel/declared::ahead.storage_accepted_mw"]))
    balancing_storage = dict(zip(columns["kernel/declared::balancing.periods"], columns["kernel/declared::balancing.storage_accepted_mw"]))
    storage_fees = columns["kernel/run_simulation::storage_fees"]
    electrolyser_vre = [
        item["args"]["name"] for item in scenario["fleet"]["generators"]
        if item["args"]["name"] in VRE_NAMES and float(item["args"].get("electrolyzer_limit", 0)) > 0
    ]
    batteries = [item["name"] for item in scenario["fleet"]["batteries"]]

    def nuclear_excess(p: int) -> bool:
        value = excess_lists[p]
        return isinstance(value, list) and any(str(item[0]).startswith("<NuclearGenerator") for item in value)

    def ahead_excess(p: int, *, non_vre: bool = False) -> float:
        # Surplus carried from the ahead stage (excess_energy_dict amounts).
        value = excess_lists[p]
        if not isinstance(value, list):
            return 0.0
        return sum(
            float(item[1]) for item in value
            if not non_vre or not str(item[0]).startswith("<ExpensiverenewableGenerator")
        )

    connections = [item["name"] for item in scenario["fleet"]["connections"]]

    def stale_export(p: int) -> bool:
        # HEAD curtailment path (modular_simulation_model.py ~955-1070): with
        # a non-empty soldable list only connections with transfer < 0 get
        # sold_energy assigned or reset, so a connection with transfer >= 0
        # keeps the previous period's sold_energy (a phantom export).
        return any(
            float(scenario["interconnectors"][name]["transfer_constraint_mw"][p]) >= 0.0
            and float(columns[f"kernel/state::{name}.sold_energy"][p]) > 0.0
            for name in connections
        )

    def carried_storage_fee(p: int) -> bool:
        # Observed carry (HEAD 2274/2768/2815): a curtailment-branch period
        # whose ahead stage accepted no storage still books a storage fee, and
        # the last balancing period before it accepted storage.
        previous = [b for b in balancing_branch if b < p]
        return (
            bool(previous) and (balancing_storage.get(previous[-1]) or 0.0) > 0.0
            and (ahead_storage.get(p) or 0.0) == 0.0 and storage_fees[p] > 0.0
        )

    def named_total(value: Any, name: str) -> float:
        if not isinstance(value, list):
            return 0.0
        label = f"<ExpensiverenewableGenerator:{name}>"
        return sum(float(item[1]) for item in value if isinstance(item, list) and item and item[0] == label)

    def skim_leak(p: int) -> bool:
        # Observed HEAD 1173 leak: the pre-clearing skim zeroed the VRE's
        # capacity before using it (real_energy == 0 although the electrolyser
        # skim is positive), and the availability is neither skimmed,
        # dispatched, curtailed nor recorded as surplus.
        for name in electrolyser_vre:
            available = float(scenario["vre_availability_mw"][name][p])
            skim = float(columns[f"kernel/state::{name}.real_energy"][p])
            dispatched = columns.get(f"kernel/dispatch::<ExpensiverenewableGenerator:{name}>", [0.0] * periods)[p]
            curtailed_vre = named_total(columns["kernel/run_simulation::curtailed_energy_dict"][p], name)
            surplus = named_total(columns["kernel/run_simulation::excess_energy_dict"][p], name)
            if available > 0 and skim == 0.0 and available - skim - dispatched - curtailed_vre - surplus > 0:
                return True
        return False

    def discharge_above_rating(p: int) -> bool:
        # P5-03: per-stage power reset lets one period discharge above rating.
        prefix = "market/market.sqlite::storage_state."
        return any(
            columns[f"{prefix}{name}.discharge_mwh"][p] / PERIOD_HOURS
            > columns[f"{prefix}{name}.power_capacity_mw"][p] + 1e-9
            for name in batteries
        )

    return {
        "curtailment_branch": curtailment_branch,
        "balancing_branch": balancing_branch,
        "nuclear_dispatched": [p for p in range(periods) if nuclear[p] > 0],
        "nuclear_surplus": [p for p in range(periods) if nuclear_excess(p)],
        "nuclear_blocking_vre_unrecorded": [
            p for p in range(periods) if nuclear_excess(p) and vre_available[p] > 0 and vre_dispatch[p] == 0.0
        ],
        "nuclear_surplus_in_balancing": [p for p in balancing_branch if nuclear_excess(p) and real[p] > forecast[p]],
        "export_consumes_surplus": [p for p in curtailment_branch if sold[p] > 0 and ahead_excess(p) > 0],
        "non_vre_surplus_exported": [
            p for p in curtailment_branch if nuclear_excess(p) and ahead_excess(p, non_vre=True) > 0 and sold[p] > 0
        ],
        "stale_export_carry": [p for p in range(periods) if stale_export(p)],
        "forecast_above_ahead_supply": [p for p in range(periods) if (ahead_unserved.get(p) or 0.0) > 0],
        "hidden_shortage_in_curtailment_branch": [
            p for p in curtailment_branch if (ahead_unserved.get(p) or 0.0) > 0 and blackout[p] == 0
        ],
        "p3_01_toy_f120_r28": [p for p in range(periods) if forecast[p] == 120.0 and real[p] == 28.0],
        "balancing_deficit": [p for p in range(periods) if blackout[p] > 0],
        "storage_charge": [p for p in range(periods) if columns[summary + "storage_charge_mwh"][p] > 0],
        "storage_discharge": [p for p in range(periods) if columns[summary + "storage_discharge_mwh"][p] > 0],
        "balancing_storage_discharge": [p for p, value in balancing_storage.items() if (value or 0.0) > 0],
        "storage_fee_carry_into_curtailment": [p for p in curtailment_branch if carried_storage_fee(p)],
        "thermal_down_regulation": [p for p in curtailment_branch if curtailed[p] > 0 and vre_available[p] == 0.0],
        "imports": [p for p in range(periods) if columns[summary + "import_mwh"][p] > 0],
        "electrolysis": [p for p in range(periods) if columns["kernel/run_simulation::flexible_demand_list"][p] > 0],
        "vre_skim_leak": [p for p in range(periods) if skim_leak(p)],
        "storage_discharge_above_rated_power": [p for p in range(periods) if discharge_above_rating(p)],
        "compatibility_adjustment": [p for p in range(periods) if columns[summary + "compatibility_adjustment_mwh"][p] != 0.0],
    }
