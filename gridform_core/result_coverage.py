"""One rule for "is this an annual result?" (P0-9 S5; F3-02, G1-10).

Every read model that shows annual totals (network annual brief, result
queries, run summaries, VRE summaries) asks this module instead of keeping
its own set of modes.  The verdict is computed from the Run's recorded
status and the period boundaries actually present in its ledger, in a fixed
priority order:

1. ``non_annual``   the Run's policy clears fewer than 17,520 periods a year
                    (smoke, two_year_smoke, validation_24h/168h, value_101_day);
2. ``in_progress``  the Run has not finished;
3. ``partial``      the Run was cancelled or failed before covering its years;
4. ``invalid``      the observed year set differs from the Run's declared years;
5. ``partial``      some year does not cover periods 0..17519 exactly once;
6. ``complete``     every declared year is fully covered.

The reason codes are stable API values.  Result queries return the precise
code in ``reason_code`` and the older wording (``ANNUAL_REASON_ALIASES``, e.g.
``annual_evidence_withheld_for_nonannual_run``) in ``legacy_reason_code``.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from .run_policy import RUN_POLICIES

COVERAGE_SCHEMA = "value.result-coverage/v1"
ANNUAL_PERIODS = 17_520
ACTIVE_RUN_STATES = frozenset({"queued", "snapshotting", "running", "cancel_requested"})
# Derived from the run policies: every mode whose year is shorter than a full
# chronology, plus the historical "tutorial" mode of pre-0.6 runs.
NON_ANNUAL_MODES = frozenset(
    mode for mode, policy in RUN_POLICIES.items() if policy.periods_per_year != ANNUAL_PERIODS
) | {"tutorial"}

STATUSES = ("complete", "partial", "non_annual", "in_progress", "invalid")

REASON_NON_ANNUAL = "annual_evidence_withheld_for_nonannual_run"
REASON_IN_PROGRESS = "run_in_progress"
REASON_CANCELLED = "run_cancelled_before_full_coverage"
REASON_FAILED = "run_failed_before_full_coverage"
REASON_YEAR_SET = "annual_year_set_mismatch"
REASON_BOUNDARY = "annual_period_boundary_incomplete"
REASON_COMPLETE = "annual_coverage_complete"

# Older wording used by result queries for the same verdicts.
ANNUAL_REASON_ALIASES = {
    REASON_NON_ANNUAL: REASON_NON_ANNUAL,
    REASON_IN_PROGRESS: "immutable_completed_run_required",
    REASON_CANCELLED: REASON_NON_ANNUAL,
    REASON_FAILED: REASON_NON_ANNUAL,
    REASON_YEAR_SET: "vre_curtailment_annual_year_set_invalid",
    REASON_BOUNDARY: REASON_NON_ANNUAL,
}

YearBounds = Mapping[int, tuple[int, int, int]]  # year -> (first period, last period, distinct periods)


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def is_non_annual(status: Mapping[str, object]) -> bool:
    """True when the Run's mode or policy cannot produce a full annual chronology."""

    mode = str(status.get("mode") or "")
    policy = status.get("run_policy")
    periods = _int(policy.get("periods_per_year")) if isinstance(policy, Mapping) else None
    if mode in NON_ANNUAL_MODES:
        return True
    if periods is not None:
        return periods != ANNUAL_PERIODS
    return mode not in RUN_POLICIES  # unknown mode without a policy: not provably annual


def expected_years(status: Mapping[str, object]) -> tuple[int, ...]:
    policy = status.get("run_policy")
    if not isinstance(policy, Mapping):
        return ()
    start, end = _int(policy.get("start_year")), _int(policy.get("end_year"))
    if start is None or end is None or end < start or end - start >= 200:
        return ()
    return tuple(range(start, end + 1))


def _year_complete(bounds: tuple[int, int, int]) -> bool:
    first, last, count = bounds
    return first == 0 and last == ANNUAL_PERIODS - 1 and count == ANNUAL_PERIODS


def stopped_reason(status: Mapping[str, object]) -> str | None:
    """``run_cancelled_before_full_coverage`` / ``run_failed_before_full_coverage``
    for a stopped Run (an archived Run is judged by the status it was archived
    from), else None."""

    run_status = str(status.get("status") or "")
    if run_status == "archived":
        run_status = str(status.get("archived_from_status") or "completed")
    return {"cancelled": REASON_CANCELLED, "failed": REASON_FAILED}.get(run_status)


def result_coverage(status: Mapping[str, object], year_bounds: YearBounds) -> dict[str, object]:
    """The annual-coverage verdict of one Run (see the module docstring)."""

    run_status = str(status.get("status") or "")
    if run_status == "archived":
        run_status = str(status.get("archived_from_status") or "completed")
    declared = expected_years(status)
    observed = tuple(sorted(int(year) for year in year_bounds))
    covered = sum(min(int(bounds[2]), ANNUAL_PERIODS) for bounds in year_bounds.values())
    denominator = (len(declared) or len(observed)) * ANNUAL_PERIODS
    fraction = (covered / denominator) if denominator else None
    years = [
        {
            "year": year,
            "first_period": int(year_bounds[year][0]),
            "last_period": int(year_bounds[year][1]),
            "period_count": int(year_bounds[year][2]),
            "coverage_fraction": min(int(year_bounds[year][2]), ANNUAL_PERIODS) / ANNUAL_PERIODS,
            "complete": _year_complete(year_bounds[year]),
        }
        for year in observed
    ]

    def verdict(annual_status: str, reason: str) -> dict[str, object]:
        return {
            "schema_version": COVERAGE_SCHEMA,
            "annual_status": annual_status,
            "reason_code": reason,
            "coverage_fraction": fraction,
            "coverage_percent": None if fraction is None else round(fraction * 100, 1),
            "expected_years": list(declared),
            "observed_years": list(observed),
            "periods_per_year": ANNUAL_PERIODS,
            "years": years,
        }

    if is_non_annual(status):
        return verdict("non_annual", REASON_NON_ANNUAL)
    if run_status in ACTIVE_RUN_STATES:
        return verdict("in_progress", REASON_IN_PROGRESS)
    all_complete = bool(years) and all(item["complete"] for item in years)
    stopped = stopped_reason(status)
    if stopped is not None:
        # A stopped Run is never published as annual, even if its years look whole.
        return verdict("partial", stopped)
    if declared and set(observed) != set(declared):
        return verdict("invalid", REASON_YEAR_SET)
    if not all_complete:
        return verdict("partial", REASON_BOUNDARY)
    return verdict("complete", REASON_COMPLETE)


def year_bounds_from_rows(rows: Iterable[Iterable[object]]) -> dict[int, tuple[int, int, int]]:
    """``{year: (first, last, count)}`` from ``SELECT year, MIN(period), MAX(period), COUNT(DISTINCT period)`` rows."""

    result: dict[int, tuple[int, int, int]] = {}
    for year, first, last, count in rows:  # type: ignore[misc]
        result[int(year)] = (int(first), int(last), int(count))
    return result


def legacy_reason(coverage: Mapping[str, object]) -> str:
    """The result-query reason code of a non-complete verdict."""

    reason = str(coverage.get("reason_code"))
    return ANNUAL_REASON_ALIASES.get(reason, reason)
