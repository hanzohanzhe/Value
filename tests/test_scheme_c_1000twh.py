import unittest
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

from gridform_core.errors import DeprecatedRouteError


PACK = Path(__file__).resolve().parents[1] / ".gridform" / "data-packs" / "value-uk-1000twh-reproduction"
HAS_RUNTIME_DEPS = all(importlib.util.find_spec(name) is not None for name in ("numpy", "pandas", "xarray"))


@unittest.skipUnless((PACK / "manifest.json").exists(), "local verified data pack not installed")
@unittest.skipUnless(sys.version_info >= (3, 10), "VALUE requires Python 3.10")
@unittest.skipUnless(HAS_RUNTIME_DEPS, "optional VALUE scientific runtime is not installed")
class SchemeCParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from gridform_core.canonical_psm_data import native_initial_state

        cls.state = native_initial_state(PACK, 2025)

    def test_initial_state_matches_verified_scheme_c_batch(self):
        totals = defaultdict(float)
        for asset in self.state.assets:
            totals[asset.technology] += asset.capacity_mw
        # The canonical v2 state has one row per executable fleet asset.  The
        # retired v1 factory emitted three additional aggregate placeholders.
        self.assertEqual(len(self.state.assets), 50)
        # v2 retains every normalized planning record so rejected/deferred
        # projects remain auditable; the v1 factory discarded them up front.
        self.assertEqual(len(self.state.planning_projects), 7372)
        self.assertAlmostEqual(totals["solar"], 10066.98, places=2)
        self.assertAlmostEqual(totals["onshore"], 14711.65, places=2)
        self.assertAlmostEqual(totals["offshore"], 14679.00, places=2)
        self.assertAlmostEqual(totals["0.25c_battery"], 299.98416468725264, places=6)
        self.assertAlmostEqual(totals["0.5c_battery"], 2465.869833729216, places=6)
        self.assertAlmostEqual(totals["1c_battery"], 74.99604117181316, places=6)
        self.assertAlmostEqual(totals["pumped_hydro"], 2828.0, places=6)

    def test_old_factory_fails_with_actionable_migration_error(self):
        from gridform_core.builtin.scheme_c_1000twh.factory import build

        with self.assertRaisesRegex(DeprecatedRouteError, "run_project_application"):
            build(PACK)


if __name__ == "__main__":
    unittest.main()
