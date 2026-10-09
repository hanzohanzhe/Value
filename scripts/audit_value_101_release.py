"""Fail-closed release audit for the formal VALUE Windows product."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PACK_IDS = (
    "value-101-baseline-v1",
    "value-101-network-v1",
)
REQUIRED_PRODUCT_FILES = (
    "README.md",
    "docs/tutorial/VALUE_101.md",
    "docs/tutorial/VALUE_101_ZH.md",
    "docs/tutorial/VALUE_101_QUICK_CARD.md",
    "docs/tutorial/JOHN_PILOT_RUNBOOK.md",
    "output/pdf/VALUE_101_guide.pdf",
    "packaging/windows-pilot/ValueInstaller.cs",
    "packaging/windows-pilot/ValueInstallerWindow.cs",
    "packaging/windows-pilot/start-portable.ps1",
    "packaging/windows-pilot/product.json",
    "packaging/windows-pilot/runtime-payload-policy.json",
)
INSTALLER_EXTRA_RELEASE_FILES = (
    "packaging/windows-pilot/ValueInstaller.cs",
    "packaging/windows-pilot/ValueInstallerWindow.cs",
    "packaging/windows-pilot/product.json",
    "packaging/windows-pilot/runtime-payload-policy.json",
    "packaging/windows-pilot/start-portable.ps1",
    "docs/tutorial/VALUE_101.md",
    "docs/tutorial/VALUE_101_QUICK_CARD.md",
    "docs/tutorial/JOHN_PILOT_RUNBOOK.md",
    "scripts/build_windows_pilot_installer.py",
    "scripts/start-portable-local.ps1",
    "scripts/check-value-101.ps1",
    "tests/test_windows_pilot_installer.py",
)
FRONTEND_DIST_DIRECTORIES = ("server", "client", ".openai")
PAYLOAD_MANIFEST_NAME = "VALUE-PAYLOAD-MANIFEST.json"
PYTHON_ARCHIVE_SHA256 = "608619f8619075629c9c69f361352a0da6ed7e62f83a0e19c63e0ea32eb7629d"
NODE_ARCHIVE_SHA256 = "c97fa376d2becdc8863fcd3ca2dd9a83a9f3468ee7ccf7a6d076ec66a645c77a"
RUNTIME_POLICY_PATH = "packaging/windows-pilot/runtime-payload-policy.json"
EXPECTED_COMPARISON_DIMENSIONS = {
    "baseline": [],
    "data": ["data_pack_id"],
    "storage": ["modules.storage_cost"],
}
FORBIDDEN_PUBLIC_AC = (
    "value-reference-ac-feasibility",
    "value-ac-data-extension",
    "domain.network.ac",
    "ac_feasibility",
    "domains/ac",
    "ac feasibility",
)
PUBLIC_SCAN_SUFFIXES = {".js", ".json", ".md", ".ts", ".tsx"}
FIXED_ALLOWED_AUDIT_OUTPUTS = {
    "publication/prompt117-value-101-evidence.json",
    "publication/prompt117-value-101-release-report.json",
    "publication/prompt117-value-101-release-report.md",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _runtime_inventory_identity(
    policy: Mapping[str, Mapping[str, object]],
) -> tuple[str, int]:
    records = [
        {"path": name, **dict(values)}
        for name, values in sorted(policy.items())
        if name.startswith(("runtime/", "node_modules/"))
    ]
    raw = (
        json.dumps(records, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), len(records)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _safe_binding_path(pack_root: Path, uri: object) -> Path | None:
    if not isinstance(uri, str) or not uri:
        return None
    candidate = (pack_root / uri).resolve()
    try:
        candidate.relative_to(pack_root.resolve())
    except ValueError:
        return None
    return candidate


def _issue(
    issues: list[dict[str, Any]],
    code: str,
    message: str,
    evidence: object | None = None,
) -> None:
    issues.append({"code": code, "message": message, "evidence": evidence})


def _read_installer_inventory(installer: Path) -> dict[str, dict[str, object]]:
    with installer.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Installer is not a Windows PE executable")
    with tempfile.TemporaryDirectory(prefix="value-101-payload-audit-") as temporary:
        inventory_path = Path(temporary) / "payload.tsv"
        completed = subprocess.run(
            [str(installer), "--audit-payload", str(inventory_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if completed.returncode != 0 or not inventory_path.is_file():
            raise RuntimeError(
                "Installer payload audit mode failed: "
                f"exit={completed.returncode}; stderr={completed.stderr[-1000:]}"
            )
        inventory: dict[str, dict[str, object]] = {}
        for line in inventory_path.read_text("utf-8").splitlines():
            digest, size, name = line.split("\t", 2)
            if name in inventory:
                raise ValueError(f"Duplicate installer payload member: {name}")
            inventory[name] = {"sha256": digest.lower(), "bytes": int(size)}
        if not inventory:
            raise ValueError("Installer payload inventory is empty")
        return inventory


def _read_installer_payload_manifest(
    installer: Path,
) -> tuple[dict[str, object], str, int]:
    with tempfile.TemporaryDirectory(prefix="value-101-payload-manifest-") as temporary:
        manifest_path = Path(temporary) / PAYLOAD_MANIFEST_NAME
        completed = subprocess.run(
            [str(installer), "--audit-payload-manifest", str(manifest_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if completed.returncode != 0 or not manifest_path.is_file():
            raise RuntimeError(
                "Installer payload-manifest audit mode failed: "
                f"exit={completed.returncode}; stderr={completed.stderr[-1000:]}"
            )
        raw_size = manifest_path.stat().st_size
        raw_hash = sha256(manifest_path)
        return load_json(manifest_path), raw_hash, raw_size


def _release_source_members(root: Path) -> set[str]:
    manifest = load_json(root / "source-release-manifest.json")
    includes = tuple(
        str(item).replace("\\", "/").strip("/")
        for item in manifest.get("include", [])
        if str(item).strip("/\\")
    )
    local_only = {
        str(item.get("repository_path") or "").replace("\\", "/").lstrip("/")
        for item in manifest.get("local_only_source_content", [])
        if isinstance(item, Mapping)
        and item.get("distribution") == "repository-local-only"
    }
    safe_root = root.resolve().as_posix()
    try:
        tracked = subprocess.run(
            ["git", "-c", f"safe.directory={safe_root}", "ls-files", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8").split("\0")
        deleted = set(subprocess.run(
            [
                "git", "-c", f"safe.directory={safe_root}", "diff",
                "--name-only", "--diff-filter=D", "HEAD", "-z",
            ],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8").split("\0"))
    except (OSError, subprocess.SubprocessError):
        tracked = [
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        ]
        deleted = set()
    return {
        name for name in tracked
        if name
        and name not in deleted
        and name not in local_only
        and any(name == prefix or name.startswith(prefix + "/") for prefix in includes)
        and not (
            name.startswith("data-packs/")
            and name.split("/", 2)[1] not in EXPECTED_PACK_IDS
        )
    }


def _expected_payload_sources(root: Path) -> dict[str, Path]:
    expected: dict[str, Path] = {}
    for relative in sorted(
        _release_source_members(root) | set(INSTALLER_EXTRA_RELEASE_FILES)
    ):
        source = root / relative
        if source.is_file():
            expected[relative] = source
    for directory_name in FRONTEND_DIST_DIRECTORIES:
        directory = root / "dist" / directory_name
        if directory.is_dir():
            for source in directory.rglob("*"):
                if source.is_file():
                    expected[source.relative_to(root).as_posix()] = source
    for pack_id in EXPECTED_PACK_IDS:
        pack_root = root / "data-packs" / pack_id
        if pack_root.is_dir():
            for source in pack_root.rglob("*"):
                if source.is_file():
                    expected[source.relative_to(root).as_posix()] = source
    guide = root / "output" / "pdf" / "VALUE_101_guide.pdf"
    if guide.is_file():
        expected["START-HERE-VALUE-101-Guide.pdf"] = guide
    return expected


def _audit_installer_payload(
    root: Path,
    installer: Path,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        inventory = _read_installer_inventory(installer)
        payload_manifest, payload_manifest_hash, payload_manifest_bytes = (
            _read_installer_payload_manifest(installer)
        )
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        _issue(
            issues,
            "INSTALLER_PAYLOAD_UNVERIFIED",
            "The executable did not expose a verifiable embedded payload inventory.",
            str(exc),
        )
        return {"verified": False, "members": 0, "mismatches": []}
    expected = _expected_payload_sources(root)
    mismatches: list[dict[str, object]] = []
    manifest_item = inventory.get(PAYLOAD_MANIFEST_NAME)
    if (
        manifest_item is None
        or manifest_item.get("sha256") != payload_manifest_hash
        or int(manifest_item.get("bytes") or -1) != payload_manifest_bytes
    ):
        mismatches.append({
            "path": PAYLOAD_MANIFEST_NAME,
            "reason": "embedded payload manifest inventory mismatch",
        })
    build_inputs = payload_manifest.get("build_inputs")
    lock_path = root / "requirements" / "value-all-py310.lock"
    expected_build_inputs = {
        "python_archive_sha256": PYTHON_ARCHIVE_SHA256,
        "node_archive_sha256": NODE_ARCHIVE_SHA256,
        "python_lock_sha256": sha256(lock_path) if lock_path.is_file() else None,
    }
    if (
        payload_manifest.get("schema_version") != "value.101-installer-payload/v1"
        or build_inputs != expected_build_inputs
    ):
        mismatches.append({
            "path": PAYLOAD_MANIFEST_NAME,
            "reason": "payload manifest build inputs differ from pinned release inputs",
        })
    policy: dict[str, dict[str, object]] = {}
    records = payload_manifest.get("members")
    if not isinstance(records, list) or not records:
        mismatches.append({
            "path": PAYLOAD_MANIFEST_NAME,
            "reason": "payload manifest has no exact member list",
        })
        records = []
    for record in records:
        if not isinstance(record, Mapping):
            mismatches.append({
                "path": PAYLOAD_MANIFEST_NAME,
                "reason": "payload manifest contains a non-object member",
            })
            continue
        name = str(record.get("path") or "")
        pure = PurePosixPath(name)
        if (
            not name
            or pure.is_absolute()
            or ".." in pure.parts
            or "\\" in name
            or pure.as_posix() != name
        ):
            mismatches.append({"path": name, "reason": "unsafe payload member path"})
            continue
        if name in policy or name == PAYLOAD_MANIFEST_NAME:
            mismatches.append({"path": name, "reason": "duplicate payload manifest member"})
            continue
        policy[name] = {
            "sha256": str(record.get("sha256") or "").lower(),
            "bytes": record.get("bytes") if isinstance(record.get("bytes"), int) else -1,
        }
    runtime_digest, runtime_count = _runtime_inventory_identity(policy)
    runtime_policy_path = root / RUNTIME_POLICY_PATH
    runtime_policy = (
        load_json(runtime_policy_path) if runtime_policy_path.is_file() else {}
    )
    if (
        runtime_policy.get("schema_version")
        != "value.101-runtime-payload-policy/v1"
        or runtime_policy.get("runtime_inventory_sha256") != runtime_digest
        or runtime_policy.get("runtime_member_count") != runtime_count
        or payload_manifest.get("runtime_inventory_sha256") != runtime_digest
        or payload_manifest.get("runtime_member_count") != runtime_count
    ):
        mismatches.append({
            "path": RUNTIME_POLICY_PATH,
            "reason": "runtime inventory differs from source-controlled policy",
        })
    actual_members = set(inventory) - {PAYLOAD_MANIFEST_NAME}
    embedded_pack_ids = {
        PurePosixPath(name).parts[1]
        for name in actual_members | set(policy)
        if len(PurePosixPath(name).parts) >= 3
        and PurePosixPath(name).parts[0] == "data-packs"
    }
    unapproved_data_pack_ids = sorted(
        pack_id for pack_id in embedded_pack_ids if pack_id not in EXPECTED_PACK_IDS
    )
    if unapproved_data_pack_ids:
        _issue(
            issues,
            "INSTALLER_UNAPPROVED_DATA_PACK",
            "The installer embeds a data pack outside the formal VALUE tutorial allowlist.",
            unapproved_data_pack_ids,
        )
        mismatches.extend(
            {
                "path": f"data-packs/{pack_id}/",
                "reason": "unapproved embedded data pack",
            }
            for pack_id in unapproved_data_pack_ids
        )
    for name in sorted(set(policy) - actual_members):
        mismatches.append({"path": name, "reason": "manifested payload member missing"})
    for name in sorted(actual_members - set(policy)):
        mismatches.append({"path": name, "reason": "unexpected payload member"})
    for name in sorted(actual_members & set(policy)):
        if inventory[name] != policy[name]:
            mismatches.append({"path": name, "reason": "payload manifest hash or size mismatch"})
    for payload_name, source in sorted(expected.items()):
        item = inventory.get(payload_name)
        if not source.is_file():
            mismatches.append({"path": payload_name, "reason": "source missing"})
        elif item is None:
            mismatches.append({"path": payload_name, "reason": "payload missing"})
        elif item.get("sha256") != sha256(source).lower():
            mismatches.append({"path": payload_name, "reason": "payload/source sha256 mismatch"})
    for runtime in ("runtime/python/python.exe", "runtime/node/node.exe"):
        item = inventory.get(runtime)
        if item is None or int(item.get("bytes") or 0) <= 0:
            mismatches.append({"path": runtime, "reason": "private runtime missing"})
    manifest_path = root / "source-release-manifest.json"
    if manifest_path.is_file():
        manifest = load_json(manifest_path)
        for record in manifest.get("local_only_source_content", []):
            if not isinstance(record, Mapping):
                continue
            if record.get("distribution") != "repository-local-only":
                continue
            name = str(record.get("repository_path") or "").replace("\\", "/").lstrip("/")
            if name and name in inventory:
                mismatches.append({"path": name, "reason": "repository-local-only content leaked"})
    if mismatches:
        _issue(
            issues,
            "INSTALLER_PAYLOAD_MISMATCH",
            "The embedded installer payload does not match the reviewed release tree.",
            mismatches,
        )
    return {
        "verified": not mismatches,
        "members": len(inventory),
        "expected_members_checked": len(expected),
        "unapproved_data_pack_ids": unapproved_data_pack_ids,
        "mismatches": mismatches,
    }


def _audit_installer(
    root: Path,
    installer: Path,
    issues: list[dict[str, Any]],
    minimum_installer_bytes: int,
) -> dict[str, Any]:
    if installer.name != "VALUE-Setup.exe":
        _issue(
            issues,
            "INSTALLER_IDENTITY_INVALID",
            "The Windows installer name does not match the formal VALUE release identity.",
            {"expected": "VALUE-Setup.exe", "actual": installer.name},
        )
    if not installer.is_file():
        _issue(issues, "INSTALLER_INCOMPLETE", "The Windows installer is missing.", str(installer))
        return {"path": str(installer), "exists": False, "bytes": 0, "sha256": None, "payload": {"verified": False}}
    size = installer.stat().st_size
    digest = sha256(installer)
    if size < minimum_installer_bytes:
        _issue(
            issues,
            "INSTALLER_INCOMPLETE",
            "The installer is smaller than the declared self-contained release floor.",
            {"bytes": size, "minimum_bytes": minimum_installer_bytes},
        )
    checksum_path = installer.with_name(installer.name + ".sha256.txt")
    declared = None
    if checksum_path.is_file():
        declared = checksum_path.read_text(encoding="ascii", errors="ignore").split(maxsplit=1)[0].lower()
    if declared != digest.lower():
        _issue(
            issues,
            "INSTALLER_CHECKSUM_MISMATCH",
            "The installer SHA-256 does not match its checksum file.",
            {"actual": digest, "declared": declared},
        )
    payload = _audit_installer_payload(root, installer, issues)
    return {
        "path": str(installer),
        "exists": True,
        "bytes": size,
        "sha256": digest,
        "checksum_path": str(checksum_path),
        "checksum_matches": declared == digest.lower(),
        "payload": payload,
    }


def _audit_product(root: Path, issues: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [name for name in REQUIRED_PRODUCT_FILES if not (root / name).is_file()]
    if missing:
        _issue(issues, "PRODUCT_FILES_MISSING", "Required VALUE product release files are absent.", missing)
    product_path = root / "packaging/windows-pilot/product.json"
    try:
        product = load_json(product_path)
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        _issue(issues, "PRODUCT_CONTRACT_INVALID", "The installer product contract cannot be read.", str(exc))
        return {"required_files_missing": missing, "contract": None}
    contract_valid = (
        product.get("product_name") == "VALUE"
        and product.get("entrypoint") == "VALUE-Setup.exe"
        and product.get("install_scope") == "current-user"
        and product.get("administrator_required") is False
        and product.get("terminal_required") is False
        and product.get("internet_required_after_download") is False
        and product.get("progress_window") is True
        and product.get("data_licence") == "CC0-1.0"
        and tuple(product.get("data_packs") or ()) == EXPECTED_PACK_IDS
    )
    if not contract_valid:
        _issue(issues, "PRODUCT_CONTRACT_INVALID", "The Windows product contract does not match the formal VALUE product.", product)
    return {"required_files_missing": missing, "contract_valid": contract_valid, "contract": product}


def _audit_packs(root: Path, issues: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    hash_failures: list[dict[str, str]] = []
    for pack_id in EXPECTED_PACK_IDS:
        pack_root = root / "data-packs" / pack_id
        manifest_path = pack_root / "manifest.json"
        try:
            manifest = load_json(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _issue(issues, "PACK_INCOMPLETE", f"Teaching pack {pack_id} is missing or invalid.", str(exc))
            rows.append({"pack_id": pack_id, "valid": False})
            continue
        bindings = manifest.get("bindings")
        contract_valid = (
            manifest.get("id") == pack_id
            and manifest.get("licence") == "CC0-1.0"
            and manifest.get("teaching_only") is True
            and isinstance(bindings, Mapping)
            and len(bindings) >= 25
        )
        if not contract_valid:
            _issue(issues, "PACK_INCOMPLETE", f"Teaching pack {pack_id} violates its public contract.", manifest_path.as_posix())
        checked = 0
        if isinstance(bindings, Mapping):
            for role, binding in bindings.items():
                if not isinstance(binding, Mapping):
                    hash_failures.append({"pack_id": pack_id, "role": str(role), "reason": "invalid binding"})
                    continue
                source = _safe_binding_path(pack_root, binding.get("uri"))
                declared = str(binding.get("sha256") or "").lower()
                if source is None or not source.is_file():
                    hash_failures.append({"pack_id": pack_id, "role": str(role), "reason": "missing or unsafe file"})
                    continue
                actual = sha256(source).lower()
                if declared != actual:
                    hash_failures.append({"pack_id": pack_id, "role": str(role), "reason": "sha256 mismatch"})
                checked += 1
        rows.append({
            "pack_id": pack_id,
            "valid": contract_valid,
            "licence": manifest.get("licence"),
            "bindings_checked": checked,
        })
    if hash_failures:
        _issue(issues, "PACK_HASH_MISMATCH", "One or more teaching-pack files fail provenance hashing.", hash_failures)
    return {"expected_pack_ids": list(EXPECTED_PACK_IDS), "packs": rows, "hash_failures": hash_failures}


def _audit_public_surface(root: Path) -> list[dict[str, str]]:
    candidates: list[Path] = [root / "README.md", root / "packaging/windows-pilot/product.json"]
    for directory in (
        root / "app",
        root / "docs" / "tutorial",
        root / "dist" / "client",
        root / "dist" / "server",
    ):
        if directory.is_dir():
            candidates.extend(path for path in directory.rglob("*") if path.is_file())
    exposed: list[dict[str, str]] = []
    for path in candidates:
        if not path.is_file() or path.suffix.lower() not in PUBLIC_SCAN_SUFFIXES:
            continue
        text = path.read_text("utf-8", errors="ignore").lower()
        for forbidden in FORBIDDEN_PUBLIC_AC:
            if forbidden in text:
                exposed.append({
                    "path": path.relative_to(root).as_posix(),
                    "token": forbidden,
                })
    return exposed


def _audit_source_control(root: Path) -> dict[str, object]:
    safe_root = root.resolve().as_posix()
    commit = subprocess.run(
        ["git", "-c", f"safe.directory={safe_root}", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-c", f"safe.directory={safe_root}", "status", "--porcelain", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8", errors="replace").split("\0")
    dirty: list[str] = []
    for record in status:
        if not record:
            continue
        path = record[3:].replace("\\", "/") if len(record) >= 4 else record
        dirty.append(path)
    unexpected = sorted(path for path in dirty if path not in FIXED_ALLOWED_AUDIT_OUTPUTS)
    return {"commit": commit, "dirty_paths": sorted(dirty), "unexpected_dirty_paths": unexpected}


def _audit_retained_sources(root: Path) -> dict[str, object]:
    manifest_path = root / "docs" / "visibility-refactor" / "retained-source-hashes.json"
    manifest = load_json(manifest_path)
    modified: list[str] = []
    for entry in manifest.get("files", []):
        if not isinstance(entry, Mapping):
            continue
        path = root / str(entry.get("path") or "")
        if not path.is_file() or sha256(path) != str(entry.get("sha256") or ""):
            modified.append(str(entry.get("path") or ""))
    return {"passed": not modified, "modified_files": modified, "manifest": str(manifest_path)}


def _probe_api_headers(api_origin: str, api_state_root: Path | None) -> tuple[dict[str, str], str | None]:
    """Session header for a direct API probe (P0-1: every route but a reduced
    /api/health needs ``X-VALUE-Session``); the token comes from the API's
    0600 session file in ``api_state_root`` (default: this process's
    VALUE_DATA_HOME rules) and is never printed."""

    from urllib.parse import urlsplit

    from backend.api_session import SessionUnavailable, authorized_headers

    try:
        port = urlsplit(api_origin).port or 80
        return authorized_headers(api_state_root, port), None
    except (SessionUnavailable, ValueError) as exc:
        return {}, str(exc)


def _probe_api(api_origin: str, api_state_root: Path | None = None) -> dict[str, object]:
    headers, session_problem = _probe_api_headers(api_origin, api_state_root)
    routes = {
        "health": "/api/health",
        "tutorial": "/api/tutorials/value-101",
        "completion_report": "/api/tutorials/value-101/completion-report",
        "data_packs": "/api/data-packs",
        "workspace": "/api/workspace",
    }
    results: dict[str, bool] = {}
    payloads: dict[str, object] = {}
    for name, route in routes.items():
        try:
            request = urllib.request.Request(api_origin.rstrip("/") + route, headers=headers)
            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
                results[name] = response.status == 200
                payloads[name] = payload
        except (OSError, ValueError, json.JSONDecodeError):
            results[name] = False
    workspace = payloads.get("workspace")
    modules = workspace.get("modules", []) if isinstance(workspace, Mapping) else []
    public_module_ids = [
        str(item.get("id")) for item in modules
        if isinstance(item, Mapping) and item.get("id")
    ]
    return {"routes": results, "public_module_ids": public_module_ids, "session": session_problem or "available"}


def _recompute_comparison(evidence: Mapping[str, Any]) -> dict[str, object]:
    roots = evidence.get("comparison_run_roots")
    if not isinstance(roots, Mapping):
        raise ValueError("comparison_run_roots is missing")
    from gridform_core.value_101_results import build_value_101_comparison
    return build_value_101_comparison(
        Path(str(roots.get("baseline"))),
        Path(str(roots.get("data"))),
        Path(str(roots.get("storage"))),
    )


def _load_network_verification(evidence: Mapping[str, Any]) -> dict[str, object]:
    source = evidence.get("network_accounting_source")
    if not isinstance(source, str) or not source:
        raise ValueError("network_accounting_source is missing")
    report = load_json(Path(source))
    return report


def _recompute_network_verification(evidence: Mapping[str, Any]) -> dict[str, object]:
    roots = evidence.get("network_run_roots")
    if not isinstance(roots, Mapping):
        raise ValueError("network_run_roots is missing")
    from scripts.verify_value_101_network_exercise import verify_network_pair
    return verify_network_pair(
        Path(str(roots.get("copperplate") or "")),
        Path(str(roots.get("constrained") or "")),
    )


def _recompute_reset_scope() -> dict[str, object]:
    from scripts.verify_value_101_reset_scope import verify_reset_scope
    return verify_reset_scope()


def _audit_evidence(
    root: Path,
    evidence: Mapping[str, Any],
    issues: list[dict[str, Any]],
    api_origin: str,
    api_state_root: Path | None = None,
) -> dict[str, Any]:
    try:
        source = _audit_source_control(root)
    except (OSError, subprocess.SubprocessError) as exc:
        source = {"commit": None, "dirty_paths": [], "unexpected_dirty_paths": [str(exc)]}
    unexpected_dirty = list(source.get("unexpected_dirty_paths") or [])
    if not source.get("commit") or unexpected_dirty:
        _issue(issues, "SOURCE_TREE_DIRTY", "The reviewed source tree is not at a clean, identified commit.", unexpected_dirty)

    public_exposed = _audit_public_surface(root)
    api = _probe_api(api_origin, api_state_root)
    public_ids = [str(item) for item in api.get("public_module_ids", [])]
    module_exposed = sorted(
        item for item in public_ids
        if any(forbidden in item.lower() for forbidden in FORBIDDEN_PUBLIC_AC)
    )
    exposed: list[object] = [*public_exposed, *module_exposed]
    if exposed:
        _issue(issues, "PUBLIC_AC_EXPOSED", "The reviewed public surface exposes an internal AC experiment.", exposed)

    boundary = evidence.get("scientific_boundary") if isinstance(evidence.get("scientific_boundary"), Mapping) else {}
    boundary_label = str(boundary.get("label") or "").lower()
    if boundary.get("annual_economics_eligible") is not False or "not annual" not in boundary_label:
        _issue(issues, "TEACHING_ANNUALISED", "VALUE 101 is not labelled as a non-annual teaching diagnostic.", boundary)

    try:
        comparison = _recompute_comparison(evidence)
    except (OSError, ValueError, sqlite3.Error) as exc:
        comparison = {}
        _issue(issues, "COMPARISON_EVIDENCE_UNVERIFIED", "The three teaching Runs could not be independently recomputed.", str(exc))
    rows = comparison.get("rows") if isinstance(comparison.get("rows"), list) else []
    row_dimensions = {
        str(row.get("variant_kind")): {
            "declared": list(row.get("declared_changed_dimensions") or []),
            "actual": list(row.get("actual_changed_dimensions") or []),
        }
        for row in rows if isinstance(row, Mapping)
    }
    comparison_gate = comparison.get("comparison_gate") if isinstance(comparison.get("comparison_gate"), Mapping) else {}
    controlled = (
        comparison.get("scope") == "teaching_window"
        and comparison.get("annual_economics_eligible") is False
        and comparison_gate.get("status") == "controlled"
        and not comparison_gate.get("violations")
        and {
            kind: values["declared"] for kind, values in row_dimensions.items()
        } == EXPECTED_COMPARISON_DIMENSIONS
        and {
            kind: values["actual"] for kind, values in row_dimensions.items()
        } == EXPECTED_COMPARISON_DIMENSIONS
    )
    if not controlled:
        _issue(issues, "UNCONTROLLED_COMPARISON", "The three-run teaching comparison changes an undeclared dimension.", row_dimensions)
    if comparison.get("annual_economics_eligible") is not False:
        _issue(issues, "TEACHING_ANNUALISED", "The comparison exposes teaching output as annual economics.", comparison.get("annual_economics_eligible"))

    try:
        declared_network = _load_network_verification(evidence)
        verified_network = _recompute_network_verification(evidence)
        if declared_network != verified_network:
            _issue(
                issues,
                "NETWORK_EVIDENCE_UNVERIFIED",
                "The saved network report does not match an independent recomputation from its declared Runs.",
                {
                    "declared_run_identity": declared_network.get("run_identity"),
                    "verified_run_identity": verified_network.get("run_identity"),
                },
            )
        network = dict(verified_network.get("network_accounting") or {})
        network_checks = verified_network.get("checks")
        network_decision_ok = (
            verified_network.get("decision") == "PASS"
            and isinstance(network_checks, Mapping)
            and bool(network_checks)
            and all(value is True for value in network_checks.values())
            and network_checks.get("actual_saved_runs_verified") is True
        )
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
        network = {}
        verified_network = {}
        network_decision_ok = False
        _issue(issues, "NETWORK_EVIDENCE_UNVERIFIED", "The network accounting report cannot be independently read.", str(exc))
    network_limits = {
        "energy_balance_residual_mwh": 1e-6,
        "soc_residual_mwh": 1e-6,
        "corridor_capacity_violation_mwh": 1e-6,
        "curtailment_identity_residual_mwh": 1e-6,
        "cost_residual_gbp": 1e-3,
    }
    network_ok = network_decision_ok and network.get("status") == "reconciled"
    for field, limit in network_limits.items():
        try:
            value = abs(float(network.get(field)))
        except (TypeError, ValueError):
            network_ok = False
            continue
        network_ok = network_ok and math.isfinite(value) and value <= limit
    if not network_ok:
        _issue(issues, "NETWORK_LEDGER_IMBALANCE", "The optional network lesson does not reconcile its declared ledgers.", dict(network))

    routes = api.get("routes") if isinstance(api.get("routes"), Mapping) else {}
    if not routes or not all(value is True for value in routes.values()):
        _issue(issues, "API_ROUTE_FAILED", "One or more installed VALUE 101 API routes failed.", dict(routes))
    declared_reset = evidence.get("reset_scope") if isinstance(evidence.get("reset_scope"), Mapping) else {}
    try:
        reset = _recompute_reset_scope()
        if dict(declared_reset) != reset:
            _issue(
                issues,
                "RESET_SCOPE_FAILED",
                "The declared reset report does not match a fresh loopback API verification.",
                {"declared": dict(declared_reset), "verified": reset},
            )
    except (OSError, ValueError, urllib.error.URLError) as exc:
        reset = {}
        _issue(issues, "RESET_SCOPE_FAILED", "The reset verifier could not execute.", str(exc))
    if (
        reset.get("passed") is not True
        or reset.get("api_exercised") is not True
        or reset.get("unrelated_state_unchanged") is not True
        or not reset.get("unrelated_tree_sha256_before")
        or reset.get("unrelated_tree_sha256_before")
        != reset.get("unrelated_tree_sha256_after")
        or not reset.get("trash_member_sha256")
    ):
        _issue(issues, "RESET_SCOPE_FAILED", "Teaching reset or installation isolation is not proven.", dict(reset))
    try:
        retained = _audit_retained_sources(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        retained = {"passed": False, "modified_files": [], "error": str(exc)}
    if retained.get("passed") is not True or retained.get("modified_files"):
        _issue(issues, "SCHEME_C_HASH_CHANGED", "Retained VALUE source hashes are not unchanged.", dict(retained))
    tests = evidence.get("test_evidence") if isinstance(evidence.get("test_evidence"), Mapping) else {}
    if not tests or not all(value is True for value in tests.values()):
        _issue(issues, "TEST_EVIDENCE_INCOMPLETE", "The declared software verification set is incomplete.", dict(tests))
    journey = evidence.get("clean_user_journey") if isinstance(evidence.get("clean_user_journey"), Mapping) else {}
    journey_ok = (
        journey.get("passed") is True
        and int(journey.get("mandatory_steps_completed") or 0) >= 7
        and float(journey.get("mandatory_elapsed_seconds") or math.inf) <= 1800
        and int(journey.get("developer_interventions") or 0) == 0
    )
    if not journey_ok:
        _issue(issues, "CLEAN_USER_JOURNEY_FAILED", "The mandatory clean-user route did not pass within 30 minutes.", dict(journey))
    return {
        "source_control": dict(source),
        "unexpected_dirty_paths": unexpected_dirty,
        "public_module_ids": public_ids,
        "public_ac_exposed": exposed,
        "scientific_boundary": dict(boundary),
        "comparison": dict(comparison),
        "network_verification": dict(verified_network),
        "network_accounting": dict(network),
        "api_routes": dict(routes),
        "reset_scope": dict(reset),
        "scheme_c_hashes": dict(retained),
        "test_evidence": dict(tests),
        "clean_user_journey": dict(journey),
    }


def audit_release(
    root: Path,
    installer: Path,
    evidence_path: Path,
    *,
    minimum_installer_bytes: int = 100 * 1024 * 1024,
    api_origin: str = "http://127.0.0.1:8766",
    api_state_root: Path | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    installer = Path(installer).resolve()
    evidence_path = Path(evidence_path).resolve()
    issues: list[dict[str, Any]] = []
    try:
        evidence = load_json(evidence_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        evidence = {}
        _issue(issues, "EVIDENCE_MISSING", "The machine-readable release evidence cannot be read.", str(exc))
    installer_report = _audit_installer(root, installer, issues, minimum_installer_bytes)
    product_report = _audit_product(root, issues)
    pack_report = _audit_packs(root, issues)
    evidence_report = _audit_evidence(root, evidence, issues, api_origin, api_state_root)
    blocking_codes = sorted({str(issue["code"]) for issue in issues})
    return {
        "schema_version": "value.101-release-audit/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_scope": "formal_value_windows_product",
        "decision": "GO" if not blocking_codes else "NO-GO",
        "release_gate_passed": not blocking_codes,
        "blocking_codes": blocking_codes,
        "issues": issues,
        "installer": installer_report,
        "product": product_report,
        "data_packs": pack_report,
        "evidence": evidence_report,
        "claim_boundary": (
            "Permission for the formal VALUE Windows product with bundled synthetic VALUE 101 teaching data; "
            "not a validated UK annual or ten-year scientific baseline."
        ),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    installer = report.get("installer") if isinstance(report.get("installer"), Mapping) else {}
    lines = [
        "# VALUE Windows product release-gate report",
        "",
        f"Decision: **{report.get('decision')}**",
        "",
        str(report.get("claim_boundary") or ""),
        "",
        "## Installer",
        "",
        f"- Path: `{installer.get('path')}`",
        f"- Bytes: `{installer.get('bytes')}`",
        f"- SHA-256: `{installer.get('sha256')}`",
        "",
        "## Blocking codes",
        "",
    ]
    codes = list(report.get("blocking_codes") or [])
    lines.extend([f"- `{code}`" for code in codes] or ["- None"])
    evidence = report.get("evidence") if isinstance(report.get("evidence"), Mapping) else {}
    journey = evidence.get("clean_user_journey") if isinstance(evidence.get("clean_user_journey"), Mapping) else {}
    lines.extend([
        "",
        "## Clean-user journey",
        "",
        f"- Passed: `{journey.get('passed')}`",
        f"- Mandatory elapsed seconds: `{journey.get('mandatory_elapsed_seconds')}`",
        f"- Developer interventions: `{journey.get('developer_interventions')}`",
        "",
        "## Evidence boundary",
        "",
        "This Markdown file renders the machine-readable report. It does not recalculate model or release evidence.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / "publication" / "prompt117-value-101-evidence.json",
    )
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--minimum-installer-bytes", type=int, default=100 * 1024 * 1024)
    parser.add_argument("--api-origin", default="http://127.0.0.1:8766")
    parser.add_argument("--api-data-home", type=Path, default=None,
                        help="VALUE_DATA_HOME of the probed API (its session file); default: this process's")
    args = parser.parse_args()
    report = audit_release(
        args.root,
        args.installer,
        args.evidence,
        minimum_installer_bytes=args.minimum_installer_bytes,
        api_origin=args.api_origin,
        api_state_root=args.api_data_home,
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "decision": report["decision"],
        "release_gate_passed": report["release_gate_passed"],
        "blocking_codes": report["blocking_codes"],
    }, ensure_ascii=False))
    return 0 if report["release_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
