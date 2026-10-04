"""Deterministic, signed VRE-curtailment attribution for one matched period."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from typing import Mapping, Sequence

from .errors import InvariantError


SNAPSHOT_SCHEMA = "value.vre-counterfactual-snapshot/v1"
ATTRIBUTION_SCHEMA = "value.vre-curtailment-attribution/v2"
ATTRIBUTION_METHOD_ID = "value.pro-rata-technology-bid-tranche/v1"
FAILURE_SCHEMA = "value.vre-curtailment-attribution-failure/v1"
INPUT_VALIDATION_CODE = "GF_VRE_ATTRIBUTION_INPUT_INVALID"
RESULT_VALIDATION_CODE = "GF_VRE_ATTRIBUTION_RESULT_INVALID"


class CurtailmentAttributionError(InvariantError):
    def __init__(self, code: str, message: str, evidence: Mapping[str, object]):
        super().__init__(message)
        self.code = code
        self.evidence = dict(evidence)


def canonical_vre_technology(raw: str) -> str | None:
    """Return Solar, Onshore wind, Offshore wind, or None."""

    if not isinstance(raw, str):
        return None
    normalised = " ".join(raw.lower().replace("_", " ").replace("-", " ").split())
    if "offshore" in normalised and "wind" in normalised:
        return "Offshore wind"
    if "onshore" in normalised and "wind" in normalised:
        return "Onshore wind"
    if "solar" in normalised or "photovolta" in normalised or normalised == "pv":
        return "Solar"
    return None


def build_bid_tranche_id(
    canonical_technology: str,
    offer_price_gbp_per_mwh: float,
) -> str:
    """Hash canonical JSON with a Decimal-normalised offer price."""

    technology = canonical_vre_technology(canonical_technology)
    if technology is None:
        raise ValueError("bid tranche technology must be supported VRE")
    try:
        price = Decimal(str(offer_price_gbp_per_mwh))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("offer price must be finite") from exc
    if not price.is_finite():
        raise ValueError("offer price must be finite")
    price = price.normalize()
    if price == 0:
        price = Decimal(0)
    payload = {
        "canonical_technology": technology,
        "offer_price_gbp_per_mwh": format(price, "f"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"vre-{technology.lower().replace(' ', '-')}-{digest}"


def _stable_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty stable identifier")
    return value.strip()


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


@dataclass(frozen=True)
class VRECounterfactualRow:
    asset_id: str
    owner_id: str
    canonical_technology: str
    zone_id: str
    bid_tranche_id: str
    realised_available_vre_mwh: float
    perfect_forecast_copperplate_dispatch_mwh: float
    realised_copperplate_dispatch_mwh: float
    zonal_final_dispatch_mwh: float

@dataclass(frozen=True)
class VRECounterfactualSnapshot:
    run_id: str
    year: int
    period: int
    period_id: str
    realised_input_sha256: str
    rows: tuple[VRECounterfactualRow, ...]
    module_identities: Mapping[str, str] = field(default_factory=dict)
    schema: str = SNAPSHOT_SCHEMA

@dataclass(frozen=True)
class VREReferenceGroup:
    canonical_technology: str
    bid_tranche_id: str
    realised_available_vre_mwh: float
    raw_perfect_forecast_copperplate_dispatch_mwh: float
    raw_realised_copperplate_dispatch_mwh: float
    perfect_reference_dispatch_mwh: float
    copperplate_reference_dispatch_mwh: float

    def __post_init__(self) -> None:
        _validate_result_values(self, self.__dataclass_fields__, "reference group")


@dataclass(frozen=True)
class VRECurtailmentDetail:
    asset_id: str
    owner_id: str
    canonical_technology: str
    zone_id: str
    bid_tranche_id: str
    realised_available_vre_mwh: float
    perfect_reference_dispatch_mwh: float
    copperplate_reference_dispatch_mwh: float
    zonal_final_dispatch_mwh: float
    economic_curtailment_mwh: float
    forecast_added_curtailment_mwh: float
    forecast_avoided_curtailment_mwh: float
    forecast_net_impact_mwh: float
    redispatch_added_curtailment_mwh: float
    redispatch_avoided_curtailment_mwh: float
    redispatch_net_impact_mwh: float
    total_curtailment_mwh: float
    identity_residual_mwh: float
    attribution_method_id: str = ATTRIBUTION_METHOD_ID

    def __post_init__(self) -> None:
        _validate_result_values(self, self.__dataclass_fields__, "curtailment detail")


@dataclass(frozen=True)
class VRECurtailmentPeriod:
    run_id: str
    year: int
    period: int
    period_id: str
    realised_input_sha256: str
    realised_available_vre_mwh: float
    perfect_reference_dispatch_mwh: float
    copperplate_reference_dispatch_mwh: float
    zonal_final_dispatch_mwh: float
    economic_curtailment_mwh: float
    forecast_added_curtailment_mwh: float
    forecast_avoided_curtailment_mwh: float
    forecast_net_impact_mwh: float
    redispatch_added_curtailment_mwh: float
    redispatch_avoided_curtailment_mwh: float
    redispatch_net_impact_mwh: float
    total_curtailment_mwh: float
    curtailment_rate: float
    identity_residual_mwh: float
    tolerance_mwh: float
    status: str = "reconciled"
    schema: str = ATTRIBUTION_SCHEMA
    attribution_method_id: str = ATTRIBUTION_METHOD_ID

    def __post_init__(self) -> None:
        _validate_result_values(self, self.__dataclass_fields__, "curtailment period")


@dataclass(frozen=True)
class VRECurtailmentAttribution:
    snapshot: VRECounterfactualSnapshot
    details: tuple[VRECurtailmentDetail, ...]
    period: VRECurtailmentPeriod
    reference_groups: tuple[VREReferenceGroup, ...]
    schema: str = ATTRIBUTION_SCHEMA
    attribution_method_id: str = ATTRIBUTION_METHOD_ID

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, VRECounterfactualSnapshot):
            raise _result_validation_error("attribution snapshot is invalid", self)
        if not isinstance(self.period, VRECurtailmentPeriod):
            raise _result_validation_error("attribution period is invalid", self)
        if not all(isinstance(item, VRECurtailmentDetail) for item in self.details):
            raise _result_validation_error("attribution details are invalid", self)
        if not all(isinstance(item, VREReferenceGroup) for item in self.reference_groups):
            raise _result_validation_error("attribution reference groups are invalid", self)


def _evidence_value(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, Mapping):
        return {
            str(key): _evidence_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_evidence_value(item) for item in value]
    if is_dataclass(value):
        return _evidence_value(asdict(value))
    return value


def _evidence_type(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _typed_evidence_value(value: object) -> dict[str, object]:
    value_type = _evidence_type(value)
    if value is None or isinstance(value, (bool, int, str)):
        return {"type": value_type, "value": value}
    if isinstance(value, float):
        return {"type": value_type, "value": _evidence_value(value)}
    if isinstance(value, bytes):
        return {"type": value_type, "hex": value.hex()}
    if isinstance(value, (tuple, list)):
        return {
            "type": value_type,
            "items": [_typed_evidence_value(item) for item in value],
        }
    if isinstance(value, Mapping):
        entries = [
            {"key": _typed_evidence_value(key), "value": _typed_evidence_value(item)}
            for key, item in value.items()
        ]
        return {
            "type": value_type,
            "entries": sorted(entries, key=_module_identity_entry_sort_key),
        }
    try:
        representation = repr(value)
    except Exception:
        representation = "<unrepresentable>"
    return {"type": value_type, "repr": representation}


def _module_identity_entry_sort_key(entry: Mapping[str, object]) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _canonical_module_identities(identities: object) -> dict[str, object]:
    if not isinstance(identities, Mapping):
        return {
            "encoding": "value.module-identities-invalid/v1",
            "invalid_mapping_type": _evidence_type(identities),
            "raw_value": _typed_evidence_value(identities),
        }
    if all(isinstance(key, str) and isinstance(value, str) for key, value in identities.items()):
        return {key: identities[key] for key in sorted(identities)}
    entries = [
        {"key": _typed_evidence_value(key), "value": _typed_evidence_value(value)}
        for key, value in identities.items()
    ]
    return {
        "encoding": "value.module-identities-invalid/v1",
        "entries": sorted(entries, key=_module_identity_entry_sort_key),
    }


def _row_payload(row: object) -> dict[str, object]:
    names = (
        "asset_id", "owner_id", "canonical_technology", "zone_id", "bid_tranche_id",
        "realised_available_vre_mwh", "perfect_forecast_copperplate_dispatch_mwh",
        "realised_copperplate_dispatch_mwh", "zonal_final_dispatch_mwh",
    )
    if isinstance(row, VRECounterfactualRow):
        return {name: _evidence_value(getattr(row, name)) for name in names}
    return {"invalid_row_type": type(row).__name__, "raw_value": _evidence_value(row)}


def _raw_row_sort_key(row: object) -> tuple[str, str, str, str, str]:
    payload = _row_payload(row)
    return tuple(str(payload.get(name, "")) for name in (
        "asset_id", "bid_tranche_id", "owner_id", "zone_id", "canonical_technology",
    ))


def _snapshot_payload(snapshot: VRECounterfactualSnapshot) -> dict[str, object]:
    raw_identities = snapshot.module_identities
    identities = _canonical_module_identities(raw_identities)
    raw_rows = snapshot.rows if isinstance(snapshot.rows, (tuple, list)) else (snapshot.rows,)
    return {
        "schema": _evidence_value(snapshot.schema),
        "run_id": _evidence_value(snapshot.run_id),
        "year": _evidence_value(snapshot.year),
        "period": _evidence_value(snapshot.period),
        "period_id": _evidence_value(snapshot.period_id),
        "realised_input_sha256": _evidence_value(snapshot.realised_input_sha256),
        "module_identities": identities,
        "rows": [_row_payload(row) for row in sorted(raw_rows, key=_raw_row_sort_key)],
    }


def _result_validation_error(message: str, value: object) -> CurtailmentAttributionError:
    return CurtailmentAttributionError(RESULT_VALIDATION_CODE, message, {
        "raw_result": _evidence_value(value),
        "raw_reference_groups": [],
        "normalised_reference_groups": [],
        "residual_mwh": None,
        "tolerance_mwh": None,
    })


def _validate_result_values(value: object, fields: Mapping[str, object], label: str) -> None:
    for name in fields:
        if name.endswith("_mwh") or name == "curtailment_rate":
            try:
                numeric = _finite(getattr(value, name), name)
            except ValueError as exc:
                raise _result_validation_error(f"{label} contains an invalid {name}", value) from exc
            if not math.isfinite(numeric):
                raise _result_validation_error(f"{label} contains an invalid {name}", value)


def _input_validation_error(
    message: str, snapshot: VRECounterfactualSnapshot | object
) -> CurtailmentAttributionError:
    raw_snapshot = (
        _snapshot_payload(snapshot)
        if isinstance(snapshot, VRECounterfactualSnapshot)
        else {"invalid_snapshot_type": type(snapshot).__name__, "raw_value": _evidence_value(snapshot)}
    )
    return CurtailmentAttributionError(INPUT_VALIDATION_CODE, message, {
        "raw_snapshot": raw_snapshot,
        "module_identities": raw_snapshot.get("module_identities", {}),
        "raw_reference_groups": [],
        "normalised_reference_groups": [],
        "residual_mwh": None,
        "tolerance_mwh": None,
        "realised_input_sha256": raw_snapshot.get("realised_input_sha256"),
    })


def _validate_snapshot_inputs(snapshot: VRECounterfactualSnapshot | object) -> None:
    if not isinstance(snapshot, VRECounterfactualSnapshot):
        raise _input_validation_error("snapshot must be a VRECounterfactualSnapshot", snapshot)
    for name in ("run_id", "period_id"):
        try:
            _stable_identifier(getattr(snapshot, name), name)
        except ValueError as exc:
            raise _input_validation_error(str(exc), snapshot) from exc
    if isinstance(snapshot.year, bool) or not isinstance(snapshot.year, int):
        raise _input_validation_error("year must be an integer", snapshot)
    if isinstance(snapshot.period, bool) or not isinstance(snapshot.period, int) or snapshot.period < 0:
        raise _input_validation_error("period must be a non-negative integer", snapshot)
    try:
        _sha256(snapshot.realised_input_sha256, "realised_input_sha256")
    except ValueError as exc:
        raise _input_validation_error(str(exc), snapshot) from exc
    if snapshot.schema != SNAPSHOT_SCHEMA:
        raise _input_validation_error("snapshot schema is unsupported", snapshot)
    if not isinstance(snapshot.rows, tuple):
        raise _input_validation_error("rows must be a tuple", snapshot)
    if not isinstance(snapshot.module_identities, Mapping):
        raise _input_validation_error("module_identities must be a mapping", snapshot)
    for key, value in snapshot.module_identities.items():
        try:
            _stable_identifier(key, "module identity key")
            _stable_identifier(value, "module identity")
        except ValueError as exc:
            raise _input_validation_error(str(exc), snapshot) from exc
    for row in snapshot.rows:
        if not isinstance(row, VRECounterfactualRow):
            raise _input_validation_error("rows must contain VRECounterfactualRow values", snapshot)
        for name in ("asset_id", "owner_id", "zone_id", "bid_tranche_id"):
            try:
                _stable_identifier(getattr(row, name), name)
            except ValueError as exc:
                raise _input_validation_error(str(exc), snapshot) from exc
        technology = canonical_vre_technology(row.canonical_technology)
        if technology is None or technology != row.canonical_technology:
            raise _input_validation_error(
                "canonical_technology must be a supported canonical VRE technology", snapshot
            )
        for name in (
            "realised_available_vre_mwh", "perfect_forecast_copperplate_dispatch_mwh",
            "realised_copperplate_dispatch_mwh", "zonal_final_dispatch_mwh",
        ):
            try:
                _finite(getattr(row, name), name)
            except ValueError as exc:
                raise _input_validation_error(str(exc), snapshot) from exc


def _sum_finite(values: Sequence[float]) -> float:
    try:
        result = math.fsum(values)
    except OverflowError as exc:
        raise ValueError("finite values overflowed during deterministic accumulation") from exc
    if not math.isfinite(result):
        raise ValueError("finite values overflowed during deterministic accumulation")
    return result


def _group_payload(rows: Sequence[VRECounterfactualRow]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[VRECounterfactualRow]] = {}
    for row in sorted(rows, key=_row_sort_key):
        grouped.setdefault((row.canonical_technology, row.bid_tranche_id), []).append(row)
    return [
        {
            "canonical_technology": technology,
            "bid_tranche_id": tranche,
            "asset_ids": [row.asset_id for row in group],
            "realised_available_vre_mwh": _sum_finite([row.realised_available_vre_mwh for row in group]),
            "perfect_forecast_copperplate_dispatch_mwh": _sum_finite(
                [row.perfect_forecast_copperplate_dispatch_mwh for row in group]
            ),
            "realised_copperplate_dispatch_mwh": _sum_finite(
                [row.realised_copperplate_dispatch_mwh for row in group]
            ),
        }
        for (technology, tranche), group in sorted(grouped.items())
    ]


def _row_sort_key(row: VRECounterfactualRow) -> tuple[str, str, str, str, str]:
    return (row.asset_id, row.bid_tranche_id, row.owner_id, row.zone_id, row.canonical_technology)


def _error(
    code: str,
    message: str,
    snapshot: VRECounterfactualSnapshot,
    *,
    raw_reference_groups: Sequence[Mapping[str, object]],
    normalised_reference_groups: Sequence[Mapping[str, object]] = (),
    residual_mwh: float | None = None,
    tolerance_mwh: float | None = None,
) -> CurtailmentAttributionError:
    return CurtailmentAttributionError(code, message, {
        "raw_snapshot": _snapshot_payload(snapshot),
        "module_identities": _canonical_module_identities(snapshot.module_identities),
        "raw_reference_groups": [dict(group) for group in raw_reference_groups],
        "normalised_reference_groups": [dict(group) for group in normalised_reference_groups],
        "residual_mwh": residual_mwh,
        "tolerance_mwh": tolerance_mwh,
        "realised_input_sha256": snapshot.realised_input_sha256,
    })


def _clamp_nonnegative(value: float, tolerance: float) -> float:
    return 0.0 if -tolerance <= value < 0.0 else value


def _clamp_dispatch(value: float, availability: float, tolerance: float) -> float:
    value = _clamp_nonnegative(value, tolerance)
    return availability if availability < value <= availability + tolerance else value


def _allocate_group_references(
    ordered: Sequence[VRECounterfactualRow],
    available: float,
    perfect: float,
    copperplate: float,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    weights = tuple(
        0.0 if available == 0.0 else max(row.realised_available_vre_mwh, 0.0) / available
        for row in ordered
    )
    return (
        tuple(perfect * weight for weight in weights),
        tuple(copperplate * weight for weight in weights),
    )


def attribute_vre_curtailment(
    snapshot: VRECounterfactualSnapshot,
) -> VRECurtailmentAttribution:
    """Validate, reference-allocate and reconcile one period."""

    _validate_snapshot_inputs(snapshot)
    try:
        availability_total = _sum_finite([
            row.realised_available_vre_mwh for row in snapshot.rows
        ])
        raw_groups = _group_payload(snapshot.rows)
    except ValueError as exc:
        raise _error(
            RESULT_VALIDATION_CODE,
            str(exc),
            snapshot,
            raw_reference_groups=[],
        ) from exc
    tolerance = max(1e-7, 1e-10 * max(availability_total, 1.0))

    keys = [(row.asset_id, row.bid_tranche_id) for row in snapshot.rows]
    if len(set(keys)) != len(keys):
        raise _error(
            "GF_VRE_COUNTERFACTUAL_SET_MISMATCH",
            "VRE counterfactual rows must contain one stable object/tranche key per case",
            snapshot,
            raw_reference_groups=raw_groups,
            tolerance_mwh=tolerance,
        )
    for row in snapshot.rows:
        values = {
            "realised availability": row.realised_available_vre_mwh,
            "perfect-forecast copperplate dispatch": row.perfect_forecast_copperplate_dispatch_mwh,
            "realised copperplate dispatch": row.realised_copperplate_dispatch_mwh,
            "zonal final dispatch": row.zonal_final_dispatch_mwh,
        }
        if any(value < -tolerance for value in values.values()):
            raise _error(
                "GF_VRE_DISPATCH_EXCEEDS_AVAILABILITY",
                f"VRE quantities cannot be materially negative for {row.asset_id}",
                snapshot,
                raw_reference_groups=raw_groups,
                tolerance_mwh=tolerance,
            )

    grouped: dict[tuple[str, str], list[VRECounterfactualRow]] = {}
    for row in snapshot.rows:
        grouped.setdefault((row.canonical_technology, row.bid_tranche_id), []).append(row)
    normalised_groups: list[dict[str, object]] = []
    details: list[VRECurtailmentDetail] = []
    reference_groups: list[VREReferenceGroup] = []
    for (technology, tranche), group in sorted(grouped.items()):
        ordered = sorted(group, key=_row_sort_key)
        try:
            available = _sum_finite([
                _clamp_nonnegative(row.realised_available_vre_mwh, tolerance)
                for row in ordered
            ])
            raw_perfect = _sum_finite([
                row.perfect_forecast_copperplate_dispatch_mwh for row in ordered
            ])
            raw_copperplate = _sum_finite([
                row.realised_copperplate_dispatch_mwh for row in ordered
            ])
        except ValueError as exc:
            raise _error(
                RESULT_VALIDATION_CODE,
                str(exc),
                snapshot,
                raw_reference_groups=raw_groups,
                normalised_reference_groups=normalised_groups,
                tolerance_mwh=tolerance,
            ) from exc
        perfect = _clamp_dispatch(raw_perfect, available, tolerance)
        copperplate = _clamp_dispatch(raw_copperplate, available, tolerance)
        if perfect > available or copperplate > available:
            raise _error(
                "GF_VRE_DISPATCH_EXCEEDS_AVAILABILITY",
                f"Copperplate dispatch exceeds realised availability for {technology}/{tranche}",
                snapshot,
                raw_reference_groups=raw_groups,
                normalised_reference_groups=normalised_groups,
                tolerance_mwh=tolerance,
            )
        if available == 0.0 and (perfect > 0.0 or copperplate > 0.0):
            raise _error(
                "GF_VRE_DISPATCH_EXCEEDS_AVAILABILITY",
                f"Positive copperplate dispatch has zero realised availability for {technology}/{tranche}",
                snapshot,
                raw_reference_groups=raw_groups,
                normalised_reference_groups=normalised_groups,
                tolerance_mwh=tolerance,
            )
        normalised_groups.append({
            "canonical_technology": technology,
            "bid_tranche_id": tranche,
            "realised_available_vre_mwh": available,
            "perfect_reference_dispatch_mwh": perfect,
            "copperplate_reference_dispatch_mwh": copperplate,
        })
        reference_groups.append(VREReferenceGroup(
            canonical_technology=technology,
            bid_tranche_id=tranche,
            realised_available_vre_mwh=available,
            raw_perfect_forecast_copperplate_dispatch_mwh=raw_perfect,
            raw_realised_copperplate_dispatch_mwh=raw_copperplate,
            perfect_reference_dispatch_mwh=perfect,
            copperplate_reference_dispatch_mwh=copperplate,
        ))
        perfect_references, copperplate_references = _allocate_group_references(
            ordered, available, perfect, copperplate
        )
        if len(perfect_references) != len(ordered) or len(copperplate_references) != len(ordered):
            raise _error(
                "GF_VRE_ATTRIBUTION_IDENTITY_FAILED",
                f"Reference allocation has the wrong row count for {technology}/{tranche}",
                snapshot,
                raw_reference_groups=raw_groups,
                normalised_reference_groups=normalised_groups,
                tolerance_mwh=tolerance,
            )
        try:
            perfect_reference_residual = _sum_finite(list(perfect_references)) - perfect
            copperplate_reference_residual = _sum_finite(list(copperplate_references)) - copperplate
        except ValueError as exc:
            raise _error(
                RESULT_VALIDATION_CODE,
                str(exc),
                snapshot,
                raw_reference_groups=raw_groups,
                normalised_reference_groups=normalised_groups,
                tolerance_mwh=tolerance,
            ) from exc
        if (
            abs(perfect_reference_residual) > tolerance
            or abs(copperplate_reference_residual) > tolerance
        ):
            raise _error(
                "GF_VRE_ATTRIBUTION_IDENTITY_FAILED",
                f"Reference allocation does not conserve group dispatch for {technology}/{tranche}",
                snapshot,
                raw_reference_groups=raw_groups,
                normalised_reference_groups=normalised_groups,
                residual_mwh=(
                    perfect_reference_residual
                    if abs(perfect_reference_residual) > tolerance
                    else copperplate_reference_residual
                ),
                tolerance_mwh=tolerance,
            )
        for row, perfect_reference, copperplate_reference in zip(
            ordered, perfect_references, copperplate_references, strict=True
        ):
            realised_available = _clamp_nonnegative(row.realised_available_vre_mwh, tolerance)
            zonal = _clamp_dispatch(row.zonal_final_dispatch_mwh, realised_available, tolerance)
            if zonal > realised_available:
                raise _error(
                    "GF_VRE_DISPATCH_EXCEEDS_AVAILABILITY",
                    f"Zonal dispatch exceeds realised availability for {row.asset_id}",
                    snapshot,
                    raw_reference_groups=raw_groups,
                    normalised_reference_groups=normalised_groups,
                    tolerance_mwh=tolerance,
                )
            economic = realised_available - perfect_reference
            forecast_delta = perfect_reference - copperplate_reference
            redispatch_delta = copperplate_reference - zonal
            forecast_added = max(forecast_delta, 0.0)
            forecast_avoided = max(-forecast_delta, 0.0)
            redispatch_added = max(redispatch_delta, 0.0)
            redispatch_avoided = max(-redispatch_delta, 0.0)
            total = realised_available - zonal
            residual = (
                economic + forecast_added - forecast_avoided
                + redispatch_added - redispatch_avoided - total
            )
            if abs(residual) <= tolerance:
                residual = 0.0
            details.append(VRECurtailmentDetail(
                asset_id=row.asset_id,
                owner_id=row.owner_id,
                canonical_technology=row.canonical_technology,
                zone_id=row.zone_id,
                bid_tranche_id=row.bid_tranche_id,
                realised_available_vre_mwh=realised_available,
                perfect_reference_dispatch_mwh=perfect_reference,
                copperplate_reference_dispatch_mwh=copperplate_reference,
                zonal_final_dispatch_mwh=zonal,
                economic_curtailment_mwh=economic,
                forecast_added_curtailment_mwh=forecast_added,
                forecast_avoided_curtailment_mwh=forecast_avoided,
                forecast_net_impact_mwh=forecast_added - forecast_avoided,
                redispatch_added_curtailment_mwh=redispatch_added,
                redispatch_avoided_curtailment_mwh=redispatch_avoided,
                redispatch_net_impact_mwh=redispatch_added - redispatch_avoided,
                total_curtailment_mwh=total,
                identity_residual_mwh=residual,
            ))
    details.sort(key=lambda detail: (
        detail.canonical_technology, detail.bid_tranche_id, detail.asset_id,
        detail.owner_id, detail.zone_id,
    ))
    try:
        totals = {
            field_name: _sum_finite([getattr(detail, field_name) for detail in details])
            for field_name in (
                "realised_available_vre_mwh", "perfect_reference_dispatch_mwh",
                "copperplate_reference_dispatch_mwh", "zonal_final_dispatch_mwh",
                "economic_curtailment_mwh", "forecast_added_curtailment_mwh",
                "forecast_avoided_curtailment_mwh", "redispatch_added_curtailment_mwh",
                "redispatch_avoided_curtailment_mwh", "total_curtailment_mwh",
            )
        }
    except ValueError as exc:
        raise _error(
            RESULT_VALIDATION_CODE,
            str(exc),
            snapshot,
            raw_reference_groups=raw_groups,
            normalised_reference_groups=normalised_groups,
            tolerance_mwh=tolerance,
        ) from exc
    residual = (
        totals["economic_curtailment_mwh"]
        + totals["forecast_added_curtailment_mwh"]
        - totals["forecast_avoided_curtailment_mwh"]
        + totals["redispatch_added_curtailment_mwh"]
        - totals["redispatch_avoided_curtailment_mwh"]
        - totals["total_curtailment_mwh"]
    )
    if abs(residual) > tolerance:
        raise _error(
            "GF_VRE_ATTRIBUTION_IDENTITY_FAILED",
            "VRE curtailment attribution identity does not reconcile",
            snapshot,
            raw_reference_groups=raw_groups,
            normalised_reference_groups=normalised_groups,
            residual_mwh=residual,
            tolerance_mwh=tolerance,
        )
    residual = 0.0
    period = VRECurtailmentPeriod(
        run_id=snapshot.run_id,
        year=snapshot.year,
        period=snapshot.period,
        period_id=snapshot.period_id,
        realised_input_sha256=snapshot.realised_input_sha256,
        realised_available_vre_mwh=totals["realised_available_vre_mwh"],
        perfect_reference_dispatch_mwh=totals["perfect_reference_dispatch_mwh"],
        copperplate_reference_dispatch_mwh=totals["copperplate_reference_dispatch_mwh"],
        zonal_final_dispatch_mwh=totals["zonal_final_dispatch_mwh"],
        economic_curtailment_mwh=totals["economic_curtailment_mwh"],
        forecast_added_curtailment_mwh=totals["forecast_added_curtailment_mwh"],
        forecast_avoided_curtailment_mwh=totals["forecast_avoided_curtailment_mwh"],
        forecast_net_impact_mwh=(
            totals["forecast_added_curtailment_mwh"] - totals["forecast_avoided_curtailment_mwh"]
        ),
        redispatch_added_curtailment_mwh=totals["redispatch_added_curtailment_mwh"],
        redispatch_avoided_curtailment_mwh=totals["redispatch_avoided_curtailment_mwh"],
        redispatch_net_impact_mwh=(
            totals["redispatch_added_curtailment_mwh"] - totals["redispatch_avoided_curtailment_mwh"]
        ),
        total_curtailment_mwh=totals["total_curtailment_mwh"],
        curtailment_rate=(
            0.0 if totals["realised_available_vre_mwh"] == 0.0
            else totals["total_curtailment_mwh"] / totals["realised_available_vre_mwh"]
        ),
        identity_residual_mwh=residual,
        tolerance_mwh=tolerance,
    )
    return VRECurtailmentAttribution(
        snapshot=snapshot,
        details=tuple(details),
        period=period,
        reference_groups=tuple(reference_groups),
    )


def failure_payload(
    error: CurtailmentAttributionError,
    snapshot: VRECounterfactualSnapshot,
) -> dict[str, object]:
    """Return an auditable failure artifact without replacing a normal result."""

    if not isinstance(error, CurtailmentAttributionError):
        raise _input_validation_error("error must be a CurtailmentAttributionError", snapshot)
    if not isinstance(snapshot, VRECounterfactualSnapshot):
        raise _input_validation_error("snapshot must be a VRECounterfactualSnapshot", snapshot)
    evidence = dict(error.evidence)
    expected_snapshot = evidence.get("raw_snapshot")
    actual_snapshot = _snapshot_payload(snapshot)
    if expected_snapshot != actual_snapshot:
        raise _error(
            INPUT_VALIDATION_CODE,
            "failure payload snapshot does not match the snapshot that raised the error",
            snapshot,
            raw_reference_groups=[],
        )
    return {
        "schema": FAILURE_SCHEMA,
        "schema_version": FAILURE_SCHEMA,
        "error_code": error.code,
        "error_message": str(error),
        "run_id": snapshot.run_id,
        "year": snapshot.year,
        "period": snapshot.period,
        "period_id": snapshot.period_id,
        "realised_input_sha256": snapshot.realised_input_sha256,
        "module_identities": _canonical_module_identities(snapshot.module_identities),
        "raw_snapshot": evidence.get("raw_snapshot", _snapshot_payload(snapshot)),
        "raw_reference_groups": evidence.get("raw_reference_groups", []),
        "normalised_reference_groups": evidence.get("normalised_reference_groups", []),
        "residual_mwh": evidence.get("residual_mwh"),
        "tolerance_mwh": evidence.get("tolerance_mwh"),
        "attribution_schema": ATTRIBUTION_SCHEMA,
        "attribution_method_id": ATTRIBUTION_METHOD_ID,
    }
