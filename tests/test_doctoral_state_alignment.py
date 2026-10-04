"""Physical state tests; these call the candidate, not a table of expected results."""

import json
import unittest
from dataclasses import replace

from gridform_core.v2.contracts import AssetStateV2, YearState


class DoctoralStateTests(unittest.TestCase):
    def api(self):
        from gridform_core.builtin.scheme_c_1000twh import doctoral_state
        return doctoral_state

    def initial(self):
        state = YearState(2025, (
            AssetStateV2("store", "1c_battery", 25, 100),
            AssetStateV2("gas", "CCGT", 100),
        ), ())
        return self.api().initialise_doctoral_state(state)

    def test_initial_storage_is_empty_not_half_capacity(self):
        state = self.initial()
        self.assertEqual(state.storage_energy_mwh("store"), 0)
        self.assertEqual(state.next_absolute_period, 0)

    def test_missing_later_year_state_is_not_silently_reinitialised(self):
        with self.assertRaisesRegex(ValueError, "missing.*physical state"):
            self.api().initialise_doctoral_state(YearState(2028, (), ()))

    def test_incomplete_generator_memory_cannot_resume_advanced_fleet(self):
        api = self.api()
        raw = api.DoctoralRuntimeState(2025, 3, 3, {}, {}, {}, ("ghost",)).to_dict()
        state = YearState(2025, (AssetStateV2("gas", "CCGT", 100),), (),
                          extensions={api.PHYSICAL_STATE_KEY: raw})
        with self.assertRaisesRegex(ValueError, "generator|identity"):
            api.initialise_doctoral_state(state)

    def test_batch_roundtrip_retains_age_and_energy(self):
        api = self.api()
        state = self.initial().commit_period(
            storage_batches={"store": (api.StorageBatch(0, 10),)},
            generator_memory={}, accepted_generator_ids=(),
        )
        decoded = api.DoctoralRuntimeState.from_dict(json.loads(json.dumps(state.to_dict())))
        self.assertEqual(decoded.to_dict(), state.to_dict())
        self.assertEqual(decoded.storage_energy_mwh("store"), 10)
        self.assertEqual(decoded.batch_age(decoded.storage_batches["store"][0]), 1)

    def test_cross_year_preserves_batches_and_advances_clock(self):
        api = self.api()
        # Synthetic state immediately before the year boundary; this does not
        # claim that the preceding 17519 periods were replayed.
        state = replace(self.initial(), next_period_index=17519, next_absolute_period=17519).commit_period(
            storage_batches={"store": (api.StorageBatch(0, 10),)},
            generator_memory={}, accepted_generator_ids=("gas",),
        )
        next_state = state.start_year(2026, storage_capacities_mwh={"store": 100})
        self.assertEqual(next_state.storage_energy_mwh("store"), 10)
        self.assertEqual(next_state.next_period_index, 0)
        self.assertEqual(next_state.next_absolute_period, 17520)
        self.assertEqual(next_state.accepted_generator_ids, ())  # source annual reset
        next_state = next_state.commit_period(
            storage_batches=next_state.storage_batches,
            generator_memory={}, accepted_generator_ids=(),
        )
        self.assertEqual(next_state.batch_age(next_state.storage_batches["store"][0]), 17521)

    def test_partial_year_cannot_be_relabelled_as_completed_year(self):
        with self.assertRaisesRegex(ValueError, "complete|17520"):
            self.initial().start_year(2026, storage_capacities_mwh={"store": 100})

    def test_year_end_cannot_commit_period_17520(self):
        from dataclasses import replace
        state = replace(self.initial(), next_period_index=17520, next_absolute_period=17520)
        with self.assertRaisesRegex(ValueError, "complete|17520"):
            state.commit_period(storage_batches={"store": ()}, generator_memory={}, accepted_generator_ids=())

    def test_decay_matches_raw_source_and_does_not_modify_previous_state(self):
        from tests.doctoral_reference_harness import load_reference_symbols
        api = self.api()
        for technology, raw_kind in (("1c_battery", "1c"), ("pumped_hydro", "pumped_hydro"),
                                     ("hydrogen_battery", "hydrogen")):
            with self.subTest(technology=technology):
                original = {0: 200.0}  # 200 source MW-period units = 100 MWh
                reference = load_reference_symbols(["decay_func"])
                reference["decay_func"](original, raw_kind)
                batch = api.StorageBatch(0, 100)
                result = api.decay_batches((batch,), technology)
                self.assertAlmostEqual(result[0].stored_energy_mwh, original[0] * 0.5, places=10)
                self.assertEqual(batch.stored_energy_mwh, 100)

    def test_age_tariff_uses_absolute_clock(self):
        api = self.api()
        batch = api.StorageBatch(10, 1)
        self.assertAlmostEqual(api.batch_bid_price(batch, 13, storage_fee=2, per_storage_fee=0.1,
                                             bid_multiplier=1.5), 3.45)
        with self.assertRaisesRegex(ValueError, "future"):
            api.batch_bid_price(batch, 9, storage_fee=2, per_storage_fee=0.1)

    def test_expansion_does_not_create_charge_and_contraction_never_clips(self):
        api = self.api()
        state = replace(self.initial(), next_period_index=17519, next_absolute_period=17519).commit_period(
            storage_batches={"store": (api.StorageBatch(0, 10),)},
            generator_memory={}, accepted_generator_ids=(),
        )
        grown = state.start_year(2026, storage_capacities_mwh={"store": 200, "new": 40})
        self.assertEqual(grown.storage_energy_mwh("store"), 10)
        self.assertEqual(grown.storage_energy_mwh("new"), 0)
        with self.assertRaisesRegex(ValueError, "disposition"):
            state.start_year(2026, storage_capacities_mwh={"store": 5})
        with self.assertRaisesRegex(ValueError, "disposition"):
            state.start_year(2026, storage_capacities_mwh={})

    def test_runtime_export_rejects_incomplete_or_non_finite_state(self):
        api = self.api()
        payload = self.initial().to_dict()
        del payload["storage_batches"]
        with self.assertRaises(ValueError):
            api.DoctoralRuntimeState.from_dict(payload)
        for value in (-1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                api.StorageBatch(0, value)

    def test_generator_carry_and_source_unit_roundtrip(self):
        api = self.api()
        memory = {"gas": {"kind": "GasGenerator", "real_gen_energy": 35.0,
                           "run_time": 4.5, "if_curtail": False}}
        state = replace(self.initial(), next_period_index=17519, next_absolute_period=17519).commit_period(storage_batches={"store": ()},
                                             generator_memory=memory, accepted_generator_ids=("gas",))
        moved = state.start_year(2026, storage_capacities_mwh={"store": 100})
        self.assertEqual(moved.generator_memory, memory)
        batches = api.batches_from_source({17: 20}, period_hours=0.5)
        self.assertEqual(batches[0].stored_energy_mwh, 10)
        self.assertEqual(api.batches_to_source(batches, period_hours=0.5), {17: 20})

    def test_future_batch_duplicate_clock_and_unknown_storage_rejected(self):
        api = self.api()
        state = self.initial()
        for batches in ({"store": (api.StorageBatch(1, 5),)},
                        {"other": ()},
                        {"store": (api.StorageBatch(0, 5), api.StorageBatch(0, 3))}):
            with self.subTest(batches=batches), self.assertRaises(ValueError):
                state.commit_period(storage_batches=batches, generator_memory={}, accepted_generator_ids=())


if __name__ == "__main__":
    unittest.main()
