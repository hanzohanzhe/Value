import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "gridform_core" / "builtin" / "scheme_c_1000twh"
ALLOWLIST = {
    "compat/case3.py",
    "compat/investment_support.py",
    "runtime_compat/case3.py",
    "runtime_compat/investment_support.py",
    "legacy_result_adapter.py",
}
FORBIDDEN = re.compile(r"\b(?:results|raw)\s*\[\s*-?\d+\s*\]")


class NoPositionalSchemeCResultTests(unittest.TestCase):
    def test_modular_and_production_consumers_use_named_fields(self):
        findings = []
        for path in PACKAGE.rglob("*.py"):
            relative = path.relative_to(PACKAGE).as_posix()
            if relative in ALLOWLIST:
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if FORBIDDEN.search(line):
                    findings.append(f"{relative}:{line_number}: {line.strip()}")
        self.assertEqual(
            findings,
            [],
            "Positional VALUE result access escaped the adapter/reference allowlist:\n"
            + "\n".join(findings),
        )


if __name__ == "__main__":
    unittest.main()
