"""Compact, on-demand audit export for annual storage-cost recovery state.

The VALUE checkpoints are Python pickle files.  Pickle is not a safe import
format for untrusted data, so callers must explicitly confirm that checkpoints
were produced locally by this VALUE workspace.  The exported JSON contains
plain data and is safe to expose as a downloadable run artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import re
from collections.abc import Mapping
from pathlib import Path

from .storage_recovery import recovery_adequacy


STORAGE_AUDIT_SCHEMA = "value.storage-cost-audit/v1"
_ANNUAL_CHECKPOINT = re.compile(r"_checkpoint_(\d{4})\.pkl$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number == number and abs(number) != float("inf") else 0.0


def _diagnostics(
    year: int, asset: Mapping[str, object], *, start_year: int
) -> list[dict[str, object]]:
    method = str(asset.get("method") or "")
    if not method.startswith(("dynamic_", "user_formula_")):
        return []
    previous = _finite_number(asset.get("previous_year_sold_mwh"))
    current = _finite_number(asset.get("current_year_sold_mwh"))
    holding = _finite_number(asset.get("holding_recovery_gbp_per_mwh_period"))
    rows: list[dict[str, object]] = []
    if year > start_year and asset.get("pricing_basis") == "full_utilisation_initialisation":
        rows.append(
            {
                "code": "GF_STORAGE_FULL_UTILISATION_FALLBACK",
                "severity": "information",
                "message": "No preceding-year sale was available; pricing returned to the full-utilisation design basis.",
            }
        )
    if previous > 0 and current == 0:
        rows.append(
            {
                "code": "GF_STORAGE_ZERO_SALES_AFTER_OBSERVED_BASIS",
                "severity": "warning",
                "message": "The asset sold no electricity after pricing from a positive preceding-year sales observation.",
            }
        )
    if holding > 10_000:
        rows.append(
            {
                "code": "GF_STORAGE_HIGH_HOLDING_RECOVERY",
                "severity": "warning",
                "message": "The preceding-year allocation denominator produced a holding recovery above GBP 10,000/MWh/period.",
                "value_gbp_per_mwh_period": holding,
            }
        )
    return rows


def storage_year_snapshot(
    state: Mapping[str, object], *, checkpoint_name: str, checkpoint_sha256: str
) -> dict[str, object]:
    year = int(state["completed_year"])
    start_year = int(state.get("start_year", year))
    battery_objects = state.get("battery_objects")
    if not isinstance(battery_objects, Mapping):
        raise ValueError("Checkpoint does not contain a storage-object mapping")

    assets: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    for object_key, storage_object in sorted(
        battery_objects.items(), key=lambda item: str(item[0]).casefold()
    ):
        reporter = getattr(storage_object, "storage_cost_report", None)
        if not callable(reporter):
            raise ValueError(f"Storage object {object_key!r} has no cost-report contract")
        report = reporter()
        if not isinstance(report, Mapping):
            raise ValueError(f"Storage object {object_key!r} returned an invalid cost report")
        asset = {"object_key": str(object_key), **dict(report)}
        asset["recovery_adequacy"] = recovery_adequacy(asset)
        asset_diagnostics = _diagnostics(year, asset, start_year=start_year)
        if asset_diagnostics:
            asset["diagnostics"] = asset_diagnostics
            diagnostics.extend(
                {"year": year, "object_key": str(object_key), **row}
                for row in asset_diagnostics
            )
        assets.append(asset)

    def total(field: str) -> float:
        return sum(_finite_number(asset.get(field)) for asset in assets)

    return {
        "year": year,
        "checkpoint": {
            "artifact_name": checkpoint_name,
            "sha256": checkpoint_sha256,
        },
        "summary": {
            "assets": len(assets),
            "power_capacity_mw": total("power_capacity_mw"),
            "energy_capacity_mwh": total("energy_capacity_mwh"),
            "previous_year_sold_mwh": total("previous_year_sold_mwh"),
            "current_year_sold_mwh": total("current_year_sold_mwh"),
            "annual_levelized_project_cost_gbp": total("annual_levelized_project_cost_gbp"),
            "current_cycle_depreciation_gbp": total("current_cycle_depreciation_gbp"),
            "diagnostics": len(diagnostics),
        },
        "assets": assets,
        "diagnostics": diagnostics,
    }


def build_storage_cost_audit(
    checkpoint_dir: Path,
    *,
    trust_local_checkpoints: bool,
    run_id: str | None = None,
) -> dict[str, object]:
    """Load trusted annual checkpoints and return a plain-JSON audit record."""

    if not trust_local_checkpoints:
        raise ValueError(
            "Refusing to load pickle checkpoints without explicit local-trust confirmation"
        )
    checkpoint_dir = checkpoint_dir.resolve()
    annual = [
        path
        for path in checkpoint_dir.glob("*_checkpoint_*.pkl")
        if _ANNUAL_CHECKPOINT.search(path.name)
    ]
    annual.sort(key=lambda path: int(_ANNUAL_CHECKPOINT.search(path.name).group(1)))  # type: ignore[union-attr]
    if not annual:
        raise FileNotFoundError(f"No annual VALUE checkpoints found in {checkpoint_dir}")

    years: list[dict[str, object]] = []
    for path in annual:
        with path.open("rb") as handle:
            state = pickle.load(handle)  # nosec B301: guarded by explicit trusted-local opt-in
        if not isinstance(state, Mapping):
            raise ValueError(f"Checkpoint {path.name} does not contain a state mapping")
        years.append(
            storage_year_snapshot(
                state,
                checkpoint_name=path.name,
                checkpoint_sha256=_sha256_file(path),
            )
        )

    diagnostics = [row for year in years for row in year["diagnostics"]]  # type: ignore[index]
    return {
        "schema_version": STORAGE_AUDIT_SCHEMA,
        "run_id": run_id,
        "source": "trusted_local_annual_checkpoints",
        "years": years,
        "summary": {
            "start_year": years[0]["year"],
            "end_year": years[-1]["year"],
            "years": len(years),
            "diagnostics": len(diagnostics),
            "warning_diagnostics": sum(
                row.get("severity") == "warning" for row in diagnostics
            ),
        },
    }


def build_storage_cost_audit_from_year_results(
    year_results_path: Path,
    *,
    run_id: str | None = None,
) -> dict[str, object]:
    """Build the same audit from the safe public v2 annual result contract."""

    payload = json.loads(year_results_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("year-results-v2.json must contain at least one annual result")
    start_year = min(int(row["year"]) for row in payload)
    years: list[dict[str, object]] = []
    for row in sorted(payload, key=lambda item: int(item["year"])):
        year = int(row["year"])
        observations = row.get("market", {}).get("extensions", {}).get(
            "storage_cost_observations"
        )
        if not isinstance(observations, Mapping):
            raise ValueError(f"Year {year} has no storage-cost observation mapping")
        assets: list[dict[str, object]] = []
        diagnostics: list[dict[str, object]] = []
        for object_key, observation in sorted(
            observations.items(), key=lambda item: str(item[0]).casefold()
        ):
            if not isinstance(observation, Mapping):
                raise ValueError(f"Storage observation {object_key!r} is not a mapping")
            asset = {"object_key": str(object_key), **dict(observation)}
            asset["recovery_adequacy"] = recovery_adequacy(asset)
            asset_diagnostics = _diagnostics(year, asset, start_year=start_year)
            if asset_diagnostics:
                asset["diagnostics"] = asset_diagnostics
                diagnostics.extend(
                    {"year": year, "object_key": str(object_key), **diagnostic}
                    for diagnostic in asset_diagnostics
                )
            assets.append(asset)

        def total(field: str) -> float:
            return sum(_finite_number(asset.get(field)) for asset in assets)

        years.append(
            {
                "year": year,
                "source_result_id": row.get("result_id"),
                "summary": {
                    "assets": len(assets),
                    "power_capacity_mw": total("power_capacity_mw"),
                    "energy_capacity_mwh": total("energy_capacity_mwh"),
                    "previous_year_sold_mwh": total("previous_year_sold_mwh"),
                    "current_year_sold_mwh": total("current_year_sold_mwh"),
                    "annual_levelized_project_cost_gbp": total(
                        "annual_levelized_project_cost_gbp"
                    ),
                    "current_cycle_depreciation_gbp": total(
                        "current_cycle_depreciation_gbp"
                    ),
                    "diagnostics": len(diagnostics),
                },
                "assets": assets,
                "diagnostics": diagnostics,
            }
        )
    all_diagnostics = [
        diagnostic for year in years for diagnostic in year["diagnostics"]
    ]
    return {
        "schema_version": STORAGE_AUDIT_SCHEMA,
        "run_id": run_id,
        "source": "safe_public_year_results_v2",
        "source_path": str(year_results_path.resolve()),
        "years": years,
        "summary": {
            "start_year": years[0]["year"],
            "end_year": years[-1]["year"],
            "years": len(years),
            "diagnostics": len(all_diagnostics),
            "warning_diagnostics": sum(
                row.get("severity") == "warning" for row in all_diagnostics
            ),
        },
    }


def export_storage_cost_audit(
    checkpoint_dir: Path,
    output_path: Path,
    *,
    trust_local_checkpoints: bool,
    run_id: str | None = None,
) -> Path:
    payload = build_storage_cost_audit(
        checkpoint_dir,
        trust_local_checkpoints=trust_local_checkpoints,
        run_id=run_id,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export plain-JSON storage-cost audit data from trusted VALUE checkpoints"
    )
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--checkpoints", type=Path)
    sources.add_argument("--year-results", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--trust-local-checkpoints", action="store_true")
    args = parser.parse_args()
    if args.year_results is not None:
        payload = build_storage_cost_audit_from_year_results(
            args.year_results, run_id=args.run_id
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(args.output)
        path = args.output
    else:
        path = export_storage_cost_audit(
            args.checkpoints,
            args.output,
            trust_local_checkpoints=args.trust_local_checkpoints,
            run_id=args.run_id,
        )
    print(path)


if __name__ == "__main__":
    main()
