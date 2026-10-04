"""REPD and model-investment planning pipeline with stable MD5 decisions."""

from __future__ import annotations

import hashlib
import math
from typing import Any

from ...contracts import CapacityDecision, ModelState, PSMResult, YearContext


def stable_draw(project_key: str) -> float:
    digest = hashlib.md5(project_key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return int(digest[:12], 16) / float(16**12 - 1)


class SchemeCPlanningPipeline:
    id = "planning-pipeline"
    version = "1000twh-md5-2026.07.19"
    order = 20

    def decide(self, context: YearContext, state: ModelState, psm_result: PSMResult, previous_decisions):
        del psm_result
        investment = next((decision for decision in previous_decisions if decision.module_id == "agent-investment"), None)
        timelines = context.parameters.get("development_timelines_months", {})
        success_rates = context.parameters.get("planning_success_rates", {})
        pipeline: list[dict[str, Any]] = [dict(project) for project in state.planning_pipeline]

        if investment:
            assets = {asset.id: asset for asset in state.assets}
            for asset_id, capacity_mw in investment.additions_mw.items():
                asset = assets.get(asset_id)
                if not asset or capacity_mw <= 0:
                    continue
                tech = asset.technology
                project_id = f"model:{context.scenario_id}:{context.year}:{asset_id}"
                region = str(asset.attributes.get("region", "GB"))
                rate = float(success_rates.get(f"{tech}:{region}", success_rates.get(tech, 1.0)))
                if stable_draw(project_id) > rate:
                    continue
                months = float(timelines.get(tech, 12.0))
                completion_year = context.year + max(1, math.ceil(months / 12.0))
                pipeline.append({
                    "project_id": project_id,
                    "source": "model_investment",
                    "asset_id": asset_id,
                    "technology": tech,
                    "region": region,
                    "capacity_mw": float(capacity_mw),
                    "decision_year": context.year,
                    "completion_year": completion_year,
                    "success_rate": rate,
                    "frozen_zone_shares": dict(
                        asset.attributes.get("frozen_zone_shares") or {}
                    ),
                    "spatial_pack_revision": asset.attributes.get("spatial_pack_revision"),
                })

        completing = [project for project in pipeline if int(project.get("completion_year", 9999)) == context.year + 1]
        remaining = [project for project in pipeline if int(project.get("completion_year", 9999)) > context.year + 1]
        additions = {}
        for project in completing:
            key = str(project.get("asset_id") or project.get("technology"))
            additions[key] = additions.get(key, 0.0) + float(project.get("capacity_mw", 0.0))
        return CapacityDecision(
            module_id=self.id,
            additions_mw=additions,
            pipeline_projects=tuple(remaining),
            evidence={
                "pipeline_total": float(len(pipeline)),
                "projects_completing_next_year": float(len(completing)),
            },
        )
