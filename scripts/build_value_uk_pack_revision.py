"""Build the GBP1 public2 data pack locally (P0-5b S11).  Nothing is uploaded.

``python -B scripts/build_value_uk_pack_revision.py --base GBP1_PUBLIC1 --approved R029_PUBLIC1 --out DIR
[--flow-evidence EVIDENCE.json] [--link copy|hardlink|symlink] [--check]``

public2 keeps every GBP1 public1 object byte-identical except the roles that
public1 reads wrongly (P6-02, P6-03, P6-04, P6-05): demand and the ten
interconnector roles are re-bound to the raw bytes of the author-approved
R029 objects (UTC demand pair, approved R03 interconnector chronology), whose
bindings already declare column, header, unit and the EUR/GBP basis.  The
builder adds the remaining declarations the corrected reader needs:

* ``interval_minutes`` 30 and ``currency`` GBP (with the R029 ``fx_basis``);
* ``time_convention`` of the ERA5 weather (ssrd accumulated to the end of the
  hour; 100 m wind instantaneous), used by weather v2 (P6-06);
* ``interval_minutes`` 60 of the three system-average VRE profiles (hourly
  ERA5 2022; ``sa.csv`` holds 8761 hourly values, one hour more than a year,
  which the declared clock recognises as hourly only when declared - FX7,
  decision A16-7: without it a strict reader refuses the series as short and
  a lenient one wraps it on the half-hour clock);
* ``flow_sign``: ``verified:positive_import`` only when an audit evidence of
  ``scripts/audit_boundary_flow_sign.py`` with ``verified: true`` names
  exactly the bound flow files' sha256; otherwise the R029 convention stays
  ``declared_unverified``.

Every source object is verified against its binding sha256 before it is
used.  The manifest is deterministic (sorted keys, no timestamps), so
``--check`` rebuilds into a temporary directory and compares the manifest
sha256 with ``--out``: equal twice means the build is reproducible.

Publishing public2 needs the author's consent (plan 4.5); this script never
uploads, and the pack id is new so no saved Study changes meaning.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

PACK_ID = "value-uk-open-data-pack-public2"
BUILDER = "scripts/build_value_uk_pack_revision.py@v2"
COUNTRIES = ("belgium", "france", "ireland", "netherlands", "norway")
REBOUND_ROLES = ("demand.real", "demand.forecast",
                 *[f"market.{c}.{kind}" for c in COUNTRIES for kind in ("profile", "price")])
UNVERIFIED_SIGN = "declared_unverified:LEGACY_MODEL_POSITIVE_IMPORT_NEGATIVE_EXPORT_NOT_SOURCE_VERIFIED"
VERIFIED_SIGN = "verified:positive_import"
WEATHER_CONVENTIONS = {"weather.solar": "accumulation_end_of_hour", "weather.wind": "instantaneous"}
# FX7 (A16-7): the hourly VRE investment profiles carry no interval declaration.
PROFILE_INTERVALS = {"profiles.vre_solar": 60, "profiles.vre_onshore": 60, "profiles.vre_offshore": 60}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified(pack: Path, binding: Mapping[str, Any], role: str) -> Path:
    path = pack / str(binding["uri"])
    observed = sha256(path)
    if observed != binding.get("sha256"):
        raise SystemExit(f"{role}: {path} sha256 {observed} differs from its binding {binding.get('sha256')}")
    return path


def _place(source: Path, target: Path, link: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    if link == "hardlink":
        os.link(source, target)
    elif link == "symlink":
        target.symlink_to(source.resolve())
    else:
        shutil.copyfile(source, target)


def _flow_sign(evidence: Mapping[str, Any] | None, country: str, flow_sha: str) -> tuple[str, dict[str, Any] | None]:
    if not evidence or not evidence.get("verified"):
        return UNVERIFIED_SIGN, None
    row = dict(evidence.get("countries", {}).get(country) or {})
    if row.get("consistent") and row.get("flow_sha256") == flow_sha:
        return VERIFIED_SIGN, {"audit_reference_sha256": evidence.get("reference_sha256"),
                               "audit_schema": evidence.get("schema_version")}
    return UNVERIFIED_SIGN, None


def build(base: Path, approved: Path, out: Path, *, link: str = "copy",
          flow_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    base_manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    approved_manifest = json.loads((approved / "manifest.json").read_text(encoding="utf-8"))
    if base_manifest.get("id") != "value-uk-open-data-pack-v1":
        raise SystemExit("--base must be GBP1 public1 (value-uk-open-data-pack-v1)")
    if approved_manifest.get("id") != "value-uk-calendar-vx-trade001":
        raise SystemExit("--approved must be R029 public1 (value-uk-calendar-vx-trade001)")
    out.mkdir(parents=True, exist_ok=True)
    bindings: dict[str, Any] = {}
    placed: dict[str, str] = {}

    def place(pack: Path, uri: str) -> str:
        source = pack / uri
        key = f"{pack.resolve()}::{uri}"
        if key not in placed:
            _place(source, out / uri, link)
            placed[key] = uri
        return uri

    for role, binding in sorted(base_manifest["bindings"].items()):
        if role in REBOUND_ROLES:
            continue
        _verified(base, binding, role)
        entry = copy.deepcopy(dict(binding))
        entry["uri"] = place(base, str(binding["uri"]))
        if role in WEATHER_CONVENTIONS:
            entry["time_convention"] = WEATHER_CONVENTIONS[role]
        if role in PROFILE_INTERVALS:
            entry["interval_minutes"] = PROFILE_INTERVALS[role]
        bindings[role] = entry
    fx_basis = str(approved_manifest["bindings"]["market.france.price"].get("source_version") or "")
    for role in REBOUND_ROLES:
        binding = dict(approved_manifest["bindings"][role])
        _verified(approved, binding, role)
        entry = copy.deepcopy(binding)
        entry["uri"] = place(approved, str(binding["uri"]))
        for key in [k for k in entry if k.endswith("_uri")]:
            entry[key] = place(approved, str(entry[key]))
        entry["interval_minutes"] = 30
        entry["rebound_from"] = {"pack_id": approved_manifest["id"], "role": role, "sha256": binding["sha256"],
                                 "public1_binding_sha256": dict(base_manifest["bindings"][role]).get("sha256")}
        if role.startswith("market."):
            country = role.split(".")[1]
            entry["currency"] = "GBP"
            entry["fx_basis"] = fx_basis
            if role.endswith(".profile"):
                sign, proof = _flow_sign(flow_evidence, country, binding["sha256"])
                entry["flow_sign"] = sign
                if proof:
                    entry["flow_sign_evidence"] = proof
        bindings[role] = entry
    signs = sorted({bindings[f"market.{c}.profile"]["flow_sign"] for c in COUNTRIES})
    manifest = {
        **{key: copy.deepcopy(value) for key, value in base_manifest.items() if key != "bindings"},
        "id": PACK_ID,
        "name": "VALUE UK open data pack - public revision 2 (GBP1 reading defects removed; local build)",
        "pack_class": "scientific_reference",
        "timezone": "UTC",
        "period_hours": 0.5,
        "periods_per_year": 17520,
        "derivation": {
            "builder": BUILDER,
            "parent_pack_id": base_manifest["id"],
            "parent_manifest_sha256": sha256(base / "manifest.json"),
            "approved_pack_id": approved_manifest["id"],
            "approved_manifest_sha256": sha256(approved / "manifest.json"),
            "rebound_roles": list(REBOUND_ROLES),
            "findings": ["P6-02", "P6-03", "P6-04", "P6-05", "P6-06"],
            "flow_sign_status": "verified" if signs == [VERIFIED_SIGN] else "not_source_verified",
            "publication": "local build only; publishing needs the author's consent",
        },
        "bindings": bindings,
    }
    text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (out / "manifest.json").write_text(text, encoding="utf-8")
    return {"pack_id": PACK_ID, "out": str(out), "manifest_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "flow_sign_status": manifest["derivation"]["flow_sign_status"], "files": len(placed)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--approved", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--flow-evidence", type=Path)
    parser.add_argument("--link", choices=("copy", "hardlink", "symlink"), default="copy")
    parser.add_argument("--check", action="store_true",
                        help="rebuild into a temporary directory and compare with the manifest in --out")
    arguments = parser.parse_args(argv)
    evidence = (json.loads(arguments.flow_evidence.read_text(encoding="utf-8"))
                if arguments.flow_evidence else None)
    if arguments.check:
        existing = arguments.out / "manifest.json"
        if not existing.is_file():
            raise SystemExit(f"--check needs an existing build in {arguments.out}")
        with tempfile.TemporaryDirectory(prefix="value-public2-check-") as temp:
            result = build(arguments.base, arguments.approved, Path(temp) / "pack", link="symlink",
                           flow_evidence=evidence)
        result["consistent"] = result["manifest_sha256"] == sha256(existing)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["consistent"] else 1
    print(json.dumps(build(arguments.base, arguments.approved, arguments.out, link=arguments.link,
                           flow_evidence=evidence), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
