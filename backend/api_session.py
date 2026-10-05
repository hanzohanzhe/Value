"""Per-port session token of the VALUE local API (P0-1, finding F5-01).

The backend generates one random token per process (``new_token``) after it
has bound its port and publishes it in ``<VALUE_DATA_HOME>/runtime/
api-session-<port>.json`` (directory 0700, file 0600, written atomically).
The token lives in exactly three places: the backend's memory, that file and
the memory of the UI gateway (``scripts/value-ui-gateway.mjs``), which reads
the file and injects the ``X-VALUE-Session`` header server side.  Launchers
never see or pass the token, it never appears on a command line, in a worker
environment or on stdout.

Command-line clients and tests that talk to the API directly use
``authorized_headers(state_root, port)``.

The session file is transient process state: it is never part of a Run,
an export, an archived workspace or a diagnostic bundle.  ``withdraw_session``
removes it only while it still carries this process's token, so a stale
backend shutting down never deletes the file of its successor.

This module is pure standard library and imports nothing from VALUE, so the
gateway path rule and the tests can rely on it without the model stack.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SESSION_SCHEMA = "value.api-session/v1"
SESSION_HEADER = "X-VALUE-Session"
SESSION_DIRECTORY = "runtime"
SESSION_FILE_PATTERN = "api-session-{port}.json"
DEFAULT_API_PORT = 8766


class SessionUnavailable(RuntimeError):
    """No published session for the requested data directory and port."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"No VALUE API session at {path}: {reason}")
        self.path = path
        self.reason = reason


def new_token() -> str:
    """A fresh 256-bit URL-safe token (43 characters)."""

    return secrets.token_urlsafe(32)


def _port(port: int) -> int:
    value = int(port)
    if not 1 <= value <= 65535:
        raise ValueError(f"API port must be between 1 and 65535, not {port!r}")
    return value


def session_directory(state_root: Path | str) -> Path:
    return Path(state_root) / SESSION_DIRECTORY


def session_path(state_root: Path | str, port: int) -> Path:
    """``<state_root>/runtime/api-session-<port>.json`` (two ports never share a file)."""

    return session_directory(state_root) / SESSION_FILE_PATTERN.format(port=_port(port))


def _private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        # The directory belongs to VALUE; tighten it even when it pre-existed.
        os.chmod(path, 0o700)


def publish_session(state_root: Path | str, port: int, token: str, *, pid: int | None = None) -> Path:
    """Atomically write the session file for ``port``; returns its path.

    The temporary file is created with ``O_EXCL`` and mode 0600 before any
    byte of the token is written, then moved over the final name, so no reader
    ever sees a partial file or a file with wider permissions.
    """

    if not isinstance(token, str) or not token:
        raise ValueError("A session token must be a nonempty string")
    target = session_path(state_root, port)
    _private_directory(target.parent)
    payload = {
        "schema_version": SESSION_SCHEMA,
        "port": _port(port),
        "pid": os.getpid() if pid is None else int(pid),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "token": token,
    }
    temporary = target.parent / f".{target.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return target


def read_session(state_root: Path | str, port: int) -> dict[str, Any]:
    """The published session for ``port``; raises ``SessionUnavailable``."""

    path = session_path(state_root, port)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SessionUnavailable(path, "the file does not exist (is the VALUE API running for this data directory?)") from None
    except (OSError, UnicodeError, ValueError) as exc:
        raise SessionUnavailable(path, f"the file is unreadable ({type(exc).__name__})") from None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != SESSION_SCHEMA
        or not isinstance(payload.get("token"), str)
        or not payload["token"]
        or payload.get("port") != _port(port)
    ):
        raise SessionUnavailable(path, "the file is not a VALUE API session for this port")
    return payload


def withdraw_session(state_root: Path | str, port: int, token: str) -> bool:
    """Delete the session file only while it still carries ``token``."""

    try:
        published = read_session(state_root, port)
    except SessionUnavailable:
        return False
    if not token_matches(published["token"], token):
        return False
    try:
        session_path(state_root, port).unlink()
    except FileNotFoundError:
        return False
    return True


def token_matches(expected: Any, presented: Any) -> bool:
    """Constant-time comparison; anything but two equal nonempty strings is False."""

    if not isinstance(expected, str) or not isinstance(presented, str):
        return False
    if not expected or not presented:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), presented.encode("utf-8"))


def load_token(state_root: Path | str, port: int = DEFAULT_API_PORT) -> str:
    return str(read_session(state_root, port)["token"])


def authorized_headers(
    state_root: Path | str | None = None,
    port: int = DEFAULT_API_PORT,
    *,
    json_body: bool = False,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Headers for a direct (non-browser) request to the local API.

    ``state_root`` defaults to the data directory this process would use
    (``VALUE_DATA_HOME`` rules of ``gridform_core.runtime_paths``)::

        from backend.api_session import authorized_headers
        request = urllib.request.Request(
            "http://127.0.0.1:8766/api/projects", data=json.dumps(body).encode(),
            headers=authorized_headers(json_body=True), method="POST")

    Never send an ``Origin`` header: the API rejects every browser-originated
    request that does not come through the UI gateway.
    """

    if state_root is None:
        from gridform_core.runtime_paths import user_data_root

        state_root = user_data_root()
    headers = {SESSION_HEADER: load_token(state_root, port)}
    if json_body:
        headers["Content-Type"] = "application/json"
    if extra:
        headers.update(extra)
    return headers
