"""Resolve a signed zonal overlay separately from the base research data pack."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .runtime_paths import user_data_root


_PACK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class ZonalPackSelection:
    base_pack_root: Path
    base_manifest: Mapping[str, object]
    network_pack_root: Path | None
    network_manifest: Mapping[str, object] | None
    network_pack_id: str | None

    @property
    def available_data_roles(self) -> tuple[str, ...]:
        roles = set(dict(self.base_manifest.get("bindings") or {}))
        if self.network_manifest is not None:
            roles.update(dict(self.network_manifest.get("bindings") or {}))
        return tuple(sorted(str(role) for role in roles))

    @property
    def revision_manifest(self) -> dict[str, object]:
        """Return a deterministic two-product identity for project fingerprints."""

        result = dict(self.base_manifest)
        bindings = dict(self.base_manifest.get("bindings") or {})
        if self.network_manifest is not None:
            bindings.update(dict(self.network_manifest.get("bindings") or {}))
            result["network_overlay"] = {
                "id": self.network_pack_id,
                "schema_version": self.network_manifest.get("schema_version"),
                "data_pack_type": self.network_manifest.get("data_pack_type"),
                "zonal_network_pack": self.network_manifest.get("zonal_network_pack"),
                "bindings": self.network_manifest.get("bindings"),
            }
        result["bindings"] = bindings
        return result


def _manifest(root: Path, label: str) -> dict[str, object]:
    path = root / "manifest.json"
    if not path.is_file():
        raise ValueError(f"{label} manifest is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} manifest cannot be read: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} manifest must contain one JSON object")
    return payload


def resolve_zonal_pack_selection(
    project: Mapping[str, object],
    *,
    base_pack_root: Path,
    base_manifest: Mapping[str, object] | None = None,
    explicit_network_pack_root: Path | None = None,
    data_home: Path | None = None,
) -> ZonalPackSelection:
    """Resolve the two-pack Study contract without embedding local paths in it."""

    base_root = Path(base_pack_root).resolve()
    resolved_base_manifest = (
        dict(base_manifest) if base_manifest is not None
        else _manifest(base_root, "Base data-pack")
    )
    modules = dict(project.get("modules") or {})
    zonal = str(modules.get("balancing") or "") == "value-zonal-redispatch-balancing"
    if not zonal:
        return ZonalPackSelection(base_root, resolved_base_manifest, None, None, None)

    extensions = {str(item) for item in project.get("selected_extensions", ())}
    if "value-zonal-redispatch-extension" not in extensions:
        raise ValueError(
            "Zonal balancing requires the value-zonal-redispatch-extension data contract"
        )
    configuration = dict(project.get("market_configuration") or {})
    network_pack_id = str(configuration.get("network_pack_id") or "")
    if not _PACK_ID.fullmatch(network_pack_id):
        raise ValueError("Zonal balancing requires a safe immutable network_pack_id")
    if explicit_network_pack_root is None:
        state_root = Path(data_home).resolve() if data_home is not None else user_data_root()
        network_root = (
            state_root / "data-workbench" / "installed-packs" / network_pack_id
        ).resolve()
        expected_parent = (state_root / "data-workbench" / "installed-packs").resolve()
        try:
            network_root.relative_to(expected_parent)
        except ValueError as exc:
            raise ValueError("Resolved network pack escapes the installed-pack store") from exc
        if not network_root.is_dir():
            raise ValueError(
                f"Signed network pack {network_pack_id!r} is not installed"
            )
    else:
        network_root = Path(explicit_network_pack_root).resolve()
    network_manifest = _manifest(network_root, "Network data-pack")
    actual_id = str(network_manifest.get("id") or "")
    if actual_id != network_pack_id:
        raise ValueError(
            f"Study network_pack_id {network_pack_id!r} does not match "
            f"the selected network manifest {actual_id!r}"
        )
    if network_manifest.get("data_pack_type") != "network_overlay":
        raise ValueError("The selected network pack is not a network_overlay data product")
    return ZonalPackSelection(
        base_root,
        resolved_base_manifest,
        network_root,
        network_manifest,
        network_pack_id,
    )
