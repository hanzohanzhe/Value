"""Shared fixtures for external module/extension lifecycle tests (P0-2).

Everything here writes only below a caller-supplied temporary directory and
cleans the interpreter state (``sys.modules``/``sys.path``) it may leave.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "external_module_bundle"
EXTENSION_DESCRIPTOR = "force-extension-bundle.json"
EXTENSION_MANIFEST = "force-extension.json"
MODULE_MANIFEST = "value-module.json"

# The four import failures named by the P0-2 finding matrix (G4-02).
IMPORT_FAILURES = {
    "runtime_error": "raise RuntimeError('simulated broken import')\n",
    "syntax_error": "def broken(:\n",
    "system_exit": "raise SystemExit(7)\n",
    "missing_dependency": "import value_missing_dependency_for_p02_tests\n",
}


def example_plugin_source() -> str:
    return (EXAMPLE / "src" / "value_example_flat_offer" / "plugin.py").read_text(encoding="utf-8")


def module_manifest(module_id: str, package: str, **overrides: object) -> dict[str, object]:
    manifest = json.loads((EXAMPLE / MODULE_MANIFEST).read_text(encoding="utf-8"))
    manifest.update(id=module_id, name=module_id, implementation=f"{package}.plugin:FlatStorageCostDefinition")
    manifest.update(overrides)
    return manifest


def write_external_module(
    modules_root: Path,
    module_id: str,
    package: str,
    *,
    prefix: str = "",
    version: str = "1.0.0",
    enabled: bool = True,
    manifest_overrides: Mapping[str, object] | None = None,
    counter_file: Path | None = None,
) -> Path:
    """Lay out an installed external module exactly as the installer does.

    ``prefix`` is prepended to the example plugin (e.g. an import failure);
    ``counter_file`` makes every import of the plugin append one byte to it.
    """

    manifest = module_manifest(module_id, package, version=version, **dict(manifest_overrides or {}))
    target = modules_root / "installed" / module_id / version
    source = target / "src" / package
    source.mkdir(parents=True, exist_ok=True)
    (source / "__init__.py").write_text('"""Test package."""\n', encoding="utf-8")
    counting = ""
    if counter_file is not None:
        counting = f"with open({str(counter_file)!r}, 'a') as _counter:\n    _counter.write('x')\n"
    (source / "plugin.py").write_text(counting + prefix + example_plugin_source(), encoding="utf-8")
    (target / MODULE_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    record = {
        "schema_version": "value.module-installation/v1", "module_id": module_id, "name": module_id,
        "module_version": version, "scientific_version": manifest.get("scientific_version"),
        "slot": manifest["slot"], "contract_version": manifest["contract_version"],
        "implementation": manifest["implementation"], "implementation_package": package,
        "source_root": "src", "manifest_path": MODULE_MANIFEST, "bundle_path": "original-bundle.zip",
        "installed_at": "2026-10-05T00:00:00+00:00", "enabled": enabled, "origin": "local_bundle",
        "execution_boundary": "in_process_trusted_python", "scientific_validation_status": "not_evaluated",
        "conformance": {"status": "passed", "errors": [], "warnings": []},
    }
    (target / "installation.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if enabled:
        (modules_root / f"{module_id}.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return target


def extension_manifest(
    extension_id: str, namespace: str, *, version: str = "0.1.0",
    hooks: Iterable[Mapping[str, object]] = (), **overrides: object,
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema_version": "value.extension-bundle/v1", "id": extension_id, "name": extension_id,
        "version": version, "licence": "Apache-2.0", "namespace": namespace,
        "provided_capabilities": [], "hooks": [dict(item) for item in hooks], "maturity": "experimental",
    }
    manifest.update(overrides)
    return manifest


def build_extension_bundle(
    path: Path, extension_id: str, namespace: str, *, version: str = "0.1.0",
    hook_package: str | None = None, hook_source: str | None = None,
    manifest_overrides: Mapping[str, object] | None = None,
) -> Path:
    """A structurally valid extension ZIP (optionally with one hook package)."""

    hooks = []
    files: dict[str, bytes] = {"LICENSE": b"Apache-2.0\n"}
    if hook_package:
        hooks = [{"hook": "finalize", "implementation": f"{hook_package}.hooks:Hook"}]
        files[f"src/{hook_package}/__init__.py"] = b'"""Hook package."""\n'
        files[f"src/{hook_package}/hooks.py"] = (hook_source or HOOK_SOURCE).encode("utf-8")
    manifest = extension_manifest(extension_id, namespace, version=version, hooks=hooks, **dict(manifest_overrides or {}))
    files[EXTENSION_MANIFEST] = json.dumps(manifest).encode("utf-8")
    descriptor = {
        "schema_version": "value.extension-bundle/v1",
        "files": [
            {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(files.items())
        ],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(EXTENSION_DESCRIPTOR, json.dumps(descriptor))
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return path


HOOK_SOURCE = (
    "class Hook:\n"
    "    def finalize(self, payload):\n"
    "        return {}\n"
)


def write_external_extension(
    modules_root: Path, extension_id: str, namespace: str, *, version: str = "0.1.0",
    enabled: bool = True, hook_package: str | None = None, hook_prefix: str = "",
    manifest_overrides: Mapping[str, object] | None = None,
) -> Path:
    """Lay out an installed extension as the installer does (no validation)."""

    hooks = []
    target = modules_root / "installed-extensions" / extension_id / version
    target.mkdir(parents=True, exist_ok=True)
    if hook_package:
        hooks = [{"hook": "finalize", "implementation": f"{hook_package}.hooks:Hook"}]
        package = target / "src" / hook_package
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text('"""Hook package."""\n', encoding="utf-8")
        (package / "hooks.py").write_text(hook_prefix + HOOK_SOURCE, encoding="utf-8")
    manifest = extension_manifest(extension_id, namespace, version=version, hooks=hooks, **dict(manifest_overrides or {}))
    (target / EXTENSION_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    record = {
        "schema_version": "value.extension-installation/v1", "extension_id": extension_id,
        "version": version, "namespace": namespace, "enabled": enabled,
        "source_root": "src" if hook_package else None, "hook_source_identities": [],
        "conformance": {"status": "passed"},
    }
    (target / "installation.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if enabled:
        active = modules_root / "extensions"
        active.mkdir(parents=True, exist_ok=True)
        (active / f"{extension_id}.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return target


def tree_digest(root: Path, *, files_only: bool = False) -> str:
    """sha256 over every path (files, directories, link targets) and file bytes below ``root``.

    ``files_only`` ignores directories (an install may leave empty folders).
    """

    digest = hashlib.sha256()
    if not root.exists():
        return digest.hexdigest()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            digest.update(b"L" + relative.encode() + b"\0" + str(path.readlink()).encode() + b"\0")
        elif path.is_dir():
            if files_only:
                continue
            digest.update(b"D" + relative.encode() + b"\0")
        else:
            digest.update(b"F" + relative.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def forget_external_code(root: Path, packages: Iterable[str] = ()) -> None:
    """Remove modules loaded from ``root`` (or named packages) and its sys.path entries."""

    root_text = str(root.resolve()) if root.exists() else str(root)
    names = set(packages)
    for name, module in list(sys.modules.items()):
        raw = getattr(module, "__file__", None) or ""
        if name.split(".", 1)[0] in names or (raw and str(Path(raw).resolve()).startswith(root_text)):
            sys.modules.pop(name, None)
    sys.path[:] = [item for item in sys.path if not str(item).startswith(root_text) and not str(item).startswith(str(root))]


def copy_example_bundle_inputs(destination: Path, module_id: str, package: str, *, prefix: str = "") -> tuple[Path, Path]:
    """Manifest and source tree for ``build_module_bundle`` with a fresh package name."""

    source = destination / "src" / package
    source.mkdir(parents=True, exist_ok=True)
    (source / "__init__.py").write_text('"""Test package."""\n', encoding="utf-8")
    (source / "plugin.py").write_text(prefix + example_plugin_source(), encoding="utf-8")
    manifest_path = destination / MODULE_MANIFEST
    manifest_path.write_text(json.dumps(module_manifest(module_id, package)), encoding="utf-8")
    return manifest_path, destination / "src"


def remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
