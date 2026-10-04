import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.verify_install_scripts import verify_install_scripts


ROOT = Path(__file__).resolve().parents[1]


class InstallScriptPolicyTests(unittest.TestCase):
    def test_current_lock_matches_reviewed_allowlist(self):
        report = verify_install_scripts(
            ROOT / "package-lock.json",
            ROOT / "publication" / "dependency-install-script-allowlist.json",
            package_path=ROOT / "package.json",
            today=date(2026, 8, 19),
        )
        self.assertTrue(report["passed"], report["errors"])

    def test_new_install_script_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lock = root / "package-lock.json"
            allowlist = root / "allowlist.json"
            lock.write_text(json.dumps({"packages": {"node_modules/new": {"version": "1.0.0", "hasInstallScript": True}}}), encoding="utf-8")
            allowlist.write_text(json.dumps({"review_by": "2099-01-01", "entries": []}), encoding="utf-8")
            report = verify_install_scripts(lock, allowlist, today=date(2026, 8, 19))
            self.assertFalse(report["passed"])
            self.assertIn("undeclared install script", report["errors"][0])

    def test_npm_native_policy_must_match_reviewed_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lock = root / "package-lock.json"
            allowlist = root / "allowlist.json"
            package = root / "package.json"
            lock.write_text(
                json.dumps({"packages": {"node_modules/tool": {"version": "1.0.0", "hasInstallScript": True}}}),
                encoding="utf-8",
            )
            allowlist.write_text(
                json.dumps({
                    "review_by": "2099-01-01",
                    "entries": [{
                        "path": "node_modules/tool",
                        "package": "tool",
                        "version": "1.0.0",
                        "reachability": "test",
                        "reason": "test",
                        "disposition": "allow_until_review",
                    }],
                }),
                encoding="utf-8",
            )
            package.write_text(json.dumps({"allowScripts": {}}), encoding="utf-8")
            report = verify_install_scripts(
                lock,
                allowlist,
                package_path=package,
                today=date(2026, 8, 19),
            )
            self.assertFalse(report["passed"])
            self.assertIn("npm allowScripts approval missing: tool@1.0.0", report["errors"])


if __name__ == "__main__":
    unittest.main()
