"""Refuse test traffic to the live VALUE install's loopback ports.

The managed install on this host serves the API on 127.0.0.1:8766 and the UI
on 127.0.0.1:8800.  Tests must never talk to it (hard rule of the P0
construction).  ``scripts/run_backend_tests.py`` puts a generated
``sitecustomize.py`` that calls :func:`install` first on ``PYTHONPATH`` of
every test subprocess, so the guard is active in the test worker and in every
Python child it starts that inherits the environment.

Once installed, ``socket.socket.connect``/``connect_ex``/``bind`` refuse any
IPv4/IPv6 address on a local host (loopback, wildcard, ``localhost``, this
host's name) whose port is forbidden:

* ``connect`` raises ``ConnectionRefusedError`` and ``connect_ex`` returns
  ``ECONNREFUSED`` without touching the network;
* ``bind`` raises ``OSError(EADDRINUSE)`` so a test cannot occupy the port
  of a stopped live install either.

Every refused attempt is appended as one JSON line to the file named by
``VALUE_TEST_NETGUARD_LOG`` together with the running test id (set by the
ratchet worker through :data:`CURRENT_TEST` and ``VALUE_TEST_NETGUARD_TEST``
for children).  The ratchet fails the run when that log is not empty.

The forbidden ports are 8766 and 8800 plus any listed (comma separated) in
``VALUE_TEST_FORBIDDEN_PORTS``; the environment can add ports, never remove
the defaults.

Not covered: non-Python children (curl, node, PowerShell) and Python children
started with ``-I``/``-S``/``-E`` or with an environment that drops
``PYTHONPATH``.
"""

from __future__ import annotations

import errno
import json
import os
import socket
import sys
from typing import Any

DEFAULT_FORBIDDEN_PORTS = (8766, 8800)
PORTS_ENV = "VALUE_TEST_FORBIDDEN_PORTS"
LOG_ENV = "VALUE_TEST_NETGUARD_LOG"
TEST_ENV = "VALUE_TEST_NETGUARD_TEST"
MARKER = "value_test_netguard"

CURRENT_TEST: str | None = None
ATTEMPTS: list[dict[str, Any]] = []
_INSTALLED = False
_LOCAL_NAMES = {"", "localhost", "ip6-localhost", "ip6-loopback", "0.0.0.0", "::", "::1", "::ffff:0.0.0.0"}


def forbidden_ports() -> frozenset[int]:
    ports = set(DEFAULT_FORBIDDEN_PORTS)
    for part in os.environ.get(PORTS_ENV, "").split(","):
        part = part.strip()
        if part.isdigit():
            ports.add(int(part))
    return frozenset(ports)


def _host_names() -> set[str]:
    names = set(_LOCAL_NAMES)
    try:
        names.add(socket.gethostname().lower())
    except OSError:  # pragma: no cover - platform dependent
        pass
    return names


def is_local_host(host: Any) -> bool:
    if isinstance(host, (bytes, bytearray)):
        host = bytes(host).decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    name = host.strip().lower().strip("[]").split("%", 1)[0]
    if name in _host_names() or name.endswith(".localhost"):
        return True
    return name.startswith("127.") or name.startswith("::ffff:127.")


def forbidden_target(sock: Any, address: Any) -> tuple[str, int] | None:
    """``(host, port)`` when ``address`` is a forbidden local endpoint."""

    family = getattr(sock, "family", None)
    if family not in (socket.AF_INET, getattr(socket, "AF_INET6", None)):
        return None
    if not isinstance(address, tuple) or len(address) < 2:
        return None
    host, port = address[0], address[1]
    try:
        port = int(port)
    except (TypeError, ValueError):
        return None
    if port in forbidden_ports() and is_local_host(host):
        return (host if isinstance(host, str) else repr(host), port)
    return None


def record(operation: str, host: str, port: int) -> dict[str, Any]:
    entry = {
        "op": operation,
        "host": host,
        "port": port,
        "test": CURRENT_TEST or os.environ.get(TEST_ENV) or "<outside a test>",
        "pid": os.getpid(),
        "argv0": sys.argv[0] if sys.argv else "",
    }
    ATTEMPTS.append(entry)
    path = os.environ.get(LOG_ENV)
    if path:
        line = (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, line)  # one small O_APPEND write per entry: safe across processes
        finally:
            os.close(descriptor)
    return entry


def set_current_test(identifier: str | None) -> None:
    global CURRENT_TEST
    CURRENT_TEST = identifier
    if identifier:
        os.environ[TEST_ENV] = identifier
    else:
        os.environ.pop(TEST_ENV, None)


def install() -> bool:
    """Patch ``socket.socket``; idempotent.  Returns True when newly installed."""

    global _INSTALLED
    if _INSTALLED or getattr(socket.socket.connect, MARKER, False):
        _INSTALLED = True
        return False
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_bind = socket.socket.bind

    def connect(self: socket.socket, address: Any) -> None:
        target = forbidden_target(self, address)
        if target is not None:
            record("connect", *target)
            raise ConnectionRefusedError(
                errno.ECONNREFUSED,
                f"{MARKER}: tests may not connect to the live VALUE port {target[1]} on {target[0]}",
            )
        return original_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:
        target = forbidden_target(self, address)
        if target is not None:
            record("connect_ex", *target)
            return errno.ECONNREFUSED
        return original_connect_ex(self, address)

    def bind(self: socket.socket, address: Any) -> None:
        target = forbidden_target(self, address)
        if target is not None:
            record("bind", *target)
            raise OSError(errno.EADDRINUSE, f"{MARKER}: tests may not bind the live VALUE port {target[1]}")
        return original_bind(self, address)

    for function in (connect, connect_ex, bind):
        setattr(function, MARKER, True)
    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
    socket.socket.bind = bind  # type: ignore[method-assign]
    _INSTALLED = True
    return True


SITECUSTOMIZE = (
    "# Generated by scripts/run_backend_tests.py: refuse test traffic to the live VALUE ports.\n"
    "import value_test_netguard as _value_test_netguard\n"
    "_value_test_netguard.install()\n"
)


def read_log(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"op": "unparsable", "raw": line[:200]})
    return rows
