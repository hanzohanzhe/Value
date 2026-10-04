"""Apply pipeline completions and cap agent proposals by technology."""

from __future__ import annotations

from dataclasses import replace

from ...contracts import AssetState, CapacityDecision, ModelState, YearContext


class SchemeCStateTransition:
    id = "scheme-c-state-transition"

    def apply(self, context: YearContext, state: ModelState, decisions: tuple[CapacityDecision, ...]) -> ModelState:
        investment = next((item for item in decisions if item.module_id == "agent-investment"), None)
        pipeline = next((item for item in decisions if item.module_id == "planning-pipeline"), None)
        vre_cap = next((item for item in decisions if item.module_id == "vre-expansion-cap"), None)
        storage_cap = next((item for item in decisions if item.module_id == "storage-expansion-scheme-c"), None)
        assets = {asset.id: asset for asset in state.assets}

        # Investment proposals become projects in the planning module. Only
        # pipeline completions are commissioned in the next state.
        completed = dict(pipeline.additions_mw) if pipeline else {}
        completed_projects = [
            dict(project) for project in state.planning_pipeline
            if int(project.get("completion_year", 9999)) == context.year + 1
        ]
        spatial_by_key: dict[str, dict[str, object]] = {}
        for project in completed_projects:
            key = str(project.get("asset_id") or project.get("technology"))
            metadata = {
                name: project[name]
                for name in ("zone_id", "frozen_zone_shares", "spatial_pack_revision")
                if project.get(name) not in (None, {}, "")
            }
            if not metadata:
                continue
            previous = spatial_by_key.get(key)
            if previous is not None and previous != metadata:
                raise ValueError(
                    f"Completed legacy projects for {key} mix incompatible spatial metadata"
                )
            spatial_by_key[key] = metadata
        by_tech: dict[str, list[tuple[str, float]]] = {}
        for key, amount in completed.items():
            tech = assets[key].technology if key in assets else key
            by_tech.setdefault(tech, []).append((key, float(amount)))

        caps = {}
        if vre_cap:
            caps.update(vre_cap.additions_mw)
        if storage_cap:
            caps.update(storage_cap.additions_mw)
        allowed_by_asset = {}
        for tech, rows in by_tech.items():
            total = sum(amount for _, amount in rows)
            allowed = min(total, float(caps.get(tech, total)))
            scale = allowed / total if total > 0 else 0.0
            for key, amount in rows:
                allowed_by_asset[key] = amount * scale

        next_assets = []
        for asset in state.assets:
            retirement = float(investment.retirements_mw.get(asset.id, 0.0)) if investment else 0.0
            addition = allowed_by_asset.get(asset.id, 0.0)
            next_assets.append(replace(asset, capacity_mw=max(0.0, asset.capacity_mw - retirement + addition)))

        # External REPD projects can complete to a technology without an exact
        # agent id. Preserve them as explicit aggregate assets.
        for key, addition in allowed_by_asset.items():
            if key in assets or addition <= 0:
                continue
            aggregate_id = f"pipeline_{key}"
            existing = next((asset for asset in next_assets if asset.id == aggregate_id), None)
            if existing:
                next_assets = [
                    replace(
                        asset,
                        capacity_mw=asset.capacity_mw + addition,
                        attributes={**dict(asset.attributes), **spatial_by_key.get(key, {})},
                    ) if asset.id == aggregate_id else asset
                    for asset in next_assets
                ]
            else:
                next_assets.append(AssetState(
                    id=aggregate_id,
                    technology=key,
                    capacity_mw=addition,
                    attributes={
                        "source": "planning_pipeline",
                        **spatial_by_key.get(key, {}),
                    },
                ))

        metrics = dict(state.cumulative_metrics)
        metrics["completed_capacity_mw"] = metrics.get("completed_capacity_mw", 0.0) + sum(allowed_by_asset.values())
        return ModelState(
            year=context.year + 1,
            assets=tuple(next_assets),
            planning_pipeline=tuple(pipeline.pipeline_projects if pipeline else state.planning_pipeline),
            cumulative_metrics=metrics,
        )
