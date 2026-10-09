"""Actionable environment checks for a local VALUE installation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.runtime_paths import APPLICATION_VERSION, user_data_root  # noqa: E402
from gridform_core.runtime_capabilities import (  # noqa: E402
    VALUE_NATIVE,
    DOCTORAL_REPRODUCTION,
    capability_matrix,
)


def check_port(port: int) -> dict[str, object]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError as exc:
        return {"passed": False, "detail": str(exc), "action": f"Stop the process using loopback port {port}, or configure another supported port."}
    finally:
        sock.close()
    return {"passed": True, "detail": "available", "action": None}


def command_version(command: list[str]) -> str | None:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def report(
    state_root: Path,
    *,
    api_port: int = 8766,
    website_port: int = 8800,
    capability: str = VALUE_NATIVE,
) -> dict[str, object]:
    checks: dict[str, dict[str, object]] = {}
    architecture_ok = platform.architecture()[0] == "64bit"
    checks["architecture"] = {
        "passed": architecture_ok,
        "detail": f"{platform.system()} {platform.machine()} {platform.architecture()[0]}",
        "action": None if architecture_ok else "Install 64-bit Windows and 64-bit Python 3.10.",
    }
    runtime = capability_matrix(selected_module_ids=("value-bid-at-cost-psm",))
    selected_runtime = runtime["capabilities"][capability]
    python_ok = bool(selected_runtime["python_supported"])
    checks["python"] = {
        "passed": python_ok,
        "detail": f"{sys.version.split()[0]} at {sys.executable}",
        "action": None if python_ok else selected_runtime["corrective_action"],
    }
    node = command_version(["node", "--version"])
    node_major = int(node.lstrip("v").split(".")[0]) if node else 0
    checks["node"] = {
        "passed": node_major >= 22,
        "detail": node or "not found",
        "action": None if node_major >= 22 else "Install Node.js 22 LTS or later.",
    }
    mandatory = ["numpy", "pandas"]
    missing_mandatory = [name for name in mandatory if importlib.util.find_spec(name) is None]
    checks["open_core"] = {
        "passed": not missing_mandatory,
        "detail": "all installed" if not missing_mandatory else "missing: " + ", ".join(missing_mandatory),
        "action": None if not missing_mandatory else "Run install-value.cmd to install the locked open-core environment.",
    }
    checks["value_native_capability"] = {
        "passed": bool(runtime["capabilities"][VALUE_NATIVE]["available"]),
        "optional": capability != VALUE_NATIVE,
        "detail": "available" if runtime["capabilities"][VALUE_NATIVE]["available"] else "unavailable",
        "action": runtime["capabilities"][VALUE_NATIVE]["corrective_action"],
    }
    checks["doctoral_reproduction_capability"] = {
        "passed": bool(runtime["capabilities"][DOCTORAL_REPRODUCTION]["available"]),
        "optional": capability != DOCTORAL_REPRODUCTION,
        "detail": "available" if runtime["capabilities"][DOCTORAL_REPRODUCTION]["available"] else "unavailable",
        "action": runtime["capabilities"][DOCTORAL_REPRODUCTION]["corrective_action"],
    }
    for optional_capability, package, action in (
        ("perfect_foresight_solver", "scipy", "Install requirements/value-perfect-foresight-py310.lock."),
        ("independent_validation_oracle", "pulp", "Install requirements/value-validation-py310.lock."),
    ):
        found = importlib.util.find_spec(package) is not None
        checks[optional_capability] = {
            "passed": found, "optional": True,
            "detail": "available" if found else "not installed",
            "action": None if found else action,
        }
    try:
        state_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="value-write-check-", dir=state_root, delete=True):
            pass
        writable = True
        write_detail = str(state_root)
    except OSError as exc:
        writable = False
        write_detail = str(exc)
    checks["state_storage"] = {
        "passed": writable, "detail": write_detail,
        "action": None if writable else "Choose a writable VALUE_DATA_HOME directory.",
    }
    try:
        free = shutil.disk_usage(state_root if state_root.exists() else state_root.parent).free
    except OSError:
        free = 0
    disk_ok = free >= 2 * 1024**3
    checks["disk_headroom"] = {
        "passed": disk_ok, "detail": f"{free / 1024**3:.2f} GiB free",
        "action": None if disk_ok else "Free at least 2 GiB before a model run; annual studies may need substantially more.",
    }
    checks["api_port"] = check_port(api_port)
    checks["website_port"] = check_port(website_port)
    required = [row for row in checks.values() if not row.get("optional")]
    return {
        "schema_version": "value.environment-doctor/v1",
        "application_version": APPLICATION_VERSION,
        "selected_capability": capability,
        "runtime_capabilities": runtime["capabilities"],
        "state_root": str(state_root),
        "ready": all(bool(row["passed"]) for row in required),
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether VALUE can run on this computer")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--api-port", type=int, default=8766)
    parser.add_argument("--website-port", type=int, default=8800)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--capability",
        choices=(VALUE_NATIVE, DOCTORAL_REPRODUCTION),
        default=VALUE_NATIVE,
    )
    args = parser.parse_args()
    payload = report(
        (args.state_root or user_data_root()).resolve(),
        api_port=args.api_port,
        website_port=args.website_port,
        capability=args.capability,
    )
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"VALUE {payload['application_version']} environment doctor")
        for name, row in payload["checks"].items():
            status = "PASS" if row["passed"] else ("OPTIONAL" if row.get("optional") else "FAIL")
            print(f"[{status}] {name.replace('_', ' ')}: {row['detail']}")
            if row.get("action"):
                print(f"       Action: {row['action']}")
        print("Ready to launch." if payload["ready"] else "Required checks failed; follow the actions above.")
    raise SystemExit(0 if payload["ready"] else 1)


if __name__ == "__main__":
    main()
