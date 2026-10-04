"""Compare VALUE source-release members across local source trees.

The command is intentionally read-only.  It uses the source-release manifest
from the primary tree, hashes only allowlisted members, and records Git identity
when a comparison tree is a repository.  It does not decide which side wins a
conflict and it never copies, stages, commits, or deletes files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_manifest(primary: Path) -> dict[str, Any]:
    path = primary / "source-release-manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "value.source-release-manifest/v1":
        raise ValueError(f"Unsupported source-release manifest: {path}")
    return payload


def _excluded(relative: PurePosixPath, manifest: dict[str, Any]) -> bool:
    excluded_names = {str(value) for value in manifest["exclude_names"]}
    if any(part in excluded_names for part in relative.parts):
        return True
    return any(
        relative.name.endswith(str(suffix))
        for suffix in manifest["exclude_suffixes"]
    )


def _allowlisted_members(
    root: Path, manifest: dict[str, Any]
) -> tuple[dict[str, Path], list[str]]:
    members: dict[str, Path] = {}
    missing_includes: list[str] = []
    for raw in manifest["include"]:
        relative = PurePosixPath(str(raw))
        path = root.joinpath(*relative.parts)
        if not path.exists():
            missing_includes.append(relative.as_posix())
            continue
        candidates: Iterable[Path] = path.rglob("*") if path.is_dir() else (path,)
        for candidate in candidates:
            if not candidate.is_file():
                continue
            member = PurePosixPath(candidate.relative_to(root).as_posix())
            if not _excluded(member, manifest):
                members[member.as_posix()] = candidate
    return members, sorted(missing_includes)


def _run_git(root: Path, *arguments: str) -> str | None:
    if not (root / ".git").exists():
        return None
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        return None
    return completed.stdout.strip()


def _root_inventory(
    label: str, root: Path, manifest: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    root = root.resolve()
    members, missing = _allowlisted_members(root, manifest)
    hashes = {name: _sha256(path) for name, path in sorted(members.items())}
    tracked_text = _run_git(root, "ls-files")
    tracked = (
        sorted(
            line.strip().replace("\\", "/")
            for line in tracked_text.splitlines()
            if line.strip()
        )
        if tracked_text is not None
        else []
    )
    status = _run_git(root, "status", "--short")
    remotes = _run_git(root, "remote", "-v")
    metadata = {
        "label": label,
        "root": str(root.resolve()),
        "exists": root.exists(),
        "release_member_count": len(hashes),
        "release_member_bytes": sum(path.stat().st_size for path in members.values()),
        "missing_manifest_includes": missing,
        "git": {
            "available": tracked_text is not None,
            "head": _run_git(root, "rev-parse", "HEAD"),
            "branch": _run_git(root, "branch", "--show-current"),
            "tracked_count": len(tracked),
            "status": status.splitlines() if status else [],
            "remotes": remotes.splitlines() if remotes else [],
        },
    }
    return metadata, hashes


def compare(primary: Path, candidates: list[tuple[str, Path]]) -> dict[str, Any]:
    manifest = _load_manifest(primary)
    primary_metadata, primary_hashes = _root_inventory(
        "primary", primary, manifest
    )
    comparisons: list[dict[str, Any]] = []
    for label, root in candidates:
        metadata, hashes = _root_inventory(label, root, manifest)
        primary_names = set(primary_hashes)
        candidate_names = set(hashes)
        identical = sorted(
            name
            for name in primary_names & candidate_names
            if primary_hashes[name] == hashes[name]
        )
        different = sorted(
            name
            for name in primary_names & candidate_names
            if primary_hashes[name] != hashes[name]
        )
        comparisons.append(
            {
                "candidate": metadata,
                "identical_count": len(identical),
                "different_count": len(different),
                "primary_only_count": len(primary_names - candidate_names),
                "candidate_only_count": len(candidate_names - primary_names),
                "different": different,
                "primary_only": sorted(primary_names - candidate_names),
                "candidate_only": sorted(candidate_names - primary_names),
            }
        )
    return {
        "schema_version": "value.release-root-comparison/v1",
        "manifest_schema": manifest["schema_version"],
        "primary": primary_metadata,
        "comparisons": comparisons,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="Comparison root. May be supplied more than once.",
    )
    parser.add_argument("--json-output", type=Path)
    arguments = parser.parse_args()
    candidates: list[tuple[str, Path]] = []
    for raw in arguments.candidate:
        if "=" not in raw:
            parser.error("--candidate must use LABEL=PATH")
        label, value = raw.split("=", 1)
        candidates.append((label, Path(value)))
    report = compare(arguments.primary, candidates)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.json_output:
        arguments.json_output.parent.mkdir(parents=True, exist_ok=True)
        arguments.json_output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
