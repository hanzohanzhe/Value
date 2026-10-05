"""P0-7 S10 integration acceptance on kept VALUE-101 run outputs and the golden bookkeeping.

Two independent parts:

``analyse``  reads the kept output of golden cases (``scripts/golden/run_case.py
             --keep-output DIR``) and checks the plan's S10 acceptance rules on
             every year of every run:

             * no Invest_High (or any proposal) without a strictly positive
               surplus S above the hurdle: a proposal needs ROI > 0 and the
               recommendation must follow ROI/payback; a thermal group whose
               A4 net revenue is ~0 must not propose (decision A4, plan S10
               "S~0 must not be High");
             * storage additions: every headroom-limited technology stays within
               its cap and, where the run declares a ``power_battery_pool``
               (corrected), the three power batteries together stay within the
               pool cap (P5-02);
             * the annual cost ledger reconciles: the headline equals the sum of
               the included lines, the capital line equals the market capital
               less network, A7 memo and (corrected) P4-03 memo, and the memo
               rows are not counted.

             It also records the A8(3) storage-investment review (income, CAPEX,
             ROI against preferred_rate, headroom) so the maintainer can see why
             storage does or does not expand.

``attribute`` walks every golden revision of both families and checks that
             every revision changing a trajectory or accounting column names a
             correction id, and that a doctoral trajectory change names an
             allow-listed universal finding with its numeric report. It lists
             the changed columns per correction id (the delta report rows).

The committed fixture ``tests/fixtures/p07/s10_acceptance.json`` is the output
of ``analyse`` on the five S10 cases plus the attribution summary; the test
``tests/test_p07_s10_acceptance.py`` re-checks it without running the model.
"""

from __future__ import annotations

import sys as _sys

_sys.dont_write_bytecode = True

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "tests" / "golden"
SCHEMA = "value.p07-s10-acceptance/v1"
POWER_BATTERIES = ("0.25c_battery", "0.5c_battery", "1c_battery")
STORAGE_TECHNOLOGIES = POWER_BATTERIES + ("hydrogen_battery", "pumped_hydro")
GROSS_PROFIT_TECHNOLOGIES = frozenset(
    {"solar", "onshore", "offshore", "nuclear", "hydro", "ror_hydro"} | set(STORAGE_TECHNOLOGIES)
)
REL_TOL = 1e-9
ABS_TOL_GBP = 1e-6
ABS_TOL_MW = 1e-9
# Revisions of the two M5 packages (P0-5b data, P0-7 investment/cost).
M5_PREFIXES = ("p05.weather-time-convention", "p05.vre-loss-factors", "p05.firm-availability",
               "p05.kernel-site", "p07.")


def _close(a: float, b: float, rel: float = REL_TOL, abs_tol: float = ABS_TOL_GBP) -> bool:
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_tol)


# ---------------------------------------------------------------- analyse ---

def check_investment_year(year: Mapping[str, Any]) -> dict[str, Any]:
    """Investment checks of one ``value.year-result/v2`` row."""

    market = year["market"]
    decision = year["investment"]
    ext = decision.get("extensions") or {}
    errors: list[str] = []
    proposals = []
    for proposal in decision.get("proposals") or []:
        evidence = proposal.get("evidence") or {}
        pext = proposal.get("extensions") or {}
        roi = float(evidence.get("roi", 0.0))
        preferred = float(evidence.get("preferred_rate", 0.0))
        payback = float(evidence.get("payback_years", math.inf))
        target = float(evidence.get("target_payback_years", math.inf))
        recommendation = str(pext.get("investment_recommendation"))
        row = {"technology": proposal["technology"], "capacity_mw": float(proposal["capacity_mw"]),
               "recommendation": recommendation, "roi": roi, "preferred_rate": preferred,
               "payback_years": payback, "owner": proposal.get("agent_id") or pext.get("investment_owner_id")}
        proposals.append(row)
        if not roi > 0.0 or not math.isfinite(payback):
            errors.append(f"{proposal['technology']}: proposal with S<=0 (roi={roi!r}, payback={payback!r})")
        if recommendation == "Invest_High" and not roi > preferred:
            errors.append(f"{proposal['technology']}: Invest_High with roi {roi} <= preferred {preferred}")
        if recommendation == "Invest_Profit" and (roi > preferred or payback > target):
            errors.append(f"{proposal['technology']}: Invest_Profit inconsistent with roi/payback")
        if recommendation not in {"Invest_High", "Invest_Profit"}:
            errors.append(f"{proposal['technology']}: unexpected recommendation {recommendation!r}")
        if row["capacity_mw"] <= 0:
            errors.append(f"{proposal['technology']}: non-positive proposal")

    # Thermal groups at S~0 (A4: bid-at-cost income == running cost) must not propose.
    a4 = (ext.get("a4_net_revenue") or {}).get("thermal_operating_cost_gbp_by_group") or {}
    income_by_asset = market.get("market_income_gbp_by_agent") or {}
    assets = {asset["asset_id"]: asset for asset in (year["planning_advance"]["operating_state"]["assets"])}
    thermal = []
    for group, operating in sorted(a4.items()):
        owner, technology, region = group.split("|")
        members = [a for a in assets.values()
                   if a["technology"] == technology and (a.get("region") or "GB") == region
                   and str((a.get("extensions") or {}).get("investment_owner_id")
                           or (a.get("extensions") or {}).get("source_agent_id") or a["asset_id"]) == owner]
        income = math.fsum(float(income_by_asset.get(a["asset_id"], 0.0) or 0.0) for a in members)
        net = income - float(operating)
        near_zero = abs(net) <= 1e-9 * max(abs(income), float(operating), 1.0)
        proposed = [p for p in proposals if p["technology"] == technology and str(p["owner"]) == owner]
        retired = math.fsum(float(v) for k, v in (decision.get("retirements_mw") or {}).items()
                            if k in {a["asset_id"] for a in members})
        thermal.append({"group": group, "income_gbp": income, "operating_cost_gbp": float(operating),
                        "net_gbp": net, "near_zero": near_zero,
                        "proposed_mw": math.fsum(p["capacity_mw"] for p in proposed), "retired_mw": retired})
        if near_zero and proposed:
            errors.append(f"{group}: S~0 (net {net}) but proposes {thermal[-1]['proposed_mw']} MW")
        if net <= 0 and proposed:
            errors.append(f"{group}: net {net} <= 0 but proposes")

    # Storage caps and the corrected power-battery pool.
    caps = {k: float(v) for k, v in (ext.get("initial_headroom_mw_by_technology") or {}).items()}
    added: dict[str, float] = defaultdict(float)
    for row in proposals:
        added[row["technology"]] += row["capacity_mw"]
    storage_headroom = next((h for h in year.get("expansion_headroom") or []
                             if h.get("module_id") == "value-storage-expansion-policy"), None)
    hext = (storage_headroom or {}).get("extensions") or {}
    pools = hext.get("pools") or {}
    for technology in STORAGE_TECHNOLOGIES:
        if added.get(technology, 0.0) > caps.get(technology, 0.0) + ABS_TOL_MW and technology in caps:
            errors.append(f"{technology}: {added[technology]} MW above its cap {caps[technology]}")
    pool_rows = {}
    for name, spec in pools.items():
        used = math.fsum(added.get(t, 0.0) for t in spec.get("technologies") or [])
        pool_rows[name] = {"cap_mw": float(spec["cap_mw"]), "added_mw": used}
        if used > float(spec["cap_mw"]) + ABS_TOL_MW:
            errors.append(f"{name}: {used} MW above the pool cap {spec['cap_mw']}")

    storage_review = []
    for asset_id, asset in sorted(assets.items()):
        if asset["technology"] not in STORAGE_TECHNOLOGIES:
            continue
        aext = asset.get("extensions") or {}
        capex = float(aext.get("total_capex_gbp", 0.0) or 0.0)
        income = float(income_by_asset.get(asset_id, 0.0) or 0.0)
        storage_review.append({
            "asset_id": asset_id, "technology": asset["technology"], "capacity_mw": float(asset["capacity_mw"]),
            "market_income_gbp": income, "total_capex_gbp": capex,
            "roi": income / capex if capex > 0 else None,
            "preferred_rate": float(aext.get("preferred_rate", 0.08) or 0.08),
            "headroom_mw": caps.get(asset["technology"]),
            "proposed_mw": added.get(asset["technology"], 0.0),
        })
    return {
        "year": year["year"],
        "proposals": proposals,
        "retirements_mw": {k: float(v) for k, v in sorted((decision.get("retirements_mw") or {}).items())},
        "thermal_groups": thermal,
        "storage_headroom": {
            "allowed_additions_mw": (storage_headroom or {}).get("allowed_additions_mw"),
            "semantics": hext.get("headroom_semantics"),
            "reason": hext.get("reason"),
            "pools": pool_rows,
        },
        "storage_review": storage_review,
        "errors": errors,
    }


def check_cost_ledger(ledger: Mapping[str, Any], years: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Reconcile each annual cost-ledger row with its market result."""

    markets = {row["year"]: row["market"] for row in years}
    results = []
    for row in ledger.get("years") or []:
        errors: list[str] = []
        lines = {line["id"]: line for line in row.get("lines") or []}
        included = math.fsum(float(line["amount_gbp"]) for line in lines.values() if line.get("included_in_cem_system_cost"))
        if not _close(included, row["cem_system_cost_gbp"]):
            errors.append(f"headline {row['cem_system_cost_gbp']} != sum of included lines {included}")
        if row.get("status") != "reconciled":
            errors.append(f"status {row.get('status')!r}")
        market = markets.get(row["year"])
        capital_line = float(lines.get("commissioned_fleet.annualised_capital", {}).get("amount_gbp", 0.0))
        memo_fom = float(row.get("vre_storage_fixed_opex_excluded_gbp") or 0.0)
        compat = float(row.get("compatibility_capital_gbp") or 0.0)
        compat_out = row.get("compatibility_capital_in_headline") is False
        network = math.fsum(float(line["amount_gbp"]) for key, line in lines.items()
                            if key.startswith("network.commissioned_assets."))
        if row.get("headline_capital_gbp") is not None and not _close(row["headline_capital_gbp"], capital_line):
            errors.append("headline_capital_gbp differs from the fleet capital line")
        if market is not None:
            expected = float(market["total_levelized_capital_cost_gbp"]) - network - memo_fom - (compat if compat_out else 0.0)
            if not _close(capital_line, max(expected, 0.0)):
                errors.append(f"capital line {capital_line} != market capital less network/memo {expected}")
        for memo_id in ("vre_storage.fixed_opex_in_levelised_capex", "existing_stock_compatibility.annualised_capital"):
            if memo_id in lines and lines[memo_id].get("included_in_cem_system_cost"):
                errors.append(f"memo row {memo_id} is counted in the headline")
        results.append({
            "year": row["year"], "cem_system_cost_gbp": row["cem_system_cost_gbp"],
            "headline_capital_gbp": capital_line, "vre_storage_fixed_opex_memo_gbp": memo_fom,
            "compatibility_capital_gbp": compat, "compatibility_capital_in_headline": row.get("compatibility_capital_in_headline"),
            "physical_reconciliation_residual_gbp": row.get("physical_reconciliation_residual_gbp"),
            "errors": errors,
        })
    return results


def analyse_output(output_dir: Path) -> dict[str, Any]:
    years = json.loads((output_dir / "year-results-v2.json").read_text(encoding="utf-8"))
    ledger = json.loads((output_dir / "ledgers" / "annual-cost-ledger.json").read_text(encoding="utf-8"))
    resolved = json.loads((output_dir / "resolved-run.json").read_text(encoding="utf-8"))
    parameters = resolved.get("scientific_parameters") or (resolved.get("run") or {}).get("scientific_parameters") or {}
    investment = [check_investment_year(year) for year in years]
    cost = check_cost_ledger(ledger, years)
    errors = [f"{row['year']}: {e}" for row in investment for e in row["errors"]]
    errors += [f"{row['year']} ledger: {e}" for row in cost for e in row["errors"]]
    return {
        "profile": parameters.get("methodology.profile") or "value-corrected (default)",
        "years": [row["year"] for row in years],
        "periods_per_year": [len(row["market"].get("period_summaries") or []) for row in years],
        "investment": investment,
        "cost_ledger": cost,
        "errors": errors,
        "passed": not errors,
    }


# -------------------------------------------------------------- attribute ---

def attribute_goldens(golden_dir: Path = GOLDEN_DIR) -> dict[str, Any]:
    allowlist = set(json.loads((golden_dir / "doctoral_trajectory_rebaselines.json").read_text(encoding="utf-8"))["findings"])
    cases = json.loads((golden_dir / "cases.json").read_text(encoding="utf-8"))["cases"]
    report: dict[str, Any] = {"cases": {}, "errors": []}
    for case_id, case in sorted(cases.items()):
        golden = json.loads((golden_dir / case["family"] / f"{case_id}.json").read_text(encoding="utf-8"))
        rows = []
        for revision in golden["revisions"][1:]:
            delta = revision.get("delta") or {}
            by_zone = delta.get("by_zone") or {}
            gated = [d for d in delta.get("differences") or [] if d.get("zone") in ("trajectory", "accounting")]
            ids = list(revision.get("correction_ids") or [])
            findings = list(revision.get("findings") or [])
            trajectory = [d for d in gated if d["zone"] == "trajectory"]
            name = f"{case['family']}/{case_id} r{revision['revision']}"
            if gated and not ids:
                report["errors"].append(f"{name}: {len(gated)} gated column(s) without a correction id")
            if case["family"] == "doctoral" and trajectory:
                if not set(findings) & allowlist:
                    report["errors"].append(f"{name}: doctoral trajectory change without an allow-listed finding")
                if not (golden_dir / "reports" / f"{case_id}-r{revision['revision']}.json").is_file():
                    report["errors"].append(f"{name}: doctoral trajectory change without its numeric report")
            rows.append({
                "revision": revision["revision"],
                "correction_ids": ids,
                "findings": findings,
                "m5": any(i.startswith(M5_PREFIXES) for i in ids),
                "trajectory_columns": by_zone.get("trajectory", 0),
                "accounting_columns": by_zone.get("accounting", 0),
                "identity_columns": by_zone.get("identity", 0),
                "trajectory_artifacts": sorted({d["key"].split("::")[0] for d in trajectory}),
            })
        report["cases"][case_id] = {"family": case["family"], "mode": case["mode"],
                                    "latest_revision": golden["revisions"][-1]["revision"], "revisions": rows}
    report["passed"] = not report["errors"]
    return report


# ------------------------------------------------------------------- main ---

def _finite(value: Any) -> Any:
    """JSON-safe copy: non-finite floats (payback of a zero surplus) become strings."""

    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, Mapping):
        return {str(k): _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyse")
    a.add_argument("--run", nargs=2, action="append", metavar=("CASE", "OUTPUT_DIR"), required=True)
    a.add_argument("--digest-check", type=Path, help="JSON {case: {revision, gated: [...]}} from an exact golden check")
    a.add_argument("--out", type=Path)
    sub.add_parser("attribute")
    arguments = parser.parse_args(argv)
    if arguments.command == "attribute":
        report = attribute_goldens()
    else:
        check = json.loads(arguments.digest_check.read_text(encoding="utf-8")) if arguments.digest_check else {}
        runs = {}
        for case_id, output in arguments.run:
            runs[case_id] = analyse_output(Path(output))
            if case_id in check:
                runs[case_id]["golden_check"] = {"revision": check[case_id]["revision"],
                                                 "gated_differences": len(check[case_id]["gated"])}
        attribution = attribute_goldens()
        report = {"schema_version": SCHEMA, "runs": runs,
                  "attribution": {"passed": attribution["passed"], "errors": attribution["errors"],
                                  "cases": {k: v for k, v in attribution["cases"].items() if k in runs}},
                  "passed": all(r["passed"] for r in runs.values()) and attribution["passed"]
                  and all(r.get("golden_check", {}).get("gated_differences", 0) == 0 for r in runs.values())}
    text = json.dumps(_finite(report), indent=1, sort_keys=True, allow_nan=False) + "\n"
    if getattr(arguments, "out", None):
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        arguments.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
