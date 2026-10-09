"""CBC executable lookup for the independent oracles (X0 S6)."""

from __future__ import annotations

import contextlib
import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gridform_validation import cbc


def _fake_executable(folder: Path, name: str = "cbc") -> Path:
    path = folder / name
    path.write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class CbcLocatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.folder = Path(self._temporary.name)
        cbc._sha256.cache_clear()

    def _environment(self, **values: str):
        environment = {key: value for key, value in os.environ.items() if key != cbc.ENVIRONMENT_VARIABLE}
        environment.update(values)
        return mock.patch.dict(os.environ, environment, clear=True)

    def test_explicit_environment_path_wins(self) -> None:
        explicit = _fake_executable(self.folder, "my-cbc")
        with self._environment(VALUE_CBC_PATH=str(explicit)), \
                mock.patch.object(cbc, "_cbcbox_path", return_value=_fake_executable(self.folder, "boxed")):
            self.assertEqual(cbc.locate_cbc(), ("env", explicit.resolve()))

    def test_invalid_explicit_path_does_not_fall_back(self) -> None:
        with self._environment(VALUE_CBC_PATH=str(self.folder / "missing")), \
                mock.patch.object(cbc, "_cbcbox_path", return_value=_fake_executable(self.folder)):
            self.assertIsNone(cbc.locate_cbc())
            with self.assertRaises(cbc.CbcUnavailableError):
                cbc.cbc_path()

    def test_cbcbox_then_path(self) -> None:
        boxed = _fake_executable(self.folder, "boxed")
        on_path = _fake_executable(self.folder, "cbc")
        with self._environment(PATH=str(self.folder)):
            with mock.patch.object(cbc, "_cbcbox_path", return_value=boxed):
                self.assertEqual(cbc.locate_cbc(), ("cbcbox", boxed))
            with mock.patch.object(cbc, "_cbcbox_path", return_value=None):
                self.assertEqual(cbc.locate_cbc(), ("path", on_path.resolve()))

    def test_nothing_found_reports_unavailable(self) -> None:
        with self._environment(PATH=str(self.folder)), mock.patch.object(cbc, "_cbcbox_path", return_value=None):
            self.assertIsNone(cbc.locate_cbc())
            self.assertEqual(cbc.cbc_identity()["available"], False)

    def test_identity_records_variant_and_sha_without_printing(self) -> None:
        boxed = _fake_executable(self.folder, "boxed")
        stdout, stderr = io.StringIO(), io.StringIO()
        with self._environment(), mock.patch.object(cbc, "_cbcbox_path", return_value=boxed), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            identity = cbc.cbc_identity()
            command = cbc.cbc_command(msg=False)
        self.assertEqual(identity["variant"], "cbcbox")
        self.assertEqual(len(identity["binary_sha256"]), 64)
        self.assertEqual(command.path, str(boxed))
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")

    def test_real_cbcbox_lookup_is_silent(self) -> None:
        stdout = io.StringIO()
        with self._environment(), contextlib.redirect_stdout(stdout):
            located = cbc.locate_cbc()
        self.assertEqual(stdout.getvalue(), "")
        if located is not None:
            self.assertTrue(Path(located[1]).is_file())


class OracleSolverLocatorTests(unittest.TestCase):
    """Every independent-oracle report states which CBC binary solved it (plan X0 S6)."""

    def setUp(self) -> None:
        if cbc.locate_cbc() is None:
            self.skipTest("no CBC executable on this host")

    def test_zonal_oracle_result_names_the_cbc_binary(self) -> None:
        from gridform_validation.zonal_case_generator import random_convex_case
        from gridform_validation.zonal_oracle import solve_zonal_oracle

        result = solve_zonal_oracle(random_convex_case(41))
        self.assertEqual(result["solver"], "independent-pulp-cbc")
        self.assertEqual(result["solver_locator"], cbc.cbc_identity())
        self.assertTrue(result["solver_locator"]["available"])
        self.assertEqual(len(result["solver_locator"]["binary_sha256"]), 64)

    def test_declared_clearing_report_names_the_cbc_binary(self) -> None:
        import hashlib
        import json
        import sqlite3

        from gridform_validation.value_clearing_oracle import ORACLE_ID, validate_declared_database
        from tests.test_force_declared_clearing_validation import declared_case

        payload_json = json.dumps({"payload": declared_case()}, sort_keys=True)
        database = self.folder / "declared.sqlite"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE clearing_inputs (input_sha256 TEXT, year INTEGER, period INTEGER, stage TEXT, payload_json TEXT)")
            connection.execute("CREATE TABLE clearing_outcomes (input_sha256 TEXT, outcome_json TEXT)")
            connection.execute(
                "INSERT INTO clearing_inputs VALUES (?, 2025, 0, 'ahead', ?)",
                (hashlib.sha256(payload_json.encode("utf-8")).hexdigest(), payload_json),
            )
        report = validate_declared_database(database)
        self.assertEqual(report["oracle_id"], ORACLE_ID)
        self.assertEqual(report["solver_locator"], cbc.cbc_identity())
        self.assertEqual(report["lp_supported_rows"], 1)

    @property
    def folder(self) -> Path:
        if not hasattr(self, "_folder"):
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            self._folder = Path(temporary.name)
        return self._folder


if __name__ == "__main__":
    unittest.main()
