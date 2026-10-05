"""Capture and check the P0-5 S0 data-reading baseline (plan 4.5, step S0).

Commands::

    capture_p0_5_baseline.py capture --pack DIR [--pack DIR ...] [--output F] [--coverage-output F]
    capture_p0_5_baseline.py check   [--pack DIR ...]
    capture_p0_5_baseline.py show    --pack DIR            # print one pack capture (no file written)

The baseline records how the code *as of this capture* reads the series of a
data pack, at the three reader sites that P0-5 later replaces with one shared
declarative reader:

* the canonical adapter (``canonical_psm_data._series``/``_clock`` and the
  complete ``build_chronology`` output for a state holding every
  representative VRE site at 1 MW, in the default and the doctoral-national
  alignment);
* the data-pack validator (``data_pack_validation._first_numeric_column``);
* the retained kernel's input block (``runtime_compat/modular_simulation_model
  .run_simulation`` lines reading ``config.file_paths`` and wrapping the ten
  interconnector series in ``IterLimit_new``, plus the demand reads in
  ``scheme_c_native_psm``), twice:

  - ``kernel_boundary_oracle`` reproduces the block with the kernel's own
    ``IterLimit_new`` class and the kernel's own pandas calls (full year and
    48 periods, no dispatch);
  - ``kernel_recorded`` runs the real kernel (the frozen golden D3 project,
    ``value_101_day``, 48 periods, pointed at the pack) and records, through
    ``tests.p0_5_fixtures.KernelBoundaryRecorder`` (a monkeypatch of
    ``ahead_market_bidding``), what the input block handed to the market in
    every period: connection limits and prices, forecast and real demand, and
    the per-unit VRE limit of every site.  ``tests/test_p0_5_baseline.py``
    also proves oracle == real kernel on a non-constant toy pack.

Nothing here changes behaviour.  Series are identified by hashes, not stored.
Packs are keyed by a label.  The research packs are the released public1
revisions, identified by the sha256 of their manifest (= ``manifest.json`` in
the release zip listed in ``docs/release/public-data-assets.json``); they are
not in the repository and are checked only when their directory is supplied
(``--pack`` or the ``VALUE_P0_5_PACKS`` environment variable, ``os.pathsep``
separated).  The teaching packs under ``data-packs/`` are always checked.

``expected_change`` in the baseline lists, per DECISIONS (docs/dev/P0_DECISIONS.md),
which recorded entries later P0-5 steps are expected to change and under
which methodology profile.  A later step that changes an entry not listed
there must stop and explain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SCHEMA_VERSION = "value.p0-5-reading-baseline/v1"
COVERAGE_SCHEMA_VERSION = "value.p0-5-declaration-coverage/v1"
BASELINE_PATH = ROOT / "tests" / "golden" / "p0_5_baseline.json"
COVERAGE_PATH = ROOT / "tests" / "golden" / "p0_5_declaration_coverage.json"
PACKS_ENVIRONMENT = "VALUE_P0_5_PACKS"
REPOSITORY_PACKS = ("data-packs/value-101-baseline-v1", "data-packs/value-101-network-v1")
# The released public1 research packs (docs/release/public-data-assets.json).
# The release keeps the original pack ids, so the label, not the id, names the
# revision; the manifest sha256 identifies it.
RESEARCH_PACKS = {
    "gbp1-public1": {
        "pack_id": "value-uk-open-data-pack-v1",
        "manifest_sha256": "17a68154c26680d472879fbe6a2f67eb3c610d5de68052b1b0101384a3270025",
        "release_asset": "value-uk-open-data-pack-v1-public1-2026-10-04.zip",
        "release_asset_sha256": "0b21f21b9e9fef74343f0e0d0ad5818931012eae43c2d61acc2dae678e9fedd2",
    },
    "r029-public1": {
        "pack_id": "value-uk-calendar-vx-trade001",
        "manifest_sha256": "717543f0ea6c7601f7c5d11b743d1c4924db5296f4b57fed063fa63be51adee8",
        "release_asset": "value-uk-calendar-vx-trade001-public1-2026-10-04.zip",
        "release_asset_sha256": "cdab4222b6030b377499e5060e2d03b6a7c704c0ddf0d6cc2ea73dee202b2f04",
    },
}
KERNEL_RECORDED_WINDOW = 48
HASH_HEX = 12  # 48-bit change detectors; the size budget of the baseline is 50 KB
PRE_P0_COMMIT = "35aadb3"
# Full year, the 168-hour and the 24-hour validation windows (P6-07 shows only
# in the short windows).
WINDOWS = (17_520, 336, 48)
KERNEL_WINDOWS = (17_520, 48)
PERIOD_HOURS = 0.5
COUNTRIES = ("france", "belgium", "netherlands", "norway", "ireland")
SERIES_ROLES = (
    "demand.real",
    "demand.forecast",
    "profiles.vre_solar",
    "profiles.vre_onshore",
    "profiles.vre_offshore",
    *(f"market.{country}.{kind}" for country in COUNTRIES for kind in ("profile", "price")),
)
VRE = ("solar", "onshore", "offshore")
# ``header=`` passed by build_chronology for each role (canonical_psm_data.py:983-1186).
HEAD_CANONICAL_HEADER: dict[str, int | None] = {
    "demand.real": 0,
    "demand.forecast": 0,
    "profiles.vre_solar": None,
    "profiles.vre_onshore": None,
    "profiles.vre_offshore": None,
    **{f"market.{country}.profile": 0 for country in COUNTRIES},
    **{f"market.{country}.price": None for country in COUNTRIES},
}
HEAD_CANONICAL_HOURLY_REPEAT = frozenset({"profiles.vre_solar", "profiles.vre_onshore", "profiles.vre_offshore"})
# run_simulation assigns data1..data10 (france, belgium, netherlands, norway,
# ireland profile/price files, in that order) to the connections in this order
# (modular_simulation_model.py:2581-2590 and 2675-2684): Netherland receives
# the Belgium files, Ireland the Netherlands files, Belgium the Ireland files.
HEAD_KERNEL_CONNECTION_FEEDS = {
    "Interconnect_France": "france",
    "Interconnect_Netherland": "belgium",
    "Interconnect_Ireland": "netherlands",
    "Interconnect_Norway": "norway",
    "Interconnect_Beligum": "ireland",
}
# Declarations P0-5 S1 (plan 4.5, scheme 1) will read; recorded per binding.
DECLARATION_KEYS = (
    "csv_header",
    "csv_column",
    "timestamp_column",
    "unit",
    "currency",
    "eur_per_gbp",
    "fx_basis",
    "interval_minutes",
    "source_periods",
    "source_start_utc",
    "cyclic",
    "leap_policy",
    "chronology_contract",
    "time_convention",
    "flow_sign",
    "country",
    "input_unit_contract",
)
PACK_DECLARATION_KEYS = ("timezone", "country", "pack_class", "teaching_only", "periods_per_year", "period_hours")
# The reader sites whose consumption of each declaration is recorded.
READER_SOURCES = {
    "canonical_adapter": "gridform_core/canonical_psm_data.py",
    "validator": "gridform_core/data_pack_validation.py",
    "kernel_input_block": "gridform_core/builtin/scheme_c_1000twh/runtime_compat/modular_simulation_model.py",
    "kernel_demand_read": "gridform_core/builtin/scheme_c_1000twh/scheme_c_native_psm.py",
    "doctoral_weather": "gridform_core/doctoral_weather.py",
}
HASH_RULE = {
    "numeric": "sha256 of numpy.asarray(values, dtype='<f8').tobytes(), first 12 hex digits",
    "object": "'obj:' + first 12 hex digits of sha256 of '\\x1f'.join(repr(value) for value in values) (values the kernel receives as Python objects, e.g. strings)",
    "manifest": "full sha256 of manifest.json (the manifest carries the sha256 of every bound file; capture verifies each read file against it)",
    "summaries": "canonical_reader: cols = CSV columns pandas saw, col/label = the column _series picked and its header (or first cell when header=None), index_like = step-1 integer sequence; n/min/max/mean of the values (rounded to 6 decimals). validator_reader: [column, values, invalid cells, hash or '=canonical' when equal to canonical_reader.sha]",
}
# Entries the later P0-5 steps are expected to change (DECISIONS overrides the
# plan: Q1 strict freeze, Q9/A3 interconnector clock universal, A5 GBP1
# reading bugs universal, A1/Q15 VRE losses corrected-only).
BOTH = ["doctoral-lineage-0.6.0a2", "value-corrected"]
CORRECTED = ["value-corrected"]
EXPECTED_CHANGE = [
    {
        "finding": "P6-01", "decision": "plan 4.5 dual-track: universal software fix (a declared csv_column is read)",
        "profiles": BOTH, "packs": ["r029-public1"],
        "entries": ["canonical_reader.market.*", "validator_reader.market.*", "canonical_clock.*.market.*",
                    "chronology.*.*.imports", "chronology.*.*.exports", "kernel_boundary_oracle.*",
                    "kernel_recorded.*"],
        "note": "at HEAD the kernel stops with a TypeError on R029 (kernel_recorded records it); after the fix it runs",
    },
    {
        "finding": "P6-07", "decision": "Q1: profile-gated; doctoral keeps the hourly-repeat clock",
        "profiles": CORRECTED, "packs": ["value-101-baseline-v1", "value-101-network-v1", "gbp1-public1", "r029-public1"],
        "entries": ["canonical_clock.336.profiles.*", "canonical_clock.48.profiles.*",
                    "chronology.*.336.headroom", "chronology.*.48.headroom"],
    },
    {
        "finding": "P6-24", "decision": "Q9/A3: universal, every interconnector series period by period on the 17520 clock",
        "profiles": BOTH, "packs": ["*"],
        "entries": ["kernel_boundary_oracle.*.connections.*", "kernel_recorded.*.connections.*"],
        "note": "constant series (all ten 101 market series) cannot show the change; hashes of non-constant series must change",
    },
    {
        "finding": "P6-02", "decision": "A5: universal, Belgium hourly EUR price -> half-hourly GBP with documented FX",
        "profiles": BOTH, "packs": ["gbp1-public1"],
        "entries": ["canonical_reader.market.belgium.price", "validator_reader.market.belgium.price",
                    "canonical_clock.*.market.belgium.price", "chronology.*.*.imports.belgium",
                    "chronology.*.*.exports.belgium", "kernel_boundary_oracle.*.connections.*",
                    "kernel_recorded.*.connections.*"],
    },
    {
        "finding": "P6-03", "decision": "A5: universal, BE/NL flow files swapped (role binding by line identity)",
        "profiles": BOTH, "packs": ["gbp1-public1"],
        "entries": ["chronology.*.*.imports.belgium", "chronology.*.*.imports.netherlands",
                    "chronology.*.*.exports.belgium", "chronology.*.*.exports.netherlands",
                    "kernel_boundary_oracle.*.connections.*", "kernel_recorded.*.connections.*"],
        "note": "whether the kernel Connection mis-wiring (head_rules.kernel_connection_feeds) is fixed under A5 or only in value-corrected is decided by the S4/S5 owner and recorded there",
    },
    {
        "finding": "P6-04", "decision": "A5: universal, demand on the UTC clock after the 2022-10-30 DST change",
        "profiles": BOTH, "packs": ["gbp1-public1"],
        "entries": ["canonical_reader.demand.*", "canonical_clock.*.demand.*", "chronology.*.*.demand",
                    "chronology.*.*.forecast", "kernel_boundary_oracle.*.demand", "kernel_recorded.*.demand"],
        "note": "the 48-period window lies before 2022-10-30; only full-year entries can show the shift",
    },
    {
        "finding": "P6-05", "decision": "plan 4.5 dual-track: corrected only (doctoral frozen, A5 does not list it)",
        "profiles": CORRECTED, "packs": ["gbp1-public1"],
        "entries": ["canonical_reader.demand.forecast", "canonical_clock.*.demand.forecast",
                    "chronology.*.*.forecast", "kernel_boundary_oracle.*.demand", "kernel_recorded.*.demand"],
    },
    {
        "finding": "P6-06/P6-08", "decision": "plan S6 / A1, Q15: weather time convention and literature loss factors, corrected only",
        "profiles": CORRECTED, "packs": ["*"],
        "entries": ["chronology.*.*.vre_sites", "chronology.*.*.vre_sites_digest", "kernel_recorded.*.vre_unit_limit"],
    },
    {
        "finding": "boundary-raw-price", "decision": "plan 4.5 scheme 6 / dual-track: unclipped boundary prices in value-corrected",
        "profiles": CORRECTED, "packs": ["gbp1-public1", "r029-public1"],
        "entries": ["chronology.value.canonical.*.imports.*.price", "chronology.value.canonical.*.exports.*.price"],
    },
]


# --------------------------------------------------------------------- hashes

def digest(values: Iterable[Any]) -> str:
    array = np.asarray(list(values) if not isinstance(values, np.ndarray) else values)
    if array.dtype.kind in "biuf":
        return hashlib.sha256(np.asarray(array, dtype="<f8").tobytes()).hexdigest()[:HASH_HEX]
    text = "\x1f".join(repr(value) for value in array.tolist())
    return "obj:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:HASH_HEX]


def file_sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _round(value: float) -> float:
    return float(round(float(value), 6))


def summary(values: np.ndarray) -> dict[str, Any]:
    if values.size == 0:
        return {"n": 0}
    return {
        "n": int(values.size),
        "min": _round(np.min(values)),
        "max": _round(np.max(values)),
        "mean": _round(np.mean(values)),
    }


def _index_like(values: np.ndarray) -> bool:
    """Step-1 increasing integer sequence (the future GF_DATA_INDEX_COLUMN guard)."""

    return bool(values.size > 2 and np.all(np.diff(values) == 1.0) and float(values[0]).is_integer())


# --------------------------------------------------------------------- packs

def load_manifest(pack_root: Path) -> dict[str, Any]:
    return json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))


def binding_path(pack_root: Path, manifest: Mapping[str, Any], role: str) -> Path:
    from gridform_core.canonical_psm_data import _binding_path

    return _binding_path(pack_root.resolve(), manifest, role)


def representative_vre_assets(pack_root: Path, manifest: Mapping[str, Any]):
    from gridform_core.v2.contracts import AssetStateV2

    fleet = json.loads(binding_path(pack_root, manifest, "fleet.generators").read_text(encoding="utf-8"))
    assets = []
    for name in fleet.get("generators", {}):
        technology = next((item for item in VRE if str(name).startswith(item)), None)
        if technology:
            assets.append(AssetStateV2(str(name), technology, 1.0))
    return assets


# ------------------------------------------------------------ reader sites

def canonical_reader(path: Path, role: str) -> dict[str, Any]:
    """What ``canonical_psm_data._series`` returns for this role, and which column it picked."""

    from gridform_core.canonical_psm_data import _series

    header = HEAD_CANONICAL_HEADER[role]
    try:
        values = _series(path, header=header)
    except Exception as error:  # noqa: BLE001 - the failure itself is HEAD behaviour
        return {"error": f"{type(error).__name__}: {error}"}
    frame = pd.read_csv(path, header=header)
    selected, label = None, None
    for index in range(frame.shape[1]):
        column = pd.to_numeric(frame.iloc[:, index], errors="coerce").dropna().to_numpy(dtype=float)
        if column.shape == values.shape and np.array_equal(column, values):
            selected = index
            label = str(frame.columns[index]) if header is not None else str(frame.iloc[0, index])
            break
    return {
        "cols": int(frame.shape[1]),
        "col": selected,
        "label": label,
        "index_like": _index_like(values),
        "sha": digest(values),
        **summary(values),
    }


def validator_reader(path: Path) -> list[Any]:
    """``[selected column, values, invalid cells, hash]`` of ``_first_numeric_column``."""

    from gridform_core.data_pack_validation import _first_numeric_column, _csv_text
    import csv
    import io

    values, invalid = _first_numeric_column(path)
    array = np.asarray(values, dtype=float)
    rows = list(csv.reader(io.StringIO(_csv_text(path)[0])))
    width = max((len(row) for row in rows), default=0)
    selected = None
    for column in range(width):
        candidate = []
        for row_number, row in enumerate(rows):
            raw = row[column].strip() if column < len(row) else ""
            try:
                candidate.append(float(raw))
            except ValueError:
                continue
        if candidate == values:
            selected = column
            break
    return [selected, int(array.size), int(invalid), digest(array)]


def canonical_clock(path: Path, role: str, periods: int) -> list[Any]:
    """``[rule, sha]`` of ``_clock(_series(...), periods)`` as build_chronology calls it."""

    from gridform_core.canonical_psm_data import _clock, _series

    try:
        values = _series(path, header=HEAD_CANONICAL_HEADER[role])
        clocked = _clock(values, periods, hourly_repeat=role in HEAD_CANONICAL_HOURLY_REPEAT)
    except Exception as error:  # noqa: BLE001
        return ["error", f"{type(error).__name__}: {error}"]
    # The branch _clock takes, in its own order; then confirmed on the output.
    hourly = role in HEAD_CANONICAL_HOURLY_REPEAT
    if values.size == periods:
        rule, candidate = "exact", values
    elif hourly and values.size * 2 >= periods:
        rule, candidate = "hourly_repeat", np.repeat(values, 2)[:periods]
    elif values.size < periods:
        rule, candidate = "resize_wrap", np.resize(values, periods)
    else:
        rule, candidate = "truncate", values[:periods]
    if candidate.shape != clocked.shape or not np.array_equal(candidate, clocked):
        rule = "other"
    return [f"{rule}:{values.size}", digest(clocked)]


def chronology_capture(pack_root: Path, manifest: Mapping[str, Any], periods: int, *, doctoral: bool) -> dict[str, Any]:
    from gridform_core.canonical_psm_data import DOCTORAL_ALIGNMENT_PROFILE, build_chronology
    from gridform_core.v2.contracts import OperatingState

    extensions = {"doctoral_alignment_profile": DOCTORAL_ALIGNMENT_PROFILE} if doctoral else {}
    state = OperatingState(2025, representative_vre_assets(pack_root, manifest), (), extensions=extensions)
    try:
        # P0-5a: the reading the baseline describes is the frozen (reference)
        # profile's: legacy-v1 reader and clock plus the universal corrections.
        from gridform_core.data_method import policy_for_profile
        from gridform_core.methodology import REFERENCE_PROFILE_ID

        chronology = build_chronology(pack_root, manifest, state, periods=periods, period_hours=PERIOD_HOURS,
                                      data_policy=policy_for_profile(REFERENCE_PROFILE_ID, manifest))
    except Exception as error:  # noqa: BLE001
        return {"error": f"{type(error).__name__}: {error}"}
    imports: dict[str, Any] = {}
    sites: dict[str, str] = {}
    for resource in chronology.resources:
        if resource.resource_type == "import":
            country = str(resource.extensions.get("country"))
            entry = {"price": digest(resource.marginal_cost_profile_gbp_per_mwh or ())}
            if not doctoral:
                entry = {
                    "cap_mw": _round(resource.capacity_mw),
                    "marginal": _round(resource.marginal_cost_gbp_per_mwh),
                    "avail": digest(resource.availability),
                    **entry,
                }
            imports[country] = entry
        elif resource.resource_type == "vre":
            sites[resource.asset_id] = digest(resource.availability)
    extensions_out = chronology.extensions
    exports: dict[str, Any] = {}
    for asset_id, envelope in sorted(extensions_out.get("boundary_export_envelope_mwh_by_asset", {}).items()):
        country = str(asset_id).removeprefix("export:")
        prices = extensions_out.get("boundary_export_price_gbp_per_mwh_by_asset", {}).get(asset_id, ())
        exports[country] = {"price": digest(prices)} if doctoral else {"env": digest(envelope), "price": digest(prices)}
    if doctoral:
        return {"imports": imports, "exports": exports}
    result: dict[str, Any] = {
        "demand": digest(chronology.demand_mwh),
        "forecast": digest(extensions_out.get("forecast_demand_mwh", ())),
        "imports": imports,
        "exports": exports,
        "headroom": {key: _round(value) for key, value in sorted(extensions_out.get("vre_expansion_headroom_mw_by_technology", {}).items())},
        "weather_method": extensions_out.get("dispatch_weather_method"),
    }
    ordered_sites = dict(sorted(sites.items()))
    if periods == WINDOWS[0]:
        # A list in head_rules.vre_site_order when the pack has exactly those sites.
        order = vre_site_order()
        result["vre_sites"] = [ordered_sites[name] for name in order] if list(ordered_sites) == order else ordered_sites
    else:
        result["vre_sites_digest"] = hashlib.sha256(json.dumps(ordered_sites, sort_keys=True).encode("utf-8")).hexdigest()[:HASH_HEX]
    return result


def vre_site_order() -> list[str]:
    """Sorted representative VRE site names of the 101 baseline pack (all captured packs share them)."""

    root = ROOT / REPOSITORY_PACKS[0]
    return sorted(asset.asset_id for asset in representative_vre_assets(root, load_manifest(root)))


# ------------------------------------------------------- kernel input block

def kernel_profile_read(path: Path) -> np.ndarray:
    """modular_simulation_model.py:2570: ``np.array(pd.read_csv(path)).flatten()``."""

    return np.array(pd.read_csv(path)).flatten()


def kernel_price_read(path: Path) -> np.ndarray:
    """modular_simulation_model.py:2571: first column, header=None, coerce, NaN -> 0."""

    return pd.to_numeric(pd.read_csv(path, header=None).iloc[:, 0], errors="coerce").fillna(0).values


def kernel_demand_read(path: Path, periods: int) -> np.ndarray:
    """scheme_c_native_psm.py: ``np.asarray(pd.read_csv(path), dtype=float).reshape(-1)[:periods]``."""

    return np.asarray(pd.read_csv(path), dtype=float).reshape(-1)[:periods]


def kernel_clock(source: np.ndarray, periods: int) -> list[Any]:
    """The values the kernel assigns in periods 0..periods-1, using the kernel's own IterLimit_new."""

    from gridform_core.builtin.scheme_c_1000twh.runtime_compat.modular_simulation_model import IterLimit_new

    iterator = IterLimit_new(source)
    return [next(iterator) for _ in range(periods)]


def kernel_boundary_oracle(pack_root: Path, manifest: Mapping[str, Any], periods: int) -> dict[str, Any]:
    connections: dict[str, Any] = {}
    for connection, country in HEAD_KERNEL_CONNECTION_FEEDS.items():
        profile = kernel_profile_read(binding_path(pack_root, manifest, f"market.{country}.profile"))
        price = kernel_price_read(binding_path(pack_root, manifest, f"market.{country}.price"))
        connections[connection] = {
            "feed": country,
            "transfer_constraint": [str(profile.dtype), int(profile.size), digest(kernel_clock(profile, periods))],
            "external_price": [str(price.dtype), int(price.size), digest(kernel_clock(price, periods))],
        }
    demand: dict[str, Any] = {}
    for key, role in (("forecast", "demand.forecast"), ("real", "demand.real")):
        try:
            demand[key] = digest(kernel_demand_read(binding_path(pack_root, manifest, role), periods))
        except Exception as error:  # noqa: BLE001
            demand[key] = f"error: {type(error).__name__}: {error}"
    return {"connections": connections, "demand": demand}


def _scrub(text: str, *roots: Path) -> str:
    for root in roots:
        text = text.replace(str(root.resolve()), "<root>")
    return text


def kernel_recorded(pack_root: Path) -> dict[str, Any]:
    """Run the real retained kernel (golden D3 project, 48 periods) on the pack and record its inputs.

    ``vre_unit_limit`` is ``capacity_limit / capacity_multiplier`` per site
    (the kernel's per-unit limit, independent of the project's capacities);
    a site whose multiplier is zero or varies is recorded as raw limits.
    A failure is HEAD behaviour and recorded with the periods reached.
    """

    from tests.p0_5_fixtures import KernelBoundaryRecorder, run_value_101_day

    recorder = KernelBoundaryRecorder()
    result: dict[str, Any] = {}
    try:
        run_value_101_day(pack_root, recorder)
    except Exception as error:  # noqa: BLE001 - the failure itself is HEAD behaviour
        result["error"] = _scrub(f"{type(error).__name__}: {error}", pack_root, ROOT)
    result["periods_reached"] = len(recorder.periods)
    result["connections"] = {
        name: {"transfer_constraint": digest(entry["transfer_constraint"]), "external_price": digest(entry["external_price"])}
        for name, entry in sorted(recorder.connections.items())
    }
    result["demand"] = {
        "forecast": digest(recorder.forecast_demands),
        "real": digest(recorder.real_demands),
        "forecast_per_period": digest(recorder.forecast_arguments),
    }
    vre: dict[str, str] = {}
    for name, rows in sorted(recorder.vre_limits.items()):
        multipliers = {multiplier for _limit, multiplier in rows}
        if len(multipliers) == 1 and next(iter(multipliers)) != 0:
            multiplier = next(iter(multipliers))
            vre[name] = digest([limit / multiplier for limit, _multiplier in rows])
        else:
            vre[name] = "raw:" + digest([limit for limit, _multiplier in rows])
    result["vre_unit_limit"] = vre_unit_limit_entry(vre)
    return result


def vre_unit_limit_entry(per_site: Mapping[str, str]) -> dict[str, Any]:
    """Compact per-site record (size budget): site count, raw sites, digest of the sorted site->hash map."""

    return {
        "sites": len(per_site),
        "raw_sites": sorted(name for name, value in per_site.items() if value.startswith("raw:")),
        "digest": hashlib.sha256(json.dumps(dict(sorted(per_site.items()))).encode("utf-8")).hexdigest()[:HASH_HEX],
    }


# ------------------------------------------------------------ declarations

def _short(value: Any) -> Any:
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    text = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
    return text if len(text) <= 60 else text[:57] + "..."


def declaration_consumers(root: Path = ROOT) -> dict[str, list[str]]:
    """Reader sites whose source contains the quoted declaration key.

    A static string scan: a mention is not proof of consumption ('cyclic' is
    also the storage SoC rule, 'country' an extension key).  An empty list is
    proof that the site never reads the key.
    """

    sources = {name: (root / path).read_text(encoding="utf-8") for name, path in READER_SOURCES.items()}
    return {
        key: sorted(name for name, text in sources.items() if f'"{key}"' in text or f"'{key}'" in text)
        for key in (*DECLARATION_KEYS, *PACK_DECLARATION_KEYS)
    }


def declaration_coverage(manifest: Mapping[str, Any], capture: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Declarations per series role; with a capture, whether HEAD honoured a declared csv_column."""

    bindings = dict(manifest.get("bindings") or {})
    roles = {}
    for role in SERIES_ROLES:
        binding = dict(bindings.get(role) or {})
        roles[role] = {key: _short(binding[key]) for key in DECLARATION_KEYS if key in binding}
        if capture and "csv_column" in binding:
            picked = dict(capture["canonical_reader"].get(role) or {}).get("label")
            roles[role]["head_canonical_label"] = picked
            roles[role]["csv_column_honoured"] = picked == binding["csv_column"]
    return {
        "pack": {key: _short(manifest[key]) for key in PACK_DECLARATION_KEYS if key in manifest},
        "roles": roles,
    }


# ----------------------------------------------------------------- capture

IDENTITY_KEYS = ("pack_id", "manifest_sha256", "country", "timezone")


def pack_label(manifest_sha256: str, pack_id: str) -> str:
    """The baseline key: the research label for a released public1 manifest, else the pack id."""

    for label, entry in RESEARCH_PACKS.items():
        if entry["manifest_sha256"] == manifest_sha256:
            return label
    if any(entry["pack_id"] == pack_id for entry in RESEARCH_PACKS.values()):
        raise ValueError(
            f"{pack_id}: manifest sha256 {manifest_sha256} is not the released public1 revision; "
            "the S0 baseline describes the released bytes only"
        )
    return pack_id


def reading_inputs(pack_root: Path, manifest: Mapping[str, Any]) -> dict[str, str]:
    """Full sha256 of every file the captured readers open, verified against the manifest.

    Not stored (the manifest hash covers the declared hashes); used to detect
    packs whose reading inputs are byte-identical.
    """

    inputs = {}
    for role in (*SERIES_ROLES, "fleet.generators"):
        observed = file_sha256(binding_path(pack_root, manifest, role))
        declared = str(dict(manifest["bindings"][role]).get("sha256") or "")
        if observed != declared:
            raise ValueError(f"{manifest.get('id')}: {role} does not match its manifest sha256")
        inputs[role] = observed
    for role in ("weather.solar", "weather.wind"):
        if role in manifest.get("bindings", {}):
            # Verified against the file by doctoral_weather._verified_hash during capture.
            inputs[role] = str(manifest["bindings"][role].get("sha256") or "")
    return inputs


def capture_pack(pack_root: Path, *, kernel: bool = True) -> dict[str, Any]:
    pack_root = pack_root.resolve()
    manifest = load_manifest(pack_root)
    reading_inputs(pack_root, manifest)
    canonical: dict[str, Any] = {}
    validator: dict[str, Any] = {}
    clocks: dict[str, Any] = {str(window): {} for window in WINDOWS}
    for role in SERIES_ROLES:
        path = binding_path(pack_root, manifest, role)
        canonical[role] = canonical_reader(path, role)
        validator[role] = validator_reader(path)
        # Same values as the canonical reader: the hash is not repeated.
        if validator[role][3] == canonical[role].get("sha"):
            validator[role][3] = "=canonical"
        for window in WINDOWS:
            rule, sha = canonical_clock(path, role, window)
            # An exact clock returns the reader series itself: its hash is
            # canonical_reader[role].sha and is not repeated.
            clocks[str(window)][role] = rule if rule.startswith("exact:") and sha == canonical[role].get("sha") else [rule, sha]
    capture = {
        "pack_id": str(manifest["id"]),
        "manifest_sha256": file_sha256(pack_root / "manifest.json"),
        "country": manifest.get("country"),
        "timezone": manifest.get("timezone"),
        "canonical_reader": canonical,
        "validator_reader": validator,
        "canonical_clock": clocks,
        "chronology": {
            "value.canonical": {str(window): chronology_capture(pack_root, manifest, window, doctoral=False) for window in WINDOWS},
            "doctoral-national": {str(window): chronology_capture(pack_root, manifest, window, doctoral=True) for window in KERNEL_WINDOWS},
        },
        "kernel_boundary_oracle": {str(window): kernel_boundary_oracle(pack_root, manifest, window) for window in KERNEL_WINDOWS},
    }
    if kernel:
        capture["kernel_recorded"] = {str(KERNEL_RECORDED_WINDOW): kernel_recorded(pack_root)}
    return capture


def reader_source_identity(root: Path = ROOT) -> dict[str, str]:
    return {path: file_sha256(root / path) for path in READER_SOURCES.values()}


def _git(*arguments: str) -> str | None:
    import subprocess

    try:
        completed = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def capture_provenance() -> dict[str, Any]:
    """Source commit and whether the reader sites (and the golden D3 runner) equal 35aadb3."""

    head = _git("rev-parse", "HEAD")
    paths = [*READER_SOURCES.values(), "gridform_core/builtin/scheme_c_1000twh/runtime_compat",
             "gridform_core/builtin/scheme_c_1000twh/scheme_c_context.py"]
    identical = None
    if head and _git("cat-file", "-e", f"{PRE_P0_COMMIT}^{{commit}}") is not None:
        identical = _git("diff", "--quiet", PRE_P0_COMMIT, "HEAD", "--", *paths) is not None
    return {
        "source_commit": head,
        "reader_sources_sha256": reader_source_identity(),
        f"reader_sources_identical_to_{PRE_P0_COMMIT}": identical,
    }


def _reading(capture: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in capture.items() if key not in IDENTITY_KEYS}


def build(pack_roots: Sequence[Path]) -> tuple[dict[str, Any], dict[str, Any]]:
    packs: dict[str, Any] = {}
    inputs_by_pack: dict[str, dict[str, str]] = {}
    coverage: dict[str, Any] = {}
    for pack_root in pack_roots:
        pack_root = pack_root.resolve()
        manifest = load_manifest(pack_root)
        label = pack_label(file_sha256(pack_root / "manifest.json"), str(manifest["id"]))
        if label in packs:
            raise ValueError(f"{label}: supplied twice")
        capture = capture_pack(pack_root)
        inputs = reading_inputs(pack_root, manifest)
        coverage[label] = declaration_coverage(manifest, capture)
        # A pack whose reading inputs are byte-identical to an earlier pack and
        # whose capture is identical is stored as a reference (the 101 network
        # pack reuses the 101 baseline series).
        for other_label, other in packs.items():
            if "same_reading_as" not in other and inputs_by_pack[other_label] == inputs and _reading(other) == _reading(capture):
                capture = {**{key: capture[key] for key in IDENTITY_KEYS}, "same_reading_as": other_label}
                break
        inputs_by_pack[label] = inputs
        packs[label] = capture
    baseline = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "P0-5 S0: data-reading behaviour of the code as of capture (reader sites identical to 35aadb3, see captured_with) for later diffs; no behaviour change",
        "hash_rule": HASH_RULE,
        "windows": list(WINDOWS),
        "kernel_windows": list(KERNEL_WINDOWS),
        "kernel_recorded_window": KERNEL_RECORDED_WINDOW,
        "research_packs": RESEARCH_PACKS,
        "head_rules": {
            "canonical_header": {role: ("none" if value is None else value) for role, value in HEAD_CANONICAL_HEADER.items()},
            "canonical_hourly_repeat_roles": sorted(HEAD_CANONICAL_HOURLY_REPEAT),
            "canonical_clock_entry": "'exact:<source length>' alone means the clock returned the reader series unchanged (hash = canonical_reader.sha); otherwise [rule:<source length>, hash]",
            "kernel_connection_feeds": HEAD_KERNEL_CONNECTION_FEEDS,
            "kernel_clock": "IterLimit_new: period p receives source[(p // 2) % len(source)]",
            "kernel_entry": "[dtype, source length, hash of the values assigned in periods 0..window-1]",
            "kernel_recorded": "real kernel, frozen golden D3 project (value_101_day, 48 periods) run on the pack; hashes of what ahead_market_bidding saw per period; vre_unit_limit = {sites, raw_sites, digest of the sorted site -> hash(capacity_limit / capacity_multiplier) map; 'raw:' + hash of the limits when the multiplier is 0 or varies}; error + periods_reached when the kernel stops",
            "vre_site_order": vre_site_order(),
            "chronology_state": "OperatingState(2025) holding every fleet.generators solar*/onshore*/offshore* site at 1 MW; doctoral-national (windows 17520 and 48) adds the doctoral_alignment_profile extension; only its boundary prices are recorded",
        },
        "captured_with": capture_provenance(),
        "packs": packs,
        "expected_change": EXPECTED_CHANGE,
    }
    coverage_document = {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "purpose": "P0-5 S0: which declarations each pack carries per series role, and which HEAD reader site mentions each key",
        "declaration_keys": list(DECLARATION_KEYS),
        "pack_keys": list(PACK_DECLARATION_KEYS),
        "mentioned_by_reader_site": declaration_consumers(),
        "mentioned_note": "static scan of the quoted key in each reader site's source; a mention is not proof of consumption ('cyclic' is also the SoC rule, 'country' an extension key), an empty list proves the site never reads it",
        "reader_sites": READER_SOURCES,
        "packs": coverage,
    }
    return baseline, coverage_document


def dumps(value: Any, indent: int = 0) -> str:
    """JSON with one compact line per leaf object or list, so diffs show one series per line."""

    def leaf(item: Any) -> bool:
        return not isinstance(item, Mapping) or not any(isinstance(child, Mapping) for child in item.values())

    if isinstance(value, Mapping) and not leaf(value):
        pad = " " * (indent + 1)
        items = [f"{pad}{json.dumps(str(key))}: {dumps(value[key], indent + 1)}" for key in sorted(value)]
        return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"
    if isinstance(value, list) and any(isinstance(item, Mapping) for item in value):
        pad = " " * (indent + 1)
        return "[\n" + ",\n".join(pad + json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value) + "\n" + " " * indent + "]"
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


# ------------------------------------------------------------------- check

def default_pack_roots(extra: Sequence[Path] = ()) -> list[Path]:
    roots = [ROOT / relative for relative in REPOSITORY_PACKS]
    environment = os.environ.get(PACKS_ENVIRONMENT, "")
    candidates = [*extra, *(Path(item) for item in environment.split(os.pathsep) if item.strip())]
    for candidate in candidates:
        if candidate.resolve() not in {root.resolve() for root in roots}:
            roots.append(candidate)
    return roots


def differences(stored: Any, fresh: Any, path: str = "") -> list[str]:
    if isinstance(stored, Mapping) and isinstance(fresh, Mapping):
        found = []
        for key in sorted(set(stored) | set(fresh)):
            child = f"{path}.{key}" if path else str(key)
            if key not in stored:
                found.append(f"{child}: not in baseline")
            elif key not in fresh:
                found.append(f"{child}: missing")
            else:
                found.extend(differences(stored[key], fresh[key], child))
        return found
    if stored != fresh:
        return [f"{path}: baseline {json.dumps(stored)[:120]} != now {json.dumps(fresh)[:120]}"]
    return []


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stored_capture(baseline: Mapping[str, Any], label: str) -> dict[str, Any]:
    """The pack's capture with a ``same_reading_as`` reference resolved."""

    stored = dict(baseline["packs"][label])
    if "same_reading_as" in stored:
        return {**_reading(baseline["packs"][stored["same_reading_as"]]), **{key: stored[key] for key in IDENTITY_KEYS}}
    return stored


def stored_label(baseline: Mapping[str, Any], pack_root: Path) -> tuple[str | None, str | None]:
    """``(label, None)`` for a captured pack; ``(None, reason)`` otherwise."""

    manifest_sha = file_sha256(pack_root / "manifest.json")
    pack_id = str(load_manifest(pack_root)["id"])
    for label, entry in baseline["packs"].items():
        if entry["manifest_sha256"] == manifest_sha:
            return label, None
    same_id = sorted(label for label, entry in baseline["packs"].items() if entry["pack_id"] == pack_id)
    if same_id:
        return None, f"{pack_id}: manifest differs from the captured revision {same_id[0]}"
    return None, f"{pack_id}: not in baseline"


def check(pack_roots: Sequence[Path], baseline: Mapping[str, Any] | None = None, *, kernel: bool = True) -> dict[str, Any]:
    baseline = baseline or load_baseline()
    report: dict[str, Any] = {"checked": [], "skipped": [], "differences": {}}
    for pack_root in pack_roots:
        if not (pack_root / "manifest.json").is_file():
            report["skipped"].append(f"{pack_root.name}: no manifest")
            continue
        label, reason = stored_label(baseline, pack_root)
        if label is None:
            if "manifest differs" in str(reason):
                report["differences"][str(load_manifest(pack_root)["id"])] = [str(reason)]
            else:
                report["skipped"].append(str(reason))
            continue
        stored = stored_capture(baseline, label)
        if not kernel:
            stored.pop("kernel_recorded", None)
        found = differences(stored, capture_pack(pack_root, kernel=kernel))
        if found:
            report["differences"][label] = found
        report["checked"].append(label)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    capture_parser = sub.add_parser("capture")
    capture_parser.add_argument("--pack", type=Path, action="append", default=[])
    capture_parser.add_argument("--output", type=Path, default=BASELINE_PATH)
    capture_parser.add_argument("--coverage-output", type=Path, default=COVERAGE_PATH)
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--pack", type=Path, action="append", default=[])
    check_parser.add_argument("--no-kernel", action="store_true", help="skip the real-kernel runs (kernel_recorded)")
    show_parser = sub.add_parser("show")
    show_parser.add_argument("--pack", type=Path, required=True)
    arguments = parser.parse_args(argv)
    if arguments.command == "show":
        sys.stdout.write(dumps(capture_pack(arguments.pack)) + "\n")
        return 0
    roots = default_pack_roots(arguments.pack)
    if arguments.command == "capture":
        for target in (arguments.output, arguments.coverage_output):
            if target.exists():
                raise SystemExit(f"refusing to overwrite {target}: the S0 baseline is captured once")
        baseline, coverage = build(roots)
        missing = sorted(set(RESEARCH_PACKS) - set(baseline["packs"]))
        if missing:
            raise SystemExit(f"refusing to capture without the released research packs: {', '.join(missing)}")
        arguments.output.write_text(dumps(baseline) + "\n", encoding="utf-8")
        arguments.coverage_output.write_text(dumps(coverage) + "\n", encoding="utf-8")
        sys.stdout.write(json.dumps({"packs": sorted(baseline["packs"]), "bytes": arguments.output.stat().st_size,
                                     "coverage_bytes": arguments.coverage_output.stat().st_size}) + "\n")
        return 0
    report = check(roots, kernel=not arguments.no_kernel)
    sys.stdout.write(json.dumps(report, indent=1, sort_keys=True) + "\n")
    return 1 if report["differences"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
