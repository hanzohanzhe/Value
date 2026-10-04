"""Install VALUE's redistributable built-in data packs into VALUE_DATA_HOME."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.runtime_paths import user_data_root  # noqa: E402


BUILTIN_PACK_IDS = (
    "value-synthetic-contract-pack-v1",
    "value-101-baseline-v1",
    "value-101-network-v1",
)
VALUE_101_PACK_IDS = (
    "value-101-baseline-v1",
    "value-101-network-v1",
)
UPGRADABLE_BUILTIN_TREES: dict[str, frozenset[str]] = {
    "value-101-network-v1": frozenset({
        # The released 48-period network teaching fixture superseded by the
        # full 2025-2026 clock. Only this exact bundled tree may be replaced.
        "754078f58b45130dcf4642f24d29f9d73641f256bb53913a2afa5103c791f6ed",
    }),
}


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _replace_known_builtin(
    source: Path,
    destination: Path,
    pack_id: str,
    expected_tree_sha256: str,
    backup_root: Path,
) -> Path:
    parent = destination.parent.resolve()
    owner_root = Path(tempfile.mkdtemp(
        prefix=f".{pack_id}.installing-",
        dir=parent,
    )).resolve()
    if owner_root.parent != parent:
        raise ValueError("Refusing unsafe built-in-pack staging path")
    temporary = owner_root / "payload"
    backup_parent = backup_root.resolve()
    backup_parent.mkdir(parents=True, exist_ok=True)
    backup = backup_parent / f"{pack_id}-{uuid.uuid4().hex}"
    try:
        shutil.copytree(source, temporary)
        destination.replace(backup)
        try:
            actual_tree_sha256 = _tree_sha256(backup)
            if actual_tree_sha256 != expected_tree_sha256:
                raise ValueError(
                    f"Built-in pack {pack_id} changed during staging; preserving it unchanged "
                    f"(expected {expected_tree_sha256}, observed {actual_tree_sha256})"
                )
            temporary.replace(destination)
        except BaseException:
            if not destination.exists() and backup.exists():
                backup.replace(destination)
            raise
    finally:
        if owner_root.exists():
            shutil.rmtree(owner_root)
    return backup


def install_builtin_packs(
    state_root: Path,
    *,
    pack_ids: tuple[str, ...] = BUILTIN_PACK_IDS,
) -> list[dict[str, str]]:
    """Install packs and upgrade only exact, allowlisted bundled revisions."""

    state_root = state_root.resolve()
    reports: list[dict[str, str]] = []
    for pack_id in pack_ids:
        source = ROOT / "data-packs" / pack_id
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("id") != pack_id:
            raise ValueError(f"Built-in source manifest identity is invalid: {pack_id}")
        destination = state_root / "data-packs" / pack_id
        if destination.is_dir():
            existing_path = destination / "manifest.json"
            if not existing_path.is_file():
                raise ValueError(f"A non-pack directory already occupies {destination}")
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
            existing_tree = _tree_sha256(destination)
            source_tree = _tree_sha256(source)
            if existing != manifest or existing_tree != source_tree:
                if existing_tree in UPGRADABLE_BUILTIN_TREES.get(pack_id, frozenset()):
                    backup = _replace_known_builtin(
                        source,
                        destination,
                        pack_id,
                        existing_tree,
                        state_root / "builtin-pack-backups" / "data-packs",
                    )
                    reports.append({
                        "pack_id": pack_id,
                        "status": "upgraded_builtin",
                        "destination": str(destination),
                        "previous_tree_sha256": existing_tree,
                        "installed_tree_sha256": source_tree,
                        "previous_revision_backup": str(backup),
                    })
                    continue
                reports.append({
                    "pack_id": pack_id,
                    "status": "conflict_preserved",
                    "destination": str(destination),
                    "bundled_source": str(source),
                    "message": (
                        "A different local revision already uses this pack ID. "
                        "The local revision and bundled source were both left unchanged."
                    ),
                })
                continue
            reports.append({
                "pack_id": pack_id,
                "status": "already_installed",
                "destination": str(destination),
            })
            continue
        if destination.exists():
            raise ValueError(f"A non-directory path already occupies {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".installing")
        resolved_parent = destination.parent.resolve()
        resolved_temporary = temporary.resolve()
        if (
            resolved_temporary.parent != resolved_parent
            or resolved_temporary.name != pack_id + ".installing"
        ):
            raise ValueError("Refusing unsafe built-in-pack staging path")
        if temporary.exists():
            shutil.rmtree(temporary)
        shutil.copytree(source, temporary)
        temporary.replace(destination)
        reports.append({
            "pack_id": pack_id,
            "status": "installed",
            "destination": str(destination),
        })
    if "value-101-network-v1" not in pack_ids:
        return reports
    source = ROOT / "data-packs" / "value-101-network-v1"
    destination = (
        state_root / "data-workbench" / "installed-packs" / "value-101-network-v1"
    )
    network_report = next(
        row for row in reports if row["pack_id"] == "value-101-network-v1"
    )
    if destination.is_dir():
        existing_tree = _tree_sha256(destination)
        source_tree = _tree_sha256(source)
        if not (destination / "manifest.json").is_file() or existing_tree != source_tree:
            if existing_tree in UPGRADABLE_BUILTIN_TREES.get(
                "value-101-network-v1", frozenset()
            ):
                backup = _replace_known_builtin(
                    source,
                    destination,
                    "value-101-network-v1",
                    existing_tree,
                    state_root / "builtin-pack-backups" / "network-overlays",
                )
                network_report["network_overlay_status"] = "upgraded_builtin"
                network_report["network_overlay_destination"] = str(destination)
                network_report["previous_overlay_tree_sha256"] = existing_tree
                network_report["previous_overlay_backup"] = str(backup)
            else:
                network_report["network_overlay_status"] = "conflict_preserved"
                network_report["network_overlay_destination"] = str(destination)
        else:
            network_report["network_overlay_status"] = "already_installed"
            network_report["network_overlay_destination"] = str(destination)
    elif destination.exists():
        raise ValueError(f"A non-directory path already occupies {destination}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".installing")
        expected_parent = destination.parent.resolve()
        if temporary.resolve().parent != expected_parent:
            raise ValueError("Refusing unsafe network-overlay staging path")
        if temporary.exists():
            shutil.rmtree(temporary)
        shutil.copytree(source, temporary)
        temporary.replace(destination)
        network_report["network_overlay_status"] = "installed"
        network_report["network_overlay_destination"] = str(destination)
    return reports


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, default=user_data_root())
    parser.add_argument(
        "--value-101-only",
        action="store_true",
        help="Install only the two CC0 VALUE 101 teaching packs.",
    )
    args = parser.parse_args()
    try:
        reports = install_builtin_packs(
            args.state_root,
            pack_ids=VALUE_101_PACK_IDS if args.value_101_only else BUILTIN_PACK_IDS,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    for report in reports:
        print(f"{report['pack_id']}: {report['status']} at {report['destination']}")


if __name__ == "__main__":
    main()
