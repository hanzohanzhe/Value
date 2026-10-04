from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from gridform_core.research_suite import validate_research_suite
from scripts.build_value_uk_research_suite import build_value_uk_research_suite


ROOT = Path(__file__).resolve().parents[1]


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _legacy_network_fixture(source: Path, target: Path) -> None:
    shutil.copytree(source, target)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["id"] = "force-fixture-zonal-v1"
    manifest["name"] = "FORCE fixture zonal pack"
    manifest["schema_version"] = "gridform.data-pack/v1"
    bindings = {}
    for role, binding_value in manifest["bindings"].items():
        binding = dict(binding_value)
        if role.startswith("value.zonal."):
            legacy_role = role.replace("value.zonal.", "force.zonal.", 1)
            old_path = target / binding["uri"]
            new_uri = binding["uri"].replace("value.zonal.", "force.zonal.")
            new_path = target / new_uri
            new_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.replace(new_path)
            legacy_payload = new_path.read_text(encoding="utf-8").replace("value.", "force.").replace("value-", "force-")
            new_path.write_text(legacy_payload, encoding="utf-8")
            binding.update({"role": legacy_role, "uri": new_uri, "filename": new_path.name})
            bindings[legacy_role] = binding
        else:
            bindings[role] = binding
    manifest["bindings"] = bindings
    manifest["zonal_network_pack"]["network_pack_id"] = manifest["id"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


class ValueUkResearchSuiteBuilderTests(unittest.TestCase):
    def test_sources_are_unchanged_and_output_is_a_minimal_value_suite(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base = root / "base-source"
            network = root / "network-source"
            shutil.copytree(ROOT / "data-packs" / "value-101-baseline-v1", base)
            _legacy_network_fixture(ROOT / "data-packs" / "value-101-network-v1", network)
            before = (_tree_digest(base), _tree_digest(network))

            result = build_value_uk_research_suite(
                base_source=base,
                network_source=network,
                destination=root / "VALUE-UK-Research-Suite.bundle.zip",
                receipt_path=root / "receipt.json",
            )

            self.assertEqual(before, (_tree_digest(base), _tree_digest(network)))
            validated = validate_research_suite(Path(result["path"]))
            self.assertEqual(
                validated.descriptor["components"]["base"]["pack_id"],
                "value-uk-open-data-pack-v1",
            )
            self.assertTrue(
                str(validated.descriptor["components"]["network"]["pack_id"]).startswith(
                    "value-gb-zonal-network-v1-"
                )
            )
            with zipfile.ZipFile(Path(result["path"])) as suite:
                self.assertFalse(any("force" in name.lower() for name in suite.namelist()))
                for name in ("research-suite.json", "study-templates.json", "RIGHTS.json", "ATTRIBUTION.md"):
                    self.assertNotIn("force", suite.read(name).decode("utf-8").lower())
                for component in (
                    "components/base.data-bundle.zip",
                    "components/network.data-bundle.zip",
                ):
                    with zipfile.ZipFile(io.BytesIO(suite.read(component))) as bundle:
                        self.assertFalse(any("force" in name.lower() for name in bundle.namelist()))
                        for member in bundle.namelist():
                            if Path(member).suffix.lower() in {".json", ".md", ".txt"}:
                                self.assertNotIn(
                                    "force",
                                    bundle.read(member).decode("utf-8").lower(),
                                    member,
                                )
            receipt = json.loads((root / "receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["source_tree_sha256"], list(before))
            self.assertEqual(receipt["study_ids"], [
                "value-uk-copperplate-2025-2034",
                "value-uk-zonal-2025-2034",
            ])


if __name__ == "__main__":
    unittest.main()
