from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
AUDITOR = ROOT / "scripts" / "audit_value_101_release.py"
EVIDENCE_BUILDER = ROOT / "scripts" / "build_value_101_release_evidence.py"
NETWORK_VERIFIER = ROOT / "scripts" / "verify_value_101_network_exercise.py"
RESET_VERIFIER = ROOT / "scripts" / "verify_value_101_reset_scope.py"
PACK_IDS = (
    "value-101-baseline-v1",
    "value-101-network-v1",
)
PAYLOAD_MANIFEST_NAME = "VALUE-PAYLOAD-MANIFEST.json"
PYTHON_ARCHIVE_SHA256 = "608619f8619075629c9c69f361352a0da6ed7e62f83a0e19c63e0ea32eb7629d"
NODE_ARCHIVE_SHA256 = "c97fa376d2becdc8863fcd3ca2dd9a83a9f3468ee7ccf7a6d076ec66a645c77a"
RUNTIME_POLICY_PATH = "packaging/windows-pilot/runtime-payload-policy.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_inventory_sha256(
    inventory: dict[str, dict[str, object]],
) -> tuple[str, int]:
    records = [
        {"path": name, **values}
        for name, values in sorted(inventory.items())
        if name.startswith(("runtime/", "node_modules/"))
    ]
    raw = (json.dumps(records, separators=(",", ":"), sort_keys=True) + "\n").encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest(), len(records)


def load_auditor():
    if not AUDITOR.is_file():
        raise AssertionError("Prompt 117 release auditor has not been implemented")
    spec = importlib.util.spec_from_file_location("value_101_release_auditor", AUDITOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_script(path: Path, module_name: str):
    if not path.is_file():
        raise AssertionError(f"Required verifier has not been implemented: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_network_run_pair(root: Path) -> tuple[Path, Path]:
    copperplate = root / "runs" / "run-copperplate"
    constrained = root / "runs" / "run-constrained"
    ahead_rows = []
    for period in range(96):
        ahead_rows.append(json.dumps({
            "contract_type": "AheadMarketResult",
            "payload": {
                "year": 2025 + period // 48,
                "period": period % 48,
                "period_id": f"{2025 + period // 48}:{period % 48}",
                "accepted_volume_mwh": 1.0,
                "clearing_price_gbp_per_mwh": 10.0,
                "schedule_mwh_by_asset": {"generator": 1.0},
                "storage_scheduled_action_mwh_by_asset": {},
                "extensions": {},
            },
        }, sort_keys=True))
    for run_root, run_id, project_id, role in (
        (copperplate, "run-copperplate", "study-copperplate", "copperplate_control"),
        (constrained, "run-constrained", "study-constrained", "fixed_three_zone_constrained"),
    ):
        market = run_root / "model-output" / "market"
        market.mkdir(parents=True)
        (market / "staged-market.jsonl").write_text("\n".join(ahead_rows) + "\n", "utf-8")
        status = {
            "id": run_id,
            "project_id": project_id,
            "status": "completed",
            "execution_status": "passed",
            "input_tree_sha256": f"input-{run_id}",
            "extensions": {"value_101": {"network_role": role}},
        }
        project = {
            "id": project_id,
            "revision_sha256": f"revision-{project_id}",
            "extensions": {"value_101": {"network_role": role}},
        }
        (run_root / "status.json").write_text(json.dumps(status), "utf-8")
        (run_root / "project-snapshot.json").write_text(json.dumps(project), "utf-8")
        (run_root / "artifact-index.json").write_text(
            json.dumps({"schema_version": "value.artifact-index/v1", "artifacts": []}),
            "utf-8",
        )
        (run_root / "data-pack-snapshot.json").write_text(
            json.dumps({"schema_version": "value.data-pack/v1"}), "utf-8"
        )
        (run_root / "preflight.json").write_text(
            json.dumps({"schema_version": "value.run-preflight/v1"}), "utf-8"
        )
        (run_root / "provenance.json").write_text(
            json.dumps({
                "completion": {"status": "completed"},
                "identity": {
                    "run_id": run_id,
                    "project_id": project_id,
                    "resolved_run_schema": "value.resolved-run/v2",
                    "execution_kind": "live_module",
                },
            }),
            "utf-8",
        )
        resolved = run_root / "model-output" / "resolved-run.json"
        resolved.write_text(json.dumps({
            "schema_version": "value.resolved-run/v2",
            "run_id": run_id,
            "project_id": project_id,
        }), "utf-8")
    diagnostics = constrained / "model-output" / "market" / "zonal-redispatch"
    diagnostics.mkdir()
    (diagnostics / "2025-0-diagnostics.json").write_text(json.dumps({
        "validation": {
            "maximum_equality_residual": 0.0,
            "maximum_inequality_violation": 0.0,
        }
    }), "utf-8")
    database = constrained / "model-output" / "market" / "market.sqlite"
    with sqlite3.connect(copperplate / "model-output" / "market" / "market.sqlite"):
        pass
    with sqlite3.connect(database) as connection:
        connection.executescript("""
        CREATE TABLE network_solver_diagnostics(period_id TEXT, validation_class TEXT);
        CREATE TABLE boundary_period_summary(
            utilisation_fraction REAL, transfer_mwh REAL,
            forward_capacity_mwh REAL, reverse_capacity_mwh REAL
        );
        CREATE TABLE redispatch_settlement(
            accepted_delta_mwh REAL, cashflow_to_agent_gbp REAL
        );
        CREATE TABLE zonal_period_accounting(
            network_constraint_cost_gbp REAL, blackout_mwh REAL,
            zonal_resource_cost_gbp REAL, realised_copperplate_resource_cost_gbp REAL
        );
        CREATE TABLE vre_curtailment_period(
            redispatch_added_curtailment_mwh REAL,
            redispatch_avoided_curtailment_mwh REAL,
            redispatch_net_impact_mwh REAL, total_curtailment_mwh REAL,
            identity_residual_mwh REAL
        );
        CREATE TABLE period_summary(energy_balance_residual_mwh REAL);
        """)
        for period in range(96):
            period_id = f"{2025 + period // 48}:{period % 48}"
            connection.executemany(
                "INSERT INTO network_solver_diagnostics VALUES (?, 'GO')",
                [(period_id,), (period_id,), (period_id,)],
            )
            connection.execute(
                "INSERT INTO boundary_period_summary VALUES (1, 1, 1, 1)"
            )
            connection.execute(
                "INSERT INTO zonal_period_accounting VALUES (1, 0, 2, 1)"
            )
            connection.execute(
                "INSERT INTO vre_curtailment_period VALUES (0, 0, 0, 0, 0)"
            )
            connection.execute("INSERT INTO period_summary VALUES (0)")
        connection.execute("INSERT INTO redispatch_settlement VALUES (1, 5)")
    for run_root in (copperplate, constrained):
        artifacts = []
        for path in sorted(run_root.rglob("*")):
            if not path.is_file() or path.name == "artifact-index.json":
                continue
            artifacts.append({
                "artifact_id": path.relative_to(run_root).as_posix(),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            })
        (run_root / "artifact-index.json").write_text(json.dumps({
            "schema_version": "value.artifact-index/v1",
            "artifacts": artifacts,
        }), "utf-8")
    return copperplate, constrained


def build_fixture(root: Path) -> tuple[Path, Path]:
    required_files = (
        "README.md",
        "docs/tutorial/VALUE_101.md",
        "docs/tutorial/VALUE_101_ZH.md",
        "docs/tutorial/VALUE_101_QUICK_CARD.md",
        "docs/tutorial/JOHN_PILOT_RUNBOOK.md",
        "output/pdf/VALUE_101_guide.pdf",
        "packaging/windows-pilot/ValueInstaller.cs",
        "packaging/windows-pilot/ValueInstallerWindow.cs",
        "packaging/windows-pilot/start-portable.ps1",
    )
    for name in required_files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"VALUE 101 fixture\n")

    product = {
        "product_name": "VALUE",
        "entrypoint": "VALUE-Setup.exe",
        "install_scope": "current-user",
        "administrator_required": False,
        "terminal_required": False,
        "internet_required_after_download": False,
        "progress_window": True,
        "data_licence": "CC0-1.0",
        "data_packs": list(PACK_IDS),
    }
    product_path = root / "packaging/windows-pilot/product.json"
    product_path.write_text(json.dumps(product), "utf-8")

    fixture_runtime_inventory = {
        "runtime/python/python.exe": {"sha256": "a" * 64, "bytes": 1},
        "runtime/node/node.exe": {"sha256": "b" * 64, "bytes": 1},
    }
    runtime_digest, runtime_count = runtime_inventory_sha256(
        fixture_runtime_inventory
    )
    runtime_policy = root / RUNTIME_POLICY_PATH
    runtime_policy.write_text(
        json.dumps(
            {
                "schema_version": "value.101-runtime-payload-policy/v1",
                "runtime_inventory_sha256": runtime_digest,
                "runtime_member_count": runtime_count,
            }
        ),
        "utf-8",
    )

    for pack_id in PACK_IDS:
        pack_root = root / "data-packs" / pack_id
        bindings = {}
        for index in range(25):
            source = pack_root / "files" / f"role-{index}.csv"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("period,value\n1,1\n", "utf-8")
            bindings[f"test.role.{index}"] = {
                "uri": f"files/role-{index}.csv",
                "sha256": sha256(source),
                "licence": "CC0-1.0",
            }
        manifest = {
            "schema_version": "value.data-pack/v1",
            "id": pack_id,
            "name": pack_id,
            "licence": "CC0-1.0",
            "teaching_only": True,
            "annual_economics_eligible": False,
            "bindings": bindings,
        }
        (pack_root / "manifest.json").write_text(json.dumps(manifest), "utf-8")

    for name in ("app/page.tsx", "dist/server/index.js", "dist/client/app.js"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("VALUE 101 public surface\n", "utf-8")
    (root / "source-release-manifest.json").write_text(json.dumps({
        "include": [
            "README.md",
            "docs/tutorial",
            "packaging/windows-pilot",
            "app",
            "requirements",
            "source-release-manifest.json",
        ],
        "local_only_source_content": [],
    }), "utf-8")
    lock = root / "requirements" / "value-all-py310.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("fixture==1.0 --hash=sha256:" + "a" * 64 + "\n", "utf-8")

    installer = root / "dist/windows-pilot/VALUE-Setup.exe"
    installer.parent.mkdir(parents=True)
    installer.write_bytes(b"VALUE-101-INSTALLER" * 128)
    installer.with_name(installer.name + ".sha256.txt").write_text(
        f"{sha256(installer)}  {installer.name}\n", "ascii"
    )

    network_accounting = {
        "status": "reconciled",
        "energy_balance_residual_mwh": 0.0,
        "soc_residual_mwh": 0.0,
        "corridor_capacity_violation_mwh": 0.0,
        "curtailment_identity_residual_mwh": 0.0,
        "cost_residual_gbp": 0.0,
    }
    network_report = root / "publication/value-101-network-verification.json"
    network_report.parent.mkdir(parents=True, exist_ok=True)
    network_verification = {
        "schema_version": "value.101-network-live-verification/v2",
        "decision": "PASS",
        "checks": {"actual_saved_runs_verified": True},
        "run_identity": {
            "copperplate": {"run_id": "run-copperplate", "project_id": "study-copperplate"},
            "constrained": {"run_id": "run-constrained", "project_id": "study-constrained"},
        },
        "network_accounting": network_accounting,
    }
    network_report.write_text(json.dumps(network_verification), "utf-8")

    evidence = {
        "schema_version": "value.101-release-evidence/v1",
        "source_control": {
            "commit": "fixture-commit",
            "dirty_paths": [],
            "allowed_dirty_paths": [],
        },
        "public_module_ids": [
            "value-bid-at-cost-psm",
            "dynamic-annual-storage-cost",
            "value-legacy-storage-tariff",
        ],
        "api_routes": {
            "health": True,
            "tutorial": True,
            "completion_report": True,
            "data_packs": True,
        },
        "scientific_boundary": {
            "label": "Teaching diagnostic: not annual economics",
            "annual_economics_eligible": False,
            "periods_per_year": 48,
            "years": 2,
        },
        "comparison": {
            "scope": "teaching_window",
            "annual_economics_eligible": False,
            "warning": "Short synthetic teaching-window totals; not annual British evidence.",
            "comparison_gate": {"status": "controlled", "violations": []},
            "rows": [
                {"variant_kind": "baseline", "declared_changed_dimensions": [], "actual_changed_dimensions": []},
                {"variant_kind": "data", "declared_changed_dimensions": ["data_pack_id"], "actual_changed_dimensions": ["data_pack_id"]},
                {"variant_kind": "storage", "declared_changed_dimensions": ["modules.storage_cost"], "actual_changed_dimensions": ["modules.storage_cost"]},
            ],
        },
        "comparison_run_roots": {
            "baseline": str(root / "runs/baseline"),
            "data": str(root / "runs/data"),
            "storage": str(root / "runs/storage"),
        },
        "network_accounting": network_accounting,
        "network_accounting_source": str(network_report),
        "network_run_roots": {
            "copperplate": str(root / "runs/run-copperplate"),
            "constrained": str(root / "runs/run-constrained"),
        },
        "reset_scope": {
            "passed": True,
            "api_exercised": True,
            "unrelated_state_unchanged": True,
            "unrelated_tree_sha256_before": "reset-tree",
            "unrelated_tree_sha256_after": "reset-tree",
            "trash_member_sha256": {"studies/value-study/project.json": "reset-item"},
        },
        "scheme_c_hashes": {"passed": True, "modified_files": []},
        "test_evidence": {
            "python_suite": True,
            "frontend_lint": True,
            "frontend_build": True,
            "rendered_html": True,
            "clean_install": True,
        },
        "clean_user_journey": {
            "passed": True,
            "mandatory_elapsed_seconds": 900,
            "mandatory_steps_completed": 7,
            "developer_interventions": 0,
        },
    }
    evidence_path = root / "publication/value-101-release-evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence), "utf-8")
    return installer, evidence_path


def _fixture_inventory_base(root: Path) -> dict[str, dict[str, object]]:
    inventory: dict[str, dict[str, object]] = {}
    aliases = {
        "output/pdf/VALUE_101_guide.pdf": "START-HERE-VALUE-101-Guide.pdf",
    }
    candidates = [
        root / "README.md",
        root / "source-release-manifest.json",
        root / "app/page.tsx",
        root / "requirements/value-all-py310.lock",
        root / "output/pdf/VALUE_101_guide.pdf",
        *(root / "docs/tutorial").glob("*"),
        *(root / "packaging/windows-pilot").glob("*"),
        root / "dist/server/index.js",
        root / "dist/client/app.js",
    ]
    for pack_id in PACK_IDS:
        candidates.extend((root / "data-packs" / pack_id).rglob("*"))
    for path in candidates:
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        payload_path = aliases.get(relative, relative)
        inventory[payload_path] = {"sha256": sha256(path), "bytes": path.stat().st_size}
    inventory["runtime/python/python.exe"] = {"sha256": "a" * 64, "bytes": 1}
    inventory["runtime/node/node.exe"] = {"sha256": "b" * 64, "bytes": 1}
    return inventory


def fixture_payload_manifest(root: Path) -> tuple[dict[str, object], str, int]:
    inventory = _fixture_inventory_base(root)
    runtime_digest, runtime_count = runtime_inventory_sha256(inventory)
    payload = {
        "schema_version": "value.101-installer-payload/v1",
        "build_inputs": {
            "python_archive_sha256": PYTHON_ARCHIVE_SHA256,
            "node_archive_sha256": NODE_ARCHIVE_SHA256,
            "python_lock_sha256": sha256(root / "requirements/value-all-py310.lock"),
        },
        "runtime_inventory_sha256": runtime_digest,
        "runtime_member_count": runtime_count,
        "members": [
            {"path": name, **values}
            for name, values in sorted(inventory.items())
        ],
    }
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return payload, hashlib.sha256(raw).hexdigest(), len(raw)


def fixture_inventory(root: Path) -> dict[str, dict[str, object]]:
    inventory = _fixture_inventory_base(root)
    _, manifest_hash, manifest_bytes = fixture_payload_manifest(root)
    inventory[PAYLOAD_MANIFEST_NAME] = {
        "sha256": manifest_hash,
        "bytes": manifest_bytes,
    }
    return inventory


def independent_overrides(auditor, root: Path, evidence_path: Path):
    evidence = json.loads(evidence_path.read_text("utf-8"))
    network = json.loads(Path(evidence["network_accounting_source"]).read_text("utf-8"))
    return (
        patch.object(auditor, "_read_installer_inventory", return_value=fixture_inventory(root)),
        patch.object(auditor, "_audit_source_control", return_value={"commit": "fixture", "dirty_paths": [], "unexpected_dirty_paths": []}),
        patch.object(auditor, "_probe_api", return_value={"routes": {"health": True, "tutorial": True, "completion_report": True, "data_packs": True, "workspace": True}, "public_module_ids": evidence["public_module_ids"]}),
        patch.object(auditor, "_recompute_comparison", return_value=evidence["comparison"]),
        patch.object(auditor, "_audit_retained_sources", return_value={"passed": True, "modified_files": []}),
        patch.object(auditor, "_recompute_network_verification", return_value=network),
        patch.object(auditor, "_recompute_reset_scope", return_value=evidence["reset_scope"]),
        patch.object(
            auditor,
            "_read_installer_payload_manifest",
            return_value=fixture_payload_manifest(root),
        ),
    )


class Value101ReleaseGateTests(unittest.TestCase):
    def test_network_verifier_binds_metrics_to_two_explicit_completed_saved_runs(self) -> None:
        verifier = load_script(NETWORK_VERIFIER, "value_101_network_verifier")
        with tempfile.TemporaryDirectory(prefix="value-101-network-bind-") as temporary:
            copperplate, constrained = build_network_run_pair(Path(temporary))
            report = verifier.verify_network_pair(copperplate, constrained)
            first_hash = report["run_identity"]["constrained"]["artifact_index_sha256"]
            (constrained / "artifact-index.json").write_text('{"tampered": true}', "utf-8")
            changed = verifier.verify_network_pair(copperplate, constrained)
        self.assertEqual(report["decision"], "PASS", report)
        self.assertTrue(report["checks"]["actual_saved_runs_verified"])
        self.assertEqual(report["run_identity"]["copperplate"]["run_id"], "run-copperplate")
        self.assertEqual(report["run_identity"]["constrained"]["project_id"], "study-constrained")
        self.assertNotEqual(
            first_hash,
            changed["run_identity"]["constrained"]["artifact_index_sha256"],
        )

    def test_network_verifier_rejects_an_empty_or_unverified_artifact_index(self) -> None:
        verifier = load_script(NETWORK_VERIFIER, "value_101_network_index_verifier")
        with tempfile.TemporaryDirectory(prefix="value-101-network-index-") as temporary:
            copperplate, constrained = build_network_run_pair(Path(temporary))
            (constrained / "artifact-index.json").write_text(json.dumps({
                "schema_version": "value.artifact-index/v1",
                "artifacts": [],
            }), "utf-8")
            report = verifier.verify_network_pair(copperplate, constrained)
        self.assertEqual(report["decision"], "FAIL")
        self.assertFalse(report["checks"]["actual_saved_runs_verified"])

    def test_network_verifier_never_creates_a_missing_run_database(self) -> None:
        verifier = load_script(NETWORK_VERIFIER, "value_101_network_no_mutation")
        with tempfile.TemporaryDirectory(prefix="value-101-network-missing-db-") as temporary:
            copperplate, constrained = build_network_run_pair(Path(temporary))
            database = constrained / "model-output" / "market" / "market.sqlite"
            database.unlink()
            with self.assertRaisesRegex(ValueError, "market.sqlite"):
                verifier.verify_network_pair(copperplate, constrained)
            self.assertFalse(database.exists())

    def test_network_verifier_rejects_unsealed_sqlite_sidecars(self) -> None:
        verifier = load_script(NETWORK_VERIFIER, "value_101_network_wal_boundary")
        with tempfile.TemporaryDirectory(prefix="value-101-network-wal-") as temporary:
            copperplate, constrained = build_network_run_pair(Path(temporary))
            wal = constrained / "model-output" / "market" / "market.sqlite-wal"
            wal.write_bytes(b"unsealed committed bytes")
            report = verifier.verify_network_pair(copperplate, constrained)
        self.assertEqual(report["decision"], "FAIL", report)
        self.assertFalse(report["checks"]["actual_saved_runs_verified"])
        self.assertIn(
            "unsealed SQLite sidecar: model-output/market/market.sqlite-wal",
            report["run_identity"]["constrained"]["artifact_index_errors"],
        )

    def test_reset_verifier_exercises_loopback_api_and_hashes_unrelated_state(self) -> None:
        verifier = load_script(RESET_VERIFIER, "value_101_reset_verifier")
        report = verifier.verify_reset_scope()
        self.assertTrue(report["passed"], report)
        self.assertTrue(report["api_exercised"])
        self.assertTrue(report["unrelated_state_unchanged"])
        self.assertEqual(
            report["unrelated_tree_sha256_before"],
            report["unrelated_tree_sha256_after"],
        )
        self.assertTrue(report["trash_member_sha256"])

    def test_value_101_reset_moves_only_guided_course_records(self) -> None:
        from backend import server

        with tempfile.TemporaryDirectory(prefix="value-101-reset-scope-") as temporary:
            state = Path(temporary)
            projects = state / "projects"
            runs = state / "runs"
            trash = state / "trash"
            guided = {
                "extensions": {
                    "value_101": {
                        "origin": "guided-course",
                        "course_revision": "value-101/v1",
                        "variant_kind": "baseline",
                    }
                }
            }
            for root, name, filename, payload in (
                (projects, "value-study", "project.json", guided),
                (projects, "ordinary-study", "project.json", {"id": "ordinary-study"}),
                (runs, "value-run", "status.json", {**guided, "status": "completed"}),
                (runs, "ordinary-run", "status.json", {"id": "ordinary-run", "status": "completed"}),
            ):
                path = root / name / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload), "utf-8")
            with patch.object(server, "PROJECTS_ROOT", projects), patch.object(
                server, "RUNS_ROOT", runs
            ), patch.object(server, "TRASH_ROOT", trash):
                study_paths, run_paths = server._value_101_reset_records()
                report = server._move_value_101_reset_records(study_paths, run_paths)
            self.assertEqual(report["deleted_study_ids"], ["value-study"])
            self.assertEqual(report["deleted_run_ids"], ["value-run"])
            self.assertTrue(report["recoverable"])
            self.assertTrue((projects / "ordinary-study" / "project.json").is_file())
            self.assertTrue((runs / "ordinary-run" / "status.json").is_file())
            self.assertFalse((projects / "value-study").exists())
            self.assertFalse((runs / "value-run").exists())

    def test_value_101_reset_rolls_back_every_move_when_a_later_move_fails(self) -> None:
        from backend import server

        with tempfile.TemporaryDirectory(prefix="value-101-reset-rollback-") as temporary:
            state = Path(temporary)
            projects = state / "projects"
            runs = state / "runs"
            trash = state / "trash"
            guided = {"extensions": {"value_101": {"origin": "guided-course"}}}
            study = projects / "value-study"
            run = runs / "value-run"
            study.mkdir(parents=True)
            run.mkdir(parents=True)
            (study / "project.json").write_text(json.dumps(guided), "utf-8")
            (run / "status.json").write_text(
                json.dumps({**guided, "status": "completed"}), "utf-8"
            )
            real_move = shutil.move
            calls = 0

            def fail_second_move(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected reset failure")
                return real_move(source, destination)

            with patch.object(server, "PROJECTS_ROOT", projects), patch.object(
                server, "RUNS_ROOT", runs
            ), patch.object(server, "TRASH_ROOT", trash), patch.object(
                server.shutil, "move", side_effect=fail_second_move
            ):
                with self.assertRaisesRegex(OSError, "injected reset failure"):
                    server._move_value_101_reset_records([study], [run])
            self.assertTrue((study / "project.json").is_file())
            self.assertTrue((run / "status.json").is_file())
            self.assertFalse(any(trash.rglob("project.json")) if trash.exists() else False)

    def test_value_101_reset_retains_trash_when_move_back_also_fails(self) -> None:
        from backend import server

        with tempfile.TemporaryDirectory(prefix="value-101-reset-double-failure-") as temporary:
            state = Path(temporary)
            projects = state / "projects"
            runs = state / "runs"
            trash = state / "trash"
            study = projects / "value-study"
            run = runs / "value-run"
            study.mkdir(parents=True)
            run.mkdir(parents=True)
            (study / "project.json").write_text("{}", "utf-8")
            (run / "status.json").write_text('{"status":"completed"}', "utf-8")
            real_move = shutil.move
            calls = 0

            def fail_forward_then_rollback(source, destination):
                nonlocal calls
                calls += 1
                if calls in (2, 3):
                    raise OSError(f"injected move failure {calls}")
                return real_move(source, destination)

            with patch.object(server, "PROJECTS_ROOT", projects), patch.object(
                server, "RUNS_ROOT", runs
            ), patch.object(server, "TRASH_ROOT", trash), patch.object(
                server.shutil, "move", side_effect=fail_forward_then_rollback
            ):
                with self.assertRaisesRegex(RuntimeError, "rollback was incomplete"):
                    server._move_value_101_reset_records([study], [run])
            retained = list(trash.rglob("project.json"))
            self.assertEqual(len(retained), 1)
            self.assertEqual(retained[0].read_text("utf-8"), "{}")

    def test_default_evidence_has_an_executable_production_builder(self) -> None:
        self.assertTrue(EVIDENCE_BUILDER.is_file(), EVIDENCE_BUILDER)
        source = EVIDENCE_BUILDER.read_text("utf-8")
        for required in (
            "prompt117-value-101-evidence.json",
            "comparison_run_roots",
            "network_accounting_source",
            "_recompute_comparison",
            "_probe_api",
            "_audit_retained_sources",
        ):
            self.assertIn(required, source)

    def test_gate_reports_six_distinct_blocking_conditions(self) -> None:
        auditor = load_auditor()
        with tempfile.TemporaryDirectory(prefix="value-101-release-invalid-") as temporary:
            root = Path(temporary)
            installer, evidence_path = build_fixture(root)
            installer.write_bytes(b"x")
            corrupt = root / "data-packs/value-101-baseline-v1/files/role-0.csv"
            corrupt.write_text("corrupt\n", "utf-8")
            evidence = json.loads(evidence_path.read_text("utf-8"))
            evidence["scientific_boundary"]["annual_economics_eligible"] = True
            evidence["public_module_ids"].append("value-reference-ac-feasibility")
            (root / "app/page.tsx").write_text("AC feasibility", "utf-8")
            evidence["comparison"]["rows"][1]["declared_changed_dimensions"].append(
                "modules.psm"
            )
            network_report = Path(evidence["network_accounting_source"])
            network_payload = json.loads(network_report.read_text("utf-8"))
            network_payload["network_accounting"]["energy_balance_residual_mwh"] = 1.0
            network_report.write_text(json.dumps(network_payload), "utf-8")
            evidence_path.write_text(json.dumps(evidence), "utf-8")

            report = auditor.audit_release(
                root,
                installer,
                evidence_path,
                minimum_installer_bytes=100,
            )

        codes = set(report["blocking_codes"])
        self.assertTrue(
            {
                "INSTALLER_INCOMPLETE",
                "UNCONTROLLED_COMPARISON",
                "TEACHING_ANNUALISED",
                "PUBLIC_AC_EXPOSED",
                "PACK_HASH_MISMATCH",
                "NETWORK_LEDGER_IMBALANCE",
            }.issubset(codes),
            codes,
        )
        self.assertFalse(report["release_gate_passed"])

    def test_valid_fixture_passes_and_markdown_renders_the_same_decision(self) -> None:
        auditor = load_auditor()
        with tempfile.TemporaryDirectory(prefix="value-101-release-valid-") as temporary:
            root = Path(temporary)
            installer, evidence_path = build_fixture(root)
            overrides = independent_overrides(auditor, root, evidence_path)
            with overrides[0], overrides[1], overrides[2], overrides[3], overrides[4], overrides[5], overrides[6], overrides[7]:
                report = auditor.audit_release(
                    root,
                    installer,
                    evidence_path,
                    minimum_installer_bytes=100,
                )
            markdown = auditor.render_markdown(report)

        self.assertTrue(report["release_gate_passed"], report["blocking_codes"])
        self.assertEqual(report["blocking_codes"], [])
        self.assertEqual(report["release_scope"], "formal_value_windows_product")
        self.assertEqual(
            report["data_packs"]["expected_pack_ids"],
            ["value-101-baseline-v1", "value-101-network-v1"],
        )
        self.assertNotIn("pilot", report["claim_boundary"].lower())
        self.assertIn("GO", markdown)
        self.assertIn("VALUE Windows product release-gate report", markdown)
        self.assertIn(report["installer"]["sha256"], markdown)

    def test_release_gate_rejects_retired_installer_filename(self) -> None:
        auditor = load_auditor()
        with tempfile.TemporaryDirectory(prefix="value-101-release-retired-name-") as temporary:
            root = Path(temporary)
            installer, evidence_path = build_fixture(root)
            retired = installer.with_name("VALUE-101-Setup.exe")
            installer.rename(retired)
            installer.with_name(installer.name + ".sha256.txt").rename(
                retired.with_name(retired.name + ".sha256.txt")
            )
            overrides = independent_overrides(auditor, root, evidence_path)
            with overrides[0], overrides[1], overrides[2], overrides[3], overrides[4], overrides[5], overrides[6], overrides[7]:
                report = auditor.audit_release(
                    root, retired, evidence_path, minimum_installer_bytes=100
                )

        self.assertFalse(report["release_gate_passed"])
        self.assertIn("INSTALLER_IDENTITY_INVALID", report["blocking_codes"])
        self.assertTrue(report["installer"]["checksum_matches"])

    def test_dummy_executable_cannot_pass_from_self_declared_evidence(self) -> None:
        auditor = load_auditor()
        with tempfile.TemporaryDirectory(prefix="value-101-release-dummy-") as temporary:
            root = Path(temporary)
            installer, evidence_path = build_fixture(root)
            report = auditor.audit_release(root, installer, evidence_path, minimum_installer_bytes=100)
        self.assertFalse(report["release_gate_passed"])
        self.assertIn("INSTALLER_PAYLOAD_UNVERIFIED", report["blocking_codes"])

    def test_public_source_scan_blocks_hidden_ac_ui(self) -> None:
        auditor = load_auditor()
        with tempfile.TemporaryDirectory(prefix="value-101-release-ac-ui-") as temporary:
            root = Path(temporary)
            installer, evidence_path = build_fixture(root)
            (root / "app/page.tsx").write_text(
                'fetch("/api/runs/x/domains/ac/results") // AC feasibility', "utf-8"
            )
            overrides = independent_overrides(auditor, root, evidence_path)
            with overrides[0], overrides[1], overrides[2], overrides[3], overrides[4], overrides[5], overrides[6], overrides[7]:
                report = auditor.audit_release(root, installer, evidence_path, minimum_installer_bytes=100)
        self.assertIn("PUBLIC_AC_EXPOSED", report["blocking_codes"])

    def test_release_gate_rejects_a_hand_written_network_summary(self) -> None:
        auditor = load_auditor()
        with tempfile.TemporaryDirectory(prefix="value-101-network-forgery-") as temporary:
            root = Path(temporary)
            installer, evidence_path = build_fixture(root)
            evidence = json.loads(evidence_path.read_text("utf-8"))
            report_path = Path(evidence["network_accounting_source"])
            forged = json.loads(report_path.read_text("utf-8"))
            forged["run_identity"]["constrained"]["run_id"] = "invented-run"
            report_path.write_text(json.dumps(forged), "utf-8")
            expected = json.loads(json.dumps(forged))
            expected["run_identity"]["constrained"]["run_id"] = "run-constrained"
            overrides = independent_overrides(auditor, root, evidence_path)
            with overrides[0], overrides[1], overrides[2], overrides[3], overrides[4], patch.object(
                auditor, "_recompute_network_verification", return_value=expected
            ), overrides[6], overrides[7]:
                report = auditor.audit_release(root, installer, evidence_path, minimum_installer_bytes=100)
        self.assertIn("NETWORK_EVIDENCE_UNVERIFIED", report["blocking_codes"])

    def test_installer_payload_rejects_any_unallowlisted_member(self) -> None:
        auditor = load_auditor()
        with tempfile.TemporaryDirectory(prefix="value-101-payload-forgery-") as temporary:
            root = Path(temporary)
            installer, evidence_path = build_fixture(root)
            inventory = fixture_inventory(root)
            inventory["secret.txt"] = {"sha256": "f" * 64, "bytes": 6}
            overrides = independent_overrides(auditor, root, evidence_path)
            with patch.object(auditor, "_read_installer_inventory", return_value=inventory), overrides[1], overrides[2], overrides[3], overrides[4], overrides[5], overrides[6], overrides[7]:
                report = auditor.audit_release(root, installer, evidence_path, minimum_installer_bytes=100)
        self.assertIn("INSTALLER_PAYLOAD_MISMATCH", report["blocking_codes"])
        mismatches = report["installer"]["payload"]["mismatches"]
        self.assertIn(
            {"path": "secret.txt", "reason": "unexpected payload member"},
            mismatches,
        )

    def test_installer_rejects_consistently_manifested_unapproved_data_pack(self) -> None:
        auditor = load_auditor()
        with tempfile.TemporaryDirectory(prefix="value-unapproved-pack-") as temporary:
            root = Path(temporary)
            installer, evidence_path = build_fixture(root)
            inventory = _fixture_inventory_base(root)
            inventory["data-packs/value-101-windy-v1/manifest.json"] = {
                "sha256": "c" * 64,
                "bytes": 17,
            }
            runtime_digest, runtime_count = runtime_inventory_sha256(inventory)
            payload = {
                "schema_version": "value.101-installer-payload/v1",
                "build_inputs": {
                    "python_archive_sha256": PYTHON_ARCHIVE_SHA256,
                    "node_archive_sha256": NODE_ARCHIVE_SHA256,
                    "python_lock_sha256": sha256(
                        root / "requirements/value-all-py310.lock"
                    ),
                },
                "runtime_inventory_sha256": runtime_digest,
                "runtime_member_count": runtime_count,
                "members": [
                    {"path": name, **values}
                    for name, values in sorted(inventory.items())
                ],
            }
            raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            )
            actual_inventory = dict(inventory)
            actual_inventory[PAYLOAD_MANIFEST_NAME] = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
            overrides = independent_overrides(auditor, root, evidence_path)
            with patch.object(
                auditor, "_read_installer_inventory", return_value=actual_inventory
            ), overrides[1], overrides[2], overrides[3], overrides[4], overrides[5], overrides[6], patch.object(
                auditor,
                "_read_installer_payload_manifest",
                return_value=(payload, hashlib.sha256(raw).hexdigest(), len(raw)),
            ):
                report = auditor.audit_release(
                    root, installer, evidence_path, minimum_installer_bytes=100
                )

        self.assertFalse(report["release_gate_passed"])
        self.assertIn("INSTALLER_UNAPPROVED_DATA_PACK", report["blocking_codes"])
        self.assertEqual(
            report["installer"]["payload"]["unapproved_data_pack_ids"],
            ["value-101-windy-v1"],
        )

    def test_installer_payload_rejects_unmanifested_runtime_startup_code(self) -> None:
        auditor = load_auditor()
        with tempfile.TemporaryDirectory(prefix="value-101-runtime-forgery-") as temporary:
            root = Path(temporary)
            installer, evidence_path = build_fixture(root)
            inventory = fixture_inventory(root)
            inventory["runtime/python/Lib/site-packages/sitecustomize.py"] = {
                "sha256": "e" * 64,
                "bytes": 12,
            }
            overrides = independent_overrides(auditor, root, evidence_path)
            with patch.object(auditor, "_read_installer_inventory", return_value=inventory), overrides[1], overrides[2], overrides[3], overrides[4], overrides[5], overrides[6], overrides[7]:
                report = auditor.audit_release(root, installer, evidence_path, minimum_installer_bytes=100)
        self.assertIn("INSTALLER_PAYLOAD_MISMATCH", report["blocking_codes"])
        self.assertIn(
            {
                "path": "runtime/python/Lib/site-packages/sitecustomize.py",
                "reason": "unexpected payload member",
            },
            report["installer"]["payload"]["mismatches"],
        )

    def test_installer_payload_rejects_self_manifested_runtime_injection(self) -> None:
        auditor = load_auditor()
        with tempfile.TemporaryDirectory(prefix="value-101-runtime-policy-") as temporary:
            root = Path(temporary)
            installer, evidence_path = build_fixture(root)
            inventory = _fixture_inventory_base(root)
            inventory["runtime/python/Lib/site-packages/sitecustomize.py"] = {
                "sha256": "e" * 64,
                "bytes": 12,
            }
            runtime_digest, runtime_count = runtime_inventory_sha256(inventory)
            payload = {
                "schema_version": "value.101-installer-payload/v1",
                "build_inputs": {
                    "python_archive_sha256": PYTHON_ARCHIVE_SHA256,
                    "node_archive_sha256": NODE_ARCHIVE_SHA256,
                    "python_lock_sha256": sha256(
                        root / "requirements/value-all-py310.lock"
                    ),
                },
                "runtime_inventory_sha256": runtime_digest,
                "runtime_member_count": runtime_count,
                "members": [
                    {"path": name, **values}
                    for name, values in sorted(inventory.items())
                ],
            }
            raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            )
            actual_inventory = dict(inventory)
            actual_inventory[PAYLOAD_MANIFEST_NAME] = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
            overrides = independent_overrides(auditor, root, evidence_path)
            with patch.object(
                auditor, "_read_installer_inventory", return_value=actual_inventory
            ), overrides[1], overrides[2], overrides[3], overrides[4], overrides[5], overrides[6], patch.object(
                auditor,
                "_read_installer_payload_manifest",
                return_value=(payload, hashlib.sha256(raw).hexdigest(), len(raw)),
            ):
                report = auditor.audit_release(
                    root, installer, evidence_path, minimum_installer_bytes=100
                )
        self.assertIn("INSTALLER_PAYLOAD_MISMATCH", report["blocking_codes"])
        self.assertIn(
            {
                "path": RUNTIME_POLICY_PATH,
                "reason": "runtime inventory differs from source-controlled policy",
            },
            report["installer"]["payload"]["mismatches"],
        )


if __name__ == "__main__":
    unittest.main()
