"""Compute or check the model CF rows of the A9 disclosure table.

    python -B scripts/vre_cf_disclosure.py --check [--packs DIR ...]
    python -B scripts/vre_cf_disclosure.py --write --packs DIR ...

For each pack directory the unweighted mean pre-curtailment capacity factor of
its representative weather sites (17,520 half-hour periods) is computed for
every dispatch weather method (doctoral v1; P0-5b v2 + losses; F2 v2 + losses
+ solar plane-of-array) and stored in
``gridform_core/data/weather/value_uk_vre_cf_disclosure_v1.json`` under the
sha256 of the pack's weather and fleet bindings.  ``--check`` recomputes the
rows of the packs it is given (default: the shipped VALUE 101 baseline plus
the ``VALUE_P0_5_PACKS`` research packs, when set) and fails on any difference
above 1e-6.  Reporting only: nothing is calibrated.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

from gridform_core import site_weather as sw  # noqa: E402
from gridform_core import vre_cf_disclosure as disclosure  # noqa: E402
from gridform_core.doctoral_weather_mapping import representative_sites  # noqa: E402

METHODS = (sw.FROZEN, sw.SiteWeatherMethod("v2", True), sw.SiteWeatherMethod("v2", True, True))
PERIODS = 17520


def default_packs() -> list[Path]:
    packs = [ROOT / "data-packs" / "value-101-baseline-v1"]
    for item in os.environ.get("VALUE_P0_5_PACKS", "").split(":"):
        if item and (Path(item) / "manifest.json").is_file():
            packs.append(Path(item))
    return packs


def compute(pack: Path) -> dict[str, object]:
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    bindings = manifest["bindings"]
    fleet = json.loads((pack / bindings["fleet.generators"]["uri"]).read_text(encoding="utf-8"))
    sites = representative_sites(fleet)
    roles = ("weather.solar", "weather.wind")
    files = {"paths": {role: pack / bindings[role]["uri"] for role in roles},
             "hashes": {role: bindings[role]["sha256"] for role in roles},
             "bindings": {role: bindings[role] for role in roles}}
    by_method: dict[str, dict[str, float]] = {}
    for method in METHODS:
        profiles = sw.site_cf_by_source(**files, sites=sites, sources=list(sites), periods=PERIODS, method=method)
        by_method[method.method_id] = {technology: round(value, 6) for technology, value in
                                       sw.annual_capacity_factors(profiles, sites).items()}
    counts: dict[str, int] = {}
    for site in sites.values():
        counts[str(site["technology"])] = counts.get(str(site["technology"]), 0) + 1
    return {
        "label": str(manifest.get("id")),
        "pack_ids": [str(manifest.get("id"))],
        "object_sha256": {role: str(bindings[role]["sha256"]) for role in disclosure.ROLES},
        "representative_sites": dict(sorted(counts.items())),
        "by_method": by_method,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--packs", nargs="*", type=Path)
    arguments = parser.parse_args(argv)
    packs = arguments.packs or default_packs()
    table = json.loads(disclosure.TABLE_PATH.read_text(encoding="utf-8"))
    rows = table["model_reference"]
    errors: list[str] = []
    for pack in packs:
        row = compute(pack)
        index = next((i for i, item in enumerate(rows) if item["object_sha256"] == row["object_sha256"]), None)
        print(json.dumps({"pack": str(pack.name), **row}, indent=1))
        if arguments.write:
            if index is None:
                rows.append(row)
            else:
                pack_ids = sorted(set(rows[index].get("pack_ids", [])) | set(row["pack_ids"]))
                rows[index] = {**row, "label": rows[index].get("label", row["label"]), "pack_ids": pack_ids}
            continue
        if index is None:
            errors.append(f"{pack}: weather/fleet not in the disclosure table")
            continue
        for method_id, values in row["by_method"].items():
            stored = rows[index]["by_method"].get(method_id)
            if stored is None or any(abs(float(stored[k]) - float(v)) > 1e-6 for k, v in values.items()):
                errors.append(f"{pack}: {method_id} stored {stored} != computed {values}")
    if arguments.write:
        disclosure.TABLE_PATH.write_text(json.dumps(table, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"written {disclosure.TABLE_PATH.relative_to(ROOT)}")
        return 0
    for line in errors:
        print("ERROR", line, file=sys.stderr)
    print("vre cf disclosure:", "passed" if not errors else "failed")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
