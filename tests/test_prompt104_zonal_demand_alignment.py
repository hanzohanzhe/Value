from __future__ import annotations

import importlib
import unittest

from gridform_core.zonal_contracts import ZonalDemand


def alignment_module():
    try:
        return importlib.import_module("gridform_core.zonal_demand_alignment")
    except ModuleNotFoundError as exc:
        raise AssertionError("the zonal demand alignment contract is missing") from exc


class ZonalDemandAlignmentTests(unittest.TestCase):
    def test_scenario_mode_applies_network_shares_to_research_national_demand(self) -> None:
        module = alignment_module()
        network = ZonalDemand(
            ("p0", "p1"),
            {"north": (30.0, 20.0), "south": (70.0, 80.0)},
            (100.0, 100.0),
        )

        aligned = module.align_zonal_demand(
            mode="scenario_scaled_zonal_shares",
            period_ids=("p0", "p1"),
            research_real_mwh=(120.0, 200.0),
            research_forecast_mwh=(108.0, 220.0),
            network_demand=network,
        )

        self.assertEqual(aligned.real_demand_mwh, (120.0, 200.0))
        self.assertEqual(aligned.forecast_demand_mwh, (108.0, 220.0))
        self.assertEqual(
            dict(aligned.demand_mwh_by_zone),
            {"north": (36.0, 40.0), "south": (84.0, 160.0)},
        )
        self.assertEqual(tuple(row.scale_factor for row in aligned.rows), (1.2, 2.0))
        self.assertLessEqual(
            max(abs(row.conservation_residual_mwh) for row in aligned.rows),
            1e-12,
        )
        self.assertEqual(
            dict(aligned.summary),
            {
                "mode": "scenario_scaled_zonal_shares",
                "period_count": 2,
                "research_real_demand_mwh": 320.0,
                "network_national_demand_mwh": 200.0,
                "aligned_national_demand_mwh": 320.0,
                "minimum_scale_factor": 1.2,
                "maximum_scale_factor": 2.0,
                "mean_scale_factor": 1.6,
                "maximum_absolute_conservation_residual_mwh": 0.0,
            },
        )

    def test_bounded_run_selects_exact_period_ids_from_a_full_network_clock(self) -> None:
        module = alignment_module()
        network = ZonalDemand(
            ("p0", "p1", "p2"),
            {
                "north": (30.0, 40.0, 90.0),
                "south": (70.0, 160.0, 210.0),
            },
            (100.0, 200.0, 300.0),
        )

        aligned = module.align_zonal_demand(
            mode="scenario_scaled_zonal_shares",
            period_ids=("p0", "p1"),
            research_real_mwh=(120.0, 100.0),
            research_forecast_mwh=(108.0, 110.0),
            network_demand=network,
        )

        self.assertEqual(aligned.period_ids, ("p0", "p1"))
        self.assertEqual(
            dict(aligned.demand_mwh_by_zone),
            {"north": (36.0, 20.0), "south": (84.0, 80.0)},
        )
        self.assertEqual(aligned.summary["network_national_demand_mwh"], 300.0)

    def test_absolute_mode_uses_network_actual_and_preserves_base_forecast_error_ratio(self) -> None:
        module = alignment_module()
        network = ZonalDemand(
            ("p0", "p1"),
            {"north": (30.0, 40.0), "south": (70.0, 160.0)},
            (100.0, 200.0),
        )

        aligned = module.align_zonal_demand(
            mode="network_pack_absolute_demand",
            period_ids=("p0", "p1"),
            research_real_mwh=(80.0, 100.0),
            research_forecast_mwh=(72.0, 110.0),
            network_demand=network,
        )

        self.assertEqual(aligned.real_demand_mwh, (100.0, 200.0))
        self.assertEqual(aligned.forecast_demand_mwh, (90.0, 220.0))
        self.assertEqual(
            dict(aligned.demand_mwh_by_zone),
            {"north": (30.0, 40.0), "south": (70.0, 160.0)},
        )
        self.assertEqual(tuple(row.scale_factor for row in aligned.rows), (1.0, 1.0))

    def test_scenario_mode_refuses_positive_research_demand_without_network_weights(self) -> None:
        module = alignment_module()
        network = ZonalDemand(
            ("p0",), {"north": (0.0,), "south": (0.0,)}, (0.0,)
        )

        with self.assertRaisesRegex(ValueError, "zero national demand"):
            module.align_zonal_demand(
                mode="scenario_scaled_zonal_shares",
                period_ids=("p0",),
                research_real_mwh=(10.0,),
                research_forecast_mwh=(10.0,),
                network_demand=network,
            )

    def test_absolute_mode_refuses_an_undefined_base_forecast_ratio(self) -> None:
        module = alignment_module()
        network = ZonalDemand(("p0",), {"gb": (10.0,)}, (10.0,))

        with self.assertRaisesRegex(ValueError, "forecast-to-real ratio"):
            module.align_zonal_demand(
                mode="network_pack_absolute_demand",
                period_ids=("p0",),
                research_real_mwh=(0.0,),
                research_forecast_mwh=(1.0,),
                network_demand=network,
            )

    def test_alignment_refuses_duplicate_or_misaligned_period_ids(self) -> None:
        module = alignment_module()
        duplicate = ZonalDemand(
            ("p0", "p0"), {"gb": (1.0, 1.0)}, (1.0, 1.0)
        )
        with self.assertRaisesRegex(ValueError, "unique periods"):
            module.align_zonal_demand(
                mode="scenario_scaled_zonal_shares",
                period_ids=("p0", "p0"),
                research_real_mwh=(1.0, 1.0),
                research_forecast_mwh=(1.0, 1.0),
                network_demand=duplicate,
            )

        shifted = ZonalDemand(("p1",), {"gb": (1.0,)}, (1.0,))
        with self.assertRaisesRegex(ValueError, "period IDs"):
            module.align_zonal_demand(
                mode="scenario_scaled_zonal_shares",
                period_ids=("p0",),
                research_real_mwh=(1.0,),
                research_forecast_mwh=(1.0,),
                network_demand=shifted,
            )

    def test_alignment_refuses_invalid_research_demand_values(self) -> None:
        module = alignment_module()
        network = ZonalDemand(("p0",), {"gb": (1.0,)}, (1.0,))
        for real, forecast in ((-1.0, 1.0), (1.0, float("nan"))):
            with self.subTest(real=real, forecast=forecast):
                with self.assertRaisesRegex(ValueError, "finite and non-negative"):
                    module.align_zonal_demand(
                        mode="scenario_scaled_zonal_shares",
                        period_ids=("p0",),
                        research_real_mwh=(real,),
                        research_forecast_mwh=(forecast,),
                        network_demand=network,
                    )


if __name__ == "__main__":
    unittest.main()
