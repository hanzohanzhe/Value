"""Immutable run-lineage helpers for explicit physics changes."""

from __future__ import annotations

from copy import deepcopy
from typing import Mapping


def copperplate_rerun_project(
    source: Mapping[str, object], *, parent_run_id: str
) -> tuple[dict[str, object], dict[str, object]]:
    """Clone a failed zonal Study for a new copperplate run.

    This function never mutates the source Study.  Revision identities are
    removed because the changed balancing physics must receive a new snapshot
    identity before the worker starts.
    """

    project = deepcopy(dict(source))
    modules = dict(project.get("modules") or {})
    if modules.get("psm") != "value-staged-bid-at-cost-psm":
        raise ValueError("Only a staged VALUE run can be rerun as copperplate")
    if modules.get("balancing") != "value-zonal-redispatch-balancing":
        raise ValueError("The parent run did not select zonal redispatch")
    modules["balancing"] = "value-copperplate-balancing"
    project["modules"] = modules
    configured = dict(project.get("market_configuration") or {})
    configured.update({
        "ahead_market_module_id": "value-staged-bid-at-cost-psm",
        "balancing_module_id": "value-copperplate-balancing",
        "network_pack_id": "",
        "zonal_demand_mode": "",
    })
    project["market_configuration"] = configured
    for key in (
        "revision_sha256", "revision_number", "parent_revision_sha256",
        "change_summary", "module_resolution_graph",
    ):
        project.pop(key, None)
    lineage = {
        "schema_version": "value.run-comparison-lineage/v1",
        "comparison_parent_run_id": str(parent_run_id),
        "relationship": "explicit_rerun_as_copperplate",
        "source_run_immutable": True,
        "automatic_fallback_used": False,
        "changed_physics": {
            "from_balancing_module_id": "value-zonal-redispatch-balancing",
            "to_balancing_module_id": "value-copperplate-balancing",
        },
    }
    return project, lineage
