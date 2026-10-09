"""Build the GBP1 public2 and R029 public2 data packs locally (P0-5b S11, A24-1).  Nothing is uploaded.

``python -B scripts/build_value_uk_pack_revision.py --base GBP1_PUBLIC1 --approved R029_PUBLIC1 --out DIR
[--flow-evidence EVIDENCE.json] [--link copy|hardlink|symlink] [--check]``

``python -B scripts/build_value_uk_pack_revision.py --pack r029-public2 --approved R029_PUBLIC1 --out DIR
[--link copy|hardlink|symlink] [--check]``

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
  ERA5 2022; FX7, decision A16-7: undeclared, the 8761-value ``sa.csv`` is
  refused as short by a strict reader and wrapped on the half-hour clock by a
  lenient one);
* the solar profile without its extra hour (decision A24-1, ``@v3``): the
  shared ``sa.csv`` (sha256 ``15ef49b3...578e``) holds 8761 values; rows
  0..8759 match the ERA5 2022 ssrd stamps 2022-01-01T00:00Z ..
  2022-12-31T23:00Z one to one and the last row (a night zero) is the stamp
  2023-01-01T00:00Z, the inclusive end of a 2022-01-01 .. 2023-01-01 slice
  (``scripts/audit_hourly_solar_profile.py``; evidence in
  ``docs/dev/p0-reports/r31-solar/sa_8761_evidence.json``).  The revised
  object is the first 8760 lines, byte for byte, and its binding records the
  dropped row (``row_revision``).  Every existing reading of the 8761-value
  file already uses only its first 8760 rows (the doctoral hourly repeat, the
  declared clock, the kernel's VRE-cap bisection, where the last row is a
  zero), so the revision changes no number; the public1 packs, and so the
  doctoral reading, are unchanged.
* ``flow_sign``: ``verified:positive_import`` only when an audit evidence of
  ``scripts/audit_boundary_flow_sign.py`` with ``verified: true`` names
  exactly the bound flow files' sha256; otherwise the R029 convention stays
  ``declared_unverified``.

Every source object is verified against its binding sha256 before it is
used.  The manifest is deterministic (sorted keys, no timestamps), so
``--check`` rebuilds into a temporary directory and compares the manifest
sha256 with ``--out``: equal twice means the build is reproducible.

R029 public2 (``--pack r029-public2``) is R029 public1 with that one object
revised and the three VRE profiles declared hourly; every other file is the
public1 file (linked or copied), and the manifest keeps the public1 fields
and adds a ``derivation``.

Publishing either revision needs the author's consent (plan 4.5); this
script never uploads, and the pack ids are new so no saved Study changes
meaning.
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
R029_PACK_ID = "value-uk-calendar-vx-trade001-public2"
GBP1_PUBLIC1_ID = "value-uk-open-data-pack-v1"
R029_PUBLIC1_ID = "value-uk-calendar-vx-trade001"
BUILDER = "scripts/build_value_uk_pack_revision.py@v3"
COUNTRIES = ("belgium", "france", "ireland", "netherlands", "norway")
REBOUND_ROLES = ("demand.real", "demand.forecast",
                 *[f"market.{c}.{kind}" for c in COUNTRIES for kind in ("profile", "price")])
UNVERIFIED_SIGN = "declared_unverified:LEGACY_MODEL_POSITIVE_IMPORT_NEGATIVE_EXPORT_NOT_SOURCE_VERIFIED"
VERIFIED_SIGN = "verified:positive_import"
WEATHER_CONVENTIONS = {"weather.solar": "accumulation_end_of_hour", "weather.wind": "instantaneous"}
# FX7 (A16-7): the hourly VRE investment profiles carry no interval declaration.
PROFILE_INTERVALS = {"profiles.vre_solar": 60, "profiles.vre_onshore": 60, "profiles.vre_offshore": 60}
# A24-1: source objects whose rows are revised, keyed by their sha256.  Each
# rule drops exactly the listed rows (0-based) after checking their text.
SOLAR_8761_SHA256 = "15ef49b3f46d07cad7eabc576d64e7764072a48b6ca4cabedc60149180e9578e"
ROW_REVISIONS: dict[str, dict[str, Any]] = {
    SOLAR_8761_SHA256: {
        "role": "profiles.vre_solar",
        "source_rows": 8761,
        "dropped_rows": [{"index": 8760, "line": 8761, "text": "0",
                          "era5_stamp_utc": "2023-01-01T00:00:00Z"}],
        "result_rows": 8760,
        "row_time_reference": ("row k is the ERA5 ssrd stamp 2022-01-01T00:00Z + k hours "
                               "(ssrd accumulated over the hour ending at the stamp)"),
        "reason": ("hourly ERA5 2022 profile with one extra row: rows 0..8759 match the ERA5 2022 stamps "
                   "2022-01-01T00:00Z..2022-12-31T23:00Z one to one (GB-mean ssrd correlation 0.956 at lag 0, "
                   "0.920/0.921 at lag -1/+1, lag 0 best in all 52 weeks, no daylight row at a dark stamp); the "
                   "last row (0) is the stamp 2023-01-01T00:00Z, the inclusive end of a 2022-01-01..2023-01-01 "
                   "slice, outside the 2022 stamps"),
        "evidence": "docs/dev/p0-reports/r31-solar/sa_8761_evidence.json",
        "decision": "A24-1",
    },
}


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


def revise_rows(source: Path, target: Path, rule: Mapping[str, Any]) -> dict[str, Any]:
    """Write ``source`` without the rule's rows, byte for byte otherwise; return the binding record."""

    data = source.read_bytes()
    lines = data.splitlines(keepends=True)
    if len(lines) != int(rule["source_rows"]):
        raise SystemExit(f"{source}: {len(lines)} rows, the revision rule expects {rule['source_rows']}")
    drop = {int(row["index"]): str(row["text"]) for row in rule["dropped_rows"]}
    for index, text in drop.items():
        observed = lines[index].decode("ascii").strip()
        if observed != text:
            raise SystemExit(f"{source}: row {index} is {observed!r}, the revision rule expects {text!r}")
    kept = [line for index, line in enumerate(lines) if index not in drop]
    if len(kept) != int(rule["result_rows"]) or not kept[-1].endswith(b"\n"):
        raise SystemExit(f"{source}: the revised object would not have {rule['result_rows']} terminated rows")
    payload = b"".join(kept)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    target.write_bytes(payload)
    return {
        "schema_version": "value.pack-row-revision/v1",
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "source_bytes": len(data),
        **{key: copy.deepcopy(value) for key, value in rule.items() if key != "role"},
    }


def _revised_binding(pack: Path, out: Path, role: str, binding: Mapping[str, Any]) -> dict[str, Any] | None:
    """The binding of a row-revised object (written into ``out``), or None when no rule applies."""

    rule = ROW_REVISIONS.get(str(binding.get("sha256") or ""))
    if rule is None or rule["role"] != role:
        return None
    uri = str(binding["uri"])
    record = revise_rows(_verified(pack, binding, role), out / uri, rule)
    entry = copy.deepcopy(dict(binding))
    entry["sha256"] = sha256(out / uri)
    entry["bytes"] = (out / uri).stat().st_size
    entry["row_revision"] = record
    entry["transformation"] = (f"{binding.get('transformation') or ''}; A24-1: row "
                               f"{rule['dropped_rows'][0]['line']} of {rule['source_rows']} (the ERA5 stamp "
                               f"{rule['dropped_rows'][0]['era5_stamp_utc']}) dropped").lstrip("; ")
    return entry


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
        entry = _revised_binding(base, out, role, binding)
        if entry is None:
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
            "row_revisions": sorted(role for role, entry in bindings.items() if "row_revision" in entry),
            "flow_sign_status": "verified" if signs == [VERIFIED_SIGN] else "not_source_verified",
            "publication": "local build only; publishing needs the author's consent",
        },
        "bindings": bindings,
    }
    text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (out / "manifest.json").write_text(text, encoding="utf-8")
    return {"pack_id": PACK_ID, "out": str(out), "manifest_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "flow_sign_status": manifest["derivation"]["flow_sign_status"], "files": len(placed)}


def build_r029(approved: Path, out: Path, *, link: str = "copy") -> dict[str, Any]:
    """R029 public2: R029 public1 with the solar profile's extra hour dropped and the VRE profiles declared hourly."""

    approved_manifest = json.loads((approved / "manifest.json").read_text(encoding="utf-8"))
    if approved_manifest.get("id") != R029_PUBLIC1_ID:
        raise SystemExit(f"--approved must be R029 public1 ({R029_PUBLIC1_ID})")
    out.mkdir(parents=True, exist_ok=True)
    bindings: dict[str, Any] = {}
    revised: set[str] = set()
    for role, binding in sorted(approved_manifest["bindings"].items()):
        _verified(approved, binding, role)
        entry = _revised_binding(approved, out, role, binding)
        if entry is None:
            entry = copy.deepcopy(dict(binding))
        else:
            revised.add(str(entry["uri"]))
        if role in PROFILE_INTERVALS:
            entry["interval_minutes"] = PROFILE_INTERVALS[role]
        bindings[role] = entry
    rule_roles = {rule["role"] for rule in ROW_REVISIONS.values()}
    if not revised or not rule_roles <= set(bindings):
        raise SystemExit("R029 public1 does not bind the 8761-row solar profile this revision removes a row from")
    # Every other file of the public1 tree is carried over unchanged (bound
    # objects, *_uri companions, audits, release evidence, attribution).
    files = 0
    for source in sorted(path for path in approved.rglob("*") if path.is_file() or path.is_symlink()):
        relative = source.relative_to(approved).as_posix()
        if relative == "manifest.json" or relative in revised:
            continue
        _place(source, out / relative, link)
        files += 1
    manifest = {
        **{key: copy.deepcopy(value) for key, value in approved_manifest.items() if key != "bindings"},
        "id": R029_PACK_ID,
        "name": f"{approved_manifest.get('name')} - revision 2 (hourly solar profile without its extra hour; local build)",
        "pack_class": "scientific_reference",
        "derivation": {
            "builder": BUILDER,
            "parent_pack_id": approved_manifest["id"],
            "parent_manifest_sha256": sha256(approved / "manifest.json"),
            "row_revisions": sorted(role for role, entry in bindings.items() if "row_revision" in entry),
            "declared_intervals": dict(sorted(PROFILE_INTERVALS.items())),
            "decisions": ["A24-1"],
            "unchanged": "every other object and file is the public1 object, byte for byte",
            "publication": "local build only; publishing needs the author's consent",
        },
        "bindings": bindings,
    }
    text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (out / "manifest.json").write_text(text, encoding="utf-8")
    return {"pack_id": R029_PACK_ID, "out": str(out), "manifest_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "files": files + len(revised)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pack", choices=("gbp1-public2", "r029-public2"), default="gbp1-public2")
    parser.add_argument("--base", type=Path, help="GBP1 public1 (gbp1-public2 only)")
    parser.add_argument("--approved", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--flow-evidence", type=Path)
    parser.add_argument("--link", choices=("copy", "hardlink", "symlink"), default="copy")
    parser.add_argument("--check", action="store_true",
                        help="rebuild into a temporary directory and compare with the manifest in --out")
    arguments = parser.parse_args(argv)
    if arguments.pack == "gbp1-public2" and arguments.base is None:
        parser.error("--base is required for --pack gbp1-public2")
    evidence = (json.loads(arguments.flow_evidence.read_text(encoding="utf-8"))
                if arguments.flow_evidence else None)

    def run(out: Path, link: str) -> dict[str, Any]:
        if arguments.pack == "r029-public2":
            return build_r029(arguments.approved, out, link=link)
        return build(arguments.base, arguments.approved, out, link=link, flow_evidence=evidence)

    if arguments.check:
        existing = arguments.out / "manifest.json"
        if not existing.is_file():
            raise SystemExit(f"--check needs an existing build in {arguments.out}")
        with tempfile.TemporaryDirectory(prefix="value-public2-check-") as temp:
            result = run(Path(temp) / "pack", "symlink")
        result["consistent"] = result["manifest_sha256"] == sha256(existing)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["consistent"] else 1
    print(json.dumps(run(arguments.out, arguments.link), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
