from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import shapefile
from openpyxl import Workbook

from gridform_core.data_workbench.official_gb_candidate import (
    build_candidate_zones,
    build_weather_bundles,
    bounded_availability,
    compile_postcode_demand_weights,
    compile_network_candidate_payload,
    normalize_interconnector_register,
    normalize_dso_source,
    normalize_scheme_c_national_demand,
    normalize_repd_source,
    normalize_scheme_c_fleet,
    solar_availability,
    wind_availability,
    read_etys_2025_capabilities,
    read_etys_boundary_geometry,
)


def _dso_source() -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::27700"}},
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "ID": 10,
                    "Name": "_A",
                    "DNO": "UKPN",
                    "Area": "East England",
                    "DNO_Full": "UK Power Networks",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]],
                },
            }
        ],
    }


class OfficialGbCandidateTests(unittest.TestCase):
    def test_real_dso_fields_are_normalized_without_losing_source_identity(self) -> None:
        result = normalize_dso_source(_dso_source(), source_crs="EPSG:27700")
        feature = result["display_geojson"]["features"][0]
        self.assertEqual(feature["properties"]["zone_id"], "dso-east-england")
        self.assertEqual(feature["properties"]["dso_owner"], "UK Power Networks")
        self.assertEqual(feature["properties"]["nation"], "England")
        self.assertEqual(feature["properties"]["source_feature_id"], "10")
        self.assertEqual(result["source_crs"], "EPSG:27700")

    def test_embedded_dso_overlap_is_resolved_by_preserving_the_smaller_area(self) -> None:
        source = _dso_source()
        source["features"].append(
            {
                "type": "Feature",
                "properties": {
                    "ID": 11,
                    "Name": "_C",
                    "DNO": "UKPN",
                    "Area": "London",
                    "DNO_Full": "UK Power Networks",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[25, 25], [75, 25], [75, 75], [25, 75], [25, 25]]],
                },
            }
        )

        result = normalize_dso_source(source, source_crs="EPSG:27700")

        geometries = {
            item["properties"]["zone_id"]: item["geometry"]
            for item in result["display_geojson"]["features"]
        }
        from shapely.geometry import shape

        self.assertEqual(shape(geometries["dso-london"]).area > 0, True)
        self.assertAlmostEqual(
            shape(geometries["dso-london"]).intersection(
                shape(geometries["dso-east-england"])
            ).area,
            0.0,
        )
        self.assertEqual(result["overlap_resolution"][0]["preserved_zone_id"], "dso-london")

    def test_real_etys_wide_workbook_is_normalized_and_symmetric_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "etys.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "ETYS 2025 Chart Data"
            sheet.append(["Boundary", "Scenario", "Category", 2025, 2030])
            sheet.append(["B6", "Holistic Transition", "Capability", 6700, 8000])
            sheet.append(["B6", "Electric Engagement", "Capability", 6700, 8100])
            sheet.append(["B6", "Hydrogen Evolution", "Capability", 6700, 8200])
            sheet.append(["B7a", "Holistic Transition", "Requirement", 4000, 5000])
            workbook.save(path)

            result = read_etys_2025_capabilities(path)

        self.assertEqual(len(result["boundaries"]), 1)
        boundary = result["boundaries"][0]
        self.assertEqual(boundary["boundary_id"], "B6")
        self.assertEqual(boundary["forward_limit_mw"], 6700.0)
        self.assertEqual(boundary["reverse_limit_mw"], 6700.0)
        self.assertEqual(boundary["reverse_limit_method"], "assumed_symmetric_from_forward")
        self.assertEqual(boundary["scenario_values"], {
            "Electric Engagement": 6700.0,
            "Holistic Transition": 6700.0,
            "Hydrogen Evolution": 6700.0,
        })

    def test_conflicting_same_year_etys_scenarios_stop_the_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "etys.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "ETYS 2025 Chart Data"
            sheet.append(["Boundary", "Scenario", "Category", 2025])
            sheet.append(["B6", "A", "Capability", 6700])
            sheet.append(["B6", "B", "Capability", 6800])
            workbook.save(path)
            with self.assertRaisesRegex(ValueError, "conflicting 2025 capability"):
                read_etys_2025_capabilities(path)

    def test_etys_shapefile_zip_is_read_with_declared_crs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "boundaries"
            writer = shapefile.Writer(str(base), shapeType=shapefile.POLYLINE)
            writer.field("Boundary_n", "C")
            writer.field("ID", "C")
            writer.line([[[0, 50], [100, 50]]])
            writer.record("B6", "BND006")
            writer.close()
            (root / "boundaries.prj").write_text("EPSG:27700", encoding="utf-8")
            archive = root / "boundaries.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                for suffix in ("shp", "shx", "dbf", "prj"):
                    handle.write(root / f"boundaries.{suffix}", f"boundaries.{suffix}")
            result = read_etys_boundary_geometry(archive, source_crs="EPSG:27700")

        self.assertEqual(result["features"][0]["properties"]["boundary_id"], "B6")
        self.assertEqual(result["features"][0]["properties"]["source_feature_id"], "BND006")

    def test_selected_etys_cut_splits_a_dso_and_preserves_parent_identity(self) -> None:
        dso = normalize_dso_source(_dso_source(), source_crs="EPSG:27700")
        boundary = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"boundary_id": "B6", "source_feature_id": "BND006"},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-7.557211138333587, 49.76725482658933], [-7.55582906241822, 49.767321314976996]],
                    },
                }
            ],
        }
        # The synthetic line above is the EPSG:4326 transform of y=50 across the
        # 100 m fixture. It must create two deterministic child zones.
        result = build_candidate_zones(
            dso["display_geojson"],
            boundary,
            selected_boundary_ids=("B6",),
            minimum_piece_share=0.001,
        )
        children = result["zone_geojson"]["features"]
        self.assertEqual(len(children), 2)
        self.assertEqual(
            {item["properties"]["dso_parent_zone_id"] for item in children},
            {"dso-east-england"},
        )
        self.assertEqual(result["selected_boundary_ids"], ["B6"])
        self.assertAlmostEqual(sum(item["properties"]["parent_area_share"] for item in children), 1.0)

    def test_postcode_consumption_and_ons_directory_compile_measured_weights(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            consumption = root / "consumption.csv"
            consumption.write_text(
                "Outcode,Postcode,Num_meters,Total_cons_kwh,Mean_cons_kwh,Median_cons_kwh\n"
                "AA1,All postcodes,2,3000,1500,1500\n"
                "AA1,AA1 1AA,1,1000,1000,1000\n"
                "BB1,BB1 1BB,1,2000,2000,2000\n"
                "NI1,BT1 1AA,1,500,500,500\n",
                encoding="utf-8",
            )
            onspd = root / "onspd.zip"
            with zipfile.ZipFile(onspd, "w") as archive:
                archive.writestr(
                    "Data/multi_csv/ONSPD_TEST_UK_1.csv",
                    "pcds,doterm,ctry25cd,long,lat\n"
                    "AA1 1AA,,E92000001,0.25,0.5\n"
                    "BB1 1BB,,W92000004,1.25,0.5\n"
                    "BT1 1AA,,N92000002,0.25,0.5\n",
                )
            zones = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"zone_id": "west"},
                        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"zone_id": "east"},
                        "geometry": {"type": "Polygon", "coordinates": [[[1, 0], [2, 0], [2, 1], [1, 1], [1, 0]]]},
                    },
                ],
            }

            result = compile_postcode_demand_weights(consumption, onspd, zones)

        self.assertEqual(result["weights"], {"east": 2 / 3, "west": 1 / 3})
        self.assertEqual(result["reconciliation"]["source_individual_postcode_mwh"], 3.5)
        self.assertEqual(result["reconciliation"]["included_gb_mwh"], 3.0)
        self.assertEqual(result["reconciliation"]["excluded_non_gb_mwh"], 0.5)
        self.assertEqual(result["coverage"]["aggregate_rows_excluded"], 1)

    def test_scheme_c_national_demand_uses_nd_and_half_hour_energy_units(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "demand.csv"
            path.write_text(
                "SETTLEMENT_DATE,SETTLEMENT_PERIOD,ND,TSD\n"
                "01-JAN-2022,1,20000,21000\n"
                "01-JAN-2022,2,22000,23000\n",
                encoding="utf-8",
            )
            result = normalize_scheme_c_national_demand(path)

        self.assertEqual(result[0], {
            "period_id": "2022-01-01:01",
            "national_demand_mwh": 10000.0,
        })
        self.assertEqual(result[1]["national_demand_mwh"], 11000.0)

    def test_scheme_c_fleet_keeps_agents_and_converts_wind_multipliers_to_mw(self) -> None:
        zones = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"zone_id": "east", "dso_parent_zone_id": "east"},
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 50], [2, 50], [2, 53], [0, 53], [0, 50]]]},
                },
                {
                    "type": "Feature",
                    "properties": {"zone_id": "ENGLAND_FALLBACK", "dso_parent_zone_id": "ENGLAND_FALLBACK"},
                    "geometry": None,
                },
            ],
        }
        generators = {
            "CCGT": {"capacity_limit": 1000},
            "solar_Ipswich": {"capacity_multiplier": 120},
            "onshore_Ipswich": {"capacity_multiplier": 4},
            "offshore1": {"capacity_multiplier": 5},
        }
        batteries = {"1c_battery": {"per_pool_limit": 50, "pool_limit": 100, "battery_type": "1c"}}
        locations = {
            "Ipswich": {"lat": 52.05, "lon": 1.15},
            "offshore1": {"lat": 52.0, "lon": 2.5},
        }

        result = normalize_scheme_c_fleet(
            zones,
            generators=generators,
            batteries=batteries,
            locations=locations,
        )

        by_id = {row["asset_id"]: row for row in result["rows"]}
        self.assertEqual(by_id["onshore_Ipswich"]["capacity_mw"], 80.0)
        self.assertEqual(by_id["offshore1"]["capacity_mw"], 100.0)
        self.assertEqual(by_id["CCGT"]["zone_id"], "ENGLAND_FALLBACK")
        self.assertEqual(by_id["1c_battery"]["asset_class"], "storage")
        self.assertEqual(by_id["offshore1"]["mapping_method"], "inferred_nearest_coast_dso")

    def test_repd_normalizer_uses_stable_ids_status_and_bng_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "repd.csv"
            source.write_text(
                "Ref ID,Site Name,Technology Type,Installed Capacity (MWelec),Development Status (short),Country,Region,X-coordinate,Y-coordinate\n"
                "1,Sun,Solar Photovoltaics,10,Operational,England,East,500000,200000\n"
                "2,Wind,Wind Onshore,20,Under Construction,Scotland,North,300000,700000\n"
                "3,Other,Anaerobic Digestion,5,Operational,England,East,500000,200000\n",
                encoding="utf-8",
            )
            result = normalize_repd_source(source)

        self.assertEqual([row["asset_id"] for row in result["rows"]], ["repd:1", "repd:2"])
        self.assertEqual(result["rows"][0]["technology"], "solar")
        self.assertEqual(result["rows"][0]["status"], "operational")
        self.assertIsInstance(result["rows"][0]["longitude"], float)
        self.assertEqual(result["excluded_by_reason"], {"technology_outside_prompt98_scope": 1})

    def test_network_payload_adds_visible_unconstrained_fallback_without_signing(self) -> None:
        zones = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "zone_id": "north", "dso_parent_zone_id": "north",
                        "display_name": "North", "dso_owner": "N", "nation": "Scotland",
                        "geometry_feature_id": "north",
                    },
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 1], [1, 1], [1, 2], [0, 2], [0, 1]]]},
                },
                {
                    "type": "Feature",
                    "properties": {
                        "zone_id": "south", "dso_parent_zone_id": "south",
                        "display_name": "South", "dso_owner": "S", "nation": "England",
                        "geometry_feature_id": "south",
                    },
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
                },
            ],
        }
        proposals = [{
            "boundary_id": "B6",
            "positive_zone_ids": ["north"],
            "negative_zone_ids": ["south"],
        }]
        capabilities = {"B6": {"forward_limit_mw": 6700.0}}

        result = compile_network_candidate_payload(zones, proposals, capabilities)

        self.assertEqual(result["etys_payload"]["unconstrained_zone_ids"], ["ENGLAND_FALLBACK"])
        self.assertEqual(result["etys_payload"]["boundaries"][0]["forward_limit_mw"], 6700.0)
        self.assertNotIn("reverse_limit_mw", result["etys_payload"]["boundaries"][0])
        self.assertEqual(result["review"]["owner_signoff"], "pending")
        self.assertEqual(result["review"]["provisional_mapping_approval"], "builder_only")

    def test_weather_conversion_matches_copied_scheme_c_curves(self) -> None:
        self.assertEqual(solar_availability([0, 3600, 7_200_000, 36_000_001]), [0.0, 0.0, 2.0, 0.0])
        # Values above one are rejected when building the bundle; this pure
        # conversion test preserves the copied VALUE irradiance equation.
        onshore = wind_availability([0, 3, 9.7, 25.1], technology="onshore")
        offshore = wind_availability([0, 3, 10.5, 30.1], technology="offshore")
        self.assertEqual(onshore[0], 0.0)
        self.assertEqual(onshore[1], 0.0)
        self.assertEqual(onshore[2], 1.0)
        self.assertEqual(onshore[3], 0.0)
        self.assertEqual(offshore, [0.0, 0.0, 1.0, 0.0])
        self.assertEqual(bounded_availability([0.0, 1.0 + 5e-13]), [0.0, 1.0])
        with self.assertRaisesRegex(ValueError, "materially outside"):
            bounded_availability([1.0001])

    def test_weather_builder_writes_both_modes_on_the_accepted_half_hour_clock(self) -> None:
        import numpy as np
        import xarray as xr

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wind = root / "wind.nc"
            solar = root / "solar.nc"
            xr.Dataset(
                {"wind_speed": (("latitude", "longitude", "dayofyear", "hour"), np.array([[[[3.0, 9.7]]]]))},
                coords={"latitude": [52.0], "longitude": [1.0], "dayofyear": [1], "hour": [0, 1]},
            ).to_netcdf(wind)
            xr.Dataset(
                {"ssrd": (("latitude", "longitude", "dayofyear", "hour"), np.array([[[[0.0, 3_600_000.0]]]]))},
                coords={"latitude": [52.0], "longitude": [1.0], "dayofyear": [1], "hour": [0, 1]},
            ).to_netcdf(solar)
            fleet = [
                {"asset_id": "solar-a", "technology": "solar", "capacity_mw": 10.0, "status": "operating", "zone_id": "east", "latitude": 52.0, "longitude": 1.0},
                {"asset_id": "wind-a", "technology": "onshore", "capacity_mw": 20.0, "status": "operating", "zone_id": "east", "latitude": 52.0, "longitude": 1.0},
            ]
            repd = [
                {"asset_id": "repd:s", "technology": "solar", "capacity_mw": 5.0, "status": "operational", "latitude": 52.0, "longitude": 1.0},
                {"asset_id": "repd:w", "technology": "onshore", "capacity_mw": 10.0, "status": "operational", "latitude": 52.0, "longitude": 1.0},
            ]
            zones = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {"zone_id": "east"},
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 51], [2, 51], [2, 53], [0, 53], [0, 51]]]},
                }],
            }

            result = build_weather_bundles(
                fleet, repd, zones,
                wind_nc=wind,
                solar_nc=solar,
                period_ids=("p0", "p1", "p2", "p3"),
            )

        representative = result["representative"]
        aggregated = result["aggregated"]
        self.assertEqual(representative["mode"], "representative_point")
        self.assertEqual(aggregated["mode"], "repd_era5_mw_aggregated")
        self.assertEqual(len(representative["profiles"]), 2)
        self.assertEqual(representative["profiles"][0]["period_ids"], ["p0", "p1", "p2", "p3"])
        self.assertEqual(
            sorted(row["aggregated_capacity_mw"] for row in aggregated["profiles"]),
            [10.0, 20.0],
        )
        self.assertEqual(result["fallback_groups"], [])

    def test_interconnector_register_keeps_latest_built_stage_and_scheme_c_countries(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "interconnectors.csv"
            source.write_text(
                "Project Name,Connection Site,Stage,MW Import - Current,MW Export - Current,Project Status,MW Effective From\n"
                "Auchencrosh (interconnector CCT) *,Auchencrosh 275kV,1,270,500,Built,2022-04-01\n"
                "Auchencrosh (interconnector CCT) *,Auchencrosh 275kV,2,475,500,Built,2022-08-01\n"
                "Britned,Grain 400kV Substation,,1200,1200,Built,\n"
                "Viking Link Denmark Interconnector,Bicker Fen 400kV Substation,,1500,1500,Built,\n"
                "Future,Unknown,,0,0,Scoping,2030-01-01\n",
                encoding="utf-8",
            )
            zones = {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"zone_id": "scotland"}, "geometry": {"type": "Polygon", "coordinates": [[[-6, 54], [-2, 54], [-2, 57], [-6, 57], [-6, 54]]]}},
                    {"type": "Feature", "properties": {"zone_id": "south-east"}, "geometry": {"type": "Polygon", "coordinates": [[[0, 50], [2, 50], [2, 53], [0, 53], [0, 50]]]}},
                ],
            }
            result = normalize_interconnector_register(source, zones)

        self.assertEqual([row["counterparty_country"] for row in result["rows"]], ["Ireland", "Netherlands"])
        self.assertEqual(result["rows"][0]["import_capacity_mw"], 475.0)
        self.assertEqual(result["rows"][0]["export_capacity_mw"], 500.0)
        self.assertEqual(result["excluded_by_reason"], {
            "not_built": 1,
            "outside_scheme_c_country_profile_scope": 1,
        })


if __name__ == "__main__":
    unittest.main()
