"""Repackage one verified VALUE application into platform-specific local installers.

Only the installer and platform instructions differ. No dependency download,
frontend rebuild, model execution, or user-state collection occurs here.
"""
from __future__ import annotations

import argparse
from datetime import date
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging/desktop-local"
TARGETS = {
    "windows": ("win32", ["x64"], "VALUE-Windows-x64", "zip"),
    "macos": ("darwin", ["x64", "arm64"], "VALUE-macOS", "zip"),
    "linux": ("linux", ["x64"], "VALUE-Linux-x64", "tar.gz"),
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name or str(path) != name:
        raise ValueError(f"Unsafe archive path: {name!r}")
    # The common application must also extract on a default Windows filesystem.
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if any(part.endswith((".", " ")) or any(c in part for c in '<>:"|?*')
           or part.split(".", 1)[0].upper() in reserved for part in path.parts):
        raise ValueError(f"Nonportable archive path: {name!r}")
    return name


def load_application(archive: Path, expected: str):
    raw = archive.read_bytes()
    if digest(raw) != expected.lower():
        raise ValueError("The accepted input archive does not match --base-sha256.")
    members = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as bundle:
        for item in bundle:
            if not item.isfile():
                raise ValueError(f"Input contains a nonregular member: {item.name}")
            name = safe_name(item.name)
            if not name.startswith("VALUE-linux-local/") or name in members:
                raise ValueError(f"Input has an unexpected root or duplicate: {name}")
            members[name.removeprefix("VALUE-linux-local/")] = bundle.extractfile(item).read()
    manifest = json.loads(members.pop("release-manifest.json"))
    if manifest.get("schema_version") != "value.linux-local-release/v1":
        raise ValueError("Input must be the verified Linux local release.")
    listed, folded = set(), set()
    for row in manifest["files"]:
        name = safe_name(row["path"])
        if name in listed or name.casefold() in folded:
            raise ValueError(f"Duplicate or case-colliding inventory path: {name}")
        listed.add(name); folded.add(name.casefold())
        data = members.get(name)
        if data is None or len(data) != row["bytes"] or digest(data) != row["sha256"]:
            raise ValueError(f"Input inventory mismatch: {name}")
    if set(members) != listed:
        raise ValueError("Input archive contains files outside its inventory.")
    app = {name: data for name, data in members.items() if name.startswith("app/")}
    required = {"app/backend/server.py", "app/dist/server/index.js", "app/app/features/workspace/runScope.ts",
                "app/public/README.md", "app/gridform_core/application.py"}
    if not required <= app.keys():
        raise ValueError("Accepted four-role application is incomplete.")
    if any(Path(name).suffix.lower() in {".so", ".node", ".dll", ".dylib", ".exe"} for name in app):
        raise ValueError("A host-native binary needs a platform-specific payload, not this portable application.")
    return app, manifest


def zip_bytes(files, folder: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, (data, mode) in sorted(files.items()):
            info = zipfile.ZipInfo(f"{folder}/{name}", date_time=(2026, 10, 2, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return stream.getvalue()


def tar_bytes(files, folder: str) -> bytes:
    stream = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, (data, mode) in sorted(files.items()):
                info = tarfile.TarInfo(f"{folder}/{name}"); info.size = len(data)
                info.mode = mode; info.mtime = 0
                archive.addfile(info, io.BytesIO(data))
    return stream.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--base-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--release-date", type=date.fromisoformat, default=date(2026, 10, 2), help="Date used to identify new candidate filenames; prior artifacts are retained.")
    args = parser.parse_args()
    app, source = load_application(args.base, args.base_sha256)
    source_modes = {entry["path"]: entry["mode"] for entry in source["files"]}
    app_identity = digest(json.dumps({name: digest(data) for name, data in sorted(app.items())}, sort_keys=True).encode())
    control = (PACKAGING / "desktop_value.py").read_bytes()
    results = []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for target, (system, archs, folder, suffix) in TARGETS.items():
        files = {name: (data, source_modes[name]) for name, data in app.items()}
        files["installer/desktop_value.py"] = (control, 0o644)
        for path in sorted((PACKAGING / target).iterdir()):
            if not path.is_file() or path.is_symlink():
                raise ValueError(f"Unexpected platform installer member: {path}")
            mode = 0o755 if path.suffix == ".command" or path.name in {"install-value", "start-value", "diagnose-value"} else 0o644
            files[safe_name(path.name)] = (path.read_bytes(), mode)
        if len(files) == len(app) + 1:
            raise ValueError(f"No platform installer entrypoints: {target}")
        inventory = [{"path": name, "bytes": len(data), "sha256": digest(data), "mode": mode}
                     for name, (data, mode) in sorted(files.items())]
        manifest = {
            "schema_version": "value.desktop-local-release/v1",
            "classification": "local_install_candidate",
            "target_platform": system,
            "architectures": archs,
            "base_archive_sha256": args.base_sha256.lower(),
            "application_files_sha256": app_identity,
            "source_commit": source["source_commit"],
            "source_snapshot_sha256": source["source_snapshot_sha256"],
            "source_dirty_entries": source.get("source_dirty_entries", []),
            "external_runtime_required": {"python": "3.10.x with VALUE scientific dependencies", "node": ">=22.13.0; same architecture as Python"},
            "api_origin": "http://127.0.0.1:8766", "ui_origin": "http://127.0.0.1:8800",
            "teaching_packs": source.get("teaching_packs", []),
            "contains_user_state": False, "scientific_release_eligible": False,
            "prebuilt_ui_provenance": "Application files copied byte-for-byte from the SHA-verified base archive. Installed-app and platform validation are reported separately.",
            "native_platform_validation": "See the accompanying platform-validation.json delivered alongside the archives. This file is not inside this archive. Linux checks do not establish Windows/macOS execution.",
            "files": inventory,
        }
        files["release-manifest.json"] = ((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(), 0o644)
        output = args.output_dir / f"{folder}-four-role-{args.release_date.isoformat()}.{suffix}"
        raw = zip_bytes(files, folder) if suffix == "zip" else tar_bytes(files, folder)
        pending = output.with_name(output.name + ".pending"); pending.write_bytes(raw); pending.replace(output)
        checksum = digest(raw)
        output.with_name(output.name + ".sha256").write_text(f"{checksum}  {output.name}\n")
        results.append({"platform": system, "architectures": archs, "archive": output.name,
                        "sha256": checksum, "bytes": len(raw), "file_count": len(files),
                        "application_files_sha256": app_identity})
    (args.output_dir / "SHA256SUMS.txt").write_text("".join(f"{item['sha256']}  {item['archive']}\n" for item in results))
    (args.output_dir / "build-manifest.json").write_text(json.dumps({"schema_version": "value.desktop-packages/v1", "packages": results}, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
