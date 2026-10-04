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


if __name__ == "__main__":
    unittest.main()
