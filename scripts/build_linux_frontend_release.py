"""Build a local Linux candidate from existing source, UI and runtime packages.

No build, dependency installation, download or model execution is performed.
The resulting application requires external Python 3.10 and Node >=22.13.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("app", "backend", "gridform_core", "model-sdk", "scripts", "requirements", "packaging/linux-local",
               "docs", "public", "examples/external_module_bundle", "examples/external_psm_bundle", "examples/external_modules")
FILES = ("package.json", "package-lock.json", "pyproject.toml", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md",
         "README.md", "README_BILINGUAL.md", "LICENSING.md", "AUTHORS.md", "public/README.md",
         "tsconfig.json", "tsconfig.frontend.json", "vite.config.ts", "next.config.ts", "next-env.d.ts", "postcss.config.mjs")
NODE_PACKAGES = ("vinext", "react", "react-dom", "react-server-dom-webpack", "scheduler")
TEACHING_PACKS = ("value-101-baseline-v1", "value-101-network-v1")
EXCLUDE = {".git", "__pycache__", "node_modules", "outputs", "output", "state", "value-state", "model-output", "test-results", ".cache", ".next", ".bin"}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def members(directory: Path):
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError(f"Required regular directory missing: {directory}")
    for base, dirs, files in os.walk(directory):
        dirs[:] = sorted(name for name in dirs if name not in EXCLUDE)
        for name in dirs:
            if (Path(base) / name).is_symlink():
                raise ValueError(f"Symlinked release directory is unsupported: {Path(base) / name}")
        for name in sorted(files):
            path = Path(base) / name
            if path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Nonregular release member: {path}")
            yield path


def absolute_api_origin_files(dist: Path) -> list[str]:
    """Built files that still embed http://127.0.0.1:8766 or localhost:8766."""

    markers = (b"127.0.0.1:8766", b"localhost:8766")
    found = []
    for path in sorted(dist.rglob("*")):
        if path.is_file() and path.suffix in {".js", ".mjs", ".html", ".json", ".css"}:
            raw = path.read_bytes()
            if any(marker in raw for marker in markers):
                found.append(path.relative_to(dist).as_posix())
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-teaching", action="store_true")
    parser.add_argument("--maximum-mib", type=int, default=512)
    parser.add_argument("--build-log", type=Path, help="Existing production-build evidence; not a claim of byte equivalence.")
    args = parser.parse_args()
    if not (ROOT / "dist/server/index.js").is_file() or not (ROOT / "dist/client").is_dir():
        raise ValueError("Build the final production UI before packaging.")
    # P0-1: the UI calls only its own origin (/api through the UI gateway); a
    # build that still names an API port predates the gateway.
    stale = absolute_api_origin_files(ROOT / "dist")
    if stale:
        raise ValueError(f"The production UI still names an absolute API origin; rebuild it: {stale[:3]}")
    selected = {f"app/{name}": ROOT / name for name in FILES}
    for name in DIRECTORIES:
        for path in members(ROOT / name):
            selected[f"app/{path.relative_to(ROOT).as_posix()}"] = path
    for name in ("dist/server", "dist/client", "dist/.openai"):
        if (ROOT / name).is_dir():
            for path in members(ROOT / name):
                selected[f"app/{path.relative_to(ROOT).as_posix()}"] = path
    runtime_versions = {}
    for name in NODE_PACKAGES:
        package = ROOT / "node_modules" / name
        runtime_versions[name] = json.loads((package / "package.json").read_text())["version"]
        for path in members(package):
            selected[f"app/node_modules/{name}/{path.relative_to(package).as_posix()}"] = path
    included = []
    if args.include_teaching:
        for name in TEACHING_PACKS:
            pack = ROOT / "data-packs" / name
            manifest = json.loads((pack / "manifest.json").read_text())
            licence = manifest.get("licence") or manifest.get("license")
            if licence != "CC0-1.0":
                raise ValueError(f"Teaching pack does not declare CC0-1.0: {name} ({licence!r})")
            for role, binding in manifest.get("bindings", {}).items():
                uri = PurePosixPath(binding.get("uri", ""))
                if uri.is_absolute() or ".." in uri.parts or not uri.parts or binding.get("licence") != "CC0-1.0":
                    raise ValueError(f"Invalid CC0 teaching binding: {name}/{role}")
                path = pack / str(uri)
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(pack.resolve()):
                    raise ValueError(f"Invalid teaching source path: {name}/{role}")
                raw = path.read_bytes()
                if len(raw) != binding.get("bytes") or sha(raw) != binding.get("sha256"):
                    raise ValueError(f"Teaching binding bytes/hash changed: {name}/{role}")
            for path in members(pack):
                selected[f"app/data-packs/{name}/{path.relative_to(pack).as_posix()}"] = path
            included.append(name)
    selected["README-LINUX.md"] = ROOT / "packaging/linux-local/README.md"
    selected["install-value"] = ROOT / "packaging/linux-local/install-value"
    if args.build_log:
        selected["validation/production-build.log"] = args.build_log.resolve()
    for destination, path in selected.items():
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Required regular member missing: {destination}")
    total = sum(path.stat().st_size for path in selected.values())
    if args.maximum_mib < 1 or total > args.maximum_mib * 1024 * 1024:
        raise ValueError(f"Refusing oversized release: {total} bytes before compression")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    inventory = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="value-linux-build-", dir=args.output.parent) as temporary:
        stage = Path(temporary) / "VALUE-linux-local"
        for destination, path in sorted(selected.items()):
            raw = path.read_bytes()
            target = stage / destination; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            mode = 0o755 if path.name in {"install-value", "start-value", "stop-value", "diagnose-value"} else 0o644
            target.chmod(mode)
            inventory.append({"path": destination, "sha256": sha(raw), "bytes": len(raw), "mode": mode})
        manifest = {"schema_version": "value.linux-local-release/v1", "classification": "local_install_candidate",
                    "source_commit": head, "source_dirty_entries": dirty, "source_snapshot_sha256": sha(json.dumps(inventory, sort_keys=True).encode()),
                    "external_runtime_required": {"python": "3.10.x Linux x86-64 with installed VALUE scientific dependencies", "node": ">=22.13.0 Linux x86-64"},
                    "api_origin": args.api_origin, "prebuilt_ui_provenance": "Packaged existing dist; final build and installed-UI validation are release evidence, not inferred from this script.",
                    "node_packages": runtime_versions, "teaching_packs": included, "contains_user_state": False,
                    "scientific_release_eligible": False, "files": inventory}
        (stage / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        for destination, path in selected.items():
            if sha(path.read_bytes()) != next(row["sha256"] for row in inventory if row["path"] == destination):
                raise ValueError(f"Source changed during packaging: {path}")
        pending = args.output.with_name(args.output.name + ".pending")
        try:
            with pending.open("wb") as stream, gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as archive:
                    for path in sorted(stage.rglob("*")):
                        if path.is_file():
                            info = archive.gettarinfo(str(path), f"VALUE-linux-local/{path.relative_to(stage).as_posix()}")
                            info.uid = info.gid = 0; info.uname = info.gname = ""; info.mtime = 0
                            with path.open("rb") as content: archive.addfile(info, content)
            pending.replace(args.output)
        finally:
            pending.unlink(missing_ok=True)
    digest = sha(args.output.read_bytes())
    args.output.with_name(args.output.name + ".sha256").write_text(f"{digest}  {args.output.name}\n")
    print(json.dumps({"archive": str(args.output), "sha256": digest, "uncompressed_bytes": total, "file_count": len(inventory), "source_commit": head}))


if __name__ == "__main__":
    main()
