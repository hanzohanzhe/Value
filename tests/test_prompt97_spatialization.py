from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from gridform_core.asset_economics import build_asset_economic_extensions
from gridform_core.builtin.scheme_c_1000twh.v2_module_definitions import SchemeCPlanningPipelineDefinition
from gridform_core.spatialization import (
    AgentZoneAllocation,
    SpatialSourceRecord,
    attach_spatial_metadata,
    build_agent_zone_allocations,
    build_spatial_fleet,
    convert_bng_to_wgs84,
    rescale_to_national_totals,
    resolve_offshore_landing,
)
from gridform_core.v2.contracts import (
    AssetStateV2,
    PlanningProject,
    ResolvedRun,
    YearState,
)
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.zonal_contracts import ZonalAssetMapping
from gridform_core.weather_spatialization import (
    REPDERA5AggregatedWeather,
    RepresentativePointWeather,
)


ROOT = Path(__file__).resolve().parents[1]


def source(
    source_id: str,
    capacity: float,
    *,
    technology: str = "onshore",
    owner: str = "wind-agent",
    unit: str = "MW",
    zone: str | None = None,
    country: str = "GB",
    kind: str = "economic_asset",
    frozen: dict[str, float] | None = None,
) -> SpatialSourceRecord:
    return SpatialSourceRecord(
        source_id=source_id,
        source_kind=kind,
        economic_owner_id=owner,
        technology=technology,
        capacity_value=capacity,
        capacity_unit=unit,
        country=country,
        zone_id=zone,
        location_method="source_coordinate" if zone else None,
        frozen_zone_shares=frozen or {},
        provenance={"fixture": "prompt97"},
    )


class Prompt97SpatialAllocationTests(unittest.TestCase):
    def test_cross_zone_weights_wind_multiplier_and_exact_national_rescaling(self):
        allocations = build_agent_zone_allocations(
            (source("regional-wind", 3.0, unit="scheme_c_20mw_multiplier"),),
            operational_mw_by_technology_zone={"onshore": {"north": 40.0, "south": 20.0}},
            pipeline_mw_by_technology_zone={"onshore": {"north": 1.0, "south": 99.0}},
            user_weights_by_technology_zone={"onshore": {"north": 0.0, "south": 1.0}},
            pack_revision="rev-a",
        )
        self.assertEqual([(row.zone_id, row.capacity_mw) for row in allocations], [
            ("north", 40.0), ("south", 20.0),
        ])
        self.assertTrue(all(row.capacity_unit_conversion == "3.0 × 20 MW" for row in allocations))
        resized = rescale_to_national_totals(allocations, {"onshore": 90.0})
        self.assertAlmostEqual(sum(row.capacity_mw for row in resized), 90.0, places=12)
        self.assertEqual([row.zone_share for row in resized], [2.0 / 3.0, 1.0 / 3.0])

    def test_frozen_shares_do_not_change_after_endogenous_growth(self):
        record = source(
            "model-growth", 30.0, kind="model_growth",
            frozen={"north": 2.0 / 3.0, "south": 1.0 / 3.0},
        )
        first = build_agent_zone_allocations(
            (record,),
            operational_mw_by_technology_zone={"onshore": {"north": 100.0}},
            pack_revision="rev-a",
        )
        changed_inputs = build_agent_zone_allocations(
            (record,),
            operational_mw_by_technology_zone={"onshore": {"south": 100.0}},
            pack_revision="rev-a",
        )
        self.assertEqual(first, changed_inputs)
        self.assertEqual([row.location_method for row in first], ["frozen_pack_share"] * 2)

    def test_located_project_ni_exclusion_fallback_and_capacity_audit(self):
        records = (
            source("project:located", 10.0, zone="west", kind="repd_project"),
            source("project:ni", 8.0, zone="ni", country="Northern Ireland", kind="repd_project"),
            source("aggregate", 2.0, technology="solar", owner="solar-agent"),
        )
        fleet = build_spatial_fleet(
            records,
            operational_mw_by_technology_zone={},
            pack_revision="rev-b",
            england_fallback_zone_id="ENGLAND_FALLBACK",
        )
        self.assertEqual(fleet.excluded_northern_ireland_asset_ids, ("project:ni",))
        self.assertEqual(fleet.fallback_asset_ids, ("aggregate",))
        self.assertTrue(fleet.material_spatial_fallback_by_technology["solar"])
        self.assertEqual(fleet.source_capacity_mw_by_technology, {"onshore": 10.0, "solar": 2.0})
        self.assertEqual(fleet.mapped_capacity_mw_by_technology, {"onshore": 10.0, "solar": 2.0})
        located = next(row for row in fleet.allocations if row.source_id == "project:located")
        self.assertEqual((located.zone_id, located.zone_share), ("west", 1.0))

    def test_bng_conversion_retains_raw_coordinate_and_crs_provenance(self):
        converted = convert_bng_to_wgs84(530000.0, 180000.0)
        self.assertAlmostEqual(converted.latitude, 51.50399, places=3)
        self.assertAlmostEqual(converted.longitude, -0.12835, places=3)
        self.assertEqual(converted.source_crs, "EPSG:27700")
        self.assertEqual(converted.target_crs, "EPSG:4326")
        self.assertEqual((converted.raw_easting, converted.raw_northing), (530000.0, 180000.0))
        self.assertTrue(converted.transformation_pipeline)

    def test_offshore_actual_override_then_nearest_coast_then_fallback(self):
        actual = resolve_offshore_landing(
            "offshore-a", 54.0, 1.0,
            landing_overrides={"offshore-a": {"zone_id": "east", "source": "project_connection_record"}},
            coast_points=({"zone_id": "north", "latitude": 55.0, "longitude": -1.0},),
        )
        self.assertEqual((actual.zone_id, actual.method, actual.actual_connection), (
            "east", "actual_landfall_override", True,
        ))
        inferred = resolve_offshore_landing(
            "offshore-b", 54.9, -1.1, landing_overrides={},
            coast_points=(
                {"zone_id": "north", "latitude": 55.0, "longitude": -1.0},
                {"zone_id": "south", "latitude": 51.0, "longitude": 1.0},
            ),
        )
        self.assertEqual((inferred.zone_id, inferred.method, inferred.actual_connection), (
            "north", "inferred_nearest_coast_dso", False,
        ))
        fallback = resolve_offshore_landing(
            "offshore-c", None, None, landing_overrides={}, coast_points=(),
        )
        self.assertEqual((fallback.zone_id, fallback.method), (
            "ENGLAND_FALLBACK", "unlocated_england_fallback",
        ))


class Prompt97WeatherAndCEMTests(unittest.TestCase):
    def allocations(self) -> tuple[AgentZoneAllocation, ...]:
        return build_agent_zone_allocations(
            (
                source("wind-1", 20.0, zone="north"),
                source("wind-2", 10.0, zone="north"),
                source("wind-3", 15.0, zone="south"),
            ),
            pack_revision="rev-weather",
        )

    def test_representative_weather_copies_trace_and_bounds_profile_count(self):
        result = RepresentativePointWeather.build(
            self.allocations(),
            period_ids=("p0", "p1", "p2"),
            profiles_by_agent_technology={"wind-agent|onshore": (0.1, 0.4, 0.7)},
            source_sha256="a" * 64,
        )
        self.assertEqual(len(result.profiles), 2)
        self.assertEqual({row.availability for row in result.profiles}, {(0.1, 0.4, 0.7)})
        self.assertEqual(result.mode, "representative_point")

    def test_repd_era5_weather_aggregates_mw_weighted_profiles_offline(self):
        result = REPDERA5AggregatedWeather.build(
            self.allocations(),
            period_ids=("p0", "p1"),
            profiles_by_source={
                "wind-1": (0.2, 0.8),
                "wind-2": (0.8, 0.2),
                "wind-3": (0.5, 0.5),
            },
            source_sha256="b" * 64,
        )
        north = next(row for row in result.profiles if row.zone_id == "north")
        self.assertEqual(north.availability, (0.4, 0.6))
        self.assertEqual(north.aggregated_capacity_mw, 30.0)
        self.assertEqual(len(result.profiles), 2)
        self.assertFalse(result.runtime_opens_repd_or_era5)

    def test_spatial_metadata_survives_project_commissioning(self):
        economics = build_asset_economic_extensions(
            "onshore", 12.0,
            energy_capacity_mwh=None,
            capital_costs_per_mw={"onshore": 1_000_000.0},
            lifetimes={"onshore": 25.0},
            discount_rate=0.05,
            source_record_id="project:located",
        )
        project = PlanningProject(
            "project:located", "Located project", "repd", "onshore", 12.0, 12.0,
            "North East", "awaiting construction", "active", 2024, 2025,
            "expected_capacity", 1.0,
            extensions=economics,
        )
        state = YearState(
            2025,
            (AssetStateV2("agent", "onshore", 30.0, region="North East"),),
            (project,),
        )
        mappings = (
            AgentZoneAllocation(
                "alloc-agent-north", "wind-owner", "onshore", "agent",
                "economic_asset", "north", 20.0, 2.0 / 3.0,
                "operational_mw_weight", "rev-cem", "MW", "direct MW",
            ),
            AgentZoneAllocation(
                "alloc-agent-south", "wind-owner", "onshore", "agent",
                "economic_asset", "south", 10.0, 1.0 / 3.0,
                "operational_mw_weight", "rev-cem", "MW", "direct MW",
            ),
            AgentZoneAllocation(
                "alloc-project", "wind-owner", "onshore", "project:located",
                "repd_project", "north", 12.0, 1.0,
                "source_coordinate", "rev-cem", "MW", "direct MW",
            ),
        )
        spatial = attach_spatial_metadata(state, mappings)
        shares = spatial.assets[0].extensions["frozen_zone_shares"]
        self.assertEqual(shares, {"north": 2.0 / 3.0, "south": 1.0 / 3.0})
        self.assertEqual(spatial.planning_projects[0].extensions["zone_id"], "north")
        run = ResolvedRun("run", "project", "scenario", "pack", 2025, 2025, {}, {}, {})
        advanced = SchemeCPlanningPipelineDefinition().advance_year(run, spatial)
        commissioned = next(row for row in advanced.operating_state.assets if row.asset_id.startswith("commissioned:"))
        self.assertEqual(commissioned.extensions["zone_id"], "north")
        self.assertEqual(commissioned.extensions["spatial_pack_revision"], "rev-cem")

    def test_new_commissioned_child_can_use_its_inherited_owner_mapping(self):
        child = AssetStateV2(
            "commissioned:model:1", "onshore", 30.0, region="GB",
            extensions={"investment_owner_id": "wind-owner"},
        )
        state = YearState(2026, (child,), ())
        from gridform_core.spatialization import allocations_for_state

        rows = allocations_for_state(
            state,
            (
                ZonalAssetMapping("wind-owner", "north", "generator", "onshore", 2 / 3, "frozen_owner_share"),
                ZonalAssetMapping("wind-owner", "south", "generator", "onshore", 1 / 3, "frozen_owner_share"),
            ),
            pack_revision="rev-owner",
        )
        self.assertEqual([(row.source_id, row.zone_id, row.capacity_mw) for row in rows], [
            ("commissioned:model:1", "north", 20.0),
            ("commissioned:model:1", "south", 10.0),
        ])
        self.assertTrue(all(row.provenance["mapping_identity"] == "wind-owner" for row in rows))

    def test_weather_preprocessors_are_optional_interchangeable_modules(self):
        registry = workspace_registry(ROOT / "missing-local-modules")
        representative = registry.manifest(
            "value-representative-point-weather", expected_slot="weather_spatializer"
        )
        aggregated = registry.manifest(
            "value-repd-era5-aggregated-weather", expected_slot="weather_spatializer"
        )
        self.assertFalse(representative.selection_required)
        self.assertFalse(aggregated.selection_required)
        self.assertEqual(representative.outputs, aggregated.outputs)
        self.assertIn("value.zonal-availability-profile/v1", representative.outputs)


if __name__ == "__main__":
    unittest.main()
