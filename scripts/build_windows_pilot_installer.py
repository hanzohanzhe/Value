"""Build the self-contained, current-user VALUE 101 Windows installer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_URL = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip"
NODE_URL = "https://nodejs.org/dist/v22.22.0/node-v22.22.0-win-x64.zip"
PYTHON_SHA256 = "608619f8619075629c9c69f361352a0da6ed7e62f83a0e19c63e0ea32eb7629d"
NODE_SHA256 = "c97fa376d2becdc8863fcd3ca2dd9a83a9f3468ee7ccf7a6d076ec66a645c77a"
PYTHON_NAME = "python-3.10.11-embed-amd64.zip"
NODE_NAME = "node-v22.22.0-win-x64.zip"
LOCK = ROOT / "requirements" / "value-all-py310.lock"
OUTPUT_NAME = "VALUE-Setup.exe"
PAYLOAD_MANIFEST_NAME = "VALUE-PAYLOAD-MANIFEST.json"
RUNTIME_POLICY = ROOT / "packaging" / "windows-pilot" / "runtime-payload-policy.json"
RUNTIME_NODE_PACKAGES = ("vinext", "react", "react-dom", "react-server-dom-webpack", "scheduler")
BUNDLED_DATA_PACKS = (
    "value-101-baseline-v1",
    "value-101-network-v1",
)
FRONTEND_DIST_DIRECTORIES = ("server", "client", ".openai")
RELEASE_DOCUMENTS = (
    ("VALUE_101_guide.pdf", "START-HERE-VALUE-101-Guide.pdf"),
    ("VALUE_101_TO_VALUE_UK_guide.pdf", "START-HERE-VALUE-101-TO-VALUE-UK-Guide.pdf"),
    ("VALUE_Methodology.pdf", "VALUE-Methodology.pdf"),
)
EXTRA_RELEASE_FILES = (
    "packaging/windows-pilot/ValueInstaller.cs",
    "packaging/windows-pilot/ValueInstallerWindow.cs",
    "packaging/windows-pilot/product.json",
    "packaging/windows-pilot/runtime-payload-policy.json",
    "packaging/windows-pilot/start-portable.ps1",
    "docs/tutorial/VALUE_101.md",
    "docs/tutorial/VALUE_101_TO_VALUE_UK.md",
    "docs/tutorial/VALUE_101_QUICK_CARD.md",
    "docs/methodology/VALUE_METHODOLOGY.md",
    "docs/tutorial/JOHN_PILOT_RUNBOOK.md",
    "scripts/build_windows_pilot_installer.py",
    "scripts/start-portable-local.ps1",
    "scripts/check-value-101.ps1",
    "tests/test_windows_pilot_installer.py",
)


def SHA256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_inventory_identity(
    members: list[dict[str, object]],
) -> tuple[str, int]:
    records = [
        dict(item)
        for item in members
        if str(item.get("path") or "").startswith(("runtime/", "node_modules/"))
    ]
    records.sort(key=lambda item: str(item["path"]))
    raw = (
        json.dumps(records, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), len(records)


def checked_download(url: str, target: Path, expected: str) -> None:
    if not target.exists():
        urllib.request.urlretrieve(url, target)
    actual = SHA256(target)
    if actual.lower() != expected.lower():
        raise RuntimeError(f"SHA256 mismatch for {target.name}: {actual}")


def repository_local_only_members(source: Path) -> set[str]:
    manifest_path = source / "source-release-manifest.json"
    if not manifest_path.is_file():
        return set()
    manifest = json.loads(manifest_path.read_text("utf-8"))
    excluded: set[str] = set()
    for item in manifest.get("local_only_source_content", []):
        if item.get("distribution") == "repository-local-only":
            member = str(item.get("repository_path", "")).replace("\\", "/").lstrip("/")
            if member:
                excluded.add(member)
    return excluded


def source_release_includes(source: Path) -> tuple[str, ...]:
    manifest_path = source / "source-release-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("source-release-manifest.json is required for installer assembly")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    includes = tuple(
        str(item).replace("\\", "/").strip("/")
        for item in manifest.get("include", [])
        if str(item).strip("/\\")
    )
    if not includes:
        raise RuntimeError("The source-release manifest has no allowlisted members")
    return includes


def is_allowlisted_release_member(name: str, includes: tuple[str, ...]) -> bool:
    normalised = name.replace("\\", "/").lstrip("/")
    return any(
        normalised == prefix or normalised.startswith(prefix + "/")
        for prefix in includes
    )


def copy_application(
    source: Path,
    app: Path,
    git_executable: Path,
    *,
    copy_dist: bool = True,
    copy_guide: bool = True,
) -> None:
    safe_source = source.resolve().as_posix()
    tracked = subprocess.run(
        [str(git_executable), "-c", f"safe.directory={safe_source}", "ls-files", "-z"],
        cwd=source,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    deleted = subprocess.run(
        [
            str(git_executable),
            "-c",
            f"safe.directory={safe_source}",
            "diff",
            "--name-only",
            "--diff-filter=D",
            "HEAD",
            "-z",
        ],
        cwd=source,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    deleted_members = {name for name in deleted if name}
    local_only_members = repository_local_only_members(source)
    release_includes = source_release_includes(source)
    members = {
        name for name in tracked
        if (
            name
            and name not in deleted_members
            and name not in local_only_members
            and is_allowlisted_release_member(name, release_includes)
        )
    }
    members.update(EXTRA_RELEASE_FILES)
    for name in sorted(members):
        if name.startswith("data-packs/"):
            pack_id = name.split("/", 2)[1]
            if pack_id not in BUNDLED_DATA_PACKS:
                continue
        item = source / name
        if not item.is_file():
            raise RuntimeError(f"Release member is missing: {name}")
        destination = app / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
    if copy_dist:
        for directory in FRONTEND_DIST_DIRECTORIES:
            frontend_source = source / "dist" / directory
            if frontend_source.is_dir():
                shutil.copytree(frontend_source, app / "dist" / directory)
    if not copy_guide:
        return
    for source_name, target_name in RELEASE_DOCUMENTS:
        document = source / "output" / "pdf" / source_name
        if not document.is_file():
            raise RuntimeError(f"The release PDF has not been generated: {source_name}")
        shutil.copy2(document, app / target_name)


def prepare_python(python_zip: Path, app: Path, builder_python: Path) -> None:
    target = app / "runtime" / "python"
    target.mkdir(parents=True)
    with zipfile.ZipFile(python_zip) as archive:
        archive.extractall(target)
    pth = target / "python310._pth"
    pth.write_text("python310.zip\n.\n..\\..\nLib\\site-packages\nimport site\n", encoding="ascii")
    site = target / "Lib" / "site-packages"
    site.mkdir(parents=True)
    subprocess.run(
        [str(builder_python), "-m", "pip", "install", "--requirement", str(LOCK),
         "--target", str(site), "--platform", "win_amd64", "--python-version", "3.10",
         "--implementation", "cp", "--abi", "cp310", "--only-binary=:all:", "--no-deps", "--no-compile"],
        check=True,
    )
    generated_commands = site / "bin"
    if generated_commands.is_dir():
        shutil.rmtree(generated_commands)
    for record in sorted(site.glob("*.dist-info/RECORD")):
        stable_lines = [
            line
            for line in record.read_text("utf-8").splitlines()
            if not line.startswith("../../bin/")
        ]
        record.write_text(
            "\n".join(stable_lines) + "\n", "utf-8", newline=""
        )


def prepare_node(node_zip: Path, app: Path) -> None:
    runtime = app / "runtime"
    with zipfile.ZipFile(node_zip) as archive:
        archive.extractall(runtime)
    extracted = runtime / "node-v22.22.0-win-x64"
    extracted.rename(runtime / "node")
    modules = app / "node_modules"
    modules.mkdir()
    for package in RUNTIME_NODE_PACKAGES:
        source = ROOT / "node_modules" / package
        if not source.is_dir():
            raise RuntimeError(f"Required frontend runtime package is missing: {package}")
        shutil.copytree(source, modules / package)


def build_payload(
    source: Path,
    work: Path,
    python_zip: Path,
    node_zip: Path,
    builder_python: Path,
    git_executable: Path,
    runtime_policy_candidate: Path | None = None,
) -> Path:
    app = work / "app"
    copy_application(source, app, git_executable)
    prepare_python(python_zip, app, builder_python)
    prepare_node(node_zip, app)
    if not (app / "dist" / "server" / "index.js").is_file():
        raise RuntimeError("The production frontend build is missing.")
    if not (app / "THIRD_PARTY_NOTICES.md").is_file():
        raise RuntimeError("THIRD_PARTY_NOTICES.md is required in the installer.")
    members = []
    for path in sorted(app.rglob("*")):
        if path.is_file():
            members.append({
                "path": path.relative_to(app).as_posix(),
                "sha256": SHA256(path),
                "bytes": path.stat().st_size,
            })
    if not RUNTIME_POLICY.is_file():
        raise RuntimeError("The source-controlled runtime payload policy is missing")
    runtime_policy = json.loads(RUNTIME_POLICY.read_text("utf-8"))
    runtime_digest, runtime_count = runtime_inventory_identity(members)
    if runtime_policy_candidate is not None:
        runtime_policy_candidate.write_text(
            json.dumps(
                {
                    "schema_version": "value.101-runtime-payload-candidate/v1",
                    "runtime_inventory_sha256": runtime_digest,
                    "runtime_member_count": runtime_count,
                    "members": [
                        item
                        for item in members
                        if str(item.get("path") or "").startswith(
                            ("runtime/", "node_modules/")
                        )
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            "utf-8",
            newline="",
        )
    if (
        runtime_policy.get("schema_version")
        != "value.101-runtime-payload-policy/v1"
        or runtime_policy.get("runtime_inventory_sha256") != runtime_digest
        or runtime_policy.get("runtime_member_count") != runtime_count
    ):
        raise RuntimeError(
            "Assembled private runtimes differ from the reviewed runtime payload policy: "
            f"expected_sha256={runtime_policy.get('runtime_inventory_sha256')}; "
            f"actual_sha256={runtime_digest}; "
            f"expected_members={runtime_policy.get('runtime_member_count')}; "
            f"actual_members={runtime_count}"
        )
    payload_manifest = {
        "schema_version": "value.101-installer-payload/v1",
        "build_inputs": {
            "python_archive_sha256": PYTHON_SHA256,
            "node_archive_sha256": NODE_SHA256,
            "python_lock_sha256": SHA256(LOCK),
        },
        "runtime_inventory_sha256": runtime_digest,
        "runtime_member_count": runtime_count,
        "members": members,
    }
    (app / PAYLOAD_MANIFEST_NAME).write_text(
        json.dumps(payload_manifest, indent=2, sort_keys=True) + "\n",
        "utf-8",
        newline="",
    )
    payload = work / "value-payload.zip"
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(app).as_posix())
    return payload


def compile_installer(payload: Path, output: Path) -> None:
    windows_root = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if not windows_root:
        raise RuntimeError("The Windows system directory is unavailable.")
    framework = Path(windows_root) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    if not framework.is_file():
        raise RuntimeError("The Windows .NET Framework C# compiler is unavailable.")
    subprocess.run([
        str(framework), "/nologo", "/target:winexe", "/optimize+", f"/out:{output}",
        "/reference:System.IO.Compression.dll", "/reference:System.IO.Compression.FileSystem.dll",
        "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll",
        f"/resource:{payload},value-payload.zip",
        str(ROOT / "packaging" / "windows-pilot" / "ValueInstaller.cs"),
        str(ROOT / "packaging" / "windows-pilot" / "ValueInstallerWindow.cs"),
    ], check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--builder-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--git", type=Path, default=Path(shutil.which("git") or "git"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    python_zip, node_zip = args.cache_dir / PYTHON_NAME, args.cache_dir / NODE_NAME
    checked_download(PYTHON_URL, python_zip, PYTHON_SHA256)
    checked_download(NODE_URL, node_zip, NODE_SHA256)
    with tempfile.TemporaryDirectory(prefix="value-windows-installer-") as temporary:
        payload = build_payload(
            ROOT,
            Path(temporary),
            python_zip,
            node_zip,
            args.builder_python,
            args.git,
            args.output_dir / "runtime-payload-candidate.json",
        )
        output = args.output_dir / OUTPUT_NAME
        compile_installer(payload, output)
    checksum = SHA256(output)
    (args.output_dir / f"{OUTPUT_NAME}.sha256.txt").write_text(f"{checksum}  {OUTPUT_NAME}\n", "ascii")
    for source_name, target_name in RELEASE_DOCUMENTS:
        shutil.copy2(ROOT / "output" / "pdf" / source_name, args.output_dir / target_name)
    print(output)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
