"""Constructed year-boundary tests, not a simulated annual dispatch claim."""
from dataclasses import replace
import unittest

from gridform_core.builtin.scheme_c_1000twh.doctoral_market import DoctoralPeriodEngine
from gridform_core.builtin.scheme_c_1000twh.doctoral_state import StorageBatch
from test_doctoral_period_engine import assets


class AnnualEngineTransitionTests(unittest.TestCase):
    def fixture(self):
        generators, batteries = assets()
        engine = DoctoralPeriodEngine(generators, batteries, year=2025)
        # Explicitly constructed closing state to test only the boundary API.
        memory = {key: dict(row) for key, row in engine.state.generator_memory.items()}
        memory["gas"]["real_gen_energy"], memory["gas"]["run_time"] = 40, 8760
        engine.state = replace(engine.state, next_period_index=17520, next_absolute_period=17520,
            storage_batches={"store": (StorageBatch(17518, 20),)}, generator_memory=memory)
        return engine, generators, batteries

    def advance(self, engine, generators, batteries, year=2026):
        self.assertTrue(callable(getattr(engine, "advance_year", None)),
                        "validated engine-to-engine year transition is missing")
        return engine.advance_year(generators, batteries, year=year)

    def test_batches_and_generator_memory_continue_without_rewriting_snapshot_identity(self):
        before, generators, batteries = self.fixture()
        snapshot = before.export_state()
        after = self.advance(before, generators, batteries)
        self.assertEqual(after.state.year, 2026)
        self.assertEqual(after.state.next_period_index, 0)
        self.assertEqual(after.state.next_absolute_period, 17520)
        self.assertEqual(after.state.batch_age(after.state.storage_batches["store"][0]), 2)
        self.assertEqual(after.state.generator_memory["gas"]["real_gen_energy"], 40)
        self.assertEqual(after.state.generator_memory["gas"]["run_time"], 8760)
        self.assertNotEqual(after.input_sha256, before.input_sha256)
        restored = DoctoralPeriodEngine(generators, batteries, year=2026, checkpoint=after.export_state())
        result = after.realise_period(after.plan_period(80, available_mw_by_vre={"wind": 0}), 80)
        replay = restored.realise_period(restored.plan_period(80, available_mw_by_vre={"wind": 0}), 80)
        self.assertEqual(result.to_dict(), replay.to_dict())
        self.assertEqual(before.export_state(), snapshot)

    def test_partial_and_skipped_years_are_rejected(self):
        engine, generators, batteries = self.fixture()
        with self.assertRaisesRegex(ValueError, "year"):
            self.advance(engine, generators, batteries, 2027)
        engine.state = replace(engine.state, next_period_index=17519)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.advance(engine, generators, batteries)

    def test_retirement_and_shrink_cannot_silently_erase_inventory(self):
        engine, generators, batteries = self.fixture()
        with self.assertRaisesRegex(ValueError, "disposition"):
            self.advance(engine, generators, [])
        batteries[0].pool_limit = 10
        with self.assertRaisesRegex(ValueError, "disposition"):
            self.advance(engine, generators, batteries)

    def test_new_assets_start_empty_but_surviving_memory_is_not_reset(self):
        engine, generators, batteries = self.fixture()
        new_generators, new_batteries = assets()
        new_generators[1].name, new_batteries[0].name = "new_gas", "new_storage"
        result = self.advance(engine, generators + [new_generators[1]], batteries + new_batteries)
        self.assertEqual(result.state.storage_batches["new_storage"], ())
        self.assertEqual(result.state.generator_memory["new_gas"]["run_time"], 0)
        self.assertEqual(result.state.generator_memory["gas"]["run_time"], 8760)

    def test_disk_annual_boundary_uses_a_trusted_parent_hash_not_edited_input_identity(self):
        from gridform_core.builtin.scheme_c_1000twh.doctoral_market import _hash
        engine, generators, batteries = self.fixture()
        fn = getattr(DoctoralPeriodEngine, "from_prior_year_snapshot", None)
        self.assertTrue(callable(fn), "disk annual continuation API is missing")
        snapshot = engine.export_state()
        result = fn(generators, batteries, year=2026, prior_snapshot=snapshot,
                    expected_prior_snapshot_sha256=_hash(snapshot))
        self.assertEqual(result.export_state(), self.advance(engine, generators, batteries).export_state())
        with self.assertRaisesRegex(ValueError, "hash"):
            fn(generators, batteries, year=2026, prior_snapshot=snapshot,
               expected_prior_snapshot_sha256="f" * 64)


if __name__ == "__main__":
    unittest.main()
