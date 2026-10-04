import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.run_dependency_audit import evaluate


class DependencyAuditPolicyTests(unittest.TestCase):
    def test_unreviewed_high_is_always_a_blocker(self):
        raw = {
            "npm": {
                "vulnerabilities": {
                    "bad": {"severity": "high", "isDirect": True, "range": "*", "nodes": ["node_modules/bad"], "via": []}
                },
                "metadata": {"vulnerabilities": {"total": 1, "high": 1, "critical": 0}},
            },
            "python": {},
        }
        with tempfile.TemporaryDirectory() as folder:
            policy = Path(folder) / "decisions.json"
            policy.write_text(json.dumps({"decisions": []}), encoding="utf-8")
            report = evaluate(raw, policy, today=date(2026, 8, 19))
        self.assertFalse(report["passed"])
        self.assertIn("unreviewed advisory", report["errors"][0])

    def test_reviewed_moderate_is_time_bounded(self):
        raw = {
            "npm": {
                "vulnerabilities": {
                    "tool": {"severity": "moderate", "isDirect": False, "range": "*", "nodes": [], "via": []}
                },
                "metadata": {"vulnerabilities": {"total": 1, "high": 0, "critical": 0}},
            },
            "python": {},
        }
        decision = {
            "finding_id": "npm:tool", "severity_classification": "moderate",
            "reachability": "build only", "exploit_surface": "none at runtime",
            "fix_availability": "pending", "disposition": "accepted_time_bound",
            "compensating_control": "not invoked", "review_by": "2026-09-01",
        }
        with tempfile.TemporaryDirectory() as folder:
            policy = Path(folder) / "decisions.json"
            policy.write_text(json.dumps({"decisions": [decision]}), encoding="utf-8")
            report = evaluate(raw, policy, today=date(2026, 8, 19))
        self.assertTrue(report["passed"], report["errors"])


if __name__ == "__main__":
    unittest.main()
