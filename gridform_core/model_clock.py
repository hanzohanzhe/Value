"""The model clock: how a period index maps to a time (four-role test S-中1).

Every chronological input is put on one clock before a Run reads it
(``series_reader.align_clock``): half-hour periods in UTC on a fixed
365-day year.  A leap-year source loses 29 February; there is no daylight
saving (``weather_demand_ensembles.normalize_half_hour_year``: "VALUE uses UTC
internally"; ``solar_irradiance.period_clock``: day 1..365, UTC hours).  A
local-time source (a mapped CSV declared Europe/London) is converted to UTC
row by row when it is mapped.

Rule (one rule for the ledger metadata, the read models, the UI and the
exports): period ``p`` of model year ``Y`` starts at 00:00 UTC of model day
``p // periods_per_day`` of ``Y`` (29 February is never a model day) plus
``(p % periods_per_day) x period length``.  Times are written ISO 8601 with
``Z`` and labelled UTC.

Ledgers written before this rule carry ``timezone: Europe/London`` and
``calendar: fixed_365_day_local_periods``; that label was wrong (the clock
was always UTC).  Readers report such a ledger on the UTC clock and say that
the stored label was corrected.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from typing import Mapping

MODEL_CLOCK_TIMEZONE = "UTC"
MODEL_CALENDAR = "fixed_365_day_utc_periods"
MODEL_DAYS_PER_YEAR = 365
LEGACY_LEDGER_CLOCK = {"timezone": "Europe/London", "calendar": "fixed_365_day_local_periods"}
MODEL_CLOCK_RULE = (
    "Half-hour periods in UTC on a fixed 365-day year: period p of model year Y starts at 00:00 UTC "
    "of model day p // periods_per_day (29 February is never a model day) plus the period's offset "
    "within the day. No daylight saving."
)
LEGACY_LABEL_NOTE = (
    "This ledger was written with the label Europe/London; the model clock was UTC. "
    "Times are shown on the UTC clock."
)


def ledger_clock_metadata() -> dict[str, str]:
    """The clock fields every market ledger records (semantic metadata)."""

    return {"timezone": MODEL_CLOCK_TIMEZONE, "calendar": MODEL_CALENDAR}


def is_legacy_clock_label(semantic: Mapping[str, object]) -> bool:
    return (
        str(semantic.get("timezone") or "") == LEGACY_LEDGER_CLOCK["timezone"]
        and str(semantic.get("calendar") or LEGACY_LEDGER_CLOCK["calendar"]) == LEGACY_LEDGER_CLOCK["calendar"]
    )


def ledger_clock(semantic: Mapping[str, object]) -> dict[str, object]:
    """The clock of a ledger as the read models report it.

    A ledger without clock fields, or with the legacy label, is reported on
    the UTC clock; ``clock_label_corrected`` says when a stored label was
    replaced.
    """

    corrected = is_legacy_clock_label(semantic)
    stored = str(semantic.get("timezone") or "")
    if stored and stored != MODEL_CLOCK_TIMEZONE and not corrected:
        # An unknown label is passed through unchanged: it is not ours to fix.
        return {
            "timezone": stored,
            "calendar": str(semantic.get("calendar") or MODEL_CALENDAR),
            "clock_rule": MODEL_CLOCK_RULE,
            "clock_label_corrected": False,
        }
    result: dict[str, object] = {
        "timezone": MODEL_CLOCK_TIMEZONE,
        "calendar": MODEL_CALENDAR,
        "clock_rule": MODEL_CLOCK_RULE,
        "clock_label_corrected": corrected,
    }
    if corrected:
        result["clock_note"] = LEGACY_LABEL_NOTE
    return result


def _periods_per_day(period_hours: float) -> int:
    value = round(24.0 / float(period_hours))
    if value <= 0 or abs(value * float(period_hours) - 24.0) > 1e-9:
        raise ValueError(f"period length {period_hours} h does not divide a day")
    return int(value)


def model_day(year: int, day_index: int) -> datetime:
    """00:00 UTC of model day ``day_index`` (0-based) of ``year``; 29 February is skipped."""

    start = datetime(int(year), 1, 1, tzinfo=timezone.utc)
    date = start + timedelta(days=int(day_index))
    if calendar.isleap(int(year)) and date >= datetime(int(year), 2, 29, tzinfo=timezone.utc):
        date += timedelta(days=1)
    return date


def period_start_utc(year: int, period: int, period_hours: float = 0.5) -> datetime:
    """The UTC start of ``period`` of model year ``year`` (``period`` may equal the year's length: the end)."""

    per_day = _periods_per_day(period_hours)
    day_index, offset = divmod(int(period), per_day)
    return model_day(year, day_index) + timedelta(hours=offset * float(period_hours))


def period_start_iso(year: int, period: int, period_hours: float = 0.5) -> str:
    """ISO 8601 UTC with ``Z``: ``2025-07-01T16:00:00Z``."""

    return period_start_utc(year, period, period_hours).strftime("%Y-%m-%dT%H:%M:%SZ")
