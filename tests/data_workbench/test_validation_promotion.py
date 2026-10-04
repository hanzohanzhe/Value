from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from gridform_core.catalog import DATASET_SLOTS
from gridform_core.data_workbench.contracts import PromotionRequest
from gridform_core.data_workbench.promotion import PromotionError, promote_candidate
from gridform_core.data_workbench.review_reporting import render_candidate_review
from gridform_core.data_workbench.validation import (
    candidate_identity,
    validate_candidate_directory,
)


ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC = ROOT / "data-packs" / "value-synthetic-contract-pack-v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_candidate(
    root: Path,
    *,
    requested_waivers: list[str] | None = None,
) -> Path:
    candidate = root / "candidate"
    shutil.copytree(SYNTHETIC, candidate / "pack")
    artifact_hashes = {
        path.relative_to(candidate).as_posix(): sha(path)
        for path in sorted((candidate / "pack").rglob("*"))
        if path.is_file()
    }
    payload: dict[str, object] = {
        "schema_version": "value.data-workbench-candidate/v1",
        "candidate_id": "",
        "artifact_hashes": artifact_hashes,
        "source_rights": [
            {"source_id": "fixture", "redistribution_decision": "redistributable"}
        ],
        "spatial_topology": {
            "dangling_references": [],
            "connected": True,
            "map_ids_reconcile": True,
        },
        "scientific_reconciliation": {
            "maximum_demand_residual_mwh": 0.0,
            "profile_conservation_residual_mw": 0.0,
        },
        "requested_waivers": requested_waivers or [],
        "candidate_inventory": [
            {
                "item_id": "fixture-pack",
                "status": "candidate",
                "usable_for": ["validation"],
                "not_usable_for": ["formal benchmark before owner promotion"],
                "blocking_reasons": [],
                "required_actions": ["owner review and promotion"],
            }
        ],
    }
    payload["candidate_id"] = candidate_identity(payload)
    (candidate / "workbench-candidate.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return candidate


def rewrite(candidate: Path, mutate: object, *, refresh_identity: bool = True) -> None:
    path = candidate / "workbench-candidate.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)  # type: ignore[operator]
    if refresh_identity:
        payload["candidate_id"] = candidate_identity(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_six_gates_report_owner_review_and_registered_scientific_waiver(tmp_path: Path) -> None:
    candidate = make_candidate(
        tmp_path,
        requested_waivers=["etys.B6.symmetric_forward_fallback"],
    )

    report = validate_candidate_directory(candidate)

    assert set(report.gate_results) == {
        "source_rights",
        "schema_hash",
        "spatial_topology",
        "scientific_reconciliation",
        "determinism_regression",
        "owner_review",
    }
    assert report.status == "blocked"
    by_code = {issue.code: issue for issue in report.issues}
    assert by_code["DW-SCI-WAIVER-001"].waivable
    assert not by_code["DW-OWNER-001"].waivable


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda payload: payload["source_rights"][0].update(redistribution_decision="needs_rights_review"), "DW-RIGHTS-001"),
        (lambda payload: payload["artifact_hashes"].update({"pack/manifest.json": "0" * 64}), "DW-HASH-001"),
        (lambda payload: payload.update(schema_version="wrong"), "DW-SCHEMA-001"),
        (lambda payload: payload["spatial_topology"].update(dangling_references=["missing-zone"]), "DW-TOPOLOGY-001"),
        (lambda payload: payload["scientific_reconciliation"].update(maximum_demand_residual_mwh=1.0), "DW-CONSERVATION-001"),
    ],
)
def test_mechanical_mutations_are_nonwaivable(
    tmp_path: Path, mutation: object, expected_code: str
) -> None:
    candidate = make_candidate(tmp_path)
    rewrite(candidate, mutation)

    report = validate_candidate_directory(candidate, reviewer="owner")

    issue = next(item for item in report.issues if item.code == expected_code)
    assert not issue.waivable
    assert report.status == "blocked"


def test_candidate_without_a_promotable_data_pack_is_mechanically_blocked(
    tmp_path: Path,
) -> None:
    candidate = make_candidate(tmp_path)
    shutil.rmtree(candidate / "pack")
    rewrite(candidate, lambda payload: payload.update(artifact_hashes={}))

    report = validate_candidate_directory(candidate, reviewer="owner")

    issue = next(item for item in report.issues if item.code == "DW-PACK-001")
    assert not issue.waivable
    assert report.gate_results["schema_hash"] == "blocked"


def test_unknown_and_unrelated_waivers_are_rejected(tmp_path: Path) -> None:
    candidate = make_candidate(
        tmp_path,
        requested_waivers=["etys.B6.symmetric_forward_fallback"],
    )
    base = {
        "candidate_id": json.loads((candidate / "workbench-candidate.json").read_text("utf-8"))["candidate_id"],
        "version": "v1",
        "reviewer": "Hanzhe Xing",
    }
    with pytest.raises(PromotionError, match="unknown"):
        promote_candidate(
            candidate,
            PromotionRequest(**base, accepted_waivers=("made.up.waiver",)),
            state_root=tmp_path / "state-unknown",
            dataset_slots=DATASET_SLOTS,
        )
    with pytest.raises(PromotionError, match="unrelated|required"):
        promote_candidate(
            candidate,
            PromotionRequest(**base, accepted_waivers=()),
            state_root=tmp_path / "state-missing",
            dataset_slots=DATASET_SLOTS,
        )


def test_stale_candidate_fails_without_installing_pack(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    candidate_id = json.loads((candidate / "workbench-candidate.json").read_text("utf-8"))["candidate_id"]

    def mutate_after_first_validation() -> None:
        with (candidate / "pack" / "manifest.json").open("a", encoding="utf-8") as stream:
            stream.write(" ")

    with pytest.raises(PromotionError, match="stale|changed"):
        promote_candidate(
            candidate,
            PromotionRequest(
                candidate_id=candidate_id,
                version="v1",
                reviewer="Hanzhe Xing",
                accepted_waivers=(),
            ),
            state_root=tmp_path / "state",
            dataset_slots=DATASET_SLOTS,
            before_revalidate=mutate_after_first_validation,
        )
    assert not (tmp_path / "state" / "installed-packs").exists()


def test_valid_promotion_uses_existing_bundle_validator_and_is_byte_deterministic(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    candidate_id = json.loads((candidate / "workbench-candidate.json").read_text("utf-8"))["candidate_id"]
    request = PromotionRequest(
        candidate_id=candidate_id,
        version="v1",
        reviewer="Hanzhe Xing",
        accepted_waivers=(),
    )

    first = promote_candidate(
        candidate,
        request,
        state_root=tmp_path / "state-a",
        dataset_slots=DATASET_SLOTS,
        approved_at="2026-08-21T10:00:00+00:00",
    )
    second = promote_candidate(
        candidate,
        request,
        state_root=tmp_path / "state-b",
        dataset_slots=DATASET_SLOTS,
        approved_at="2026-08-21T11:00:00+00:00",
    )

    assert first.signature_type == "local_approval_attestation"
    assert first.bundle_sha256 == second.bundle_sha256
    assert (tmp_path / "state-a" / "installed-packs" / first.network_pack_id).is_dir()
    assert (tmp_path / "state-a" / "approvals" / f"{candidate_id}.json").is_file()


def test_review_package_answers_use_blockers_and_required_actions(tmp_path: Path) -> None:
    candidate = make_candidate(
        tmp_path,
        requested_waivers=["demand.island.static_share_fallback"],
    )
    report = validate_candidate_directory(candidate)

    outputs = render_candidate_review(candidate, report, tmp_path / "review")

    machine = json.loads((tmp_path / "review" / "candidate-review.json").read_text("utf-8"))
    assert machine["candidate_inventory"][0]["usable_for"] == ["validation"]
    assert machine["candidate_inventory"][0]["not_usable_for"]
    assert machine["blocking_reasons"]
    assert machine["required_actions"]
    assert set(machine["artifacts"]) == {
        "assumptions",
        "candidate_inventory",
        "reconciliation",
        "rights",
        "validation",
        "version_diff",
    }
    assert outputs["human_review"] == "candidate-review.md"
