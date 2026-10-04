"""Build reproducible VALUE wheel and source-distribution artifacts."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DATE_EPOCH = 1767225600  # 2026-01-01T00:00:00Z


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_sdist_archive(source: Path, destination: Path, *, epoch: int) -> None:
    """Rewrite an sdist with stable member order, metadata and gzip headers."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with tarfile.open(source, "r:gz") as incoming, temporary.open("wb") as raw:
        members = sorted(incoming.getmembers(), key=lambda item: item.name)
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=9,
            mtime=epoch,
        ) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as outgoing:
                for original in members:
                    member = copy.copy(original)
                    member.uid = 0
                    member.gid = 0
                    member.uname = ""
                    member.gname = ""
                    member.mtime = epoch
                    member.pax_headers = {}
                    handle = incoming.extractfile(original) if original.isfile() else None
                    outgoing.addfile(member, handle)
    temporary.replace(destination)


def build_release(outdir: Path, *, epoch: int = DEFAULT_SOURCE_DATE_EPOCH) -> dict[str, object]:
    outdir = outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(epoch)
    with tempfile.TemporaryDirectory(prefix="force-python-release-", dir=outdir.parent) as raw:
        staging = Path(raw)
        subprocess.run(
            [sys.executable, "-m", "build", "--outdir", str(staging)],
            cwd=ROOT,
            env=environment,
            check=True,
        )
        wheels = sorted(staging.glob("*.whl"))
        sdists = sorted(staging.glob("*.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            raise RuntimeError(
                f"Expected one wheel and one sdist; found {len(wheels)} wheel(s) "
                f"and {len(sdists)} sdist(s)"
            )
        wheel = outdir / wheels[0].name
        sdist = outdir / sdists[0].name
        shutil.copyfile(wheels[0], wheel)
        normalize_sdist_archive(sdists[0], sdist, epoch=epoch)
    artifacts = []
    for path in (wheel, sdist):
        artifacts.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return {
        "schema_version": "value.python-release-build/v1",
        "source_date_epoch": epoch,
        "artifacts": artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path, default=ROOT / "dist")
    parser.add_argument("--source-date-epoch", type=int, default=DEFAULT_SOURCE_DATE_EPOCH)
    arguments = parser.parse_args()
    print(
        json.dumps(
            build_release(arguments.outdir, epoch=arguments.source_date_epoch),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
