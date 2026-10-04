import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "visibility-refactor" / "retained-source-hashes.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RetainedSourceManifestTests(unittest.TestCase):
    def test_retained_sources_and_installed_data_pack_are_unchanged(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        errors = []

        for entry in manifest["files"]:
            path = ROOT / entry["path"]
            if not path.is_file():
                errors.append(f"MISSING retained {entry['kind']}: {entry['path']}")
                continue
            actual = sha256(path)
            if actual != entry["sha256"]:
                errors.append(
                    f"CHANGED retained {entry['kind']}: {entry['path']}\n"
                    f"  expected {entry['sha256']}\n  actual   {actual}"
                )

        for pack in manifest.get("data_packs", []):
            root = ROOT / pack["root"]
            if not root.exists():
                continue
            pack_manifest_path = root / pack["manifest"]
            if not pack_manifest_path.is_file():
                errors.append(f"MISSING installed data-pack manifest: {pack_manifest_path}")
                continue
            actual_manifest_hash = sha256(pack_manifest_path)
            if actual_manifest_hash != pack["manifest_sha256"]:
                errors.append(
                    f"CHANGED installed data-pack manifest: {pack['root']}/{pack['manifest']}\n"
                    f"  expected {pack['manifest_sha256']}\n"
                    f"  actual   {actual_manifest_hash}"
                )
                continue
            if not pack.get("validate_binding_sha256"):
                continue
            pack_manifest = json.loads(pack_manifest_path.read_text(encoding="utf-8"))
            for role, binding in pack_manifest.get("bindings", {}).items():
                path = root / binding["uri"]
                if not path.is_file():
                    errors.append(f"MISSING data-pack binding {role}: {binding['uri']}")
                    continue
                actual = sha256(path)
                if actual != binding["sha256"]:
                    errors.append(
                        f"CHANGED data-pack binding {role}: {binding['uri']}\n"
                        f"  expected {binding['sha256']}\n  actual   {actual}"
                    )

        if errors:
            self.fail("Retained VALUE preservation boundary failed:\n\n" + "\n\n".join(errors))


if __name__ == "__main__":
    unittest.main()
