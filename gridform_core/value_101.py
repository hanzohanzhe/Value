"""Canonical VALUE 101 descriptors built from ordinary VALUE Study contracts."""

from __future__ import annotations

from copy import deepcopy

from .value_101_lifecycle import value_101_origin


VALUE_101_TUTORIAL_ID = "value-101"
VALUE_101_BASELINE_PACK_ID = "value-101-baseline-v1"
VALUE_101_NETWORK_PACK_ID = "value-101-network-v1"
VALUE_101_BASELINE_STUDY_ID = "value-101-baseline"
VALUE_101_PACK_IDS = (VALUE_101_BASELINE_PACK_ID,)


_VALUE_101_STUDY: dict[str, object] = {
    "schema_version": "value.project/v1",
    "id": VALUE_101_BASELINE_STUDY_ID,
    "name": "VALUE 101 baseline",
    "data_pack_id": VALUE_101_BASELINE_PACK_ID,
    "start_year": 2025,
    "end_year": 2026,
    "modules": {
        "psm": "value-bid-at-cost-psm",
        "storage_cost": "dynamic-annual-storage-cost",
        "investment": "agent-investment",
        "pipeline": "planning-pipeline",
        "vre_cap": "vre-expansion-cap",
        "storage_cap": "value-storage-expansion-policy",
        "transition": "value-annual-state-transition",
    },
    "purpose": "VALUE 101 synthetic annual teaching model",
    "selected_extensions": [],
    "extension_parameters": {},
    "maturity_acknowledgements": {},
    "parameters": {"planning.defer_spread_years": 0},
    "runtime_options": {
        "runtime.market_trace_level": "summary",
        "runtime.checkpoint_enabled": True,
    },
    "extensions": {
        "value_101": value_101_origin(
            variant_kind="baseline",
            parent_project_id=None,
            changed_dimensions=(),
        )
    },
}


def value_101_study() -> dict[str, object]:
    """Return a fresh VALUE 101 draft for the ordinary Study composer."""

    return deepcopy(_VALUE_101_STUDY)


def value_101_descriptor(*, installed_pack_ids: set[str]) -> dict[str, object]:
    """Describe the guided course without creating a second execution route."""

    packs = [
        {"pack_id": pack_id, "installed": pack_id in installed_pack_ids}
        for pack_id in VALUE_101_PACK_IDS
    ]
    return {
        "schema_version": "value.tutorial/v1",
        "id": VALUE_101_TUTORIAL_ID,
        "name": "VALUE 101 — a synthetic GB-style teaching system",
        "summary": (
            "Use one annual synthetic data pack to learn market clearing, then run "
            "the complete two-year VALUE PSM-CEM chain and inspect its evidence."
        ),
        "run_modes": {
            "one_day": "value_101_day",
            "complete_two_year": "two_year",
        },
        "study": value_101_study(),
        "pack_ids": list(VALUE_101_PACK_IDS),
        "concepts": [
            {"id": "data", "label": "Data", "plain_language": "Demand, weather, fleet, costs and planning records supplied to a Study."},
            {"id": "study", "label": "Study", "plain_language": "A saved combination of years, one data pack and selected model modules."},
            {"id": "modules", "label": "Modules", "plain_language": "Replaceable implementations of clearing, storage pricing, investment, planning and transition steps."},
            {"id": "run", "label": "Run", "plain_language": "An immutable execution of one saved Study revision."},
            {"id": "evidence", "label": "Results", "plain_language": "Dispatch, bids, storage, unused VRE, cost, carbon and planning artifacts written by the model."},
        ],
        "availability": {
            "packs": packs,
            "all_packs_installed": all(row["installed"] for row in packs),
            "corrective_action": (
                None
                if all(row["installed"] for row in packs)
                # M-D9: a source checkout has no installer run; name its command too.
                else "Run the standard VALUE installer to add the bundled VALUE 101 packs. In a source "
                "checkout, run python scripts/install_synthetic_pack.py --value-101-only from the "
                "repository root (with VALUE_DATA_HOME set to this instance's data folder), then reload."
            ),
            "optional_network_pack": {
                "pack_id": VALUE_101_NETWORK_PACK_ID,
                "installed": VALUE_101_NETWORK_PACK_ID in installed_pack_ids,
                "required_for_core_course": False,
            },
        },
        "scientific_boundary": {
            "label": "Synthetic annual model: not evidence about Great Britain",
            "country": "SYNTHETIC",
            "timezone": "UTC",
            "teaching_only": True,
            "period_hours": 0.5,
            "one_day_periods": 48,
            "periods_per_year": 17_520,
            "years": 2,
            "annual_economics_eligible": True,
            "scientific_baseline_eligible": False,
            "excluded_claims": [
                "Great Britain annual system cost",
                "national capacity pathway",
                "real network or hydrology result",
            ],
        },
    }
