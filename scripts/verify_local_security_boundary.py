"""Probe a running VALUE for the P0-1 local security boundary.

    python -B scripts/verify_local_security_boundary.py [--api-origin http://127.0.0.1:8766]
                                                        [--ui-origin http://127.0.0.1:8800] [--json report.json]

Every probe is a request the boundary must refuse, chosen so that it changes
nothing even if a broken boundary accepted it (validation-only routes, a
nonexistent Run id, an empty module upload without the trust acknowledgement).
The probe never reads or sends the session token.  Exit code 0 = PASS (every
probe refused as expected), 1 = FAIL, 2 = an origin could not be reached.

Run it after installing or upgrading VALUE (and against scratch instances in
tests); it is read-only for the instance it probes.
"""

from __future__ import annotations

import argparse
import http.client
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

EVIL_ORIGIN = "https://attacker.example"
SECURITY_HEADERS = {
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
}


@dataclass
class Probe:
    name: str
    target: str
    method: str
    path: str
    expected: tuple[int, ...]
    status: int | None = None
    passed: bool = False
    detail: str = ""
    headers_checked: list[str] = field(default_factory=list)


def _split(origin: str) -> tuple[str, int]:
    parts = urlsplit(origin)
    if parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost"} or parts.port is None:
        raise ValueError(f"expected http://127.0.0.1:<port> or http://localhost:<port>, not {origin}")
    return parts.hostname, int(parts.port)


def _send(origin: str, method: str, path: str, headers: dict[str, str], body: bytes | None = None,
          timeout: float = 10.0) -> tuple[int, dict[str, str], bytes]:
    host, port = _split(origin)
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for name, value in headers.items():
            connection.putheader(name, value)
        if body is not None:
            connection.putheader("Content-Length", str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        payload = response.read(65536)
        return response.status, {key.lower(): value for key, value in response.getheaders()}, payload
    finally:
        connection.close()


def _probes(api: str, ui: str) -> list[tuple[Probe, dict[str, str], bytes | None]]:
    _, api_port = _split(api)
    _, ui_port = _split(ui)
    api_host = f"127.0.0.1:{api_port}"
    ui_host = f"127.0.0.1:{ui_port}"
    validate = json.dumps({"name": "value-boundary-probe"}).encode()
    missing_run = f"value-boundary-probe-{uuid.uuid4().hex[:12]}"
    plain = {"Content-Type": "text/plain"}
    rows: list[tuple[Probe, dict[str, str], bytes | None]] = [
        # API: DNS rebinding, browser origins, missing session, simple types.
        (Probe("api-forged-host", "api", "GET", "/api/health", (421,)), {"Host": f"attacker.example:{api_port}"}, None),
        (Probe("api-host-without-port", "api", "GET", "/api/health", (421,)), {"Host": "127.0.0.1"}, None),
        (Probe("api-cross-site-text-plain-post", "api", "POST", "/api/projects/validate", (403,)),
         {"Host": api_host, "Origin": EVIL_ORIGIN, **plain}, validate),
        (Probe("api-form-post", "api", "POST", "/api/projects/validate", (403,)),
         {"Host": api_host, "Origin": EVIL_ORIGIN, "Content-Type": "application/x-www-form-urlencoded"}, validate),
        (Probe("api-old-dev-origin-preflight", "api", "OPTIONS", "/api/modules/install", (403,)),
         {"Host": api_host, "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
          "Access-Control-Request-Headers": "x-value-executable-trust"}, None),
        (Probe("api-ui-origin-direct", "api", "POST", "/api/projects/validate", (403,)),
         {"Host": api_host, "Origin": ui, "Content-Type": "application/json"}, validate),
        (Probe("api-no-session-read", "api", "GET", "/api/workspace", (403,)), {"Host": api_host}, None),
        (Probe("api-no-session-json-post", "api", "POST", "/api/projects/validate", (403,)),
         {"Host": api_host, "Content-Type": "application/json"}, validate),
        (Probe("api-no-session-module-install", "api", "POST", "/api/modules/install", (403,)),
         {"Host": api_host, "Content-Type": "application/zip", "X-Filename": "probe.zip"}, b""),
        (Probe("api-no-session-module-rescan", "api", "POST", "/api/modules/rescan", (403,)),
         {"Host": api_host, "Content-Type": "application/json", "X-VALUE-Acknowledge-Pending-Runs": "acknowledged"}, b"{}"),
        (Probe("api-no-session-mark-lost", "api", "POST", f"/api/runs/{missing_run}/mark-lost", (403,)),
         {"Host": api_host, "Content-Type": "application/json"}, json.dumps({"confirm_run_id": missing_run}).encode()),
        (Probe("api-forged-session", "api", "GET", "/api/workspace", (403,)),
         {"Host": api_host, "X-VALUE-Session": "value-boundary-probe-not-a-token"}, None),
        # UI gateway: DNS rebinding and cross-site requests from other pages.
        (Probe("ui-forged-host-page", "ui", "GET", "/", (421,)), {"Host": f"attacker.example:{ui_port}"}, None),
        (Probe("ui-forged-host-api", "ui", "GET", "/api/health", (421,)), {"Host": f"attacker.example:{ui_port}"}, None),
        (Probe("ui-cross-site-post", "ui", "POST", "/api/projects/validate", (403,)),
         {"Host": ui_host, "Origin": EVIL_ORIGIN, "Sec-Fetch-Site": "cross-site", **plain}, validate),
        (Probe("ui-same-site-post", "ui", "POST", "/api/projects/validate", (403,)),
         {"Host": ui_host, "Origin": f"http://localhost:{ui_port + 1}", "Sec-Fetch-Site": "same-site",
          "Content-Type": "application/json"}, validate),
        (Probe("ui-foreign-origin-post", "ui", "POST", "/api/projects/validate", (403,)),
         {"Host": ui_host, "Origin": EVIL_ORIGIN, "Content-Type": "application/json"}, validate),
        (Probe("ui-cross-site-read", "ui", "GET", "/api/workspace", (403,)),
         {"Host": ui_host, "Sec-Fetch-Site": "cross-site"}, None),
    ]
    return rows


def verify(api_origin: str, ui_origin: str) -> dict[str, object]:
    results: list[Probe] = []
    unreachable: list[str] = []
    for probe, headers, body in _probes(api_origin, ui_origin):
        origin = api_origin if probe.target == "api" else ui_origin
        try:
            status, response_headers, payload = _send(origin, probe.method, probe.path, headers, body)
        except OSError as exc:
            probe.detail = f"unreachable: {type(exc).__name__}"
            unreachable.append(origin)
            results.append(probe)
            continue
        probe.status = status
        problems = []
        if status not in probe.expected:
            problems.append(f"status {status}, expected {probe.expected}")
        cors = sorted(name for name in response_headers if name.startswith("access-control-"))
        if cors:
            problems.append(f"CORS headers present: {cors}")
        for name, value in SECURITY_HEADERS.items():
            probe.headers_checked.append(name)
            if response_headers.get(name) != value:
                problems.append(f"{name} is {response_headers.get(name)!r}")
        probe.passed = not problems
        probe.detail = "; ".join(problems) or str(response_headers.get("x-value-error-code", ""))
        results.append(probe)
    page_problems: list[str] = []
    try:
        status, headers, _payload = _send(ui_origin, "GET", "/", {"Host": f"127.0.0.1:{_split(ui_origin)[1]}"})
        csp = headers.get("content-security-policy", "")
        if status != 200:
            page_problems.append(f"UI page status {status}")
        for directive in ("frame-ancestors 'none'", "script-src 'self' 'nonce-", "object-src 'none'"):
            if directive not in csp:
                page_problems.append(f"page CSP lacks {directive!r}")
        for name, value in SECURITY_HEADERS.items():
            if headers.get(name) != value:
                page_problems.append(f"page {name} is {headers.get(name)!r}")
    except OSError as exc:
        page_problems.append(f"UI page unreachable: {type(exc).__name__}")
        unreachable.append(ui_origin)
    passed = not unreachable and not page_problems and all(probe.passed for probe in results)
    return {
        "schema_version": "value.local-security-boundary-probe/v1",
        "api_origin": api_origin,
        "ui_origin": ui_origin,
        "verdict": "PASS" if passed else ("UNREACHABLE" if unreachable else "FAIL"),
        "passed": passed,
        "probes": [asdict(probe) for probe in results],
        "page_problems": page_problems,
        "unreachable": sorted(set(unreachable)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--api-origin", default="http://127.0.0.1:8766")
    parser.add_argument("--ui-origin", default="http://127.0.0.1:8800")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    report = verify(args.api_origin, args.ui_origin)
    text = json.dumps(report, indent=2)
    if args.json:
        args.json.write_text(text + "\n", encoding="utf-8")
    failed = [probe for probe in report["probes"] if not probe["passed"]]  # type: ignore[index]
    print(f"VALUE local security boundary: {report['verdict']} "
          f"({len(report['probes']) - len(failed)}/{len(report['probes'])} probes refused as expected)")  # type: ignore[arg-type]
    for probe in failed:
        print(f"  FAIL {probe['name']}: {probe['detail']}")
    for problem in report["page_problems"]:  # type: ignore[union-attr]
        print(f"  FAIL page: {problem}")
    if report["verdict"] == "UNREACHABLE":
        return 2
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
