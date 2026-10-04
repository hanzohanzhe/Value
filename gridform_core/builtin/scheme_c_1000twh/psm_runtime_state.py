"""Pure-JSON year-to-date state for resumable staged PSM execution."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, fields
from typing import Mapping, Sequence

from ...v2.contracts import JsonContract, PeriodSummary
from ...market_ledger import NetworkSolverDiagnosticRow


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _normalize_json(value: object, path: str) -> object:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise ValueError(f"{path} must contain only finite numbers")
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} keys must be strings")
            result[key] = _normalize_json(item, f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return tuple(
            _normalize_json(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    raise ValueError(f"{path} must contain only JSON values")


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_integer(value: object, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field_name} must be an integer >= {minimum}")
    return value


def _require_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def _numeric_mapping(value: object, field_name: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    result: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{field_name} keys must be non-empty strings")
        result[key] = _require_finite(item, f"{field_name}.{key}")
    return result


def _json_mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    result = _normalize_json(value, field_name)
    if not isinstance(result, dict):
        raise ValueError(f"{field_name} must be an object")
    return result


def _nested_json_mapping(
    value: object, field_name: str
) -> dict[str, Mapping[str, object]]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    result: dict[str, Mapping[str, object]] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{field_name} keys must be non-empty strings")
        result[key] = _json_mapping(item, f"{field_name}.{key}")
    return result


def _strict_mapping(
    value: object, contract: type[object], field_name: str
) -> dict[str, object]:
    result = _json_mapping(value, field_name)
    expected = {item.name for item in fields(contract)}
    if set(result) != expected:
        raise ValueError(f"{field_name} fields must be exactly {sorted(expected)}")
    return result


def _period_summary(value: object) -> dict[str, object]:
    result = _strict_mapping(value, PeriodSummary, "summary")
    try:
        PeriodSummary.from_dict(result)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"summary is invalid: {exc}") from exc
    if result["schema_version"] != "value.period-summary/v2":
        raise ValueError("summary has an unsupported schema_version")
    return result


def _solver_rows(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("solver_diagnostic_rows must be an array")
    rows: list[Mapping[str, object]] = []
    for index, item in enumerate(value):
        row = _strict_mapping(
            item, NetworkSolverDiagnosticRow, f"solver_diagnostic_rows[{index}]"
        )
        try:
            NetworkSolverDiagnosticRow(**row)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"solver_diagnostic_rows[{index}] is invalid: {exc}") from exc
        rows.append(row)
    return tuple(rows)


def _json_rows(value: object, field_name: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be an array")
    return tuple(
        _json_mapping(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )


def _sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256")
    return value


def _balancing_state(
    value: object, expected_next_period_index: int
) -> dict[str, object]:
    result = _json_mapping(value, "balancing_state")
    expected = {"schema_version", "next_period_index", "consumed_inputs"}
    if set(result) != expected:
        raise ValueError(f"balancing_state fields must be exactly {sorted(expected)}")
    if result["schema_version"] != "value.zonal-redispatch-runtime-state/v1":
        raise ValueError("balancing_state has an unsupported schema_version")
    next_period_index = _require_integer(
        result["next_period_index"], "balancing_state.next_period_index"
    )
    if next_period_index != expected_next_period_index:
        raise ValueError(
            "balancing_state next_period_index does not match the outer state"
        )
    consumed = result["consumed_inputs"]
    if not isinstance(consumed, tuple):
        raise ValueError("balancing_state.consumed_inputs must be an array")
    normalized: list[Mapping[str, object]] = []
    hashes: set[str] = set()
    for expected_period, item in enumerate(consumed):
        if not isinstance(item, Mapping) or set(item) != {
            "period_index",
            "input_sha256",
        }:
            raise ValueError(
                "Each balancing consumed input must contain period_index and input_sha256"
            )
        if item["period_index"] != expected_period:
            raise ValueError(
                "balancing_state consumed periods must be ordered 0..next_period_index-1"
            )
        input_sha256 = _sha256(
            item["input_sha256"],
            f"balancing_state.consumed_inputs[{expected_period}].input_sha256",
        )
        if input_sha256 in hashes:
            raise ValueError("balancing_state consumed input hashes must be unique")
        hashes.add(input_sha256)
        normalized.append(
            {"period_index": expected_period, "input_sha256": input_sha256}
        )
    if len(normalized) != next_period_index:
        raise ValueError(
            "balancing_state consumed inputs must cover every completed period"
        )
    return {
        "schema_version": "value.zonal-redispatch-runtime-state/v1",
        "next_period_index": next_period_index,
        "consumed_inputs": tuple(normalized),
    }


def _validate_solver_evidence(
    rows: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    year: int,
    period_id_by_index: Mapping[int, str],
) -> dict[int, str]:
    if period_id_by_index and not rows:
        raise ValueError("solver diagnostic rows must cover every completed period")
    seen_periods: list[int] = []
    declared_hash_by_period: dict[int, str] = {}
    for row in rows:
        period = row["period"]
        if row["run_id"] != run_id or row["year"] != year:
            raise ValueError("solver diagnostic row run/year identity does not match")
        if period not in period_id_by_index:
            raise ValueError("solver diagnostic row is foreign or outside chronology")
        if row["period_id"] != period_id_by_index[period]:
            raise ValueError("solver diagnostic row period_id does not match chronology")
        if seen_periods and period < seen_periods[-1]:
            raise ValueError("solver diagnostic rows are not in period chronology")
        seen_periods.append(period)
        declared = _sha256(
            row["declared_input_sha256"],
            f"solver_diagnostic_rows[{period}].declared_input_sha256",
        )
        existing = declared_hash_by_period.setdefault(period, declared)
        if existing != declared:
            raise ValueError("solver diagnostic hashes disagree within a period")
    if set(declared_hash_by_period) != set(period_id_by_index):
        raise ValueError("solver diagnostic rows must cover every completed period")
    return declared_hash_by_period


def _validate_reliability_evidence(
    rows: Sequence[Mapping[str, object]],
    *,
    run_id: str,
    year: int,
    period_id_by_index: Mapping[int, str],
) -> None:
    if len(rows) != len(period_id_by_index):
        raise ValueError("reliability period rows must cover every completed period")
    for expected_period, row in zip(sorted(period_id_by_index), rows):
        if row.get("year") != year or row.get("period") != expected_period:
            raise ValueError("reliability period rows do not match chronology")
        if "run_id" in row and row["run_id"] != run_id:
            raise ValueError("reliability row run identity does not match")
        if (
            "period_id" in row
            and row["period_id"] != period_id_by_index[expected_period]
        ):
            raise ValueError("reliability row period_id does not match chronology")


def _validate_balancing_hashes(
    balancing_state: Mapping[str, object],
    declared_hash_by_period: Mapping[int, str],
) -> None:
    consumed = balancing_state["consumed_inputs"]
    if not isinstance(consumed, tuple):
        raise ValueError("balancing_state consumed_inputs must be normalized")
    for period, declared_hash in declared_hash_by_period.items():
        item = consumed[period]
        if not isinstance(item, Mapping):
            raise ValueError("balancing_state consumed input must be an object")
        if declared_hash != item["input_sha256"]:
            raise ValueError(
                "balancing_state consumed hash does not match solver diagnostics"
            )


def _sum_mapping(
    current: Mapping[str, float], increment: Mapping[str, float]
) -> dict[str, float]:
    return {
        key: math.fsum((float(current.get(key, 0.0)), float(increment.get(key, 0.0))))
        for key in sorted(set(current) | set(increment))
    }


@dataclass(frozen=True)
class StagedPeriodOutcome(JsonContract):
    """Committed one-period increments and post-period runtime snapshots."""

    run_id: str
    year: int
    period_index: int
    summary: Mapping[str, object]
    ahead_result_sha256: str
    balancing_result_sha256: str
    post_period_soc_mwh_by_asset: Mapping[str, float]
    storage_cost_state_by_asset: Mapping[str, Mapping[str, object]]
    balancing_state: Mapping[str, object]
    generation_mwh_by_asset: Mapping[str, float]
    income_gbp_by_owner: Mapping[str, float]
    operating_cost_gbp: float
    operating_cost_gbp_by_class: Mapping[str, float]
    total_blackout_mwh: float
    total_excess_mwh: float
    total_export_mwh: float
    national_settlement_gbp_by_owner: Mapping[str, float]
    redispatch_settlement_gbp_by_owner: Mapping[str, float]
    actual_storage_discharge_mwh_by_asset: Mapping[str, float]
    final_dispatch_mwh_by_physical_asset: Mapping[str, float]
    last_soc_mwh_by_base_asset: Mapping[str, float]
    zonal_account_totals_gbp: Mapping[str, float]
    reliability_period_rows: Sequence[Mapping[str, object]]
    solver_diagnostic_rows: Sequence[Mapping[str, object]]
    schema_version: str = "value.staged-period-outcome/v1"

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_integer(self.year, "year", minimum=1)
        _require_integer(self.period_index, "period_index")
        if self.schema_version != "value.staged-period-outcome/v1":
            raise ValueError("Unsupported staged period outcome schema_version")
        summary = _period_summary(self.summary)
        if summary["year"] != self.year or summary["period"] != self.period_index:
            raise ValueError("summary year/period does not match the outcome")
        object.__setattr__(self, "summary", summary)
        object.__setattr__(
            self, "ahead_result_sha256", _sha256(self.ahead_result_sha256, "ahead_result_sha256")
        )
        object.__setattr__(
            self,
            "balancing_result_sha256",
            _sha256(self.balancing_result_sha256, "balancing_result_sha256"),
        )
        for name in (
            "post_period_soc_mwh_by_asset",
            "generation_mwh_by_asset",
            "income_gbp_by_owner",
            "operating_cost_gbp_by_class",
            "national_settlement_gbp_by_owner",
            "redispatch_settlement_gbp_by_owner",
            "actual_storage_discharge_mwh_by_asset",
            "final_dispatch_mwh_by_physical_asset",
            "last_soc_mwh_by_base_asset",
            "zonal_account_totals_gbp",
        ):
            object.__setattr__(self, name, _numeric_mapping(getattr(self, name), name))
        for name in (
            "operating_cost_gbp",
            "total_blackout_mwh",
            "total_excess_mwh",
            "total_export_mwh",
        ):
            object.__setattr__(self, name, _require_finite(getattr(self, name), name))
        object.__setattr__(
            self,
            "storage_cost_state_by_asset",
            _nested_json_mapping(
                self.storage_cost_state_by_asset, "storage_cost_state_by_asset"
            ),
        )
        balancing_state = _balancing_state(
            self.balancing_state, self.period_index + 1
        )
        object.__setattr__(self, "balancing_state", balancing_state)
        period_id_by_index = {
            self.period_index: str(summary["period_id"]),
        }
        reliability_rows = _json_rows(
            self.reliability_period_rows, "reliability_period_rows"
        )
        _validate_reliability_evidence(
            reliability_rows,
            run_id=self.run_id,
            year=self.year,
            period_id_by_index=period_id_by_index,
        )
        object.__setattr__(
            self,
            "reliability_period_rows",
            reliability_rows,
        )
        solver_rows = _solver_rows(self.solver_diagnostic_rows)
        declared_hashes = _validate_solver_evidence(
            solver_rows,
            run_id=self.run_id,
            year=self.year,
            period_id_by_index=period_id_by_index,
        )
        _validate_balancing_hashes(balancing_state, declared_hashes)
        object.__setattr__(self, "solver_diagnostic_rows", solver_rows)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "StagedPeriodOutcome":
        if not isinstance(payload, Mapping):
            raise ValueError("StagedPeriodOutcome payload must be an object")
        expected = {item.name for item in fields(cls)}
        if set(payload) != expected:
            raise ValueError(f"StagedPeriodOutcome fields must be exactly {sorted(expected)}")
        return cls(**dict(payload))


@dataclass(frozen=True)
class StagedPSMRuntimeState(JsonContract):
    run_id: str
    year: int
    next_period_index: int
    soc_mwh_by_asset: Mapping[str, float]
    storage_cost_state_by_asset: Mapping[str, Mapping[str, object]]
    balancing_state: Mapping[str, object]
    summaries: Sequence[Mapping[str, object]]
    ahead_hashes: Mapping[str, str]
    balancing_hashes: Mapping[str, str]
    generation_mwh_by_asset: Mapping[str, float]
    income_gbp_by_owner: Mapping[str, float]
    operating_cost_gbp: float
    operating_cost_gbp_by_class: Mapping[str, float]
    total_blackout_mwh: float
    total_excess_mwh: float
    total_export_mwh: float
    national_settlement_gbp_by_owner: Mapping[str, float]
    redispatch_settlement_gbp_by_owner: Mapping[str, float]
    actual_storage_discharge_mwh_by_asset: Mapping[str, float]
    final_dispatch_mwh_by_physical_asset: Mapping[str, float]
    last_soc_mwh_by_base_asset: Mapping[str, float]
    zonal_account_totals_gbp: Mapping[str, float]
    reliability_period_rows: Sequence[Mapping[str, object]]
    solver_diagnostic_rows: Sequence[Mapping[str, object]]
    schema_version: str = "value.staged-psm-runtime-state/v1"

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_integer(self.year, "year", minimum=1)
        _require_integer(self.next_period_index, "next_period_index")
        if self.schema_version != "value.staged-psm-runtime-state/v1":
            raise ValueError("Unsupported staged PSM runtime-state schema_version")
        for name in (
            "soc_mwh_by_asset",
            "generation_mwh_by_asset",
            "income_gbp_by_owner",
            "operating_cost_gbp_by_class",
            "national_settlement_gbp_by_owner",
            "redispatch_settlement_gbp_by_owner",
            "actual_storage_discharge_mwh_by_asset",
            "final_dispatch_mwh_by_physical_asset",
            "last_soc_mwh_by_base_asset",
            "zonal_account_totals_gbp",
        ):
            object.__setattr__(self, name, _numeric_mapping(getattr(self, name), name))
        for name in (
            "operating_cost_gbp",
            "total_blackout_mwh",
            "total_excess_mwh",
            "total_export_mwh",
        ):
            object.__setattr__(self, name, _require_finite(getattr(self, name), name))
        object.__setattr__(
            self,
            "storage_cost_state_by_asset",
            _nested_json_mapping(
                self.storage_cost_state_by_asset, "storage_cost_state_by_asset"
            ),
        )
        summaries = tuple(_period_summary(item) for item in self.summaries)
        period_ids = [str(item["period_id"]) for item in summaries]
        if len(period_ids) != len(set(period_ids)):
            raise ValueError("summaries contain a duplicate period_id")
        if [item["period"] for item in summaries] != list(range(self.next_period_index)):
            raise ValueError("summaries must cover every completed period in order")
        if any(item["year"] != self.year for item in summaries):
            raise ValueError("summary year does not match runtime state")
        object.__setattr__(self, "summaries", summaries)
        period_id_by_index = {
            index: period_id for index, period_id in enumerate(period_ids)
        }
        balancing_state = _balancing_state(
            self.balancing_state, self.next_period_index
        )
        object.__setattr__(self, "balancing_state", balancing_state)
        object.__setattr__(self, "ahead_hashes", self._validated_hashes(self.ahead_hashes, period_ids, "ahead_hashes"))
        object.__setattr__(self, "balancing_hashes", self._validated_hashes(self.balancing_hashes, period_ids, "balancing_hashes"))
        reliability_rows = _json_rows(
            self.reliability_period_rows, "reliability_period_rows"
        )
        _validate_reliability_evidence(
            reliability_rows,
            run_id=self.run_id,
            year=self.year,
            period_id_by_index=period_id_by_index,
        )
        object.__setattr__(
            self,
            "reliability_period_rows",
            reliability_rows,
        )
        solver_rows = _solver_rows(self.solver_diagnostic_rows)
        declared_hashes = _validate_solver_evidence(
            solver_rows,
            run_id=self.run_id,
            year=self.year,
            period_id_by_index=period_id_by_index,
        )
        _validate_balancing_hashes(balancing_state, declared_hashes)
        object.__setattr__(self, "solver_diagnostic_rows", solver_rows)

    @staticmethod
    def _validated_hashes(
        value: object, period_ids: Sequence[str], field_name: str
    ) -> dict[str, str]:
        if not isinstance(value, Mapping) or set(value) != set(period_ids):
            raise ValueError(f"{field_name} must contain exactly the completed period IDs")
        return {
            period_id: _sha256(value[period_id], f"{field_name}.{period_id}")
            for period_id in period_ids
        }

    @classmethod
    def initial(
        cls,
        *,
        run_id: str,
        year: int,
        soc_mwh_by_asset: Mapping[str, float],
        storage_cost_state_by_asset: Mapping[str, Mapping[str, object]] | None = None,
        balancing_state: Mapping[str, object] | None = None,
    ) -> "StagedPSMRuntimeState":
        return cls(
            run_id=run_id,
            year=year,
            next_period_index=0,
            soc_mwh_by_asset=soc_mwh_by_asset,
            storage_cost_state_by_asset=storage_cost_state_by_asset or {},
            balancing_state=(
                balancing_state
                if balancing_state is not None
                else {
                    "schema_version": "value.zonal-redispatch-runtime-state/v1",
                    "next_period_index": 0,
                    "consumed_inputs": (),
                }
            ),
            summaries=(),
            ahead_hashes={},
            balancing_hashes={},
            generation_mwh_by_asset={},
            income_gbp_by_owner={},
            operating_cost_gbp=0.0,
            operating_cost_gbp_by_class={},
            total_blackout_mwh=0.0,
            total_excess_mwh=0.0,
            total_export_mwh=0.0,
            national_settlement_gbp_by_owner={},
            redispatch_settlement_gbp_by_owner={},
            actual_storage_discharge_mwh_by_asset={},
            final_dispatch_mwh_by_physical_asset={},
            last_soc_mwh_by_base_asset={},
            zonal_account_totals_gbp={},
            reliability_period_rows=(),
            solver_diagnostic_rows=(),
        )

    def apply_period(self, outcome: StagedPeriodOutcome) -> "StagedPSMRuntimeState":
        if not isinstance(outcome, StagedPeriodOutcome):
            raise TypeError("outcome must be a StagedPeriodOutcome")
        if outcome.run_id != self.run_id:
            raise ValueError("Period outcome run does not match runtime state")
        if outcome.year != self.year:
            raise ValueError("Period outcome year does not match runtime state")
        if outcome.period_index != self.next_period_index:
            raise ValueError("Period outcome is not the next period")
        period_id = str(outcome.summary["period_id"])
        if period_id in {str(item["period_id"]) for item in self.summaries}:
            raise ValueError("Period outcome has a duplicate period_id")
        return StagedPSMRuntimeState(
            run_id=self.run_id,
            year=self.year,
            next_period_index=self.next_period_index + 1,
            soc_mwh_by_asset=outcome.post_period_soc_mwh_by_asset,
            storage_cost_state_by_asset=outcome.storage_cost_state_by_asset,
            balancing_state=outcome.balancing_state,
            summaries=(*self.summaries, outcome.summary),
            ahead_hashes={**self.ahead_hashes, period_id: outcome.ahead_result_sha256},
            balancing_hashes={
                **self.balancing_hashes,
                period_id: outcome.balancing_result_sha256,
            },
            generation_mwh_by_asset=_sum_mapping(
                self.generation_mwh_by_asset, outcome.generation_mwh_by_asset
            ),
            income_gbp_by_owner=_sum_mapping(
                self.income_gbp_by_owner, outcome.income_gbp_by_owner
            ),
            operating_cost_gbp=math.fsum((self.operating_cost_gbp, outcome.operating_cost_gbp)),
            operating_cost_gbp_by_class=_sum_mapping(
                self.operating_cost_gbp_by_class,
                outcome.operating_cost_gbp_by_class,
            ),
            total_blackout_mwh=math.fsum((self.total_blackout_mwh, outcome.total_blackout_mwh)),
            total_excess_mwh=math.fsum((self.total_excess_mwh, outcome.total_excess_mwh)),
            total_export_mwh=math.fsum((self.total_export_mwh, outcome.total_export_mwh)),
            national_settlement_gbp_by_owner=_sum_mapping(
                self.national_settlement_gbp_by_owner,
                outcome.national_settlement_gbp_by_owner,
            ),
            redispatch_settlement_gbp_by_owner=_sum_mapping(
                self.redispatch_settlement_gbp_by_owner,
                outcome.redispatch_settlement_gbp_by_owner,
            ),
            actual_storage_discharge_mwh_by_asset=_sum_mapping(
                self.actual_storage_discharge_mwh_by_asset,
                outcome.actual_storage_discharge_mwh_by_asset,
            ),
            final_dispatch_mwh_by_physical_asset=_sum_mapping(
                self.final_dispatch_mwh_by_physical_asset,
                outcome.final_dispatch_mwh_by_physical_asset,
            ),
            last_soc_mwh_by_base_asset=outcome.last_soc_mwh_by_base_asset,
            zonal_account_totals_gbp=_sum_mapping(
                self.zonal_account_totals_gbp, outcome.zonal_account_totals_gbp
            ),
            reliability_period_rows=(
                *self.reliability_period_rows,
                *outcome.reliability_period_rows,
            ),
            solver_diagnostic_rows=(
                *self.solver_diagnostic_rows,
                *outcome.solver_diagnostic_rows,
            ),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "StagedPSMRuntimeState":
        if not isinstance(payload, Mapping):
            raise ValueError("StagedPSMRuntimeState payload must be an object")
        expected = {item.name for item in fields(cls)}
        if set(payload) != expected:
            raise ValueError(f"StagedPSMRuntimeState fields must be exactly {sorted(expected)}")
        return cls(**dict(payload))
