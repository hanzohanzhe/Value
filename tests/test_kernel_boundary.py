"""P0-5a, decisions Q9/A3 and A5: the retained kernel's interconnector input (P6-24, P6-03).

The real kernel runs the frozen golden D3 project (value_101_day, 48
periods) on a copy of the 101 pack whose ten boundary series are
non-constant and distinct per country.  Every Connection must receive its
own country's series period by period (src[p]) - the 35aadb3 kernel served
src[p // 2] and fed three Connections another country's files (the stored
P0-5 S0 baseline keeps that record in head_rules).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from gridform_core.builtin.scheme_c_1000twh import kernel_boundary
from gridform_core.interconnector_identity import KERNEL_CONNECTION_BY_COUNTRY
from tests.p0_5_fixtures import (
    KernelBoundaryRecorder,
    capture_module,
    nonconstant_boundary_pack,
    run_value_101_day,
    toy_price,
    toy_profile,
)


class KernelBoundaryTests(unittest.TestCase):
    def test_kernel_receives_each_country_period_by_period(self) -> None:
        capture = capture_module()
        with tempfile.TemporaryDirectory() as directory:
            pack = nonconstant_boundary_pack(Path(directory))
            recorder = KernelBoundaryRecorder()
            run_value_101_day(pack, recorder)
            manifest = capture.load_manifest(pack)
            chronology = capture.chronology_capture(pack, manifest, 48, doctoral=False)
        self.assertEqual(recorder.periods, list(range(48)))
        self.assertEqual(set(recorder.connections), set(KERNEL_CONNECTION_BY_COUNTRY.values()))
        for country, connection in KERNEL_CONNECTION_BY_COUNTRY.items():
            observed = recorder.connections[connection]
            with self.subTest(connection=connection):
                self.assertEqual([float(value) for value in observed["transfer_constraint"]],
                                 [toy_profile(country, period) for period in range(48)])
                self.assertEqual([float(value) for value in observed["external_price"]],
                                 [toy_price(country, period) for period in range(48)])
        # The kernel and the canonical adapter now read the same series.
        france = capture.digest([float(value) for value in recorder.connections["Interconnect_France"]["external_price"]])
        self.assertEqual(chronology["imports"]["france"]["price"], france)

    def test_legacy_file_session_is_served_period_by_period_and_wraps(self) -> None:
        boundary = kernel_boundary.KernelBoundary(
            {country: np.array([1.0, 2.0, 3.0]) for country in KERNEL_CONNECTION_BY_COUNTRY},
            {country: np.array([10.0, 20.0, 30.0]) for country in KERNEL_CONNECTION_BY_COUNTRY},
            "toy", {},
        )
        connections = {name: SimpleNamespace(name=name, transfer_constraint=0, external_price=0)
                       for name in KERNEL_CONNECTION_BY_COUNTRY.values()}
        seen = []
        for period in range(5):
            kernel_boundary.assign_period(boundary, connections, period)
            seen.append((connections["Interconnect_Beligum"].transfer_constraint,
                         connections["Interconnect_Beligum"].external_price))
        self.assertEqual(seen, [(1.0, 10.0), (2.0, 20.0), (3.0, 30.0), (1.0, 10.0), (2.0, 20.0)])

    def test_short_injection_is_refused(self) -> None:
        injected = kernel_boundary.KernelBoundary(
            {country: np.zeros(3) for country in KERNEL_CONNECTION_BY_COUNTRY},
            {country: np.zeros(3) for country in KERNEL_CONNECTION_BY_COUNTRY}, "toy", {},
        )
        with self.assertRaises(ValueError):
            kernel_boundary.active_boundary(SimpleNamespace(kernel_boundary=injected), {}, 48)


if __name__ == "__main__":
    unittest.main()
