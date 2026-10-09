"""Single source of truth for run purpose, size and publication policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class RunPolicy:
    mode: str
    label: str
    purpose: str
    periods_per_year: int
    maximum_years: int | None
    annual_economics_candidate: bool
    scientific_baseline_candidate: bool
    requires_declared_clearing_inputs: bool
    required_configured_years: int | None = None

    def years(self, project: Mapping[str, object]) -> tuple[int, int]:
        start = int(project["start_year"])
        configured_end = int(project["end_year"])
        if configured_end < start:
            raise ValueError("The end year cannot be earlier than the start year")
        configured_years = configured_end - start + 1
        if (
            self.required_configured_years is not None
            and configured_years != self.required_configured_years
        ):
            word = "two" if self.required_configured_years == 2 else str(self.required_configured_years)
            raise ValueError(f"{self.label} requires exactly {word} configured years")
        end = configured_end if self.maximum_years is None else min(
            configured_end, start + self.maximum_years - 1
        )
        if self.maximum_years == 2 and end == start:
            raise ValueError(f"{self.label} requires a project covering at least two years")
        return start, end

    def to_dict(self, project: Mapping[str, object]) -> dict[str, object]:
        start, end = self.years(project)
        return {
            **asdict(self),
            "start_year": start,
            "end_year": end,
            "years": end - start + 1,
            "total_periods": (end - start + 1) * self.periods_per_year,
        }


RUN_POLICIES = {
    "smoke": RunPolicy(
        "smoke", "Two-period verification",
        "module wiring and data-interface verification", 2, 1, False, False, False,
    ),
    "two_year_smoke": RunPolicy(
        "two_year_smoke", "Two-year smoke test",
        "cross-year PSM, CEM, planning and state-transition verification",
        2, 2, False, False, False,
    ),
    "validation_24h": RunPolicy(
        "validation_24h", "24-hour clearing validation",
        "independent solver validation of 48 half-hour VALUE periods",
        48, 1, False, False, True,
    ),
    "validation_168h": RunPolicy(
        "validation_168h", "168-hour clearing validation",
        "independent solver validation of 336 half-hour VALUE periods",
        336, 1, False, False, True,
    ),
    "value_101_day": RunPolicy(
        "value_101_day", "One-day market lesson",
        "48-period teaching run through the selected production PSM only",
        48, 1, False, False, False,
    ),
    "two_year": RunPolicy(
        "two_year", "Complete two-year model",
        "full-year PSM/CEM integration and numerical validation",
        17_520, 2, True, True, False,
    ),
    "full": RunPolicy(
        "full", "Complete project", "complete configured scientific study",
        17_520, None, True, True, False,
    ),
}


def validate_pack_run_mode(manifest: Mapping[str, object], mode: str) -> None:
    """Keep shortened teaching data out of annual or scientific run modes."""

    if not bool(manifest.get("teaching_only")):
        return
    allowed = tuple(str(item) for item in manifest.get("allowed_run_modes", ()))
    if mode not in allowed:
        raise ValueError(
            f"Teaching data pack {manifest.get('id') or '<unknown>'} does not allow run mode "
            f"{mode!r}; allowed modes are {', '.join(allowed)}"
        )


def resolve_run_policy(mode: str) -> RunPolicy:
    try:
        return RUN_POLICIES[str(mode)]
    except KeyError as exc:
        raise ValueError("mode must be " + ", ".join(RUN_POLICIES)) from exc


# F-D2 (DECISIONS A16-3): scopes that run the market step only.  The one-day
# lesson returns before the extension runtime exists, so a selected extension
# would be recorded in the Run identity without executing.  Preflight blocks
# that combination; comparison and Inspect treat such recorded extensions as
# not executed.
PSM_ONLY_RUN_MODES = frozenset({"value_101_day"})


def scope_runs_extensions(mode: object) -> bool:
    """True when a run of ``mode`` executes selected extension hooks."""

    return str(mode or "") not in PSM_ONLY_RUN_MODES


def scope_extension_block_message(extension_ids: Sequence[str]) -> str:
    names = ", ".join(str(item) for item in extension_ids)
    return (
        "The one-day lesson runs the market step only, so the selected "
        f"extension(s) {names} would not execute. Choose two-period or a longer "
        "scope, or deselect the extension(s)."
    )
