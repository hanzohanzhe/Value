import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "source_release_scan", ROOT / "scripts" / "source_release_scan.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

# P0-1 local API security boundary files (grows with S3/S4/S7).
P0_1_RELEASE_FILES = (
    "backend/api_session.py",
    "tests/test_api_session.py",
)


class SourceReleaseTreeTests(unittest.TestCase):
    def test_zonal_solver_contract_sources_are_release_members(self):
        members = {
            path.relative_to(ROOT).as_posix()
            for path in MODULE.release_members(ROOT)
        }
        required = {
            "gridform_core/zonal_redispatch.py",
            "gridform_core/data/contracts/network-solver-contract-v1.schema.json",
            "gridform_core/data/contracts/solver-validation-registry-v1.json",
            "gridform_core/data/contracts/market-ledger-v7.schema.sql",
            "docs/superpowers/specs/2026-08-23-zonal-solver-contract-v1-design.md",
            "docs/scientific-readiness/ZONAL_SOLVER_CONTRACT_V1.md",
            "docs/scientific-readiness/prompts/108-zonal-solver-contract-v1.md",
            "scripts/generate_reference_tables.py",
            "tests/test_documentation_consistency.py",
            "tests/test_source_release_tree.py",
        }
        self.assertTrue(required.issubset(members), required.difference(members))

    def test_run_lifecycle_sources_are_release_members(self):
        """P0-3: the worker entry, lease, status API and supervisor ship with
        the backend; without them an installed VALUE cannot start a Run."""
        members = {
            path.relative_to(ROOT).as_posix()
            for path in MODULE.release_members(ROOT)
        }
        lifecycle = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "backend" / "lifecycle").glob("*.py")
        }
        required = lifecycle | {"backend/run_supervisor.py", "backend/worker_entry.py"}
        self.assertGreaterEqual(len(lifecycle), 8)
        self.assertTrue(required.issubset(members), required.difference(members))
        manifest = json.loads((ROOT / "source-release-manifest.json").read_text(encoding="utf-8"))
        listed = set(json.dumps(manifest).split('"'))
        self.assertTrue(required.issubset(listed), required.difference(listed))

    def test_local_api_security_sources_are_release_members(self):
        """P0-1: the session module (and, from S3 on, the UI gateway) ship
        with every release; the pilot builder copies only allowlisted files,
        so a missing entry would silently drop it from installers."""
        members = {
            path.relative_to(ROOT).as_posix()
            for path in MODULE.release_members(ROOT)
        }
        required = set(P0_1_RELEASE_FILES)
        self.assertTrue(required.issubset(members), required.difference(members))
        manifest = json.loads((ROOT / "source-release-manifest.json").read_text(encoding="utf-8"))
        listed = set(json.dumps(manifest).split('"'))
        self.assertTrue(required.issubset(listed), required.difference(listed))

    def test_prompt107_and_prompt108_authoritative_reports_are_release_members(self):
        members = {
            path.relative_to(ROOT).as_posix()
            for path in MODULE.release_members(ROOT)
        }
        required = {
            "publication/PROMPT107_ZONAL_PRODUCTION_GATE_V2.md",
            "publication/prompt107-zonal-production-gate-v2.json",
            "publication/PROMPT108_ZONAL_SOLVER_CONTRACT_TEST_REPORT.md",
            "publication/prompt108-zonal-solver-contract-test-report.json",
        }
        self.assertTrue(required.issubset(members), required.difference(members))

    def test_retained_real_prompt107_input_is_local_only(self):
        retained = (
            "tests/fixtures/zonal_solver_failures/period-2025-14.json.gz"
        )
        manifest = json.loads(
            (ROOT / "source-release-manifest.json").read_text(encoding="utf-8")
        )
        members = {
            path.relative_to(ROOT).as_posix()
            for path in MODULE.release_members(ROOT)
        }

        self.assertIn(".json.gz", manifest["exclude_suffixes"])
        self.assertNotIn(retained, members)

    def test_content_scan_rejects_retained_real_input_even_if_suffix_exclusion_is_removed(self):
        manifest = json.loads(
            (ROOT / "source-release-manifest.json").read_text(encoding="utf-8")
        )
        manifest["exclude_suffixes"] = [
            suffix
            for suffix in manifest["exclude_suffixes"]
            if suffix != ".json.gz"
        ]

        with mock.patch.object(MODULE, "_load_manifest", return_value=manifest):
            report = MODULE.scan(ROOT)

        retained = "tests/fixtures/zonal_solver_failures/period-2025-14.json.gz"
        self.assertFalse(report["passed"])
        self.assertIn(retained, report["local_only_content_members"])
        self.assertTrue(
            any("Local-only content" in error for error in report["errors"]),
            report["errors"],
        )

    def test_vre_attribution_sources_ship_without_run_databases(self):
        members = {
            path.relative_to(ROOT).as_posix()
            for path in MODULE.release_members(ROOT)
        }
        required = {
            "gridform_core/vre_curtailment_attribution.py",
            "gridform_core/data/contracts/market-ledger-v6.schema.sql",
            "app/features/network/CurtailmentWaterfall.tsx",
            "docs/superpowers/specs/2026-08-22-vre-curtailment-attribution-v2-design.md",
            "docs/superpowers/plans/2026-08-22-vre-curtailment-attribution-v2.md",
            "docs/scientific-readiness/prompts/107-vre-curtailment-attribution-v2.md",
        }
        self.assertTrue(required.issubset(members), required.difference(members))

        run_database_names = {
            "market.sqlite",
            "project-index.sqlite",
            "annual-carbon-ledger.sqlite",
        }
        manifest = json.loads(
            (ROOT / "source-release-manifest.json").read_text(encoding="utf-8")
        )
        self.assertTrue(
            run_database_names.issubset(set(manifest["exclude_names"])),
            run_database_names.difference(manifest["exclude_names"]),
        )
        self.assertFalse(
            {member for member in members if Path(member).name in run_database_names}
        )

    def test_allowlisted_source_product_is_complete_and_excludes_local_state(self):
        report = MODULE.scan(ROOT)
        self.assertTrue(report["passed"], report["errors"])
        self.assertGreater(report["member_count"], 100)
        self.assertFalse(report["forbidden_members"])
        self.assertFalse(report["local_only_content_members"])
        self.assertEqual(report["frontend_lock_authority"], "npm package-lock.json")
        self.assertIn("uk_public_data", report["separate_products"])
        self.assertIn("github_checkout_ready", report["git_tracking"])

    def test_vite_build_has_no_author_worktree_only_input(self):
        members = {
            path.relative_to(ROOT).as_posix()
            for path in MODULE.release_members(ROOT)
        }
        self.assertIn(".openai/hosting.json", members)
        for pack_id in (
            "value-101-baseline-v1",
            "value-101-windy-v1",
            "value-101-high-demand-v1",
            "value-101-network-v1",
        ):
            self.assertIn(f"data-packs/{pack_id}/manifest.json", members)
        vite = (ROOT / "vite.config.ts").read_text(encoding="utf-8")
        self.assertNotIn('from "./build/', vite)
        self.assertIn('from "@openai/sites-vite-plugin"', vite)
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(
            package["devDependencies"]["@openai/sites-vite-plugin"],
            "0.2.0",
        )

    def test_exact_hash_catalogues_keep_lf_checkout_bytes(self):
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        expected = {
            "data-packs/value-synthetic-contract-pack-v1/** text eol=lf",
            "data-packs/value-101-*/** text eol=lf",
            "examples/zonal-network-pack/**/*.json text eol=lf",
            "tests/fixtures/zonal_solver_failures/*.json text eol=lf",
            "tests/fixtures/zonal_solver_failures/*.json.gz -text",
            "publication/prompt104-copperplate-preflight.json -text",
            "publication/prompt104-zonal-preflight.json -text",
            "publication/prompt104-staged-copperplate-study.json text eol=lf",
            "publication/prompt104-zonal-study.json text eol=lf",
            "gridform_core/data/carbon/*.csv text eol=lf",
            "gridform_core/data/carbon/*.json text eol=lf",
            "gridform_core/data/carbon/*.sql text eol=lf",
            "gridform_core/data/carbon/scenarios/*.json text eol=lf",
        }
        self.assertTrue(expected.issubset(set(attributes.splitlines())))

    def test_default_public_data_build_does_not_replace_audited_uk_bill(self):
        builder_spec = importlib.util.spec_from_file_location(
            "build_publication_data_packs",
            ROOT / "scripts" / "build_publication_data_packs.py",
        )
        builder = importlib.util.module_from_spec(builder_spec)
        assert builder_spec.loader is not None
        builder_spec.loader.exec_module(builder)
        with mock.patch.object(builder, "build_synthetic", return_value={"bindings": {}}), \
             mock.patch.object(builder, "build_uk_bill") as build_uk_bill:
            builder.main([])
        build_uk_bill.assert_not_called()

    def test_source_plan_uk_bill_requires_explicit_switch(self):
        builder_spec = importlib.util.spec_from_file_location(
            "build_publication_data_packs_explicit",
            ROOT / "scripts" / "build_publication_data_packs.py",
        )
        builder = importlib.util.module_from_spec(builder_spec)
        assert builder_spec.loader is not None
        builder_spec.loader.exec_module(builder)
        bill = {"roles_expected": 25, "publication_status": "NO-GO_INCOMPLETE"}
        with mock.patch.object(builder, "build_synthetic", return_value={"bindings": {}}), \
             mock.patch.object(builder, "build_uk_bill", return_value=bill) as build_uk_bill:
            builder.main(["--write-uk-source-plan-bill"])
        build_uk_bill.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
