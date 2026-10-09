from __future__ import annotations

import json
import hashlib
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# Files that record an earlier release on purpose (plan X0 S14 whitelist):
# they are not bumped with the application version.
# website/content.py and docs/PUBLICATION_PLAN.md were on this list until the
# live website source (origin/main e2a1ed4, merged in 07f56fd) dropped their
# historical 0.6.0-alpha.2 metadata block and line; they no longer record any
# earlier release, so there is nothing left in them to protect.
HISTORICAL_VERSION_RECORDS = {
    "website/static/assets/value-source-CITATION.cff": "version: 0.6.0-alpha.2",
    "website/static/assets/value-source-metadata.bib": "version = {0.6.0-alpha.2}",
}


class DocumentationConsistencyTests(unittest.TestCase):
    def test_zonal_solver_contract_fragments_match_executable_manifest(self) -> None:
        manifest = json.loads(
            (ROOT / "gridform_core/manifests/value-zonal-redispatch-balancing.json").read_text(
                encoding="utf-8"
            )
        )
        expected = manifest["solver_contract"]
        for guide in (
            "docs/MODULE_DEVELOPER_101.md",
            "docs/BUILD_YOUR_OWN_MODEL_101.md",
        ):
            text = (ROOT / guide).read_text(encoding="utf-8")
            fragments = [
                json.loads(block)["solver_contract"]
                for block in re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
                if block.lstrip().startswith("{") and '"solver_contract"' in block
            ]
            self.assertEqual(fragments, [expected], guide)

    def test_scientific_references_publish_numerical_contract(self) -> None:
        manifest = json.loads(
            (ROOT / "gridform_core/manifests/value-zonal-redispatch-balancing.json").read_text(
                encoding="utf-8"
            )
        )
        defaults = manifest["solver_contract"]["defaults"]
        objectives = (
            ("Redispatch bid cost", "GBP", "primary_bid_cost_gbp"),
            ("Absolute schedule deviation", "MWh", "secondary_schedule_deviation_mwh"),
            ("Physical throughput", "MWh", "physical_throughput_mwh"),
        )
        formula = "max(computed_tolerance, observed_degradation) / validated_ceiling"
        for reference in (
            "docs/MATHEMATICAL_REFERENCE.md",
            "docs/scientific-readiness/ZONAL_SOLVER_CONTRACT_V4.md",  # current contract (P0-8)
        ):
            text = (ROOT / reference).read_text(encoding="utf-8")
            normalized = re.sub(r"\s+", " ", text)
            for relationship in (
                "U_k     = sum(abs(c_i * x_i*))",
                "C_k     = sum(abs(c_i))",
                "gamma_n = n * epsilon / (1 - n * epsilon)",
                "epsilon_effective = max(solver_tolerance_k, bound_canonicalisation_tolerance)",
                "tau_k   = max(unit_floor_k, epsilon_effective * max(1, U_k), gamma_n * U_k, C_k * epsilon_effective)",
                "objective_k(x) <= objective_k(x*) + tau_k",
            ):
                self.assertIn(relationship, text, reference)
            if reference.endswith("MATHEMATICAL_REFERENCE.md"):
                ceilings = re.search(
                    r"The validated ceilings per half-hour are `([^ ]+) GBP`, `([^ ]+) MWh` "
                    r"schedule\s+deviation and `([^ ]+) MWh` throughput\. Recorded reference "
                    r"thresholds are\s+`([^ ]+) GBP`, `([^ ]+) MWh` and `([^ ]+) MWh` "
                    r"respectively\.",
                    text,
                )
                self.assertIsNotNone(ceilings, reference)
                expected_ceilings = [
                    defaults["validated_ceilings"]["primary_bid_cost_gbp"],
                    defaults["validated_ceilings"]["secondary_schedule_deviation_mwh"],
                    defaults["validated_ceilings"]["physical_throughput_mwh"],
                    defaults["absolute_ceilings"]["primary_bid_cost_gbp"],
                    defaults["absolute_ceilings"]["secondary_schedule_deviation_mwh"],
                    defaults["absolute_ceilings"]["physical_throughput_mwh"],
                ]
                self.assertEqual(
                    [float(value) for value in ceilings.groups()],
                    expected_ceilings,
                    reference,
                )
            else:
                for label, unit, ceiling_key in objectives:
                    validated = defaults["validated_ceilings"][ceiling_key]
                    absolute = defaults["absolute_ceilings"][ceiling_key]
                    row = re.search(
                        rf"\| {re.escape(label)} \| {unit} \| `([^`]+)` \| `([^`]+)` \|",
                        text,
                    )
                    self.assertIsNotNone(row, reference)
                    self.assertEqual(float(str(row.group(1))), validated, reference)
                    self.assertEqual(float(str(row.group(2))), absolute, reference)
            self.assertIn(formula, text, reference)
            self.assertIn(
                "numerical tolerance does not relax physical feasibility",
                normalized.lower(),
                reference,
            )
            self.assertIn("up to 10%", text, reference)
            self.assertIn("above 10% and up to 100%", text, reference)
            self.assertRegex(
                text,
                r"above 100%\s+is",
                reference,
            )

    def test_user_and_scientific_docs_do_not_promote_unvalidated_solver(self) -> None:
        manifest = json.loads(
            (ROOT / "gridform_core/manifests/value-zonal-redispatch-balancing.json").read_text(
                encoding="utf-8"
            )
        )
        registry = json.loads(
            (ROOT / "gridform_core/data/contracts/solver-validation-registry-v1.json").read_text(
                encoding="utf-8"
            )
        )
        status = next(
            entry["status"]
            for entry in registry["entries"]
            if entry["module_id"] == manifest["id"]
            and entry["module_version"] == manifest["version"]
        )
        for document in (
            "docs/USER_GUIDE.md",
            "docs/scientific-readiness/ZONAL_SOLVER_CONTRACT_V2.md",
        ):
            text = (ROOT / document).read_text(encoding="utf-8")
            self.assertIn(f"source-registered as `{status}`", text, document)
            if status != "validated":
                self.assertRegex(
                    text,
                    rf"`{re.escape(status)}`, not\s+independently validated",
                    document,
                )
                for contradictory_claim in (
                    r"(?<!not )\bis independently validated\b",
                    r"(?<!not )\bhas been independently validated\b",
                    r"\bsource-registered as validated\b",
                    r"\bbuilt-in (?:baseline|default(?: configuration)?) is "
                    r"(?!not\b)(?:independently )?validated\b",
                    r"\bbuilt-in (?:independently )?validated "
                    r"(?:baseline|default(?: configuration)?)\b",
                ):
                    self.assertNotRegex(text, contradictory_claim, document)

    def test_user_guide_explains_solver_controls_and_failure_boundary(self) -> None:
        manifest = json.loads(
            (ROOT / "gridform_core/manifests/value-zonal-redispatch-balancing.json").read_text(
                encoding="utf-8"
            )
        )
        registry = json.loads(
            (ROOT / "gridform_core/data/contracts/solver-validation-registry-v1.json").read_text(
                encoding="utf-8"
            )
        )
        user_guide = (ROOT / "docs/USER_GUIDE.md").read_text(encoding="utf-8")
        normalized_user_guide = re.sub(r"\s+", " ", user_guide)
        defaults = manifest["solver_contract"]["defaults"]
        ranges = manifest["solver_contract"]["ranges"]
        scipy_version = next(
            entry["scipy_version"]
            for entry in registry["entries"]
            if entry["module_id"] == manifest["id"]
            and entry["module_version"] == manifest["version"]
        )

        def scientific_notation(value: float) -> str:
            significand, exponent = f"{value:.0e}".split("e")
            return f"{significand}e{int(exponent)}"

        def decimal(value: float) -> str:
            return f"{value:g}"

        self.assertIn(f"SciPy `{scipy_version}`", user_guide)
        self.assertIn(f"`{defaults['method']}`", user_guide)
        allowed_methods = ", ".join(f"`{method}`" for method in ranges["method"][:-1])
        allowed_methods += f" or `{ranges['method'][-1]}`"
        self.assertIn(allowed_methods, user_guide)
        for tolerance in (
            "primal_feasibility_tolerance",
            "dual_feasibility_tolerance",
            "ipm_optimality_tolerance",
        ):
            lower, upper = ranges[tolerance]
            self.assertIn(
                f"`{scientific_notation(lower)}` through `{scientific_notation(upper)}`",
                user_guide,
            )
        warning_range = ranges["warning_fraction"]
        self.assertIn(
            "warning fraction must be greater than "
            f"`{decimal(warning_range['exclusive_minimum'])}` and at most "
            f"`{decimal(warning_range['maximum'])}`",
            normalized_user_guide.lower(),
        )
        reference_thresholds = manifest["solver_contract"]["recorded_reference_thresholds"]
        validated_ceilings = defaults["validated_ceilings"]
        for key, reference_threshold in reference_thresholds.items():
            self.assertGreater(validated_ceilings[key], 0.0)
            self.assertLess(validated_ceilings[key], reference_threshold)
        self.assertIn(
            "each validated ceiling must be greater than `0` and strictly below its "
            "read-only recorded reference threshold",
            normalized_user_guide.lower(),
        )
        self.assertIn(
            "The recorded reference thresholds are "
            f"`{reference_thresholds['primary_bid_cost_gbp']:.2f} GBP` per half-hour for "
            "primary bid cost, "
            f"`{reference_thresholds['secondary_schedule_deviation_mwh']:.2f} MWh` per "
            "half-hour for schedule deviation, and "
            f"`{reference_thresholds['physical_throughput_mwh']:.2f} MWh` per half-hour "
            "for physical throughput; they are not user-editable.",
            normalized_user_guide,
        )
        self.assertIn("no automatic fallback", user_guide)
        self.assertIn(
            "one explicit acknowledgement: it creates a new project revision",
            normalized_user_guide,
        )
        self.assertIn(
            "Numerical warning and unvalidated status propagate",
            normalized_user_guide,
        )
        self.assertIn(
            "the zonal study remains failed and preserves",
            normalized_user_guide,
        )
        self.assertIn(
            "separate copperplate or alternative-solver Study",
            normalized_user_guide,
        )

    def test_module_guides_and_catalogue_publish_v7_obligations_and_version(self) -> None:
        manifest = json.loads(
            (ROOT / "gridform_core/manifests/value-zonal-redispatch-balancing.json").read_text(
                encoding="utf-8"
            )
        )
        module_guide = (ROOT / "docs/MODULE_DEVELOPER_101.md").read_text(encoding="utf-8")
        build_guide = (ROOT / "docs/BUILD_YOUR_OWN_MODEL_101.md").read_text(encoding="utf-8")
        generated = (ROOT / "docs/generated/MODULES.md").read_text(encoding="utf-8")

        self.assertIn(f"`{manifest['version']}`", build_guide)
        self.assertIn("source-registered as `candidate`, not independently validated", build_guide)
        self.assertIn(
            "Every locked phase must emit v7 solver diagnostics for each period",
            module_guide,
        )
        self.assertIn(
            "Each period and locked phase must write v7 solver diagnostics",
            build_guide,
        )
        self.assertIn("ledger schema v7", (ROOT / "docs/USER_GUIDE.md").read_text(encoding="utf-8"))
        self.assertIn(
            f"| {manifest['id']} | balancing | {manifest['version']} |",
            generated,
        )

    def test_generated_zonal_module_row_matches_manifest_implementation_hash(self) -> None:
        manifest_path = ROOT / "gridform_core" / "manifests" / "value-zonal-redispatch-balancing.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_module = manifest["implementation"].split(":", 1)[0]
        source_path = ROOT / (source_module.replace(".", "/") + ".py")
        source_text = source_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        generated = (ROOT / "docs" / "generated" / "MODULES.md").read_text(encoding="utf-8")

        self.assertIn(
            f"| {manifest['id']} | {manifest['slot']} | {manifest['version']} | "
            f"{manifest['contract_version']} | {manifest['solver_contract']['defaults']['contract_version']} | "
            "experimental | false | "
            f"gridform_core/zonal_redispatch.py | {source_hash} |",
            generated,
        )

    def test_v7_curtailment_field_dictionary_matches_executable_schema(self) -> None:
        from gridform_core.market_ledger import SQLiteMarketLedger

        with tempfile.TemporaryDirectory() as folder:
            market = Path(folder) / "market"
            database = market / "market.sqlite"
            ledger = SQLiteMarketLedger(database, trace_level="summary")
            ledger.close()

            dictionary = json.loads(
                (market / "field-dictionary.json").read_text(encoding="utf-8")
            )
            with closing(sqlite3.connect(database)) as connection:
                executable_columns = {
                    table: {
                        str(row[1])
                        for row in connection.execute(f"PRAGMA table_info({table})")
                    }
                    for table in (
                        "vre_curtailment_period",
                        "vre_curtailment_detail",
                        "network_solver_diagnostics",
                    )
                }

        self.assertEqual(
            dictionary["ledger_schema_version"], "value.market-ledger/v7"
        )
        self.assertTrue(
            set().union(*executable_columns.values()).issubset(dictionary["fields"]),
            set().union(*executable_columns.values()).difference(dictionary["fields"]),
        )
        self.assertEqual(
            dictionary["fields"]["total_curtailment_mwh"],
            "Final VRE curtailment: realised available VRE minus final zonal dispatch.",
        )
        self.assertTrue(
            all(isinstance(semantics, str) for semantics in dictionary["fields"].values())
        )

        table_fields = {
            table: metadata["fields"]
            for table, metadata in dictionary["tables"].items()
        }
        self.assertEqual(
            set(table_fields),
            {
                "vre_curtailment_period",
                "vre_curtailment_detail",
                "network_solver_diagnostics",
            },
        )
        for table, columns in executable_columns.items():
            self.assertEqual(set(table_fields[table]), columns)
            self.assertTrue(
                all(
                    set(metadata) == {"unit", "semantics"}
                    and isinstance(metadata["unit"], str)
                    and bool(metadata["unit"].strip())
                    and isinstance(metadata["semantics"], str)
                    and bool(metadata["semantics"].strip())
                    for metadata in table_fields[table].values()
                )
            )

        period_fields = table_fields["vre_curtailment_period"]
        detail_fields = table_fields["vre_curtailment_detail"]
        diagnostics_fields = table_fields["network_solver_diagnostics"]
        self.assertEqual(period_fields["total_curtailment_mwh"]["unit"], "MWh")
        self.assertEqual(period_fields["curtailment_rate"]["unit"], "fraction")
        self.assertEqual(
            period_fields["counterfactual_realised_input_sha256"]["unit"],
            "sha256",
        )
        self.assertEqual(period_fields["year"]["unit"], "index")
        self.assertEqual(period_fields["period"]["unit"], "index")
        self.assertEqual(detail_fields["evidence_level"]["unit"], "status enum")
        self.assertIn("total_curtailment_mwh", detail_fields)
        self.assertNotIn("curtailment_rate", detail_fields)
        self.assertNotIn("evidence_level", period_fields)
        self.assertEqual(diagnostics_fields["phase_id"]["unit"], "identifier")
        self.assertEqual(diagnostics_fields["objective_unit"]["unit"], "GBP or MWh")
        self.assertEqual(diagnostics_fields["computed_tolerance"]["unit"], "GBP or MWh")
        self.assertEqual(diagnostics_fields["declared_input_sha256"]["unit"], "sha256")
        self.assertEqual(
            set(dictionary["attribution_components"]),
            {
                "economic_curtailment_mwh",
                "forecast_added_curtailment_mwh",
                "forecast_avoided_curtailment_mwh",
                "redispatch_added_curtailment_mwh",
                "redispatch_avoided_curtailment_mwh",
                "total_curtailment_mwh",
            },
        )
        self.assertEqual(
            dictionary["public_labels"]["redispatch_net_impact_mwh"],
            "Redispatch impact",
        )
        self.assertEqual(
            dictionary["aggregation"]["annual_curtailment_rate"],
            {
                "formula": (
                    "sum(total_curtailment_mwh) / "
                    "sum(realised_available_vre_mwh)"
                ),
                "denominator": "sum(realised_available_vre_mwh)",
                "weighting": "realised available VRE energy",
                "unit": "fraction",
            },
        )
        self.assertEqual(
            dictionary["compatibility_statuses"]["legacy_partial"],
            {
                "avoided_curtailment": "unavailable",
                "missing_value": None,
                "zero_is_not_a_missing_value": True,
            },
        )
        self.assertEqual(
            set(dictionary["capabilities"]),
            {
                "evidence.vre-counterfactual-snapshot/v1",
                "results.vre-curtailment-attribution/v2",
            },
        )
        self.assertTrue(dictionary["presentation"]["waterfall_is_presentation_only"])

    def test_generated_runtime_tables_are_current(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate_reference_tables.py"), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_prompt108_reports_trace_every_design_section_to_tasks_and_evidence(self) -> None:
        report = json.loads(
            (
                ROOT
                / "publication"
                / "prompt108-zonal-solver-contract-test-report.json"
            ).read_text(encoding="utf-8")
        )
        expected_sections = {
            "Purpose",
            "Baseline solver identity",
            "One-sided lexicographic tolerance",
            "Validation and execution ceilings",
            "Advanced settings and project identity",
            "Module and platform contracts",
            "Evidence and storage",
            "Frontend and documentation",
            "Error handling",
            "Verification sequence",
            "Acceptance criteria",
        }
        rows = report["design_traceability"]
        self.assertEqual({row["design_section"] for row in rows}, expected_sections)
        self.assertEqual(
            {task for row in rows for task in row["tasks"]},
            {f"Task {task}" for task in range(1, 9)},
        )
        for row in rows:
            with self.subTest(section=row["design_section"]):
                self.assertTrue(row["tasks"])
                self.assertTrue(row["executable_files"])
                self.assertTrue(row["tests"])
                self.assertTrue(row["evidence"])
                for path in row["executable_files"] + row["tests"]:
                    self.assertTrue((ROOT / path).is_file(), path)

        markdown = (
            ROOT / "publication" / "PROMPT108_ZONAL_SOLVER_CONTRACT_TEST_REPORT.md"
        ).read_text(encoding="utf-8")
        self.assertIn("## Approved design → Tasks 1–8 traceability", markdown)
        for row in rows:
            self.assertIn(f"| {row['design_section']} |", markdown)
            for reference in row["executable_files"] + row["tests"] + row["evidence"]:
                self.assertIn(f"`{reference}`", markdown, row["design_section"])

    def test_prompt107_task_mapping_uses_the_approved_plan_titles(self) -> None:
        report = json.loads(
            (
                ROOT / "publication" / "prompt107-zonal-production-gate-v2.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            report["design_task_mapping"],
            {
                "task_1": "Canonical Numerical Solver Contract",
                "task_2": "Numerical Lexicographic Optimiser and Module v1.2",
                "task_3": "Project Identity, Validation and Explicit Study Derivation",
                "task_4": "Market Ledger v7 and Status Propagation",
                "task_5": "Advanced Solver Settings and Compact Result UI",
                "task_6": "Public Documentation, Generated References and Release Product",
                "task_7": "Affected-Suite Verification and Preserved Failure Replay",
                "task_8": "Resume Task 10 Production Gate from a Fresh Output Root",
            },
        )

    def test_prompt_reports_separate_historical_gate_from_current_revalidation(
        self,
    ) -> None:
        report_paths = (
            "publication/prompt107-zonal-production-gate-v2.json",
            "publication/prompt108-zonal-solver-contract-test-report.json",
        )
        historical = {
            "classification": "STOPPED_AT_24H_UNDER_HISTORICAL_VALIDATOR",
            "validator_basis": "execution_time_validator_before_final_fixes",
            "smoke": "GO_AT_EXECUTION_TIME",
            "exact_periods": "GO_AT_EXECUTION_TIME",
            "24h": "NO-GO_AT_EXECUTION_TIME",
            "later_stages": [
                "168h:NOT_STARTED",
                "annual:NOT_STARTED",
                "two-year:NOT_STARTED",
            ],
            "is_current_public_evidence_validation": False,
        }
        current = {
            "classification": "INVALID_ORPHAN_SOLVER_DIAGNOSTICS",
            "validator": "gridform_core.market_ledger.validate_market_ledger_file",
            "database": (
                "outputs/prompt107-zonal-solver-contract-v1/runs/"
                "exact-periods/market/market.sqlite"
            ),
            "valid": False,
            "schema_version": "value.market-ledger/v7",
            "integrity": "ok",
            "errors": [
                "solver_diagnostics_orphan_period:"
                "prompt107-24h-zonal:2025:14:2022-01-01:15"
            ],
            "earliest_current_scientific_evidence_blocker": "exact-periods",
            "preserved_exact_period_scientific_evidence": "INVALID",
            "read_only_snapshot_unchanged": True,
            "exact_period_root_file_count": 8,
            "sqlite_wal_or_shm_sidecar_count": 0,
        }
        for report_path in report_paths:
            with self.subTest(report=report_path):
                report = json.loads((ROOT / report_path).read_text(encoding="utf-8"))
                self.assertEqual(
                    report["historical_execution_gate_classification"], historical
                )
                self.assertEqual(
                    report["current_public_evidence_revalidation"], current
                )
                self.assertEqual(
                    report["future_exact_period_executor"],
                    {
                        "source_status": "FIXED_AND_TESTED",
                        "preserved_history_rerun": False,
                        "preserved_history_reinterpreted": False,
                    },
                )

    def test_prompt_markdown_qualifies_preserved_exact_period_gate_status(
        self,
    ) -> None:
        exact_error = (
            "solver_diagnostics_orphan_period:"
            "prompt107-24h-zonal:2025:14:2022-01-01:15"
        )
        for report_path in (
            "publication/PROMPT107_ZONAL_PRODUCTION_GATE_V2.md",
            "publication/PROMPT108_ZONAL_SOLVER_CONTRACT_TEST_REPORT.md",
        ):
            with self.subTest(report=report_path):
                markdown = (ROOT / report_path).read_text(encoding="utf-8")
                normalized = " ".join(markdown.split())
                self.assertIn("Historical execution-time gate classification", markdown)
                self.assertIn("Current public evidence revalidation", markdown)
                self.assertIn(exact_error, markdown)
                self.assertIn(
                    "not a current preserved exact-period scientific GO", normalized
                )
                self.assertIn(
                    "fixed and tested for a future fresh run", normalized
                )

    def test_every_shipped_module_is_named_in_reference(self) -> None:
        reference = (ROOT / "docs" / "MATHEMATICAL_REFERENCE.md").read_text(encoding="utf-8")
        generated = (ROOT / "docs" / "generated" / "MODULES.md").read_text(encoding="utf-8")
        for path in (ROOT / "gridform_core" / "manifests").glob("*.json"):
            module_id = json.loads(path.read_text(encoding="utf-8"))["id"]
            self.assertIn(module_id, reference + generated)

    def test_versions_are_consistent(self) -> None:
        # X0 S14: one application version everywhere except historical
        # records (HISTORICAL_VERSION_RECORDS), which keep the version they
        # describe.  The ledger is the source.
        ledger = json.loads((ROOT / "docs" / "release" / "VERSION_LEDGER.json").read_text(encoding="utf-8"))
        node_expected = ledger["application_version"]["current"]
        py_expected = ledger["application_version"]["current_python"]
        self.assertEqual((node_expected, py_expected), ("0.7.0-alpha.1", "0.7.0a1"))
        self.assertEqual(ledger["application_version"]["bumps"][-1]["to"], node_expected)
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, flags=re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(str(match.group(1)), py_expected)
        self.assertEqual(json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"], node_expected)
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["version"], node_expected)
        self.assertEqual(lock["packages"][""]["version"], node_expected)
        self.assertEqual(
            json.loads((ROOT / "packaging" / "windows-pilot" / "product.json").read_text(encoding="utf-8"))["version"],
            node_expected,
        )
        from gridform_core.runtime_paths import APPLICATION_VERSION
        from gridform_core.builtin.scheme_c_1000twh.psm import REMOVAL_VERSION

        self.assertEqual(APPLICATION_VERSION, node_expected)
        self.assertEqual(REMOVAL_VERSION, "0.8.0")
        current_lines = {
            "README.md": node_expected,
            "docs/USER_GUIDE.md": f"This guide covers VALUE Network Extensions {node_expected}.",
            "docs/USER_GUIDE_ZH.md": f"本手册对应 VALUE Network Extensions {node_expected}。",
            "docs/INSTALLATION.md": f"The\nsource tree is now {node_expected}",
            "docs/MATHEMATICAL_REFERENCE.md": f"Version {node_expected}, October 2026",
            "docs/VALIDATION_AND_CLAIMS.md": f"VALUE Network Extensions {node_expected} source",
            "docs/frontend/EXPANDED_FRONTEND_FIELD_MAP.md": f"Version: VALUE Network Extensions {node_expected}",
            "packaging/windows-pilot/ValueInstaller.cs": f'key.SetValue("DisplayVersion", "{node_expected}");',
            "gridform_core/builtin/scheme_c_1000twh/factory.py": "Removal is scheduled for VALUE 0.8.0.",
        }
        for relative, expected in current_lines.items():
            self.assertIn(expected, (ROOT / relative).read_text(encoding="utf-8"), relative)
        # Historical records keep the version they describe (plan X0 S14).
        for relative, recorded in HISTORICAL_VERSION_RECORDS.items():
            self.assertIn(recorded, (ROOT / relative).read_text(encoding="utf-8"), relative)

    def test_claims_do_not_overstate_validation(self) -> None:
        texts = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "README.md", "docs/MATHEMATICAL_REFERENCE.md", "docs/VALIDATION_AND_CLAIMS.md"
            )
        ).lower()
        forbidden = (
            r"globally optimal cem",
            r"exact reproduction[^\n]{0,80}(?:passes|passed|proven)",
            r"public release decision is `?go`?",
            r"smoke (?:test )?(?:proves|publishes) annual economics",
        )
        for pattern in forbidden:
            self.assertIsNone(re.search(pattern, texts), pattern)
        self.assertIn("not_evaluated", texts)
        self.assertIn("single-node", texts)
        self.assertIn("no internal transmission", texts)


if __name__ == "__main__":
    unittest.main()
