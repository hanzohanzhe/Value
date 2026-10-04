from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gridform_core.path_hygiene import find_absolute_paths, scan_path
from gridform_core.builtin.scheme_c_1000twh.runtime_overlay import verify_runtime_overlay


ROOT = Path(__file__).resolve().parents[1]


class PathHygieneTests(unittest.TestCase):
    def test_python_decoding_distinguishes_newline_from_raw_drive_path(self) -> None:
        source = b'print("cost by year:\\n")\nweather = r"E:\\weather\\solar.nc"\n'
        findings = find_absolute_paths(source, ".py")
        self.assertEqual([(row.kind, row.line) for row in findings], [("windows_drive", 2)])
        self.assertIn("E:\\weather\\solar.nc", findings[0].value)

    def test_detects_drive_unc_and_posix_home_paths(self) -> None:
        payloads = (
            (b'value = r"C:\\Users\\researcher\\data.csv"\n', ".py", "windows_drive"),
            (b'value = r"\\\\server\\share\\data.csv"\n', ".py", "windows_unc"),
            (json.dumps({"path": "/home/researcher/data.csv"}).encode(), ".json", "posix_home"),
        )
        for data, suffix, expected in payloads:
            with self.subTest(expected=expected):
                self.assertEqual(find_absolute_paths(data, suffix)[0].kind, expected)

    def test_urls_and_regular_escaped_strings_are_not_paths(self) -> None:
        source = b'url = "https://example.org/C:/Users/not-local"\nlabel = "year:\\n"\n'
        self.assertEqual(find_absolute_paths(source, ".py"), [])

    def test_only_preserved_config_has_current_reference_findings(self) -> None:
        config = ROOT / "gridform_core/builtin/scheme_c_1000twh/compat/config.py"
        mechanism = ROOT / "gridform_core/builtin/scheme_c_1000twh/compat/load_mechanism_costs.py"
        runtime = ROOT / "gridform_core/builtin/scheme_c_1000twh/runtime_compat/config.py"
        self.assertEqual(len(scan_path(config)), 2)
        self.assertEqual(scan_path(mechanism), [])
        self.assertEqual(scan_path(runtime), [])

    def test_scanner_reports_line_for_plain_text(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.txt"
            path.write_text("safe\n/home/user/input.csv\n", encoding="utf-8")
            finding = scan_path(path)[0]
            self.assertEqual(finding.line, 2)

    def test_runtime_copy_matches_source_hashed_overlay_manifest(self) -> None:
        report = verify_runtime_overlay()
        self.assertTrue(report["verified"])
        self.assertEqual(
            report["required_bindings"], ["weather.solar", "weather.wind"]
        )


if __name__ == "__main__":
    unittest.main()
