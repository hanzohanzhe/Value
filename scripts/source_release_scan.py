"""Build and audit the deterministic full VALUE source/website release set."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "source-release-manifest.json"


def _load_manifest() -> dict[str, object]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "value.source-release-manifest/v1":
        raise ValueError("Unsupported source-release manifest schema")
    return payload


def _excluded(relative: PurePosixPath, manifest: dict[str, object]) -> bool:
    if any(part in set(manifest["exclude_names"]) for part in relative.parts):
        return True
    return any(relative.name.endswith(str(suffix)) for suffix in manifest["exclude_suffixes"])


def release_members(root: Path = ROOT) -> tuple[Path, ...]:
    manifest = _load_manifest()
    members: dict[str, Path] = {}
    missing = []
    for raw in manifest["include"]:
        relative = PurePosixPath(str(raw))
        path = root.joinpath(*relative.parts)
        if not path.exists():
            missing.append(relative.as_posix())
            continue
        candidates: Iterable[Path] = path.rglob("*") if path.is_dir() else (path,)
        for candidate in candidates:
            if not candidate.is_file():
                continue
            member = PurePosixPath(candidate.relative_to(root).as_posix())
            if _excluded(member, manifest):
                continue
            members[member.as_posix()] = candidate
    if missing:
        raise ValueError("Missing required source-release paths: " + ", ".join(sorted(missing)))
    return tuple(members[key] for key in sorted(members))


def _git_tracking(root: Path, members: tuple[Path, ...]) -> dict[str, object]:
    try:
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", "ls-files"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        tracked = {line.strip().replace("\\", "/") for line in completed.stdout.splitlines()}
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"available": False, "github_checkout_ready": False, "error": str(exc)}
    member_names = {path.relative_to(root).as_posix() for path in members}
    untracked = sorted(member_names - tracked)
    return {
        "available": True,
        "tracked_files": len(tracked),
        "release_member_files": len(member_names),
        "untracked_release_members": untracked,
        "untracked_release_member_count": len(untracked),
        "github_checkout_ready": not untracked,
        "note": "Staging and committing are explicit maintainer actions and are never performed by this scanner.",
    }


def _local_only_content_members(
    root: Path,
    members: tuple[Path, ...],
    manifest: dict[str, object],
) -> list[str]:
    policies = tuple(manifest.get("local_only_source_content") or ())
    forbidden_content_hashes = {
        str(policy["content_sha256"])
        for policy in policies
        if isinstance(policy, dict) and policy.get("content_sha256")
    }
    forbidden_declared_inputs = {
        str(policy["declared_input_sha256"])
        for policy in policies
        if isinstance(policy, dict) and policy.get("declared_input_sha256")
    }
    violations: list[str] = []
    for path in members:
        raw = path.read_bytes()
        content = gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw
        content_sha256 = hashlib.sha256(content).hexdigest()
        declared_input_sha256 = None
        if content_sha256 not in forbidden_content_hashes:
            try:
                payload = json.loads(content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                declared_input_sha256 = payload.get("source_sha256")
        if (
            content_sha256 in forbidden_content_hashes
            or (isinstance(declared_input_sha256, str) and declared_input_sha256 in forbidden_declared_inputs)
        ):
            violations.append(path.relative_to(root).as_posix())
    return sorted(violations)


def scan(root: Path = ROOT) -> dict[str, object]:
    manifest = _load_manifest()
    errors: list[str] = []
    try:
        members = release_members(root)
    except ValueError as exc:
        members = ()
        errors.append(str(exc))
    names = [path.relative_to(root).as_posix() for path in members]
    forbidden = tuple(str(value).rstrip("/") for value in manifest["forbidden_roots"])
    included_forbidden = sorted(
        name for name in names
        if any(name == prefix or name.startswith(prefix + "/") for prefix in forbidden)
    )
    if included_forbidden:
        errors.append("Forbidden release members: " + ", ".join(included_forbidden[:20]))
    local_only_content_members = _local_only_content_members(root, members, manifest)
    if local_only_content_members:
        errors.append(
            "Local-only content entered the source release: "
            + ", ".join(local_only_content_members[:20])
        )
    package_manager = json.loads((root / "package.json").read_text(encoding="utf-8")).get(
        "packageManager"
    )
    if not str(package_manager).startswith("npm@"):
        errors.append("package.json does not name npm as the frontend lock authority")
    contradictory_locks = [
        name for name in ("pnpm-lock.yaml", "yarn.lock") if (root / name).exists()
    ]
    if contradictory_locks:
        errors.append("Contradictory frontend locks remain: " + ", ".join(contradictory_locks))
    return {
        "schema_version": "value.source-release-scan/v1",
        "passed": not errors,
        "errors": errors,
        "member_count": len(members),
        "uncompressed_bytes": sum(path.stat().st_size for path in members),
        "forbidden_members": included_forbidden,
        "local_only_content_members": local_only_content_members,
        "frontend_lock_authority": manifest["frontend_lock_authority"],
        "separate_products": manifest["separate_products"],
        "git_tracking": _git_tracking(root, members),
    }


def build_zip(destination: Path, root: Path = ROOT) -> dict[str, object]:
    report = scan(root)
    if not report["passed"]:
        raise ValueError("Source-release scan failed: " + "; ".join(report["errors"]))
    members = release_members(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in members:
            name = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    temporary.replace(destination)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return {**report, "archive": str(destination), "archive_bytes": destination.stat().st_size, "sha256": digest}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--build-zip", type=Path)
    arguments = parser.parse_args()
    report = build_zip(arguments.build_zip) if arguments.build_zip else scan()
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if arguments.json_output:
        arguments.json_output.parent.mkdir(parents=True, exist_ok=True)
        arguments.json_output.write_text(text, encoding="utf-8")
    print(text)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
