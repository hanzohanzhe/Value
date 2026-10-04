from __future__ import annotations

from dataclasses import replace
import json
import math

import gridform_core.vre_curtailment_attribution as attribution_module
from gridform_core.vre_curtailment_attribution import (
    CurtailmentAttributionError,
    VRECounterfactualRow,
    VRECounterfactualSnapshot,
    attribute_vre_curtailment,
    build_bid_tranche_id,
    canonical_vre_technology,
    failure_payload,
)
import pytest


def row(
    asset: str,
    zone: str,
    available: float,
    perfect: float,
    copperplate: float,
    zonal: float,
) -> VRECounterfactualRow:
    return VRECounterfactualRow(
        asset_id=asset,
        owner_id=f"owner-{asset}",
        canonical_technology="Onshore wind",
        zone_id=zone,
        bid_tranche_id="vre-onshore-0",
        realised_available_vre_mwh=available,
        perfect_forecast_copperplate_dispatch_mwh=perfect,
        realised_copperplate_dispatch_mwh=copperplate,
        zonal_final_dispatch_mwh=zonal,
    )


def test_redispatch_can_avoid_all_copperplate_curtailment() -> None:
    snapshot = VRECounterfactualSnapshot(
        run_id="run",
        year=2025,
        period=6,
        period_id="2022-01-01:07",
        realised_input_sha256="a" * 64,
        rows=(row("wind", "north", 10.0, 7.0, 7.0, 10.0),),
    )

    result = attribute_vre_curtailment(snapshot)

    assert result.period.economic_curtailment_mwh == 3.0
    assert result.period.redispatch_added_curtailment_mwh == 0.0
    assert result.period.redispatch_avoided_curtailment_mwh == 3.0
    assert result.period.redispatch_net_impact_mwh == -3.0
    assert result.period.total_curtailment_mwh == 0.0
    assert result.period.identity_residual_mwh == 0.0


def test_empty_canonical_vre_snapshot_returns_one_reconciled_zero_period() -> None:
    snapshot = VRECounterfactualSnapshot(
        run_id="vre-free-run",
        year=2025,
        period=0,
        period_id="p0",
        realised_input_sha256="0" * 64,
        rows=(),
        module_identities={
            "perfect_forecast_copperplate": "value-copperplate-balancing@1.0.0",
            "realised_copperplate": "value-copperplate-balancing@1.0.0",
            "zonal_final": "value-zonal-redispatch-balancing@1.0.0",
        },
    )

    result = attribute_vre_curtailment(snapshot)

    assert result.details == ()
    assert result.reference_groups == ()
    assert result.period.status == "reconciled"
    assert result.period.realised_available_vre_mwh == 0.0
    assert result.period.perfect_reference_dispatch_mwh == 0.0
    assert result.period.copperplate_reference_dispatch_mwh == 0.0
    assert result.period.zonal_final_dispatch_mwh == 0.0
    assert result.period.economic_curtailment_mwh == 0.0
    assert result.period.forecast_added_curtailment_mwh == 0.0
    assert result.period.forecast_avoided_curtailment_mwh == 0.0
    assert result.period.redispatch_added_curtailment_mwh == 0.0
    assert result.period.redispatch_avoided_curtailment_mwh == 0.0
    assert result.period.total_curtailment_mwh == 0.0
    assert result.period.curtailment_rate == 0.0
    assert result.period.identity_residual_mwh == 0.0


def test_simultaneous_zonal_added_and_avoided_are_kept_gross() -> None:
    snapshot = VRECounterfactualSnapshot(
        run_id="run",
        year=2025,
        period=0,
        period_id="p0",
        realised_input_sha256="b" * 64,
        rows=(
            row("north", "north", 10.0, 8.0, 8.0, 6.0),
            row("south", "south", 10.0, 8.0, 8.0, 10.0),
        ),
    )

    result = attribute_vre_curtailment(snapshot)

    assert result.period.redispatch_added_curtailment_mwh == 2.0
    assert result.period.redispatch_avoided_curtailment_mwh == 2.0
    assert result.period.redispatch_net_impact_mwh == 0.0
    assert result.period.total_curtailment_mwh == 4.0


def test_copperplate_reference_is_invariant_to_raw_solver_allocation() -> None:
    first = VRECounterfactualSnapshot(
        run_id="a",
        year=2025,
        period=0,
        period_id="p0",
        realised_input_sha256="c" * 64,
        rows=(
            row("small", "north", 30.0, 0.0, 0.0, 20.0),
            row("large", "south", 70.0, 50.0, 50.0, 30.0),
        ),
    )
    second = VRECounterfactualSnapshot(
        run_id="b",
        year=2025,
        period=0,
        period_id="p0",
        realised_input_sha256="c" * 64,
        rows=(
            row("large", "south", 70.0, 0.0, 0.0, 30.0),
            row("small", "north", 30.0, 50.0, 50.0, 20.0),
        ),
    )

    left = attribute_vre_curtailment(first)
    right = attribute_vre_curtailment(second)

    assert [(item.asset_id, item.perfect_reference_dispatch_mwh) for item in left.details] == [
        (item.asset_id, item.perfect_reference_dispatch_mwh) for item in right.details
    ]


def test_canonical_technology_and_bid_tranche_identity_are_stable() -> None:
    assert canonical_vre_technology("Solar PV") == "Solar"
    assert canonical_vre_technology("Offshore Wind") == "Offshore wind"
    assert canonical_vre_technology("reservoir hydro") is None
    assert build_bid_tranche_id("Onshore wind", 3.0) == build_bid_tranche_id(
        "Onshore wind", 3.000
    )


def test_dispatch_above_available_is_rejected_with_a_serialisable_failure_payload() -> None:
    snapshot = VRECounterfactualSnapshot(
        run_id="run",
        year=2025,
        period=4,
        period_id="p4",
        realised_input_sha256="d" * 64,
        module_identities={"zonal": "value.zonal/v1"},
        rows=(row("wind", "north", 10.0, 11.0, 10.0, 10.0),),
    )

    with pytest.raises(CurtailmentAttributionError) as caught:
        attribute_vre_curtailment(snapshot)

    assert caught.value.code == "GF_VRE_DISPATCH_EXCEEDS_AVAILABILITY"
    payload = failure_payload(error=caught.value, snapshot=snapshot)
    assert payload["schema"] == "value.vre-curtailment-attribution-failure/v1"
    assert payload["run_id"] == "run"
    assert payload["module_identities"] == {"zonal": "value.zonal/v1"}
    assert payload["raw_snapshot"]["rows"][0]["perfect_forecast_copperplate_dispatch_mwh"] == 11.0


@pytest.mark.parametrize(
    ("changed_row", "changed_snapshot"),
    (
        ({"asset_id": ""}, {}),
        ({"canonical_technology": "Wind"}, {}),
        ({"realised_available_vre_mwh": math.nan}, {}),
        ({}, {"realised_input_sha256": "not-a-sha256"}),
    ),
)
def test_invalid_core_inputs_fail_with_typed_raw_evidence(
    changed_row: dict[str, object], changed_snapshot: dict[str, object]
) -> None:
    snapshot = VRECounterfactualSnapshot(
        run_id="run",
        year=2025,
        period=4,
        period_id="p4",
        realised_input_sha256="e" * 64,
        rows=(replace(row("wind", "north", 10.0, 7.0, 7.0, 7.0), **changed_row),),
    )
    snapshot = replace(snapshot, **changed_snapshot)

    with pytest.raises(CurtailmentAttributionError) as caught:
        attribute_vre_curtailment(snapshot)

    assert caught.value.code == "GF_VRE_ATTRIBUTION_INPUT_INVALID"
    assert caught.value.evidence["raw_snapshot"]["run_id"] == "run"
    assert caught.value.evidence["raw_reference_groups"] == []


def test_group_reference_conservation_rejects_corrupted_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = VRECounterfactualSnapshot(
        run_id="run",
        year=2025,
        period=5,
        period_id="p5",
        realised_input_sha256="f" * 64,
        rows=(
            row("small", "north", 30.0, 0.0, 0.0, 20.0),
            row("large", "south", 70.0, 50.0, 50.0, 30.0),
        ),
    )

    monkeypatch.setattr(
        attribution_module,
        "_allocate_group_references",
        lambda ordered, available, perfect, copperplate: ((0.0, 0.0), (0.0, 0.0)),
    )

    with pytest.raises(CurtailmentAttributionError) as caught:
        attribute_vre_curtailment(snapshot)

    assert caught.value.code == "GF_VRE_ATTRIBUTION_IDENTITY_FAILED"
    assert caught.value.evidence["residual_mwh"] == -50.0


def test_overflowed_aggregate_result_is_rejected() -> None:
    snapshot = VRECounterfactualSnapshot(
        run_id="run",
        year=2025,
        period=6,
        period_id="p6",
        realised_input_sha256="0" * 64,
        rows=(
            row("first", "north", 1e308, 0.0, 0.0, 0.0),
            row("second", "south", 1e308, 0.0, 0.0, 0.0),
        ),
    )

    with pytest.raises(CurtailmentAttributionError) as caught:
        attribute_vre_curtailment(snapshot)

    assert caught.value.code == "GF_VRE_ATTRIBUTION_RESULT_INVALID"
    assert caught.value.evidence["raw_snapshot"]["rows"][0]["asset_id"] == "first"


def test_result_dataclasses_reject_nonfinite_aggregate_values() -> None:
    snapshot = VRECounterfactualSnapshot(
        run_id="run",
        year=2025,
        period=7,
        period_id="p7",
        realised_input_sha256="1" * 64,
        rows=(row("wind", "north", 10.0, 7.0, 7.0, 7.0),),
    )
    result = attribute_vre_curtailment(snapshot)

    with pytest.raises(CurtailmentAttributionError) as caught:
        replace(result.period, total_curtailment_mwh=math.inf)

    assert caught.value.code == "GF_VRE_ATTRIBUTION_RESULT_INVALID"


def test_failure_payload_rejects_a_different_snapshot() -> None:
    failed_snapshot = VRECounterfactualSnapshot(
        run_id="failed",
        year=2025,
        period=8,
        period_id="p8",
        realised_input_sha256="2" * 64,
        rows=(row("wind", "north", 10.0, 11.0, 10.0, 10.0),),
    )
    other_snapshot = replace(
        failed_snapshot,
        run_id="other",
        realised_input_sha256="3" * 64,
    )
    with pytest.raises(CurtailmentAttributionError) as caught:
        try:
            attribute_vre_curtailment(failed_snapshot)
        except CurtailmentAttributionError as error:
            failure_payload(error=error, snapshot=other_snapshot)

    assert caught.value.code == "GF_VRE_ATTRIBUTION_INPUT_INVALID"


def test_failure_evidence_rows_are_canonically_sorted() -> None:
    snapshot = VRECounterfactualSnapshot(
        run_id="run",
        year=2025,
        period=9,
        period_id="p9",
        realised_input_sha256="4" * 64,
        rows=(
            row("zulu", "north", 10.0, 21.0, 10.0, 10.0),
            row("alpha", "south", 10.0, 0.0, 0.0, 0.0),
        ),
    )

    with pytest.raises(CurtailmentAttributionError) as caught:
        attribute_vre_curtailment(snapshot)

    assert [item["asset_id"] for item in caught.value.evidence["raw_snapshot"]["rows"]] == [
        "alpha",
        "zulu",
    ]


def test_failure_payload_module_identities_are_canonical_across_insertion_orders() -> None:
    def payload(module_identities: dict[str, str]) -> dict[str, object]:
        snapshot = VRECounterfactualSnapshot(
            run_id="run",
            year=2025,
            period=10,
            period_id="p10",
            realised_input_sha256="5" * 64,
            module_identities=module_identities,
            rows=(row("wind", "north", 10.0, 11.0, 10.0, 10.0),),
        )
        with pytest.raises(CurtailmentAttributionError) as caught:
            attribute_vre_curtailment(snapshot)
        return failure_payload(error=caught.value, snapshot=snapshot)

    forward = payload({"perfect": "value.perfect/v1", "zonal": "value.zonal/v1"})
    reverse = payload({"zonal": "value.zonal/v1", "perfect": "value.perfect/v1"})

    assert list(forward["module_identities"].items()) == [
        ("perfect", "value.perfect/v1"),
        ("zonal", "value.zonal/v1"),
    ]
    assert forward == reverse
    assert json.dumps(forward, separators=(",", ":")) == json.dumps(reverse, separators=(",", ":"))


def test_failure_payload_serializes_mixed_module_identity_key_types() -> None:
    snapshot = VRECounterfactualSnapshot(
        run_id="run",
        year=2025,
        period=11,
        period_id="p11",
        realised_input_sha256="6" * 64,
        module_identities={"valid": "force/v1", 1: "bad"},  # type: ignore[dict-item]
        rows=(row("wind", "north", 10.0, 7.0, 7.0, 7.0),),
    )

    with pytest.raises(CurtailmentAttributionError) as caught:
        attribute_vre_curtailment(snapshot)

    payload = failure_payload(error=caught.value, snapshot=snapshot)
    entries = payload["module_identities"]["entries"]
    assert payload["error_code"] == "GF_VRE_ATTRIBUTION_INPUT_INVALID"
    assert {entry["key"]["type"] for entry in entries} == {"builtins.int", "builtins.str"}
    assert json.dumps(payload, separators=(",", ":"))


def test_failure_payload_preserves_str_colliding_module_identity_keys_deterministically() -> None:
    def payload(module_identities: dict[object, object]) -> dict[str, object]:
        snapshot = VRECounterfactualSnapshot(
            run_id="run",
            year=2025,
            period=12,
            period_id="p12",
            realised_input_sha256="7" * 64,
            module_identities=module_identities,  # type: ignore[arg-type]
            rows=(row("wind", "north", 10.0, 7.0, 7.0, 7.0),),
        )
        with pytest.raises(CurtailmentAttributionError) as caught:
            attribute_vre_curtailment(snapshot)
        return failure_payload(error=caught.value, snapshot=snapshot)

    forward = payload({"valid": "force/v1", 1: "integer-key", "1": "string-key"})
    reverse = payload({"1": "string-key", 1: "integer-key", "valid": "force/v1"})

    assert forward == reverse
    assert json.dumps(forward, separators=(",", ":")) == json.dumps(reverse, separators=(",", ":"))
    entries = forward["module_identities"]["entries"]
    assert len(entries) == 3
    assert [entry["key"] for entry in entries if str(entry["key"]["value"]) == "1"] == [
        {"type": "builtins.int", "value": 1},
        {"type": "builtins.str", "value": "1"},
    ]
