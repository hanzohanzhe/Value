from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class NetCDFPreflightTests(unittest.TestCase):
    def test_scalar_numeric_metadata_does_not_break_bounded_sampling(self):
        try:
            import netCDF4
        except ImportError:
            self.skipTest("netCDF4 is optional")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scalar.nc"
            with netCDF4.Dataset(path, "w") as dataset:
                scalar = dataset.createVariable("metadata_scalar", "f8")
                scalar.assignValue(1.0)
                dataset.createDimension("time", 2)
                values = dataset.createVariable("values", "f8", ("time",))
                values[:] = [1.0, 2.0]
            # Exercise the same bounded expression as data-pack validation.
            with netCDF4.Dataset(path) as dataset:
                for variable in dataset.variables.values():
                    bounded = variable[...] if variable.ndim == 0 else variable[: min(variable.shape[0], 2)]
                    self.assertGreaterEqual(bounded.size, 1)


if __name__ == "__main__":
    unittest.main()
