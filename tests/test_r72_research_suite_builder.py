"""R7-2 (3): a reproducible research-suite build on another base pack (DECISIONS A34).

* ``build_research_suite`` takes the suite ID as a parameter (default
  unchanged) and the suite validator refuses an unsafe suite ID, because it
  names the installation folder;
* ``scripts/build_value_uk_research_suite.py`` can take published base and
  network bundles as they are (no re-wrapping: the component SHA-256 is the
  published bundle's), with ``--base-pack-id``, ``--suite-id`` and a Study-ID
  suffix; the Study templates come from ``value_uk_study_templates``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from gridform_core.data_bundle import build_data_bundle
from gridform_core.research_suite import (
    DEFAULT_SUITE_ID,
    NETWORK_MEMBER,
    BASE_MEMBER,
    ResearchSuiteError,
    build_research_suite,
    validate_research_suite,
)
from gridform_core.value_uk import value_uk_study_templates
from scripts.build_value_uk_research_suite import build_value_uk_research_suite
from tests.test_build_value_uk_research_suite import _legacy_network_fixture
from tests.test_research_suite import ResearchSuiteTests


ROOT = Path(__file__).resolve().parents[1]
BASE_PACK = ROOT / "data-packs" / "value-101-baseline-v1"
NETWORK_PACK = ROOT / "data-packs" / "value-101-network-v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class R72ResearchSuiteBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        base = self.root / "base-pack"
        network = self.root / "network-pack"
        shutil.copytree(BASE_PACK, base)
        shutil.copytree(NETWORK_PACK, network)
        (base / "derivation.json").unlink(missing_ok=True)
        (network / "derivation.json").unlink(missing_ok=True)
        # Stand-ins for the published bundles (built once, then used as is).
        self.base_bundle = self.root / "published" / "base-published.zip"
        self.network_bundle = self.root / "published" / "network-published.zip"
        build_data_bundle(pack_root=base, destination=self.base_bundle)
        build_data_bundle(pack_root=network, destination=self.network_bundle)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _published_suite(self, **options: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "base_bundle": self.base_bundle,
            "network_bundle": self.network_bundle,
            "destination": self.root / "suite.zip",
            "receipt_path": self.root / "receipt.json",
            "suite_id": "value-uk-research-suite-v1-public2",
            "study_id_suffix": "-public2",
            "study_name_suffix": " (GBP1 public2)",
        }
        arguments.update(options)
        return build_value_uk_research_suite(**arguments)  # type: ignore[arg-type]

    def test_published_bundles_are_used_byte_for_byte(self) -> None:
        before = (_sha256(self.base_bundle), _sha256(self.network_bundle))
        receipt = self._published_suite()
        suite = Path(str(receipt["path"]))
        validated = validate_research_suite(suite)
        self.assertEqual(validated.descriptor["suite_id"], "value-uk-research-suite-v1-public2")
        components = validated.descriptor["components"]
        self.assertEqual(components["base"]["pack_id"], "value-101-baseline-v1")
        self.assertEqual(components["network"]["pack_id"], "value-101-network-v1")
        self.assertEqual(components["base"]["bundle_sha256"], before[0])
        self.assertEqual(components["network"]["bundle_sha256"], before[1])
        with zipfile.ZipFile(suite) as archive:
            self.assertEqual(archive.read(BASE_MEMBER), self.base_bundle.read_bytes())
            self.assertEqual(archive.read(NETWORK_MEMBER), self.network_bundle.read_bytes())
            templates = json.loads(archive.read("study-templates.json"))
            rights = json.loads(archive.read("RIGHTS.json"))
        self.assertEqual(before, (_sha256(self.base_bundle), _sha256(self.network_bundle)))
        self.assertEqual(rights["suite_id"], "value-uk-research-suite-v1-public2")
        self.assertEqual(rights["components"], ["value-101-baseline-v1", "value-101-network-v1"])
        expected = [dict(item) for item in value_uk_study_templates("value-101-baseline-v1", "value-101-network-v1")]
        for item in expected:
            item["id"] = item["id"] + "-public2"
            item["name"] = item["name"] + " (GBP1 public2)"
        self.assertEqual(templates["studies"], json.loads(json.dumps(expected)))
        self.assertEqual(receipt["study_ids"], [
            "value-uk-copperplate-2025-2034-public2", "value-uk-zonal-2025-2034-public2",
        ])
        self.assertEqual(receipt["component_bundle_sha256"], list(before))
        self.assertEqual(receipt["source_tree_sha256"], [None, None])
        self.assertEqual(receipt["component_inputs"]["base"]["mode"], "published_bundle")
        self.assertEqual(receipt["component_inputs"]["network"]["bundle_sha256"], before[1])
        stored = json.loads((self.root / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["sha256"], receipt["sha256"])

    def test_build_is_reproducible(self) -> None:
        first = self._published_suite(destination=self.root / "one.zip", receipt_path=self.root / "one.json")
        second = self._published_suite(destination=self.root / "two.zip", receipt_path=self.root / "two.json")
        self.assertEqual(first["sha256"], second["sha256"])

    def test_published_suite_installs_with_suffixed_studies(self) -> None:
        receipt = self._published_suite()
        state = self.root / "state"
        installed = ResearchSuiteTests._install(self, Path(str(receipt["path"])), state)  # type: ignore[arg-type]
        self.assertEqual(installed["study_ids"], receipt["study_ids"])
        self.assertTrue((state / "research-suites" / "value-uk-research-suite-v1-public2").is_dir())
        zonal = json.loads(
            (state / "projects" / "value-uk-zonal-2025-2034-public2" / "project.json").read_text(encoding="utf-8")
        )
        self.assertEqual(zonal["data_pack_id"], "value-101-baseline-v1")
        self.assertEqual(zonal["market_configuration"]["network_pack_id"], "value-101-network-v1")

    def test_base_pack_id_must_match_a_published_base_bundle(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match the published base bundle"):
            self._published_suite(base_pack_id="value-uk-open-data-pack-public2")
        receipt = self._published_suite(base_pack_id="value-101-baseline-v1")
        self.assertEqual(receipt["component_pack_ids"][0], "value-101-baseline-v1")

    def test_swapped_or_missing_components_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a network_overlay"):
            self._published_suite(network_bundle=self.base_bundle)
        with self.assertRaisesRegex(ValueError, "is a network_overlay"):
            self._published_suite(base_bundle=self.network_bundle)
        with self.assertRaisesRegex(ValueError, "exactly one of base_source"):
            self._published_suite(base_source=BASE_PACK)
        with self.assertRaisesRegex(ValueError, "exactly one of network_source"):
            self._published_suite(network_bundle=None)
        with self.assertRaisesRegex(ValueError, "Study ID is not a safe"):
            self._published_suite(study_id_suffix="/../x")
        with self.assertRaisesRegex(ValueError, "Suite ID is not a safe"):
            self._published_suite(suite_id="../suite")

    def test_reseal_takes_base_pack_id_and_suite_id(self) -> None:
        base = self.root / "base-source"
        network = self.root / "network-source"
        shutil.copytree(BASE_PACK, base)
        _legacy_network_fixture(NETWORK_PACK, network)
        receipt = build_value_uk_research_suite(
            base_source=base,
            network_bundle=self.network_bundle,
            base_pack_id="value-uk-open-data-pack-test2",
            suite_id="value-uk-research-suite-test2",
            destination=self.root / "resealed.zip",
            receipt_path=self.root / "resealed.json",
        )
        validated = validate_research_suite(Path(str(receipt["path"])))
        self.assertEqual(validated.descriptor["suite_id"], "value-uk-research-suite-test2")
        self.assertEqual(validated.descriptor["components"]["base"]["pack_id"], "value-uk-open-data-pack-test2")
        self.assertEqual(receipt["component_inputs"]["base"]["mode"], "resealed_source")
        self.assertIsNotNone(receipt["source_tree_sha256"][0])
        self.assertIsNone(receipt["source_tree_sha256"][1])
        with zipfile.ZipFile(Path(str(receipt["path"]))) as archive:
            templates = json.loads(archive.read("study-templates.json"))
        self.assertEqual({item["data_pack_id"] for item in templates["studies"]}, {"value-uk-open-data-pack-test2"})
        self.assertEqual(receipt["study_ids"], ["value-uk-copperplate-2025-2034", "value-uk-zonal-2025-2034"])

    def test_command_line_options(self) -> None:
        completed = subprocess.run(
            [
                sys.executable, "-B", str(ROOT / "scripts" / "build_value_uk_research_suite.py"),
                "--base-bundle", str(self.base_bundle),
                "--network-bundle", str(self.network_bundle),
                "--base-pack-id", "value-101-baseline-v1",
                "--suite-id", "value-uk-research-suite-v1-public2",
                "--study-id-suffix=-public2",
                "--output", str(self.root / "cli.zip"),
                "--receipt", str(self.root / "cli.json"),
            ],
            capture_output=True, text=True, timeout=300, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertEqual(receipt["suite_id"], "value-uk-research-suite-v1-public2")
        self.assertEqual(receipt["study_ids"][1], "value-uk-zonal-2025-2034-public2")
        both = subprocess.run(
            [
                sys.executable, "-B", str(ROOT / "scripts" / "build_value_uk_research_suite.py"),
                "--base-bundle", str(self.base_bundle), "--base-source", str(BASE_PACK),
                "--network-bundle", str(self.network_bundle),
                "--output", str(self.root / "x.zip"), "--receipt", str(self.root / "x.json"),
            ],
            capture_output=True, text=True, timeout=300, check=False,
        )
        self.assertEqual(both.returncode, 2)
        self.assertIn("not allowed with argument", both.stderr)


class R72ResearchSuiteIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        base = self.root / "base-pack"
        network = self.root / "network-pack"
        shutil.copytree(BASE_PACK, base)
        shutil.copytree(NETWORK_PACK, network)
        (base / "derivation.json").unlink(missing_ok=True)
        (network / "derivation.json").unlink(missing_ok=True)
        self.base_bundle = self.root / "base.zip"
        self.network_bundle = self.root / "network.zip"
        build_data_bundle(pack_root=base, destination=self.base_bundle)
        build_data_bundle(pack_root=network, destination=self.network_bundle)
        self.templates = self.root / "study-templates.json"
        self.templates.write_text(json.dumps({
            "schema_version": "value.study-templates/v1",
            "studies": list(value_uk_study_templates("value-101-baseline-v1", "value-101-network-v1")),
        }), encoding="utf-8")
        self.rights = self.root / "RIGHTS.json"
        self.rights.write_text("{}", encoding="utf-8")
        self.attribution = self.root / "ATTRIBUTION.md"
        self.attribution.write_text("# Attribution\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _build(self, destination: Path, **options: object) -> dict[str, object]:
        return build_research_suite(
            base_bundle=self.base_bundle, network_bundle=self.network_bundle,
            studies_path=self.templates, rights_paths=(self.rights, self.attribution),
            destination=destination, **options,  # type: ignore[arg-type]
        )

    def test_default_suite_id_is_unchanged(self) -> None:
        self.assertEqual(DEFAULT_SUITE_ID, "value-uk-research-suite-v1")
        result = self._build(self.root / "default.zip")
        self.assertEqual(result["suite_id"], "value-uk-research-suite-v1")
        explicit = self._build(self.root / "explicit.zip", suite_id="value-uk-research-suite-v1")
        self.assertEqual(result["sha256"], explicit["sha256"])

    def test_suite_id_parameter_and_unsafe_ids(self) -> None:
        result = self._build(self.root / "public2.zip", suite_id="value-uk-research-suite-v1-public2")
        self.assertEqual(
            validate_research_suite(self.root / "public2.zip").descriptor["suite_id"],
            "value-uk-research-suite-v1-public2",
        )
        self.assertEqual(result["suite_id"], "value-uk-research-suite-v1-public2")
        for unsafe in ("", "../escape", "a/b", ".hidden"):
            with self.assertRaises(ResearchSuiteError) as caught:
                self._build(self.root / "unsafe.zip", suite_id=unsafe)
            self.assertEqual(caught.exception.code, "VALUE_RESEARCH_SUITE_ID")

    def test_validator_refuses_an_unsafe_descriptor_suite_id(self) -> None:
        source = self.root / "good.zip"
        self._build(source)
        crafted = self.root / "crafted.zip"
        with zipfile.ZipFile(source) as old, zipfile.ZipFile(crafted, "w") as new:
            for member in old.infolist():
                data = old.read(member)
                if member.filename == "research-suite.json":
                    descriptor = json.loads(data)
                    descriptor["suite_id"] = "../../outside"
                    data = json.dumps(descriptor).encode("utf-8")
                new.writestr(member, data)
        with self.assertRaises(ResearchSuiteError) as caught:
            validate_research_suite(crafted)
        self.assertEqual(caught.exception.code, "VALUE_RESEARCH_SUITE_ID")


if __name__ == "__main__":
    unittest.main()
