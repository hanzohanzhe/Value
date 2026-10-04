from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from gridform_core.errors import RuntimeCapabilityError
from gridform_core.runtime_capabilities import (
    VALUE_NATIVE,
    SCHEME_C_REFERENCE,
    capability_status,
    require_runtime_capability,
)


class RuntimeCapabilityTests(unittest.TestCase):
    def test_optional_solver_modules_do_not_break_base_registry_import(self):
        root = Path(__file__).resolve().parents[1]
        script = (
            "import sys; "
            "sys.modules['scipy'] = None; "
            "from gridform_core.v2.module_manifest import workspace_registry; "
            "registry = workspace_registry(); "
            "assert registry.manifest('value-bid-at-cost-psm').id == 'value-bid-at-cost-psm'; "
            "assert registry.manifest('value-reference-dc-network').id == "
            "'value-reference-dc-network'"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_native_and_reference_are_distinct_dependency_scopes(self):
        native = capability_status(VALUE_NATIVE, selected_module_ids=("value-bid-at-cost-psm",))
        reference = capability_status(SCHEME_C_REFERENCE)
        self.assertNotIn("matplotlib", native["required_imports"])
        self.assertNotIn("openpyxl", native["required_imports"])
        self.assertIn("matplotlib", reference["required_imports"])
        self.assertIn("openpyxl", reference["required_imports"])

    def test_missing_reference_only_package_does_not_disable_native(self):
        actual = importlib.util.find_spec

        def find_spec(name):
            return None if name in {"matplotlib", "openpyxl", "seaborn"} else actual(name)

        with patch("gridform_core.runtime_capabilities.importlib.util.find_spec", side_effect=find_spec):
            native = capability_status(VALUE_NATIVE, selected_module_ids=("value-bid-at-cost-psm",))
            reference = capability_status(SCHEME_C_REFERENCE)
        self.assertTrue(native["available"])
        self.assertFalse(reference["available"])

    def test_unverified_python_is_not_claimed(self):
        with patch("gridform_core.runtime_capabilities.sys.version_info", (3, 12, 0)):
            status = capability_status(VALUE_NATIVE)
            self.assertFalse(status["python_supported"])
            with self.assertRaisesRegex(RuntimeCapabilityError, "No broader Python support"):
                require_runtime_capability(VALUE_NATIVE)

    def test_scipy_backed_network_modules_declare_solver_dependency(self):
        for module_id in (
            "value-perfect-foresight-lp",
            "value-reference-dc-network",
            "value-reference-ac-feasibility",
        ):
            status = capability_status(VALUE_NATIVE, selected_module_ids=(module_id,))
            self.assertIn("scipy", status["required_imports"])


if __name__ == "__main__":
    unittest.main()
