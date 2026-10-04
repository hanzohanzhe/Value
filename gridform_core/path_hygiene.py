"""Syntax-aware detection of developer-machine absolute paths.

Python source is tokenized and string literals are decoded before inspection.
That distinction matters: a raw drive-path literal remains a path, while an
escaped newline in a normal string decodes to a control character and is not one.
"""

from __future__ import annotations

import ast
import io
import json
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_WINDOWS_DRIVE = re.compile(
    r"(?<![A-Za-z0-9])(?P<path>[A-Za-z]:[\\/][^\x00-\x1f\r\n<>\"|?*]+)"
)
_WINDOWS_UNC = re.compile(
    r"(?P<path>" + r"\\\\" + r"[^\\/\s<>\"|?*]+[\\/][^\x00-\x1f\r\n<>\"|?*]+)"
)
_POSIX_HOME = re.compile(
    r"(?<![A-Za-z0-9:])(?P<path>/(?:home|Users)/[^/\s]+(?:/[^\s'\"<>]*)?)"
)
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)


@dataclass(frozen=True)
class AbsolutePathFinding:
    kind: str
    value: str
    line: int


def _matches(value: str, *, line: int) -> Iterable[AbsolutePathFinding]:
    url_spans = [match.span() for match in _URL.finditer(value)]
    for label, pattern in (
        ("windows_drive", _WINDOWS_DRIVE),
        ("windows_unc", _WINDOWS_UNC),
        ("posix_home", _POSIX_HOME),
    ):
        for match in pattern.finditer(value):
            if any(start <= match.start() < end for start, end in url_spans):
                continue
            yield AbsolutePathFinding(
                kind=label,
                value=match.group("path").rstrip(".,;:)]"),
                line=line + value.count("\n", 0, match.start()),
            )


def _python_findings(text: str) -> list[AbsolutePathFinding]:
    findings: list[AbsolutePathFinding] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type != tokenize.STRING:
                continue
            try:
                decoded = ast.literal_eval(token.string)
            except (SyntaxError, ValueError):
                continue
            if isinstance(decoded, bytes):
                decoded = decoded.decode("utf-8", errors="replace")
            if isinstance(decoded, str):
                findings.extend(_matches(decoded, line=token.start[0]))
    except (IndentationError, tokenize.TokenError):
        # Invalid source is handled by compilation tests; do not reinterpret it
        # as raw text and introduce escape-sequence false positives here.
        return []
    return findings


def _json_strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _json_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _json_strings(key)
            yield from _json_strings(item)


def find_absolute_paths(data: bytes, suffix: str) -> list[AbsolutePathFinding]:
    """Return plausible absolute paths, decoding structured string literals."""

    text = data.decode("utf-8", errors="replace")
    normalized_suffix = suffix.lower()
    if normalized_suffix == ".py":
        return _python_findings(text)
    if normalized_suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            findings: list[AbsolutePathFinding] = []
            for value in _json_strings(payload):
                findings.extend(_matches(value, line=1))
            return findings
    findings = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        findings.extend(_matches(line, line=line_number))
    return findings


def scan_path(path: Path) -> list[AbsolutePathFinding]:
    return find_absolute_paths(path.read_bytes(), path.suffix)
