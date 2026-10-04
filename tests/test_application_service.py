import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing, redirect_stderr, redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / ".gridform" / "data-packs" / "value-uk-1000twh-reproduction"
HAS_RUNTIME_DEPS = all(
    importlib.util.find_spec(name) is not None
    for name in ("numpy", "pandas", "xarray", "netCDF4")
)
MODULES = {
    "psm": "value-bid-at-cost-psm",
    "investment": "agent-investment",
    "pipeline": "planning-pipeline",
    "vre_cap": "vre-expansion-cap",
    "storage_cap": "value-storage-expansion-policy",
}
ZONAL_SOLVER_TEST_ROLES = (
    "value.zonal.zones",
    "value.zonal.corridors",
    "value.zonal.cutsets",
    "value.zonal.asset-map",
    "value.zonal.demand",
    "value.zonal.ratings",
    "value.zonal.interconnector-landings",
    "value.zonal.spatial-audit",
)


class ZonalSolverContractSaveApiTests(unittest.TestCase):
    def test_run_application_injects_custom_contract_into_live_frozen_graph(self) -> None:
        from gridform_core import application
        from gridform_core.v2.module_manifest import builtin_registry
        from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS
        from test_prompt99_zonal_redispatch import (
            FIXTURE_ROOT,
            balancing_input_from_fixture,
        )

        project = json.loads(
            (ROOT / "publication" / "prompt104-zonal-study.json").read_text(
                encoding="utf-8"
            )
        )
        project["selected_extensions"] = []
        project["maturity_acknowledgements"] = {
            "module:value-zonal-redispatch-balancing@2.0.0": "value.experimental-ack/v1",
            "module:value-representative-point-weather@1.0.0": "value.experimental-ack/v1",
        }
        custom = DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
        custom.update({
            "method": "highs",
            "primal_feasibility_tolerance": 1e-8,
            "dual_feasibility_tolerance": 1e-8,
            "ipm_optimality_tolerance": 1e-10,
            "warning_fraction": 0.2,
            "validated_ceilings": {
                "primary_bid_cost_gbp": 0.02,
                "secondary_schedule_deviation_mwh": 0.002,
                "physical_throughput_mwh": 0.002,
            },
            "is_builtin_default": False,
            "requires_acknowledgement": True,
        })
        project["solver_contract"] = custom
        registry = builtin_registry()
        original_resolve = registry.resolve_selection
        observed: dict[str, object] = {}

        def capture_original_graph(*args, **kwargs):
            graph = original_resolve(*args, **kwargs)
            observed["original_graph"] = graph
            return graph

        def execute_live_graph(**kwargs):
            graph = kwargs["resolution_graph"]
            observed["live_graph"] = graph
            balancing = graph.implementation("balancing")
            result = balancing.clear(balancing_input_from_fixture(
                FIXTURE_ROOT / "period-bound-noise.json"
            ))
            return {
                "solver_contract": result.extensions["solver"]["solver_contract"],
                "network_solver_diagnostics": result.extensions[
                    "network_solver_diagnostics"
                ],
                "frozen_project_solver_contract": dict(
                    kwargs["project"]["solver_contract"]
                ),
            }

        resolved_parameters = SimpleNamespace(
            scientific=SimpleNamespace(values={"scenario.id": "solver-contract-test"}),
            runtime=SimpleNamespace(values={}),
            sources={},
        )
        pack_selection = SimpleNamespace(
            base_manifest=json.loads(
                (ROOT / "data-packs" / "value-synthetic-contract-pack-v1" / "manifest.json")
                .read_text(encoding="utf-8")
            ),
            network_pack_root=ROOT,
            available_data_roles=ZONAL_SOLVER_TEST_ROLES,
        )
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(
            registry, "resolve_selection", side_effect=capture_original_graph
        ), mock.patch.object(
            application, "resolve_scheme_c_parameters", return_value=resolved_parameters
        ), mock.patch.object(
            application, "resolve_zonal_pack_selection", return_value=pack_selection
        ), mock.patch.object(
            application, "snapshot_module_manifests", return_value={}
        ), mock.patch.object(
            application, "_run_native_project", side_effect=execute_live_graph
        ):
            result = application.run_project_application(
                project,
                run_id="custom-solver-live-graph",
                pack_root=ROOT / "data-packs" / "value-synthetic-contract-pack-v1",
                output_dir=Path(folder),
                mode="smoke",
                registry=registry,
                network_pack_root=ROOT,
            )

        original_balancing = observed["original_graph"].implementation("balancing")
        live_balancing = observed["live_graph"].implementation("balancing")
        self.assertIsNot(original_balancing, live_balancing)
        self.assertEqual(
            original_balancing._solver_settings.to_dict(),
            DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict(),
        )
        self.assertEqual(result["solver_contract"], custom)
        self.assertEqual(result["frozen_project_solver_contract"], custom)
        self.assertTrue(all(
            "warning_fraction" not in row
            for row in result["network_solver_diagnostics"]
        ))
        self.assertTrue(all(
            row["validated_ceiling"]
            == custom["validated_ceilings"][{
                "primary_bid_cost": "primary_bid_cost_gbp",
                "secondary_schedule_deviation": "secondary_schedule_deviation_mwh",
                "physical_throughput": "physical_throughput_mwh",
            }[row["phase_id"]]]
            for row in result["network_solver_diagnostics"]
        ))

    def test_custom_contract_requires_one_acknowledged_revision(self) -> None:
        from backend import server
        from gridform_core.project_revision import derive_zonal_execution_project
        from gridform_core.v2.module_manifest import builtin_registry
        from gridform_core.zonal_pack_selection import ZonalPackSelection

        source = (ROOT / "publication" / "prompt104-zonal-study.json").read_bytes()
        pack = json.loads(
            (
                ROOT
                / "data-packs"
                / "value-synthetic-contract-pack-v1"
                / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        network_manifest = {
            "schema_version": "value.data-pack/v1",
            "id": "force-zonal-contract-test-overlay-v1",
            "data_pack_type": "network_overlay",
            "bindings": {
                role: {"uri": f"files/{index}.json"}
                for index, role in enumerate(ZONAL_SOLVER_TEST_ROLES)
            },
        }
        revision_manifest = ZonalPackSelection(
            ROOT,
            pack,
            ROOT,
            network_manifest,
            str(network_manifest["id"]),
        ).revision_manifest
        project, _evidence = derive_zonal_execution_project(
            source,
            registry=builtin_registry(),
            data_pack_manifest=revision_manifest,
        )
        project.update({
            "id": "solver-contract-save",
            "name": "Solver contract save",
            "data_pack_id": "value-synthetic-contract-pack-v1",
            "selected_extensions": [],
        })
        project["maturity_acknowledgements"].pop(
            "extension:value-zonal-redispatch-extension@1.0.0", None
        )
        project.pop("extensions", None)
        project["parameters"] = project.pop("parameter_overrides")
        project["runtime_options"] = project.pop("runtime_controls")
        project["solver_contract"]["dual_feasibility_tolerance"] = 1e-8
        project.pop("revision_sha256", None)
        project.pop("revision_number", None)
        project.pop("parent_revision_sha256", None)

        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            patches = (
                mock.patch.object(server, "PACKS_ROOT", ROOT / "data-packs"),
                mock.patch.object(server, "PROJECTS_ROOT", state / "projects"),
                mock.patch.object(server, "RUNS_ROOT", state / "runs"),
                mock.patch.object(
                    server,
                    "resolve_scheme_c_parameters",
                    return_value=SimpleNamespace(
                        to_dict=lambda: {}, warnings=[], warning_events=[]
                    ),
                ),
            )
            for item in patches:
                item.start()
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{httpd.server_address[1]}"

            def post(payload: dict[str, object]) -> dict[str, object]:
                request = urllib.request.Request(
                    origin + "/api/projects",
                    data=json.dumps(payload).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                return json.loads(urllib.request.urlopen(request, timeout=10).read())

            try:
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    post(project)
                self.assertEqual(rejected.exception.code, 422)
                rejection = json.loads(rejected.exception.read())
                self.assertEqual(
                    rejection["error_code"], "GF_SOLVER_CONTRACT_ACK_REQUIRED"
                )
                self.assertIn("validation", rejection)

                project["maturity_acknowledgements"][
                    "solver-contract:value-zonal-redispatch-balancing@2.0.0"
                ] = "value.solver-contract-ack/v1"
                try:
                    first = post(project)["project"]
                except urllib.error.HTTPError as exc:
                    self.fail(exc.read().decode("utf-8"))
                project["base_revision_sha256"] = first["revision_sha256"]
                second = post(project)["project"]

                self.assertEqual(second["revision_sha256"], first["revision_sha256"])
                self.assertEqual(second["revision_number"], 1)
                self.assertEqual(
                    len(list(
                        (state / "projects" / project["id"] / "revisions").glob(
                            "*.json"
                        )
                    )),
                    1,
                )
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
                for item in reversed(patches):
                    item.stop()


class VRECurtailmentArtifactTests(unittest.TestCase):
    def _ledger(
        self,
        path: Path,
        *,
        with_evidence: bool,
        with_detail: bool = True,
        trace_level: str = "summary",
    ) -> None:
        from gridform_core.market_ledger import (
            SQLiteMarketLedger,
            VRECurtailmentDetailRow,
            VRECurtailmentPeriodRow,
            ZonalAccountingLedgerRow,
        )

        ledger = SQLiteMarketLedger(
            path,
            trace_level=trace_level,
            semantic_metadata={
                "run_id": "artifact-run",
                "run_parent_id": None,
                "data_pack_id": "research-pack",
                "network_pack_id": "network-pack",
                "module_ids": ["fixture-psm", "fixture-balancing"],
            },
        )
        accounting = SimpleNamespace(
            year=2025,
            period=0,
            period_id="2025:0",
            system_resource_cost_gbp=120.0,
            transmission_constraint_resource_cost_gbp=20.0,
            national_settlement_gbp=500.0,
            redispatch_settlement_gbp=20.0,
            policy_transfer_gbp=3.0,
            perfect_forecast_resource_cost_gbp=90.0,
            realised_copperplate_resource_cost_gbp=100.0,
            zonal_resource_cost_gbp=120.0,
            forecast_error_cost_gbp=10.0,
            total_deviation_cost_gbp=30.0,
            blackout_mwh=0.0,
            counterfactual_realised_input_sha256="a" * 64,
            accounting_status="reconciled",
        )
        ledger.record_zonal_accounting(
            (ZonalAccountingLedgerRow.from_accounting(accounting),)
        )
        if with_evidence:
            ledger.record_vre_curtailment_periods((VRECurtailmentPeriodRow(
                2025, 0, "2025:0", 10.0, 8.0, 8.0, 9.0,
                2.0, 0.0, 0.0, 0.0, 1.0, -1.0, 1.0, 0.1,
                0.0, 1e-7, "reconciled", "a" * 64,
                "value.pro-rata-technology-bid-tranche/v1",
            ),))
            if with_detail:
                ledger.record_vre_curtailment_details((VRECurtailmentDetailRow(
                    2025, 0, "2025:0", "vre-0", "owner-0", "north",
                    "Onshore wind", "tranche-0", 10.0, 8.0, 8.0, 9.0,
                    2.0, 0.0, 0.0, 0.0, 1.0, -1.0, 1.0,
                    "deterministic_reference_allocation",
                ),))
        ledger.close()

    @staticmethod
    def _resolution(
        *,
        declares_capability: bool,
        balancing_produces_zonal_dispatch: bool | None = None,
        unrelated_manifest_declares_capability: bool = False,
    ):
        from gridform_core.v2.module_manifest import (
            ModuleManifest,
            ResolvedModuleGraph,
            ResolvedModuleIdentity,
        )

        psm_capabilities = (
            ("evidence.vre-counterfactual-snapshot/v1",)
            if declares_capability
            else ()
        )
        psm_manifest = ModuleManifest(
            id="fixture-psm",
            name="Fixture PSM",
            version="1.0.0",
            slot="psm",
            implementation=(
                "gridform_core.builtin.scheme_c_1000twh.staged_psm:MODULE"
            ),
            contract_version="value.psm/v2",
            inputs=(),
            outputs=(),
            parameters=(),
            state_reads=(),
            state_writes=(),
            determinism="deterministic",
            artifacts=(),
            description="Explicit test resolution fixture.",
            provides_capabilities=psm_capabilities,
        )
        psm_identity = ResolvedModuleIdentity(
            slot="psm",
            module_id="fixture-psm",
            module_version="1.0.0",
            contract_version="value.psm/v2",
            entry_point=psm_manifest.implementation,
            source_sha256="b" * 64,
            distribution="test-fixture",
            scientific_version="1.0.0",
            execution_kind="live_module",
        )
        zonal_output = (
            declares_capability
            if balancing_produces_zonal_dispatch is None
            else balancing_produces_zonal_dispatch
        )
        balancing_manifest = ModuleManifest(
            id="fixture-balancing",
            name="Fixture balancing",
            version="1.0.0",
            slot="balancing",
            implementation=(
                "gridform_core.builtin.scheme_c_1000twh.copperplate_balancing:"
                "CopperplateBalancing"
            ),
            contract_version="value.balancing-module/v1",
            inputs=(),
            outputs=(
                ("network.zonal-redispatch-result/v1",)
                if zonal_output
                else ("market.balancing-result/v1",)
            ),
            parameters=(),
            state_reads=(),
            state_writes=(),
            determinism="deterministic",
            artifacts=(),
            description="Explicit selected balancing fixture.",
            provides_capabilities=("market.balancing/v1",),
        )
        balancing_identity = ResolvedModuleIdentity(
            slot="balancing",
            module_id="fixture-balancing",
            module_version="1.0.0",
            contract_version="value.balancing-module/v1",
            entry_point=balancing_manifest.implementation,
            source_sha256="e" * 64,
            distribution="test-fixture",
            scientific_version="1.0.0",
            execution_kind="live_module",
        )
        manifests = {
            "psm": psm_manifest,
            "balancing": balancing_manifest,
        }
        identities = {
            "psm": psm_identity,
            "balancing": balancing_identity,
        }
        implementations = {"psm": object(), "balancing": object()}
        if unrelated_manifest_declares_capability:
            unrelated_manifest = ModuleManifest(
                id="fixture-storage-cost",
                name="Fixture storage cost",
                version="1.0.0",
                slot="storage_cost",
                implementation=(
                    "gridform_core.builtin.scheme_c_1000twh.storage_cost:MODULE"
                ),
                contract_version="value.storage-cost/v1",
                inputs=(), outputs=(), parameters=(), state_reads=(), state_writes=(),
                determinism="deterministic", artifacts=(),
                description="Unrelated capability fixture.",
                provides_capabilities=("evidence.vre-counterfactual-snapshot/v1",),
            )
            unrelated_identity = ResolvedModuleIdentity(
                slot="storage_cost", module_id="fixture-storage-cost",
                module_version="1.0.0", contract_version="value.storage-cost/v1",
                entry_point=unrelated_manifest.implementation,
                source_sha256="f" * 64, distribution="test-fixture",
                scientific_version="1.0.0", execution_kind="live_module",
            )
            manifests["storage_cost"] = unrelated_manifest
            identities["storage_cost"] = unrelated_identity
            implementations["storage_cost"] = object()
        return ResolvedModuleGraph(
            manifests_by_slot=manifests,
            implementations_by_slot=implementations,
            identities_by_slot=identities,
            graph_sha256="c" * 64,
        )

    def test_compact_attribution_artifact_is_atomic_and_contains_audit_identity(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(database, with_evidence=True)
            path = write_vre_curtailment_attribution_artifact(
                output_dir=output,
                database=database,
                data_pack_id="research-pack",
                network_pack_id="network-pack",
                initial_state_sha256="d" * 64,
                resolution_graph=self._resolution(declares_capability=True),
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            temporary_files = list(path.parent.glob("*.tmp"))

        self.assertEqual(
            payload["schema_version"], "value.vre-curtailment-run-evidence/v1"
        )
        self.assertEqual(
            payload["contract_version"], "value.vre-curtailment-attribution/v2"
        )
        self.assertEqual(
            payload["snapshot_contract_version"],
            "value.vre-counterfactual-snapshot/v1",
        )
        self.assertEqual(
            payload["attribution_method_id"],
            "value.pro-rata-technology-bid-tranche/v1",
        )
        self.assertEqual(payload["data_pack_id"], "research-pack")
        self.assertEqual(payload["network_pack_id"], "network-pack")
        self.assertEqual(payload["initial_state_sha256"], "d" * 64)
        self.assertEqual(payload["capability_status"], "reconciled")
        self.assertEqual(payload["matched_counterfactual_proof"]["period_count"], 1)
        self.assertTrue(payload["matched_counterfactual_proof"]["period_sets_match"])
        self.assertTrue(
            payload["matched_counterfactual_proof"]["realised_input_hashes_match"]
        )
        self.assertIn(
            "period_identity_set_sha256",
            payload["matched_counterfactual_proof"],
        )
        self.assertNotEqual(
            payload["matched_counterfactual_proof"]["period_identity_set_sha256"],
            payload["counterfactual_realised_input_set_sha256"],
        )
        self.assertEqual(payload["annual_totals"][0]["period_count"], 1)
        self.assertEqual(payload["annual_totals"][0]["total_mwh"], 1.0)
        self.assertEqual(payload["maximum_absolute_period_residual_mwh"], 0.0)
        self.assertEqual(payload["maximum_residual_period_id"], "2025:0")
        self.assertIsNone(payload["detail_location"])
        self.assertEqual(payload["detail_evidence_level"], "period_summary")
        self.assertIn("psm", payload["module_identities"])
        self.assertEqual(temporary_files, [])
        self.assertNotIn("detail_rows", payload)
        self.assertNotIn("asset_id", json.dumps(payload))

    def test_declaring_resolution_without_period_evidence_fails_the_run(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(database, with_evidence=False)
            with self.assertRaisesRegex(
                ValueError, "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING"
            ):
                write_vre_curtailment_attribution_artifact(
                    output_dir=output,
                    database=database,
                    data_pack_id="research-pack",
                    network_pack_id="network-pack",
                    initial_state_sha256="d" * 64,
                    resolution_graph=self._resolution(declares_capability=True),
                )
            with self.assertRaisesRegex(
                ValueError, "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING"
            ):
                write_vre_curtailment_attribution_artifact(
                    output_dir=output,
                    database=output / "missing-market.sqlite",
                    data_pack_id="research-pack",
                    network_pack_id="network-pack",
                    initial_state_sha256="d" * 64,
                    resolution_graph=self._resolution(declares_capability=True),
                )

    def test_declaring_resolution_without_nonzero_detail_evidence_fails_the_run(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(
                database,
                with_evidence=True,
                with_detail=False,
                trace_level="full",
            )
            with self.assertRaisesRegex(
                ValueError, "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING"
            ):
                write_vre_curtailment_attribution_artifact(
                    output_dir=output,
                    database=database,
                    data_pack_id="research-pack",
                    network_pack_id="network-pack",
                    initial_state_sha256="d" * 64,
                    resolution_graph=self._resolution(declares_capability=True),
                )

    def test_v8_summary_uses_reconciled_period_evidence_without_full_detail(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(database, with_evidence=True, with_detail=False)
            path = write_vre_curtailment_attribution_artifact(
                output_dir=output,
                database=database,
                data_pack_id="research-pack",
                network_pack_id="network-pack",
                initial_state_sha256="d" * 64,
                resolution_graph=self._resolution(declares_capability=True),
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["capability_status"], "reconciled")
        self.assertEqual(payload["ledger_trace_level"], "summary")
        self.assertEqual(payload["detail_evidence_level"], "period_summary")
        self.assertIsNone(payload["detail_location"])

    def test_declaring_resolution_with_mismatched_detail_evidence_fails_the_run(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(database, with_evidence=True, trace_level="full")
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE vre_curtailment_detail "
                    "SET total_curtailment_mwh=2.0"
                )
                connection.commit()
            with self.assertRaisesRegex(
                ValueError, "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING"
            ):
                write_vre_curtailment_attribution_artifact(
                    output_dir=output,
                    database=database,
                    data_pack_id="research-pack",
                    network_pack_id="network-pack",
                    initial_state_sha256="d" * 64,
                    resolution_graph=self._resolution(declares_capability=True),
                )

    def test_declaring_resolution_accepts_vre_free_period_without_detail_rows(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(database, with_evidence=True)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("DELETE FROM vre_curtailment_detail")
                connection.execute("""
                    UPDATE vre_curtailment_period SET
                        realised_available_vre_mwh=0,
                        perfect_reference_dispatch_mwh=0,
                        copperplate_reference_dispatch_mwh=0,
                        zonal_final_dispatch_mwh=0,
                        economic_curtailment_mwh=0,
                        forecast_added_curtailment_mwh=0,
                        forecast_avoided_curtailment_mwh=0,
                        redispatch_added_curtailment_mwh=0,
                        redispatch_avoided_curtailment_mwh=0,
                        redispatch_net_impact_mwh=0,
                        total_curtailment_mwh=0,
                        curtailment_rate=0
                """)
                connection.commit()
            path = write_vre_curtailment_attribution_artifact(
                output_dir=output,
                database=database,
                data_pack_id="research-pack",
                network_pack_id="network-pack",
                initial_state_sha256="d" * 64,
                resolution_graph=self._resolution(declares_capability=True),
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["capability_status"], "reconciled")
        self.assertEqual(payload["annual_totals"][0]["total_mwh"], 0.0)

    def test_artifact_rejects_mutated_period_identity_and_signed_net(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        mutations = {
            "residual_over_tolerance": (
                "UPDATE vre_curtailment_period SET identity_residual_mwh=1.0",
            ),
            "signed_net_not_gross_added_minus_avoided": (
                "UPDATE vre_curtailment_period SET redispatch_net_impact_mwh=0.0",
                "UPDATE vre_curtailment_detail SET redispatch_net_impact_mwh=0.0",
            ),
            "gross_signed_identity_mismatch": (
                "UPDATE vre_curtailment_period "
                "SET forecast_added_curtailment_mwh=1.0",
                "UPDATE vre_curtailment_detail "
                "SET forecast_added_curtailment_mwh=1.0",
            ),
        }
        for name, statements in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "model-output"
                database = output / "market" / "market.sqlite"
                self._ledger(database, with_evidence=True)
                with closing(sqlite3.connect(database)) as connection:
                    for statement in statements:
                        connection.execute(statement)
                    connection.commit()
                    if name == "gross_signed_identity_mismatch":
                        stored = connection.execute(
                            "SELECT accounting_status, identity_residual_mwh, "
                            "redispatch_net_impact_mwh, "
                            "redispatch_added_curtailment_mwh, "
                            "redispatch_avoided_curtailment_mwh "
                            "FROM vre_curtailment_period"
                        ).fetchone()
                        self.assertEqual(stored, ("reconciled", 0.0, -1.0, 0.0, 1.0))
                with self.assertRaisesRegex(
                    ValueError, "GF_VRE_ATTRIBUTION_IDENTITY_FAILED"
                ):
                    write_vre_curtailment_attribution_artifact(
                        output_dir=output,
                        database=database,
                        data_pack_id="research-pack",
                        network_pack_id="network-pack",
                        initial_state_sha256="d" * 64,
                        resolution_graph=self._resolution(declares_capability=True),
                    )

    def test_artifact_rejects_every_nonfinite_period_and_detail_quantity(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        detail_fields = (
            "realised_available_vre_mwh",
            "perfect_reference_dispatch_mwh",
            "copperplate_reference_dispatch_mwh",
            "zonal_final_dispatch_mwh",
            "economic_curtailment_mwh",
            "forecast_added_curtailment_mwh",
            "forecast_avoided_curtailment_mwh",
            "redispatch_added_curtailment_mwh",
            "redispatch_avoided_curtailment_mwh",
            "redispatch_net_impact_mwh",
            "total_curtailment_mwh",
        )
        participating_fields = {
            "vre_curtailment_period": detail_fields + (
                "identity_residual_mwh",
                "validation_tolerance_mwh",
            ),
            "vre_curtailment_detail": detail_fields,
        }
        for table, fields in participating_fields.items():
            for field in fields:
                with (
                    self.subTest(table=table, field=field),
                    tempfile.TemporaryDirectory() as folder,
                ):
                    output = Path(folder) / "model-output"
                    database = output / "market" / "market.sqlite"
                    self._ledger(database, with_evidence=True)
                    with closing(sqlite3.connect(database)) as connection:
                        connection.execute(
                            f"UPDATE {table} SET {field}=?",
                            (float("inf"),),
                        )
                        connection.commit()
                    with self.assertRaisesRegex(
                        ValueError, "GF_VRE_ATTRIBUTION_IDENTITY_FAILED"
                    ):
                        write_vre_curtailment_attribution_artifact(
                            output_dir=output,
                            database=database,
                            data_pack_id="research-pack",
                            network_pack_id="network-pack",
                            initial_state_sha256="d" * 64,
                            resolution_graph=self._resolution(
                                declares_capability=True
                            ),
                        )

    def test_artifact_rejects_nonfinite_stored_period_rate(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(database, with_evidence=True)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "UPDATE vre_curtailment_period SET curtailment_rate=?",
                    (float("inf"),),
                )
                connection.commit()
            with self.assertRaisesRegex(
                ValueError, "GF_VRE_ATTRIBUTION_IDENTITY_FAILED"
            ):
                write_vre_curtailment_attribution_artifact(
                    output_dir=output,
                    database=database,
                    data_pack_id="research-pack",
                    network_pack_id="network-pack",
                    initial_state_sha256="d" * 64,
                    resolution_graph=self._resolution(declares_capability=True),
                )

    def test_only_formally_all_zero_vre_period_may_omit_detail_rows(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(database, with_evidence=True)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("DELETE FROM vre_curtailment_detail")
                connection.execute("""
                    UPDATE vre_curtailment_period SET
                        realised_available_vre_mwh=5e-8,
                        perfect_reference_dispatch_mwh=0,
                        copperplate_reference_dispatch_mwh=0,
                        zonal_final_dispatch_mwh=0,
                        economic_curtailment_mwh=5e-8,
                        forecast_added_curtailment_mwh=0,
                        forecast_avoided_curtailment_mwh=0,
                        redispatch_added_curtailment_mwh=0,
                        redispatch_avoided_curtailment_mwh=0,
                        redispatch_net_impact_mwh=0,
                        total_curtailment_mwh=5e-8,
                        curtailment_rate=1,
                        identity_residual_mwh=0
                """)
                connection.commit()
            with self.assertRaisesRegex(
                ValueError, "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING"
            ):
                write_vre_curtailment_attribution_artifact(
                    output_dir=output,
                    database=database,
                    data_pack_id="research-pack",
                    network_pack_id="network-pack",
                    initial_state_sha256="d" * 64,
                    resolution_graph=self._resolution(declares_capability=True),
                )

    def test_vre_free_period_without_detail_requires_zero_stored_rate(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(database, with_evidence=True)
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("DELETE FROM vre_curtailment_detail")
                connection.execute("""
                    UPDATE vre_curtailment_period SET
                        realised_available_vre_mwh=0,
                        perfect_reference_dispatch_mwh=0,
                        copperplate_reference_dispatch_mwh=0,
                        zonal_final_dispatch_mwh=0,
                        economic_curtailment_mwh=0,
                        forecast_added_curtailment_mwh=0,
                        forecast_avoided_curtailment_mwh=0,
                        redispatch_added_curtailment_mwh=0,
                        redispatch_avoided_curtailment_mwh=0,
                        redispatch_net_impact_mwh=0,
                        total_curtailment_mwh=0,
                        curtailment_rate=1,
                        identity_residual_mwh=0
                """)
                connection.commit()
            with self.assertRaisesRegex(
                ValueError, "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING"
            ):
                write_vre_curtailment_attribution_artifact(
                    output_dir=output,
                    database=database,
                    data_pack_id="research-pack",
                    network_pack_id="network-pack",
                    initial_state_sha256="d" * 64,
                    resolution_graph=self._resolution(declares_capability=True),
                )

    def test_artifact_requires_exact_period_id_sets_and_detail_identity(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        mutations = {
            "accounting_period_id_orphan": (
                "UPDATE zonal_period_accounting SET period_id='accounting-orphan'",
            ),
            "detail_period_id_orphan": (
                "UPDATE vre_curtailment_detail SET period_id='detail-orphan'",
            ),
        }
        for name, statements in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "model-output"
                database = output / "market" / "market.sqlite"
                self._ledger(database, with_evidence=True)
                with closing(sqlite3.connect(database)) as connection:
                    for statement in statements:
                        connection.execute(statement)
                    connection.commit()
                with self.assertRaisesRegex(
                    ValueError, "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING"
                ):
                    write_vre_curtailment_attribution_artifact(
                        output_dir=output,
                        database=database,
                        data_pack_id="research-pack",
                        network_pack_id="network-pack",
                        initial_state_sha256="d" * 64,
                        resolution_graph=self._resolution(declares_capability=True),
                    )

    def test_artifact_streams_detail_rows_without_fetchall(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        real_connect = sqlite3.connect

        class GuardedCursor:
            def __init__(self, cursor):
                self._cursor = cursor

            def __iter__(self):
                return iter(self._cursor)

            def fetchall(self):
                raise AssertionError(
                    "VRE detail validation must not materialise the full cursor"
                )

            def __getattr__(self, name):
                return getattr(self._cursor, name)

        class GuardedConnection:
            def __init__(self, connection):
                self._connection = connection

            @property
            def row_factory(self):
                return self._connection.row_factory

            @row_factory.setter
            def row_factory(self, value):
                self._connection.row_factory = value

            def execute(self, statement, *args, **kwargs):
                cursor = self._connection.execute(statement, *args, **kwargs)
                normalized = " ".join(statement.lower().split())
                is_unbounded_detail_path = (
                    "from vre_curtailment_detail" in normalized
                    and (
                        "group by" not in normalized
                        or "group by year, period, period_id" in normalized
                    )
                )
                if is_unbounded_detail_path:
                    return GuardedCursor(cursor)
                return cursor

            def __enter__(self):
                self._connection.__enter__()
                return self

            def __exit__(self, *args):
                try:
                    return self._connection.__exit__(*args)
                finally:
                    self._connection.close()

            def close(self):
                self._connection.close()

        def guarded_connect(*args, **kwargs):
            return GuardedConnection(real_connect(*args, **kwargs))

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(database, with_evidence=True)
            with mock.patch(
                "gridform_core.application.sqlite3.connect",
                side_effect=guarded_connect,
            ):
                path = write_vre_curtailment_attribution_artifact(
                    output_dir=output,
                    database=database,
                    data_pack_id="research-pack",
                    network_pack_id="network-pack",
                    initial_state_sha256="d" * 64,
                    resolution_graph=self._resolution(declares_capability=True),
                )
                payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["capability_status"], "reconciled")

    def test_streamed_detail_reconciliation_rejects_corrupt_later_period(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(database, with_evidence=True)
            with closing(sqlite3.connect(database)) as connection:
                for table in (
                    "zonal_period_accounting",
                    "vre_curtailment_period",
                    "vre_curtailment_detail",
                ):
                    columns = [
                        str(row[1])
                        for row in connection.execute(
                            f"PRAGMA table_info({table})"
                        )
                    ]
                    expressions = [
                        "1" if column == "period" else
                        "'2025:1'" if column == "period_id" else
                        column
                        for column in columns
                    ]
                    connection.execute(
                        f"INSERT INTO {table} ({', '.join(columns)}) "
                        f"SELECT {', '.join(expressions)} FROM {table} "
                        "WHERE year=2025 AND period=0"
                    )
                connection.execute(
                    "UPDATE vre_curtailment_detail "
                    "SET total_curtailment_mwh=2.0 WHERE period=1"
                )
                connection.commit()
            with self.assertRaisesRegex(
                ValueError, "GF_VRE_ATTRIBUTION_CAPABILITY_MISSING"
            ):
                write_vre_curtailment_attribution_artifact(
                    output_dir=output,
                    database=database,
                    data_pack_id="research-pack",
                    network_pack_id="network-pack",
                    initial_state_sha256="d" * 64,
                    resolution_graph=self._resolution(declares_capability=True),
                )

    def test_capability_requires_selected_psm_and_zonal_balancing_composition(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        cases = {
            "psm_snapshot_with_copperplate_balancing": self._resolution(
                declares_capability=True,
                balancing_produces_zonal_dispatch=False,
            ),
            "unrelated_manifest_cannot_supply_psm_capability": self._resolution(
                declares_capability=False,
                balancing_produces_zonal_dispatch=True,
                unrelated_manifest_declares_capability=True,
            ),
        }
        for name, resolution in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                output = Path(folder) / "model-output"
                database = output / "market" / "market.sqlite"
                self._ledger(database, with_evidence=True)
                path = write_vre_curtailment_attribution_artifact(
                    output_dir=output,
                    database=database,
                    data_pack_id="research-pack",
                    network_pack_id="network-pack",
                    initial_state_sha256="d" * 64,
                    resolution_graph=resolution,
                )
                payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["capability_status"], "unavailable")
            self.assertFalse(payload["declared_snapshot_capability"])

    def test_non_declaring_resolution_writes_an_unavailable_compact_artifact(self):
        from gridform_core.application import write_vre_curtailment_attribution_artifact

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            database = output / "market" / "market.sqlite"
            self._ledger(database, with_evidence=False)
            path = write_vre_curtailment_attribution_artifact(
                output_dir=output,
                database=database,
                data_pack_id="research-pack",
                network_pack_id="network-pack",
                initial_state_sha256="d" * 64,
                resolution_graph=self._resolution(declares_capability=False),
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["capability_status"], "unavailable")
        self.assertEqual(
            payload["reason_code"],
            "module_does_not_provide_counterfactual_snapshot",
        )
        self.assertEqual(payload["annual_totals"], [])


class SolverValidationApplicationPayloadTests(unittest.TestCase):
    def test_native_payload_exposes_compact_causally_inherited_solver_status(self):
        from gridform_core.application import _native_result_payload

        cause = {
            "year": 2025,
            "period": 7,
            "period_id": "2025:7",
            "phase_id": "primary_bid_cost",
            "validation_class": "COMPLETED_WITH_NUMERICAL_WARNING",
        }

        def year_result(year, *, inherited, warning_periods):
            summary = {
                "schema_version": "value.solver-validation-summary/v1",
                "annual_status": (
                    "GO" if inherited else "COMPLETED_WITH_NUMERICAL_WARNING"
                ),
                "study_status": "COMPLETED_WITH_NUMERICAL_WARNING",
                "solver_validated": False,
                "inherited_unvalidated": inherited,
                "first_causal_period": cause,
                "warning_periods": warning_periods,
                "unvalidated_periods": warning_periods,
                "maximum_validated_ceiling_use": 2.0 if not inherited else 0.01,
            }
            return SimpleNamespace(
                year=year,
                market=SimpleNamespace(
                    total_generation_mwh=1.0,
                    total_levelized_capital_cost_gbp=0.0,
                    total_operational_cost_gbp=0.0,
                    total_blackout_mwh=0.0,
                    total_excess_mwh=0.0,
                    period_summaries=(),
                    extensions={"solver_validation_summary": summary},
                ),
                planning_advance=SimpleNamespace(
                    operating_state=SimpleNamespace(assets=()),
                    active_projects=(),
                    commissioned_projects=(),
                    failed_projects=(),
                    deferred_projects=(),
                ),
                planning_admission=SimpleNamespace(
                    admitted_projects=(),
                ),
                investment=SimpleNamespace(proposals=(), retirements_mw={}),
            )

        results = (
            year_result(2025, inherited=False, warning_periods=1),
            year_result(2026, inherited=True, warning_periods=0),
        )
        ledgers = tuple(SimpleNamespace(
            year=year,
            cem_system_cost_gbp=0.0,
            cem_system_cost_gbp_per_mwh_served=0.0,
        ) for year in (2025, 2026))
        payload = _native_result_payload(
            results, ledgers, planning_mode="expected_capacity"
        )

        summary = payload["solver_validation_summary"]
        self.assertIs(summary["solver_validated"], False)
        self.assertEqual(summary["first_causal_period"], cause)
        self.assertEqual(summary["maximum_validated_ceiling_use"], 2.0)
        self.assertEqual(summary["warning_periods"], 1)
        self.assertEqual([row["year"] for row in summary["years"]], [2025, 2026])


@unittest.skipUnless(sys.version_info[:2] == (3, 10), "VALUE requires Python 3.10")
@unittest.skipUnless((PACK / "manifest.json").is_file(), "verified local pack is required")
@unittest.skipUnless(HAS_RUNTIME_DEPS, "VALUE scientific dependencies are required")
class ApplicationServiceTests(unittest.TestCase):
    def test_two_year_smoke_runs_psm_cem_and_transition_in_both_years(self):
        from gridform_core.application import run_project_application

        project = {
            "id": "application-two-year-smoke",
            "name": "Application two-year smoke",
            "data_pack_id": "value-uk-1000twh-reproduction",
            "start_year": 2025,
            "end_year": 2026,
            "modules": MODULES,
            "parameters": {},
            "runtime_options": {"runtime.market_trace_level": "full"},
        }
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model-output"
            console = io.StringIO()
            with redirect_stdout(console), redirect_stderr(console):
                result = run_project_application(
                    project, run_id="application-two-year-smoke", pack_root=PACK,
                    output_dir=output, mode="two_year_smoke",
                )
            stages = [
                json.loads(line)
                for line in (output / "orchestrator-events.jsonl").read_text("utf-8").splitlines()
            ]
            typed = json.loads((output / "year-results-v2.json").read_text("utf-8"))
            resolved = json.loads((output / "resolved-run.json").read_text("utf-8"))
            market_metadata = json.loads(
                (output / "market" / "metadata.json").read_text("utf-8")
            )
            provenance = json.loads((output / "provenance.json").read_text("utf-8"))
            parity = json.loads(
                (output / "parity" / "stage-parity.json").read_text("utf-8")
            )
            attribution = json.loads(
                (output / "network" / "vre-curtailment-attribution.json").read_text(
                    "utf-8"
                )
            )
            from gridform_core.bundle_validator import validate_run_bundle
            valid_bundle = validate_run_bundle(output)
            manifest_path = output / provenance["modules"]["psm"]["manifest_artifact_id"]
            manifest_path.write_text(
                manifest_path.read_text("utf-8") + "\n", encoding="utf-8"
            )
            corrupt_bundle = validate_run_bundle(output)

        self.assertEqual(result["engine"], "gridform-annual-orchestrator/v2")
        annual_stages = [
            "planning.advance_year", "psm.run", "expansion.evaluate",
            "expansion.evaluate", "investment.decide",
            "planning.admit_projects", "state_transition.apply",
        ]
        self.assertEqual([row["stage"] for row in stages], annual_stages * 2)
        self.assertEqual([row["year"] for row in stages[::7]], [2025, 2026])
        self.assertEqual({row["module_id"] for row in stages}, set(MODULES.values()) | {"value-annual-state-transition"})
        versions = {row["module_id"]: row["module_version"] for row in stages}
        self.assertEqual(versions["value-bid-at-cost-psm"], "5.1.0")
        self.assertEqual(versions["value-storage-expansion-policy"], "4.0.0")
        self.assertEqual(versions["agent-investment"], "2.2.0")
        self.assertEqual(versions["planning-pipeline"], "2.2.0")
        self.assertEqual(versions["vre-expansion-cap"], "2.0.0")
        self.assertEqual(versions["value-annual-state-transition"], "2.1.0")
        self.assertFalse((output / "market" / "balance-diagnostic.jsonl").exists())
        self.assertEqual(len(typed), 2)
        self.assertEqual(len(result["system_cost_history"]), 2)
        self.assertEqual(typed[0]["market"]["total_system_cost_gbp"], result["system_cost_history"][0]["Total_System_Cost_GBP"])
        self.assertEqual(len(result["cem_cost_ledgers"]), 2)
        self.assertEqual(result["cem_cost_ledgers"][0]["definition_id"], "value.cem-system-resource-cost/v1")
        self.assertEqual(result["cem_cost_ledgers"][0]["status"], "reconciled")
        self.assertEqual(resolved["modules"]["psm"]["module_id"], MODULES["psm"])
        self.assertEqual(resolved["modules"]["transition"]["module_id"], "value-annual-state-transition")
        self.assertEqual(market_metadata["trace_level"], "full")
        self.assertEqual(market_metadata["rows"]["period_summary"], 4)
        self.assertGreater(market_metadata["rows"]["orders"], 0)
        self.assertLess(
            market_metadata["maximum_absolute_energy_balance_residual_mwh"], 12.0
        )
        self.assertEqual(provenance["schema_version"], "value.run-provenance/v2")
        self.assertEqual(provenance["identity"]["run_id"], "application-two-year-smoke")
        self.assertEqual(len(provenance["modules"]), 7)
        self.assertEqual(len(provenance["data_bindings"]), 25)
        self.assertEqual(len(provenance["annual_state_chain"]), 2)
        self.assertEqual(
            provenance["annual_state_chain"][0]["output_state_sha256"],
            provenance["annual_state_chain"][1]["input_state_sha256"],
        )
        self.assertNotIn(folder, json.dumps(provenance))
        self.assertTrue(parity["passed"], parity["first_divergence"])
        self.assertEqual(attribution["capability_status"], "unavailable")
        self.assertEqual(
            result["vre_curtailment_attribution_artifact"],
            "network/vre-curtailment-attribution.json",
        )
        self.assertTrue(parity["contract_parity_passed"])
        self.assertIsNone(parity["retained_numerical_parity_passed"])
        self.assertIsNone(parity["release_gate_passed"])
        self.assertEqual(parity["market_evidence"]["periods"], 4)
        self.assertEqual(parity["planning_evidence"]["years"], 2)
        self.assertTrue(parity["planning_evidence"]["available"])
        self.assertFalse(parity["agent_economics_evidence"]["available"])
        self.assertTrue(typed[0]["market"]["extensions"]["live_scheme_c_clearing_invocation"])
        self.assertEqual(typed[1]["market"]["extensions"]["live_invocation_sequence"], [2025, 2026])
        sold_2025 = typed[0]["market"]["extensions"]["storage_cost_observations"]["pumpedhydro_battery"]["current_year_sold_mwh"]
        if sold_2025 > 0:
            self.assertEqual(
                typed[1]["market"]["extensions"]["storage_cost_observations"]["pumpedhydro_battery"]["pricing_basis"],
                "previous_year_sales",
            )
        self.assertTrue(valid_bundle["valid"], valid_bundle["errors"])
        self.assertFalse(corrupt_bundle["valid"])
        self.assertIn(
            "GF_BUNDLE_HASH_MISMATCH",
            {item["code"] for item in corrupt_bundle["errors"]},
        )


if __name__ == "__main__":
    unittest.main()
