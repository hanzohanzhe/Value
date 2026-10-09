"""R3M-1 (DECISIONS A23): the module developer guides name the contract IDs the
installer accepts, and a bundle written the way the guide says installs."""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from gridform_core.module_bundle import build_module_bundle
from gridform_core.module_installation import ModuleInstallationError, install_module_bundle
from gridform_core.module_bundle import ModuleBundleError
from gridform_core.v2.module_manifest import SUPPORTED_CONTRACTS


ROOT = Path(__file__).resolve().parents[1]
GUIDES = (ROOT / "docs" / "MODULE_DEVELOPER_101.md", ROOT / "docs" / "MODULE_DEVELOPER_101_ZH.md")
USER_GUIDES = (ROOT / "docs" / "USER_GUIDE.md", ROOT / "docs" / "USER_GUIDE_ZH.md")
EXAMPLE = ROOT / "examples" / "external_module_bundle"
TABLE_ROW = re.compile(r"^\| `([a-z_]+)` \| `([a-z]+\.[a-z-]+/v\d+)` \|")
PRE_VALUE_CONTRACT = re.compile(
    r"gridform\.(psm|storage-cost|expansion-policy|investment|planning|state-transition|"
    r"network-expansion|balancing-module|weather-spatializer)/v\d+"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _slot_table(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in _text(path).splitlines():
        match = TABLE_ROW.match(line)
        if match and match.group(1) in SUPPORTED_CONTRACTS:
            rows[match.group(1)] = match.group(2)
    return rows


class DeveloperGuideContractIdTests(unittest.TestCase):
    def test_slot_tables_name_the_installer_contracts(self) -> None:
        for guide in GUIDES:
            with self.subTest(guide=guide.name):
                table = _slot_table(guide)
                self.assertGreaterEqual(len(table), 7)
                for slot, contract in table.items():
                    self.assertEqual(contract, SUPPORTED_CONTRACTS[slot], f"{guide.name}: {slot}")

    def test_manifest_examples_use_the_slot_contract(self) -> None:
        for guide in GUIDES:
            blocks = re.findall(r"```json\n(.*?)```", _text(guide), flags=re.S)
            manifests = []
            for block in blocks:
                try:
                    payload = json.loads(block)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and "slot" in payload and "contract_version" in payload:
                    manifests.append(payload)
            with self.subTest(guide=guide.name):
                self.assertTrue(manifests, "the general manifest example is missing")
                for payload in manifests:
                    self.assertEqual(payload["contract_version"], SUPPORTED_CONTRACTS[payload["slot"]])

    def test_pre_value_contract_ids_appear_only_as_the_rejection_example(self) -> None:
        for guide in GUIDES + USER_GUIDES:
            for number, line in enumerate(_text(guide).splitlines(), start=1):
                if PRE_VALUE_CONTRACT.search(line):
                    self.assertIn("expected value.", line, f"{guide.name}:{number}: {line}")
                self.assertNotIn("force-module.json", line, f"{guide.name}:{number}")
                self.assertNotIn("force.vre-counterfactual-snapshot", line, f"{guide.name}:{number}")
                self.assertNotIn("FORCE Python", line, f"{guide.name}:{number}")


class DocumentedExampleInstallsTests(unittest.TestCase):
    """Build the storage-cost example with the contract ID the guide's table gives
    and install it; the pre-VALUE ID is refused with the quoted message."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.modules = self.root / "modules"

    def tearDown(self) -> None:
        for name in list(sys.modules):
            if name == "value_example_flat_offer" or name.startswith("value_example_flat_offer."):
                sys.modules.pop(name, None)
        root_text = str(self.modules)
        sys.path[:] = [item for item in sys.path if not str(item).startswith(root_text)]
        self.temporary.cleanup()

    def _project(self, contract: str, module_id: str) -> Path:
        project = self.root / module_id
        shutil.copytree(EXAMPLE, project)
        manifest = json.loads((project / "value-module.json").read_text(encoding="utf-8"))
        manifest["id"] = module_id
        manifest["contract_version"] = contract
        (project / "value-module.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        shutil.copy(ROOT / "LICENSE", project / "LICENSE")
        return project

    def _build(self, project: Path) -> Path:
        destination = self.root / f"{project.name}.zip"
        build_module_bundle(
            manifest_path=project / "value-module.json",
            source_root=project / "src",
            license_path=project / "LICENSE",
            readme_path=project / "README.md",
            destination=destination,
        )
        return destination

    def test_bundle_written_from_the_guide_installs(self) -> None:
        for guide in GUIDES:
            self.assertEqual(_slot_table(guide)["storage_cost"], "value.storage-cost/v1")
        contract = _slot_table(GUIDES[0])["storage_cost"]
        bundle = self._build(self._project(contract, "r2-guide-flat-offer"))
        installation = install_module_bundle(bundle, trust_acknowledged=True, modules_root=self.modules)
        self.assertEqual(installation["module_id"], "r2-guide-flat-offer")
        self.assertEqual(installation["conformance"]["status"], "passed")

    def test_pre_value_contract_id_is_refused_with_the_documented_message(self) -> None:
        bundle = self._build(self._project("gridform.storage-cost/v1", "my-module"))
        with self.assertRaises((ModuleInstallationError, ModuleBundleError, ValueError)) as caught:
            install_module_bundle(bundle, trust_acknowledged=True, modules_root=self.modules)
        quoted = "Module my-module in slot storage_cost uses gridform.storage-cost/v1; expected value.storage-cost/v1"
        self.assertIn(quoted, str(caught.exception))
        for guide in GUIDES:
            self.assertIn(quoted, _text(guide))
        self.assertFalse((self.modules / "my-module.json").exists())


if __name__ == "__main__":
    unittest.main()
