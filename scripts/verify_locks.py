"""Verify the accepted interpreter and installed versions against a lock file."""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")


def pins(path: Path, seen: set[Path] | None = None) -> dict[str, str]:
    seen = seen or set()
    path = path.resolve()
    if path in seen:
        return {}
    seen.add(path)
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            values.update(pins(path.parent / line[3:].strip(), seen))
            continue
        match = PIN.fullmatch(line)
        if not match:
            raise ValueError(f"Unsupported lock entry in {path.name}: {line}")
        values[match.group(1).lower().replace("_", "-")] = match.group(2)
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("lock", type=Path, nargs="?", default=ROOT / "requirements" / "value-all-py310.lock")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 10):
        raise SystemExit(f"FAIL: lock requires Python 3.10; found {sys.version.split()[0]}")
    mismatches = []
    for package, expected in sorted(pins(args.lock).items()):
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            actual = "not installed"
        if actual != expected:
            mismatches.append(f"{package}: expected {expected}, found {actual}")
    if mismatches:
        raise SystemExit("LOCK MISMATCH\n" + "\n".join(mismatches))
    print(f"LOCK VERIFIED: {args.lock} ({len(pins(args.lock))} distributions)")


if __name__ == "__main__":
    main()
