from __future__ import annotations

import unittest

from scripts.global_mutation_scan import scan


class GlobalMutationAllowlistTests(unittest.TestCase):
    def test_no_undeclared_scientific_global_mutations(self) -> None:
        report = scan()
        self.assertTrue(report["go"], report["undeclared"])


if __name__ == "__main__":
    unittest.main()
