"""Build the private, versioned VALUE UK benchmark data release asset.

Only the 25 objects referenced by the pack manifest are included. Unbound
working files are deliberately excluded. Every bound object is checked against
its declared byte count and SHA-256 before any archive is promoted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile


FIXED_TIME = (2026, 8, 12, 0, 0, 0)
CHUNK = 1024 * 1024
METADATA_FILES = (
    "ATTRIBUTION.md",
    "SOURCE_REGISTER.md",
    "bill-of-data.json",
    "local-source-inventory.json",
    "policy-provenance.json",
    "semantic-preflight.json",
    "LOCAL_INSTALL.md",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def add_file(archive: zipfile.ZipFile, source: Path, member: str) -> None:
    info = zipfile.ZipInfo(member, FIXED_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o100644 << 16
    with source.open("rb") as reader, archive.open(info, "w", force_zip64=True) as writer:
        shutil.copyfileobj(reader, writer, CHUNK)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-root", type=Path, required=True)
    parser.add_argument("--metadata-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--release-id", default="value-uk-benchmark-2025-v1")
    args = parser.parse_args()

    pack_root = args.pack_root.resolve()
    metadata_root = args.metadata_root.resolve()
    manifest_path = pack_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    bindings = sorted(manifest["bindings"].values(), key=lambda item: item["role"])
    if len(bindings) != 25:
        raise SystemExit(f"Expected 25 interface bindings, found {len(bindings)}")

    records: list[dict[str, object]] = []
    sources: list[tuple[Path, str]] = []
    prefix = PurePosixPath(args.release_id)
    for binding in bindings:
        relative = PurePosixPath(binding["uri"])
        source = pack_root.joinpath(*relative.parts)
        actual_size = source.stat().st_size
        actual_hash = sha256(source)
        if actual_size != int(binding["bytes"]) or actual_hash != binding["sha256"]:
            raise SystemExit(f"Manifest mismatch for {binding['role']}: {relative}")
        member = str(prefix / relative)
        sources.append((source, member))
        records.append({
            "role": binding["role"],
            "member": member,
            "bytes": actual_size,
            "sha256": actual_hash,
            "unit": binding.get("unit"),
            "format": binding.get("format"),
        })

    sources.append((manifest_path, str(prefix / "manifest.json")))
    for name in METADATA_FILES:
        source = metadata_root / name
        if not source.is_file():
            raise SystemExit(f"Missing publication metadata: {source}")
        sources.append((source, str(prefix / "provenance" / name)))

    asset_manifest = {
        "schema_version": "value.uk-benchmark-asset/v1",
        "release_id": args.release_id,
        "source_pack_id": manifest["id"],
        "source_manifest_sha256": sha256(manifest_path),
        "interfaces": len(records),
        "bound_payload_bytes": sum(int(record["bytes"]) for record in records),
        "objects": records,
        "unbound_working_files_included": False,
    }
    manifest_bytes = (json.dumps(asset_manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=args.output.parent, suffix=".zip", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
            for source, member in sorted(sources, key=lambda item: item[1]):
                add_file(archive, source, member)
            info = zipfile.ZipInfo(str(prefix / "release-manifest.json"), FIXED_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, manifest_bytes)
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)

    sidecar = {
        **asset_manifest,
        "asset": {
            "filename": args.output.name,
            "bytes": args.output.stat().st_size,
            "sha256": sha256(args.output),
            "zip_integrity": "passed",
        },
    }
    with zipfile.ZipFile(args.output) as archive:
        bad = archive.testzip()
        if bad:
            raise SystemExit(f"ZIP integrity failure: {bad}")
    args.sidecar.parent.mkdir(parents=True, exist_ok=True)
    args.sidecar.write_text(
        json.dumps(sidecar, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(sidecar["asset"], indent=2))


if __name__ == "__main__":
    main()
