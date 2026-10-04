"""Every project module a release member imports is itself a release member.

The public source release (and the installer built from it) contains only the
paths listed in ``source-release-manifest.json``.  A new module that is
imported but missing from the manifest installs fine and then fails with
ImportError (review finding on P0-4: the oracle's new files were not in the
manifest).  ``scripts/refresh_source_release_manifest.py`` is the first line
of defence (C25); this test is the second.

Scope: absolute imports of the in-repository packages and relative imports,
statically resolved from every ``.py`` release member.  A target that exists
in the repository must be a release member; a target that exists nowhere is
reported unless the import is guarded by ``try``.
"""

from __future__ import annotations

import ast
import importlib.util
import unittest
import warnings
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_release_scan_p04", ROOT / "scripts" / "source_release_scan.py")
SCAN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SCAN)

INTERNAL_PACKAGES = ("gridform_core", "gridform_validation", "backend", "scripts", "tests")

# Files added by P0-4 S1 (plan 4.4); they must ship with the source release.
P04_S1_MEMBERS = (
    "gridform_core/energy_balance_contract.py",
    "gridform_core/energy_balance_oracle.py",
    "scripts/p04_capture_trajectory_golden.py",
    "tests/p04_variants.py",
    "tests/fixtures/p04_trajectory_golden.json",
    "tests/test_energy_balance_oracle.py",
    "tests/test_p04_variant_fixtures.py",
    "tests/test_release_members_cover_imports.py",
)


def _module_candidates(dotted: str) -> tuple[str, str]:
    base = dotted.replace(".", "/")
    return f"{base}.py", f"{base}/__init__.py"


def _exists(relative: str) -> bool:
    return (ROOT / relative).is_file()


def _package_parts(relative: str) -> list[str]:
    return list(PurePosixPath(relative).parts[:-1])


def _guarded_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for statement in node.body:
                for child in ast.walk(statement):
                    if hasattr(child, "lineno"):
                        lines.add(child.lineno)
    return lines


def imported_targets(relative: str, source: str) -> list[tuple[int, str, bool, bool]]:
    """(line, dotted module, guarded, may_be_attribute) for project imports in one file."""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # invalid escapes in other modules are not this test's concern
        tree = ast.parse(source, filename=relative)
    guarded = _guarded_lines(tree)
    targets: list[tuple[int, str, bool, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in INTERNAL_PACKAGES:
                    targets.append((node.lineno, alias.name, node.lineno in guarded, False))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = _package_parts(relative)
                if node.level > 1:
                    package = package[: len(package) - (node.level - 1)]
                base = ".".join(package + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            if not base or base.split(".")[0] not in INTERNAL_PACKAGES:
                continue
            targets.append((node.lineno, base, node.lineno in guarded, False))
            for alias in node.names:
                if alias.name != "*":
                    # ``from pkg import name``: name is a submodule only if such a file exists.
                    targets.append((node.lineno, f"{base}.{alias.name}", node.lineno in guarded, True))
    return targets


def missing_release_members(members: set[str]) -> list[str]:
    problems: list[str] = []
    for relative in sorted(members):
        if not relative.endswith(".py") or relative.split("/", 1)[0] not in INTERNAL_PACKAGES:
            continue
        source = (ROOT / relative).read_text(encoding="utf-8")
        for line, dotted, guarded, may_be_attribute in imported_targets(relative, source):
            candidates = _module_candidates(dotted)
            existing = [candidate for candidate in candidates if _exists(candidate)]
            if existing:
                if not any(candidate in members for candidate in existing):
                    problems.append(f"{relative}:{line} imports {dotted} ({existing[0]} is not a release member)")
                continue
            namespace = (ROOT / dotted.replace(".", "/")).is_dir()
            if may_be_attribute or guarded or namespace:
                continue
            problems.append(f"{relative}:{line} imports {dotted}, which does not exist")
    return problems


class ReleaseMembersCoverImports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.members = {path.relative_to(ROOT).as_posix() for path in SCAN.release_members(ROOT)}

    def test_p04_s1_files_are_release_members(self):
        self.assertEqual([path for path in P04_S1_MEMBERS if path not in self.members], [])

    def test_every_project_import_resolves_to_a_release_member(self):
        self.assertEqual(missing_release_members(self.members), [])

    def test_detects_an_unlisted_module(self):
        # Drop the contract from the member set: the oracle's import must be reported.
        reduced = set(self.members) - {"gridform_core/energy_balance_contract.py"}
        problems = missing_release_members(reduced)
        self.assertTrue(
            any(problem.startswith("gridform_core/energy_balance_oracle.py:") and "energy_balance_contract" in problem
                for problem in problems),
            problems,
        )

    def test_resolves_relative_imports(self):
        targets = imported_targets(
            "gridform_core/energy_balance_oracle.py",
            "from . import energy_balance_contract as contract\nfrom .missing_module import name\n",
        )
        self.assertIn((1, "gridform_core.energy_balance_contract", False, True), targets)
        self.assertIn((2, "gridform_core.missing_module", False, False), targets)
        problems = missing_release_members({"gridform_core/energy_balance_oracle.py"})
        self.assertTrue(any("energy_balance_contract.py is not a release member" in problem for problem in problems), problems)


if __name__ == "__main__":
    unittest.main()
