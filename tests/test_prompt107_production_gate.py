import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

import scripts.run_prompt107_production_gate as production_gate
from scripts.run_prompt107_production_gate import (
    BASE_PACK_ID,
    EXPECTED_FAILED_PERIOD,
    NETWORK_PACK_ID,
    NETWORK_SCIENTIFIC_SHA256,
    STAGE_ORDER,
    ProductionGateError,
    build_application_stage_executor,
    derive_execution_studies,
    execute_production_gate,
    ensure_source_root,
    read_exact_failed_period_evidence,
    resolve_required_packs,
    run_stage_sequence,
)
from gridform_core.market_ledger import validate_market_ledger_file


def _write_manifest(root: Path, payload: dict[str, object]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _pack_store(tmp_path: Path) -> Path:
    base_root = tmp_path / "data-packs" / BASE_PACK_ID
    base_root.mkdir(parents=True, exist_ok=True)
    demand = base_root / "files" / "demand.csv"
    demand.parent.mkdir(parents=True, exist_ok=True)
    demand.write_bytes(b"period,demand_mwh\n0,1\n")
    _write_manifest(
        base_root,
        {
            "schema_version": "value.data-pack/v1",
            "id": BASE_PACK_ID,
            "bindings": {
                "demand.real": {
                    "uri": "files/demand.csv",
                    "sha256": hashlib.sha256(demand.read_bytes()).hexdigest(),
                    "redistribution_class": "redistributable_open",
                    "licence": "fixture",
                    "attribution": "fixture",
                }
            },
        },
    )
    _write_manifest(
        tmp_path / "data-workbench" / "installed-packs" / NETWORK_PACK_ID,
        {
            "schema_version": "value.data-pack/v1",
            "id": NETWORK_PACK_ID,
            "data_pack_type": "network_overlay",
            "zonal_network_pack": {
                "network_pack_id": NETWORK_PACK_ID,
                "scientific_sha256": NETWORK_SCIENTIFIC_SHA256,
            },
            "owner_approval": {
                "network_pack_id": NETWORK_PACK_ID,
                "installed_scientific_sha256": NETWORK_SCIENTIFIC_SHA256,
            },
            "bindings": {
                role: {"uri": f"files/{role}.json"}
                for role in (
                    "value.zonal.zones",
                    "value.zonal.corridors",
                    "value.zonal.cutsets",
                    "value.zonal.asset-map",
                    "value.zonal.demand",
                    "value.zonal.ratings",
                    "value.zonal.interconnector-landings",
                    "value.zonal.spatial-audit",
                )
            },
        },
    )
    return tmp_path


def test_missing_base_pack_hard_fails_without_scheme_c_or_synthetic_substitution(
    tmp_path: Path,
) -> None:
    _write_manifest(
        tmp_path / "data-packs" / "uk-scheme-c",
        {"schema_version": "value.data-pack/v1", "id": "uk-scheme-c"},
    )
    _write_manifest(
        tmp_path / "data-packs" / "value-synthetic-contract-pack-v1",
        {
            "schema_version": "value.data-pack/v1",
            "id": "value-synthetic-contract-pack-v1",
        },
    )

    with pytest.raises(ProductionGateError) as caught:
        resolve_required_packs(tmp_path)

    assert caught.value.code == "GF_PROMPT107_BASE_PACK_MISSING"
    assert caught.value.evidence["required_pack_id"] == BASE_PACK_ID
    assert "uk-scheme-c" not in caught.value.evidence.get("selected_pack_id", "")
    assert "synthetic" not in caught.value.evidence.get("selected_pack_id", "")


def test_real_gate_attempt_records_missing_base_and_invokes_no_stage(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    output = tmp_path / "outputs"

    report = execute_production_gate(
        through="168h",
        output_root=output,
        data_root=tmp_path / "force-data",
        execute_stage=lambda stage_id, _packs: calls.append(stage_id) or {},
    )

    assert calls == []
    assert report["decision"] == "NO-GO"
    assert report["stop_decision"] == {
        "error_code": "GF_PROMPT107_BASE_PACK_MISSING",
        "stopped_before": "smoke",
        "not_started": ["smoke", "exact-periods", "24h", "168h"],
        "prompt105_ten_year_started": False,
    }
    assert report["invoked_stages"] == []
    assert report["pack_resolution"]["base_pack"]["status"] == "missing"
    assert json.loads(
        (output / "prompt107-production-gate.json").read_text(encoding="utf-8")
    ) == report


@pytest.mark.parametrize(
    ("target", "replacement_id", "code"),
    (
        ("base", "wrong-base-pack", "GF_PROMPT107_BASE_PACK_ID_MISMATCH"),
        ("network", "wrong-network-pack", "GF_PROMPT107_NETWORK_PACK_ID_MISMATCH"),
    ),
)
def test_pack_directory_name_never_overrides_manifest_identity(
    tmp_path: Path,
    target: str,
    replacement_id: str,
    code: str,
) -> None:
    data_root = _pack_store(tmp_path)
    manifest = (
        data_root / "data-packs" / BASE_PACK_ID / "manifest.json"
        if target == "base"
        else data_root
        / "data-workbench"
        / "installed-packs"
        / NETWORK_PACK_ID
        / "manifest.json"
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["id"] = replacement_id
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProductionGateError) as caught:
        resolve_required_packs(data_root)

    assert caught.value.code == code
    assert caught.value.evidence == {
        "expected_pack_id": BASE_PACK_ID if target == "base" else NETWORK_PACK_ID,
        "observed_pack_id": replacement_id,
        "manifest": str(manifest.resolve()),
    }


def test_network_scientific_hash_must_match_the_owner_approved_install(
    tmp_path: Path,
) -> None:
    data_root = _pack_store(tmp_path)
    manifest = (
        data_root
        / "data-workbench"
        / "installed-packs"
        / NETWORK_PACK_ID
        / "manifest.json"
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["zonal_network_pack"]["scientific_sha256"] = "0" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProductionGateError) as caught:
        resolve_required_packs(data_root)

    assert caught.value.code == "GF_PROMPT107_NETWORK_PACK_HASH_MISMATCH"
    assert caught.value.evidence["required_scientific_sha256"] == (
        NETWORK_SCIENTIFIC_SHA256
    )
    assert caught.value.evidence["observed_scientific_sha256"] == "0" * 64


def _failed_period_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE vre_curtailment_period(
                year INTEGER NOT NULL,
                period INTEGER NOT NULL,
                period_id TEXT NOT NULL,
                realised_available_vre_mwh REAL NOT NULL,
                perfect_reference_dispatch_mwh REAL NOT NULL,
                copperplate_reference_dispatch_mwh REAL NOT NULL,
                zonal_final_dispatch_mwh REAL NOT NULL,
                economic_curtailment_mwh REAL NOT NULL,
                forecast_added_curtailment_mwh REAL NOT NULL,
                forecast_avoided_curtailment_mwh REAL NOT NULL,
                redispatch_added_curtailment_mwh REAL NOT NULL,
                redispatch_avoided_curtailment_mwh REAL NOT NULL,
                redispatch_net_impact_mwh REAL NOT NULL,
                total_curtailment_mwh REAL NOT NULL,
                identity_residual_mwh REAL NOT NULL,
                validation_tolerance_mwh REAL NOT NULL,
                accounting_status TEXT NOT NULL
            )
            """
        )
        rows = (
            (
                2025,
                6,
                "2022-01-01:07",
                2000.0,
                100.0,
                306.2187624267754,
                2000.0,
                1900.0,
                0.0,
                206.2187624267754,
                0.0,
                1693.7812375732246,
                -1693.7812375732246,
                0.0,
                0.0,
                2e-6,
                "reconciled",
            ),
            # A nearby row must never be accepted in place of the exact failed row.
            (
                2025,
                7,
                "2022-01-01:08",
                2000.0,
                100.0,
                306.2187624267754,
                2000.0,
                1900.0,
                0.0,
                206.2187624267754,
                0.0,
                1693.7812375732246,
                -1693.7812375732246,
                0.0,
                0.0,
                2e-6,
                "reconciled",
            ),
        )
        connection.executemany(
            "INSERT INTO vre_curtailment_period VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()


def test_failed_period_evidence_is_read_and_validated_by_exact_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "market.sqlite"
    _failed_period_database(database)

    evidence = read_exact_failed_period_evidence(database)

    assert (evidence["year"], evidence["period"], evidence["period_id"]) == (
        2025,
        6,
        "2022-01-01:07",
    )
    assert evidence["redispatch_avoided_curtailment_mwh"] == pytest.approx(
        EXPECTED_FAILED_PERIOD["redispatch_avoided_curtailment_mwh"], abs=1e-9
    )
    assert evidence["total_curtailment_mwh"] == 0.0
    assert evidence["accounting_status"] == "reconciled"
    assert evidence["case_split"] == {
        "perfect_reference_dispatch_mwh": 100.0,
        "copperplate_reference_dispatch_mwh": 306.2187624267754,
        "zonal_final_dispatch_mwh": 2000.0,
        "economic_curtailment_mwh": 1900.0,
        "forecast_added_curtailment_mwh": 0.0,
        "forecast_avoided_curtailment_mwh": 206.2187624267754,
        "redispatch_added_curtailment_mwh": 0.0,
        "redispatch_avoided_curtailment_mwh": 1693.7812375732246,
    }


def test_failed_period_evidence_accepts_reconciled_bounded_solver_curtailment(
    tmp_path: Path,
) -> None:
    database = tmp_path / "market.sqlite"
    _failed_period_database(database)
    bounded_curtailment = 1.8e-6
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            """
            UPDATE vre_curtailment_period
            SET zonal_final_dispatch_mwh = realised_available_vre_mwh - ?,
                redispatch_added_curtailment_mwh = ?,
                redispatch_net_impact_mwh = ? - redispatch_avoided_curtailment_mwh,
                total_curtailment_mwh = ?,
                validation_tolerance_mwh = ?
            WHERE year = 2025 AND period = 6 AND period_id = '2022-01-01:07'
            """,
            (
                bounded_curtailment,
                bounded_curtailment,
                bounded_curtailment,
                bounded_curtailment,
                6e-7,
            ),
        )
        connection.commit()

    evidence = read_exact_failed_period_evidence(database)

    assert evidence["accounting_status"] == "reconciled"
    assert evidence["identity_residual_mwh"] == 0.0
    assert evidence["total_curtailment_mwh"] == pytest.approx(
        bounded_curtailment, abs=1e-12
    )


def test_annual_failure_stops_before_any_two_year_invocation() -> None:
    calls: list[str] = []

    def execute(stage_id: str) -> dict[str, object]:
        calls.append(stage_id)
        return {
            "stage_id": stage_id,
            "status": "failed" if stage_id == "annual" else "passed",
        }

    result = run_stage_sequence("two-year", execute)

    assert calls == ["smoke", "exact-periods", "24h", "168h", "annual"]
    assert result["status"] == "failed"
    assert result["stopped_after"] == "annual"
    assert result["not_started"] == ["two-year"]


def test_two_year_is_invoked_only_after_annual_go() -> None:
    calls: list[str] = []

    def execute(stage_id: str) -> dict[str, object]:
        calls.append(stage_id)
        return {"stage_id": stage_id, "status": "passed"}

    result = run_stage_sequence("two-year", execute)

    assert calls == [
        "smoke",
        "exact-periods",
        "24h",
        "168h",
        "annual",
        "two-year",
    ]
    assert calls.index("annual") < calls.index("two-year")
    assert result["status"] == "passed"
    assert result["stopped_after"] is None
    assert result["not_started"] == []


def test_exact_period_failure_stops_before_24h_and_every_later_stage() -> None:
    calls: list[str] = []

    def execute(stage_id: str) -> dict[str, object]:
        calls.append(stage_id)
        return {
            "stage_id": stage_id,
            "status": "failed" if stage_id == "exact-periods" else "passed",
        }

    result = run_stage_sequence("two-year", execute)

    assert calls == ["smoke", "exact-periods"]
    assert result["status"] == "failed"
    assert result["stopped_after"] == "exact-periods"
    assert result["not_started"] == ["24h", "168h", "annual", "two-year"]


@pytest.mark.parametrize(
    "solver_status",
    (
        "GO_WITH_NUMERICAL_WARNING",
        "COMPLETED_WITH_NUMERICAL_WARNING",
    ),
)
def test_nested_solver_warning_forces_top_level_fail_stop(
    solver_status: str,
) -> None:
    calls: list[str] = []

    def execute(stage_id: str) -> dict[str, object]:
        calls.append(stage_id)
        return {
            "stage_id": stage_id,
            "status": "passed",
            "runs": [
                {
                    "study_kind": "zonal",
                    "solver_validation_gate_status": solver_status,
                }
            ],
        }

    result = run_stage_sequence("two-year", execute)

    assert calls == ["smoke"]
    assert result["status"] == "failed"
    assert result["stopped_after"] == "smoke"
    assert result["stages"][0]["error_code"] == (
        "GF_PROMPT107_NUMERICAL_VALIDATION_NO_GO"
    )
    assert result["stages"][0]["solver_gate_failures"] == [solver_status]
    assert result["not_started"] == [
        "exact-periods", "24h", "168h", "annual", "two-year"
    ]


@pytest.mark.parametrize(
    "through", ("smoke", "exact-periods", "24h", "168h", "annual", "two-year")
)
def test_cli_accepts_every_stage_as_a_through_target(
    through: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def execute_gate(**kwargs: object) -> dict[str, object]:
        calls.append(str(kwargs["through"]))
        return {
            "decision": "GO",
            "through": kwargs["through"],
            "stop_decision": {},
        }

    monkeypatch.setattr(production_gate, "execute_production_gate", execute_gate)
    monkeypatch.setattr(
        production_gate,
        "build_application_stage_executor",
        lambda _output: object(),
    )

    exit_code = production_gate.main(
        ["--through", through, "--output-root", str(tmp_path / through)]
    )

    assert exit_code == 0
    assert calls == [through]


def test_stage_order_places_exact_replays_between_smoke_and_matched_24h() -> None:
    assert STAGE_ORDER == (
        "smoke",
        "exact-periods",
        "24h",
        "168h",
        "annual",
        "two-year",
    )


def test_nonempty_destination_is_blocked_without_launch_or_mutation(
    tmp_path: Path,
) -> None:
    data_root = _pack_store(tmp_path / "force-data")
    output = tmp_path / "production"
    output.mkdir()
    sentinel = output / "existing-evidence.txt"
    sentinel.write_bytes(b"preserve exactly\n")
    calls: list[str] = []

    report = execute_production_gate(
        through="smoke",
        output_root=output,
        data_root=data_root,
        execute_stage=lambda stage_id, _packs: calls.append(stage_id) or {},
    )

    assert calls == []
    assert report["decision"] == "BLOCKED"
    assert report["stop_decision"]["error_code"] == (
        "GF_PROMPT107_OUTPUT_ROOT_NOT_EMPTY"
    )
    assert report["output_root_preflight"]["contents"] == [
        {
            "path": "existing-evidence.txt",
            "type": "file",
            "bytes": len(b"preserve exactly\n"),
            "sha256": hashlib.sha256(b"preserve exactly\n").hexdigest(),
        }
    ]
    assert sentinel.read_bytes() == b"preserve exactly\n"
    assert list(output.iterdir()) == [sentinel]


def _create_directory_reparse_point(link: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except OSError:
        pass
    if os.name != "nt":
        pytest.skip("directory symlink creation is unavailable")
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip(f"junction creation is unavailable: {completed.stderr}")


@pytest.mark.parametrize("redirect_parent", (False, True))
def test_output_root_rejects_reparse_point_without_touching_target(
    tmp_path: Path,
    redirect_parent: bool,
) -> None:
    target = tmp_path / "alternate-target"
    link = tmp_path / "declared-output"
    _create_directory_reparse_point(link, target)
    output = link / "child" if redirect_parent else link
    calls: list[str] = []
    try:
        report = execute_production_gate(
            through="smoke",
            output_root=output,
            data_root=tmp_path / "unused-data-root",
            execute_stage=lambda stage_id, _packs: calls.append(stage_id) or {},
        )
    finally:
        if link.exists() or link.is_symlink():
            os.rmdir(link)

    assert calls == []
    assert report["decision"] == "BLOCKED"
    assert report["stop_decision"]["error_code"] == (
        "GF_PROMPT107_OUTPUT_ROOT_REDIRECTED"
    )
    assert report["output_root_preflight"]["redirect_component"] == str(link)
    assert list(target.iterdir()) == []


def _initialise_runtime_git_tree(root: Path) -> None:
    (root / "gridform_core").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "gridform_core" / "zonal_redispatch.py").write_text(
        "SOLVER = 'highs-ds'\n", encoding="utf-8"
    )
    (root / "scripts" / "run_prompt107_production_gate.py").write_text(
        "print('gate')\n", encoding="utf-8"
    )
    (root / ".gitignore").write_text("outputs/\n", encoding="utf-8")
    for command in (
        ["git", "init"],
        ["git", "config", "user.email", "prompt107@example.invalid"],
        ["git", "config", "user.name", "Prompt 107 Test"],
        ["git", "add", "."],
        ["git", "commit", "-m", "runtime tree"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)


@pytest.mark.parametrize(
    ("relative_path", "content"),
    (
        ("gridform_core/zonal_redispatch.py", "SOLVER = 'highs-ipm'\n"),
        ("gridform_core/untracked_runtime_module.py", "RUNTIME = True\n"),
    ),
)
def test_runtime_lineage_rejects_any_visible_runtime_worktree_change(
    tmp_path: Path,
    relative_path: str,
    content: str,
) -> None:
    repository = tmp_path / "runtime-tree"
    repository.mkdir()
    _initialise_runtime_git_tree(repository)
    changed = repository / relative_path
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text(content, encoding="utf-8")

    with pytest.raises(ProductionGateError) as caught:
        production_gate._runtime_source_lineage(repository)

    assert caught.value.code == "GF_PROMPT107_WORKTREE_DIRTY"
    assert any(relative_path in row for row in caught.value.evidence["worktree_status"])
    assert caught.value.evidence["head"]
    assert caught.value.evidence["tree_id"]
    assert len(caught.value.evidence["worktree_state_sha256"]) == 64


def test_runtime_lineage_allows_ignored_output_from_clean_tree(tmp_path: Path) -> None:
    repository = tmp_path / "runtime-tree"
    repository.mkdir()
    _initialise_runtime_git_tree(repository)
    output = repository / "outputs" / "preserved" / "evidence.json"
    output.parent.mkdir(parents=True)
    output.write_text("{}\n", encoding="utf-8")

    lineage = production_gate._runtime_source_lineage(repository)

    assert lineage["worktree_clean"] is True
    assert lineage["worktree_status"] == []
    assert lineage["lineage_status"] == "clean_runtime_tree"
    assert lineage["tracked_file_count"] == 3


def test_preflight_records_revision_lineage_signed_packs_disk_and_candidate_stack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = _pack_store(tmp_path / "force-data")
    output = tmp_path / "production"
    clean_lineage = {
        "head": "1" * 40,
        "tree_id": "2" * 40,
        "worktree_clean": True,
        "worktree_status": [],
        "git_diff_sha256": hashlib.sha256(b"").hexdigest(),
        "git_status_sha256": hashlib.sha256(b"").hexdigest(),
        "worktree_state_sha256": "3" * 64,
        "lineage_status": "clean_runtime_tree",
    }
    monkeypatch.setattr(
        production_gate, "_runtime_source_lineage", lambda: clean_lineage
    )

    report = execute_production_gate(
        through="smoke",
        output_root=output,
        data_root=data_root,
        execute_stage=lambda stage_id, _packs: {
            "stage_id": stage_id,
            "status": "passed",
        },
    )

    preflight = report["production_preflight"]
    assert preflight["status"] == "PERMITTED_UNVALIDATED"
    assert preflight["project_revision"] == {
        **clean_lineage,
        "source_root": str(Path.cwd()),
        "accepted_source_lineage_status": "not_supplied",
    }
    assert preflight["module_graph"]["zonal_module_version"] == "1.2.0"
    assert preflight["base_pack_verification"]["decision"] == "GO"
    assert preflight["network_pack_verification"]["status"] == "verified"
    assert preflight["disk"]["free_bytes"] > preflight["disk"]["minimum_free_bytes"]
    assert preflight["solver_stack"]["scipy_version"] == "1.8.1"
    assert preflight["solver_stack"]["registry_status"] == "candidate"
    assert preflight["solver_stack_validation_status"] == (
        "solver_stack_not_yet_validated"
    )
    assert preflight["execution_permission"] == "PERMITTED_UNVALIDATED"
    assert set(preflight["study_lineage"]) == {"copperplate", "zonal"}
    assert preflight["original_prompt104_hashes"] == {
        "prompt104-copperplate-preflight.json": (
            "93e74ad18772ad99bda9c141210094d1909fa0b13a672961f25f9c1ddfb66b25"
        ),
        "prompt104-staged-copperplate-study.json": (
            "37096955e425c9c350a8ae8a5e7c9958b29c45629f5d714ef70969d4fbe00f43"
        ),
        "prompt104-zonal-preflight.json": (
            "ba3c410909cbe5a3bfe2a4c497928589a7857329e4527c184608db2284839d62"
        ),
        "prompt104-zonal-study.json": (
            "9c3c5cea12a67a25fcb8309fde1c1b11be76fafdfb4ef8abfbbc6a0f4492bea3"
        ),
    }


def test_preflight_rejects_mismatched_external_accepted_source_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packs = resolve_required_packs(_pack_store(tmp_path / "force-data"))
    clean_lineage = {
        "head": "1" * 40,
        "tree_id": "2" * 40,
        "worktree_clean": True,
        "worktree_status": [],
        "git_diff_sha256": hashlib.sha256(b"").hexdigest(),
        "git_status_sha256": hashlib.sha256(b"").hexdigest(),
        "worktree_state_sha256": "3" * 64,
        "lineage_status": "clean_runtime_tree",
    }
    monkeypatch.setattr(
        production_gate, "_runtime_source_lineage", lambda: clean_lineage
    )
    accepted = {
        "schema_version": "value.prompt107-accepted-source-lineage/v1",
        "head": "1" * 40,
        "tree_id": "0" * 40,
    }

    with pytest.raises(ProductionGateError) as caught:
        production_gate.build_production_preflight(
            tmp_path / "production",
            packs,
            tmp_path / "force-data",
            accepted_source_lineage=accepted,
        )

    assert caught.value.code == "GF_PROMPT107_SOURCE_LINEAGE_MISMATCH"
    assert caught.value.evidence["mismatched_fields"] == ["tree_id"]


def test_exact_period_stage_replays_only_retained_inputs_and_writes_v7_evidence(
    tmp_path: Path,
) -> None:
    packs = resolve_required_packs(_pack_store(tmp_path / "force-data"))
    output_root = tmp_path / "production"
    executor = build_application_stage_executor(output_root)

    result = executor("exact-periods", packs)

    assert result["status"] == "passed"
    assert result["stage_id"] == "exact-periods"
    assert result["mode"] == "retained_declared_input_replay"
    assert result["solver_stack_validation_status"] == (
        "solver_stack_not_yet_validated"
    )
    assert [row["fixture"] for row in result["replays"]] == [
        "period-2025-14.json.gz",
        "period-bound-noise.json",
    ]
    assert [row["declared_input_sha256"] for row in result["replays"]] == [
        "88d613706bd1400bd16cc0210526a864c0ea93acd6d4262ffa058811dd77068a",
        "92d90fdf2a9b17e6599e09f0f8456108efe14a8293a4f58208d86f4b40602184",
    ]
    assert all(
        row["solver_stack_validation_status"] == "solver_stack_not_yet_validated"
        for row in result["replays"]
    )
    assert result["solver_validation_summary"]["annual_status"] == "GO"
    assert result["solver_validation_summary"]["row_count"] == 6
    assert result["solver_validation_summary"]["unvalidated_periods"] == 0
    assert Path(result["solver_validation_summary_path"]).is_file()
    database = Path(result["v7_database"])
    public_validation = validate_market_ledger_file(database)
    assert public_validation["valid"] is True, public_validation["errors"]
    assert not database.with_name(f"{database.name}-wal").exists()
    assert not database.with_name(f"{database.name}-shm").exists()
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute(
            "SELECT COUNT(*) FROM zonal_period_accounting "
            "WHERE accounting_status='reconciled'"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM solver_declaration_link"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM network_solver_diagnostics"
        ).fetchone()[0] == 6
        assert connection.execute(
            "SELECT COUNT(DISTINCT declared_input_sha256) "
            "FROM network_solver_diagnostics"
        ).fetchone()[0] == 2


def _exact_output_for_solver_mutation(tmp_path: Path) -> tuple[Path, Path]:
    packs = resolve_required_packs(_pack_store(tmp_path / "force-data"))
    output_root = tmp_path / "production"
    result = build_application_stage_executor(output_root)("exact-periods", packs)
    assert result["status"] == "passed"
    return output_root, Path(result["v7_database"])


def _validate_mutated_exact_database_as_application(
    output_root: Path,
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    run_root = output_root / "runs" / "exact-periods"
    metadata = run_root / "market" / "metadata.json"
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload.setdefault("rows", {})["period_summary"] = 2
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    attribution = run_root / "network" / "vre-curtailment-attribution.json"
    attribution.parent.mkdir(parents=True, exist_ok=True)
    attribution.write_text(
        json.dumps(
            {
                "capability_status": "reconciled",
                "matched_counterfactual_proof": {"period_count": 2},
                "annual_totals": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "gridform_core.bundle_validator.validate_run_bundle",
        lambda _root: {"valid": True, "errors": []},
    )
    assert database == run_root / "market" / "market.sqlite"
    return production_gate._validate_application_output(
        stage_id="smoke",
        kind="zonal",
        run_id="mutation-run",
        output_dir=run_root,
        expected_periods=2,
        expected_years=1,
        project={"id": "mutation", "revision_sha256": "a" * 64},
        result={"engine": "mutation"},
    )


def test_application_gate_rejects_completed_class_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, database = _exact_output_for_solver_mutation(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE network_solver_diagnostics "
            "SET validation_class='COMPLETED_WITH_NUMERICAL_WARNING' "
            "WHERE rowid=(SELECT MIN(rowid) FROM network_solver_diagnostics)"
        )
        connection.commit()

    with pytest.raises(ProductionGateError) as caught:
        _validate_mutated_exact_database_as_application(
            output_root, database, monkeypatch
        )

    assert caught.value.code == "GF_PROMPT107_NUMERICAL_VALIDATION_NO_GO", (
        caught.value.evidence
    )


def test_application_gate_rejects_quantitative_validated_ceiling_exceedance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, database = _exact_output_for_solver_mutation(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE network_solver_diagnostics "
            "SET achieved_final_value=optimum + validated_ceiling * 1.01, "
            "degradation=validated_ceiling * 1.01, validation_class='GO' "
            "WHERE rowid=(SELECT MIN(rowid) FROM network_solver_diagnostics)"
        )
        connection.commit()

    with pytest.raises(ProductionGateError) as caught:
        _validate_mutated_exact_database_as_application(
            output_root, database, monkeypatch
        )

    assert caught.value.code == "GF_PROMPT107_NUMERICAL_VALIDATION_NO_GO", (
        caught.value.evidence
    )


def test_prompt107_recomputes_degradation_identity_from_final_values(
    tmp_path: Path,
) -> None:
    _output_root, database = _exact_output_for_solver_mutation(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE network_solver_diagnostics "
            "SET achieved_final_value=optimum + computed_tolerance * 2, "
            "degradation=0.0 "
            "WHERE rowid=(SELECT MIN(rowid) FROM network_solver_diagnostics)"
        )
        connection.commit()

    with pytest.raises(ProductionGateError) as caught:
        production_gate._validate_solver_gate_evidence(
            database, expected_periods=2
        )

    assert caught.value.code == "GF_PROMPT107_NUMERICAL_VALIDATION_NO_GO"
    assert caught.value.evidence["numerical_errors"][0]["error"] == (
        "degradation does not equal max(0, achieved_final_value - optimum)"
    )


def test_application_gate_rejects_summary_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, database = _exact_output_for_solver_mutation(tmp_path)
    from gridform_core.zonal_results import query_solver_validation_summary

    mismatched = dict(query_solver_validation_summary(database) or {})
    mismatched["phases"] = {
        **dict(mismatched["phases"]),
        "primary_bid_cost": {
            **dict(mismatched["phases"]["primary_bid_cost"]),
            "max_degradation": 999.0,
        },
    }
    monkeypatch.setattr(
        "gridform_core.zonal_results.query_solver_validation_summary",
        lambda _database, **_kwargs: mismatched,
    )

    with pytest.raises(ProductionGateError) as caught:
        _validate_mutated_exact_database_as_application(
            output_root, database, monkeypatch
        )

    assert caught.value.code == "GF_PROMPT107_SOLVER_SUMMARY_MISMATCH"


def test_exact_period_gate_rejects_completed_class_mismatch(
    tmp_path: Path,
) -> None:
    _output_root, database = _exact_output_for_solver_mutation(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(
            "UPDATE network_solver_diagnostics "
            "SET validation_class='COMPLETED_WITH_NUMERICAL_WARNING' "
            "WHERE rowid=(SELECT MIN(rowid) FROM network_solver_diagnostics)"
        )
        connection.commit()

    with pytest.raises(ProductionGateError) as caught:
        production_gate._validate_solver_gate_evidence(
            database, expected_periods=2
        )

    assert caught.value.code == "GF_PROMPT107_NUMERICAL_VALIDATION_NO_GO"


def test_exact_period_gate_rejects_mismatched_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _output_root, database = _exact_output_for_solver_mutation(tmp_path)
    from gridform_core.zonal_results import build_solver_validation_summary

    mismatched = dict(build_solver_validation_summary([], evidence_errors=()))
    mismatched.update(
        {
            "row_count": 3,
            "annual_status": "GO",
            "warning_periods": 0,
            "unvalidated_periods": 0,
            "maximum_validated_ceiling_use": 0.0,
            "evidence_status": "valid",
            "solver_stack_validation_status": "solver_stack_not_yet_validated",
        }
    )
    monkeypatch.setattr(
        "gridform_core.zonal_results.build_solver_validation_summary",
        lambda _rows, **_kwargs: mismatched,
    )

    with pytest.raises(ProductionGateError) as caught:
        production_gate._validate_solver_gate_evidence(
            database, expected_periods=2
        )

    assert caught.value.code == "GF_PROMPT107_SOLVER_SUMMARY_MISMATCH"


SOLVER_CONTRACT_MUTATIONS = (
    (
        "highs_ipm",
        "UPDATE network_solver_diagnostics SET method='highs-ipm', "
        "ipm_optimality_tolerance=1e-9",
    ),
    (
        "feasibility_tolerances",
        "UPDATE network_solver_diagnostics "
        "SET primal_feasibility_tolerance=5e-9, "
        "dual_feasibility_tolerance=6e-9",
    ),
    (
        "near_equal_declared_tolerance",
        "UPDATE network_solver_diagnostics "
        "SET primal_feasibility_tolerance=1.0000000000005e-9",
    ),
    (
        "unitful_ceilings",
        "UPDATE network_solver_diagnostics SET warning_ceiling=warning_ceiling*2, "
        "validated_ceiling=validated_ceiling*2, "
        "absolute_ceiling=absolute_ceiling*2",
    ),
    (
        "solver_stack",
        "UPDATE network_solver_diagnostics SET scipy_version='9.9.9', "
        "highs_binary_sha256='0000000000000000000000000000000000000000000000000000000000000000', "
        "highs_identity='scipy-embedded-highs:0000000000000000000000000000000000000000000000000000000000000000'",
    ),
    (
        "contract_and_module_version",
        "UPDATE network_solver_diagnostics "
        "SET solver_contract_version='value.zonal-lexicographic/v999', "
        "module_version='999.0.0'",
    ),
    (
        "objective_unit",
        "UPDATE network_solver_diagnostics SET objective_unit='MWh' "
        "WHERE phase_id='primary_bid_cost'",
    ),
    (
        "fallback_status",
        "UPDATE solver_declaration_link SET solver_status='fallback'",
    ),
)


@pytest.mark.parametrize("gate_kind", ("application", "exact-periods"))
@pytest.mark.parametrize(("_mutation_id", "mutation_sql"), SOLVER_CONTRACT_MUTATIONS)
def test_solver_gate_rejects_rows_outside_approved_manifest_and_registry_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gate_kind: str,
    _mutation_id: str,
    mutation_sql: str,
) -> None:
    output_root, database = _exact_output_for_solver_mutation(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(mutation_sql)
        connection.commit()

    with pytest.raises(ProductionGateError) as caught:
        if gate_kind == "application":
            _validate_mutated_exact_database_as_application(
                output_root, database, monkeypatch
            )
        else:
            production_gate._validate_solver_gate_evidence(
                database, expected_periods=2
            )

    assert caught.value.code == "GF_PROMPT107_SOLVER_CONTRACT_MISMATCH"
    assert caught.value.evidence["contract_mismatches"]


def _valid_summary_from_database(database: Path) -> dict[str, object]:
    from gridform_core.zonal_results import build_solver_validation_summary

    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM network_solver_diagnostics "
                "ORDER BY run_id, year, period, phase_id"
            )
        ]
    return dict(build_solver_validation_summary(rows, evidence_errors=()))


@pytest.mark.parametrize("gate_kind", ("application", "exact-periods"))
def test_solver_gate_rejects_mutated_summary_stack_and_contract_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gate_kind: str,
) -> None:
    output_root, database = _exact_output_for_solver_mutation(tmp_path)
    mismatched = _valid_summary_from_database(database)
    mismatched.update(
        {
            "method": "highs-ipm",
            "solver_contract_version": "value.zonal-lexicographic/v999",
            "scipy_version": "9.9.9",
            "highs_identity": "scipy-embedded-highs:" + "0" * 64,
        }
    )
    target = (
        "gridform_core.zonal_results.query_solver_validation_summary"
        if gate_kind == "application"
        else "gridform_core.zonal_results.build_solver_validation_summary"
    )
    monkeypatch.setattr(target, lambda *_args, **_kwargs: mismatched)

    with pytest.raises(ProductionGateError) as caught:
        if gate_kind == "application":
            _validate_mutated_exact_database_as_application(
                output_root, database, monkeypatch
            )
        else:
            production_gate._validate_solver_gate_evidence(
                database, expected_periods=2
            )

    assert caught.value.code == "GF_PROMPT107_SOLVER_SUMMARY_MISMATCH"
    assert set(caught.value.evidence["mismatches"]).issuperset(
        {"method", "solver_contract_version", "scipy_version", "highs_identity"}
    )


@pytest.mark.parametrize("gate_kind", ("application", "exact-periods"))
def test_consistent_numerical_warning_is_visible_and_forces_no_go(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gate_kind: str,
) -> None:
    output_root, database = _exact_output_for_solver_mutation(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "UPDATE network_solver_diagnostics "
            "SET nonzero_term_count=1, absolute_term_scale=2000000.0, "
            "computed_tolerance=0.002, "
            "validation_class='GO_WITH_NUMERICAL_WARNING' "
            "WHERE rowid=(SELECT MIN(rowid) FROM network_solver_diagnostics)"
        )
        connection.commit()
    if gate_kind == "application":
        summary = _valid_summary_from_database(database)
        monkeypatch.setattr(
            "gridform_core.zonal_results.query_solver_validation_summary",
            lambda *_args, **_kwargs: summary,
        )

    with pytest.raises(ProductionGateError) as caught:
        if gate_kind == "application":
            _validate_mutated_exact_database_as_application(
                output_root, database, monkeypatch
            )
        else:
            production_gate._validate_solver_gate_evidence(
                database, expected_periods=2
            )

    assert caught.value.code == "GF_PROMPT107_NUMERICAL_VALIDATION_NO_GO", (
        caught.value.evidence
    )
    assert caught.value.evidence["solver_validation_summary"]["annual_status"] == (
        "GO_WITH_NUMERICAL_WARNING"
    )
    assert caught.value.evidence["warning_periods"] == 1


@pytest.mark.parametrize("gate_kind", ("application", "exact-periods"))
def test_consistent_completed_numerical_warning_is_visible_and_forces_no_go(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    gate_kind: str,
) -> None:
    output_root, database = _exact_output_for_solver_mutation(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "UPDATE network_solver_diagnostics "
            "SET nonzero_term_count=1, absolute_term_scale=20000000.0, "
            "computed_tolerance=0.02, "
            "validation_class='COMPLETED_WITH_NUMERICAL_WARNING' "
            "WHERE rowid=(SELECT MIN(rowid) FROM network_solver_diagnostics)"
        )
        connection.commit()
    if gate_kind == "application":
        summary = _valid_summary_from_database(database)
        monkeypatch.setattr(
            "gridform_core.zonal_results.query_solver_validation_summary",
            lambda *_args, **_kwargs: summary,
        )

    with pytest.raises(ProductionGateError) as caught:
        if gate_kind == "application":
            _validate_mutated_exact_database_as_application(
                output_root, database, monkeypatch
            )
        else:
            production_gate._validate_solver_gate_evidence(
                database, expected_periods=2
            )

    assert caught.value.code == "GF_PROMPT107_NUMERICAL_VALIDATION_NO_GO", (
        caught.value.evidence
    )
    summary = caught.value.evidence["solver_validation_summary"]
    assert summary["annual_status"] == "COMPLETED_WITH_NUMERICAL_WARNING"
    assert summary["warning_periods"] == 1
    assert summary["unvalidated_periods"] == 1
    assert caught.value.evidence["warning_periods"] == 1
    assert caught.value.evidence["unvalidated_periods"] == 1


def test_application_stage_executor_copies_approved_studies_and_uses_explicit_outputs(
    tmp_path: Path,
) -> None:
    packs = resolve_required_packs(_pack_store(tmp_path / "force-data"))
    calls: list[dict[str, object]] = []

    def run_application(project: dict[str, object], **kwargs: object) -> dict[str, object]:
        calls.append({"project": project, **kwargs})
        return {"engine": "test-engine"}

    def validate_output(**kwargs: object) -> dict[str, object]:
        return {
            "status": "passed",
            "run_id": kwargs["run_id"],
            "output_dir": str(kwargs["output_dir"]),
        }

    output_root = tmp_path / "production"
    executor = build_application_stage_executor(
        output_root,
        application_runner=run_application,
        output_validator=validate_output,
    )

    result = executor("168h", packs)

    assert result["status"] == "passed"
    assert [call["project"]["id"] for call in calls] == [
        "prompt104-staged-copperplate-2025",
        "prompt104-zonal-2025",
    ]
    assert [call["mode"] for call in calls] == [
        "validation_168h",
        "validation_168h",
    ]
    assert [Path(call["output_dir"]).relative_to(output_root).as_posix() for call in calls] == [
        "runs/168h/copperplate",
        "runs/168h/zonal",
    ]
    assert calls[0]["network_pack_root"] is None
    assert calls[1]["network_pack_root"] == packs.network_root
    assert (output_root / "studies" / "source" / "prompt104-staged-copperplate-study.json").read_bytes() == (
        Path("publication/prompt104-staged-copperplate-study.json").read_bytes()
    )
    assert (output_root / "studies" / "source" / "prompt104-zonal-study.json").read_bytes() == (
        Path("publication/prompt104-zonal-study.json").read_bytes()
    )


def test_failed_application_stage_retains_unvalidated_solver_stack_status(
    tmp_path: Path,
) -> None:
    packs = resolve_required_packs(_pack_store(tmp_path / "force-data"))

    def fail_application(
        _project: dict[str, object], **_kwargs: object
    ) -> dict[str, object]:
        raise RuntimeError("controlled failure")

    executor = build_application_stage_executor(
        tmp_path / "production", application_runner=fail_application
    )

    result = executor("smoke", packs)

    assert result["status"] == "failed"
    assert result["solver_stack_validation_status"] == (
        "solver_stack_not_yet_validated"
    )


def _changed_leaf_paths(
    original: object, derived: object, prefix: str = ""
) -> set[str]:
    if isinstance(original, dict) and isinstance(derived, dict):
        changes: set[str] = set()
        for key in set(original) | set(derived):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in original or key not in derived:
                changes.add(path)
            else:
                changes.update(_changed_leaf_paths(original[key], derived[key], path))
        return changes
    return set() if original == derived else {prefix}


def test_derived_execution_studies_preserve_source_and_recalculate_only_allowed_identity(
    tmp_path: Path,
) -> None:
    from gridform_core.project_revision import project_fingerprint
    from gridform_core.v2.module_manifest import workspace_registry
    from gridform_core.zonal_pack_selection import resolve_zonal_pack_selection

    packs = resolve_required_packs(_pack_store(tmp_path / "force-data"))
    source_paths = {
        "copperplate": Path("publication/prompt104-staged-copperplate-study.json"),
        "zonal": Path("publication/prompt104-zonal-study.json"),
    }
    before = {kind: path.read_bytes() for kind, path in source_paths.items()}

    evidence = derive_execution_studies(tmp_path / "production", packs)

    assert {kind: path.read_bytes() for kind, path in source_paths.items()} == before
    registry = workspace_registry()
    derived = {
        kind: json.loads(Path(row["execution_copy"]).read_text(encoding="utf-8"))
        for kind, row in evidence.items()
    }
    original = {
        kind: json.loads(value.decode("utf-8")) for kind, value in before.items()
    }
    assert _changed_leaf_paths(original["copperplate"], derived["copperplate"]) == {
        "revision_sha256"
    }
    assert _changed_leaf_paths(original["zonal"], derived["zonal"]) == {
        "revision_sha256",
        "solver_contract",
        "maturity_acknowledgements.module:value-zonal-redispatch-balancing@1.0.0",
        "maturity_acknowledgements.module:value-zonal-redispatch-balancing@2.0.0",
    }
    assert (
        "module:value-zonal-redispatch-balancing@1.0.0"
        not in derived["zonal"]["maturity_acknowledgements"]
    )
    assert derived["zonal"]["maturity_acknowledgements"][
        "module:value-zonal-redispatch-balancing@2.0.0"
    ] == "value.experimental-ack/v1"
    from gridform_core.zonal_solver_contract import DEFAULT_ZONAL_SOLVER_SETTINGS

    assert derived["zonal"]["solver_contract"] == (
        DEFAULT_ZONAL_SOLVER_SETTINGS.to_dict()
    )
    selection = resolve_zonal_pack_selection(
        derived["zonal"],
        base_pack_root=packs.base_root,
        base_manifest=packs.base_manifest,
        explicit_network_pack_root=packs.network_root,
    )
    assert derived["copperplate"]["revision_sha256"] == project_fingerprint(
        derived["copperplate"], registry, packs.base_manifest
    )
    assert derived["zonal"]["revision_sha256"] == project_fingerprint(
        derived["zonal"], registry, selection.revision_manifest
    )
    for kind in ("copperplate", "zonal"):
        row = evidence[kind]
        assert row["source_sha256"] == hashlib.sha256(before[kind]).hexdigest()
        assert Path(row["source_copy"]).read_bytes() == before[kind]
        assert row["source_revision_sha256"] == original[kind]["revision_sha256"]
        assert row["execution_revision_sha256"] == derived[kind]["revision_sha256"]
    assert evidence["zonal"]["derivation"] == {
        "schema_version": "value.study-execution-derivation/v1",
        "source_sha256": hashlib.sha256(before["zonal"]).hexdigest(),
        "reason": "zonal-module-1.2-solver-contract-migration",
        "derived_revision_sha256": derived["zonal"]["revision_sha256"],
    }


def _two_year_causal_results(*, include_live_clearing: bool = True) -> list[dict[str, object]]:
    project = {
        "project_id": "project-alpha",
        "expected_completion_year": 2026,
        "extensions": {
            "total_capex_gbp": 12_000_000.0,
            "annual_fixed_opex_gbp": 240_000.0,
            "economic_lifetime_years": 30.0,
        },
    }
    record = {
        "schema_version": "value.commissioned-asset/v1",
        "asset_id": "commissioned:project-alpha",
        "source_project_id": "project-alpha",
        "commissioning_year": 2026,
        "total_capex_gbp": 12_000_000.0,
        "annual_fixed_opex_gbp": 240_000.0,
        "economic_lifetime_years": 30.0,
    }
    asset = {
        "asset_id": "commissioned:project-alpha",
        "status": "commissioned",
        "extensions": {
            **project["extensions"],
            "source_project_id": "project-alpha",
            "commissioning_year": 2026,
            "commissioned_asset_record": record,
        },
    }
    return [
        {
            "year": 2025,
            "planning_advance": {
                "operating_state": {"assets": []},
                "commissioned_projects": [],
                "events": [],
            },
            "market": {"generation_mwh_by_asset": {}, "extensions": {}},
            "investment": {
                "proposals": [
                    {
                        "proposal_id": "proposal-alpha",
                        "expected_completion_year": 2026,
                    }
                ]
            },
            "planning_admission": {
                "admitted_projects": [project],
                "events": [
                    {
                        "project_id": "project-alpha",
                        "event_type": "admitted_model_investment",
                    }
                ],
            },
            "next_state": {"assets": [], "planning_projects": [project]},
        },
        {
            "year": 2026,
            "planning_advance": {
                "operating_state": {"assets": [asset]},
                "commissioned_projects": [project],
                "events": [
                    {
                        "project_id": "project-alpha",
                        "event_type": "commissioned",
                        "extensions": {
                            "commissioned_asset_id": "commissioned:project-alpha"
                        },
                    }
                ],
            },
            "market": {
                "generation_mwh_by_asset": (
                    {"commissioned:project-alpha": 0.0}
                    if include_live_clearing
                    else {}
                ),
                "extensions": {},
            },
            "investment": {"proposals": []},
            "planning_admission": {"admitted_projects": [], "events": []},
            "next_state": {"assets": [asset], "planning_projects": []},
        },
    ]


def test_two_year_studies_are_deterministically_derived_from_approved_2025_revisions(
    tmp_path: Path,
) -> None:
    from gridform_core.project_revision import project_fingerprint
    from gridform_core.v2.module_manifest import workspace_registry
    from gridform_core.zonal_pack_selection import resolve_zonal_pack_selection

    packs = resolve_required_packs(_pack_store(tmp_path / "force-data"))
    root = tmp_path / "production"
    annual = derive_execution_studies(root, packs)

    first = production_gate.derive_two_year_execution_studies(root, packs, annual)
    second = production_gate.derive_two_year_execution_studies(root, packs, annual)

    assert first == second
    registry = workspace_registry()
    for kind, row in first.items():
        project = json.loads(Path(row["execution_copy"]).read_text(encoding="utf-8"))
        parent = json.loads(Path(annual[kind]["execution_copy"]).read_text(encoding="utf-8"))
        assert project["start_year"] == 2025
        assert project["end_year"] == 2026
        assert project["parent_revision_sha256"] == parent["revision_sha256"]
        assert project["revision_number"] == parent["revision_number"] + 1
        manifest = packs.base_manifest
        if kind == "zonal":
            manifest = resolve_zonal_pack_selection(
                project,
                base_pack_root=packs.base_root,
                base_manifest=packs.base_manifest,
                explicit_network_pack_root=packs.network_root,
            ).revision_manifest
        assert project["revision_sha256"] == project_fingerprint(
            project, registry, manifest
        )
        assert row["source_revision_sha256"] == parent["revision_sha256"]
        assert row["changed_leaf_paths"] == [
            "end_year",
            "id",
            "name",
            "parent_revision_sha256",
            "revision_number",
            "revision_sha256",
        ]


def test_24h_executor_runs_matched_rerun_and_records_pair_fingerprint(
    tmp_path: Path,
) -> None:
    packs = resolve_required_packs(_pack_store(tmp_path / "force-data"))
    calls: list[dict[str, object]] = []

    def run_application(project: dict[str, object], **kwargs: object) -> dict[str, object]:
        calls.append({"project": project, **kwargs})
        output = Path(kwargs["output_dir"])
        (output / "year-results-v2.json").write_text(
            json.dumps([{"year": 2025, "project_id": project["id"]}]),
            encoding="utf-8",
        )
        return {"engine": "test-engine"}

    executor = build_application_stage_executor(
        tmp_path / "production",
        application_runner=run_application,
        output_validator=lambda **kwargs: {"run_id": kwargs["run_id"]},
    )

    result = executor("24h", packs)

    assert result["status"] == "passed"
    assert len(calls) == 4
    assert [Path(call["output_dir"]).parts[-2:] for call in calls] == [
        ("24h", "copperplate"),
        ("24h", "zonal"),
        ("matched-rerun", "copperplate"),
        ("matched-rerun", "zonal"),
    ]
    assert len(result["matched_reruns"]) == 2
    assert len(result["deterministic_rerun_fingerprint"]) == 64


def test_24h_executor_fails_closed_when_matched_rerun_science_changes(
    tmp_path: Path,
) -> None:
    packs = resolve_required_packs(_pack_store(tmp_path / "force-data"))

    def run_application(project: dict[str, object], **kwargs: object) -> dict[str, object]:
        output = Path(kwargs["output_dir"])
        changed = "matched-rerun" in output.parts and project["id"].endswith("2025")
        (output / "year-results-v2.json").write_text(
            json.dumps([{"year": 2025, "scientific_value": 2 if changed else 1}]),
            encoding="utf-8",
        )
        return {}

    result = build_application_stage_executor(
        tmp_path / "production",
        application_runner=run_application,
        output_validator=lambda **kwargs: {"run_id": kwargs["run_id"]},
    )("24h", packs)

    assert result["status"] == "failed"
    assert result["error_code"] == "GF_PROMPT107_NONDETERMINISTIC_RERUN"


@pytest.mark.parametrize("include_live_clearing", (True, False))
def test_two_year_executor_requires_attributable_commissioning_to_live_clearing_chain(
    tmp_path: Path,
    include_live_clearing: bool,
) -> None:
    packs = resolve_required_packs(_pack_store(tmp_path / "force-data"))

    def run_application(_project: dict[str, object], **kwargs: object) -> dict[str, object]:
        output = Path(kwargs["output_dir"])
        (output / "year-results-v2.json").write_text(
            json.dumps(
                _two_year_causal_results(
                    include_live_clearing=include_live_clearing
                )
            ),
            encoding="utf-8",
        )
        return {}

    result = build_application_stage_executor(
        tmp_path / "production",
        application_runner=run_application,
        output_validator=lambda **kwargs: {"run_id": kwargs["run_id"]},
    )("two-year", packs)

    if include_live_clearing:
        assert result["status"] == "passed"
        assert all(run["two_year_causality"]["status"] == "attributable" for run in result["runs"])
        assert all(run["two_year_causality"]["asset_id"] == "commissioned:project-alpha" for run in result["runs"])
    else:
        assert result["status"] == "failed"
        assert result["error_code"] == "GF_PROMPT107_TWO_YEAR_CAUSALITY_MISSING"


def test_direct_script_execution_pins_its_own_worktree_before_runtime_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(
        sys,
        "path",
        [entry for entry in sys.path if Path(entry or ".").resolve() != source_root],
    )

    resolved = ensure_source_root()

    assert resolved == source_root
    assert Path(sys.path[0]).resolve() == source_root
