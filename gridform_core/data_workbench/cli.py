"""Thin command adapter over a Data Workbench service."""

from __future__ import annotations

import argparse
import json
from typing import Sequence


_COMMANDS = (
    "discover",
    "fetch",
    "compile",
    "validate",
    "candidates",
    "promote",
    "sources",
    "diff",
    "report",
    "export",
    "freshness",
)


def command_names() -> tuple[str, ...]:
    return _COMMANDS


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="force-data", description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    for name in _COMMANDS:
        command = commands.add_parser(name)
        command.add_argument("identifier", nargs="?")
        command.add_argument("--request-json")
    return value


def execute_command(service: object, argv: Sequence[str]) -> dict[str, object]:
    args = parser().parse_args(list(argv))
    method = getattr(service, args.command)
    request = json.loads(args.request_json) if args.request_json else None
    if request is not None and not isinstance(request, dict):
        raise ValueError("CLI request JSON must be an object")
    if args.identifier is not None and request is not None:
        return method(args.identifier, request)
    if args.identifier is not None:
        return method(args.identifier)
    if request is not None:
        return method(request)
    return method()
