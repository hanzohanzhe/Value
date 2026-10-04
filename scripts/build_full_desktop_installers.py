"""Assemble offline VALUE installers from a verified app and private runtimes.

This step never downloads dependencies, rebuilds the UI, or collects user state.
prepare_private_runtimes.py produces the separately audited runtime inputs.
"""
from __future__ import annotations

import argparse
from datetime import date
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tarfile
import tempfile
import zipfile

from build_desktop_installers import load_application, safe_name

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "linux-x64": ("linux", "x64", "linux", "VALUE-Linux-x64", "tar.gz"),
    "windows-x64": ("win32", "x64", "windows", "VALUE-Windows-x64", "zip"),
    "macos-x64": ("darwin", "x64", "macos", "VALUE-macOS-Intel", "zip"),
    "macos-arm64": ("darwin", "arm64", "macos", "VALUE-macOS-AppleSilicon", "zip"),
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(root, *, case_insensitive=True):
    rows, folded = [], set()
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError(f"Runtime must contain only regular files/directories: {path}")
        for name in sorted(files):
            path = Path(directory) / name
            relative = safe_name(path.relative_to(root).as_posix())
            key = relative.casefold() if case_insensitive else relative
            if key in folded:
                raise ValueError(f"Case-colliding member: {relative}")
            folded.add(key)
            if not path.is_file() or path.suffix in {".pyc", ".pyo"}:
                raise ValueError(f"Unexpected generated/nonregular file: {path}")
            if relative.split("/", 1)[0] in {"state", "logs", "runs", "results"}:
                raise ValueError(f"User state cannot enter a release: {relative}")
            rows.append({"path": relative, "bytes": path.stat().st_size,
                         "sha256": sha(path), "mode": stat.S_IMODE(path.stat().st_mode)})
    return sorted(rows, key=lambda row: row["path"])


def pack(stage, destination, folder, extension, release_date):
    pending = destination.with_name(destination.name + ".pending")
    try:
        if extension == "zip":
            with zipfile.ZipFile(pending, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for path in sorted(stage.rglob("*")):
                    if path.is_file():
                        info = zipfile.ZipInfo(f"{folder}/{path.relative_to(stage).as_posix()}",
                                               (release_date.year, release_date.month, release_date.day, 0, 0, 0))
                        info.create_system = 3
                        info.external_attr = (stat.S_IFREG | stat.S_IMODE(path.stat().st_mode)) << 16
                        info.compress_type = zipfile.ZIP_DEFLATED
                        with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                            shutil.copyfileobj(source, target, length=1024 * 1024)
        else:
            with pending.open("wb") as stream, gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as archive:
                    for path in sorted(stage.rglob("*")):
                        if path.is_file():
                            info = archive.gettarinfo(str(path), f"{folder}/{path.relative_to(stage).as_posix()}")
                            info.uid = info.gid = 0
                            info.uname = info.gname = ""
                            info.mtime = 0
                            with path.open("rb") as source:
                                archive.addfile(info, source)
        pending.replace(destination)
    finally:
        pending.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--base-sha256", required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target", action="append", choices=TARGETS)
    parser.add_argument("--release-date", type=date.fromisoformat, required=True)
    parser.add_argument("--revision", default="rc1")
    args = parser.parse_args()
    if not args.revision.isalnum():
        parser.error("--revision must contain only letters and digits")
    app, base = load_application(args.base, args.base_sha256)
    app_identity = hashlib.sha256(json.dumps({name: hashlib.sha256(raw).hexdigest()
                                            for name, raw in sorted(app.items())}, sort_keys=True).encode()).hexdigest()
    modes = {row["path"]: row["mode"] for row in base["files"]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for target in args.target or TARGETS:
        system, arch, platform_folder, folder, suffix = TARGETS[target]
        runtime_root = args.runtime_root / target
        provenance = json.loads((runtime_root / "runtime-provenance.json").read_text("utf-8"))
        # Refuse a mislabelled runtime before assigning a platform to the archive.
        if provenance.get("target") != target:
            raise ValueError(f"Runtime provenance target differs: {target}")
        runtime_inventory_path = runtime_root / "runtime-inventory.json"
        if sha(runtime_inventory_path) != provenance.get("runtime_inventory_sha256"):
            raise ValueError(f"Prepared runtime inventory identity differs: {target}")
        prepared_inventory = json.loads(runtime_inventory_path.read_text("utf-8"))
        actual_runtime = inventory(runtime_root / "runtime", case_insensitive=system != "linux")
        for row in actual_runtime:
            row["path"] = "runtime/" + row["path"]
        if actual_runtime != sorted(prepared_inventory, key=lambda row: row["path"]):
            raise ValueError(f"Prepared runtime has changed after dependency/source verification: {target}")
        with tempfile.TemporaryDirectory(prefix=".value-full-build-", dir=args.output_dir) as temporary:
            stage = Path(temporary)
            for name, raw in app.items():
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                mode = modes[name]
                path.chmod(int(mode, 8) if isinstance(mode, str) else mode)
            # Inventory first so copytree cannot silently dereference input links.
            shutil.copytree(runtime_root / "runtime", stage / "runtime", symlinks=True)
            shutil.copy2(runtime_root / "runtime-provenance.json", stage / "runtime-provenance.json")
            shutil.copy2(runtime_inventory_path, stage / "runtime-inventory.json")
            license_inventory = runtime_root / "runtime-licenses.json"
            if sha(license_inventory) != provenance.get("runtime_licenses_sha256"):
                raise ValueError(f"Runtime licence inventory identity differs: {target}")
            shutil.copy2(license_inventory, stage / "runtime-licenses.json")
            (stage / "installer").mkdir()
            shutil.copy2(ROOT / "packaging/desktop-local/desktop_value.py", stage / "installer/desktop_value.py")
            for path in sorted((ROOT / "packaging/full-local" / platform_folder).iterdir()):
                if not path.is_file() or path.is_symlink():
                    raise ValueError(f"Unexpected installer input: {path}")
                copied = stage / path.name
                shutil.copy2(path, copied)
                copied.chmod(0o755 if path.suffix == ".command" or path.name in {"install-value", "start-value", "diagnose-value"} else 0o644)
            runtimes = {"python": "runtime/python/python.exe" if system == "win32" else "runtime/python/bin/python3.10",
                        "node": "runtime/node/node.exe" if system == "win32" else "runtime/node/bin/node"}
            for name in runtimes.values():
                if not (stage / name).is_file():
                    raise ValueError(f"Private runtime entry point missing: {name}")
            members = inventory(stage, case_insensitive=system != "linux")
            if [row for row in members if row["path"].startswith("runtime/")] != actual_runtime:
                raise ValueError(f"Runtime changed during copying: {target}")
            manifest = {
                "schema_version": "value.desktop-local-release/v1",
                "classification": "offline_full_install_candidate",
                "release_id": f"{args.release_date.isoformat()}-{args.revision}",
                "target_platform": system, "architectures": [arch],
                "base_archive_sha256": args.base_sha256.lower(),
                "application_files_sha256": app_identity,
                "source_commit": base["source_commit"],
                "source_snapshot_sha256": base["source_snapshot_sha256"],
                "source_dirty_entries": base.get("source_dirty_entries", []),
                "bundled_runtimes": runtimes, "external_runtime_required": False,
                "internet_required_for_install_or_teaching": False,
                "runtime_provenance_sha256": sha(stage / "runtime-provenance.json"),
                "api_origin": "http://127.0.0.1:8766", "ui_origin": "http://127.0.0.1:8800",
                "teaching_packs": base["teaching_packs"],
                "contains_user_state": False, "scientific_release_eligible": False,
                "prebuilt_ui_provenance": "Application copied byte-for-byte from the SHA-verified accepted base; private runtimes and installation controller are separately inventoried.",
                "native_platform_validation": "See accompanying platform-validation.json; assembling an archive does not establish native execution.",
                "files": members,
            }
            (stage / "release-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
            output = args.output_dir / f"{folder}-Full-{args.release_date.isoformat()}-{args.revision}.{suffix}"
            if output.exists():
                raise ValueError(f"Refusing to replace an existing release; select a new revision or output folder: {output}")
            pack(stage, output, folder, suffix, args.release_date)
            checksum = sha(output)
            output.with_name(output.name + ".sha256").write_text(f"{checksum}  {output.name}\n", "utf-8")
            row = {"target": target, "platform": system, "architectures": [arch],
                   "archive": output.name, "sha256": checksum, "bytes": output.stat().st_size,
                   "file_count": len(members) + 1, "uncompressed_bytes": sum(item["bytes"] for item in members),
                   "application_files_sha256": app_identity,
                   "release_manifest_sha256": sha(stage / "release-manifest.json"),
                   "bundled_runtimes": runtimes, "external_runtime_required": False,
                   "runtime_provenance_sha256": manifest["runtime_provenance_sha256"]}
            results.append(row)
            print(json.dumps(row), flush=True)
    summary_path = args.output_dir / "build-manifest.json"
    existing = json.loads(summary_path.read_text()) if summary_path.exists() else {"schema_version": "value.full-desktop-packages/v1", "packages": []}
    targets = {item["target"] for item in results}
    existing["packages"] = sorted([item for item in existing["packages"] if item["target"] not in targets] + results, key=lambda row: row["target"])
    summary_path.write_text(json.dumps(existing, indent=2) + "\n", "utf-8")
    (args.output_dir / "SHA256SUMS.txt").write_text("".join(f"{row['sha256']}  {row['archive']}\n" for row in existing["packages"]), "utf-8")


if __name__ == "__main__":
    main()
