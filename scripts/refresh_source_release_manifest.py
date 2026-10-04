"""Deterministically refresh ``source-release-manifest.json``.

The manifest's ``include`` list is the set of repository files (tracked, or
new and not ignored) minus the patterns in
``tests/baselines/release-exclusions.txt``.  Every included file except the
manifest itself has a ``files`` entry carrying its sha256 and byte count.

* Existing entries keep their key order and ``transform`` text unless the
  file content changed, in which case ``transform`` becomes
  ``--transform`` (default: the P0 construction label).
* New files get ``{path, sha256, bytes, transform}``.
* Removed or excluded files are dropped.

``--check`` writes nothing and exits 1 when the manifest is out of date.
Run it in every commit that adds, removes or edits a file (plan 3.2, C25).
With ``--index`` the staged index defines both the file set and the content,
so a commit can be refreshed exactly while other work stays unstaged.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "source-release-manifest.json"
EXCLUSIONS = Path("tests/baselines/release-exclusions.txt")
DEFAULT_TRANSFORM = "VALUE P0 review fixes (fix/review-2026-10-04)"


def read_exclusions(root: Path) -> list[str]:
    path = root / EXCLUSIONS
    if not path.is_file():
        return []
    patterns = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def is_excluded(relative: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/"):
            if relative.startswith(pattern):
                return True
        elif fnmatch.fnmatchcase(relative, pattern):
            return True
    return False


def repository_files(root: Path) -> list[str]:
    """Tracked files plus untracked files that are not ignored, that exist."""

    completed = subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    names = {name.decode("utf-8") for name in completed.stdout.split(b"\0") if name}
    return sorted(name for name in names if (root / PurePosixPath(name)).is_file() and not (root / PurePosixPath(name)).is_symlink())


def index_files(root: Path) -> dict[str, bytes]:
    """Staged content of every regular file in the git index (``--index`` mode)."""

    listing = subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", "ls-files", "-s", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    entries: list[tuple[str, str]] = []
    for record in listing.split(b"\0"):
        if not record:
            continue
        meta, _, name = record.partition(b"\t")
        mode, blob, _stage = meta.decode("ascii").split(" ")
        if mode in {"100644", "100755"}:
            entries.append((name.decode("utf-8"), blob))
    contents: dict[str, bytes] = {}
    if not entries:
        return contents
    process = subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", "cat-file", "--batch"],
        cwd=root,
        input=b"".join(f"{blob}\n".encode("ascii") for _, blob in entries),
        check=True,
        capture_output=True,
    ).stdout
    offset = 0
    for name, _blob in entries:
        header_end = process.index(b"\n", offset)
        size = int(process[offset:header_end].split(b" ")[2])
        start = header_end + 1
        contents[name] = process[start:start + size]
        offset = start + size + 1
    return contents


def _digest(path: Path) -> tuple[str, int]:
    payload = path.read_bytes()
    return hashlib.sha256(payload).hexdigest(), len(payload)


def refreshed_manifest(
    root: Path, transform: str = DEFAULT_TRANSFORM, use_index: bool = False
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    manifest_path = root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    patterns = read_exclusions(root)
    staged = index_files(root) if use_index else None
    names = sorted(staged) if staged is not None else repository_files(root)
    include = sorted(name for name in names if not is_excluded(name, patterns))
    if MANIFEST_NAME not in include:
        include.append(MANIFEST_NAME)
        include.sort()
    previous = {entry["path"]: entry for entry in manifest.get("files", [])}
    files: list[dict[str, Any]] = []
    changes: dict[str, list[str]] = {"added": [], "removed": [], "updated": []}
    for name in include:
        if name == MANIFEST_NAME:
            continue
        if staged is not None:
            payload = staged[name]
            sha256, size = hashlib.sha256(payload).hexdigest(), len(payload)
        else:
            sha256, size = _digest(root / PurePosixPath(name))
        entry = previous.get(name)
        if entry is None:
            files.append({"path": name, "sha256": sha256, "bytes": size, "transform": transform})
            changes["added"].append(name)
            continue
        if entry.get("sha256") != sha256 or entry.get("bytes") != size:
            entry = dict(entry)
            entry["sha256"] = sha256
            entry["bytes"] = size
            entry["transform"] = transform
            changes["updated"].append(name)
        files.append(entry)
    changes["removed"] = sorted(set(previous) - {entry["path"] for entry in files})
    updated = dict(manifest)
    updated["include"] = include
    updated["files"] = files
    return updated, changes


def render(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="exit 1 if the manifest is stale; write nothing")
    parser.add_argument("--transform", default=DEFAULT_TRANSFORM)
    parser.add_argument(
        "--index",
        action="store_true",
        help="use the staged git index (paths and content) instead of the working tree",
    )
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    manifest, changes = refreshed_manifest(root, arguments.transform, arguments.index)
    text = render(manifest)
    current = (root / MANIFEST_NAME).read_text(encoding="utf-8")
    stale = text != current
    summary = {key: value for key, value in changes.items() if value}
    if arguments.check:
        print(json.dumps({"stale": stale, **summary}, indent=2, ensure_ascii=False))
        return 1 if stale else 0
    if stale:
        (root / MANIFEST_NAME).write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"written": stale, **summary}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
