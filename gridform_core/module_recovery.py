"""Offline self-rescue and registry probe for local modules (P0-2).

    python -m gridform_core.module_recovery verify [--modules-root DIR] [--report FILE]

``verify`` builds the workspace registry exactly as a newly started worker
would and writes a JSON report (registered IDs and quarantined entries).  It
is the out-of-process layer of the post-write check after every install or
enable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .module_quarantine import PROBE_SCHEMA
from .runtime_paths import external_modules_root


def _write(payload: dict[str, object], report: Path | None) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if report is None:
        sys.stdout.write(text)
        return
    temporary = report.with_name(report.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(report)


def command_verify(modules_root: Path, report: Path | None) -> int:
    from .v2.module_manifest import workspace_registry

    registry = workspace_registry(modules_root)
    _write({
        "schema_version": PROBE_SCHEMA,
        "modules_root": "<modules>",
        "modules": list(registry.manifests()),
        "extensions": list(registry.extension_manifests()),
        "quarantined": [entry.to_dict() for entry in registry.quarantined],
    }, report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m gridform_core.module_recovery",
        description="Inspect and repair locally installed VALUE modules without starting VALUE.",
    )
    parser.add_argument("--modules-root", type=Path, default=None,
                        help="modules directory (default: $VALUE_DATA_HOME/modules)")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="build the registry as a new worker would and report it")
    verify.add_argument("--modules-root", type=Path, default=None, dest="sub_modules_root")
    verify.add_argument("--report", type=Path, default=None, help="write the JSON report to this file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    root = getattr(arguments, "sub_modules_root", None) or arguments.modules_root or external_modules_root()
    root = Path(root).expanduser().resolve()
    if arguments.command == "verify":
        return command_verify(root, arguments.report)
    raise SystemExit(2)  # pragma: no cover - argparse rejects unknown commands


if __name__ == "__main__":
    raise SystemExit(main())
