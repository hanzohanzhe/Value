from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_data_workbench_release import audit_release
from scripts.build_official_gb_zonal_candidate import attempt_official_build


def test_official_build_stops_truthfully_when_the_normalized_inventory_is_missing(
    tmp_path: Path,
) -> None:
    result = attempt_official_build(
        state_root=tmp_path / "workbench",
        build_label="official-a",
        inventory_key="official-uk-network-v1.json",
    )

    assert result["status"] == "stopped_missing_normalized_inventory"
    assert result["candidate_built"] is False
    assert result["required_actions"]


def test_release_audit_separates_data_state_from_solver_and_long_run_claims(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "workbench"
    freshness = state_root / "reports" / "freshness"
    freshness.mkdir(parents=True)
    (freshness / "source_discovery_report.json").write_text(
        json.dumps(
            {
                "revisions": [
                    {
                        "source_id": "neso.dno-license-areas",
                        "revision_id": "2024-05-03",
                        "status": "new",
                        "object_key": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = audit_release(state_root)

    assert result["decision"] == "stopped_missing_official_sources"
    assert result["scientific_readiness_claim"] is False
    assert result["solver_validation"] == "out_of_scope"
    assert result["annual_and_ten_year_runs"] == "out_of_scope"


def test_release_audit_keeps_pinned_bytes_in_rights_review(tmp_path: Path) -> None:
    state_root = tmp_path / "workbench"
    receipts = state_root / "receipts" / "neso.dno-license-areas"
    receipts.mkdir(parents=True)
    (receipts / "2024-05-03.json").write_text(
        json.dumps(
            {
                "source_id": "neso.dno-license-areas",
                "revision_id": "2024-05-03",
                "object_key": "raw/sha256/" + "a" * 64,
                "redistribution_decision": "needs_rights_review",
            }
        ),
        encoding="utf-8",
    )

    result = audit_release(state_root)

    assert result["official_sources"]["rights_review_pending"] == [
        "neso.dno-license-areas@2024-05-03"
    ]
