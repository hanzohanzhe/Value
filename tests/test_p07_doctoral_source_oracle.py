"""P0-7 S1: in-repo source oracle for the doctoral source investment rule.

``doctoral_policy.evaluate_investment_accounts`` (the typed source rule behind
``decide_doctoral_investment(basis='source')``) is compared value by value with
the original Scheme C decision code kept read-only in the repository:
``gridform_core/builtin/scheme_c_1000twh/compat/modular_investment_support.py``
(byte-identical to its 35aadb3 blob; the sha256 is pinned below).

Only these pieces of ``analyze_investment`` are extracted with ``ast`` and run:

* the ``df_analysis['payback_years']`` (2257) and ``df_analysis['ROI']``
  (2270) assignments;
* the nested ``assign_recommendation`` (2273), ``_profit_based_addition_mw``
  (2330) and ``calculate_new_capacity`` (2337);
* the technology lists ``vre_battery_techs = [...]`` (2381) and
  ``battery_techs = {...}`` (2383), and the proportional VRE / battery scaling
  loop ``for tech_type in vre_battery_techs`` (2385-2435).

``_sec.EXPANDABLE_STORAGE_KEYS`` is read from the preserved
``compat/modular_storage_expansion_cap.py`` (sha256 pinned, equal to its
35aadb3 blob): ``tuple(BATTERY_ELIGIBLE_TIERS.keys())`` with the dict literal
evaluated by ``ast.literal_eval``. The annual entry point, its I/O, dispatch
and configuration loading never run; configuration (per-technology CAPEX,
thermal High multiplier, annual caps) is fixture input. No value from the
candidate (``doctoral_policy``) enters the oracle namespace; a separate test
only checks that the source technology lists equal the candidate constants.

Cross-check: ``compat/case3.py`` (``analyze_investment_case3``, sha256 pinned,
equal to its 35aadb3 blob) is the in-repo copy of the doctoral Case 3 code that
``doctoral_policy`` cites (896-904, 991-1029, 1168-1216). Its
``assign_recommendation`` (896), ``_profit_based_addition_mw`` (989),
``calculate_new_capacity`` (996), payback / ROI assignments, technology lists
and scaling loop (1168) are asserted ``ast.dump``-equal to the extracted
pieces, so the oracle stands for Case 3 as well. The author's private file
(sha256 e0e11057..., AUTHORITATIVE_SOURCE.json) differs from case3.py by sha
only; it is not on this host. This replaces, for this host, the external-tree
oracle of ``tests/test_doctoral_investment_alignment.py`` (quarantined, R2-09).

Six cases agree value by value. A seventh documents the one approved deviation
of the typed rule: a depletion in a VRE technology whose positive proposals are
scaled is overwritten to "no change" by the source loop, and kept by the typed
rule (doctoral_policy module docstring, "approved defect correction").

This is the oracle for the in-repo source rule only. The frozen doctoral
profile (Q1) keeps the HEAD v2 ``decide()``, recorded separately in
``tests/fixtures/p07/head_decide_record.json``. Decision A6: the ROI / payback
tiers are undiscounted by design (constant base-year money).
"""
from __future__ import annotations

import ast
import hashlib
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from gridform_core.builtin.scheme_c_1000twh import doctoral_policy

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "gridform_core/builtin/scheme_c_1000twh/compat/modular_investment_support.py"
# sha256 of the 35aadb3 blob; compat/ is the read-only preserved source.
SOURCE_SHA256 = "93aaea361ef48c326eb831f631a7237733a8df87de70ecc216c0d586f6d3d076"
SOURCE_FUNCTION = "analyze_investment"
NESTED_FUNCTIONS = {
    "assign_recommendation": (2273, 2281),
    "_profit_based_addition_mw": (2330, 2335),
    "calculate_new_capacity": (2337, 2371),
}
FRAME_ASSIGNMENTS = {"df_analysis['payback_years']": 2257, "df_analysis['ROI']": 2270}
TECHNOLOGY_LISTS = {"vre_battery_techs": 2381, "battery_techs": 2383}
SCALING_LOOP_SPAN = (2385, 2435)
STORAGE_CAP_PATH = ROOT / "gridform_core/builtin/scheme_c_1000twh/compat/modular_storage_expansion_cap.py"
STORAGE_CAP_SHA256 = "74e4c9c85573268577438dbedbe2c2b85a41267dbbb40a0350d350447973b43f"
STORAGE_TIERS_LINE, STORAGE_KEYS_LINE = 77, 133
CASE3_PATH = ROOT / "gridform_core/builtin/scheme_c_1000twh/compat/case3.py"
CASE3_SHA256 = "68baa3c61630e3959087ba863e1ba697ec3e3c76a4eb1384d8751de4f9e77dd8"
CASE3_FUNCTION = "analyze_investment_case3"
CASE3_LINES = {
    "assign_recommendation": [896], "_profit_based_addition_mw": [989], "calculate_new_capacity": [996],
    "df_analysis['payback_years']": [882, 945], "df_analysis['ROI']": [894, 950],
    "vre_battery_techs": [1093], "battery_techs": [1097], "scaling_loop": [1168],
}
THERMAL_HIGH_MULTIPLIER = 1.01  # source regulated target for CCGT/OCGT/bio_and_waste; policy default


def _pinned_tree(path, sha256):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != sha256:
        raise AssertionError(f"preserved source {path.name} changed: {digest}")
    return ast.parse(raw.decode("utf-8-sig"), filename=str(path))


def _function_body(tree, name):
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise AssertionError(f"{name} is not unique in the preserved source")
    return matches[0].body


def _decision_pieces(body):
    """Decision pieces of an analyze_investment body, keyed by name, in source order."""
    pieces: dict[str, list] = {}
    for node in body:
        if isinstance(node, ast.FunctionDef) and node.name in NESTED_FUNCTIONS:
            pieces.setdefault(node.name, []).append(node)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = ast.unparse(node.targets[0])
            if target in FRAME_ASSIGNMENTS or target in TECHNOLOGY_LISTS:
                pieces.setdefault(target, []).append(node)
        elif (isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == "tech_type"
              and isinstance(node.iter, ast.Name) and node.iter.id == "vre_battery_techs"):
            pieces.setdefault("scaling_loop", []).append(node)
    return pieces


def source_storage_keys():
    """``_sec.EXPANDABLE_STORAGE_KEYS`` evaluated from the preserved module text."""
    tree = _pinned_tree(STORAGE_CAP_PATH, STORAGE_CAP_SHA256)
    tiers = [node for node in tree.body if isinstance(node, ast.AnnAssign)
             and ast.unparse(node.target) == "BATTERY_ELIGIBLE_TIERS"]
    keys = [node for node in tree.body if isinstance(node, ast.Assign) and len(node.targets) == 1
            and ast.unparse(node.targets[0]) == "EXPANDABLE_STORAGE_KEYS"]
    if ([node.lineno for node in tiers], [node.lineno for node in keys]) != ([STORAGE_TIERS_LINE], [STORAGE_KEYS_LINE]):
        raise AssertionError("storage expansion keys moved or are not unique")
    if ast.unparse(keys[0].value) != "tuple(BATTERY_ELIGIBLE_TIERS.keys())":
        raise AssertionError("EXPANDABLE_STORAGE_KEYS is no longer the keys of BATTERY_ELIGIBLE_TIERS")
    return tuple(ast.literal_eval(tiers[0].value).keys())


def _source_nodes():
    tree = _pinned_tree(SOURCE_PATH, SOURCE_SHA256)
    body = _function_body(tree, SOURCE_FUNCTION)
    functions = [node for node in body if isinstance(node, ast.FunctionDef) and node.name in NESTED_FUNCTIONS]
    spans = {node.name: (node.lineno, node.end_lineno) for node in functions}
    if spans != NESTED_FUNCTIONS:
        raise AssertionError(f"nested decision functions moved: {spans}")
    assignments = [
        node for node in body
        if isinstance(node, ast.Assign) and len(node.targets) == 1
        and ast.unparse(node.targets[0]) in FRAME_ASSIGNMENTS
    ]
    if {ast.unparse(node.targets[0]): node.lineno for node in assignments} != FRAME_ASSIGNMENTS:
        raise AssertionError("ROI / payback frame assignments moved or are not unique")
    lists = [
        node for node in body
        if isinstance(node, ast.Assign) and len(node.targets) == 1
        and ast.unparse(node.targets[0]) in TECHNOLOGY_LISTS
    ]
    if {ast.unparse(node.targets[0]): node.lineno for node in lists} != TECHNOLOGY_LISTS or len(lists) != 2:
        raise AssertionError("source technology lists moved or are not unique")
    loops = _decision_pieces(body).get("scaling_loop", [])
    if len(loops) != 1 or (loops[0].lineno, loops[0].end_lineno) != SCALING_LOOP_SPAN:
        raise AssertionError("source proportional scaling loop moved or is not unique")
    return assignments, functions, lists + loops


def source_technology_lists():
    """The literal ``vre_battery_techs`` and ``battery_techs`` of the source."""
    _, _, nodes = _source_nodes()
    namespace: dict = {}
    exec(compile(ast.Module(body=[node for node in nodes if isinstance(node, ast.Assign)], type_ignores=[]),
                 "<source-technology-lists>", "exec"), namespace)
    return namespace["vre_battery_techs"], namespace["battery_techs"]


def source_oracle(accounts, caps):
    """Run the extracted source code on a fixture frame; returns per-account outcome."""
    assignments, functions, loops = _source_nodes()
    capex_by_tech: dict[str, float] = {}
    for row in accounts:
        tech, capex = row["technology"], float(row["capital_cost_per_mw_gbp"])
        # The source reads CAPEX per MW by technology (config.capital_costs_per_mw).
        if capex_by_tech.setdefault(tech, capex) != capex:
            raise AssertionError("source oracle needs one CAPEX per technology")
    frame = pd.DataFrame(
        {
            "asset_type": [row["technology"] for row in accounts],
            "current_capacity": [float(row["current_capacity_mw"]) for row in accounts],
            "net_revenue": [float(row["net_revenue_gbp"]) for row in accounts],
            "capital_cost": [float(row["replacement_capital_gbp"]) for row in accounts],
            "preferred_rate": [float(row["preferred_rate"]) for row in accounts],
            "target_payback": [float(row["target_payback_years"]) for row in accounts],
        },
        index=pd.Index([row["account_id"] for row in accounts], name="asset_name"),
    )
    namespace = {
        "pd": pd,
        "np": np,
        "df_analysis": frame,
        "config": SimpleNamespace(capital_costs_per_mw=dict(capex_by_tech)),
        "regulated_targets": {
            "CCGT": THERMAL_HIGH_MULTIPLIER, "OCGT": THERMAL_HIGH_MULTIPLIER,
            "bio_and_waste": THERMAL_HIGH_MULTIPLIER, **{str(k): float(v) for k, v in caps.items()},
        },
        "_sec": SimpleNamespace(EXPANDABLE_STORAGE_KEYS=source_storage_keys()),
    }
    exec(compile(ast.Module(body=assignments + functions, type_ignores=[]),
                 "<source-investment-functions>", "exec"), namespace)
    frame["recommendation"] = frame.apply(namespace["assign_recommendation"], axis=1)
    frame["suggested_new_capacity"] = frame.apply(namespace["calculate_new_capacity"], axis=1)
    exec(compile(ast.Module(body=loops, type_ignores=[]), "<source-investment-scaling>", "exec"), namespace)
    result = namespace["df_analysis"]
    return {
        str(name): {
            "recommendation": str(row["recommendation"]),
            "current_capacity_mw": float(row["current_capacity"]),
            "delta_mw": float(row["suggested_new_capacity"]) - float(row["current_capacity"]),
        }
        for name, row in result.iterrows()
    }


def candidate(accounts, caps):
    rows = doctoral_policy.evaluate_investment_accounts(accounts, caps)
    return {
        row["account_id"]: {
            "recommendation": row["recommendation"],
            "delta_mw": float(row["accepted_addition_mw"]) - float(row["retirement_mw"]),
            "accepted_addition_mw": float(row["accepted_addition_mw"]),
            "retirement_mw": float(row["retirement_mw"]),
        }
        for row in rows
    }


def account(name, tech, capacity, net, capex, *, preferred=0.08, target=25.0):
    return {
        "account_id": name, "technology": tech, "current_capacity_mw": float(capacity),
        "net_revenue_gbp": float(net), "capital_cost_per_mw_gbp": float(capex),
        "replacement_capital_gbp": float(capacity) * float(capex),
        "preferred_rate": preferred, "target_payback_years": target,
    }


# Six agreement cases. Comments give the hand-computed outcome.
CASES = {
    "tier_boundaries_uncapped_gas": (
        [
            # ROI 0.09 > 0.08 -> High, +9 MW (net / CAPEX).
            account("gas-high", "gas", 100, 9e6, 1e6),
            # ROI == 0.08 exactly: strict ROI test fails, payback 12.5 <= 25 -> Profit, +8 MW.
            account("gas-roi-equal", "gas", 100, 8e6, 1e6),
            # payback == 25 exactly: inclusive -> Profit, +4 MW.
            account("gas-payback-equal", "gas", 100, 4e6, 1e6),
            # payback 25.64 > 25 and net >= 0 -> Do_Nothing.
            account("gas-hold", "gas", 100, 3.9e6, 1e6),
            # net < 0 -> Deplete, retire 1.825e6 x 25 / 1e6 = 45.625 MW.
            account("gas-loss", "gas", 100, -1.825e6, 1e6),
        ],
        {},
    ),
    "thermal_high_one_percent": (
        [
            account("ccgt", "CCGT", 200, 3e7, 1e6),
            account("ocgt", "OCGT", 50, 1e7, 5e5),
            account("bio", "bio_and_waste", 80, 2e7, 2e6, preferred=0.06, target=20.0),
        ],
        {},
    ),
    "vre_proportional_scaling_under_one_cap": (
        [
            # ROI 0.04, payback 25 == target -> Profit, request 12 MW.
            account("solar-a", "solar", 300, 6e6, 5e5),
            # ROI 0.03, payback 33.3 > 25 -> Do_Nothing (still in the source loop, adds 0).
            account("solar-b", "solar", 100, 1.5e6, 5e5),
            # ROI 0.1 -> High, request 5 MW. 17 MW requested against cap 10 -> scale 10/17.
            account("solar-c", "solar", 50, 2.5e6, 5e5),
            # ROI 0.1 -> High, 12 MW under the onshore cap of 40 -> unscaled.
            account("onshore-a", "onshore", 120, 1.2e7, 1e6, target=30.0),
        ],
        {"solar": 10.0, "onshore": 40.0},
    ),
    "storage_high_cap_profit_floor_and_profit_tier": (
        [
            # 1c High: ROI 0.2 and 0.1, profit floors 20 and 2.5 MW, requests max(cap 15, floor) = 20 and 15.
            # allowed = max(floors 22.5, min(35, 15)) = 22.5, scale 22.5/35; bat-a binds at its floor 20,
            # bat-b gets 15 x 22.5/35 (the source per-row floor can overspend the cap; kept here).
            account("bat-a", "1c_battery", 100, 1e7, 5e5, target=10.0),
            account("bat-b", "1c_battery", 25, 1.25e6, 5e5, target=10.0),
            # 1c Profit (ROI 0.12 <= 0.15, payback 8.33 <= 10): +4.8 MW, outside the High-only scaling.
            account("bat-c", "1c_battery", 40, 2.4e6, 5e5, preferred=0.15, target=10.0),
            # hydrogen High (ROI 0.1) with cap 30 > floor 6: requests and receives the cap.
            account("h2-a", "hydrogen_battery", 60, 6e6, 1e6),
        ],
        {"1c_battery": 15.0, "hydrogen_battery": 30.0},
    ),
    "offshore_proportional_scaling": (
        [
            # ROI 0.05 <= 0.08, payback 20 <= 30 -> Profit, request 4e7 / 2e6 = 20 MW.
            account("off-a", "offshore", 400, 4e7, 2e6, target=30.0),
            # ROI 0.06, payback 16.67 <= 30 -> Profit, request 12 MW. 32 MW against cap 16 -> scale 1/2.
            account("off-b", "offshore", 200, 2.4e7, 2e6, target=30.0),
        ],
        {"offshore": 16.0},
    ),
    "depletion_without_positive_scaling": (
        [
            # offshore: one loss, one hold; no positive proposal so the loop skips the technology.
            account("off-loss", "offshore", 400, -2e6, 2e6, target=30.0),
            account("off-hold", "offshore", 200, 1e6, 2e6, target=30.0),
            # storage loss: the battery loop only rescales Invest_High rows.
            account("bat-loss", "0.5c_battery", 50, -5e5, 1e6, target=10.0),
            # thermal loss capped at current capacity.
            account("ccgt-loss", "CCGT", 10, -1e9, 1e6),
        ],
        {"offshore": 25.0, "0.5c_battery": 5.0},
    ),
}

# The approved deviation: solar depletion in a technology with scaled positive proposals.
DEVIATION_CASE = (
    [
        account("solar-high", "solar", 100, 1e7, 1e6),
        account("solar-loss", "solar", 100, -2e6, 1e6),
    ],
    {"solar": 4.0},
)


def _close(source_delta, candidate_delta, current):
    """The source forms (current + x) - current; allow its rounding, nothing more."""
    if source_delta == candidate_delta:
        return True
    tolerance = 2.0 * math.ulp(abs(current) + abs(candidate_delta))
    return abs(source_delta - candidate_delta) <= tolerance


class DoctoralSourceOracleTest(unittest.TestCase):
    def test_preserved_source_is_pinned_and_extracted_spans_match_the_plan(self):
        assignments, functions, nodes = _source_nodes()
        self.assertEqual(len(assignments), 2)
        self.assertEqual({node.name for node in functions}, set(NESTED_FUNCTIONS))
        self.assertEqual([node.lineno for node in nodes], [2381, 2383, 2385])
        self.assertEqual((nodes[-1].lineno, nodes[-1].end_lineno), SCALING_LOOP_SPAN)

    def test_source_technology_lists_equal_the_candidate_constants(self):
        """The oracle reads its lists from the source; the candidate must agree as sets."""
        vre_battery, battery = source_technology_lists()
        storage_keys = source_storage_keys()
        self.assertEqual(vre_battery, ["solar", "onshore", "offshore",
                                       "1c_battery", "0.5c_battery", "0.25c_battery", "hydrogen_battery"])
        self.assertEqual(set(battery), set(doctoral_policy.STORAGE_TECHNOLOGIES))
        self.assertEqual(set(storage_keys), set(doctoral_policy.STORAGE_TECHNOLOGIES))
        self.assertEqual(set(vre_battery) - set(battery), set(doctoral_policy.VRE_TECHNOLOGIES))
        self.assertEqual(set(vre_battery), set(doctoral_policy.VRE_TECHNOLOGIES) | set(doctoral_policy.STORAGE_TECHNOLOGIES))

    def test_case3_decision_pieces_are_ast_identical_to_the_extracted_source(self):
        """compat/case3.py is the in-repo Case 3 copy cited by doctoral_policy."""
        case3 = _decision_pieces(_function_body(_pinned_tree(CASE3_PATH, CASE3_SHA256), CASE3_FUNCTION))
        source = _decision_pieces(_function_body(_pinned_tree(SOURCE_PATH, SOURCE_SHA256), SOURCE_FUNCTION))
        self.assertEqual({key: [node.lineno for node in nodes] for key, nodes in case3.items()}, CASE3_LINES)
        self.assertEqual(set(source), set(CASE3_LINES))
        for key, nodes in case3.items():
            self.assertEqual(len(source[key]), 1, key)
            for node in nodes:
                with self.subTest(piece=key, case3_line=node.lineno):
                    self.assertEqual(ast.dump(node), ast.dump(source[key][0]))

    def test_six_cases_agree_value_by_value(self):
        for name, (accounts, caps) in CASES.items():
            with self.subTest(name):
                source = source_oracle(accounts, caps)
                typed = candidate(accounts, caps)
                self.assertEqual(list(source), list(typed))
                for account_id, expected in source.items():
                    got = typed[account_id]
                    self.assertEqual(got["recommendation"], expected["recommendation"], account_id)
                    self.assertTrue(
                        _close(expected["delta_mw"], got["delta_mw"], expected["current_capacity_mw"]),
                        f"{name}/{account_id}: source {expected['delta_mw']!r} typed {got['delta_mw']!r}",
                    )

    def test_cases_exercise_every_tier_and_the_binding_rules(self):
        """Guard against a vacuous oracle: hand-computed anchors per case."""
        out = {name: candidate(accounts, caps) for name, (accounts, caps) in CASES.items()}
        tiers = out["tier_boundaries_uncapped_gas"]
        self.assertEqual(
            {key: row["recommendation"] for key, row in tiers.items()},
            {"gas-high": "Invest_High", "gas-roi-equal": "Invest_Profit", "gas-payback-equal": "Invest_Profit",
             "gas-hold": "Do_Nothing", "gas-loss": "Deplete"})
        self.assertEqual(tiers["gas-high"]["delta_mw"], 9.0)
        self.assertEqual(tiers["gas-payback-equal"]["delta_mw"], 4.0)
        self.assertEqual(tiers["gas-loss"]["delta_mw"], -45.625)
        thermal = out["thermal_high_one_percent"]
        self.assertTrue(all(row["recommendation"] == "Invest_High" for row in thermal.values()))
        self.assertAlmostEqual(thermal["ccgt"]["delta_mw"], 2.0, places=12)
        self.assertAlmostEqual(thermal["bio"]["delta_mw"], 0.8, places=12)
        vre = out["vre_proportional_scaling_under_one_cap"]
        self.assertEqual([vre[key]["recommendation"] for key in ("solar-a", "solar-b", "solar-c", "onshore-a")],
                         ["Invest_Profit", "Do_Nothing", "Invest_High", "Invest_High"])
        self.assertAlmostEqual(vre["solar-a"]["delta_mw"], 120.0 / 17.0, places=12)
        self.assertAlmostEqual(vre["solar-c"]["delta_mw"], 50.0 / 17.0, places=12)
        self.assertEqual(vre["solar-b"]["delta_mw"], 0.0)
        self.assertEqual(vre["onshore-a"]["delta_mw"], 12.0)
        storage = out["storage_high_cap_profit_floor_and_profit_tier"]
        self.assertEqual(storage["bat-c"]["recommendation"], "Invest_Profit")
        self.assertEqual(storage["bat-c"]["delta_mw"], 4.8)
        self.assertEqual([storage[key]["recommendation"] for key in ("bat-a", "bat-b", "h2-a")], ["Invest_High"] * 3)
        self.assertEqual(storage["bat-a"]["delta_mw"], 20.0)
        self.assertAlmostEqual(storage["bat-b"]["delta_mw"], 15.0 * 22.5 / 35.0, places=12)
        self.assertEqual(storage["h2-a"]["delta_mw"], 30.0)
        offshore = out["offshore_proportional_scaling"]
        self.assertEqual([offshore[key]["recommendation"] for key in ("off-a", "off-b")], ["Invest_Profit"] * 2)
        self.assertEqual((offshore["off-a"]["delta_mw"], offshore["off-b"]["delta_mw"]), (10.0, 6.0))
        loss = out["depletion_without_positive_scaling"]
        self.assertEqual(loss["off-loss"]["delta_mw"], -30.0)
        self.assertEqual(loss["bat-loss"]["delta_mw"], -5.0)
        self.assertEqual(loss["ccgt-loss"]["delta_mw"], -10.0)

    def test_approved_deviation_depletion_survives_positive_scaling(self):
        accounts, caps = DEVIATION_CASE
        source = source_oracle(accounts, caps)
        typed = candidate(accounts, caps)
        self.assertEqual(source["solar-loss"]["recommendation"], "Deplete")
        self.assertEqual(typed["solar-loss"]["recommendation"], "Deplete")
        # Source loop: clip(lower=0) then current + 0 * scale overwrites the depletion.
        self.assertEqual(source["solar-loss"]["delta_mw"], 0.0)
        # Typed rule keeps it: 2e6 x 25 / 1e6 = 50 MW.
        self.assertEqual(typed["solar-loss"]["retirement_mw"], 50.0)
        self.assertEqual(typed["solar-loss"]["delta_mw"], -50.0)
        # Positive proposals still agree.
        self.assertTrue(_close(source["solar-high"]["delta_mw"], typed["solar-high"]["delta_mw"], 100.0))
        self.assertEqual(typed["solar-high"]["delta_mw"], 4.0)
        self.assertIn("approved defect correction", doctoral_policy.__doc__)


if __name__ == "__main__":
    unittest.main()
