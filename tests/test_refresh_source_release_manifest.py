"""Tests for scripts/refresh_source_release_manifest.py."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "refresh_source_release_manifest", ROOT / "scripts" / "refresh_source_release_manifest.py"
)
REFRESH = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REFRESH)


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


class RefreshSourceReleaseManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        _git(self.root, "init", "-q")
        (self.root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        (self.root / "kept.txt").write_text("kept\n", encoding="utf-8")
        (self.root / "changed.txt").write_text("old\n", encoding="utf-8")
        (self.root / "gone.txt").write_text("gone\n", encoding="utf-8")
        (self.root / "tests" / "baselines").mkdir(parents=True)
        (self.root / "tests" / "baselines" / "release-exclusions.txt").write_text("# comment\nprivate/\n*.secret\n", encoding="utf-8")
        seed = {"schema_version": "value.source-release-manifest/v1", "include": [], "files": [], "methodology_edition": "0.3"}
        (self.root / "source-release-manifest.json").write_text(REFRESH.render(seed), encoding="utf-8")
        _git(self.root, "add", "-A")
        manifest, _ = REFRESH.refreshed_manifest(self.root)
        for entry in manifest["files"]:
            entry["transform"] = "byte copy"
        (self.root / "source-release-manifest.json").write_text(REFRESH.render(manifest), encoding="utf-8")

    def _run(self, *arguments: str) -> tuple[int, dict]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = REFRESH.main(["--root", str(self.root), *arguments])
        return code, json.loads(stdout.getvalue())

    def test_current_manifest_is_a_no_op(self) -> None:
        before = (self.root / "source-release-manifest.json").read_bytes()
        code, report = self._run("--check")
        self.assertEqual(code, 0, report)
        code, report = self._run()
        self.assertFalse(report["written"])
        self.assertEqual((self.root / "source-release-manifest.json").read_bytes(), before)

    def test_adds_updates_removes_and_honours_exclusions(self) -> None:
        (self.root / "changed.txt").write_text("new\n", encoding="utf-8")
        (self.root / "gone.txt").unlink()
        (self.root / "new.txt").write_text("new file\n", encoding="utf-8")
        (self.root / "ignored.txt").write_text("ignored\n", encoding="utf-8")
        (self.root / "private").mkdir()
        (self.root / "private" / "notes.md").write_text("local\n", encoding="utf-8")
        (self.root / "key.secret").write_text("x\n", encoding="utf-8")
        code, report = self._run("--check")
        self.assertEqual(code, 1)
        code, report = self._run()
        self.assertEqual(code, 0)
        manifest = json.loads((self.root / "source-release-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["include"],
            [".gitignore", "changed.txt", "kept.txt", "new.txt", "source-release-manifest.json", "tests/baselines/release-exclusions.txt"],
        )
        entries = {entry["path"]: entry for entry in manifest["files"]}
        self.assertNotIn("source-release-manifest.json", entries)
        self.assertEqual(entries["kept.txt"]["transform"], "byte copy")
        self.assertEqual(entries["changed.txt"]["transform"], REFRESH.DEFAULT_TRANSFORM)
        self.assertEqual(entries["changed.txt"]["sha256"], hashlib.sha256(b"new\n").hexdigest())
        self.assertEqual(entries["new.txt"]["bytes"], len(b"new file\n"))
        self.assertEqual(report["removed"], ["gone.txt"])
        self.assertEqual(manifest["methodology_edition"], "0.3")
        code, _ = self._run("--check")
        self.assertEqual(code, 0)

    def test_index_mode_uses_staged_paths_and_content(self) -> None:
        (self.root / "changed.txt").write_text("staged\n", encoding="utf-8")
        _git(self.root, "add", "changed.txt")
        (self.root / "changed.txt").write_text("unstaged edit\n", encoding="utf-8")
        (self.root / "untracked.txt").write_text("not staged\n", encoding="utf-8")
        code, report = self._run("--index")
        self.assertEqual(code, 0)
        manifest = json.loads((self.root / "source-release-manifest.json").read_text(encoding="utf-8"))
        entries = {entry["path"]: entry for entry in manifest["files"]}
        self.assertNotIn("untracked.txt", entries)
        self.assertEqual(entries["changed.txt"]["sha256"], hashlib.sha256(b"staged\n").hexdigest())

    def test_repository_manifest_is_current(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = REFRESH.main(["--root", str(ROOT), "--check"])
        self.assertEqual(code, 0, stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
